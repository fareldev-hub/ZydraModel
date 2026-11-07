#!/usr/bin/env python3
import argparse
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge a no-system-prompt identity LoRA adapter into Qwen2.5-0.5B."
    )
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument(
        "--adapter", type=Path, default=Path("model/qwen2.5-0.5b-zydra-lora")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("model/qwen2.5-0.5b-zydra-merged")
    )
    args = parser.parse_args()

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(model, args.adapter)
    merged_model = model.merge_and_unload()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    merged_model.save_pretrained(
        args.output_dir,
        safe_serialization=True,
        max_shard_size="2GB",
    )
    AutoTokenizer.from_pretrained(args.base_model).save_pretrained(args.output_dir)
    print(f"Merged model saved to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
