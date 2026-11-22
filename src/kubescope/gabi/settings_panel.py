"""Her section of the Settings: whether the chat shows, which program answers,
the model and the effort of each, and where the programs are.

The window gives it a card, loads it when the Settings open and asks it
to save with the rest; it does what the person typed through the
functions it is given.
"""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kubescope.gabi import ASSISTANTS, installed, runner
from kubescope.gabi.runner import is_available
from kubescope.gabi.settings import GabiSettings

ApplySettings = Callable[
    [bool, str, dict[str, str], dict[str, str], dict[str, str]], None
]


class GabiSettingsPanel(QWidget):
    def __init__(
        self,
        settings: GabiSettings,
        apply: ApplySettings,
        notify: Callable[[str], None],
        clear_history: Callable[[], None],
    ) -> None:
        super().__init__()
        self.settings = settings
        self._apply = apply
        self._notify = notify  # tells the person why nothing was saved
        self._models: dict[str, tuple[QComboBox, QComboBox]] = {}
        self._paths: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.enabled = QCheckBox(
            self.tr("Show the assistant, a chat in the corner of the window")
        )
        self.enabled.setToolTip(
            self.tr(
                "Turns the chat button on or off. Nothing is sent anywhere until "
                "you open the chat and agree."
            )
        )
        layout.addWidget(self.enabled)

        self.program = QComboBox()
        self.program.setProperty("variant", "filter")
        self.program.setToolTip(
            self.tr(
                "The program of this computer that answers. Automatic uses the "
                "first one the system has."
            )
        )
        layout.addWidget(self.program)

        self.models_label = QLabel(self.tr("Model and effort of each program"))
        self.models_label.setProperty("variant", "muted")
        layout.addWidget(self.models_label)
        self.models_layout = QVBoxLayout()
        self.models_layout.setSpacing(6)
        self.models_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.models_layout)

        paths_label = QLabel(
            self.tr("Where the programs are, when the system does not find them")
        )
        paths_label.setProperty("variant", "muted")
        layout.addWidget(paths_label)
        self.paths_layout = QVBoxLayout()
        self.paths_layout.setSpacing(6)
        self.paths_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.paths_layout)

        hint = QLabel(
            self.tr(
                "The assistant uses the client that is already installed on this "
                "computer, such as Claude Code or Codex, signed in the way you "
                "already are. KubeScope asks you for no credentials and stores "
                "none: the sign-in stays with that program. What you ask, attach "
                "and what it reads from the cluster go to that program and to its "
                "service. The conversations are kept on this computer, without the "
                "documents and logs that were read."
            )
        )
        hint.setWordWrap(True)
        hint.setProperty("variant", "muted")
        layout.addWidget(hint)

        self.clear_button = QPushButton(self.tr("Clear the chat history"))
        self.clear_button.setProperty("variant", "secondary")
        self.clear_button.clicked.connect(clear_history)
        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        layout.addLayout(row)

    # showing what is saved

    def load(self) -> None:
        """Show the preferences as they are saved."""
        self.enabled.setChecked(self.settings.assistant_enabled)
        self._fill_paths()
        self._fill_models()
        self.program.clear()
        self.program.addItem(self.tr("Automatic: the first one found"), "")
        for one in installed():  # only what this computer has
            self.program.addItem(one.name, one.key)
        self.program.setCurrentIndex(
            max(self.program.findData(self.settings.assistant), 0)
        )

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while (item := layout.takeAt(0)) is not None:
            if (widget := item.widget()) is not None:
                widget.deleteLater()

    @staticmethod
    def _line(label: str, *widgets: QWidget, stretch: bool = False) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        name = QLabel(label)
        name.setFixedWidth(100)
        row.addWidget(name)
        for widget in widgets:
            row.addWidget(widget, 1 if stretch and widget is widgets[0] else 0)
        if not stretch:
            row.addStretch(1)
        holder = QWidget()
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
            model = QComboBox()
            model.addItem(self.tr("Default model"), "")
            for name in one.models:
                model.addItem(name, name)
            kept = self.settings.assistant_models.get(one.key, "")
            if kept and model.findData(kept) < 0:
                model.addItem(kept, kept)  # a model the program no longer lists
            model.setCurrentIndex(max(model.findData(kept), 0))
            effort = QComboBox()
            effort.addItem(self.tr("Default effort"), "")
            for level in one.efforts:
                effort.addItem(level, level)
            saved = self.settings.assistant_efforts.get(one.key, "")
            if saved and effort.findData(saved) < 0:
                effort.addItem(saved, saved)  # a level the program no longer lists
            effort.setCurrentIndex(max(effort.findData(saved), 0))
            effort.setEnabled(one.effort_options is not None)
            for box in (model, effort):
                box.setProperty("variant", "filter")
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
            edit = QLineEdit(saved.get(one.key, ""))
            missing = self.tr("Not found: {program} is not on the path").format(
                program=one.program
            )
            edit.setPlaceholderText(
                self.tr("Found on the path of the system")
                if is_available(one)
                else missing
            )
            edit.setProperty("variant", "filter")
            browse = QPushButton(self.tr("Browse..."))
            browse.setProperty("variant", "secondary")
            browse.clicked.connect(
                lambda _checked=False, field=edit, name=one.name: self._browse(
                    field, name
                )
            )
            self.paths_layout.addWidget(
                self._line(one.name, edit, browse, stretch=True)
            )
            self._paths[one.key] = edit

    def _browse(self, edit: QLineEdit, name: str) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, self.tr("Where is {name}?").format(name=name), str(Path.home())
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
                    self.tr("{path} is not a program that can be run ({name}).").format(
                        path=path, name=one.name
                    )
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
