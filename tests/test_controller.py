import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dataclasses

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from kubescope.gabi import ASSISTANTS, controller, runner
from kubescope.gabi.actions import BY_NAME, Request
from kubescope.gabi.controller import GabiController, GabiPort
from kubescope.gabi.panel import BUBBLE, MARGIN
from kubescope.gabi.settings import GabiSettings
from tests.conftest import Store

application = QApplication.instance() or QApplication([])
CLAUDE = ASSISTANTS["claude"]
CODEX = ASSISTANTS["codex"]


class FakeApp:
    write_mode = False
    language = "auto"
    resolved_language = "en_US"
    language_name = "English"
    language_names = ("English", "Portuguese")


class Setup:
    def __init__(self, tmp_path) -> None:
        self.settings = GabiSettings(Store())
        self.settings.assistant_enabled = True
        self.app = FakeApp()
        self.parent = QWidget()
        self.central = QWidget(self.parent)
        self.parent.resize(900, 600)
        self.parent.show()
        self.context = "prod"
        self.invoked: list[tuple] = []
        self.invoke_answer: object = None
        self.messages: list[tuple] = []
        self.settings_shown = 0
        self.corners: list[int] = []
        self.menu_hidden: list[bool] = []
        self.smaller: list[bool] = []
        self.actions: list[tuple] = []
        self.port = GabiPort(
            settings=self.settings,
            app=self.app,  # type: ignore[arg-type]
            parent=self.parent,
            central=self.central,
            invoke=self.invoke,
            context=lambda: self.context,
            screen=lambda: "the screen",
            show_message=lambda icon, title, text: self.messages.append(
                (icon, title, text)
            ),
            run_action=self.run_action,
            style_box=lambda box: None,
            show_settings=lambda: setattr(
                self, "settings_shown", self.settings_shown + 1
            ),
            reserve_corner=self.corners.append,
            hide_side_menu=self.menu_hidden.append,
            content_area=lambda: (0, 40, 900, 500),
            smaller_window=self.smaller.append,
            history_path=tmp_path / "history.json",
        )

    def invoke(self, name, **arguments):
        self.invoked.append((name, arguments))
        return self.invoke_answer

    def run_action(self, function, done, *arguments, on_error=None, quiet=False):
        self.actions.append((function, arguments))
        try:
            answer = function(*arguments)
        except Exception as error:
            assert on_error is not None
            on_error(str(error))
            return
        done(answer)

    def make(self) -> GabiController:
        self.controller = GabiController(self.port)
        return self.controller


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "installed_assistants", lambda: [CLAUDE, CODEX])
    made = Setup(tmp_path)
    yield made
    if hasattr(made, "controller"):
        made.controller.end_chat()
        made.controller.dock.dispose()
    made.parent.close()
    runner.CUSTOM_PROGRAMS.clear()


@pytest.fixture
def agreed(setup):
    setup.settings.assistant_consent = True
    return setup


def answer(monkeypatch, yes: bool) -> list[str]:
    asked: list[str] = []

    def question(parent, title, text, *args, **kwargs):
        asked.append(text)
        return QMessageBox.StandardButton.Yes if yes else QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


def test_the_button_and_the_corner_follow_the_setting(setup) -> None:
    gabi = setup.make()

    assert gabi.dock.bubble.isVisibleTo(setup.central)
    assert setup.corners[-1] == BUBBLE + MARGIN

    setup.settings.assistant_enabled = False
    gabi.make_room()
    assert setup.corners[-1] == 0


def test_the_models_and_efforts_of_the_settings_go_to_the_runner(setup) -> None:
    setup.settings.assistant_models = {"claude": "opus"}
    setup.settings.assistant_efforts = {"claude": "high"}

    setup.make()

    assert runner.CUSTOM_MODELS["claude"] == "opus"
    assert runner.CUSTOM_EFFORTS["claude"] == "high"


def test_applying_the_settings_keeps_them_and_the_window_follows(setup) -> None:
    gabi = setup.make()

    gabi.apply_settings(
        False, "codex", {"codex": "/bin/x"}, {"codex": "m"}, {"codex": "low"}
    )

    settings = setup.settings
    assert settings.assistant_enabled is False and settings.assistant == "codex"
    assert settings.assistant_programs == {"codex": "/bin/x"}
    assert runner.CUSTOM_PROGRAMS == {"codex": "/bin/x"}
    assert runner.CUSTOM_MODELS["codex"] == "m"
    assert gabi.dock.bubble.isHidden() and setup.corners[-1] == 0


def test_the_theme_and_the_language_reach_the_dock_and_the_chat(agreed) -> None:
    gabi = agreed.make()
    gabi.restyle()
    gabi.retranslate()
    gabi.open()

    gabi.restyle()  # with a chat open too

    assert gabi.tab is not None


def test_a_chat_belongs_to_one_context(agreed) -> None:
    gabi = agreed.make()
    gabi.context_changed()  # nothing open: nothing to do
    gabi.open()
    gabi.context_changed()  # the same context
    assert gabi.tab is not None

    agreed.context = "staging"
    gabi._switching = True
    gabi.context_changed()  # the assistant itself moved the window
    assert gabi.tab is not None
    gabi._switching = False
    gabi.context_changed()

    assert gabi.tab is None and not gabi.dock.is_open


def test_closing_takes_gabi_out_and_frees_the_corner(agreed) -> None:
    gabi = agreed.make()
    gabi.open()

    gabi.shutdown()
    gabi.close()

    assert gabi.tab is None and agreed.corners[-1] == 0
    gabi.shutdown()  # without a chat: nothing


def test_the_program_is_the_chosen_one_or_the_first_found(setup, monkeypatch) -> None:
    gabi = setup.make()
    assert gabi.program() is CLAUDE
    setup.settings.assistant = "codex"
    assert gabi.program() is CODEX
    setup.settings.assistant = "gone"
    assert gabi.program() is CLAUDE
    monkeypatch.setattr(controller, "installed_assistants", lambda: [])
    assert gabi.program() is None


def test_the_person_is_asked_once_whether_the_text_may_leave(
    setup, monkeypatch
) -> None:
    gabi = setup.make()
    asked = answer(monkeypatch, yes=False)

    gabi.open()
    assert gabi.tab is None and "Claude" in asked[0]
    assert setup.settings.assistant_consent is False

    answer(monkeypatch, yes=True)
    gabi.open()

    assert gabi.tab is not None and setup.settings.assistant_consent is True


def test_without_a_context_the_person_is_told_to_choose_one(agreed) -> None:
    gabi = agreed.make()
    agreed.context = ""

    gabi.open()

    assert gabi.tab is None
    assert agreed.messages[0][2] == "Choose a context first."


def test_without_a_program_the_person_is_guided(setup, monkeypatch) -> None:
    monkeypatch.setattr(controller, "installed_assistants", lambda: [])
    setup.settings.assistant_programs = {"claude": "/nowhere/claude"}
    gabi = setup.make()
    seen: dict = {}

    def run(box) -> int:
        seen["text"] = box.informativeText()
        seen["buttons"] = [button.text() for button in box.buttons()]
        seen["settings"] = next(b for b in box.buttons() if b.text() == "Open Settings")
        seen["settings"].click()
        guide = next(b for b in box.buttons() if b.text().endswith("guide"))
        opened: list[str] = []
        monkeypatch.setattr(
            controller.QDesktopServices,
            "openUrl",
            staticmethod(lambda url: opened.append(url.toString()) or True),
        )
        guide.click()
        seen["opened"] = opened
        return 0

    monkeypatch.setattr(QMessageBox, "exec", run)

    gabi.open()

    assert "neither of them" in seen["text"] and "Claude Code" in seen["text"]
    assert "The path set for" in seen["text"]
    assert "Close" in seen["buttons"] and setup.settings_shown == 1
    assert seen["opened"] and seen["opened"][0].startswith("https://")


def test_opening_makes_the_chat_once_and_reuses_it(agreed) -> None:
    gabi = agreed.make()

    gabi.open()
    first = gabi.tab
    gabi.dock.close()
    gabi.open()

    assert first is not None and gabi.tab is first and gabi.dock.is_open
    assert "Claude" in gabi.dock.panel.engine.text()


def test_auto_compacting_is_loaded_and_saved_with_the_chat(agreed) -> None:
    agreed.settings.auto_compact = False
    gabi = agreed.make()

    gabi.open()

    assert gabi.tab is not None
    assert gabi.tab.auto_compact is False
    gabi.tab._set_auto_compact(True)
    assert agreed.settings.auto_compact is True


def test_the_settings_button_steps_the_focus_page_aside_before_opening(
    agreed,
) -> None:
    gabi = agreed.make()
    gabi.toggle_focus()
    panel = gabi.dock.panel
    assert not panel.isHidden()

    panel.settings_button.click()

    assert agreed.settings_shown == 1
    assert panel.isHidden() and gabi.dock.is_open


def test_the_button_opens_and_puts_the_chat_away(agreed) -> None:
    gabi = agreed.make()

    gabi.toggle()
    assert gabi.dock.is_open
    gabi.toggle()

    assert not gabi.dock.is_open


def test_the_shortcut_opens_the_chat_and_then_puts_it_away(agreed) -> None:
    gabi = agreed.make()
    agreed.settings.assistant_enabled = False
    gabi.shortcut()  # off in the settings: nothing happens
    assert gabi.tab is None

    agreed.settings.assistant_enabled = True
    gabi.shortcut()
    assert gabi.dock.is_open and gabi.tab is not None
    tab = gabi.tab
    tab.input.hasFocus = lambda: False  # type: ignore[method-assign]
    gabi.shortcut()  # open, but the cursor is elsewhere: it goes to the chat
    assert gabi.dock.is_open
    tab.input.hasFocus = lambda: True  # type: ignore[method-assign]
    gabi.shortcut()  # the cursor is in it: put it away

    assert not gabi.dock.is_open


def test_the_engine_is_told_in_words(setup) -> None:
    gabi = setup.make()
    runner.CUSTOM_MODELS["claude"] = "opus"
    runner.CUSTOM_EFFORTS["claude"] = "high"

    assert gabi.engine(CLAUDE, None) == "Claude Code · opus · high"
    assert gabi.engine(CLAUDE, "sonnet").startswith("Claude Code · sonnet")
    runner.CUSTOM_MODELS.clear()
    runner.CUSTOM_EFFORTS.clear()
    assert gabi.engine(CODEX, None).endswith("unknown model · unknown effort") or (
        "unknown model" in gabi.engine(CODEX, None)
    )


def test_debug_says_how_the_assistant_is_set_without_secrets(agreed) -> None:
    gabi = agreed.make()
    gabi.open()
    agreed.settings.assistant_models = {"claude": "opus"}
    agreed.settings.assistant_efforts = {"claude": "high"}
    agreed.app.write_mode = True

    report = gabi.debug_report()

    assert report.startswith("/debug\nAssistant: Gabi")
    for wanted in (
        "Program: Claude Code (claude)",
        "Model: opus (set in Settings)",
        "Write mode: on",
        "Language: en_US",
        "Command: ",
    ):
        assert wanted in report
    assert "--system-prompt <" in report  # the long instruction is not in it
    runner.CUSTOM_PROGRAMS["claude"] = "/x/claude"
    assert "(set in Settings)" in gabi.debug_report().split("Program file:")[1]


def test_debug_for_a_program_that_cannot_be_told_an_effort(agreed) -> None:
    agreed.settings.assistant = "codex"
    gabi = agreed.make()
    gabi.open()

    report = gabi.debug_report()

    assert "Program: " in report and "Effort: " in report


def test_the_kube_report_is_read_off_the_thread_and_put_in_the_chat(
    agreed, monkeypatch
) -> None:
    gabi = agreed.make()
    gabi.open()
    notes: list[str] = []
    assert gabi.tab is not None
    gabi.tab.note = notes.append  # type: ignore[method-assign]

    class Cluster:
        failing = False

        def describe_kube(self):
            if self.failing:
                raise RuntimeError("no kubectl\nmore")
            return "kubectl 1.30"

    cluster = Cluster()
    monkeypatch.setattr(controller.services, "cluster", lambda: cluster)

    gabi._kube_report(gabi.tab)
    cluster.failing = True
    gabi._kube_report(gabi.tab)

    assert notes == ["/kube\nkubectl 1.30", "/kube\nno kubectl"]


def test_the_header_names_what_answers_and_the_chosen_program_takes_over(
    agreed,
) -> None:
    gabi = agreed.make()
    gabi.show_engine()  # no chat yet: nothing
    gabi.open()
    assert gabi.tab is not None

    agreed.settings.assistant = "codex"
    gabi.show_engine()

    assert gabi.tab.session.assistant is CODEX
    assert "Codex" in gabi.dock.panel.engine.text()


def test_a_change_of_language_or_mode_is_told_to_the_open_chat(agreed) -> None:
    gabi = agreed.make()
    gabi.refresh_system()  # no chat: nothing
    gabi.open()
    assert gabi.tab is not None
    before = gabi.tab.session.system

    agreed.app.write_mode = True
    gabi.refresh_system()

    assert gabi.tab.session.system != before


def test_ending_the_chat_drops_it_and_what_it_runs(agreed) -> None:
    gabi = agreed.make()
    gabi.end_chat()  # none: nothing
    gabi.open()

    gabi.end_chat()

    assert gabi.tab is None and gabi.dock.panel.engine.text() == ""


def test_the_size_of_the_panel_and_the_conversation_are_written_down(agreed) -> None:
    gabi = agreed.make()
    gabi.open()
    assert gabi.tab is not None

    gabi._keep_panel()
    gabi._keep_chat(gabi.tab)

    assert agreed.settings.assistant_panel  # something was kept
    assert gabi.history.entries("prod") == gabi.tab.entries()


@pytest.mark.parametrize("yes", [True, False])
def test_forgetting_asks_first(agreed, monkeypatch, yes) -> None:
    gabi = agreed.make()
    gabi.open()
    assert gabi.tab is not None
    gabi.history.set("prod", [])
    asked = answer(monkeypatch, yes=yes)
    first = gabi.tab

    gabi.clear_chat()

    assert "in this context" in asked[0]
    # yes: the conversation is dropped and, the panel being open, made again
    assert (gabi.tab is not first) == yes

    gabi.clear_history()
    assert "every conversation" in asked[1]


def test_forgetting_with_the_panel_closed_leaves_it_closed(agreed, monkeypatch) -> None:
    gabi = agreed.make()
    gabi.open()
    gabi.dock.close()
    answer(monkeypatch, yes=True)

    gabi.clear_history()

    assert gabi.tab is None and not gabi.dock.is_open


def test_what_the_assistant_navigates_to_is_done_as_the_person_would(agreed) -> None:
    gabi = agreed.make()
    gabi.open()
    assert gabi.tab is not None
    request = Request(BY_NAME["open_view"], {"view": "pods"})

    gabi._navigate(gabi.tab, request)

    assert agreed.invoked == [("open_view", {"report": gabi.tab.note, "view": "pods"})]


def test_moving_to_another_context_makes_the_chat_follow(agreed) -> None:
    gabi = agreed.make()
    gabi.open()
    assert gabi.tab is not None
    request = Request(BY_NAME["switch_context"], {"context": "staging"})

    agreed.invoke_answer = False  # the window did not move
    gabi._navigate(gabi.tab, request)
    assert gabi.tab.context == "prod" and not gabi._switching

    agreed.invoke_answer = True
    agreed.context = "staging"
    gabi._navigate(gabi.tab, request)

    assert gabi.tab.context == "staging" and not gabi._switching


def test_a_change_runs_only_in_the_write_mode_and_says_how_it_went(
    agreed, monkeypatch
) -> None:
    gabi = agreed.make()
    gabi.open()
    assert gabi.tab is not None
    notes: list[str] = []
    gabi.tab.note = notes.append  # type: ignore[method-assign]
    request = Request(
        BY_NAME["scale"], {"namespace": "app", "name": "api", "replicas": 2}
    )
    calls: list[tuple] = []

    def scale(*arguments):
        calls.append(arguments)
        if len(calls) == 2:
            raise RuntimeError("forbidden")

    monkeypatch.setattr(controller, "write_call", lambda r, c: (scale, (c, "api")))

    gabi._write(gabi.tab, request)
    assert notes[-1].startswith("Not run, the write mode is off") and calls == []

    agreed.app.write_mode = True
    gabi._write(gabi.tab, request)
    gabi._write(gabi.tab, request)

    assert notes[-2].startswith("Done: scale(") and "app" in notes[-2]
    assert notes[-1].startswith("Failed: scale(") and notes[-1].endswith("forbidden")


def test_a_program_that_cannot_be_told_an_effort_shows_none(setup) -> None:
    gabi = setup.make()
    runner.CUSTOM_EFFORTS["claude"] = "high"
    plain = dataclasses.replace(CLAUDE, effort_options=None)

    assert "unknown effort" in gabi.engine(plain, "opus")
    assert "high" not in gabi.engine(plain, "opus")
    runner.CUSTOM_EFFORTS.clear()


def test_debug_says_when_the_program_decides_the_model(agreed) -> None:
    gabi = agreed.make()
    gabi.open()
    assert gabi.tab is not None
    gabi.tab.session.assistant = dataclasses.replace(CLAUDE, defaults=None)

    report = gabi.debug_report()

    assert "Model: not told: the program decides" in report
    assert "Effort: not told: the program decides" in report


def test_debug_says_what_the_program_is_set_to_use(agreed) -> None:
    gabi = agreed.make()
    gabi.open()
    assert gabi.tab is not None
    gabi.tab.session.assistant = dataclasses.replace(
        CLAUDE, defaults=lambda: ("sonnet", "medium")
    )

    report = gabi.debug_report()

    assert "Model: sonnet (what Claude Code is set to use)" in report


def test_the_focus_mode_fills_the_window_and_hides_the_side_menu_while_open(
    agreed,
) -> None:
    gabi = agreed.make()
    gabi.open()
    assert agreed.menu_hidden[-1] is False and not gabi.dock.panel.new_button.isHidden()

    gabi.toggle_focus()
    assert gabi.dock.is_focused and agreed.menu_hidden[-1] is True
    assert gabi.dock.panel.geometry().getRect() == (0, 40, 900, 500)  # the pages
    assert agreed.settings.focus_mode is True

    gabi.toggle()  # put away: the menu comes back, the mode is kept
    assert agreed.menu_hidden[-1] is False and gabi.dock.is_focused
    gabi.toggle()
    assert agreed.menu_hidden[-1] is True

    gabi.dock.set_floating(True)  # focus mode cannot be detached
    assert not gabi.dock.is_floating and agreed.menu_hidden[-1] is True
    gabi.toggle_focus()
    assert agreed.menu_hidden[-1] is False and not gabi.dock.is_focused


def test_the_focus_mode_is_taken_back_on_the_next_run_and_freed_on_unload(
    agreed,
) -> None:
    agreed.settings.focus_mode = True
    gabi = agreed.make()
    assert gabi.dock.is_focused and agreed.menu_hidden[-1] is True  # open at once

    gabi.close()
    assert agreed.menu_hidden[-1] is False


def test_saving_other_settings_keeps_the_focus_mode(agreed) -> None:
    gabi = agreed.make()
    gabi.toggle_focus()

    gabi.apply_settings(True, "", {}, {}, {})

    assert agreed.settings.focus_mode is True and gabi.dock.is_focused


def test_a_new_session_starts_from_nothing_and_forgets_nothing_else(agreed) -> None:
    gabi = agreed.make()
    gabi.new_session()  # nothing open: nothing to do
    assert gabi.tab is None

    gabi.open()
    first = gabi.tab
    assert first is not None
    first.note("a note")
    first.changed.emit()
    assert gabi.history.entries("prod")
    other = agreed.context
    gabi.history.set("dev", [("user", "keep me")])

    gabi.new_session()

    assert gabi.tab is not None and gabi.tab is not first
    assert gabi.history.entries(other) == []
    assert gabi.history.entries("dev") == [("user", "keep me")]
    assert gabi.dock.is_open


def test_the_tokens_of_the_session_are_under_the_box_of_the_question(
    agreed, monkeypatch
) -> None:
    from kubescope.gabi.usage import Usage

    gabi = agreed.make()
    gabi.show_usage()  # no chat yet: nothing to tell

    gabi.open()
    label = gabi.tab.usage_label
    assert label.text() == "0 in · 0 out · 0% cached"  # none yet
    session = gabi.tab.session
    session.usage = Usage(10, 2000, 90, 0, 0.0123)
    session.last_usage = Usage(5, 1000, 45, 0, 0.0123)
    gabi.tab.usage_changed.emit()

    assert label.text() == "100 in · 2.0k out · 90% cached"
    assert "Read from the cache: 90" in label.toolTip()
    assert "Cost: $0.0123" in label.toolTip()
    assert not hasattr(gabi.dock.panel, "usage")  # and not in the header

    session.usage = Usage(10, 2, 0, 0, None)
    gabi.show_usage()
    assert "Cost" not in label.toolTip()

    monkeypatch.setattr(gabi.tab.session, "cache_left", lambda: 0)
    gabi.show_usage()
    assert label.text() == "10 in · 2 out · cache expired"


def test_in_the_focus_mode_there_is_no_button_and_the_tokens_are_under_the_box(
    agreed,
) -> None:
    from kubescope.gabi.usage import Usage

    gabi = agreed.make()
    gabi.open()
    assert not gabi.dock.bubble.isHidden() and agreed.smaller[-1] is False

    gabi.toggle_focus()
    assert gabi.dock.bubble.isHidden() and agreed.smaller[-1] is True
    gabi.tab.session.usage = Usage(10, 2000, 90, 0, None)
    gabi.show_usage()
    assert gabi.tab.usage_label.text() == "100 in · 2.0k out · 90% cached"

    gabi.toggle_focus()
    assert not gabi.dock.bubble.isHidden() and agreed.smaller[-1] is False
    assert gabi.tab.usage_label.text() == "100 in · 2.0k out · 90% cached"  # still


def test_the_focus_page_steps_aside_for_the_settings_and_comes_back(agreed) -> None:
    gabi = agreed.make()
    gabi.toggle_focus()
    panel = gabi.dock.panel
    assert not panel.isHidden()

    gabi.settings_shown(True)
    assert panel.isHidden() and gabi.dock.is_open  # not closed, only aside

    gabi.settings_shown(False)
    assert not panel.isHidden() and panel.geometry().getRect() == (0, 40, 900, 500)


def test_the_corner_panel_stays_over_the_settings(agreed) -> None:
    gabi = agreed.make()
    gabi.open()

    gabi.settings_shown(True)
    assert not gabi.dock.panel.isHidden() and not gabi.dock.is_yielding


def test_the_chat_button_returns_to_focus_mode_from_settings(agreed) -> None:
    gabi = agreed.make()
    gabi.toggle_focus()
    gabi.settings_shown(True)
    assert gabi.dock.panel.isHidden() and not gabi.dock.bubble.isHidden()

    gabi.toggle()

    name, arguments = agreed.invoked[-1]
    assert name == "open_page" and arguments["page"] == "overview"
    assert callable(arguments["report"])
    gabi.settings_shown(False)
    assert not gabi.dock.panel.isHidden() and gabi.dock.bubble.isHidden()


def test_in_the_focus_mode_a_page_the_assistant_opens_is_not_covered(agreed) -> None:
    from kubescope.gabi.actions import BY_NAME, Request

    gabi = agreed.make()
    gabi.toggle_focus()
    assert not gabi.dock.panel.isHidden()

    other = next(one for one in BY_NAME.values() if one.name != "switch_context")
    gabi._navigate(gabi.tab, Request(other, {}))

    assert gabi.dock.panel.isHidden() and gabi.dock.is_open
    assert agreed.menu_hidden[-1] is False  # the menu is back, to go on
    assert not gabi.dock.bubble.isHidden()  # and so is the way back

    gabi.toggle()  # the button brings the chat back
    assert not gabi.dock.panel.isHidden() and gabi.dock.bubble.isHidden()
    assert agreed.menu_hidden[-1] is True


def test_the_shortcut_also_brings_the_chat_back_from_a_page(agreed) -> None:
    from kubescope.gabi.actions import BY_NAME, Request

    gabi = agreed.make()
    gabi.toggle_focus()
    other = next(one for one in BY_NAME.values() if one.name != "switch_context")
    gabi._navigate(gabi.tab, Request(other, {}))

    gabi.shortcut()
    assert not gabi.dock.panel.isHidden()


def test_outside_the_focus_mode_the_chat_stays_where_it_is_when_it_navigates(
    agreed,
) -> None:
    from kubescope.gabi.actions import BY_NAME, Request

    gabi = agreed.make()
    gabi.open()
    other = next(one for one in BY_NAME.values() if one.name != "switch_context")
    gabi._navigate(gabi.tab, Request(other, {}))

    assert not gabi.dock.panel.isHidden() and not gabi.dock.is_yielding
