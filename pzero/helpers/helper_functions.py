"""helper_functions.py
PZero© Andrea Bistacchi"""

from datetime import datetime

from os import path as os_path

from csv import Sniffer

from pandas import DataFrame as pd_DataFrame

from PIL import Image

from numpy import array as np_array
from numpy import corrcoef as np_corrcoef
from numpy import cos as np_cos
from numpy import cov as np_cov
from numpy import deg2rad as np_deg2rad
from numpy import dot as np_dot
from numpy import linalg as np_linalg
from numpy import mean as np_mean
from numpy import pi as np_pi
from numpy import sin as np_sin
from numpy import sqrt as np_sqrt
from numpy import square as np_square
from numpy import std as np_std
from numpy import sum as np_sum
from numpy import float32 as np_float32
from numpy import float64 as np_float64


def auto_sep(filename):
    with open(filename, "r") as IN:
        separator = Sniffer().sniff(IN.readline()).delimiter
    return separator


def profiler(path, iter):
    """Function used to profile the time needed to run a given function.

    The output is a text file in which each row corresponds the mean run time and std of functions.
    As a secondary output the profiler saves the raw differences in a separate csv file.
    This tool can be used as a decorator.

    Input:
        + path: Where to save the output files (in csv,txt or whatever)
        + iter: Number of iterations
    Output:
        + mean +- std time text file
        + raw data .csv file

    Usage:
    @profiler(path/to/output/file.*, n_iter)
    def func(foo):
    do some stuff"""

    root, base = os_path.split(path)
    diff_list = []

    def secondary(func):
        def inner(*args, **kwargs):
            title = func.__name__
            date = datetime.now()
            print(
                f"\n-------------------{title} PROFILING STARTED-------------------\n"
            )
            for i in range(iter):
                print(f"{i + 1} cycle of {iter}")
                start = datetime.now()
                res = func(*args, **kwargs)
                end = datetime.now()
                diff = (end - start).total_seconds()
                diff_list.append(diff)
                print(f"cycle {i + 1} completed. It took {diff} seconds")
            raw_time_diff = pd_DataFrame(diff_list, columns=["time diff [s]"])
            raw_time_diff.to_csv(
                os_path.join(
                    root, f'{title}_raw{date.strftime("%d_%m_%Y-%H%M%S")}.csv'
                ),
                sep=";",
                mode="w",
            )
            mean = np_mean(diff_list)
            std = np_std(diff_list)

            if os_path.exists(path):
                with open(path, "a") as f:
                    f.write(
                        f'{date.strftime("%d_%m_%Y-%H%M%S")};{title};{mean};{std};{iter};\n'
                    )
            else:
                with open(path, "a") as f:
                    f.write(
                        f"Rec. time;function title [-];mean [s];std [-];n of iterations[-];\n"
                    )
                    f.write(
                        f'{date.strftime("%d_%m_%Y-%H%M%S")};{title};{mean};{std};{iter};\n'
                    )
            print(
                f"Profiling finished in ~{mean * iter}s! The results are saved in the specified {root} directory"
            )
            print(f"\n-------------------{title} PROFILING ENDED-------------------\n")
            return res

        return inner

    return secondary


def angle_wrapper(angle):
    """Simple function to wrap a [pi;-pi] angle in [0;2pi]"""

    return angle % (2 * np_pi)


def PCA(data, correlation=False, sort=True):
    """PCA code taken from https://stackoverflow.com/a/38770513/19331382
    Applies Principal Component Analysis to the data

    Parameters
    ----------
    data: array
        The array containing the data. The array must have NxM dimensions, where each
        of the N rows represents a different individual record (point) and each of the M columns (xyz)
        represents a different variable recorded for that individual record.
            array([
            [V11, ... , V1m],
            ...,
            [Vn1, ... , Vnm]])

    correlation(Optional) : bool
            Set the type of matrix to be computed (see Notes):
                If True compute the correlation matrix.
                If False(Default) compute the covariance matrix.

    sort(Optional) : bool
            Set the order that the eigenvalues/vectors will have
                If True(Default) they will be sorted (from higher value to less).
                If False they won't.
    Returns
    -------
    eigenvalues: (1,M) array
    The eigenvalues of the corresponding matrix. -> max sum of the square distances

    eigenvector: (M,M) array
        The eigenvectors of the corresponding matrix.-> vector for the given PC axis

    Notes
    -----
    The correlation matrix is a better choice when there are different magnitudes
    representing the M variables. Use covariance matrix in other cases.

    """

    mean = np_mean(data, axis=0)

    data_adjust = data - mean  # center the points to the mean

    #: the data is transposed due to np.cov/corrcoef syntax
    if correlation:
        matrix = np_corrcoef(data_adjust.T)

    else:
        matrix = np_cov(data_adjust.T)

    eigenvalues, eigenvectors = np_linalg.eig(matrix)

    if sort:
        #: sort eigenvalues and eigenvectors
        sort = eigenvalues.argsort()[::-1]
        eigenvalues = eigenvalues[sort]
        eigenvectors = eigenvectors[:, sort]

    return eigenvalues, eigenvectors


def best_fitting_plane(points, equation=False):
    """code from https://stackoverflow.com/a/38770513/19331382
       Computes the best fitting plane of the given points

    Parameters
    ----------
    points: array
        The x,y,z coordinates corresponding to the points from which we want
        to define the best fitting plane. Expected format:
            array([
            [x1,y1,z1],
            ...,
            [xn,yn,zn]])

    equation(Optional) : bool
            Set the oputput plane format:
                If True return the a,b,c,d coefficients of the plane.
                If False(Default) return 1 Point and 1 Normal vector.
    Returns
    -------
    a, b, c, d : float
        The coefficients solving the plane equation.

    or

    point, normal: array
        The plane defined by 1 Point and 1 Normal vector. With format:
        array([Px,Py,Pz]), array([Nx,Ny,Nz])

    """

    points64 = np_float64(points)
    del points

    w, v = PCA(points64)

    #: the normal to the plane is the last eigenvector (lower correlation)
    normal = v[:, 2]

    #: get center point of the plane (mean)
    point = np_mean(points64, axis=0)

    if equation:
        a, b, c = normal
        d = -(np_dot(normal, point))
        return a, b, c, d

    else:
        return point, normal


def gen_frame(arr):
    """Function used to generate transparent PIL frames to create gifs.
    Code modified from https://stackoverflow.com/questions/46850318/transparent-background-in-gif-using-python-imageio
    """
    im = Image.fromarray(arr)
    alpha = im.getchannel("A")

    # Convert the image into P mode but only use 255 colors in the palette out of 256
    im = im.convert("RGBA").convert("P", palette=Image.ADAPTIVE, colors=255)

    # Set all pixel values below 128 to 255 , and the rest to 0
    mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)

    # Paste the color of index 255 and use alpha as a mask
    im.paste(255, mask)

    # The transparency index is 255
    im.info["transparency"] = 255

    return im


def rotate_vec_along(vector, axis, degrees):
    angle = np_deg2rad(degrees)
    if axis.lower() == "x":
        R = np_array(
            [
                [1, 0, 0],
                [0, np_cos(angle), -np_sin(angle)],
                [0, np_sin(angle), np_cos(angle)],
            ]
        )
    elif axis.lower() == "y":
        R = np_array(
            [
                [np_cos(angle), 0, np_sin(angle)],
                [0, 1, 0],
                [-np_sin(angle), 0, np_cos(angle)],
            ]
        )
    elif axis.lower() == "z":
        R = np_array(
            [
                [np_cos(angle), -np_sin(angle), 0],
                [np_sin(angle), np_cos(angle), 0],
                [0, 0, 1],
            ]
        )
    rot_vec = vector.dot(R)
    return rot_vec


def srf(vectors):
    n = len(vectors)
    x = np_sum(vectors[:, 0])
    y = np_sum(vectors[:, 1])
    z = np_sum(vectors[:, 2])

    result = np_sqrt(np_square(x) + np_square(y) + np_square(z)) / n

    return result


def _freeze_gui(self):
    """Disable actions and dock controls until the operation finishes."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractButton, QDockWidget

    self.disable_actions()
    project = getattr(self, "parent", None)
    if project is None or callable(project):
        project = self
    if (
        not hasattr(project, "findChildren")
        or getattr(project, "_active_interaction_view", None) is not None
    ):
        return
    project._active_interaction_view = self
    self._frozen_gui_project = project
    self._frozen_dock_buttons = []
    for dock in project.findChildren(QDockWidget):
        for name in ("qt_dockwidget_closebutton", "qt_dockwidget_floatbutton"):
            button = dock.findChild(QAbstractButton, name, Qt.FindDirectChildrenOnly)
            if button is not None:
                self._frozen_dock_buttons.append((button, button.isEnabled()))
                button.setEnabled(False)
    _install_escape_handler(self, project)


def set_escape_callback(self, callback):
    """Set the active tool's finish action for the decorator's Escape handler."""
    self._escape_callback = callback


def _install_escape_handler(self, project):
    """Protect docks and handle Escape while a freeze decorator is active."""
    from PySide6.QtCore import QEvent, QObject, Qt
    from PySide6.QtWidgets import QApplication, QDockWidget, QWidget

    app = QApplication.instance()
    if app is None:
        return
    self._escape_callback = None

    class EscapeFilter(QObject):
        def finish(filter_self):
            try:
                while getattr(self, "_escape_callback", None) is not None:
                    callback = self._escape_callback
                    self._escape_callback = None
                    callback()
            finally:
                if (
                    getattr(self, "_frozen_gui_project", None) is project
                    and getattr(self, "_escape_filter", None) is filter_self
                ):
                    freeze_gui_off(self)

        def eventFilter(filter_self, obj, event):
            if not isinstance(obj, QWidget):
                return False
            widget = obj
            while widget is not None and widget is not project:
                widget = QObject.parent(widget)
            if widget is None:
                return False
            if isinstance(obj, QDockWidget):
                if event.type() == QEvent.Close:
                    event.ignore()
                    return True
                if (
                    event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick)
                    and obj.widget() is not None
                    and not obj.widget().geometry().contains(event.position().toPoint())
                ):
                    return True
            if (
                event.type() != QEvent.KeyPress
                or event.key() != Qt.Key_Escape
                or app.activeModalWidget() is not None
                or getattr(self, "_escape_callback", None) is None
            ):
                return False
            filter_self.finish()
            return True

    self._escape_filter = EscapeFilter()
    app.installEventFilter(self._escape_filter)


def freeze_gui_on(func):
    """Decorator function used to start GUI freeze."""

    def wrapper(self, *args, **kwargs):
        # Disable GUI before function is called.
        _freeze_gui(self)
        # the wrapped function goes here, with try-except to avoid crashes
        try:
            print(f"Function {func} started.")
            func(self, *args, **kwargs)
            print(f"Function {func} ended successfully.")
        except Exception:
            self.print_terminal(f"Function {func} cannot be started.")
            freeze_gui_off(self)

    return wrapper


def freeze_gui_off(self):
    """Function used to unfreeze the GUI, in combination with freeze_gui_on."""
    from PySide6.QtWidgets import QApplication

    escape_filter = getattr(self, "_escape_filter", None)
    if escape_filter is not None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(escape_filter)
        self._escape_filter = None
    self._escape_callback = None
    project = getattr(self, "_frozen_gui_project", None)
    if project is not None and getattr(project, "_active_interaction_view", None) is self:
        project._active_interaction_view = None
        for button, enabled in self._frozen_dock_buttons:
            try:
                button.setEnabled(enabled)
            except RuntimeError:
                pass  # The dock was deleted while the project was closing.
        self._frozen_dock_buttons = []
        self._frozen_gui_project = None
    self.enable_actions()


def freeze_gui_onoff(func):
    """Decorator function used to freeze and then unfreeze the GUI when some processing, editing etc. is running."""

    def wrapper(self, *args, **kwargs):
        # Disable GUI before function is called.
        _freeze_gui(self)
        # the wrapped function goes here, with try-except to avoid crashes
        result = None
        try:
            print(f"Function {func} started.")
            result = func(self, *args, **kwargs)
            print(f"Function {func} ended successfully.")
        except Exception:
            self.print_terminal(f"Function {func} cannot be started.")
        # Enable GUI after function is called.
        freeze_gui_off(self)
        return result

    return wrapper
