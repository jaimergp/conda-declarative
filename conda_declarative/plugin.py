from __future__ import annotations

from collections.abc import Iterable

from conda import plugins
from conda.core.path_actions import Action

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


class UpdateState(Action):
    """An action that updates the env file when a user modifies an environment.

    This action runs as a post-transaction action.
    """

    def verify(self):
        self._verified = True

    def execute(self):
        update_state(
            self.target_prefix,
            self.remove_specs,
            self.update_specs,
        )

    def reverse(self):
        pass

    def cleanup(self):
        pass


@plugins.hookimpl
def conda_post_transaction_actions() -> Iterable[plugins.CondaPostTransactionAction]:
    yield plugins.CondaPostTransactionAction(
        name="update-declarative-env-post-transaction-action",
        action=UpdateState,
    )
