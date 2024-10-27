"""properties_manager.py
PZero© Andrea Bistacchi"""
from operator import index

import cmocean as cmo

import colorcet as cc

from matplotlib.pyplot import colormaps as plt_colormaps

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QTableWidgetItem, QLabel, QComboBox, QHeaderView

from numpy import linspace as np_linspace

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat
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
    colormap = pv_get_cmap_safe(cmap)  # maybe this is the problem with pyinstaller
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

    # List of all  matplotlib, colorcet, or cmocean colormaps used by PyVista
    # https://docs.pyvista.org/examples/02-plot/cmap.html
    colormaps_list = (
        plt_colormaps()
        + ["cet_" + cmap for cmap in list(cc.cm.keys())]
        + cmo.cm.cmapnames
    )

    def __init__(self, parent=None, *args, **kwargs):
        QObject.__init__(self, parent)

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
                if coll_prop_comps[i] == 3:
                    add_props = (
                        add_props
                        + [coll_props[i] + "[0]"]
                        + [coll_props[i] + "[1]"]
                        + [coll_props[i] + "[2]"]
                    )
                elif coll_prop_comps[i] == 1:
                    add_props = add_props + [coll_props[i]]

        if parent.well_coll.df["properties_names"].to_list():
            add_props.append("MD")

        add_props = list(set(add_props))  # a set is composed of unique values from a list
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
                parent.prop_legend_df = pd_concat([
                    parent.prop_legend_df,
                    pd_DataFrame([{"property_name": prop, "colormap": "rainbow"}])
                    ],
                    ignore_index=True)
        # The remove old ones no more used.
        for prop in parent.prop_legend_df["property_name"].to_list():
            if not prop in all_props:
                """Get index of row to be removed, then remove it in place with .drop()."""
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
            cmap_combo_box.addItems(self.colormaps_list)
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
        parent.PropertiesTableWidget.horizontalHeader().ResizeMode(QHeaderView.ResizeToContents)

    def change_property_cmap(self, sender=None, parent=None):
        # new_cmap = str(self.sender().currentText())
        # this_property = self.sender().this_property
        new_cmap = str(sender.currentText())
        this_property = sender.this_property
        index = sender.index
        row = sender.row
        # Here the query is reversed and modified, dropping the values() method,
        # to allow SETTING the line thickness in the legend"
        parent.prop_legend_df.loc[
            parent.prop_legend_df["property_name"] == this_property,
            "colormap"
        ] = new_cmap

        ## old solution
        # # this is to update the sender color - see if there is a simpler solution
        # self.update_widget(parent=parent)

        # this is to update the sender color
        label = QLabel()
        label.setPixmap(cmap2qpixmap(row["colormap"]))
        parent.PropertiesTableWidget.setCellWidget(index, 2, label)
        # Signal to update actors in windows. This is emitted only for the modified
        # uid under the 'line_thick' key.
        parent.prop_legend_cmap_modified_signal.emit(this_property)
