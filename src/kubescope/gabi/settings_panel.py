"""Her section of the Settings: whether the chat shows, which program answers,
the model and the effort of each, and where the programs are.

The window gives it a card, loads it when the Settings open and asks it
to save with the rest; it does what the person typed through the
functions it is given.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from kubescope.sdk import translate

from kubescope.gabi import ASSISTANTS, installed, runner
from kubescope.gabi.runner import is_available
from kubescope.gabi.settings import GabiSettings

ApplySettings = Callable[
    [bool, str, dict[str, str], dict[str, str], dict[str, str]], None
]


class GabiSettingsPanel:
    def __init__(
        self,
        components: Any,
        settings: GabiSettings,
        apply: ApplySettings,
        notify: Callable[[str], None],
        clear_history: Callable[[], None],
    ) -> None:
        self.components = components
        self.widget = components.widget(load=self.load, save=self.save)
        self.settings = settings
        self._apply = apply
        self._notify = notify  # tells the person why nothing was saved
        self._models: dict[str, tuple[Any, Any]] = {}
        self._paths: dict[str, Any] = {}
        self.enabled = components.checkbox(
            translate(
                "GabiSettingsPanel",
                "Show the assistant, a chat in the corner of the window",
            )
        )
        self.enabled.setToolTip(
            translate(
                "GabiSettingsPanel",
                "Turns the chat button on or off. Nothing is sent anywhere until "
                "you open the chat and agree.",
            )
        )
        self.program = components.filter_select()
        self.program.setToolTip(
            translate(
                "GabiSettingsPanel",
                "The program of this computer that answers. Automatic uses the "
                "first one the system has.",
            )
        )
        self.models_label = components.label(
            translate("GabiSettingsPanel", "Model and effort of each program"), "muted"
        )
        self.models_layout = components.column(spacing=6)
        self.models_layout.setContentsMargins(0, 0, 0, 0)
        self.paths_layout = components.column(spacing=6)
        self.paths_layout.setContentsMargins(0, 0, 0, 0)
        self.clear_button = components.button(
            translate("GabiSettingsPanel", "Clear the chat history"),
            on_click=clear_history,
        )
        layout = components.column(
            self.enabled,
            self.program,
            self.models_label,
            self.models_layout,
            components.label(
                translate(
                    "GabiSettingsPanel",
                    "Where the programs are, when the system does not find them",
                ),
                "muted",
            ),
            self.paths_layout,
            components.label(
                translate(
                    "GabiSettingsPanel",
                    "The assistant uses the client that is already installed on "
                    "this computer, such as Claude Code or Codex, signed in the "
                    "way you already are. KubeScope asks you for no credentials "
                    "and stores none: the sign-in stays with that program. What "
                    "you ask, attach and what it reads from the cluster go to "
                    "that program and to its service. The conversations are kept "
                    "on this computer, without the documents and logs that were "
                    "read.",
                ),
                "muted",
                wrap=True,
            ),
            components.row(self.clear_button, None),
            spacing=14,
        )
        layout.setContentsMargins(0, 0, 0, 0)
        self.widget.setLayout(layout)

    # showing what is saved

    def load(self) -> None:
        """Show the preferences as they are saved."""
        self.enabled.setChecked(self.settings.assistant_enabled)
        self._fill_paths()
        self._fill_models()
        self.program.clear()
        self.program.addItem(
            translate("GabiSettingsPanel", "Automatic: the first one found"), ""
        )
        for one in installed():  # only what this computer has
            self.program.addItem(one.name, one.key)
        self.program.setCurrentIndex(
            max(self.program.findData(self.settings.assistant), 0)
        )

    @staticmethod
    def _clear(layout: Any) -> None:
        while (item := layout.takeAt(0)) is not None:
            if (widget := item.widget()) is not None:
                widget.deleteLater()

    def _line(self, label: str, *widgets: Any, stretch: bool = False) -> Any:
        name = self.components.label(label)
        name.setFixedWidth(100)
        items: list[Any] = [
            (widget, 1 if stretch and widget is widgets[0] else 0) for widget in widgets
        ]
        if not stretch:
            items.append(None)
        row = self.components.row(name, *items, spacing=6)
        row.setContentsMargins(0, 0, 0, 0)
        holder = self.components.widget()
        holder.setLayout(row)
        return holder

    def _fill_models(self) -> None:
        """One line for each assistant to choose its model and its effort, from
        what that program allows."""
        self._clear(self.models_layout)
        self._models = {}
        found = installed()  # only the programs this computer has
        self.models_label.setVisible(bool(found))
        for one in found:
            model = self.components.filter_select()
            model.addItem(translate("GabiSettingsPanel", "Default model"), "")
            for name in one.models:
                model.addItem(name, name)
            kept = self.settings.assistant_models.get(one.key, "")
            if kept and model.findData(kept) < 0:
                model.addItem(kept, kept)  # a model the program no longer lists
            model.setCurrentIndex(max(model.findData(kept), 0))
            effort = self.components.filter_select()
            effort.addItem(translate("GabiSettingsPanel", "Default effort"), "")
            for level in one.efforts:
                effort.addItem(level, level)
            saved = self.settings.assistant_efforts.get(one.key, "")
            if saved and effort.findData(saved) < 0:
                effort.addItem(saved, saved)  # a level the program no longer lists
            effort.setCurrentIndex(max(effort.findData(saved), 0))
            effort.setEnabled(one.effort_options is not None)
            model.setFixedWidth(240)
            effort.setFixedWidth(170)
            self.models_layout.addWidget(self._line(one.name, model, effort))
            self._models[one.key] = (model, effort)

    def _fill_paths(self) -> None:
        """One line for each assistant to say where its program is, which the
        system may not find by itself."""
        self._clear(self.paths_layout)
        self._paths = {}
        saved = self.settings.assistant_programs
        for one in ASSISTANTS.values():
            edit = self.components.text_field()
            edit.setText(saved.get(one.key, ""))
            missing = translate(
                "GabiSettingsPanel", "Not found: {program} is not on the path"
            ).format(program=one.program)
            edit.setPlaceholderText(
                translate("GabiSettingsPanel", "Found on the path of the system")
                if is_available(one)
                else missing
            )
            browse = self.components.button(
                translate("GabiSettingsPanel", "Browse..."),
                on_click=lambda field=edit, name=one.name: self._browse(field, name),
            )
            self.paths_layout.addWidget(
                self._line(one.name, edit, browse, stretch=True)
            )
            self._paths[one.key] = edit

    def _browse(self, edit: Any, name: str) -> None:
        path = self.components.open_file(
            self.widget,
            translate("GabiSettingsPanel", "Where is {name}?").format(name=name),
            str(Path.home()),
        )
        if path:
            edit.setText(path)

    # keeping what was typed

    def _programs(self) -> dict[str, str] | None:
        """The paths typed; None, with a notice, when one is not a program that
        can be run.

        Empty ones are left out.
        """
        programs: dict[str, str] = {}
        for one in ASSISTANTS.values():
            path = self._paths[one.key].text().strip()
            if not path:
                continue
            if not runner.is_runnable(str(Path(path).expanduser())):
                self._notify(
                    translate(
                        "GabiSettingsPanel",
                        "{path} is not a program that can be run ({name}).",
                    ).format(path=path, name=one.name)
                )
                return None
            programs[one.key] = path
        return programs

    def save(self) -> bool:
        """Keep what the person typed, and make the window follow it; False
        (after telling why) when a path is not a program."""
        programs = self._programs()
        if programs is None:
            return False
        self._apply(
            self.enabled.isChecked(),
            self.program.currentData() or "",
            programs,
            {  # what was chosen for a program that is not here now is kept
                **self.settings.assistant_models,
                **{
                    key: box.currentData() or ""
                    for key, (box, _) in self._models.items()
                },
            },
            {
                **self.settings.assistant_efforts,
                **{
                    key: box.currentData() or ""
                    for key, (_, box) in self._models.items()
                },
            },
        )
        return True
