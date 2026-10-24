"""
IncuBrix AI Video Generation Server for Google Colab
Model: THUDM/CogVideoX-2b (Open Source & Free)
Hardware Target: Google Colab Free Tier (Nvidia T4 GPU / 15GB VRAM)

This script loads CogVideoX-2b with memory optimizations and serves an HTTP API
compatible with IncuBrix Video B-Roll Engine's AIGeneratedMediaProvider.
"""

import os
import gc
import tempfile
from pathlib import Path
from typing import Optional

import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Initialize FastAPI application
app = FastAPI(
    title="IncuBrix CogVideoX-2B Video Generator",
    description="Free AI Text-to-Video generation backend powered by CogVideoX-2B",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global pipeline holder
pipeline = None
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
OUTPUT_DIR = Path("./generated_videos")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="Visual scene prompt for video generation")
    aspect_ratio: Optional[str] = Field(default="16:9", description="16:9, 9:16, or 1:1")
    duration_seconds: Optional[float] = Field(default=4.0, description="Target clip duration")
    num_inference_steps: Optional[int] = Field(default=30, description="Denoising steps (25-35 recommended)")
    guidance_scale: Optional[float] = Field(default=6.0, description="Classifier-free guidance scale")
    num_frames: Optional[int] = Field(default=49, description="Total video frames to generate (49 is CogVideoX native)")


def load_model():
    """Loads CogVideoX-2B with aggressive memory optimizations for Google Colab T4."""
    global pipeline
    if pipeline is not None:
        return pipeline

    from diffusers import CogVideoXPipeline
    from diffusers.utils import export_to_video

    print(f"[*] Initializing THUDM/CogVideoX-2b on device: {DEVICE}...")

    # Load in bfloat16 (or float16 if bfloat16 unsupported)
    torch_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    pipe = CogVideoXPipeline.from_pretrained(
        "THUDM/CogVideoX-2b",
        torch_dtype=torch_dtype
    )

    # VRAM Optimizations for Google Colab T4 (15GB VRAM ceiling):
    # 1. CPU offload moves model layers to RAM when not in use
    pipe.enable_model_cpu_offload()
    # 2. VAE tiling slices spatial dimensions to avoid VAE decode OOM
    pipe.vae.enable_tiling()
    # 3. VAE slicing processes frames in chunks
    pipe.vae.enable_slicing()

    print("[+] Model loaded and optimized successfully!")
    pipeline = pipe
    return pipeline


@app.on_event("startup")
async def startup_event():
    if torch.cuda.is_available():
        print(f"[+] CUDA detected: {torch.cuda.get_device_name(0)}")
        load_model()
    else:
        print("[!] WARNING: Running on CPU. Video generation will be slow without a GPU.")


@app.get("/health")
def health():
    """Health check endpoint polled by IncuBrix."""
    has_gpu = torch.cuda.is_available()
    vram_free_gb = 0.0
    if has_gpu:
        vram_free_gb = round(torch.cuda.mem_get_info()[0] / (1024 ** 3), 2)

    return {
        "status": "ready",
        "model": "THUDM/CogVideoX-2b",
        "device": DEVICE,
        "gpu_available": has_gpu,
        "vram_free_gb": vram_free_gb,
        "pipeline_loaded": pipeline is not None
    }


@app.post("/generate")
def generate_video(req: GenerateRequest):
    """
    Generates a 1080p-ready B-roll clip from prompt and streams MP4 bytes.
    """
    pipe = load_model()
    if pipe is None:
        raise HTTPException(status_code=500, detail="Video diffusion pipeline failed to initialize.")

    from diffusers.utils import export_to_video

    clean_prompt = req.prompt.strip()
    print(f"[*] Generating video for prompt: '{clean_prompt}'")
    print(f"    Steps: {req.num_inference_steps}, Guidance: {req.guidance_scale}, Frames: {req.num_frames}")

    try:
        # Run diffusion generation
        # CogVideoX-2b generates 49 frames natively at 8 fps (~6 seconds)
        with torch.inference_mode():
            video_frames = pipe(
                prompt=clean_prompt,
                num_videos_per_prompt=1,
                num_inference_steps=req.num_inference_steps,
                num_frames=req.num_frames or 49,
                guidance_scale=req.guidance_scale,
                generator=torch.Generator(device="cpu").manual_seed(42)
            ).frames[0]

        # Save to temporary MP4 file
        output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=OUTPUT_DIR)
        output_path = output_file.name
        output_file.close()

        # Export frames to MP4 video at 8 fps
        export_to_video(video_frames, output_path, fps=8)

        # Clear PyTorch CUDA cache
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        print(f"[+] Video successfully generated: {output_path} ({os.path.getsize(output_path)} bytes)")

        return FileResponse(
            path=output_path,
            media_type="video/mp4",
            filename="cogvideox_scene.mp4"
        )

    except Exception as exc:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print(f"[!] Error during generation: {exc}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(exc)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8003"))
    uvicorn.run(app, host="0.0.0.0", port=port)
