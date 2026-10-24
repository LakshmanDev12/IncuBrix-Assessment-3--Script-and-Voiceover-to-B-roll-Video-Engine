"""
CogVideoX-2B LoRA Fine-Tuning Script.
Optimized for Google Colab T4 / L4 and Consumer GPUs.

Uses Hugging Face Diffusers + PEFT to fine-tune CogVideoX-2B attention projection layers
on custom B-roll video datasets.
"""

import argparse
import math
import os
from pathlib import Path
import shutil

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from tqdm.auto import tqdm

from diffusers import (
    AutoencoderKLCogVideoX,
    CogVideoXDPMScheduler,
    CogVideoXTransformer3DModel,
)
from peft import LoraConfig, get_peft_model
from transformers import AutoTokenizer, T5EncoderModel

from dataset_prep import VideoCaptionDataset


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune CogVideoX-2B using LoRA on custom videos.")
    parser.add_argument(
        "--pretrained_model_name_or_path",
        type=str,
        default="THUDM/CogVideoX-2b",
        help="Path to pretrained model or model identifier from huggingface.co/models.",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        required=True,
        help="Folder containing input MP4 videos and matching .txt caption files.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="./cogvideox_lora_weights",
        help="Directory where the fine-tuned LoRA weights will be saved.",
    )
    parser.add_argument(
        "--lora_rank",
        type=int,
        default=16,
        help="The dimension of the LoRA update matrices.",
    )
    parser.add_argument(
        "--lora_alpha",
        type=int,
        default=32,
        help="LoRA scaling factor.",
    )
    parser.add_argument(
        "--train_batch_size",
        type=int,
        default=1,
        help="Batch size (per device) for the training dataloader. Keep 1 for T4 GPU.",
    )
    parser.add_argument(
        "--num_train_epochs",
        type=int,
        default=25,
        help="Total number of training epochs to perform.",
    )
    parser.add_argument(
        "--gradient_accumulation_steps",
        type=int,
        default=4,
        help="Number of update steps to accumulate before performing a backward/update pass.",
    )
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=1e-4,
        help="Initial learning rate (after warmup) to use.",
    )
    parser.add_argument(
        "--mixed_precision",
        type=str,
        default="bf16",
        choices=["no", "fp16", "bf16"],
        help="Whether to use mixed precision. Choose between fp16 and bf16.",
    )
    parser.add_argument(
        "--gradient_checkpointing",
        action="store_true",
        default=True,
        help="Whether or not to use gradient checkpointing to save memory at the expense of slower backward pass.",
    )
    parser.add_argument(
        "--num_frames",
        type=int,
        default=49,
        help="Number of frames sampled per video clip (49 is native CogVideoX).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] Starting CogVideoX-2B LoRA training on: {device}")

    weight_dtype = torch.float32
    if args.mixed_precision == "fp16":
        weight_dtype = torch.float16
    elif args.mixed_precision == "bf16":
        weight_dtype = torch.bfloat16

    # 1. Load Tokenizer & T5 Text Encoder (Frozen)
    print("[*] Loading Text Encoder...")
    tokenizer = AutoTokenizer.from_pretrained(args.pretrained_model_name_or_path, subfolder="tokenizer")
    text_encoder = T5EncoderModel.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="text_encoder",
        torch_dtype=weight_dtype
    ).to(device)
    text_encoder.eval()
    text_encoder.requires_grad_(False)

    # 2. Load CogVideoX 3D VAE (Frozen)
    print("[*] Loading 3D VAE...")
    vae = AutoencoderKLCogVideoX.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="vae",
        torch_dtype=weight_dtype
    ).to(device)
    vae.eval()
    vae.requires_grad_(False)
    vae.enable_tiling()
    vae.enable_slicing()

    # 3. Load Noise Scheduler
    scheduler = CogVideoXDPMScheduler.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="scheduler"
    )

    # 4. Load Transformer3D Model & Configure PEFT LoRA
    print("[*] Loading CogVideoXTransformer3DModel...")
    transformer = CogVideoXTransformer3DModel.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="transformer",
        torch_dtype=weight_dtype
    )

    if args.gradient_checkpointing:
        transformer.enable_gradient_checkpointing()

    # Configure LoRA targeting self-attention & cross-attention projections
    lora_config = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        init_lora_weights="gaussian",
        target_modules=["to_q", "to_k", "to_v", "to_out.0"],
    )
    transformer = get_peft_model(transformer, lora_config)
    transformer.to(device)
    transformer.print_trainable_parameters()

    # 5. Optimizer
    # Try 8-bit AdamW if bitsandbytes is installed for VRAM reduction
    try:
        import bitsandbytes as bnb
        optimizer = bnb.optim.AdamW8bit(
            transformer.parameters(),
            lr=args.learning_rate,
            weight_decay=1e-2
        )
        print("[+] Utilizing bitsandbytes 8-bit AdamW optimizer.")
    except ImportError:
        optimizer = torch.optim.AdamW(
            transformer.parameters(),
            lr=args.learning_rate,
            weight_decay=1e-2
        )
        print("[+] Utilizing standard PyTorch AdamW optimizer.")

    # 6. Dataloader
    dataset = VideoCaptionDataset(
        data_dir=args.data_dir,
        num_frames=args.num_frames,
        width=720,
        height=480
    )
    train_dataloader = DataLoader(
        dataset,
        batch_size=args.train_batch_size,
        shuffle=True,
        drop_last=True
    )

    total_steps = len(train_dataloader) * args.num_train_epochs
    print(f"[+] Dataset loaded with {len(dataset)} items. Training for {args.num_train_epochs} epochs ({total_steps} steps).")

    # 7. Training Loop
    transformer.train()
    progress_bar = tqdm(range(total_steps), desc="Fine-tuning LoRA")
    global_step = 0

    for epoch in range(args.num_train_epochs):
        epoch_loss = 0.0
        for step, batch in enumerate(train_dataloader):
            videos = batch["video"].to(device, dtype=weight_dtype)  # (B, C, F, H, W)
            prompts = batch["prompt"]

            with torch.no_grad():
                # Encode text prompt
                text_inputs = tokenizer(
                    prompts,
                    padding="max_length",
                    max_length=226,
                    truncation=True,
                    return_tensors="pt"
                ).to(device)
                prompt_embeds = text_encoder(text_inputs.input_ids)[0]

                # Encode video frames to latent space using VAE
                # CogVideoX VAE takes (B, C, F, H, W)
                latents = vae.encode(videos).latent_dist.sample()
                latents = latents * vae.config.scaling_factor

                # Sample noise and random timesteps
                noise = torch.randn_like(latents)
                timesteps = torch.randint(
                    0, scheduler.config.num_train_timesteps,
                    (latents.shape[0],),
                    device=device
                ).long()

                # Add noise according to scheduler
                noisy_latents = scheduler.add_noise(latents, noise, timesteps)

            # Predict the noise residual using LoRA-adapted Transformer
            model_pred = transformer(
                hidden_states=noisy_latents,
                encoder_hidden_states=prompt_embeds,
                timestep=timesteps,
                return_dict=False
            )[0]

            # Compute loss
            target = noise
            loss = F.mse_loss(model_pred.float(), target.float(), reduction="mean")
            loss = loss / args.gradient_accumulation_steps
            loss.backward()

            epoch_loss += loss.item() * args.gradient_accumulation_steps

            if (step + 1) % args.gradient_accumulation_steps == 0:
                torch.nn.utils.clip_grad_norm_(transformer.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad()
                progress_bar.update(1)
                global_step += 1
                progress_bar.set_postfix({"loss": f"{loss.item() * args.gradient_accumulation_steps:.4f}"})

        avg_loss = epoch_loss / len(train_dataloader)
        print(f"\n[Epoch {epoch+1}/{args.num_train_epochs}] Average Loss: {avg_loss:.5f}")

        # Save checkpoint periodically
        if (epoch + 1) % 5 == 0 or (epoch + 1) == args.num_train_epochs:
            ckpt_dir = Path(args.output_dir) / f"checkpoint-epoch-{epoch+1}"
            transformer.save_pretrained(ckpt_dir)
            print(f"[+] Saved LoRA checkpoint to: {ckpt_dir}")

    # 8. Final Save
    print(f"[*] Training finished! Saving final LoRA weights to: {args.output_dir}")
    transformer.save_pretrained(args.output_dir)
    print("\n=======================================================")
    print(" ✅ LoRA FINE-TUNING COMPLETE!")
    print(f" Weights saved at: {os.path.abspath(args.output_dir)}")
    print(" You can load these weights into CogVideoXPipeline using:")
    print(f'   pipe.load_lora_weights("{args.output_dir}")')
    print("=======================================================\n")


if __name__ == "__main__":
    main()
