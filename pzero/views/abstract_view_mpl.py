"""abstract_view_mpl.py
PZero© Andrea Bistacchi"""

# PZero imports____
from .abstract_base_view import BaseView

# Matplotlib imports____
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection


class ViewMPL(BaseView):
    """Abstract class used as a base for all classes using the Matplotlib plotting canvas."""

    def __init__(self, *args, **kwargs):
        """Incrementally initialize the ViewMPL intermediate-level class."""

        # Initialize dictionary to store reference to actors in the Matplotlib plot, with key = uid
        self.mpl_actors = dict()

        super(ViewMPL, self).__init__(*args, **kwargs)

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This method collects menus and actions in superclasses and then adds custom ones, specific to this view."""
        # append code from superclass
        super().initialize_menu_tools()

        # then add new code specific to this class

    # ================================  Methods required by BaseView(), (re-)implemented here =========================

    def closeEvent(self, event):
        """Override the standard closeEvent method by (i) disconnecting all signals and,
        (ii) closing the plotter for vtk windows."""
        self.enable_actions()
        self.disconnect_all_signals()
        event.accept()

    def get_actor_by_uid(self, uid: str = None):
        """
        Get an actor by uid in a Matplotlib plotter. Here we use self.plotter.renderer.actors
        that is a dictionary with key = uid string and value = actor (artist in MPL).
        """
        print(f"get_actor_by_uid: {uid}")
        return self.mpl_actors[uid]

    def get_uid_from_actor(self, actor=None):
        """
        Get the uid of an actor in a Matplotlib plotter. Here we use self.plotter.renderer.actors
        that is a dictionary with key = uid string and value = actor (artist in MPL).
        """
        # return next(
        #     key
        #     for key, value in self.mpl_actors.items()
        #     if value == this_actor
        # )
        uid = None
        for uid_i, actor_i in self.mpl_actors.items():
            if actor_i == actor:
                uid = uid_i
                break
        print(f"get_uid_from_actor: {uid}")
        return uid

    def actor_shown(self, uid: str = None):
        """Method to check if an actor is shown in a Matplotlib plotter. Returns a boolean."""
        # actors = self.plotter.renderer.actors
        # this_actor = actors[uid]
        # return this_actor.GetVisibility()
        print(f"actor_shown: {uid}")
        return self.mpl_actors[uid].visible()

    def show_actors(self, uids: list = None):
        """Method to show actors in uids list in a Matplotlib plotter."""
        actors = self.mpl_actors
        for uid, actor in actors.items():
            if uid in uids:
                actor.set_visible(True)
                print(f"show_actors: {uid}")

    def hide_actors(self, uids: list = None):
        """Method to hide actors in uids list in a Matplotlib plotter."""
        actors = self.mpl_actors
        for uid, actor in actors.items():
            if uid in uids:
                actor.set_visible(False)
                print(f"hide_actors: {uid}")

    def change_actor_color(self, uids: list=None, collection=None):
        """Change color for Matplotlib plots."""
        for uid in uids:
            print(f'changing actor color - uid: {uid} - collection: {collection}')
            # # refactor using a collection parameter instead of if - elif - else
            # if collection == "geol_coll":
            #     color_R = self.parent.geol_coll.get_uid_legend(uid=uid)["color_R"]
            #     color_G = self.parent.geol_coll.get_uid_legend(uid=uid)["color_G"]
            #     color_B = self.parent.geol_coll.get_uid_legend(uid=uid)["color_B"]
            #     color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            # elif collection == "xsect_coll":
            #     color_R = self.parent.xsect_coll.get_legend()["color_R"]
            #     color_G = self.parent.xsect_coll.get_legend()["color_G"]
            #     color_B = self.parent.xsect_coll.get_legend()["color_B"]
            #     color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            # else:
            #     return
            # if isinstance(self.mpl_actors[uid], Line2D):
            #     "Case for Line2D"
            #     self.mpl_actors[uid].set_color(color_RGB)
            #     self.mpl_actors[uid].figure.canvas.draw()
            #     print(f"change_actor_color: {uid}")

            if uid in self.uids_in_view:
                print('uid in view')
                # Get color from legend
                color_R = collection.get_uid_legend(uid=uid)["color_R"]
                color_G = collection.get_uid_legend(uid=uid)["color_G"]
                color_B = collection.get_uid_legend(uid=uid)["color_B"]
                color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                print(f'color_RGB: {color_RGB}')
                # Now update color for actor uid
                self.mpl_actors[uid].set_color(color_RGB)
                self.mpl_actors[uid].figure.canvas.draw()
            else:
                print('uid not in view')
                continue

    # ___________________________________________________________________________________
    def change_actor_opacity(self, uid=None, collection=None):
        """Update opacity for actor uid"""
        if uid in self.actors_df.uid:
            # _______________________________________________________________________
            # THIS COULD BE SIMPLIFIED IF A SUPER-CLASS TO COLLECTIONS IS IMPLEMENTED
            # _______________________________________________________________________
            if collection == "geol_coll":
                opacity = self.parent.geol_coll.get_uid_legend(uid=uid)["opacity"] / 100
            elif collection == "xsect_coll":
                opacity = self.parent.xsect_coll.get_legend()["opacity"] / 100
            elif collection == "boundary_coll":
                opacity = self.parent.boundary_coll.get_legend()["opacity"] / 100
            elif collection == "mesh3d_coll":
                opacity = self.parent.mesh3d_coll.get_legend()["opacity"] / 100
            elif collection == "dom_coll":
                opacity = self.parent.dom_coll.get_legend()["opacity"] / 100
            elif collection == "well_coll":
                opacity = self.parent.well_coll.get_uid_legend(uid=uid)["opacity"] / 100
            elif collection == "fluid_coll":
                opacity = (
                    self.parent.fluid_coll.get_uid_legend(uid=uid)["opacity"] / 100
                )
            elif collection == "backgrnd_coll":
                opacity = (
                    self.parent.backgrnd_coll.get_uid_legend(uid=uid)["opacity"] / 100
                )
            elif collection == "image_coll":
                opacity = self.parent.image_coll.get_legend()["opacity"] / 100
            # Now update color for actor uid
            # self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0].GetProperty().SetOpacity(opacity)
            self.get_actor_by_uid(uid).GetProperty().SetOpacity(opacity)
        else:
            return

    # ___________________________________________________________________________________
    def change_actor_line_thick(self, uid=None, collection=None):
        """Update line thickness for actor uid"""
        if uid in self.actors_df.uid:
            # _______________________________________________________________________
            # THIS COULD BE SIMPLIFIED IF A SUPER-CLASS TO COLLECTIONS IS IMPLEMENTED
            # _______________________________________________________________________
            if collection == "geol_coll":
                line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)["line_thick"]
            elif collection == "xsect_coll":
                line_thick = self.parent.xsect_coll.get_legend()["line_thick"]
            elif collection == "boundary_coll":
                line_thick = self.parent.boundary_coll.get_legend()["line_thick"]
            elif collection == "mesh3d_coll":
                line_thick = self.parent.mesh3d_coll.get_legend()["line_thick"]
            elif collection == "dom_coll":
                line_thick = self.parent.dom_coll.get_legend()["line_thick"]
            elif collection == "well_coll":
                line_thick = self.parent.well_coll.get_uid_legend(uid=uid)["line_thick"]
            elif collection == "fluid_coll":
                line_thick = self.parent.fluid_coll.get_uid_legend(uid=uid)[
                    "line_thick"
                ]
            elif collection == "backgrnd_coll":
                line_thick = self.parent.backgrnd_coll.get_uid_legend(uid=uid)[
                    "line_thick"
                ]
            # No thickness for image
            # Now update thickness for actor uid
            # self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0].GetProperty().SetLineWidth(line_thick)
            self.get_actor_by_uid(uid).GetProperty().SetLineWidth(line_thick)
        else:
            return

    # ___________________________________________________________________________________
    def change_actor_point_size(self, uid=None, collection=None):
        """Update point size for actor uid"""
        if uid in self.actors_df.uid:
            # _______________________________________________________________________
            # THIS COULD BE SIMPLIFIED IF A SUPER-CLASS TO COLLECTIONS IS IMPLEMENTED
            # _______________________________________________________________________
            if collection == "geol_coll":
                point_size = self.parent.geol_coll.get_uid_legend(uid=uid)["point_size"]
            elif collection == "xsect_coll":
                point_size = self.parent.xsect_coll.get_legend()["point_size"]
            elif collection == "boundary_coll":
                point_size = self.parent.boundary_coll.get_legend()["point_size"]
            elif collection == "mesh3d_coll":
                point_size = self.parent.mesh3d_coll.get_legend()["point_size"]
            elif collection == "dom_coll":
                point_size = self.parent.dom_coll.get_legend()["point_size"]
                """Note: no legend for image."""
            elif collection == "well_coll":
                point_size = self.parent.well_coll.get_uid_legend(uid=uid)["point_size"]
            elif collection == "fluid_coll":
                point_size = self.parent.fluid_coll.get_uid_legend(uid=uid)[
                    "point_size"
                ]
            elif collection == "backgrnd_coll":
                point_size = self.parent.backgrnd_coll.get_uid_legend(uid=uid)[
                    "point_size"
                ]
            # No thickness for image
            # Now update point size for actor uid
            # self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0].GetProperty().SetPointSize(point_size)
            self.get_actor_by_uid(uid).GetProperty().SetPointSize(point_size)
        else:
            return

    def set_actor_visible(self, uid=None, visible=None):
        """Set actor uid visible or invisible (visible = True or False)"""
        # The options below seem too much, and for instance contours are not toggled.
        # We keep them for future reference, but we use a simplera approach and see if it works.
        try:
            self.mpl_actors[uid].set_visible(visible)
            self.mpl_actors[uid].figure.canvas.draw()
        except:
            self.print_terminal(f"ERROR with set_actor_visible: {uid}")
        # if isinstance(self.mpl_actors[uid], Line2D):
        #     "Case for Line2D"
        #     self.mpl_actors[uid].set_visible(visible)
        #     self.mpl_actors[uid].figure.canvas.draw()
        #     print(f"set_actor_visible: {uid}")
        # elif isinstance(self.mpl_actors[uid], PathCollection):
        #     "Case for PathCollection -> ax.scatter"
        #     pass
        # # elif isinstance(self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0], TriContourSet):
        # #     "Case for TriContourSet -> ax.tricontourf"
        # #     pass
        # # elif isinstance(self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0], AxesImage):
        # #     "Case for AxesImage (i.e. images)"
        # #     # Hide other images if (1) they are shown and (2) you are showing another one.
        # #     for hide_uid in self.actors_df.loc[
        # #         (self.actors_df["collection"] == "image_coll")
        # #         & (self.actors_df["show"])
        # #         & (self.actors_df["uid"] != uid),
        # #         "uid",
        # #     ].to_list():
        # #         self.actors_df.loc[self.actors_df["uid"] == hide_uid, "show"] = False
        # #         self.actors_df.loc[self.actors_df["uid"] == hide_uid, "actor"].values[
        # #             0
        # #         ].set_visible(False)
        # #         row = self.ImagesTableWidget.findItems(hide_uid, Qt.MatchExactly)[
        # #             0
        # #         ].row()
        # #         self.ImagesTableWidget.item(row, 0).setCheckState(Qt.Unchecked)
        # #     # Then show this one.
        # #     self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
        # #         0
        # #     ].set_visible(visible)
        # #     self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
        # #         0
        # #     ].figure.canvas.draw()
        # else:
        #     "Do-nothing option to avoid errors, but it does not set/unset visibility."
        #     pass

    def remove_actor_in_view(self, uid=None, redraw=False):
        """ "Remove actor from plotter. Can remove a single entity or a list of
        entities as actors - here we remove a single entity"""

        if not self.mpl_actors[uid].empty:
            if self.mpl_actors[uid]:
                self.mpl_actors[uid].remove()
                print(f"remove_actor_in_view: {uid}")
                # the following should go in the abstract base view
                # self.actors_df.drop(
                #     self.actors_df[self.actors_df["uid"] == uid].index, inplace=True
                # )
            if redraw:
                # IN THE FUTURE check if there is a way to redraw just the actor that has just been removed.
                self.figure.canvas.draw()
