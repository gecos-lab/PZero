"""view_tree.py
PZero© Andrea Bistacchi"""

# Standard library imports____
from functools import wraps

# PySide imports____
from PySide6.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QHBoxLayout,
    QPushButton,
    QWidget,
    QSizePolicy,
    QComboBox,
)
from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDrag


class DraggableButton(QPushButton):
    """
    A draggable button that inherits from QPushButton. It can be dragged across
    the interface while maintaining custom appearances and behavior.
    """

    def __init__(self, text, parent=None):
        """
        Initializes the checkable button with a fixed size, defaulting it to a checked state.
        """
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setChecked(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumSize(self.sizeHint())
        self.setMaximumSize(self.sizeHint())

    def mouseMoveEvent(self, event):
        """
        Handle mouse move events to enable drag-and-drop functionality. This method is triggered
        when the mouse is moved while a mouse button is pressed and initiates a
        drag-and-drop action if the left mouse button is pressed.
        """
        if event.buttons() == Qt.LeftButton:
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(self.text())
            drag.setMimeData(mime_data)
            drag.setHotSpot(event.pos() - self.rect().topLeft())
            drag.exec(Qt.MoveAction)


class CustomHeader(QWidget):
    """
    A custom header widget with draggable buttons and signal support. The button layout
    can be rearranged dynamically through drag-and-drop interactions. Each button click
    emits a signal to trigger actions, and the current order of buttons can be extracted.
    """

    buttonToggled = Signal()

    def __init__(self, parent=None, labels=None):
        """
        A horizontal layout containing multiple draggable buttons. The constructor initializes a
        layout with buttons provided in the labels argument, connects their click events to a
        toggling method, and sets up the widget to accept drag-and-drop interactions.

        layout : QHBoxLayout - The horizontal layout to manage the arrangement of the draggable buttons.
        buttons : list - A list of DraggableButton objects representing the buttons within the layout.
        parent: Optional parent widget of the graphical component.
        labels: A sequence of strings to label and create the draggable buttons.
        """
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.buttons = []
        for label in labels:
            button = DraggableButton(label)
            button.clicked.connect(self.on_button_toggled)
            self.layout.addWidget(button)
            self.buttons.append(button)
        self.layout.addStretch()
        self.setAcceptDrops(True)

    def on_button_toggled(self):
        """
        Emits the `buttonToggled` signal when the button's state is toggled.
        """
        self.buttonToggled.emit()

    def get_order(self):
        """
        Method that iterates through a list of buttons, checks which buttons are
        selected, and gathers their textual representations into a list. This list
        of ordered text values is then returned.
        """
        order = [button.text() for button in self.buttons if button.isChecked()]
        return order

    def dragEnterEvent(self, event):
        """
        Handles the drag enter event when a drag operation enters the widget's
        area. This function ensures that the drag operation is accepted if
        the conditions of the event are met.
        """
        event.accept()

    def dragMoveEvent(self, event):
        """
        Handles the event triggered when an item is dragged within the widget's boundaries.
        This method is a part of the drag-and-drop functionality. The event provided is
        processed to handle cases where a dragged item is moving over the widget, and
        actions are adjusted accordingly to maintain proper drag sequence and behavior.
        """
        event.accept()

    def dropEvent(self, event):
        """
        Handles the drop event for rearranging buttons.
        This method is triggered when a drag-and-drop event ends. It validates if the
        source of the event is part of the recognized buttons. If it is, the method
        rearranges the button to the designated position, updates the internal button
        list, and emits a signal indicating the button state has changed.
        """
        source_button = event.source()
        if source_button not in self.buttons:
            return

        self._rearrange_button(source_button, event.position().toPoint())
        self._update_button_list()
        self.buttonToggled.emit()

    def _rearrange_button(self, source_button, drop_position):
        """
        Rearranges a button within a layout by removing it from its current position
        and inserting it at a new position based on the provided drop position.
        The method determines the closest button to the drop position and adjusts
        the placement accordingly.
        """
        self.layout.removeWidget(source_button)
        closest_button, index = self._find_closest_button(drop_position)

        if closest_button:
            if self._should_insert_after(closest_button, drop_position):
                index += 1
            self.layout.insertWidget(index, source_button)
        else:
            self.layout.addWidget(source_button)

    def _find_closest_button(self, position):
        """
        Finds the closest button to a given position horizontally and returns it along with its index.
        This method calculates the horizontal distance between the given position
        and the center of each button. It identifies the button with the minimum
        distance and returns it alongside its index.
        """
        closest_button = None
        min_distance = float("inf")
        index = -1

        for i, button in enumerate(self.buttons):
            distance = abs(button.geometry().center().x() - position.x())
            if distance < min_distance:
                min_distance = distance
                closest_button = button
                index = i

        return closest_button, index

    def _should_insert_after(self, button, position):
        """
        Determines whether a button should be inserted after a given position
        based on the button's geometry and the provided position's x-coordinate.
        This private method compares the x-coordinate of the given position to the
        center point of the button's geometry and returns True if the position is
        on the right side of the button.
        """
        return position.x() > button.geometry().left() + button.geometry().width() / 2

    def _update_button_list(self):
        """
        Updates the list of buttons by iterating through the items in the layout, checking
        if each item is a widget of type DraggableButton, and storing matching widgets
        in the 'buttons' attribute.
        """
        self.buttons = [
            widget
            for i in range(self.layout.count())
            if isinstance((widget := self.layout.itemAt(i).widget()), DraggableButton)
        ]


class CustomTreeWidget(QTreeWidget):
    """
    A customized tree widget with advanced operations and a hierarchical data structure.
    It integrates additional features like custom draggable headers, context menu functions,
    multi-level checkboxes, and selection preservation. The widget also supports advanced customization
    via parameters passed at instantiation.
    """

    def __init__(
        self,
        parent=None,
        view=None,
        collection=None,
        tree_labels=None,
        name_label=None,
        uid_label=None,
        prop_label=None,
        default_labels=None,
    ):
        """
        Initializes CustomTreeWidget with the following parameters:

        parent: the parent in Qt, so the QtWidget where this tree is included.
        view: the parent view = the parent in the sense of the main application.
        collection.df: Dataframe containing hierarchical collection data to populate the tree.
        tree_labels: List of labels for the tree's header columns.
        name_label: Label representing the name column.
        uid_label: Label representing a unique identifier for tree nodes.
        prop_label: Label representing additional property fields to be used in combo boxes.
        default_labels: Initial list of default labels.
        """
        super().__init__()
        # set all parameters with default values
        self.parent = parent
        self.view = view
        self.collection = collection
        self.tree_labels = tree_labels
        self.name_label = name_label
        self.prop_label = prop_label
        self.default_labels = default_labels
        self.uid_label = uid_label
        # ================== self.checked_uids -> self.view.actors.df =================================================
        # self.checked_uids = []
        # ---------------------- self.combo_values ->  self.view.actors.df --------------------------------------------
        self.combo_values = {}
        self.blockSignals(False)
        # one column for the tree hierarchy, one for name and one for properties
        self.setColumnCount(3)
        self.header_labels = ["Tree", name_label]  # not shown
        self.setHeaderLabels(self.header_labels)  # not shown
        self.header().hide()  # not shown
        self.setSelectionMode(QTreeWidget.ExtendedSelection)

        # set header with draggable buttons
        self.header_widget = CustomHeader(labels=self.tree_labels)
        self.header_widget.buttonToggled.connect(self.rearrange_hierarchy)

        # populate the tree with view entities
        self.populate_tree()

        # # Import initial property states from actors_df
        # # if self.view and hasattr(self.view, "actors_df"):
        # for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
        #     uid = self.get_item_uid(item)
        #     if uid:
        #         combo = self.itemWidget(item, self.columnCount() - 1)
        #         if combo:
        #             # Get the show_property value for this uid from actors_df
        #             property_value = self.view.actors_df.loc[
        #                 self.view.actors_df["uid"] == uid, "show_property"
        #             ].iloc[0]
        #             # Find and set the index in the combo box
        #             index = combo.findText(property_value)
        #             if index >= 0:
        #                 combo.setCurrentIndex(index)
        #                 # Update the stored combo value
        #                 self.combo_values[uid] = property_value

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.toggle_with_menu)
        self.itemExpanded.connect(self.resize_columns)
        self.itemCollapsed.connect(self.resize_columns)
        # self.view.actors.df must be updated when an item is checked/unchecked and self.itemChanged emitted ============
        self.itemChanged.connect(
            lambda item, column: (
                self.on_checkbox_changed(item, column)
                if item.childCount() == 0
                else None
            )
        )
        # self.itemSelectionChanged.connect(self.emit_selection_changed)  # really necessary ?? =======================
        # Import initial selection state if parent and collection exist
        if hasattr(self.collection, "selected_uids"):
            self.restore_selection(self.collection.selected_uids)

    @property
    def tree_name(self):
        return self.objectName()

    def preserve_selection(func):
        """
        Decorator that preserves the current selection of items while executing the decorated
        function. After the function execution, the original selection is restored.
        """

        # =============================================================================================================

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # this is recoded before the function runs
            current_selection = self.collection.selected_uids.copy()
            # the wrapped function runs here
            result = func(self, *args, **kwargs)
            # this is restored after the function has run
            self.restore_selection(current_selection)
            # the wrapped function's return value is returned here
            return result

        return wrapper

    def restore_selection(self, uids_to_select):
        """
        Restores the previously saved selection of items in the widget based on their unique identifiers.
        This method clears any existing selection in the widget, selects the items matching the provided
        UIDs, and updates the parent's collection of selected UIDs. During this process, widget signals
        are temporarily blocked to avoid triggering unwanted loops.
        """
        if not uids_to_select:
            return

        # Temporarily block signals to prevent recursive calls
        self.blockSignals(True)

        # Clear current selection
        self.clearSelection()

        # Find all items matching previously selected UIDs and select them
        for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
            uid = self.get_item_uid(item)
            if uid and uid in uids_to_select:
                item.setSelected(True)

        # Restore selection list
        self.collection.selected_uids = uids_to_select.copy()

        # Unblock signals
        self.blockSignals(False)

    def populate_tree(self):
        """
        (Re-)Populates the tree widget with hierarchical data and configures each item
        with checkboxes and combo boxes. This function retains the state of the combo boxes
        from previous iterations, clears and resets the tree, and updates the widget hierarchy
        based on a defined order. It also ensures the synchronization of checkbox states with
        the external data source.
        """
        # Save current combo values before clearing the tree
        # this should be the same as shown properties =================================================================
        if self.invisibleRootItem().childCount() > 0:
            for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
                uid = self.get_item_uid(item)
                if uid:
                    combo = self.itemWidget(item, self.columnCount() - 1)
                    if combo:
                        self.combo_values[uid] = (
                            combo.currentText()
                        )  # ---------------------------------------------

        # Clean up existing widgets before clearing the tree
        self._cleanup_tree_widgets()
        self.clear()
        hierarchy = self.header_widget.get_order()

        # Ensure actors_df 'show' column is string type before we start  ______________ no string but boolean__________
        # if hasattr(self.view, "actors_df"):
        #     self.view.actors_df["show"] = self.view.actors_df["show"].astype(str)

        for _, row in self.collection.df.iterrows():
            parent = self.invisibleRootItem()
            for level in hierarchy:
                parent = self.get_or_create_item(parent, row[level])

            # Create item with empty first column and name in the second column
            name_item = QTreeWidgetItem(["", row[self.name_label]])

            # Store the UID and set the initial checkbox state
            if self.uid_label and self.uid_label in row:
                uid = str(row[self.uid_label])
                name_item.setData(0, Qt.UserRole, uid)
                name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)

                # # Force initial state to unchecked
                # name_item.setCheckState(0, Qt.Unchecked)

                # if hasattr(self.view, "actors_df"):
                # mask = self.view.actors_df["uid"] == uid
                # if any(mask):
                # show_state = str(self.view.actors_df.loc[mask, "show"].iloc[0])

                # Ensure we're working with string values
                # is_checked = show_state.lower() == "true"  __________________ no string but boolean__________
                is_checked = self.view.actors_df.loc[
                    self.view.actors_df["uid"] == uid, "show"
                ].iloc[0]
                checkbox_state = Qt.Checked if is_checked else Qt.Unchecked
                # if is_checked:
                #     self.checked_uids.append(
                #         uid
                #     )  # =====self.checked_uids -> self.view.actors.df nothing to do here "show" is already set =====
                name_item.setCheckState(0, checkbox_state)
            else:
                name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
                name_item.setCheckState(0, Qt.Unchecked)

            parent.addChild(name_item)

            # Create and set up the QComboBox
            property_combo = QComboBox()
            for label in self.default_labels:
                property_combo.addItem(label)
            if self.prop_label:
                property_combo.addItems(row[self.prop_label])

            # Restore the previously selected value if it exists
            if (
                uid in self.combo_values
            ):  # this should be the same as shown properties  # ---------------------------
                index = property_combo.findText(
                    self.combo_values[uid]
                )  # -------------------------------------------
                if index >= 0:
                    property_combo.setCurrentIndex(index)
            property_combo.currentTextChanged.connect(
                lambda prop_text, item=name_item: self.on_combo_changed(item, prop_text)
            )

            # Add the item and set the combo box in the last column
            self.setItemWidget(name_item, self.columnCount() - 1, property_combo)

        # Expand all items and resize columns
        self.expandAll()
        self.resize_columns()

        # Update parent checkbox states based on the imported states
        self.update_all_parent_check_states()

    @preserve_selection
    def rearrange_hierarchy(self):
        """
        Rearranges the tree hierarchy, preserving and restoring the selection and checkbox
        states of tree items. This method saves the current states of selected and checked
        items, repopulates the tree hierarchy, and restores item states, while maintaining
        the synchronization with the parent collection.
        """

        # Store the current selection and checkbox states before repopulating
        # saved_selected = self.collection.selected_uids.copy()
        # saved_checked = (
        #     self.checked_uids.copy()
        # )  # =========self.checked_uids -> self.view.actors.df nothing to do here "show" is not affected ==============
        # print("saved_checked: ", saved_checked)

        # # Save any additional checkboxes that might not be in self.checked_uids yet
        # if self.invisibleRootItem().childCount() > 0:
        #     for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
        #         uid = self.get_item_uid(item)
        #         if (
        #             uid
        #             and item.checkState(0) == Qt.Checked
        #             and uid not in saved_checked
        #         ):
        #             saved_checked.append(uid)

        # Block signals temporarily to prevent unnecessary signal emissions during rebuild
        self.blockSignals(True)

        # Repopulate the tree (this will clear selections and checkboxes)
        self.populate_tree()

        # # Restore checkbox states
        # self.checked_uids = saved_checked  # Restore the self.checked_uids list directly ================================
        # for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
        #     uid = self.get_item_uid(item)
        #     if uid and uid in saved_checked:
        #         item.setCheckState(0, Qt.Checked)
        #
        # # Update parent checkbox states based on children
        # self.update_all_parent_check_states()

        # # Restore selection
        # self.clearSelection()  # Ensure a clean state before restoring
        # if saved_selected:
        #     # Find all items matching our saved UIDs and select them
        #     for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
        #         uid = self.get_item_uid(item)
        #         if uid and uid in saved_selected:
        #             item.setSelected(True)
        #
        # # Restore our saved selection list directly
        # self.collection.selected_uids = saved_selected

        # Unblock signals
        self.blockSignals(False)

        # # Emit selection signal to notify any listeners of the restored selection
        # if saved_selected:
        #     self.collection.signals.itemsSelected.emit(self.collection.collection_name)

    @preserve_selection
    def add_items_to_tree(self, uids_to_add):
        """
        Adds the specified items to the tree view, updating the hierarchical
        structure dynamically based on the defined order. This method either adds new
        items into the current tree or rebuilds the entire tree depending on the number
        of items to add with respect to the total number of items. It initializes the
        checkbox state and additional properties for each new item, including setting
        up the QComboBox for custom labeling. Parent items in the tree are expanded
        after the addition of new child nodes.
        """
        # If adding more than 20% of total items, rebuild entire tree
        total_items = len(self.collection.df)
        if len(uids_to_add) > total_items * 0.2:
            self.populate_tree()
            return False

        hierarchy = self.header_widget.get_order()

        for uid in uids_to_add:
            # Get the row from collection.df for this UID
            row = self.collection.df.loc[
                self.collection.df[self.uid_label] == uid
            ].iloc[0]

            # Find or create the path in the tree hierarchy
            parent = self.invisibleRootItem()
            # Keep track of created/found parents to expand them later
            parents_to_expand = []

            for level in hierarchy:
                # Set checkbox flags for hierarchy items
                parent = self.get_or_create_item(parent, row[level])
                parents_to_expand.append(parent)
                if not (parent.flags() & Qt.ItemIsUserCheckable):
                    parent.setFlags(
                        parent.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate
                    )
                    parent.setCheckState(0, Qt.Unchecked)

            # Create item with empty first column and name in second column
            name_item = QTreeWidgetItem(["", row[self.name_label]])
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setCheckState(0, Qt.Unchecked)  # Set initial state

            # Set the UID and checkbox state
            name_item.setData(0, Qt.UserRole, uid)

            # Set initial checkbox state based on actors_df if available
            # if hasattr(self.view, "actors_df"):
            # mask = self.view.actors_df["uid"] == uid
            # if any(mask):
            is_checked = self.view.actors_df.loc[
                self.view.actors_df["uid"] == uid, "show"
            ].iloc[0]
            # is_checked = show_state.lower() == "true"
            checkbox_state = Qt.Checked if is_checked else Qt.Unchecked
            # if is_checked:
            #     self.checked_uids.append(
            #         uid
            #     )  # =========self.checked_uids -> self.view.actors.df nothing to do here "show" is already set =====
            name_item.setCheckState(0, checkbox_state)

            parent.addChild(name_item)

            # Create and set up the QComboBox...
            property_combo = QComboBox()
            for label in self.default_labels:
                property_combo.addItem(label)
            property_combo.addItems(row[self.prop_label])

            # # Restore previously selected value if it exists
            # if uid in self.combo_values:
            #     index = property_combo.findText(self.combo_values[uid])
            #     if index >= 0:
            #         property_combo.setCurrentIndex(index)

            property_combo.currentTextChanged.connect(
                lambda prop_text, item=name_item: self.on_combo_changed(item, prop_text)
            )

            self.setItemWidget(name_item, self.columnCount() - 1, property_combo)

            # Expand all parent items in the path
            for parent_item in parents_to_expand:
                parent_item.setExpanded(True)

        # Update parent checkbox states and resize columns
        self.update_all_parent_check_states()
        self.resize_columns()
        return True

    @preserve_selection
    def remove_items_from_tree(self, uids_to_remove):
        """
        Removes specified items from the tree structure and updates the state of the tree.

        This function handles the removal of items identified by their unique IDs from
        both a tree widget and an associated dataframe.

        If the specified number of items to be removed exceeds 20% of the total collection,
        it triggers a full rebuild of the tree structure. Otherwise, items are removed individually,
        handling any associated UI elements and maintaining data consistency.
        """
        # If removing more than 20% of total items, rebuild entire tree
        total_items = len(self.collection.df)
        if len(uids_to_remove) > total_items * 0.2:
            # # Remove items from collection.df  ======================================================================
            # self.collection.df = self.collection.df[
            #     ~self.collection.df[self.uid_label].isin(uids_to_remove)
            # ]
            self.populate_tree()

        # Remove items one by one
        for uid in uids_to_remove:
            # Find all items matching our UID
            items_to_remove = []
            for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
                if self.get_item_uid(item) == uid:
                    items_to_remove.append(item)

            # Remove found items
            for item in items_to_remove:
                # Clean up any associated widgets (like combo boxes)
                combo = self.itemWidget(item, self.columnCount() - 1)
                if combo:
                    combo.deleteLater()
                    self.removeItemWidget(item, self.columnCount() - 1)

                # # Remove the item from self.checked_uids if present
                # if (
                #     uid in self.checked_uids
                # ):  # ==============================================================
                #     self.checked_uids.remove(
                #         uid
                #     )  # ====self.checked_uids -> self.view.actors.df nothing to do here "show" is not affected =====

                # Remove the item from combo_values if present
                if (
                    uid in self.combo_values
                ):  # ---------------------------------------------------------------------
                    del self.combo_values[
                        uid
                    ]  # --------------------------------------------------------------------

                # Get the parent before removing the item
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:  # Item is at root level
                    index = self.indexOfTopLevelItem(item)
                    self.takeTopLevelItem(index)

                # Clean up empty parents recursively
                self._cleanup_empty_parents(parent)

        # # Remove items from collection.df  ==========================================================================
        # self.collection.df = self.collection.df[~self.collection.df[self.uid_label].isin(uids_to_remove)]

        # Update parent checkbox states and resize columns
        self.update_all_parent_check_states()
        self.resize_columns()

    def get_or_create_item(self, parent, text):
        """
        Searches for a child item with the given text under the provided parent. If the child item does
        not exist, creates a new one with the specified text, assigns necessary flags, sets its initial
        state to unchecked, adds it to the parent, and then returns the item.
        """
        for i in range(parent.childCount()):
            if parent.child(i).text(0) == text:
                return parent.child(i)
        item = QTreeWidgetItem([text])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
        item.setCheckState(0, Qt.Unchecked)
        parent.addChild(item)
        return item

    def set_selection_from_collection(self):
        """
        To be called from the main application, sets the selection of items in the tree
        from self.collection.selected_uids. It temporarily blocks signals to prevent triggering
        multiple selection signals during the process.  All current selections
        are cleared, and items with a matching UID from the provided list are selected.
        """
        # Block signals temporarily to prevent multiple selection signals
        self.blockSignals(True)

        # Clear current selection
        self.clearSelection()

        # Find and select items with matching UIDs
        for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
            uid = self.get_item_uid(item)
            if uid in self.collection.selected_uids:
                item.setSelected(True)

        # Unblock signals
        self.blockSignals(False)

        # # Emit selection changed signal
        # self.emit_selection_changed()  # ============================================================================

    def emit_selection_changed(self):
        """
        To be used when selecting items from the tree towards the main application, it clears the current
        selection, update it with the UIDs of selected items, and emits a signal to indicate that
        the selection has changed.
        The method resets the internal selection state by clearing the list of selected
        UIDs in the parent collection and repopulates it based on the currently selected
        items. After updating the internal state, it emits a signal to notify observers
        about the updated selection.
        """
        # Clear the current selection list
        self.collection.selected_uids = []

        # Add the UID of each selected item to the list
        for item in self.selectedItems():
            uid = self.get_item_uid(item)
            if uid:
                self.collection.selected_uids.append(uid)

        # Emit signal
        self.collection.signals.itemsSelected.emit(self.collection.collection_name)

    def update_child_check_states(self, item, check_state):
        """
        Recursively updates the check state of child items in the hierarchical structure. This method
        iterates through all children of `item` and sets their check states to the specified `check_state`.
        It ensures that all nested child items have their check state updated by calling itself recursively.
        """
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, check_state)
            self.update_child_check_states(child, check_state)

    def update_parent_check_states(self, item):
        """
        Updates the check state of the parent item in a tree structure based on the check
        states of its child items. This method recursively evaluates the state of parent
        items up the tree structure until the root.
        """
        parent = item.parent()
        if parent:
            children = [parent.child(i) for i in range(parent.childCount())]
            check_states = [child.checkState(0) for child in children]

            if all(state == Qt.Checked for state in check_states):
                parent.setCheckState(0, Qt.Checked)
            elif all(state == Qt.Unchecked for state in check_states):
                parent.setCheckState(0, Qt.Unchecked)
            else:
                parent.setCheckState(0, Qt.PartiallyChecked)

            self.update_parent_check_states(parent)

    def update_all_parent_check_states(self):
        """
        Updates the check states of all parent items in the tree. This method traverses through all
        the items in the tree in reverse order, updating the check states of their respective
        parent items based on the check states of their children.
        """
        all_items = self.findItems("", Qt.MatchContains | Qt.MatchRecursive)
        for item in reversed(all_items):
            if item.parent():
                self.update_parent_check_states(item)

    def emit_checkbox_toggled(self):
        """
        To be used when checking/unchecking, to send the new state to the main application.
        Updates the checked state of items in the actors DataFrame based on the current
        state of checkboxes in the tree widget and emits a signal to notify listeners
        about the changes. This function processes all items in the tree widget, compares
        their checkbox state with the corresponding `show` state in the actors DataFrame,
        updates the DataFrame accordingly, and emits a signal with lists of unique
        identifiers (UIDs) for items that were turned on or off.
        """
        # Update the checked state in actors_df based on the current tree state
        turn_on_uids = []
        turn_off_uids = []
        for item in self.findItems(
            "", Qt.MatchContains | Qt.MatchRecursive, 1
        ):  # Search in the name column (1)
            uid = self.get_item_uid(item)
            if uid:
                is_checked = item.checkState(0) == Qt.Checked
                is_shown = self.view.actors_df.loc[
                    self.view.actors_df["uid"] == uid, "show"
                ].values[0]
                if is_checked != is_shown:
                    if is_checked:
                        turn_on_uids.append(uid)
                    else:
                        turn_off_uids.append(uid)
        # Emit signal
        self.view.signals.checkboxToggled.emit(
            self.collection.collection_name, turn_on_uids, turn_off_uids
        )

    @preserve_selection
    def on_checkbox_changed(self, item, column):
        """Handle checkbox state changes."""
        if column != 0 or item.checkState(0) == Qt.PartiallyChecked:
            return

        self.blockSignals(True)
        self.update_child_check_states(item, item.checkState(0))
        self.update_parent_check_states(item)
        self.blockSignals(False)

        self.emit_checkbox_toggled()

    def create_property_combo(self, row, uid):
        """
        Creates a QComboBox with items from the given `row` data and sets the current index
        based on the `uid`. This method initializes a QComboBox instance, populates it,
        and optionally selects a predefined item if it matches the provided unique identifier
        (`uid`) in `combo_values`.
        """
        property_combo = QComboBox()
        property_combo.addItems(row[self.prop_label])

        if (
            uid in self.combo_values
        ):  # -----------------------------------------------------------------------------
            index = property_combo.findText(
                self.combo_values[uid]
            )  # -----------------------------------------------
            if index >= 0:
                property_combo.setCurrentIndex(index)

        return property_combo

    @preserve_selection
    def on_combo_changed(self, item, prop_text):
        """
        To be used to send the new combo state to the main application.
        Updates the combo box value and handles property toggling for the associated item
        while maintaining the state of the current selection.
        """
        # Update the stored combo value
        uid = self.get_item_uid(item)
        if uid:
            self.combo_values[uid] = (
                prop_text  # --------------------------------------------------------------------
            )
            # Update show_property in actors_df for the current uid
            self.view.actors_df.loc[
                self.view.actors_df["uid"] == uid, "show_property"
            ] = prop_text
            self.view.signals.propertyToggled.emit(
                self.collection.collection_name, uid, prop_text
            )

    def toggle_with_menu(self, position):
        """
        Provides functionality to toggle the states of checkboxes for selected
        items through a context menu initiated at a given position.
        This method displays a context menu at the specified position, allowing
        the user to toggle the checkbox states of the selected items in the view.
        When the "Toggle Checkboxes" option is chosen, the method checks the state
        of each selected item's checkbox and switches it to the opposite state
        (either checked or unchecked). Additionally, it updates the state of
        child and parent checkboxes for the affected items to maintain consistency.
        A signal indicating that a checkbox has been toggled is then emitted.
        """
        menu = QMenu()
        toggle_action = menu.addAction("Toggle Checkboxes")
        action = menu.exec_(self.viewport().mapToGlobal(position))
        if action == toggle_action:
            for item in self.selectedItems():
                new_state = (
                    Qt.Checked if item.checkState(0) == Qt.Unchecked else Qt.Unchecked
                )
                item.setCheckState(0, new_state)
                self.update_child_check_states(item, new_state)
                self.update_parent_check_states(item)
            self.emit_checkbox_toggled()

    def resize_columns(self):
        """
        Adjusts the width of all columns in a table to fit the content within each column. It iterates over
        all columns of the table and resizes them based on their content.
        """
        for i in range(self.columnCount()):
            self.resizeColumnToContents(i)

    def update_properties_for_uids(self, uids, properties_list):
        """
        Updates properties for the provided UIDs by manipulating combo boxes and updating corresponding
        dataframes. This method temporarily blocks signals to avoid unnecessary updates during the operation.
        """
        # Block signals temporarily to prevent unnecessary updates
        self.blockSignals(True)

        for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
            uid = self.get_item_uid(item)
            if uid and uid in uids:
                combo = self.itemWidget(item, self.columnCount() - 1)
                if combo:
                    # Store current selection if it exists
                    current_text = combo.currentText()

                    # Clear the combo box
                    combo.clear()

                    # Add default labels first
                    for label in self.default_labels:
                        combo.addItem(label)

                    # Add the new properties
                    combo.addItems(properties_list)

                    # Try to restore previous selection if it's still available
                    index = combo.findText(current_text)
                    if index >= 0:
                        combo.setCurrentIndex(index)
                    else:
                        # If previous selection is no longer available, set to first default label
                        combo.setCurrentIndex(0)
                        self.combo_values[uid] = combo.itemText(
                            0
                        )  # -------------------------------------------------

                        # Update show_property in actors_df
                        # if hasattr(self.view, "actors_df"):
                        self.view.actors_df.loc[
                            self.view.actors_df["uid"] == uid, "show_property"
                        ] = combo.itemText(0)

                        # Emit property changed signal  ===============================================================
                        self.view.signals.propertyToggled.emit(
                            self.collection.collection_name, uid, combo.itemText(0)
                        )

        # # Update the collection.df to reflect the new properties  ===================================================
        # for uid in uids:
        #     mask = self.collection.df[self.uid_label] == uid
        #     self.collection.df.loc[mask, self.prop_label] = properties_list

        # Unblock signals
        self.blockSignals(False)

    def get_item_uid(self, item):
        """
        Retrieves the unique identifier (UID) of a given item.
        """
        return item.data(0, Qt.UserRole)

    def _recursive_cleanup(self, item):
        """
        Recursively cleans up the provided item and its children in a tree-like structure.
        """
        for i in range(item.childCount()):
            child = item.child(i)
            self._recursive_cleanup(child)

        # Remove and delete the widget
        widget = self.itemWidget(item, self.columnCount() - 1)
        if widget:
            widget.deleteLater()
            self.removeItemWidget(item, self.columnCount() - 1)

    def _cleanup_tree_widgets(self):
        """
        Recursively cleans up tree widgets by accessing the root and its child items.
        """
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            self._recursive_cleanup(item)

    def _cleanup_empty_parents(self, item):
        """
        Removes empty parent items from a tree structure. This method is used to clean up
        the hierarchy by removing items that have no children.
        """
        if not item:
            return

        while item and item.childCount() == 0:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                index = self.indexOfTopLevelItem(item)
                self.takeTopLevelItem(index)
            item = parent
