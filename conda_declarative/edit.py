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

from collections.abc import Iterable

from conda.models.records import PrefixRecord
from conda.plugins.virtual_packages.cuda import cached_cuda_version
from rich.style import Style
from rich.text import Text as RichText
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Label,
    TextArea,
)

from .apply import solve
from .constants import CONDA_MANIFEST_FILE
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


class Text(RichText):
    """A Text class which allows comparison between Text and str objects for sorting."""

    def __lt__(self, other: Any) -> bool:  # noqa: ANN401
        return str(self) < other

    def __gt__(self, other: Any) -> bool:  # noqa: ANN401
        return str(self) > other


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
    #output {
        height: 1fr;
    }
    #progress-area {
        height: 1;
    }
    #editor-label-area {
        height: 1;
    }
    #editor {
        height: 1fr;
    }
    """

    def __init__(
        self,
        filename: os.PathLike,
        prefix: os.PathLike,
        subdirs: tuple[str, str],
    ):
        super().__init__()

        self.filename = filename
        self.prefix = str(prefix)
        self.subdirs = subdirs

        with open(self.filename) as f:
            text = f.read()

        self.initial_text = text
        self.editor = TextArea.code_editor(text=text, language="toml", id="editor")
        self.editor_label = Label()
        self.progress_label = Label()

        self.table = DataTable(id="output", cursor_type="row")
        self.table_sort_key = "name"
        self.table_sort_order = SortOrder.ASC

        # Save the solution for the currently saved environment spec
        # and for the pending environment spec
        self.initial_solution = None
        self.current_solution = None

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
        column_key = event.column_key
        sort_key = str(column_key.value)

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

        # Update the labels to indicate sort order
        for key in self.table.columns:
            if key == column_key:
                self.table.columns[
                    key
                ].label = f"{key.value} {'↑' if self.table_sort_order == SortOrder.ASC else '↓'}"
            else:
                self.table.columns[key].label = str(key.value)

    @on(TextArea.Changed)
    async def handle_editor_changed(self, event: TextArea.Changed) -> None:
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
        if event.text_area.text == self.initial_text:
            self.editor_label.update(f"Editing {self.filename}")
        else:
            self.editor_label.update(f"Editing {self.filename} (Modified)")

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
            self.set_status("done")
            return

        self.set_status("solving")
        with set_conda_console():
            try:
                records = await asyncio.to_thread(
                    solve,
                    prefix=self.prefix,
                    channels=manifest.get("channels", []),
                    subdirs=self.subdirs,
                    specs=manifest.get("requirements", []),
                )
            except Exception as e:
                # Disable markup styling here because conda exceptions include ANSI
                # color codes which don't play nice with textual markup enabled
                self.notify(
                    f"No valid solution for the given requirements: {e}",
                    severity="error",
                    markup=False,
                )
                self.set_status("done")
                return

        self.current_solution = records
        self.render_table(self.format_table_data(records))
        self.set_status("done")

    def to_table(self, records: Iterable[PrefixRecord]) -> list[tuple[str, ...]]:
        """Convert a list of prefix records into a list of tuples for the table.

        Parameters
        ----------
        records : Iterable[PrefixRecord]
            Records which should be displayed in the table

        Returns
        -------
        list[tuple[str, ...]]
            A list of rows for different packages; each row is a tuple containing
            various information to display in the table
        """
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
        return rows

    def format_table_data(
        self,
        records: Iterable[PrefixRecord],
    ) -> list[tuple[str | Text, ...]]:
        """Format the solved records for printing into the table.

        Packages will be compared to the current environment file. Packages which
        are added or removed will be specially marked up.

        Parameters
        ----------
        records : Iterable[PrefixRecord]
            Solved set of records which will exist in the final environment

        Returns
        -------
        list[tuple[str | Text, ...]]
            A list of marked up rows to display in the table
        """
        if self.initial_solution is None:
            # If this is the first time running the solver, store the solved
            # records for comparison to future solves
            self.initial_solution = records
            return self.to_table(records)

        # Otherwise, compare the packages in the solution to the current
        # set of packages
        saved_rows = set(self.to_table(self.initial_solution))
        current_solution_rows = set(self.to_table(records))

        rows = []

        # Packages to be added
        for row in current_solution_rows - saved_rows:
            rows.append((Text(row[0], style=Style(color="blue", bold=True)), *row[1:]))

        # Packages to be removed
        for row in saved_rows - current_solution_rows:
            rows.append(
                (
                    Text(row[0], style=Style(color="red", bold=True, strike=True)),
                    *row[1:],
                )
            )

        rows.extend(current_solution_rows & saved_rows)
        return rows

    def compose(self) -> Generator[ComposeResult, None, None]:
        """Yield the widgets that make up the app.

        Returns
        -------
        Generator[ComposeResult, None, None]
            The widgets that make up the app
        """
        with Horizontal():
            with Vertical():
                with Horizontal(id="editor-label-area"), Center():
                    yield self.editor_label
                yield self.editor
            with Vertical():
                yield self.table
                with Horizontal(id="progress-area"), Center():
                    yield self.progress_label
        yield Footer()

    async def on_mount(self):
        """Set the initial configuration of the app.

        Each column name for the table includes extra spaces for sort indicators.
        """
        self.editor_label.update(f"Editing {self.filename}")

        for label in ("name", "version", "build", "build_number", "channel"):
            self.table.add_column(label + "  ", key=label)
        self.run_worker(self.update_table(debounce=0), exclusive=True)

    def action_quit(self) -> None:
        """Quit the editor.

        If the file hasn't been saved, ask to save it first.
        """
        if self.editor.text != self.initial_text:
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

    def render_table(self, rows: Iterable[tuple[Text | str, ...]]) -> None:
        """Clear the table and render the given rows.

        Parameters
        ----------
        rows : Iterable[tuple[Text | str, ...]]
            Rows to render in the table
        """
        self.table.clear()
        self.table.add_rows(rows)
        self.table.sort(self.table_sort_key)

    def action_save(self) -> None:
        """Save the current text to the file."""
        with open(self.filename, "w") as f:
            f.write(self.editor.text)

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
