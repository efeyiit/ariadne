"""Pinned chat inference weights, independent of the training experiments."""

import hashlib
from pathlib import Path

MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
MODEL_PATH = (Path(__file__).resolve().parent / ".cache" / "hf" /
              "models--Qwen--Qwen3-4B-Instruct-2507" / "snapshots" / REVISION)
WEIGHTS_SHA256 = {
    "model-00001-of-00003.safetensors": "75311d91bb08cf0b882913da464a1e722a31fb44db35208663487efb7a3d8ed6",
    "model-00002-of-00003.safetensors": "0b48adbb1f60e901153d91907ba11ce63bd4b8b584482e730f48808d055dfba1",
    "model-00003-of-00003.safetensors": "7dd39ccca5e4de123c74c14af44c9bf2eb75df33b4614382af0134528e060d5d",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_weights(path=MODEL_PATH, expected=WEIGHTS_SHA256):
    for name, digest in expected.items():
        file = Path(path) / name
        if not file.is_file():
            raise RuntimeError(f"Pinned chat weights missing: {name}. Run training/download_chat_model.py.")
        if sha256_file(file) != digest:
            raise RuntimeError(f"Pinned chat weights hash mismatch: {name}")


def model_from_weights():
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    return AutoModelForCausalLM.from_pretrained(
        MODEL_PATH, local_files_only=True, trust_remote_code=False,
        use_safetensors=True, dtype=torch.float16, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16),
    )
