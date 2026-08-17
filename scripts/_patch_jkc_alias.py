from pathlib import Path

p = Path(
    "/home/acboy/.local/share/uv/tools/google-colab-cli/lib/python3.12/"
    "site-packages/jupyter_kernel_client/__init__.py"
)
t = p.read_text()
needle = "from jupyter_kernel_client.client import JupyterKernelClient\n"
alias = (
    "from jupyter_kernel_client.client import JupyterKernelClient\n"
    "KernelClient = JupyterKernelClient  # alias for google-colab-cli\n"
)
if "KernelClient = JupyterKernelClient" not in t:
    if needle not in t:
        raise SystemExit("unexpected __init__.py format")
    t = t.replace(needle, alias, 1)
    t = t.replace('"JupyterKernelClient",', '"JupyterKernelClient",\n    "KernelClient",', 1)
    p.write_text(t)
    print("patched")
else:
    print("already patched")
