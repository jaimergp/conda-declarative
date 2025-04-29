"""
Performs modifications to the manifest file of a given environment.
"""

from __future__ import annotations

import os
from pathlib import Path
from shutil import which
from subprocess import run
from typing import TYPE_CHECKING

try:
    import tomllib
except ImportError:
    # TODO: remove when py310 support is dropped
    import tomli as tomllib

from conda.history import History
import tomli_w

from .constants import DEFAULT_EDITORS, CONDA_MANIFEST_FILE, MANIFEST_TEMPLATE


if TYPE_CHECKING:
    from subprocess import CompletedProcess
    from typing import Any

    from conda.common.path import PathType


def run_editor(prefix: PathType) -> CompletedProcess:
    if editor := os.environ.get("EDITOR"):
        pass
    else:
        for maybe_editor in DEFAULT_EDITORS:
            if editor := which(maybe_editor):
                break
        else:
            editor = DEFAULT_EDITORS[-1]

    return run([editor, os.path.join(prefix, CONDA_MANIFEST_FILE)])


def read_manifest(prefix: PathType) -> dict[str, Any]:
    manifest_path = Path(prefix, CONDA_MANIFEST_FILE)
    return tomllib.loads(manifest_path.read_text())


def update_manifest(prefix: PathType) -> tuple[str, str]:
    # TODO: This can/should be delegated to Manifest class that knows how to do these editions
    prefix = Path(prefix)
    manifest_path = prefix / CONDA_MANIFEST_FILE
    if manifest_path.is_file():
        manifest_text = manifest_path.read_text()
        manifest_data = tomllib.loads(manifest_text)
    else:
        manifest_text = MANIFEST_TEMPLATE.format(name=prefix.name, path=str(prefix))
        manifest_data = tomllib.loads(manifest_text)
    manifest_data["requirements"] = [
        str(s) for s in History(prefix).get_requested_specs_map().values()
    ]
    new_manifest_text = tomli_w.dumps(manifest_data)
    manifest_path.write_text(new_manifest_text)
    return manifest_text, new_manifest_text
