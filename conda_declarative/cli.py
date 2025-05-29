"""`conda edit` subcommand."""

from __future__ import annotations

import argparse
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from conda.base.context import context
from conda.cli.conda_argparse import add_parser_help
from conda.cli.helpers import add_parser_prefix, add_parser_verbose
from conda.exceptions import DryRunExit

from .exceptions import LockOnlyExit


def configure_parser_edit(parser: argparse.ArgumentParser) -> None:
    """Configure the command line argument parser for the `conda edit` subcommand.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Parser which is to be configured
    """
    parser.prog = "conda edit"
    add_parser_help(parser)
    add_parser_prefix(parser)
    add_parser_verbose(parser)
    parser.add_argument(
        "--show",
        action="store_true",
        help="Only display contents of manifest file",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Run 'conda apply' immediately after a successful edition.",
    )


def execute_edit(args: argparse.Namespace) -> int:
    """Read the existing manifest; open the editor app; then apply the user's changes.

    Parameters
    ----------
    args : argparse.Namespace
        Arguments passed to the `conda edit` subcommand

    Returns
    -------
    int
        Return value of the process; 0 means success
    """
    from .constants import CONDA_MANIFEST_FILE
    from .edit import run_editor, update_manifest

    prefix = context.target_prefix
    manifest_path = Path(prefix, CONDA_MANIFEST_FILE)
    if args.show:
        print(manifest_path)
        return 0

    if manifest_path.is_file():
        old = manifest_path.read_text()
    else:
        _, old = update_manifest(prefix)

    with set_conda_console():
        run_editor(
            prefix,
            context.subdirs,
        )

    if not context.quiet:
        print(" done.")
    new = manifest_path.read_text()

    if not context.quiet:
        if old == new:
            print("No changes detected.")
        else:
            from difflib import unified_diff

            print("Detected changes:")
            print(*unified_diff(old.splitlines(), new.splitlines()), sep="\n")

    if not args.apply:  # nothing else to do
        return 0

    if not context.quiet:
        print("Applying changes...")

    return execute_apply(
        argparse.Namespace(
            dry_run=False,
            lock_only=False,
            **vars(args),
        )
    )


def configure_parser_apply(parser: argparse.ArgumentParser) -> None:
    """Configure the argument parser for the `conda apply` subcommand.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Parser which is to be configured
    """
    parser.prog = "conda apply"
    add_parser_help(parser)
    add_parser_prefix(parser)
    add_parser_verbose(parser)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes only")
    parser.add_argument(
        "--lock-only",
        action="store_true",
        help="Only add history checkpoint, do not link packages to disk",
    )


def execute_apply(args: argparse.Namespace) -> int:
    """Read the current manifest; solve the environment; and apply filesystem changes.

    Parameters
    ----------
    args : argparse.Namespace
        Arguments passed into the `conda apply` subcommand

    Returns
    -------
    int
        Return value of the process; 0 means success
    """
    from .apply import link, lock, solve
    from .edit import read_manifest

    manifest = read_manifest(context.target_prefix)
    records = solve(
        prefix=context.target_prefix,
        channels=manifest.get("channels", []),
        subdirs=context.subdirs,
        specs=manifest.get("requirements", []),
    )
    if not context.quiet:
        print(*records, sep="\n")  # This should be a diff'd report
    if context.dry_run:
        raise DryRunExit()

    lockdir = lock(prefix=context.target_prefix, records=records)

    if args.lock_only:
        raise LockOnlyExit()
    link(prefix=context.target_prefix, records=records)

    return 0


@contextmanager
def set_conda_console() -> Generator[None, None, None]:
    """Set the CONDA_CONSOLE environment variable to "tui" to use the TUI plugin.

    Returns
    -------
    Generator[None, None, None]
        An empty generator is yielded here to defer environment cleanup
    """
    old_conda_console = os.environ.get("CONDA_CONSOLE")
    os.environ.update({"CONDA_CONSOLE": "tui"})

    yield

    if old_conda_console:
        os.environ.update({"CONDA_CONSOLE": old_conda_console})
    else:
        del os.environ["CONDA_CONSOLE"]
