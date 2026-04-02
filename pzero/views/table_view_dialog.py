"""table_view_dialog.py
Simple dialog to manage user-defined editable tables."""

from pandas import DataFrame as pd_DataFrame
from pandas import isna as pd_isna

from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from pzero.helpers.helper_dialogs import input_text_dialog


class EditableDataFrameModel(QAbstractTableModel):
    """Expose a pandas dataframe as a simple editable Qt table model."""

    def __init__(self, dataframe=None, parent=None):
        super().__init__(parent)
        self._dataframe = dataframe if dataframe is not None else pd_DataFrame()

    @property
    def dataframe(self):
        return self._dataframe

    def set_dataframe(self, dataframe=None):
        self.beginResetModel()
        self._dataframe = dataframe if dataframe is not None else pd_DataFrame()
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent and parent.isValid() else self._dataframe.shape[0]

    def columnCount(self, parent=None):
        return 0 if parent and parent.isValid() else self._dataframe.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        value = self._dataframe.iloc[index.row(), index.column()]
        if pd_isna(value):
            return ""
        return str(value)

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False
        self._dataframe.iloc[index.row(), index.column()] = (
            "" if value is None else str(value)
        )
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return (
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsEditable
        )

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            try:
                return str(self._dataframe.columns[section])
            except Exception:
                return None
        return str(section + 1)

    def add_empty_row(self):
        row_data = {column: "" for column in self._dataframe.columns.tolist()}
        self.beginResetModel()
        self._dataframe.loc[len(self._dataframe.index)] = row_data
        self.endResetModel()

    def remove_rows(self, row_indexes=None):
        if not row_indexes:
            return
        self.beginResetModel()
        self._dataframe.drop(index=row_indexes, inplace=True)
        self._dataframe.reset_index(drop=True, inplace=True)
        self.endResetModel()

    def add_column(self, column_name: str):
        self.beginResetModel()
        self._dataframe[column_name] = ""
        self.endResetModel()

    def remove_column(self, column_name: str):
        self.beginResetModel()
        self._dataframe.drop(columns=[column_name], inplace=True)
        self.endResetModel()


class NewTableDialog(QDialog):
    """Dialog used to create a new custom table and its initial fields."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Table")
        self.resize(420, 360)

        layout = QVBoxLayout(self)

        name_label = QLabel("Table name")
        self.table_name_edit = QLineEdit()
        self.table_name_edit.setPlaceholderText("table_name")
        layout.addWidget(name_label)
        layout.addWidget(self.table_name_edit)

        fields_label = QLabel("Attribute fields")
        layout.addWidget(fields_label)

        field_row = QHBoxLayout()
        self.field_name_edit = QLineEdit()
        self.field_name_edit.setPlaceholderText("field_name")
        add_field_button = QPushButton("Add field")
        add_field_button.clicked.connect(self.add_field)
        field_row.addWidget(self.field_name_edit)
        field_row.addWidget(add_field_button)
        layout.addLayout(field_row)

        self.fields_list = QListWidget()
        layout.addWidget(self.fields_list)

        remove_field_button = QPushButton("Remove selected field")
        remove_field_button.clicked.connect(self.remove_selected_field)
        layout.addWidget(remove_field_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def table_name(self) -> str:
        return self.table_name_edit.text().strip()

    @property
    def field_names(self) -> list:
        return [
            self.fields_list.item(index).text().strip()
            for index in range(self.fields_list.count())
        ]

    def add_field(self):
        field_name = self.field_name_edit.text().strip()
        if not field_name:
            return
        if field_name in self.field_names:
            QMessageBox.warning(
                self,
                "Duplicate field",
                f'The field "{field_name}" already exists.',
            )
            return
        self.fields_list.addItem(field_name)
        self.field_name_edit.clear()
        self.field_name_edit.setFocus()

    def remove_selected_field(self):
        current_row = self.fields_list.currentRow()
        if current_row >= 0:
            self.fields_list.takeItem(current_row)

    def validate_and_accept(self):
        if not self.table_name:
            QMessageBox.warning(self, "Missing name", "Insert a table name.")
            return
        self.accept()


class TableViewDialog(QDialog):
    """Dialog that lists and edits user-defined project tables."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Table View")
        self.resize(980, 620)
        self.setModal(False)

        main_layout = QHBoxLayout(self)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Existing tables"))
        self.tables_list = QListWidget()
        self.tables_list.currentItemChanged.connect(self.on_table_selection_changed)
        left_layout.addWidget(self.tables_list)

        new_table_button = QPushButton("New table")
        new_table_button.clicked.connect(self.create_table)
        left_layout.addWidget(new_table_button)

        delete_table_button = QPushButton("Delete table")
        delete_table_button.clicked.connect(self.delete_current_table)
        left_layout.addWidget(delete_table_button)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        self.current_table_label = QLabel("No table selected")
        right_layout.addWidget(self.current_table_label)

        toolbar_layout = QHBoxLayout()
        add_row_button = QPushButton("Add row")
        add_row_button.clicked.connect(self.add_row)
        delete_row_button = QPushButton("Delete row")
        delete_row_button.clicked.connect(self.delete_selected_rows)
        add_field_button = QPushButton("Add field")
        add_field_button.clicked.connect(self.add_field)
        delete_field_button = QPushButton("Delete field")
        delete_field_button.clicked.connect(self.delete_field)
        toolbar_layout.addWidget(add_row_button)
        toolbar_layout.addWidget(delete_row_button)
        toolbar_layout.addWidget(add_field_button)
        toolbar_layout.addWidget(delete_field_button)
        right_layout.addLayout(toolbar_layout)

        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table_model = EditableDataFrameModel(parent=self)
        self.table_view.setModel(self.table_model)
        right_layout.addWidget(self.table_view)

        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 3)

        self.refresh_table_list()

    def showEvent(self, event):
        self.refresh_table_list(select_name=self.current_table_name)
        super().showEvent(event)

    @property
    def current_table_name(self):
        current_item = self.tables_list.currentItem()
        return current_item.text() if current_item else None

    def refresh_table_list(self, select_name: str = None):
        current_name = select_name or self.current_table_name
        self.tables_list.blockSignals(True)
        self.tables_list.clear()
        for table_name in self.parent.custom_tables.keys():
            self.tables_list.addItem(QListWidgetItem(table_name))
        self.tables_list.blockSignals(False)

        if self.tables_list.count() == 0:
            self.table_model.set_dataframe(pd_DataFrame())
            self.current_table_label.setText("No table selected")
            return

        if not current_name or current_name not in self.parent.custom_tables:
            current_name = next(iter(self.parent.custom_tables.keys()))

        matching_items = self.tables_list.findItems(current_name, Qt.MatchExactly)
        if matching_items:
            self.tables_list.setCurrentItem(matching_items[0])
            self.on_table_selection_changed(matching_items[0], None)

    def on_table_selection_changed(self, current, previous):
        del previous
        if current is None:
            self.table_model.set_dataframe(pd_DataFrame())
            self.current_table_label.setText("No table selected")
            return

        table_name = current.text()
        dataframe = self.parent.custom_tables.get(table_name, pd_DataFrame())
        self.table_model.set_dataframe(dataframe)
        self.current_table_label.setText(f"Table: {table_name}")

    def create_table(self):
        dialog = NewTableDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        table_name = dialog.table_name
        if table_name in self.parent.custom_tables:
            QMessageBox.warning(
                self,
                "Duplicate table",
                f'The table "{table_name}" already exists.',
            )
            return

        self.parent.custom_tables[table_name] = pd_DataFrame(columns=dialog.field_names)
        self.refresh_table_list(select_name=table_name)

    def delete_current_table(self):
        table_name = self.current_table_name
        if not table_name:
            return

        confirm = QMessageBox.question(
            self,
            "Delete table",
            f'Delete table "{table_name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.parent.custom_tables.pop(table_name, None)
        self.refresh_table_list()

    def add_row(self):
        table_name = self.current_table_name
        if not table_name:
            QMessageBox.information(
                self,
                "No table",
                "Create or select a table first.",
            )
            return
        if self.table_model.columnCount() == 0:
            QMessageBox.information(
                self,
                "No fields",
                "Add at least one field before inserting rows.",
            )
            return
        self.table_model.add_empty_row()

    def delete_selected_rows(self):
        table_name = self.current_table_name
        if not table_name:
            return

        selection_model = self.table_view.selectionModel()
        if selection_model is None:
            return

        selected_rows = sorted(
            {index.row() for index in selection_model.selectedRows()},
            reverse=True,
        )
        if not selected_rows and self.table_view.currentIndex().isValid():
            selected_rows = [self.table_view.currentIndex().row()]
        if not selected_rows:
            return
        self.table_model.remove_rows(selected_rows)

    def add_field(self):
        table_name = self.current_table_name
        if not table_name:
            QMessageBox.information(
                self,
                "No table",
                "Create or select a table first.",
            )
            return

        field_name = input_text_dialog(
            parent=self,
            title="Add field",
            label="Field name",
            default_text="field_1",
        )
        if not field_name:
            return
        field_name = field_name.strip()
        if field_name in self.table_model.dataframe.columns.tolist():
            QMessageBox.warning(
                self,
                "Duplicate field",
                f'The field "{field_name}" already exists.',
            )
            return
        self.table_model.add_column(field_name)

    def delete_field(self):
        table_name = self.current_table_name
        if not table_name or self.table_model.columnCount() == 0:
            return

        current_index = self.table_view.currentIndex()
        if current_index.isValid():
            field_name = self.table_model.dataframe.columns[current_index.column()]
        else:
            field_name = self.table_model.dataframe.columns[-1]

        confirm = QMessageBox.question(
            self,
            "Delete field",
            f'Delete field "{field_name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.table_model.remove_column(field_name)
