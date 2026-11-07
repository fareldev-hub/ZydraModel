# Third-Party Model Notice

The Zydra model uses **Qwen2.5-0.5B-Instruct** as its base checkpoint and a
project LoRA adapter fine-tuned with `training_data/identity_train.jsonl`.
The API loads the base and adapter locally with Transformers and PEFT.

- Hugging Face model: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct
- Model license: Apache License 2.0
- Full license text: `QWEN-APACHE-2.0` (Apache License 2.0, Copyright 2024 Alibaba Cloud)

The model weights and their license are separate from the Zydra project code.
The project code is licensed under MIT in the repository's `LICENSE` file.
Model weights are stored locally in `model/` and are excluded from Git. The
Qwen model's Apache 2.0 license is included here for attribution.
