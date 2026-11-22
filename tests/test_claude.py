import json

import pytest

import kubescope.gabi as assistant
from kubescope.gabi import claude, runner
from kubescope.gabi.runner import AssistantError


def _delta(text: str) -> str:
    event = {
        "type": "content_block_delta",
        "delta": {"type": "text_delta", "text": text},
    }
    return json.dumps({"type": "stream_event", "event": event}) + "\n"


def test_claude_runs_with_nothing_it_could_act_on_the_machine_with(monkeypatch) -> None:
    monkeypatch.setattr(runner, "find_program", lambda program: None)
    options = runner.command(claude.CLAUDE)

    assert options[:2] == ["claude", "-p"]
    assert options[options.index("--tools") + 1] == ""
    assert "--no-session-persistence" in options
    assert "--strict-mcp-config" in options  # no MCP servers of the person
    assert "--disable-slash-commands" in options  # no skills of the person
    assert options[options.index("--setting-sources") + 1] == ""  # no settings
    assert options[options.index("--system-prompt") + 1] == runner.SYSTEM_PROMPT
    assert "--model" not in options
    assert runner.command(claude.CLAUDE, "opus")[-2:] == ["--model", "opus"]
    custom = runner.command(claude.CLAUDE, None, "my rules")
    assert custom[custom.index("--system-prompt") + 1] == "my rules"


def test_a_line_gives_its_text_or_its_error() -> None:
    assert claude.parse_line(_delta("hi")) == ("hi", "")
    assert claude.parse_line("not json\n") == ("", "")
    assert claude.parse_line("[1]\n") == ("", "")
    assert claude.parse_line('{"type": "system"}\n') == ("", "")
    assert claude.parse_line('{"event": {"delta": {"text": 3}}}\n') == ("", "")
    failed = json.dumps({"type": "result", "is_error": True, "result": "Not logged in"})
    assert claude.parse_line(failed) == ("", "Not logged in")
    unknown = json.dumps({"type": "result", "is_error": True})
    assert claude.parse_line(unknown) == ("", "The assistant failed")
    done = json.dumps({"type": "result", "is_error": False, "result": "ok"})
    assert claude.parse_line(done) == ("", "")


def test_the_installed_assistants_are_the_known_ones_the_system_has(
    monkeypatch,
) -> None:
    assert assistant.ASSISTANTS["claude"] is claude.CLAUDE

    monkeypatch.setattr(assistant, "is_available", lambda one: one.key == "claude")
    assert assistant.installed() == [claude.CLAUDE]
    monkeypatch.setattr(assistant, "is_available", lambda one: False)
    assert assistant.installed() == []


def test_claude_takes_images_as_one_message_with_the_question() -> None:
    import base64

    from kubescope.gabi.attachments import Attachment

    image = Attachment("shot.png", "image", b"\x89PNGdata", "image/png")

    options = runner.command(claude.CLAUDE, None, "rules", with_images=True)
    line = claude.image_payload("what is this?", [image])

    assert options[options.index("--input-format") + 1] == "stream-json"
    assert options[options.index("--tools") + 1] == ""  # still no tools
    assert "--input-format" not in runner.command(claude.CLAUDE)
    assert claude.CLAUDE.takes_images and line.endswith("\n")
    message = json.loads(line)["message"]
    assert message["role"] == "user"
    first, second = message["content"]
    assert first["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(b"\x89PNGdata").decode(),
    }
    assert second == {"type": "text", "text": "what is this?"}


def test_the_defaults_of_claude_code_come_from_its_settings(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert claude.defaults() == ("", "")  # no settings

    (tmp_path / "settings.json").write_text(
        '{"model": "sonnet", "effortLevel": "low"}', encoding="utf-8"
    )
    assert claude.defaults() == ("sonnet", "low")

    (tmp_path / "settings.json").write_text('{"model": 3}', encoding="utf-8")
    assert claude.defaults() == ("", "")
    (tmp_path / "settings.json").write_text("[", encoding="utf-8")
    assert claude.defaults() == ("", "")


class FakeChild:
    """What `ClaudeLive` talks to: lines to read, what was written, how it
    ends."""

    def __init__(self, lines, why="") -> None:
        self._lines, self.why = lines, why
        self.written: list[str] = []
        self.up = True
        self.closed = False

    @property
    def alive(self) -> bool:
        return self.up

    def write(self, text) -> None:
        self.written.append(text)

    def lines(self):
        return iter(self._lines)

    def reason(self) -> str:
        return self.why

    def close(self) -> None:
        self.closed = True


def _result(error=False, text="") -> str:
    event = {"type": "result", "is_error": error, "result": text}
    event["usage"] = {"input_tokens": 2, "output_tokens": 3}
    return json.dumps(event) + "\n"


def test_a_kept_program_gets_a_message_and_answers_until_its_result() -> None:
    child = FakeChild(
        [_delta("Hel"), "a notice\n", _delta("lo"), _result(), _delta("x")]
    )
    live = claude.ClaudeLive(child)  # type: ignore[arg-type]
    used: list = []

    assert list(live.ask("hi", (), used.append)) == ["Hel", "lo"]  # not what follows

    message = json.loads(child.written[0])
    assert message["message"]["content"][-1] == {"type": "text", "text": "hi"}
    assert [u.output_tokens for u in used] == [3] and live.alive
    live.close()
    assert child.closed


def test_a_kept_program_that_reports_an_error_or_stops_says_why() -> None:
    failing = claude.ClaudeLive(FakeChild([_result(True, "no quota")]))  # type: ignore[arg-type]
    with pytest.raises(AssistantError, match="no quota"):
        list(failing.ask("hi", (), lambda used: None))

    gone = claude.ClaudeLive(FakeChild([_delta("a")], why="killed"))  # type: ignore[arg-type]
    with pytest.raises(AssistantError, match="killed"):
        list(gone.ask("hi", (), lambda used: None))

    silent = claude.ClaudeLive(FakeChild([]))  # type: ignore[arg-type]
    with pytest.raises(AssistantError, match="without an answer"):
        list(silent.ask("hi", (), lambda used: None))


def test_the_program_is_started_for_a_conversation_with_the_options_of_a_question(
    monkeypatch,
) -> None:
    started: list = []
    monkeypatch.setattr(
        claude, "Child", lambda arguments: started.append(arguments) or FakeChild([])
    )
    monkeypatch.setattr(runner, "find_program", lambda program: None)

    live = claude.open_live("opus", "my rules")

    [arguments] = started
    assert arguments[:2] == ["claude", "-p"]
    assert arguments[arguments.index("--input-format") + 1] == "stream-json"
    assert arguments[arguments.index("--system-prompt") + 1] == "my rules"
    assert arguments[arguments.index("--model") + 1] == "opus" and live.alive
    assert claude.CLAUDE.open_live is claude.open_live


def test_a_line_that_is_not_an_event_is_not_a_result() -> None:
    assert claude._is_result("a notice") is False
    assert claude._is_result(json.dumps({"type": "assistant"})) is False
