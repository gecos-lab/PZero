"""
Isomap-based Geodesic Unfolding for Complex Folded Surfaces.

This module provides robust parameterization for recumbent, overturned, and
tightly folded geological surfaces where standard 2D projection fails.

The approach:
1. Use Isomap (geodesic distances + MDS) to unfold the 3D surface into 2D
2. Perform Constrained Delaunay Triangulation (CDT) in the parameterized 2D space
3. Map the mesh topology back to 3D using IDW interpolation for Steiner points

This method preserves all constraint segments and produces watertight meshes
even on complex fold geometries.
"""

import numpy as np
import logging
import time
from typing import Optional, Tuple, Dict, List, Any
from scipy.spatial import ConvexHull, cKDTree
from scipy.spatial.distance import pdist

logger = logging.getLogger("MeshIt-Workflow")


class IsomapTriangulator:
    """
    Geodesic Unfolding triangulator using Isomap parameterization.
    
    This class handles complex folded surfaces (recumbent/overturned folds)
    by unrolling them into 2D using geodesic distances, then performing
    standard CDT operations before mapping back to 3D.
    
    Attributes:
        n_neighbors (int): Number of neighbors for Isomap graph construction.
        n_components (int): Target dimensionality (always 2 for surface unfolding).
        isomap_model: Fitted sklearn Isomap model.
        points_3d (np.ndarray): Original 3D points.
        points_2d (np.ndarray): Isomap-transformed 2D points.
        point_map_3d_to_2d (dict): Mapping from 3D point indices to 2D coordinates.
    """
    
    def __init__(self, n_neighbors: int = 15, gradient: float = 2.0, 
                 min_angle: float = 20.0, base_size: Optional[float] = None):
        """
        Initialize the IsomapTriangulator.
        
        Args:
            n_neighbors: Number of neighbors for Isomap (default: 15).
                         Higher values = smoother unfolding but may miss tight folds.
                         Lower values = better fold detail but may disconnect.
            gradient: Mesh gradient control parameter.
            min_angle: Minimum triangle angle for quality control.
            base_size: Target edge length for triangulation.
        """
        self.n_neighbors = n_neighbors
        self.n_components = 2  # Always unfold to 2D
        self.gradient = gradient
        self.min_angle = min_angle
        self.base_size = base_size
        
        self.isomap_model = None
        self.points_3d = None
        self.points_2d = None
        self._fitted = False
        
        # KDTree for fast 3D->2D lookups
        self._tree_3d = None
        self._tree_2d = None
        
        logger.info(f"IsomapTriangulator initialized with n_neighbors={n_neighbors}")
    
    def fit(self, points_3d: np.ndarray) -> 'IsomapTriangulator':
        """
        Fit the Isomap model to the 3D point cloud.
        
        This computes the geodesic unfolding from 3D to 2D.
        
        Args:
            points_3d: (N, 3) array of 3D surface points.
            
        Returns:
            self: For method chaining.
            
        Raises:
            ValueError: If points are insufficient or degenerate.
        """
        try:
            from sklearn.manifold import Isomap
        except ImportError:
            raise ImportError(
                "sklearn is required for Isomap unfolding. "
                "Install with: pip install scikit-learn"
            )
        
        points_3d = np.asarray(points_3d, dtype=np.float64)
        
        if points_3d.ndim != 2 or points_3d.shape[1] != 3:
            raise ValueError("points_3d must have shape (N, 3)")
        
        n_points = len(points_3d)
        if n_points < 4:
            raise ValueError(f"Need at least 4 points for Isomap, got {n_points}")
        
        # Adaptively adjust n_neighbors if we have few points
        effective_neighbors = min(self.n_neighbors, n_points - 1)
        if effective_neighbors < 3:
            effective_neighbors = min(3, n_points - 1)
        
        logger.info(f"Fitting Isomap with {n_points} points, n_neighbors={effective_neighbors}")
        
        # Store original points
        self.points_3d = points_3d.copy()
        
        # Build 3D KDTree for lookups
        self._tree_3d = cKDTree(self.points_3d)
        
        # Fit Isomap
        fit_start = time.perf_counter()
        try:
            self.isomap_model = Isomap(
                n_neighbors=effective_neighbors,
                n_components=self.n_components,
                metric='euclidean',
                p=2,
                neighbors_algorithm='kd_tree',
                n_jobs=-1,
                eigen_solver='arpack',
                path_method='D'
            )
            self.points_2d = self.isomap_model.fit_transform(self.points_3d)
            
        except Exception as e:
            logger.error(f"Isomap fitting failed: {e}")
            # Fallback: Use PCA projection
            logger.warning("Falling back to PCA projection")
            self.points_2d = self._pca_fallback(self.points_3d)
        
        # Build 2D KDTree for interpolation
        self._tree_3d = cKDTree(self.points_3d)
        self._tree_2d = cKDTree(self.points_2d)
        
        self._fitted = True
        logger.info(f"Isomap fit complete in {time.perf_counter() - fit_start:.3f}s. 2D point range: "
                   f"X=[{self.points_2d[:,0].min():.2f}, {self.points_2d[:,0].max():.2f}], "
                   f"Y=[{self.points_2d[:,1].min():.2f}, {self.points_2d[:,1].max():.2f}]")
        
        return self

    def _pca_fallback(self, points_3d: np.ndarray) -> np.ndarray:
        """
        PCA-based 2D projection as fallback when Isomap fails.
        
        Args:
            points_3d: (N, 3) array of 3D points.
            
        Returns:
            (N, 2) array of projected 2D points.
        """
        centroid = points_3d.mean(axis=0)
        centered = points_3d - centroid
        
        try:
            _, _, vh = np.linalg.svd(centered, full_matrices=False)
            # Project onto first two principal components
            proj_2d = centered @ vh[:2].T
            return proj_2d
        except np.linalg.LinAlgError:
            # Ultimate fallback: just use X,Y
            logger.warning("PCA failed, using X,Y coordinates directly")
            return points_3d[:, :2].copy()
    
    def transform(self, points_3d: np.ndarray) -> np.ndarray:
        """
        Transform 3D points to 2D using the fitted Isomap model.
        
        For points that were part of the original fit, returns exact 2D coordinates.
        For new points, uses nearest-neighbor interpolation.
        
        Args:
            points_3d: (M, 3) array of 3D points to transform.
            
        Returns:
            (M, 2) array of 2D coordinates.
        """
        if not self._fitted:
            raise RuntimeError("Must call fit() before transform()")
        
        points_3d = np.asarray(points_3d, dtype=np.float64)
        if points_3d.ndim == 1:
            points_3d = points_3d.reshape(1, -1)
        
        n_query = len(points_3d)
        result_2d = np.zeros((n_query, 2), dtype=np.float64)

        exact_dists, exact_idxs = self._tree_3d.query(points_3d, k=1)
        exact_mask = exact_dists < 1e-10

        if np.any(exact_mask):
            result_2d[exact_mask] = self.points_2d[exact_idxs[exact_mask]]

        interp_mask = ~exact_mask
        if np.any(interp_mask):
            k = min(5, len(self.points_3d))
            dists, idxs = self._tree_3d.query(points_3d[interp_mask], k=k)

            if k == 1:
                dists = dists[:, np.newaxis]
                idxs = idxs[:, np.newaxis]

            weights = 1.0 / np.maximum(dists ** 2, 1e-12)
            weights /= weights.sum(axis=1, keepdims=True)
            result_2d[interp_mask] = np.einsum('ij,ijk->ik', weights, self.points_2d[idxs])
        
        return result_2d
    
    def generate_hull(self, points_3d: np.ndarray) -> np.ndarray:
        """
        Generate the convex hull boundary in 3D using Isomap unfolding.
        
        This method:
        1. Transforms 3D points to 2D using Isomap
        2. Computes the 2D convex hull
        3. Returns the corresponding 3D boundary points
        
        Args:
            points_3d: (N, 3) array of surface points.
            
        Returns:
            (M, 3) array of ordered 3D hull boundary points.
        """
        # Fit if not already done
        if not self._fitted or self.points_3d is None:
            self.fit(points_3d)
        
        # Compute 2D convex hull on Isomap-transformed points
        try:
            hull = ConvexHull(self.points_2d)
            hull_indices = hull.vertices
            
            # Get ordered 3D points
            hull_points_3d = self.points_3d[hull_indices]
            
            # Close the boundary
            if len(hull_points_3d) > 0 and not np.allclose(hull_points_3d[0], hull_points_3d[-1]):
                hull_points_3d = np.vstack([hull_points_3d, hull_points_3d[0:1]])
            
            logger.info(f"Isomap hull: {len(hull_indices)} boundary vertices from {len(points_3d)} points")
            return hull_points_3d
            
        except Exception as e:
            logger.error(f"Isomap hull computation failed: {e}")
            raise
    
    def generate_alpha_hull(self, points_3d: np.ndarray, alpha_factor: float = 1.0) -> np.ndarray:
        """
        Generate a concave hull (alpha shape) boundary using Isomap unfolding.
        
        This is better than convex hull for surfaces with concave boundaries.
        
        Args:
            points_3d: (N, 3) array of surface points.
            alpha_factor: Controls boundary tightness (higher = looser).
            
        Returns:
            (M, 3) array of ordered 3D boundary points.
        """
        # Fit if not already done
        if not self._fitted or self.points_3d is None:
            self.fit(points_3d)
        
        # Try alpha shape on 2D Isomap points
        try:
            boundary_indices = self._compute_alpha_boundary_2d(self.points_2d, alpha_factor)
            
            if boundary_indices is not None and len(boundary_indices) >= 3:
                hull_points_3d = self.points_3d[boundary_indices]
                
                # Close the boundary
                if not np.allclose(hull_points_3d[0], hull_points_3d[-1]):
                    hull_points_3d = np.vstack([hull_points_3d, hull_points_3d[0:1]])
                
                logger.info(f"Isomap alpha hull: {len(boundary_indices)} boundary vertices")
                return hull_points_3d
            else:
                # Fallback to convex hull
                logger.warning("Alpha shape failed, using convex hull")
                return self.generate_hull(points_3d)
                
        except Exception as e:
            logger.warning(f"Alpha shape failed ({e}), using convex hull")
            return self.generate_hull(points_3d)
    
    def _compute_alpha_boundary_2d(self, points_2d: np.ndarray, 
                                    alpha_factor: float = 1.0) -> Optional[np.ndarray]:
        """
        Compute alpha shape boundary on 2D points.
        
        Args:
            points_2d: (N, 2) array of 2D points.
            alpha_factor: Boundary tightness multiplier.
            
        Returns:
            Array of ordered boundary point indices, or None if failed.
        """
        from scipy.spatial import Delaunay
        
        try:
            tri = Delaunay(points_2d)
            
            # Compute characteristic edge length
            edges_all = set()
            for simplex in tri.simplices:
                for j in range(3):
                    e = tuple(sorted([simplex[j], simplex[(j+1) % 3]]))
                    edges_all.add(e)
            
            edge_lengths = [np.linalg.norm(points_2d[e[0]] - points_2d[e[1]]) for e in edges_all]
            median_length = np.median(edge_lengths)
            
            # Alpha radius
            alpha = alpha_factor * median_length * 2.0
            
            # Find boundary edges (alpha criterion)
            boundary_edges = []
            edge_count = {}
            
            for simplex in tri.simplices:
                # Check circumradius
                pts = points_2d[simplex]
                circumradius = self._circumradius_2d(pts)
                
                if circumradius is None or circumradius > alpha:
                    continue  # Skip this triangle
                
                # Count edges
                for j in range(3):
                    e = tuple(sorted([simplex[j], simplex[(j+1) % 3]]))
                    edge_count[e] = edge_count.get(e, 0) + 1
            
            # Boundary edges appear exactly once
            for e, count in edge_count.items():
                if count == 1:
                    boundary_edges.append(e)
            
            if not boundary_edges:
                return None
            
            # Order the boundary edges
            return self._order_boundary_edges(boundary_edges)
            
        except Exception as e:
            logger.warning(f"Alpha boundary computation failed: {e}")
            return None
    
    def _circumradius_2d(self, triangle_pts: np.ndarray) -> Optional[float]:
        """Compute circumradius of a 2D triangle."""
        a = np.linalg.norm(triangle_pts[1] - triangle_pts[0])
        b = np.linalg.norm(triangle_pts[2] - triangle_pts[1])
        c = np.linalg.norm(triangle_pts[0] - triangle_pts[2])
        
        s = (a + b + c) / 2
        area_sq = s * (s - a) * (s - b) * (s - c)
        
        if area_sq <= 0:
            return None
        
        area = np.sqrt(area_sq)
        if area < 1e-12:
            return None
        
        return (a * b * c) / (4 * area)
    
    def _order_boundary_edges(self, edges: List[Tuple[int, int]]) -> Optional[np.ndarray]:
        """Order boundary edges into a continuous path."""
        if not edges:
            return None
        
        edge_set = set(edges)
        ordered = list(edge_set.pop())
        
        while edge_set:
            last = ordered[-1]
            found = False
            
            for e in list(edge_set):
                if last in e:
                    next_pt = e[1] if e[0] == last else e[0]
                    if next_pt != ordered[0] or len(edge_set) == 1:
                        ordered.append(next_pt)
                        edge_set.remove(e)
                        found = True
                        break
            
            if not found:
                break
        
        return np.array(ordered)
    
    def triangulate_with_constraints(
        self, 
        points_3d: np.ndarray,
        segments: Optional[np.ndarray] = None,
        holes: Optional[np.ndarray] = None,
        base_size: Optional[float] = None,
        min_angle: Optional[float] = None,
        uniform: bool = True,
        reference_points_3d: Optional[np.ndarray] = None,
        smoothing: float = 0.0,
        interpolator: str = "tps"
    ) -> Dict[str, Any]:
        """
        Perform constrained triangulation using Isomap unfolding.
        
        OPTIMIZED WORKFLOW:
        1. Fit Isomap on reference_points_3d (all raw surface points) to learn fold geometry
        2. Transform ONLY points_3d (boundary/segmentation points) to 2D
        3. Run CDT in 2D with segments as constraints
        4. Map Steiner points back to 3D using selected interpolation method:
           - TPS (Thin Plate Spline): Globally smooth, best for folds, prevents self-intersections
           - IDW (Inverse Distance Weighting): Local smoothing, faster but may create bumps
        
        This is much faster than triangulating all raw points while still
        preserving the fold structure through the Isomap parameterization.
        
        Args:
            points_3d: (N, 3) array of BOUNDARY/SEGMENTATION points to triangulate.
            segments: (M, 2) array of segment indices into points_3d defining constraints.
            holes: (P, 3) array of hole marker points (optional).
            base_size: Target edge size (uses self.base_size if None).
            min_angle: Minimum angle constraint (uses self.min_angle if None).
            uniform: Whether to generate uniform mesh density.
            reference_points_3d: (R, 3) array of ALL raw surface points for Isomap fitting.
                                 If None, uses points_3d (slower, less accurate for folds).
            smoothing: Smoothing parameter (0 = exact interpolation, >0 = smoother).
                       Higher values create smoother surfaces but may deviate from data.
            interpolator: Interpolation method for Steiner points:
                         - "tps" or "Thin Plate Spline": Globally smooth, best for folds
                         - "idw" or "IDW": Local smoothing, faster but may create bumps
            
        Returns:
            Dictionary with:
                - 'vertices': (V, 3) array of 3D mesh vertices
                - 'triangles': (T, 3) array of triangle indices
                - 'original_count': number of original (non-Steiner) vertices
                - 'steiner_count': number of Steiner points added
        """
        from .triangle_direct import DirectTriangleWrapper
        
        points_3d = np.asarray(points_3d, dtype=np.float64)
        
        # Store smoothing and interpolator for use in interpolation
        self._tps_smoothing = smoothing
        self._interpolator = interpolator.lower() if interpolator else "tps"
        
        # Normalize interpolator value
        if "tps" in self._interpolator or "thin" in self._interpolator or "spline" in self._interpolator:
            self._interpolator = "tps"
        elif "idw" in self._interpolator:
            self._interpolator = "idw"
        else:
            self._interpolator = "tps"  # Default to TPS
        
        logger.info(f"Isomap: Using '{self._interpolator.upper()}' interpolation with smoothing={smoothing}")
        
        # Use reference points if provided, otherwise use boundary points
        if reference_points_3d is not None:
            reference_points = np.asarray(reference_points_3d, dtype=np.float64)
            logger.info(f"Isomap: Using {len(reference_points)} reference points to learn fold geometry")
        else:
            reference_points = points_3d
            logger.info(f"Isomap: No reference points provided, using boundary points only")
        
        if base_size is None:
            base_size = self.base_size
        if min_angle is None:
            min_angle = self.min_angle
        
        # Compute base_size from point cloud if not provided
        if base_size is None:
            if len(points_3d) > 1:
                dists = pdist(points_3d)
                base_size = np.median(dists) * 0.5
                if base_size < 1e-6:
                    base_size = 1.0
            else:
                base_size = 1.0
        
        logger.info(f"Isomap triangulation: {len(points_3d)} boundary points, "
                   f"{len(segments) if segments is not None else 0} segments, "
                   f"base_size={base_size:.4f}")
        
        total_start = time.perf_counter()

        # Step 1: Fit Isomap on REFERENCE points (all raw points)
        # This learns the fold geometry from the dense point cloud
        fit_start = time.perf_counter()
        self.fit(reference_points)
        logger.info(f"Isomap triangulation stage: fit={time.perf_counter() - fit_start:.3f}s")
        
        # Step 2: Transform ONLY the boundary points to 2D
        # This is fast since we only transform a small subset
        transform_start = time.perf_counter()
        boundary_points_2d = self.transform(points_3d)
        logger.info(f"Isomap triangulation stage: boundary_transform={time.perf_counter() - transform_start:.3f}s")
        
        n_original = len(points_3d)
        
        # Step 3: Transform hole markers if provided
        holes_2d = None
        if holes is not None and len(holes) > 0:
            holes_start = time.perf_counter()
            holes_2d = self.transform(holes)
            logger.info(f"Isomap triangulation stage: hole_transform={time.perf_counter() - holes_start:.3f}s")
        
        # Step 4: Run CDT in 2D using DirectTriangleWrapper
        # Only triangulates the boundary points with segments as constraints
        triangulator = DirectTriangleWrapper(
            gradient=self.gradient,
            min_angle=min_angle,
            base_size=base_size
        )
        
        triangulation_start = time.perf_counter()
        try:
            tri_result = triangulator.triangulate(
                points=boundary_points_2d,
                segments=segments,
                holes=holes_2d,
                uniform=uniform
            )
        except Exception as e:
            logger.error(f"2D triangulation failed: {e}")
            raise
        
        if tri_result is None or 'vertices' not in tri_result:
            raise ValueError("Triangulation returned no vertices")
        
        vertices_2d = tri_result['vertices']
        triangles = tri_result['triangles']
        
        n_total = len(vertices_2d)
        n_steiner = n_total - n_original
        
        logger.info(f"2D triangulation complete: {n_total} vertices "
                   f"({n_steiner} Steiner points), {len(triangles)} triangles "
                   f"in {time.perf_counter() - triangulation_start:.3f}s")
        
        # Step 5: Map back to 3D using the REFERENCE points for interpolation
        # Boundary points get exact 3D coords, Steiner points get IDW-interpolated
        map_start = time.perf_counter()
        vertices_3d = self._map_vertices_to_3d_with_reference(
            vertices_2d,
            boundary_points_2d,  # Original boundary points in 2D
            points_3d,          # Original boundary points in 3D (exact coords)
            reference_points,   # All reference points in 3D (for TPS)
            n_original
        )
        logger.info(f"Isomap triangulation stage: map_to_3d={time.perf_counter() - map_start:.3f}s")
        
        # Step 6: Validate mesh quality - check for potential self-intersections
        validate_start = time.perf_counter()
        n_inverted = self._count_inverted_triangles(vertices_3d, triangles)
        logger.info(f"Isomap triangulation stage: validate={time.perf_counter() - validate_start:.3f}s")
        if n_inverted > 0:
            logger.warning(f"Detected {n_inverted} potentially inverted triangles. "
                          f"Consider increasing smoothing parameter or using finer segmentation.")

        logger.info(f"Isomap triangulation total={time.perf_counter() - total_start:.3f}s")
        
        return {
            'vertices': vertices_3d,
            'triangles': triangles,
            'original_count': n_original,
            'steiner_count': n_steiner,
            'inverted_count': n_inverted
        }
    
    def _count_inverted_triangles(
        self, 
        vertices: np.ndarray, 
        triangles: np.ndarray
    ) -> int:
        """
        Count triangles that may cause self-intersections.
        
        Checks for triangles where:
        1. Normal direction flips compared to neighbors
        2. Triangle has very small or negative area in 3D
        
        Args:
            vertices: (V, 3) array of 3D vertices.
            triangles: (T, 3) array of triangle indices.
            
        Returns:
            Number of potentially problematic triangles.
        """
        if len(triangles) < 2:
            return 0

        tri_vertices = vertices[triangles]
        edge_1 = tri_vertices[:, 1] - tri_vertices[:, 0]
        edge_2 = tri_vertices[:, 2] - tri_vertices[:, 0]
        raw_normals = np.cross(edge_1, edge_2)
        areas = 0.5 * np.linalg.norm(raw_normals, axis=1)

        normals = np.zeros_like(raw_normals)
        valid_mask = areas > 1e-12
        normals[valid_mask] = raw_normals[valid_mask] / (2.0 * areas[valid_mask, np.newaxis])
        
        # Compute average normal direction
        avg_normal = normals.mean(axis=0)
        avg_norm = np.linalg.norm(avg_normal)
        
        if avg_norm < 1e-12:
            return 0
        
        avg_normal = avg_normal / avg_norm
        
        # Count triangles with flipped normals or tiny areas
        min_area = np.median(areas) * 0.001  # Very small compared to median
        alignment = normals @ avg_normal

        return int(np.count_nonzero((alignment < -0.5) | (areas < min_area)))
    
    def _map_vertices_to_3d(
        self,
        vertices_2d: np.ndarray,
        original_points_3d: np.ndarray,
        n_original: int
    ) -> np.ndarray:
        """
        Map 2D vertices back to 3D coordinates.
        
        Original points get their exact 3D coordinates.
        Steiner points (added by Triangle) get IDW-interpolated 3D coordinates.
        
        Args:
            vertices_2d: (V, 2) array of all 2D vertices (original + Steiner).
            original_points_3d: (N, 3) array of original 3D points.
            n_original: Number of original points.
            
        Returns:
            (V, 3) array of 3D vertex coordinates.
        """
        n_total = len(vertices_2d)
        vertices_3d = np.zeros((n_total, 3), dtype=np.float64)
        
        # Original points: exact mapping
        # The first n_original vertices in 2D correspond to original 3D points
        for i in range(min(n_original, n_total)):
            # Match 2D vertex to closest original 2D point
            dist, idx = self._tree_2d.query(vertices_2d[i])
            
            if dist < 1e-10:
                # Exact match - use original 3D coordinates
                vertices_3d[i] = original_points_3d[idx]
            else:
                # Small deviation - still prefer original if very close
                if idx < len(original_points_3d):
                    vertices_3d[i] = original_points_3d[idx]
                else:
                    # Interpolate (shouldn't happen for original points)
                    vertices_3d[i] = self._interpolate_3d_from_2d(
                        vertices_2d[i], 
                        original_points_3d
                    )
        
        # Steiner points: IDW interpolation
        if n_total > n_original:
            logger.info(f"Interpolating {n_total - n_original} Steiner points to 3D...")
            
            for i in range(n_original, n_total):
                vertices_3d[i] = self._interpolate_3d_from_2d(
                    vertices_2d[i],
                    original_points_3d
                )
        
        return vertices_3d
    
    def _interpolate_3d_from_2d(
        self,
        point_2d: np.ndarray,
        original_points_3d: np.ndarray,
        k: int = 8,
        power: float = 2.0
    ) -> np.ndarray:
        """
        Interpolate 3D coordinates for a 2D Steiner point using IDW.
        
        Uses Inverse Distance Weighting with the k nearest neighbors
        in 2D space to interpolate the 3D coordinates.
        
        Args:
            point_2d: (2,) array - the 2D Steiner point.
            original_points_3d: (N, 3) array of original 3D points.
            k: Number of neighbors to use.
            power: IDW power parameter (2 = inverse square).
            
        Returns:
            (3,) array of interpolated 3D coordinates.
        """
        # Find k nearest neighbors in 2D Isomap space
        k_actual = min(k, len(self.points_2d))
        
        dists, idxs = self._tree_2d.query(point_2d, k=k_actual)
        
        if k_actual == 1:
            dists = np.array([dists])
            idxs = np.array([idxs])
        
        # Handle exact matches
        if np.any(dists < 1e-12):
            zero_idx = np.where(dists < 1e-12)[0][0]
            return original_points_3d[idxs[zero_idx]].copy()
        
        # IDW interpolation
        weights = 1.0 / np.power(dists, power)
        weights /= weights.sum()
        
        valid_mask = idxs < len(original_points_3d)
        if not np.any(valid_mask):
            return np.zeros(3, dtype=np.float64)

        return weights[valid_mask] @ original_points_3d[idxs[valid_mask]]
    
    def _map_vertices_to_3d_with_reference(
        self,
        vertices_2d: np.ndarray,
        boundary_points_2d: np.ndarray,
        boundary_points_3d: np.ndarray,
        reference_points_3d: np.ndarray,
        n_original: int
    ) -> np.ndarray:
        """
        Map 2D vertices back to 3D using TPS interpolation for smooth surfaces.
        
        This method:
        - Maps original boundary points to their exact 3D coordinates
        - Uses TPS (Thin Plate Spline) interpolation for Steiner points
        - TPS creates a globally smooth surface that follows the fold geometry
        - This prevents self-intersecting triangles in complex folds
        
        Args:
            vertices_2d: (V, 2) array of all 2D vertices (boundary + Steiner).
            boundary_points_2d: (N, 2) array of original boundary points in 2D.
            boundary_points_3d: (N, 3) array of original boundary points in 3D.
            reference_points_3d: (R, 3) array of ALL reference points in 3D.
            n_original: Number of original boundary points.
            
        Returns:
            (V, 3) array of 3D vertex coordinates.
        """
        n_total = len(vertices_2d)
        vertices_3d = np.full((n_total, 3), np.nan, dtype=np.float64)
        
        # Build KDTree for boundary points in 2D for exact matching
        boundary_tree_2d = cKDTree(boundary_points_2d)
        
        # Original boundary points: exact mapping
        n_boundary = min(n_original, n_total)
        if n_boundary > 0:
            boundary_dists, boundary_idxs = boundary_tree_2d.query(vertices_2d[:n_boundary], k=1)
            exact_boundary_mask = (boundary_dists < 1e-10) & (boundary_idxs < len(boundary_points_3d))
            if np.any(exact_boundary_mask):
                exact_positions = np.flatnonzero(exact_boundary_mask)
                vertices_3d[exact_positions] = boundary_points_3d[boundary_idxs[exact_boundary_mask]]
        else:
            exact_boundary_mask = np.zeros(0, dtype=bool)
        
        # Steiner points: Use selected interpolation method
        steiner_indices = np.arange(n_original, n_total, dtype=int)

        # Also include any boundary points that didn't get exact matches
        if n_boundary > 0 and np.any(~exact_boundary_mask):
            steiner_indices = np.concatenate([np.flatnonzero(~exact_boundary_mask), steiner_indices])
        
        if len(steiner_indices) > 0:
            n_steiner = len(steiner_indices)
            interpolator = getattr(self, '_interpolator', 'tps')
            
            steiner_2d = vertices_2d[steiner_indices]
            
            # Choose interpolation method based on user selection
            if interpolator == "tps":
                # TPS (Thin Plate Spline) - globally smooth, best for folds
                logger.info(f"Interpolating {n_steiner} Steiner points using TPS "
                           f"from {len(reference_points_3d)} reference points...")
                
                steiner_3d = self._interpolate_steiner_batch_tps(
                    steiner_2d,
                    reference_points_3d
                )
                
                if steiner_3d is not None:
                    vertices_3d[steiner_indices] = steiner_3d
                    logger.info("TPS interpolation successful - smooth surface created")
                else:
                    # Fallback to IDW if TPS fails
                    logger.warning("TPS interpolation failed, falling back to IDW")
                    vertices_3d[steiner_indices] = self._interpolate_steiner_batch_idw(
                        steiner_2d,
                        reference_points_3d
                    )
            else:
                # IDW (Inverse Distance Weighting) - local smoothing, faster
                logger.info(f"Interpolating {n_steiner} Steiner points using IDW "
                           f"from {len(reference_points_3d)} reference points...")
                
                vertices_3d[steiner_indices] = self._interpolate_steiner_batch_idw(
                    steiner_2d,
                    reference_points_3d
                )
                logger.info("IDW interpolation complete")
        
        return vertices_3d
    
    def _interpolate_steiner_batch_tps(
        self,
        steiner_points_2d: np.ndarray,
        reference_points_3d: np.ndarray,
        smoothing: Optional[float] = None
    ) -> Optional[np.ndarray]:
        """
        Batch interpolate Steiner points using Thin Plate Spline (TPS).
        
        TPS creates a globally smooth surface that minimizes bending energy,
        which is ideal for geological fold surfaces. This prevents the
        "bumpy" interpolation that IDW can produce, avoiding self-intersections.
        
        Args:
            steiner_points_2d: (S, 2) array of Steiner points in 2D Isomap space.
            reference_points_3d: (R, 3) array of reference points in 3D.
            smoothing: TPS smoothing parameter (0 = exact interpolation).
                       If None, uses self._tps_smoothing or defaults to 0.0.
            
        Returns:
            (S, 3) array of interpolated 3D coordinates, or None if failed.
        """
        try:
            from scipy.interpolate import RBFInterpolator
            
            # Use stored smoothing value if not explicitly provided
            if smoothing is None:
                smoothing = getattr(self, '_tps_smoothing', 0.0)
            
            if self.points_2d is None or len(self.points_2d) == 0:
                return None
            
            # Use the fitted Isomap 2D points as the interpolation source
            # and reference_points_3d as the target values
            source_2d = self.points_2d
            
            # Ensure we have matching counts
            n_source = min(len(source_2d), len(reference_points_3d))
            if n_source < 4:
                logger.warning("Not enough points for TPS interpolation")
                return None
            
            source_2d = source_2d[:n_source]
            target_3d = reference_points_3d[:n_source]
            
            logger.info(f"TPS interpolation with smoothing={smoothing:.4f}, "
                       f"using {n_source} source points")
            
            tps_start = time.perf_counter()
            tps_neighbors = None
            if n_source > 2000:
                tps_neighbors = min(256, max(96, n_source // 80))

            try:
                rbf = RBFInterpolator(
                    source_2d,
                    target_3d,
                    kernel='thin_plate_spline',
                    smoothing=smoothing,
                    neighbors=tps_neighbors,
                    degree=1  # Linear polynomial for stability
                )
                result_3d = rbf(steiner_points_2d)
            except Exception as e:
                logger.warning(f"TPS interpolation solve failed: {e}")
                return None

            logger.info(
                f"TPS interpolation evaluated in {time.perf_counter() - tps_start:.3f}s "
                f"(neighbors={tps_neighbors if tps_neighbors is not None else 'all'})"
            )
            
            # Validate results - check for NaN or extreme values
            if np.any(np.isnan(result_3d)) or np.any(np.isinf(result_3d)):
                logger.warning("TPS produced invalid values (NaN/Inf)")
                return None
            
            # Check for outliers (points too far from reference cloud)
            ref_center = reference_points_3d.mean(axis=0)
            ref_radius = np.max(np.linalg.norm(reference_points_3d - ref_center, axis=1))
            
            result_distances = np.linalg.norm(result_3d - ref_center, axis=1)
            if np.any(result_distances > ref_radius * 3):
                logger.warning("TPS produced outlier points, falling back to IDW")
                return None
            
            return result_3d
            
        except ImportError:
            logger.warning("scipy.interpolate.RBFInterpolator not available")
            return None
        except Exception as e:
            logger.warning(f"TPS interpolation failed: {e}")
            return None

    def _interpolate_steiner_batch_idw(
        self,
        points_2d: np.ndarray,
        reference_points_3d: np.ndarray,
        k: int = 12,
        power: float = 2.0
    ) -> np.ndarray:
        """
        Batch IDW interpolation in Isomap 2D space for one or more points.
        """
        points_2d = np.asarray(points_2d, dtype=np.float64)
        if points_2d.ndim == 1:
            points_2d = points_2d.reshape(1, -1)

        if len(points_2d) == 0:
            return np.empty((0, 3), dtype=np.float64)

        if self._tree_2d is None:
            raise RuntimeError("Isomap model not fitted - call fit() first")

        k_actual = min(k, len(self.points_2d))
        dists, idxs = self._tree_2d.query(points_2d, k=k_actual)

        if k_actual == 1:
            dists = dists[:, np.newaxis]
            idxs = idxs[:, np.newaxis]

        weights = 1.0 / np.power(np.maximum(dists, 1e-12), power)
        weights /= weights.sum(axis=1, keepdims=True)

        results = np.einsum('ij,ijk->ik', weights, reference_points_3d[idxs])

        exact_rows = np.any(dists < 1e-12, axis=1)
        if np.any(exact_rows):
            exact_cols = np.argmax(dists[exact_rows] < 1e-12, axis=1)
            exact_indices = idxs[exact_rows, exact_cols]
            results[exact_rows] = reference_points_3d[exact_indices]

        return results
    
    def _interpolate_steiner_from_reference(
        self,
        point_2d: np.ndarray,
        reference_points_3d: np.ndarray,
        k: int = 12,
        power: float = 2.0
    ) -> np.ndarray:
        """
        Interpolate 3D coordinates for a Steiner point using reference points.
        
        Uses the pre-fitted Isomap 2D space (_tree_2d) to find neighbors,
        then IDW-interpolates from the corresponding reference 3D coordinates.
        
        Args:
            point_2d: (2,) array - the 2D Steiner point.
            reference_points_3d: (R, 3) array of reference 3D points.
            k: Number of neighbors to use (more = smoother).
            power: IDW power parameter.
            
        Returns:
            (3,) array of interpolated 3D coordinates.
        """
        if self._tree_2d is None:
            raise RuntimeError("Isomap model not fitted - call fit() first")

        return self._interpolate_steiner_batch_idw(
            point_2d,
            reference_points_3d,
            k=k,
            power=power
        )[0]

    def is_surface_suitable_for_isomap(self, points_3d: np.ndarray, threshold: float = 0.5) -> bool:
        """
        Check if a surface is complex enough to benefit from Isomap unfolding.
        
        Simple planar or nearly-planar surfaces can use standard projection.
        Folded surfaces with high curvature benefit from Isomap.
        
        Args:
            points_3d: (N, 3) array of surface points.
            threshold: Curvature threshold (0-1). Higher = only use Isomap for very folded.
            
        Returns:
            True if Isomap is recommended, False if standard projection suffices.
        """
        if len(points_3d) < 10:
            return False
        
        # Compute planarity using PCA
        centered = points_3d - points_3d.mean(axis=0)
        _, s, _ = np.linalg.svd(centered, full_matrices=False)
        
        # Ratio of smallest to largest singular value
        # Small ratio = nearly planar, large ratio = folded
        planarity_measure = s[2] / (s[0] + 1e-12)
        
        return planarity_measure > threshold


def create_isomap_triangulator(
    n_neighbors: int = 15,
    gradient: float = 2.0,
    min_angle: float = 20.0,
    base_size: Optional[float] = None
) -> IsomapTriangulator:
    """
    Factory function to create an IsomapTriangulator.
    
    Args:
        n_neighbors: Number of neighbors for Isomap graph.
        gradient: Mesh density gradient.
        min_angle: Minimum triangle angle.
        base_size: Target edge size.
        
    Returns:
        Configured IsomapTriangulator instance.
    """
    return IsomapTriangulator(
        n_neighbors=n_neighbors,
        gradient=gradient,
        min_angle=min_angle,
        base_size=base_size
    )
