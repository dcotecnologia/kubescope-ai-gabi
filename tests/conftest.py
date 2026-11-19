"""Fixtures of the tests of Gabi."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


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
    """A modal dialog nobody can answer would hang the run; fail fast instead."""
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


class LentApp:
    """The context that the app gives Gabi, with the real bridges of the app and
    the write mode in the hand of the test."""

    id = "kubescope.gabi"
    permissions = frozenset({"cluster.read", "cluster.write", "ui.window"})

    def __init__(self) -> None:
        from kubescope.extensions.cluster_access import ClusterBridge, WritesBridge

        from kubescope import theme

        self.write_mode = True
        self.cluster = ClusterBridge()
        self.writes = WritesBridge(lambda: self.write_mode)

        class Ui:
            def themed(self, color: str, text: bool = False) -> str:
                return theme.themed(color, text=text)

        self.ui = Ui()


@pytest.fixture(autouse=True)
def app():
    """Gabi is activated with the services of the app, as she is in the window."""
    from kubescope.gabi import services

    lent = LentApp()
    services.install(lent)  # type: ignore[arg-type]
    yield lent
    services.install(None)
