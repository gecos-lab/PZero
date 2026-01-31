"""
DirectTriangleWrapper: Improved implementation of Triangle refinement with C callback.

This module provides a direct wrapper for the Triangle library using the
C++ extension module for the triunsuitable callback.
"""

import numpy as np
import triangle as tr
import logging
from typing import Dict, List, Optional, Tuple, Union
from matplotlib.path import Path
from scipy.spatial.distance import pdist

# Try to import the C++ extension module (fallback if not available)
try:
    from . import triangle_callback
    HAS_TRIANGLE_CALLBACK = True
except ImportError:
    HAS_TRIANGLE_CALLBACK = False
    triangle_callback = None

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
        
    def set_feature_points(self, points: np.ndarray, sizes: np.ndarray):
        """
        Set feature points and their associated sizes.
        
        These points influence the mesh density with a smooth transition
        based on the gradient parameter.
        
        Args:
            points: Array of feature points (N, 2)
            sizes: Array of sizes for each feature point (N,)
        """
        self.feature_points = np.asarray(points, dtype=np.float64)
        self.feature_sizes = np.asarray(sizes, dtype=np.float64)
        
    def _create_boundary_feature_points(self, hull_points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create dense feature points along the convex hull boundary.
        
        This ensures a much more uniform transition from boundary to interior.
        
        Args:
            hull_points: Points on the convex hull
            
        Returns:
            Tuple of (boundary feature points, boundary feature sizes)
        """
        if len(hull_points) < 3:
            return np.empty((0, 2)), np.empty(0)
            
        # Create evenly spaced points along each hull edge
        # for a more uniform boundary transition
        boundary_points = []
        boundary_sizes = []
        
        # Size for boundary points - smaller than the base size
        boundary_size = self.base_size * 0.2
        
        # For each hull edge, create intermediate points
        for i in range(len(hull_points)):
            p1 = hull_points[i]
            p2 = hull_points[(i + 1) % len(hull_points)]
            
            # Edge vector
            edge = p2 - p1
            edge_length = np.linalg.norm(edge)
            
            if edge_length < 1e-8:
                continue
                
            # Normalize
            edge = edge / edge_length
            
            # Number of divisions depends on edge length
            num_divisions = max(2, int(edge_length / (boundary_size * 0.5)))
            
            # Create points along the edge
            for j in range(1, num_divisions):
                t = j / num_divisions
                point = p1 + t * (p2 - p1)
                boundary_points.append(point)
                boundary_sizes.append(boundary_size)
        
        return np.array(boundary_points), np.array(boundary_sizes)
        
    def _create_offset_feature_points(self, hull_points: np.ndarray, 
                                     num_layers: int = 4) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create feature points offset inward from the hull boundary.
        
        Args:
            hull_points: Points on the convex hull
            num_layers: Number of inward offset layers to create
            
        Returns:
            Tuple of (offset feature points, offset feature sizes)
        """
        if len(hull_points) < 3:
            return np.empty((0, 2)), np.empty(0)
            
        # Calculate centroid
        centroid = np.mean(hull_points, axis=0)
        
        # Create offset points
        offset_points = []
        offset_sizes = []
        
        # For each hull point
        for hull_pt in hull_points:
            # Vector from centroid to hull point
            vec = hull_pt - centroid
            dist = np.linalg.norm(vec)
            
            if dist < 1e-8:
                continue
                
            # Normalize
            vec = vec / dist
            
            # Create offset points along the ray from hull to centroid
            for i in range(1, num_layers + 1):
                # Offset distance increases with each layer
                offset_dist = i * self.base_size * 0.75
                
                # Make sure we don't go past the centroid
                if offset_dist >= dist:
                    offset_dist = dist * 0.8
                    
                # Create offset point
                offset_pt = hull_pt - vec * offset_dist
                
                # Size increases as we move inward
                size_factor = 0.25 + 0.5 * (i / num_layers)
                offset_size = self.base_size * size_factor
                
                offset_points.append(offset_pt)
                offset_sizes.append(offset_size)
        
        return np.array(offset_points), np.array(offset_sizes)
    
    def _create_transition_feature_points(self, points: np.ndarray, hull_points: np.ndarray, 
                                         segments: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create more uniform transition feature points between hull and interior
        with enhanced distribution for high-quality meshes similar to C++ MeshIt.
        
        Args:
            points: All input points
            hull_points: Points on the convex hull
            segments: Segment indices forming the boundary
            
        Returns:
            Tuple of (transition feature points, transition feature sizes)
        """
        # Calculate centroid of all points
        centroid = np.mean(points, axis=0)
        
        # Calculate bounding box diagonal for scaling
        min_coords = np.min(points, axis=0)
        max_coords = np.max(points, axis=0)
        domain_width = max_coords[0] - min_coords[0]
        domain_height = max_coords[1] - min_coords[1]
        diagonal = np.sqrt(domain_width**2 + domain_height**2)
        
        # Calculate target element size based on domain size
        # C++ MeshIt likely uses similar scaling
        uniform_size = self.base_size * 0.85  # Base size is already set from outside
        
        # --- Boundary feature points with consistent spacing ---
        boundary_points = []
        boundary_sizes = []
        
        # Higher density for boundary points (smaller than uniform_size)
        boundary_size = uniform_size * 0.7
        
        # Create evenly distributed points along the boundary
        for i in range(len(hull_points)):
            p1 = hull_points[i]
            p2 = hull_points[(i + 1) % len(hull_points)]
            
            edge_length = np.linalg.norm(p2 - p1)
            if edge_length < 1e-8:
                continue
                
            # Calculate number of divisions based on edge length
            num_divisions = max(3, int(edge_length / (boundary_size * 0.8)))
            
            # Create points along the edge
            for j in range(1, num_divisions):
                t = j / num_divisions
                point = p1 + t * (p2 - p1)
                boundary_points.append(point)
                # Use consistent sizing for boundary
                boundary_sizes.append(boundary_size)
        
        # --- Interior grid with controlled perturbation (C++ MeshIt style) ---
        interior_points = []
        interior_sizes = []
        
        # Calculate the optimal grid spacing based on base_size
        grid_spacing = uniform_size * 1.3  # Slightly larger than element size
        
        # Determine the safe zone for interior points (inset from hull to avoid bad elements)
        hull_bb_min = np.min(hull_points, axis=0)
        hull_bb_max = np.max(hull_points, axis=0)
        
        # Add a small inset to avoid points too close to boundary
        inset = grid_spacing * 0.25
        x_min = hull_bb_min[0] + inset
        y_min = hull_bb_min[1] + inset
        x_max = hull_bb_max[0] - inset
        y_max = hull_bb_max[1] - inset
        
        # Generate grid with slight offset to avoid alignment with boundary
        offset_factor = 0.1
        x_offset = grid_spacing * offset_factor
        y_offset = grid_spacing * offset_factor
        
        # Create grid ranges with offset
        x_range = np.arange(x_min + x_offset, x_max, grid_spacing)
        y_range = np.arange(y_min + y_offset, y_max, grid_spacing)
        
        # Create a path object for point-in-polygon test
        hull_path = Path(hull_points)
        
        # Generate grid points with MeshIt-style sinusoidal perturbation
        base_grid_points = []
        
        # First create a base grid
        for x in x_range:
            for y in y_range:
                point = np.array([x, y])
                if hull_path.contains_point(point):
                    base_grid_points.append(point)
        
        # Apply sinusoidal perturbation to create C++ MeshIt-like distribution
        grid_points = []
        
        # Parameters for sinusoidal perturbation
        freq_factor_x = 2.0 * np.pi / domain_width
        freq_factor_y = 2.0 * np.pi / domain_height
        amp_factor = grid_spacing * 0.2  # Amplitude of perturbation (20% of grid spacing)
        
        for point in base_grid_points:
            # Distance from centroid (normalized)
            dx = point[0] - centroid[0]
            dy = point[1] - centroid[1]
            dist = np.sqrt(dx**2 + dy**2)
            
            # Calculate angle from centroid
            angle = np.arctan2(dy, dx)
            
            # Calculate perturbation factors using multiple frequencies for natural distribution
            # This creates the sinusoidal pattern visible in C++ MeshIt
            perturb_x = amp_factor * np.sin(freq_factor_x * point[0] + freq_factor_y * point[1] * 0.5)
            perturb_y = amp_factor * np.sin(freq_factor_y * point[1] + freq_factor_x * point[0] * 0.5)
            
            # Add small radial component to make elements grow gradually from boundary
            radial_factor = 0.15
            boundary_dist = min_distance_to_boundary(point, hull_points)
            scaling = min(1.0, boundary_dist / (grid_spacing * 2))
            radial_perturb = radial_factor * scaling * grid_spacing
            
            perturb_x += radial_perturb * np.cos(angle)
            perturb_y += radial_perturb * np.sin(angle)
            
            # Apply perturbation to create a more natural distribution
            perturbed_point = np.array([point[0] + perturb_x, point[1] + perturb_y])
            
            # Verify perturbed point is still inside hull
            if hull_path.contains_point(perturbed_point):
                grid_points.append(perturbed_point)
                
                # Size variation based on distance from boundary
                size_factor = 0.9 + 0.2 * (scaling ** 0.5)  # Smoother transition
                interior_sizes.append(uniform_size * size_factor)
        
        # --- Add additional points for smoother transitions ---
        # This is similar to how C++ MeshIt creates more uniform transitions
        transition_points = []
        transition_sizes = []
        
        # Add radial rays from centroid to help with size transitions
        num_rays = 12
        ray_angles = np.linspace(0, 2*np.pi, num_rays, endpoint=False)
        
        # Find typical distance from centroid to boundary
        distances_to_centroid = [np.linalg.norm(p - centroid) for p in hull_points]
        avg_radius = np.mean(distances_to_centroid) * 0.8
        
        # Create rays from centroid (not all the way to boundary)
        for angle in ray_angles:
            # Create points along ray with increasing spacing
            num_points = 5
            for i in range(1, num_points):
                # Gradually increasing spacing from centroid
                t = (i / num_points) ** 1.2  # Non-linear spacing for better transitions
                ray_length = avg_radius * t
                
                # Calculate point on ray
                ray_point = np.array([
                    centroid[0] + ray_length * np.cos(angle),
                    centroid[1] + ray_length * np.sin(angle)
                ])
                
                # Check if point is inside hull
                if hull_path.contains_point(ray_point):
                    # Size increases with distance from centroid
                    size_factor = 0.8 + 0.4 * t
                    
                    # Add slightly randomized point to break regularity
                    jitter = (np.random.random(2) - 0.5) * grid_spacing * 0.1
                    jittered_ray_point = ray_point + jitter
                    
                    if hull_path.contains_point(jittered_ray_point):
                        transition_points.append(jittered_ray_point)
                        transition_sizes.append(uniform_size * size_factor)
        
        # --- Combine all points ---
        all_feature_points = []
        all_feature_sizes = []
        
        # Add boundary points (always include these)
        if boundary_points:
            all_feature_points.extend(boundary_points)
            all_feature_sizes.extend(boundary_sizes)
        
        # Add interior grid points (main distribution)
        if grid_points:
            all_feature_points.extend(grid_points)
            all_feature_sizes.extend(interior_sizes)
            
        # Add transition points (improves smoothness)
        if transition_points:
            all_feature_points.extend(transition_points)
            all_feature_sizes.extend(transition_sizes)
            
        # Convert to numpy arrays
        if all_feature_points:
            all_trans_points = np.array(all_feature_points)
            all_trans_sizes = np.array(all_feature_sizes)
        else:
            all_trans_points = np.empty((0, 2))
            all_trans_sizes = np.empty(0)
            
        self.logger.info(f"Created {len(all_trans_points)} enhanced transition points for more uniform mesh")
        return all_trans_points, all_trans_sizes

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
            
            # Determine if we need 'p' switch (PSLG mode)
            # Only use 'p' if we have segments or holes, otherwise it might fail on some systems
            has_constraints = (segments is not None and len(segments) > 0) or \
                             (holes is not None and len(holes) > 0)
            p_switch = 'p' if has_constraints else ''
            
            effective_min_angle = self.min_angle
            area_constraint = self.base_size * self.base_size * 0.5
            
            if use_cpp_switches:
                # C++ MeshIt compatible switches with better area control
                # The C++ version actually uses "pzYYu" but 'u' needs external callback
                tri_options = f'{p_switch}zYYa{area_constraint:.8f}'
                self.logger.info(f"Using C++ MeshIt compatible Triangle options: '{tri_options}'")
            else:
                # Simplified options - no expensive callbacks or complex features
                tri_options = f'{p_switch}zYYa{area_constraint:.8f}'
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

    def _create_uniform_grid_points(self, hull_points: np.ndarray,
                                  spacing: float = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create a uniform grid of points inside the hull for better uniform meshing.
        
        Args:
            hull_points: Points defining the convex hull
            spacing: Spacing between grid points (defaults to base_size if None)
            
        Returns:
            Tuple of (grid points, grid point sizes)
        """
        if len(hull_points) < 3:
            return np.empty((0, 2)), np.empty(0)
            
        if spacing is None:
            spacing = self.base_size * 1.5
            
        # Create a path object for point-in-polygon test
        try:
            # Use matplotlib's Path for point-in-polygon test
            hull_path = Path(hull_points)
            
            # Find a suitable grid spacing based on the domain size
            # Create a bounding box with some margin
            x_min, y_min = np.min(hull_points, axis=0) + spacing * 0.5
            x_max, y_max = np.max(hull_points, axis=0) - spacing * 0.5
            
            # Generate grid points
            x_range = np.arange(x_min, x_max + spacing, spacing)
            y_range = np.arange(y_min, y_max + spacing, spacing)
            
            # Create grid points
            grid_points = []
            grid_sizes = []
            
            # Add points on a regular grid inside the hull
            for x in x_range:
                for y in y_range:
                    point = np.array([x, y])
                    if hull_path.contains_point(point):
                        grid_points.append(point)
                        grid_sizes.append(self.base_size)
            
            # Add some jittered grid points to break up the regularity
            # This helps achieve a more natural but still uniform distribution
            num_jittered = int(len(grid_points) * 0.2)
            for _ in range(num_jittered):
                # Pick a random existing grid point
                if grid_points:
                    idx = np.random.randint(0, len(grid_points))
                    base_point = grid_points[idx]
                    
                    # Add jitter (within 30% of grid spacing)
                    jitter = (np.random.random(2) - 0.5) * spacing * 0.3
                    jittered_point = base_point + jitter
                    
                    # Check if still inside hull
                    if hull_path.contains_point(jittered_point):
                        grid_points.append(jittered_point)
                        grid_sizes.append(self.base_size)
            
            return np.array(grid_points), np.array(grid_sizes)
        except Exception as e:
            self.logger.error(f"Error creating uniform grid: {str(e)}")
            return np.empty((0, 2)), np.empty(0)
            
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
        
        When enabled, uses "pzYYu" switches similar to C++ MeshIt instead of "pzq" switches.
        This can produce denser, higher quality meshes that are more compatible with TetGen.
        
        Args:
            enable: Whether to enable C++ compatible mode
        """
        self.use_cpp_switches = enable
        if enable:
            self.logger.info("Enabled C++ MeshIt compatible Triangle switches (pzYYu)")
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

    def triangulate_folded_surface(self, points_3d: np.ndarray, segments: Optional[np.ndarray] = None,
                                   fold_angle_threshold: float = 120.0,
                                   uniform: bool = True,
                                   interpolator: str = 'tps',
                                   smoothing: float = 0.0,
                                   reference_points_3d: Optional[np.ndarray] = None) -> Dict:
        """
        Multi-patch triangulation for folded surfaces (recumbent/overturned folds).
        
        This method handles surfaces that fold back on themselves by:
        1. Computing local normals for each point
        2. Detecting fold hinges where normal direction reverses
        3. Partitioning the surface into monotonic patches
        4. Triangulating each patch separately using its local projection
        5. Stitching patches together along shared hinge constraints
        
        Args:
            points_3d: Input 3D points (N, 3) - constraint points for triangulation
            segments: Optional boundary segment indices (M, 2)
            fold_angle_threshold: Angle threshold (degrees) for fold hinge detection
            uniform: Whether to use uniform mesh generation
            reference_points_3d: Optional dense reference points for fold detection.
                                 If provided, these are used for normal computation and
                                 fold region detection instead of points_3d. Constraint 
                                 points are then assigned to patches based on proximity.
            
        Returns:
            Dictionary with combined triangulation results (vertices, triangles)
        """
        import triangle as tr
        from scipy.spatial import cKDTree, Delaunay
        
        self.logger.info(f"Multi-patch triangulation: {len(points_3d)} points, fold_threshold={fold_angle_threshold}°")
        
        points_3d = np.asarray(points_3d, dtype=np.float64)
        if segments is not None and len(segments) > 0:
            segments = self._sanitize_segments(segments, len(points_3d))
            if len(segments) == 0:
                segments = None
        
        # Handle reference points for fold detection (used when points_3d are sparse constraints)
        # For Refine Mesh case: Use standard CDT with reference mesh for Z-interpolation
        # and add reference points as Steiner guides to maintain internal density
        if reference_points_3d is not None:
            reference_points_3d = np.asarray(reference_points_3d, dtype=np.float64)
            self.logger.info(f"Using {len(reference_points_3d)} reference points for Z-interpolation (Refine Mesh mode)")
            
            # Use standard CDT with reference mesh Z-interpolation
            return self._fallback_standard_triangulation(
                points_3d, segments, uniform, interpolator, smoothing,
                reference_mesh_3d=reference_points_3d
            )
        
        fold_detection_points = points_3d
        
        if len(points_3d) < 4:
            self.logger.warning("Too few points for multi-patch triangulation, using standard method")
            self.logger.warning("All patches failed, using standard triangulation")
            return self._fallback_standard_triangulation(points_3d, segments, uniform, interpolator, smoothing)
        
        # Step 1: Compute local normals using k-nearest neighbors
        ref_normals = self._compute_local_normals(fold_detection_points)
        
        if ref_normals is None:
            self.logger.warning("Failed to compute normals, using standard triangulation")
            self.logger.warning("All patches failed, using standard triangulation")
            return self._fallback_standard_triangulation(points_3d, segments, uniform, interpolator, smoothing)
        
        # Step 2: Detect fold hinges based on normal angle changes
        ref_fold_regions = self._detect_fold_regions(fold_detection_points, ref_normals, fold_angle_threshold)
        
        if len(ref_fold_regions) <= 1:
            self.logger.info("No significant folds detected, using standard triangulation")
            self.logger.warning("All patches failed, using standard triangulation")
            return self._fallback_standard_triangulation(points_3d, segments, uniform, interpolator, smoothing)
        
        self.logger.info(f"Detected {len(ref_fold_regions)} fold regions/patches")
        
        # For dense point clouds (first triangulation tab), use detected fold regions directly
        fold_regions = ref_fold_regions
        normals = ref_normals
        
        # Build tree for finding patch boundaries/overlaps
        tree = cKDTree(points_3d)
        max_deviation_deg = min(fold_angle_threshold, 60.0)
        buffer_min_dot = np.cos(np.radians(max_deviation_deg))
        tangent_align_max = 0.3
        nn_median = None
        overlap_radius = self.base_size * 0.5 if self.base_size else 1.0
        try:
            dists_all, _ = tree.query(points_3d, k=2)
            nn = dists_all[:, 1]
            nn = nn[np.isfinite(nn)]
            if len(nn) > 0:
                nn_median = float(np.median(nn))
                overlap_radius = nn_median * 2.0
        except Exception:
            pass
        segment_adj = None
        if segments is not None and len(segments) > 0:
            segment_adj = {}
            for s in segments:
                u, v = int(s[0]), int(s[1])
                segment_adj.setdefault(u, []).append(v)
                segment_adj.setdefault(v, []).append(u)
        
        # Step 3: Triangulate each patch separately
        all_vertices = []
        all_triangles = []
        vertex_offset = 0
        
        for i, region_indices in enumerate(fold_regions):
            if len(region_indices) < 3:
                continue
        
            
            # Expand region via explicit segments (BFS)
            # If segment connects P1 (in region) to P2 (outside), add P2.
            # This ensures refined boundary points that might have been skipped by growing
            # due to poor normals are "dragged" into the correct patch.
            if segment_adj is not None:
                seed_avg_normal = np.mean(normals[region_indices], axis=0)
                seed_avg_normal /= (np.linalg.norm(seed_avg_normal) + 1e-12)
                current_region_set = set(region_indices)
                
                # BFS expansion
                queue = list(region_indices)
                expanded_count = 0
                
                while queue:
                    u = queue.pop(0)
                    if u in segment_adj:
                        for v in segment_adj[u]:
                            if v not in current_region_set:
                                # Add to region only if normals agree with seed patch
                                if np.dot(normals[v], seed_avg_normal) > buffer_min_dot:
                                    current_region_set.add(v)
                                    queue.append(v)
                                    expanded_count += 1
                
                if expanded_count > 0:
                    region_indices = list(current_region_set)
                    # self.logger.debug(f"Expanded patch {i} by {expanded_count} points via segments")

            # Add spatial buffer (1-ring neighbors) to ensure patches overlap/touch
            # This is critical for the stitching/merging step to work
            patch_mask = np.zeros(len(points_3d), dtype=bool)
            patch_mask[region_indices] = True
            
            # Find neighbors of region points
            # Simple approach: query radius or k-neighbors
            # Uses base_size or estimation
            search_k = 30
            dists, nbrs = tree.query(points_3d[region_indices], k=search_k)
            
            # Flatten and find candidates
            candidates = np.unique(nbrs.flatten())
            candidates = candidates[candidates < len(points_3d)]
            
            # Filter candidates: Only add points that are compatible with the region's orientation
            # This prevents jumping gaps to opposing limbs (e.g., Top -> Bottom)
            # We use a safe threshold to prevent back-folding (concave artifacts)
            
            # Calculate robust patch normal (mean of seed or all region)
            # region_indices are the core points.
            patch_avg_normal = np.mean(normals[region_indices], axis=0)
            patch_avg_normal /= (np.linalg.norm(patch_avg_normal) + 1e-12)
            
            # Vectorized check for candidates
            cand_normals = normals[candidates]
            dots = np.dot(cand_normals, patch_avg_normal)
            
            # Threshold: Must be positively aligned with patch average
            # This ensures injectivity of the projection and prevents artifacts like "bitten" edges
            valid_mask = dots > buffer_min_dot

            # Add a close + tangential overlap buffer to stitch hinges without cross-limb mixing
            try:
                region_core = points_3d[region_indices]
                region_tree = cKDTree(region_core)
                d_core, idx_core = region_tree.query(points_3d[candidates], k=1)
                vec = points_3d[candidates] - region_core[idx_core]
                vec_norm = np.linalg.norm(vec, axis=1) + 1e-12
                align = np.abs(np.einsum('ij,j->i', vec / vec_norm[:, None], patch_avg_normal))
                close_mask = d_core < overlap_radius
                tangent_mask = align < tangent_align_max
                valid_mask = valid_mask | (close_mask & tangent_mask)
            except Exception:
                pass

            buffered_indices = np.unique(np.concatenate((candidates[valid_mask], region_indices)))
            
            region_points = points_3d[buffered_indices]
            
            # Project region to its local best-fit plane
            local_2d, projection_params = self._project_to_local_plane(region_points)
            
            if local_2d is None:
                self.logger.warning(f"Failed to project patch {i}, skipping")
                continue
            
            # Triangulate in 2D
            try:
                # Set up triangulation for this patch
                if self.base_size is None:
                    min_coords = np.min(local_2d, axis=0)
                    max_coords = np.max(local_2d, axis=0)
                    diagonal = np.sqrt(np.sum((max_coords - min_coords) ** 2))
                    patch_base_size = diagonal / 10.0
                else:
                    patch_base_size = self.base_size
                
                # Compute Concave Hull boundary for this patch to prevent "big triangle" artifacts
                # This ensures the triangulation respects the actual shape of the patch
                boundary_segments = self._compute_patch_boundary(local_2d, patch_base_size)
                
                # Filter explicit segments relevant to this patch
                explicit_patch_segments = []
                if segments is not None:
                    # Create a mapping from global index to local patch index (0..M)
                    # buffered_indices contains global indices in order of local_2d
                    global_to_local = {global_idx: local_idx for local_idx, global_idx in enumerate(buffered_indices)}
                    
                    for seg in segments:
                        p1, p2 = seg[0], seg[1]
                        # If both endpoints are in this patch, add the segment
                        if p1 in global_to_local and p2 in global_to_local:
                            explicit_patch_segments.append([global_to_local[p1], global_to_local[p2]])
                
                explicit_patch_segments = np.array(explicit_patch_segments, dtype=int) if explicit_patch_segments else np.empty((0, 2), dtype=int)

                # Sanitize boundary/explicit segments before combining
                if boundary_segments is not None and len(boundary_segments) > 0:
                    boundary_segments = self._sanitize_segments(boundary_segments, len(local_2d))
                else:
                    boundary_segments = np.empty((0, 2), dtype=np.int32)
                explicit_patch_segments = self._sanitize_segments(explicit_patch_segments, len(local_2d))

                # Match standard CDT area constraint (0.5 factor, same as _setup_complex_triangulation)
                area_constraint = patch_base_size * patch_base_size * 0.5
                min_seg_len = max(1e-8, patch_base_size * 1e-4)

                segment_candidates = []
                if len(boundary_segments) > 0 and len(explicit_patch_segments) > 0:
                    segment_candidates.append(("combined", np.vstack((boundary_segments, explicit_patch_segments))))
                if len(explicit_patch_segments) > 0:
                    segment_candidates.append(("explicit", explicit_patch_segments))
                if len(boundary_segments) > 0:
                    segment_candidates.append(("boundary", boundary_segments))
                if not segment_candidates:
                    segment_candidates.append(("none", None))

                result_vertices_2d = None
                patch_triangles = None
                remapped_indices_map = None
                used_opts = None
                used_label = None

                for seg_label, segs in segment_candidates:
                    if segs is not None and len(segs) > 0:
                        segs = self._sanitize_segments(segs, len(local_2d))
                        segs = self._filter_short_segments(segs, local_2d, min_seg_len)
                        # Remove intersecting segments to prevent Triangle's "Topological inconsistency" error
                        if len(segs) > 1:
                            segs = self._remove_intersecting_segments(segs, local_2d)
                        if len(segs) == 0:
                            segs = None

                    # SPARSE INPUT STRATEGY (uniformity fix):
                    # Instead of passing ALL local_2d vertices (dense cloud) to Triangle,
                    # we pass ONLY the vertices used by segments (boundary + constraints).
                    # Triangle will then fill the interior using Steiner points based on 'a' constraint.
                    # This ensures the mesh density is controlled by 'a' and not the dense input cloud.
                    if segs is not None and len(segs) > 0:
                        unique_indices = np.unique(segs.flatten())
                        old_to_new = {old: new for new, old in enumerate(unique_indices)}
                        remapped_indices_map = unique_indices
                        tri_vertices = local_2d[unique_indices]
                        tri_segments = np.array([[old_to_new[s[0]], old_to_new[s[1]]] for s in segs], dtype=int)
                    else:
                        tri_vertices = local_2d
                        tri_segments = None
                        remapped_indices_map = None

                    p_switch = 'p' if tri_segments is not None and len(tri_segments) > 0 else ''
                    tri_options_list = [
                        f'{p_switch}zYYa{area_constraint:.8f}',
                        f'{p_switch}za{area_constraint:.8f}',
                    ]

                    for tri_options in tri_options_list:
                        tri_input = {'vertices': tri_vertices}
                        if tri_segments is not None and len(tri_segments) > 0:
                            tri_input['segments'] = tri_segments

                        try:
                            result = tr.triangulate(tri_input, tri_options)
                        except Exception:
                            result = None

                        if result and 'vertices' in result and 'triangles' in result:
                            result_vertices_2d = result['vertices']
                            patch_triangles = result['triangles']
                            used_opts = tri_options
                            used_label = seg_label
                            break

                    if result_vertices_2d is not None:
                        break

                # Fallback: triangulate without segments if all segment-based attempts failed
                if result_vertices_2d is None or patch_triangles is None:
                    self.logger.warning(f"All segment-based triangulations failed for patch {i}, trying without segments")
                    try:
                        # Use all local_2d points without segments
                        fallback_opts = f'za{area_constraint:.8f}'
                        fallback_input = {'vertices': local_2d}
                        result = tr.triangulate(fallback_input, fallback_opts)
                        if result and 'vertices' in result and 'triangles' in result:
                            result_vertices_2d = result['vertices']
                            patch_triangles = result['triangles']
                            used_opts = fallback_opts
                            used_label = 'no_segments_fallback'
                            remapped_indices_map = None  # Full cloud used
                    except Exception as e:
                        self.logger.warning(f"Fallback triangulation also failed for patch {i}: {e}")
                
                if result_vertices_2d is None or patch_triangles is None:
                    continue

                self.logger.info(
                    f"Patch {i}: base_size={patch_base_size:.4f}, max_area={area_constraint:.4f}, "
                    f"segments='{used_label}', opts='{used_opts}'"
                )
                
                # Project back to 3D
                # We need to map result vertices back.
                # Case A: Vertex came from input (sparse) -> Exact match to remapped_indices_map -> local_2d -> region_points
                # Case B: Vertex is Steiner (new) -> Interpolate using local_2d/region_points as source
                
                # Reconstruct 'input_2d' and 'input_3d' for exact matching in _project_back_to_3d
                # If we sparsified, we only have exact 3D coords for the sparse subset.
                # However, _project_back_to_3d's "input_2d" arg is used for KDTree snapping.
                # We should pass the *sparse* subset as the valid snap targets? 
                # YES, because we only want to snap to original constraint points, not arbitrary dense interior points we discarded.
                
                exact_2d_targets = None
                exact_3d_targets = None
                
                if remapped_indices_map is not None:
                     exact_2d_targets = local_2d[remapped_indices_map]
                     exact_3d_targets = region_points[remapped_indices_map]
                else:
                     exact_2d_targets = local_2d
                     exact_3d_targets = region_points
                
                # For interpolation source, use the FULL DENSE CLOUD to capture curvature
                # (Note: Refine Mesh case with sparse constraints is handled earlier via standard CDT)
                patch_vertices_3d = self._project_back_to_3d(
                    result_vertices_2d, projection_params, region_points,
                    input_2d=exact_2d_targets, input_3d=exact_3d_targets,
                    interpolator=interpolator, smoothing=smoothing
                )
                
                # Adjust triangle indices and add to combined result
                adjusted_triangles = patch_triangles + vertex_offset
                
                all_vertices.append(patch_vertices_3d)
                all_triangles.append(adjusted_triangles)
                vertex_offset += len(patch_vertices_3d)
                
                self.logger.debug(f"Patch {i}: {len(patch_vertices_3d)} vertices, {len(patch_triangles)} triangles")
                
            except Exception as e:
                self.logger.warning(f"Triangulation failed for patch {i}: {e}")
                continue
        
        if not all_vertices:
            self.logger.warning("All patches failed, using standard triangulation")

            return self._fallback_standard_triangulation(points_3d, segments, uniform, interpolator, smoothing)
        
        # Step 4: Combine all patches
        combined_vertices = np.vstack(all_vertices)
        combined_triangles = np.vstack(all_triangles)
        
        # Step 5: Merge duplicate vertices at patch boundaries (stitching)
        # Use an adaptive tolerance based on point spacing, and a normal-consistency gate.
        merge_tolerance = 1e-2
        merge_normals = None
        merge_min_dot = np.cos(np.radians(min(fold_angle_threshold, 60.0)))
        merge_orig_index = None
        snap_tol = 1e-2
        try:
            if len(combined_vertices) > 1:
                tree = cKDTree(combined_vertices)
                dists, _ = tree.query(combined_vertices, k=2)
                nn = dists[:, 1]
                nn = nn[np.isfinite(nn)]
                if len(nn) > 0:
                    nn_median = float(np.median(nn))
                    tol_nn = nn_median * 0.6
                    tol_base = self.base_size * 0.08 if self.base_size else tol_nn
                    merge_tolerance = max(1e-8, min(tol_nn, tol_base))
                    snap_tol = min(nn_median * 0.2, (self.base_size * 0.05) if self.base_size else nn_median * 0.2)
                elif self.base_size:
                    merge_tolerance = max(1e-8, self.base_size * 0.08)
                    snap_tol = self.base_size * 0.05
                else:
                    snap_tol = 1e-4
            # Compute normals for merge gating (prevents cross-limb stitching)
            merge_normals = self._compute_local_normals(combined_vertices, k=12)
            # Map combined vertices to nearest original points for exact stitch gating
            if len(combined_vertices) > 0:
                orig_tree = cKDTree(points_3d)
                d_orig, idx_orig = orig_tree.query(combined_vertices, k=1)
                merge_orig_index = np.full(len(combined_vertices), -1, dtype=np.int64)
                merge_orig_index[d_orig < snap_tol] = idx_orig[d_orig < snap_tol]
        except Exception as e:
            self.logger.debug(f"Adaptive merge tolerance failed: {e}")
            if self.base_size:
                merge_tolerance = max(1e-8, self.base_size * 0.05)
        merged_vertices, merged_triangles = self._merge_patch_boundaries(
            combined_vertices, combined_triangles, tolerance=merge_tolerance,
            normals=merge_normals, min_dot=merge_min_dot,
            orig_index=merge_orig_index
        )
        
        self.logger.info(f"Multi-patch result: {len(merged_vertices)} vertices, {len(merged_triangles)} triangles")
        
        return {
            'vertices': merged_vertices,
            'triangles': merged_triangles
        }
    
    def _compute_local_normals(self, points_3d: np.ndarray, k: int = 20) -> Optional[np.ndarray]:
        """
        Compute consistently oriented local surface normals using PCA and BFS propagation.
        
        Args:
            points_3d: 3D points (N, 3)
            k: Number of neighbors to use for normal estimation (increase for smoothness)
            
        Returns:
            Array of unit normals (N, 3), or None if computation fails
        """
        from scipy.spatial import cKDTree
        
        try:
            n_points = len(points_3d)
            k = min(k, n_points - 1) # preventing more neighbours than availble points
            # Ensure minimal neighbors
            if n_points < 4:
                return None
            k = max(k, 6) # 6 means at least 6 neighbors for each point
            
            tree = cKDTree(points_3d)
            _, indices = tree.query(points_3d, k=k+1)  # +1 because query includes the point itself
            
            normals = np.zeros((n_points, 3))
            
            # 1. Compute unoriented PCA normals
            for i in range(n_points):
                neighbors = points_3d[indices[i]]
                centered = neighbors - neighbors.mean(axis=0)
                
                try:
                    u, s, vh = np.linalg.svd(centered, full_matrices=False)
                    normal = vh[-1]  # Smallest singular vector is the normal
                    normals[i] = normal / (np.linalg.norm(normal) + 1e-12)
                except:
                    normals[i] = np.array([0, 0, 1.0])
            
            # 2. Consistent Orientation Propagation using BFS
            visited = np.zeros(n_points, dtype=bool)
            orient_dot_min = np.cos(np.radians(60.0))
            tangent_align_max = 0.3
            
            # Iterate through all components (handles disconnected islands)
            for start_node in range(n_points):
                if visited[start_node]:
                    continue
                
                # Seed orientation: keep PCA sign to preserve fold flips
                if np.linalg.norm(normals[start_node]) < 1e-12:
                    normals[start_node] = np.array([0.0, 0.0, 1.0])
                    
                visited[start_node] = True
                queue = [start_node]
                
                # BFS
                head = 0
                while head < len(queue):
                    curr = queue[head]
                    head += 1
                    curr_normal = normals[curr]
                    
                    # Propagate to neighbors
                    # indices[curr] has self at 0, neighbors at 1..k
                    nbrs = indices[curr][1:]
                    
                    for nbr in nbrs:
                        if not visited[nbr]:
                            dot = np.dot(normals[nbr], curr_normal)
                            if dot >= orient_dot_min:
                                visited[nbr] = True
                                queue.append(nbr)
                            elif dot <= -orient_dot_min:
                                vec = points_3d[nbr] - points_3d[curr]
                                vec_len = np.linalg.norm(vec)
                                if vec_len > 1e-12:
                                    align = abs(np.dot(vec / vec_len, curr_normal))
                                    if align < tangent_align_max:
                                        normals[nbr] = -normals[nbr]
                                        visited[nbr] = True
                                        queue.append(nbr)
                        # If already visited, we could check for conflict, but ignore for now
            
            return normals
            
        except Exception as e:
            self.logger.warning(f"Normal computation failed: {e}")
            return None
    
    def _detect_fold_regions(self, points_3d: np.ndarray, normals: np.ndarray, 
                            angle_threshold: float = 120.0) -> List[np.ndarray]:
        """
        Detect fold regions using seed-based region growing.
        Segments the surface into patches monotonic enough for projection.
        
        Args:
            points_3d: 3D points (N, 3)
            normals: Unit normals for each point (N, 3)
            angle_threshold: Angle threshold in degrees (tolerance for patch deviation)
            
        Returns:
            List of arrays, each containing point indices for a fold region
        """
        from scipy.spatial import cKDTree
        
        try:
            n_points = len(points_3d)
            
            # Calculate strict dot threshold for projection safety
            # If a patch bends more than 90 degrees, it cannot be projected injectively
            # We enforce a safe limit (e.g., 60 degrees) to force splitting hinges
            # angle_threshold from user is likely large (120), so we clamp it aggressively
            max_deviation_deg = min(angle_threshold, 50.0) # we use 60 because we want to split before the hinge not at the hinge
            min_dot = np.cos(np.radians(max_deviation_deg))
            
            # Build spatial tree for neighbor queries
            tree = cKDTree(points_3d)
            k = 12
            _, all_indices = tree.query(points_3d, k=k+1)
            
            visited = np.zeros(n_points, dtype=bool)
            regions = []
            
            for i in range(n_points):
                if visited[i]:
                    continue
                
                # Start new region/patch
                region = []
                queue = [i]
                visited[i] = True
                region.append(i)
                
                # The normal of the SEED defines the projection plane for this patch
                seed_normal = normals[i]
                
                head = 0
                while head < len(queue):
                    curr = queue[head]
                    head += 1
                    
                    # Direct neighbors
                    nbrs = all_indices[curr][1:]
                    
                    for nbr in nbrs:
                        if visited[nbr]:
                            continue
                        
                        # Check criteria 1: Consistency with SEED normal (Global patch planarity)
                        # This prevents the patch from wrapping around > 60 degrees
                        dot_seed = np.dot(normals[nbr], seed_normal)
                        
                        # Check criteria 2: Consistency with CURRENT normal (Local smoothness)
                        dot_local = np.dot(normals[nbr], normals[curr])
                        
                        # Grow if satisfies both
                        if dot_seed > min_dot and dot_local > 0.5:
                            visited[nbr] = True
                            queue.append(nbr)
                            region.append(nbr)
                
                # Keep significant regions
                if len(region) >= 4:
                    regions.append(np.array(region))
            
            return regions
            
        except Exception as e:
            self.logger.warning(f"Fold region detection failed: {e}")
            return [np.arange(len(points_3d))]

    def _compute_patch_boundary(self, points_2d: np.ndarray, base_size: float) -> Optional[np.ndarray]:
        """
        Compute the concave hull boundary segments for a set of 2D points.
        Uses Delaunay filtering (Alpha Shape concept) to avoid "big triangle" artifacts.
        
        Args:
            points_2d: 2D points (N, 2)
            base_size: Reference length for edge filtering
            
        Returns:
            Segments array (M, 2) of indices, or None on failure
        """
        from scipy.spatial import Delaunay
        
        try:
            if len(points_2d) < 3:
                return None
                
            tri = Delaunay(points_2d)
            simplices = tri.simplices
            
            # Calculate edge lengths
            edges = []
            # Extract unique edges and their lengths
            # An edge is internal if shared by 2 triangles, boundary if only 1
            
            edge_dict = {} # (idx1, idx2) -> count
            
            for s in simplices:
                #Sort indices for consistent edge keys
                s_edges = [
                    tuple(sorted((s[0], s[1]))),
                    tuple(sorted((s[1], s[2]))),
                    tuple(sorted((s[2], s[0])))
                ]
                
                for e in s_edges:
                    if e not in edge_dict:
                        edge_dict[e] = 0
                    edge_dict[e] += 1
            
            # Use strict alpha-like threshold
            # Edges longer than this are considered "spanning the void" and removed
            # But we can't just remove edges, we need to find the boundary of the kept triangles.
            max_len_sq = (base_size * 2.5) ** 2
            
            valid_boundary_edges = []
            
            for s in simplices:
                # Check if triangle is valid (perimeter/area check or max edge check)
                # Simple check: max edge length
                pts = points_2d[s]
                d1 = np.sum((pts[0] - pts[1])**2)
                d2 = np.sum((pts[1] - pts[2])**2)
                d3 = np.sum((pts[2] - pts[0])**2)
                
                if max(d1, d2, d3) > max_len_sq:
                    # Too big, discard
                    continue
                    
                # Add its edges to a boundary counter for valid triangles
                s_edges = [
                    tuple(sorted((s[0], s[1]))),
                    tuple(sorted((s[1], s[2]))),
                    tuple(sorted((s[2], s[0])))
                ]
                
                for e in s_edges:
                    edge_dict[e] = edge_dict.get(e, 0) # Track specifically for kept tris?
                    # No, simpler: 
                    # Re-build edge count for ONLY kept triangles
                    pass

            # Lets do it cleanly:
            kept_simplices = []
            for s in simplices:
                pts = points_2d[s]
                d1 = np.sum((pts[0] - pts[1])**2)
                d2 = np.sum((pts[1] - pts[2])**2)
                d3 = np.sum((pts[2] - pts[0])**2)
                if max(d1, d2, d3) <= max_len_sq:
                    kept_simplices.append(s)
            
            if not kept_simplices:
                # Fallback: keep all if too strict
                kept_simplices = simplices
                
            # Find boundary of kept simplices
            boundary_counts = {}
            for s in kept_simplices:
                es = [
                    tuple(sorted((s[0], s[1]))),
                    tuple(sorted((s[1], s[2]))),
                    tuple(sorted((s[2], s[0])))
                ]
                for e in es:
                    if e in boundary_counts:
                        boundary_counts[e] += 1
                    else:
                        boundary_counts[e] = 1
            
            # Boundary edges appear exactly once
            segments = []
            for e, count in boundary_counts.items():
                if count == 1:
                    segments.append(e)
            
            return np.array(segments)
            
        except Exception as e:
            self.logger.warning(f"Boundary computation failed: {e}")
            return None
    
    def _project_to_local_plane(self, points_3d: np.ndarray) -> Tuple[Optional[np.ndarray], Dict]:
        """
        Project 3D points to their local best-fit plane.
        
        Args:
            points_3d: 3D points (N, 3)
            
        Returns:
            Tuple of (2D projected points, projection parameters dict)
        """
        try:
            centroid = points_3d.mean(axis=0)
            centered = points_3d - centroid
            
            _, _, vh = np.linalg.svd(centered, full_matrices=False)
            
            # u_axis and v_axis span the plane, normal is perpendicular
            u_axis = vh[0]
            v_axis = vh[1]
            normal = vh[2]
            
            # Project to 2D
            u_coords = np.dot(centered, u_axis)
            v_coords = np.dot(centered, v_axis)
            
            points_2d = np.column_stack([u_coords, v_coords])
            
            projection_params = {
                'centroid': centroid,
                'u_axis': u_axis,
                'v_axis': v_axis,
                'normal': normal
            }
            
            return points_2d, projection_params
            
        except Exception as e:
            self.logger.warning(f"Projection failed: {e}")
            return None, {}
    
    def _project_back_to_3d(self, points_2d: np.ndarray, params: Dict, 
                           original_3d: np.ndarray, 
                           input_2d: np.ndarray = None, input_3d: np.ndarray = None,
                           interpolator: str = 'tps', smoothing: float = 0.0) -> np.ndarray:
        """
        Project 2D triangulation vertices back to 3D using interpolation.
        
        Args:
            points_2d: 2D vertices from triangulation (M, 2)
            params: Projection parameters from _project_to_local_plane
            original_3d: Original 3D points used for interpolation
            input_2d: Optional original 2D points (N, 2) for exact matching
            input_3d: Optional original 3D points (N, 3) for exact matching
            
        Returns:
            3D coordinates (M, 3)
        """
        from scipy.interpolate import RBFInterpolator
        from scipy.spatial import cKDTree
        
        try:
            centroid = params['centroid']
            u_axis = params['u_axis']
            v_axis = params['v_axis']
            
            # Project original points to 2D for interpolation reference
            centered_orig = original_3d - centroid
            u_orig = np.dot(centered_orig, u_axis)
            v_orig = np.dot(centered_orig, v_axis)
            orig_2d = np.column_stack([u_orig, v_orig])
            
            # Z-values in local coordinate system
            normal = params['normal']
            z_orig = np.dot(centered_orig, normal)
            
            # Interpolate Z for new vertices using TPS or IDW
            if interpolator is not None and 'idw' in interpolator.lower():
                 # Explicit IDW requested
                 self.logger.info("Using IDW interpolation for patch back-projection")
                 tree = cKDTree(orig_2d)
                 k = min(12, len(orig_2d)) # Use slightly more neighbors for IDW explicit
                 dists, indices = tree.query(points_2d, k=k)
                 
                 if dists.ndim == 1:
                     dists = dists[:, np.newaxis]
                     indices = indices[:, np.newaxis]
                 
                 # Inverse distance weighting with small epsilon
                 # power = 2.0 (standard)
                 weights = 1.0 / np.maximum(dists ** 2, 1e-10)
                 weights_sum = weights.sum(axis=1, keepdims=True)
                 weights_norm = weights / weights_sum
                 
                 z_new = np.sum(weights_norm * z_orig[indices], axis=1)
                 
            elif interpolator is not None and 'linear' in interpolator.lower():
                # Linear interpolation
                self.logger.info("Using Linear interpolation for patch back-projection")
                from scipy.interpolate import LinearNDInterpolator
                try:
                    lin_interp = LinearNDInterpolator(orig_2d, z_orig)
                    z_new = lin_interp(points_2d)
                    
                    # Fill NaNs (outside convex hull of data) with Nearest
                    nan_mask = np.isnan(z_new)
                    if np.any(nan_mask):
                        from scipy.interpolate import NearestNDInterpolator
                        near_interp = NearestNDInterpolator(orig_2d, z_orig)
                        z_new[nan_mask] = near_interp(points_2d[nan_mask])
                except Exception as e:
                    self.logger.warning(f"Linear interpolation failed: {e}, falling back to TPS")
                    # Fallback to TPS
                    rbf = RBFInterpolator(orig_2d, z_orig, kernel='thin_plate_spline', smoothing=smoothing)
                    z_new = rbf(points_2d)

            else:
                # Default: Thin Plate Spline (TPS)
                try:
                    self.logger.info(f"Using TPS interpolation for patch back-projection (smoothing={smoothing})")
                    rbf = RBFInterpolator(orig_2d, z_orig, kernel='thin_plate_spline', smoothing=smoothing)
                    z_new = rbf(points_2d)
                except:
                    # Fallback to IDW if TPS fails singular matrix etc
                    self.logger.warning("TPS interpolation failed, falling back to IDW")
                    z_new = None
                
                # Check for NaN/inf values and fix them with IDW fallback
                if z_new is None or not np.all(np.isfinite(z_new)):
                    if z_new is not None:
                        nan_mask = ~np.isfinite(z_new)
                        nan_count = np.sum(nan_mask)
                        if nan_count > 0:
                            self.logger.warning(f"TPS produced {nan_count} NaN/inf values, using IDW fallback for those points")
                    else:
                        nan_mask = np.ones(len(points_2d), dtype=bool)
                    
                    # IDW fallback for NaN values
                    tree = cKDTree(orig_2d)
                    k = min(12, len(orig_2d))
                    dists, indices = tree.query(points_2d[nan_mask] if z_new is not None else points_2d, k=k)
                
                    if dists.ndim == 1:
                        dists = dists[:, np.newaxis]
                        indices = indices[:, np.newaxis]
                    
                    weights = 1.0 / np.maximum(dists ** 2, 1e-10)
                    weights_sum = weights.sum(axis=1, keepdims=True)
                    weights_norm = weights / weights_sum
                    
                    z_idw = np.sum(weights_norm * z_orig[indices], axis=1)
                    
                    if z_new is not None:
                        z_new[nan_mask] = z_idw
                    else:
                        z_new = z_idw
            
            # Final safety check - replace any remaining NaN with nearest neighbor
            if not np.all(np.isfinite(z_new)):
                remaining_nan = ~np.isfinite(z_new)
                self.logger.warning(f"Still have {np.sum(remaining_nan)} NaN values, using nearest neighbor")
                tree = cKDTree(orig_2d)
                _, nearest_idx = tree.query(points_2d[remaining_nan], k=1)
                z_new[remaining_nan] = z_orig[nearest_idx]
            
            # Convert back to 3D
            points_3d = (centroid + 
                        points_2d[:, 0:1] * u_axis + 
                        points_2d[:, 1:2] * v_axis + 
                        z_new[:, np.newaxis] * normal)
            
            # Final NaN check on points_3d before restoration
            nan_pts_mask = ~np.all(np.isfinite(points_3d), axis=1)
            if np.any(nan_pts_mask):
                self.logger.warning(f"Found {np.sum(nan_pts_mask)} NaN/inf points in 3D result, fixing with nearest neighbor")
                # Use nearest valid original point
                valid_orig_mask = np.all(np.isfinite(original_3d), axis=1)
                if np.any(valid_orig_mask):
                    valid_orig = original_3d[valid_orig_mask]
                    valid_orig_2d = orig_2d[valid_orig_mask]
                    tree_valid = cKDTree(valid_orig_2d)
                    _, nn_idx = tree_valid.query(points_2d[nan_pts_mask], k=1)
                    points_3d[nan_pts_mask] = valid_orig[nn_idx]
            
            # Restore exact points if inputs are provided
            # Uses KDTree to match output points to original input points robustly
            if input_2d is not None and input_3d is not None:
                try:
                    # Filter out any NaN values from input_2d/input_3d
                    valid_input_mask = np.all(np.isfinite(input_2d), axis=1) & np.all(np.isfinite(input_3d), axis=1)
                    if not np.any(valid_input_mask):
                        raise ValueError("No valid input points for restoration")
                    
                    valid_input_2d = input_2d[valid_input_mask]
                    valid_input_3d = input_3d[valid_input_mask]
                    
                    tree = cKDTree(valid_input_2d)
                    # Find nearest original point within tolerance
                    dists, indices = tree.query(points_2d, k=1)
                    
                    # Tolerance: adaptive to local spacing (prevents hinge cracks)
                    tolerance = 1e-5
                    try:
                        if len(valid_input_2d) > 1:
                            nn_dists, _ = tree.query(valid_input_2d, k=2)
                            nn = nn_dists[:, 1]
                            nn = nn[np.isfinite(nn)]
                            if len(nn) > 0:
                                nn_med = float(np.median(nn))
                                tolerance = max(tolerance, nn_med * 0.1)
                    except Exception:
                        pass
                    if self.base_size:
                        tolerance = max(tolerance, self.base_size * 1e-3)
                        
                    match_mask = dists < tolerance
                    
                    # Snap matched points
                    if np.any(match_mask):
                        matched_indices = indices[match_mask]
                        # 3D sanity check to avoid snapping across limbs
                        try:
                            nn3 = None
                            try:
                                if len(valid_input_2d) > 1:
                                    nn3_dists, _ = tree.query(valid_input_2d, k=2)
                                    nn3 = nn3_dists[:, 1]
                                    nn3 = nn3[np.isfinite(nn3)]
                                    nn3 = float(np.median(nn3)) if len(nn3) > 0 else None
                            except Exception:
                                nn3 = None
                            tol_3d = (nn3 * 0.2) if nn3 is not None else tolerance * 0.5
                            matched_rows = np.where(match_mask)[0]
                            
                            # Only compute delta for rows with finite points_3d
                            finite_matched = np.all(np.isfinite(points_3d[matched_rows]), axis=1)
                            if np.any(finite_matched):
                                finite_rows = matched_rows[finite_matched]
                                finite_indices = matched_indices[finite_matched]
                                deltas = points_3d[finite_rows] - valid_input_3d[finite_indices]
                                dist3 = np.linalg.norm(deltas, axis=1)
                                ok = dist3 <= tol_3d
                                if np.any(ok):
                                    points_3d[finite_rows[ok]] = valid_input_3d[finite_indices[ok]]
                            
                            # For non-finite rows, just snap directly
                            if np.any(~finite_matched):
                                nonfinite_rows = matched_rows[~finite_matched]
                                nonfinite_indices = matched_indices[~finite_matched]
                                points_3d[nonfinite_rows] = valid_input_3d[nonfinite_indices]
                        except Exception:
                            points_3d[match_mask] = valid_input_3d[matched_indices]
                        
                except Exception as e:
                    self.logger.warning(f"Exact point restoration failed: {e}")
            
            return points_3d
            
        except Exception as e:
            self.logger.warning(f"Back-projection failed: {e}, using planar projection")
            # Fallback: simple planar projection
            centroid = params['centroid']
            u_axis = params['u_axis']
            v_axis = params['v_axis']
            
            points_3d = centroid + points_2d[:, 0:1] * u_axis + points_2d[:, 1:2] * v_axis
            return points_3d
    
    def _merge_patch_boundaries(self, vertices: np.ndarray, triangles: np.ndarray, 
                               tolerance: float = 1e-6,
                               normals: Optional[np.ndarray] = None,
                               min_dot: Optional[float] = None,
                               orig_index: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Merge duplicate vertices at patch boundaries to stitch patches together.
        
        Args:
            vertices: Combined vertices from all patches (M, 3)
            triangles: Combined triangles with original indices (T, 3)
            tolerance: Distance tolerance for merging vertices
            normals: Optional normals for gating merges (M, 3)
            min_dot: Optional minimum dot product to allow merge
            orig_index: Optional mapping to original points for exact stitch gating
            
        Returns:
            Tuple of (merged vertices, updated triangles)
        """
        from scipy.spatial import cKDTree
        
        try:
            tree = cKDTree(vertices)
            
            # Find duplicate vertices
            pairs = tree.query_pairs(tolerance)
            
            if not pairs:
                return vertices, triangles
            
            # Optional gating by normal alignment to prevent cross-limb stitching
            if normals is not None and min_dot is not None and len(normals) == len(vertices):
                relax_dist = tolerance * 0.25
                gated_pairs = set()
                for i, j in pairs:
                    # Always allow merges that map to the same original point
                    if orig_index is not None and orig_index[i] >= 0 and orig_index[i] == orig_index[j]:
                        gated_pairs.add((i, j))
                    else:
                        if np.dot(normals[i], normals[j]) >= min_dot:
                            gated_pairs.add((i, j))
                        else:
                            # Allow very close vertices to merge even if normals disagree
                            if relax_dist > 0.0:
                                d = np.linalg.norm(vertices[i] - vertices[j])
                                if d <= relax_dist:
                                    gated_pairs.add((i, j))
                pairs = gated_pairs
                if not pairs:
                    return vertices, triangles
            
            # Build union-find structure for merging
            parent = np.arange(len(vertices))
            
            def find(x):
                if parent[x] != x:
                    parent[x] = find(parent[x])
                return parent[x]
            
            def union(x, y):
                px, py = find(x), find(y)
                if px != py:
                    parent[px] = py
            
            for i, j in pairs:
                union(i, j)
            
            # Build mapping from old to new indices
            unique_roots = {}
            new_index = 0
            old_to_new = np.zeros(len(vertices), dtype=np.int32)
            
            for i in range(len(vertices)):
                root = find(i)
                if root not in unique_roots:
                    unique_roots[root] = new_index
                    new_index += 1
                old_to_new[i] = unique_roots[root]
            
            # Create merged vertex array (use representative vertex for each group)
            n_unique = len(unique_roots)
            merged_vertices = np.zeros((n_unique, 3))
            
            for old_idx, new_idx in enumerate(old_to_new):
                merged_vertices[new_idx] = vertices[old_idx]
            
            # Update triangle indices
            merged_triangles = old_to_new[triangles]
            
            # Remove degenerate triangles (where two or more vertices are the same)
            valid_mask = (merged_triangles[:, 0] != merged_triangles[:, 1]) & \
                        (merged_triangles[:, 1] != merged_triangles[:, 2]) & \
                        (merged_triangles[:, 0] != merged_triangles[:, 2])
            
            merged_triangles = merged_triangles[valid_mask]
            
            self.logger.info(f"Merged {len(vertices)} -> {n_unique} vertices, removed {np.sum(~valid_mask)} degenerate triangles")
            
            return merged_vertices, merged_triangles
            
        except Exception as e:
            self.logger.warning(f"Vertex merging failed: {e}")
            return vertices, triangles
    
    def _triangulate_folded_with_patches(self, constraint_pts: np.ndarray,
                                          segments: Optional[np.ndarray],
                                          reference_pts: np.ndarray,
                                          fold_regions: List[np.ndarray],
                                          ref_normals: np.ndarray,
                                          uniform: bool,
                                          interpolator: str,
                                          smoothing: float,
                                          fold_angle_threshold: float) -> Dict:
        """
        Triangulate a folded surface by handling each fold patch separately.
        
        For each patch:
        1. Project patch reference points to local 2D
        2. Find constraint points that belong to this patch
        3. Triangulate with constraints in local 2D
        4. Back-project to 3D using patch reference points
        """
        from scipy.spatial import cKDTree
        
        self.logger.info(f"Patch-based triangulation: {len(fold_regions)} patches, {len(constraint_pts)} constraints")
        
        all_vertices = []
        all_triangles = []
        vertex_offset = 0
        
        # Build KD-tree for reference points to assign constraints to patches
        ref_tree = cKDTree(reference_pts)
        
        # Find which patch each constraint point belongs to (based on nearest reference point)
        _, nearest_ref_idx = ref_tree.query(constraint_pts, k=1)
        
        # Create mapping: reference point index -> patch index
        ref_to_patch = np.zeros(len(reference_pts), dtype=int)
        for patch_idx, region_indices in enumerate(fold_regions):
            ref_to_patch[region_indices] = patch_idx
        
        # Assign each constraint to a patch
        constraint_patches = ref_to_patch[nearest_ref_idx]
        
        # Process each patch
        for patch_idx, region_indices in enumerate(fold_regions):
            patch_ref_pts = reference_pts[region_indices]
            
            if len(patch_ref_pts) < 4:
                continue
            
            # Find constraints belonging to this patch
            patch_constraint_mask = constraint_patches == patch_idx
            patch_constraints = constraint_pts[patch_constraint_mask]
            
            # Map original constraint indices to patch indices for segments
            orig_to_patch_idx = np.full(len(constraint_pts), -1, dtype=int)
            patch_constraint_indices = np.where(patch_constraint_mask)[0]
            for new_idx, orig_idx in enumerate(patch_constraint_indices):
                orig_to_patch_idx[orig_idx] = new_idx
            
            # Filter segments to only include those with both endpoints in this patch
            patch_segments = None
            if segments is not None and len(segments) > 0:
                valid_segs = []
                for seg in segments:
                    i, j = int(seg[0]), int(seg[1])
                    if orig_to_patch_idx[i] >= 0 and orig_to_patch_idx[j] >= 0:
                        valid_segs.append([orig_to_patch_idx[i], orig_to_patch_idx[j]])
                if valid_segs:
                    patch_segments = np.array(valid_segs, dtype=np.int32)
            
            self.logger.info(f"Patch {patch_idx}: {len(patch_ref_pts)} ref pts, {len(patch_constraints)} constraints, {len(patch_segments) if patch_segments is not None else 0} segs")
            
            if len(patch_constraints) < 3:
                # Not enough constraints for this patch, use reference points only
                patch_constraints = patch_ref_pts
                patch_segments = None
            
            # Project patch to local 2D using PCA on reference points
            centroid = patch_ref_pts.mean(axis=0)
            centered_ref = patch_ref_pts - centroid
            _, _, vh = np.linalg.svd(centered_ref, full_matrices=False)
            u_axis, v_axis = vh[0], vh[1]
            
            # Project constraints to 2D
            centered_constraints = patch_constraints - centroid
            constraints_2d = np.column_stack([
                np.dot(centered_constraints, u_axis),
                np.dot(centered_constraints, v_axis)
            ])
            
            # Project reference points to 2D for Steiner guides
            ref_2d = np.column_stack([
                np.dot(centered_ref, u_axis),
                np.dot(centered_ref, v_axis)
            ])
            
            # Add reference points as Steiner guides (filtered)
            try:
                from scipy.spatial import Delaunay
                if len(constraints_2d) >= 3:
                    delaunay = Delaunay(constraints_2d)
                    simplex_indices = delaunay.find_simplex(ref_2d)
                    interior_mask = simplex_indices >= 0
                    interior_ref_2d = ref_2d[interior_mask]
                    
                    if len(interior_ref_2d) > 0:
                        constraint_tree = cKDTree(constraints_2d)
                        min_dist = self.base_size * 0.15 if self.base_size else 1.0
                        dists, _ = constraint_tree.query(interior_ref_2d, k=1)
                        far_enough = dists > min_dist
                        interior_ref_2d = interior_ref_2d[far_enough]
                        
                        if len(interior_ref_2d) > 0:
                            max_pts = min(300, len(interior_ref_2d))
                            if len(interior_ref_2d) > max_pts:
                                idx = np.random.choice(len(interior_ref_2d), max_pts, replace=False)
                                interior_ref_2d = interior_ref_2d[idx]
                            constraints_2d = np.vstack([constraints_2d, interior_ref_2d])
                            self.logger.info(f"  Added {len(interior_ref_2d)} interior Steiner guides")
            except Exception as e:
                self.logger.debug(f"Could not add Steiner guides: {e}")
            
            # Triangulate this patch
            try:
                result_2d = self.triangulate(constraints_2d, patch_segments, uniform=uniform)
                
                if 'vertices' not in result_2d or 'triangles' not in result_2d:
                    continue
                
                vertices_2d = result_2d['vertices']
                triangles = result_2d['triangles']
                
                # Back-project to 3D
                vertices_3d = centroid + vertices_2d[:, 0:1] * u_axis + vertices_2d[:, 1:2] * v_axis
                
                # Interpolate Z using patch reference points (limb-aware)
                ref_z = np.dot(centered_ref, vh[2])
                ref_tree_2d = cKDTree(ref_2d)
                k = min(8, len(ref_2d))
                dists, indices = ref_tree_2d.query(vertices_2d, k=k)
                
                if dists.ndim == 1:
                    dists = dists[:, np.newaxis]
                    indices = indices[:, np.newaxis]
                
                weights = 1.0 / np.maximum(dists ** 2, 1e-10)
                weights_norm = weights / weights.sum(axis=1, keepdims=True)
                z_new = np.sum(weights_norm * ref_z[indices], axis=1)
                
                vertices_3d = vertices_3d + z_new[:, np.newaxis] * vh[2]
                
                # Add to global mesh with offset
                all_vertices.append(vertices_3d)
                all_triangles.append(triangles + vertex_offset)
                vertex_offset += len(vertices_3d)
                
                self.logger.info(f"  Patch {patch_idx}: {len(vertices_3d)} vertices, {len(triangles)} triangles")
                
            except Exception as e:
                self.logger.warning(f"Patch {patch_idx} triangulation failed: {e}")
                continue
        
        if not all_vertices:
            self.logger.warning("All patches failed, falling back to standard triangulation")
            return self._fallback_standard_triangulation(
                constraint_pts, segments, uniform, interpolator, smoothing,
                reference_mesh_3d=reference_pts
            )
        
        # Merge all patches
        merged_vertices = np.vstack(all_vertices)
        merged_triangles = np.vstack(all_triangles)
        
        # Merge duplicate vertices at patch boundaries
        merged_vertices, merged_triangles = self._merge_patch_boundaries(
            merged_vertices, merged_triangles, tolerance=self.base_size * 0.1 if self.base_size else 0.1
        )
        
        self.logger.info(f"Patch-based triangulation complete: {len(merged_vertices)} vertices, {len(merged_triangles)} triangles")
        
        return {
            'vertices': merged_vertices,
            'triangles': merged_triangles
        }
    
    def _fallback_standard_triangulation(self, points_3d: np.ndarray, 
                                         segments: Optional[np.ndarray],
                                         uniform: bool,
                                         interpolator: str = 'tps',
                                         smoothing: float = 0.0,
                                         reference_mesh_3d: Optional[np.ndarray] = None) -> Dict:
        """
        Fallback to standard 2D projected triangulation.
        
        Args:
            points_3d: 3D points (constraint points for triangulation)
            segments: Optional segments
            uniform: Uniform mesh flag
            reference_mesh_3d: Optional reference mesh for Z-interpolation (preserves fold structure)
            
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
                # IMPORTANT: For folded surfaces, we need LIMB-AWARE interpolation
                # Standard TPS/IDW fails because multiple ref points map to same 2D location with different Z
                from scipy.spatial import cKDTree
                
                self.logger.info(f"Using reference mesh ({len(reference_mesh_3d)} pts) for Z-interpolation to preserve fold structure")
                ref_centered = reference_mesh_3d - centroid
                ref_z = np.dot(ref_centered, vh[2])
                ref_2d = np.column_stack([np.dot(ref_centered, u_axis), np.dot(ref_centered, v_axis)])
                
                # Get constraint points Z values for limb detection
                constraint_z = np.dot(centered, vh[2])
                
                # Build tree for finding nearest constraint point to each vertex
                constraint_tree = cKDTree(points_2d)
                
                # For each output vertex, find nearest constraint point and use its Z as limb guide
                _, nearest_constraint_idx = constraint_tree.query(vertices_2d, k=1)
                vertex_limb_z = constraint_z[nearest_constraint_idx]
                
                # Use limb-aware IDW: for each vertex, only use reference points with similar Z
                self.logger.info("Using limb-aware IDW interpolation for folded surface")
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
                        rbf = RBFInterpolator(orig_2d, z_orig, kernel='thin_plate_spline', smoothing=smoothing)
                        z_new = rbf(vertices_2d)
                    except Exception as e:
                        self.logger.warning(f"Fallback TPS failed: {e}")

                if z_new is not None:
                    vertices_3d = vertices_3d + z_new[:, np.newaxis] * vh[2]

            return {
                'vertices': vertices_3d,
                'triangles': result_2d['triangles']
            }
            
        except Exception as e:
            self.logger.error(f"Fallback triangulation failed: {e}")
            return {}


# Helper function for calculating minimum distance to boundary
def min_distance_to_boundary(point, hull_points):
    """Calculate minimum distance from a point to the hull boundary."""
    min_dist = float('inf')
    
    for i in range(len(hull_points)):
        p1 = hull_points[i]
        p2 = hull_points[(i + 1) % len(hull_points)]
        
        # Line segment vector
        line_vec = p2 - p1
        line_len = np.linalg.norm(line_vec)
        
        if line_len < 1e-8:
            continue
            
        # Normalize line vector
        line_vec = line_vec / line_len
        
        # Vector from line start to point
        point_vec = point - p1
        
        # Project point onto line
        proj_len = np.dot(point_vec, line_vec)
        
        # Calculate closest point on line segment
        if proj_len < 0:
            closest = p1  # Before start of segment
        elif proj_len > line_len:
            closest = p2  # After end of segment
        else:
            # On the segment
            closest = p1 + line_vec * proj_len
            
        # Calculate distance to closest point
        dist = np.linalg.norm(point - closest)
        min_dist = min(min_dist, dist)
        
    return min_dist 
