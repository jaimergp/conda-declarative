from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def set_conda_console() -> Generator[None, None, None]:
    """Set the context.console config variable to "tui" to use the TUI plugin.

    Upon cleanup, the

    Returns
    -------
    Generator[None, None, None]
        An empty generator is yielded here to defer environment cleanup
    """
    # reset_context(
    #     argparse_args=Namespace(console="classic")
    # )
    yield
    # reset_context()
