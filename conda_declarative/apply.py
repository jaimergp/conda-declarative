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
    return None
    # unlink_records, link_records = diff_for_unlink_link_precs(prefix, set(records))
    # setup = PrefixSetup(prefix, unlink_precs=unlink_records, link_precs=link_records)
    # txn = UnlinkLinkTransaction(setup)
    # handle_txn(txn, prefix)
    # return txn
