"""The preferences of Gabi, kept in the settings of her extension.

They are saved as they are set, and read as tolerant of damage as the
settings of the app are: what does not fit is left out and the default
is used.
"""

from typing import Any, Protocol


class Store(Protocol):
    """Where the preferences are kept (`ctx.settings`)."""

    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...


class GabiSettings:
    def __init__(self, store: Store) -> None:
        self._store = store

    @property
    def assistant_enabled(self) -> bool:
        """Whether the chat button shows in the window; on unless the person
        turned it off.

        Nothing is sent before the person opens the chat and agrees.
        """
        return self._store.get("enabled", True) is not False

    @assistant_enabled.setter
    def assistant_enabled(self, value: bool) -> None:
        self._store.set("enabled", bool(value))

    def _map(self, key: str) -> dict[str, str]:
        """A text for each assistant, by its key; what is not a key and a text
        is left out."""
        value = self._store.get(key, {})
        return {
            name.strip(): text.strip()
            for name, text in (value.items() if isinstance(value, dict) else [])
            if isinstance(name, str)
            and isinstance(text, str)
            and name.strip()
            and text.strip()
        }

    @property
    def assistant_models(self) -> dict[str, str]:
        """The model each assistant answers with; an assistant not in it uses
        the default of its program."""
        return self._map("models")

    @assistant_models.setter
    def assistant_models(self, value: dict[str, str]) -> None:
        self._store.set("models", dict(value))

    @property
    def assistant_efforts(self) -> dict[str, str]:
        """How much each assistant thinks before it answers; an assistant not
        in it uses the default of its program."""
        return self._map("efforts")

    @assistant_efforts.setter
    def assistant_efforts(self, value: dict[str, str]) -> None:
        self._store.set("efforts", dict(value))

    @property
    def assistant_programs(self) -> dict[str, str]:
        """The path of the program of each assistant, for the ones the system
        does not find; what is not a name and a path is left out."""
        return self._map("programs")

    @assistant_programs.setter
    def assistant_programs(self, value: dict[str, str]) -> None:
        self._store.set("programs", dict(value))

    @property
    def auto_compact(self) -> bool:
        """Whether a long conversation is compacted by itself; on unless the
        person turned it off."""
        return self._store.get("auto_compact", True) is not False

    @auto_compact.setter
    def auto_compact(self, value: bool) -> None:
        self._store.set("auto_compact", bool(value))

    @property
    def focus_mode(self) -> bool:
        """Whether the chat fills the page between the header and the footer of
        the window, in place of the corner panel; off unless the person turned
        it on."""
        return self._store.get("focus", False) is True

    @focus_mode.setter
    def focus_mode(self, value: bool) -> None:
        self._store.set("focus", bool(value))

    @property
    def assistant_panel(self) -> dict[str, Any]:
        """The size of the chat panel, whether it is out of the window and
        where; what cannot be read is left out."""
        value = self._store.get("panel", {})
        stored = value if isinstance(value, dict) else {}
        kept: dict[str, Any] = {}
        for key in ("width", "height"):
            number = stored.get(key)
            if type(number) is int and 200 <= number <= 10_000:
                kept[key] = number
        if stored.get("floating") is True:
            kept["floating"] = True
        geometry = stored.get("geometry")
        if isinstance(geometry, str) and geometry.isascii() and len(geometry) < 4096:
            kept["geometry"] = geometry
        return kept

    @assistant_panel.setter
    def assistant_panel(self, value: dict[str, Any]) -> None:
        self._store.set("panel", dict(value))

    @property
    def assistant(self) -> str:
        """The program the person chose for the assistant; empty leaves it to
        the first one the system has."""
        value = self._store.get("assistant", "")
        return value if isinstance(value, str) else ""

    @assistant.setter
    def assistant(self, value: str) -> None:
        self._store.set("assistant", str(value))

    @property
    def assistant_consent(self) -> bool:
        """True once the person agreed that what they ask the assistant, with
        what it reads from the cluster, goes to the program of this
        computer."""
        return self._store.get("consent", False) is True

    @assistant_consent.setter
    def assistant_consent(self, value: bool) -> None:
        self._store.set("consent", bool(value))
