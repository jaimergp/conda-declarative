from __future__ import annotations

from conda import plugins
from conda.plugins.types import (
    CondaReporterBackend,
)

from . import cli
from .renderers import TuiReporterRenderer


@plugins.hookimpl
def conda_subcommands():
    """Implement the new conda subcommands."""
    yield plugins.CondaSubcommand(
        name="edit",
        summary="Edit the manifest file of the given environment.",
        action=cli.execute_edit,
        configure_parser=cli.configure_parser_edit,
    )
    yield plugins.CondaSubcommand(
        name="apply",
        summary="Render the changes found in the manifest file to disk.",
        action=cli.execute_apply,
        configure_parser=cli.configure_parser_apply,
    )


@plugins.hookimpl
def conda_reporter_backends():
    """Implement the TUI reporter for conda."""
    yield CondaReporterBackend(
        name="tui",
        description="Reporter backend for the TUI",
        renderer=TuiReporterRenderer,
    )
