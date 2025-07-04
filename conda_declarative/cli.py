"""`edit` and `apply` subcommands for CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from conda.base.context import context
from conda.cli.conda_argparse import add_parser_help
from conda.cli.helpers import add_parser_prefix, add_parser_verbose


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
    from .edit import run_editor

    prefix = context.target_prefix
    manifest_path = Path(prefix, CONDA_MANIFEST_FILE)
    if args.show:
        print(manifest_path)
        return 0

    run_editor(
        prefix, context.subdirs, context.plugin_manager.get_reporter_backend("tui")
    )

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
    from .apply import apply

    apply(
        prefix=context.target_prefix,
        quiet=context.quiet,
        lock_only=args.lock_only,
        dry_run=args.dry_run,
        args=args,
    )
    return 0
