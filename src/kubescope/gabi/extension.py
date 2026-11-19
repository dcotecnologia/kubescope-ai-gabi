"""Gabi as an extension: what she asks of the app and what she adds to it.

`activate(ctx)` is what the app calls when it runs her. In the window she adds
the chat in the corner, its shortcut, and her section of the Settings; in the
terminal she adds the command `chat`. What she reads and changes of a cluster,
and everything else of the app, comes through `ctx`.
"""

from typing import Any

from kubescope.sdk import (
    CONTEXT_CHANGED,
    LANGUAGE_CHANGED,
    SHUTDOWN,
    THEME_CHANGED,
    WRITE_MODE_CHANGED,
    Context,
)
from kubescope.sdk.paths import config_directory
from PySide6.QtWidgets import QMessageBox

from kubescope.gabi import cli, services
from kubescope.gabi.controller import GabiController, GabiPort
from kubescope.gabi.settings import GabiSettings
from kubescope.gabi.settings_panel import GabiSettingsPanel

TITLE = "Gabi"  # the section of the Settings, and its button
SHORTCUT = "kubescope.gabi.ask"
OLD_HISTORY = "assistant_history.json"  # where the app kept the conversations

_ICONS = {
    QMessageBox.Icon.Warning: "warning",
    QMessageBox.Icon.Critical: "critical",
}


def activate(ctx: Context) -> None:
    services.install(ctx)
    ctx.on_unload(lambda: services.install(None))
    if ctx.ui is not None:
        _in_the_window(ctx, GabiSettings(ctx.settings))
    ctx.add_cli_command("chat", cli.main)
    ctx.add_cli_command("assistant", cli.main)


def _adopt_old_history(ctx: Context) -> None:
    """The conversations the app kept for her before she was an extension move to
    the folder of her own, once."""
    old = config_directory() / OLD_HISTORY
    new = ctx.data_directory / "history.json"
    if old.is_file() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        old.replace(new)


def _in_the_window(ctx: Context, settings: GabiSettings) -> None:
    ui = ctx.ui
    assert ui is not None
    _adopt_old_history(ctx)

    def show_message(icon: QMessageBox.Icon, title: str, text: str) -> None:
        ui.show_message(_ICONS.get(icon, "information"), title, text)

    controller = GabiController(
        GabiPort(
            settings=settings,
            app=ctx.app,
            parent=ui.window,
            central=ui.central,
            invoke=ctx.invoke,
            context=lambda: ctx.current_context or "",
            screen=ctx.snapshot,
            show_message=show_message,
            run_action=ui.run_action,
            style_box=ui.style_box,
            show_settings=lambda: ui.show_settings(TITLE),
            reserve_corner=lambda pixels: ui.reserve_corner(ctx.id, pixels),
            history_path=ctx.data_directory / "history.json",
        )
    )
    services.controller = controller
    ctx.events.on(CONTEXT_CHANGED, lambda context: controller.context_changed())
    ctx.events.on(THEME_CHANGED, lambda: controller.restyle())
    ctx.events.on(LANGUAGE_CHANGED, lambda language: _language_changed(controller))
    ctx.events.on(WRITE_MODE_CHANGED, lambda write_mode: controller.refresh_system())
    ctx.events.on(SHUTDOWN, lambda: controller.shutdown())
    ctx.add_shortcut(
        SHORTCUT,
        "Ask the assistant",
        "Ctrl+G",
        lambda: controller.shortcut(),
        application=True,
    )
    ctx.add_settings_section(
        TITLE,
        lambda: GabiSettingsPanel(
            settings,
            lambda *chosen: controller.apply_settings(*chosen),
            lambda text: ui.show_message("warning", TITLE, text),
            lambda: controller.clear_history(),
        ),
    )
    ctx.on_unload(lambda: controller.close())
    ctx.on_unload(lambda: setattr(services, "controller", None))


def _language_changed(controller: GabiController) -> Any:
    controller.retranslate()
    controller.refresh_system()
