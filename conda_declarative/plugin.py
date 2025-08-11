"""Plugin implementations for conda-declarative functionality.

Includes:
- Conda subcommand hooks for adding the `conda edit` and `conda apply` commands
- A post-transaction action hook for updating `conda.toml` when the user installs,
  updates, or removes packages
- A reporter backend hook for redirecting progress info from conda to the TUI
- An environment specifier hook for using `conda.toml` to specify conda environments
"""

from __future__ import annotations

from collections.abc import Iterable

from conda import plugins
from conda.core.path_actions import Action
from conda.plugins.types import (
    CondaReporterBackend,
)

from . import cli, spec
from .renderers import TuiReporterRenderer
from .state import get_manifest_path, update_state


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


class UpdateState(Action):
    """An action that updates the env file when a user modifies an environment.

    This action runs as a post-transaction action.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_env = None

    def verify(self):
        """Carry out pre-execution verification.

        No pre-execution verification is needed, so we set the verified state by default.
        """
        self._verified = True

    def execute(self):
        """Update the declarative env file with the current environment."""
        if get_manifest_path(self.target_prefix).is_file():
            with open(get_manifest_path(self.target_prefix)) as f:
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
            get_manifest_path(self.target_prefix).unlink(missing_ok=True)
        else:
            with open(get_manifest_path(self.target_prefix), "w") as f:
                f.write(self.original_env)

    def cleanup(self):
        """Clean up after the action runs.

        No cleanup is needed here, so this is just a no-op.
        """
        pass


@plugins.hookimpl
def conda_post_transaction_actions() -> Iterable[plugins.CondaPostTransactionAction]:
    """Implement the post-transaction action for updating declarative envs state.

    Returns
    -------
    Iterable[plugins.CondaPostTransactionAction]
        Post-transaction action plugin
    """
    yield plugins.CondaPostTransactionAction(
        name="update-declarative-env-post-transaction-action",
        action=UpdateState,
    )


@plugins.hookimpl
def conda_reporter_backends():
    """Implement the TUI reporter for conda."""
    yield CondaReporterBackend(
        name="tui",
        description="Reporter backend for the TUI",
        renderer=TuiReporterRenderer,
    )


@plugins.hookimpl
def conda_environment_specifiers():
    """Implement the TOML spec for conda."""
    yield plugins.CondaEnvironmentSpecifier(
        name="toml",
        environment_spec=spec.TomlSpec,
    )
