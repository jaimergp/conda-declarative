"""Performs modifications to the manifest file of a given environment."""

from __future__ import annotations

import asyncio
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

try:
    from tomllib import loads
except ImportError:
    from tomli import loads

from collections.abc import Iterable

from conda import CondaMultiError
from conda.models.match_spec import MatchSpec
from conda.models.records import PrefixRecord
from conda.plugins.virtual_packages.cuda import cached_cuda_version
from rich.spinner import Spinner
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
    ProgressBar,
    Static,
    TextArea,
)

from . import app
from .apply import apply, solve
from .constants import CONDA_MANIFEST_FILE
from .spec import TomlSingleEnvironment, TomlSpec
from .state import update_state
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

REQUESTED_STYLE = Style(color="yellow", bold=True)
ADDED_STYLE = Style(color="blue")
REMOVED_STYLE = Style(color="red")


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


class SpinnerWidget(Static):
    """Textual widget which displays a spinner.

    See https://textual.textualize.io/blog/2022/11/24/spinners-and-progress-bars-in-textual/
    for more inspiration.
    """

    DEFAULT_CLASSES = "hidden"
    DEFAULT_CSS = """
    SpinnerWidget {
        visibility: visible;
    }
    SpinnerWidget.hidden {
        visibility: hidden;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._spinner = Spinner("dots12")

    def on_mount(self) -> None:
        """Set the update interval of the spinner."""
        self.update_render = self.set_interval(1 / 60, self.update_spinner)

    def update_spinner(self) -> None:
        """Update the spinner status."""
        self.update(self._spinner)

    def set_text(self, text: str) -> None:
        """Set the text next to the spinner.

        Parameters
        ----------
        text : str
            Text to display
        """
        self._spinner.update(text=text)

    def hide(self):
        """Hide the spinner."""
        self.add_class("hidden")

    def show(self):
        """Show the spinner."""
        self.remove_class("hidden")


class LabeledProgressBar(ProgressBar):
    """A progress bar with a label."""

    DEFAULT_CSS = """
    Horizontal {
        align-horizontal: right;
        height: auto;
        width: auto;
        visibility: visible;
        max-width: 120;
        padding: 0 2;
    }
    """

    def __init__(self, text: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text

    def compose(self):
        """Display a progress bar with a label next to it."""
        with Horizontal():
            yield Label(self.text)
            yield from super().compose()


class ProgressBars(Vertical):
    """An area that displays progress bars, but only if there are bars to show.

    See https://textual.textualize.io/guide/app/#mounting for the reference
    used here to dynamically add widgets.
    """

    DEFAULT_CSS = """
    ProgressBars {
        layer: top;
        width: 1fr;
        height: auto;
        dock: bottom;
        align: right bottom;
        visibility: hidden;
        padding: 0 2;
        overflow-y: scroll;
        margin-bottom: 1;
    }
    #bar-container {
        align: right bottom;
        width: auto;
        height: auto;
        padding: 2;
        outline: solid $primary;
        visibility: visible;
        background: $surface;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bars: dict[UUID, LabeledProgressBar] = {}
        self.container = Vertical(id="bar-container")

    def add_bar(self, uuid: UUID, description: str):
        """Add a bar to the progress bars widget.

        Parameters
        ----------
        uuid : UUID
            Unique identifier for the bar
        description : str
            Text to show next to the bar
        """
        if not self.bars:
            self.mount(self.container)
        self.bars[uuid] = LabeledProgressBar(text=description, total=1.0)
        self.container.mount(self.bars[uuid])

    def remove_bar(self, uuid: UUID):
        """Remove a bar from the progress bars widget.

        Parameters
        ----------
        uuid : UUID
            UUID of the bar to remove
        """
        self.bars[uuid].remove()
        del self.bars[uuid]
        if not self.bars:
            self.container.remove()

    def update_bar(self, uuid: UUID, fraction: float):
        """Update a bar in the progress bars widget.

        Parameters
        ----------
        uuid : UUID
            UUID of the bar to update
        fraction : float
            Value the bar should be updated to. Should be in the range [0, 1]
        """
        self.bars[uuid].update(progress=fraction)


class EditApp(App):
    """Main application which runs upon `conda edit`."""

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("ctrl+e", "apply", "Apply", priority=True),
    ]
    DEFAULT_CSS = """
    EditApp {
        layers: base top;
        layer: base;
    }
    #output {
        height: 1fr;
    }
    #progress-area {
        height: 2;
    }
    #editor-label-area {
        height: 1;
    }
    #editor {
        height: 1fr;
    }
    #spinner {
        width: 4;
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

        if not Path(self.filename).exists():
            update_state(self.prefix)
            self.notify(
                f"No declarative environment file found at {self.filename}."
                "Generating a new file from the PrefixData for the environment.",
                severity="warning",
            )

        with open(self.filename) as f:
            text = f.read()

        self.initial_text = text

        try:
            self.editor = TextArea.code_editor(text=text, language="toml", id="editor")
        except Exception as e:
            raise ValueError(f"Could not instantiate TUI with text:\n{text}\n") from e

        self.editor_label = Label()
        self.progress_bar_area = ProgressBars()
        self.spinner = SpinnerWidget(id="spinner")
        self.progress_label = Label(id="progress-label")

        self.table = DataTable(id="output", cursor_type="row")
        self.table_sort_key = "name"
        self.table_sort_order = SortOrder.ASC

        # Save the solution for the currently saved environment spec
        # and for the pending environment spec
        self.initial_solution: Iterable[PrefixRecord] | None = None
        self.current_solution: Iterable[PrefixRecord] | None = None

        self.set_status("done")

    def add_bar(self, uuid: UUID, description: str):
        """Add a bar to the progress bars widget.

        Parameters
        ----------
        uuid : UUID
            Unique identifier for the bar
        description : str
            Text to show next to the bar
        """
        self.progress_bar_area.add_bar(uuid, description)

    def remove_bar(self, uuid: UUID):
        """Remove a bar from the progress bars widget.

        Parameters
        ----------
        uuid : UUID
            UUID of the bar to remove
        """
        self.progress_bar_area.remove_bar(uuid)

    def update_bar(self, uuid: UUID, fraction: float):
        """Update a bar in the progress bars widget.

        Parameters
        ----------
        uuid : UUID
            UUID of the bar to update
        fraction : float
            Value the bar should be updated to. Should be in the range [0, 1]
        """
        self.progress_bar_area.update_bar(uuid, fraction)

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

    def spinner_hide(self):
        """Hide the spinner widget."""
        self.spinner.hide()

    def spinner_show(self):
        """Show the spinner widget."""
        self.spinner.show()

    def spinner_set_text(self, text: str):
        """Set the text on the spinner widget.

        Parameters
        ----------
        text : str
            Text to display
        """
        self.spinner.set_text(text)

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
            model: TomlSingleEnvironment = TomlSpec(loads(self.editor.text)).model
        except Exception as e:
            self.notify(
                f"The current file is invalid TOML: {str(e)}",
                severity="error",
                markup=False,
            )
            self.set_status("done")
            return

        if model.config is not None:
            channels = model.config.channels
        else:
            channels = []

        self.set_status("solving")
        with set_conda_console():
            try:
                records = await asyncio.to_thread(
                    solve,
                    prefix=self.prefix,
                    channels=channels,
                    subdirs=self.subdirs,
                    specs=model.get_requested_packages(),
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
        self.render_table(
            self.format_table_data(records, model.get_requested_packages())
        )
        self.set_status("done")

    def to_table_row(self, record: PrefixRecord) -> tuple[str, ...]:
        """Convert a PrefixRecord to a row to be displayed in the table.

        Parameters
        ----------
        record : PrefixRecord
            Package record to display as a row

        Returns
        -------
        tuple[str, ...]
            A row of data for the given record to display in the table
        """
        return (
            "",  # Status column
            record.name,
            record.version,
            record.build,
            str(record.build_number),
            str(record.channel),
        )

    def format_table_data(
        self,
        records: Iterable[PrefixRecord],
        requested_specs: Iterable[MatchSpec],
    ) -> list[tuple[str | Text, ...]]:
        """Format the solved records for printing into the table.

        Packages will be compared to the current environment file. Packages which
        are added or removed will be specially marked up.

        Parameters
        ----------
        records : Iterable[PrefixRecord]
            Solved set of records which will exist in the final environment
        requested_specs : Iterable[MatchSpec]
            Requested package specifications. Any packages in the current solution that
            are requested will be specially highlighted

        Returns
        -------
        list[tuple[str | Text, ...]]
            A list of marked up rows to display in the table
        """
        if self.initial_solution is None:
            # If this is the first time running the solver, store the solved
            # records for comparison to future solves
            self.initial_solution = records
            return [self.to_table_row(record) for record in records]

        rows = []
        for record in records:
            row = self.to_table_row(record)
            if any(spec.match(record) for spec in requested_specs):
                # If a record was explicitly requested, highlight it
                rows.append(
                    Text(col, style=REQUESTED_STYLE) for col in ("++>", *row[1:])
                )

            elif record in self.initial_solution:
                # If a record is unchanged and not requested, no special highlight
                rows.append(row)

            else:
                # Otherwise, it is a record that was added as a transitive dependency
                rows.append(Text(col, style=ADDED_STYLE) for col in ("+  ", *row[1:]))

        # If a record in the initial solution doesn't exist anymore, highlight it as
        # removed
        for record in self.initial_solution:
            row = self.to_table_row(record)
            if record not in records:
                rows.append(Text(col, style=REMOVED_STYLE) for col in ("-  ", *row[1:]))

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
                with Vertical(id="progress-area"):
                    yield Label(
                        Text("++>  Requested package", style=REQUESTED_STYLE)
                        + Text("       +  Added package", style=ADDED_STYLE)
                        + Text("       -  Removed package", style=REMOVED_STYLE)
                        + Text("          Unchanged package", style="default")
                    )
                    with Horizontal(id="status-bar"):
                        yield self.spinner
                        yield self.progress_label
        yield Footer()

    async def on_mount(self):
        """Set the initial configuration of the app.

        Each column name for the table includes extra spaces for sort indicators.
        """
        self.mount(self.progress_bar_area)
        self.editor_label.update(f"Editing {self.filename}")

        for label in ("status", "name", "version", "build", "build_number", "channel"):
            self.table.add_column(label + "  ", key=label)
        self.run_worker(self.update_table(debounce=0), exclusive=True)

    def action_quit(self) -> None:
        """Quit the editor.

        If the file hasn't been saved, ask to save it first.
        """
        with open(self.filename) as f:
            current_text = f.read()

        if self.editor.text != current_text:
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
        """Save the current text to the file.

        Also display a toast notification to alert the user.
        """
        with open(self.filename, "w") as f:
            f.write(self.editor.text)

        self.title = f"Editing {self.filename}"
        self.notify(f"Saved: {self.filename}")

    async def action_apply(self) -> None:
        """Run the save action, then apply the changes to the environment async."""
        self.action_save()
        self.run_worker(self.run_apply(), exclusive=True)

    async def run_apply(self):
        """Apply the current env file to the target environment."""
        try:
            with set_conda_console():
                await asyncio.to_thread(
                    apply,
                    prefix=self.prefix,
                    quiet=True,
                    dry_run=False,
                    lock_only=False,
                )
        except CondaMultiError as e:
            self.notify(
                f"Exception while applying the environment: {repr(e)}.",
                severity="error",
                markup=False,
            )
        except Exception as e:
            self.notify(
                f"Exception while applying the environment: {e}. Type: {type(e)}",
                severity="error",
                markup=False,
            )

        self.set_status("done")


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


def run_editor(
    prefix: PathType,
    subdirs: tuple[str, str],
) -> None:
    """Launch the textual editor.

    Parameters
    ----------
    prefix : PathType
        Prefix of the context; this is the prefix we will be configuring the environment
        for
    subdirs : tuple[str, str]
        Subdirectories known by conda; see docs for `context.subdirs`
    """
    if app.app is None:
        app.app = EditApp(Path(prefix, CONDA_MANIFEST_FILE), Path(prefix), subdirs)
        app.app.run()
    else:
        raise RuntimeError("App is already running.")
