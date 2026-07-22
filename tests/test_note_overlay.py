from pathlib import Path

from picpicker.gui import PicPickerApp


def make_app():
    app = PicPickerApp.__new__(PicPickerApp)
    app.image_lists = [
        [],
        [Path("/images/compare-1.jpg")],
        [Path("/images/compare-2.jpg")],
    ]
    app.current_indices = [0, 0, 0]
    app.notes = [{0: "图1备注"}, {0: "图2备注"}]
    app.blind_mode = False
    app.blind_swap_indices = set()
    return app


def test_note_overlay_uses_note_for_its_preview_slot():
    app = make_app()

    assert app._get_note_overlay_text(1) == "图1备注"
    assert app._get_note_overlay_text(2) == "图2备注"


def test_note_overlay_follows_blind_mode_swap():
    app = make_app()
    app.blind_mode = True
    app.blind_swap_indices = {0}

    assert app._get_note_overlay_text(1) == "图2备注"
    assert app._get_note_overlay_text(2) == "图1备注"


def test_note_overlay_is_empty_for_missing_or_invalid_image():
    app = make_app()
    app.image_lists[1] = []
    app.current_indices[2] = 10

    assert app._get_note_overlay_text(0) == ""
    assert app._get_note_overlay_text(1) == ""
    assert app._get_note_overlay_text(2) == ""


def test_note_toggle_refreshes_again_after_current_tk_event():
    class FakeMenu:
        def __init__(self):
            self.label = None

        def entryconfig(self, index, *, label):
            self.label = label

    class FakeRoot:
        def __init__(self):
            self.idle_callback = None

        def after_idle(self, callback):
            self.idle_callback = callback

    app = PicPickerApp.__new__(PicPickerApp)
    app.show_note_overlay = False
    app.view_menu = FakeMenu()
    app.toggle_note_menu_index = 1
    app.root = FakeRoot()
    refresh_calls = []
    app._refresh_note_overlays = lambda: refresh_calls.append(True)

    app._toggle_note_visibility()

    assert app.show_note_overlay is True
    assert app.view_menu.label == "隐藏备注"
    assert len(refresh_calls) == 1
    assert app.root.idle_callback is not None

    app.root.idle_callback()
    assert len(refresh_calls) == 2


def test_note_text_color_contrasts_with_preview_background():
    assert PicPickerApp._get_contrasting_text_color("#FFFFFF") == "#000000"
    assert PicPickerApp._get_contrasting_text_color("#e0e0e0") == "#000000"
    assert PicPickerApp._get_contrasting_text_color("#000000") == "#FFFFFF"
    assert PicPickerApp._get_contrasting_text_color("#990000") == "#FFFFFF"
    assert PicPickerApp._get_contrasting_text_color("#006400") == "#FFFFFF"
    assert PicPickerApp._get_contrasting_text_color("#0000AA") == "#FFFFFF"
