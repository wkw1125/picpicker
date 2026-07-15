from pathlib import Path

from picpicker.gui import PicPickerApp


def test_find_filename_matches_ignores_case_and_preserves_list_order():
    image_paths = [
        Path("/images/Holiday-One.JPG"),
        Path("/images/portrait.png"),
        Path("/images/my-HOLIDAY-photo.webp"),
    ]

    assert PicPickerApp._find_filename_matches(image_paths, "holiday") == [0, 2]
    assert PicPickerApp._find_filename_matches(image_paths, "HOLIDAY") == [0, 2]


def test_find_filename_matches_searches_filename_only():
    image_paths = [
        Path("/holiday/portrait.png"),
        Path("/images/holiday.png"),
    ]

    assert PicPickerApp._find_filename_matches(image_paths, "holiday") == [1]
    assert PicPickerApp._find_filename_matches(image_paths, "missing") == []


def test_find_filename_matches_respects_filtered_candidate_indices():
    image_paths = [
        Path("/images/holiday-one.jpg"),
        Path("/images/holiday-two.jpg"),
        Path("/images/holiday-three.jpg"),
    ]

    assert PicPickerApp._find_filename_matches(image_paths, "holiday", [2, 0]) == [2, 0]
    assert PicPickerApp._find_filename_matches(image_paths, "holiday", []) == []
