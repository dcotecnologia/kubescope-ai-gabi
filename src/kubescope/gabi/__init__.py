"""The coding assistants of the system the person can ask about the cluster."""

from kubescope.gabi.claude import CLAUDE
from kubescope.gabi.codex import CODEX
from kubescope.gabi.runner import Assistant, is_available

ASSISTANTS = {assistant.key: assistant for assistant in (CLAUDE, CODEX)}


def installed() -> list[Assistant]:
    """The assistants whose program the system has."""
    return [assistant for assistant in ASSISTANTS.values() if is_available(assistant)]


def activate(ctx) -> None:
    """What the app calls to run Gabi (see `kubescope.gabi.extension`)."""
    from kubescope.gabi import extension

    extension.activate(ctx)
