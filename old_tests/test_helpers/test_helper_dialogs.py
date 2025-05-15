from pzero.helpers.helper_dialogs import progress_dialog
import pytest

"""
def test_option_dialogs(self, qtbot):
    title = "test_dialog"
    message = "this is a test message"
    res = options_dialog(title=title, message=message, yes_role="yes", no_role="no")

    qtbot.mouseClick()

    # if pressed no res == 1, otherwise res == 0
    assert res == 1
"""


# Testing the class progress_dialog()
class TestProgressDialog:

    # testing if the initial dialog values are correct
    @pytest.fixture
    def test_init_dialog(self, qtbot):
        max_value = 1
        title = "Title_test"
        label = "Saving test"

        progress_dialog_instance = progress_dialog(
            max_value=max_value,
            title_txt=title,
            label_txt=label,
            cancel_txt=None,
            parent=self,
        )

        assert (
            progress_dialog_instance.value() == -1
            and progress_dialog_instance.maximum() == max_value
            and progress_dialog_instance.windowTitle() == title
            and progress_dialog_instance.labelText() == label
        )

    # Testing the add_one function
    @pytest.fixture
    def test_add_one(self, qtbot):
        max_value = 5000
        title = "Title_test"
        label = "Saving test"

        progress_dialog_instance = progress_dialog(
            max_value=max_value,
            title_txt=title,
            label_txt=label,
            cancel_txt=None,
            parent=self,
        )

        for i in range(max_value):
            progress_dialog_instance.add_one()

        # we use max_value -1 because the value in the dialog starts with -1
        assert progress_dialog_instance.value() == max_value - 1

    # Testing was_canceled in the progress dialog
    @pytest.fixture
    def test_was_canceled(self, qtbot):
        max_value = 1
        title = "Title_test"
        label = "Saving test"
        cancel_button_text = "test delete me"

        progress_dialog_instance = progress_dialog(
            max_value=max_value,
            title_txt=title,
            label_txt=label,
            cancel_txt=cancel_button_text,
            parent=self,
        )

        assert progress_dialog_instance.wasCanceled() is False

    # Testing with calling the cancel button in the progress dialog
    @pytest.fixture
    def test_was_canceled_true(self, qtbot):
        max_value = 1
        title = "Title_test"
        label = "Saving test"
        cancel_button_text = "test delete me"

        progress_dialog_instance = progress_dialog(
            max_value=max_value,
            title_txt=title,
            label_txt=label,
            cancel_txt=cancel_button_text,
            parent=self,
        )
        progress_dialog_instance.cancel()

        assert progress_dialog_instance.wasCanceled() is True

    # Testing change in the dialog
    @pytest.fixture
    def test_change_dialog_label(self, qtbot):
        max_value = 5000
        title = "Title_test"
        label = "Saving test"
        change_label = "new_test_label"

        progress_dialog_instance = progress_dialog(
            max_value=max_value,
            title_txt=title,
            label_txt=label,
            cancel_txt=None,
            parent=self,
        )
        progress_dialog_instance.setLabelText(change_label)

        assert progress_dialog_instance.labelText() == change_label
