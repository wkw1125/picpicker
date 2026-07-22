from pathlib import Path

import pytest

from picpicker import gui
from picpicker.gui import PicPickerApp


class FakeRoot:
    def __init__(self):
        self.current_title = None

    def title(self, value):
        self.current_title = value


def make_app():
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()
    app.current_csv_path = None
    app.is_dirty = False
    return app


def make_savable_app(tmp_path):
    app = make_app()
    app.folder_paths = [str(tmp_path / "original"), str(tmp_path / "compare"), None]
    app.image_lists = [
        [tmp_path / "original" / "a.jpg"],
        [tmp_path / "compare" / "a.jpg"],
        [],
    ]
    app.mask_folder_paths = [None, None]
    app.mask_image_lists = [[], []]
    app.selected_states = [{0: True}, {}]
    app.notes = [{0: "备注"}, {}]
    app.is_dirty = True
    return app


def test_dirty_state_updates_window_title():
    app = make_app()

    app._set_dirty(True)
    assert app.is_dirty is True
    assert app.root.current_title == "PicPicker - 比卡拾图 *"

    app._set_dirty(False)
    assert app.is_dirty is False
    assert app.root.current_title == "PicPicker - 比卡拾图"


def test_window_title_shows_current_csv_absolute_path_before_dirty_marker(tmp_path):
    app = make_app()
    app.current_csv_path = str(tmp_path / "marks.csv")

    app._set_dirty(True)

    assert app.root.current_title == f"PicPicker - 比卡拾图 — {tmp_path / 'marks.csv'} *"


@pytest.mark.parametrize(
    ("choice", "save_result", "expected"),
    [
        ("save", True, True),
        ("save", False, False),
        ("discard", None, True),
        ("cancel", None, False),
    ],
)
def test_unsaved_confirmation_controls_pending_action(choice, save_result, expected):
    app = make_app()
    app.is_dirty = True
    app._prompt_unsaved_changes = lambda pending_action: choice
    save_calls = []

    def save():
        save_calls.append(True)
        return save_result

    app._export_to_csv = save

    assert app._confirm_unsaved_changes("退出") is expected
    assert len(save_calls) == (1 if choice == "save" else 0)


def test_clean_current_csv_save_is_no_op():
    app = make_app()
    app.current_csv_path = "/tmp/current.csv"
    app.is_dirty = False
    app._can_generate_csv = lambda: (_ for _ in ()).throw(
        AssertionError("clean save should not generate CSV")
    )

    assert app._export_to_csv() is True


def test_atomic_csv_write_replaces_target_and_removes_temp_file(tmp_path):
    app = make_app()
    target = tmp_path / "marks.csv"
    target.write_text("old", encoding="gbk")

    app._write_csv_atomically(str(target), "新内容")

    assert target.read_text(encoding="gbk") == "新内容"
    assert list(tmp_path.glob(".marks.csv.*.tmp")) == []


def test_atomic_csv_write_preserves_target_if_replace_fails(tmp_path, monkeypatch):
    app = make_app()
    target = tmp_path / "marks.csv"
    target.write_text("old", encoding="gbk")

    def fail_replace(source: Path, destination: Path):
        raise OSError("replace failed")

    monkeypatch.setattr(gui.os, "replace", fail_replace)

    with pytest.raises(RuntimeError, match="replace failed"):
        app._write_csv_atomically(str(target), "new")

    assert target.read_text(encoding="gbk") == "old"
    assert list(tmp_path.glob(".marks.csv.*.tmp")) == []


def test_successful_save_updates_current_path_and_clears_dirty_state(tmp_path):
    app = make_savable_app(tmp_path)
    target = tmp_path / "marks.csv"

    assert app._save_csv_to_path(str(target)) is True

    assert app.current_csv_path == str(target.absolute())
    assert app.is_dirty is False
    assert app.root.current_title == f"PicPicker - 比卡拾图 — {target.absolute()}"
    assert "图1备注" in target.read_text(encoding="gbk")


def test_failed_save_preserves_current_path_and_dirty_state(tmp_path, monkeypatch):
    app = make_savable_app(tmp_path)
    app.current_csv_path = str(tmp_path / "current.csv")
    errors = []
    monkeypatch.setattr(
        app,
        "_write_csv_atomically",
        lambda csv_path, csv_data: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, message: errors.append(message))

    assert app._save_csv_to_path(str(tmp_path / "new.csv")) is False

    assert app.current_csv_path == str(tmp_path / "current.csv")
    assert app.is_dirty is True
    assert errors == ["保存CSV文件失败：\ndisk full"]

