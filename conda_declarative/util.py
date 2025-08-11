"""Assorted utilities for conda-declarative."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Generator
from contextlib import contextmanager

from conda.base.context import reset_context


@contextmanager
def set_conda_console() -> Generator[None, None, None]:
    """Set the context.console config variable to "tui" to use the TUI plugin.

    Upon cleanup, the context is reset once again.

    Returns
    -------
    Generator[None, None, None]
        An empty generator is yielded here to defer environment cleanup
    """
    reset_context(argparse_args=Namespace(console="tui"))
    yield
    reset_context()
