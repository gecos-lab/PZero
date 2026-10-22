"""Edit one metadata field for a selection of collection entities."""

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMessageBox,
    QStyledItemDelegate,
)


class EditMetadataDialog(QDialog):
    def __init__(self, collection, selected_uids, default_field=None, parent=None):
        super().__init__(parent)
        self.collection = collection
        self.selected_uids = list(dict.fromkeys(selected_uids))
        self.updated_uids = []
        self.setWindowTitle(f"Edit metadata — {len(self.selected_uids)} selected entities")

        layout = QFormLayout(self)
        self.field_combo = QComboBox()
        for field in collection.editable_columns_names:
            if field in collection.df.columns:
                self.field_combo.addItem(field.replace("_", " ").title(), field)
        index = self.field_combo.findData(default_field)
        if index >= 0:
            self.field_combo.setCurrentIndex(index)
        layout.addRow("Field:", self.field_combo)

        self.value_combo = QComboBox()
        self.value_combo.setMinimumWidth(260)
        self.value_combo.setInsertPolicy(QComboBox.NoInsert)
        self.value_combo.setPlaceholderText("Choose a value")
        layout.addRow("New value:", self.value_combo)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.Ok)
        self.apply_button.setText(f"Apply to {len(self.selected_uids)} entities")
        layout.addRow(self.buttons)
        self.buttons.accepted.connect(self.apply_changes)
        self.buttons.rejected.connect(self.reject)
        self.field_combo.currentIndexChanged.connect(self.refresh_values)
        self.value_combo.currentTextChanged.connect(self.update_apply_button)
        self.refresh_values()

    def refresh_values(self):
        field = self.field_combo.currentData()
        self.value_combo.clear()
        if field is None:
            self.apply_button.setEnabled(False)
            return

        roles = self.collection.valid_roles if field == "role" else []
        self.value_combo.setEditable(not bool(roles))
        values = roles or sorted(
            self.collection.df[field].dropna().astype(str).unique(), key=str.casefold
        )
        self.value_combo.addItems(values)
        self.value_combo.setCurrentIndex(-1)
        current = self.collection.df.loc[
            self.collection.df["uid"].isin(self.selected_uids), field
        ].drop_duplicates()
        if len(current) == 1 and current.notna().all():
            self.value_combo.setCurrentText(str(current.iloc[0]))
        if self.value_combo.isEditable():
            self.value_combo.lineEdit().setPlaceholderText("Choose or enter a value")
        self.update_apply_button()

    def update_apply_button(self):
        self.apply_button.setEnabled(
            bool(self.selected_uids)
            and self.field_combo.currentData() is not None
            and bool(self.value_combo.currentText().strip())
        )

    def apply_changes(self):
        try:
            self.updated_uids = self.collection.set_metadata_for_uids(
                self.selected_uids,
                self.field_combo.currentData(),
                self.value_combo.currentText(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Edit metadata", str(error))
            return
        self.accept()


class MetadataValueDelegate(QStyledItemDelegate):
    """Editable suggestions with Qt's normal Enter, Escape, and focus handling."""

    def __init__(self, collection, parent=None):
        super().__init__(parent)
        self.collection = collection

    def createEditor(self, parent, option, index):
        field = index.model().headerData(index.column(), Qt.Horizontal, Qt.DisplayRole)
        editor = QComboBox(parent)
        editor.setFocusPolicy(Qt.StrongFocus)
        editor.setEditable(True)
        editor.setInsertPolicy(QComboBox.NoInsert)
        editor.addItems(sorted(
            self.collection.df[field].dropna().astype(str).unique(), key=str.casefold
        ))
        editor.activated.connect(lambda: self.commitData.emit(editor))
        editor.activated.connect(lambda: self.closeEditor.emit(editor))
        QTimer.singleShot(0, editor, editor.showPopup)
        return editor

    def setEditorData(self, editor, index):
        value = index.data(Qt.DisplayRole)
        editor.setCurrentIndex(editor.findText("" if value is None else str(value)))
        editor.setEditText("" if value is None else str(value))
        editor.lineEdit().selectAll()

    def eventFilter(self, editor, event):
        if (
            isinstance(editor, QComboBox)
            and event.type() == QEvent.FocusOut
            and (event.reason() == Qt.PopupFocusReason or editor.view().isVisible())
        ):
            # Moving focus into the dropdown is still part of the same edit.
            return False
        return super().eventFilter(editor, event)

    def setModelData(self, editor, model, index):
        value = editor.currentText().strip()
        if value != index.data(Qt.DisplayRole):
            model.setData(index, value, Qt.EditRole)


def bind_metadata_value_editors(table_view, collection):
    """Use editable dropdowns for Feature and Scenario, leaving Name unchanged."""
    columns = [
        collection.df.columns.get_loc(field)
        for field in ("feature", "scenario")
        if field in collection.editable_columns_names and field in collection.df.columns
    ]
    old_handler = getattr(table_view, "_metadata_value_click_handler", None)
    if old_handler is not None:
        table_view.clicked.disconnect(old_handler)
    old_delegate = getattr(table_view, "_metadata_value_delegate", None)
    if old_delegate is not None:
        old_delegate.deleteLater()
    delegate = MetadataValueDelegate(collection, parent=table_view)
    for column in columns:
        table_view.setItemDelegateForColumn(column, delegate)

    def edit_value(index):
        if index.column() in columns:
            table_view.edit(index)

    table_view._metadata_value_delegate = delegate
    table_view._metadata_value_click_handler = edit_value
    table_view.clicked.connect(edit_value)
