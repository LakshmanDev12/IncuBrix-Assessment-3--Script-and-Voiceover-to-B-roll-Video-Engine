# 🚀 Fine-Tuning CogVideoX-2B with LoRA for IncuBrix

This folder contains a complete, free workflow for fine-tuning the open-source **CogVideoX-2B** video generation model on custom video clips and text captions using Hugging Face **Diffusers + PEFT**.

---

## 📁 1. Dataset Preparation

Place your custom video clips and captions in a single folder, e.g. `./my_dataset`:

```
my_dataset/
├── clip_01.mp4
├── clip_01.txt       # "Cinematic slow motion drone shot of modern tech office building"
├── clip_02.mp4
├── clip_02.txt       # "Futuristic glowing AI brain network data visualization"
└── ...
```

*Tip: If `.txt` files are omitted, the filename itself (e.g. `tech_office.mp4` -> "tech office") will be used as the prompt.*

---

## ⚡ 2. Environment Setup

Install the required dependencies:

```bash
pip install -r requirements.txt
```

---

## 🏋️ 3. Run LoRA Training

Execute the training script:

```bash
python train_cogvideox_lora.py \
    --pretrained_model_name_or_path "THUDM/CogVideoX-2b" \
    --data_dir "./my_dataset" \
    --output_dir "./cogvideox_lora_weights" \
    --lora_rank 16 \
    --lora_alpha 32 \
    --num_train_epochs 25 \
    --gradient_accumulation_steps 4 \
    --learning_rate 1e-4 \
    --mixed_precision "bf16"
```

### Memory Optimization Highlights:
- **LoRA rank 16:** Targets attention projection matrices (`to_q`, `to_k`, `to_v`, `to_out.0`) so only ~0.5% of model weights are trained.
- **Gradient Checkpointing:** Keeps VRAM usage under 15 GB, fitting within free Google Colab T4 / L4 environments.
- **bitsandbytes 8-bit AdamW:** Reduces optimizer state memory by 75%.

---

## 🔌 4. Deploying Your LoRA to IncuBrix

Once training is complete, load your custom weights into the Colab inference server (`colab/server.py`):

```python
pipe = CogVideoXPipeline.from_pretrained("THUDM/CogVideoX-2b", torch_dtype=torch.bfloat16)
# Load your fine-tuned LoRA weights:
pipe.load_lora_weights("./cogvideox_lora_weights")
```

Now, every time IncuBrix requests a video clip for that style or domain, CogVideoX will generate videos tailored to your dataset!
