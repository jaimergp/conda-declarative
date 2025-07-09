"""A module which keeps track of the singleton TUI frontend instance.

Currently `textual._context.active_app` contains the reference we need,
but that's part of the private API so instead we keep the reference to
the TUI here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .edit import EditApp

app: EditApp | None = None
