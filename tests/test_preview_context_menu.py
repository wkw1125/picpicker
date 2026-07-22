from types import SimpleNamespace

from picpicker.gui import PicPickerApp


class FakeMenu:
    def __init__(self):
        self.popup_position = None
        self.released = False
        self.entries = []

    def delete(self, start, end):
        self.entries.clear()

    def add_command(self, **options):
        self.entries.append(("command", options))

    def add_checkbutton(self, **options):
        self.entries.append(("checkbutton", options))

    def tk_popup(self, x, y):
        self.popup_position = (x, y)

    def grab_release(self):
        self.released = True


def test_preview_context_menu_opens_at_pointer_and_releases_grab():
    app = PicPickerApp.__new__(PicPickerApp)
    app.folder_paths = ["/images", None, None]
    app.magnifier_menu_var = object()
    app._toggle_magnifier = lambda: None
    app.show_note_overlay = True
    app._toggle_note_visibility = lambda: None
    menu = FakeMenu()
    event = SimpleNamespace(x_root=120, y_root=240)

    result = app._show_preview_context_menu(event, menu, 0)

    assert result == "break"
    assert menu.popup_position == (120, 240)
    assert menu.released is True


def test_unopened_preview_context_menu_only_offers_folder_selection():
    app = PicPickerApp.__new__(PicPickerApp)
    app.folder_paths = [None, None, None]
    menu = FakeMenu()

    app._populate_preview_context_menu(menu, 1)

    assert [(kind, options["label"]) for kind, options in menu.entries] == [
        ("command", "打开图1文件夹")
    ]


def test_opened_preview_context_menu_offers_file_actions():
    app = PicPickerApp.__new__(PicPickerApp)
    app.folder_paths = ["/images", None, None]
    menu = FakeMenu()

    app._populate_preview_context_menu(menu, 0)

    assert [(kind, options["label"]) for kind, options in menu.entries] == [
        ("command", "打开"),
        ("command", "打开方式"),
        ("command", "拷贝"),
        ("command", "拷贝路径"),
    ]
