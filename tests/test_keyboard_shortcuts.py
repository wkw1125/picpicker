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
        "<Control-g>": app._on_key_g,
        "<KeyPress-a>": app._on_key_a,
        "<KeyPress-s>": app._on_key_s,
        "<KeyPress-comma>": app._on_key_comma,
        "<KeyPress-period>": app._on_key_period,
        "<KeyPress-slash>": app._on_key_slash,
        "<Control-b>": app._on_key_b,
    }
    for sequence, callback in expected_bindings.items():
        assert app.root.bindings[sequence] == callback

    assert app.root.global_bindings["<Control-l>"] == app._on_key_l
    assert "<Command-l>" not in app.root.global_bindings
    assert "<KeyPress-g>" not in app.root.bindings
    assert "<KeyPress-c>" not in app.root.bindings
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


def test_macos_registers_command_g_for_jump(monkeypatch):
    monkeypatch.setattr(gui.platform, "system", lambda: "Darwin")
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()

    app._bind_keyboard_shortcuts()

    assert app.root.bindings["<Command-g>"] == app._on_key_g
    assert app.root.bindings["<Command-G>"] == app._on_key_g
    assert "<KeyPress-g>" not in app.root.bindings


def test_note_shortcuts_do_not_fire_while_typing_in_text_field():
    class FakeEntry:
        def winfo_class(self):
            return "Entry"

    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()
    app.root.focus_get = lambda: FakeEntry()
    edited_slots = []
    app._edit_note = edited_slots.append
    app._toggle_note_visibility = lambda: edited_slots.append("toggle")

    assert app._on_key_comma(None) is None
    assert app._on_key_period(None) is None
    assert app._on_key_slash(None) is None
    assert edited_slots == []


def test_windows_registers_new_save_shortcuts(monkeypatch):
    monkeypatch.setattr(gui.platform, "system", lambda: "Windows")
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()

    app._bind_keyboard_shortcuts()

    assert "<Control-s>" in app.root.bindings
    assert "<Control-Shift-s>" in app.root.bindings
    assert "<Control-Shift-e>" in app.root.bindings
    assert "<Control-S>" not in app.root.bindings
