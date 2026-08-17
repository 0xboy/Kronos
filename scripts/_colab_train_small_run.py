import os
import subprocess

os.chdir("/content/Kronos/finetune_csv")
subprocess.check_call(
    [
        "python",
        "train_sequential.py",
        "--config",
        "configs/config_spus_small_v2_colab_runtime.yaml",
        "--skip-tokenizer",
    ]
)
