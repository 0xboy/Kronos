import os
import subprocess
from pathlib import Path

os.chdir("/content/Kronos/finetune_csv")
log_dir = Path("/content/drive/MyDrive/kronos/finetuned")
log_dir.mkdir(parents=True, exist_ok=True)
log_path = log_dir / "spus_small_v2_train.log"
pid_path = log_dir / "spus_small_v2_train.pid"

# Don't double-start
if pid_path.exists():
    old = pid_path.read_text().strip()
    try:
        os.kill(int(old), 0)
        print(f"already running pid={old} log={log_path}")
        raise SystemExit(0)
    except (OSError, ValueError):
        pass

log_f = open(log_path, "w", buffering=1)
proc = subprocess.Popen(
    [
        "python",
        "-u",
        "train_sequential.py",
        "--config",
        "configs/config_spus_small_v2_colab_runtime.yaml",
        "--skip-tokenizer",
    ],
    stdout=log_f,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
pid_path.write_text(str(proc.pid))
print(f"started pid={proc.pid}")
print(f"log={log_path}")
