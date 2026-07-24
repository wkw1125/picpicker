from pathlib import Path
from unittest.mock import patch

from picpicker.gui import PicPickerApp


def _app_with_image(path: Path):
    app = PicPickerApp.__new__(PicPickerApp)
    app._get_displayed_image_path = lambda index: path
    return app


def test_reveal_image_file_uses_finder_reveal(tmp_path):
    image_path = tmp_path / "photo with spaces.jpg"
    app = _app_with_image(image_path)

    with (
        patch("picpicker.gui.platform.system", return_value="Darwin"),
        patch("picpicker.gui.subprocess.run") as run,
    ):
        app._reveal_image_file(0)

    run.assert_called_once_with(
        ["open", "-R", str(image_path.absolute())],
        check=True,
    )


def test_reveal_image_file_uses_explorer_select(tmp_path):
    image_path = tmp_path / "photo.jpg"
    app = _app_with_image(image_path)

    with (
        patch("picpicker.gui.platform.system", return_value="Windows"),
        patch("picpicker.gui.subprocess.Popen") as popen,
    ):
        app._reveal_image_file(0)

    popen.assert_called_once_with(
        ["explorer.exe", f"/select,{image_path.absolute()}"]
    )
