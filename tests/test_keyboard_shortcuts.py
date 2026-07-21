from picpicker import gui
from picpicker.gui import PicPickerApp


class FakeRoot:
    def __init__(self):
        self.bindings = {}
        self.global_bindings = {}
        self.focused = False

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def bind_all(self, sequence, callback):
        self.global_bindings[sequence] = callback

    def focus_set(self):
        self.focused = True


def test_windows_registers_view_shortcuts_before_window_maximization(monkeypatch):
    monkeypatch.setattr(gui.platform, "system", lambda: "Windows")
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()

    app._bind_keyboard_shortcuts()

    expected_bindings = {
        "<KeyPress-g>": app._on_key_g,
        "<KeyPress-a>": app._on_key_a,
        "<KeyPress-s>": app._on_key_s,
        "<KeyPress-c>": app._on_key_c,
        "<Control-b>": app._on_key_b,
    }
    for sequence, callback in expected_bindings.items():
        assert app.root.bindings[sequence] == callback

    assert app.root.global_bindings["<Control-l>"] == app._on_key_l
    assert "<Command-l>" not in app.root.global_bindings
    assert app.root.focused


def test_windows_registers_main_and_keypad_background_shortcuts(monkeypatch):
    monkeypatch.setattr(gui.platform, "system", lambda: "Windows")
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()

    app._bind_keyboard_shortcuts()

    for number in range(1, 7):
        main_callback = app.root.bindings[f"<KeyPress-{number}>"]
        keypad_callback = app.root.bindings[f"<KeyPress-KP_{number}>"]
        assert main_callback.__defaults__ == (number - 1,)
        assert keypad_callback.__defaults__ == (number - 1,)
