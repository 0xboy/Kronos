#!/usr/bin/env bash
# Run from WSL with Colab CLI (no browser training loop).
# Prereq: uv tool install google-colab-cli && colab auth flow once
#
# Usage:
#   bash scripts/colab_train_base.sh
set -euo pipefail

SESSION="${COLAB_SESSION:-kronos-base}"
GPU="${COLAB_GPU:-T4}"

echo "==> new session $SESSION gpu=$GPU"
colab new -s "$SESSION" --gpu "$GPU"

echo "==> mount Drive"
colab drivemount -s "$SESSION"

echo "==> clone / pull repo on VM"
colab exec -s "$SESSION" <<'PY'
from pathlib import Path
import subprocess
repo = Path("/content/Kronos")
url = "https://github.com/0xboy/Kronos.git"
if repo.exists():
    subprocess.check_call(["git", "-C", str(repo), "pull", "--ff-only"])
else:
    subprocess.check_call(["git", "clone", url, str(repo)])
print("ok", repo)
PY

echo "==> install deps"
colab install -s "$SESSION" einops==0.8.1 huggingface_hub==0.33.1 safetensors==0.6.2 tqdm pyyaml matplotlib

echo "==> train base (runtime paths patched for Drive)"
colab exec -s "$SESSION" <<'PY'
import os
from pathlib import Path
import yaml

drive = Path("/content/drive/MyDrive")
roots = [p for p in drive.iterdir() if p.is_dir() and p.name.lower() == "kronos"]
root = next((p for p in roots if (p / "data" / "spus").exists()), roots[0] if roots else drive / "kronos")
data = root / "data" / "spus"
out = root / "finetuned"
assert data.exists() and len(list(data.glob("*.csv"))) >= 50, f"missing SPUS csv under {data}"

os.chdir("/content/Kronos/finetune_csv")
with open("configs/config_spus_base_v1_colab.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
cfg["data"]["data_path"] = str(data)
cfg["model_paths"]["base_path"] = str(out)
rt = Path("configs/config_spus_base_v1_colab_runtime.yaml")
with open(rt, "w", encoding="utf-8") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
print("data", data, "csv", len(list(data.glob('*.csv'))))
print("out", out)
PY

colab exec -s "$SESSION" <<'PY'
import os, subprocess
os.chdir("/content/Kronos/finetune_csv")
subprocess.check_call([
    "python", "train_sequential.py",
    "--config", "configs/config_spus_base_v1_colab_runtime.yaml",
    "--skip-tokenizer",
])
PY

echo "==> done. Checkpoint on Drive: kronos/finetuned/spus_base_v1/basemodel/best_model/"
echo "    Leave session up or: colab stop -s $SESSION"
