"""
LoRA / QLoRA configuration for fine-tuning Mistral-7B on German SOPs.

LoRA adds small rank-decomposition matrices (r=16) to the attention projections
(q_proj, v_proj), training ~0.1% of parameters - enough to learn German academic
SOP style without catastrophic forgetting. QLoRA loads the 7B base in 4-bit NF4
so it fits on a single 16GB GPU / free Colab T4.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LoRAConfig:
    r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = field(default_factory=lambda: ["q_proj", "v_proj"])
    bias: str = "none"
    task_type: str = "CAUSAL_LM"


@dataclass
class QLoRAConfig:
    load_in_4bit: bool = True
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"


@dataclass
class TrainConfig:
    base_model: str = "mistralai/Mistral-7B-Instruct-v0.2"
    output_dir: str = "./outputs/intelliadmit-sop-lora"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "cosine"
    warmup_ratio: float = 0.03
    max_seq_length: int = 2048
    logging_steps: int = 10
    save_strategy: str = "epoch"
    optim: str = "paged_adamw_8bit"


def peft_lora_config():
    """Build the actual peft.LoraConfig object (import deferred)."""
    from peft import LoraConfig

    c = LoRAConfig()
    return LoraConfig(
        r=c.r,
        lora_alpha=c.lora_alpha,
        lora_dropout=c.lora_dropout,
        target_modules=c.target_modules,
        bias=c.bias,
        task_type=c.task_type,
    )


def bnb_config():
    import torch
    from transformers import BitsAndBytesConfig

    c = QLoRAConfig()
    return BitsAndBytesConfig(
        load_in_4bit=c.load_in_4bit,
        bnb_4bit_quant_type=c.bnb_4bit_quant_type,
        bnb_4bit_use_double_quant=c.bnb_4bit_use_double_quant,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
