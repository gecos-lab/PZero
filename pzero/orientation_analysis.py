"""orientation_analysis.py
PZero© Andrea Bistacchi"""

from numpy import cos as np_cos
from numpy import sin as np_sin
from numpy import deg2rad as np_deg2rad
from numpy import greater as np_greater
from numpy import less_equal as np_less_equal
from numpy import array as np_array
from numpy import asarray as np_asarray
from numpy import arange as np_arange
from numpy import cross as np_cross
from numpy import squeeze as np_squeeze
from numpy import sum as np_sum
from numpy import dot as np_dot
from numpy import argsort as np_argsort
from numpy import column_stack as np_column_stack
from numpy import vstack as np_vstack
from numpy import argmin as np_argmin
from numpy import where as np_where
from numpy import all as np_all
from numpy.linalg import norm as np_linalg_norm
from numpy.linalg import eigh as np_linalg_eigh
from numpy.linalg import det as np_linalg_det
from numpy.random import default_rng as np_random_default_rng
from numpy import ndarray as np_ndarray
from numpy import number as np_number

from scipy.spatial.distance import cdist
from scipy.cluster.vq import kmeans2

from pzero.helpers.helper_dialogs import multiple_input_dialog

from .helpers.helper_functions import freeze_gui_onoff, freeze_gui_on, freeze_gui_off

# -----IN THE FUTURE add functions for orientation analysis.-----


def strikes2dip_directions(strikes=None):
    """Convert Strike to Dip-Direction according to right-hand rule,
    all in degrees. Accepts single values, lists or Numpy arrays and
    returns the same types."""
    if isinstance(strikes, np_ndarray):
        strikes_array = strikes
        directions_array = (strikes_array + 90) * np_less_equal(strikes_array, 270) + (
            strikes_array - 270
        ) * np_greater(strikes_array, 270)
        directions = directions_array
        return directions
    elif isinstance(strikes, list):
        strikes_array = np_asarray(strikes)
        directions_array = (strikes_array + 90) * np_less_equal(strikes_array, 270) + (
            strikes_array - 270
        ) * np_greater(strikes_array, 270)
        directions = list(directions_array)
        return directions
    elif isinstance(strikes, (float, int)):
        if strikes <= 270:
            directions = strikes + 90
        else:
            directions = strikes - 270
        return directions
    else:
        print("Strike type not recognized")


def plunge_trends2lineations(plunges=None, trends=None):
    """Convert Plunge/Trend measurements in degrees (single or list)
    to lineation unit vectors pointing downwards if Plunge > 0.
    Accepts single values, lists or Numpy arrays and
    returns Numpy arrays."""
    if isinstance(plunges, (float, int, list, np_number)) and isinstance(
        trends, (float, int, list, np_number)
    ):
        plunges_array = np_asarray(plunges)
        trends_array = np_asarray(trends)
    elif isinstance(plunges, np_ndarray) and isinstance(trends, np_ndarray):
        plunges_array = plunges
        trends_array = trends
    else:
        print("Plunge/Trend type not recognized.")
    plunges_array = np_deg2rad(plunges_array)
    trends_array = np_deg2rad(trends_array)
    lineations = np_asarray(
        [
            np_sin(trends_array) * np_cos(plunges_array),
            np_cos(trends_array) * np_cos(plunges_array),
            -np_sin(plunges_array),
        ]
    )
    return lineations.T


def dip_directions2normals(dips=None, directions=None, return_dip_dir_vec=False):
    """Convert Dip/Direction measurements in degrees (single or list)
    to normal unit vectors pointing downwards if Dip > 0.
    Accepts single values, lists or Numpy arrays and
    returns Numpy arrays. We use np_squeeze to avoid having multi-dimensional arrays"""
    if isinstance(dips, (float, int, list)) and isinstance(
        directions, (float, int, list)
    ):
        dips_array = np_squeeze(np_asarray(dips))
        directions_array = np_squeeze(np_asarray(directions))
    elif isinstance(dips, np_ndarray) and isinstance(directions, np_ndarray):
        dips_array = np_squeeze(dips)
        directions_array = np_squeeze(directions)
    else:
        print("Dip/Direction type not recognized.")
    dips_array = np_squeeze(dips_array)
    directions_array = np_squeeze(directions_array)
    plunges_array = 90 - dips_array
    trends_array = (directions_array + 180) * np_less_equal(directions_array, 180) + (
        directions_array - 180
    ) * np_greater(directions_array, 180)
    normals = plunge_trends2lineations(plunges=plunges_array, trends=trends_array)

    return normals


def vset_set_normals(VertexSet=None, dip_name=None, dir_name=None):
    from .entities_factory import VertexSet

    dips_array = VertexSet.get_point_data(dip_name)
    dirs_array = VertexSet.get_point_data(dir_name)
    normals = dip_directions2normals(dips=dips_array, directions=dirs_array)
    VertexSet.init_point_data(data_key="Normals", dimension=3)
    VertexSet.set_point_data(data_key="Normals", attribute_matrix=normals)


@freeze_gui_onoff
def set_normals(self):
    """
    General function to set normals on different entities.
    It branches to other functions depending on the selected entity
    and aborts if the input entities are not homogeneous.
    """
    from .entities_factory import TriSurf, VertexSet, XsVertexSet, XsPolyLine

    # Check if some vtkPolyData is selected.
    if self.selected_uids:
        if self.shown_table == "tabGeology":
            # Case for VertexSet and XsVertexSet that alreadz have Dip and Direction properties.
            if isinstance(
                self.geol_coll.get_uid_vtk_obj(self.selected_uids[0]),
                (VertexSet, XsVertexSet),
            ):
                for uid in self.selected_uids:
                    if not isinstance(
                        self.geol_coll.get_uid_vtk_obj(uid), (VertexSet, XsVertexSet)
                    ):
                        self.print_terminal(
                            "Setting normals failed: all entities must be of the same type."
                        )
                        return
                # Choose Dip/Direction property names. If list is empty return.
                property_name_list = self.geol_coll.get_uid_properties_names(
                    uid=self.selected_uids[0]
                )
                if len(self.selected_uids) > 1:
                    for uid in self.selected_uids[1:]:
                        property_name_list = list(
                            set(property_name_list)
                            & set(self.geol_coll.get_uid_properties_names(uid=uid))
                        )
                if property_name_list == []:
                    return
                input_dict = {
                    "dip_name": ["Dip property: ", property_name_list],
                    "dir_name": ["Direction property: ", property_name_list],
                }
                updt_dict = multiple_input_dialog(
                    title="Select Dip/Direction property names", input_dict=input_dict
                )
                if updt_dict is None:
                    return
                # Now calculate Normals on each VTK object and append Normals to properties_names list.
                for uid in self.selected_uids:
                    self.geol_coll.append_uid_property(
                        uid=uid, property_name="Normals", property_components=3
                    )
                    vset_set_normals(
                        VertexSet=self.geol_coll.get_uid_vtk_obj(uid),
                        dip_name=updt_dict["dip_name"],
                        dir_name=updt_dict["dir_name"],
                    )
                    self.prop_legend.update_widget(self)
                    self.print_terminal("Normals set on vertex set " + uid)
                self.print_terminal("All Normals set.")
            # Case for TriSurf and XsPolyLine where Normal are calculated from geometry
            elif isinstance(
                self.geol_coll.get_uid_vtk_obj(self.selected_uids[0]),
                (TriSurf, XsPolyLine),
            ):
                self.print_terminal("Normals on TriSurf or XsPolyLine.")
                for uid in self.selected_uids:
                    if not isinstance(
                        self.geol_coll.get_uid_vtk_obj(uid), (TriSurf, XsPolyLine)
                    ):
                        self.print_terminal(
                            "Setting normals failed: all entities must be of the same type."
                        )
                        return
                for uid in self.selected_uids:
                    self.geol_coll.append_uid_property(
                        uid=uid, property_name="Normals", property_components=3
                    )
                    self.geol_coll.get_uid_vtk_obj(uid).vtk_set_normals()
                    self.prop_legend.update_widget(self)
                    self.print_terminal("Normals set on TriSurf or XsPolyLine" + uid)
                    obj = self.geol_coll.get_uid_vtk_obj(uid)
                    normals = obj.get_property("Normals")
                    # self.print_terminal(f"UID {uid}:")
                    # self.print_terminal("getproperties", normals)
                    # for n in normals:
                    #     self.print_terminal("Normals: X={0}, Y={1}, Z={2}".format(n[0], n[1], n[2]))

                self.print_terminal("All Normals set.")
            else:
                self.print_terminal(
                    "Only VertexSet, XsVertexSet, XsPolyLine and TriSurf entities can be processed."
                )

        elif self.shown_table == "tabDOMs":
            self.print_terminal("Calculating normals for Point Cloud")
            for uid in self.selected_uids:
                self.dom_coll.append_uid_property(
                    uid=uid, property_name="Normals", property_components=3
                )
                self.dom_coll.get_uid_vtk_obj(uid).vtk_set_normals()
                self.prop_legend.update_widget(self)
                # self.print_terminal(self.prop_legend_df)
            self.print_terminal("Done")
        else:
            self.print_terminal(
                "Normals can be calculated only on geological entities and Point Clouds (at the moment)."
            )
    else:
        self.print_terminal("No input data selected.")


def get_dip_dir_vectors(normals=None, az=False):
    if normals.ndim == 1:
        normals = np_array([normals])
    # normals[np_where(normals[:, 2] > 0)] *= -1
    dir_vectors = normals.copy()
    dir_vectors[:, 2] = 0
    dir_vectors[:, 0], dir_vectors[:, 1] = (
        normals[:, 1],
        -normals[:, 0],
    )  # direction is the az vector rotated clockwise by 90° around the Z axis
    dip_vectors = np_cross(normals, dir_vectors)
    if az:
        az_vectors = dip_vectors.copy()
        az_vectors[:, 2] = 0
        return az_vectors, dir_vectors
    else:
        return dip_vectors, dir_vectors


def fisherparams(samplecart, is_axial=False):
    """
    Calculate fisher parameters.

    Parameters
    ----------
    samplecart : ndarray, shape (N, 3)
        Sample of unit vectors on the sphere
    is_axial : bool, optional
        If True, vectors are resolved to the lower hemisphere before
        computing. Use for plane normals (axial data). Default False
        (polar/lineation data).

    Returns
    -------
    dict
        "mean_direction" : ndarray, shape (1, 3)
            Mean direction (unit vector), resolved to lower hemisphere.
        "kappa" : float
            Fisher concentration parameter.
    """
    samplecart = np_asarray(samplecart, dtype=float)

    if samplecart.ndim != 2 or samplecart.shape[1] != 3:
        raise ValueError("samplecart must have shape (N, 3)")

    if is_axial:
        samplecart = resolve_lower_hemisphere(samplecart)

    n = samplecart.shape[0]

    # Resultant vector
    Rvec = np_sum(samplecart, axis=0)
    R = np_linalg_norm(Rvec)

    if R == 0:
        raise ValueError("Resultant length is zero; mean direction undefined")

    # Mean direction
    muhat = Rvec / R

    # Mean resultant length
    Rbar = R / n

    # Fisher concentration estimate (sphstat formula)
    if Rbar < 0.9:
        kappahat = (3 * Rbar - Rbar**3) / (1 - Rbar**2)
    else:
        kappahat = 1.0 / (Rbar**3 - 4 * Rbar**2 + 3 * Rbar)

    axeshat = muhat.reshape(1, 3)

    # Enforce lower hemisphere on returned mean direction
    if axeshat[0, 2] > 0:
        axeshat = -axeshat

    return {"mean_direction": axeshat, "kappa": kappahat}


# def kentparams(samplecart, is_axial=False):
#     """
#     Calculate kents parameters.

#     Parameters
#     ----------
#     samplecart : ndarray, shape (N, 3)
#         Sample of unit vectors
#     is_axial : bool, optional
#         If True, vectors are resolved to the lower hemisphere before
#         computing. Use for plane normals (axial data). Default False
#         (polar/lineation data).

#     Returns
#     -------
#     dict
#         "axes": ndarray, shape (3, 3)
#             Orthonormal axes:
#             axes[0] = mean direction (mu), resolved to lower hemisphere.
#             axes[1] = major axis (gamma1)
#             axes[2] = minor axis (gamma2)
#         "kappa" : float
#             Kent concentration parameter
#         "beta" : float
#             Kent ovalness parameter
#     """
#     samplecart = np_asarray(samplecart, dtype=float)

#     if samplecart.ndim != 2 or samplecart.shape[1] != 3:
#         raise ValueError("samplecart must have shape (N, 3)")

#     if is_axial:
#         samplecart = resolve_lower_hemisphere(samplecart)

#     n = samplecart.shape[0]

#     # Scatter matrix
#     S = np_dot(samplecart.T, samplecart) / n

#     # Eigen-decomposition (symmetric matrix)
#     evals, evecs = np_linalg_eigh(S)

#     # Sort eigenvalues descending
#     idx = np_argsort(evals)[::-1]
#     evals = evals[idx]
#     evecs = evecs[:, idx]

#     # Axes: mean direction, major, minor
#     mu = evecs[:, 0]
#     gamma1 = evecs[:, 1]
#     gamma2 = evecs[:, 2]

#     # Enforce lower hemisphere on mean direction — eigh returns eigenvectors
#     # with arbitrary sign, so mu and -mu are equally valid mathematically.
#     # For consistent plotting, we resolve to the lower hemisphere here.
#     if mu[2] > 0:
#         mu = -mu
#         # Flip gamma1 too to keep the right-handed system consistent
#         gamma1 = -gamma1

#     # Enforce right-handed coordinate system
#     if np_linalg_det(np_column_stack((mu, gamma1, gamma2))) < 0:
#         gamma2 = -gamma2

#     axes = np_vstack((mu, gamma1, gamma2))

#     # Kent parameters (moment estimates)
#     kappahat = n * (evals[0] - evals[2])
#     betahat = n * (evals[1] - evals[2]) / 2.0

#     return {"axes": axes, "kappa": kappahat, "beta": betahat}


def bingham(samplecart, is_axial=False):
    """
    Calculate Bingham parameters.

    Parameters
    ----------
    samplecart : ndarray, shape (N, 3)
        Sample of unit vectors
    is_axial : bool, optional
        If True, vectors are resolved to the lower hemisphere before
        computing. Use for plane normals (axial data). Default False
        (polar/lineation data). Note: Bingham's orientation tensor is
        already sign-invariant, so is_axial has no effect on kappa/eigenvalues
        — it only affects the sign of returned eigenvectors.

    Returns
    -------
    dict
        "eigenvalues": ndarray, shape (3,)
            Eigenvalues
        "axes": ndarray, shape (3, 3)
            Orthonormal axes:
            axes[0] = major axis (mu), resolved to lower hemisphere.
            axes[1] = intermediate axis (gamma1)
            axes[2] = minor axis (gamma2)
    """
    samplecart = np_asarray(samplecart, dtype=float)

    if samplecart.ndim != 2 or samplecart.shape[1] != 3:
        raise ValueError("samplecart must have shape (N, 3)")

    if is_axial:
        samplecart = resolve_lower_hemisphere(samplecart)

    n = samplecart.shape[0]

    # Scatter matrix
    T = np_dot(samplecart.T, samplecart) / n

    # Bingham distribution parameters
    eigenvalues, eigenvectors = np_linalg_eigh(T)
    idx = np_argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Axes: major, intermediate, minor
    mu = eigenvectors[:, 0]
    gamma1 = eigenvectors[:, 1]
    gamma2 = eigenvectors[:, 2]

    # Enforce lower hemisphere on major axis — same reasoning as kentparams:
    # eigh sign is arbitrary, resolve for consistent plotting.
    if mu[2] > 0:
        mu = -mu
        gamma1 = -gamma1

    # Enforce right-handed coordinate system
    if np_linalg_det(np_column_stack((mu, gamma1, gamma2))) < 0:
        gamma2 = -gamma2

    axes = np_vstack((mu, gamma1, gamma2))

    return {"eigenvalues": eigenvalues, "axes": axes}


def kmeans_clusters(samplecart, k, seeds=None, is_axial=False):
    """
    Calculate k-means clusters.

    Parameters
    ----------
    samplecart : ndarray, shape (N, 3)
        Sample of unit vectors
    k : int
        Number of clusters to form
    seeds : ndarray, shape (k, 3), optional
        Initial centroids for k-means. If provided, used directly as starting
        points (minit='matrix'). If None, k-means++ initialization is used.
    is_axial : bool, optional
        If True, the data is treated as axial (e.g. plane normals). Vectors
        are first resolved to the lower hemisphere, then doubled by appending
        their antipodes before clustering. This prevents clusters that straddle
        the stereonet equator from being split into two phantom clusters.
        Only the labels for the original N vectors are returned.
        Default is False (polar/lineation data).

    Returns
    -------
    dict
        "centroids" : ndarray, shape (k, 3)
            Cluster centroids. Not guaranteed to be unit vectors — must be
            re-normalized before plotting as poles.
        "labels" : ndarray, shape (N,)
            Cluster index (0 to k-1) assigned to each input vector, in the
            same order as samplecart.
    """
    samplecart = np_asarray(samplecart, dtype=float)

    if samplecart.ndim != 2 or samplecart.shape[1] != 3:
        raise ValueError("samplecart must have shape (N, 3)")

    n = samplecart.shape[0]

    if k < 1:
        raise ValueError("k must be at least 1")

    if is_axial:
        samplecart_resolved = resolve_lower_hemisphere(samplecart)
        samplecart_input = double_axial(samplecart_resolved)
    else:
        samplecart_input = samplecart

    n_input = samplecart_input.shape[0]

    if k > n_input:
        raise ValueError(
            f"k ({k}) cannot be greater than the number of data points ({n_input})"
        )

    if seeds is not None:
        seeds = np_asarray(seeds, dtype=float)
        if seeds.shape != (k, 3):
            raise ValueError(f"seeds must have shape ({k}, 3), got {seeds.shape}")
        if is_axial:
            seeds_input = resolve_lower_hemisphere(seeds)
        else:
            seeds_input = seeds
        centroids, labels_input = kmeans2(samplecart_input, seeds_input, minit="matrix")
    else:
        centroids, labels_input = kmeans2(samplecart_input, k, minit="++")

    # For axial data, keep only labels for the original N vectors
    labels = labels_input[:n]

    return {"centroids": centroids, "labels": labels}


def kmedoids_clusters(samplecart, k, seeds=None, is_axial=False):
    """
    Calculate k-medoids clusters using the PAM algorithm.
    Unlike k-means, medoids are actual data points rather than arithmetic
    means, making them more appropriate for directional/spherical data where
    the mean of unit vectors is not itself a unit vector.

    Parameters
    ----------
    samplecart : ndarray, shape (N, 3)
        Sample of unit vectors
    k : int
        Number of clusters to form
    seeds : ndarray, shape (k, 3), optional
        Initial medoid vectors. Each seed is matched to its nearest actual
        data point, which becomes the initial medoid. If None, k random
        data points are chosen as initial medoids.
    is_axial : bool, optional
        If True, the data is treated as axial (plane normals) and doubled
        before clustering to prevent border-straddling splits. Only the
        labels for the original N vectors are returned. Default False.

    Returns
    -------
    dict
        "centroids" : ndarray, shape (k, 3)
            Medoid vectors — actual data points from samplecart, guaranteed
            to be unit vectors. Named "centroids" for interface compatibility
            with kmeans_clusters.
        "labels" : ndarray, shape (N,)
            Cluster index (0 to k-1) assigned to each input vector.
    """
    samplecart = np_asarray(samplecart, dtype=float)

    ### Clause guard part ###
    if samplecart.ndim != 2 or samplecart.shape[1] != 3:
        raise ValueError("samplecart must have shape (N, 3)")

    n = samplecart.shape[0]

    if k < 1:
        raise ValueError("k must be at least 1")

    if is_axial:
        samplecart_resolved = resolve_lower_hemisphere(samplecart)
        samplecart_input = double_axial(samplecart_resolved)
    else:
        samplecart_input = samplecart

    n_input = samplecart_input.shape[0]

    if k > n_input:
        raise ValueError(
            f"k ({k}) cannot be greater than the number of data points ({n_input})"
        )

    # Initialize medoid indices
    if seeds is not None:
        seeds = np_asarray(seeds, dtype=float)
        if seeds.shape[0] != k:
            raise ValueError(f"seeds must have shape (k, 3), got {seeds.shape}")
        # Match each seed to its nearest actual data point
        D_seeds = cdist(
            seeds, samplecart_input
        )  # If seed picking, initialize the medoid with the closest point
        medoid_indices = np_argmin(D_seeds, axis=1)  # for each seed
    else:
        rng = np_random_default_rng(42)  # If no seed picking, random pick
        medoid_indices = rng.choice(n_input, k, replace=False)

    # PAM update loop
    ### The actual loop that is the method ###
    for _ in range(300):  # 300 should be enough to converge
        D = cdist(
            samplecart_input, samplecart_input[medoid_indices]
        )  # Distance between all poles and the current medoids
        labels_input = np_argmin(D, axis=1)  # Find the nearest medoid for each point

        new_medoid_indices = medoid_indices.copy()
        for j in range(k):  # For each cluster j
            cluster_mask = labels_input == j  # Test if there are poles in that cluster
            if not cluster_mask.any():
                continue
            cluster_indices = np_where(cluster_mask)[
                0
            ]  # Take all the points assigned to that cluster
            D_cluster = cdist(
                samplecart_input[cluster_indices], samplecart_input[cluster_indices]
            )  # Distance between each points of that cluster
            best = cluster_indices[
                np_argmin(D_cluster.sum(axis=1))
            ]  # Sum each row giving total distance from point i to every other
            # points in the cluster and keep the smallest one
            new_medoid_indices[j] = best  # Make this point the new medoid

        if np_all(
            new_medoid_indices == medoid_indices
        ):  # If the medoid didn't changed, it converge, break the loop
            break
        medoid_indices = new_medoid_indices

    # Final assignment
    # For axial data, keep only labels for the original N vectors
    if is_axial:
        medoid_indices_resolved = np_where(
            medoid_indices >= n, medoid_indices - n, medoid_indices
        )

        seen = []
        used = set()
        all_indices = np_arange(n)
        for i, idx in enumerate(medoid_indices_resolved):
            if idx not in used:
                used.add(idx)
                seen.append(idx)
            else:
                # Find nearest unused data point to the original medoid
                unused = np_array([j for j in all_indices if j not in used])
                D_unused = cdist(
                    samplecart_input[idx : idx + 1], samplecart_input[unused]
                )
                replacement = unused[np_argmin(D_unused)]
                used.add(replacement)
                seen.append(replacement)
        medoid_indices_resolved = np_array(seen)

    else:
        medoid_indices_resolved = medoid_indices

    D = cdist(samplecart_input, samplecart_input[medoid_indices_resolved])
    labels_input = np_argmin(D, axis=1)

    # For axial data, keep only labels for the original N vectors
    ### That part is just because we doubled the data for planes ###
    labels = labels_input[:n]  # Label all the points to their cluster
    medoids = samplecart_input[medoid_indices_resolved]

    return {"centroids": medoids, "labels": labels}


def resolve_lower_hemisphere(vectors):
    """
    Ensure all unit vectors in the input array point into the lower hemisphere
    (Z <= 0), by flipping any vector with Z > 0. This is the standard
    preprocessing step for axial data (plane normals) before running statistics
    that assume directional data — it eliminates cancellation in resultant-vector
    sums and ensures consistent orientation across the dataset.

    Parameters
    ----------
    vectors : ndarray, shape (N, 3)
        Sample of unit vectors. Modified in-place is avoided by working on
        a copy — the input array is not altered.

    Returns
    -------
    ndarray, shape (N, 3)
        Same vectors, with any upward-pointing vectors flipped to point downward.
    """
    vectors = np_asarray(vectors, dtype=float)
    if vectors.ndim != 2 or vectors.shape[1] != 3:
        raise ValueError("vectors must have shape (N, 3)")
    resolved = vectors.copy()
    upward = resolved[:, 2] > 0
    resolved[upward] *= -1
    return resolved


def double_axial(vectors):
    """
    Double an axial dataset by appending the antipode of every vector.
    For a dataset of N unit vectors, returns a (2N, 3) array whose second
    half is the element-wise negation of the first half.

    This is used before running k-means on axial data (plane normals):
    by including both poles of every plane, clusters that straddle the
    equator of the stereonet are unified rather than split. After clustering,
    only the labels for the first N rows (the original vectors) are kept —
    the second N rows are discarded.

    Parameters
    ----------
    vectors : ndarray, shape (N, 3)
        Sample of unit vectors, already resolved to the lower hemisphere
        via resolve_lower_hemisphere before being passed here.

    Returns
    -------
    ndarray, shape (2N, 3)
        Original vectors stacked on top of their antipodes.
    """
    vectors = np_asarray(vectors, dtype=float)
    if vectors.ndim != 2 or vectors.shape[1] != 3:
        raise ValueError("vectors must have shape (N, 3)")
    return np_vstack([vectors, -vectors])
