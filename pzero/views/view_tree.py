"""view_tree.py
PZero© Andrea Bistacchi"""

from functools import wraps

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
    A draggable button that inherits from QPushButton.

    Provides functionality for a button that can be dragged across
    the interface while maintaining custom appearances and behaviors.
    This widget is checkable, with fixed size settings, and supports
    drag-and-drop operations.

    :ivar checkable: Indicates if the button can be toggled on/off.
    :type checkable: bool
    :ivar checked: States whether the button is currently checked or not.
    :type checked: bool
    :ivar size_policy: Defines the size policy of the button, set to fixed.
    :type size_policy: QSizePolicy
    :ivar minimum_size: Specifies the minimum allowable size for the button.
    :type minimum_size: QSize
    :ivar maximum_size: Specifies the maximum allowable size for the button.
    :type maximum_size: QSize
    """

    def __init__(self, text, parent=None):
        """
        Initializes a checkable widget with a fixed size, defaulting it to a checked state.
        This constructor sets the widget's size policy to fixed, ensuring its dimensions
        match the preferred size hint, and configures it to be checkable and checked.

        :param text: The text label displayed on the widget.
        :type text: str
        :param parent: The parent widget that contains this widget. Defaults to None.
        :type parent: QWidget, optional
        """
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setChecked(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumSize(self.sizeHint())
        self.setMaximumSize(self.sizeHint())

    def mouseMoveEvent(self, event):
        """
        Handle mouse move events to enable drag-and-drop functionality.

        This method is triggered when the mouse is moved while a mouse button is pressed.
        It initiates a drag-and-drop action if the left mouse button is pressed.

        :param event: The QMouseEvent instance containing event-related data.
        :type event: QMouseEvent
        :return: None
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
    Provides a custom header widget with draggable buttons and signal support.

    This class allows creating a custom header for a widget that can include draggable
    buttons. The button layout can be rearranged dynamically through drag-and-drop
    interactions. Each button click emits a signal to trigger further actions, and
    the current order of buttons can be extracted via a defined method.

    :ivar buttonToggled: Signal emitted when a button is toggled.
    :type buttonToggled: Signal
    :ivar layout: Layout manager containing the draggable buttons.
    :type layout: QHBoxLayout
    :ivar buttons: List of draggable button objects in the header.
    :type buttons: List[DraggableButton]
    """

    buttonToggled = Signal()

    def __init__(self, parent=None, labels=None):
        """
        Represents a graphical user interface element that consists of a horizontal layout
        containing multiple draggable buttons. This class initializes a layout with buttons
        provided in the labels argument, connects their click events to a toggling method,
        and sets up the widget to accept drag-and-drop interactions.

        Attributes
        ----------
        layout : QHBoxLayout
            The horizontal layout to manage the arrangement of the draggable buttons.
        buttons : list
            A list of DraggableButton objects representing the buttons within the layout.

        Parameters
        ----------
        :param parent: Optional parent widget of the graphical component.
        :type parent: QWidget, optional
        :param labels: A sequence of strings to label and create the draggable buttons.
        :type labels: list or sequence of str
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

        This method is triggered when the button associated with it has its
        state changed (toggled). It emits a signal called `buttonToggled`,
        which can be connected to other slots or handlers to execute custom
        actions when the toggled event occurs.

        :return: None
        """
        self.buttonToggled.emit()

    def get_order(self):
        """
        Retrieves the text values of checked buttons from a collection of buttons.

        This method iterates through a list of buttons, checks which buttons are
        selected, and gathers their textual representations into a list. This list
        of text values is then returned.

        :return: A list containing the text of all selected buttons.
        :rtype: list[str]
        """
        order = [button.text() for button in self.buttons if button.isChecked()]
        return order

    def dragEnterEvent(self, event):
        """
        Handles the drag enter event when a drag operation enters the widget's
        area. This function ensures that the drag operation is accepted if
        the conditions of the event are met.

        :param event: The QDragEnterEvent object that contains information
            about the drag enter event.
        :return: None
        """
        event.accept()

    def dragMoveEvent(self, event):
        """
        Handles the event triggered when an item is dragged within the widget's boundaries.

        This method is a part of the drag-and-drop functionality. The event provided is
        processed to handle cases where a dragged item is moving over the widget, and
        actions are adjusted accordingly to maintain proper drag sequence and behavior.

        :param event: The QDragMoveEvent object containing details about the dragged
            item's movement, including position and possible actions.
        :type event: QDragMoveEvent
        :return: None
        """
        event.accept()

    def dropEvent(self, event):
        """
        Handles the drop event for rearranging buttons.

        This method is triggered when a drag-and-drop event ends. It validates if the
        source of the event is part of the recognized buttons. If it is, the method
        rearranges the button to the designated position, updates the internal button
        list, and emits a signal indicating the button state has changed.

        :param event: The event object representing the drop action. Carries the source
            of the event and its position.
        :type event: QDropEvent
        :return: None
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

        :param source_button: The button widget to be rearranged.
        :type source_button: QWidget
        :param drop_position: The position at which the button should be placed.
        :type drop_position: QPoint
        :return: None
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

        :param position: The position against which the closest button is calculated.
                         It is expected to have an `x()` method for retrieving the x-coordinate.
        :type position: Any object that has an `x()` method
        :return: A tuple containing the closest button object and its index in the buttons list.
        :rtype: tuple
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

        :param button: The button whose position is being compared.
        :type button: QWidget
        :param position: The position to compare against the button's geometry.
        :type position: QPoint
        :return: True if the position is to the right of the button's center, otherwise False.
        :rtype: bool
        """
        return position.x() > button.geometry().left() + button.geometry().width() / 2

    def _update_button_list(self):
        """
        Updates the list of buttons by iterating through the items in the layout, checking
        if each item is a widget of type DraggableButton, and storing matching widgets
        in the 'buttons' attribute.

        :raises AttributeError: If 'layout' or 'itemAt' is not properly defined on the class,
            an AttributeError may be raised during execution.
        """
        self.buttons = [
            widget
            for i in range(self.layout.count())
            if isinstance((widget := self.layout.itemAt(i).widget()), DraggableButton)
        ]


class CustomTreeWidget(QTreeWidget):
    """
    Represents a customized tree widget with advanced operations such as
    managing items, check states, and property-based behaviors.

    CustomTreeWidget facilitates the organization and interaction with a hierarchical
    data structure. It integrates additional features like custom headers, context
    menu functionality, item-specific widgets, and selection preservation for more
    comprehensive user interactions. The widget also supports advanced customization
    via properties tied to hierarchical elements.

    :ivar parent: Parent widget or object of the CustomTreeWidget.
    :type parent: QWidget or None
    :ivar collection_df: DataFrame collection used to structure and populate the widget.
    :type collection_df: pandas.DataFrame or None
    :ivar tree_labels: Labels for headers used in structuring the hierarchical tree.
    :type tree_labels: List[str] or None
    :ivar name_label: Label for naming identification purposes within the tree.
    :type name_label: str or None
    :ivar uid_label: Identifier label corresponding to unique item UIDs.
    :type uid_label: str or None
    :ivar prop_label: Property label used for additional metadata management.
    :type prop_label: str or None
    :ivar default_labels: Default labels for the tree widget columns.
    :type default_labels: List[str] or None
    :ivar checked_uids: List of UIDs whose items are currently checked within the tree structure.
    :type checked_uids: List[Any]
    :ivar combo_values: Dictionary mapping UIDs to their corresponding property combo box values.
    :type combo_values: Dict[Any, str]
    :ivar header_labels: List of column headers displayed at the top of the tree widget.
    :type header_labels: List[str]
    :ivar header_widget: A custom header widget used to enable additional functionality like toggling and hierarchy rearrangement.
    :type header_widget: CustomHeader
    """

    def __init__(
        self,
        parent=None,
        collection_df=None,
        tree_labels=None,
        name_label=None,
        uid_label=None,
        prop_label=None,
        default_labels=None,
    ):
        """
        Initializes an advanced QTreeWidget subclass and configures its settings
        and data population using provided parameters. This class is designed to
        manage hierarchical data with customizable headers, context menus,
        selection options, and property mappings.

        :param parent: Parent widget that owns this tree widget.
        :type parent: QWidget, optional
        :param collection_df: Dataframe containing hierarchical collection data
            to populate the tree structure.
        :type collection_df: pandas.DataFrame, optional
        :param tree_labels: List of labels for the tree's header columns.
        :type tree_labels: list of str, optional
        :param name_label: Label representing the name column.
        :type name_label: str, optional
        :param uid_label: Label representing a unique identifier for tree nodes.
        :type uid_label: str, optional
        :param prop_label: Label representing additional property fields.
        :type prop_label: str, optional
        :param default_labels: Initial list of default labels to be used if required.
        :type default_labels: list of str, optional

        :raises ValueError: Raised internally if incorrect arguments or unexpected
            parameters are passed during instantiation. Does not describe specific
            triggers since the behavior depends on implementation logic in the
            methods utilizing the parameters.

        """
        super().__init__()
        self.parent = parent
        self.collection_df = collection_df
        self.tree_labels = tree_labels
        self.name_label = name_label
        self.prop_label = prop_label
        self.default_labels = default_labels
        self.uid_label = uid_label
        self.checked_uids = []
        self.combo_values = {}
        self.header_labels = ["Tree", name_label]
        self.blockSignals(False)
        self.setColumnCount(3)
        self.setHeaderLabels(self.header_labels)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.header_widget = CustomHeader(labels=self.tree_labels)
        self.header_widget.buttonToggled.connect(self.rearrange_hierarchy)
        self.populate_tree()

        # Import initial property states from actors_df
        if self.parent and hasattr(self.parent, "actors_df"):
            for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
                uid = self.get_item_uid(item)
                if uid:
                    combo = self.itemWidget(item, self.columnCount() - 1)
                    if combo:
                        # Get the show_property value for this uid from actors_df
                        property_value = self.parent.actors_df.loc[
                            self.parent.actors_df["uid"] == uid, "show_property"
                        ].iloc[0]
                        # Find and set the index in the combo box
                        index = combo.findText(property_value)
                        if index >= 0:
                            combo.setCurrentIndex(index)
                            # Update the stored combo value
                            self.combo_values[uid] = property_value

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.toggle_with_menu)
        self.header().hide()
        self.itemExpanded.connect(self.resize_columns)
        self.itemCollapsed.connect(self.resize_columns)
        self.itemChanged.connect(
            lambda item, column: (
                self.on_checkbox_changed(item, column)
                if item.childCount() == 0
                else None
            )
        )
        self.itemSelectionChanged.connect(self.emit_selection_changed)
        # Import initial selection state if parent and collection exist
        if (
            self.parent
            and hasattr(self.parent, "collection")
            and hasattr(self.parent.collection, "selected_uids")
        ):
            self.restore_selection(self.parent.collection.selected_uids)

    def preserve_selection(func):
        """
        Decorator that preserves the current selection of items in a collection
        while executing the decorated function. After the function execution,
        the original selection is restored. This is particularly useful in cases
        when the function manipulates the collection and might otherwise alter
        the selection unintentionally.

        :param func: The function to be wrapped by the decorator.
        :type func: Callable
        :return: The wrapped function that restores the current selection after execution.
        :rtype: Callable
        """

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            current_selection = self.parent.collection.selected_uids.copy()
            result = func(self, *args, **kwargs)
            self.restore_selection(current_selection)
            return result

        return wrapper

    def restore_selection(self, uids_to_select):
        """
        Restores the previously saved selection of items in the widget based on their unique identifiers.
        This method clears any existing selection in the widget, selects the items matching the provided
        UIDs, and updates the parent's collection of selected UIDs. During this process, widget signals
        are temporarily blocked to avoid triggering unwanted behaviors.

        :param uids_to_select: A list of unique identifiers (UIDs) representing the items to be selected in
            the widget. If list is empty or None, no changes are made.
        :type uids_to_select: list[str]
        :return: None
        """
        if not uids_to_select:
            return

        # Temporarily block signals to prevent recursive calls
        self.blockSignals(True)

        # Clear current selection
        self.clearSelection()

        # Find all items matching our UIDs and select them
        for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
            uid = self.get_item_uid(item)
            if uid and uid in uids_to_select:
                item.setSelected(True)

        # Restore our selection list
        self.parent.collection.selected_uids = uids_to_select.copy()

        # Unblock signals
        self.blockSignals(False)

    def populate_tree(self):
        """
        Populates a tree widget with hierarchical data and correctly configures each item
        with checkboxes and combo boxes. This function retains the state of the combo boxes
        from previous iterations, clears and resets the tree, and updates the widget hierarchy
        based on a defined order. It also ensures the synchronization of checkbox states with
        the external data source for a consistent and dynamic interface.

        :raises TypeError: If accessing non-existent columns in the dataframes.
        :raises AttributeError: If parent or header_widget attributes are not correctly set.
        :param self: The instance of the class containing the method.
        :return: None
        """
        # Save current combo values before clearing the tree
        if self.invisibleRootItem().childCount() > 0:
            for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
                uid = self.get_item_uid(item)
                if uid:
                    combo = self.itemWidget(item, self.columnCount() - 1)
                    if combo:
                        self.combo_values[uid] = combo.currentText()

        # Clean up existing widgets before clearing the tree
        self._cleanup_tree_widgets()
        self.clear()
        hierarchy = self.header_widget.get_order()

        # Ensure actors_df 'show' column is string type before we start
        if hasattr(self.parent, "actors_df"):
            self.parent.actors_df["show"] = self.parent.actors_df["show"].astype(str)

        for _, row in self.collection_df.iterrows():
            parent = self.invisibleRootItem()
            for level in hierarchy:
                parent = self.get_or_create_item(parent, row[level])

            # Create item with empty first column and name in the second column
            name_item = QTreeWidgetItem(["", row[self.name_label]])

            # Store the UID and set initial checkbox state
            if self.uid_label and self.uid_label in row:
                uid = str(row[self.uid_label])
                name_item.setData(0, Qt.UserRole, uid)
                name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)

                # Force initial state to unchecked
                name_item.setCheckState(0, Qt.Unchecked)

                if hasattr(self.parent, "actors_df"):
                    mask = self.parent.actors_df["uid"] == uid
                    if any(mask):
                        show_state = str(
                            self.parent.actors_df.loc[mask, "show"].iloc[0]
                        )

                        # Ensure we're working with string values
                        is_checked = show_state.lower() == "true"
                        checkbox_state = Qt.Checked if is_checked else Qt.Unchecked
                        if is_checked:
                            self.checked_uids.append(uid)
                        name_item.setCheckState(0, checkbox_state)
            else:
                name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
                name_item.setCheckState(0, Qt.Unchecked)

            parent.addChild(name_item)

            # Create and set up the QComboBox
            property_combo = QComboBox()
            for label in self.default_labels:
                property_combo.addItem(label)
            property_combo.addItems(row[self.prop_label])

            # Restore the previously selected value if it exists
            if uid in self.combo_values:
                index = property_combo.findText(self.combo_values[uid])
                if index >= 0:
                    property_combo.setCurrentIndex(index)
            property_combo.currentTextChanged.connect(
                lambda text, item=name_item: self.on_combo_changed(item, text)
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

        :param self: Instance of the class to operate on.
        """
        # Store the current selection and checkbox states before repopulating
        saved_selected = self.parent.collection.selected_uids.copy()
        saved_checked = self.checked_uids.copy()

        # Save any additional checkboxes that might not be in self.checked_uids yet
        if self.invisibleRootItem().childCount() > 0:
            for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
                uid = self.get_item_uid(item)
                if (
                    uid
                    and item.checkState(0) == Qt.Checked
                    and uid not in saved_checked
                ):
                    saved_checked.append(uid)

        # Block signals temporarily to prevent unnecessary signal emissions during rebuild
        self.blockSignals(True)

        # Repopulate the tree (this will clear selections and checkboxes)
        self.populate_tree()

        # Restore checkbox states
        self.checked_uids = saved_checked  # Restore the checked_uids list directly
        for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
            uid = self.get_item_uid(item)
            if uid and uid in saved_checked:
                item.setCheckState(0, Qt.Checked)

        # Update parent checkbox states based on children
        self.update_all_parent_check_states()

        # Restore selection
        self.clearSelection()  # Ensure a clean state before restoring
        if saved_selected:
            # Find all items matching our saved UIDs and select them
            for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
                uid = self.get_item_uid(item)
                if uid and uid in saved_selected:
                    item.setSelected(True)

        # Restore our saved selection list directly
        self.parent.collection.selected_uids = saved_selected

        # Unblock signals
        self.blockSignals(False)

        # Emit selection signal to notify any listeners of the restored selection
        if saved_selected:
            self.parent.collection.signals.itemsSelected.emit(
                self.parent.collection.name
            )

    @preserve_selection
    def add_items_to_tree(self, uids_to_add):
        """
        Adds the specified items to the tree view, creating necessary hierarchical
        structure dynamically based on the defined order. This method either adds new
        items into the current tree or rebuilds the entire tree depending on the number
        of items to add with respect to the total number of items. It initializes the
        checkbox state and additional properties for each new item, including setting
        up the QComboBox for custom labeling. Parent items in the tree are expanded
        after the addition of new child nodes.

        This method ensures hierarchical relationships are preserved and properly
        rendered in the tree view. It also attempts to restore previously stored UI
        states such as combo box selection and checked states for tree nodes.

        :param uids_to_add: List of unique identifiers to add to the tree view.
                           The items represented by these UIDs must already exist in
                           `collection_df`.
        :type uids_to_add: list
        :return: Boolean indicating whether the items were added successfully
                 (True) or if the tree was rebuilt entirely (False).
        :rtype: bool
        """
        # If adding more than 20% of total items, rebuild entire tree
        total_items = len(self.collection_df)
        if len(uids_to_add) > total_items * 0.2:
            self.populate_tree()
            return False

        hierarchy = self.header_widget.get_order()

        for uid in uids_to_add:
            # Get the row from collection_df for this UID
            row = self.collection_df.loc[
                self.collection_df[self.uid_label] == uid
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
            if hasattr(self.parent, "actors_df"):
                mask = self.parent.actors_df["uid"] == uid
                if any(mask):
                    show_state = str(self.parent.actors_df.loc[mask, "show"].iloc[0])
                    is_checked = show_state.lower() == "true"
                    checkbox_state = Qt.Checked if is_checked else Qt.Unchecked
                    if is_checked:
                        self.checked_uids.append(uid)
                    name_item.setCheckState(0, checkbox_state)

            parent.addChild(name_item)

            # Create and set up the QComboBox...
            property_combo = QComboBox()
            for label in self.default_labels:
                property_combo.addItem(label)
            property_combo.addItems(row[self.prop_label])

            # Restore previously selected value if it exists
            if uid in self.combo_values:
                index = property_combo.findText(self.combo_values[uid])
                if index >= 0:
                    property_combo.setCurrentIndex(index)

            property_combo.currentTextChanged.connect(
                lambda text, item=name_item: self.on_combo_changed(item, text)
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
        Removes specified items from a tree structure and updates the state of the tree.
        This function handles the removal of items identified by their unique IDs from
        both a tree widget and an associated dataframe. If the specified number of items
        to be removed exceeds 20% of the total collection, it triggers a full rebuild of
        the tree structure. Otherwise, items are removed individually, handling any
        associated UI elements and maintaining data consistency.

        :param uids_to_remove: List of unique IDs to be removed from the tree and dataframe.
        :type uids_to_remove: list

        :return: A boolean indicating whether the tree structure was only updated
                 (`True`) or fully rebuilt (`False`).
        :rtype: bool
        """
        # If removing more than 20% of total items, rebuild entire tree
        total_items = len(self.collection_df)
        if len(uids_to_remove) > total_items * 0.2:
            # Remove items from collection_df
            self.collection_df = self.collection_df[
                ~self.collection_df[self.uid_label].isin(uids_to_remove)
            ]
            self.populate_tree()
            return False

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

                # Remove the item from checked_uids if present
                if uid in self.checked_uids:
                    self.checked_uids.remove(uid)

                # Remove the item from combo_values if present
                if uid in self.combo_values:
                    del self.combo_values[uid]

                # Get the parent before removing the item
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:  # Item is at root level
                    index = self.indexOfTopLevelItem(item)
                    self.takeTopLevelItem(index)

                # Clean up empty parents recursively
                self._cleanup_empty_parents(parent)

        # Remove items from collection_df
        self.collection_df = self.collection_df[
            ~self.collection_df[self.uid_label].isin(uids_to_remove)
        ]

        # Update parent checkbox states and resize columns
        self.update_all_parent_check_states()
        self.resize_columns()
        return True

    def get_or_create_item(self, parent, text):
        """
        Searches for a child item with the given text under the provided parent. If the child item does
        not exist, creates a new one with the specified text, assigns necessary flags, sets its initial
        state to unchecked, adds it to the parent, and then returns the item.

        :param parent: The parent item under which the search or creation of the child item is performed.
        :type parent: QTreeWidgetItem
        :param text: The text used to search for an existing child or to assign to a new child item.
        :type text: str
        :return: The existing or newly created child item.
        :rtype: QTreeWidgetItem
        """
        for i in range(parent.childCount()):
            if parent.child(i).text(0) == text:
                return parent.child(i)
        item = QTreeWidgetItem([text])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
        item.setCheckState(0, Qt.Unchecked)
        parent.addChild(item)
        return item

    def set_selection_from_uids(self, uids):
        """
        Sets the selection of items based on their unique identifiers (UIDs). It temporarily
        blocks signals to prevent triggering multiple selection signals during the process.
        All current selections are cleared, and items with a matching UID from the provided
        list are selected.

        :param uids: A list of unique identifiers (UIDs) to select items for.
        :type uids: list
        :return: None
        """
        # Block signals temporarily to prevent multiple selection signals
        self.blockSignals(True)

        # Clear current selection
        self.clearSelection()

        # Find and select items with matching UIDs
        for item in self.findItems("", Qt.MatchContains | Qt.MatchRecursive):
            uid = self.get_item_uid(item)
            if uid in uids:
                item.setSelected(True)

        # Unblock signals
        self.blockSignals(False)

        # Emit selection changed signal
        self.emit_selection_changed()

    def emit_selection_changed(self):
        """
        Clear the current selection, update it with the UIDs of selected items, and emit
        a signal to indicate that the selection has changed.

        The method resets the internal selection state by clearing the list of selected
        UIDs in the parent collection and repopulates it based on the currently selected
        items. After updating the internal state, it emits a signal to notify observers
        about the updated selection.

        :raises AttributeError: If any of the required objects or attributes in the
            parent or collection hierarchy are missing.
        :raises TypeError: If the operation involves invalid types, such as incorrect
            item UID retrieval or list modification.
        """
        # Clear the current selection list
        self.parent.collection.selected_uids = []

        # Add the UID of each selected item to the list
        for item in self.selectedItems():
            uid = self.get_item_uid(item)
            if uid:
                self.parent.collection.selected_uids.append(uid)

        # Emit signal
        self.parent.collection.signals.itemsSelected.emit(self.parent.collection.name)

    def update_child_check_states(self, item, check_state):
        """
        Recursively updates the check state of child items in a hierarchical structure.

        This method iterates through all children of the given `item` and sets their
        check states to the specified `check_state`. It ensures that all nested child
        items have their check state updated as well by calling itself recursively.

        :param item: The parent node whose children will have their check states updated.
        :type item: QStandardItem
        :param check_state: The new check state to set for all child items. It must be
            a value corresponding to the Qt.CheckState enumeration (e.g., Qt.Checked,
            Qt.Unchecked, or Qt.PartiallyChecked).
        :type check_state: Qt.CheckState
        :return: None
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

        :param item: The current item whose parent's check state needs to be updated.
        :type item: QTreeWidgetItem
        :return: None
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
        Updates the check states of all parent items in the tree.

        This method traverses through all the items in the tree in reverse order,
        updating the check states of their respective parent items based on the
        check states of their children. It ensures consistency in check states
        throughout the tree hierarchy.

        :return: None
        """
        all_items = self.findItems("", Qt.MatchContains | Qt.MatchRecursive)
        for item in reversed(all_items):
            if item.parent():
                self.update_parent_check_states(item)

    def emit_checkbox_toggled(self):
        """
        Updates the checked state of items in the actors DataFrame based on the current
        state of checkboxes in the tree widget and emits a signal to notify listeners
        about the changes. This function processes all items in the tree widget, compares
        their checkbox state with the corresponding `show` state in the actors DataFrame,
        updates the DataFrame accordingly, and emits a signal with lists of unique
        identifiers (UIDs) for items that were turned on or off.

        :raises TypeError: Raised if the item's UID cannot be determined.

        :raises KeyError: Raised if the required columns `uid` or `show` are missing from
            the actors DataFrame.

        :param turn_on_uids: A list of UIDs corresponding to items whose checkboxes are
            toggled to the checked state.

        :param turn_off_uids: A list of UIDs corresponding to items whose checkboxes are
            toggled to the unchecked state.

        :rtype: None
        :return: None
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
                is_shown = self.parent.actors_df.loc[
                    self.parent.actors_df["uid"] == uid, "show"
                ].iloc[0]
                if is_checked != is_shown:
                    self.parent.actors_df.loc[
                        self.parent.actors_df["uid"] == uid, "show"
                    ] = is_checked
                    if is_checked:
                        turn_on_uids.append(uid)
                    else:
                        turn_off_uids.append(uid)
        # Emit signal
        self.parent.signals.checkboxToggled.emit(
            self.parent.collection.name, turn_on_uids, turn_off_uids
        )

    @preserve_selection
    def on_checkbox_changed(self, item, column):
        """Handle checkbox state changes."""
        # is this "if" working???
        if column != 0 or item.checkState(0) == Qt.PartiallyChecked:
            return

        self.blockSignals(True)
        self.update_child_check_states(item, item.checkState(0))
        self.update_parent_check_states(item)
        self.blockSignals(False)

        self.emit_checkbox_toggled()

    def create_property_combo(self, row, uid):
        """
        Creates a QComboBox with items from the given `row` data and sets the
        current index based on the `uid`.

        This method initializes a QComboBox instance, populates it with items from a data source,
        and optionally selects a predefined item if it matches the provided unique identifier
        (`uid`) in `combo_values`. It ensures that the correct selection is pre-loaded if there
        is an existing binding between the `uid` and a combo value.

        :param row: The data source for the combobox items. Expected to contain a key
            corresponding to `self.prop_label` with a list of items.
        :type row: dict
        :param uid: The unique identifier used to set a default combo box value, if applicable.
        :return: A QComboBox initialized with items from `row` and, if applicable,
            preselected based on `uid`'s corresponding value in `self.combo_values`.
        :rtype: QComboBox
        """
        property_combo = QComboBox()
        property_combo.addItems(row[self.prop_label])

        if uid in self.combo_values:
            index = property_combo.findText(self.combo_values[uid])
            if index >= 0:
                property_combo.setCurrentIndex(index)

        return property_combo

    @preserve_selection
    def on_combo_changed(self, item, text):
        """
        Updates the combo box value and handles property toggling for the associated item
        while maintaining the state of the current selection.

        :param item: The item associated with the combo box.
        :param text: The new value to set for the combo box.
        :return: None
        """
        # Update the stored combo value
        uid = self.get_item_uid(item)
        if uid:
            self.combo_values[uid] = text
            # Update show_property in actors_df for the current uid
            self.parent.actors_df.loc[
                self.parent.actors_df["uid"] == uid, "show_property"
            ] = text
            self.parent.signals.propertyToggled.emit(
                self.parent.collection.name, uid, text
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

        :param position: The position at which the context menu will appear.
                         The position should be defined in coordinates relative
                         to the view.
        :type position: QPoint
        :return: None
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
        all columns of the table and resizes them based on their content. This method is typically useful
        to ensure that the columns are appropriately sized and no extra space is wasted.

        :return: None
        """
        for i in range(self.columnCount()):
            self.resizeColumnToContents(i)

    def update_properties_for_uids(self, uids, properties_list):
        """
        Updates properties for the provided UIDs by manipulating UI components like combo boxes
        and updating corresponding data structures or dataframes. This method temporarily blocks
        signals to avoid unnecessary updates during the operation.

        :param uids:
            List of unique identifiers (UIDs) to identify the target items to update.
        :param properties_list:
            List of property values to be applied to the identified items.
        :return:
            None
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
                        self.combo_values[uid] = combo.itemText(0)

                        # Update show_property in actors_df
                        if hasattr(self.parent, "actors_df"):
                            self.parent.actors_df.loc[
                                self.parent.actors_df["uid"] == uid, "show_property"
                            ] = combo.itemText(0)

                        # Emit property changed signal
                        self.parent.signals.propertyToggled.emit(
                            self.parent.collection.name, uid, combo.itemText(0)
                        )

        # Update the collection_df to reflect the new properties
        for uid in uids:
            mask = self.collection_df[self.uid_label] == uid
            self.collection_df.loc[mask, self.prop_label] = properties_list

        # Unblock signals
        self.blockSignals(False)

    def get_item_uid(self, item):
        """
        Retrieves the unique identifier (UID) of a given item.

        This function extracts the UID from the provided item's data stored
        under a specific role identifier, `Qt.UserRole`.

        :param item: The item from which the UID will be extracted.
                     Expected to be an instance of a class compatible with
                     the `data` method, such as a `QTreeWidgetItem`.
        :type item: Any

        :return: The unique identifier (UID) extracted from the item's
                 data stored under the `Qt.UserRole`.
        :rtype: Any
        """
        return item.data(0, Qt.UserRole)

    def _recursive_cleanup(self, item):
        """
        Recursively cleans up the provided item and its children in a tree-like structure.
        This involves iterating through all children of the given item, cleaning up child
        widgets, and removing them properly to ensure no memory leaks or dangling references.

        :param item: The root item to be cleaned up recursively. The function will process
                     this item and all its child nodes.
        :type item: Any
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

        This method starts at the invisible root item of a tree widget structure and
        performs cleanup operations recursively on all its child items using an
        internal helper method.

        :return: None
        """
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            self._recursive_cleanup(item)

    def _cleanup_empty_parents(self, item):
        """
        Removes empty parent items from a tree structure. This method is used to clean up
        the hierarchy by removing items that have no children.

        :param item: The starting item to begin cleanup process. May be a top-level or
                     child item.
        :return: None
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
