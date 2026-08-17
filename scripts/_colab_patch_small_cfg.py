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
with open("configs/config_spus_small_v2_colab.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
cfg["data"]["data_path"] = str(data)
cfg["model_paths"]["base_path"] = str(out)
rt = Path("configs/config_spus_small_v2_colab_runtime.yaml")
with open(rt, "w", encoding="utf-8") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)

print("data", data, "csv", len(list(data.glob("*.csv"))))
print("out", out)
print("loss_last_n", cfg["training"].get("loss_last_n"))
print("batch_size", cfg["training"].get("batch_size"))
print("exp", cfg["model_paths"].get("exp_name"))
print("runtime", rt)
