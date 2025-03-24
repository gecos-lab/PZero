"""helper_functions.py
PZero© Andrea Bistacchi"""

import datetime

import os

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

    root, base = os.path.split(path)
    diff_list = []

    def secondary(func):
        def inner(*args, **kwargs):
            title = func.__name__
            date = datetime.datetime.now()
            print(
                f"\n-------------------{title} PROFILING STARTED-------------------\n"
            )
            for i in range(iter):
                print(f"{i + 1} cycle of {iter}")
                start = datetime.datetime.now()
                res = func(*args, **kwargs)
                end = datetime.datetime.now()
                diff = (end - start).total_seconds()
                diff_list.append(diff)
                print(f"cycle {i + 1} completed. It took {diff} seconds")
            raw_time_diff = pd_DataFrame(diff_list, columns=["time diff [s]"])
            raw_time_diff.to_csv(
                os.path.join(
                    root, f'{title}_raw{date.strftime("%d_%m_%Y-%H%M%S")}.csv'
                ),
                sep=";",
                mode="w",
            )
            mean = np_mean(diff_list)
            std = np_std(diff_list)

            if os.path.exists(path):
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

    w, v = PCA(points)

    #: the normal to the plane is the last eigenvector (lower correlation)
    normal = v[:, 2]

    #: get center point of the plane (mean)
    point = np_mean(points, axis=0)

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


def freeze_gui(func):
    """Decorator function used to freeze the GUI when some processing, editing etc. is running."""
    def wrapper(self, *args, **kwargs):
        # Disable GUI before function is called.
        self.disable_actions()
        # the wrapped function goes here, with try-except to avoid crashes
        try:
            func(self, *args, **kwargs)
        except:
            self.print_terminal(f'Function {func} ended without output.')
        # Enable GUI after function is called.
        self.enable_actions()
    return wrapper
