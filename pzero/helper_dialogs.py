"""helper_dialogs.py
PZero© Andrea Bistacchi"""

from qtpy.QtWidgets import QMessageBox, QInputDialog, QLineEdit, QPushButton, QFileDialog, QWidget, QProgressDialog
from qtpy import QtWidgets, QtCore


def options_dialog(title=None, message=None, yes_role=None, no_role=None, reject_role=None):
    """Generic message box with title, message, and three buttons.
    Returns 0, 1, or 2 (int) for the 1st, 2nd and 3rd button.
    If reject_role is None, the third button is not visualized."""
    msg_box = QMessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.addButton(QPushButton(yes_role), QMessageBox.YesRole)
    msg_box.addButton(QPushButton(no_role), QMessageBox.NoRole)
    if reject_role:
        msg_box.addButton(QPushButton(reject_role), QMessageBox.RejectRole)
    output = msg_box.exec()
    return output


def input_text_dialog(parent=None, title="title", label="label", default_text="text"):
    """Open a dialog and input a STRING.
    If the dialog is closed without OK or without a valid text, it returns None."""
    in_text, ok = QInputDialog.getText(parent, title, label, QLineEdit.Normal, default_text)
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


def input_one_value_dialog(parent=None, title="title", label="label", default_value=0.0):
    """Open a dialog and input a DOUBLE.
    If the dialog is closed without OK or without a valid value, it returns None."""
    default_value = str(default_value)
    in_value = input_text_dialog(parent=parent, title=title, label=label, default_text=default_value)
    if in_value:
        in_value = float(in_value)
        return in_value
    else:
        return


def open_file_dialog(parent=None, caption=None, filter=None):
    """Open a dialog and input a file or folder name.
    If the dialog is closed without a valid file name, it returns None."""
    in_file_name = QFileDialog.getOpenFileName(parent=parent, caption=caption, filter=filter)
    in_file_name = in_file_name[0]
    return in_file_name


def save_file_dialog(parent=None, caption=None, filter=None):
    """Open a dialog and input a file or folder name.
    If the dialog is closed without a valid file name, it returns None."""
    out_file_name = QFileDialog.getSaveFileName(parent=parent, caption=caption, filter=filter)
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


def multiple_input_dialog(title="title", input_dict=None):
    """Generic widget for input of several variables. It takes as input:
    1) title of the widget
    2) a dictionary of the form -->
        dict = {'key_0': ['label_0', 'default_value_0'],
                'key_1': ['label_1', ['default_value_1.0', 'default_value_1.1', 'default_value_1.2']],
                'key_2': ['label_2', 'default_value_2']}
        The values can be either strings, doubles, integers, or lists. In case of lists a combo box is used for input.
    Based on the length of dict, the widget builds the right number of QLineEdits and QComboBoxes.
    Two additional QPushButton are generated: Cancel to exit the widget, and OK to get the input values and pass them to the main code in a dictionary."""
    """Create the widget and set size and title."""
    widget = QWidget()
    widget.resize(len(input_dict) * 100, len(input_dict))
    widget.setWindowTitle(title)
    """Define a grid layout."""
    gridLayout = QtWidgets.QGridLayout(widget)
    objects_qt = {}
    i = 0
    """FOR loop that builds labels and boxes according to the input_dict."""
    for key in input_dict:
        """Create dynamic variables."""
        objects_qt[key] = [None, None]
        """Create QLabels, assign them to the grid layout, and set the text."""
        objects_qt[key][0] = QtWidgets.QLabel(widget)
        objects_qt[key][0].setText(input_dict[key][0])
        gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
        """Create QLineEdits and QComboBoxes."""
        if isinstance(input_dict[key][1], list):
            objects_qt[key][1] = QtWidgets.QComboBox(widget)
            objects_qt[key][1].addItems(input_dict[key][1])
            objects_qt[key][1].setEditable(True)
        elif isinstance(input_dict[key][1], int):
            objects_qt[key][1] = QtWidgets.QLineEdit(widget)
            objects_qt[key][1].setText(str(input_dict[key][1]))
        elif isinstance(input_dict[key][1], float):
            objects_qt[key][1] = QtWidgets.QLineEdit(widget)
            objects_qt[key][1].setText(str(input_dict[key][1]))
        # elif isinstance(input_dict[key][1], int):
        #     objects_qt[key][1] = QtWidgets.QSpinBox(widget)
        #     objects_qt[key][1].setValue(input_dict[key][1])
        #     objects_qt[key][1].setMinimum(-(np.inf))
        #     objects_qt[key][1].setMaximum(np.inf)
        # elif isinstance(input_dict[key][1], float):
        #     objects_qt[key][1] = QtWidgets.QDoubleSpinBox(widget)
        #     objects_qt[key][1].setValue(input_dict[key][1])
        #     objects_qt[key][1].setMinimum(-(np.inf))
        #     objects_qt[key][1].setMaximum(np.inf)
        else:
            objects_qt[key][1] = QtWidgets.QLineEdit(widget)
            objects_qt[key][1].setText(input_dict[key][1])
        gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
        i += 1
    """Create OK Button, add it to the grid layout an set name and state."""
    button_ok = QtWidgets.QPushButton(widget)
    gridLayout.addWidget(button_ok, i + 2, 1)
    button_ok.setAutoDefault(True)
    button_ok.setText("OK")
    """Cancel Button, add it to the grid layout an set name and state."""
    button_cancel = QtWidgets.QPushButton(widget)
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
    loop = QtCore.QEventLoop()  # Create a QEventLoop necessary to stop the main loop
    button_ok.clicked.connect(loop.quit)  # Response to clicking the Collect PushButton. End the QEventLoop
    button_cancel.clicked.connect(cancel_option)  # Set the first QLineEdit empty - useful for an IF
    button_cancel.clicked.connect(loop.quit)  # Response to clicking the Cancel PushButton. End the QEventLoop
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
    gridLayout = QtWidgets.QGridLayout(widget)
    objects_qt = {}
    i = 0
    """Insert QLabel to explain the reason of the choice"""
    label_line = QtWidgets.QLabel(widget)
    label_line.setText(label)
    gridLayout.addWidget(label_line, 1, 1)
    """FOR loop that builds checkboxes according to the choice_list"""
    for element in choice_list:
        """Create dynamic variables."""
        objects_qt[element] = [None, None]
        """Create QCheckBoxes."""
        objects_qt[element][0] = QtWidgets.QCheckBox(widget)
        objects_qt[element][0].setText(element) # set text for the checkbox
        gridLayout.addWidget(objects_qt[element][0], i + 2, 1)
        i += 1
    """Create OK Button, add it to the grid layout an set name and state"""
    button_ok = QtWidgets.QPushButton(widget)
    gridLayout.addWidget(button_ok, i + 3, 1)
    button_ok.setAutoDefault(True)
    button_ok.setText("OK")
    """Cancel Button, add it to the grid layout an set name and state"""
    button_cancel = QtWidgets.QPushButton(widget)
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
    loop = QtCore.QEventLoop()  # Create a QEventLoop necessary to stop the main loop
    button_ok.clicked.connect(loop.quit)  # Response to clicking the Collect PushButton. End the QEventLoop
    button_cancel.clicked.connect(cancel_option)  # Clear the widget
    button_cancel.clicked.connect(loop.quit)  # Response to clicking the Cancel PushButton. End the QEventLoop
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
    The dialog can handle: QLabel, QComboBox, QLineEdit, QCheckBox --- and even more in the future."""
    """Create the widget and set size and title."""
    widget = QWidget()
    # widget.resize(len(input_dict) * 100, len(input_dict))
    widget.setWindowTitle(title)
    """Define a grid layout."""
    gridLayout = QtWidgets.QGridLayout(widget)
    objects_qt = {}
    i = 0
    """FOR loop that builds labels and boxes according to the input_dict."""
    for key in input_dict:
        """Create dynamic variables."""
        objects_qt[key] = [None, None]
        if input_dict[key][2] == "QLabel":
            """Create QLabels, assign them to the grid layout, and set the text."""
            objects_qt[key][0] = QtWidgets.QLabel(widget)
            objects_qt[key][0].setText(input_dict[key][1]) # use second column to set the label
            gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
        elif input_dict[key][2] == "QLineEdit":
            if isinstance(input_dict[key][1], int):
                """Create QLabels, assign them to the grid layout, and set the text."""
                objects_qt[key][0] = QtWidgets.QLabel(widget)
                objects_qt[key][0].setText(input_dict[key][0])
                gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
                """Create QLineEdit"""
                objects_qt[key][1] = QtWidgets.QLineEdit(widget)
                objects_qt[key][1].setText(str(input_dict[key][1]))
                gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
            elif isinstance(input_dict[key][1], float):
                """Create QLabels, assign them to the grid layout, and set the text."""
                objects_qt[key][0] = QtWidgets.QLabel(widget)
                objects_qt[key][0].setText(input_dict[key][0])
                gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
                """Create QLineEdit"""
                objects_qt[key][1] = QtWidgets.QLineEdit(widget)
                objects_qt[key][1].setText(str(input_dict[key][1]))
                gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
            else:
                """Create QLabels, assign them to the grid layout, and set the text."""
                objects_qt[key][0] = QtWidgets.QLabel(widget)
                objects_qt[key][0].setText(input_dict[key][0])
                gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
                """Create QLineEdit"""
                objects_qt[key][1] = QtWidgets.QLineEdit(widget)
                objects_qt[key][1].setText(input_dict[key][1])
                gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
        elif input_dict[key][2] == "QComboBox":
            """Create QLabels, assign them to the grid layout, and set the text."""
            objects_qt[key][0] = QtWidgets.QLabel(widget)
            objects_qt[key][0].setText(input_dict[key][0])
            gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
            """Create QComboBox"""
            objects_qt[key][1] = QtWidgets.QComboBox(widget)
            objects_qt[key][1].addItems(input_dict[key][1])
            objects_qt[key][1].setEditable(True)
            gridLayout.addWidget(objects_qt[key][1], i + 1, 2)
        elif input_dict[key][2] == "QCheckBox":
            objects_qt[key][0] = QtWidgets.QCheckBox(widget)
            objects_qt[key][0].setText(input_dict[key][1]) # use second column to set the label
            gridLayout.addWidget(objects_qt[key][0], i + 1, 1)
        elif input_dict[key][2] == "QSpinBox":
            """---- to be implemented ----"""
            pass
        i += 1
    """Create OK Button, add it to the grid layout an set name and state."""
    button_ok = QtWidgets.QPushButton(widget)
    gridLayout.addWidget(button_ok, i + 2, 1)
    button_ok.setAutoDefault(True)
    button_ok.setText("OK")
    """Cancel Button, add it to the grid layout an set name and state."""
    button_cancel = QtWidgets.QPushButton(widget)
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
    loop = QtCore.QEventLoop()  # Create a QEventLoop necessary to stop the main loop
    button_ok.clicked.connect(loop.quit)  # Response to clicking the Collect PushButton. End the QEventLoop
    button_cancel.clicked.connect(cancel_option)  # Set the first QLineEdit empty - useful for an IF
    button_cancel.clicked.connect(loop.quit)  # Response to clicking the Cancel PushButton. End the QEventLoop
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
    https://stackoverflow.com/questions/5849800/what-is-the-python-equivalent-of-matlabs-tic-and-toc-functions"""
    import time
    global startTime_for_tictoc
    startTime_for_tictoc = time.time()
    print("Tic...")


def toc():
    import time
    if 'startTime_for_tictoc' in globals():
        print("...Toc: Elapsed time [s]: " + str(time.time() - startTime_for_tictoc))
    else:
        print("Tic-Toc start time not set")


class progress_dialog(QProgressDialog):
    def __init__(self, max_value=None, title_txt=None, label_txt=None, cancel_txt=None, parent=None, *args, **kwargs):
        super(QProgressDialog, self).__init__(*args, **kwargs)
        self.parent = parent
        self.setWindowModality(QtCore.Qt.WindowModal)
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
        self.setValue(self.value()+1)

    @property
    def was_canceled(self):
        return self.wasCanceled()
