"""
`conda edit` subcommand
"""

from __future__ import annotations

import argparse
from pathlib import Path

from conda.base.context import context
from conda.exceptions import DryRunExit
from conda.cli.conda_argparse import add_parser_help
from conda.cli.helpers import add_parser_prefix, add_parser_verbose

from .exceptions import LockOnlyExit


def configure_parser_edit(parser: argparse.ArgumentParser) -> None:
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

    if not context.quiet:
        print("Opening editor...", end="", flush=True)

    process = run_editor(prefix)

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
        return process.returncode

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
    from .edit import read_manifest
    from .apply import link, lock, solve

    manifest = read_manifest(context.target_prefix)
    records = solve(
        prefix=context.target_prefix,
        channels=manifest.get('channels', []),  # TODO: merge with context?
        subdirs=context.subdirs,  # TODO: check if supported
        specs=manifest.get('requirements', []),
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
