from pathlib import Path
from urllib.parse import urljoin
import httpx

from app.config import settings
from app.security import SecurityValidationError, validate_url_security


def download_audio_from_url(
    url_str: str,
    dest_path: Path,
    max_bytes: int = settings.MAX_AUDIO_FILE_SIZE_BYTES,
    timeout_seconds: float = settings.URL_FETCH_TIMEOUT_SECONDS
) -> dict:
    """
    Downloads audio from an external URL with redirect protection,
    SSRF validation at every redirect hop, and strict chunked size bounding.
    If an error occurs or size limit is breached, any partial file is immediately deleted.
    """
    current_url = validate_url_security(url_str)
    redirects = 0

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            while redirects <= settings.MAX_URL_REDIRECTS:
                with client.stream("GET", current_url) as response:
                    # Handle redirect
                    if response.is_redirect:
                        redirects += 1
                        if redirects > settings.MAX_URL_REDIRECTS:
                            raise SecurityValidationError("Too many redirects during audio download.", code="EXCESSIVE_REDIRECTS")
                        location = response.headers.get("Location")
                        if not location:
                            raise SecurityValidationError("Redirect response missing Location header.", code="INVALID_REDIRECT")
                        current_url = validate_url_security(urljoin(current_url, location))
                        continue

                    if response.status_code >= 400:
                        raise SecurityValidationError(
                            f"Remote server returned HTTP {response.status_code}.",
                            code="REMOTE_HTTP_ERROR"
                        )

                    # Check Content-Length header if available
                    cl_header = response.headers.get("Content-Length")
                    if cl_header and cl_header.isdigit():
                        if int(cl_header) > max_bytes:
                            raise SecurityValidationError(
                                f"Audio Content-Length ({cl_header} bytes) exceeds limit ({max_bytes} bytes).",
                                code="FILE_TOO_LARGE"
                            )

                    content_type = response.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()

                    # Stream into destination file
                    with open(dest_path, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            total_bytes += len(chunk)
                            if total_bytes > max_bytes:
                                raise SecurityValidationError(
                                    f"Audio download exceeded limit of {max_bytes} bytes.",
                                    code="FILE_TOO_LARGE"
                                )
                            f.write(chunk)

                    if total_bytes == 0:
                        raise SecurityValidationError("Downloaded audio file is empty (0 bytes).", code="EMPTY_FILE")

                    return {
                        "final_url": current_url,
                        "bytes_downloaded": total_bytes,
                        "content_type": content_type
                    }

            raise SecurityValidationError("Unable to download audio within redirect limits.", code="EXCESSIVE_REDIRECTS")
    except Exception:
        # Guarantee cleanup on failure
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        raise
