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


from PySide6.QtCore import QObject
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QTableWidgetItem, QLabel, QComboBox, QHeaderView

from numpy import linspace as np_linspace

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat
from pandas import to_numeric as pd_to_numeric
from pandas.core.common import flatten as pd_flatten

from pyvista import get_cmap_safe as pv_get_cmap_safe


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


class PropertiesCMaps(QObject):
    """Properties legend manager."""

    # Dictionaries used to define types of legend columns.
    prop_cmap_dict = {
        "property_name": ["X", "Y", "Z"],
        "colormap": ["rainbow", "rainbow", "terrain"],
    }

    prop_cmap_dict_types = {"property_name": str, "colormap": str}

    # List of all matplotlib, colorcet, or cmocean colormaps used by PyVista
    # https://docs.pyvista.org/examples/02-plot/cmap.html
    base_colormaps_list = (
        ["seismic_pzero"]
        + plt_colormaps()
        + ["cet_" + cmap for cmap in list(cc.cm.keys())]
        + cmo.cm.cmapnames
    )

    custom_colormap_table_type = "colormap"
    custom_colormap_columns = ["value", "color_R", "color_G", "color_B"]

    def __init__(self, parent=None, *args, **kwargs):
        QObject.__init__(self, parent)

    @classmethod
    def _safe_register_cmap(cls, cmap=None):
        """Register a colormap across supported Matplotlib APIs."""
        if cmap is None:
            return

        cmap_name = getattr(cmap, "name", None)
        if not cmap_name:
            return

        try:
            if (
                hasattr(mpl, "colormaps")
                and hasattr(mpl.colormaps, "unregister")
            ):
                try:
                    mpl.colormaps.unregister(cmap_name)
                except Exception:
                    pass
            elif hasattr(cm, "unregister_cmap"):
                try:
                    cm.unregister_cmap(cmap_name)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if hasattr(mpl, "colormaps") and hasattr(mpl.colormaps, "register"):
                try:
                    mpl.colormaps.register(cmap=cmap)
                except TypeError:
                    mpl.colormaps.register(cmap)
            elif hasattr(plt, "register_cmap"):
                plt.register_cmap(name=cmap_name, cmap=cmap)
            elif hasattr(cm, "register_cmap"):
                cm.register_cmap(name=cmap_name, cmap=cmap)
        except ValueError:
            pass
        except Exception as exc:
            print(f"Warning: Colormap registration failed for {cmap_name}: {exc}")

    @classmethod
    def get_colormaps_list(cls, parent=None):
        """Return the full list of built-in and project custom colormaps."""
        colormap_names = list(cls.base_colormaps_list)
        if parent is not None:
            colormap_names.extend(cls.get_custom_colormap_names(parent=parent))
        return sorted(list(dict.fromkeys(colormap_names)))

    @classmethod
    def get_custom_colormap_names(cls, parent=None):
        """Return the names of custom colormap tables stored in the project."""
        if parent is None:
            return []

        custom_table_types = getattr(parent, "custom_table_types", {})
        return [
            table_name
            for table_name, table_type in custom_table_types.items()
            if table_type == cls.custom_colormap_table_type
        ]

    @classmethod
    def build_custom_colormap(cls, table_name=None, parent=None):
        """Build a matplotlib colormap from a custom colormap table."""
        if parent is None or not table_name:
            return None

        dataframe = getattr(parent, "custom_tables", {}).get(table_name, None)
        if dataframe is None or dataframe.empty:
            return None

        missing_columns = [
            column_name
            for column_name in cls.custom_colormap_columns
            if column_name not in dataframe.columns
        ]
        if missing_columns:
            return None

        working_df = dataframe[cls.custom_colormap_columns].copy()
        for column_name in cls.custom_colormap_columns:
            working_df[column_name] = pd_to_numeric(
                working_df[column_name], errors="coerce"
            )
        working_df.dropna(inplace=True)
        if len(working_df) < 2:
            return None

        working_df = working_df.sort_values(by="value").drop_duplicates(
            subset=["value"], keep="last"
        )
        if len(working_df) < 2:
            return None

        min_value = float(working_df["value"].min())
        max_value = float(working_df["value"].max())
        if max_value == min_value:
            return None

        mode = (
            getattr(parent, "custom_table_options", {})
            .get(table_name, {})
            .get("mode", "continuous")
        )

        normalized_positions = (
            (working_df["value"].astype(float) - min_value) / (max_value - min_value)
        ).tolist()
        color_rows = []
        for _, row in working_df.iterrows():
            color_rows.append(
                (
                    float(row["color_R"]) / 255.0,
                    float(row["color_G"]) / 255.0,
                    float(row["color_B"]) / 255.0,
                )
            )

        if mode == "discrete":
            step_stops = []
            total_rows = len(normalized_positions)
            for idx, position in enumerate(normalized_positions):
                rgb = color_rows[idx]
                if idx == 0:
                    step_stops.append((position, rgb))
                    continue
                epsilon = min(1e-6, max((position - normalized_positions[idx - 1]) / 10.0, 1e-9))
                step_stops.append((max(position - epsilon, 0.0), color_rows[idx - 1]))
                step_stops.append((position, rgb))
            cmap_stops = step_stops
        else:
            cmap_stops = list(zip(normalized_positions, color_rows))

        if not cmap_stops:
            return None

        return LinearSegmentedColormap.from_list(table_name, cmap_stops, N=256)

    @classmethod
    def register_custom_colormaps(cls, parent=None):
        """Register all custom colormaps available in the current project."""
        if parent is None:
            return

        for table_name in cls.get_custom_colormap_names(parent=parent):
            cmap = cls.build_custom_colormap(table_name=table_name, parent=parent)
            if cmap is not None:
                cls._safe_register_cmap(cmap=cmap)

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
        self.register_custom_colormaps(parent=parent)
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
                        pd_DataFrame([{"property_name": prop, "colormap": "rainbow"}]),
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

        # Set up the PropertiesTableWidget.
        parent.PropertiesTableWidget.clear()
        parent.PropertiesTableWidget.setColumnCount(3)
        parent.PropertiesTableWidget.setRowCount(len(all_props))
        parent.PropertiesTableWidget.setHorizontalHeaderLabels(
            list(self.prop_cmap_dict.keys()) + [""]
        )
        # parent.PropertiesTableWidget.setColumnWidth(1, 500)
        parent.PropertiesTableWidget.setColumnWidth(2, 200)

        for index, row in parent.prop_legend_df.iterrows():
            parent.PropertiesTableWidget.setItem(
                index, 0, QTableWidgetItem(row["property_name"])
            )
            cmap_combo_box = QComboBox()
            cmap_combo_box.addItems(self.get_colormaps_list(parent=parent))
            cmap_combo_box.setCurrentText(row["colormap"])
            cmap_combo_box.this_property = row["property_name"]
            cmap_combo_box.index = index
            cmap_combo_box.row = row
            parent.PropertiesTableWidget.setCellWidget(index, 1, cmap_combo_box)
            label = QLabel()
            label.setPixmap(cmap2qpixmap(row["colormap"]))
            parent.PropertiesTableWidget.setCellWidget(index, 2, label)
            cmap_combo_box.currentTextChanged.connect(
                lambda *, sender=cmap_combo_box: self.change_property_cmap(
                    sender=sender, parent=parent
                )
            )

        # Squeeze column width to fit content
        parent.PropertiesTableWidget.horizontalHeader().ResizeMode(
            QHeaderView.ResizeToContents
        )

    def change_property_cmap(self, sender=None, parent=None):
        new_cmap = str(sender.currentText())
        this_property = sender.this_property
        index = sender.index
        row = sender.row
        # Here the query is reversed and modified, dropping the values() method,
        # to allow SETTING the line thickness in the legend"
        parent.prop_legend_df.loc[
            parent.prop_legend_df["property_name"] == this_property, "colormap"
        ] = new_cmap

        # this is to update the sender color
        label = QLabel()
        label.setPixmap(cmap2qpixmap(new_cmap))
        parent.PropertiesTableWidget.setCellWidget(index, 2, label)
        # Signal to update actors in windows. This is emitted only for the modified
        # uid under the 'line_thick' key.
        parent.signals.prop_legend_cmap_modified.emit(this_property)
