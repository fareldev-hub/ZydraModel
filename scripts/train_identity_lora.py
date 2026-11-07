#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)


def load_examples(path: Path) -> List[List[Dict[str, str]]]:
    examples = []
    with path.open(encoding="utf-8") as dataset_file:
        for line_number, line in enumerate(dataset_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                messages = record["messages"]
                if (
                    not isinstance(messages, list)
                    or len(messages) < 2
                    or any(
                        not isinstance(message, dict)
                        or message.get("role") not in {"user", "assistant"}
                        or not isinstance(message.get("content"), str)
                        for message in messages
                    )
                    or messages[-1]["role"] != "assistant"
                    or not any(message["role"] == "user" for message in messages)
                ):
                    raise ValueError("expected user/assistant messages ending in assistant")
                examples.append(messages)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid dataset record at {path}:{line_number}: {exc}") from exc
    if not examples:
        raise ValueError(f"No training examples found in {path}")
    return examples


def tokenize_examples(
    examples: List[List[Dict[str, str]]],
    tokenizer: Any,
    max_length: int,
) -> Dataset:
    processed = []
    for messages in examples:
        messages = [dict(message) for message in messages]
        prefix_ids = tokenizer.apply_chat_template(
            messages[:-1],
            tokenize=True,
            add_generation_prompt=True,
        )
        full_ids = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=False,
        )
        if full_ids[: len(prefix_ids)] != prefix_ids:
            raise ValueError(
                "Tokenizer chat template does not preserve the generation prefix; "
                "cannot safely mask non-assistant tokens."
            )

        input_ids = full_ids[:max_length]
        labels = [-100] * min(len(prefix_ids), len(input_ids))
        labels.extend(input_ids[len(labels) :])
        if not any(label != -100 for label in labels):
            raise ValueError("An example has no assistant tokens after max-length truncation.")
        processed.append({"input_ids": input_ids, "labels": labels})
    return Dataset.from_list(processed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune Qwen2.5 Instruct with identity examples and no system prompt."
    )
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument(
        "--train-file", type=Path, default=Path("training_data/identity_train.jsonl")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("model/zydra-lora")
    )
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=1024)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    train_dataset = tokenize_examples(
        load_examples(args.train_file),
        tokenizer,
        args.max_length,
    )

    use_cuda = torch.cuda.is_available()
    use_bf16 = use_cuda and torch.cuda.is_bf16_supported()
    dtype = torch.bfloat16 if use_bf16 else torch.float16 if use_cuda else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=dtype,
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
        ),
    )
    model.print_trainable_parameters()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(args.output_dir),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.gradient_accumulation_steps,
            learning_rate=args.learning_rate,
            logging_steps=5,
            save_strategy="epoch",
            save_total_limit=2,
            gradient_checkpointing=True,
            fp16=use_cuda and not use_bf16,
            bf16=use_bf16,
            report_to="none",
            remove_unused_columns=False,
        ),
        train_dataset=train_dataset,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            model=model,
            label_pad_token_id=-100,
            pad_to_multiple_of=8 if use_cuda else None,
        ),
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"LoRA adapter saved to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
