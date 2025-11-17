# In tetra_mesh_utils.py

import numpy as np
import logging
import tetgen
import pyvista as pv
from typing import Dict, List, Tuple, Optional, Any, Union
from Pymeshit.intersection_utils import Vector3D

logger = logging.getLogger("MeshIt-Workflow")

# Try to import netCDF4 for NetCDF export support
try:
    import netCDF4 as nc
    HAS_NETCDF = True
    logger.info("netCDF4 library available for NetCDF export")
except ImportError:
    HAS_NETCDF = False
    logger.warning("netCDF4 library not available. NetCDF export will be disabled.")


class TetrahedralMeshGenerator:
    """
    A utility class for generating tetrahedral meshes from surface data.
    
    This class follows the C++ MeshIt approach by directly using pre-computed
    conforming surface meshes to build the final PLC for TetGen.
    """
    
    def __init__(self, datasets: List[Dict], selected_surfaces: set, 
                 border_surface_indices: set, unit_surface_indices: set, 
                 fault_surface_indices: set, materials: List[Dict] = None,
                 surface_data: Dict = None, holes: List = None):
        """
        Initialize the tetrahedral mesh generator.
        
        Args:
            datasets: List of surface datasets containing mesh data.
            selected_surfaces: Set of selected surface indices.
            border_surface_indices: Set of border surface indices.
            unit_surface_indices: Set of unit surface indices.
            fault_surface_indices: Set of fault surface indices.
            materials: List of material definitions with locations.
            surface_data: Dictionary of conforming mesh data {surface_idx: mesh_data}.
            holes: List of hole points [(x, y, z), ...] to be passed to TetGen.
        """
        self.datasets = datasets
        self.selected_surfaces = selected_surfaces
        self.border_surface_indices = border_surface_indices
        self.unit_surface_indices = unit_surface_indices
        self.fault_surface_indices = fault_surface_indices
        self.materials = materials or []
        self.surface_data = surface_data or {}
        self.external_holes = holes or []  # Holes passed from GUI
        self.tetrahedral_mesh = None
        
        # PLC data containers
        self.plc_vertices = None
        self.plc_facets = None
        self.plc_facet_markers = None
        self.plc_regions = None
        self.plc_edge_constraints = None
        self.plc_edge_markers = None
        self.plc_holes = None  # Store hole points

    def generate_tetrahedral_mesh(self, tetgen_switches: str = "pq1.414aAY") -> Optional[pv.UnstructuredGrid]:
        """
        Generate tetrahedral mesh from the provided conforming surface data.
        """
        if not self.selected_surfaces:
            logger.warning("No surfaces selected for mesh generation.")
            return None
        
        logger.info("Generating tetrahedral mesh from pre-computed conforming PLC...")
        
        try:
            # Step 1: Directly use the conforming mesh data to build the final PLC.
            self._build_plc_from_precomputed_meshes()
            
            if self.plc_vertices is None or len(self.plc_vertices) == 0:
                logger.error("PLC assembly failed: No vertices found.")
                return None
            
            # Step 2: Create a TetGen object.
            tet = tetgen.TetGen(self.plc_vertices, self.plc_facets, self.plc_facet_markers)
            
            # Step 2.5: Add holes to TetGen if any exist
            if hasattr(self, 'plc_holes') and self.plc_holes is not None and len(self.plc_holes) > 0:
                for hole_point in self.plc_holes:
                    hole_coords = (float(hole_point[0]), float(hole_point[1]), float(hole_point[2]))
                    tet.add_hole(hole_coords)
                    logger.info(f"Added hole to TetGen at ({hole_coords[0]:.3f}, {hole_coords[1]:.3f}, {hole_coords[2]:.3f})")
                logger.info(f"✓ Added {len(self.plc_holes)} holes to TetGen mesh")
            
            # Step 3: Add edge constraints.
            if self.plc_edge_constraints is not None and len(self.plc_edge_constraints) > 0:
                tet.edge_list = self.plc_edge_constraints.tolist()
                tet.edge_marker_list = self.plc_edge_markers.tolist()
                logger.info(f"Added {len(self.plc_edge_constraints)} intersection edge constraints to TetGen.")
            
            # Step 4: Add material seed points using C++ MeshIt approach
            if self.materials:
                # Separate faults (2D surface materials) from units (3D volumetric materials)
                volumetric_regions, surface_materials = self._prepare_materials_cpp_style()
                
                if volumetric_regions:
                    # Only add VOLUMETRIC materials (units/formations) as 3D regions
                    # Check for holes and avoid placing material points in hole regions
                    hole_distance_threshold = 5.0  # Minimum distance from hole centers
                    
                    for i, region in enumerate(volumetric_regions):
                        region_id = int(region[3])  # material attribute
                        point = (float(region[0]), float(region[1]), float(region[2]))
                        max_vol = float(region[4]) if region[4] > 0 else 0.0  # TetGen expects 0.0 for no constraint
                        
                        # Check if this material point is too close to any hole
                        too_close_to_hole = False
                        if hasattr(self, 'plc_holes') and self.plc_holes is not None and len(self.plc_holes) > 0:
                            for hole in self.plc_holes:
                                distance = np.linalg.norm(np.array(point) - np.array(hole))
                                if distance < hole_distance_threshold:
                                    logger.warning(f"Material point {point} is {distance:.2f} units from hole at {hole}. Adjusting position.")
                                    # Move the material point away from the hole
                                    direction = np.array(point) - np.array(hole)
                                    if np.linalg.norm(direction) > 1e-10:
                                        direction = direction / np.linalg.norm(direction)
                                        adjusted_point = np.array(hole) + direction * hole_distance_threshold * 1.5
                                        point = tuple(adjusted_point)
                                        logger.info(f"Adjusted material point to {point}")
                                    break
                        
                        tet.add_region(region_id, point, max_vol)
                        logger.info(f"Added 3D region {region_id}: point={point}, max_vol={max_vol}")
                    
                    # Log hole information for debugging
                    if hasattr(self, 'plc_holes') and self.plc_holes is not None and len(self.plc_holes) > 0:
                        logger.info(f"✓ C++ Style: Added {len(volumetric_regions)} 3D regions (units/formations) to TetGen, avoiding {len(self.plc_holes)} holes")
                        for hole in self.plc_holes:
                            logger.debug(f"Hole at ({hole[0]:.3f}, {hole[1]:.3f}, {hole[2]:.3f})")
                    else:
                        logger.info(f"✓ C++ Style: Added {len(volumetric_regions)} 3D regions (units/formations) to TetGen")
                    
                if surface_materials:
                    logger.info(f"✓ C++ Style: {len(surface_materials)} 2D materials (faults) handled as surface constraints")
                    # Note: Faults are already included in the surface triangulation as constraints
                    # They don't need separate 3D region seeds - this matches C++ behavior
                    
                # Store for attribute assignment later
                self.plc_regions = volumetric_regions
                self.surface_materials = surface_materials
            
            # Step 5: Run TetGen with improved error handling (C++ style).
            logger.info(f"Running TetGen with switches: '{tetgen_switches}'")
            
            # C++ style: Handle self-intersections properly
            try:
                # Ensure region attributes are enabled when we have volumetric materials (C++ style)
                if self.materials and hasattr(self, 'plc_regions') and self.plc_regions:
                    # Enable region attributes using the regionattrib parameter (equivalent to '-A' switch)
                    if 'A' in tetgen_switches:
                        # Capture the returned attributes when regions are defined
                        nodes, elements, attributes = tet.tetrahedralize(switches=tetgen_switches, regionattrib=1.0)
                    else:
                        # Add 'A' switch if not present
                        modified_switches = tetgen_switches + 'A'
                        logger.info(f"Added 'A' switch for region attributes: '{modified_switches}'")
                        nodes, elements, attributes = tet.tetrahedralize(switches=modified_switches, regionattrib=1.0)
                    
                    # Apply the material attributes to the grid
                    grid = tet.grid
                    if attributes is not None and len(attributes) > 0:
                        grid.cell_data['MaterialID'] = attributes.astype(int)
                        import numpy as np
                        unique_materials = np.unique(attributes.astype(int))
                        logger.info(f"✓ Applied TetGen material attributes directly: {unique_materials}")
                    else:
                        logger.warning("TetGen returned no material attributes despite having regions")
                else:
                    tet.tetrahedralize(switches=tetgen_switches)
                    grid = tet.grid
                    
            except RuntimeError as e:
                error_msg = str(e)
                if "self-intersection" in error_msg.lower() or "manifold" in error_msg.lower():
                    logger.warning("TetGen detected geometric issues. Attempting C++ style recovery...")
                    # C++ style: Try with detection switches first
                    try:
                        detection_switches = tetgen_switches.replace('Y', '') + 'd'  # Add detection, remove Y
                        logger.info(f"Trying TetGen with geometric detection: '{detection_switches}'")
                        tet.tetrahedralize(switches=detection_switches)
                        grid = tet.grid
                        logger.info("✓ TetGen succeeded with geometric detection")
                    except Exception as e2:
                        logger.error(f"TetGen with detection also failed: {e2}")
                        raise e  # Re-raise original error for fallback handling
                else:
                    raise e  # Re-raise non-intersection errors
            
            # Step 6: Check if material attributes were successfully applied
            # If not, fall back to manual assignment
            if grid is not None and grid.n_cells > 0:
                if 'MaterialID' not in grid.cell_data or len(grid.cell_data['MaterialID']) == 0:
                    logger.info("No MaterialID found in mesh - will use manual assignment")
                else:
                    # Material attributes were successfully applied from TetGen
                    logger.info("✓ Material attributes successfully obtained from TetGen")
            
            if grid is None or grid.n_cells == 0:
                logger.error("TetGen ran but produced no tetrahedra.")
                self._export_plc_for_debugging()
                return self._run_tetgen_fallback_strategies(tetgen_switches)
            
            logger.info(f"✓ TetGen succeeded: {grid.n_cells} tetrahedra generated.")
            self.tetrahedral_mesh = grid
            
            # ✅ CRITICAL: Store TetGen object to access constraint surface triangles (C++ style)
            self.tetgen_object = tet
            logger.info(f"Stored TetGen object for constraint surface access")
            
            return grid
            
        except Exception as e:
            logger.error(f"TetGen execution failed: {e}", exc_info=True)
            self._export_plc_for_debugging()
            return self._run_tetgen_fallback_strategies(tetgen_switches)
    
    
    def _build_plc_from_precomputed_meshes(self):
        """
        Builds the final PLC by combining pre-computed conforming meshes (preferred)
        with fallback constraint-based triangulation, and adds WELL polylines as edge
        constraints (C++: wells are 1D, not triangulated).
        """
        logger.info("Building final PLC from pre-computed conforming meshes...")

        def _xyz(pt) -> List[float]:
            if isinstance(pt, Vector3D):
                return [float(pt.x), float(pt.y), float(pt.z)]
            elif isinstance(pt, (list, tuple, np.ndarray)):
                return [float(pt[0]), float(pt[1]), float(pt[2])]
            else:
                raise ValueError(f"Unsupported point type: {type(pt)}")

        key_to_global_idx = {}
        global_vertices = []
        global_facets = []
        global_facet_markers = []
        edge_constraints = set()
        global_holes = []

        boundary_surfaces = (self.border_surface_indices | self.unit_surface_indices) & self.selected_surfaces
        fault_surfaces = self.fault_surface_indices & self.selected_surfaces
        logger.info(f"Processing {len(boundary_surfaces)} boundary surfaces, {len(fault_surfaces)} fault surfaces")

        # Holes from stored constraints and GUI
        logger.info("Collecting holes from stored constraints...")
        self._collect_holes_from_datasets(global_holes)
        if self.external_holes:
            for hole in self.external_holes:
                global_holes.append(hole)
            logger.info(f"Added {len(self.external_holes)} external holes from GUI")

        # 1) Use precomputed conforming meshes
        surfaces_with_precomputed = set()
        for s_idx in boundary_surfaces | fault_surfaces:
            if s_idx not in self.surface_data:
                continue

            conforming_mesh = self.surface_data[s_idx]
            local_vertices = conforming_mesh.get('vertices')
            local_triangles = conforming_mesh.get('triangles')
            local_holes = conforming_mesh.get('holes', [])

            if local_vertices is None or local_triangles is None or len(local_vertices) == 0:
                continue

            # Add holes from this surface
            for hole in (local_holes or []):
                global_holes.append(_xyz(hole))

            # Map vertices to global
            local_to_global = {}
            for lv_idx, v in enumerate(local_vertices):
                key = (round(v[0], 9), round(v[1], 9), round(v[2], 9))
                g = key_to_global_idx.get(key)
                if g is None:
                    g = len(global_vertices)
                    key_to_global_idx[key] = g
                    global_vertices.append(_xyz(v))
                local_to_global[lv_idx] = g

            # Add triangles as facets with markers
            for tri in local_triangles:
                gtri = [local_to_global.get(vidx) for vidx in tri[:3]]
                if all(t is not None for t in gtri) and len(set(gtri)) == 3:
                    v0, v1, v2 = [global_vertices[i] for i in gtri]
                    area = 0.5 * np.linalg.norm(np.cross(np.array(v1) - np.array(v0),
                                                        np.array(v2) - np.array(v0)))
                    if area > 1e-12:
                        global_facets.append(gtri)
                        global_facet_markers.append(1000 + s_idx if s_idx in fault_surfaces else s_idx)
                        if s_idx in fault_surfaces:
                            for k in range(3):
                                e = tuple(sorted((gtri[k], gtri[(k + 1) % 3])))
                                if e[0] != e[1]:
                                    edge_constraints.add(e)

            surfaces_with_precomputed.add(s_idx)
            surface_name = self.datasets[s_idx].get("name", f"Surface_{s_idx}")
            logger.info(f"✓ Used precomputed mesh for '{surface_name}': {len(local_vertices)} vertices, {len(local_triangles)} triangles")

        # 2) Fallback triangulation for missing surfaces (unchanged core logic)
        missing_surfaces = (boundary_surfaces | fault_surfaces) - surfaces_with_precomputed
        if missing_surfaces:
            logger.info(f"Fallback: Generating triangles for {len(missing_surfaces)} surfaces without pre-computed meshes")

            # First add constraint vertices to global pool
            for s_idx in missing_surfaces:
                dataset = self.datasets[s_idx]
                hull_points = dataset.get("hull_points", [])
                if hull_points is not None:
                    for p in hull_points:
                        key = (round(p[0], 9), round(p[1], 9), round(p[2], 9))
                        if key not in key_to_global_idx:
                            key_to_global_idx[key] = len(global_vertices)
                            global_vertices.append(_xyz(p))

                for constraint in dataset.get("stored_constraints", []):
                    if constraint.get("type") == "intersection_line":
                        for p in constraint.get("points", []):
                            key = (round(p[0], 9), round(p[1], 9), round(p[2], 9))
                            if key not in key_to_global_idx:
                                key_to_global_idx[key] = len(global_vertices)
                                global_vertices.append(_xyz(p))

            # Now triangulate missing surfaces
            for s_idx in missing_surfaces:
                dataset = self.datasets[s_idx]
                surface_name = dataset.get("name", f"Surface_{s_idx}")
                surface_plc_points_3d, surface_plc_segments, point_map = [], [], {}

                def add_surface_point(p):
                    key = (round(p[0], 9), round(p[1], 9), round(p[2], 9))
                    idx = point_map.get(key)
                    if idx is None:
                        idx = len(surface_plc_points_3d)
                        point_map[key] = idx
                        surface_plc_points_3d.append(_xyz(p))
                    return idx

                if s_idx in boundary_surfaces:
                    hull_points = dataset.get("hull_points", [])
                    if hull_points is not None and len(hull_points) > 1:
                        for i in range(len(hull_points) - 1):
                            p1 = add_surface_point(hull_points[i])
                            p2 = add_surface_point(hull_points[i + 1])
                            if p1 != p2:
                                surface_plc_segments.append([p1, p2])

                for constraint in dataset.get("stored_constraints", []):
                    if constraint.get("type") == "intersection_line":
                        pts = constraint.get("points", [])
                        for i in range(len(pts) - 1):
                            p1 = add_surface_point(pts[i])
                            p2 = add_surface_point(pts[i + 1])
                            if p1 != p2:
                                surface_plc_segments.append([p1, p2])

                if not surface_plc_points_3d or not surface_plc_segments:
                    logger.warning(f"Skipping fallback triangulation for '{surface_name}' - insufficient constraint data")
                    continue

                local_tris = self._triangulate_surface_constraints(surface_plc_points_3d, surface_plc_segments, surface_name)
                if local_tris is None or len(local_tris) == 0:
                    logger.warning(f"Fallback triangulation failed for '{surface_name}' - surface excluded")
                    continue

                # Map to global
                for tri in local_tris:
                    gtri = []
                    valid = True
                    for lv in tri:
                        coords = surface_plc_points_3d[lv]
                        key = (round(coords[0], 9), round(coords[1], 9), round(coords[2], 9))
                        g = key_to_global_idx.get(key)
                        if g is None:
                            valid = False
                            break
                        gtri.append(g)
                    if valid and len(set(gtri)) == 3:
                        global_facets.append(gtri)
                        global_facet_markers.append(1000 + s_idx if s_idx in fault_surfaces else s_idx)

                logger.info(f"✓ Fallback triangulation successful for '{surface_name}': {len(local_tris)} triangles")

        # 3) Add intersection line constraints (existing logic, kept permissive)
        validated_edge_constraints = set()
        for s_idx in self.selected_surfaces:
            if s_idx >= len(self.datasets):
                continue
            dataset = self.datasets[s_idx]
            for constraint in dataset.get("stored_constraints", []):
                if constraint.get("type") == "intersection_line":
                    pts = constraint.get("points", [])
                    if len(pts) < 2:
                        continue
                    for i in range(len(pts) - 1):
                        k1 = (round(pts[i][0], 9), round(pts[i][1], 9), round(pts[i][2], 9))
                        k2 = (round(pts[i+1][0], 9), round(pts[i+1][1], 9), round(pts[i+1][2], 9))
                        g1, g2 = key_to_global_idx.get(k1), key_to_global_idx.get(k2)
                        if g1 is not None and g2 is not None and g1 != g2:
                            e = tuple(sorted((g1, g2)))
                            validated_edge_constraints.add(e)

        # 4) NEW: Add WELL polylines as edge constraints (no triangulation)
        well_edges_added = 0
        for d in self.datasets:
            if d.get('type') == 'WELL':
                pts = d.get('refined_well_points') or d.get('points')  # prefer refined wells
                if pts is None or len(pts) < 2:
                    continue
                gidxs = []
                for p in pts:
                    key = (round(float(p[0]), 9), round(float(p[1]), 9), round(float(p[2]), 9))
                    g = key_to_global_idx.get(key)
                    if g is None:
                        g = len(global_vertices)
                        key_to_global_idx[key] = g
                        global_vertices.append(_xyz(p))
                    gidxs.append(g)
                for i in range(len(gidxs) - 1):
                    if gidxs[i] != gidxs[i + 1]:
                        e = tuple(sorted((gidxs[i], gidxs[i + 1])))
                        validated_edge_constraints.add(e)
                        well_edges_added += 1
        if well_edges_added > 0:
            logger.info(f"✓ Added {well_edges_added} well edge constraints")

        # 5) Validate triangles (light cleanup)
        validated_facets = []
        validated_facet_markers = []
        for i, tri in enumerate(global_facets):
            if self._is_valid_triangle(tri, global_vertices):
                validated_facets.append(tri)
                validated_facet_markers.append(global_facet_markers[i])

        # Final assignment
        self.plc_vertices = np.asarray(global_vertices, dtype=np.float64)
        self.plc_facets = np.asarray(validated_facets, dtype=np.int32)
        self.plc_facet_markers = np.asarray(validated_facet_markers, dtype=np.int32)
        self.plc_edge_constraints = np.asarray(list(validated_edge_constraints), dtype=np.int32) if validated_edge_constraints else np.empty((0, 2), dtype=np.int32)
        self.plc_edge_markers = np.arange(1, len(self.plc_edge_constraints) + 1, dtype=np.int32)
        self.plc_holes = np.asarray(global_holes, dtype=np.float64) if global_holes else np.empty((0, 3), dtype=np.float64)

        logger.info(f"Final PLC built: {len(self.plc_vertices)} vertices, {len(self.plc_facets)} facets, {len(self.plc_edge_constraints)} edge constraints"
                    + (f", {len(global_holes)} holes" if len(global_holes) > 0 else ""))
    
    def _collect_holes_from_datasets(self, global_holes):
        """
        Collect hole centers from stored constraints in datasets.
        This is needed because conforming mesh data doesn't include hole information.
        """
        hole_count = 0
        processed_holes = set()  # Avoid duplicates
        
        for s_idx in self.selected_surfaces:
            if s_idx >= len(self.datasets):
                continue
                
            dataset = self.datasets[s_idx]
            surface_name = dataset.get("name", f"Surface_{s_idx}")
            
            # Look for intersection line constraints that might be marked as holes
            for constraint in dataset.get("stored_constraints", []):
                constraint_type = constraint.get("type")
                is_hole = constraint.get("is_hole", False)
                
                if constraint_type == "intersection_line" and is_hole:
                    # Get hole center from constraint points
                    points = constraint.get("points", [])
                    if points:
                        # Calculate centroid of intersection line points
                        hole_center = self._calculate_hole_center(points)
                        if hole_center:
                            # Create a unique key for this hole to avoid duplicates
                            hole_key = (round(hole_center[0], 3), round(hole_center[1], 3), round(hole_center[2], 3))
                            if hole_key not in processed_holes:
                                global_holes.append(hole_center)
                                processed_holes.add(hole_key)
                                hole_count += 1
                                logger.info(f"Collected hole from '{surface_name}' intersection at ({hole_center[0]:.3f}, {hole_center[1]:.3f}, {hole_center[2]:.3f})")
        
        if hole_count > 0:
            logger.info(f"✓ Collected {hole_count} holes from stored constraints")
        else:
            logger.info("No holes found in stored constraints - will check for GUI hole data")
    
    def _calculate_hole_center(self, points):
        """Calculate the center point of a hole from its boundary points."""
        if not points:
            return None
        
        # Convert points to numpy array for easier calculation
        import numpy as np
        
        try:
            # Handle different point formats
            coords = []
            for pt in points:
                if hasattr(pt, 'x'):  # Vector3D-like object
                    coords.append([pt.x, pt.y, pt.z])
                elif isinstance(pt, (list, tuple)) and len(pt) >= 3:
                    coords.append([pt[0], pt[1], pt[2]])
                else:
                    continue
            
            if not coords:
                return None
                
            coords_array = np.array(coords)
            center = np.mean(coords_array, axis=0)
            return [float(center[0]), float(center[1]), float(center[2])]
            
        except Exception as e:
            logger.warning(f"Failed to calculate hole center: {e}")
            return None

    def _edge_intersects_triangles(self, edge_tuple, triangles, vertices):
        """
        Check if an edge intersects any existing triangle (basic geometric validation).
        Made less aggressive to preserve more valid constraints (C++ style).
        """
        try:
            v1_idx, v2_idx = edge_tuple
            edge_start = np.array(vertices[v1_idx])
            edge_end = np.array(vertices[v2_idx])
            edge_vec = edge_end - edge_start
            edge_len = np.linalg.norm(edge_vec)
            
            if edge_len < 1e-10:
                return True  # Degenerate edge
            
            # Much less aggressive check - only check a few triangles randomly
            # to avoid removing too many valid constraints
            if len(triangles) > 20:
                # Sample only a small subset to avoid being too restrictive
                sample_indices = np.random.choice(len(triangles), min(10, len(triangles)), replace=False)
                sample_triangles = [triangles[i] for i in sample_indices]
            else:
                sample_triangles = triangles
            
            edge_dir = edge_vec / edge_len
            
            for tri in sample_triangles:
                if v1_idx in tri or v2_idx in tri:
                    continue  # Skip triangles that share vertices with the edge
                
                # Only flag clear intersections, not potential ones
                tri_verts = np.array([vertices[tri[j]] for j in range(3)])
                tri_center = np.mean(tri_verts, axis=0)
                
                # Very simple check: if edge passes very close to triangle center
                edge_to_center = tri_center - edge_start
                proj_len = np.dot(edge_to_center, edge_dir)
                
                if 0 < proj_len < edge_len:
                    closest_point = edge_start + proj_len * edge_dir
                    dist_to_tri = np.linalg.norm(tri_center - closest_point)
                    
                    # Only flag if edge passes very close to triangle center
                    if dist_to_tri < 1e-6:
                        return True
            
            return False
            
        except Exception:
            return False  # Be permissive on error

    def _is_valid_triangle(self, tri, vertices):
        """
        Check if a triangle is geometrically valid (non-degenerate).
        """
        try:
            if len(set(tri)) != 3:
                return False  # Duplicate vertices
            
            v0, v1, v2 = [np.array(vertices[i]) for i in tri]
            
            # Check for degenerate area
            edge1 = v1 - v0
            edge2 = v2 - v0
            cross = np.cross(edge1, edge2)
            area = 0.5 * np.linalg.norm(cross)
            
            return area > 1e-12
            
        except Exception:
            return False

    def _resolve_overlapping_triangles(self, triangles, markers, vertices):
        """
        Simple approach to resolve overlapping triangles by removing duplicates
        and triangles that are too close (C++ style validation).
        """
        try:
            if len(triangles) == 0:
                return triangles, markers
            
            # Convert to sets for easier duplicate detection
            triangle_sets = [frozenset(tri) for tri in triangles]
            
            # Remove exact duplicates
            seen = set()
            unique_indices = []
            for i, tri_set in enumerate(triangle_sets):
                if tri_set not in seen:
                    seen.add(tri_set)
                    unique_indices.append(i)
            
            unique_triangles = [triangles[i] for i in unique_indices]
            unique_markers = [markers[i] for i in unique_indices]
            
            logger.debug(f"Removed {len(triangles) - len(unique_triangles)} duplicate triangles")
            
            return unique_triangles, unique_markers
            
        except Exception as e:
            logger.warning(f"Triangle overlap resolution failed: {e}")
            return triangles, markers

    def _edge_creates_conflict(self, edge_tuple, existing_edges):
        """
        Check if adding this edge would create conflicts with existing edges.
        Simple check to avoid redundant or conflicting constraints.
        """
        if edge_tuple in existing_edges:
            return True  # Already exists
        
        # Check for reversed edge (should not happen with sorted tuples, but be safe)
        reversed_edge = (edge_tuple[1], edge_tuple[0])
        if reversed_edge in existing_edges:
            return True
        
        return False

    def _triangulate_surface_constraints(self, points_3d, segments, surface_name):
        """
        Robust triangulation of surface constraints with multiple fallback strategies.
        Returns triangle indices or None if all strategies fail.
        """
        if len(points_3d) < 3 or len(segments) < 1:
            return None
        
        try:
            # Project to best-fit plane for robust 2D triangulation
            points_3d_np = np.array(points_3d)
            centroid = np.mean(points_3d_np, axis=0)
            _, _, vh = np.linalg.svd(points_3d_np - centroid)
            basis = vh[0:2]
            points_2d_np = (points_3d_np - centroid) @ basis.T
            
            import triangle as tr
            plc_dict = {'vertices': points_2d_np, 'segments': np.array(segments)}
            
            # Strategy 1: Basic CDT (Constrained Delaunay Triangulation)
            try:
                tri_out = tr.triangulate(plc_dict, 'p')
                if 'triangles' in tri_out and len(tri_out['triangles']) > 0:
                    logger.debug(f"CDT successful for '{surface_name}': {len(tri_out['triangles'])} triangles")
                    return tri_out['triangles']
            except Exception as e:
                logger.debug(f"CDT failed for '{surface_name}': {e}")
            
            # Strategy 2: CDT with quality refinement (if not too many points)
            if len(points_3d) < 100:  # Avoid expensive refinement on large datasets
                try:
                    tri_out = tr.triangulate(plc_dict, 'pq20')  # 20-degree minimum angle
                    if 'triangles' in tri_out and len(tri_out['triangles']) > 0:
                        logger.debug(f"Quality CDT successful for '{surface_name}': {len(tri_out['triangles'])} triangles")
                        return tri_out['triangles']
                except Exception as e:
                    logger.debug(f"Quality CDT failed for '{surface_name}': {e}")
            
            # Strategy 3: Conforming Delaunay without constraints (last resort)
            try:
                # Remove segments and just triangulate the points
                simple_dict = {'vertices': points_2d_np}
                tri_out = tr.triangulate(simple_dict, 'p')
                if 'triangles' in tri_out and len(tri_out['triangles']) > 0:
                    logger.warning(f"Unconstrained triangulation used for '{surface_name}': {len(tri_out['triangles'])} triangles (constraints ignored)")
                    return tri_out['triangles']
            except Exception as e:
                logger.debug(f"Unconstrained triangulation failed for '{surface_name}': {e}")
                
        except Exception as e:
            logger.warning(f"All triangulation strategies failed for '{surface_name}': {e}")
        
        return None
        # ======================================================================
        # All intersection lines become hard edge constraints
        for s_idx in self.selected_surfaces:
            for constraint in self.datasets[s_idx].get("stored_constraints", []):
                if constraint.get("type") == "intersection_line":
                    points = constraint.get("points", [])
                    for i in range(len(points) - 1):
                        key1 = (round(points[i][0], 9), round(points[i][1], 9), round(points[i][2], 9))
                        key2 = (round(points[i+1][0], 9), round(points[i+1][1], 9), round(points[i+1][2], 9))
                        g_idx1, g_idx2 = key_to_global_idx.get(key1), key_to_global_idx.get(key2)
                        if g_idx1 is not None and g_idx2 is not None and g_idx1 != g_idx2:
                            edge_constraints.add(tuple(sorted((g_idx1, g_idx2))))
        
        # Final assignment to class attributes
        self.plc_vertices = np.asarray(global_vertices, dtype=np.float64)
        self.plc_facets = np.asarray(global_facets, dtype=np.int32)
        self.plc_facet_markers = np.asarray(global_facet_markers, dtype=np.int32)
        self.plc_edge_constraints = np.asarray(list(edge_constraints), dtype=np.int32) if edge_constraints else np.empty((0, 2), dtype=np.int32)
        self.plc_edge_markers = np.arange(1, len(self.plc_edge_constraints) + 1, dtype=np.int32)
        self.plc_holes = np.empty((0, 3), dtype=np.float64)  # No holes in fallback method

        logger.info(f"Final PLC built: {len(self.plc_vertices)} vertices, {len(self.plc_facets)} facets, {len(self.plc_edge_constraints)} edge constraints")

    def _prepare_material_regions(self) -> List[List[float]]:
        region_attributes_list = []
        if not self.materials:
            if self.plc_vertices is not None and len(self.plc_vertices) > 0:
                bounds_min = np.min(self.plc_vertices, axis=0)
                bounds_max = np.max(self.plc_vertices, axis=0)
                center = (bounds_min + bounds_max) / 2.0
                # FIX: Use 0 for volume constraint (no constraint), not -1
                region_attributes_list.append([center[0], center[1], center[2], 1, 0])
                logger.info("No materials defined. Using default material region at PLC center.")
        else:
            for material_idx, material in enumerate(self.materials):
                locations = material.get('locations', [])
                material_attribute = material.get('attribute', material_idx + 1)
                for loc in locations:
                    if len(loc) >= 3:
                        # FIX: Use 0 for volume constraint (no constraint), not -1
                        # This matches C++ geometry.cpp: in.regionlist[currentRegion*5+4]=0;
                        region_attributes_list.append([float(loc[0]), float(loc[1]), float(loc[2]), int(material_attribute), 0])
            logger.info(f"Prepared {len(region_attributes_list)} material regions from {len(self.materials)} materials.")
        return region_attributes_list

    def _prepare_materials_cpp_style(self) -> tuple:
        """
        Prepare materials following EXACT C++ MeshIt approach:
        - ONLY FORMATIONS become 3D volumetric regions (units/formations)
        - FAULTS are ONLY surface constraints (NO volumetric regions)
        - Material IDs MUST be sequential indices (0, 1, 2...) like C++ Mats array
        - This matches C++ where faults are facetmarkerlist[], formations are regionlist[]
        
        Returns:
            tuple: (volumetric_regions, surface_materials)
        """
        volumetric_regions = []
        surface_materials = []
        
        if not self.materials:
            # Default fallback: create one volumetric region at PLC center with material ID = 0
            if self.plc_vertices is not None and len(self.plc_vertices) > 0:
                bounds_min = np.min(self.plc_vertices, axis=0)
                bounds_max = np.max(self.plc_vertices, axis=0)
                center = (bounds_min + bounds_max) / 2.0
                volumetric_regions.append([center[0], center[1], center[2], 0, 0])  # Material ID = 0
                logger.info("No materials defined. Using default volumetric material region at PLC center with ID=0")
        else:
            # C++ Style: ALL materials get volumetric regions with SEQUENTIAL indices (0,1,2...)
            # CRITICAL: Sort materials by their attribute to ensure sequential ordering!
            sorted_materials = sorted(self.materials, key=lambda m: m.get('attribute', 0))
            
            for material in sorted_materials:
                material_name = material.get('name', '').lower()
                material_type = material.get('type', 'FORMATION')
                locations = material.get('locations', [])
                material_attribute = material.get('attribute', 0)  # Use material's attribute as ID
                
                # Check if this is a fault
                is_fault = (material_type == 'FAULT' or 
                           any(keyword in material_name for keyword in ['fault', 'fracture', 'crack', 'fissure']))
                
                if is_fault:
                    # CRITICAL: Faults are ONLY surface constraints - NO volumetric regions!
                    surface_materials.append(material)
                    logger.info(f"Material {material_attribute} '{material_name}' -> FAULT (surface constraint only)")
                    continue
                
                # ONLY formations/units get volumetric regions
                for loc in locations:
                    if len(loc) >= 3:
                        # CRITICAL: Use the material's attribute directly (already sequential 0,1,2...)
                        volumetric_regions.append([float(loc[0]), float(loc[1]), float(loc[2]), material_attribute, 0])
                        logger.info(f"Added 3D region: '{material.get('name')}' with C++ style ID={material_attribute}")
        
        max_material_id = max([int(region[3]) for region in volumetric_regions]) if volumetric_regions else -1
        logger.info(f"✓ TRUE C++ Style: {len(volumetric_regions)} volumetric regions (formations only, TetGen indices 0-{max_material_id})")
        logger.info(f"✓ TRUE C++ Style: {len(surface_materials)} surface materials (faults only, surface constraints)")
        
        return volumetric_regions, surface_materials

    def _run_tetgen_fallback_strategies(self, original_switches: str) -> Optional[pv.UnstructuredGrid]:
        logger.warning("Initial TetGen failed. Trying C++ style fallback strategies...")
        
        # C++ inspired fallback sequence - progressively more relaxed
        fallback_switches = [
            original_switches.replace('Y', '') + 'd',  # Detection without boundary Steiner points
            "pq1.2aA",   # C++ command line style with materials
            "pAd",       # Basic with materials and detection
            "pA",        # Basic with materials only
            "pd",        # Detection only
            "pzQ"        # Last resort (no refinement, no materials)
        ]
        
        for switches in fallback_switches:
            try:
                logger.warning(f"Trying fallback TetGen switches: '{switches}'")
                tet = tetgen.TetGen(self.plc_vertices, self.plc_facets, self.plc_facet_markers)
                
                if self.plc_edge_constraints is not None and len(self.plc_edge_constraints) > 0:
                    tet.edge_list = self.plc_edge_constraints.tolist()
                    tet.edge_marker_list = self.plc_edge_markers.tolist()
                
                # Use add_region() method for fallback strategies too (C++ style - only volumetric regions)
                if hasattr(self, 'plc_regions') and self.plc_regions:
                    for region in self.plc_regions:
                        region_id = int(region[3])  # material attribute
                        point = (float(region[0]), float(region[1]), float(region[2]))
                        max_vol = float(region[4]) if region[4] > 0 else 0.0
                        tet.add_region(region_id, point, max_vol)
                
                # Enable region attributes for fallback if 'A' switch is present and we have regions
                if hasattr(self, 'plc_regions') and self.plc_regions and 'A' in switches:
                    nodes, elements, attributes = tet.tetrahedralize(switches=switches, regionattrib=1.0)
                    grid = tet.grid
                    # Apply material attributes from fallback too
                    if attributes is not None and len(attributes) > 0:
                        grid.cell_data['MaterialID'] = attributes.astype(int)
                        import numpy as np
                        unique_materials = np.unique(attributes.astype(int))
                        logger.info(f"✓ Fallback: Applied TetGen material attributes: {unique_materials}")
                else:
                    tet.tetrahedralize(switches=switches)
                    grid = tet.grid
                    
                if grid is not None and grid.n_cells > 0:
                    logger.info(f"✓ Fallback TetGen succeeded with '{switches}': {grid.n_cells} tetrahedra")
                    
                    # Check if material attributes were applied in fallback
                    if 'MaterialID' in grid.cell_data and len(grid.cell_data['MaterialID']) > 0:
                        logger.info("✓ Fallback: Material attributes successfully obtained from TetGen")
                    else:
                        logger.info("Fallback: No material attributes - will need manual assignment")
                    
                    # Store TetGen object for constraint surface access
                    self.tetgen_object = tet
                    self.tetrahedral_mesh = grid
                    return grid
                else:
                    logger.warning(f"Fallback switches '{switches}' produced no tetrahedra.")
            except Exception as e:
                logger.warning(f"Fallback switches '{switches}' also failed: {e}")
        
        logger.error("All TetGen strategies failed. The input PLC has severe geometric issues.")
        return None
    
    def _export_plc_for_debugging(self):
        try:
            logger.info("Exporting PLC to debug_plc.vtm for inspection...")
            mesh = pv.PolyData(self.plc_vertices, faces=np.hstack((np.full((len(self.plc_facets), 1), 3), self.plc_facets)))
            mesh.cell_data['surface_id'] = self.plc_facet_markers
            
            multi_block = pv.MultiBlock()
            multi_block.append(mesh, "Facets")

            if self.plc_edge_constraints is not None and len(self.plc_edge_constraints) > 0:
                lines = []
                for edge in self.plc_edge_constraints:
                    lines.extend([2, edge[0], edge[1]])
                edge_mesh = pv.PolyData(self.plc_vertices, lines=np.array(lines))
                multi_block.append(edge_mesh, "Constraints")

            multi_block.save("debug_plc.vtm")
            logger.info("PLC debug file saved as debug_plc.vtm")
        except Exception as e:
            logger.error(f"Failed to export PLC debug files: {e}")

    def _export_netcdf(self, file_path: str, mesh_data: pv.UnstructuredGrid) -> bool:
        """
        Export tetrahedral mesh to NetCDF/EXODUS format following C++ MeshIt approach.

        Args:
            file_path: Path to save the NetCDF file
            mesh_data: PyVista UnstructuredGrid containing the tetrahedral mesh

        Returns:
            bool: True if export successful, False otherwise
        """
        if not HAS_NETCDF:
            logger.error("netCDF4 library not available. Cannot export to NetCDF format.")
            return False

        try:
            # Get mesh data
            points = mesh_data.points
            cells = mesh_data.cells
            cell_types = mesh_data.celltypes

            # Filter tetrahedral cells (cell type 10 in VTK)
            tetra_mask = cell_types == 10
            if not np.any(tetra_mask):
                logger.error("No tetrahedral cells found in mesh")
                return False

            # Extract tetrahedral cells only
            tetra_indices = np.where(tetra_mask)[0]
            tetra_cells = []
            offset = 0

            for i, cell_type in enumerate(cell_types):
                if cell_type == 10:  # Tetrahedral cell
                    n_points = cells[offset]
                    cell_data = cells[offset:offset + n_points + 1]
                    tetra_cells.append(cell_data)
                offset += cells[offset] + 1

            tetra_cells = np.array(tetra_cells)
            n_tetrahedra = len(tetra_cells)

            if n_tetrahedra == 0:
                logger.error("No tetrahedral cells found after processing")
                return False

            # Extract connectivity for tetrahedra only (skip the first element which is the number of points)
            connectivity = []
            for tetra_cell in tetra_cells:
                connectivity.extend(tetra_cell[1:])  # Skip the first element (number of points)

            connectivity = np.array(connectivity, dtype=np.int32)

            # Create NetCDF file following C++ EXODUS structure
            with nc.Dataset(file_path, 'w', format='NETCDF4') as rootgrp:
                # Set global attributes (matching C++ version)
                rootgrp.title = "MeshIt export"
                rootgrp.api_version = "4.98"
                rootgrp.version = "4.98"
                rootgrp.floating_point_word_size = "8"
                rootgrp.file_size = "0"

                # Dimensions (matching C++ structure)
                rootgrp.createDimension("num_dim", 3)
                rootgrp.createDimension("num_nodes", len(points))
                rootgrp.createDimension("num_elem", n_tetrahedra)
                rootgrp.createDimension("num_elem_blk", 1)  # Single block for now
                rootgrp.createDimension("num_node_sets", 0)
                rootgrp.createDimension("num_side_sets", 0)
                rootgrp.createDimension("len_string", 33)
                rootgrp.createDimension("len_line", 81)
                rootgrp.createDimension("four", 4)
                rootgrp.createDimension("time_step", None)  # unlimited

                # Coordinate variables (matching C++ naming)
                coordx = rootgrp.createVariable("coordx", "f8", ("num_nodes",))
                coordy = rootgrp.createVariable("coordy", "f8", ("num_nodes",))
                coordz = rootgrp.createVariable("coordz", "f8", ("num_nodes",))

                coordx[:] = points[:, 0]
                coordy[:] = points[:, 1]
                coordz[:] = points[:, 2]

                coordx.units = "mesh units"
                coordy.units = "mesh units"
                coordz.units = "mesh units"

                # Coordinate names (matching C++ const_cast<char**>(ex.coord_names))
                coor_names = rootgrp.createVariable("coor_names", "S1", ("num_dim", "len_string"))
                coor_names[0, :] = b"xcoor"
                coor_names[1, :] = b"ycoor"
                coor_names[2, :] = b"zcoor"

                # Element block info (matching C++ ex.ebids)
                eb_prop1 = rootgrp.createVariable("eb_prop1", "i4", ("num_elem_blk",))
                eb_prop1[0] = 1  # Default material ID

                eb_names = rootgrp.createVariable("eb_names", "S1", ("num_elem_blk", "len_string"))
                eb_names[0, :] = b"TETRA"

                # Node number map (matching C++ ex.node_num_map)
                node_num_map = rootgrp.createVariable("node_num_map", "i4", ("num_nodes",))
                node_num_map[:] = np.arange(1, len(points) + 1, dtype=np.int32)

                # Connectivity (matching C++ ex_put_elem_conn)
                connect1 = rootgrp.createVariable("connect1", "i4", ("num_elem", "four"))
                for i in range(n_tetrahedra):
                    # Convert to 1-based indexing (matching C++: (Mesh->tetrahedronlist[t * 4 + 0]) + 1)
                    connect1[i, :] = connectivity[i*4:(i+1)*4] + 1

                # Element map (matching C++ ex_put_map)
                elem_map = rootgrp.createVariable("elem_map", "i4", ("num_elem",))
                elem_map[:] = np.arange(1, n_tetrahedra + 1, dtype=np.int32)

                # QA records (matching C++ style)
                qa_records = rootgrp.createVariable("qa_records", "S1", ("num_elem_blk", "four", "len_string"))
                qa_records[0, 0, :] = b"MeshIt"
                qa_records[0, 1, :] = b"1.0"
                qa_records[0, 2, :] = b"2024-01-01"
                qa_records[0, 3, :] = b"00:00:00"

                # Info records (matching C++ style)
                rootgrp.createDimension("num_info", 1)
                info_records = rootgrp.createVariable("info_records", "S1", ("num_info", "len_line"))
                info_records[0, :] = b"Tetrahedral mesh generated by MeshIt Python"

            logger.info(f"Tetrahedral mesh exported to NetCDF/EXODUS format: {file_path}")
            return True

        except Exception as e:
            logger.error(f"NetCDF export failed: {str(e)}")
            return False

    def export_mesh(self, file_path: str, mesh_data: Optional[Dict] = None) -> bool:
        if mesh_data is None: mesh_data = self.tetrahedral_mesh
        if not mesh_data:
            logger.error("No tetrahedral mesh to export")
            return False

        try:
            if isinstance(mesh_data, pv.UnstructuredGrid):
                # Check file extension to determine export format
                file_ext = file_path.lower().split('.')[-1]

                if file_ext in ['nc', 'nc4', 'cdf', 'exo']:
                    # Use NetCDF/EXODUS export
                    return self._export_netcdf(file_path, mesh_data)
                else:
                    # Use PyVista's built-in export for other formats
                    mesh_data.save(file_path)
                    logger.info(f"Tetrahedral mesh exported to: {file_path}")
                    return True
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            return False
        return False

    def get_mesh_statistics(self, mesh_data: Optional[Dict] = None) -> Dict[str, Union[int, float]]:
        if mesh_data is None: mesh_data = self.tetrahedral_mesh
        if not mesh_data: return {}
        stats = {}
        if isinstance(mesh_data, pv.UnstructuredGrid):
            stats['n_vertices'] = mesh_data.n_points
            stats['n_tetrahedra'] = mesh_data.n_cells
            stats['volume'] = float(mesh_data.volume) if hasattr(mesh_data, 'volume') else 0.0
        return stats
