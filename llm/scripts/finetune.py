"""
QLoRA Fine-tuning Script for MLB Best Ball LLM

Optimized for 4070 Ti Super 16GB VRAM
Uses 4-bit quantization + LoRA for efficient training
"""

import os
import torch
from pathlib import Path
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer

# Paths
SCRIPT_DIR = Path(__file__).parent
LLM_DIR = SCRIPT_DIR.parent
TRAINING_DATA = LLM_DIR / 'training_data' / 'training_data.json'
OUTPUT_DIR = LLM_DIR / 'output'
MODELS_DIR = LLM_DIR / 'models'

# Model selection - Mistral 7B works great on 16GB with QLoRA
BASE_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"
# Alternative options:
# BASE_MODEL = "meta-llama/Llama-2-7b-chat-hf"  # Requires HF login
# BASE_MODEL = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # Smaller, faster

# QLoRA Configuration for 16GB VRAM
QLORA_CONFIG = {
    'r': 64,                    # LoRA rank - higher = more capacity
    'lora_alpha': 128,          # Scaling factor
    'target_modules': [         # Modules to apply LoRA to
        'q_proj', 'k_proj', 'v_proj', 'o_proj',
        'gate_proj', 'up_proj', 'down_proj'
    ],
    'lora_dropout': 0.05,
    'bias': 'none',
    'task_type': 'CAUSAL_LM'
}

# Training hyperparameters optimized for 16GB
TRAINING_CONFIG = {
    'num_train_epochs': 3,
    'per_device_train_batch_size': 2,      # Small batch for VRAM
    'gradient_accumulation_steps': 8,       # Effective batch = 16
    'learning_rate': 2e-4,
    'weight_decay': 0.01,
    'warmup_ratio': 0.03,
    'lr_scheduler_type': 'cosine',
    'logging_steps': 10,
    'save_strategy': 'epoch',
    'fp16': True,                           # Mixed precision
    'optim': 'paged_adamw_8bit',            # Memory-efficient optimizer
    'max_grad_norm': 0.3,
    'gradient_checkpointing': True,         # Trade compute for memory
}


def format_instruction(sample):
    """Format a sample for instruction tuning."""
    system = sample.get('system', '')
    instruction = sample['instruction']
    response = sample['response']

    # Mistral instruction format
    if 'mistral' in BASE_MODEL.lower():
        return f"<s>[INST] {system}\n\n{instruction} [/INST] {response}</s>"

    # Llama 2 format
    elif 'llama' in BASE_MODEL.lower():
        return f"""<s>[INST] <<SYS>>
{system}
<</SYS>>

{instruction} [/INST] {response} </s>"""

    # Generic format
    else:
        return f"### System:\n{system}\n\n### User:\n{instruction}\n\n### Assistant:\n{response}"


def load_and_prepare_model():
    """Load base model with 4-bit quantization."""
    print(f"Loading base model: {BASE_MODEL}")

    # 4-bit quantization config
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    # Load model
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

    # Add LoRA adapters
    lora_config = LoraConfig(**QLORA_CONFIG)
    model = get_peft_model(model, lora_config)

    # Print trainable parameters
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Trainable parameters: {trainable_params:,} ({100 * trainable_params / total_params:.2f}%)")

    return model, tokenizer


def load_training_data():
    """Load the prepared training dataset."""
    print(f"Loading training data from: {TRAINING_DATA}")

    if not TRAINING_DATA.exists():
        raise FileNotFoundError(
            f"Training data not found at {TRAINING_DATA}\n"
            "Run prepare_training_data.py first!"
        )

    dataset = load_dataset('json', data_files=str(TRAINING_DATA), split='train')
    print(f"Loaded {len(dataset)} training examples")

    return dataset


def train():
    """Run the fine-tuning process."""
    print("=" * 60)
    print("MLB Best Ball LLM Fine-tuning")
    print("=" * 60)

    # Check CUDA
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA not available! GPU required for training.")

    gpu_name = torch.cuda.get_device_name(0)
    gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU: {gpu_name} ({gpu_memory:.1f} GB)")

    # Load model and tokenizer
    model, tokenizer = load_and_prepare_model()

    # Load dataset
    dataset = load_training_data()

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        **TRAINING_CONFIG,
        report_to="none",  # Disable wandb
    )

    # Create trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        tokenizer=tokenizer,
        args=training_args,
        formatting_func=format_instruction,
        max_seq_length=1024,
        packing=False,
    )

    # Train!
    print("\nStarting training...")
    print(f"Output directory: {OUTPUT_DIR}")
    trainer.train()

    # Save the final model
    final_model_path = OUTPUT_DIR / 'final_model'
    print(f"\nSaving final model to: {final_model_path}")
    trainer.save_model(str(final_model_path))
    tokenizer.save_pretrained(str(final_model_path))

    print("\n" + "=" * 60)
    print("Training complete!")
    print(f"Model saved to: {final_model_path}")
    print("=" * 60)


def merge_and_save():
    """Merge LoRA weights with base model for faster inference."""
    from peft import PeftModel

    print("Merging LoRA weights with base model...")

    # Load base model (full precision for merging)
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    # Load LoRA adapter
    adapter_path = OUTPUT_DIR / 'final_model'
    model = PeftModel.from_pretrained(base_model, str(adapter_path))

    # Merge
    model = model.merge_and_unload()

    # Save merged model
    merged_path = MODELS_DIR / 'mlb_bestball_merged'
    merged_path.mkdir(parents=True, exist_ok=True)

    print(f"Saving merged model to: {merged_path}")
    model.save_pretrained(str(merged_path))

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokenizer.save_pretrained(str(merged_path))

    print("Merge complete!")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Fine-tune MLB Best Ball LLM')
    parser.add_argument('--merge', action='store_true', help='Merge LoRA weights after training')
    args = parser.parse_args()

    if args.merge:
        merge_and_save()
    else:
        train()
