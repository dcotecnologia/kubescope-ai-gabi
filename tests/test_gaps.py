import pytest
from kubescope.extensions import testing
from kubescope.extensions.components import UiComponents

import kubescope.gabi as gabi
from kubescope.gabi import claude, extension
from kubescope.gabi.session import ChatSession
from kubescope.gabi.tab import AssistantTab as _AssistantTab
from tests.test_tab import FAKE

application = testing.application()


def AssistantTab(*args, **kwargs):  # noqa: N802
    return _AssistantTab(*args, components=UiComponents(), **kwargs)


def test_the_app_runs_gabi_through_her_extension(monkeypatch) -> None:
    given = []
    monkeypatch.setattr(extension, "activate", given.append)

    gabi.activate("the context")

    assert given == ["the context"]


def test_the_quickstart_of_claude_code_is_in_the_language_of_the_app() -> None:
    assert claude.guide("pt_BR").endswith("/pt/quickstart")
    assert claude.guide("en_US").endswith("/en/quickstart")


def test_the_assistants_installed_are_the_ones_whose_program_is_found(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        gabi, "is_available", lambda assistant: assistant.key == "codex"
    )

    assert [one.key for one in gabi.installed()] == ["codex"]


def test_another_assistant_takes_over_the_conversation() -> None:
    tab = AssistantTab(ChatSession(FAKE), "ctx", lambda: False)
    other = FAKE.__class__(
        "other", "Other", "other-ai", lambda m, s: [], lambda line: ("", "")
    )

    tab.use(other)

    assert tab.session.assistant is other


@pytest.mark.parametrize("command", ["/debug", "/kube", "/kubectl"])
def test_the_commands_of_the_chat_are_answered_here_not_by_the_program(command) -> None:
    tab = AssistantTab(ChatSession(FAKE), "ctx", lambda: False)
    tab.debug_report = lambda: "the report"
    asked: list[int] = []
    tab.kube_requested.connect(lambda: asked.append(1))
    shown: list[str] = []
    tab.note = shown.append  # type: ignore[method-assign]
    tab.input.setPlainText(command)

    tab.submit()

    assert tab.input.toPlainText() == "" and not tab.busy
    assert (shown == ["the report"]) == (command == "/debug")
    assert asked == ([] if command == "/debug" else [1])
