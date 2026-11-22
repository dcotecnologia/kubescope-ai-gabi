import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QFileDialog, QLabel, QWidget

from kubescope.gabi import settings_panel
from kubescope.gabi.runner import Assistant
from kubescope.gabi.settings import GabiSettings
from kubescope.gabi.settings_panel import GabiSettingsPanel

application = QApplication.instance() or QApplication([])

ONE = Assistant("one", "One", "one-ai", lambda m, s: [], lambda line: ("", ""))
MANY = Assistant(
    "many",
    "Many",
    "many-ai",
    lambda m, s: [],
    lambda line: ("", ""),
    models=("big", "small"),
    efforts=("low", "high"),
    effort_options=lambda effort: ["--effort", effort],
)


class Store(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value) -> None:
        self[key] = value


class Setup:
    def __init__(self, monkeypatch, found=(MANY, ONE)) -> None:
        monkeypatch.setattr(settings_panel, "installed", lambda: list(found))
        monkeypatch.setattr(
            settings_panel, "ASSISTANTS", {one.key: one for one in (MANY, ONE)}
        )
        monkeypatch.setattr(settings_panel, "is_available", lambda one: one is MANY)
        self.store = Store()
        self.settings = GabiSettings(self.store)
        self.applied: list = []
        self.notices: list[str] = []
        self.cleared = 0
        self.panel = GabiSettingsPanel(
            self.settings, self.apply, self.notices.append, self.clear
        )
        self.panel.load()

    def apply(self, enabled, assistant, programs, models, efforts, focus) -> None:
        self.applied.append((enabled, assistant, programs, models, efforts))
        self.settings.focus_mode = focus
        self.settings.assistant_enabled = enabled
        self.settings.assistant = assistant
        self.settings.assistant_programs = programs
        self.settings.assistant_models = models
        self.settings.assistant_efforts = efforts

    def clear(self) -> None:
        self.cleared += 1


@pytest.fixture
def setup(monkeypatch):
    return Setup(monkeypatch)


def combos(setup: Setup, key: str) -> tuple[QComboBox, QComboBox]:
    return setup.panel._models[key]


def test_the_panel_shows_what_is_saved_and_the_programs_of_this_computer(
    setup,
) -> None:
    panel = setup.panel

    assert panel.enabled.isChecked()
    assert [panel.program.itemText(i) for i in range(3)] == [
        "Automatic: the first one found",
        "Many",
        "One",
    ]
    model, effort = combos(setup, "many")
    assert [model.itemText(i) for i in range(3)] == ["Default model", "big", "small"]
    assert effort.isEnabled() and not combos(setup, "one")[1].isEnabled()


def test_what_was_chosen_is_shown_again(monkeypatch) -> None:
    setup = Setup(monkeypatch)
    setup.settings.assistant_enabled = False
    setup.settings.assistant = "one"
    setup.settings.assistant_models = {"many": "small"}
    setup.settings.assistant_efforts = {"many": "high"}

    setup.panel.load()

    assert not setup.panel.enabled.isChecked()
    assert setup.panel.program.currentData() == "one"
    model, effort = combos(setup, "many")
    assert model.currentData() == "small" and effort.currentData() == "high"


def test_a_model_or_effort_the_program_no_longer_lists_stays_selectable(
    monkeypatch,
) -> None:
    setup = Setup(monkeypatch)
    setup.settings.assistant_models = {"many": "gone"}
    setup.settings.assistant_efforts = {"many": "old"}

    setup.panel.load()

    model, effort = combos(setup, "many")
    assert model.currentData() == "gone" and effort.currentData() == "old"


def test_loading_again_does_not_pile_up_the_lines(setup) -> None:
    setup.panel.load()
    setup.panel.load()
    application.sendPostedEvents(None, 52)  # QEvent.DeferredDelete

    assert setup.panel.models_layout.count() == 2
    assert setup.panel.paths_layout.count() == 2
    assert set(setup.panel._paths) == {"many", "one"}


def test_the_programs_the_system_does_not_find_say_so(setup) -> None:
    paths = setup.panel._paths

    assert paths["many"].placeholderText() == "Found on the path of the system"
    assert paths["one"].placeholderText() == "Not found: one-ai is not on the path"


def test_without_programs_there_is_no_line_for_models(monkeypatch) -> None:
    setup = Setup(monkeypatch, found=())

    assert setup.panel.models_label.isHidden()
    assert setup.panel._models == {}
    assert setup.panel.program.count() == 1


def test_saving_keeps_what_was_chosen_and_follows_it(setup) -> None:
    setup.panel.enabled.setChecked(False)
    setup.panel.program.setCurrentIndex(setup.panel.program.findData("many"))
    model, effort = combos(setup, "many")
    model.setCurrentIndex(model.findData("small"))
    effort.setCurrentIndex(effort.findData("high"))

    assert setup.panel.save() is True

    assert setup.applied == [
        (False, "many", {}, {"many": "small", "one": ""}, {"many": "high", "one": ""})
    ]


def test_what_was_chosen_for_a_program_that_is_not_here_now_is_kept(
    monkeypatch,
) -> None:
    setup = Setup(monkeypatch, found=(ONE,))
    setup.settings.assistant_models = {"many": "big", "one": "x"}
    setup.panel.load()

    setup.panel.save()

    assert setup.applied[0][3] == {"many": "big", "one": "x"}  # both stay


def test_a_path_that_is_not_a_program_keeps_everything_from_being_saved(
    setup, tmp_path
) -> None:
    setup.panel._paths["one"].setText("/nowhere/one-ai")

    assert setup.panel.save() is False

    assert setup.applied == []
    assert setup.notices == ["/nowhere/one-ai is not a program that can be run (One)."]


def test_a_path_that_runs_is_kept_and_an_empty_one_is_left_out(setup, tmp_path) -> None:
    program = tmp_path / "one-ai"
    program.write_text("#!/bin/sh\n")
    program.chmod(0o755)
    setup.panel._paths["one"].setText(str(program))
    setup.panel._paths["many"].setText("   ")

    assert setup.panel.save() is True

    assert setup.applied[0][2] == {"one": str(program)}
    setup.panel.load()
    assert setup.panel._paths["one"].text() == str(program)


def test_browsing_fills_the_path_and_cancelling_changes_nothing(
    setup, monkeypatch, tmp_path
) -> None:
    chosen = [str(tmp_path / "one-ai"), ""]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a: (chosen.pop(0), ""))
    edit = setup.panel._paths["one"]

    setup.panel._browse(edit, "One")
    setup.panel._browse(edit, "One")

    assert edit.text() == str(tmp_path / "one-ai")


def test_the_button_forgets_the_conversations(setup) -> None:
    setup.panel.clear_button.click()

    assert setup.cleared == 1


def test_the_panel_explains_where_the_conversations_and_the_credentials_go(
    setup,
) -> None:
    text = " ".join(label.text() for label in setup.panel.findChildren(QLabel))

    assert "asks you for no credentials and stores none" in text
    assert "kept on this computer" in text
    assert isinstance(setup.panel, QWidget)


def test_the_focus_mode_is_shown_and_saved_with_the_rest(setup) -> None:
    assert setup.panel.focus.isChecked() is False

    setup.panel.focus.setChecked(True)
    assert setup.panel.save()

    assert setup.settings.focus_mode is True
    setup.panel.load()
    assert setup.panel.focus.isChecked() is True
