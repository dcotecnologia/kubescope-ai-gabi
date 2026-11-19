"""Fixtures of the tests of Gabi."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from kubescope.sdk.errors import ClusterError


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Never read or write the real user settings during tests."""
    monkeypatch.setenv("KUBESCOPE_CONFIG_DIR", str(tmp_path / "config"))
    # nor the configuration of the programs Gabi runs, which says the model and
    # the effort they use
    home = tmp_path / "isolated-home"  # not made: it is only a place with nothing in it
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))


@pytest.fixture(autouse=True)
def light_theme():
    """The theme is process-wide state; every test starts and ends on light."""
    from kubescope import theme

    theme.set_theme("light")
    yield
    theme.set_theme("light")


@pytest.fixture(autouse=True)
def still_windows(monkeypatch):
    """Windows and lists show at once."""
    from kubescope.views import motion

    monkeypatch.setattr(motion, "ENABLED", False)
    monkeypatch.setattr(motion, "DURATION_MS", 0)


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch):
    """A modal dialog nobody can answer would hang the run; fail fast
    instead."""
    from PySide6.QtWidgets import QDialog, QMessageBox

    def refuse(*_args, **_kwargs):
        running = os.environ.get("PYTEST_CURRENT_TEST", "no test")
        raise AssertionError(f"a test opened a real modal dialog ({running})")

    monkeypatch.setattr(QDialog, "exec", refuse)
    monkeypatch.setattr(QMessageBox, "exec", refuse)


@pytest.fixture(autouse=True)
def no_chosen_assistant_programs():
    """The program, the model and the effort chosen for an assistant are kept
    in the runner; a test starts without."""
    from kubescope.gabi import runner

    saved = [
        dict(d)
        for d in (runner.CUSTOM_PROGRAMS, runner.CUSTOM_MODELS, runner.CUSTOM_EFFORTS)
    ]
    for chosen in (runner.CUSTOM_PROGRAMS, runner.CUSTOM_MODELS, runner.CUSTOM_EFFORTS):
        chosen.clear()
    yield
    for chosen, before in zip(
        (runner.CUSTOM_PROGRAMS, runner.CUSTOM_MODELS, runner.CUSTOM_EFFORTS),
        saved,
        strict=True,
    ):
        chosen.clear()
        chosen.update(before)


@pytest.fixture(autouse=True)
def still_panel(monkeypatch):
    """The panel of Gabi shows and goes at once."""
    from kubescope.gabi import panel

    monkeypatch.setattr(panel, "ANIMATION_MS", 0)


class Store(dict):
    """What ctx.settings is: a dictionary that is saved when a key is set."""

    failure: OSError | None = None  # a disk that cannot be written

    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value) -> None:
        if self.failure is not None:
            raise self.failure
        self[key] = value


class LentTerminal:
    """What the terminal lends to a command (`ctx.cli`)."""

    def __init__(self) -> None:
        self.answer = True
        self.asked: list[str] = []

    def choose_context(self, name):
        if name:
            return name
        raise ClusterError("Pass --context (the choice is asked on a terminal only)")

    def confirm(self, question: str) -> bool:
        self.asked.append(question)
        return self.answer


class LentApp:
    """The context that the app gives Gabi, with the real bridges of the app
    and the write mode, the settings and the terminal in the hand of the
    test."""

    id = "kubescope.gabi"
    permissions = frozenset({"cluster.read", "cluster.write", "ui.window", "cli"})

    def __init__(self, data_directory) -> None:
        from kubescope.extensions.cluster_access import ClusterBridge, WritesBridge

        from kubescope import theme

        self.write_mode = True
        self.language = "auto"
        self.resolved_language = "en_US"
        self.language_name = "English"
        self.language_names = ("English", "Portuguese")
        self.app = self  # what the app says about itself is on the same object
        self.data_directory = data_directory
        self.settings = Store()
        self.cli: LentTerminal | None = LentTerminal()
        self.cluster = ClusterBridge()
        self.writes = WritesBridge(lambda: self.write_mode)

        class Ui:
            def themed(self, color: str, text: bool = False) -> str:
                return theme.themed(color, text=text)

        self.ui = Ui()

    @property
    def preferences(self):
        """Her preferences, as the code reads them."""
        from kubescope.gabi.settings import GabiSettings

        return GabiSettings(self.settings)


@pytest.fixture(autouse=True)
def app(tmp_path):
    """Gabi is activated with the services of the app, as she is in the
    window."""
    from kubescope.gabi import services

    lent = LentApp(tmp_path / "data")
    services.install(lent)  # type: ignore[arg-type]
    yield lent
    services.install(None)


class _FakeRefreshWorker:
    """Stands in for the worker that reads a cluster: it answers nothing, at
    once."""

    def __init__(self, *_args, **_kwargs) -> None:
        from PySide6.QtCore import QObject, Signal

        class Signals(QObject):
            completed = Signal(list, list)
            failed = Signal(str)
            finished = Signal()

        self._signals = Signals()
        self.completed = self._signals.completed
        self.failed = self._signals.failed
        self.finished = self._signals.finished
        self.key = None

    def isRunning(self) -> bool:
        return False

    def start(self) -> None:
        self.finished.emit()


@pytest.fixture
def window(monkeypatch):
    """The window of the app, with a "prod" context and no cluster behind
    it."""
    import time

    from PySide6.QtWidgets import QApplication

    from kubescope import window as window_module

    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(window_module, "list_contexts", lambda: ([], None))
    monkeypatch.setattr(
        window_module.WorkloadWindow, "refresh_overview", lambda *_a: None
    )
    monkeypatch.setattr(window_module, "RefreshWorker", _FakeRefreshWorker)
    shown = window_module.WorkloadWindow()
    deadline = time.monotonic() + 3
    while shown._action_workers and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    shown.context_combo.blockSignals(True)
    shown.context_combo.addItem("prod")
    shown.context_combo.setCurrentIndex(0)
    shown.context_combo.blockSignals(False)
    yield shown
    shown.close()


@pytest.fixture(autouse=True)
def no_recommended_extensions(monkeypatch):
    """The window of the app downloads what it recommends the first time it
    runs; a test never reaches GitHub."""
    monkeypatch.setattr("kubescope.extensions.defaults.DEFAULTS", ())
