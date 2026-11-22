import io
import sys

import pytest
from kubescope.sdk.errors import ClusterError

from kubescope import writes
from kubescope.gabi import cli as cli_chat
from kubescope.gabi import runner
from kubescope.gabi.actions import FENCE
from kubescope.gabi.history import History
from kubescope.gabi.runner import Assistant, AssistantError
from kubescope.gabi.session import ChatSession


def _assistant(key="claude", defaults=None):
    return Assistant(
        key, key.title(), key, lambda m, s: [], lambda line: ("", ""), defaults=defaults
    )


class Brain:
    """Stands in for the program: answers each question with the next reply."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, assistant, prompt, model, system, images, on_usage=None):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        yield from reply


def block(**fields):
    import json

    return f"```{FENCE}\n{json.dumps(fields)}\n```\n"


@pytest.fixture(autouse=True)
def world(monkeypatch, app):
    app.preferences.assistant_consent = True  # the person agreed already
    monkeypatch.setattr(cli_chat, "installed_assistants", lambda: [_assistant()])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    yield
    runner.CUSTOM_PROGRAMS.clear()
    runner.CUSTOM_MODELS.clear()
    runner.CUSTOM_EFFORTS.clear()


def _brain(monkeypatch, *replies):
    brain = Brain(*replies)
    monkeypatch.setattr(runner, "ask", brain)
    return brain


def _typed(monkeypatch, *lines):
    given = iter(lines)

    def read(_prompt):
        line = next(given)
        if isinstance(line, BaseException):
            raise line
        return line

    monkeypatch.setattr("builtins.input", read)


def _chat(tmp_path, write_mode=False, read=None, confirm=None):
    session = ChatSession(_assistant())
    chat = cli_chat.Chat(
        session,
        "a",
        write_mode,
        History(tmp_path / "h.json"),
        read or (lambda *_: "R"),
        confirm or (lambda question: False),
    )
    return chat


def test_one_shot_message(monkeypatch, capsys):
    brain = _brain(monkeypatch, ["Hello ", "there"])
    assert cli_chat.main(["--context", "a", "how", "are", "you"]) == 0
    assert capsys.readouterr().out == "Hello there\n"
    assert "User: how are you" in brain.prompts[0]


def test_the_conversation(monkeypatch, capsys, tmp_path):
    _brain(monkeypatch, ["one"], ["two"])
    _typed(monkeypatch, "", "/help", "q1", KeyboardInterrupt(), "/clear", "q2", "/exit")
    assert cli_chat.main(["--context", "a"]) == 0
    captured = capsys.readouterr()
    assert "/clear" in captured.out and "one" in captured.out and "two" in captured.out
    assert "Forgotten" in captured.err and "Hi, I'm Gabi" in captured.err


def test_the_conversation_ends_with_ctrl_d(monkeypatch):
    _typed(monkeypatch, EOFError())
    assert cli_chat.main(["--context", "a"]) == 0


def test_the_conversation_is_resumed(monkeypatch, app):
    History(app.data_directory / "history.json").set(
        "a", [("user", "before"), ("assistant", "yes"), ("app", "note")]
    )
    brain = _brain(monkeypatch, ["ok"])
    assert cli_chat.main(["--context", "a", "now"]) == 0
    assert "User: before" in brain.prompts[0] and "App" not in brain.prompts[0]
    kept = History(app.data_directory / "history.json").entries("a")
    assert kept[-2:] == [("user", "now"), ("assistant", "ok")]


def test_stopping_an_answer(monkeypatch, capsys):
    def stop(*_):
        raise KeyboardInterrupt
        yield

    monkeypatch.setattr(runner, "ask", stop)
    _typed(monkeypatch, "q", "/exit")
    assert cli_chat.main(["--context", "a"]) == 0
    assert "[stopped]" in capsys.readouterr().err


def test_a_failed_answer(monkeypatch, capsys, app):
    _brain(monkeypatch, AssistantError("no sign in"))
    assert cli_chat.main(["--context", "a", "q"]) == 0
    assert "could not answer: no sign in" in capsys.readouterr().err
    assert History(app.data_directory / "history.json").entries("a") == []


def test_the_assistant_is_off(capsys, app):
    app.preferences.assistant_enabled = False
    assert cli_chat.main(["--context", "a", "q"]) == 1
    assert "assistant is off" in capsys.readouterr().err


def test_no_program_installed(monkeypatch, capsys):
    monkeypatch.setattr(cli_chat, "installed_assistants", lambda: [])
    assert cli_chat.main(["--context", "a", "q"]) == 1
    assert "installed and signed in" in capsys.readouterr().err


def test_choosing_the_program(monkeypatch, capsys, app):
    both = [_assistant("claude"), _assistant("codex")]
    monkeypatch.setattr(cli_chat, "installed_assistants", lambda: both)
    settings = app.preferences
    assert cli_chat._choose(settings, None).key == "claude"
    assert cli_chat._choose(settings, "codex").key == "codex"
    settings.assistant = "codex"
    assert cli_chat._choose(settings, None).key == "codex"
    settings.assistant = "gone"
    assert cli_chat._choose(settings, None).key == "claude"
    monkeypatch.setattr(cli_chat, "installed_assistants", lambda: both[:1])
    with pytest.raises(ClusterError, match="codex is not installed"):
        cli_chat._choose(settings, "codex")


def test_consent_needs_a_terminal(capsys, app):
    app.preferences.assistant_consent = False
    assert cli_chat.main(["--context", "a", "q"]) == 1
    assert "once on a terminal" in capsys.readouterr().err


def test_consent_given_and_refused(monkeypatch, capsys, app):
    app.preferences.assistant_consent = False
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert app.cli is not None
    app.cli.answer = False
    assert cli_chat.main(["--context", "a", "q"]) == 1
    assert "not allowed" in capsys.readouterr().err
    assert app.cli.asked == ["Use the assistant?"]
    assert app.preferences.assistant_consent is False
    app.cli.answer = True
    cli_chat._consent(app.preferences, _assistant(), app.cli.confirm)
    assert app.preferences.assistant_consent is True
    assert app.settings["consent"] is True  # and it was saved with the settings


def test_consent_that_cannot_be_saved(monkeypatch, capsys, app):
    app.preferences.assistant_consent = False
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    app.settings.failure = OSError(13, "denied")

    cli_chat._consent(app.preferences, _assistant(), lambda question: True)

    assert "Could not save the settings" in capsys.readouterr().err


def test_no_context_without_terminal(capsys):
    assert cli_chat.main(["q"]) == 1
    assert "Pass --context" in capsys.readouterr().err


def test_interrupted_at_the_start(monkeypatch, app):
    def stop(*_):
        raise KeyboardInterrupt

    assert app.cli is not None
    monkeypatch.setattr(app.cli, "choose_context", stop)
    assert cli_chat.main([]) == 130


def test_the_choices_of_the_program_are_given_to_the_runner(app):
    settings = app.preferences
    settings.assistant_programs = {"claude": "/x/claude"}
    settings.assistant_models = {"claude": "big"}
    settings.assistant_efforts = {}
    cli_chat._sync_choices(settings)
    assert runner.CUSTOM_PROGRAMS == {"claude": "/x/claude"}
    assert runner.CUSTOM_MODELS["claude"] == "big"


def test_the_defaults_of_the_program(monkeypatch, app):
    one = _assistant("claude", defaults=lambda: ("small", "high"))
    monkeypatch.setattr(cli_chat, "ASSISTANTS", {"claude": one})
    cli_chat._sync_choices(app.preferences)
    assert runner.CUSTOM_MODELS == {"claude": "small"}
    assert runner.CUSTOM_EFFORTS == {"claude": "high"}


def test_the_language_is_the_one_of_the_app_and_falls_back_to_english(app):
    app.language_name = "Portuguese"
    assert cli_chat._language() == "Portuguese"

    del app.language_name  # the app cannot say it

    assert cli_chat._language() == "English"


def test_the_action_blocks_are_not_shown(monkeypatch, capsys):
    _brain(
        monkeypatch,
        ["Look ", "```kubescope", "-action\n", '{"action": "bad"}\n', "```\n", "done"],
    )
    assert cli_chat.main(["--context", "a", "q"]) == 0
    captured = capsys.readouterr()
    assert captured.out.split() == ["Look", "done"]
    assert "Ignored an action" in captured.err


def test_an_unclosed_block_is_held_back(tmp_path):
    visible = cli_chat.Chat._visible
    assert visible("Hi ```kubescope-action\n{", final=False) == "Hi "
    assert visible("Hi ``", final=False) == "Hi "
    assert visible("Hi there  ", final=True) == "Hi there"


def test_the_escape_character_never_reaches_the_terminal(monkeypatch, capsys):
    _brain(monkeypatch, ["a\x1b[31mred"])
    cli_chat.main(["--context", "a", "q"])
    assert "\x1b" not in capsys.readouterr().out


def test_navigation_is_only_told(monkeypatch, capsys):
    _brain(monkeypatch, [block(action="open_view", view="pods")])
    cli_chat.main(["--context", "a", "q"])
    assert "no meaning on the command line" in capsys.readouterr().err


def test_a_read_goes_back_to_the_assistant(monkeypatch, tmp_path, capsys):
    brain = _brain(
        monkeypatch,
        [block(action="list", view="pods", namespace="ns")],
        ["Found it"],
    )
    reads = []
    chat = _chat(tmp_path, read=lambda request, ctx: reads.append(ctx) or "THE-LIST")
    chat.ask("what runs?")
    assert reads == ["a"] and "THE-LIST" in brain.prompts[1]
    assert "Found it" in capsys.readouterr().out
    assert any(role == "app" for role, _ in chat.entries)


def test_too_many_reads(monkeypatch, tmp_path, capsys):
    reply = [block(action="list", view="pods", namespace="")]
    _brain(monkeypatch, *([reply] * (cli_chat.MAX_FOLLOW_UPS + 1)))
    chat = _chat(tmp_path)
    chat.ask("loop")
    assert "too many reads" in capsys.readouterr().err


def test_a_failed_follow_up_stops(monkeypatch, tmp_path):
    _brain(
        monkeypatch,
        [block(action="list", view="pods", namespace="")],
        AssistantError("gone"),
    )
    chat = _chat(tmp_path)
    chat.ask("q")
    assert [role for role, _ in chat.entries] == ["user", "assistant"]


WRITE = block(action="scale", namespace="ns", name="api", replicas=2)


def test_a_write_in_read_only_mode(monkeypatch, tmp_path, capsys):
    _brain(monkeypatch, [WRITE])
    _chat(tmp_path).ask("scale it")
    assert "Read-only mode" in capsys.readouterr().err


def test_a_write_needs_a_terminal(monkeypatch, tmp_path, capsys):
    _brain(monkeypatch, [WRITE])
    _chat(tmp_path, write_mode=True).ask("scale it")
    assert "without a terminal" in capsys.readouterr().err


def test_a_write_confirmed_cancelled_and_failed(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(writes, "scale_deployment", lambda *a: calls.append(a))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter([True, False, True])
    _brain(monkeypatch, [WRITE], [WRITE], [WRITE])
    chat = _chat(tmp_path, write_mode=True, confirm=lambda question: next(answers))
    chat.ask("1")
    assert calls == [("a", "ns", "api", 2)]
    chat.ask("2")
    assert len(calls) == 1

    def refuse(*_):
        raise ClusterError("forbidden")

    monkeypatch.setattr(writes, "scale_deployment", refuse)
    chat.ask("3")
    err = capsys.readouterr().err
    assert "Ran scale" in err and "Cancelled scale" in err and "forbidden" in err


def test_the_answer_is_painted_on_a_terminal(monkeypatch, capsys):
    monkeypatch.setenv("FORCE_COLOR", "1")
    _brain(monkeypatch, ["Use **kubectl**\n- `get`", " pods\ndone"])
    assert cli_chat.main(["--context", "a", "q"]) == 0
    out = capsys.readouterr().out
    assert "\x1b[1;35mGabi\x1b[0m" in out and "\x1b[1mkubectl\x1b[0m" in out
    assert "•" in out and "done" in out


def test_the_answer_painted_ends_with_its_last_line(monkeypatch, capsys):
    monkeypatch.setenv("FORCE_COLOR", "1")
    _brain(monkeypatch, ["one\n"])
    cli_chat.main(["--context", "a", "q"])
    assert capsys.readouterr().out.endswith("one\n")


def test_the_prompt_is_painted_for_readline(monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setattr(cli_chat, "_READLINE", True)
    prompt = cli_chat._prompt()
    assert prompt == "\x01\x1b[1;32m\x02you>\x01\x1b[0m\x02 "
    monkeypatch.setattr(cli_chat, "_READLINE", False)
    assert cli_chat._prompt() == "\x1b[1;32myou>\x1b[0m "
    monkeypatch.delenv("FORCE_COLOR")
    monkeypatch.setattr(
        sys, "stdout", io.StringIO()
    )  # pytest runs with -s: not a terminal
    assert cli_chat._prompt() == "you> "


def test_the_old_conversations_move_when_the_command_runs(monkeypatch, app):
    from kubescope.sdk.paths import config_directory

    from kubescope.gabi.history import OLD_NAME

    old = config_directory() / OLD_NAME
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("{}")
    _brain(monkeypatch, ["hi"])

    assert cli_chat.main(["--context", "a", "q"]) == 0

    assert (app.data_directory / "history.json").exists() and not old.exists()


def test_the_command_says_it_needs_the_terminal_when_it_is_not_there(capsys, app):
    app.cli = None

    assert cli_chat.main(["--context", "a", "q"]) == 1

    assert "runs in the terminal" in capsys.readouterr().err
