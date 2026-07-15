from pathlib import Path

from picpicker.gui import COPY, DND_FILES, PicPickerApp, REFUSE_DROP


def make_app():
    app = PicPickerApp.__new__(PicPickerApp)
    app.image_lists = [
        [Path("/images/original-1.jpg")],
        [Path("/images/compare-1.jpg")],
        [Path("/images/compare-2.jpg")],
    ]
    app.mask_image_lists = [
        [Path("/masks/mask-1.png")],
        [Path("/masks/mask-2.png")],
    ]
    app.current_indices = [0, 0, 0]
    app.show_mask_mode = [False, False]
    app.blind_mode = False
    app.blind_swap_indices = set()
    return app


def test_displayed_image_path_uses_original_and_compare_sources():
    app = make_app()

    assert app._get_displayed_image_path(0) == Path("/images/original-1.jpg")
    assert app._get_displayed_image_path(1) == Path("/images/compare-1.jpg")
    assert app._get_displayed_image_path(2) == Path("/images/compare-2.jpg")


def test_displayed_image_path_uses_mask_and_falls_back_to_image():
    app = make_app()
    app.show_mask_mode = [True, True]

    assert app._get_displayed_image_path(1) == Path("/masks/mask-1.png")
    app.mask_image_lists[1] = []
    assert app._get_displayed_image_path(2) == Path("/images/compare-2.jpg")


def test_displayed_image_path_follows_blind_mode_swap():
    app = make_app()
    app.blind_mode = True
    app.blind_swap_indices = {0}

    assert app._get_displayed_image_path(1) == Path("/images/compare-2.jpg")
    assert app._get_displayed_image_path(2) == Path("/images/compare-1.jpg")


def test_drag_init_returns_source_file_with_copy_action(tmp_path):
    image_path = tmp_path / "image with spaces.png"
    image_path.write_bytes(b"source image")
    app = make_app()
    app.image_lists[0] = [image_path]

    assert app._on_preview_drag_init(None, 0) == (
        COPY,
        DND_FILES,
        (str(image_path.absolute()),),
    )
    assert image_path.read_bytes() == b"source image"


def test_drag_init_refuses_when_no_source_file_exists():
    app = make_app()
    app.image_lists[0] = []

    assert app._on_preview_drag_init(None, 0) == REFUSE_DROP
