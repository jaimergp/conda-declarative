"""Renders a manifest file to disk."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from conda.base.context import context
from conda.core.link import UnlinkLinkTransaction
from conda.models.prefix_graph import PrefixGraph

from .constants import CONDA_HISTORY_D

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
            prefix, channels, subdirs, specs_to_add=specs
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


def link(prefix: PathType, records: Iterable[PackageRecord]) -> UnlinkLinkTransaction:
    """Create and run the `UnlinkLinkTransaction` on the prefix for the given records.

    Parameters
    ----------
    prefix : PathType
        Prefix for which the `UnlinkLinkTransaction` is to be carried out
    records : Iterable[PackageRecord]
        Packages for which the `UnlinkLinkTransaction` is being applied to

    Returns
    -------
    UnlinkLinkTransaction
        The transaction carries out the tasks of linking, unlinking, fetching,
        downgrading, etc the requested packages
    """
    return None
    # unlink_records, link_records = diff_for_unlink_link_precs(prefix, set(records))
    # setup = PrefixSetup(prefix, unlink_precs=unlink_records, link_precs=link_records)
    # txn = UnlinkLinkTransaction(setup)
    # handle_txn(txn, prefix)
    # return txn
