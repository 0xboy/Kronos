import os
import time
from pathlib import Path

log = Path("/content/drive/MyDrive/kronos/finetuned/spus_small_v2_train.log")
pid = int(Path("/content/drive/MyDrive/kronos/finetuned/spus_small_v2_train.pid").read_text().strip())
print("pid", pid)
print("alive", end=" ")
try:
    os.kill(pid, 0)
    print(True)
except OSError as e:
    print(False, e)

# cmdline / status if /proc exists
p = Path(f"/proc/{pid}")
if p.exists():
    print("cmdline:", (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")[:200])
    print("status:", [ln for ln in (p / "status").read_text().splitlines() if ln.startswith(("Name", "State", "VmRSS"))][:5])

size1 = log.stat().st_size
time.sleep(8)
size2 = log.stat().st_size
print("log size", size1, "->", size2, "grew", size2 > size1)

try:
    import torch
    print("cuda", torch.cuda.is_available(), "alloc_mb", round(torch.cuda.memory_allocated()/1e6,1) if torch.cuda.is_available() else None)
except Exception as e:
    print("torch check", e)
