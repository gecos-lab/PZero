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
        self.region_attribute_map = {}

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
            # Pass per-facet markers into TetGen so trifacemarkerlist mirrors C++
            tet = tetgen.TetGen(self.plc_vertices, self.plc_facets, self.plc_facet_markers)
            
            # Step 2.5: Add holes to TetGen if any exist
            if hasattr(self, 'plc_holes') and self.plc_holes is not None and len(self.plc_holes) > 0:
                for hole_point in self.plc_holes:
                    hole_coords = (float(hole_point[0]), float(hole_point[1]), float(hole_point[2]))
                    tet.add_hole(hole_coords)
                    logger.info(f"Added hole to TetGen at ({hole_coords[0]:.3f}, {hole_coords[1]:.3f}, {hole_coords[2]:.3f})")
                logger.info(f"✓ Added {len(self.plc_holes)} holes to TetGen mesh")
            
            # Step 3: Add edge constraints.
            # NOTE: With new tetgen library, edge setting may need different approach
            # The properties are now read-only; edges come from tetrahedralize output
            if self.plc_edge_constraints is not None and len(self.plc_edge_constraints) > 0:
                try:
                    # Try the old API first (may work if attributes are set directly)
                    tet.edge_list = self.plc_edge_constraints.tolist()
                    tet.edge_marker_list = self.plc_edge_markers.tolist()
                    logger.info(f"Added {len(self.plc_edge_constraints)} intersection edge constraints to TetGen.")
                except AttributeError as e:
                    # If old API doesn't work, edges might need to be passed differently
                    logger.warning(f"Could not set edge constraints using old API: {e}")
                    logger.warning("Edge constraints may need to be included in the input mesh specification")
            
            # Step 4: Add material seed points using C++ MeshIt approach
            if self.materials:
                # Separate faults (2D surface materials) from units (3D volumetric materials)
                volumetric_regions, surface_materials = self._prepare_materials_cpp_style()
                
                if volumetric_regions:
                    # Only add VOLUMETRIC materials (units/formations) as 3D regions
                    # Check for holes and avoid placing material points in hole regions
                    hole_distance_threshold = 5.0  # Minimum distance from hole centers
                    
                    for i, region in enumerate(volumetric_regions):
                        region_id = int(region[3])  # unique TetGen region ID
                        material_attribute = self.region_attribute_map.get(region_id, region_id)
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
                        logger.info(
                            f"Added 3D region seed {region_id} for material {material_attribute}: "
                            f"point={point}, max_vol={max_vol}"
                        )
                    
                    # Log hole information for debugging
                    if hasattr(self, 'plc_holes') and self.plc_holes is not None and len(self.plc_holes) > 0:
                        logger.info(
                            f"✓ C++ Style: Added {len(volumetric_regions)} 3D region seeds "
                            f"(units/formations) to TetGen, avoiding {len(self.plc_holes)} holes"
                        )
                        for hole in self.plc_holes:
                            logger.debug(f"Hole at ({hole[0]:.3f}, {hole[1]:.3f}, {hole[2]:.3f})")
                    else:
                        logger.info(
                            f"✓ C++ Style: Added {len(volumetric_regions)} 3D region seeds "
                            f"(units/formations) to TetGen"
                        )
                    
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
                        nodes, elements, attributes, triface_markers = tet.tetrahedralize(switches=tetgen_switches, regionattrib=True)
                    else:
                        # Add 'A' switch if not present
                        modified_switches = tetgen_switches + 'A'
                        logger.info(f"Added 'A' switch for region attributes: '{modified_switches}'")
                        # New code capturing markers
                        nodes, elements, attributes, triface_markers = tet.tetrahedralize(switches=modified_switches, regionattrib=True)
                    
                    # Apply the material attributes to the grid
                    grid = tet.grid
                    if attributes is not None and len(attributes) > 0:
                        import numpy as np
                        mapped_attributes = self._map_region_ids_to_materials(attributes)
                        grid.cell_data['MaterialID'] = mapped_attributes
                        unique_materials = np.unique(mapped_attributes)
                        logger.info(f"✓ Applied TetGen material attributes directly: {unique_materials}")
                    else:
                        logger.warning("TetGen returned no material attributes despite having regions")
                else:
                    nodes, elements, attributes, triface_markers = tet.tetrahedralize(switches=tetgen_switches)
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
            
            # Extract fault surfaces using triface_markers (C++ style)
            if triface_markers is not None and len(triface_markers) > 0:
                try:
                    # Get the boundary/fault faces using the new property names
                    surf_markers = tet.triface_markers
                    surf_faces = tet.trifaces
                    
                    # Reconstruct the surface mesh (PolyData)
                    # tet.node is the new property for vertices
                    extracted_surface = pv.PolyData.from_regular_faces(tet.node, surf_faces)
                    extracted_surface.cell_data["MarkerID"] = surf_markers
                    
                    # Extract ONLY the faults
                    # Your logic used (1000 + s_idx) for faults
                    # So we filter for markers >= 1000
                    fault_indices = np.where(surf_markers >= 1000)[0]
                    if len(fault_indices) > 0:
                        # Extract only the fault cells
                        fault_mesh = extracted_surface.extract_cells(fault_indices)
                        logger.info(f"✓ Extracted {fault_mesh.n_cells} fault surface triangles from TetGen result")
                        
                        # Optional: Store it for export or debug
                        self.extracted_faults = fault_mesh
                    else:
                        logger.info("No fault surfaces detected (no markers >= 1000)")
                        self.extracted_faults = None
                        
                except Exception as e:
                    logger.warning(f"Failed to extract fault surfaces: {e}")
                    self.extracted_faults = None
            else:
                logger.info("No triface markers available for fault extraction")
                self.extracted_faults = None
            
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
        fault_marker_map = {}
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
                        if s_idx in fault_surfaces:
                            marker = 1000 + s_idx
                            global_facet_markers.append(marker)
                            fault_marker_map[marker] = s_idx
                        else:
                            global_facet_markers.append(s_idx)
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
                        if s_idx in fault_surfaces:
                            marker = 1000 + s_idx
                            global_facet_markers.append(marker)
                            fault_marker_map[marker] = s_idx
                        else:
                            global_facet_markers.append(s_idx)

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
        # Map: facet marker -> dataset surface index (only for faults)
        self.fault_surface_markers = fault_marker_map
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

    def _map_region_ids_to_materials(self, region_ids: Any) -> np.ndarray:
        """
        Convert TetGen region IDs back into the geological material attributes defined in the GUI.

        TetGen requires each region seed to have a unique ID, but multiple seeds can belong to the
        same geological material. This helper remaps the unique region IDs returned by TetGen to the
        intended material attribute IDs stored in ``self.region_attribute_map``.
        """
        if region_ids is None:
            return None

        region_ids_np = np.asarray(region_ids, dtype=int)

        if not self.region_attribute_map:
            return region_ids_np

        mapped = region_ids_np.copy()
        for region_id, material_attr in self.region_attribute_map.items():
            mask = region_ids_np == int(region_id)
            if np.any(mask):
                mapped[mask] = int(material_attr)

        return mapped

    def _prepare_materials_cpp_style(self) -> tuple:
        """
        Prepare materials following EXACT C++ MeshIt approach:
        - ONLY FORMATIONS become 3D volumetric regions (units/formations)
        - FAULTS are ONLY surface constraints (NO volumetric regions)
        - Material IDs MUST be sequential indices (0, 1, 2...) like C++ Mats array
        - This matches C++ where faults are facetmarkerlist[], formations are regionlist[]
        
        NOTE: Fault detection is now MANUAL via GUI checkboxes (C++ style).
        No automatic name-based fault detection. A material is only a fault if:
        - Its 'type' field is explicitly set to 'FAULT'
        - OR its surface index is in self.fault_surface_indices (from GUI checkboxes)
        
        Returns:
            tuple: (volumetric_regions, surface_materials)
        """
        volumetric_regions = []
        surface_materials = []
        self.region_attribute_map = {}
        region_id_counter = 0
        
        if not self.materials:
            # Default fallback: create one volumetric region at PLC center with material ID = 0
            if self.plc_vertices is not None and len(self.plc_vertices) > 0:
                bounds_min = np.min(self.plc_vertices, axis=0)
                bounds_max = np.max(self.plc_vertices, axis=0)
                center = (bounds_min + bounds_max) / 2.0
                volumetric_regions.append([center[0], center[1], center[2], region_id_counter, 0])
                self.region_attribute_map[region_id_counter] = 0
                logger.info("No materials defined. Using default volumetric material region at PLC center with ID=0")
                region_id_counter += 1
        else:
            # C++ Style: ALL materials get volumetric regions with SEQUENTIAL indices (0,1,2...)
            # CRITICAL: Sort materials by their attribute to ensure sequential ordering!
            sorted_materials = sorted(self.materials, key=lambda m: m.get('attribute', 0))
            
            for material in sorted_materials:
                material_name = material.get('name', '')
                material_type = material.get('type', 'FORMATION')
                locations = material.get('locations', [])
                material_attribute = material.get('attribute', 0)  # Geological material ID
                
                # Check if this is a fault - ONLY by explicit type, NOT by name (C++ style manual selection)
                # Faults are marked via GUI checkboxes which set type='FAULT'
                is_fault = (material_type == 'FAULT')
                
                if is_fault:
                    # CRITICAL: Faults are ONLY surface constraints - NO volumetric regions!
                    surface_materials.append(material)
                    logger.info(f"Material {material_attribute} '{material_name}' -> FAULT (surface constraint only, manually selected)")
                    continue
                
                # ONLY formations/units get volumetric regions
                for loc in locations:
                    if len(loc) >= 3:
                        region_id = region_id_counter
                        region_id_counter += 1
                        volumetric_regions.append([float(loc[0]), float(loc[1]), float(loc[2]), region_id, 0])
                        self.region_attribute_map[region_id] = material_attribute
                        logger.info(
                            f"Added 3D region seed {region_id} for '{material_name}' "
                            f"(material ID {material_attribute})"
                        )
        
        max_region_id = max([int(region[3]) for region in volumetric_regions]) if volumetric_regions else -1
        logger.info(
            f"✓ C++ Style: {len(volumetric_regions)} volumetric region seeds (region IDs 0-{max_region_id}) "
            f"covering {len(set(self.region_attribute_map.values()))} formation material(s)"
        )
        logger.info(f"✓ C++ Style: {len(surface_materials)} surface materials (faults only, manually selected)")
        logger.info(f"✓ C++ Style: {len(self.fault_surface_indices)} surface indices marked as faults via GUI")
        
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
                    try:
                        tet.edge_list = self.plc_edge_constraints.tolist()
                        tet.edge_marker_list = self.plc_edge_markers.tolist()
                    except AttributeError:
                        logger.warning("Could not set edge constraints in fallback - may need different API")
                
                # Use add_region() method for fallback strategies too (C++ style - only volumetric regions)
                if hasattr(self, 'plc_regions') and self.plc_regions:
                    for region in self.plc_regions:
                        region_id = int(region[3])  # unique TetGen region ID
                        point = (float(region[0]), float(region[1]), float(region[2]))
                        max_vol = float(region[4]) if region[4] > 0 else 0.0
                        tet.add_region(region_id, point, max_vol)
                
                # Enable region attributes for fallback if 'A' switch is present and we have regions
                if hasattr(self, 'plc_regions') and self.plc_regions and 'A' in switches:
                    nodes, elements, attributes, triface_markers = tet.tetrahedralize(switches=switches, regionattrib=True)
                    grid = tet.grid
                    # Apply material attributes from fallback too
                    if attributes is not None and len(attributes) > 0:
                        import numpy as np
                        mapped_attributes = self._map_region_ids_to_materials(attributes)
                        grid.cell_data['MaterialID'] = mapped_attributes
                        unique_materials = np.unique(mapped_attributes)
                        logger.info(f"✓ Fallback: Applied TetGen material attributes: {unique_materials}")
                else:
                    nodes, elements, attributes, triface_markers = tet.tetrahedralize(switches=switches)
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
                    # Enhanced export for VTK/VTU formats with material information
                    return self._export_with_materials(file_path, mesh_data)
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            return False
        return False
    
    def _export_with_materials(self, file_path: str, mesh_data: pv.UnstructuredGrid) -> bool:
        """
        Export mesh with proper material information for ParaView visualization.
        Combines volumetric tetrahedra AND fault surfaces into a single mesh (C++ style).
        This ensures faults appear as embedded constraint surfaces in ParaView.
        """
        try:
            import numpy as np
            import pyvista as pv
            
            logger.info("Exporting tetrahedral mesh with embedded fault surfaces (C++ MeshIt style)...")
            
            # Start with the volumetric tetrahedral mesh
            volume_mesh = mesh_data.copy()
            
            # Extract all fault surfaces from TetGen and merge with volume
            fault_surfaces_added = 0
            if hasattr(self, 'tetgen_object') and self.tetgen_object is not None:
                logger.info("DEBUG: TetGen object is available for fault extraction")
                
                # Check BOTH materials lists (self.materials and tetra_materials)
                fault_materials = []
                
                # Check self.materials (from PLC generation)
                if hasattr(self, 'materials') and self.materials:
                    self_faults = [m for m in self.materials if m.get('type') == 'FAULT']
                    fault_materials.extend(self_faults)
                    logger.info(f"DEBUG: Found {len(self_faults)} faults in self.materials")
                else:
                    logger.info("DEBUG: No self.materials or it's empty")
                
                # Check tetra_materials (from GUI, includes TetGen markers)
                if hasattr(self, 'tetra_materials') and self.tetra_materials:
                    tetra_faults = [m for m in self.tetra_materials if m.get('type') == 'FAULT']
                    logger.info(f"DEBUG: Found {len(tetra_faults)} faults in self.tetra_materials")
                    # Add only if not already in fault_materials
                    for tf in tetra_faults:
                        if not any(f.get('attribute') == tf.get('attribute') for f in fault_materials):
                            fault_materials.append(tf)
                            logger.info(f"DEBUG: Added fault from tetra_materials: {tf.get('name')}")
                else:
                    logger.info("DEBUG: No self.tetra_materials or it's empty")
                
                logger.info(f"Found {len(fault_materials)} fault materials for export")
                for fm in fault_materials:
                    logger.info(f"  Fault: {fm.get('name')} (ID {fm.get('attribute')}, marker {fm.get('marker')})")
                
                # Collect all fault triangles
                all_fault_points = []
                all_fault_cells = []
                all_fault_material_ids = []
                
                for fault_mat in fault_materials:
                    mat_id = fault_mat.get('attribute')
                    if mat_id is None:
                        continue
                    
                    # Extract fault surface from TetGen output
                    fault_surface = self._extract_fault_surface_for_export(mat_id)
                    
                    if fault_surface is not None and fault_surface.n_cells > 0:
                        # Get fault triangles
                        n_triangles = fault_surface.n_cells
                        
                        # Add MaterialID for this fault
                        fault_material_ids = np.full(n_triangles, mat_id, dtype=np.int32)
                        all_fault_material_ids.append(fault_material_ids)
                        
                        # Store the fault surface for merging
                        all_fault_points.append(fault_surface.points)
                        all_fault_cells.append(fault_surface.faces)
                        
                        fault_surfaces_added += 1
                        mat_name = fault_mat.get('name', f'Fault_{mat_id}')
                        logger.info(f"Extracted fault surface: {mat_name} (ID {mat_id}) with {n_triangles} triangles")
                
                # Merge fault surfaces with volume mesh (C++ style: single combined mesh)
                if fault_surfaces_added > 0:
                    logger.info(f"Merging {fault_surfaces_added} fault surfaces with volume mesh...")
                    
                    # Create a combined UnstructuredGrid with both tetrahedra and triangles
                    # This is the C++ MeshIt approach: mixed element types in one mesh
                    
                    # Get volume data
                    volume_points = volume_mesh.points
                    volume_cells = volume_mesh.cells
                    volume_cell_types = volume_mesh.celltypes
                    
                    # Prepare merged mesh arrays
                    merged_points = [volume_points]
                    merged_cells = [volume_cells]
                    merged_cell_types = [volume_cell_types]
                    
                    # Prepare MaterialID array (start with volume MaterialID)
                    if 'MaterialID' in volume_mesh.cell_data:
                        merged_material_ids = [volume_mesh.cell_data['MaterialID']]
                    else:
                        merged_material_ids = [np.zeros(volume_mesh.n_cells, dtype=np.int32)]
                    
                    # Add each fault surface
                    current_point_offset = len(volume_points)
                    
                    for i, (fault_pts, fault_cells, fault_mat_ids) in enumerate(zip(all_fault_points, all_fault_cells, all_fault_material_ids)):
                        # Reindex fault cells to account for point offset
                        fault_cells_array = np.array(fault_cells)
                        
                        # Parse VTK face format: [n, i1, i2, i3, n, i1, i2, i3, ...]
                        reindexed_cells = []
                        idx = 0
                        n_fault_triangles = 0
                        while idx < len(fault_cells_array):
                            n_pts = fault_cells_array[idx]
                            reindexed_cells.append(n_pts)
                            for j in range(1, n_pts + 1):
                                reindexed_cells.append(fault_cells_array[idx + j] + current_point_offset)
                            idx += n_pts + 1
                            n_fault_triangles += 1
                        
                        merged_points.append(fault_pts)
                        merged_cells.append(np.array(reindexed_cells))
                        merged_cell_types.append(np.full(n_fault_triangles, 5, dtype=np.uint8))  # VTK_TRIANGLE = 5
                        merged_material_ids.append(fault_mat_ids)
                        
                        current_point_offset += len(fault_pts)
                    
                    # Combine all arrays
                    final_points = np.vstack(merged_points)
                    final_cells = np.hstack(merged_cells)
                    final_cell_types = np.hstack(merged_cell_types)
                    final_material_ids = np.hstack(merged_material_ids)
                    
                    # Create the combined unstructured grid
                    combined_mesh = pv.UnstructuredGrid(final_cells, final_cell_types, final_points)
                    combined_mesh.cell_data['MaterialID'] = final_material_ids
                    
                    # Add a CellType array to distinguish tetrahedra from triangles in ParaView
                    cell_type_names = np.where(final_cell_types == 10, 0, 1)  # 0=Tetrahedra, 1=Triangle(Fault)
                    combined_mesh.cell_data['CellType'] = cell_type_names
                    
                    logger.info(f"✓ Created combined mesh: {combined_mesh.n_cells} cells ({volume_mesh.n_cells} tetrahedra + {combined_mesh.n_cells - volume_mesh.n_cells} fault triangles)")
                    logger.info(f"✓ Total points: {combined_mesh.n_points}")
                    
                    # Use the combined mesh for export
                    volume_mesh = combined_mesh
                else:
                    logger.info("No fault surfaces found - exporting volume mesh only")
            
            # Save the combined mesh
            file_ext = file_path.lower().split('.')[-1]
            
            if file_ext in ['vtu', 'vtk']:
                volume_mesh.save(file_path)
                logger.info(f"Saved combined mesh (volume + embedded faults) to {file_ext.upper()} format: {file_path}")
            elif file_ext == 'vtm':
                # For VTM, create a multiblock with the combined mesh
                multi_block = pv.MultiBlock()
                multi_block.append(volume_mesh, "Combined_Mesh")
                multi_block.save(file_path)
                logger.info(f"Saved combined mesh in VTM format: {file_path}")
            else:
                # For other formats, use PyVista's default
                volume_mesh.save(file_path)
                logger.info(f"Saved mesh to {file_ext.upper()} format: {file_path}")
            
            logger.info(f"✓ Tetrahedral mesh exported successfully!")
            logger.info(f"  ParaView Tips:")
            logger.info(f"  • Color by 'MaterialID' to see different materials")
            logger.info(f"  • Color by 'CellType' to distinguish tetrahedra (0) from faults (1)")
            logger.info(f"  • Use 'Extract Surface' filter to see fault outlines")
            logger.info(f"  • Use 'Threshold' filter on MaterialID to isolate specific materials")
            logger.info(f"  • Faults will appear as embedded surfaces (wireframe) within the volume")
            return True
            
        except Exception as e:
            logger.error(f"Enhanced export failed: {e}", exc_info=True)
            # Fallback to simple export
            try:
                mesh_data.save(file_path)
                logger.warning("Fell back to simple export without material blocks")
                return True
            except Exception as e2:
                logger.error(f"Simple export also failed: {e2}")
                return False
    
    def _extract_fault_surface_for_export(self, material_id: int):
        """Extract fault surface from TetGen for export (similar to GUI extraction)."""
        try:
            import numpy as np
            import pyvista as pv
            
            tet = self.tetgen_object
            if tet is None:
                logger.debug(f"No TetGen object available for fault {material_id}")
                return None
            
            # Find the PLC marker for this fault
            plc_marker = None
            
            # First check materials list
            for mat in self.materials:
                if mat.get('attribute') == material_id and mat.get('type') == 'FAULT':
                    plc_marker = mat.get('marker')
                    logger.debug(f"Found marker {plc_marker} for fault {material_id} in materials list")
                    break
            
            # If not found, check tetra_materials (GUI materials)
            if plc_marker is None and hasattr(self, 'tetra_materials'):
                for mat in self.tetra_materials:
                    if mat.get('attribute') == material_id and mat.get('type') == 'FAULT':
                        plc_marker = mat.get('marker')
                        logger.debug(f"Found marker {plc_marker} for fault {material_id} in tetra_materials")
                        break
            
            if plc_marker is None:
                logger.warning(f"No marker found for fault material {material_id}")
                return None
            
            # Try to get trifaces and markers from TetGen
            faces = None
            marks = None
            
            for fn in ('trifaces', 'f', 'faces', 'triangle_faces'):
                if hasattr(tet, fn):
                    faces = np.asarray(getattr(tet, fn))
                    if faces is not None and faces.ndim == 2 and faces.shape[1] == 3:
                        logger.debug(f"Got faces from TetGen.{fn}: {len(faces)} faces")
                        break
            
            for mn in ('triface_markers', 'face_markers', 'trifacemarkers', 'facetmarkerlist'):
                if hasattr(tet, mn):
                    marks = np.asarray(getattr(tet, mn))
                    if marks is not None and marks.ndim == 1:
                        logger.debug(f"Got markers from TetGen.{mn}: {len(marks)} markers")
                        break
            
            if faces is not None and marks is not None and len(faces) == len(marks):
                # Keep only faces on input facets (positive markers)
                pos = np.where(marks > 0)[0]
                if len(pos) > 0:
                    faces = faces[pos]
                    marks = marks[pos]
                    logger.debug(f"Filtered to {len(faces)} constraint faces (positive markers)")
                
                # Filter faces by marker
                idx = np.where(marks == plc_marker)[0]
                logger.info(f"Export: Found {len(idx)} faces for fault {material_id} with marker {plc_marker}")
                
                if len(idx) > 0:
                    # Get vertices
                    pts = None
                    for pn in ('node', 'points', 'v'):
                        if hasattr(tet, pn):
                            pts = np.asarray(getattr(tet, pn))
                            if pts is not None and pts.size > 0:
                                logger.debug(f"Got {len(pts)} points from TetGen.{pn}")
                                break
                    
                    if pts is not None:
                        fault_faces = faces[idx]
                        # Create PolyData
                        faces_vtk = np.hstack((np.full((fault_faces.shape[0], 1), 3, np.int32), fault_faces)).ravel()
                        fault_mesh = pv.PolyData(pts, faces_vtk)
                        logger.info(f"✓ Created fault surface for export: {fault_mesh.n_cells} triangles, {fault_mesh.n_points} points")
                        return fault_mesh
                    else:
                        logger.warning(f"No points found in TetGen object")
                else:
                    logger.warning(f"No faces found with marker {plc_marker}")
            else:
                logger.warning(f"Face/marker mismatch or not found: faces={faces is not None}, marks={marks is not None}")
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract fault surface for material {material_id}: {e}", exc_info=True)
            return None
    
    def _get_material_type_by_id(self, material_id: int) -> str:
        """Get material type by ID."""
        if hasattr(self, 'materials') and self.materials:
            for mat in self.materials:
                if mat.get('attribute') == material_id:
                    return mat.get('type', 'FORMATION')
        return 'FORMATION'
    
    def _get_material_name_by_id(self, material_id: int) -> str:
        """Get material name by ID."""
        if hasattr(self, 'materials') and self.materials:
            for mat in self.materials:
                if mat.get('attribute') == material_id:
                    return mat.get('name', f'Material_{material_id}')
        return f'Material_{material_id}'

    def get_mesh_statistics(self, mesh_data: Optional[Dict] = None) -> Dict[str, Union[int, float]]:
        if mesh_data is None: mesh_data = self.tetrahedral_mesh
        if not mesh_data: return {}
        stats = {}
        if isinstance(mesh_data, pv.UnstructuredGrid):
            stats['n_vertices'] = mesh_data.n_points
            stats['n_tetrahedra'] = mesh_data.n_cells
            stats['volume'] = float(mesh_data.volume) if hasattr(mesh_data, 'volume') else 0.0
        return stats