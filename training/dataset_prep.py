"""
Dataset Preparation Utility for CogVideoX-2B LoRA Training.

Prepares video-text pairs from a directory of MP4 video clips and captions.
Accepts either:
  1. A folder containing pairs of `video_01.mp4` and `video_01.txt`
  2. A metadata JSON file mapping video filenames to prompts
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import torch
from torch.utils.data import Dataset
import torchvision.transforms as T
from PIL import Image


class VideoCaptionDataset(Dataset):
    """
    Loads video clips and corresponding text prompts for CogVideoX LoRA training.
    """

    def __init__(
        self,
        data_dir: str,
        num_frames: int = 49,
        width: int = 720,
        height: int = 480,
        metadata_file: Optional[str] = None
    ):
        self.data_dir = Path(data_dir)
        self.num_frames = num_frames
        self.width = width
        self.height = height
        self.samples: List[Dict[str, str]] = []

        self._load_samples(metadata_file)

        # Video frame transform
        self.transform = T.Compose([
            T.Resize((height, width), antialias=True),
            T.ToTensor(),
            T.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),  # [-1, 1] range
        ])

    def _load_samples(self, metadata_file: Optional[str]):
        if metadata_file and Path(metadata_file).exists():
            with open(metadata_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    vpath = self.data_dir / item["video"]
                    if vpath.exists():
                        self.samples.append({
                            "video_path": str(vpath),
                            "prompt": item["prompt"]
                        })
        else:
            # Pair .mp4 with .txt in same directory
            for vid in sorted(self.data_dir.glob("*.mp4")):
                txt_path = vid.with_suffix(".txt")
                if txt_path.exists():
                    prompt = txt_path.read_text(encoding="utf-8").strip()
                else:
                    # Fallback to sanitized filename
                    prompt = vid.stem.replace("_", " ").replace("-", " ")
                self.samples.append({
                    "video_path": str(vid),
                    "prompt": prompt
                })

        print(f"[+] Loaded {len(self.samples)} video-caption samples from {self.data_dir}")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        sample = self.samples[idx]
        video_path = sample["video_path"]
        prompt = sample["prompt"]

        frames = self._read_video_frames(video_path)

        # Process frames into tensor (F, C, H, W)
        transformed_frames = torch.stack([self.transform(f) for f in frames])

        # CogVideoX expects (C, F, H, W) format
        video_tensor = transformed_frames.permute(1, 0, 2, 3)

        return {
            "video": video_tensor,
            "prompt": prompt
        }

    def _read_video_frames(self, video_path: str) -> List[Image.Image]:
        """Reads evenly spaced frames from video file."""
        import cv2

        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames <= 0:
            cap.release()
            # Return dummy blank frames if video read fails
            return [Image.new("RGB", (self.width, self.height), (0, 0, 0)) for _ in range(self.num_frames)]

        # Determine indices to sample exactly self.num_frames
        indices = torch.linspace(0, total_frames - 1, self.num_frames).long().tolist()
        indices_set = set(indices)

        frames = []
        frame_idx = 0
        while cap.isOpened() and len(frames) < self.num_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx in indices_set:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(Image.fromarray(rgb_frame))
            frame_idx += 1

        cap.release()

        # If video had fewer frames than required, pad by looping last frame
        while len(frames) < self.num_frames:
            frames.append(frames[-1] if frames else Image.new("RGB", (self.width, self.height), (0, 0, 0)))

        return frames[:self.num_frames]
