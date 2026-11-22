import pytest

from kubescope.gabi.settings import GabiSettings


class Store(dict):
    """What ctx.settings is: a dictionary that is saved when a key is set."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.saved = 0

    def get(self, key, default=None):  # as the Store protocol has it
        return super().get(key, default)

    def set(self, key, value) -> None:
        self[key] = value
        self.saved += 1


def settings(**stored) -> tuple[GabiSettings, Store]:
    store = Store(stored)
    return GabiSettings(store), store


def test_the_defaults_are_a_chat_that_shows_and_nothing_chosen() -> None:
    found, _ = settings()

    assert found.assistant_enabled is True
    assert found.assistant == "" and found.assistant_consent is False
    assert found.assistant_models == found.assistant_efforts == {}
    assert found.assistant_programs == {} and found.assistant_panel == {}


def test_what_is_set_is_saved_and_read_back() -> None:
    found, store = settings()

    found.assistant_enabled = False
    found.assistant = "claude"
    found.assistant_consent = True
    found.assistant_models = {"claude": "opus"}
    found.assistant_efforts = {"codex": "high"}
    found.assistant_programs = {"claude": "/opt/claude/bin/claude"}
    found.assistant_panel = {"width": 500, "height": 520, "floating": True}

    assert store.saved == 7
    again = GabiSettings(store)
    assert again.assistant_enabled is False and again.assistant == "claude"
    assert again.assistant_consent is True
    assert again.assistant_models == {"claude": "opus"}
    assert again.assistant_efforts == {"codex": "high"}
    assert again.assistant_programs == {"claude": "/opt/claude/bin/claude"}
    assert again.assistant_panel == {"width": 500, "height": 520, "floating": True}


def test_only_a_real_false_hides_the_chat_and_only_a_real_true_is_a_consent() -> None:
    assert settings(enabled="no")[0].assistant_enabled is True
    assert settings(consent="yes")[0].assistant_consent is False
    assert settings(assistant=3)[0].assistant == ""


def test_a_map_keeps_only_names_and_texts() -> None:
    found, _ = settings(
        programs={"codex": " /x/codex ", "": "/y", "a": "", "b": 3},
        models={"codex": " gpt ", " ": "x"},
        efforts=["low"],
    )

    assert found.assistant_programs == {"codex": "/x/codex"}
    assert found.assistant_models == {"codex": "gpt"}
    assert found.assistant_efforts == {}


@pytest.mark.parametrize(
    "stored",
    [
        {"width": 5, "height": True, "floating": "yes", "geometry": "é"},
        [1],
        {"width": 90000, "geometry": "A" * 5000},
    ],
)
def test_a_panel_that_cannot_be_used_is_left_out(stored) -> None:
    assert settings(panel=stored)[0].assistant_panel == {}


def test_the_size_the_floating_and_the_place_of_the_panel_are_kept() -> None:
    found, _ = settings(
        panel={"width": 400, "height": 300, "floating": True, "geometry": "AAAA"}
    )

    assert found.assistant_panel == {
        "width": 400,
        "height": 300,
        "floating": True,
        "geometry": "AAAA",
    }


def test_the_focus_mode_is_off_unless_it_was_turned_on() -> None:
    store = Store()
    settings = GabiSettings(store)
    assert settings.focus_mode is False
    settings.focus_mode = True
    assert settings.focus_mode is True
    store["focus"] = "yes"
    assert settings.focus_mode is False
