"""properties_manager.py
PZero© Andrea Bistacchi"""

import cmocean as cmo

import colorcet as cc

from matplotlib.pyplot import colormaps as plt_colormaps
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.cm as cm

# Define custom Petrel-like seismic colormap (Blue-White-Red high contrast)
# Colors: Dark Blue -> White -> Dark Red
# This makes amplitudes "pop" more than the standard diluted seismic map.
# Colors: Cyan -> Navy -> Blue -> Gray -> Light Gray -> Maroon -> Red -> Yellow
# Detailed gradient for maximum contrast and Petrel-like appearance.
#seismic_pzero_colors = [[255,0,0],"blue", "gray", "lightgray", "maroon", "red", "yellow"]
#seismic_pzero_cmap = LinearSegmentedColormap.from_list("seismic_pzero", seismic_pzero_colors, N=256)

# create a custom colormap from RGB values and their value positions
# Normalize RGB values from 0-255 to 0-1 range
import matplotlib as mpl
import matplotlib.pyplot as plt

seismic_pzero_cmap = LinearSegmentedColormap.from_list(
    "seismic_pzero",
    [
        (0.0, (255/255, 255/255, 0/255)),      # Yellow
        (0.32, (191/255, 0/255, 0/255)),       # Dark Red
        (0.4, (97/255, 69/255, 0/255)),        # Brown
        (0.5, (204/255, 204/255, 204/255)),    # Light Gray
        (0.6, (77/255, 77/255, 77/255)),       # Dark Gray
        (0.68, (0/255, 0/255, 191/255)),       # Dark Blue
        (1.0, (161/255, 255/255, 255/255)),    # Cyan
    ],
    N=256,
)

# Register the colormap with matplotlib
try:
    # Try modern Matplotlib API (3.5+)
    if hasattr(mpl, 'colormaps') and hasattr(mpl.colormaps, 'register'):
        mpl.colormaps.register(cmap=seismic_pzero_cmap)
        # Also register with space in name for compatibility
        seismic_pzero_cmap_space = LinearSegmentedColormap.from_list(
            "seismic pzero",
            [
                (0.0, (255/255, 255/255, 0/255)),
                (0.32, (191/255, 0/255, 0/255)),
                (0.4, (97/255, 69/255, 0/255)),
                (0.5, (204/255, 204/255, 204/255)),
                (0.6, (77/255, 77/255, 77/255)),
                (0.68, (0/255, 0/255, 191/255)),
                (1.0, (161/255, 255/255, 255/255)),
            ],
            N=256,
        )
        mpl.colormaps.register(cmap=seismic_pzero_cmap_space)
    # Try older API (via pyplot or cm)
    elif hasattr(plt, 'register_cmap'):
        plt.register_cmap(name="seismic_pzero", cmap=seismic_pzero_cmap)
        plt.register_cmap(name="seismic pzero", cmap=seismic_pzero_cmap)
    elif hasattr(cm, 'register_cmap'):
        cm.register_cmap(name="seismic_pzero", cmap=seismic_pzero_cmap)
        cm.register_cmap(name="seismic pzero", cmap=seismic_pzero_cmap)
except ValueError:
    # Already registered
    pass
except Exception as e:
    print(f"Warning: Colormap registration failed: {e}")


from PySide6.QtCore import QObject, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QTableWidgetItem,
    QLabel,
    QComboBox,
    QHeaderView,
    QDoubleSpinBox,
)

from numpy import (
    asarray as np_asarray,
    isfinite as np_isfinite,
    linspace as np_linspace,
    nan as np_nan,
)

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat
from pandas.core.common import flatten as pd_flatten

from pyvista import get_cmap_safe as pv_get_cmap_safe
import pyvista as pv


PROPERTY_COLLECTION_NAMES = (
    "geol_coll",
    "dom_coll",
    "image_coll",
    "mesh3d_coll",
    "fluid_coll",
    "backgrnd_coll",
    "well_coll",
)

PROPERTY_LEGEND_DEFAULTS = {
    "range_mode": "auto",
    "range_min": np_nan,
    "range_max": np_nan,
}

PROPERTY_LEGEND_DEFAULT_COLUMNS = {
    "property_name": "",
    "colormap": "rainbow",
    **PROPERTY_LEGEND_DEFAULTS,
}

PROPERTY_LEGEND_COLUMN_TYPES = {
    "property_name": str,
    "colormap": str,
    "range_mode": str,
    "range_min": float,
    "range_max": float,
}


def cmap2qpixmap(cmap=None, steps=50):
    """Takes a maplotlib, colorcet, or cmocean colormap and returns a QPixmap,
    modified after
    https://gist.github.com/ChrisBeaumont/4025831
    using pv_get_cmap_safe from PyVista
    https://github.com/pyvista/pyvista/blob/6777a6a5fb4f3691b829edf6103401537faeb3cb/pyvista/plotting/colors.py#L397
    """
    inds = np_linspace(0, 1, steps)
    try:
        colormap = pv_get_cmap_safe(cmap)
    except ValueError:
        # Fallback if the colormap is invalid (e.g. removed or renamed custom map)
        # This prevents the app from crashing due to persisted settings.
        try:
            # Try replacing space with underscore if that was the issue
            if isinstance(cmap, str) and " " in cmap:
                 colormap = pv_get_cmap_safe(cmap.replace(" ", "_"))
            else:
                 colormap = pv_get_cmap_safe("gray")
        except:
             colormap = pv_get_cmap_safe("gray")
    rgbas = colormap(inds)
    q_rgbas = [
        QColor(int(r * 255), int(g * 255), int(b * 255), int(a * 255)).rgba()
        for r, g, b, a in rgbas
    ]
    im = QImage(steps, 1, QImage.Format_Indexed8)
    im.setColorTable(q_rgbas)
    for i in range(steps):
        im.setPixel(i, 0, i)
    im = im.scaled(200, 50)
    pm = QPixmap.fromImage(im)
    return pm


def create_property_legend_entry(property_name=None, colormap="rainbow"):
    """Build a default row for the property legend dataframe."""
    return {
        "property_name": property_name,
        "colormap": colormap,
        "range_mode": PROPERTY_LEGEND_DEFAULTS["range_mode"],
        "range_min": PROPERTY_LEGEND_DEFAULTS["range_min"],
        "range_max": PROPERTY_LEGEND_DEFAULTS["range_max"],
    }


def ensure_property_legend_schema(prop_legend_df=None):
    """Backfill missing property-legend columns and normalize persisted values."""
    if prop_legend_df is None:
        return prop_legend_df

    for column, default_value in PROPERTY_LEGEND_DEFAULT_COLUMNS.items():
        if column not in prop_legend_df.columns:
            prop_legend_df[column] = default_value

    if prop_legend_df.empty:
        return prop_legend_df

    prop_legend_df["colormap"] = (
        prop_legend_df["colormap"].fillna("rainbow").astype(str)
    )
    prop_legend_df["range_mode"] = (
        prop_legend_df["range_mode"].fillna(PROPERTY_LEGEND_DEFAULTS["range_mode"])
        .astype(str)
        .str.lower()
    )
    prop_legend_df.loc[
        ~prop_legend_df["range_mode"].isin(["auto", "manual"]), "range_mode"
    ] = PROPERTY_LEGEND_DEFAULTS["range_mode"]
    prop_legend_df["range_min"] = prop_legend_df["range_min"].astype(float)
    prop_legend_df["range_max"] = prop_legend_df["range_max"].astype(float)
    return prop_legend_df


def _split_component_property_name(property_name=None):
    if not isinstance(property_name, str):
        return None, None
    if property_name.endswith("]") and "[" in property_name:
        try:
            pos = property_name.rindex("[")
            return property_name[:pos], int(property_name[pos + 1 : -1])
        except ValueError:
            return None, None
    return None, None


def _get_collection_property_datasets(parent=None):
    for collection_name in PROPERTY_COLLECTION_NAMES:
        collection = getattr(parent, collection_name, None)
        if collection is None or not hasattr(collection, "df"):
            continue
        if "uid" not in collection.df.columns:
            continue
        for uid in collection.df["uid"].dropna().tolist():
            try:
                vtk_obj = collection.get_uid_vtk_obj(uid)
            except Exception:
                continue
            if vtk_obj is not None:
                yield vtk_obj


def _get_property_values_from_dataset(dataset=None, property_name=None):
    if dataset is None or not property_name:
        return None

    try:
        wrapped = dataset if isinstance(dataset, pv.DataSet) else pv.wrap(dataset)
    except Exception:
        return None

    if property_name in ["X", "Y", "Z"]:
        points = getattr(wrapped, "points", None)
        if points is None or len(points) == 0:
            return None
        idx = {"X": 0, "Y": 1, "Z": 2}[property_name]
        return points[:, idx]

    base_name, component_idx = _split_component_property_name(property_name)
    if base_name is not None:
        for data_store_name in ("point_data", "cell_data", "field_data"):
            try:
                data_store = getattr(wrapped, data_store_name)
                if base_name not in data_store:
                    continue
                values = np_asarray(data_store[base_name])
                if values.size == 0:
                    return None
                if values.ndim == 1:
                    if component_idx == 0:
                        return values
                    return None
                if values.shape[-1] <= component_idx:
                    return None
                return values[..., component_idx].reshape(-1)
            except Exception:
                continue
        return None

    try:
        if property_name in wrapped.array_names:
            return np_asarray(wrapped.get_array(property_name))
    except Exception:
        pass

    for data_store_name in ("point_data", "cell_data", "field_data"):
        try:
            data_store = getattr(wrapped, data_store_name)
            if property_name in data_store:
                return np_asarray(data_store[property_name])
        except Exception:
            continue
    return None


def get_auto_property_range(parent=None, property_name=None):
    """Compute the project-wide scalar range for a property."""
    range_min = None
    range_max = None

    for dataset in _get_collection_property_datasets(parent=parent):
        values = _get_property_values_from_dataset(
            dataset=dataset, property_name=property_name
        )
        if values is None:
            continue

        values = np_asarray(values).reshape(-1)
        if values.size == 0:
            continue
        finite_values = values[np_isfinite(values)]
        if finite_values.size == 0:
            continue

        dataset_min = float(finite_values.min())
        dataset_max = float(finite_values.max())
        if range_min is None or dataset_min < range_min:
            range_min = dataset_min
        if range_max is None or dataset_max > range_max:
            range_max = dataset_max

    if range_min is None or range_max is None or not range_min < range_max:
        return None
    return (range_min, range_max)


def get_property_render_settings(parent=None, property_name=None):
    """Return the effective colormap and scalar range for a property."""
    settings = {"cmap": None, "clim": None}
    if parent is None or not property_name or not hasattr(parent, "prop_legend_df"):
        return settings

    parent.prop_legend_df = ensure_property_legend_schema(parent.prop_legend_df)
    prop_row = parent.prop_legend_df.loc[
        parent.prop_legend_df["property_name"] == property_name
    ]
    if prop_row.empty:
        return settings

    row = prop_row.iloc[0]
    cmap = row["colormap"] if isinstance(row["colormap"], str) else None
    if cmap:
        settings["cmap"] = cmap

    manual_min = row["range_min"]
    manual_max = row["range_max"]
    if (
        row["range_mode"] == "manual"
        and np_isfinite(manual_min)
        and np_isfinite(manual_max)
        and manual_min < manual_max
    ):
        settings["clim"] = (float(manual_min), float(manual_max))
        return settings

    settings["clim"] = get_auto_property_range(parent=parent, property_name=property_name)
    return settings


class PropertiesCMaps(QObject):
    """Properties legend manager."""

    # Dictionaries used to define types of legend columns.
    prop_cmap_dict = {
        "property_name": ["X", "Y", "Z"],
        "colormap": ["rainbow", "rainbow", "terrain"],
        "range_mode": ["auto", "auto", "auto"],
        "range_min": [np_nan, np_nan, np_nan],
        "range_max": [np_nan, np_nan, np_nan],
    }

    prop_cmap_dict_types = PROPERTY_LEGEND_COLUMN_TYPES

    # List of all  matplotlib, colorcet, or cmocean colormaps used by PyVista
    # https://docs.pyvista.org/examples/02-plot/cmap.html
    colormaps_list = (
        ["seismic_pzero"]
        + plt_colormaps()
        + ["cet_" + cmap for cmap in list(cc.cm.keys())]
        + cmo.cm.cmapnames
    )

    def __init__(self, parent=None, *args, **kwargs):
        QObject.__init__(self, parent)

    def _build_range_spin_box(self):
        spin_box = QDoubleSpinBox()
        spin_box.setDecimals(6)
        spin_box.setRange(-1e18, 1e18)
        spin_box.setSingleStep(0.1)
        return spin_box

    def _print_invalid_range(self, parent=None, property_name=None):
        if parent is not None and hasattr(parent, "print_terminal"):
            parent.print_terminal(
                f"Invalid range for property '{property_name}': min must be smaller than max."
            )

    def _set_preview_label(self, parent=None, index=None, cmap=None):
        label = QLabel()
        label.setPixmap(cmap2qpixmap(cmap))
        parent.PropertiesTableWidget.setCellWidget(index, 2, label)

    def _refresh_range_widgets(self, parent=None, index=None, property_name=None):
        if parent is None or index is None or property_name is None:
            return

        prop_row = parent.prop_legend_df.loc[
            parent.prop_legend_df["property_name"] == property_name
        ]
        if prop_row.empty:
            return

        row = prop_row.iloc[0]
        mode_combo_box = parent.PropertiesTableWidget.cellWidget(index, 3)
        min_spin_box = parent.PropertiesTableWidget.cellWidget(index, 4)
        max_spin_box = parent.PropertiesTableWidget.cellWidget(index, 5)
        if mode_combo_box is None or min_spin_box is None or max_spin_box is None:
            return

        auto_range = get_auto_property_range(parent=parent, property_name=property_name)
        range_mode = row["range_mode"]
        if range_mode == "manual":
            display_min = float(row["range_min"]) if np_isfinite(row["range_min"]) else None
            display_max = float(row["range_max"]) if np_isfinite(row["range_max"]) else None
            if display_min is None or display_max is None or not display_min < display_max:
                if auto_range is not None:
                    display_min, display_max = auto_range
                else:
                    display_min, display_max = (0.0, 1.0)
            min_enabled = True
        else:
            if auto_range is not None:
                display_min, display_max = auto_range
            else:
                display_min, display_max = (0.0, 0.0)
            min_enabled = False

        blockers = [
            QSignalBlocker(mode_combo_box),
            QSignalBlocker(min_spin_box),
            QSignalBlocker(max_spin_box),
        ]
        _ = blockers
        mode_combo_box.setCurrentText(range_mode.title())
        min_spin_box.setEnabled(min_enabled)
        max_spin_box.setEnabled(min_enabled)
        min_spin_box.setValue(display_min)
        max_spin_box.setValue(display_max)
        min_spin_box.last_valid_value = display_min
        max_spin_box.last_valid_value = display_max
        if auto_range is None:
            min_spin_box.setToolTip("No valid project-wide range is currently available.")
            max_spin_box.setToolTip("No valid project-wide range is currently available.")
        elif range_mode == "auto":
            min_spin_box.setToolTip("Project-wide automatic minimum.")
            max_spin_box.setToolTip("Project-wide automatic maximum.")
        else:
            min_spin_box.setToolTip("Manual minimum.")
            max_spin_box.setToolTip("Manual maximum.")

    def _emit_property_style_changed(self, parent=None, property_name=None):
        if parent is not None and hasattr(parent, "signals"):
            parent.signals.prop_legend_cmap_modified.emit(property_name)

    def update_widget(self, parent=None):
        """Update the properties colormap dataframe and widget. This is different from legend manager,
        where the geol_coll.legend_df dataframe is managed directly by the geol_coll class. The reason for
        this difference is that property colormaps are managed at the whole project level, across the
        geological, dom and mesh3d collections.
        The pattern to extract a cell value from a Pandas dataframe is:
        dataframe.loc[boolean_index_rows, boolean_index_columns].values[cell_id]
        The boolean indexes used by loc can be:
        - the name of a column (e.g. "color")
        - a boolean indexing series (i.e. a sequence of True and False values) obtained by one or more
        conditions applied on the dataframe
        - a numeric index or a range of indexes as used by iloc (i.e. 3 or 3:5)
        The method values() applied at the end returns the cell value(s) at specified cell(s), otherwise
        a dataframe would be returned
        The function pd.unique() used above returns a list of unique values from a set of cells.
        TO ADD MORE PROPERTIES TO THE LEGEND, SIMPLY ADD MORE COLUMNS TO THE legend AND NEW
        WIDGETS HERE POINTING TO THE NEW COLUMNS.
        Note that at and iat can be used to access a single value in a cell directly (so values()
        is not required), but do not work with conditional indexing."""
        parent.prop_legend_df = ensure_property_legend_schema(parent.prop_legend_df)
        # Update the prop_legend_df. X, Y Z are added to the list in order not to alter them.
        all_props = ["X", "Y", "Z"]
        add_props = []
        # Make a list of all properties (unique values).
        for collection in [
            parent.geol_coll,
            parent.dom_coll,
            parent.image_coll,
            parent.mesh3d_coll,
            parent.fluid_coll,
            parent.backgrnd_coll,
        ]:
            coll_props = collection.df["properties_names"].to_list()
            coll_props = list(pd_flatten(coll_props))
            coll_prop_comps = collection.df["properties_components"].to_list()
            coll_prop_comps = list(pd_flatten(coll_prop_comps))
            for i in range(len(coll_props)):
                # if coll_prop_comps[i] == 3:
                #     add_props = (
                #         add_props
                #         + [coll_props[i] + "[0]"]
                #         + [coll_props[i] + "[1]"]
                #         + [coll_props[i] + "[2]"]
                #     )
                if coll_prop_comps[i] > 1:
                    for j in range(coll_prop_comps[i]):
                        add_props.append(coll_props[i] + f"[{j}]")
                elif coll_prop_comps[i] == 1:
                    add_props = add_props + [coll_props[i]]

        if parent.well_coll.df["properties_names"].to_list():
            add_props.append("MD")

        add_props = list(
            set(add_props)
        )  # a set is composed of unique values from a list
        add_props = list(filter(None, add_props))  # eliminate empty elements
        all_props = all_props + add_props

        # Add new properties to dataframe.
        for prop in all_props:
            if not prop in parent.prop_legend_df["property_name"].to_list():
                # Old Pandas <= 1.5.3
                # parent.prop_legend_df = parent.prop_legend_df.append(
                #     {"property_name": prop, "colormap": "rainbow"}, ignore_index=True
                # )
                # New Pandas >= 2.0.0
                parent.prop_legend_df = pd_concat(
                    [
                        parent.prop_legend_df,
                        pd_DataFrame([create_property_legend_entry(prop, "rainbow")]),
                    ],
                    ignore_index=True,
                )
        # The remove old ones no more used.
        for prop in parent.prop_legend_df["property_name"].to_list():
            if not prop in all_props:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = parent.prop_legend_df[
                    parent.prop_legend_df["property_name"] == prop
                ].index
                parent.prop_legend_df.drop(idx_remove, inplace=True)

        # Reset dataframe index otherwise the TableWidget indexing can be messed up.
        parent.prop_legend_df.reset_index(drop=True, inplace=True)
        parent.prop_legend_df = ensure_property_legend_schema(parent.prop_legend_df)

        # Set up the PropertiesTableWidget.
        parent.PropertiesTableWidget.clear()
        parent.PropertiesTableWidget.setColumnCount(6)
        parent.PropertiesTableWidget.setRowCount(len(all_props))
        parent.PropertiesTableWidget.setHorizontalHeaderLabels(
            ["Property", "Colormap", "Preview", "Range", "Min", "Max"]
        )
        parent.PropertiesTableWidget.setColumnWidth(2, 200)

        for index, row in parent.prop_legend_df.iterrows():
            item = QTableWidgetItem(row["property_name"])
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            parent.PropertiesTableWidget.setItem(index, 0, item)

            cmap_combo_box = QComboBox()
            cmap_combo_box.addItems(self.colormaps_list)
            cmap_combo_box.setCurrentText(row["colormap"])
            cmap_combo_box.this_property = row["property_name"]
            cmap_combo_box.index = index
            parent.PropertiesTableWidget.setCellWidget(index, 1, cmap_combo_box)
            self._set_preview_label(parent=parent, index=index, cmap=row["colormap"])

            range_mode_combo_box = QComboBox()
            range_mode_combo_box.addItems(["Auto", "Manual"])
            range_mode_combo_box.this_property = row["property_name"]
            range_mode_combo_box.index = index
            parent.PropertiesTableWidget.setCellWidget(index, 3, range_mode_combo_box)

            range_min_spin_box = self._build_range_spin_box()
            range_min_spin_box.this_property = row["property_name"]
            range_min_spin_box.index = index
            range_min_spin_box.range_key = "range_min"
            parent.PropertiesTableWidget.setCellWidget(index, 4, range_min_spin_box)

            range_max_spin_box = self._build_range_spin_box()
            range_max_spin_box.this_property = row["property_name"]
            range_max_spin_box.index = index
            range_max_spin_box.range_key = "range_max"
            parent.PropertiesTableWidget.setCellWidget(index, 5, range_max_spin_box)

            cmap_combo_box.currentTextChanged.connect(
                lambda *, sender=cmap_combo_box: self.change_property_cmap(
                    sender=sender, parent=parent
                )
            )
            range_mode_combo_box.currentTextChanged.connect(
                lambda *, sender=range_mode_combo_box: self.change_property_range_mode(
                    sender=sender, parent=parent
                )
            )
            range_min_spin_box.editingFinished.connect(
                lambda sender=range_min_spin_box: self.change_property_range_value(
                    sender=sender, parent=parent
                )
            )
            range_max_spin_box.editingFinished.connect(
                lambda sender=range_max_spin_box: self.change_property_range_value(
                    sender=sender, parent=parent
                )
            )
            self._refresh_range_widgets(
                parent=parent, index=index, property_name=row["property_name"]
            )

        # Squeeze column width to fit content
        parent.PropertiesTableWidget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

    def change_property_cmap(self, sender=None, parent=None):
        new_cmap = str(sender.currentText())
        this_property = sender.this_property
        index = sender.index
        # Here the query is reversed and modified, dropping the values() method,
        # to allow SETTING the line thickness in the legend"
        parent.prop_legend_df.loc[
            parent.prop_legend_df["property_name"] == this_property, "colormap"
        ] = new_cmap

        self._set_preview_label(parent=parent, index=index, cmap=new_cmap)
        self._emit_property_style_changed(parent=parent, property_name=this_property)

    def change_property_range_mode(self, sender=None, parent=None):
        range_mode = str(sender.currentText()).strip().lower()
        this_property = sender.this_property
        index = sender.index

        parent.prop_legend_df.loc[
            parent.prop_legend_df["property_name"] == this_property, "range_mode"
        ] = range_mode

        if range_mode == "manual":
            auto_range = get_auto_property_range(parent=parent, property_name=this_property)
            if auto_range is None:
                auto_range = (0.0, 1.0)
            parent.prop_legend_df.loc[
                parent.prop_legend_df["property_name"] == this_property, "range_min"
            ] = float(auto_range[0])
            parent.prop_legend_df.loc[
                parent.prop_legend_df["property_name"] == this_property, "range_max"
            ] = float(auto_range[1])

        self._refresh_range_widgets(
            parent=parent, index=index, property_name=this_property
        )
        self._emit_property_style_changed(parent=parent, property_name=this_property)

    def change_property_range_value(self, sender=None, parent=None):
        this_property = sender.this_property
        index = sender.index
        prop_row = parent.prop_legend_df.loc[
            parent.prop_legend_df["property_name"] == this_property
        ]
        if prop_row.empty:
            return

        row = prop_row.iloc[0]
        if row["range_mode"] != "manual":
            self._refresh_range_widgets(
                parent=parent, index=index, property_name=this_property
            )
            return

        min_spin_box = parent.PropertiesTableWidget.cellWidget(index, 4)
        max_spin_box = parent.PropertiesTableWidget.cellWidget(index, 5)
        new_min = float(min_spin_box.value())
        new_max = float(max_spin_box.value())

        if not new_min < new_max:
            blocker = QSignalBlocker(sender)
            _ = blocker
            sender.setValue(getattr(sender, "last_valid_value", float(row[sender.range_key])))
            self._print_invalid_range(parent=parent, property_name=this_property)
            return

        parent.prop_legend_df.loc[
            parent.prop_legend_df["property_name"] == this_property, "range_min"
        ] = new_min
        parent.prop_legend_df.loc[
            parent.prop_legend_df["property_name"] == this_property, "range_max"
        ] = new_max

        self._refresh_range_widgets(
            parent=parent, index=index, property_name=this_property
        )
        self._emit_property_style_changed(parent=parent, property_name=this_property)
