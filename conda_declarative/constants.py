from conda.common.compat import on_win

CONDA_HISTORY_D = "conda-meta/history.d"
CONDA_MANIFEST_FILE = "conda-meta/environment.toml"
DEFAULT_EDITORS = ("notepad.exe",) if on_win else ("pico", "nano", "vim", "vi")
MANIFEST_TEMPLATE = """
[environment]
name = "{name}"
path = "{path}"

[requirements]

"""
