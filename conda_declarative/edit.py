"""
Performs modifications to the manifest file of a given environment.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from tomllib import loads
except ImportError:
    from tomli import loads

import tomli_w
from conda.history import History
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, TextArea

from .constants import CONDA_MANIFEST_FILE, MANIFEST_TEMPLATE

if TYPE_CHECKING:
    from subprocess import CompletedProcess
    from typing import Any

    from conda.common.path import PathType


class EditApp(App):
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
    ]

    def __init__(self, filename: os.PathLike):
        self.filename = filename
        self.saved = True
        with open(self.filename) as f:
            self.text = f.read()

        self.text_area = TextArea.code_editor(
            text=self.text,
            language="toml",
        )

        super().__init__()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.saved = False
        self.title = f"Editing {self.filename} (Unsaved)"

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.text_area
        yield Footer()

    def on_mount(self):
        self.title = f"Editing {self.filename}"

    def action_quit(self) -> None:
        """Quit the editor.

        If the file hasn't been saved, ask to save it first.
        """
        if not self.saved:
            # Ask about quitting without saving
            def check_should_save(should_save: bool | None) -> None:
                """Optionally save before quitting based on the QuitModal return result.

                Parameters
                ----------
                should_save : bool | None
                    If true, save the current text to self.filename before quitting
                """
                if should_save:
                    self.action_save()
                self.exit()

            self.push_screen(QuitModal(id="modal"), check_should_save)
        else:
            self.exit()

    def action_save(self) -> None:
        """Save the current text to the file."""
        with open(self.filename, 'w') as f:
            f.write(self.text_area.text)

        self.saved = True
        self.title = f"Editing {self.filename}"


class QuitModal(ModalScreen):
    DEFAULT_CSS = """
    QuitModal {
        align: center middle;
    }
    QuitModal > Container {
        width: auto;
        height: auto;
        background: $surface;
        padding: 0 2 1 2;
    }
    QuitModal > Container > Horizontal {
        width: auto;
        height: auto;
    }
    QuitModal > Container > Label {
        width: 100%;
        content-align-horizontal: center;
        margin: 1;
    }
    QuitModal > Container > Horizontal > Button {
        margin: 0 2;
    }
    """
    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Save before quitting?", id="save-label")
            with Horizontal():
                yield Button("Yes", variant="primary", id="yes")
                yield Button("No", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


def run_editor(prefix: PathType) -> CompletedProcess:
    app = EditApp(Path(prefix, CONDA_MANIFEST_FILE))
    app.run()


def read_manifest(prefix: PathType) -> dict[str, Any]:
    manifest_path = Path(prefix, CONDA_MANIFEST_FILE)
    return loads(manifest_path.read_text())


def update_manifest(prefix: PathType) -> tuple[str, str]:
    # TODO: This can/should be delegated to Manifest class that knows how to do these editions
    prefix = Path(prefix)
    manifest_path = prefix / CONDA_MANIFEST_FILE
    if manifest_path.is_file():
        manifest_text = manifest_path.read_text()
        manifest_data = loads(manifest_text)
    else:
        manifest_text = MANIFEST_TEMPLATE.format(name=prefix.name, path=str(prefix))
        manifest_data = loads(manifest_text)
    manifest_data["requirements"] = [
        str(s) for s in History(prefix).get_requested_specs_map().values()
    ]
    new_manifest_text = tomli_w.dumps(manifest_data)
    manifest_path.write_text(new_manifest_text)
    return manifest_text, new_manifest_text
