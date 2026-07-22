from picpicker.gui import PicPickerApp


class FakeRoot:
    def update_idletasks(self):
        pass

    def winfo_rootx(self):
        return 100

    def winfo_rooty(self):
        return 50

    def winfo_width(self):
        return 1200

    def winfo_height(self):
        return 800


class FakeDialog:
    def __init__(self):
        self.position = None

    def update_idletasks(self):
        pass

    def winfo_reqwidth(self):
        return 400

    def winfo_reqheight(self):
        return 200

    def winfo_screenwidth(self):
        return 1440

    def winfo_screenheight(self):
        return 900

    def geometry(self, value):
        self.position = value


class FakePreview:
    def winfo_rootx(self):
        return 500

    def winfo_rooty(self):
        return 100

    def winfo_width(self):
        return 300

    def winfo_height(self):
        return 600


def test_dialog_is_centered_on_application_window():
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()
    dialog = FakeDialog()

    app._center_dialog_on_root(dialog)

    assert dialog.position == "+500+350"


def test_note_dialog_is_centered_in_lower_part_of_its_preview():
    app = PicPickerApp.__new__(PicPickerApp)
    app.root = FakeRoot()
    app.preview_labels = [None, FakePreview(), FakePreview()]
    dialog = FakeDialog()

    app._position_note_dialog(dialog, 2)

    assert dialog.position == "+450+420"
