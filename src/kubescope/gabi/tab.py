"""A conversation with the assistant of the system: what it is told, what it
answers, what it asks of the window.

The chat itself (the bubbles, the field, the attachments) is drawn by
the app (`ctx.ui.components.chat_view`); this is what the conversation
does.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kubescope.sdk import translate
from kubescope.sdk.timezone import zone_now

from kubescope.gabi import actions, attachments, executor
from kubescope.gabi.actions import Invalid, Request
from kubescope.gabi.attachments import Attachment, AttachmentError
from kubescope.gabi.history import Entry
from kubescope.gabi.runner import (
    COMPANY,
    NAME,
    Assistant,
)
from kubescope.gabi.session import ChatSession, Message
from kubescope.gabi.usage import compact

SHUTDOWN_WAIT_MS = 3000
COMPACT_COMMAND = "/compact"  # summarizes the conversation, to make it short
DEBUG_COMMAND = "/debug"  # tells what answers, from the settings
KUBE_COMMANDS = ("/kube", "/kubectl")  # tell what the computer has for kubectl
MAX_FOLLOW_UPS = 5  # reads the assistant may ask for after one question
LONG_PASTE = 2000  # a pasted text this long is attached as a file, not typed


def tab_texts() -> dict[str, str]:
    """The words of the chat in the language of the app, by their English
    text."""
    return {
        "welcome": translate(
            "AssistantTab",
            "Hi, I'm {name}, from {company}. I know Kubernetes and KubeScope "
            "well. Ask me about what you see on the screen, ask me to look into "
            "a problem, or ask me to take you somewhere in the app.",
        ).format(name=NAME, company=COMPANY),
        "placeholder": translate(
            "AssistantTab", "Ask Gabi about the cluster or ask for an action..."
        ),
        "Send": translate("AssistantTab", "Send"),
        "Stop": translate("AssistantTab", "Stop"),
        "Attach": translate("AssistantTab", "Attach"),
        "Open {name}": translate("AssistantTab", "Open {name}"),
        "{count} lines": translate("AssistantTab", "{count} lines"),
        "Images and text files ({patterns});;All files (*)": translate(
            "AssistantTab", "Images and text files ({patterns});;All files (*)"
        ),
    }


class Event:
    """What an owner of the tab listens to: `connect` a function, and `emit`
    calls it with the arguments."""

    def __init__(self) -> None:
        self._handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self._handlers.append(handler)

    def emit(self, *arguments: Any) -> None:
        for handler in list(self._handlers):
            handler(*arguments)


@dataclass
class Compacted:
    """A long conversation was compacted before the question went."""

    before: int
    after: int


SUMMARY = 140  # characters of an answer that a notice carries


def summary_of(answer: str) -> str:
    """The first line of an answer, cut to what a notice can hold."""
    lines = [line.strip() for line in actions.strip(answer).splitlines()]
    first = next((line for line in lines if line), "")
    return first if len(first) <= SUMMARY else first[: SUMMARY - 1].rstrip() + "…"


class AssistantTab:
    """A conversation with the assistant of the system, laid out as a chat:
    what the person writes on the right, what comes back on the left.

    The assistant only asks. Navigation runs at once, a read goes back
    to it as the next message, and a change waits here for the person to
    run it.
    """

    def __init__(
        self,
        session: ChatSession,
        context: str,
        write_mode: Callable[[], bool],
        components: Any,
        fetch: Callable[[Request, str], str] = executor.fetch,
        screen: Callable[[], str] = lambda: "",
        history: Sequence[Entry] = (),
        takes_images: bool = True,
    ) -> None:
        self.session = session
        self.context = context
        self.save_name = "assistant.txt"
        self.closed = False
        self.navigate = Event()  # a Request of the app, to show
        self.write = Event()  # a Request the person confirmed
        self.kube_requested = Event()  # the person typed /kube: the window reads it
        self.auto_compact_changed = Event()  # the person turned it on or off
        self.changed = Event()  # the conversation has a new entry to keep
        self.usage_changed = Event()  # an answer came: the tokens of the session grew
        # the assistant is done with what was asked (the answer, or why there is
        # none) and the success of it, for a notice when the person is not looking
        self.activity_done = Event()
        self._components = components
        self._write_mode = write_mode
        self._fetch = fetch
        self._screen = screen
        self._takes_images = takes_images
        self.debug_report: Callable[[], str] | None = None  # what /debug says
        self._pending: list[Attachment] = []  # attached, not sent yet
        self._entries: list[Entry] = []  # (role, text) of what is shown
        self._stream: Any = None  # the bubble of the answer coming in
        self._answer = ""
        self._follow_ups = 0
        self._failed = False
        self._worker: Any = None
        self._reader: Any = None
        self.auto_compact = True  # a long conversation is compacted by itself

        view = self.view = components.chat_view(tab_texts())
        self.widget = view
        view.submitted.connect(self.submit)
        view.stop_requested.connect(self.stop)
        view.attach_requested.connect(self._choose_files)
        view.image_pasted.connect(self.attach_image)
        view.files_pasted.connect(self.attach_all)
        view.text_pasted.connect(self.attach_text)
        view.ring_clicked.connect(self._show_context_menu)
        view.usage_expired.connect(lambda: self.usage_changed.emit())
        for role, text in history:
            self._entries.append((role, text))
            self._add_bubble(role, text)
            if role in ("user", "assistant"):
                self.session.messages.append(Message(role, text))  # type: ignore[arg-type]

    # the parts of the chat the owner and the tests reach
    @property
    def input(self) -> Any:
        return self.view.input

    @property
    def send_button(self) -> Any:
        return self.view.send_button

    @property
    def stop_button(self) -> Any:
        return self.view.stop_button

    @property
    def attach_button(self) -> Any:
        return self.view.attach_button

    @property
    def status(self) -> Any:
        return self.view.status

    @property
    def usage_label(self) -> Any:
        return self.view.usage_label

    @property
    def ring(self) -> Any:
        return self.view.ring

    @property
    def cards(self) -> Any:
        return self.view.cards

    @property
    def chips(self) -> Any:
        return self.view.chips

    @property
    def chip_bar(self) -> Any:
        return self.view.chip_bar

    @property
    def thread_view(self) -> Any:
        return self.view.thread_view

    @property
    def thread_scroll(self) -> Any:
        return self.view.thread_scroll

    @property
    def welcome(self) -> Any:
        return self.view.welcome

    @property
    def composer(self) -> Any:
        return self.view.composer

    @property
    def _bubbles(self) -> list[Any]:
        return self.view._bubbles

    @property
    def _labels(self) -> list[Any]:
        return self.view._labels

    def retranslate(self) -> None:
        """The language changed."""
        self.view.set_texts(tab_texts())

    def restyle(self) -> None:
        """Take the colors of the theme in use, for what is already shown."""
        self.view.restyle()

    def set_usage(self, text: str, tip: str) -> None:
        """Say what the session used in tokens, under the box of the
        question."""
        left = self.session.cache_left()
        self.view.set_usage(
            text,
            tip,
            self.session.context_fraction(),
            "\n".join(line for line in self._context_lines() if line),
            int(left * 1000) + 500 if left else 0,  # made again when it expires
        )

    def _context_lines(self) -> list[str]:
        """What the ring tells: how full the conversation is and what is left
        of the cache of the prompt."""
        percent = round(self.session.context_fraction() * 100)
        left = self.session.cache_left()
        if left is None:
            cache = ""
        elif left <= 0:
            cache = translate(
                "AssistantTab", "Cache expired: the next question writes it again"
            )
        else:
            cache = translate("AssistantTab", "Cache: it expires in {time}").format(
                time=translate("AssistantTab", "{n} min").format(
                    n=max(round(left / 60), 1)
                )
            )
        return [
            translate("AssistantTab", "Context: {percent}% full").format(
                percent=percent
            ),
            cache,
        ]

    def _show_context_menu(self) -> None:
        """The menu of the ring."""
        self._menu = self._context_menu()

    def _context_menu(self) -> Any:
        return self.view.show_ring_menu(
            self._context_lines(),
            translate("AssistantTab", "Compact now"),
            len(self.session.messages) >= 2 and not self.busy,
            self._compact,
            translate("AssistantTab", "Compact automatically"),
            self.auto_compact,
            self._set_auto_compact,
        )

    def _set_auto_compact(self, on: bool) -> None:
        self.auto_compact = on
        self.auto_compact_changed.emit(on)

    def use(self, assistant: Assistant) -> None:
        """Go on with the conversation on another assistant."""
        self.session.assistant = assistant
        self._takes_images = assistant.takes_images

    @property
    def busy(self) -> bool:
        return self._worker is not None or self._reader is not None

    def entries(self) -> list[Entry]:
        """What is shown, oldest first, for the history."""
        return list(self._entries)

    def submit(self) -> None:
        """Send what was typed."""
        text = self.input.toPlainText().strip()
        if text == DEBUG_COMMAND and self.debug_report is not None:
            self.input.clear()  # answered here, from the settings, not by the program
            self.note(self.debug_report())
            return
        if text in KUBE_COMMANDS:
            self.input.clear()
            self.kube_requested.emit()
            return
        if text == COMPACT_COMMAND and not self.busy:
            self.input.clear()
            self._compact()
            return
        if (not text and not self._pending) or self.busy:
            return
        files, self._pending = tuple(self._pending), []
        self._refresh_chips()
        self.input.clear()
        self._follow_ups = 0
        self._ask(
            text or translate("AssistantTab", "See what is attached."),
            "user",
            text,
            files,
        )

    def _compact(self) -> None:
        """Compact the conversation, which the assistant summarizes."""
        if len(self.session.messages) < 2:
            self.note(translate("AssistantTab", "There is nothing to compact yet."))
            return
        self._failed = False
        self._set_busy(True)
        self._show_status(translate("AssistantTab", "Compacting the conversation..."))
        self._worker = self._components.background(
            self.session.compact,
            on_done=lambda result: self._compacted(*result),
            on_error=self._compact_failed,
            on_finished=self._compact_finished,
        )

    def _compacted(self, before: int, after: int) -> None:
        """Tell that the conversation got shorter, in tokens, near enough."""
        self.note(
            translate(
                "AssistantTab",
                "The conversation was compacted: about {before} tokens became "
                "about {after}.",
            ).format(before=compact(before // 4), after=compact(after // 4))
        )

    def _compact_failed(self, message: str) -> None:
        self._failed = True
        self.status.setText(
            translate(
                "AssistantTab", "The conversation could not be compacted: {message}"
            ).format(message=message)
        )

    def _compact_finished(self) -> None:
        self._worker = None
        self._set_busy(False)

    def _choose_files(self) -> None:
        """Pick the files to attach."""
        patterns = " ".join(
            f"*{suffix}"
            for suffix in (*attachments.IMAGE_TYPES, *attachments.TEXT_TYPES)
        )
        for path in self.view.choose_files(
            translate("AssistantTab", "Attach"), patterns
        ):
            self.attach(path)

    def attach_all(self, paths: list[Path]) -> None:
        """Attach every file pasted, each saying why when it cannot be."""
        for path in paths:
            self.attach(path)

    def attach(self, path: Path) -> None:
        """Attach a file to the next question, saying why when it cannot be."""
        try:
            self._keep(attachments.load(path))
        except AttachmentError as error:
            self._show_status(str(error))

    def attach_image(self, png: bytes) -> None:
        """Attach a picture, such as one pasted from the clipboard, as the
        bytes of its PNG."""
        number = 1 + sum(item.name.startswith("pasted-") for item in self._pending)
        try:
            if len(png) > attachments.MAX_IMAGE_BYTES:
                raise AttachmentError(
                    translate("AssistantTab", "The picture is too large.")
                )
            self._keep(Attachment(f"pasted-{number}.png", "image", png, "image/png"))
        except AttachmentError as error:
            self._show_status(str(error))

    def attach_text(self, text: str) -> None:
        """Attach a long pasted text as a file, so it does not fill the
        field."""
        number = 1 + sum(item.name.startswith("pasted-") for item in self._pending)
        data = text.encode("utf-8")
        try:
            if len(data) > attachments.MAX_TEXT_BYTES:
                raise AttachmentError(
                    translate("AssistantTab", "The pasted text is too large.")
                )
            self._keep(Attachment(f"pasted-{number}.txt", "text", data))
        except AttachmentError as error:
            self._show_status(str(error))

    def _keep(self, item: Attachment) -> None:
        if len(self._pending) >= attachments.MAX_ATTACHMENTS:
            raise AttachmentError(
                translate(
                    "AssistantTab", "At most {count} files go with a question."
                ).format(count=attachments.MAX_ATTACHMENTS)
            )
        if item.kind == "image" and not self._takes_images:
            raise AttachmentError(
                translate(
                    "AssistantTab", "This assistant takes text files only, not {name}."
                ).format(name=item.name)
            )
        self._pending.append(item)
        self._refresh_chips()
        self._show_status("")

    def _refresh_chips(self) -> None:
        """Show what is attached, each with a × to take it off."""
        self.view.show_chips(self._pending, self._open_attachment, self._detach)

    def _open_attachment(self, item: Attachment) -> None:
        """Open an attachment with the program the system uses for its kind."""
        problem = self.view.open_attachment(item)
        if problem:
            self._show_status(problem)

    def _detach(self, item: Attachment) -> None:
        self._pending.remove(item)
        self._refresh_chips()

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.stopped = True

    def note(self, text: str) -> None:
        """Say something in the conversation that the assistant does not see,
        such as how an action ended."""
        self._add_entry("app", text)
        self.changed.emit()

    def _add_entry(self, role: str, text: str) -> None:
        self._entries.append((role, text))
        self._add_bubble(role, text)

    def _add_bubble(
        self, role: str, text: str, files: tuple[Attachment, ...] = ()
    ) -> Any:
        """Put a bubble at the end: the person's on the right, the others on
        the left."""
        return self.view.add_bubble(
            role, text, zone_now().strftime("%H:%M"), files, self._open_attachment
        )

    def _drop_last_bubble(self) -> None:
        self.view.drop_last_bubble()

    def _ask(
        self,
        text: str,
        role: str,
        shown: str,
        files: tuple[Attachment, ...] = (),
    ) -> None:
        kept = shown
        if files:
            names = ", ".join(item.name for item in files)
            kept = f"{shown}\n" if shown else ""
            kept += translate("AssistantTab", "(attached: {names})").format(names=names)
        self._entries.append((role, kept))  # the files themselves are not kept
        self._add_bubble(role, shown, files)
        self._answer = ""
        self._stream = None
        self._failed = False
        self._set_busy(True)
        screen = self._screen()
        compacting = self.auto_compact and self.session.needs_compact()

        def produce():  # type: ignore[no-untyped-def]
            """The answer as it is made, after the compaction of a long
            conversation."""
            if compacting:
                yield Compacted(*self.session.compact())
            stream = self.session.send(text, screen, files)
            try:
                yield from stream
            finally:
                stream.close()  # stops the program when the answer was cut short

        self._worker = self._components.background(
            produce,
            on_piece=self._on_piece,
            on_error=self._on_failed,
            on_finished=self._on_finished,
            stream=True,
        )

    def _on_piece(self, piece: Any) -> None:
        if isinstance(piece, Compacted):
            self._compacted(piece.before, piece.after)
            return
        self._answer += piece
        shown = actions.strip(self._answer)
        if self._stream is None:
            self._stream = self._add_bubble("assistant", shown)
        else:
            self._stream.setText(shown)

    def _on_failed(self, message: str) -> None:
        if self._stream is not None:  # the half of an answer that came
            self._drop_last_bubble()
            self._stream = None
        self._entries.pop()  # the session took the question back
        self._drop_last_bubble()
        self._answer = ""
        self._failed = True
        self.status.setText(
            translate(
                "AssistantTab", "The assistant could not answer: {message}"
            ).format(message=message)
        )

    def _on_finished(self) -> None:
        self._worker = None
        answer, self._answer = self._answer, ""
        stream, self._stream = self._stream, None
        if answer and stream is not None:
            stream.setText(actions.strip(answer))
            self._entries.append(("assistant", actions.strip(answer)))
            self._act_on(answer)
        if not self._failed:
            self.changed.emit()
            self.usage_changed.emit()
        if self._reader is None:
            self._set_busy(False)
            if answer or self._failed:  # a worker that was stopped says nothing
                self.activity_done.emit(
                    self.status.text() if self._failed else summary_of(answer),
                    not self._failed,
                )

    def _act_on(self, answer: str) -> None:
        reads: list[Request] = []
        for found in actions.parse(answer):
            if isinstance(found, Invalid):
                self._add_entry(
                    "app",
                    translate("AssistantTab", "Ignored an action: {why}").format(
                        why=found.reason
                    ),
                )
            elif found.action.kind == "navigate":
                self.navigate.emit(found)
            elif found.action.kind == "write" and not self._write_mode():
                self._add_entry(
                    "app",
                    translate(
                        "AssistantTab",
                        "Read-only mode: nothing was changed. Turn on the write mode "
                        "in Settings to allow {what}.",
                    ).format(what=actions.describe(found)),
                )
            elif found.action.kind == "write":
                self._add_card(found)
            else:
                reads.append(found)
        if reads:
            self._read(reads)

    def _read(self, requests: list[Request]) -> None:
        if self._follow_ups >= MAX_FOLLOW_UPS:
            self._add_entry(
                "app",
                translate(
                    "AssistantTab", "Stopped reading: too many reads for one question."
                ),
            )
            return
        self._follow_ups += 1
        self._reader = self._components.background(
            lambda: "\n\n".join(self._fetch(item, self.context) for item in requests),
            on_done=lambda message: self._on_read(requests, message),
            on_finished=lambda: setattr(self, "_reader", None),
        )

    def _on_read(self, requests: list[Request], message: str) -> None:
        self._reader = None
        self._ask(
            message,
            "app",
            translate("AssistantTab", "(read) {what}").format(
                what="; ".join(actions.describe(item) for item in requests)
            ),
        )

    def _add_card(self, request: Request) -> None:
        card: list[Any] = []

        def dismiss() -> None:
            self.view.remove_card(card[0])

        def confirm() -> None:
            dismiss()
            self.write.emit(request)

        card.append(
            self.view.add_action_card(
                actions.describe(request),
                translate("AssistantTab", "Run"),
                translate("AssistantTab", "Cancel"),
                confirm,
                dismiss,
            )
        )

    def _show_status(self, text: str) -> None:
        """Say what is going on, taking no room when there is nothing to
        say."""
        self.view.show_status(text)

    def _set_busy(self, busy: bool) -> None:
        self.view.set_busy(busy)
        if busy:
            self._show_status(translate("AssistantTab", "Thinking..."))
        elif not self._failed:
            self._show_status("")

    def markdown(self) -> str:
        """The conversation, to read or to save."""
        who = {
            "user": translate("AssistantTab", "You"),
            "assistant": NAME,
            "app": translate("AssistantTab", "App"),
        }
        turns = list(self._entries)
        if self._stream is not None and self._answer:
            turns.append(("assistant", actions.strip(self._answer)))
        return "\n\n".join(f"**{who[role]}**\n\n{text}" for role, text in turns)

    def shutdown(self) -> None:
        """Stop what is running, before the tab goes."""
        self.closed = True
        for worker in (self._worker, self._reader):
            if worker is not None:
                worker.stopped = True
                worker.wait(SHUTDOWN_WAIT_MS)
        self.session.close()  # the program kept running goes with the tab
