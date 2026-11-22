"""Run the coding assistant of the person's own system and stream its answer.

The app asks one question and shows the answer as it comes. It holds no
key and never sees the sign-in: the program uses the login the person
already has, and in a Flatpak the host runs it. These are coding agents,
so each one is started in its read-only mode, with no saved session and
from an empty folder, which leaves it unable to change a file or run a
command on the machine. What differs from one program to another, its
options and the shape of its output, is an `Assistant` of its own.
"""

import os
import subprocess
import sys
import tempfile
import threading
from collections import deque
from collections.abc import Callable, Generator, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from kubescope.sdk.errors import first_line
from kubescope.sdk.flatpak import host_has, in_flatpak, on_host
from kubescope.sdk.programs import find_program

from kubescope.gabi.attachments import Attachment
from kubescope.gabi.usage import Usage

# no console window flashing up from the program, on Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

NAME = "Gabi"
COMPANY = "DCO Tecnologia"
BORN = date(1992, 6, 6)
HOMETOWN = "São Paulo, Brazil"
SYSTEM_PROMPT = (
    f"You are {NAME}, an AI assistant of {COMPANY}, the makers of KubeScope, and "
    "an expert in Kubernetes and KubeScope. Say you are an AI if asked, and give "
    "your name when greeted or asked who you are. If asked what powers you, say "
    "you use the assistant program installed on the person's computer, nothing "
    "else. You help read a Kubernetes cluster: you get what they selected in the "
    "client, Secret values hidden. Explain it, find what is wrong, suggest what "
    "to check or change. You run nothing: give commands and YAML to review. Say "
    "so when unsure."
)


class AssistantError(Exception):
    """The assistant could not answer; the message says why."""


class Live(Protocol):
    """A program that stays running through a conversation, so that it keeps
    the conversation itself (in memory, never on disk) and what is already said
    is not sent again with every question."""

    @property
    def alive(self) -> bool: ...

    def ask(
        self,
        text: str,
        images: Sequence[Attachment],
        on_usage: Callable[[Usage], None],
    ) -> Generator[str]:
        """Send a message and yield the answer in pieces."""
        ...

    def close(self) -> None:
        """Stop the program."""
        ...


class Child:
    """A program started for a conversation: its standard input and output, and
    the last lines of what it said on its error output, read as they come so
    that it never blocks on a full pipe."""

    def __init__(self, arguments: list[str]) -> None:
        try:
            self.process = subprocess.Popen(
                arguments,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=tempfile.gettempdir(),  # no project files for it to read
                creationflags=_NO_WINDOW,
            )
        except OSError as error:
            raise AssistantError(str(error)) from error
        assert self.process.stdin is not None and self.process.stdout is not None
        assert self.process.stderr is not None
        self._stdin, self._stdout = self.process.stdin, self.process.stdout
        self._errors: deque[str] = deque(maxlen=20)
        threading.Thread(
            target=self._drain, args=(self.process.stderr,), daemon=True
        ).start()

    def _drain(self, stream: Iterator[str]) -> None:
        for line in stream:
            self._errors.append(line)

    @property
    def alive(self) -> bool:
        return self.process.poll() is None

    def write(self, text: str) -> None:
        try:
            self._stdin.write(text)
            self._stdin.flush()
        except OSError as error:
            raise AssistantError(str(error)) from error

    def lines(self) -> Iterator[str]:
        return iter(self._stdout)

    def reason(self) -> str:
        """Why it stopped, from the first line of its error output."""
        return first_line("".join(self._errors))

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


@dataclass(frozen=True, slots=True)
class Assistant:
    key: str  # what the settings keep
    name: str  # what the person reads
    program: str
    # the options of the program for a read-only answer, from the model and the
    # instructions it follows
    options: Callable[[str | None, str], list[str]]
    # the text a line of its output adds, and the error it reports
    parse_line: Callable[[str], tuple[str, str]]
    # for a program that takes images: its options for a question that comes
    # with them, and the message to write to it, with the images in it
    image_options: Callable[[str | None, str], list[str]] | None = None
    image_payload: Callable[[str, Sequence[Attachment]], str] | None = None
    # where its installation is explained, for a language code such as "pt"
    guide: Callable[[str], str] | None = None
    # a program with no option for its instructions gets them before the question
    compose: Callable[[str, str], str] | None = None
    # a program that reads images from files: its options for the files
    image_files: Callable[[Sequence[str]], list[str]] | None = None
    # the models it can suggest, how much it can think, and the options that set it
    models: tuple[str, ...] = ()
    efforts: tuple[str, ...] = ()
    effort_options: Callable[[str], list[str]] | None = None
    # the model and the effort the program uses when it is told none, from its own
    # configuration; empty when it does not say
    defaults: Callable[[], tuple[str, str]] | None = None
    # for a program that can keep a conversation: starts it, from the model and
    # the instructions; None sends the whole conversation with every question
    open_live: Callable[[str | None, str], Live] | None = None
    # the tokens an answer used, from a line of its output; None for any other line
    parse_usage: Callable[[str], Usage | None] | None = None

    @property
    def takes_images(self) -> bool:
        by_message = self.image_options is not None and self.image_payload is not None
        return by_message or self.image_files is not None


# where the person says a program is, by the key of its assistant, for the ones the
# system does not find on its path
CUSTOM_PROGRAMS: dict[str, str] = {}

# the model and the effort the person chose, by the key of the assistant
CUSTOM_MODELS: dict[str, str] = {}
CUSTOM_EFFORTS: dict[str, str] = {}


def program_of(assistant: Assistant) -> str:
    """The program to run: the path the person gave, or the name on the
    path."""
    custom = CUSTOM_PROGRAMS.get(assistant.key)
    return str(Path(custom).expanduser()) if custom else assistant.program


def is_runnable(path: str) -> bool:
    """Whether a path is a file that can be run, on this computer or, in a
    Flatpak, on the host."""
    if in_flatpak():
        return host_has(path)
    return os.path.isfile(path) and os.access(path, os.X_OK)


def is_available(assistant: Assistant) -> bool:
    """Whether the system has the program."""
    program = program_of(assistant)
    if assistant.key in CUSTOM_PROGRAMS:
        return is_runnable(program)
    if in_flatpak():
        return host_has(program)
    return find_program(program) is not None


def command(
    assistant: Assistant,
    model: str | None = None,
    system: str = SYSTEM_PROMPT,
    with_images: bool = False,
) -> list[str]:
    """The program and the options that keep it from acting on the machine."""
    options = assistant.image_options if with_images else assistant.options
    assert options is not None
    program = program_of(assistant)
    if sys.platform == "win32" and not in_flatpak():
        # CreateProcess adds only ".exe" to a name, so a ".cmd" must be given whole
        program = find_program(program) or program
    model = model or CUSTOM_MODELS.get(assistant.key)
    arguments = [program, *options(model, system)]
    effort = CUSTOM_EFFORTS.get(assistant.key)
    if effort and assistant.effort_options is not None:
        arguments += assistant.effort_options(effort)
    return on_host(arguments)


def start_live(
    assistant: Assistant, model: str | None = None, system: str = SYSTEM_PROMPT
) -> Live | None:
    """The program running for a conversation, or None for one that answers a
    question at a time."""
    if assistant.open_live is None:
        return None
    return assistant.open_live(model, system)


def ask(
    assistant: Assistant,
    prompt: str,
    model: str | None = None,
    system: str = SYSTEM_PROMPT,
    images: Sequence[Attachment] = (),
    on_usage: Callable[[Usage], None] | None = None,
) -> Generator[str]:
    """Send the question, with the images that came with it, and yield the
    answer in pieces; `on_usage` is told the tokens it used, when the program
    says.

    Closing the generator before the end stops the program.
    """
    if images and not assistant.takes_images:
        raise AssistantError(f"{assistant.name} does not take images")
    folder = tempfile.TemporaryDirectory() if images and assistant.image_files else None
    try:
        yield from _run(assistant, prompt, model, system, images, folder, on_usage)
    finally:
        if folder is not None:
            folder.cleanup()


def _run(
    assistant: Assistant,
    prompt: str,
    model: str | None,
    system: str,
    images: Sequence[Attachment],
    folder: tempfile.TemporaryDirectory[str] | None,
    on_usage: Callable[[Usage], None] | None = None,
) -> Generator[str]:
    """Start the program and read its answer; the images it reads from files
    are written to `folder`."""
    arguments = command(assistant, model, system, bool(images) and folder is None)
    if folder is not None and assistant.image_files is not None:
        paths = []
        for number, image in enumerate(images, start=1):
            path = Path(folder.name) / f"image-{number}{Path(image.name).suffix}"
            path.write_bytes(image.data)
            paths.append(str(path))
        arguments += assistant.image_files(paths)
    try:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=tempfile.gettempdir(),  # no project files for it to read
            creationflags=_NO_WINDOW,
        )
    except OSError as error:
        raise AssistantError(str(error)) from error
    assert process.stdin is not None and process.stdout is not None
    assert process.stderr is not None
    try:
        try:
            payload = assistant.image_payload
            if images and folder is None and payload is not None:
                text = payload(prompt, images)
            elif assistant.compose is not None:
                text = assistant.compose(system, prompt)
            else:
                text = prompt
            process.stdin.write(text)
            process.stdin.close()
        except OSError as error:
            raise AssistantError(str(error)) from error
        for line in process.stdout:
            if on_usage is not None and assistant.parse_usage is not None:
                used = assistant.parse_usage(line)
                if used is not None:
                    on_usage(used)
            text, error = assistant.parse_line(line)
            if error:
                raise AssistantError(error)
            if text:
                yield text
        if process.wait() != 0:
            reason = first_line(process.stderr.read())
            raise AssistantError(reason or "The assistant stopped without an answer")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
