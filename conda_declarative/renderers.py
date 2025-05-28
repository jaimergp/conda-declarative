from __future__ import annotations

from conda.plugins.types import (
    ProgressBarBase,
    ReporterRendererBase,
)
from textual.app import App


class TuiProgressBar(ProgressBarBase):
    def update_to(self, fraction: float) -> None:
        pass

    def refresh(self) -> None:
        pass

    def close(self) -> None:
        pass


class TuiReporterRenderer(ReporterRendererBase):
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

    def detail_view(self, data: dict[str, str | int | bool], **kwargs) -> str:
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

    def envs_list(self, data, **kwargs) -> str:
        return ""

    def progress_bar(self, description: str, **kwargs) -> TuiProgressBar:
        return TuiProgressBar()
