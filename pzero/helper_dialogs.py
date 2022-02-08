"""helper_dialogs.py
PZero© Andrea Bistacchi"""

from PyQt5.QtWidgets import QMessageBox, QInputDialog, QLineEdit, QPushButton, QFileDialog, QWidget, QProgressDialog, QMainWindow,QComboBox
from PyQt5 import QtWidgets, QtCore, Qt

from .import_window_ui import Ui_ImportOptionsWindow
from .assign_ui import Ui_AssignWindow
import pandas as pd
import laspy as lp
import os
import numpy as np
from .pc2vtk import pc2vtk


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

class PCDataModel(QtCore.QAbstractTableModel):

    '''[Gabriele]  Abstract table model that can be used to quickly display imported pc files data  from a pandas df. Taken from this stack overflow post https://stackoverflow.com/questions/31475965/fastest-way-to-populate-qtableview-from-pandas-data-frame
    '''
    def __init__(self, data, start_col,end_col,start_row,end_row, parent=None,*args, **kwargs):
        super(PCDataModel,self).__init__(*args, **kwargs)


        self.limit = 100

        if end_row == -1:
            self.data = data.iloc[start_row:start_row+100, start_col:end_col] # [Gabriele] limit the preview data if the number of points are grater than 100
            print(f'Number of points grater than {self.limit}, displaying the 100 rows below the start row')
        else:
            self.data = data.iloc[start_row:end_row, start_col:end_col]

    def columnCount(self, parent=None): # [Gabriele] the n of columns is = to the number of columns of the input data set (.shape[1])
        return self.data.shape[1]

    def rowCount(self, parent=None): # [Gabriele] the n of rows is = to the number of rows of the input data set (.shape[0])
        return self.data.shape[0]
    '''[Gabriele]  Populate the table with data depending on how much of the table is shown. The model has different indexes with different roles, DisplayRole has index 0.'''

    def data(self, index, role: QtCore.Qt.DisplayRole):
        # print(index.column())
        if index.isValid():
            if role == QtCore.Qt.DisplayRole:
                return str(self.data.iloc[index.row(), index.column()])
        return None

    '''[Gabriele] Set header and index If the "container" is horizontal (orientation index 1) and has a display role (index 0) (-> is the header of the table). If the "container" is vertical (orientation index 2) and has a display role (index 0) (-> is the index of the table).'''

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return str(self.data.columns[col]) # [Gabriele] Set the header names
        if orientation == QtCore.Qt.Vertical and role == QtCore.Qt.DisplayRole:
            return self.data.index[col] # [Gabriele] Set the indexes
        return None


class import_dialog(QMainWindow, Ui_ImportOptionsWindow):

    '''[Gabriele]  New window class used to display import options and data preview. To add a new import function (e.g. import_PC -> pc2vtk) append the function at the end of this class and add it to the import_func_dict with this template:
        NameOfActionMenu: self.import_func()
    '''

    '''[Gabriele]  Different options that can be changed in the import menu:
        + in_path -> input file path
        + StartColspinBox -> Start import from column number
        + EndColspinBox -> End import on column number
        + HeaderspinBox -> Row index with header dataset
        + StartRowspinBox -> Start import from row number
        + EndRowspinBox -> End import on row number
        + Separator -> Type of separtor in the data set'''


    import_options_dict = {
    'in_path':'',
    'StartColspinBox':0,
    'EndColspinBox':3,
    'HeaderspinBox':0,
    'StartRowspinBox':0,
    'EndRowspinBox':100,
    'SeparatorcomboBox':' '
    }

    '''[Gabriele]  Different types of separators.'''
    sep_dict= {
    '<space>': ' ',
    '<comma>': ',',
    '<semi-col>': ';',
    '<tab>':'   '
    }





    def __init__(self, parent=None, *args, **kwargs):

        super(import_dialog, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)
        # _____________________________________________________________________________
        # THE FOLLOWING ACTUALLY DELETES ANY REFERENCE TO CLOSED WINDOWS, HENCE FREEING
        # MEMORY, BUT CREATES PROBLEMS WITH SIGNALS THAT ARE STILL ACTIVE
        # SEE DISCUSSIONS ON QPointer AND WA_DeleteOnClose ON THE INTERNET
        # self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.import_func_dict = {
        'actionImportPC': self.import_PC
        }


        self.parent = parent
        self.action = self.sender() # [Gabriele] Name of the actionmenu from which the import function was called.
        self.assigned = False
        self.show_qt_canvas()


        '''[Gabriele]  Different types of signals depending on the field in the import options'''
        self.PathtoolButton.clicked.connect(self.import_file)

        self.StartColspinBox.valueChanged.connect(lambda: self.import_options(self.StartColspinBox.objectName(),self.StartColspinBox.value()))

        self.EndColspinBox.valueChanged.connect(lambda: self.import_options(self.EndColspinBox.objectName(),self.EndColspinBox.value()))

        self.HeaderspinBox.valueChanged.connect(lambda: self.import_options(self.HeaderspinBox.objectName(),self.HeaderspinBox.value()))

        self.StartRowspinBox.valueChanged.connect(lambda: self.import_options(self.StartRowspinBox.objectName(),self.StartRowspinBox.value()))

        self.EndRowspinBox.valueChanged.connect(lambda: self.import_options(self.EndRowspinBox.objectName(),self.EndRowspinBox.value()))

        ''' [Gabriele] The text separator value is confronted with the dict values and then assigned the correct symbol. <comma> --> ","'''

        self.SeparatorcomboBox.currentTextChanged.connect(lambda: self.import_options(self.SeparatorcomboBox.objectName(),self.sep_dict[self.SeparatorcomboBox.currentText()]))

        self.PreviewButton.clicked.connect(lambda: self.preview_file(self.input_data_df))

        self.assignDataButton.clicked.connect(lambda: assign_data(self))

        self.ConfirmBox.accepted.connect(self.import_func_dict[self.action.objectName()])
        self.ConfirmBox.rejected.connect(self.close)

    def closeEvent(self, event):

        """Override the standard closeEvent method since self.plotter.close() is needed to cleanly close the vtk plotter."""
        reply = QMessageBox.question(self, 'Closing window', 'Close this window?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            #self.quit()  # needed to cleanly close the vtk plotter
            event.accept()
        else:
            event.ignore()

    '''[Gabriele]  Single function that manages all of the above signals.'''
    def import_options(self,origin,value):
        self.import_options_dict[origin] = value

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()

    def import_file(self):

        self.import_options_dict['in_path'] = open_file_dialog(parent=self,caption='Import point cloud data',filter="All supported (*.txt *.csv *.xyz *.ply *.las *.laz);;Text files (*.txt *.csv *.xyz);;PLY files (*.ply);;LAS/LAZ files (*.las *.laz)")
        self.PathlineEdit.setText(self.import_options_dict['in_path'])

        try:

            _,extension = os.path.splitext(self.import_options_dict['in_path'])

            if extension == '.las' or extension == '.laz':
                self.input_data_df = self.las2df(self.import_options_dict['in_path'])

            else:

                self.input_data_df = pd.read_csv(self.import_options_dict['in_path'],
                                            sep=self.import_options_dict['SeparatorcomboBox'],
                                            header=self.import_options_dict['HeaderspinBox'])

        except ValueError:
            print('Could not preview: invalid column, row or separator')
        except FileNotFoundError:
            print('Could not preview: invalid file name')


    '''[Gabriele]  Function used to preview the data using the PCDataModel'''

    def preview_file(self,input_data_df):

        start_col = self.import_options_dict['StartColspinBox']
        end_col = self.import_options_dict['EndColspinBox']

        start_row = self.import_options_dict['StartRowspinBox']
        end_row = self.import_options_dict['EndRowspinBox']

        self.model = PCDataModel(self.input_data_df,start_col,end_col,start_row,end_row)
        self.dataView.setModel(self.model)

        '''[Gabriele]  When the endrow number is -1 -> use all rows (below the start row). Else use the range defined as start_row (skip_rows) and end_row - start_row (n_rows)'''


    def import_PC(self):
         # [Gabriele] import the data without the preview
        start_col = self.import_options_dict['StartColspinBox']
        end_col = self.import_options_dict['EndColspinBox']

        start_row = self.import_options_dict['StartRowspinBox']
        end_row = self.import_options_dict['EndRowspinBox']
        # print(self.input_data_df['r'])
        pc2vtk(self.import_options_dict['in_path'],self.input_data_df,start_col,end_col,start_row,end_row,self=self.parent)

    def las2df(self,in_path):
        las_data = lp.read(in_path)
        prop_dict = dict()
        for format in las_data.point_format.dimensions:
            if format.name == 'X' or format.name == 'Y' or format.name == 'Z':
                attr = format.name.lower()
                prop_dict[attr] = np.c_[getattr(las_data,attr)].flatten()
            else:
                prop_dict[format.name] = np.c_[getattr(las_data,format.name)].flatten()
        df = pd.DataFrame.from_dict(prop_dict)
        return df

class assign_data(QMainWindow, Ui_AssignWindow):

    def __init__(self, parent=None, *args, **kwargs):

        super(assign_data, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)

        self.parent = parent
        self.rename_df = {} # [Gabriele] Dict used to rename the columns of the df
        self.show_qt_canvas()
        self.ConfirmButton.rejected.connect(self.close)

        try:
            self.df = self.parent.input_data_df
            n_attr = self.parent.input_data_df.shape[1]
            col_names = list(self.parent.input_data_df.columns)

        except AttributeError:
            print('No data to assign')
            self.ConfirmButton.accepted.connect(self.close)
        else:
            self.AssignTable.setRowCount(n_attr)
            self.AssignTable.setColumnCount(2)
            self.AssignTable.setHorizontalHeaderLabels(['Column name','Attributes'])
            self.ConfirmButton.accepted.connect(self.modify_df)

            for i in range(n_attr):
                self.AttrcomboBox = QtWidgets.QComboBox(self)
                self.AttrcomboBox.setObjectName(f'AttrcomboBox{i}')
                self.AttrcomboBox.setEditable(False)
                self.AttrcomboBox.addItems(['N.A.','x','y','z','r','g','b'])
                self.AttrcomboBox.SelectedIndex = 0
                self.AttrcomboBox.currentTextChanged.connect(lambda: self.ass_value())
                self.ColnameItem = QtWidgets.QTableWidgetItem()
                self.ColnameItem.setText(str(col_names[i]))
                self.AssignTable.setItem(i,0,self.ColnameItem)
                self.AssignTable.setCellWidget(i,1,self.AttrcomboBox)


    def ass_value(self):
        '''[Gabriele] Get column and row of clicked widget in table '''
        clicked = QtWidgets.QApplication.focusWidget().pos()
        index = self.AssignTable.indexAt(clicked)
        col = index.column()
        row = index.row()
        sel_combo = self.AssignTable.cellWidget(row,col) # [Gabriele] Combobox @ row and column
        '''[Gabriele] Use a dict to rename the columns. The keys are the original column names while the values are the new names'''
        self.rename_df[self.df.columns[row]] = sel_combo.currentText()
        self.df = self.parent.input_data_df.rename(columns=self.rename_df)

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()

    def modify_df(self):
        self.parent.input_data_df = self.df # [Gabriele] Update the data in memory
        self.close()
