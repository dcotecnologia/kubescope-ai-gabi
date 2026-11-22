"""The `claude` program, as an assistant."""

import json
import os
from collections.abc import Callable, Generator, Sequence
from pathlib import Path
from typing import Any

from kubescope.gabi import runner
from kubescope.gabi.attachments import Attachment
from kubescope.gabi.runner import Assistant, AssistantError, Child
from kubescope.gabi.usage import Usage, count


def options(model: str | None, system: str) -> list[str]:
    """No tools, so it cannot read a file or run a command, and no saved
    session.

    Nothing of the person's own Claude Code is sent along either: not
    the MCP servers, nor the skills and commands, nor the settings of
    the user (their instructions and memory), which would be sent with
    every question and cost tokens that have nothing to do with the
    cluster.
    """
    arguments = [
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--tools",
        "",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--setting-sources",
        "",
        "--system-prompt",
        system,
    ]
    return [*arguments, "--model", model] if model else arguments


def image_options(model: str | None, system: str) -> list[str]:
    """The same, reading the question as a message, which can hold images."""
    return [*options(model, system), "--input-format", "stream-json"]


def image_payload(prompt: str, images: Sequence[Attachment]) -> str:
    """The question and its images as the one message the program reads."""
    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.media_type,
                "data": image.base64,
            },
        }
        for image in images
    ]
    content.append({"type": "text", "text": prompt})
    message = {"type": "user", "message": {"role": "user", "content": content}}
    return json.dumps(message) + "\n"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_line(line: str) -> tuple[str, str]:
    """The text a line of its output adds, and the error it reports."""
    try:
        event = _dict(json.loads(line))
    except ValueError:  # not an event: a notice of the program
        return "", ""
    if event.get("type") == "result" and event.get("is_error"):
        return "", str(event.get("result") or "The assistant failed")
    delta = _dict(_dict(event.get("event")).get("delta"))
    text = delta.get("text")
    return (text if isinstance(text, str) else ""), ""


def parse_usage(line: str) -> Usage | None:
    """The tokens of an answer, which the final line of its output reports."""
    try:
        event = _dict(json.loads(line))
    except ValueError:
        return None
    if event.get("type") != "result":
        return None
    used = _dict(event.get("usage"))
    cost: Any = event.get("total_cost_usd")
    written = _dict(used.get("cache_creation"))  # by how long the cache is kept
    ttl = 3600 if count(written.get("ephemeral_1h_input_tokens")) else 0
    ttl = ttl or (300 if count(written.get("ephemeral_5m_input_tokens")) else 0)
    return Usage(
        count(used.get("input_tokens")),
        count(used.get("output_tokens")),
        count(used.get("cache_read_input_tokens")),
        count(used.get("cache_creation_input_tokens")),
        float(cost) if isinstance(cost, int | float) else None,
        ttl,
    )


def _is_result(line: str) -> bool:
    try:
        return _dict(json.loads(line)).get("type") == "result"
    except ValueError:
        return False


class ClaudeLive:
    """One `claude` program kept running for a conversation: the messages go in
    one by one, and it keeps what was said in memory (it is told to save no
    session), so each question sends only what is new."""

    def __init__(self, child: Child) -> None:
        self.child = child

    @property
    def alive(self) -> bool:
        return self.child.alive

    def ask(
        self,
        text: str,
        images: Sequence[Attachment],
        on_usage: Callable[[Usage], None],
    ) -> Generator[str]:
        self.child.write(image_payload(text, images))
        for line in self.child.lines():
            piece, error = parse_line(line)
            if error:
                raise AssistantError(error)
            if piece:
                yield piece
            used = parse_usage(line)
            if used is not None:
                on_usage(used)
            if _is_result(line):  # the answer is over, the program waits
                return
        raise AssistantError(
            self.child.reason() or "The assistant stopped without an answer"
        )

    def close(self) -> None:
        self.child.close()


def open_live(model: str | None, system: str) -> ClaudeLive:
    """Start `claude` for a conversation, with the same options as for a
    question, which take messages one by one."""
    return ClaudeLive(Child(runner.command(CLAUDE, model, system, with_images=True)))


def defaults() -> tuple[str, str]:
    """The model and the effort in the settings of Claude Code."""
    folder = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    try:
        data = _dict(json.loads((Path(folder) / "settings.json").read_text("utf-8")))
    except OSError, ValueError:
        return "", ""
    model, effort = data.get("model"), data.get("effortLevel")
    return (
        model if isinstance(model, str) else "",
        effort if isinstance(effort, str) else "",
    )


def guide(language: str) -> str:
    """The quickstart of Claude Code, in Portuguese or English."""
    return (
        f"https://code.claude.com/docs/{'pt' if language.startswith('pt') else 'en'}"
        "/quickstart"
    )


CLAUDE = Assistant(
    "claude",
    "Claude Code",
    "claude",
    options,
    parse_line,
    image_options,
    image_payload,
    guide=guide,
    models=("fable", "opus", "sonnet", "haiku"),
    efforts=("low", "medium", "high", "xhigh", "max"),
    effort_options=lambda effort: ["--effort", effort],
    defaults=defaults,
    parse_usage=parse_usage,
    open_live=open_live,
)
