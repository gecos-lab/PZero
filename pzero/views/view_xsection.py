"""view_xsection.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtGui import QAction

# numpy import____
from numpy import array as np_array

# PyVista imports____
from pyvista import Arrow as pv_Arrow

# PZero imports____
from .abstract_view_2d import View2D
from vtkmodules.vtkFiltersCore import vtkAppendPolyData
from pyvista import Line as pv_Line
from .view_map import ViewMap
from ..helpers.helper_functions import freeze_gui_onoff
from ..orientation_analysis import get_dip_dir_vectors
from ..helpers.helper_dialogs import (
    input_combo_dialog,
    message_dialog,
    options_dialog,
    input_checkbox_dialog,
)


class ViewXsection(View2D):
    def __init__(self, parent=None, *args, **kwargs):
        # Choose section name with dialog.
        if parent.xsect_coll.get_names:
            self.this_x_section_name = input_combo_dialog(
                parent=None,
                title="Xsection",
                label="Choose Xsection",
                choice_list=parent.xsect_coll.get_names,
            )
        else:
            message_dialog(title="Xsection", message="No Xsection in project")
            return
        # Select section uid from name.
        if self.this_x_section_name:
            self.this_x_section_uid = parent.xsect_coll.df.loc[
                parent.xsect_coll.df["name"] == self.this_x_section_name, "uid"
            ].values[0]
        else:
            return
        # Set a filter for entities belonging to this cross-section.
        # Note that in past releases this filter was not returning the cross-section itself.
        # This is now fixed since cross-sections have their own uid as parent_uid.
        self.view_filter = (
            f'parent_uid.str.contains("{self.this_x_section_uid}", na=False)'
        )

        # Super here after having set the x_section_uid and _name
        super(ViewXsection, self).__init__(parent, *args, **kwargs)
        self.parent = parent
        # self.parent.signals.selection_changed.connect(self.on_selection_changed)

        # Rename Base View, Menu and Tool
        self.setWindowTitle(f"Xsection View: {self.this_x_section_name}")

        # Store center and direction in internal variables of this view
        self.set_section_projection()

    # Update the views depending on the sec_uid. We need to redefine the functions to use
    # the sec_uid parameter for the update_dom_list_added func. We just need the x_added_x
    # functions because the x_removed_x works on an already built/modified tree.

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This method collects menus and actions in superclasses and then adds custom ones, specific to this view."""
        # append code from superclass
        super().initialize_menu_tools()

        # then add new code specific to this class
        self.horizMirrorButton = QAction("Mirror horizontal axes", self)
        self.horizMirrorButton.triggered.connect(self.horizontal_mirror)
        self.menuView.addAction(self.horizMirrorButton)

        self.fitFrameButton = QAction("Fit frame to all entities", self)
        self.fitFrameButton.triggered.connect(self.fit_frame)
        self.menuModify.addAction(self.fitFrameButton)

        self.switchPscAreasButton = QAction("Switch PSC areas", self)
        self.switchPscAreasButton.triggered.connect(self.switch_psc_areas)
        self.menuModify.addAction(self.switchPscAreasButton)

        self.buildPscSectionAreasButton = QAction("Build PSC section areas", self)
        self.buildPscSectionAreasButton.triggered.connect(
            self.build_psc_section_areas
        )
        self.menuCreate.addAction(self.buildPscSectionAreasButton)

    def build_psc_section_areas(self):
        """Build PSC-derived seeds and filled areas for the active Xsection."""
        from ..pymeshit_app.PiecewiseStructuralComplex import (
            TwoDPiecewiseStructuralComplex,
        )

        TwoDPiecewiseStructuralComplex(self).open_section_areas_dialog()

    def switch_psc_areas(self):
        """Switch role/feature assignments between two selected PSC area classes."""
        geol_coll = getattr(self.parent, "geol_coll", None)
        if geol_coll is None:
            return

        selected_uids = self._selected_geology_uids()
        if not selected_uids:
            return self._switch_psc_fail(
                "Select PSC area polygons before using Switch PSC areas."
            )

        area_uids = []
        rejected_uids = []
        for uid in selected_uids:
            if uid not in geol_coll.get_uids:
                rejected_uids.append(uid)
                continue
            try:
                topology = geol_coll.get_uid_topology(uid)
                name = geol_coll.get_uid_name(uid)
                parent_uid = geol_coll.get_uid_x_section(uid)
            except Exception:
                rejected_uids.append(uid)
                continue
            if (
                topology == "TriSurf"
                and "PSC_area_" in str(name or "")
                and self.this_x_section_uid in str(parent_uid or "")
            ):
                area_uids.append(uid)
            else:
                rejected_uids.append(uid)

        if rejected_uids:
            return self._switch_psc_fail(
                "Switch PSC areas accepts selected PSC area polygons only. "
                f"Rejected {len(rejected_uids)} selected item(s)."
            )
        if len(area_uids) < 2:
            return self._switch_psc_fail(
                "Select at least two PSC area polygons to switch."
            )

        combos = []
        for uid in area_uids:
            combo = (
                str(geol_coll.get_uid_role(uid) or ""),
                str(geol_coll.get_uid_feature(uid) or ""),
            )
            if combo not in combos:
                combos.append(combo)
        if len(combos) != 2:
            return self._switch_psc_fail(
                "Switch PSC areas requires exactly two role/feature classes."
            )

        switch_map = {combos[0]: combos[1], combos[1]: combos[0]}
        updated_uids = []
        linked_seed_count = 0
        for area_uid in area_uids:
            old_combo = (
                str(geol_coll.get_uid_role(area_uid) or ""),
                str(geol_coll.get_uid_feature(area_uid) or ""),
            )
            new_role, new_feature = switch_map[old_combo]
            if self._switch_psc_entity_metadata(area_uid, new_role, new_feature):
                updated_uids.append(area_uid)

            for seed_uid in self._linked_psc_seed_uids(area_uid):
                if self._switch_psc_entity_metadata(seed_uid, new_role, new_feature):
                    updated_uids.append(seed_uid)
                    linked_seed_count += 1

        if not updated_uids:
            return
        geol_coll.modelReset.emit()
        geol_coll.attr_modified_update_legend_table()
        self.parent.signals.metadata_modified.emit(updated_uids, geol_coll)
        self.print_terminal(
            f"Switched PSC assignments for {len(area_uids)} area(s) "
            f"and {linked_seed_count} linked seed(s)."
        )
        self.clear_selection()

    def _switch_psc_fail(self, message: str) -> None:
        self.print_terminal(message)
        self.clear_selection()

    def _selected_geology_uids(self) -> list:
        selected_uids = []
        for uid in getattr(self, "selected_uids", []) or []:
            if uid not in selected_uids:
                selected_uids.append(uid)
        for uid in getattr(self.parent, "selected_uids", []) or []:
            if uid not in selected_uids:
                selected_uids.append(uid)
        return selected_uids

    def _switch_psc_entity_metadata(
        self,
        uid: str,
        new_role: str,
        new_feature: str,
    ) -> bool:
        geol_coll = self.parent.geol_coll
        if uid not in geol_coll.get_uids:
            return False
        old_role = str(geol_coll.get_uid_role(uid) or "")
        old_feature = str(geol_coll.get_uid_feature(uid) or "")
        old_name = str(geol_coll.get_uid_name(uid) or uid)
        geol_coll.set_uid_role(uid=uid, role=new_role)
        geol_coll.set_uid_feature(uid=uid, feature=new_feature)
        geol_coll.set_uid_name(
            uid=uid,
            name=f"Switched from {old_role}/{old_feature} - {old_name}",
        )
        return True

    def _linked_psc_seed_uids(self, area_uid: str) -> list:
        geol_coll = self.parent.geol_coll
        linked_uids = []
        for uid in geol_coll.get_uids:
            try:
                if geol_coll.get_uid_topology(uid) != "XsVertexSet":
                    continue
                if "PSC_seed_" not in str(geol_coll.get_uid_name(uid) or ""):
                    continue
                parent_tokens = self._parent_uid_tokens(
                    geol_coll.get_uid_x_section(uid)
                )
            except Exception:
                continue
            if area_uid in parent_tokens:
                linked_uids.append(uid)
        return linked_uids

    @staticmethod
    def _parent_uid_tokens(parent_uid) -> list:
        text = str(parent_uid or "")
        for separator in (";", ",", "|"):
            text = text.replace(separator, " ")
        return [token.strip() for token in text.split() if token.strip()]

    # # --- AGGIUNTA: funzione di slot per sincronizzazione selezione ---
    # def on_selection_changed(self, collection):
    #     print("DEBUG SLOT: selection_changed ricevuto per collection:", collection)
    #     self.selected_uids = collection.selected_uids.copy()
    #     self.actor_in_table(self.selected_uids)

    # ================================  Methods required by ViewVTK(), (re-)implemented here ==========================

    def set_orientation_widget(self):
        self.plotter.add_orientation_widget(
            pv_Arrow(direction=(0.0, 1.0, 0.0), scale=0.3),
            interactive=None,
            color="gold",
        )

    # ================================  Methods specific to Xsection views ============================================

    def set_section_projection(
        self,
    ):  # Store center and direction in internal variables of this view
        section_plane = self.parent.xsect_coll.get_uid_vtk_plane(
            self.this_x_section_uid
        )
        self.center = np_array(section_plane.GetOrigin())
        self.direction = np_array(section_plane.GetNormal())
        # Apply to plotter
        self.plotter.camera.focal_point = self.center
        self.plotter.camera.position = self.center + self.direction
        self.plotter.reset_camera()

    def horizontal_mirror(self):
        """Mirror horizontal axes."""
        self.print_terminal("Mirroring horizontal axes.")
        # Mirror internal variable used to store direction
        self.direction = -self.direction
        # Apply to plotter
        self.plotter.camera.focal_point = self.center
        self.plotter.camera.position = self.center + self.direction
        self.plotter.reset_camera()

    def fit_frame(self):
        """
        Fit frame to all entities in view.
        At the momento only the "parallel" method is implemented.
        """
        opt_dialog = input_checkbox_dialog(
            title="title",
            label="label",
            choice_list=[
                "Fit cross-section frame only",
                "Fit vertical cross-section plane and frame",
                "Fit dipping cross-section plane and frame",
            ],
            exclusive=True,
        )
        if not opt_dialog:
            return
        opt_dialog = opt_dialog[0]  # Extract the first element from the list

        if opt_dialog == "Fit cross-section frame only":
            fit_method = "frame"
        elif opt_dialog == "Fit vertical cross-section plane and frame":
            fit_method = "vertical"
        elif opt_dialog == "Fit dipping cross-section plane and frame":
            fit_method = "dipping"
        else:
            return
        print("Fitting frame. ", fit_method)
        # Run the fitting method with parallel option
        self.parent.xsect_coll.fit_to_entities(
            xuid=self.this_x_section_uid, fit_method=fit_method
        )
        # Re-set the section projection
        self.set_section_projection()

        self.print_terminal("...fitting completed.")
