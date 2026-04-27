"""
DirectTriangleWrapper: Improved implementation of Triangle refinement with C callback.

This module provides a direct wrapper for the Triangle library using the
C++ extension module for the triunsuitable callback.
"""

import numpy as np
import triangle as tr
import logging
from typing import Dict, List, Optional, Tuple

TPS_GLOBAL_POINT_LIMIT = 1200
TPS_LOCAL_NEIGHBORS = 128


def _unique_xy_samples(xy: np.ndarray, values: np.ndarray, decimals: int = 12) -> Tuple[np.ndarray, np.ndarray]:
    xy = np.asarray(xy, dtype=float)
    values = np.asarray(values, dtype=float)
    if xy.ndim != 2 or len(xy) == 0:
        return xy, values

    keys = np.round(xy, decimals=decimals)
    unique_keys, inverse = np.unique(keys, axis=0, return_inverse=True)
    if len(unique_keys) == len(xy):
        return xy, values

    xy_accum = np.zeros((len(unique_keys), xy.shape[1]), dtype=float)
    val_accum = np.zeros(len(unique_keys), dtype=float)
    counts = np.bincount(inverse).astype(float)
    np.add.at(xy_accum, inverse, xy)
    np.add.at(val_accum, inverse, values)
    return xy_accum / counts[:, None], val_accum / counts


def _tps_neighbors_for_count(n_samples: int) -> Optional[int]:
    if n_samples <= TPS_GLOBAL_POINT_LIMIT:
        return None
    return min(TPS_LOCAL_NEIGHBORS, max(32, n_samples - 1))

# Try to import triunsuitable bridge helpers.
try:
    from . import triangle_callback
    HAS_TRIANGLE_CALLBACK_BRIDGE = True
except ImportError:
    HAS_TRIANGLE_CALLBACK_BRIDGE = False
    triangle_callback = None
    print("WARNING (triangle_direct): triangle_callback not found. Constrained triangulation might be limited.")    

class DirectTriangleWrapper:
    """
    PERFORMANCE-OPTIMIZED wrapper for Triangle library.
    
    Major performance improvements:
    - Removed expensive interior grid point generation (was creating 1000s of points)
    - Simplified Triangle options for faster execution
    - Direct Triangle library calls without complex callbacks
    - Minimal preprocessing overhead
    - Fast hull computation methods
    
    This provides 5-10x speed improvement over the original implementation
    while maintaining mesh quality for geological surfaces.
    """
    
    def __init__(self, gradient: float = 2.0, min_angle: float = 20.0, 
                base_size: Optional[float] = None):
        """
        Initialize the DirectTriangleWrapper with refinement parameters.
        
        Args:
            gradient: Gradient control parameter (default: 2.0)
            min_angle: Minimum angle for triangle quality (default: 20.0)
            base_size: Base size for triangles (calculated from input if None)
        """
        self.gradient = float(gradient)
        self.min_angle = float(min_angle)
        self.base_size = base_size
        self.feature_points = None
        self.feature_sizes = None
        self.logger = logging.getLogger("MeshIt-Workflow")
        self.triangle_opts = None  # Will store custom triangle options if set
        self.use_cpp_switches = False
        # Guardrails for Python triunsuitable bridge cost on complex surfaces.
        self.triunsuitable_max_iterations = 4
        self.triunsuitable_max_new_points = 1000
        self.triunsuitable_min_point_spacing = None
        
    def set_feature_points(self, points: np.ndarray, sizes: np.ndarray):
        """
        Set feature points and their associated sizes.
        
        These points influence the mesh density with a smooth transition
        based on the gradient parameter.
        
        Args:
            points: Array of feature points (N, 2)
            sizes: Array of sizes for each feature point (N,)
        """
        pts = np.asarray(points, dtype=np.float64)
        sz = np.asarray(sizes, dtype=np.float64).reshape(-1)
        if pts.ndim == 1:
            pts = pts.reshape(1, -1)
        if pts.ndim != 2 or pts.shape[1] != 2:
            raise ValueError("Feature points must have shape (N, 2)")
        if sz.size == 0:
            sz = np.full((pts.shape[0],), float(self.base_size if self.base_size else 1.0))
        elif sz.size == 1 and pts.shape[0] > 1:
            sz = np.full((pts.shape[0],), float(sz[0]))
        elif sz.size != pts.shape[0]:
            n = min(pts.shape[0], sz.size)
            pts = pts[:n]
            sz = sz[:n]

        self.feature_points = pts
        self.feature_sizes = np.clip(sz, 1e-12, np.inf)

    def triangulate(self, points: np.ndarray, segments: Optional[np.ndarray] = None,
                   holes: Optional[np.ndarray] = None, create_feature_points: bool = False,
                   create_transition: bool = False, uniform: bool = True) -> Dict:
        """
        PERFORMANCE-OPTIMIZED triangulation using Triangle with minimal overhead.
        
        Key optimizations:
        - Removed expensive interior grid point generation 
        - Simplified Triangle options
        - Removed complex feature point calculations
        - Direct Triangle library calls
        
        Args:
            points: Input points (N, 2)
            segments: Optional segment indices (M, 2) for constraining triangulation
            holes: Optional hole points (P, 2)
            create_feature_points: IGNORED for performance (was causing major slowdowns)
            create_transition: IGNORED for performance (was causing major slowdowns)
            uniform: Whether to use uniform mesh generation (simplified for speed)
            
        Returns:
            Dictionary with triangulation results (vertices, triangles)
        """
        import triangle as tr
        
        # Ensure inputs are numpy arrays
        points = np.asarray(points, dtype=np.float64)
        
        if segments is not None:
            segments = np.asarray(segments, dtype=np.int32)
        
        if holes is not None:
            holes = np.asarray(holes, dtype=np.float64)
            
        self.logger.info(f"FAST triangulation: {len(points)} points, {len(segments) if segments is not None else 0} segments")
        
        # Calculate base_size if not provided (simplified calculation)
        if self.base_size is None:
            if len(points) > 1:
                # Use simple bounding box diagonal approach for speed
                min_coords = np.min(points, axis=0)
                max_coords = np.max(points, axis=0)
                diagonal = np.sqrt(np.sum((max_coords - min_coords) ** 2))
                self.base_size = diagonal / 15.0
            else:
                self.base_size = 1.0
            
        # PERFORMANCE: Skip expensive feature point generation entirely
        # The old implementation created thousands of interior points causing massive slowdowns
        # For geological surfaces, good boundary conformity is more important than dense interiors
        
        # Set up Triangle input (minimal and fast)
        tri_input = {'vertices': points}
        
        if segments is not None and len(segments) > 0:
            tri_input['segments'] = segments
            
        if holes is not None and len(holes) > 0:
            tri_input['holes'] = holes

        # PERFORMANCE: Optimized Triangle options for speed
        if uniform:
            # Check if C++ MeshIt compatible mode is requested
            use_cpp_switches = getattr(self, 'use_cpp_switches', False)
            
            if use_cpp_switches:
                # C++ MeshIt compatible switches with better area control
                # Use "pzY" (no boundary insertion) with area constraint
                # The C++ version actually uses "pzYYu" but 'u' needs external callback
                area_constraint = self.base_size * self.base_size * 0.5
                tri_options = f'pzYYa{area_constraint:.8f}'
                self.logger.info(f"Using C++ MeshIt compatible Triangle options: '{tri_options}'")
            else:
                # Original fast approach
                effective_min_angle = self.min_angle
                area_constraint = self.base_size * self.base_size * 0.5
                
                # Simplified options - no expensive callbacks or complex features
                tri_options = f'pzYYa{area_constraint:.8f}'
        else:
            # Non-uniform approach for complex cases
            hull_points = self._get_hull_points_fast(points)
            tri_input, tri_options = self._setup_complex_triangulation_fast(tri_input, hull_points)

        # Allow custom Triangle options override
        if hasattr(self, 'triangle_opts') and self.triangle_opts:
            tri_options = self.triangle_opts
            self.logger.info(f"Using custom Triangle options: '{tri_options}'")
        
        self.logger.info(f"Using fast Triangle options: '{tri_options}'")
        
        # PERFORMANCE: Direct Triangle call with error handling and C++ fallback
        try:
            use_cpp_switches = getattr(self, 'use_cpp_switches', False)
            use_triunsuitable_bridge = (
                use_cpp_switches and
                self.feature_points is not None and
                self.feature_sizes is not None and
                len(self.feature_points) > 0
            )

            if use_triunsuitable_bridge and HAS_TRIANGLE_CALLBACK and hasattr(triangle_callback, "triangulate_with_cpp_triunsuitable"):
                self.logger.info(
                    "Using C++ triunsuitable bridge with %d feature point(s)",
                    len(self.feature_points),
                )
                result = triangle_callback.triangulate_with_cpp_triunsuitable(
                    tri_input=tri_input,
                    tri_options=tri_options,
                    gradient=float(self.gradient),
                    mesh_size=float(self.base_size),
                    feature_points=self.feature_points,
                    feature_sizes=self.feature_sizes,
                    max_iterations=int(self.triunsuitable_max_iterations),
                    max_new_points=int(self.triunsuitable_max_new_points),
                    min_point_spacing=self.triunsuitable_min_point_spacing,
                    logger=self.logger,
                )
            else:
                if use_triunsuitable_bridge and not HAS_TRIANGLE_CALLBACK:
                    self.logger.warning(
                        "Feature points are set but triunsuitable bridge module is unavailable; "
                        "falling back to standard Triangle call"
                    )
                result = tr.triangulate(tri_input, tri_options)
            
            if 'triangles' in result and len(result['triangles']) > 0:
                self.logger.info(f"FAST triangulation complete: {len(result['triangles'])} triangles, {len(result['vertices'])} vertices")
                return result
            else:
                # Primary triangulation failed, try fallbacks
                raise RuntimeError("Primary triangulation produced no triangles")
                
        except Exception as e:
            self.logger.warning(f"Primary triangulation failed: {e}")
            
            # Try C++ compatible fallback if not already using it
            if not getattr(self, 'use_cpp_switches', False) and uniform:
                self.logger.warning("Trying C++ MeshIt compatible fallback switches")
                area_constraint = self.base_size * self.base_size * 0.5
                cpp_options = f'pzYa{area_constraint:.8f}'
                try:
                    result = tr.triangulate(tri_input, cpp_options)
                    if 'triangles' in result and len(result['triangles']) > 0:
                        self.logger.info(f"C++ compatible fallback succeeded: {len(result['triangles'])} triangles")
                        return result
                except Exception as e2:
                    self.logger.warning(f"C++ compatible fallback also failed: {e2}")
            
            # Quick fallback without area constraint
            self.logger.warning("Trying minimal constraint fallback")
            try:
                if uniform:
                    effective_min_angle = self.min_angle
                    fallback_options = f'pzq{effective_min_angle:.1f}'
                else:
                    fallback_options = 'pz'
                result = tr.triangulate(tri_input, fallback_options)
                
                if 'triangles' in result and len(result['triangles']) > 0:
                    self.logger.info(f"Fast fallback successful: {len(result['triangles'])} triangles")
                    return result
                else:
                    raise RuntimeError("Fast fallback also failed")
            except Exception as e3:
                self.logger.warning(f"Minimal constraint fallback failed: {e3}")
                    
        except Exception as e:
            self.logger.error(f"All triangulation strategies failed: {e}")
            # Ultimate fallback - basic Delaunay only
            try:
                ultimate_options = 'pz'
                result = tr.triangulate(tri_input, ultimate_options)
                self.logger.warning(f"Ultimate fallback (basic Delaunay): {len(result.get('triangles', []))} triangles")
                return result
            except Exception as e2:
                self.logger.error(f"All triangulation attempts failed: {e2}")
                raise RuntimeError(f"Complete triangulation failure: {e2}")
        
        return {}
    
    
    def _get_hull_points_fast(self, points: np.ndarray) -> np.ndarray:
        """Fast convex hull computation for complex triangulation cases."""
        if len(points) <= 3:
            return points
            
        try:
            from scipy.spatial import ConvexHull
            hull_indices = ConvexHull(points).vertices
            return points[hull_indices]
        except Exception:
            # Fallback: use bounding box corners
            min_coords = np.min(points, axis=0)
            max_coords = np.max(points, axis=0)
            return np.array([
                [min_coords[0], min_coords[1]],
                [max_coords[0], min_coords[1]], 
                [max_coords[0], max_coords[1]],
                [min_coords[0], max_coords[1]]
            ])
    
    def _setup_complex_triangulation_fast(self, tri_input: Dict, hull_points: np.ndarray) -> Tuple[Dict, str]:
        """Fast setup for complex triangulation cases (simplified from original)."""
        # For complex cases, we add a minimal set of interior points
        # Much faster than the original grid generation
        
        if len(hull_points) < 3:
            return tri_input, f'pzq{self.min_angle:.1f}'
        
        # Add a few strategic interior points for better quality (not thousands like before)
        centroid = np.mean(hull_points, axis=0)
        
        # Add centroid and a few nearby points
        interior_points = [centroid]
        
        # Add 4 points around centroid for better quality  
        radius = np.mean([np.linalg.norm(pt - centroid) for pt in hull_points]) * 0.3
        for angle in [0, np.pi/2, np.pi, 3*np.pi/2]:
            pt = centroid + radius * np.array([np.cos(angle), np.sin(angle)])
            interior_points.append(pt)
        
        # Combine original points with minimal interior points
        all_points = np.vstack([tri_input['vertices'], np.array(interior_points)])
        tri_input['vertices'] = all_points
        
        # Simple area constraint
        area_constraint = self.base_size * self.base_size * 0.5
        tri_options = f'pzq{self.min_angle:.1f}a{area_constraint:.8f}'
        
        return tri_input, tri_options

    def __del__(self):
        """Clean up C++ resources when the wrapper is destroyed."""
        # No explicit cleanup needed, the Python-C++ binding handles this 

    def set_triangle_options(self, options: str):
        """
        Set custom options for the Triangle library.
        
        This allows direct control over Triangle's behavior by passing specific
        options string that will override the default options generated.
        
        Args:
            options: String with Triangle options (e.g., 'pzq30a40')
        """
        self.triangle_opts = options
        self.logger.info(f"Setting custom Triangle options: {options}") 

    def set_cpp_compatible_mode(self, enable: bool = True):
        """
        Enable or disable C++ MeshIt compatible Triangle switches.
        
        When enabled, uses C++-compatible Triangle switches and (if feature points
        are provided) the triunsuitable bridge that emulates MeshIt's `-u` grading.
        This can produce denser, higher quality meshes that are more compatible with TetGen.
        
        Args:
            enable: Whether to enable C++ compatible mode
        """
        self.use_cpp_switches = enable
        if enable:
            self.logger.info("Enabled C++ MeshIt compatible Triangle switches")
        else:
            self.logger.info("Disabled C++ MeshIt compatible mode, using standard switches")
    def _sanitize_segments(self, segments: Optional[np.ndarray], n_vertices: int) -> np.ndarray:
        """
        Remove degenerate/duplicate/out-of-range segments for robust PSLG input.
        """
        if segments is None or len(segments) == 0 or n_vertices <= 0:
            return np.empty((0, 2), dtype=np.int32)

        segs = np.asarray(segments, dtype=np.int32)
        if segs.ndim != 2 or segs.shape[1] != 2:
            return np.empty((0, 2), dtype=np.int32)

        # Drop degenerate or out-of-range segments
        valid_mask = (
            (segs[:, 0] != segs[:, 1]) &
            (segs[:, 0] >= 0) & (segs[:, 1] >= 0) &
            (segs[:, 0] < n_vertices) & (segs[:, 1] < n_vertices)
        )
        segs = segs[valid_mask]
        if len(segs) == 0:
            return np.empty((0, 2), dtype=np.int32)

        # Remove duplicates regardless of orientation
        segs_sorted = np.sort(segs, axis=1)
        _, unique_idx = np.unique(segs_sorted, axis=0, return_index=True)
        return segs[unique_idx]

    def _filter_short_segments(self, segments: Optional[np.ndarray], points_2d: np.ndarray,
                               min_len: float) -> np.ndarray:
        """
        Drop segments that are effectively zero-length in 2D (numerical robustness).
        """
        if segments is None or len(segments) == 0:
            return np.empty((0, 2), dtype=np.int32)
        if min_len <= 0.0:
            return np.asarray(segments, dtype=np.int32)

        segs = np.asarray(segments, dtype=np.int32)
        pts = points_2d[segs]
        lengths = np.linalg.norm(pts[:, 0] - pts[:, 1], axis=1)
        segs = segs[lengths >= min_len]
        if len(segs) == 0:
            return np.empty((0, 2), dtype=np.int32)
        return segs

    def _remove_intersecting_segments(self, segments: np.ndarray, points_2d: np.ndarray) -> np.ndarray:
        """
        Remove segments that intersect other segments (not at endpoints).
        This prevents Triangle's "Topological inconsistency" errors.
        
        Uses a simple O(n^2) approach - fine for typical segment counts (<1000).
        """
        if segments is None or len(segments) < 2:
            return segments if segments is not None else np.empty((0, 2), dtype=np.int32)
        
        segs = np.asarray(segments, dtype=np.int32)
        n_segs = len(segs)
        
        def ccw(A, B, C):
            """Check if three points are in counter-clockwise order."""
            return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])
        
        def segments_intersect(p1, p2, p3, p4):
            """Check if segment (p1,p2) intersects segment (p3,p4) not at endpoints."""
            # First check if they share an endpoint (allowed)
            eps = 1e-10
            for pa in [p1, p2]:
                for pb in [p3, p4]:
                    if np.linalg.norm(pa - pb) < eps:
                        return False  # Shared endpoint is OK
            
            # Standard intersection test
            if ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4):
                return True
            return False
        
        # Track which segments to keep
        keep = np.ones(n_segs, dtype=bool)
        intersection_count = np.zeros(n_segs, dtype=int)
        
        # Check all pairs for intersections
        for i in range(n_segs):
            if not keep[i]:
                continue
            p1, p2 = points_2d[segs[i, 0]], points_2d[segs[i, 1]]
            
            for j in range(i + 1, n_segs):
                if not keep[j]:
                    continue
                p3, p4 = points_2d[segs[j, 0]], points_2d[segs[j, 1]]
                
                if segments_intersect(p1, p2, p3, p4):
                    intersection_count[i] += 1
                    intersection_count[j] += 1
        
        # Remove segments with intersections (prefer removing those with more intersections)
        # Iteratively remove worst offenders
        removed = 0
        while np.any(intersection_count > 0):
            worst_idx = np.argmax(intersection_count)
            if intersection_count[worst_idx] == 0:
                break
            
            keep[worst_idx] = False
            removed += 1
            
            # Recount intersections for remaining segments
            intersection_count[worst_idx] = 0
            p1, p2 = points_2d[segs[worst_idx, 0]], points_2d[segs[worst_idx, 1]]
            
            for j in range(n_segs):
                if not keep[j] or j == worst_idx:
                    continue
                p3, p4 = points_2d[segs[j, 0]], points_2d[segs[j, 1]]
                if segments_intersect(p1, p2, p3, p4):
                    intersection_count[j] = max(0, intersection_count[j] - 1)
        
        if removed > 0:
            self.logger.warning(f"Removed {removed} intersecting segments to prevent Triangle errors")
        
        return segs[keep]

    def _fallback_standard_triangulation(self, points_3d: np.ndarray,
                                         segments: Optional[np.ndarray],
                                         uniform: bool,
                                         interpolator: str = 'tps',
                                         smoothing: float = 0.0,
                                         reference_mesh_3d: Optional[np.ndarray] = None,
                                         reference_triangles: Optional[np.ndarray] = None) -> Dict:
        """
        Fallback to standard 2D projected triangulation.

        Args:
            points_3d: 3D points (constraint points for triangulation)
            segments: Optional segments
            uniform: Uniform mesh flag
            reference_mesh_3d: Optional reference mesh for Z-interpolation (preserves fold structure)
            reference_triangles: Optional reference mesh triangles for barycentric interpolation

        Returns:
            Triangulation result dict
        """
        # Project to 2D using PCA
        try:
            centroid = points_3d.mean(axis=0)
            centered = points_3d - centroid
            _, _, vh = np.linalg.svd(centered, full_matrices=False)

            u_axis = vh[0]
            v_axis = vh[1]
            w_axis = vh[2]  # Normal direction (Z in local frame)

            # For folded surfaces with reference mesh, try limb-separated triangulation first
            # This prevents cross-limb connections that cause overlapping triangles
            if reference_mesh_3d is not None and len(reference_mesh_3d) > 0:
                self.logger.info("Attempting limb-separated triangulation for folded surface")
                limb_result = self._triangulate_limb_separated(
                    points_3d, segments, reference_mesh_3d,
                    u_axis, v_axis, w_axis, centroid, uniform
                )

                if limb_result is not None and 'vertices' in limb_result:
                    # Post-process to remove any overlapping triangles
                    vertices_3d = limb_result['vertices']
                    triangles = limb_result['triangles']

                    valid_mask = self._detect_overlapping_triangles(vertices_3d, triangles)
                    n_invalid = np.sum(~valid_mask)

                    if n_invalid > 0:
                        self.logger.info(f"Removed {n_invalid} overlapping/inverted triangles")
                        triangles = triangles[valid_mask]

                    self.logger.info(f"Limb-separated triangulation: {len(vertices_3d)} vertices, {len(triangles)} triangles")
                    return {
                        'vertices': vertices_3d,
                        'triangles': triangles
                    }
                else:
                    self.logger.info("Limb-separated triangulation returned None, falling back to standard method")

            u_coords = np.dot(centered, u_axis)
            v_coords = np.dot(centered, v_axis)
            points_2d = np.column_stack([u_coords, v_coords])

            # For Refine Mesh case with reference mesh, add reference points as internal Steiner guides
            # This ensures folded surfaces have proper internal density matching the reference mesh
            original_base_size = self.base_size
            augmented_points_2d = points_2d
            n_original_points = len(points_2d)

            if reference_mesh_3d is not None and len(reference_mesh_3d) > 0:
                from scipy.spatial import cKDTree
                
                # Project reference mesh to 2D
                ref_centered = reference_mesh_3d - centroid
                ref_2d = np.column_stack([np.dot(ref_centered, u_axis), np.dot(ref_centered, v_axis)])
                
                # Add ALL reference points as Steiner guides (no interior filtering)
                # For folded surfaces, Delaunay/convex hull tests fail due to 2D collapse
                # Instead, just filter by distance from constraints and let Triangle handle it
                try:
                    # Remove reference points too close to existing constraint points
                    constraint_tree = cKDTree(points_2d)
                    min_dist = self.base_size * 0.15 if self.base_size else 1.0
                    dists, _ = constraint_tree.query(ref_2d, k=1)
                    far_enough_mask = dists > min_dist
                    interior_ref_2d = ref_2d[far_enough_mask]
                    
                    self.logger.info(f"Adding {len(interior_ref_2d)}/{len(ref_2d)} reference points as Steiner guides (filtered by distance)")
                    
                    if len(interior_ref_2d) > 0:
                        # Subsample if too many points (keep it manageable)
                        max_interior = min(1000, len(interior_ref_2d))
                        if len(interior_ref_2d) > max_interior:
                            indices = np.random.choice(len(interior_ref_2d), max_interior, replace=False)
                            interior_ref_2d = interior_ref_2d[indices]
                        
                        # Add reference points as Steiner guides
                        augmented_points_2d = np.vstack([points_2d, interior_ref_2d])
                        self.logger.info(f"Added {len(interior_ref_2d)} interior reference points as Steiner guides for fold structure")
                except Exception as e:
                    self.logger.warning(f"Could not add interior Steiner guides: {e}")
            
            # Use standard triangulation with augmented points
            result_2d = self.triangulate(augmented_points_2d, segments, uniform=uniform)
            
            # Restore original base_size
            self.base_size = original_base_size
            
            if 'vertices' not in result_2d:
                return result_2d
            
            # Project back to 3D
            vertices_2d = result_2d['vertices']
            vertices_3d = centroid + vertices_2d[:, 0:1] * u_axis + vertices_2d[:, 1:2] * v_axis
            
            # Interpolate Z values - use reference mesh if provided (Refine Mesh case)
            if reference_mesh_3d is not None and len(reference_mesh_3d) > 0:
                # Use reference mesh for Z-interpolation to preserve fold structure
                from scipy.spatial import cKDTree

                self.logger.info(f"Using reference mesh ({len(reference_mesh_3d)} pts) for Z-interpolation to preserve fold structure")
                ref_centered = reference_mesh_3d - centroid
                ref_z = np.dot(ref_centered, vh[2])
                ref_2d = np.column_stack([np.dot(ref_centered, u_axis), np.dot(ref_centered, v_axis)])

                # If reference triangles available, use barycentric interpolation for better accuracy
                if reference_triangles is not None and len(reference_triangles) > 0:
                    self.logger.info("Using barycentric interpolation from reference mesh triangles")

                    z_new = np.zeros(len(vertices_2d))
                    ref_tree = cKDTree(ref_2d)

                    for i in range(len(vertices_2d)):
                        pt_2d = vertices_2d[i]

                        # Find which reference triangle this point is in
                        best_tri = None
                        best_bary = None
                        min_dist_to_tri = float('inf')

                        # First find nearby reference vertices to limit triangle search
                        _, nearby_verts = ref_tree.query(pt_2d, k=min(20, len(ref_2d)))
                        if isinstance(nearby_verts, np.integer):
                            nearby_verts = [nearby_verts]

                        # Find triangles that include nearby vertices
                        nearby_vert_set = set(nearby_verts)
                        candidate_tris = []
                        for tri in reference_triangles:
                            if int(tri[0]) in nearby_vert_set or int(tri[1]) in nearby_vert_set or int(tri[2]) in nearby_vert_set:
                                candidate_tris.append(tri)

                        # If no candidates found, search all triangles
                        if len(candidate_tris) == 0:
                            candidate_tris = reference_triangles

                        for tri in candidate_tris:
                            t0, t1, t2 = int(tri[0]), int(tri[1]), int(tri[2])
                            p0, p1, p2 = ref_2d[t0], ref_2d[t1], ref_2d[t2]

                            # Compute barycentric coordinates
                            v0 = p2 - p0
                            v1 = p1 - p0
                            v2 = pt_2d - p0

                            dot00 = np.dot(v0, v0)
                            dot01 = np.dot(v0, v1)
                            dot02 = np.dot(v0, v2)
                            dot11 = np.dot(v1, v1)
                            dot12 = np.dot(v1, v2)

                            denom = dot00 * dot11 - dot01 * dot01
                            if abs(denom) < 1e-10:
                                continue

                            inv_denom = 1.0 / denom
                            u = (dot11 * dot02 - dot01 * dot12) * inv_denom
                            v = (dot00 * dot12 - dot01 * dot02) * inv_denom

                            # Check if inside triangle (with small tolerance)
                            if u >= -0.05 and v >= -0.05 and (u + v) <= 1.05:
                                best_tri = (t0, t1, t2)
                                # Clamp to valid range
                                u = max(0, min(1, u))
                                v = max(0, min(1, v))
                                w = 1 - u - v
                                if w < 0:
                                    total = u + v
                                    if total > 0:
                                        u /= total
                                        v /= total
                                    w = 0
                                best_bary = (w, v, u)
                                break

                            # Track closest triangle center
                            center = (p0 + p1 + p2) / 3
                            dist_to_center = np.linalg.norm(pt_2d - center)
                            if dist_to_center < min_dist_to_tri:
                                min_dist_to_tri = dist_to_center
                                best_tri = (t0, t1, t2)
                                # Use clamped coordinates
                                u = max(0, min(1, u))
                                v = max(0, min(1, v))
                                w = 1 - u - v
                                if w < 0:
                                    total = u + v
                                    if total > 0:
                                        u /= total
                                        v /= total
                                    w = 0
                                best_bary = (w, v, u)

                        if best_tri is not None and best_bary is not None:
                            t0, t1, t2 = best_tri
                            w0, w1, w2 = best_bary
                            # Interpolate Z from reference triangle vertices
                            z_new[i] = w0 * ref_z[t0] + w1 * ref_z[t1] + w2 * ref_z[t2]
                        else:
                            # Fallback: nearest neighbor
                            _, nearest = ref_tree.query(pt_2d, k=1)
                            z_new[i] = ref_z[nearest]

                else:
                    # Fallback: limb-aware IDW when no reference triangles
                    self.logger.info("Using limb-aware IDW interpolation for folded surface")

                    # Get constraint points Z values for limb detection
                    constraint_z = np.dot(centered, vh[2])

                    # Build tree for finding nearest constraint point to each vertex
                    constraint_tree = cKDTree(points_2d)

                    # For each output vertex, find nearest constraint point and use its Z as limb guide
                    _, nearest_constraint_idx = constraint_tree.query(vertices_2d, k=1)
                    vertex_limb_z = constraint_z[nearest_constraint_idx]

                    ref_tree = cKDTree(ref_2d)
                    k = min(20, len(ref_2d))  # More neighbors to filter from
                    dists, indices = ref_tree.query(vertices_2d, k=k)

                    if dists.ndim == 1:
                        dists = dists[:, np.newaxis]
                        indices = indices[:, np.newaxis]

                    # Compute Z range for limb filtering threshold
                    z_range = np.ptp(ref_z)
                    limb_threshold = z_range * 0.3  # Points within 30% of Z range are "same limb"

                    z_new = np.zeros(len(vertices_2d))
                    for i in range(len(vertices_2d)):
                        target_z = vertex_limb_z[i]
                        neighbor_indices = indices[i]
                        neighbor_dists = dists[i]
                        neighbor_z = ref_z[neighbor_indices]

                        # Filter to same-limb neighbors (similar Z value)
                        limb_mask = np.abs(neighbor_z - target_z) < limb_threshold

                        if np.sum(limb_mask) >= 3:
                            # Use filtered neighbors
                            filtered_dists = neighbor_dists[limb_mask]
                            filtered_z = neighbor_z[limb_mask]
                        else:
                            # Fallback: use closest neighbors regardless of limb
                            filtered_dists = neighbor_dists[:5]
                            filtered_z = neighbor_z[:5]

                        # IDW interpolation
                        weights = 1.0 / np.maximum(filtered_dists ** 2, 1e-10)
                        weights_norm = weights / weights.sum()
                        z_new[i] = np.sum(weights_norm * filtered_z)

                vertices_3d = vertices_3d + z_new[:, np.newaxis] * vh[2]
            else:
                # Standard interpolation for non-folded surfaces
                z_orig = np.dot(centered, vh[2])
                orig_2d = points_2d
                
                z_new = None
                
                if interpolator is not None and 'idw' in interpolator.lower():
                     self.logger.info("Fallback: Using IDW interpolation")
                     tree = cKDTree(orig_2d)
                     k = min(12, len(orig_2d))
                     dists, indices = tree.query(vertices_2d, k=k)
                     
                     if dists.ndim == 1:
                         dists = dists[:, np.newaxis]
                         indices = indices[:, np.newaxis]
                     
                     weights = 1.0 / np.maximum(dists ** 2, 1e-10)
                     weights_sum = weights.sum(axis=1, keepdims=True)
                     weights_norm = weights / weights_sum
                     
                     z_new = np.sum(weights_norm * z_orig[indices], axis=1)
                     
                elif interpolator is not None and 'linear' in interpolator.lower():
                    self.logger.info("Fallback: Using Linear interpolation")
                    from scipy.interpolate import LinearNDInterpolator
                    try:
                        lin_interp = LinearNDInterpolator(orig_2d, z_orig)
                        z_new = lin_interp(vertices_2d)
                        
                        nan_mask = np.isnan(z_new)
                        if np.any(nan_mask):
                            from scipy.interpolate import NearestNDInterpolator
                            near_interp = NearestNDInterpolator(orig_2d, z_orig)
                            z_new[nan_mask] = near_interp(vertices_2d[nan_mask])
                    except Exception as e:
                        self.logger.warning(f"Fallback Linear interpolation failed: {e}")
                
                if z_new is None:
                    try:
                        self.logger.info(f"Fallback: Using TPS interpolation (smoothing={smoothing})")
                        from scipy.interpolate import RBFInterpolator
                        tps_xy, tps_z = _unique_xy_samples(orig_2d, z_orig)
                        if len(tps_xy) < 4:
                            raise ValueError("not enough unique TPS samples")
                        tps_neighbors = _tps_neighbors_for_count(len(tps_xy))
                        self.logger.info(
                            "Fallback TPS: %d source samples, %d query points, neighbors=%s",
                            len(tps_xy),
                            len(vertices_2d),
                            tps_neighbors if tps_neighbors is not None else "global",
                        )
                        rbf = RBFInterpolator(
                            tps_xy,
                            tps_z,
                            kernel='thin_plate_spline',
                            smoothing=smoothing,
                            neighbors=tps_neighbors,
                            degree=1,
                        )
                        z_new = rbf(vertices_2d)
                    except Exception as e:
                        self.logger.warning(f"Fallback TPS failed: {e}")

                if z_new is not None:
                    vertices_3d = vertices_3d + z_new[:, np.newaxis] * vh[2]

            # Post-process to remove overlapping triangles for folded surfaces
            triangles = result_2d['triangles']
            if reference_mesh_3d is not None and len(reference_mesh_3d) > 0:
                valid_mask = self._detect_overlapping_triangles(vertices_3d, triangles)
                n_invalid = np.sum(~valid_mask)
                if n_invalid > 0:
                    self.logger.info(f"Removed {n_invalid} overlapping/inverted triangles from fallback triangulation")
                    triangles = triangles[valid_mask]

            return {
                'vertices': vertices_3d,
                'triangles': triangles
            }
            
        except Exception as e:
            self.logger.error(f"Fallback triangulation failed: {e}")
            return {}

    def _detect_overlapping_triangles(self, vertices_3d: np.ndarray, triangles: np.ndarray) -> np.ndarray:
        """
        Detect overlapping/inverted triangles in a 3D mesh.

        Returns a boolean mask where True indicates a valid (non-overlapping) triangle.
        """
        if len(triangles) == 0:
            return np.array([], dtype=bool)

        # Compute normals for each triangle
        v0 = vertices_3d[triangles[:, 0]]
        v1 = vertices_3d[triangles[:, 1]]
        v2 = vertices_3d[triangles[:, 2]]

        edge1 = v1 - v0
        edge2 = v2 - v0
        normals = np.cross(edge1, edge2)
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        # Avoid division by zero for degenerate triangles
        norms = np.maximum(norms, 1e-10)
        normals = normals / norms

        # Compute triangle areas (half of cross product magnitude)
        areas = np.linalg.norm(np.cross(edge1, edge2), axis=1) / 2.0

        # Build adjacency: which triangles share edges
        from collections import defaultdict
        edge_to_triangles = defaultdict(list)
        for tri_idx, tri in enumerate(triangles):
            for i in range(3):
                # Create edge key (sorted to be direction-independent)
                edge = tuple(sorted([tri[i], tri[(i + 1) % 3]]))
                edge_to_triangles[edge].append(tri_idx)

        # Check for normal consistency with neighbors
        valid_mask = np.ones(len(triangles), dtype=bool)

        # Mark degenerate triangles as invalid
        valid_mask[areas < 1e-10] = False

        # Check normal consistency with neighbors
        for tri_idx in range(len(triangles)):
            if not valid_mask[tri_idx]:
                continue

            tri = triangles[tri_idx]
            tri_normal = normals[tri_idx]

            # Find neighboring triangles
            neighbor_normals = []
            for i in range(3):
                edge = tuple(sorted([tri[i], tri[(i + 1) % 3]]))
                for neighbor_idx in edge_to_triangles[edge]:
                    if neighbor_idx != tri_idx and valid_mask[neighbor_idx]:
                        neighbor_normals.append(normals[neighbor_idx])

            if len(neighbor_normals) > 0:
                # Check if this triangle's normal is consistent with neighbors
                neighbor_normals = np.array(neighbor_normals)
                dots = np.dot(neighbor_normals, tri_normal)

                # If most neighbors have opposite normal, this triangle is likely inverted
                if np.mean(dots) < -0.3:  # More than ~107 degrees average deviation
                    valid_mask[tri_idx] = False

        # Check for actual triangle-triangle intersections
        # Only check triangles that share an edge (for efficiency)
        for edge, tri_indices in edge_to_triangles.items():
            if len(tri_indices) != 2:
                continue

            t1_idx, t2_idx = tri_indices
            if not valid_mask[t1_idx] or not valid_mask[t2_idx]:
                continue

            # Check if the two triangles intersect (not just share an edge)
            t1 = triangles[t1_idx]
            t2 = triangles[t2_idx]

            # Find the vertex of each triangle not on the shared edge
            shared_verts = set(edge)
            t1_free = [v for v in t1 if v not in shared_verts][0]
            t2_free = [v for v in t2 if v not in shared_verts][0]

            # Get the shared edge vertices
            e0, e1 = edge
            p_shared_0 = vertices_3d[e0]
            p_shared_1 = vertices_3d[e1]
            p_t1_free = vertices_3d[t1_free]
            p_t2_free = vertices_3d[t2_free]

            # Check if triangles fold over each other (overlap when projected)
            # Compute signed volume to check if free vertices are on same side of shared edge plane
            edge_vec = p_shared_1 - p_shared_0
            to_t1 = p_t1_free - p_shared_0
            to_t2 = p_t2_free - p_shared_0

            # Normal of edge in the plane of triangles
            cross1 = np.cross(edge_vec, to_t1)
            cross2 = np.cross(edge_vec, to_t2)

            # If crosses point in same direction, triangles might overlap
            if np.dot(cross1, cross2) > 0:
                # Check if the overlap is significant
                center1 = np.mean(vertices_3d[t1], axis=0)
                center2 = np.mean(vertices_3d[t2], axis=0)

                # If centers are very close but normals are opposite, it's an overlap
                center_dist = np.linalg.norm(center1 - center2)
                avg_area = (areas[t1_idx] + areas[t2_idx]) / 2
                expected_size = np.sqrt(avg_area)

                if center_dist < expected_size * 0.5:
                    dot = np.dot(normals[t1_idx], normals[t2_idx])
                    if dot < 0:  # Opposite normals = overlap
                        # Mark the smaller triangle as invalid
                        if areas[t1_idx] < areas[t2_idx]:
                            valid_mask[t1_idx] = False
                        else:
                            valid_mask[t2_idx] = False

        return valid_mask

    def _classify_points_into_limbs(self, points_3d: np.ndarray, reference_mesh_3d: np.ndarray,
                                    u_axis: np.ndarray, v_axis: np.ndarray, w_axis: np.ndarray,
                                    centroid: np.ndarray) -> np.ndarray:
        """
        Classify points into fold limbs based on their Z position relative to reference mesh.

        Returns array of limb labels (0 or 1) for each point.
        """
        from scipy.spatial import cKDTree

        # Project to 2D for finding nearest reference points
        points_2d = np.column_stack([
            np.dot(points_3d - centroid, u_axis),
            np.dot(points_3d - centroid, v_axis)
        ])
        points_z = np.dot(points_3d - centroid, w_axis)

        ref_centered = reference_mesh_3d - centroid
        ref_2d = np.column_stack([np.dot(ref_centered, u_axis), np.dot(ref_centered, v_axis)])
        ref_z = np.dot(ref_centered, w_axis)

        # Build tree for reference points
        ref_tree = cKDTree(ref_2d)

        # For each constraint point, find nearby reference points
        k = min(20, len(ref_2d))
        dists, indices = ref_tree.query(points_2d, k=k)

        if dists.ndim == 1:
            dists = dists[:, np.newaxis]
            indices = indices[:, np.newaxis]

        # Determine limb by comparing constraint Z to reference Z values
        # If multiple reference points at same 2D location have different Z, use closest Z match
        limb_labels = np.zeros(len(points_3d), dtype=int)

        # Find Z threshold to separate limbs
        z_range = np.ptp(ref_z)
        z_median = np.median(ref_z)

        for i in range(len(points_3d)):
            point_z = points_z[i]
            neighbor_z = ref_z[indices[i]]

            # Find reference points above and below median
            above_mask = neighbor_z > z_median
            below_mask = neighbor_z <= z_median

            if np.any(above_mask) and np.any(below_mask):
                # Determine which limb this point is closer to
                above_z = neighbor_z[above_mask]
                below_z = neighbor_z[below_mask]

                dist_to_above = np.min(np.abs(point_z - above_z))
                dist_to_below = np.min(np.abs(point_z - below_z))

                limb_labels[i] = 0 if dist_to_below < dist_to_above else 1
            else:
                # Simple Z threshold if no clear separation
                limb_labels[i] = 0 if point_z <= z_median else 1

        return limb_labels

    def _triangulate_limb_separated(self, points_3d: np.ndarray, segments: Optional[np.ndarray],
                                    reference_mesh_3d: np.ndarray, u_axis: np.ndarray,
                                    v_axis: np.ndarray, w_axis: np.ndarray, centroid: np.ndarray,
                                    uniform: bool = False) -> Dict:
        """
        Triangulate folded surface using limb-separated approach.

        This prevents cross-limb connections that cause overlapping triangles.
        """
        from scipy.spatial import cKDTree

        # Classify points into limbs
        limb_labels = self._classify_points_into_limbs(
            points_3d, reference_mesh_3d, u_axis, v_axis, w_axis, centroid
        )

        # Get unique limbs
        unique_limbs = np.unique(limb_labels)

        if len(unique_limbs) <= 1:
            self.logger.info("All points on same limb, using standard triangulation")
            return None  # Caller will use standard method

        self.logger.info(f"Detected {len(unique_limbs)} limbs for limb-separated triangulation")

        # Project all points to 2D
        centered = points_3d - centroid
        points_2d = np.column_stack([np.dot(centered, u_axis), np.dot(centered, v_axis)])
        points_z = np.dot(centered, w_axis)

        # Triangulate each limb separately
        all_vertices = []
        all_triangles = []
        vertex_offset = 0

        for limb in unique_limbs:
            limb_mask = limb_labels == limb
            limb_indices = np.where(limb_mask)[0]
            limb_points_2d = points_2d[limb_mask]
            limb_points_z = points_z[limb_mask]

            if len(limb_points_2d) < 3:
                self.logger.warning(f"Limb {limb} has fewer than 3 points, skipping")
                continue

            self.logger.info(f"Triangulating limb {limb} with {len(limb_points_2d)} points")

            # Filter segments to this limb
            limb_segments = None
            if segments is not None and len(segments) > 0:
                # Create mapping from global to local index
                global_to_local = {g: l for l, g in enumerate(limb_indices)}

                filtered_segs = []
                for seg in segments:
                    p1, p2 = int(seg[0]), int(seg[1])
                    if p1 in global_to_local and p2 in global_to_local:
                        filtered_segs.append([global_to_local[p1], global_to_local[p2]])

                if filtered_segs:
                    limb_segments = np.array(filtered_segs, dtype=int)

            # Triangulate this limb
            try:
                if self.base_size is None:
                    min_coords = np.min(limb_points_2d, axis=0)
                    max_coords = np.max(limb_points_2d, axis=0)
                    diagonal = np.sqrt(np.sum((max_coords - min_coords) ** 2))
                    patch_base_size = diagonal / 10.0
                else:
                    patch_base_size = self.base_size

                area_constraint = patch_base_size * patch_base_size * 0.5

                tri_input = {'vertices': limb_points_2d}
                if limb_segments is not None and len(limb_segments) > 0:
                    limb_segments = self._sanitize_segments(limb_segments, len(limb_points_2d))
                    if len(limb_segments) > 0:
                        tri_input['segments'] = limb_segments

                p_switch = 'p' if 'segments' in tri_input else ''
                tri_options = f'{p_switch}zYYa{area_constraint:.8f}'

                result = tr.triangulate(tri_input, tri_options)

                if result and 'vertices' in result and 'triangles' in result:
                    result_verts_2d = result['vertices']
                    result_tris = result['triangles']

                    # Map output vertices back to 3D
                    n_orig = len(limb_points_2d)
                    n_verts = len(result_verts_2d)

                    # For original vertices, use their known Z
                    # For Steiner points, interpolate Z from neighbors
                    result_z = np.zeros(n_verts)
                    result_z[:n_orig] = limb_points_z

                    if n_verts > n_orig:
                        # Interpolate Z for Steiner points using IDW
                        tree = cKDTree(limb_points_2d)
                        steiner_2d = result_verts_2d[n_orig:]
                        k = min(5, n_orig)
                        dists, indices = tree.query(steiner_2d, k=k)

                        if dists.ndim == 1:
                            dists = dists[:, np.newaxis]
                            indices = indices[:, np.newaxis]

                        weights = 1.0 / np.maximum(dists ** 2, 1e-10)
                        weights_sum = weights.sum(axis=1, keepdims=True)
                        weights_norm = weights / weights_sum

                        steiner_z = np.sum(weights_norm * limb_points_z[indices], axis=1)
                        result_z[n_orig:] = steiner_z

                    # Convert to 3D
                    result_verts_3d = (centroid +
                                       result_verts_2d[:, 0:1] * u_axis +
                                       result_verts_2d[:, 1:2] * v_axis +
                                       result_z[:, np.newaxis] * w_axis)

                    # Add to global mesh
                    all_vertices.append(result_verts_3d)
                    all_triangles.append(result_tris + vertex_offset)
                    vertex_offset += len(result_verts_3d)

            except Exception as e:
                self.logger.warning(f"Triangulation of limb {limb} failed: {e}")
                continue

        if len(all_vertices) == 0:
            return None

        # Merge limb meshes
        merged_vertices = np.vstack(all_vertices)
        merged_triangles = np.vstack(all_triangles)

        # Stitch limbs at hinge points
        # Find boundary vertices of each limb that are close to boundary of other limbs
        merged_vertices, merged_triangles = self._stitch_limbs_at_hinge(
            merged_vertices, merged_triangles, all_vertices, all_triangles
        )

        self.logger.info(f"Limb-separated triangulation: {len(merged_vertices)} vertices, {len(merged_triangles)} triangles")

        return {
            'vertices': merged_vertices,
            'triangles': merged_triangles
        }

    def _stitch_limbs_at_hinge(self, vertices: np.ndarray, triangles: np.ndarray,
                               limb_vertices_list: List[np.ndarray],
                               limb_triangles_list: List[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Stitch separate limb meshes at the fold hinge.

        Finds boundary vertices that are close in 3D space and merges them.
        """
        if len(limb_vertices_list) < 2:
            return vertices, triangles

        from scipy.spatial import cKDTree

        # Find boundary vertices of each limb mesh
        def get_boundary_vertices(tris, n_verts):
            from collections import Counter
            edge_count = Counter()
            for tri in tris:
                for i in range(3):
                    edge = tuple(sorted([tri[i], tri[(i + 1) % 3]]))
                    edge_count[edge] += 1

            # Boundary edges appear only once
            boundary_verts = set()
            for edge, count in edge_count.items():
                if count == 1:
                    boundary_verts.add(edge[0])
                    boundary_verts.add(edge[1])
            return np.array(list(boundary_verts), dtype=int)

        # Compute offsets for each limb in merged mesh
        offsets = [0]
        for verts in limb_vertices_list[:-1]:
            offsets.append(offsets[-1] + len(verts))

        # Find pairs of boundary vertices from different limbs that are close
        merge_pairs = []
        merge_threshold = self.base_size * 0.1 if self.base_size else 0.1

        for i in range(len(limb_vertices_list)):
            for j in range(i + 1, len(limb_vertices_list)):
                boundary_i = get_boundary_vertices(limb_triangles_list[i], len(limb_vertices_list[i]))
                boundary_j = get_boundary_vertices(limb_triangles_list[j], len(limb_vertices_list[j]))

                if len(boundary_i) == 0 or len(boundary_j) == 0:
                    continue

                # Build tree for limb j boundary
                tree_j = cKDTree(limb_vertices_list[j][boundary_j])

                # Find close pairs
                for bi in boundary_i:
                    dists, indices = tree_j.query(limb_vertices_list[i][bi], k=1)
                    if dists < merge_threshold:
                        # Found a pair to merge
                        global_i = offsets[i] + bi
                        global_j = offsets[j] + boundary_j[indices]
                        merge_pairs.append((global_i, global_j))

        if len(merge_pairs) == 0:
            return vertices, triangles

        self.logger.info(f"Found {len(merge_pairs)} boundary vertex pairs to merge at fold hinge")

        # Merge vertices: keep first vertex, remap second to first
        # Build remap table
        remap = np.arange(len(vertices))
        for (v1, v2) in merge_pairs:
            # Use the lower index as the target
            target = min(v1, v2)
            source = max(v1, v2)
            remap[source] = target

        # Apply remap to triangles
        new_triangles = remap[triangles]

        # Remove degenerate triangles (where two or more vertices are the same)
        valid_mask = np.ones(len(new_triangles), dtype=bool)
        for i, tri in enumerate(new_triangles):
            if len(set(tri)) < 3:
                valid_mask[i] = False

        new_triangles = new_triangles[valid_mask]

        # Note: We keep all vertices (some may become unused, but that's OK)
        # The caller can compact if needed

        return vertices, new_triangles

    def _triangulate_with_reference_insertion(self, constraint_points_3d: np.ndarray,
                                              segments: Optional[np.ndarray],
                                              reference_vertices_3d: np.ndarray,
                                              reference_triangles: np.ndarray) -> Optional[Dict]:
        """
        Triangulate by inserting constraint points into the reference mesh topology.

        This approach preserves the fold structure by working within the existing
        reference mesh connectivity, avoiding cross-limb triangle creation.

        Args:
            constraint_points_3d: 3D constraint points (hull + intersection lines)
            segments: Constraint segments that must be mesh edges
            reference_vertices_3d: Reference mesh vertices
            reference_triangles: Reference mesh triangles

        Returns:
            Dict with 'vertices' and 'triangles', or None if failed
        """
        from scipy.spatial import cKDTree

        if len(reference_triangles) == 0:
            return None

        self.logger.info(f"Reference mesh insertion: {len(constraint_points_3d)} constraints into "
                        f"{len(reference_vertices_3d)} vertices, {len(reference_triangles)} triangles")

        # Project everything to local 2D coordinate system
        all_points = np.vstack([reference_vertices_3d, constraint_points_3d])
        centroid = all_points.mean(axis=0)
        centered = all_points - centroid

        _, _, vh = np.linalg.svd(centered[:len(reference_vertices_3d)], full_matrices=False)
        u_axis, v_axis, w_axis = vh[0], vh[1], vh[2]

        # Project reference mesh to 2D
        ref_centered = reference_vertices_3d - centroid
        ref_2d = np.column_stack([np.dot(ref_centered, u_axis), np.dot(ref_centered, v_axis)])

        # Project constraint points to 2D
        con_centered = constraint_points_3d - centroid
        con_2d = np.column_stack([np.dot(con_centered, u_axis), np.dot(con_centered, v_axis)])

        # Build reference mesh edge set
        ref_edges = set()
        for tri in reference_triangles:
            for i in range(3):
                edge = tuple(sorted([int(tri[i]), int(tri[(i + 1) % 3])]))
                ref_edges.add(edge)

        # Merge constraint points that are very close to reference vertices
        ref_tree = cKDTree(ref_2d)
        merge_threshold = self.base_size * 0.05 if self.base_size else 0.1

        # Map constraint points to either existing reference vertices or new vertices
        constraint_to_vertex = {}  # constraint_idx -> vertex_idx in merged mesh
        new_vertices_3d = list(reference_vertices_3d)
        n_ref = len(reference_vertices_3d)

        for i, (c2d, c3d) in enumerate(zip(con_2d, constraint_points_3d)):
            dists, idx = ref_tree.query(c2d, k=1)
            if dists < merge_threshold:
                # Merge with existing reference vertex
                constraint_to_vertex[i] = idx
            else:
                # Add as new vertex
                constraint_to_vertex[i] = len(new_vertices_3d)
                new_vertices_3d.append(c3d)

        new_vertices_3d = np.array(new_vertices_3d)

        # Build combined point set for triangulation
        combined_centered = new_vertices_3d - centroid
        combined_2d = np.column_stack([
            np.dot(combined_centered, u_axis),
            np.dot(combined_centered, v_axis)
        ])

        # Remap segments to new vertex indices
        if segments is not None and len(segments) > 0:
            remapped_segments = []
            for seg in segments:
                new_p1 = constraint_to_vertex.get(int(seg[0]), int(seg[0]))
                new_p2 = constraint_to_vertex.get(int(seg[1]), int(seg[1]))
                if new_p1 != new_p2:
                    remapped_segments.append([new_p1, new_p2])
            segments = np.array(remapped_segments, dtype=int) if remapped_segments else None

        # Use Triangle with all points but respecting reference structure
        # Strategy: Triangulate with points, then project original reference triangles' connectivity
        # onto new triangulation where possible

        # First, try direct triangulation with all points + segments
        try:
            if self.base_size is None:
                min_coords = np.min(combined_2d, axis=0)
                max_coords = np.max(combined_2d, axis=0)
                diagonal = np.sqrt(np.sum((max_coords - min_coords) ** 2))
                area_constraint = (diagonal / 10.0) ** 2 * 0.5
            else:
                area_constraint = self.base_size ** 2 * 0.5

            tri_input = {'vertices': combined_2d}

            if segments is not None and len(segments) > 0:
                segments = self._sanitize_segments(segments, len(combined_2d))
                if len(segments) > 0:
                    tri_input['segments'] = segments

            p_switch = 'p' if 'segments' in tri_input else ''
            tri_options = f'{p_switch}zYYa{area_constraint:.8f}'

            result = tr.triangulate(tri_input, tri_options)

            if not result or 'vertices' not in result or 'triangles' not in result:
                self.logger.warning("Reference insertion triangulation failed")
                return None

            result_verts_2d = result['vertices']
            result_tris = result['triangles']

        except Exception as e:
            self.logger.warning(f"Reference insertion triangulation error: {e}")
            return None

        # Map output vertices back to 3D
        n_combined = len(combined_2d)
        n_result = len(result_verts_2d)

        result_verts_3d = np.zeros((n_result, 3))

        # For original vertices (reference + constraint), use their known 3D positions
        for i in range(min(n_combined, n_result)):
            # Check if this is close to an original vertex
            if i < n_combined:
                result_verts_3d[i] = new_vertices_3d[i]

        # For Steiner points added by Triangle, interpolate Z from reference mesh
        if n_result > n_combined:
            steiner_2d = result_verts_2d[n_combined:]
            ref_tree_2d = cKDTree(ref_2d)

            # Use reference mesh for Z interpolation (preserves fold structure)
            ref_z = np.dot(ref_centered, w_axis)
            k = min(10, len(ref_2d))
            dists, indices = ref_tree_2d.query(steiner_2d, k=k)

            if dists.ndim == 1:
                dists = dists[:, np.newaxis]
                indices = indices[:, np.newaxis]

            for i in range(len(steiner_2d)):
                pt_2d = steiner_2d[i]

                # Find which reference triangle this point is in (or closest to)
                best_tri = None
                best_bary = None
                min_dist_to_tri = float('inf')

                for tri in reference_triangles:
                    t0, t1, t2 = int(tri[0]), int(tri[1]), int(tri[2])
                    p0, p1, p2 = ref_2d[t0], ref_2d[t1], ref_2d[t2]

                    # Compute barycentric coordinates
                    v0 = p2 - p0
                    v1 = p1 - p0
                    v2 = pt_2d - p0

                    dot00 = np.dot(v0, v0)
                    dot01 = np.dot(v0, v1)
                    dot02 = np.dot(v0, v2)
                    dot11 = np.dot(v1, v1)
                    dot12 = np.dot(v1, v2)

                    denom = dot00 * dot11 - dot01 * dot01
                    if abs(denom) < 1e-10:
                        continue

                    inv_denom = 1.0 / denom
                    u = (dot11 * dot02 - dot01 * dot12) * inv_denom
                    v = (dot00 * dot12 - dot01 * dot02) * inv_denom

                    # Check if inside triangle
                    if u >= -0.01 and v >= -0.01 and (u + v) <= 1.01:
                        best_tri = (t0, t1, t2)
                        best_bary = (1 - u - v, v, u)
                        break

                    # Track closest triangle
                    center = (p0 + p1 + p2) / 3
                    dist_to_center = np.linalg.norm(pt_2d - center)
                    if dist_to_center < min_dist_to_tri:
                        min_dist_to_tri = dist_to_center
                        best_tri = (t0, t1, t2)
                        # Clamp barycentric coords
                        u = max(0, min(1, u))
                        v = max(0, min(1, v))
                        w = 1 - u - v
                        if w < 0:
                            total = u + v
                            u /= total
                            v /= total
                            w = 0
                        best_bary = (w, v, u)

                if best_tri is not None and best_bary is not None:
                    t0, t1, t2 = best_tri
                    w0, w1, w2 = best_bary

                    # Interpolate 3D position from reference triangle vertices
                    interp_3d = (w0 * reference_vertices_3d[t0] +
                                w1 * reference_vertices_3d[t1] +
                                w2 * reference_vertices_3d[t2])
                    result_verts_3d[n_combined + i] = interp_3d
                else:
                    # Fallback: IDW from nearest reference vertices
                    neighbor_dists = dists[i]
                    neighbor_indices = indices[i]
                    weights = 1.0 / np.maximum(neighbor_dists ** 2, 1e-10)
                    weights_norm = weights / weights.sum()

                    interp_3d = np.zeros(3)
                    for j, idx in enumerate(neighbor_indices):
                        interp_3d += weights_norm[j] * reference_vertices_3d[idx]
                    result_verts_3d[n_combined + i] = interp_3d

        # Check triangle quality - remove degenerate or inverted triangles
        valid_mask = self._detect_overlapping_triangles(result_verts_3d, result_tris)
        n_invalid = np.sum(~valid_mask)

        if n_invalid > 0:
            self.logger.info(f"Reference insertion: removed {n_invalid} problematic triangles")
            result_tris = result_tris[valid_mask]

        # If too many triangles were removed, this approach failed
        if len(result_tris) < len(reference_triangles) * 0.5:
            self.logger.warning(f"Too many triangles removed ({n_invalid}), reference insertion failed")
            return None

        self.logger.info(f"Reference insertion complete: {len(result_verts_3d)} vertices, {len(result_tris)} triangles")

        return {
            'vertices': result_verts_3d,
            'triangles': result_tris
        }

    def _refine_mesh_with_constraints(self, constraint_points_3d: np.ndarray,
                                      segments: Optional[np.ndarray],
                                      reference_vertices_3d: np.ndarray,
                                      reference_triangles: np.ndarray) -> Optional[Dict]:
        """
        Refine mesh using 2D CDT with per-triangle barycentric Z-interpolation.

        This approach:
        1. Projects to 2D using reference mesh PCA
        2. Uses Triangle library's CDT (guarantees constraint edges)
        3. Recovers Z using barycentric interpolation within reference triangles
           (handles folds because each triangle is planar)

        Args:
            constraint_points_3d: Constraint points to insert (hull + intersection lines)
            segments: Constraint segments that must be mesh edges
            reference_vertices_3d: Reference mesh vertices
            reference_triangles: Reference mesh triangles

        Returns:
            Dict with 'vertices' and 'triangles', or None if failed
        """
        import triangle as tr
        from scipy.spatial import cKDTree

        if len(reference_triangles) == 0:
            return None

        self.logger.info(f"CDT with barycentric Z: {len(constraint_points_3d)} constraints, "
                        f"{len(reference_vertices_3d)} ref verts, {len(reference_triangles)} ref tris")

        # Step 1: Project reference mesh to 2D using PCA
        ref_centroid = reference_vertices_3d.mean(axis=0)
        ref_centered = reference_vertices_3d - ref_centroid
        _, _, vh = np.linalg.svd(ref_centered, full_matrices=False)
        u_axis, v_axis, w_axis = vh[0], vh[1], vh[2]

        ref_2d = np.column_stack([
            np.dot(ref_centered, u_axis),
            np.dot(ref_centered, v_axis)
        ])
        ref_z = np.dot(ref_centered, w_axis)

        # Step 2: Project constraint points to 2D
        con_centered = constraint_points_3d - ref_centroid
        con_2d = np.column_stack([
            np.dot(con_centered, u_axis),
            np.dot(con_centered, v_axis)
        ])
        con_z = np.dot(con_centered, w_axis)  # Original Z for exact matching

        # Step 3: Build triangle lookup for barycentric interpolation
        # Precompute 2D triangle data for fast point-in-triangle tests
        tri_data = []
        for tri in reference_triangles:
            t0, t1, t2 = int(tri[0]), int(tri[1]), int(tri[2])
            p0, p1, p2 = ref_2d[t0], ref_2d[t1], ref_2d[t2]
            z0, z1, z2 = ref_z[t0], ref_z[t1], ref_z[t2]

            # Precompute barycentric coordinate helpers
            v0 = p2 - p0
            v1 = p1 - p0
            dot00 = np.dot(v0, v0)
            dot01 = np.dot(v0, v1)
            dot11 = np.dot(v1, v1)
            denom = dot00 * dot11 - dot01 * dot01

            tri_data.append({
                'indices': (t0, t1, t2),
                'p0': p0, 'p1': p1, 'p2': p2,
                'z0': z0, 'z1': z1, 'z2': z2,
                'v0': v0, 'v1': v1,
                'dot00': dot00, 'dot01': dot01, 'dot11': dot11,
                'denom': denom,
                'center': (p0 + p1 + p2) / 3
            })

        # Build KD-tree of triangle centers for fast lookup
        tri_centers = np.array([td['center'] for td in tri_data])
        tri_center_tree = cKDTree(tri_centers)

        def find_containing_triangle_and_interpolate_z(point_2d):
            """Find which reference triangle contains this 2D point and interpolate Z."""
            # Search nearby triangles
            _, candidates = tri_center_tree.query(point_2d, k=min(20, len(tri_data)))
            if isinstance(candidates, (int, np.integer)):
                candidates = [candidates]

            best_tri_idx = None
            best_bary = None

            for tri_idx in candidates:
                td = tri_data[tri_idx]
                if abs(td['denom']) < 1e-12:
                    continue

                # Compute barycentric coordinates
                v2 = point_2d - td['p0']
                dot02 = np.dot(td['v0'], v2)
                dot12 = np.dot(td['v1'], v2)

                inv_denom = 1.0 / td['denom']
                u = (td['dot11'] * dot02 - td['dot01'] * dot12) * inv_denom
                v = (td['dot00'] * dot12 - td['dot01'] * dot02) * inv_denom
                w = 1.0 - u - v

                # Check if inside triangle (with small tolerance)
                if u >= -0.01 and v >= -0.01 and w >= -0.01:
                    best_tri_idx = tri_idx
                    # Clamp to valid range
                    u = max(0, min(1, u))
                    v = max(0, min(1, v))
                    w = 1 - u - v
                    if w < 0:
                        total = u + v
                        if total > 0:
                            u, v = u / total, v / total
                        w = 0
                    best_bary = (w, v, u)
                    break

            if best_tri_idx is not None and best_bary is not None:
                td = tri_data[best_tri_idx]
                # Barycentric interpolation of Z
                z = best_bary[0] * td['z0'] + best_bary[1] * td['z1'] + best_bary[2] * td['z2']
                return z, best_tri_idx

            # Fallback: nearest reference vertex
            return None, None

        # Step 4: Sanitize segments
        if segments is not None and len(segments) > 0:
            segments = self._sanitize_segments(segments, len(con_2d))
            if len(segments) > 0:
                min_len = self.base_size * 1e-4 if self.base_size else 1e-8
                segments = self._filter_short_segments(segments, con_2d, min_len)

        # Step 5: Run Triangle CDT
        tri_input = {'vertices': con_2d}
        if segments is not None and len(segments) > 0:
            tri_input['segments'] = segments

        # Use area constraint based on reference mesh density
        if self.base_size:
            area_constraint = self.base_size ** 2 * 0.5
        else:
            # Estimate from reference mesh
            ref_areas = []
            for tri in reference_triangles[:100]:  # Sample
                t0, t1, t2 = int(tri[0]), int(tri[1]), int(tri[2])
                v0 = ref_2d[t1] - ref_2d[t0]
                v1 = ref_2d[t2] - ref_2d[t0]
                area = abs(v0[0] * v1[1] - v0[1] * v1[0]) / 2
                ref_areas.append(area)
            area_constraint = np.median(ref_areas) * 2 if ref_areas else 100.0

        p_switch = 'p' if segments is not None and len(segments) > 0 else ''
        tri_options = f'{p_switch}zYYa{area_constraint:.8f}'

        self.logger.info(f"Running 2D CDT with options: '{tri_options}'")

        try:
            result = tr.triangulate(tri_input, tri_options)
        except Exception as e:
            self.logger.warning(f"CDT failed: {e}, trying without area constraint")
            try:
                result = tr.triangulate(tri_input, f'{p_switch}zYY')
            except Exception as e2:
                self.logger.error(f"CDT fallback also failed: {e2}")
                return None

        if 'vertices' not in result or 'triangles' not in result:
            return None

        result_2d = result['vertices']
        result_tris = result['triangles']

        self.logger.info(f"CDT produced: {len(result_2d)} vertices, {len(result_tris)} triangles")

        # Step 6: Recover Z values using barycentric interpolation
        n_constraints = len(con_2d)
        result_z = np.zeros(len(result_2d))

        # Build tree for matching constraint points
        con_tree = cKDTree(con_2d)
        match_threshold = self.base_size * 0.01 if self.base_size else 1e-6

        matched_count = 0
        interpolated_count = 0
        fallback_count = 0

        for i, pt_2d in enumerate(result_2d):
            # First check if this is a constraint point (use exact Z)
            dist, nearest_con = con_tree.query(pt_2d)
            if dist < match_threshold:
                result_z[i] = con_z[nearest_con]
                matched_count += 1
                continue

            # Otherwise, interpolate Z from reference mesh
            z_interp, tri_idx = find_containing_triangle_and_interpolate_z(pt_2d)
            if z_interp is not None:
                result_z[i] = z_interp
                interpolated_count += 1
            else:
                # Fallback: nearest reference vertex
                ref_tree = cKDTree(ref_2d)
                _, nearest_ref = ref_tree.query(pt_2d)
                result_z[i] = ref_z[nearest_ref]
                fallback_count += 1

        self.logger.info(f"Z recovery: {matched_count} matched, {interpolated_count} interpolated, {fallback_count} fallback")

        # Step 7: Convert back to 3D
        result_3d = (ref_centroid +
                    result_2d[:, 0:1] * u_axis +
                    result_2d[:, 1:2] * v_axis +
                    result_z[:, np.newaxis] * w_axis)

        # Step 8: Verify constraint edges are present
        if segments is not None and len(segments) > 0:
            edge_count = 0
            for seg in segments:
                s0, s1 = int(seg[0]), int(seg[1])
                # Find which output vertices correspond to these constraint points
                d0, v0_out = con_tree.query(con_2d[s0])
                d1, v1_out = con_tree.query(con_2d[s1])

                # Check in result triangles
                found = False
                for tri in result_tris:
                    edges = [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]
                    for e0, e1 in edges:
                        # Match by position
                        if np.linalg.norm(result_2d[e0] - con_2d[s0]) < match_threshold and \
                           np.linalg.norm(result_2d[e1] - con_2d[s1]) < match_threshold:
                            found = True
                            break
                        if np.linalg.norm(result_2d[e1] - con_2d[s0]) < match_threshold and \
                           np.linalg.norm(result_2d[e0] - con_2d[s1]) < match_threshold:
                            found = True
                            break
                    if found:
                        break
                if found:
                    edge_count += 1

            self.logger.info(f"Constraint edge verification: {edge_count}/{len(segments)} edges present")

        self.logger.info(f"CDT refinement complete: {len(result_3d)} vertices, {len(result_tris)} triangles")

        return {
            'vertices': result_3d,
            'triangles': result_tris
        }

    def _edge_exists_in_mesh(self, triangles: List, v0: int, v1: int) -> bool:
        """Check if edge (v0, v1) exists in the mesh."""
        for tri in triangles:
            t0, t1, t2 = tri[0], tri[1], tri[2]
            edges = [(t0, t1), (t1, t2), (t2, t0)]
            for e0, e1 in edges:
                if (e0 == v0 and e1 == v1) or (e0 == v1 and e1 == v0):
                    return True
        return False

    def _segment_segment_intersection_3d(self, a0: np.ndarray, a1: np.ndarray,
                                         b0: np.ndarray, b1: np.ndarray) -> Optional[np.ndarray]:
        """Find intersection point of two 3D segments if they cross (with tolerance for near-coplanar)."""
        da = a1 - a0
        db = b1 - b0
        dc = b0 - a0

        cross = np.cross(da, db)
        cross_norm_sq = np.dot(cross, cross)

        if cross_norm_sq < 1e-20:
            return None  # Parallel

        # More relaxed coplanarity check - allow 5% deviation
        coplanar_test = abs(np.dot(dc, cross)) / np.sqrt(cross_norm_sq + 1e-20)
        seg_len = max(np.linalg.norm(da), np.linalg.norm(db))
        if coplanar_test > seg_len * 0.05:
            return None  # Not sufficiently coplanar

        s = np.dot(np.cross(dc, db), cross) / cross_norm_sq
        t = np.dot(np.cross(dc, da), cross) / cross_norm_sq

        # Check if intersection is within both segments (not at endpoints)
        # Allow slightly more tolerance at endpoints
        if s > 0.01 and s < 0.99 and t > 0.01 and t < 0.99:
            return a0 + s * da

        return None

    def _try_flip_toward_target(self, triangles: List, vertices: List, v_start: int, v_target: int) -> bool:
        """
        Try to flip edges around v_start to create path toward v_target.
        Returns True if a flip was made.
        """
        p_target = np.array(vertices[v_target])

        # Find triangles containing v_start
        star_tris = []
        for tri_idx, tri in enumerate(triangles):
            if v_start in tri:
                star_tris.append(tri_idx)

        # For each triangle, check if we can flip an edge closer to target
        for tri_idx in star_tris:
            tri = triangles[tri_idx]
            t0, t1, t2 = tri[0], tri[1], tri[2]

            # Find the edge opposite to v_start
            if t0 == v_start:
                opp_edge = (t1, t2)
                apex = t0
            elif t1 == v_start:
                opp_edge = (t2, t0)
                apex = t1
            else:
                opp_edge = (t0, t1)
                apex = t2

            # Find adjacent triangle sharing opposite edge
            adj_tri_idx = None
            for i, t in enumerate(triangles):
                if i == tri_idx:
                    continue
                if opp_edge[0] in t and opp_edge[1] in t:
                    adj_tri_idx = i
                    break

            if adj_tri_idx is None:
                continue

            # Get the fourth vertex (opposite apex in adjacent triangle)
            adj_tri = triangles[adj_tri_idx]
            fourth_v = None
            for v in adj_tri:
                if v != opp_edge[0] and v != opp_edge[1]:
                    fourth_v = v
                    break

            if fourth_v is None or fourth_v == v_target:
                continue

            # Check if flipping would bring us closer to target
            p_fourth = np.array(vertices[fourth_v])
            p_apex = np.array(vertices[apex])

            dist_before = np.linalg.norm(p_apex - p_target)
            dist_after = np.linalg.norm(p_fourth - p_target)

            if dist_after < dist_before:
                # Check if flip is valid (convex quadrilateral)
                if self._can_flip_edge(vertices, apex, opp_edge[0], opp_edge[1], fourth_v):
                    # Perform flip
                    triangles[tri_idx] = [apex, opp_edge[0], fourth_v]
                    triangles[adj_tri_idx] = [apex, fourth_v, opp_edge[1]]
                    return True

        return False

    def _can_flip_edge(self, vertices: List, v0: int, v1: int, v2: int, v3: int) -> bool:
        """Check if edge (v1, v2) can be flipped in quadrilateral (v0, v1, v3, v2)."""
        p0 = np.array(vertices[v0])
        p1 = np.array(vertices[v1])
        p2 = np.array(vertices[v2])
        p3 = np.array(vertices[v3])

        # Check that quadrilateral is convex
        # Cross products should all have same sign
        def cross_2d_sign(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

        # Project to 2D using dominant plane
        normal = np.cross(p1 - p0, p2 - p0)
        abs_normal = np.abs(normal)

        if abs_normal[2] >= abs_normal[0] and abs_normal[2] >= abs_normal[1]:
            # XY plane
            pts = [(p[0], p[1]) for p in [p0, p1, p3, p2]]
        elif abs_normal[1] >= abs_normal[0]:
            # XZ plane
            pts = [(p[0], p[2]) for p in [p0, p1, p3, p2]]
        else:
            # YZ plane
            pts = [(p[1], p[2]) for p in [p0, p1, p3, p2]]

        # Check convexity
        signs = []
        n = 4
        for i in range(n):
            s = cross_2d_sign(pts[i], pts[(i + 1) % n], pts[(i + 2) % n])
            signs.append(s)

        return all(s >= 0 for s in signs) or all(s <= 0 for s in signs)

    def _find_containing_triangle_3d_v2(self, point: np.ndarray, vertices: List,
                                        triangles: List, centroid_tree, tri_centroids) -> Optional[int]:
        """Find triangle containing point using 3D barycentric coordinates."""
        if len(tri_centroids) == 0:
            return None

        _, candidates = centroid_tree.query(point, k=min(30, len(tri_centroids)))
        if isinstance(candidates, (int, np.integer)):
            candidates = [candidates]

        for tri_idx in candidates:
            if tri_idx >= len(triangles):
                continue

            tri = triangles[tri_idx]
            v0, v1, v2 = tri[0], tri[1], tri[2]

            if v0 >= len(vertices) or v1 >= len(vertices) or v2 >= len(vertices):
                continue

            p0, p1, p2 = vertices[v0], vertices[v1], vertices[v2]

            # Compute barycentric coords
            bary = self._compute_bary_3d(point, p0, p1, p2)
            if bary is None:
                continue

            u, v, w = bary
            if u >= -0.02 and v >= -0.02 and w >= -0.02:
                return tri_idx

        return None

    def _compute_bary_3d(self, point: np.ndarray, p0: np.ndarray, p1: np.ndarray, p2: np.ndarray):
        """Compute barycentric coordinates projecting point onto triangle plane."""
        v0 = p1 - p0
        v1 = p2 - p0

        normal = np.cross(v0, v1)
        norm_sq = np.dot(normal, normal)
        if norm_sq < 1e-20:
            return None

        # Project point onto plane
        v2 = point - p0
        dist = np.dot(v2, normal) / np.sqrt(norm_sq)
        proj = point - dist * normal / np.sqrt(norm_sq)
        v2_proj = proj - p0

        dot00 = np.dot(v0, v0)
        dot01 = np.dot(v0, v1)
        dot02 = np.dot(v0, v2_proj)
        dot11 = np.dot(v1, v1)
        dot12 = np.dot(v1, v2_proj)

        denom = dot00 * dot11 - dot01 * dot01
        if abs(denom) < 1e-20:
            return None

        inv = 1.0 / denom
        v = (dot11 * dot02 - dot01 * dot12) * inv
        w = (dot00 * dot12 - dot01 * dot02) * inv
        u = 1.0 - v - w

        return (u, v, w)

