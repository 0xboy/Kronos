import os
import subprocess
from pathlib import Path

print("=== nvidia-smi ===")
print(subprocess.check_output(["nvidia-smi"], text=True))

print("=== process ===")
pid_path = Path("/content/drive/MyDrive/kronos/finetuned/spus_small_v2_train.pid")
pid = pid_path.read_text().strip() if pid_path.exists() else "?"
print("train pid:", pid)
print(
    subprocess.check_output(
        f"ps -p {pid} -o pid,pcpu,pmem,rss,etime,cmd --no-headers || true",
        shell=True,
        text=True,
    )
)

print("=== disk (Drive finetuned) ===")
out = Path("/content/drive/MyDrive/kronos/finetuned")
for p in sorted(out.rglob("*")):
    if p.is_file() and ("spus_small_v2" in str(p)):
        print(f"{p.stat().st_size/1e6:8.2f} MB  {p}")
