from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .edit import EditApp

app: EditApp | None = None
