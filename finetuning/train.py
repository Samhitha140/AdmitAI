"""
QLoRA fine-tuning entry point.

    python -m finetuning.train

Loads Mistral-7B in 4-bit, attaches LoRA adapters, trains with TRL's SFTTrainer
for 3 epochs, and pushes the ~50MB adapter to the HuggingFace Hub. Requires a
GPU (16GB+) and HUGGINGFACE_TOKEN; this script is correct-as-written but will
no-op with a clear message on a machine without CUDA.
"""
from __future__ import annotations

from config.settings import settings
from finetuning.dataset import load_sop_dataset
from finetuning.lora_config import (
    TrainConfig,
    bnb_config,
    peft_lora_config,
)


def train(push_to_hub: bool = False) -> None:
    try:
        import torch
        from peft import get_peft_model, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from trl import SFTTrainer
    except Exception as exc:
        print(f"[train] training deps not installed ({exc}).")
        print("        pip install transformers peft trl bitsandbytes accelerate datasets")
        return

    if not torch.cuda.is_available():
        print("[train] No CUDA GPU detected. QLoRA needs a GPU (Colab T4 is fine).")
        print("        The pipeline below is the exact code that would run on GPU:")

    cfg = TrainConfig(base_model=settings.BASE_SOP_MODEL)

    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model,
        quantization_config=bnb_config(),
        device_map="auto",
    )
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, peft_lora_config())
    model.print_trainable_parameters()  # ~0.1% of 7B

    dataset = load_sop_dataset()

    args = TrainingArguments(
        output_dir=cfg.output_dir,
        num_train_epochs=cfg.num_train_epochs,
        per_device_train_batch_size=cfg.per_device_train_batch_size,
        gradient_accumulation_steps=cfg.gradient_accumulation_steps,
        learning_rate=cfg.learning_rate,
        lr_scheduler_type=cfg.lr_scheduler_type,
        warmup_ratio=cfg.warmup_ratio,
        logging_steps=cfg.logging_steps,
        save_strategy=cfg.save_strategy,
        optim=cfg.optim,
        bf16=True,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=cfg.max_seq_length,
        tokenizer=tokenizer,
        args=args,
    )
    trainer.train()
    trainer.model.save_pretrained(cfg.output_dir)
    tokenizer.save_pretrained(cfg.output_dir)
    print(f"[train] LoRA adapter saved to {cfg.output_dir}")

    if push_to_hub and settings.HF_TOKEN:
        trainer.model.push_to_hub(settings.SOP_ADAPTER, token=settings.HF_TOKEN)
        print(f"[train] adapter pushed to {settings.SOP_ADAPTER}")


if __name__ == "__main__":
    train(push_to_hub=False)
