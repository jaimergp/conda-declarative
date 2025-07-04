"""Renders a manifest file to disk."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from boltons.setutils import IndexedSet
from conda.base.context import context
from conda.cli.install import handle_txn
from conda.core.link import PrefixSetup, UnlinkLinkTransaction
from conda.core.solve import diff_for_unlink_link_precs
from conda.exceptions import (
    DryRunExit,
)
from conda.models.prefix_graph import PrefixGraph

from .constants import CONDA_HISTORY_D
from .exceptions import LockOnlyExit
from .state import from_env_file

if TYPE_CHECKING:
    from collections.abc import Iterable

    from conda.common.path import PathType
    from conda.models.channel import Channel
    from conda.models.match_spec import MatchSpec
    from conda.models.records import PackageRecord


def solve(
    prefix: PathType,
    channels: Iterable[Channel],
    subdirs: Iterable[str],
    specs: Iterable[MatchSpec],
    **solve_final_state_kwargs,
) -> tuple[PackageRecord]:
    """Solve the environment for the given prefix, channels, subdirs, and package specs.

    Parameters
    ----------
    prefix : PathType
        Prefix to solve the environment for
    channels : Iterable[Channel]
        Channels to search when looking for valid packages
    subdirs : Iterable[str]
        Subdirs to write packages to; see `context.subdirs` for more info
    specs : Iterable[MatchSpec]
        Package specs needed in the environment
    **solve_final_state_kwargs
        Extra kwargs to pass to `solver.solve_final_state`

    Returns
    -------
    tuple[PackageRecord]
        This is the set of packages that you get when you request the packages passed
        in `specs`.
    """
    with patch("conda.history.History.get_requested_specs_map") as mock:
        # We patch History here so it doesn't interfere with the "pure" manifest specs
        # Otherwise the solver will try to adapt to previous user preferences, but this
        # would have been captured in the manifest anyway. This is a simpler mental model.
        # Every environment is treated as a new one (no history), but we do cache the IO
        # when linking / unlinking thanks to the UnlinkLinkTransaction machinery.
        mock.return_value = {}
        solver = context.plugin_manager.get_cached_solver_backend()(
            str(prefix), channels, subdirs, specs_to_add=specs
        )

        records = solver.solve_final_state(**solve_final_state_kwargs)
    return tuple(dict.fromkeys(PrefixGraph(records).graph))


def lock(prefix: PathType, records: Iterable[PackageRecord]) -> Path:
    """Write a file lock in the prefix for every record passed in `records`.

    Parameters
    ----------
    prefix : PathType
        Prefix where the records reside
    records : Iterable[PackageRecord]
        Records which need to be locked

    Returns
    -------
    Path
        Path to the directory containing file locks
    """
    timestamp = f"{time.time() * 1000:0f}"
    lockdir = Path(prefix) / CONDA_HISTORY_D / timestamp
    lockdir.mkdir(parents=True)
    for record in records:
        if record.fn.endswith(".tar.bz2"):
            basename = record.fn[: -len(".tar.bz2")]
        else:
            basename = record.fn.rsplit(".", 1)[0]
        record_lock = Path(lockdir, basename + ".json")
        record_lock.write_text(json.dumps(dict(record.dump())))
    return lockdir


def link(
    prefix: PathType, records: Iterable[PackageRecord], args: argparse.Namespace
) -> UnlinkLinkTransaction:
    """Create and run the `UnlinkLinkTransaction` on the prefix for the given records.

    Parameters
    ----------
    prefix : PathType
        Prefix for which the `UnlinkLinkTransaction` is to be carried out
    records : Iterable[PackageRecord]
        Packages for which the `UnlinkLinkTransaction` is being applied to
    args : argparse.Namespace
        Command line arguments to pass to `handle_txn`. Currently, only
        `args.package_names` is used

    Returns
    -------
    UnlinkLinkTransaction
        The transaction carries out the tasks of linking, unlinking, fetching,
        downgrading, etc the requested packages
    """
    unlink_records, link_records = diff_for_unlink_link_precs(
        prefix, IndexedSet(records)
    )
    txn = UnlinkLinkTransaction(
        PrefixSetup(
            target_prefix=prefix,
            unlink_precs=unlink_records,
            link_precs=link_records,
            remove_specs=(),
            update_specs=(),
            neutered_specs=(),
        )
    )
    handle_txn(txn, prefix, args, False, True)
    return txn


def apply(
    prefix: str | None = None,
    quiet: bool = False,
    dry_run: bool = False,
    lock_only: bool = False,
    *args,
) -> None:
    """Read the env file, solve it, and then link the resulting transaction.

    Parameters
    ----------
    prefix : str | None
        Prefix of the environment to modify
    quiet : bool
        If True, suppress status messages
    dry_run : bool
        If True, only solve the environment, don't change the environment
    lock_only : bool
        If True, only lock the records in the target prefix - don't change the
        environment
    *args
        Any additional command line arguments to be passed to `link`. Currently,
        only `args.package_names` is used
    """
    if prefix is None:
        prefix = context.target_prefix

    env = from_env_file(str(prefix))

    if env is not None:
        requested_packages = env.requested_packages
        if env.config is not None:
            channels = env.config.channels
    else:
        channels = []
        requested_packages = []

    records = solve(
        prefix=context.target_prefix,
        channels=channels,
        subdirs=context.subdirs,
        specs=requested_packages,
    )

    if not quiet:
        print(*records, sep="\n")  # This should be a diff'd report

    if dry_run:
        raise DryRunExit()

    if lock_only:
        lock(prefix=context.target_prefix, records=records)
        raise LockOnlyExit()

    link(prefix=context.target_prefix, records=records, args=args)


# def handle_txn(
#     unlink_link_transaction: UnlinkLinkTransaction,
#     prefix: str,
#     package_names: Iterable[MatchSpec | PackageRecord | str] | None,
#     newenv: bool = False,
#     remove_op: bool = False,
# ):
#     """Handle the transaction.
#
#     Parameters
#     ----------
#     unlink_link_transaction : UnlinkLinkTransaction
#         Transaction to carry out
#     prefix : str
#         Prefix in which the transaction should be carried out
#     package_names : Iterable[MatchSpec | PackageRecord | str] | None
#
#     newenv : bool
#         If True, and `context.subdir` is not the native subdir for the system,
#         the `subdir` config option in .condarc will be modified to include
#         `context.subdir`.
#     remove_op : bool
#
#
#     """
#     if unlink_link_transaction.nothing_to_do:
#         if remove_op:
#             # No packages found to remove from environment
#             if package_names is None:
#                 package_names = []
#
#             raise PackagesNotFoundError(package_names)
#         elif not newenv:
#             if context.json:
#                 common.stdout_json_success(
#                     message="All requested packages already installed."
#                 )
#             else:
#                 print("\n# All requested packages already installed.\n")
#             return
#
#     if not context.json:
#         unlink_link_transaction.print_transaction_summary()
#         confirm_yn()
#
#     elif context.dry_run:
#         actions = unlink_link_transaction._make_legacy_action_groups()[0]
#         common.stdout_json_success(prefix=prefix, actions=actions, dry_run=True)
#         raise DryRunExit()
#
#     try:
#         unlink_link_transaction.download_and_extract()
#         if context.download_only:
#             raise CondaExitZero(
#                 "Package caches prepared. UnlinkLinkTransaction cancelled with "
#                 "--download-only option."
#             )
#         unlink_link_transaction.execute()
#
#     except SystemExit as e:
#         raise CondaSystemExit("Exiting", e) from None
#
#     if newenv and context.subdir != context._native_subdir():
#         set_keys(
#             ("subdir", context.subdir),
#             path=Path(prefix, ".condarc"),
#         )
#
#     if context.json:
#         actions = unlink_link_transaction._make_legacy_action_groups()[0]
#         common.stdout_json_success(prefix=prefix, actions=actions)
