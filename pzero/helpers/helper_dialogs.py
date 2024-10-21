"""helper_dialogs.py
PZero© Andrea Bistacchi"""

from difflib import SequenceMatcher

from os import path as os_path

from PySide6.QtCore import QEventLoop, Qt, QAbstractTableModel
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QMessageBox,
    QInputDialog,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QWidget,
    QProgressDialog,
    QMainWindow,
    QComboBox,
    QGridLayout,
    QLabel,
    QCheckBox,
    QTableWidgetItem,
    QHeaderView,
    QApplication,
    QFormLayout,
)

from laspy import open as lp_open

from numpy import c_ as np_c_

from pandas import DataFrame as pd_DataFrame
from pandas import read_csv as pd_read_csv

from pyvistaqt import QtInteractor as pvQtInteractor

from pzero.ui.import_window_ui import Ui_ImportOptionsWindow
from pzero.ui.navigator_window_ui import Ui_NavWindow
from pzero.ui.preview_window_ui import Ui_PreviewWindow
from .helper_functions import auto_sep


def options_dialog(title=None, message=None, yes_role="Yes", no_role="No", reject_role=None):
    """Generic message box with title, message, and up to three buttons.
    Returns 0, 1, or 2 for the first, second, and third button, respectively.
    If reject_role is None, the third button is not displayed."""
    msg_box = QMessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(message)

    buttons = []
    if yes_role:
        yes_button = msg_box.addButton(yes_role, QMessageBox.YesRole)
        buttons.append(yes_button)
    if no_role:
        no_button = msg_box.addButton(no_role, QMessageBox.NoRole)
        buttons.append(no_button)
    if reject_role:
        reject_button = msg_box.addButton(reject_role, QMessageBox.RejectRole)
        buttons.append(reject_button)

    msg_box.exec()

    clicked_button = msg_box.clickedButton()
    try:
        index = buttons.index(clicked_button)
        return index
    except ValueError:
        return -1  # In case no button is matched



def input_text_dialog(parent=None, title="title", label="label", default_text="text"):
    """Open a dialog and input a STRING.
    If the dialog is closed without OK or without a valid text, it returns None."""
    in_text, ok = QInputDialog.getText(
        parent, title, label, QLineEdit.Normal, default_text
    )
    if ok and in_text:
        return in_text
    else:
        return


def input_combo_dialog(parent=None, title="title", label="label", choice_list=None):
    """Open a dialog and get a STRING from a combo box filled with values in choice_list.
    If the dialog is closed without OK or without a valid text, it returns None."""
    choice_tuple = tuple(choice_list)
    in_item, ok = QInputDialog.getItem(parent, title, label, choice_tuple, 0, False)
    if ok and in_item:
        return in_item
    else:
        return


def input_one_value_dialog(
    parent=None, title="title", label="label", default_value=0.0
):
    """Open a dialog and input a DOUBLE.
    If the dialog is closed without OK or without a valid value, it returns None."""
    default_value = str(default_value)
    in_value = input_text_dialog(
        parent=parent, title=title, label=label, default_text=default_value
    )
    if in_value:
        in_value = float(in_value)
        return in_value
    else:
        return


def open_file_dialog(parent=None, caption=None, filter=None, multiple=False):
    """Open a dialog and input a file or folder name.
    If the dialog is closed without a valid file name, it returns None."""
    if multiple:
        in_file_name = QFileDialog.getOpenFileNames(
            parent=parent, caption=caption, filter=filter
        )
        in_file_name = in_file_name[0]
    else:
        in_file_name = QFileDialog.getOpenFileName(
            parent=parent, caption=caption, filter=filter
        )
        in_file_name = in_file_name[0]
    return in_file_name


def open_files_dialog(parent=None, caption=None, filter=None):
    """Open a dialog one or more files, that are returned as a list of file names.
    If the dialog is closed without a valid file name, it returns None."""
    in_file_name = QFileDialog.getOpenFileNames(parent=parent, caption=caption, filter=filter)
    return in_file_name[0]


def save_file_dialog(parent=None, caption=None, filter=None, directory=False):
    """Open a dialog and input a file or folder name.
    If the dialog is closed without a valid file name, it returns None."""
    if directory:
        out_file_name = [
            QFileDialog.getExistingDirectory(parent=parent, caption=caption)
        ]
    else:
        out_file_name = QFileDialog.getSaveFileName(
            parent=parent, caption=caption, filter=filter
        )
    out_file_name = out_file_name[0]
    return out_file_name


def message_dialog(title=None, message=None):
    """Generic message box with title, message, and OK button.
    Returns nothing."""
    msg_box = QMessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    output = msg_box.exec()
    return


def multiple_input_dialog(title="title", input_dict=None, return_widget=False):
    """Generic widget for input of several variables.

    It takes as input:
        1) title of the widget
        2) a dictionary of the form -->
            dict = {'key_0': ['label_0', 'default_value_0'],
                    'key_1': ['label_1', ['default_value_1.0', 'default_value_1.1', 'default_value_1.2'],set_value],
                    'key_2': ['label_2', 'default_value_2']}
            The values can be either strings, doubles, integers, or lists. In case of lists a combo box is used for input.
    Based on the length of dict, the widget builds the right number of QLineEdits and QComboBoxes.
    Two additional QPushButton are generated: Cancel to exit the widget,
    and OK to get the input values and pass them to the main code in a dictionary.
    @param title:
    @param input_dict:
    @param return_widget:
    @return: widget (not always)"""

    # Create the widget and set size and title.
    widget = QWidget()
    widget.resize(len(input_dict) * 100, len(input_dict))
    widget.setWindowTitle(title)

    # Define a grid layout.
    gridLayout = QGridLayout(widget)
    objects_qt = {}
    i = 0
    # FOR loop that builds labels and boxes according to the input_dict.
    for key in input_dict:
        # Create dynamic variables.
        objects_qt[key] = [None, None]
        # Create QLabels, assign them to the grid layout, and set the text.
        objects_qt[key][0] = QLabel(widget)
        objects_qt[key][0].setText(input_dict[key][0])
        gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
        # Create QLineEdits and QComboBoxes.
        if isinstance(input_dict[key][1], list):
            objects_qt[key][1] = QComboBox(widget, objectName=f"par_{key}")
            if len(input_dict[key]) == 3:
                display_value = input_dict[key][2]
                index = input_dict[key][1].index(display_value)
            else:
                index = 0
            objects_qt[key][1].addItems(input_dict[key][1])
            objects_qt[key][1].setEditable(True)
            objects_qt[key][1].setCurrentIndex(index)
        elif isinstance(input_dict[key][1], bool):
            objects_qt[key][1] = QCheckBox(widget, objectName=f"par_{key}")
            # objects_qt[key][1].setText(str(input_dict[key][0]))
            objects_qt[key][1].setChecked(input_dict[key][1])
        elif isinstance(input_dict[key][1], int):
            objects_qt[key][1] = QLineEdit(widget, objectName=f"par_{key}")
            objects_qt[key][1].setText(str(input_dict[key][1]))
        elif isinstance(input_dict[key][1], float):
            objects_qt[key][1] = QLineEdit(widget, objectName=f"par_{key}")
            objects_qt[key][1].setText(str(input_dict[key][1]))
        # elif isinstance(input_dict[key][1], int):
        #     objects_qt[key][1] = QSpinBox(widget)
        #     objects_qt[key][1].setValue(input_dict[key][1])
        #     objects_qt[key][1].setMinimum(-(np_inf))
        #     objects_qt[key][1].setMaximum(np_inf)
        # elif isinstance(input_dict[key][1], float):
        #     objects_qt[key][1] = QDoubleSpinBox(widget)
        #     objects_qt[key][1].setValue(input_dict[key][1])
        #     objects_qt[key][1].setMinimum(-(np_inf))
        #     objects_qt[key][1].setMaximum(np_inf)
        else:
            objects_qt[key][1] = QLineEdit(widget)
            objects_qt[key][1].setText(input_dict[key][1])
        gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
        i += 1

    if not return_widget:
        """Create OK Button, add it to the grid layout an set name and state."""
        button_ok = QPushButton(widget)
        gridLayout.addWidget(button_ok, i + 2, 1)
        button_ok.setAutoDefault(True)
        button_ok.setText("OK")
        """Cancel Button, add it to the grid layout an set name and state."""
        button_cancel = QPushButton(widget)
        gridLayout.addWidget(button_cancel, i + 2, 2)
        button_cancel.setAutoDefault(True)
        button_cancel.setText("Cancel")
        """Show the widget."""
        widget.show()
    else:
        return widget

    def cancel_option():
        """Clear the objects_qt dictionary if Cancel button is clicked"""
        """This function has to be implemented before creating and calling the QEventLoop"""
        objects_qt.clear()
        return

    """A QEventLoop is created. Signals and connections are created. QEventLoop is executed. When button is clicked,
    the QEventLoop.quit() will be called to close the widget and the loop. Attention: it's not a linear path in the code"""
    loop = QEventLoop()  # Create a QEventLoop necessary to stop the main loop
    button_ok.clicked.connect(
        loop.quit
    )  # Response to clicking the Collect PushButton. End the QEventLoop
    button_cancel.clicked.connect(
        cancel_option
    )  # Set the first QLineEdit empty - useful for an IF
    button_cancel.clicked.connect(
        loop.quit
    )  # Response to clicking the Cancel PushButton. End the QEventLoop
    loop.exec_()  # Execute the QEventLoop

    """When the QEventLoop is closed, the typed text is collected"""
    if not objects_qt:
        """Return None if Cancel is pressed."""
        return
    else:
        output_dict = {}
        for key in input_dict:
            if isinstance(input_dict[key][1], list):
                output_dict[key] = objects_qt[key][1].currentText()
            elif isinstance(input_dict[key][1], int):
                try:
                    output_dict[key] = int(objects_qt[key][1].text())
                except:
                    print("ERROR -- input value of wrong type")
                    return
            elif isinstance(input_dict[key][1], float):
                try:
                    output_dict[key] = float(objects_qt[key][1].text())
                except:
                    print("ERROR -- input value of wrong type")
                    return
            else:
                output_dict[key] = objects_qt[key][1].text()
    return output_dict


def input_checkbox_dialog(title="title", label="label", choice_list=None):
    """Open a dialog with a text line explaining the widget, followed by a list of non-exclusive checkboxes."""
    widget = QWidget()
    widget.setWindowTitle(title)
    """Define a grid layout"""
    gridLayout = QGridLayout(widget)
    objects_qt = {}
    i = 0
    """Insert QLabel to explain the reason of the choice"""
    label_line = QLabel(widget)
    label_line.setText(label)
    gridLayout.addWidget(label_line, 1, 1)
    """FOR loop that builds checkboxes according to the choice_list"""
    for element in choice_list:
        """Create dynamic variables."""
        objects_qt[element] = [None, None]
        """Create QCheckBoxes."""
        objects_qt[element][0] = QCheckBox(widget)
        objects_qt[element][0].setText(element)  # set text for the checkbox
        gridLayout.addWidget(objects_qt[element][0], i + 2, 1)
        i += 1
    """Create OK Button, add it to the grid layout an set name and state"""
    button_ok = QPushButton(widget)
    gridLayout.addWidget(button_ok, i + 3, 1)
    button_ok.setAutoDefault(True)
    button_ok.setText("OK")
    """Cancel Button, add it to the grid layout an set name and state"""
    button_cancel = QPushButton(widget)
    gridLayout.addWidget(button_cancel, i + 3, 2)
    button_cancel.setAutoDefault(True)
    button_cancel.setText("Cancel")
    """Show the widget."""
    widget.show()

    def cancel_option():
        """Clear the objects_qt dictionary if Cancel button is clicked"""
        """This function has to be implemented before creating and calling the QEventLoop"""
        objects_qt.clear()
        return

    """A QEventLoop is created. Signals and connections are created. QEventLoop is executed. When button is clicked,
    the QEventLoop.quit() will be called to close the widget and the loop. Attention: it's not a linear path in the code"""
    loop = QEventLoop()  # Create a QEventLoop necessary to stop the main loop
    button_ok.clicked.connect(
        loop.quit
    )  # Response to clicking the Collect PushButton. End the QEventLoop
    button_cancel.clicked.connect(cancel_option)  # Clear the widget
    button_cancel.clicked.connect(
        loop.quit
    )  # Response to clicking the Cancel PushButton. End the QEventLoop
    loop.exec_()  # Execute the QEventLoop

    """When the QEventLoop is closed, the typed text is collected"""
    if not objects_qt:
        return
    else:
        output_dict = []
        for element in choice_list:
            if objects_qt[element][0].isChecked():
                output_dict.append(element)
    return output_dict


def general_input_dialog(title="title", input_dict=None):
    """Most general input dialog.

    Dictionary must have the form:
        eg: dict = {'key_0': ['label_0', 'message_to_show', 'QLabel'],
                'key_1': ['label_1', ['default_value_1.0', 'default_value_1.1', 'default_value_1.2'], 'QComboBox'],
                'key_2': ['label_2', 'default_value_2', 'QLineEdit'],
                'key_3': ['label_3', 'message_to_show', 'QCheckBox']}
    The dialog can handle: QLabel, QComboBox, QLineEdit, QCheckBox --- and even more in the future.
    """

    # Create the widget and set size and title.
    widget = QWidget()
    # widget.resize(len(input_dict) * 100, len(input_dict))
    widget.setWindowTitle(title)
    # Define a grid layout.
    gridLayout = QGridLayout(widget)
    objects_qt = {}
    i = 0

    """FOR loop that builds labels and boxes according to the input_dict."""
    for key in input_dict:
        """Create dynamic variables."""
        objects_qt[key] = [None, None]
        if input_dict[key][2] == "QLabel":
            """Create QLabels, assign them to the grid layout, and set the text."""
            objects_qt[key][0] = QLabel(widget)
            objects_qt[key][0].setText(
                input_dict[key][1]
            )  # use second column to set the label
            gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
        elif input_dict[key][2] == "QLineEdit":
            if isinstance(input_dict[key][1], int):
                """Create QLabels, assign them to the grid layout, and set the text."""
                objects_qt[key][0] = QLabel(widget)
                objects_qt[key][0].setText(input_dict[key][0])
                gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
                """Create QLineEdit"""
                objects_qt[key][1] = QLineEdit(widget)
                objects_qt[key][1].setText(str(input_dict[key][1]))
                gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
            elif isinstance(input_dict[key][1], float):
                """Create QLabels, assign them to the grid layout, and set the text."""
                objects_qt[key][0] = QLabel(widget)
                objects_qt[key][0].setText(input_dict[key][0])
                gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
                """Create QLineEdit"""
                objects_qt[key][1] = QLineEdit(widget)
                objects_qt[key][1].setText(str(input_dict[key][1]))
                gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
            else:
                """Create QLabels, assign them to the grid layout, and set the text."""
                objects_qt[key][0] = QLabel(widget)
                objects_qt[key][0].setText(input_dict[key][0])
                gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
                """Create QLineEdit"""
                objects_qt[key][1] = QLineEdit(widget)
                objects_qt[key][1].setText(input_dict[key][1])
                gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
        elif input_dict[key][2] == "QComboBox":
            """Create QLabels, assign them to the grid layout, and set the text."""
            objects_qt[key][0] = QLabel(widget)
            objects_qt[key][0].setText(input_dict[key][0])
            gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
            """Create QComboBox"""
            objects_qt[key][1] = QComboBox(widget)
            objects_qt[key][1].addItems(input_dict[key][1])
            objects_qt[key][1].setEditable(True)
            gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
        elif input_dict[key][2] == "QCheckBox":
            objects_qt[key][0] = QCheckBox(widget)
            objects_qt[key][0].setText(
                input_dict[key][1]
            )  # use second column to set the label
            gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
        elif input_dict[key][2] == "QSpinBox":
            """---- to be implemented ----"""
            return
        elif input_dict[key][2] == "QPushButton":
            # func = input_dict[key][3]
            objects_qt[key][0] = QPushButton(widget)
            objects_qt[key][0].setObjectName(input_dict[key][0])
            objects_qt[key][0].setText(input_dict[key][1])
            # objects_qt[key][0].clicked.connect(func)
            gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
        i += 1

    """Create OK Button, add it to the grid layout an set name and state."""
    button_ok = QPushButton(widget)
    gridLayout.addWidget(button_ok, i + 2, 1)
    button_ok.setAutoDefault(True)
    button_ok.setText("OK")
    """Cancel Button, add it to the grid layout an set name and state."""
    button_cancel = QPushButton(widget)
    gridLayout.addWidget(button_cancel, i + 2, 2)
    button_cancel.setAutoDefault(True)
    button_cancel.setText("Cancel")
    """Show the widget."""
    widget.show()

    def cancel_option():
        """Clear the objects_qt dictionary if Cancel button is clicked"""
        """This function has to be implemented before creating and calling the QEventLoop"""
        objects_qt.clear()
        return

    """A QEventLoop is created. Signals and connections are created. QEventLoop is executed. When button is clicked,
    the QEventLoop.quit() will be called to close the widget and the loop. Attention: it's not a linear path in the code"""
    loop = QEventLoop()  # Create a QEventLoop necessary to stop the main loop
    button_ok.clicked.connect(
        loop.quit
    )  # Response to clicking the Collect PushButton. End the QEventLoop
    button_cancel.clicked.connect(
        cancel_option
    )  # Set the first QLineEdit empty - useful for an IF
    button_cancel.clicked.connect(
        loop.quit
    )  # Response to clicking the Cancel PushButton. End the QEventLoop
    loop.exec_()  # Execute the QEventLoop

    """When the QEventLoop is closed, the typed text is collected"""
    if not objects_qt:
        """Return None if Cancel is pressed."""
        return
    else:
        output_dict = {}
        for key in input_dict:
            if input_dict[key][2] == "QLineEdit":
                if isinstance(input_dict[key][1], int):
                    try:
                        output_dict[key] = int(objects_qt[key][1].text())
                    except:
                        print("ERROR -- input value of wrong type")
                        return
                elif isinstance(input_dict[key][1], float):
                    try:
                        output_dict[key] = float(objects_qt[key][1].text())
                    except:
                        print("ERROR -- input value of wrong type")
                        return
                else:
                    output_dict[key] = objects_qt[key][1].text()
            elif input_dict[key][2] == "QComboBox":
                output_dict[key] = objects_qt[key][1].currentText()
            elif input_dict[key][2] == "QCheckBox":
                if objects_qt[key][0].isChecked():
                    output_dict[key] = "check"
                else:
                    output_dict[key] = "uncheck"
            elif input_dict[key][2] == "QSpinBox":
                """---- to be implemented ----"""
                pass
    return output_dict


def tic():
    """Homemade version of Matlab tic and toc functions inspired by
    https://stackoverflow.com/questions/5849800/what-is-the-python-equivalent-of-matlabs-tic-and-toc-functions
    """
    import time

    global startTime_for_tictoc
    startTime_for_tictoc = time.time()
    print("Tic...")


def toc():
    import time

    if "startTime_for_tictoc" in globals():
        print("...Toc: Elapsed time [s]: " + str(time.time() - startTime_for_tictoc))
    else:
        print("Tic-Toc start time not set")


class progress_dialog(QProgressDialog):
    def __init__(
        self,
        max_value=None,
        title_txt=None,
        label_txt=None,
        cancel_txt=None,
        parent=None,
        *args,
        **kwargs,
    ):
        super(progress_dialog, self).__init__(*args, **kwargs)
        self.parent = parent
        self.setWindowModality(Qt.WindowModal)
        self.setAutoReset(True)
        self.setAutoClose(True)
        self.setMinimumDuration(0)
        self.setMinimum(0)
        self.setRange(0, max_value)
        self.setWindowTitle(title_txt)
        self.setLabelText(label_txt)
        self.setCancelButtonText(cancel_txt)
        self.setMinimumWidth(600)
        self.forceShow()

    def add_one(self):
        self.setValue(self.value() + 1)

    @property
    def was_canceled(self):
        return self.wasCanceled()


class PCDataModel(QAbstractTableModel):
    """[Gabriele]  Abstract table model that can be used to quickly display imported pc files data  from a pandas df. Taken from this stack overflow post https://stackoverflow.com/questions/31475965/fastest-way-to-populate-qtableview-from-pandas-data-frame"""

    def __init__(self, data, index_list, parent=None, *args, **kwargs):
        super(PCDataModel, self).__init__(*args, **kwargs)

        self.data = data
        self.index_list = index_list

    def columnCount(
        self, parent=None
    ):  # [Gabriele] the n of columns is = to the number of columns of the input data set (.shape[1])
        return self.data.shape[1]

    def rowCount(
        self, parent=None
    ):  # [Gabriele] the n of rows is = to the number of rows of the input data set (.shape[0])
        return self.data.shape[0]

    def data(self, index, qt_role):
        # print(index.column())
        if index.isValid():
            if qt_role == Qt.DisplayRole:
                return str(
                    self.data.iloc[index.row(), index.column()]
                )  # if qt_role == Qt.BackgroundRole and index.column() in self.index_list:  # return QColor(Qt.green)
            if qt_role == Qt.BackgroundRole and index.column() in self.index_list:
                return QColor(Qt.green)  # [Gabriele] Set the color
        return None

    """[Gabriele] Set header and index If the "container" is horizontal (orientation index 1) and has a display qt_role (index 0) (-> is the header of the table). If the "container" is vertical (orientation index 2) and has a display qt_role (index 0) (-> is the index of the table)."""

    def headerData(self, col, orientation, qt_role):
        if orientation == Qt.Horizontal and qt_role == Qt.DisplayRole:
            return str(self.data.columns[col])  # [Gabriele] Set the header names
        if orientation == Qt.Vertical and qt_role == Qt.DisplayRole:
            return self.data.index[col]  # [Gabriele] Set the indexes
        return None


class import_dialog(QMainWindow, Ui_ImportOptionsWindow):
    """[Gabriele]  New window class used to display import options and data preview."""

    """[Gabriele]  Different options that can be changed in the import menu:
        + in_path -> input file path
        + StartColspinBox -> Start import from column number
        + EndColspinBox -> End import on column number
        + HeaderspinBox -> Row index with header dataset
        + StartRowspinBox -> Start import from row number
        + EndRowspinBox -> End import on row number
        + Separator -> Role of separtor in the data set"""

    import_options_dict = {
        "in_path": "",
        "StartRowspinBox": 0,
        "EndRowspinBox": 100,
        "SeparatorcomboBox": " ",
    }

    """[Gabriele]  Different types of separators. By writing not using the symbol as a display we can avoid possible confusion between similar separators (e.g tab and space)-> the separator is auto assigned with the auto_sep function"""
    sep_dict = {"<space>": " ", "<comma>": ",", "<semi-col>": ";", "<tab>": "   "}

    def __init__(
        self,
        parent=None,
        default_attr_list=None,
        ext_filter=None,
        caption=None,
        add_opt=None,
        multiple=False,
        *args,
        **kwargs,
    ):
        self.loop = QEventLoop()  # Create a QEventLoop necessary to stop the main loop
        super(import_dialog, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)

        self.parent = parent
        self.action = (
            self.sender()
        )  # [Gabriele] Name of the actionmenu from which the import function was called.
        self.default_attr_list = default_attr_list
        self.ext_filter = ext_filter
        self.caption = caption

        self.setWindowTitle(caption)
        """[Gabriele]  Different types of signals depending on the field in the import options"""
        self.PathtoolButton.clicked.connect(lambda: self.import_file(multiple=multiple))
        self.PathlineEdit.editingFinished.connect(
            lambda: self.import_file(path=self.PathlineEdit.text())
        )

        self.StartRowspinBox.valueChanged.connect(
            lambda: self.import_options(
                self.StartRowspinBox.objectName(), self.StartRowspinBox.value()
            )
        )

        self.EndRowspinBox.valueChanged.connect(
            lambda: self.import_options(
                self.EndRowspinBox.objectName(), self.EndRowspinBox.value()
            )
        )

        ''' [Gabriele] The text separator value is confronted with the dict values and then assigned the correct symbol. <comma> --> ","'''

        self.SeparatorcomboBox.currentTextChanged.connect(
            lambda: self.import_options(
                self.SeparatorcomboBox.objectName(),
                self.sep_dict[self.SeparatorcomboBox.currentText()],
            )
        )

        self.PreviewButton.clicked.connect(
            lambda: self.preview_file(self.input_data_df)
        )

        self.ConfirmBox.accepted.connect(lambda: self.export_data())
        self.ConfirmBox.rejected.connect(self.close)

        self.AssignTable.setColumnCount(3)
        self.AssignTable.setHorizontalHeaderLabels(
            ["Column name", "Property name", "Custom property name"]
        )
        self.AssignTable.setColumnWidth(1, 200)
        self.AssignTable.setColumnWidth(2, 300)

        if add_opt is not None:
            for i, opt in enumerate(add_opt):
                opt_name = opt[0]
                opt_label = opt[1]
                setattr(self, opt_name, QCheckBox(self.OptionsFrame))
                opt = getattr(self, opt_name)
                opt.setObjectName(opt_name)
                opt.setText(opt_label)
                self.formLayout.setWidget(3 + i, QFormLayout.FieldRole, opt)

        self.show_qt_canvas()

    def import_options(self, origin, value):
        """[Gabriele]  Single function that manages all of the signals by adding to the import_options_dict a key,value pair corresponding to the origin object name and the set value."""
        self.import_options_dict[origin] = value

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()
        self.loop.exec_()  # Execute the QEventLoop

    def import_file(self, path=None, multiple=False):
        """[Gabriele] Function used to read and preview a PC data file. The open_file_dialog function is used to obtain the file path. Once the file is chosen a different parser is used depending on the extension. Once the file is read the properties are autoassigned (where possible)"""
        if path == None:
            self.import_options_dict["in_path"] = open_file_dialog(
                parent=self,
                caption="Import point cloud data",
                filter=self.ext_filter,
                multiple=multiple,
            )
            if multiple:
                path = self.import_options_dict["in_path"][0]
                self.PathlineEdit.setText(
                    f"Multiple file chosen in {os_path.dirname(path)}"
                )
            else:
                path = self.import_options_dict["in_path"]
                self.PathlineEdit.setText(path)
        else:
            self.import_options_dict["in_path"] = path

        try:
            _, extension = os_path.splitext(path)

            if (
                extension == ".las" or extension == ".laz"
            ):  # this could be a problem with .las files (boreholes)
                self.input_data_df = self.las2df(path)

            elif extension == ".ply":
                self.input_data_df = self.ply2df(path)
            elif extension == ".ags":
                ...
            else:
                self.input_data_df = self.csv2df(path)

            """[Gabriele]  Auto-assign values using the difflib library (internal). If there is no match then the column is not imported (N.a.). In this step the rename_dict dictionary is compiled where:
            - the keys correspond to the column index of the input df
            - the items correspond to the matched attribute (match score >0.8).
            If there is no match, the item will correspond to the original input column name.

            This dict is then used in the assign_data menu window to fill the corresponding values in each comboBox.
            """

            col_names = list(self.input_data_df.columns)
            self.rename_dict = {}

            remove_char_dict = {
                "/": "",
                "\\": "",
                "?": "",
                "!": "",
                "-": "",
                "_": "",
            }  # [Gabriele] Forbidden characters that are removed from the names using the translate function

            for i, attr in enumerate(col_names):
                table = attr.maketrans(remove_char_dict)
                matches = [
                    SequenceMatcher(
                        None, attr.translate(table).lower(), string.lower()
                    ).ratio()
                    for string in self.default_attr_list
                ]
                match = max(matches)

                if match > 0.8:
                    index = matches.index(match)
                    self.rename_dict[i] = self.default_attr_list[index]
                else:
                    self.rename_dict[i] = "N.a."
            self.assign_data()  # [Gabriele] Open the assign data ui.
        except ValueError:
            print("Could not preview: invalid column, row or separator")
        except FileNotFoundError:
            print("Could not import: invalid file name")
            # [Gabriele] This clears the AssingTable and dataView table
            self.AssignTable.setRowCount(0)
            self.dataView.setModel(None)

    def preview_file(self, input_data_df):
        """[Gabriele]  Function used to preview the data using the PCDataModel. The column and row ranges are obtained to properly slice the preview table."""
        value_dict = {k: v for k, v in list(self.rename_dict.items()) if v != "N.a."}
        index_list = list(value_dict.keys())
        self.model = PCDataModel(self.input_data_df, index_list)
        self.dataView.setModel(self.model)

    def export_data(self):
        """[Gabriele]  Import the pc data in PZero. Here the information needed to read and properly import the whole file is prepared:
        - path: file path
        - row_range: range of needed rows
        - delimiter: delimiter type
        - clean_dict: sliced and without N.a. version of the raw rename_dict
        - col_names: names of the column that will be used to set the properties name in the vtk object (final header of the pandas df)
        - index_list: list of final column index used for the import. This is necessary since the header names can change depending on the file so it's better to point to an ubiquitous column index instead of a name.
        - x and y_pos: index position of the X and Y data column. Note that these columns are not always labeled as such in the raw imported df.
        - offset: offset quantity to recenter the point cloud.
        """

        path = self.import_options_dict["in_path"]

        start_row = self.import_options_dict["StartRowspinBox"]
        end_row = self.import_options_dict["EndRowspinBox"]

        row_range = range(start_row, end_row)

        delimiter = self.import_options_dict["SeparatorcomboBox"]

        clean_dict = {k: v for k, v in list(self.rename_dict.items()) if v != "N.a."}
        col_names = list(clean_dict.values())
        index_list = list(clean_dict.keys())

        """ [Gabriele] X and Y are not always called exactly like this and they can occupy other positions. The clean_dict is reverse searched (get the key using a given valdue) to obtain the index positions of the X Y columns in the raw df."""

        self.args = [path, col_names, row_range, index_list, delimiter, self]
        self.close()
        self.loop.quit()
        # [Gabriele] Would be more convinient to import from here. This way we can modify the import parameters without opening every time the dialog.
        # pc2vtk(in_file_name=path, col_names=col_names, row_range=row_range, usecols=index_list, delimiter=delimiter, offset=offset, self=self, header_row=0)

    def las2df(self, path):
        """[Gabriele]  LAS/LAZ file parser.
        Reads .las and .laz file using the laspy package. The whole file is read and then processed in a dict cycling through the dim_names list. The dict then is converted in a pandas dataframe using the from_dict function.
        --------------------------------------------------------
        Inputs:
        - .las/.laz file path

        Outputs:
        - pandas df

        avg run time of 0.0016 +- 0.0001 s for 50 lines
        --------------------------------------------------------
        """
        with lp_open(path) as f:
            for chunk in f.chunk_iterator(50):
                las_data = chunk
                break
        dim_names = las_data.point_format.dimension_names
        prop_dict = dict()
        for dim in dim_names:
            if dim == "X" or dim == "Y" or dim == "Z":
                attr = dim.lower()
                prop_dict[attr] = np_c_[las_data[attr]].flatten()
            else:
                prop_dict[dim] = np_c_[las_data[dim]].flatten()
        df = pd_DataFrame.from_dict(prop_dict)
        return df

    def csv2df(self, path):
        """[Gabriele]  csv file parser.
        It reads the specified csv file using pd_read_csv. Wrapped in a function so that it can be profiled.
        --------------------------------------------------------
        Inputs:
        - csv file path

        Outputs:
        - Pandas df

        avg run time of 0.0014+-0.0007 s for 50 lines
        --------------------------------------------------------

        """
        sep = auto_sep(path)
        self.SeparatorcomboBox.setCurrentIndex(list(self.sep_dict.values()).index(sep))
        df = pd_read_csv(path, sep=sep, nrows=50, engine="c", index_col=False)
        return df

    def ply2df(self, path):
        """[Gabriele]  PLY file parser.
        It reads the first header lines to search for properties such as XYZ, RGB etcetc. When the "end_header" line is reached the file is read as a normal .csv file and parsed with pandas.read_csv skipping the header lines.
        --------------------------------------------------------
        Inputs:
        - PLY file path

        Outputs:
        - Pandas df

        avg run time of 0.0017 +- 0.0005s for 50 lines.
        --------------------------------------------------------

        """
        header = []
        end_line = 0
        with open(path, "r") as f:
            for i, line in enumerate(f):
                if "property" in line:
                    header.append(line.split()[-1])
                elif "end_header" in line:
                    end_line = i
                    break
        df = pd_read_csv(
            path,
            skiprows=end_line + 1,
            delimiter=" ",
            names=header,
            engine="c",
            index_col=False,
            nrows=50,
        )
        return df

    def assign_data(self):
        df = self.input_data_df
        col_names = list(df.columns)
        LineList = []

        self.AssignTable.setRowCount(len(col_names))

        for i, col in enumerate(col_names):
            """[Gabriele]  To create the assign menu we cicle through the column names and assign the comboBox text to the corresponding rename_dict item if the item is contained in the default_attr_list"""
            self.ColnameItem = QTableWidgetItem()
            self.ColnameItem.setText(str(col_names[i]))
            self.AttrcomboBox = QComboBox(self)
            self.AttrcomboBox.setObjectName(f"AttrcomboBox_{i}")
            self.AttrcomboBox.setEditable(False)
            self.AttrcomboBox.addItems(self.default_attr_list)
            self.AttrcomboBox.activated.connect(lambda: ass_value(self.AttrcomboBox))
            self.ScalarnameLine = QLineEdit()
            self.ScalarnameLine.setObjectName(f"ScalarnameLine_{i}")
            self.ScalarnameLine.setEnabled(False)
            self.ScalarnameLine.returnPressed.connect(lambda: ass_scalar())
            self.AssignTable.setItem(i, 0, self.ColnameItem)
            self.AssignTable.setCellWidget(i, 1, self.AttrcomboBox)
            self.AssignTable.setCellWidget(i, 2, self.ScalarnameLine)
            LineList.append(self.AssignTable.cellWidget(i, 2))

            if self.rename_dict[i] in self.default_attr_list:
                self.AssignTable.cellWidget(i, 1).setCurrentText(self.rename_dict[i])
            elif "user_" in self.rename_dict[i]:
                self.AssignTable.cellWidget(i, 1).setCurrentText("User defined")
                self.AssignTable.cellWidget(i, 2).setEnabled(True)
                self.AssignTable.cellWidget(i, 2).setText(self.rename_dict[i])

            else:
                self.AssignTable.cellWidget(i, 1).setCurrentText("As is")

            self.AssignTable.setCellWidget(i, 2, self.ScalarnameLine)
            self.AssignTable.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeToContents
            )

        # self.resize(750, 600) #[Gabriele] Set appropriate window size

        def ass_value(attr):
            """[Gabriele] Get column and row of clicked widget in table"""
            sel_combo = self.sender()  # [Gabriele] Combobox @ row and column
            row = int(sel_combo.objectName().split("_")[1])
            print(row)

            """[Gabriele] Use a dict to rename the columns. The keys are the column index of the original df while the values are the new names. """

            if sel_combo.currentText() == "User defined":
                self.AssignTable.cellWidget(row, 2).setEnabled(True)
                self.AssignTable.cellWidget(row, 2).setPlaceholderText("user_")

            elif sel_combo.currentText() == "As is":
                self.rename_dict[row] = df.columns[row]
                # self.AssignTable.cellWidget(row,2).clear()
                self.AssignTable.cellWidget(row, 2).setEnabled(False)
            else:
                items = list(self.rename_dict.values())
                self.AssignTable.cellWidget(row, 2).clear()
                self.AssignTable.cellWidget(row, 2).setEnabled(False)
                if (
                    sel_combo.currentText() in items
                    and sel_combo.currentText() != "N.a."
                ):
                    print("Item already assigned")
                else:
                    self.rename_dict[row] = sel_combo.currentText()
            self.preview_file(self.input_data_df)

        def ass_scalar():
            clicked = QApplication.focusWidget().pos()
            index = self.AssignTable.indexAt(clicked)
            col = index.column()
            row = index.row()
            """[Gabriele]  This is the only way to choose the QLineEdit otherwise self.AssignTable.cellWidget(row,2) returns somehow a QWidget instad than a QLineEdit"""
            sel_line = LineList[row]
            scal_name = f"user_{sel_line.text()}"
            self.rename_dict[row] = scal_name
            sel_line.setText(scal_name)
            self.preview_file(self.input_data_df)

    def close_ui(self):
        self.close()
        self.loop.quit()


class NavigatorWidget(QMainWindow, Ui_NavWindow):
    """Navigator widget prototype for Xsections. This widget can be used to
    change the different Xsections without opening a new window.

    FOR NOW IS INACTIVE.
    """

    def __init__(self, parent=None, val_list=None, start_idx=None, *args, **kwargs):
        self.loop = QEventLoop()  # Create a QEventLoop necessary to stop the main loop
        super(NavigatorWidget, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)

        self.parent = parent
        self.idx = start_idx
        self.value_list = val_list
        curr_obj = self.value_list[self.idx]

        self.ForwardButton.clicked.connect(self.forward)
        self.BackButton.clicked.connect(self.back)
        self.SectionLabel.setText(curr_obj)
        self.setWindowTitle("Section navigator")
        self.show_qt_canvas()

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()
        self.loop.exec_()  # Execute the QEventLoop

    def forward(self):
        self.idx += 1
        print(self.idx)
        if self.idx > len(self.value_list) - 1:
            self.idx = 0

        curr_obj = self.value_list[self.idx]
        self.SectionLabel.setText(curr_obj)
        return curr_obj

    def back(self):
        self.idx -= 1
        print(self.idx)
        if self.idx < 0:
            self.idx = len(self.value_list) - 1

        curr_obj = self.value_list[self.idx]
        self.SectionLabel.setText(curr_obj)
        return curr_obj


class PreviewWidget(QMainWindow, Ui_PreviewWindow):
    """Widget used to attach a pyvista plotter instance to a dialog (such as
    general input dialog). This can be useful to view the final object before
    applying the given function (e.g. resample, simplify ...).

    This widget takes:
    - parent
    - titles: Titles for the two views
    - mesh: the initial mesh
    - opt_widget: the widget resulting from the dialog (return_widget option see multiple_input_dialog)
    - function: function to apply to the mesh. For the function a mode argument (0 or 1) is set. if
    Mode is 1 the first mesh is returned to be plotted in the previewer. For mode 0 the filter
    is executed for all surfaces (the preview plotting is skipped).
    """

    def __init__(
        self,
        parent=None,
        titles=None,
        mesh=None,
        opt_widget=None,
        function=None,
        *args,
        **kwargs,
    ):
        self.loop = QEventLoop()  # Create a QEventLoop necessary to stop the main loop
        super(PreviewWidget, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)

        self.parent = parent
        self.previewButton.clicked.connect(self.plot)
        self.ConfirmButtonBox.rejected.connect(self.close)
        self.ConfirmButtonBox.accepted.connect(self.apply)
        self.function = function
        self.parameters = []
        if (mesh, titles, opt_widget):
            self.title1 = titles[0]
            self.title2 = titles[1]
            self.OptionsLayout.addWidget(opt_widget)
            for child in opt_widget.children():
                if child.objectName():
                    self.parameters.append(child)
            self.initialize_interactor()
        else:
            return

        self.show_qt_canvas()

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()
        self.loop.exec_()  # Execute the QEventLoop

    def closeEvent(self, event):
        self.preview_plotter.close()  # needed to cleanly close the vtk plotter
        event.accept()

    def initialize_interactor(self):
        """Add the pyvista interactor object to self.ViewFrameLayout ->
        the layout of an empty frame generated with Qt Designer"""
        self.preview_plotter = pvQtInteractor(self.PreviewVerticalFrame, shape=(1, 2))
        self.preview_plotter.set_background(
            "black"
        )  # background color - could be made interactive in the future
        self.PreviewLayout.addWidget(self.preview_plotter.interactor)
        uid = self.parent.selected_uids[0]
        self.mesh = self.parent.geol_coll.get_uid_vtk_obj(uid)

        self.preview_plotter.subplot(0, 0)
        self.preview_plotter.add_text(self.title1, font_size=10)
        self.preview_plotter.add_mesh(self.mesh, style="wireframe", color="y")
        self.preview_plotter.subplot(0, 1)
        self.preview_plotter.add_text(self.title2, font_size=10)
        # self.preview_plotter.add_mesh(self.decimated, style='wireframe', color='y')

        self.preview_plotter.link_views()
        # self.preview_plotter.show_axes_all()

    def plot(self):
        parameters = []

        for par in self.parameters:
            if isinstance(par, QLineEdit):
                parameters.append(par.text())
            elif isinstance(par, QComboBox):
                parameters.append(par.currentText())
            elif isinstance(par, QCheckBox):
                parameters.append(par.checkState())

        mod_mesh = self.function(self.parent, 1, *parameters)
        self.preview_plotter.clear()
        self.preview_plotter.subplot(0, 0)
        self.preview_plotter.add_text(self.title1, font_size=10)
        self.preview_plotter.add_mesh(self.mesh, style="wireframe", color="y")
        self.preview_plotter.subplot(0, 1)
        self.preview_plotter.add_text(self.title2, font_size=10)
        self.preview_plotter.add_mesh(mod_mesh, style="wireframe", color="y")

    def apply(self):
        parameters = []

        for par in self.parameters:
            if isinstance(par, QLineEdit):
                parameters.append(par.text())
            elif isinstance(par, QComboBox):
                parameters.append(par.currentText())
            elif isinstance(par, QCheckBox):
                parameters.append(par.checkState())

        mod_mesh = self.function(self.parent, 0, *parameters)
        self.close()
