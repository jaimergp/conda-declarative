"""Renderers which pass conda progress information to the TUI.

The TuiReporterRenderer instantiates TuiProgressBar and TuiSpinner instances, both
of which pass their respective status information to the global `conda_declarative.app`
singleton instance. The app in turn updates the UI.
"""

from __future__ import annotations  # noqa: I001

from uuid import uuid4
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
        if app.app:
            self.uuid = uuid4()
            app.app.call_from_thread(app.app.add_bar, self.uuid, description)

    def update_to(self, fraction: float) -> None:
        """Update the progress bar to the specified fraction.

        Parameters
        ----------
        fraction : float
            Fraction to set the progress bar to
        """
        if app.app:
            app.app.call_from_thread(app.app.update_bar, self.uuid, fraction)

    def refresh(self) -> None:
        """Redraw the progress bar."""
        pass

    def close(self) -> None:
        """Close out the progress bar."""
        if app.app:
            app.app.call_from_thread(app.app.remove_bar, self.uuid)


class TuiReporterRenderer(ReporterRendererBase):
    """Conda reporter that passes messages and progress to the TUI."""

    def detail_view(self, data: dict[str, str | int | bool], **kwargs) -> str:  # noqa: ARG002
        """Render the output in tabular format.

        Unused.

        Parameters
        ----------
        data : dict[str, str | int | bool]
            Data to be rendered as a table
        **kwargs
            Unused

        Returns
        -------
        str
            An empty string
        """
        return ""

    def envs_list(self, data: Iterable[PathType], **kwargs) -> str:  # noqa: ARG002
        """Render a list of environments.

        Unused.

        Parameters
        ----------
        data : Iterable[PathType]
            Unused
        **kwargs
            Unused

        Returns
        -------
        str
            An empty string
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
        return TuiProgressBar(description)

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
        return TuiSpinner(message, failed_message)

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
    """Conda spinner which passes spinner state to the TUI.

    The spinner is only shown during the time it is active as a context manager.
    """

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
