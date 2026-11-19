from pathlib import Path

import pytest
import shiboken6
from kubescope.extensions.context import ExtensionContext
from kubescope.extensions.manifest import read_manifest
from kubescope.sdk import (
    CONTEXT_CHANGED,
    LANGUAGE_CHANGED,
    SHUTDOWN,
    THEME_CHANGED,
    WRITE_MODE_CHANGED,
)
from PySide6.QtWidgets import QApplication, QMessageBox

from kubescope.gabi import extension, services
from kubescope.gabi.controller import GabiController

ROOT = Path(__file__).resolve().parents[1]


def run(window) -> ExtensionContext:
    """Gabi, activated the way the app does it: with what her manifest asks for."""
    manifest = read_manifest(ROOT)
    ctx = ExtensionContext(manifest.id, manifest.permissions, window.extension_host)
    extension.activate(ctx)
    return ctx


@pytest.fixture
def ctx(window):
    context = run(window)
    yield context
    context.close()


def test_she_is_activated_with_the_chat_in_the_corner_and_her_shortcut(
    window, ctx
) -> None:
    controller = services.controller

    assert isinstance(controller, GabiController)
    assert controller.dock.bubble.parent() is window.centralWidget()
    [shortcut] = [
        one
        for one in window.extension_host.contributions.shortcuts
        if one.extension == ctx.id
    ]
    assert shortcut.action == "kubescope.gabi.ask" and shortcut.default == "Ctrl+G"
    assert shortcut.application is True and callable(shortcut.handler)


def test_she_adds_the_command_chat_and_its_alias_to_the_terminal(window, ctx) -> None:
    names = {
        one.name
        for one in window.extension_host.contributions.cli_commands
        if one.extension == ctx.id
    }

    assert names == {"chat", "assistant"}


def test_the_manifest_asks_for_what_she_uses() -> None:
    manifest = read_manifest(ROOT)

    assert manifest.entry == "kubescope.gabi:activate"
    assert manifest.permissions >= {
        "cluster.read",
        "cluster.write",
        "subprocess",
        "ui.window",
        "ui.settings",
        "cli",
    }
    assert "ui.dock" not in manifest.permissions  # she adds no panel of the SDK's


def test_unloading_her_takes_everything_out_of_the_window(window) -> None:
    base = window.ui.footerRow.contentsMargins().right()
    ctx = run(window)
    controller = services.controller
    bubble, panel = controller.dock.bubble, controller.dock.panel
    assert window.ui.footerRow.contentsMargins().right() > base  # her button's room

    ctx.close()
    QApplication.sendPostedEvents(None, 52)  # QEvent.DeferredDelete

    assert not shiboken6.isValid(bubble) and not shiboken6.isValid(panel)
    assert services.controller is None
    with pytest.raises(RuntimeError, match="not activated"):
        services.context()
    assert [
        one
        for one in window.extension_host.contributions.shortcuts
        if one.extension == ctx.id
    ] == []
    assert window.ui.footerRow.contentsMargins().right() == base


@pytest.mark.parametrize(
    ("event", "payload", "calls"),
    [
        (CONTEXT_CHANGED, {"context": "prod"}, ["context_changed"]),
        (THEME_CHANGED, {}, ["restyle"]),
        (LANGUAGE_CHANGED, {"language": "pt_BR"}, ["retranslate", "refresh_system"]),
        (WRITE_MODE_CHANGED, {"write_mode": True}, ["refresh_system"]),
        (SHUTDOWN, {}, ["shutdown"]),
    ],
)
def test_the_chat_hears_what_the_app_tells_it(
    window, ctx, monkeypatch, event, payload, calls
) -> None:
    heard: list[str] = []
    controller = services.controller
    for name in (
        "context_changed",
        "restyle",
        "retranslate",
        "refresh_system",
        "shutdown",
    ):
        monkeypatch.setattr(controller, name, lambda name=name: heard.append(name))

    window.extension_host.events.emit(event, **payload)

    assert heard == calls


def test_the_shortcut_opens_the_chat_through_the_controller(
    window, ctx, monkeypatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(services.controller, "shortcut", lambda: opened.append("key"))
    [shortcut] = [
        one
        for one in window.extension_host.contributions.shortcuts
        if one.extension == ctx.id
    ]

    shortcut.handler()

    assert opened == ["key"]


def test_the_conversations_the_app_kept_move_to_her_own_folder_once(
    window, tmp_path
) -> None:
    from kubescope.sdk.paths import config_directory

    old = config_directory() / "assistant_history.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text('{"prod": []}')

    ctx = run(window)
    new = ctx.data_directory / "history.json"

    assert new.read_text() == '{"prod": []}' and not old.exists()
    ctx.close()
    old.write_text("another")  # an old file does not replace the one she has
    ctx = run(window)
    assert new.read_text() == '{"prod": []}' and old.read_text() == "another"
    ctx.close()


def test_without_an_old_history_nothing_is_created(window, ctx) -> None:
    assert not (ctx.data_directory / "history.json").exists()


def test_what_she_shows_goes_through_the_window_with_the_right_icon(
    window, ctx, monkeypatch
) -> None:
    shown: list = []
    monkeypatch.setattr(
        window, "_show_message", lambda icon, title, text: shown.append(icon)
    )
    port = services.controller.port

    port.show_message(QMessageBox.Icon.Warning, "T", "x")
    port.show_message(QMessageBox.Icon.Critical, "T", "x")
    port.show_message(QMessageBox.Icon.Information, "T", "x")
    port.show_message(QMessageBox.Icon.Question, "T", "x")

    assert shown == [
        QMessageBox.Icon.Warning,
        QMessageBox.Icon.Critical,
        QMessageBox.Icon.Information,
        QMessageBox.Icon.Information,
    ]


def test_her_button_in_the_chat_takes_the_person_to_the_settings(window, ctx) -> None:
    services.controller.port.show_settings()

    assert window.pages.currentIndex() == 2


def test_the_context_is_empty_when_the_window_has_none(window, ctx) -> None:
    port = services.controller.port
    assert port.context() == "prod"

    window.context_combo.clear()

    assert port.context() == ""


def test_her_preferences_are_kept_with_the_settings_of_the_app_under_her_id(
    window, ctx
) -> None:
    port = services.controller.port

    port.settings.assistant_consent = True
    port.settings.assistant = "claude"

    assert window.settings.extension_data("kubescope.gabi") == {
        "consent": True,
        "assistant": "claude",
    }


def test_the_write_mode_and_the_language_are_the_ones_of_the_app(window, ctx) -> None:
    port = services.controller.port

    window.settings.write_mode = True

    assert port.app.write_mode is True
    assert port.app.language_name and port.app.resolved_language


def test_what_she_asks_of_the_window_goes_by_the_commands_of_the_window(
    window, ctx, monkeypatch
) -> None:
    called: list = []
    monkeypatch.setattr(window, "_press_refresh", lambda: called.append("refresh"))

    services.controller.port.invoke("refresh", report=lambda message: None)

    assert called == ["refresh"]


def sections(window) -> list:
    return [
        one for one in window._extension_sections if one.extension == "kubescope.gabi"
    ]


def test_her_section_is_in_the_settings_of_the_window(window, ctx) -> None:
    window._apply_extension_contributions()
    [entry] = sections(window)
    form = window.settings_ui

    assert entry.title == "Gabi" and entry.button.text() == "Gabi"
    assert not entry.card.isVisibleTo(form.settingsContent)
    entry.button.click()
    assert entry.card.isVisibleTo(form.settingsContent)
    assert entry.panel.enabled.isChecked()


def test_her_shortcut_is_in_the_shortcuts_of_the_settings(window, ctx) -> None:
    window._apply_extension_contributions()
    table = window.settings_ui.shortcutsTable
    rows = {
        table.item(row, 0).text(): row
        for row in range(table.rowCount())
        if table.item(row, 0) is not None
    }

    assert "Ask the assistant" in rows
    shortcut = window._shortcuts["kubescope.gabi.ask"]
    assert shortcut.key().toString() == "Ctrl+G"


def test_saving_the_settings_saves_her_section_and_the_chat_follows(
    window, ctx
) -> None:
    window._apply_extension_contributions()
    [entry] = sections(window)
    window._show_page(2)
    entry.panel.enabled.setChecked(False)

    window._save_preferences()

    assert window.settings.extension_data("kubescope.gabi")["enabled"] is False
    assert services.controller.dock.bubble.isHidden()
    entry.panel.enabled.setChecked(True)
    window._save_preferences()
    assert window.settings.extension_data("kubescope.gabi")["enabled"] is True


def test_a_path_that_is_not_a_program_stops_the_settings_from_saving(
    window, ctx, monkeypatch
) -> None:
    window._apply_extension_contributions()
    [entry] = sections(window)
    window._show_page(2)
    shown: list = []
    monkeypatch.setattr(
        window, "_show_message", lambda icon, title, text: shown.append((title, text))
    )
    entry.panel._paths["claude"].setText("/nowhere/claude")
    before = window.settings.remember_last_context
    window.settings_ui.rememberCheck.setChecked(not before)

    window._save_preferences()

    assert shown and "is not a program that can be run" in shown[0][1]
    assert window.settings.remember_last_context is before  # nothing was saved


def test_the_button_of_the_section_forgets_the_conversations(
    window, ctx, monkeypatch
) -> None:
    window._apply_extension_contributions()
    [entry] = sections(window)
    cleared: list = []
    monkeypatch.setattr(services.controller, "clear_history", lambda: cleared.append(1))

    entry.panel.clear_button.click()

    assert cleared == [1]
