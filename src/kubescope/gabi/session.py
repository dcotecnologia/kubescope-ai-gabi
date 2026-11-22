"""A conversation with an assistant.

A program that can keep a conversation (it stays running, and holds what
was said in memory only) is sent just what is new with each question.
The ones that answer one question each are sent the whole conversation
every time, and when it is longer than the limit the oldest messages are
left out. It works the same with any of them and the app decides what
leaves the machine.
"""

from collections.abc import Generator
from dataclasses import dataclass
from typing import Literal

from kubescope.gabi import attachments as files
from kubescope.gabi import runner
from kubescope.gabi.attachments import Attachment
from kubescope.gabi.runner import Assistant, AssistantError
from kubescope.gabi.usage import Usage

HISTORY_LIMIT = 40_000  # characters of the conversation that are sent
COMPACT_TOKENS = 100_000  # the context after which a long conversation is compacted
SUMMARY_INPUT_LIMIT = 150_000  # characters of the conversation a summary is made of
SUMMARY_LABEL = "[Summary of the conversation so far]"
SUMMARY_REQUEST = (
    "Write a summary of the conversation above so that it can be carried on "
    "from the summary alone: the cluster and what the person is looking into, "
    "what was found, what was decided or changed, the names of the resources "
    "that matter and what is still open. Be complete and brief, in the "
    "language of the conversation, and answer with the summary only."
)

Role = Literal["user", "assistant"]
_LABELS: dict[Role, str] = {"user": "User", "assistant": "Assistant"}


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    text: str
    screen: str = ""  # what the person saw when they asked; sent with the newest only
    attachments: tuple[Attachment, ...] = ()  # sent with the newest only, never kept


class ChatSession:
    def __init__(
        self,
        assistant: Assistant,
        model: str | None = None,
        system: str = runner.SYSTEM_PROMPT,
        limit: int = HISTORY_LIMIT,
    ) -> None:
        self.assistant = assistant
        self.model = model
        self.system = system
        self.limit = limit
        self.messages: list[Message] = []
        self.usage = Usage()  # the tokens of every answer of this conversation
        self.last_usage = Usage()  # and of the newest one
        self._live: runner.Live | None = None  # the program kept running
        self._live_key: tuple[object, ...] | None = None  # how it was started
        self._primed = False  # it already has the conversation up to now

    def prompt(self) -> str:
        """The conversation to send: the newest messages that fit, and the last
        one is always there."""
        turns = self._turns(self.messages, self.limit)
        newest = self.messages[-1] if self.messages else None
        if newest is not None and (block := files.text_block(newest.attachments)):
            turns += f"\n\n{block}"
        if self.messages and self.messages[-1].screen:
            turns += (
                "\n\n[What the person sees in KubeScope right now]\n"
                f"{self.messages[-1].screen}"
            )
        return f"{turns}\n\nAnswer the last message of the User as the Assistant."

    def _key(self) -> tuple[object, ...]:
        """What the program running depends on: when one of these changes, it
        is started again."""
        key = self.assistant.key
        return (
            key,
            self.model,
            self.system,
            runner.CUSTOM_MODELS.get(key),
            runner.CUSTOM_EFFORTS.get(key),
            runner.program_of(self.assistant),
        )

    def close(self) -> None:
        """Stop the program kept running, which forgets the conversation (the
        session still has it)."""
        self._drop_live()

    def _drop_live(self) -> None:
        live, self._live, self._primed = self._live, None, False
        if live is not None:
            live.close()

    def _live_for(self, key: tuple[object, ...]) -> runner.Live:
        """The program running for this conversation, started if it is not."""
        if self._live is None or not self._live.alive or self._live_key != key:
            self._drop_live()
            live = runner.start_live(self.assistant, self.model, self.system)
            assert live is not None
            self._live, self._live_key = live, key
        return self._live

    def turn(self) -> str:
        """The newest message alone, for a program that has the rest."""
        newest = self.messages[-1]
        text = newest.text
        if block := files.text_block(newest.attachments):
            text += f"\n\n{block}"
        if newest.screen:
            text += (
                "\n\n[What the person sees in KubeScope right now]\n" + newest.screen
            )
        return text

    def _answer(self, attachments: tuple[Attachment, ...]) -> Generator[str]:
        """The pieces of the answer to the newest message."""
        if self.assistant.open_live is None:
            yield from runner.ask(
                self.assistant,
                self.prompt(),
                self.model,
                self.system,
                files.images(attachments),
                self._used,
            )
            return
        images = files.images(attachments)
        key = self._key()
        for again in (True, False):
            reused = self._live is not None and self._live.alive
            live = self._live_for(key)
            text = self.turn() if self._primed else self.prompt()
            answered = False
            try:
                for piece in live.ask(text, images, self._used):
                    answered = True
                    yield piece
            except GeneratorExit:  # stopped halfway: it is in the middle of an answer
                self._drop_live()
                raise
            except AssistantError:
                self._drop_live()
                if reused and not answered and again:
                    continue  # it had died since the last question: start again
                raise
            self._primed = True
            return

    def size(self) -> int:
        """The characters of the conversation as it is kept."""
        return sum(len(message.text) for message in self.messages)

    def needs_compact(self) -> bool:
        """Whether the conversation has grown enough to be compacted before the
        next question: when a program that keeps it holds more than
        `COMPACT_TOKENS`, or when one that is sent it all is about to leave
        the oldest messages out."""
        if len(self.messages) < 2:
            return False
        if self.assistant.open_live is not None:
            return self.last_usage.context >= COMPACT_TOKENS
        return self.size() > self.limit * 0.9

    def compact(self) -> tuple[int, int]:
        """Replace the conversation with a summary of it, made by the
        assistant; what it was and what it is now, in characters.

        The program kept running forgets the old conversation and is
        told the summary with the next question.
        """
        before = self.size()
        if len(self.messages) < 2:
            return before, before
        turns = self._turns(self.messages, SUMMARY_INPUT_LIMIT)
        summary = "".join(
            runner.ask(
                self.assistant,
                f"{turns}\n\n{SUMMARY_REQUEST}",
                self.model,
                self.system,
                (),
                self._used,
            )
        ).strip()
        if not summary:
            raise AssistantError("The assistant gave no summary")
        self.messages = [Message("user", f"{SUMMARY_LABEL}\n{summary}")]
        self._drop_live()
        self.last_usage = Usage()
        return before, self.size()

    @staticmethod
    def _turns(messages: list[Message], limit: int) -> str:
        """The newest messages that fit in `limit` characters, as text, and the
        last one is always there."""
        kept: list[Message] = []
        size = 0
        for message in reversed(messages):
            size += len(message.text)
            if kept and size > limit:
                break
            kept.append(message)
        return "\n\n".join(
            f"{_LABELS[message.role]}: {message.text}" for message in reversed(kept)
        )

    def _used(self, used: Usage) -> None:
        self.last_usage = used
        self.usage += used

    def reset(self) -> None:
        """Start over: no messages and no tokens counted."""
        self.messages.clear()
        self.usage = self.last_usage = Usage()
        self._drop_live()

    def send(
        self,
        text: str,
        screen: str = "",
        attachments: tuple[Attachment, ...] = (),
    ) -> Generator[str]:
        """Add the question and yield the answer in pieces.

        An answer that was stopped halfway is kept as it is; a failure
        takes the question back, so it can be sent again.
        """
        self.messages.append(Message("user", text, screen, attachments))
        answer: list[str] = []
        failed = False
        try:
            for piece in self._answer(attachments):
                answer.append(piece)
                yield piece
        except AssistantError:
            failed = True
            raise
        finally:
            if answer and not failed:
                self.messages.append(Message("assistant", "".join(answer)))
            else:
                self.messages.pop()
