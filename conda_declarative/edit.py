"""Performs modifications to the manifest file of a given environment."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from tomllib import loads
except ImportError:
    from tomli import loads

import tomli_w
from conda.history import History
from conda.plugins.virtual_packages.cuda import cached_cuda_version
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Label, TextArea
from textual.worker import Worker

from .apply import solve
from .constants import CONDA_MANIFEST_FILE, MANIFEST_TEMPLATE
from .util import set_conda_console

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    from conda.common.path import PathType


# Call this once upon module initialization because it ensures the cuda
# version is cached, which is needed when retrieving virtual packages.
# If the cuda version is not cached up front, the daemonic subprocess
# spawned by conda to retrieve the cuda version interferes with the
# textual's event loop, causing calls to `solve` to fail. Fortunately
# we can just ensure this is cached up front to avoid the issue
# altogether.
cuda = cached_cuda_version()


class EditApp(App):
    """Main application which runs upon `conda edit`."""

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
    ]

    def __init__(
        self,
        filename: os.PathLike,
        prefix: os.PathLike,
        subdirs: tuple[str, str],
    ):
        self.filename = filename
        self.prefix = str(prefix)
        self.subdirs = subdirs

        with open(self.filename) as f:
            text = f.read()

        self.saved_hash = hash(text)
        self.editor = TextArea.code_editor(
            text=text,
            language="toml",
        )
        self.output = DataTable()

        super().__init__()

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Run post change actions on the text.

        First, we check for changes compared to the version on disk.
        If there are changes:

        - Update the title of the app
        - Check that the text area contains valid toml.
            - If valid:
                - Run the solver to get the new dependencies
                - Update the right hand pane with the new dependencies
            - Otherwise, make a notification that the toml is invalid

        Parameters
        ----------
        event : TextArea.Changed
            Event that triggered the call
        """
        if hash(event.text_area.text) == self.saved_hash:
            self.title = f"Editing {self.filename}"
        else:
            self.title = f"Editing {self.filename} (Unsaved)"

        self.run_worker(self.update_table(), exclusive=True)

    async def update_table(self):
        await asyncio.sleep(1)
        try:
            manifest = await loads(self.editor.text)
        except Exception as e:
            self.action_notify(
                f"The current file is invalid TOML: {e}", severity="error"
            )
            return

        self.run_worker(
            self.solve(
                prefix=self.prefix,
                channels=manifest.get("channels", []),
                subdirs=self.subdirs,
                specs=manifest.get("requirements", []),
            ),
            exclusive=True,
        )

    async def solve(self, prefix, channels, subdirs, specs) -> None:
        await asyncio.sleep(1)
        with set_conda_console():
            records = solve(prefix, channels, subdirs, specs)

        rows = []
        for record in records:
            rows.append(
                (
                    record.name,
                    record.version,
                    record.build,
                    record.build_number,
                    record.channel,
                )
            )
        self.output.clear()
        # self.output.add_columns("name", "version", "build", "build_number", "channel")
        self.output.add_rows(rows)
        # self.output.sort("name")

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        self.notify(str(event))

    def compose(self) -> Generator[ComposeResult, None, None]:
        """Yield the widgets that make up the app.

        Returns
        -------
        Generator[ComposeResult, None, None]
            The widgets that make up the app
        """
        yield Header()
        with Horizontal():
            yield self.editor
            yield self.output
        yield Footer()

    async def on_mount(self):
        """Set the initial configuration of the app."""
        self.title = f"Editing {self.filename}"
        self.output.add_columns("name", "version", "build", "build_number", "channel")

    def action_quit(self) -> None:
        """Quit the editor.

        If the file hasn't been saved, ask to save it first.
        """
        if hash(self.editor.text) != self.saved_hash:
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
        with open(self.filename, "w") as f:
            f.write(self.editor.text)

        self.saved_hash = hash(self.editor.text)
        self.title = f"Editing {self.filename}"


class QuitModal(ModalScreen):
    """Modal dialog which appears when trying to quit without having saved."""

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

    def compose(self) -> Generator[ComposeResult, None, None]:
        """Yield the widgets that make up the modal.

        Returns
        -------
        Generator[ComposeResult, None, None]
            The widgets that make up the modal
        """
        with Container():
            yield Label("Save before quitting?", id="save-label")
            with Horizontal():
                yield Button("Yes", variant="primary", id="yes")
                yield Button("No", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Respond to the button click.

        Dismisses the modal dialog.

        Parameters
        ----------
        event : Button.Pressed
            Event which triggered this call.
        """
        self.dismiss(event.button.id == "yes")


def run_editor(prefix: PathType, subdirs: tuple[str, str]) -> None:
    """Launch the textual editor.

    Parameters
    ----------
    prefix : PathType
        Prefix of the context; this is the prefix we will be configuring the environment
        for
    subdirs : tuple[str, str]
        Subdirectories known by conda; see docs for `context.subdirs`
    """
    app = EditApp(
        Path(prefix, CONDA_MANIFEST_FILE),
        Path(prefix),
        subdirs,
    )
    app.run()


def read_manifest(prefix: PathType) -> dict[str, Any]:
    """Read the manifest from <prefix>/conda-meta/environment.yml.

    Parameters
    ----------
    prefix : PathType
        Prefix to read the manifest for

    Returns
    -------
    dict[str, Any]
        Manifest from the requested prefix
    """
    manifest_path = Path(prefix, CONDA_MANIFEST_FILE)
    return loads(manifest_path.read_text())


def update_manifest(prefix: PathType) -> tuple[str, str]:
    """Update the manifest for the given prefix with the user-requested packages.

    Parameters
    ----------
    prefix : PathType
        Prefix to update the manifest for

    Returns
    -------
    tuple[str, str]
        (Old manifest file contents, new manifest file contents)
    """
    # This can/should be delegated to Manifest class that knows how to do these editions
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
