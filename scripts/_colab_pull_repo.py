from pathlib import Path
import subprocess

repo = Path("/content/Kronos")
url = "https://github.com/0xboy/Kronos.git"
if repo.exists():
    subprocess.check_call(["git", "-C", str(repo), "pull", "--ff-only"])
else:
    subprocess.check_call(["git", "clone", url, str(repo)])
print("ok", repo)

cfg = repo / "finetune_csv/configs/config_spus_small_v2_colab.yaml"
print("cfg exists", cfg.exists())
text = cfg.read_text(encoding="utf-8")
assert "loss_last_n: 1" in text, "v2 loss_last_n missing — wrong commit?"
assert "spus_small_v2" in text
print("loss_last_n ok, exp spus_small_v2")
