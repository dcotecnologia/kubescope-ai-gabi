import pytest

from kubescope.gabi import session as chat
from kubescope.gabi.runner import Assistant, AssistantError
from kubescope.gabi.session import ChatSession, Message
from kubescope.gabi.usage import Usage

FAKE = Assistant(
    "fake", "Fake", "fake-ai", lambda model, system: [], lambda line: ("", "")
)


@pytest.fixture
def answers(monkeypatch):
    """Make the program answer with the given pieces, or fail; the arguments of
    each call are kept in `calls`."""
    calls: list[tuple] = []
    plan: dict = {"pieces": [], "error": None}

    def ask(assistant, prompt, model, system, images=(), on_usage=None):
        calls.append((assistant, prompt, model, system))
        if on_usage is not None and plan.get("usage") is not None:
            on_usage(plan["usage"])
        yield from plan["pieces"]
        if plan["error"]:
            raise plan["error"]

    monkeypatch.setattr(chat.runner, "ask", ask)
    return calls, plan


def test_the_session_sends_the_whole_conversation_each_time(answers) -> None:
    calls, plan = answers
    session = ChatSession(FAKE, model="big", system="rules")
    plan["pieces"] = ["It is ", "a Pod."]

    assert list(session.send("what is x?")) == ["It is ", "a Pod."]
    plan["pieces"] = ["Yes."]
    assert list(session.send("really?")) == ["Yes."]

    assert calls[0] == (
        FAKE,
        "User: what is x?\n\nAnswer the last message of the User as the Assistant.",
        "big",
        "rules",
    )
    assert calls[1][1] == (
        "User: what is x?\n\nAssistant: It is a Pod.\n\nUser: really?\n\n"
        "Answer the last message of the User as the Assistant."
    )
    assert session.messages[-2:] == [
        Message("user", "really?"),
        Message("assistant", "Yes."),
    ]


def test_the_oldest_messages_are_left_out_but_the_last_one_never(answers) -> None:
    session = ChatSession(FAKE, limit=10)
    session.messages = [
        Message("user", "a" * 8),
        Message("assistant", "b" * 8),
        Message("user", "c" * 30),
    ]

    prompt = session.prompt()

    assert "a" * 8 not in prompt and "b" * 8 not in prompt
    assert "User: " + "c" * 30 in prompt

    session.messages = [Message("user", "a" * 4), Message("assistant", "b" * 4)]
    assert "User: aaaa" in session.prompt()


def test_a_failure_takes_the_question_back_so_it_can_be_sent_again(answers) -> None:
    _calls, plan = answers
    session = ChatSession(FAKE)
    plan["pieces"] = ["half"]
    plan["error"] = AssistantError("Not logged in")

    with pytest.raises(AssistantError):
        list(session.send("why?"))

    assert session.messages == []


def test_stopping_keeps_what_was_answered_and_nothing_when_nothing_was(
    answers,
) -> None:
    _calls, plan = answers
    session = ChatSession(FAKE)
    plan["pieces"] = ["one", "two"]

    pieces = session.send("why?")
    assert next(pieces) == "one"
    pieces.close()
    assert session.messages[-1] == Message("assistant", "one")

    plan["pieces"] = []
    silent = session.send("and?")
    with pytest.raises(StopIteration):
        next(silent)
    assert session.messages[-1] == Message("assistant", "one")
    assert len(session.messages) == 2


def test_what_the_person_sees_goes_with_the_newest_question_only(answers) -> None:
    calls, plan = answers
    session = ChatSession(FAKE)
    plan["pieces"] = ["ok"]

    list(session.send("what is wrong?", "Context: prod"))
    list(session.send("and now?", "Context: dev"))

    assert "[What the person sees in KubeScope right now]\nContext: prod" in calls[0][1]
    second = calls[1][1]
    assert "Context: dev" in second and "Context: prod" not in second
    assert session.messages[0].screen == "Context: prod"
    list(session.send("again"))
    assert "[What the person sees" not in calls[2][1]


def test_text_files_go_after_the_newest_question_and_images_to_the_program(
    monkeypatch,
) -> None:
    from kubescope.gabi.attachments import Attachment

    seen: list = []

    def ask(assistant, prompt, model, system, images, on_usage=None):
        seen.append((prompt, [image.name for image in images]))
        yield "ok"

    monkeypatch.setattr(chat.runner, "ask", ask)
    session = ChatSession(FAKE)
    log = Attachment("app.log", "text", b"boom\n")
    shot = Attachment("shot.png", "image", b"x", "image/png")

    list(session.send("why?", "", (log, shot)))
    list(session.send("and now?"))

    first, second = seen
    assert "Attached file app.log:\n```\nboom\n\n```" in first[0]
    assert first[1] == ["shot.png"]
    assert "boom" not in second[0] and second[1] == []  # sent once, not kept
    assert session.messages[0].attachments == (log, shot)


def test_the_session_adds_up_the_tokens_of_its_answers_and_starts_over(answers) -> None:
    _calls, plan = answers
    session = ChatSession(FAKE)
    plan["pieces"] = ["Yes."]
    plan["usage"] = Usage(10, 5, 100, 20, 0.5)
    list(session.send("one"))
    plan["usage"] = Usage(3, 2, 130, 0, None)
    list(session.send("two"))

    assert session.last_usage == Usage(3, 2, 130, 0, None)
    assert session.usage == Usage(13, 7, 230, 20, 0.5)

    session.reset()
    assert session.messages == [] and not session.usage and not session.last_usage


class FakeLive:
    """A program kept running: what it was asked, and how it answers."""

    def __init__(self, plan: dict) -> None:
        self.plan = plan
        self.asked: list[tuple[str, int]] = []
        self.up = True
        self.closed = False

    @property
    def alive(self) -> bool:
        return self.up

    def ask(self, text, images, on_usage):
        self.asked.append((text, len(images)))
        if self.plan.get("usage") is not None:
            on_usage(self.plan["usage"])
        outcome = self.plan["outcomes"].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield from outcome

    def close(self) -> None:
        self.up = False
        self.closed = True


LIVE = Assistant(
    "live",
    "Live",
    "live-ai",
    lambda model, system: [],
    lambda line: ("", ""),
    open_live=lambda model, system: FakeLive({}),  # the fixture starts its own
)


@pytest.fixture
def lives(monkeypatch):
    """Make the program kept running a fake one; every one started is kept."""
    started: list[FakeLive] = []
    plan: dict = {"outcomes": [], "usage": None}

    def start(assistant, model=None, system=""):
        live = FakeLive(plan)
        started.append(live)
        return live

    monkeypatch.setattr(chat.runner, "start_live", start)
    return started, plan


def test_a_program_that_keeps_the_conversation_is_sent_only_what_is_new(lives) -> None:
    started, plan = lives
    session = ChatSession(LIVE, system="rules")
    plan["outcomes"] = [["It is ", "a Pod."], ["Yes."]]

    assert list(session.send("what is x?")) == ["It is ", "a Pod."]
    assert list(session.send("really?", "the screen")) == ["Yes."]

    assert len(started) == 1  # the same program answered both
    first, second = started[0].asked
    assert first[0].startswith("User: what is x?")  # a first time, the conversation
    assert second[0] == (
        "really?\n\n[What the person sees in KubeScope right now]\nthe screen"
    )
    assert session.messages[-2:] == [
        Message("user", "really?", "the screen"),
        Message("assistant", "Yes."),
    ]


def test_the_files_of_the_newest_message_go_with_it_and_its_images_beside(
    lives,
) -> None:
    from kubescope.gabi.attachments import Attachment

    started, plan = lives
    session = ChatSession(LIVE)
    plan["outcomes"] = [["a"], ["b"]]
    log = Attachment("app.log", "text", b"boom\n")
    shot = Attachment("shot.png", "image", b"x", "image/png")

    list(session.send("one"))
    list(session.send("why?", "", (log, shot)))

    text, images = started[0].asked[1]
    assert "why?" in text and "boom" in text and images == 1


def test_the_program_is_started_again_when_what_it_depends_on_changes(lives) -> None:
    started, plan = lives
    session = ChatSession(LIVE, system="rules")
    plan["outcomes"] = [["a"], ["b"]]
    list(session.send("one"))

    session.system = "other rules"  # the language or the mode changed
    list(session.send("two"))

    assert len(started) == 2 and started[0].closed
    assert started[1].asked[0][0].startswith("User: one")  # it is told what was said
    assert "Assistant: a" in started[1].asked[0][0]


def test_a_stopped_answer_leaves_a_program_that_is_started_again(lives) -> None:
    started, plan = lives
    session = ChatSession(LIVE)
    plan["outcomes"] = [["It is ", "a Pod."], ["ok"]]
    stream = session.send("what is x?")
    assert next(stream) == "It is "

    stream.close()  # stopped halfway: the program is in the middle of an answer

    assert started[0].closed
    list(session.send("and?"))
    assert len(started) == 2
    assert "Assistant: It is " in started[1].asked[0][0]  # what came is kept


def test_a_failure_stops_the_program_and_takes_the_question_back(lives) -> None:
    started, plan = lives
    session = ChatSession(LIVE)
    plan["outcomes"] = [AssistantError("no")]

    with pytest.raises(AssistantError):
        list(session.send("one"))

    assert started[0].closed and session.messages == []


def test_a_program_that_died_since_the_last_question_is_replaced(lives) -> None:
    started, plan = lives
    session = ChatSession(LIVE)
    plan["outcomes"] = [["a"], ["b"]]
    list(session.send("one"))
    started[0].up = False  # it died between the questions

    assert list(session.send("two")) == ["b"]

    assert len(started) == 2 and "User: one" in started[1].asked[0][0]


def test_a_program_that_dies_on_the_question_is_replaced_once(lives) -> None:
    started, plan = lives
    session = ChatSession(LIVE)
    plan["outcomes"] = [["a"], AssistantError("gone"), ["b"]]
    list(session.send("one"))

    assert list(session.send("two")) == ["b"]  # it came back, told the whole of it
    assert len(started) == 2 and "User: one" in started[1].asked[0][0]

    plan["outcomes"] = [AssistantError("gone"), AssistantError("again")]
    started[1].up = True
    with pytest.raises(AssistantError, match="again"):
        list(session.send("three"))  # a fresh one failing is an error


def test_closing_or_starting_over_stops_the_program(lives) -> None:
    started, plan = lives
    session = ChatSession(LIVE)
    plan["outcomes"] = [["a"]]
    list(session.send("one"))

    session.close()
    assert started[0].closed
    session.close()  # nothing left to stop

    plan["outcomes"] = [["a"]]
    list(session.send("two"))
    session.reset()
    assert started[1].closed


def test_compacting_replaces_the_conversation_with_a_summary_of_it(answers) -> None:
    calls, plan = answers
    session = ChatSession(FAKE, system="rules")
    plan["pieces"] = ["a"]
    list(session.send("one " * 40))
    list(session.send("two " * 40))
    session.last_usage = Usage(1, 1, 1, 1)

    plan["pieces"] = ["  The summary.  "]
    before, after = session.compact()

    assert calls[-1][1].startswith("User: one one")
    assert "Assistant: a\n\nUser: two two" in calls[-1][1]
    assert calls[-1][1].endswith(chat.SUMMARY_REQUEST)
    assert session.messages == [Message("user", f"{chat.SUMMARY_LABEL}\nThe summary.")]
    assert before > after and after == session.size()
    assert not session.last_usage  # nothing is known of the new conversation yet


def test_compacting_needs_something_to_compact_and_a_summary(answers) -> None:
    _calls, plan = answers
    session = ChatSession(FAKE)
    assert session.compact() == (0, 0)  # nothing said yet
    plan["pieces"] = ["a"]
    list(session.send("one"))
    list(session.send("two"))

    plan["pieces"] = ["  "]
    with pytest.raises(AssistantError, match="no summary"):
        session.compact()
    assert len(session.messages) == 4  # as it was


def test_a_long_conversation_is_summarized_from_its_newest_part(answers) -> None:
    calls, plan = answers
    session = ChatSession(FAKE)
    session.messages = [
        Message("user", "x" * 100_000),
        Message("assistant", "y" * 100_000),
        Message("user", "last"),
    ]
    plan["pieces"] = ["s"]

    session.compact()

    asked = calls[-1][1]
    assert "last" in asked and "x" * 100 not in asked  # the oldest is left out


def test_the_conversation_is_compacted_when_it_is_long(lives) -> None:
    started, plan = lives
    session = ChatSession(LIVE, limit=1000)
    assert not session.needs_compact()  # nothing said

    session.messages = [Message("user", "a"), Message("assistant", "b")]
    session.last_usage = Usage(10, 1, 1000, 0)
    assert not session.needs_compact()  # a program that keeps it: by its tokens
    session.last_usage = Usage(10, 1, chat.COMPACT_TOKENS, 0)
    assert session.needs_compact()

    plain = ChatSession(FAKE, limit=100)  # one that is sent it all: by its size
    plain.messages = [Message("user", "a" * 40), Message("assistant", "b" * 40)]
    assert not plain.needs_compact()
    plain.messages.append(Message("user", "c" * 20))
    assert plain.needs_compact()


def test_the_prompt_cache_counts_down_and_stops_at_zero(monkeypatch) -> None:
    session = ChatSession(FAKE)
    session.cache_ttl = 10
    session.answered_at = 20
    monkeypatch.setattr(chat, "clock", lambda: 25)

    assert session.cache_left() == 5

    monkeypatch.setattr(chat, "clock", lambda: 35)
    assert session.cache_left() == 0


def test_compacting_stops_the_program_kept_running(lives, monkeypatch) -> None:
    started, plan = lives
    session = ChatSession(LIVE)
    plan["outcomes"] = [["a"], ["b"]]
    list(session.send("one"))
    list(session.send("two"))
    monkeypatch.setattr(chat.runner, "ask", lambda *args, **kwargs: iter(["sum"]))

    session.compact()

    assert started[0].closed
    plan["outcomes"] = [["c"]]
    list(session.send("three"))
    assert "Summary of the conversation" in started[1].asked[0][0]  # it is told
