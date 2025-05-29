"""abstract_view_mpl.py
PZero© Andrea Bistacchi"""

# PZero imports____
from .abstract_base_view import BaseView

# Matplotlib imports____ currently not used here
#
# Background color for matplotlib plots, it could be made interactive in the future.
# import matplotlib.style as mplstyle
# mplstyle.use("default")
# mplstyle.use("dark_background")
# 'fast' is supposed to make plotting large objects faster.
# mplstyle.use(["dark_background", "fast"])
#
# from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
# class NavigationToolbar(NavigationToolbar2QT):
#     """Customize NavigationToolbar2QT used in matplotlib to display only the buttons we need.
#     Note that toolitems is a class variable defined before __init__."""
#
#     toolitems = [
#         t
#         for t in NavigationToolbar2QT.toolitems
#         if t[0] in ("Home", "Pan", "Zoom", "Save")
#     ]
#
#     def __init__(self, parent=None, *args, **kwargs):
#         super(NavigationToolbar, self).__init__(parent, *args, **kwargs)


class ViewMPL(BaseView):
    """Abstract class used as a base for all classes using the Matplotlib plotting canvas."""

    def __init__(self, *args, **kwargs):
        super(ViewMPL, self).__init__(*args, **kwargs)
