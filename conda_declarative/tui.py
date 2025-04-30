#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import var
from textual.widgets import (
    Button,
    Footer,
    Header,
    Static,
    Label,
    LoadingIndicator,
    TextArea,
)
from textual.message import Message
from textual.binding import Binding


class CondaEnvEditorApp(App[None]):
    """A Textual app to modify Conda environments via a TOML file."""

    CSS = """
    #app-grid {
        grid-size: 2;
        grid-gutter: 1 2;
    }

    #left-panel {
        border: thick gray;
        border-title-align: center;
    }

    #right-panel {
        border: thick gray;
        border-title-align: center;
    }

    #preview-pane {
        height: 85%; /* Adjust height as needed */
        border: round $primary;
        margin: 1 0;
        overflow-y: scroll;
        /* background: $panel; */ /* Optional: background color */
    }

    #preview-pane Static {
         width: auto; /* Allow text to wrap */
    }


    #status-bar {
        height: auto;
        padding: 0 1;
        /* border-top: thin $background-lighten-2; */
    }

    #toml-status {
        color: $text;
        text-style: bold;
    }

    #toml-status.valid {
        color: $success;
    }

    #toml-status.invalid {
        color: $error;
    }

    #action-buttons {
        height: auto; /* Take needed height */
        align: center middle;
    }

    #action-buttons Button {
        margin: 1 2;
        width: auto;
        min-width: 15;
    }

    LoadingIndicator {
        height: 1;
        margin-top: 1;
    }

    .working-message {
        margin-top: 1;
        text-align: center;
        color: $accent;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save File", show=True, priority=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+r", "preview_changes", "Preview Changes", show=True),
    ]

    # --- Reactive Vars ---
    toml_valid = var(True, init=False)
    toml_error_message = var("")
    file_path = var(Path())
    env_prefix = var(Path())
    is_working = var(False, init=False)
    working_message = var("")

    # --- Custom Messages ---
    class CondaOperationComplete(Message):
        """Message sent when a conda operation finishes."""

        def __init__(self, success: bool, output: str, operation: str):
            self.success = success
            self.output = output
            self.operation = operation  # e.g., "preview", "apply"
            super().__init__()

    # --- App Methods ---
    def __init__(
        self,
        file_path: Path,
        env_prefix: Path,
        driver_class=None,
        css_path=None,
        watch_css=False,
    ):
        super().__init__(
            driver_class=driver_class, css_path=css_path, watch_css=watch_css,
        )
        self.file_path = Path(file_path)
        self.env_prefix = Path(env_prefix)

    def compose(self) -> ComposeResult:
        yield Header(name="conda edit", icon="📝")
        with Horizontal(id="app-grid"):
            with Vertical(id="left-panel"):
                yield Label(f"Editing {self.file_path.parent.name}")
                yield TextArea.code_editor(
                    self.file_path.read_text(),
                    language="toml",
                    id="editor",
                )
                with Horizontal(id="status-bar"):
                    yield Static("TOML:", id="toml-status-label", classes="valid")
                    yield Static("Valid", id="toml-status")
            with Vertical(id="right-panel"):
                yield Label("Preview for prefix")
                with Container(id="preview-pane"):
                    yield Static(
                        "Press 'Preview Changes' or F5 to see diff.",
                        id="preview-content",
                    )
                yield LoadingIndicator(id="loading")  # Hidden initially
                yield Static(
                    "", id="working-message", classes="working-message"
                )  # Hidden initially
                with Horizontal(id="action-buttons"):
                    yield Button(
                        "Preview Changes", id="btn-preview", variant="primary"
                    )
                    yield Button(
                        "Apply Changes",
                        id="btn-apply",
                        variant="success",
                        disabled=True,
                    )  # Disabled initially
                    yield Button("Reload Editor", id="btn-reload", variant="default")

        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        editor = self.query_one(TextArea)
        editor.focus()
        self.query_one("#loading").display = False  # Hide loading indicator
        self.query_one("#working-message").display = False
        self._validate_toml_content(editor.text)  # Initial validation

        # Watch for changes in the TextArea content
        self.watch(editor, "text", self._on_editor_text_changed)

    def _validate_toml_content(self, text: str):
        pass

    def _on_editor_text_changed(self, old, new):
        self._validate_toml_content(new)
        self.query_one("#preview-pane").text = "Preview run!"
    