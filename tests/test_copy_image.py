from pathlib import Path

from picpicker import gui
from picpicker.gui import PicPickerApp


class FakeRoot:
    def __init__(self):
        self.clipboard_text = None
        self.updated = False

    def clipboard_clear(self):
        self.clipboard_text = None

    def clipboard_append(self, text):
        self.clipboard_text = text

    def update_idletasks(self):
        self.updated = True


class FakeStatus:
    def __init__(self):
        self.text = None

    def config(self, *, text):
        self.text = text


def make_app(image_path):
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()
    app.status_label = FakeStatus()
    app._get_displayed_image_path = lambda index: Path(image_path)
    return app


def test_copy_image_path_writes_absolute_path_as_text(tmp_path):
    image_path = tmp_path / "image.jpg"
    app = make_app(image_path)

    app._copy_image_path(0)

    assert app.root.clipboard_text == str(image_path.absolute())
    assert app.root.updated is True


def test_macos_copy_image_writes_file_object_to_clipboard(tmp_path, monkeypatch):
    image_path = tmp_path / "image.jpg"
    app = make_app(image_path)
    calls = []
    monkeypatch.setattr(gui.platform, "system", lambda: "Darwin")

    class Result:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        gui.subprocess,
        "run",
        lambda args, **kwargs: calls.append((args, kwargs)) or Result(),
    )

    app._copy_image_file(0)

    args, kwargs = calls[0]
    assert args[0] == "osascript"
    assert args[1:3] == ["-l", "JavaScript"]
    assert "$.NSArray.arrayWithObject(fileURL)" in args[4]
    assert "pasteboard.writeObjects(files)" in args[4]
    assert args[-1] == str(image_path.absolute())
    assert kwargs == {"capture_output": True, "text": True}
