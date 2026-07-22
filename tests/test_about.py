from picpicker import gui


def test_about_dialog_displays_application_version(monkeypatch):
    app = gui.PicPickerApp.__new__(gui.PicPickerApp)
    app.root = object()
    shown = {}

    monkeypatch.setattr(gui, "VERSION", "v1.2.0")
    monkeypatch.setattr(
        gui.messagebox,
        "showinfo",
        lambda title, message, parent: shown.update(
            title=title,
            message=message,
            parent=parent,
        ),
    )

    app._show_about()

    assert shown["title"] == "关于 PicPicker"
    assert "版本：v1.2.0" in shown["message"]
    assert shown["parent"] is app.root


def test_macos_native_about_uses_application_dialog(monkeypatch):
    app = gui.PicPickerApp.__new__(gui.PicPickerApp)
    registered = {}

    class FakeRoot:
        def createcommand(self, name, callback):
            registered[name] = callback

    app.root = FakeRoot()
    monkeypatch.setattr(gui.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(app, "_show_about", lambda: registered.update(opened=True))

    app._register_macos_about_command()
    registered["tkAboutDialog"]()

    assert registered["opened"] is True
