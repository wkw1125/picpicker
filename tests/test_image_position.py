from picpicker.gui import PicPickerApp


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def make_app(position):
    app = PicPickerApp.__new__(PicPickerApp)
    app.image_position_var = FakeVar(position)
    return app


def test_image_position_anchor_mapping():
    assert make_app("头部")._get_preview_image_anchor() == "nw"
    assert make_app("居中")._get_preview_image_anchor() == "center"
    assert make_app("尾部")._get_preview_image_anchor() == "se"


def test_horizontal_letterbox_offsets_follow_image_position():
    dimensions = (300, 200, 100, 200)

    assert make_app("头部")._get_preview_image_offsets(*dimensions) == (0, 0)
    assert make_app("居中")._get_preview_image_offsets(*dimensions) == (100, 0)
    assert make_app("尾部")._get_preview_image_offsets(*dimensions) == (200, 0)


def test_vertical_letterbox_offsets_follow_image_position():
    dimensions = (300, 300, 300, 100)

    assert make_app("头部")._get_preview_image_offsets(*dimensions) == (0, 0)
    assert make_app("居中")._get_preview_image_offsets(*dimensions) == (0, 100)
    assert make_app("尾部")._get_preview_image_offsets(*dimensions) == (0, 200)
