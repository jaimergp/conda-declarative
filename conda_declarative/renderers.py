from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from conda.plugins.reporter_backends.console import (
    SpinnerBase,
)
from conda.plugins.types import (
    ProgressBarBase,
    ReporterRendererBase,
)
from textual.app import App

if TYPE_CHECKING:
    from conda.common.path import PathType


class TuiProgressBar(ProgressBarBase):
    """Conda progress bar that passes progress info to the TUI."""

    def __init__(self):
        super().__init__(description="")

    def update_to(self, fraction: float) -> None:
        """Update the progress bar to the specified fraction.

        Parameters
        ----------
        fraction : float
            Fraction to set the progress bar to
        """
        pass

    def refresh(self) -> None:
        """Redraw the progress bar."""
        pass

    def close(self) -> None:
        """Close out the progress bar."""
        pass


class TuiReporterRenderer(ReporterRendererBase):
    """Conda reporter that passes messages and progress to the TUI."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = None

    def register_app(self, app: App):
        """Register a TUI app with the renderer.

        Once registered, messages sent from conda will be
        passed to the app.

        Parameters
        ----------
        app : App
            TUI app instance to which conda output will be passed
        """
        self.app = app

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
        return TuiProgressBar()

    def spinner(self, message: str, failed_message: str) -> SpinnerBase:
        """Return a spinner for the TUI."""
        return TuiSpinner(message, failed_message)

    def prompt(
        self,
        message: str = "Proceed",
        choices: tuple[str, str] = ("yes", "no"),
        default: str = "yes",
    ) -> str:
        """Allow for defining an implementation of a "yes/no" confirmation function."""


class TuiSpinner(SpinnerBase):
    """A simple spinner."""

    def __enter__(self, *args, **kwargs):
        return

    def __exit__(self, *args, **kwargs):
        return
