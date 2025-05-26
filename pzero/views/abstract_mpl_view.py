"""abstract_mpl_view.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QAbstractItemView,
    QDockWidget,
    QSizePolicy,
    QMessageBox,
)

# PZero imports____
from .abstract_base_view import BaseView

# Matplotlib imports____
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# DO NOT USE import matplotlib.pyplot as plt  IT CREATES A DUPLICATE WINDOW IN NOTEBOOK
# from matplotlib.figure import Figure
# from matplotlib.offsetbox import TextArea
from matplotlib.lines import Line2D
from matplotlib.image import AxesImage
from matplotlib.collections import PathCollection
from matplotlib.tri import TriContourSet
import matplotlib.style as mplstyle



class MPLView(BaseView):
    """Abstract class used as a base for all classes using the Matplotlib plotting canvas."""

    def __init__(self, *args, **kwargs):
        super(MPLView, self).__init__(*args, **kwargs)
