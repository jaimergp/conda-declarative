from __future__ import annotations

from collections.abc import Iterable

from conda import plugins
from conda.core.path_actions import Action

from . import cli
from .state import update_state, get_env_path


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_env = None

    def verify(self):
        self._verified = True

    def execute(self):
        """Update the declarative env file with the current environment."""
        if get_env_path(self.target_prefix).is_file():
            with open(get_env_path(self.target_prefix)) as f:
                self.original_env = f.read()

        update_state(
            self.target_prefix,
            self.remove_specs,
            self.update_specs,
        )

    def reverse(self):
        """Reverse the update state action.

        If there was no declarative env file before this action, delete the one that was
        created. Otherwise, write the content of the original environment back to where
        it was previously.
        """
        if self.original_env is None:
            get_env_path(self.target_prefix).unlink(missing_ok=True)
        else:
            with open(get_env_path(self.target_prefix), "w") as f:
                f.write(self.original_env)

    def cleanup(self):
        pass


@plugins.hookimpl
def conda_post_transaction_actions() -> Iterable[plugins.CondaPostTransactionAction]:
    yield plugins.CondaPostTransactionAction(
        name="update-declarative-env-post-transaction-action",
        action=UpdateState,
    )
