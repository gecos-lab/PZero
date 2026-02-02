"""abstract_view_mpl.py
PZero© Andrea Bistacchi"""

# PZero imports____
from .abstract_base_view import BaseView


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
        return self.mpl_actors[uid]

    def get_uid_from_actor(self, actor=None):
        """
        Get the uid of an actor in a Matplotlib plotter. Here we use self.plotter.renderer.actors
        that is a dictionary with key = uid string and value = actor (artist in MPL).
        """
        uid = None
        for uid_i, actor_i in self.mpl_actors.items():
            if actor_i == actor:
                uid = uid_i
                break
        return uid

    def actor_shown(self, uid: str = None):
        """Method to check if an actor is shown in a Matplotlib plotter. Returns a boolean."""
        return self.mpl_actors[uid].visible()

    def show_actors(self, uids: list = None):
        """Method to show actors in uids list in a Matplotlib plotter."""
        actors = self.mpl_actors
        for uid, actor in actors.items():
            if uid in uids:
                actor.set_visible(True)

    def hide_actors(self, uids: list = None):
        """Method to hide actors in uids list in a Matplotlib plotter."""
        actors = self.mpl_actors
        for uid, actor in actors.items():
            if uid in uids:
                actor.set_visible(False)

    def change_actor_color(self, updated_uids: list = None, collection=None):
        """Change color for Matplotlib plots."""
        for uid in updated_uids:
            if uid in self.uids_in_view:
                # Get color from legend
                color_R = collection.get_uid_legend(uid=uid)["color_R"]
                color_G = collection.get_uid_legend(uid=uid)["color_G"]
                color_B = collection.get_uid_legend(uid=uid)["color_B"]
                color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                # Now update color for actor uid
                self.mpl_actors[uid].set_color(color_RGB)
                self.mpl_actors[uid].figure.canvas.draw()
            else:
                continue

    def change_actor_opacity(self, updated_uids: list = None, collection=None):
        """Change opacity for actor uid"""
        for uid in updated_uids:
            if uid in self.uids_in_view:
                # Get color from legend
                opacity = collection.get_uid_legend(uid=uid)["opacity"] / 100
                # Now update color for actor uid
                self.mpl_actors[uid].set_alpha(opacity)
                self.mpl_actors[uid].figure.canvas.draw()
            else:
                continue

    def change_actor_line_thick(self, updated_uids: list = None, collection=None):
        """Change line thickness for actor uid"""
        for uid in updated_uids:
            if uid in self.uids_in_view:
                # Get color from legend
                line_thick = collection.get_uid_legend(uid=uid)["line_thick"]
                # Now update color for actor uid
                self.mpl_actors[uid].set_linewidth(line_thick)
                self.mpl_actors[uid].figure.canvas.draw()
            else:
                continue

    def change_actor_point_size(self, updated_uids: list = None, collection=None):
        """Change point size for actor uid"""
        for uid in updated_uids:
            if uid in self.uids_in_view:
                # Get color from legend
                point_size = collection.get_uid_legend(uid=uid)["point_size"]
                # Now update color for actor uid
                self.mpl_actors[uid].set_markersize(point_size)
                self.mpl_actors[uid].figure.canvas.draw()
            else:
                continue

    def set_actor_visible(self, uid=None, visible=None):
        """Set actor uid visible or invisible (visible = True or False)"""
        # The options below seem too much, and for instance contours are not toggled.
        # We keep them for future reference, but we use a simplera approach and see if it works.
        try:
            self.mpl_actors[uid].set_visible(visible)
            self.mpl_actors[uid].figure.canvas.draw()
        except:
            self.print_terminal(f"ERROR with set_actor_visible: {uid}")

    def remove_actor_in_view(self, uid=None, redraw=False):
        """ "Remove actor from plotter. Can remove a single entity or a list of
        entities as actors - here we remove a single entity"""

        if not self.mpl_actors[uid].empty:
            if self.mpl_actors[uid]:
                self.mpl_actors[uid].remove()
            if redraw:
                # IN THE FUTURE check if there is a way to redraw just the actor that has just been removed.
                self.figure.canvas.draw()
