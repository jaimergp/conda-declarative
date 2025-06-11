"""Performs modifications to the manifest file of a given environment."""

from __future__ import annotations

import asyncio
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from tomllib import loads
except ImportError:
    from tomli import loads

import tomli_w
from conda.history import History
from conda.plugins.virtual_packages.cuda import cached_cuda_version
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Input,
    Label,
    ProgressBar,
    TextArea,
)

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


class SortOrder(Enum):
    """Table sorting order."""

    ASC = "ascending"
    DESC = "descending"


class EditApp(App):
    """Main application which runs upon `conda edit`."""

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
    ]

    DEFAULT_CSS = """
    #search-area {
        margin: 1 0 0 0;
        height: 4;
        Input {
            width: 1fr;
        }
    }
    #search-controls {
        align: left middle;
        width: 20;
        margin: 0 0;
    }
    #output {
        height: 1fr;
    }
    #progress-area {
        height: 1;
    }
    """

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

        self.saved_text = text
        self.editor = TextArea.code_editor(text=text, language="toml", id="editor")
        self.search = Input(placeholder=" ")
        self.regex = Checkbox(label="regex", compact=True)
        self.case = Checkbox(label="case sensitive", compact=True)
        self.progress_label = Label()
        self.progress = ProgressBar()

        self.table = DataTable(id="output", cursor_type="row")
        self.table_data = []
        self.table_sort_key = "name"
        self.table_sort_order = SortOrder.ASC

        super().__init__()

        self.set_status("done")

    def set_status(self, text: str) -> None:
        """Set the progress label to the given text.

        Ensures that the progress label is properly padded.

        Parameters
        ----------
        text : str
            Text to set the progress bar label to
        """
        label = f"Status: {text}"
        if text != "done":
            label += "..."

        self.progress_label.update(f"{label:<30}")

    @on(DataTable.HeaderSelected)
    async def handle_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Sort the table when a column header is selected.

        If the current column is clicked again, reverse the sort order.

        Parameters
        ----------
        event : DataTable.HeaderSelected
            Header which was clicked by the user
        """
        sort_key = str(event.column_key.value)

        if sort_key != self.table_sort_key:
            self.table_sort_key = sort_key
        else:
            if self.table_sort_order == SortOrder.ASC:
                self.table_sort_order = SortOrder.DESC
            else:
                self.table_sort_order = SortOrder.ASC

        self.table.sort(
            self.table_sort_key,
            reverse=self.table_sort_order == SortOrder.DESC,
        )

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
        if event.text_area.text == self.saved_text:
            self.title = f"Editing {self.filename}"
        else:
            self.title = f"Editing {self.filename} (Unsaved)"

        self.run_worker(self.update_table(), exclusive=True)

    async def update_table(self, debounce: int = 1) -> None:
        """Update the table in the right hand pane.

        The table will be updated with the solution to the environment in the left hand pane.

        Parameters
        ----------
        debounce : int
            Length of time to debounce the update
        """
        # Since this function runs inside an exclusive worker, this await serves to
        # debounce input to avoid solving on every keypress.
        if debounce > 0:
            await asyncio.sleep(debounce)
        try:
            self.set_status("reading toml")
            manifest = await asyncio.to_thread(loads, self.editor.text)
        except Exception as e:
            self.notify(f"The current file is invalid TOML: {e}", severity="error")
            return

        # Store the current data so that we know which rows to update
        current_data = {}
        for row in self.table.rows:
            name, version, build, build_number, channel = self.table.get_row(row)
            current_data[name] = [version, build, build_number, channel]

        self.set_status("solving")
        with set_conda_console():
            records = await asyncio.to_thread(
                solve,
                prefix=self.prefix,
                channels=manifest.get("channels", []),
                subdirs=self.subdirs,
                specs=manifest.get("requirements", []),
            )

        rows = []
        for record in records:
            rows.append(
                (
                    record.name,
                    record.version,
                    record.build,
                    record.build_number,
                    str(record.channel),
                )
            )

        self.table.clear()
        self.table.add_rows(rows)
        self.table.sort(self.table_sort_key)
        self.set_status("done")

    def compose(self) -> Generator[ComposeResult, None, None]:
        """Yield the widgets that make up the app.

        Returns
        -------
        Generator[ComposeResult, None, None]
            The widgets that make up the app
        """
        with Horizontal():
            yield self.editor
            with Vertical():
                with Horizontal(id="search-area"):
                    yield self.search
                    with Vertical(id="search-controls"):
                        yield self.regex
                        yield self.case
                yield self.table
                with Horizontal(id="progress-area"):
                    yield self.progress_label
                    yield self.progress
        yield Footer()

    async def on_mount(self):
        """Set the initial configuration of the app."""
        self.title = f"Editing {self.filename}"
        for label in ("name", "version", "build", "build_number", "channel"):
            self.table.add_column(label, key=label)
        self.run_worker(self.update_table(debounce=0), exclusive=True)

    def action_quit(self) -> None:
        """Quit the editor.

        If the file hasn't been saved, ask to save it first.
        """
        if self.editor.text != self.saved_text:
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

        self.saved_text = self.editor.text
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
