import time

import pytest
from kubescope.extensions import testing
from kubescope.extensions.components import UiComponents

from kubescope.gabi import session as chat
from kubescope.gabi import tab as assistant_tab
from kubescope.gabi.runner import Assistant, AssistantError
from kubescope.gabi.session import ChatSession
from kubescope.gabi.tab import AssistantTab as _AssistantTab

application = testing.application()


def AssistantTab(*args, **kwargs):  # noqa: N802
    """A tab with the real components of the app."""
    return _AssistantTab(*args, components=UiComponents(), **kwargs)


FAKE = Assistant("fake", "Fake", "fake-ai", lambda m, s: [], lambda line: ("", ""))


def _block(document: str) -> str:
    return f"```kubescope-action\n{document}\n```\n"


def settle(tab: _AssistantTab) -> None:
    deadline = time.monotonic() + 5
    while tab.busy and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    application.processEvents()


@pytest.fixture
def replies(monkeypatch):
    """The program answers with the next of these (a list of pieces, or an
    error); the prompts it got are kept in `prompts`."""
    queue: list = []
    prompts: list[str] = []

    def ask(assistant, prompt, model, system, images=(), on_usage=None):
        prompts.append(prompt)
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        yield from reply

    monkeypatch.setattr(chat.runner, "ask", ask)
    return queue, prompts


def _tab(write_mode=True, fetch=None) -> _AssistantTab:
    kwargs = {"fetch": fetch} if fetch else {}
    return AssistantTab(ChatSession(FAKE), "ctx", lambda: write_mode, **kwargs)


def _card(tab: _AssistantTab):
    item = tab.cards.itemAt(0)
    assert item is not None
    card = item.widget()
    assert card is not None
    return card


def _say(tab: _AssistantTab, text: str) -> None:
    tab.input.setPlainText(text)
    tab.send_button.click()
    settle(tab)


def test_the_question_is_sent_and_the_answer_is_shown_as_it_comes(replies) -> None:
    queue, prompts = replies
    queue.append(["It is ", "a Pod."])
    tab = _tab()

    _say(tab, "  what is x?  ")

    assert "what is x?" in prompts[0]
    assert "**You**\n\nwhat is x?" in tab.markdown()
    assert "**Gabi**\n\nIt is a Pod." in tab.markdown()
    assert tab.input.toPlainText() == "" and tab.status.text() == ""
    assert tab.send_button.isEnabled() and not tab.stop_button.isEnabled()
    assert [label.text() for label in tab._labels] == ["what is x?", "It is a Pod."]


def test_an_empty_question_or_one_while_busy_is_ignored(replies) -> None:
    queue, prompts = replies
    queue.append(["ok"])
    tab = _tab()

    _say(tab, "   ")
    assert prompts == []

    tab.input.setPlainText("first")
    tab.submit()
    tab.input.setPlainText("second")
    tab.submit()  # still answering the first
    settle(tab)

    assert len(prompts) == 1 and tab.input.toPlainText() == "second"


def test_a_failure_is_said_and_the_question_is_taken_back(replies) -> None:
    queue, _prompts = replies
    queue.append(AssistantError("Not logged in"))
    tab = _tab()

    _say(tab, "why?")

    assert "Not logged in" in tab.status.text()
    assert "why?" not in tab.markdown() and tab.session.messages == []
    assert tab.send_button.isEnabled()


def test_navigation_runs_at_once_and_the_blocks_are_not_shown(replies) -> None:
    queue, _prompts = replies
    queue.append(["Opening.\n", _block('{"action": "open_view", "view": "pods"}')])
    tab = _tab()
    seen: list = []
    tab.navigate.connect(seen.append)

    _say(tab, "show pods")

    assert [request.action.name for request in seen] == ["open_view"]
    assert "Opening." in tab.markdown() and "kubescope-action" not in tab.markdown()


def test_a_change_waits_for_the_person_and_can_be_run_or_cancelled(replies) -> None:
    queue, _prompts = replies
    scale = '{"action": "scale", "namespace": "ns", "name": "web", "replicas": 2}'
    queue.extend([[_block(scale)], [_block(scale)]])
    tab = _tab()
    confirmed: list = []
    tab.write.connect(confirmed.append)

    _say(tab, "scale web")
    assert tab.cards.count() == 1 and confirmed == []
    card = _card(tab)
    buttons = testing.find_all(card, "button")
    buttons[0].click()  # Run
    assert [request.action.name for request in confirmed] == ["scale"]
    assert tab.cards.count() == 0

    _say(tab, "again")
    card = _card(tab)
    testing.find_all(card, "button")[1].click()  # Cancel
    assert tab.cards.count() == 0 and len(confirmed) == 1


def test_in_the_read_only_mode_a_change_is_refused_and_no_card_is_offered(
    replies,
) -> None:
    queue, _prompts = replies
    for document in (
        '{"action": "restart", "namespace": "ns", "name": "web"}',
        '{"action": "delete", "kind": "Pod", "namespace": "ns", "name": "p"}',
        '{"action": "scale", "namespace": "ns", "name": "web", "replicas": 0}',
        '{"action": "evict_pod", "namespace": "ns", "name": "p"}',
        '{"action": "replace", "kind": "Pod", "namespace": "ns", "name": "p",'
        ' "document": {"a": 1}}',
    ):
        queue.append(["Done, I changed it.\n" + _block(document)])
    tab = _tab(write_mode=False)
    wrote: list = []
    tab.write.connect(wrote.append)

    for question in ("restart", "delete", "scale", "evict", "edit"):
        _say(tab, question)

    assert tab.cards.count() == 0 and wrote == []  # nothing to run, nothing sent
    notes = [text for role, text in tab.entries() if role == "app"]
    assert len(notes) == 5
    assert all(
        note.startswith("Read-only mode: nothing was changed.") for note in notes
    )
    assert "restart(namespace=ns, name=web)" in notes[0]
    assert "Turn on the write mode in Settings" in notes[0]


def test_what_only_reads_or_moves_the_window_still_works_in_the_read_only_mode(
    replies,
) -> None:
    queue, _prompts = replies
    queue.append([_block('{"action": "open_view", "view": "pods"}')])
    tab = _tab(write_mode=False)
    seen: list = []
    tab.navigate.connect(seen.append)

    _say(tab, "show the pods")

    assert [request.action.name for request in seen] == ["open_view"]
    assert not any(role == "app" for role, _text in tab.entries())


def test_a_block_that_does_not_fit_the_catalog_is_noted(replies) -> None:
    queue, _prompts = replies
    queue.append([_block('{"action": "rm_rf"}')])
    tab = _tab()

    _say(tab, "do it")

    assert "Ignored an action: there is no action rm_rf" in tab.markdown()


def test_two_reads_asked_together_both_go_back_in_one_message(replies) -> None:
    queue, prompts = replies
    first = '{"action": "get_details", "kind": "Pod", "namespace": "ns", "name": "a"}'
    second = '{"action": "get_details", "kind": "Pod", "namespace": "ns", "name": "b"}'
    queue.extend([[_block(first), _block(second)], ["Both read."]])
    tab = _tab(fetch=lambda request, context: f"DATA {request.args['name']}")

    _say(tab, "check both")

    assert "DATA a" in prompts[1] and "DATA b" in prompts[1]
    assert "name=a" in tab.markdown() and "name=b" in tab.markdown()


def test_a_read_goes_back_to_the_assistant_as_the_next_message(replies) -> None:
    queue, prompts = replies
    details = '{"action": "get_details", "kind": "Pod", "namespace": "ns", "name": "p"}'
    queue.extend([[_block(details)], ["It is healthy."]])
    reads: list = []

    def fetch(request, context):
        reads.append((request.action.name, context))
        return "DATA OF THE POD"

    tab = _tab(fetch=fetch)

    _say(tab, "check p")

    assert reads == [("get_details", "ctx")]
    assert "DATA OF THE POD" in prompts[1]
    assert "DATA OF THE POD" not in tab.markdown()  # the person sees what was read
    assert "(read) get_details(kind=Pod, namespace=ns, name=p)" in tab.markdown()
    assert "It is healthy." in tab.markdown()
    assert tab.send_button.isEnabled()


def test_the_assistant_cannot_keep_reading_forever(replies) -> None:
    queue, prompts = replies
    again = _block(
        '{"action": "get_logs", "namespace": "ns", "pod": "p", "since_minutes": 5}'
    )
    queue.extend([[again]] * (assistant_tab.MAX_FOLLOW_UPS + 1))
    tab = _tab(fetch=lambda request, context: "log")

    _say(tab, "look")

    assert len(prompts) == assistant_tab.MAX_FOLLOW_UPS + 1
    assert "too many reads" in tab.markdown()
    assert tab.send_button.isEnabled()


def test_the_chat_goes_to_the_newest_message_and_keeps_the_sides(replies) -> None:
    tab = _tab()
    tab.widget.resize(400, 300)
    tab.widget.show()
    for number in range(40):
        tab.note(f"line {number}")
    for _ in range(10):  # the layout settles over a few turns of the loop
        application.processEvents()
        time.sleep(0.02)
    bar = tab.thread_scroll.verticalScrollBar()
    assert bar.value() == bar.maximum() > 0

    bar.setValue(0)  # the person scrolls up to read: the view stays there
    tab.note("a new one")
    for _ in range(5):
        application.processEvents()
        time.sleep(0.02)
    assert bar.value() == 0
    bar.setValue(bar.maximum())

    first = tab._bubbles[0]
    assert first.maximumWidth() <= int(tab.thread_scroll.viewport().width() * 0.82) + 1
    tab.widget.resize(700, 300)
    application.processEvents()
    assert tab._bubbles[0].maximumWidth() > first.maximumWidth() - 1
    tab.widget.close()


def test_closing_the_tab_stops_what_is_running(replies) -> None:
    queue, _prompts = replies
    queue.append(["slow"])
    tab = _tab()

    tab.input.setPlainText("go")
    tab.submit()
    tab.shutdown()
    assert tab.closed
    settle(tab)

    tab._reader = tab._components.background(lambda: time.sleep(0.05))
    tab.shutdown()
    tab._reader = None
    _tab().shutdown()  # nothing running


def test_stop_cuts_the_answer_short_and_keeps_what_came(replies) -> None:
    queue, _prompts = replies

    def slow():
        yield "first "
        time.sleep(0.3)
        yield "second"

    queue.append(slow())
    tab = _tab()

    tab.input.setPlainText("go")
    tab.submit()
    deadline = time.monotonic() + 5
    while tab._stream is None and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    assert "first" in tab.markdown()  # the answer is there as it comes
    tab.stop_button.click()
    settle(tab)

    assert "first" in tab.markdown() and "second" not in tab.markdown()
    assert tab.send_button.isEnabled()


def test_the_question_goes_with_what_the_window_shows_now(replies) -> None:
    queue, prompts = replies
    queue.append(["ok"])
    tab = AssistantTab(
        ChatSession(FAKE),
        "ctx",
        lambda: True,
        screen=lambda: "Context: prod\nPage: pods",
    )

    _say(tab, "what is wrong?")

    assert "[What the person sees in KubeScope right now]\nContext: prod" in prompts[0]
    assert "Page: pods" not in tab.markdown()  # the person is not shown it again


def test_what_the_person_writes_is_on_the_right_and_the_rest_on_the_left(
    replies,
) -> None:
    queue, _prompts = replies
    queue.append(["**bold** answer"])
    tab = _tab()
    tab.widget.resize(500, 400)
    tab.widget.show()

    _say(tab, "hello")
    tab.note("noted")
    application.processEvents()

    def side(bubble) -> str:
        row = bubble.geometry().center().x() > tab.thread_view.width() / 2
        return "right" if row else "left"

    mine, answer, noted = tab._bubbles
    assert [side(b) for b in (mine, answer, noted)] == ["right", "left", "left"]
    assert "Plain" in str(tab._labels[0].textFormat())
    assert "Markdown" in str(tab._labels[1].textFormat())
    tab.widget.close()


def test_the_conversation_comes_back_from_the_history_and_goes_to_it(replies) -> None:
    queue, prompts = replies
    queue.append(["Sure."])
    saved: list = []
    kept = [
        ("user", "earlier question"),
        ("assistant", "earlier answer"),
        ("app", "Done: scale()"),
    ]
    tab = AssistantTab(ChatSession(FAKE), "ctx", lambda: True, history=kept)
    tab.changed.connect(lambda: saved.append(tab.entries()))

    assert [label.text() for label in tab._labels] == [text for _role, text in kept]
    assert [m.role for m in tab.session.messages] == ["user", "assistant"]

    _say(tab, "and now?")

    assert "earlier question" in prompts[0] and "earlier answer" in prompts[0]
    assert "Done: scale()" not in prompts[0]  # a note of the app is not a message
    assert saved[-1][-2:] == [("user", "and now?"), ("assistant", "Sure.")]
    assert tab.entries()[:3] == kept


def test_a_failure_after_half_an_answer_takes_both_bubbles_back(replies) -> None:
    queue, _prompts = replies

    def half():
        yield "half an ans"
        raise AssistantError("cut off")

    queue.append(half())
    tab = _tab()

    _say(tab, "why?")

    assert "cut off" in tab.status.text()
    assert tab._bubbles == [] and tab._labels == [] and tab.entries() == []
    assert tab.send_button.isEnabled()


def test_the_chat_takes_its_colors_from_the_theme_and_follows_a_change(
    replies, monkeypatch
) -> None:
    from kubescope import theme

    tab = _tab()
    tab.note("noted")
    tab._add_entry("user", "hello")
    tab._add_entry("assistant", "hi")
    light = [bubble.styleSheet() for bubble in tab._bubbles]
    wall = tab.thread_view.color.name()

    monkeypatch.setattr(theme, "_active", theme.DARK_THEME)
    tab.restyle()

    dark = [bubble.styleSheet() for bubble in tab._bubbles]
    assert dark != light and tab.thread_view.color.name() != wall
    assert theme.themed("#e5f4eb") in dark[1]  # the bubble of the person
    assert theme.themed("#ffffff") in dark[2]  # the bubble of the others
    stamp = tab.view._bubble_info[1][1]
    assert stamp is not None and theme.themed("#176b58") in stamp.text()
    assert theme.themed("#3020a5") in tab.send_button.styleSheet()  # as Save changes
    monkeypatch.setattr(theme, "_active", theme.LIGHT_THEME)


def _picture(path, color="red") -> None:
    testing.write_png(path, width=30, height=20)


def test_the_plus_picks_files_that_wait_as_chips_until_the_question_goes(
    replies, monkeypatch, tmp_path
) -> None:
    queue, prompts = replies
    queue.append(["I see."])
    log = tmp_path / "app.log"
    log.write_text("boom\n", encoding="utf-8")
    shot = tmp_path / "shot.png"
    _picture(shot)
    tab = _tab()
    tab.view.choose_files = lambda title, patterns: [log, shot]
    tab.widget.show()

    tab.attach_button.click()

    assert [item.name for item in tab._pending] == ["app.log", "shot.png"]
    assert tab.chip_bar.isVisible() and tab.chips.count() == 3  # two chips, a stretch

    tab.input.setPlainText("what is this?")
    tab.send_button.click()
    settle(tab)

    assert "Attached file app.log" in prompts[0] and "boom" in prompts[0]
    assert tab._pending == [] and not tab.chip_bar.isVisible()
    # the bubble shows the picture and the question; the history holds only names
    first = tab._bubbles[0]
    assert any(
        label.pixmap() is not None and not label.pixmap().isNull()
        for label in testing.find_all(first, "label")
    )
    assert tab.entries()[0] == (
        "user",
        "what is this?\n(attached: app.log, shot.png)",
    )
    tab.widget.close()


def test_a_chip_can_be_taken_off_and_a_question_can_be_only_the_files(
    replies, tmp_path
) -> None:
    queue, prompts = replies
    queue.append(["ok"])
    a, b = tmp_path / "a.log", tmp_path / "b.log"
    a.write_text("A", encoding="utf-8")
    b.write_text("B", encoding="utf-8")
    tab = _tab()
    tab.attach(a)
    tab.attach(b)

    tab._detach(tab._pending[0])
    assert [item.name for item in tab._pending] == ["b.log"]

    tab.send_button.click()  # no text, one file
    settle(tab)

    assert "See what is attached." in prompts[0] and "B" in prompts[0]
    assert tab.entries()[0] == ("user", "(attached: b.log)")
    assert tab._labels[0].isHidden()  # no text to show, only the file


def test_a_file_that_cannot_be_attached_says_why_and_is_left_out(tmp_path) -> None:
    tab = _tab()
    (tmp_path / "tool.exe").write_bytes(b"MZ")

    tab.attach(tmp_path / "tool.exe")

    assert "not an image or a text file" in tab.status.text()
    assert tab._pending == [] and not tab.chip_bar.isVisible()


def test_no_more_than_four_files_go_with_a_question(tmp_path) -> None:
    tab = _tab()
    for number in range(5):
        path = tmp_path / f"f{number}.log"
        path.write_text("x", encoding="utf-8")
        tab.attach(path)

    assert len(tab._pending) == 4
    assert "At most 4 files" in tab.status.text()


def test_an_assistant_that_takes_text_only_refuses_images(tmp_path) -> None:
    tab = AssistantTab(ChatSession(FAKE), "ctx", lambda: True, takes_images=False)
    shot = tmp_path / "shot.png"
    _picture(shot)
    note = tmp_path / "n.txt"
    note.write_text("hello", encoding="utf-8")

    tab.attach(shot)
    assert tab._pending == [] and "takes text files only" in tab.status.text()
    tab.attach(note)
    assert [item.name for item in tab._pending] == ["n.txt"]
    assert tab.status.isHidden()  # the notice went away with a good attachment


def _chip(tab: _AssistantTab):
    item = tab.chips.itemAt(0)
    assert item is not None
    widget = item.widget()
    assert widget is not None
    return widget


def test_the_chips_take_the_colors_of_the_theme(monkeypatch, tmp_path) -> None:
    from kubescope import theme

    tab = _tab()
    path = tmp_path / "a.log"
    path.write_text("x", encoding="utf-8")
    tab.attach(path)
    light = _chip(tab).styleSheet()

    monkeypatch.setattr(theme, "_active", theme.DARK_THEME)
    tab.restyle()

    assert _chip(tab).styleSheet() != light
    monkeypatch.setattr(theme, "_active", theme.LIGHT_THEME)


def test_the_empty_chat_greets_with_the_name_and_the_company_and_gives_way(
    replies,
) -> None:
    queue, _prompts = replies
    queue.append(["Hello"])
    tab = _tab()
    tab.widget.show()

    assert tab.welcome.isVisible()
    assert "Hi, I'm Gabi, from DCO." in tab.welcome.text()
    assert tab.entries() == []  # the greeting is not a message: not kept, not sent

    _say(tab, "hi")
    assert not tab.welcome.isVisible()
    assert all("Hi, I'm Gabi" not in text for _role, text in tab.entries())
    tab.widget.close()


def test_the_greeting_is_back_when_a_question_is_taken_back(replies) -> None:
    queue, _prompts = replies
    queue.append(AssistantError("Not logged in"))
    tab = _tab()
    tab.widget.show()

    _say(tab, "why?")

    assert tab.welcome.isVisible() and tab._bubbles == []
    tab.widget.close()


def test_a_conversation_that_comes_from_the_history_has_no_greeting() -> None:
    tab = AssistantTab(
        ChatSession(FAKE), "ctx", lambda: True, history=[("user", "before")]
    )
    tab.widget.show()

    assert not tab.welcome.isVisible()
    tab.widget.close()


_LONG = (
    "Eu não consigo ler o consumo ao vivo. As ações que tenho devolvem só os "
    "documentos do cluster, e o uso atual não vem neles.\n\n"
    "Se preferir o terminal, este comando mostra o uso por container:\n\n"
    "`kubectl top pod arquitt-back-ocr-api-89777fb74-5bqjt --containers`\n\n"
    "- **CPU:** request de `25m` e nenhum limit.\n"
    "- **Memória:** request de `512Mi` e nenhum limit.\n\n"
    "Sem limits, o container pode usar mais que o request, até o que sobrar no "
    "node. O request só reserva a capacidade no scheduler. Se o uso real ficar "
    "bem acima de 25m de CPU ou de 512Mi de memória, vale aumentar o request."
)


def _settle(tab: _AssistantTab) -> None:
    for _ in range(12):
        application.processEvents()
        time.sleep(0.01)


def test_a_message_is_as_high_as_its_text_at_any_width_of_the_panel() -> None:
    tab = _tab()
    tab.widget.resize(430, 560)
    tab.widget.show()
    tab._add_entry("assistant", _LONG)
    tab._add_entry("user", "Quanto está consumindo de cpu e memória, atualmente?")

    for width in (430, 330, 700, 360, 520):
        tab.widget.resize(width, 560)
        _settle(tab)
        for label in tab._labels:
            needed = label.document().size().height()
            assert label.height() >= needed - 1, (width, label.text()[:20])
            assert label.height() <= needed + 2  # and no blank room under it
    tab.widget.close()


def test_a_short_message_is_as_wide_as_its_text_and_not_squeezed(replies) -> None:
    tab = _tab()
    tab.widget.resize(430, 560)
    tab.widget.show()
    question = "Quanto está consumindo de cpu e memória, atualmente?"
    tab._add_entry("user", question)
    tab._add_entry("user", "ok")
    _settle(tab)

    question_label, short = tab._labels
    room = tab._bubbles[0].maximumWidth() - 20  # what its bubble leaves for the text
    wanted = question_label.sizeHint().width()  # as wide as the text, not wrapped
    # as wide as the text needs, or as the room it has: whatever the font is
    assert question_label.width() >= min(wanted, room) - 2
    assert question_label.width() > 130  # not squeezed into a narrow column
    assert question_label.height() < short.height() * 4  # nor a tall thin bubble
    assert 0 < short.width() < 100  # a short answer has a small bubble
    tab.widget.close()


def test_debug_is_answered_by_the_app_and_only_when_it_has_a_report(replies) -> None:
    queue, prompts = replies
    queue.append(["ok"])
    tab = _tab()
    tab.debug_report = lambda: "the report"

    _say(tab, "/debug")

    assert prompts == [] and tab.entries()[-1] == ("app", "the report")
    assert tab.input.toPlainText() == ""

    plain = _tab()  # nothing to report: it is a question like any other
    _say(plain, "/debug")
    settle(plain)
    assert len(prompts) == 1


def test_compact_summarizes_the_conversation_and_says_how_much_shorter(
    replies,
) -> None:
    queue, prompts = replies
    queue.extend([["a " * 200], ["b " * 200], ["A short summary."]])
    tab = _tab()
    _say(tab, "one " * 200)
    _say(tab, "two " * 200)

    _say(tab, "/compact")

    assert "Summarize" not in prompts[-1] and "summary" in prompts[-1]
    assert tab.session.messages[0].text.endswith("A short summary.")
    assert len(tab.session.messages) == 1
    role, text = tab.entries()[-1]
    assert role == "app" and "was compacted: about" in text and "tokens became" in text
    assert tab.input.toPlainText() == "" and not tab.busy


def test_compact_with_nothing_said_says_so_and_a_failure_says_why(replies) -> None:
    queue, prompts = replies
    tab = _tab()

    _say(tab, "/compact")
    assert tab.entries()[-1] == ("app", "There is nothing to compact yet.")
    assert prompts == []

    queue.extend([["a"], ["b"], AssistantError("no quota")])
    _say(tab, "one")
    _say(tab, "two")
    _say(tab, "/compact")
    assert "could not be compacted: no quota" in tab.status.text()
    assert len(tab.session.messages) == 4  # it was left as it was


def test_the_context_menu_compacts_now_or_turns_auto_compacting_off(
    replies,
) -> None:
    queue, _prompts = replies
    tab = _tab()
    tab.session.messages = [
        chat.Message("user", "one"),
        chat.Message("assistant", "two"),
    ]

    menu = tab._context_menu()
    now = next(action for action in menu.actions() if action.text() == "Compact now")
    auto = next(
        action for action in menu.actions() if action.text() == "Compact automatically"
    )

    assert now.isEnabled() and auto.isChecked()
    auto.setChecked(False)
    assert tab.auto_compact is False


def test_the_context_ring_and_cache_indicator(replies, monkeypatch) -> None:
    tab = _tab()
    ring = tab.ring
    ring.show()

    monkeypatch.setattr(chat, "clock", lambda: 20)
    tab.session.cache_ttl = 90
    tab.session.answered_at = 0
    tab.set_usage("", "tip")
    assert tab.usage_label.isHidden() and ring.isHidden()
    assert tab.view._cache_timer.isActive()
    assert "Cache: it expires in 1 min" in ring.toolTip()

    monkeypatch.setattr(chat, "clock", lambda: 110)
    tab.set_usage("tokens", "tip")
    assert not tab.usage_label.isHidden() and not ring.isHidden()
    assert not tab.view._cache_timer.isActive()
    assert "Cache expired: the next question writes it again" in ring.toolTip()


def test_a_conversation_that_grew_is_compacted_before_the_next_question(
    replies, monkeypatch
) -> None:
    queue, prompts = replies
    queue.extend([["a"], ["b"], ["The summary."], ["answer"]])
    tab = _tab()
    _say(tab, "one")
    _say(tab, "two")
    monkeypatch.setattr(tab.session, "needs_compact", lambda: True)

    _say(tab, "three")

    assert "summary" in prompts[-2]  # first the summary, then the question
    assert prompts[-1].startswith(f"User: {chat.SUMMARY_LABEL}")
    assert prompts[-1].endswith("Answer the last message of the User as the Assistant.")
    roles = [role for role, _text in tab.entries()]
    assert roles.count("app") == 1 and tab.entries()[-1][0] == "assistant"


def test_a_compaction_that_fails_before_a_question_stops_it(
    replies, monkeypatch
) -> None:
    queue, prompts = replies
    queue.extend([["a"], ["b"], AssistantError("down")])
    tab = _tab()
    _say(tab, "one")
    _say(tab, "two")
    monkeypatch.setattr(tab.session, "needs_compact", lambda: True)

    _say(tab, "three")

    assert "down" in tab.status.text()
    assert len(prompts) == 3  # the question itself was not sent


def test_the_end_of_an_activity_is_told_with_the_start_of_the_answer(replies) -> None:
    queue, _prompts = replies
    queue.append(["\n  It is ", "a Pod.\nThen more."])
    tab = _tab()
    told: list[tuple[str, bool]] = []
    tab.activity_done.connect(lambda text, ok: told.append((text, ok)))

    _say(tab, "what is x?")

    assert told == [("It is a Pod.", True)]


def test_a_failure_is_told_too_and_a_long_answer_is_cut(replies) -> None:
    queue, _prompts = replies
    queue.append(AssistantError("Not logged in"))
    queue.append(["word " * 80])
    tab = _tab()
    told: list[tuple[str, bool]] = []
    tab.activity_done.connect(lambda text, ok: told.append((text, ok)))

    _say(tab, "why?")
    _say(tab, "again")

    assert told[0][1] is False and "Not logged in" in told[0][0]
    assert told[1][1] is True and told[1][0].endswith("…")
    assert len(told[1][0]) <= assistant_tab.SUMMARY


def test_a_stopped_activity_and_an_empty_answer_tell_nothing(replies) -> None:
    queue, _prompts = replies
    queue.append([])
    tab = _tab()
    told: list[object] = []
    tab.activity_done.connect(lambda *args: told.append(args))

    _say(tab, "hello?")

    assert told == []
    assert assistant_tab.summary_of("") == ""


def test_a_picture_pasted_is_attached_by_its_bytes_and_a_big_one_is_refused(
    monkeypatch,
) -> None:
    tab = _tab()
    png = testing.png_bytes(10, 10)

    tab.attach_image(png)
    tab.attach_image(png)
    tab.attach_text("pasted words")

    assert [item.name for item in tab._pending] == [
        "pasted-1.png",
        "pasted-2.png",
        "pasted-3.txt",
    ]
    assert tab._pending[0].data.startswith(b"\x89PNG")

    monkeypatch.setattr(assistant_tab.attachments, "MAX_IMAGE_BYTES", 10)
    tab.attach_image(png)
    assert "The picture is too large." in tab.status.text()
    assert len(tab._pending) == 3
    tab._pending.clear()
    huge = "x" * (assistant_tab.attachments.MAX_TEXT_BYTES + 1)
    tab.attach_text(huge)
    assert "too large" in tab.status.text()


def test_files_pasted_are_attached_and_an_attachment_that_cannot_open_says_why(
    tmp_path, monkeypatch
) -> None:
    tab = _tab()
    log = tmp_path / "app.log"
    log.write_text("one\ntwo\n")

    tab.attach_all([log])

    assert [item.name for item in tab._pending] == ["app.log"]
    assert tab.chips.count() >= 2  # a card for each, then the stretch
    monkeypatch.setattr(tab.view, "open_attachment", lambda item: "Permission denied")
    tab._open_attachment(tab._pending[0])
    assert "Permission denied" in tab.status.text()
    monkeypatch.setattr(tab.view, "open_attachment", lambda item: "")
    tab._show_status("")
    tab._open_attachment(tab._pending[0])
    assert tab.status.isHidden()


def test_the_enter_of_the_field_sends_the_question(replies) -> None:
    queue, prompts = replies
    queue.append(["ok"])
    tab = _tab()
    tab.input.setPlainText("first line\nsecond")

    tab.view.submitted.emit()  # what Enter says
    settle(tab)

    assert len(prompts) == 1 and "first line\nsecond" in prompts[0]
    assert tab.input.toPlainText() == ""
