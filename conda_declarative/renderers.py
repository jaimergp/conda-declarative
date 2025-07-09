from __future__ import annotations

from collections.abc import Iterable
from types import TracebackType
from typing import TYPE_CHECKING

from conda.plugins.reporter_backends.console import (
    SpinnerBase,
)
from conda.plugins.types import (
    ProgressBarBase,
    ReporterRendererBase,
)

from . import app

if TYPE_CHECKING:
    from conda.common.path import PathType


class TuiProgressBar(ProgressBarBase):
    """Conda progress bar which updates a textual progress bar in the TUI."""

    def __init__(self, description: str, **kwargs):
        super().__init__(description=description, **kwargs)

    def update_to(self, fraction: float) -> None:
        """Update the progress bar to the specified fraction.

        Parameters
        ----------
        fraction : float
            Fraction to set the progress bar to
        """
        if app.app:
            app.app.set_progress(fraction)

    def refresh(self) -> None:
        """Redraw the progress bar."""
        pass

    def close(self) -> None:
        """Close out the progress bar."""
        if app.app:
            app.app.set_progress(1.0)


class TuiReporterRenderer(ReporterRendererBase):
    """Conda reporter that passes messages and progress to the TUI."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._progress_bar: TuiProgressBar = None
        self._spinner: TuiSpinner = None

    def detail_view(self, data: dict[str, str | int | bool], **kwargs) -> str:  # noqa: ARG002
        """Render the output in tabular format.

        Parameters
        ----------
        data : dict[str, str | int | bool]
            Data to be rendered as a table
        **kwargs
            Unused

        Returns
        -------
        str
            A table of data
        """
        return ""

    def envs_list(self, data: Iterable[PathType], **kwargs) -> str:  # noqa: ARG002
        """Render a list of environments.

        Parameters
        ----------
        data : Iterable[PathType]
            Unused
        **kwargs
            Unused

        Returns
        -------
        str


        """
        return ""

    def progress_bar(self, description: str, **kwargs) -> TuiProgressBar:  # noqa: ARG002
        """Return the TuiProgressBar used to report progress to the TUI.

        Parameters
        ----------
        description : str
            Unused
        **kwargs
            Unused

        Returns
        -------
        TuiProgressBar
            Progress bar which reports progress to the TUI
        """
        if self._progress_bar is None:
            self._progress_bar = TuiProgressBar(description)
        return self._progress_bar

    def spinner(self, message: str, failed_message: str) -> TuiSpinner:
        """Return the conda spinner class instance.

        Parameters
        ----------
        message : str
            Message to display next to the spinner
        failed_message : str
            Message to display in case of failure

        Returns
        -------
        TuiSpinner
            Spinner to be displayed
        """
        if self._spinner is None:
            self._spinner = TuiSpinner(message, failed_message)

        self._spinner.set_text(message)
        return self._spinner

    def prompt(self, message: str, choices: list[str], default: str) -> str:  # noqa: ARG002
        """Prompt to use when user input is required.

        Unused here.

        Parameters
        ----------
        message : str
            Message to display to the user
        choices : list[str]
            Valid choices
        default : str
            Default choice

        Returns
        -------
        str
            User-provided input
        """
        return default


class TuiSpinner(SpinnerBase):
    """Conda spinner which passes spinner state to the TUI."""

    def __init__(self, message: str, failed_message: str):
        super().__init__(message, failed_message)

    def __enter__(self, *args, **kwargs):
        if app.app:
            app.app.spinner_show()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        if app.app:
            app.app.spinner_hide()

    def set_text(self, text: str):
        """Set the text on the spinner widget.

        Parameters
        ----------
        text : str
            Text for the spinner to display
        """
        if app.app:
            app.app.spinner_set_text(text)
