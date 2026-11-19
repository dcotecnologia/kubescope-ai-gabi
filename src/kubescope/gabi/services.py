"""What the app lends to Gabi, once she is activated.

`activate(ctx)` hands the context to `install`, and the rest of the code
asks for the cluster, the changes to it and the colors of the theme
here, so that it never reaches into the app. Before she is activated (or
without a window, in the terminal) the colors are what they are written
as.
"""

from typing import Any

from kubescope.sdk import ClusterAccess, Context, Writes

_context: Context | None = None
controller: Any = None  # the chat in the window, while there is one


def install(ctx: Context | None) -> None:
    """Keep the context of the extension, or forget it (`None`)."""
    global _context
    _context = ctx


def context() -> Context:
    if _context is None:
        raise RuntimeError("Gabi was not activated")
    return _context


def cluster() -> ClusterAccess:
    """What may be read of a cluster."""
    return context().cluster


def writes() -> Writes:
    """The changes to a cluster, which refuse unless the write mode is on."""
    return context().writes


def themed(color: str, text: bool = False) -> str:
    """A color as the theme in use shows it."""
    ui = _context.ui if _context is not None else None
    return ui.themed(color, text) if ui is not None else color
