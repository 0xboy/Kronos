from pathlib import Path
import os

log = Path("/content/drive/MyDrive/kronos/finetuned/spus_small_v2_train.log")
pid = Path("/content/drive/MyDrive/kronos/finetuned/spus_small_v2_train.pid")
print("log exists", log.exists(), "size", log.stat().st_size if log.exists() else 0)
print("pid file", pid.read_text().strip() if pid.exists() else None)
if pid.exists():
    try:
        os.kill(int(pid.read_text().strip()), 0)
        print("process alive")
    except OSError:
        print("process dead")
if log.exists():
    text = log.read_text(encoding="utf-8", errors="replace")
    print("--- tail ---")
    print(text[-2500:])
