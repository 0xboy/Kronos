from pathlib import Path
import os

drive = Path("/content/drive/MyDrive")
print("drive mounted", drive.exists())
if not drive.exists():
    raise SystemExit("need drivemount")

root = Path("/content/drive/MyDrive/kronos/finetuned")
print("finetuned exists", root.exists())
if root.exists():
    for p in sorted(root.rglob("*")):
        if "spus_small_v2" in str(p):
            sz = p.stat().st_size if p.is_file() else 0
            kind = "F" if p.is_file() else "D"
            print(f"{kind} {sz/1e6:8.2f} MB  {p.relative_to(root)}")

log = root / "spus_small_v2_train.log"
if log.exists():
    text = log.read_text(encoding="utf-8", errors="replace")
    print("\n=== LOG SIZE", len(text), "===")
    print(text[-3500:])
else:
    print("no train log")

best = root / "spus_small_v2/basemodel/best_model"
if best.exists():
    print("\nbest_model files:", [p.name for p in best.iterdir()])
