"""What the app lends to Gabi, once she is activated.

`activate(ctx)` hands the context to `install`, and the rest of the code
asks for the cluster and the changes to it here, so that it never
reaches into the app.
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
