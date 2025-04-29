from __future__ import annotations

from conda import plugins

from . import cli


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
