import ipaddress
import os
from pathlib import Path
import re
import socket
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.config import settings

FORBIDDEN_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254"
}

CLOUD_METADATA_IPS = {
    "169.254.169.254",   # AWS / GCP / Azure IMDS
    "100.100.100.200",   # Alibaba IMDS
    "fd00:ec2::254"      # AWS IPv6 IMDS
}


class SecurityValidationError(ValueError):
    """Raised when security boundaries (SSRF, path traversal, bounded limits) are violated."""
    def __init__(self, message: str, code: str = "SECURITY_VIOLATION"):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_url_syntax(url_str: str) -> Tuple[str, str]:
    """Validates basic URL syntax and ensures scheme is permitted."""
    if not url_str or not isinstance(url_str, str):
        raise SecurityValidationError("URL must be a non-empty string.", code="INVALID_URL")
    
    url_str = url_str.strip()
    try:
        parsed = urlparse(url_str)
    except Exception as exc:
        raise SecurityValidationError(f"Malformed URL: {exc}", code="MALFORMED_URL")

    if parsed.scheme.lower() not in settings.ALLOWED_URL_SCHEMES:
        raise SecurityValidationError(
            f"Scheme '{parsed.scheme}' is not permitted. Only HTTP/HTTPS URLs are allowed.",
            code="FORBIDDEN_SCHEME"
        )

    if not parsed.netloc or not parsed.hostname:
        raise SecurityValidationError("URL must include a valid hostname.", code="MISSING_HOSTNAME")

    if parsed.username or parsed.password:
        raise SecurityValidationError("Embedded credentials in URLs are prohibited.", code="FORBIDDEN_CREDENTIALS")

    return parsed.hostname.lower(), url_str


def validate_ip_address(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Checks an IP address against loopback, private, link-local, multicast, and cloud metadata blocks."""
    ip_str = str(ip_obj)
    if ip_str in CLOUD_METADATA_IPS:
        raise SecurityValidationError(f"Target IP {ip_str} is a protected cloud metadata address.", code="SSRF_METADATA_ATTEMPT")

    if settings.ALLOW_PRIVATE_NETWORKS:
        return

    if ip_obj.is_loopback:
        raise SecurityValidationError(f"Target IP {ip_str} is a loopback address (localhost).", code="SSRF_LOOPBACK_ATTEMPT")
    
    if ip_obj.is_private:
        raise SecurityValidationError(f"Target IP {ip_str} belongs to a private network.", code="SSRF_PRIVATE_IP_ATTEMPT")

    if ip_obj.is_link_local:
        raise SecurityValidationError(f"Target IP {ip_str} is a link-local address.", code="SSRF_LINK_LOCAL_ATTEMPT")

    if ip_obj.is_multicast:
        raise SecurityValidationError(f"Target IP {ip_str} is a multicast address.", code="SSRF_MULTICAST_ATTEMPT")

    if ip_obj.is_reserved:
        raise SecurityValidationError(f"Target IP {ip_str} is a reserved address.", code="SSRF_RESERVED_IP_ATTEMPT")

    if ip_obj.is_unspecified:
        raise SecurityValidationError(f"Target IP {ip_str} is an unspecified address.", code="SSRF_UNSPECIFIED_IP_ATTEMPT")


def validate_target_host(hostname: str) -> None:
    """Resolves DNS and verifies all resolved IP addresses are safe from SSRF."""
    hostname_clean = hostname.rstrip(".").lower()

    if hostname_clean in FORBIDDEN_HOSTNAMES or hostname_clean.endswith(".localhost") or hostname_clean.endswith(".internal"):
        raise SecurityValidationError(f"Access to '{hostname}' is blocked.", code="SSRF_FORBIDDEN_HOSTNAME")

    # If hostname is a literal IP
    try:
        ip_obj = ipaddress.ip_address(hostname_clean)
        validate_ip_address(ip_obj)
        return
    except ValueError:
        pass  # Not a literal IP, proceed to DNS resolution

    try:
        addr_info = socket.getaddrinfo(hostname_clean, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SecurityValidationError(f"Could not resolve hostname '{hostname_clean}': {exc}", code="DNS_RESOLUTION_FAILURE")

    resolved_ips = set()
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        resolved_ips.add(ip_str)

    if not resolved_ips:
        raise SecurityValidationError(f"No IP addresses resolved for hostname '{hostname_clean}'.", code="DNS_RESOLUTION_FAILURE")

    for ip_str in resolved_ips:
        ip_obj = ipaddress.ip_address(ip_str)
        validate_ip_address(ip_obj)


def validate_url_security(url_str: str) -> str:
    """Combines syntax validation and DNS/IP validation to ensure the URL is safe for external retrieval."""
    hostname, clean_url = validate_url_syntax(url_str)
    validate_target_host(hostname)
    return clean_url


WINDOWS_RESERVED_NAMES = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$",
    re.IGNORECASE
)


def validate_safe_filename(base_dir: Path, requested_filename: str) -> Path:
    """
    Guards against directory traversal, Windows device names, alternate data streams,
    hidden files, and blacklisted internal state files.
    """
    if not requested_filename or not isinstance(requested_filename, str):
        raise SecurityValidationError("Invalid filename: filename cannot be empty.", code="INVALID_FILENAME")

    filename_clean = requested_filename.strip()

    # Directory traversal sequence check and null bytes
    if ".." in filename_clean or "/" in filename_clean or "\\" in filename_clean or "\x00" in filename_clean:
        raise SecurityValidationError("Invalid filename: directory traversal sequence detected.", code="PATH_TRAVERSAL_ATTEMPT")

    # Windows Alternate Data Stream (ADS) check (e.g. file.txt:stream)
    if ":" in filename_clean:
        raise SecurityValidationError("Invalid filename: alternate data stream separator ':' is not permitted.", code="FORBIDDEN_FILE_ACCESS")

    # Hidden / dotfiles check
    if filename_clean.startswith("."):
        raise SecurityValidationError("Access denied: hidden or dotfiles are not accessible.", code="FORBIDDEN_FILE_ACCESS")

    # Windows reserved device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    if WINDOWS_RESERVED_NAMES.match(filename_clean):
        raise SecurityValidationError(f"Access denied: '{filename_clean}' is a reserved system device name.", code="FORBIDDEN_FILE_ACCESS")

    # Blacklisted internal state or application files
    if filename_clean.lower() in {f.lower() for f in settings.FORBIDDEN_FILENAMES}:
        raise SecurityValidationError(f"Access denied: '{filename_clean}' is an internal system file.", code="FORBIDDEN_FILE_ACCESS")

    safe_path = (base_dir / filename_clean).resolve()
    base_resolved = base_dir.resolve()

    if base_resolved not in safe_path.parents and safe_path != base_resolved:
        raise SecurityValidationError("Access denied: path escapes target directory.", code="PATH_TRAVERSAL_ATTEMPT")

    return safe_path


def probe_and_validate_audio_url(url_str: str) -> dict:
    """
    Safely probes an audio URL with redirect tracking, ensuring each redirect target is SSRF-safe,
    and verifying size limits and content-type before initiating full download.
    """
    current_url = validate_url_security(url_str)
    redirects = 0

    with httpx.Client(timeout=settings.URL_FETCH_TIMEOUT_SECONDS, follow_redirects=False) as client:
        while redirects <= settings.MAX_URL_REDIRECTS:
            try:
                response = client.head(current_url)
                if response.status_code in (405, 501):
                    # HEAD not allowed, use GET with Range 0-0
                    response = client.get(current_url, headers={"Range": "bytes=0-0"})
            except httpx.RequestError as exc:
                raise SecurityValidationError(f"Network error probing URL: {exc}", code="URL_NETWORK_ERROR")

            # Check redirect
            if response.is_redirect:
                redirects += 1
                if redirects > settings.MAX_URL_REDIRECTS:
                    raise SecurityValidationError("Too many redirects.", code="EXCESSIVE_REDIRECTS")
                location = response.headers.get("Location")
                if not location:
                    raise SecurityValidationError("Redirect response missing Location header.", code="INVALID_REDIRECT")
                # Validate redirect target
                from urllib.parse import urljoin
                current_url = validate_url_security(urljoin(current_url, location))
                continue

            if response.status_code >= 400:
                raise SecurityValidationError(
                    f"Remote audio server returned HTTP error {response.status_code}.",
                    code="REMOTE_HTTP_ERROR"
                )

            # Validate Content-Length if present
            content_length_header = response.headers.get("Content-Length")
            content_length = int(content_length_header) if content_length_header and content_length_header.isdigit() else None
            if content_length and content_length > settings.MAX_AUDIO_FILE_SIZE_BYTES:
                raise SecurityValidationError(
                    f"Audio file size ({content_length} bytes) exceeds maximum permitted limit ({settings.MAX_AUDIO_FILE_SIZE_BYTES} bytes).",
                    code="FILE_TOO_LARGE"
                )

            # Check Content-Type or path extension
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            url_path = urlparse(current_url).path.lower()
            has_valid_extension = any(url_path.endswith(ext) for ext in settings.ALLOWED_AUDIO_EXTENSIONS)
            is_valid_mime = content_type in settings.ALLOWED_AUDIO_MIME_TYPES

            if not is_valid_mime and not has_valid_extension and content_type not in ("application/octet-stream", "binary/octet-stream"):
                raise SecurityValidationError(
                    f"Unsupported content type '{content_type}'. Must be a supported audio format.",
                    code="UNSUPPORTED_MEDIA_TYPE"
                )

            return {
                "validated_url": current_url,
                "content_length": content_length,
                "content_type": content_type or "audio/mpeg"
            }

    raise SecurityValidationError("Unable to validate audio URL within redirect limits.", code="EXCESSIVE_REDIRECTS")
