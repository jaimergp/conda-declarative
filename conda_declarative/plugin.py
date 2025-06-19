from __future__ import annotations

from collections.abc import Iterable

from conda import plugins

from . import cli
from .state import update_state


@plugins.hookimpl
def conda_subcommands():
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
def conda_post_commands() -> Iterable[plugins.CondaPostCommand]:
    """Plugin that updates the env state when conda install or create is called."""
    yield plugins.CondaPostCommand(
        name="declarative-input-states",
        action=update_state,
        run_for={
            "create",
            "install",
            "remove",
            "uninstall",
            "update",
            "upgrade",
            "env_create",
            "env_remove",
            "env_update",
        },
    )
