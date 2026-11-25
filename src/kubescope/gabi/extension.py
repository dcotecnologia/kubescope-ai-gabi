"""Gabi as an extension: what she asks of the app and what she adds to it.

`activate(ctx)` is what the app calls when it runs her. In the window
she adds the chat in the corner, its shortcut, and her section of the
Settings; in the terminal she adds the command `chat`. What she reads
and changes of a cluster, and everything else of the app, comes through
`ctx`.
"""

from typing import Any

from kubescope.sdk import (
    CONTEXT_CHANGED,
    LANGUAGE_CHANGED,
    SETTINGS_SHOWN,
    SHUTDOWN,
    THEME_CHANGED,
    WRITE_MODE_CHANGED,
    Context,
)

from kubescope.gabi import cli, services
from kubescope.gabi.controller import GabiController, GabiPort
from kubescope.gabi.history import adopt_old_history
from kubescope.gabi.settings import GabiSettings
from kubescope.gabi.settings_panel import GabiSettingsPanel

TITLE = "Gabi"  # the section of the Settings, and its button
SHORTCUT = "kubescope.gabi.ask"


def activate(ctx: Context) -> None:
    services.install(ctx)
    ctx.on_unload(lambda: services.install(None))
    if ctx.ui is not None:
        _in_the_window(ctx, GabiSettings(ctx.settings))
    ctx.add_cli_command("chat", cli.main)
    ctx.add_cli_command("assistant", cli.main)


def _in_the_window(ctx: Context, settings: GabiSettings) -> None:
    ui = ctx.ui
    assert ui is not None
    adopt_old_history(ctx.data_directory / "history.json")

    controller = GabiController(
        GabiPort(
            settings=settings,
            app=ctx.app,
            components=ui.components,
            parent=ui.window,
            central=ui.central,
            invoke=ctx.invoke,
            context=lambda: ctx.current_context or "",
            screen=ctx.snapshot,
            show_message=ui.show_message,
            run_action=ui.run_action,
            show_settings=lambda: ui.show_settings(TITLE),
            reserve_corner=lambda pixels: ui.reserve_corner(ctx.id, pixels),
            hide_side_menu=lambda hidden: ui.hide_side_menu(ctx.id, hidden),
            content_area=lambda: ui.content_area(),
            smaller_window=lambda smaller: ui.components.let_window_shrink(
                ui.window, smaller
            ),
            history_path=ctx.data_directory / "history.json",
            notify=lambda title, message, click: ui.show_system_notification(
                title, message, click, "task"
            ),
        )
    )
    services.controller = controller
    ctx.events.on(CONTEXT_CHANGED, lambda context: controller.context_changed())
    ctx.events.on(THEME_CHANGED, lambda: controller.restyle())
    ctx.events.on(LANGUAGE_CHANGED, lambda language: _language_changed(controller))
    ctx.events.on(WRITE_MODE_CHANGED, lambda write_mode: controller.refresh_system())
    ctx.events.on(SETTINGS_SHOWN, lambda shown: controller.settings_shown(shown))
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
        lambda: (
            GabiSettingsPanel(
                ui.components,
                settings,
                lambda *chosen: controller.apply_settings(*chosen),
                lambda text: ui.show_message("warning", TITLE, text),
                lambda: controller.clear_history(),
            ).widget
        ),
    )
    ctx.on_unload(lambda: controller.close())
    ctx.on_unload(lambda: setattr(services, "controller", None))


def _language_changed(controller: GabiController) -> Any:
    controller.retranslate()
    controller.refresh_system()
