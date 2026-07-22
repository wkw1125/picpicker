from pathlib import Path
from types import SimpleNamespace

from picpicker import gui
from picpicker.gui import PicPickerApp


def make_app(image_path):
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = object()
    app._get_displayed_image_path = lambda index: Path(image_path)
    return app


def test_macos_open_with_uses_system_application_chooser(tmp_path, monkeypatch):
    image_path = tmp_path / "image.jpg"
    app = make_app(image_path)
    calls = []
    monkeypatch.setattr(gui.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        gui.subprocess,
        "run",
        lambda args, **kwargs: calls.append((args, kwargs))
        or SimpleNamespace(returncode=0, stderr=""),
    )

    app._open_image_with(0)

    args, kwargs = calls[0]
    assert args[0] == "osascript"
    assert "choose application" in args[2]
    assert args[-1] == str(image_path.absolute())
    assert kwargs == {"capture_output": True, "text": True}


def test_windows_open_with_uses_shell_dialog(tmp_path, monkeypatch):
    image_path = tmp_path / "image.jpg"
    app = make_app(image_path)
    calls = []
    monkeypatch.setattr(gui.platform, "system", lambda: "Windows")
    monkeypatch.setattr(gui.subprocess, "Popen", calls.append)

    app._open_image_with(0)

    assert calls == [
        ["rundll32.exe", "shell32.dll,OpenAs_RunDLL", str(image_path.absolute())]
    ]
