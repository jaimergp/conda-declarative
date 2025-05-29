from __future__ import annotations

from collections.abc import Iterable

from conda.common.path import PathType
from conda.plugins.types import (
    ProgressBarBase,
    ReporterRendererBase,
)
from textual.app import App


class TuiProgressBar(ProgressBarBase):
    """Conda progress bar that passes progress info to the TUI."""

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

    def detail_view(self, _data: dict[str, str | int | bool], **_kwargs) -> str:
        """Render the output in tabular format.

        Parameters
        ----------
        _data : dict[str, str | int | bool]
            Data to be rendered as a table
        **_kwargs
            Unused

        Returns
        -------
        str
            A table of data
        """
        return ""

    def envs_list(self, _data: Iterable[PathType], **_kwargs) -> str:
        """Render a list of environments.

        Parameters
        ----------
        _data :

        **_kwargs


        Returns
        -------
        str


        """
        return ""

    def progress_bar(self, _description: str, **_kwargs) -> TuiProgressBar:
        """Return the TuiProgressBar used to report progress to the TUI.

        Parameters
        ----------
        _description : str
            Unused
        **_kwargs
            Unused

        Returns
        -------
        TuiProgressBar
            Progress bar which reports progress to the TUI
        """
        return TuiProgressBar()
