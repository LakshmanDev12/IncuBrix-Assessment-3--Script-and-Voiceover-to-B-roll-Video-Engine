#!/usr/bin/env python3
"""
Batch Runner CLI for IncuBrix Video B-Roll Engine
Executes a batch of test input scripts or files against the running API
and writes all deliverables into a specified destination folder.

Usage:
    python batch_runner.py --input-dir tests/fixtures/batch_inputs --output-dir output/batch_results
    python batch_runner.py --input tests/fixtures/sample_story.json --output-dir output/batch_results
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List
import urllib.request
import urllib.error
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_runner")


def check_api_health(api_base: str) -> bool:
    """Verifies that the API server is reachable."""
    endpoints = [f"{api_base}/health/live", f"{api_base}/ready", f"{api_base}/health"]
    for ep in endpoints:
        try:
            req = urllib.request.Request(ep, headers={"User-Agent": "BatchRunner/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 202):
                    return True
        except Exception:
            continue
    return False


def submit_job(api_base: str, payload: Dict[str, Any]) -> str:
    """Submits a job payload to the API and returns the job_id."""
    endpoints = [f"{api_base}/api/v1/jobs", f"{api_base}/v1/jobs"]
    idempotency_key = f"batch-{uuid.uuid4()}"
    data_bytes = json.dumps(payload).encode("utf-8")

    last_error = None
    for ep in endpoints:
        try:
            req = urllib.request.Request(
                ep,
                data=data_bytes,
                headers={
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                    "User-Agent": "BatchRunner/1.0"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201, 202):
                    res_json = json.loads(resp.read().decode("utf-8"))
                    return res_json["job_id"]
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"Failed to submit job to API: {last_error}")


def poll_job_completion(api_base: str, job_id: str, timeout_seconds: int = 180) -> Dict[str, Any]:
    """Polls job status until terminal state (completed, failed, cancelled)."""
    endpoints = [f"{api_base}/api/v1/jobs/{job_id}", f"{api_base}/v1/jobs/{job_id}"]
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        for ep in endpoints:
            try:
                req = urllib.request.Request(ep, headers={"User-Agent": "BatchRunner/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        status = data.get("status")
                        progress = data.get("progress_pct", 0)
                        logger.info(f"Job {job_id[:8]} -> status: {status} ({progress}%)")
                        if status in ("completed", "failed", "cancelled"):
                            return data
            except Exception:
                pass
        time.sleep(2.0)

    raise TimeoutError(f"Job {job_id} exceeded poll timeout of {timeout_seconds}s")


def download_artifact(api_base: str, job_id: str, artifact_name: str, dest_path: Path):
    """Downloads an artifact file from the API."""
    endpoints = [
        f"{api_base}/api/v1/jobs/{job_id}/artifacts/{artifact_name}",
        f"{api_base}/v1/jobs/{job_id}/artifacts/{artifact_name}",
        f"{api_base}/output/{job_id}/{artifact_name}"
    ]
    for ep in endpoints:
        try:
            req = urllib.request.Request(ep, headers={"User-Agent": "BatchRunner/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest_path, "wb") as f:
                        f.write(resp.read())
                    return True
        except Exception:
            continue
    return False


def load_input_file(file_path: Path) -> Dict[str, Any]:
    """Loads JSON or TXT script input into a standard job payload."""
    if file_path.suffix.lower() == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        # Text file
        text = file_path.read_text(encoding="utf-8").strip()
        title = file_path.stem.replace("_", " ").title()
        return {
            "title": title,
            "aspect_ratio": "16:9",
            "resolution": "1080p",
            "scenes": [
                {
                    "narration": text[:200],
                    "duration_seconds": 4.0,
                    "visual_description": f"Visual representing {title}"
                }
            ]
        }


def main():
    parser = argparse.ArgumentParser(description="Batch Runner for Video B-Roll Engine")
    parser.add_argument("--input", "-i", type=str, help="Path to single input JSON/TXT file")
    parser.add_argument("--input-dir", "-d", type=str, help="Directory containing multiple input files")
    parser.add_argument("--output-dir", "-o", type=str, default="output/batch_results", help="Directory to save output videos")
    parser.add_argument("--api-url", "-u", type=str, default="http://localhost:8002", help="Base URL of running API")
    args = parser.parse_args()

    # Collect input files
    input_files: List[Path] = []
    if args.input:
        p = Path(args.input)
        if p.exists():
            input_files.append(p)
        else:
            logger.error(f"Input file not found: {p}")
            sys.exit(1)
    elif args.input_dir:
        dir_path = Path(args.input_dir)
        if dir_path.is_dir():
            input_files = sorted(list(dir_path.glob("*.json")) + list(dir_path.glob("*.txt")))
        else:
            logger.error(f"Input directory not found: {dir_path}")
            sys.exit(1)
    else:
        # Default fallback sample
        sample_path = Path("tests/fixtures/sample_story.json")
        if sample_path.exists():
            input_files.append(sample_path)
        else:
            logger.info("No input specified. Creating default batch demo payload...")
            temp_demo = Path("output/temp_batch_demo.json")
            temp_demo.parent.mkdir(parents=True, exist_ok=True)
            temp_demo.write_text(json.dumps({
                "title": "Batch Runner Test",
                "aspect_ratio": "16:9",
                "resolution": "1080p",
                "scenes": [
                    {
                        "narration": "Batch processing automated video generation.",
                        "duration_seconds": 3.5,
                        "visual_description": "Data center servers with flashing LEDs"
                    }
                ]
            }), encoding="utf-8")
            input_files.append(temp_demo)

    logger.info(f"Found {len(input_files)} input file(s) to process.")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Health check
    if not check_api_health(args.api_url):
        # Also try port 8000
        alt_url = "http://localhost:8000"
        if check_api_health(alt_url):
            args.api_url = alt_url
        else:
            logger.warning(f"Could not reach API at {args.api_url}. Please ensure server is running.")

    logger.info(f"Target API: {args.api_url}")
    results = []

    for idx, inp in enumerate(input_files, 1):
        logger.info(f"[{idx}/{len(input_files)}] Processing {inp.name}...")
        try:
            payload = load_input_file(inp)
            job_id = submit_job(args.api_url, payload)
            logger.info(f"Job enqueued: {job_id}")

            final_state = poll_job_completion(args.api_url, job_id)
            if final_state.get("status") == "completed":
                job_out_dir = out_dir / job_id
                job_out_dir.mkdir(parents=True, exist_ok=True)
                download_artifact(args.api_url, job_id, "video.mp4", job_out_dir / "video.mp4")
                download_artifact(args.api_url, job_id, "captions.srt", job_out_dir / "captions.srt")
                download_artifact(args.api_url, job_id, "manifest.json", job_out_dir / "manifest.json")
                results.append({"file": inp.name, "job_id": job_id, "status": "SUCCESS", "output": str(job_out_dir)})
            else:
                results.append({"file": inp.name, "job_id": job_id, "status": "FAILED", "error": final_state.get("error")})
        except Exception as e:
            logger.error(f"Error processing {inp.name}: {e}")
            results.append({"file": inp.name, "status": "ERROR", "error": str(e)})

    print("\n================== BATCH EXECUTION SUMMARY ==================")
    for r in results:
        status_str = r.get("status")
        print(f"File: {r['file']:<25} | Status: {status_str:<8} | Output: {r.get('output', r.get('error', 'N/A'))}")
    print("=============================================================\n")


if __name__ == "__main__":
    main()
