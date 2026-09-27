"""Explicitly download pinned chat model data; inference itself stays offline."""

import os
import subprocess
from huggingface_hub import hf_hub_download
from chat_model import MODEL_ID, MODEL_PATH, REVISION, WEIGHTS_SHA256, sha256_file, verify_weights


def main():
    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "generation_config.json", "tokenizer.json",
                 "tokenizer_config.json", "model.safetensors.index.json", "merges.txt", "vocab.json"):
        if not (MODEL_PATH / name).is_file():
            hf_hub_download(repo_id=MODEL_ID, revision=REVISION, filename=name,
                            local_dir=MODEL_PATH, token=False)
    for name, expected in WEIGHTS_SHA256.items():
        target = MODEL_PATH / name
        if target.is_file() and sha256_file(target) == expected:
            continue
        # Download to a separate file so interrupted transfers are never loaded.
        partial = target.with_suffix(target.suffix + ".partial")
        subprocess.run(["curl.exe" if os.name == "nt" else "curl", "--fail",
                        "--location", "--retry", "3", "--continue-at", "-",
                        "--silent", "--show-error", "--output", str(partial),
                        f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}"], check=True)
        if sha256_file(partial) != expected:
            raise RuntimeError(f"Downloaded chat shard hash mismatch: {name}")
        partial.replace(target)
    verify_weights()
    print(f"Verified {MODEL_ID}@{REVISION}")


if __name__ == "__main__":
    main()
