# In tetra_mesh_utils.py

import numpy as np
import logging
import tetgen
import pyvista as pv
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Union
from collections import defaultdict
from Pymeshit.intersection_utils import Vector3D
from scipy.spatial import cKDTree
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
                 surface_data: Dict = None, holes: List = None,
                 well_data: Dict = None):
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
            well_data: Dictionary of well data for 1D edge constraints (C++ style).
                       Format: {well_idx: {'points': [], 'marker': int, 'name': str}}
        """
        self.datasets = datasets
        self.selected_surfaces = selected_surfaces
        self.border_surface_indices = border_surface_indices
        self.unit_surface_indices = unit_surface_indices
        self.fault_surface_indices = fault_surface_indices
        self.materials = materials or []
        self.surface_data = surface_data or {}
        self.external_holes = holes or []  # Holes passed from GUI
        self.well_data = well_data or {}  # Well data for 1D edge constraints (C++ style)
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
        self.plc_marker_surface_map = {}
        self.plc_edge_surface_map = {}
        self.plc_edge_marker_map = {}
        self.plc_edge_facet_count = {}
        self._tetgen_failure_diagnostics_logged = False

    def _surface_name(self, surface_idx: Optional[int]) -> str:
        """Return a stable human-readable surface label for logging."""
        if surface_idx is None or surface_idx < 0 or surface_idx >= len(self.datasets):
            return f"Surface_{surface_idx}"
        return self.datasets[surface_idx].get("name", f"Surface_{surface_idx}")

    def _marker_to_surface_idx(self, marker: Any) -> Optional[int]:
        """Map a TetGen facet marker back to the originating dataset surface index."""
        try:
            marker_i = int(marker)
        except Exception:
            return None

        if marker_i >= 1000:
            surface_idx = marker_i - 1000
        elif marker_i > 0:
            surface_idx = marker_i - 1
        else:
            return None

        if 0 <= surface_idx < len(self.datasets):
            return surface_idx
        return None

    def _surface_kind_label(self, surface_idx: Optional[int]) -> str:
        """Return the configured TetGen role of a surface."""
        if surface_idx is None:
            return "unknown"
        if surface_idx in self.fault_surface_indices:
            return "fault"
        if surface_idx in self.border_surface_indices:
            return "border"
        if surface_idx in self.unit_surface_indices:
            return "unit"
        return "surface"

    def _get_surface_mesh_arrays(self, surface_idx: int) -> Tuple[np.ndarray, np.ndarray]:
        """Return `(vertices, triangles)` for a surface mesh used in TetGen diagnostics."""
        mesh_data = self.surface_data.get(surface_idx) or self.datasets[surface_idx].get("conforming_mesh") or {}
        vertices = np.asarray(mesh_data.get("vertices", []), dtype=float)
        triangles = np.asarray(mesh_data.get("triangles", []), dtype=int)

        if vertices.ndim != 2 or vertices.shape[0] == 0:
            return np.empty((0, 3), dtype=float), np.empty((0, 3), dtype=int)
        if triangles.ndim != 2 or triangles.shape[0] == 0:
            return vertices, np.empty((0, 3), dtype=int)

        return vertices, triangles[:, :3]

    def _summarize_surface_topology(self, surface_idx: int) -> Dict[str, int]:
        """Summarize local manifold issues on one conforming surface mesh."""
        vertices, triangles = self._get_surface_mesh_arrays(surface_idx)
        edge_count: Dict[Tuple[int, int], int] = defaultdict(int)
        triangle_keys = set()
        duplicate_triangles = 0

        for tri in triangles:
            try:
                tri_idx = [int(tri[0]), int(tri[1]), int(tri[2])]
            except Exception:
                continue
            if len(set(tri_idx)) != 3:
                duplicate_triangles += 1
                continue

            tri_key = tuple(sorted(tri_idx))
            if tri_key in triangle_keys:
                duplicate_triangles += 1
            triangle_keys.add(tri_key)

            for i in range(3):
                edge = tuple(sorted((tri_idx[i], tri_idx[(i + 1) % 3])))
                edge_count[edge] += 1

        return {
            "vertices": int(len(vertices)),
            "triangles": int(len(triangles)),
            "duplicate_triangles": int(duplicate_triangles),
            "non_manifold_edges": int(sum(1 for count in edge_count.values() if count > 2)),
            "boundary_edges": int(sum(1 for count in edge_count.values() if count == 1)),
        }

    def _surface_intersection_partners(self, surface_idx: int) -> List[int]:
        """Return other surfaces that this surface is explicitly constrained against."""
        partners = set()
        if surface_idx < 0 or surface_idx >= len(self.datasets):
            return []

        for constraint in self.datasets[surface_idx].get("stored_constraints", []):
            if constraint.get("type") != "intersection_line":
                continue
            other_surface = constraint.get("other_surface_id")
            if isinstance(other_surface, int) and 0 <= other_surface < len(self.datasets):
                partners.add(other_surface)

        return sorted(partners)

    def _build_plc_debug_maps(self) -> None:
        """Build PLC edge/facet ownership maps used by TetGen failure diagnostics."""
        marker_surface_map: Dict[int, int] = {}
        edge_surface_map: Dict[Tuple[int, int], set] = defaultdict(set)
        edge_marker_map: Dict[Tuple[int, int], set] = defaultdict(set)
        edge_facet_count: Dict[Tuple[int, int], int] = defaultdict(int)

        if self.plc_facets is None or self.plc_facet_markers is None:
            self.plc_marker_surface_map = {}
            self.plc_edge_surface_map = {}
            self.plc_edge_marker_map = {}
            self.plc_edge_facet_count = {}
            return

        for tri, marker in zip(np.asarray(self.plc_facets), np.asarray(self.plc_facet_markers)):
            try:
                tri_idx = [int(tri[0]), int(tri[1]), int(tri[2])]
                marker_i = int(marker)
            except Exception:
                continue

            surface_idx = self._marker_to_surface_idx(marker_i)
            if surface_idx is not None:
                marker_surface_map[marker_i] = surface_idx

            for i in range(3):
                edge = tuple(sorted((tri_idx[i], tri_idx[(i + 1) % 3])))
                edge_facet_count[edge] += 1
                edge_marker_map[edge].add(marker_i)
                if surface_idx is not None:
                    edge_surface_map[edge].add(surface_idx)

        self.plc_marker_surface_map = marker_surface_map
        self.plc_edge_surface_map = {edge: tuple(sorted(owners)) for edge, owners in edge_surface_map.items()}
        self.plc_edge_marker_map = {edge: tuple(sorted(markers)) for edge, markers in edge_marker_map.items()}
        self.plc_edge_facet_count = dict(edge_facet_count)

    def _format_plc_edge_coords(self, edge: Tuple[int, int]) -> str:
        """Format one PLC edge by coordinate for concise diagnostics."""
        if self.plc_vertices is None:
            return str(edge)
        try:
            p0 = np.asarray(self.plc_vertices[int(edge[0])], dtype=float)
            p1 = np.asarray(self.plc_vertices[int(edge[1])], dtype=float)
            return (
                f"({p0[0]:.2f}, {p0[1]:.2f}, {p0[2]:.2f}) -> "
                f"({p1[0]:.2f}, {p1[1]:.2f}, {p1[2]:.2f})"
            )
        except Exception:
            return str(edge)

    def _count_shared_plc_edges(self, surface_a: int, surface_b: int) -> Tuple[int, Optional[Tuple[int, int]]]:
        """Count PLC edges that are shared by two surfaces and return one example edge."""
        count = 0
        sample_edge = None
        for edge, owners in self.plc_edge_surface_map.items():
            if surface_a in owners and surface_b in owners:
                count += 1
                if sample_edge is None:
                    sample_edge = edge
        return count, sample_edge

    def _parse_tetgen_skipped_faces(
        self,
        face_path: str = "tetgen-tmpfile_skipped.face",
        node_path: str = "tetgen-tmpfile_skipped.node",
    ) -> Dict[str, Any]:
        """Parse TetGen skipped-face output to recover failing surfaces and markers."""
        result: Dict[str, Any] = {
            "entries": [],
            "surface_counts": {},
            "surface_markers": {},
        }

        if not os.path.exists(face_path):
            return result

        node_coords: Dict[int, Tuple[float, float, float]] = {}
        if os.path.exists(node_path):
            try:
                with open(node_path, "r", encoding="utf-8", errors="ignore") as handle:
                    lines = [line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#")]
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    node_coords[int(parts[0])] = (float(parts[1]), float(parts[2]), float(parts[3]))
            except Exception as exc:
                logger.warning("Failed to parse TetGen skipped node file '%s': %s", node_path, exc)

        surface_counts: Dict[int, int] = defaultdict(int)
        surface_markers: Dict[int, set] = defaultdict(set)

        try:
            with open(face_path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = [line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#")]
        except Exception as exc:
            logger.warning("Failed to parse TetGen skipped face file '%s': %s", face_path, exc)
            return result

        has_marker = 0
        if lines:
            header = lines[0].split()
            if len(header) > 1:
                try:
                    has_marker = int(header[1])
                except Exception:
                    has_marker = 0

        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 4:
                continue

            try:
                face_id = int(parts[0])
                nodes = (int(parts[1]), int(parts[2]), int(parts[3]))
                marker = int(parts[4]) if has_marker and len(parts) > 4 else 0
            except Exception:
                continue

            surface_idx = self._marker_to_surface_idx(marker)
            coords = [node_coords.get(node_id) for node_id in nodes if node_id in node_coords]
            entry = {
                "face_id": face_id,
                "nodes": nodes,
                "marker": marker,
                "surface_idx": surface_idx,
                "surface_name": self._surface_name(surface_idx) if surface_idx is not None else f"marker_{marker}",
                "coords": coords,
            }
            result["entries"].append(entry)

            if surface_idx is not None:
                surface_counts[surface_idx] += 1
                surface_markers[surface_idx].add(marker)

        result["surface_counts"] = dict(surface_counts)
        result["surface_markers"] = {
            surface_idx: tuple(sorted(markers)) for surface_idx, markers in surface_markers.items()
        }
        return result

    def _build_surface_polydata(self, surface_idx: int) -> Optional[pv.PolyData]:
        """Build a PyVista mesh for one surface for collision diagnostics."""
        vertices, triangles = self._get_surface_mesh_arrays(surface_idx)
        if len(vertices) == 0 or len(triangles) == 0:
            return None

        try:
            faces = np.hstack(
                (
                    np.full((len(triangles), 1), 3, dtype=np.int64),
                    np.asarray(triangles, dtype=np.int64),
                )
            ).ravel()
            return pv.PolyData(np.asarray(vertices, dtype=float), faces)
        except Exception as exc:
            logger.debug("Failed to build surface PolyData for '%s': %s", self._surface_name(surface_idx), exc)
            return None

    def _infer_problem_surface_pairs(self, surface_indices: List[int]) -> List[Dict[str, Any]]:
        """Infer likely bad surface intersections from PLC sharing and mesh collisions."""
        if len(surface_indices) < 2:
            return []

        surface_meshes = {}
        for surface_idx in surface_indices:
            mesh = self._build_surface_polydata(surface_idx)
            if mesh is not None and mesh.n_cells > 0:
                surface_meshes[surface_idx] = mesh

        pair_summaries: List[Dict[str, Any]] = []
        ordered_indices = sorted(surface_indices)
        for idx, surface_a in enumerate(ordered_indices):
            for surface_b in ordered_indices[idx + 1:]:
                collision_contacts = 0
                mesh_a = surface_meshes.get(surface_a)
                mesh_b = surface_meshes.get(surface_b)
                if mesh_a is not None and mesh_b is not None:
                    try:
                        _, collision_contacts = mesh_a.collision(
                            mesh_b,
                            contact_mode=0,
                            box_tolerance=1e-6,
                            cell_tolerance=0.0,
                        )
                    except Exception as exc:
                        logger.debug(
                            "Collision diagnostics failed for '%s' <-> '%s': %s",
                            self._surface_name(surface_a),
                            self._surface_name(surface_b),
                            exc,
                        )

                shared_plc_edges, sample_edge = self._count_shared_plc_edges(surface_a, surface_b)
                has_stored_intersection = (
                    surface_b in self._surface_intersection_partners(surface_a)
                    or surface_a in self._surface_intersection_partners(surface_b)
                )

                if collision_contacts <= 0 and shared_plc_edges <= 0 and not has_stored_intersection:
                    continue

                pair_summaries.append(
                    {
                        "surface_a": surface_a,
                        "surface_b": surface_b,
                        "collision_contacts": int(collision_contacts),
                        "shared_plc_edges": int(shared_plc_edges),
                        "has_stored_intersection": bool(has_stored_intersection),
                        "sample_edge": sample_edge,
                    }
                )

        return sorted(
            pair_summaries,
            key=lambda item: (
                item["collision_contacts"],
                item["shared_plc_edges"],
                int(item["has_stored_intersection"]),
            ),
            reverse=True,
        )

    def _collect_non_manifold_plc_edges(
        self,
        only_surfaces: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """Collect PLC edges shared by more than two facets."""
        issues: List[Dict[str, Any]] = []
        for edge, facet_count in self.plc_edge_facet_count.items():
            if facet_count <= 2:
                continue

            owner_surfaces = tuple(self.plc_edge_surface_map.get(edge, ()))
            if only_surfaces and owner_surfaces and not any(surface in only_surfaces for surface in owner_surfaces):
                continue

            issues.append(
                {
                    "edge": edge,
                    "facet_count": int(facet_count),
                    "surface_indices": owner_surfaces,
                    "markers": tuple(self.plc_edge_marker_map.get(edge, ())),
                }
            )

        return sorted(issues, key=lambda item: item["facet_count"], reverse=True)

    def _build_tetgen_failure_report(
        self,
        phase: str,
        tetgen_switches: str,
        error: Exception,
    ) -> str:
        """Build a plain-text TetGen failure report for debugging problematic surfaces."""
        self._build_plc_debug_maps()

        skipped_info = self._parse_tetgen_skipped_faces()
        problematic_surfaces = sorted(skipped_info.get("surface_counts", {}).keys())
        non_manifold_edges = self._collect_non_manifold_plc_edges(
            set(problematic_surfaces) if problematic_surfaces else None
        )
        pair_summaries = self._infer_problem_surface_pairs(problematic_surfaces) if problematic_surfaces else []

        lines: List[str] = []
        lines.append("TetGen Failure Report")
        lines.append("====================")
        lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
        lines.append(f"Phase: {phase}")
        lines.append(f"Switches: {tetgen_switches}")
        lines.append(f"Error: {error}")
        lines.append("")

        if skipped_info.get("entries"):
            lines.append(
                f"Skipped facets: {len(skipped_info['entries'])} facet(s) were skipped by TetGen due to self-intersections."
            )
        else:
            lines.append("Skipped facets: no skipped-face file was available.")
        lines.append("")

        if problematic_surfaces:
            lines.append("Problematic surfaces")
            lines.append("--------------------")
            for surface_idx in problematic_surfaces:
                counts = skipped_info["surface_counts"].get(surface_idx, 0)
                markers = skipped_info["surface_markers"].get(surface_idx, ())
                topology = self._summarize_surface_topology(surface_idx)
                partners = self._surface_intersection_partners(surface_idx)
                partner_names = [self._surface_name(idx) for idx in partners]

                reasons = [f"{counts} skipped facet(s)"]
                if topology["non_manifold_edges"] > 0:
                    reasons.append(f"{topology['non_manifold_edges']} non-manifold edge(s)")
                if topology["duplicate_triangles"] > 0:
                    reasons.append(f"{topology['duplicate_triangles']} duplicate triangle(s)")

                lines.append(
                    f"- {self._surface_name(surface_idx)} [idx={surface_idx}, kind={self._surface_kind_label(surface_idx)}, markers={list(markers)}]"
                )
                lines.append(f"  Reason: {', '.join(reasons)}")
                lines.append(
                    f"  Mesh summary: triangles={topology['triangles']}, vertices={topology['vertices']}, boundary_edges={topology['boundary_edges']}"
                )
                lines.append(
                    f"  Stored intersections: {', '.join(partner_names) if partner_names else 'none'}"
                )
            lines.append("")

        if pair_summaries:
            lines.append("Likely problematic surface intersections")
            lines.append("---------------------------------------")
            for summary in pair_summaries[:20]:
                sample_edge = summary.get("sample_edge")
                sample_edge_text = (
                    self._format_plc_edge_coords(sample_edge) if sample_edge is not None else "n/a"
                )
                lines.append(
                    f"- {self._surface_name(summary['surface_a'])} [idx={summary['surface_a']}] <-> "
                    f"{self._surface_name(summary['surface_b'])} [idx={summary['surface_b']}]: "
                    f"collision_contacts={summary['collision_contacts']}, "
                    f"shared_plc_edges={summary['shared_plc_edges']}, "
                    f"stored_intersection={summary['has_stored_intersection']}, "
                    f"sample_shared_edge={sample_edge_text}"
                )
            lines.append("")

        if non_manifold_edges:
            lines.append("PLC non-manifold edges")
            lines.append("----------------------")
            for issue in non_manifold_edges[:20]:
                owner_names = ", ".join(self._surface_name(idx) for idx in issue["surface_indices"]) or "unknown"
                lines.append(
                    f"- {self._format_plc_edge_coords(issue['edge'])}: "
                    f"facet_count={issue['facet_count']}, "
                    f"surfaces=[{owner_names}], markers={list(issue['markers'])}"
                )
            lines.append("")

        if skipped_info.get("entries"):
            lines.append("Skipped facets detail")
            lines.append("--------------------")
            for entry in skipped_info["entries"]:
                coord_text = (
                    "; ".join(f"({pt[0]:.3f}, {pt[1]:.3f}, {pt[2]:.3f})" for pt in entry["coords"])
                    if entry.get("coords")
                    else "n/a"
                )
                lines.append(
                    f"- face_id={entry['face_id']}, marker={entry['marker']}, "
                    f"surface={entry['surface_name']}, nodes={list(entry['nodes'])}, coords={coord_text}"
                )
            lines.append("")

        if not problematic_surfaces and not non_manifold_edges and not skipped_info.get("entries"):
            lines.append("No surface-specific diagnosis could be recovered from TetGen artifacts.")
            lines.append("")

        lines.append("Generated files")
        lines.append("---------------")
        lines.append("- debug_plc.vtm: PLC geometry with marker_id and surface_id cell data.")
        lines.append("- tetgen-tmpfile_skipped.face / tetgen-tmpfile_skipped.node: raw TetGen skipped-facet artifacts.")
        return "\n".join(lines) + "\n"

    def _write_tetgen_failure_report(
        self,
        phase: str,
        tetgen_switches: str,
        error: Exception,
        report_path: str = "tetgen_failure_report.txt",
    ) -> None:
        """Write a plain-text TetGen failure report to disk."""
        try:
            report_text = self._build_tetgen_failure_report(phase, tetgen_switches, error)
            with open(report_path, "w", encoding="utf-8") as handle:
                handle.write(report_text)
            logger.error("TetGen failure report saved as %s", report_path)
        except Exception as exc:
            logger.error("Failed to write TetGen failure report '%s': %s", report_path, exc)

    def _log_tetgen_failure_diagnostics(self, phase: str, tetgen_switches: str, error: Exception) -> None:
        """Emit a high-signal TetGen failure summary with surface and intersection names."""
        if self._tetgen_failure_diagnostics_logged:
            return
        self._tetgen_failure_diagnostics_logged = True

        self._build_plc_debug_maps()

        logger.error(
            "TetGen diagnostics after %s with switches '%s': %s",
            phase,
            tetgen_switches,
            error,
        )
        self._write_tetgen_failure_report(phase, tetgen_switches, error)

        skipped_info = self._parse_tetgen_skipped_faces()
        problematic_surfaces = sorted(skipped_info.get("surface_counts", {}).keys())

        if skipped_info.get("entries"):
            logger.error(
                "TetGen skipped %d surface facet(s) due to self-intersections.",
                len(skipped_info["entries"]),
            )
            for surface_idx in problematic_surfaces:
                counts = skipped_info["surface_counts"].get(surface_idx, 0)
                markers = skipped_info["surface_markers"].get(surface_idx, ())
                topology = self._summarize_surface_topology(surface_idx)
                partners = self._surface_intersection_partners(surface_idx)
                partner_names = ", ".join(self._surface_name(idx) for idx in partners[:4]) if partners else "none"

                logger.error(
                    "  Problem surface '%s' [idx=%d, kind=%s, marker(s)=%s]: skipped_facets=%d, triangles=%d, non_manifold_edges=%d, duplicate_triangles=%d, stored_intersections=%s",
                    self._surface_name(surface_idx),
                    surface_idx,
                    self._surface_kind_label(surface_idx),
                    list(markers),
                    counts,
                    topology["triangles"],
                    topology["non_manifold_edges"],
                    topology["duplicate_triangles"],
                    partner_names,
                )
        else:
            logger.error("TetGen did not leave a skipped-face file. Falling back to PLC topology diagnostics only.")

        non_manifold_edges = self._collect_non_manifold_plc_edges(set(problematic_surfaces) if problematic_surfaces else None)
        if non_manifold_edges:
            logger.error("Detected %d PLC non-manifold edge(s) shared by more than two facets.", len(non_manifold_edges))
            for issue in non_manifold_edges[:10]:
                owner_names = ", ".join(self._surface_name(idx) for idx in issue["surface_indices"]) or "unknown"
                logger.error(
                    "  PLC edge %s is shared by %d facets across surfaces [%s] (markers=%s)",
                    self._format_plc_edge_coords(issue["edge"]),
                    issue["facet_count"],
                    owner_names,
                    list(issue["markers"]),
                )

        if problematic_surfaces:
            pair_summaries = self._infer_problem_surface_pairs(problematic_surfaces)
            if pair_summaries:
                logger.error("Likely problematic surface intersections:")
                for summary in pair_summaries[:10]:
                    sample_edge = summary.get("sample_edge")
                    sample_edge_text = self._format_plc_edge_coords(sample_edge) if sample_edge is not None else "n/a"
                    logger.error(
                        "  '%s' [idx=%d] <-> '%s' [idx=%d]: collision_contacts=%d, shared_plc_edges=%d, stored_intersection=%s, sample_shared_edge=%s",
                        self._surface_name(summary["surface_a"]),
                        summary["surface_a"],
                        self._surface_name(summary["surface_b"]),
                        summary["surface_b"],
                        summary["collision_contacts"],
                        summary["shared_plc_edges"],
                        summary["has_stored_intersection"],
                        sample_edge_text,
                    )
            else:
                logger.error(
                    "No cross-surface collision pair was inferred from the problematic surfaces; the issue may be inside individual surface triangulations."
                )


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
                    logger.info(f"Added {len(self.plc_edge_constraints)} edge constraints to TetGen.")
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
                        detection_switches = tetgen_switches if 'd' in tetgen_switches else tetgen_switches + 'd'
                        logger.info(f"Trying TetGen with geometric detection: '{detection_switches}'")
                        tet.tetrahedralize(switches=detection_switches)
                        grid = tet.grid
                        logger.info("✓ TetGen succeeded with geometric detection")
                    except Exception as e2:
                        logger.error(f"TetGen with detection also failed: {e2}")
                        self._log_tetgen_failure_diagnostics("initial TetGen attempt", detection_switches, e2)
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

        # C++ MeshIt behavior: only wells are exported as TetGen edge constraints.
        # Surface intersections are encoded by matching surface facets, not by extra 3D edges.
        cpp_well_only_edges = True

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
                            # Use 1-based markers to avoid collision with TetGen's internal marker 0
                            global_facet_markers.append(s_idx + 1)
                        if s_idx in fault_surfaces and not cpp_well_only_edges:
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
                            # Use 1-based markers to avoid collision with TetGen's internal marker 0
                            global_facet_markers.append(s_idx + 1)

                logger.info(f"✓ Fallback triangulation successful for '{surface_name}': {len(local_tris)} triangles")

        # 3) Edge constraints initialization.
        # Use a dict (edge_tuple -> marker) so edges stay paired with markers.
        edge_constraint_markers = {}
        if not cpp_well_only_edges:
            for e in edge_constraints:
                edge_constraint_markers[e] = 1
        else:
            logger.info("C++ style: skipping extra surface/intersection edge constraints; exporting wells as TetGen edges only")

        # 4) Add WELL polylines as edge constraints (C++ style: merge into global
        #    point list, use selected segments from self.well_data when available).
        #
        # C++ uses tetID to guarantee well intersection points share the exact
        # same global vertex as the surface mesh.  Python stores coordinates
        # independently, so tiny float differences can cause a well endpoint to
        # miss the hash and create a new vertex *slightly* off the surface.
        # That makes the well edge pierce a surface triangle -> TetGen fails.
        #
        # Fix: build a KDTree from existing (surface) vertices and snap any
        # well point within SNAP_TOL to the nearest existing vertex.
        SNAP_TOL = 1e-6
        snap_tree = None
        num_surface_verts = len(global_vertices)
        if num_surface_verts > 0:
            snap_tree = cKDTree(np.asarray(global_vertices, dtype=np.float64))
        well_edges_added = 0
        well_snapped = 0

        def _add_well_pts_as_edges(pts, marker: int):
            """Merge well points into global PLC and create edges."""
            nonlocal well_edges_added, well_snapped
            gidxs = []
            for p in pts:
                if isinstance(p, Vector3D):
                    coords = [float(p.x), float(p.y), float(p.z)]
                else:
                    coords = [float(p[0]), float(p[1]), float(p[2])]
                key = (round(coords[0], 9), round(coords[1], 9), round(coords[2], 9))
                g = key_to_global_idx.get(key)
                if g is None and snap_tree is not None:
                    dist, nearest_idx = snap_tree.query(coords, k=1)
                    if dist <= SNAP_TOL:
                        g = int(nearest_idx)
                        key_to_global_idx[key] = g
                        well_snapped += 1
                if g is None:
                    g = len(global_vertices)
                    key_to_global_idx[key] = g
                    global_vertices.append(coords)
                gidxs.append(g)
            for i in range(len(gidxs) - 1):
                if gidxs[i] != gidxs[i + 1]:
                    e = tuple(sorted((gidxs[i], gidxs[i + 1])))
                    if e not in edge_constraint_markers:
                        edge_constraint_markers[e] = marker
                        well_edges_added += 1

        if self.well_data:
            for w_idx, well_info in self.well_data.items():
                marker = well_info.get('marker', w_idx + 2)
                well_edges = well_info.get('edges', [])
                if well_edges:
                    for edge_pts in well_edges:
                        _add_well_pts_as_edges(edge_pts, marker)
                else:
                    well_pts = well_info.get('points', [])
                    if well_pts and len(well_pts) >= 2:
                        _add_well_pts_as_edges(well_pts, marker)
                logger.info(f"  Well '{well_info.get('name', w_idx)}': added edges to PLC (marker={marker})")
        else:
            for d_idx, d in enumerate(self.datasets):
                if d.get('type') != 'WELL':
                    continue
                pts = d.get('refined_well_points') or d.get('points')
                if pts is None or len(pts) < 2:
                    continue
                _add_well_pts_as_edges(pts, d_idx + 2)

        if well_edges_added > 0:
            logger.info(f"✓ Added {well_edges_added} well edge constraints (from {'constraint tree' if self.well_data else 'all wells'})")
        if well_snapped > 0:
            logger.info(f"✓ Snapped {well_snapped} well points to existing surface mesh vertices (tol={SNAP_TOL})")

        # 5) Validate triangles (light cleanup)
        validated_facets = []
        validated_facet_markers = []
        for i, tri in enumerate(global_facets):
            if self._is_valid_triangle(tri, global_vertices):
                validated_facets.append(tri)
                validated_facet_markers.append(global_facet_markers[i])
        
        # 6) CRITICAL: Remove duplicate/overlapping triangles (C++ MeshIt style)
        # When two surfaces share an intersection, both might generate triangles
        # at the same location. TetGen will fail if the same triangle exists twice
        # with different facet markers.
        validated_facets, validated_facet_markers = self._remove_duplicate_triangles(
            validated_facets, validated_facet_markers, global_vertices
        )

        # Final assignment
        self.plc_vertices = np.asarray(global_vertices, dtype=np.float64)
        self.plc_facets = np.asarray(validated_facets, dtype=np.int32)
        self.plc_facet_markers = np.asarray(validated_facet_markers, dtype=np.int32)
        if edge_constraint_markers:
            edge_list = list(edge_constraint_markers.keys())
            marker_list = [edge_constraint_markers[e] for e in edge_list]
            self.plc_edge_constraints = np.asarray(edge_list, dtype=np.int32)
            self.plc_edge_markers = np.asarray(marker_list, dtype=np.int32)
        else:
            self.plc_edge_constraints = np.empty((0, 2), dtype=np.int32)
            self.plc_edge_markers = np.empty(0, dtype=np.int32)
        # Map: facet marker -> dataset surface index (only for faults)
        self.fault_surface_markers = fault_marker_map
        self.plc_holes = np.asarray(global_holes, dtype=np.float64) if global_holes else np.empty((0, 3), dtype=np.float64)
        self._build_plc_debug_maps()

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
    
    def _remove_duplicate_triangles(self, triangles, markers, vertices):
        """
        Remove duplicate and overlapping triangles from the PLC.
        
        This is critical for TetGen because overlapping facets with different markers
        will cause meshing to fail. When two surfaces share an intersection line,
        they can each generate triangles that are geometrically identical or very close.
        
        Strategy (C++ MeshIt style):
        1. Remove exact duplicates (same vertex indices, regardless of order)
        2. Remove geometrically duplicate triangles (same vertices, different indices due to tolerance)
        3. When duplicates exist with different markers, keep one (prefer boundary over fault)
        
        Returns:
            Tuple of (cleaned_triangles, cleaned_markers)
        """
        if len(triangles) == 0:
            return triangles, markers
        
        # Ensure we're working with lists for consistent behavior
        triangles = [list(t) for t in triangles]
        markers = list(markers)
        
        logger.info(f"Checking {len(triangles)} triangles for duplicates/overlaps...")
        
        # Step 1: Remove exact duplicates (same vertex indices)
        # Use frozenset to catch triangles with same vertices in any order
        seen_index_sets = {}  # frozenset(tri) -> (first_index, marker)
        index_duplicates = 0
        duplicate_pairs = []  # For logging which surfaces are overlapping
        
        for i, tri in enumerate(triangles):
            tri_set = frozenset(tri)
            if tri_set in seen_index_sets:
                index_duplicates += 1
                orig_idx, orig_marker = seen_index_sets[tri_set]
                curr_marker = markers[i]
                if orig_marker != curr_marker:
                    duplicate_pairs.append((orig_marker, curr_marker, tri))
            else:
                seen_index_sets[tri_set] = (i, markers[i])
        
        if index_duplicates > 0:
            logger.warning(f"Found {index_duplicates} duplicate triangles (same vertex indices, different markers)")
            # Log which surface pairs have overlapping triangles
            marker_conflicts = {}
            for orig_m, curr_m, tri in duplicate_pairs:
                key = tuple(sorted([orig_m, curr_m]))
                if key not in marker_conflicts:
                    marker_conflicts[key] = 0
                marker_conflicts[key] += 1
            for (m1, m2), count in marker_conflicts.items():
                logger.warning(f"  Surfaces {m1} and {m2}: {count} shared triangles")
        
        # Keep only unique triangles after index dedup
        unique_indices = [info[0] for info in seen_index_sets.values()]
        triangles = [triangles[i] for i in sorted(unique_indices)]
        markers = [markers[i] for i in sorted(unique_indices)]
        
        # Step 2: Remove geometrically duplicate triangles
        # Two triangles are geometric duplicates if their centroids and areas match closely
        def get_triangle_signature(tri):
            """Create a geometric signature for a triangle."""
            try:
                v0, v1, v2 = [np.array(vertices[idx]) for idx in tri]
                centroid = (v0 + v1 + v2) / 3.0
                edge1 = v1 - v0
                edge2 = v2 - v0
                area = 0.5 * np.linalg.norm(np.cross(edge1, edge2))
                # Round to tolerance for comparison
                cx, cy, cz = round(centroid[0], 6), round(centroid[1], 6), round(centroid[2], 6)
                a = round(area, 6)
                return (cx, cy, cz, a)
            except Exception:
                return None
        
        # Group triangles by their geometric signature
        signature_to_tris = {}  # signature -> [(tri_index, marker), ...]
        for i, tri in enumerate(triangles):
            sig = get_triangle_signature(tri)
            if sig is not None:
                if sig not in signature_to_tris:
                    signature_to_tris[sig] = []
                signature_to_tris[sig].append((i, markers[i]))
        
        # For each group of geometric duplicates, keep only one
        # Priority: boundary surfaces (lower marker) over faults (marker >= 1000)
        kept_indices = set()
        geometric_duplicates = 0
        
        for sig, tri_list in signature_to_tris.items():
            if len(tri_list) == 1:
                kept_indices.add(tri_list[0][0])
            else:
                geometric_duplicates += len(tri_list) - 1
                # Sort by marker: prefer lower markers (boundary surfaces)
                # Fault markers are >= 1000, so boundaries will be preferred
                tri_list_sorted = sorted(tri_list, key=lambda x: x[1])
                kept_indices.add(tri_list_sorted[0][0])
                
                # Log what we're removing
                removed_markers = [m for _, m in tri_list_sorted[1:]]
                kept_marker = tri_list_sorted[0][1]
                logger.debug(f"Geometric duplicate: keeping marker {kept_marker}, removing markers {removed_markers}")
        
        if geometric_duplicates > 0:
            logger.warning(f"Removed {geometric_duplicates} geometrically duplicate triangles (overlapping surfaces)")
        
        # Build final lists
        final_triangles = []
        final_markers = []
        for i in sorted(kept_indices):
            final_triangles.append(triangles[i])
            final_markers.append(markers[i])
        
        total_removed = len(triangles) - len(final_triangles) + index_duplicates
        if total_removed > 0:
            logger.info(f"✓ Duplicate removal complete: {total_removed} triangles removed, {len(final_triangles)} remaining")
        
        return final_triangles, final_markers

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
                if (
                    not self._tetgen_failure_diagnostics_logged
                    and ("self-intersection" in str(e).lower() or "manifold" in str(e).lower())
                ):
                    self._log_tetgen_failure_diagnostics("fallback TetGen attempt", switches, e)
                logger.warning(f"Fallback switches '{switches}' also failed: {e}")
        
        logger.error("All TetGen strategies failed. The input PLC has severe geometric issues.")
        if not self._tetgen_failure_diagnostics_logged:
            self._write_tetgen_failure_report(
                "final fallback summary",
                "all fallback strategies",
                RuntimeError("All TetGen strategies failed. The input PLC has severe geometric issues."),
            )
        return None
    
    def _export_plc_for_debugging(self):
        try:
            logger.info("Exporting PLC to debug_plc.vtm for inspection...")
            mesh = pv.PolyData(self.plc_vertices, faces=np.hstack((np.full((len(self.plc_facets), 1), 3), self.plc_facets)))
            mesh.cell_data['marker_id'] = self.plc_facet_markers
            dataset_idx = np.array(
                [self._marker_to_surface_idx(marker) if self._marker_to_surface_idx(marker) is not None else -1
                 for marker in self.plc_facet_markers],
                dtype=np.int32,
            )
            mesh.cell_data['surface_id'] = dataset_idx
            
            multi_block = pv.MultiBlock()
            multi_block.append(mesh, "Facets")

            if self.plc_edge_constraints is not None and len(self.plc_edge_constraints) > 0:
                lines = []
                for edge in self.plc_edge_constraints:
                    lines.extend([2, edge[0], edge[1]])
                edge_mesh = pv.PolyData(self.plc_vertices, lines=np.array(lines))
                if self.plc_edge_markers is not None and len(self.plc_edge_markers) == len(self.plc_edge_constraints):
                    edge_mesh.cell_data['edge_marker'] = np.asarray(self.plc_edge_markers, dtype=np.int32)
                multi_block.append(edge_mesh, "Constraints")

            multi_block.save("debug_plc.vtm")
            logger.info("PLC debug file saved as debug_plc.vtm")
        except Exception as e:
            logger.error(f"Failed to export PLC debug files: {e}")

    def _export_netcdf(self, file_path: str, mesh_data: pv.UnstructuredGrid,
                       custom_block_names: Optional[Dict[int, str]] = None,
                       custom_sideset_names: Optional[Dict[int, str]] = None,
                       custom_well_names: Optional[Dict[int, str]] = None,
                       well_export_type: str = "Node Sets") -> bool:
        """
        Export tetrahedral mesh to EXODUS II format for GOLEM/MOOSE/ParaView compatibility.
        
        This follows the EXODUS II specification with proper:
        - Element Blocks: One per material domain (3D tetrahedra) with proper naming
        - Node Sets: Well nodes for point sources/sinks (GOLEM DiracKernels)
        - Sidesets: One per surface boundary for boundary conditions
        - All required EXODUS II attributes for ParaView compatibility

        Args:
            file_path: Path to save the EXODUS file (.exo)
            mesh_data: PyVista UnstructuredGrid containing the tetrahedral mesh
            custom_block_names: Optional dict mapping material_id -> custom block name
            custom_sideset_names: Optional dict mapping marker_id -> custom sideset name
            custom_well_names: Optional dict mapping well_marker -> custom well name
            well_export_type: "Node Sets" (for GOLEM DiracKernels) or "Element Blocks" (BAR2)

        Returns:
            bool: True if export successful, False otherwise
        """
        if not HAS_NETCDF:
            logger.error("netCDF4 library not available. Cannot export to EXODUS format.")
            return False

        # Store custom names for use by helper methods
        self._custom_block_names = custom_block_names or {}
        self._custom_sideset_names = custom_sideset_names or {}
        self._custom_well_names = custom_well_names or {}
        self._well_export_type = well_export_type

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

            # Extract tetrahedral cells and their connectivity
            tetra_cells = []
            tetra_global_indices = []
            offset = 0

            for i, cell_type in enumerate(cell_types):
                if cell_type == 10:  # Tetrahedral cell
                    n_points = cells[offset]
                    cell_data = cells[offset:offset + n_points + 1]
                    tetra_cells.append(cell_data)
                    tetra_global_indices.append(i)
                offset += cells[offset] + 1

            tetra_cells = np.array(tetra_cells)
            n_tetrahedra = len(tetra_cells)

            if n_tetrahedra == 0:
                logger.error("No tetrahedral cells found after processing")
                return False

            # Extract material IDs from mesh data
            material_ids = None
            if 'MaterialID' in mesh_data.cell_data:
                all_material_ids = mesh_data.cell_data['MaterialID']
                material_ids = np.array([all_material_ids[idx] for idx in tetra_global_indices], dtype=np.int32)
            else:
                material_ids = np.ones(n_tetrahedra, dtype=np.int32)
            
            # Group tetrahedra by material
            unique_materials = np.unique(material_ids)
            num_tetra_blk = len(unique_materials)
            
            # Build element blocks: {material_id: [tetra_indices]}
            elem_blocks = {}
            for mat_id in unique_materials:
                elem_blocks[mat_id] = np.where(material_ids == mat_id)[0]
            
            # ========== COLLECT WELL DATA AND MAP TO EXISTING MESH NODES ==========
            # CRITICAL FIX: Wells must share node IDs with the tetra mesh, not duplicate points.
            # This ensures fracture-well connectivity works in MOOSE/GOLEM.
            # Wells can be exported as Node Sets (for GOLEM DiracKernels) or Element Blocks (BAR2)
            well_blocks = {}  # {well_marker: {'mapped_indices': [], 'n_edges': int, 'name': str}}
            well_node_sets = {}  # {well_marker: {'mapped_indices': [], 'name': str}}
            total_well_edges = 0
            total_well_nodes = 0
            
            export_wells_as_nodesets = (self._well_export_type == "Node Sets")
            
            if hasattr(self, 'well_data') and self.well_data:
                logger.info(f"Processing wells as {'Node Sets' if export_wells_as_nodesets else 'Element Blocks'} (mapping to existing mesh nodes)...")

                def _extract_coord_nc(p):
                    if hasattr(p, 'x'):
                        return (float(p.x), float(p.y), float(p.z))
                    return (float(p[0]), float(p[1]), float(p[2]))

                for well_idx, well_info in self.well_data.items():
                    well_marker = well_info.get('marker', well_idx + 2)
                    well_name = well_info.get('name', f'Well_{well_idx}')
                    well_edges = well_info.get('edges', [])

                    if hasattr(self, '_custom_well_names') and well_marker in self._custom_well_names:
                        well_name = self._custom_well_names[well_marker]

                    if well_edges:
                        unique_pts = []
                        key_to_local = {}
                        edge_pairs = []
                        for edge_pts in well_edges:
                            if len(edge_pts) < 2:
                                continue
                            local_idxs = []
                            for p in (edge_pts[0], edge_pts[1]):
                                c = _extract_coord_nc(p)
                                key = (round(c[0], 9), round(c[1], 9), round(c[2], 9))
                                if key not in key_to_local:
                                    key_to_local[key] = len(unique_pts)
                                    unique_pts.append(list(c))
                                local_idxs.append(key_to_local[key])
                            if local_idxs[0] != local_idxs[1]:
                                edge_pairs.append((local_idxs[0], local_idxs[1]))
                    else:
                        well_pts = well_info.get('points')
                        if well_pts is None or len(well_pts) < 2:
                            continue
                        unique_pts = [list(_extract_coord_nc(p)) for p in well_pts]
                        edge_pairs = [(i, i + 1) for i in range(len(unique_pts) - 1)]

                    if len(unique_pts) < 2 or not edge_pairs:
                        continue

                    pts_arr = np.array(unique_pts, dtype=np.float64)
                    n_pts = len(pts_arr)
                    n_edges = len(edge_pairs)

                    try:
                        mapped_indices = map_well_points_to_mesh_nodes(
                            points, pts_arr, tolerance=1e-5, precision=9
                        )
                        logger.info(f"  Well '{well_name}': mapped {n_pts} unique points to existing mesh nodes")
                    except ValueError as e:
                        logger.error(f"  Well '{well_name}' mapping failed: {e}")
                        raise

                    unused_nodes = validate_well_node_usage(mapped_indices, cells, cell_types)
                    if unused_nodes:
                        logger.warning(
                            f"  Well '{well_name}': {len(unused_nodes)} mapped nodes are not used by any "
                            f"tetrahedral element. This may indicate incomplete PLC integration. "
                            f"Unused node indices: {unused_nodes[:5]}{'...' if len(unused_nodes) > 5 else ''}"
                        )

                    if export_wells_as_nodesets:
                        well_node_sets[well_marker] = {
                            'mapped_indices': mapped_indices,
                            'n_nodes': n_pts,
                            'name': well_name
                        }
                        total_well_nodes += n_pts
                        logger.info(f"  Well node set '{well_name}' (marker {well_marker}): {n_pts} nodes (shared with mesh)")
                    else:
                        well_blocks[well_marker] = {
                            'mapped_indices': mapped_indices,
                            'edge_pairs': edge_pairs,
                            'n_edges': n_edges,
                            'name': well_name
                        }
                        total_well_edges += n_edges
                        logger.info(f"  Well element block '{well_name}' (marker {well_marker}): {n_edges} BAR2 elements (shared nodes)")
            
            num_well_blk = len(well_blocks) if not export_wells_as_nodesets else 0
            num_well_nodesets = len(well_node_sets) if export_wells_as_nodesets else 0
            num_elem_blk = num_tetra_blk + num_well_blk
            
            if export_wells_as_nodesets:
                logger.info(f"EXODUS export: {num_tetra_blk} tetra blocks, {num_well_nodesets} well node sets")
            else:
                logger.info(f"EXODUS export: {num_tetra_blk} tetra blocks + {num_well_blk} well element blocks = {num_elem_blk} total")

            # Build sidesets from TetGen surface triangles
            sidesets = self._build_exodus_sidesets(mesh_data, tetra_cells, tetra_global_indices)
            num_side_sets = len(sidesets)
            logger.info(f"EXODUS export: {num_side_sets} sidesets for boundary surfaces")

            # Extract connectivity for tetrahedra only
            connectivity = []
            for tetra_cell in tetra_cells:
                connectivity.extend(tetra_cell[1:])
            connectivity = np.array(connectivity, dtype=np.int32)

            # Create EXODUS II file using NETCDF3_64BIT_OFFSET for maximum compatibility
            with nc.Dataset(file_path, 'w', format='NETCDF3_64BIT_OFFSET') as rootgrp:
                
                # ========== EXODUS II REQUIRED GLOBAL ATTRIBUTES ==========
                rootgrp.setncattr('api_version', np.float32(4.98))
                rootgrp.setncattr('version', np.float32(4.98))
                rootgrp.setncattr('floating_point_word_size', np.int32(8))
                rootgrp.setncattr('file_size', np.int32(1))
                rootgrp.setncattr('maximum_name_length', np.int32(32))
                rootgrp.setncattr('int64_status', np.int32(0))
                rootgrp.setncattr('title', 'PyMeshIt mesh for GOLEM/MOOSE')

                # ========== WELL NODE INDICES ARE ALREADY MAPPED ==========
                # CRITICAL FIX: Do NOT append well points to coordinates.
                # Wells now use mapped_indices that reference existing mesh nodes.
                # This ensures wells share node IDs with the tetra mesh for fracture connectivity.
                
                total_elements = n_tetrahedra + total_well_edges  # BAR2 elements only if not using node sets
                total_points = len(points)  # NO extra well points - they're mapped to existing nodes
                
                logger.info(f"EXODUS: {total_points} nodes (tetra mesh only, wells use shared node IDs)")
                
                # ========== EXODUS II REQUIRED DIMENSIONS ==========
                rootgrp.createDimension('len_string', 33)
                rootgrp.createDimension('len_name', 33)
                rootgrp.createDimension('len_line', 81)
                rootgrp.createDimension('four', 4)
                rootgrp.createDimension('num_dim', 3)
                rootgrp.createDimension('num_nodes', total_points)
                rootgrp.createDimension('num_elem', total_elements)
                rootgrp.createDimension('num_el_blk', num_elem_blk)
                rootgrp.createDimension('num_node_sets', num_well_nodesets)  # Well node sets for GOLEM
                rootgrp.createDimension('num_side_sets', num_side_sets)
                rootgrp.createDimension('num_qa_rec', 1)
                rootgrp.createDimension('time_step', 1)  # Fixed size for NETCDF3 compatibility

                # ========== COORDINATES (tetra mesh nodes only) ==========
                coordx = rootgrp.createVariable('coordx', 'f8', ('num_nodes',))
                coordy = rootgrp.createVariable('coordy', 'f8', ('num_nodes',))
                coordz = rootgrp.createVariable('coordz', 'f8', ('num_nodes',))
                coordx[:] = points[:, 0]
                coordy[:] = points[:, 1]
                coordz[:] = points[:, 2]

                # Coordinate names
                coor_names = rootgrp.createVariable('coor_names', 'S1', ('num_dim', 'len_name'))
                self._write_exodus_string_v2(coor_names, 0, 'x', 33)
                self._write_exodus_string_v2(coor_names, 1, 'y', 33)
                self._write_exodus_string_v2(coor_names, 2, 'z', 33)

                # ========== ELEMENT BLOCK METADATA ==========
                eb_status = rootgrp.createVariable('eb_status', 'i4', ('num_el_blk',))
                eb_prop1 = rootgrp.createVariable('eb_prop1', 'i4', ('num_el_blk',))
                eb_prop1.setncattr('name', 'ID')
                
                eb_names = rootgrp.createVariable('eb_names', 'S1', ('num_el_blk', 'len_name'))

                # CRITICAL: Build mapping from TetGen element index to EXODUS global element index
                # This is needed because EXODUS stores elements grouped by blocks, but sidesets
                # need to reference the EXODUS global element numbers
                tetgen_to_exodus_elem = np.zeros(n_tetrahedra, dtype=np.int32)
                exodus_elem_counter = 0

                # Create element blocks
                for blk_idx, mat_id in enumerate(unique_materials):
                    mat_id_int = int(mat_id)
                    block_tetra_indices = elem_blocks[mat_id]
                    num_el_in_blk = len(block_tetra_indices)
                    
                    # Build the mapping: TetGen index -> EXODUS global index (0-based)
                    for local_idx, tetgen_idx in enumerate(block_tetra_indices):
                        tetgen_to_exodus_elem[tetgen_idx] = exodus_elem_counter + local_idx
                    exodus_elem_counter += num_el_in_blk
                    
                    # Block ID and status
                    eb_prop1[blk_idx] = mat_id_int + 1  # 1-based block IDs
                    eb_status[blk_idx] = 1
                    
                    # Block name
                    block_name = self._generate_block_name(mat_id_int)
                    self._write_exodus_string_v2(eb_names, blk_idx, block_name, 33)
                    
                    # Create dimensions for this block
                    blk_num = blk_idx + 1
                    rootgrp.createDimension(f'num_el_in_blk{blk_num}', num_el_in_blk)
                    rootgrp.createDimension(f'num_nod_per_el{blk_num}', 4)
                    
                    # Connectivity variable
                    connect = rootgrp.createVariable(
                        f'connect{blk_num}', 'i4',
                        (f'num_el_in_blk{blk_num}', f'num_nod_per_el{blk_num}')
                    )
                    connect.setncattr('elem_type', 'TETRA4')
                    
                    # Write connectivity (1-based)
                    for local_idx, global_tetra_idx in enumerate(block_tetra_indices):
                        connect[local_idx, :] = connectivity[global_tetra_idx*4:(global_tetra_idx+1)*4] + 1
                    
                    logger.info(f"  Block {blk_num}: '{block_name}' - {num_el_in_blk} elements")
                
                # ========== WELL ELEMENT BLOCKS (BAR2) - Only if not using Node Sets ==========
                # CRITICAL FIX: Use mapped_indices to reference existing mesh nodes
                if not export_wells_as_nodesets and well_blocks:
                    for well_idx, (well_marker, well_blk) in enumerate(well_blocks.items()):
                        blk_idx = num_tetra_blk + well_idx
                        blk_num = blk_idx + 1
                        
                        well_name = well_blk['name']
                        n_edges = well_blk['n_edges']
                        mapped_indices = well_blk['mapped_indices']  # 0-based mesh node indices
                        
                        # Block ID and status
                        eb_prop1[blk_idx] = int(well_marker) + 1000  # Use marker + 1000 to distinguish from tetra blocks
                        eb_status[blk_idx] = 1
                        
                        # Write block name
                        self._write_exodus_string_v2(eb_names, blk_idx, well_name, 33)
                        
                        # Create dimensions for this well block
                        rootgrp.createDimension(f'num_el_in_blk{blk_num}', n_edges)
                        rootgrp.createDimension(f'num_nod_per_el{blk_num}', 2)  # BAR2 = 2 nodes per edge
                        
                        # Connectivity variable
                        connect = rootgrp.createVariable(
                            f'connect{blk_num}', 'i4',
                            (f'num_el_in_blk{blk_num}', f'num_nod_per_el{blk_num}')
                        )
                        connect.setncattr('elem_type', 'BAR2')  # EXODUS BAR2 element type
                        
                        # Write well edge connectivity using edge_pairs and MAPPED mesh node indices (1-based)
                        edge_pairs = well_blk['edge_pairs']
                        for edge_idx, (a, b) in enumerate(edge_pairs):
                            connect[edge_idx, 0] = mapped_indices[a] + 1   # First node (1-based)
                            connect[edge_idx, 1] = mapped_indices[b] + 1   # Second node (1-based)
                        
                        # Validate connectivity references valid nodes
                        max_node_ref = max(mapped_indices) + 1  # 1-based
                        if max_node_ref > total_points:
                            raise ValueError(f"BAR2 connectivity references node {max_node_ref} but only {total_points} nodes exist")
                        
                        logger.info(f"  Well Block {blk_num}: '{well_name}' - {n_edges} BAR2 elements (shared nodes with mesh)")
                
                # ========== WELL NODE SETS (for GOLEM DiracKernels) ==========
                # CRITICAL FIX: Use mapped_indices to reference existing mesh nodes
                if export_wells_as_nodesets and num_well_nodesets > 0:
                    ns_status = rootgrp.createVariable('ns_status', 'i4', ('num_node_sets',))
                    ns_prop1 = rootgrp.createVariable('ns_prop1', 'i4', ('num_node_sets',))
                    ns_prop1.setncattr('name', 'ID')
                    ns_names = rootgrp.createVariable('ns_names', 'S1', ('num_node_sets', 'len_name'))
                    
                    for ns_idx, (well_marker, well_ns) in enumerate(well_node_sets.items()):
                        well_name = well_ns['name']
                        n_nodes = well_ns['n_nodes']
                        mapped_indices = well_ns['mapped_indices']  # 0-based mesh node indices
                        
                        ns_num = ns_idx + 1
                        ns_prop1[ns_idx] = int(well_marker)  # Node set ID
                        ns_status[ns_idx] = 1
                        self._write_exodus_string_v2(ns_names, ns_idx, well_name, 33)
                        
                        # Create dimension for this node set
                        rootgrp.createDimension(f'num_nod_ns{ns_num}', n_nodes)
                        
                        # Node list using MAPPED mesh node indices (1-based)
                        # Wells now reference existing mesh nodes - no duplicate points
                        node_ns = rootgrp.createVariable(f'node_ns{ns_num}', 'i4', (f'num_nod_ns{ns_num}',))
                        node_indices = mapped_indices + 1  # Convert 0-based to 1-based
                        node_ns[:] = node_indices
                        
                        # Validate node set references valid nodes
                        max_node_ref = np.max(node_indices)
                        if max_node_ref > total_points:
                            raise ValueError(f"Node set '{well_name}' references node {max_node_ref} but only {total_points} nodes exist")
                        
                        # Distribution factors (optional but good practice - all 1.0)
                        dist_fact_ns = rootgrp.createVariable(f'dist_fact_ns{ns_num}', 'f8', (f'num_nod_ns{ns_num}',))
                        dist_fact_ns[:] = np.ones(n_nodes, dtype=np.float64)
                        
                        logger.info(f"  Well Node Set {ns_num}: '{well_name}' - {n_nodes} nodes (shared with mesh, for DiracKernels)")

                # ========== SIDESETS ==========
                if num_side_sets > 0:
                    ss_status = rootgrp.createVariable('ss_status', 'i4', ('num_side_sets',))
                    ss_prop1 = rootgrp.createVariable('ss_prop1', 'i4', ('num_side_sets',))
                    ss_prop1.setncattr('name', 'ID')
                    ss_names = rootgrp.createVariable('ss_names', 'S1', ('num_side_sets', 'len_name'))
                    
                    for ss_idx, (surface_marker, sideset_data) in enumerate(sidesets.items()):
                        elem_list = sideset_data['elem_list']
                        side_list = sideset_data['side_list']
                        surface_name = sideset_data['name']
                        num_sides = len(elem_list)
                        
                        ss_num = ss_idx + 1
                        ss_prop1[ss_idx] = int(surface_marker)
                        ss_status[ss_idx] = 1
                        self._write_exodus_string_v2(ss_names, ss_idx, surface_name, 33)
                        
                        # Create dimension for sideset
                        rootgrp.createDimension(f'num_side_ss{ss_num}', num_sides)
                        
                        # Element and side lists
                        # CRITICAL: Map TetGen element indices to EXODUS global indices
                        elem_ss = rootgrp.createVariable(f'elem_ss{ss_num}', 'i4', (f'num_side_ss{ss_num}',))
                        side_ss = rootgrp.createVariable(f'side_ss{ss_num}', 'i4', (f'num_side_ss{ss_num}',))
                        
                        # Convert TetGen indices to EXODUS indices (then add 1 for 1-based)
                        exodus_elem_indices = tetgen_to_exodus_elem[np.array(elem_list)]
                        elem_ss[:] = exodus_elem_indices + 1  # 1-based
                        side_ss[:] = np.array(side_list, dtype=np.int32)
                        
                        logger.info(f"  Sideset {ss_num}: '{surface_name}' - {num_sides} faces")

                # ========== QA RECORDS ==========
                qa_records = rootgrp.createVariable('qa_records', 'S1', ('num_qa_rec', 'four', 'len_string'))
                import datetime
                self._write_exodus_string_v2(qa_records[0], 0, 'PyMeshIt', 33)
                self._write_exodus_string_v2(qa_records[0], 1, '1.0', 33)
                self._write_exodus_string_v2(qa_records[0], 2, datetime.datetime.now().strftime('%m/%d/%y'), 33)
                self._write_exodus_string_v2(qa_records[0], 3, datetime.datetime.now().strftime('%H:%M:%S'), 33)

                # ========== TIME VALUES (required for EXODUS II) ==========
                time_whole = rootgrp.createVariable('time_whole', 'f8', ('time_step',))
                time_whole[0] = 0.0  # Initial time step

            logger.info(f"✓ EXODUS II mesh exported: {file_path}")
            logger.info(f"  {n_tetrahedra} tetrahedra in {num_tetra_blk} blocks, {num_side_sets} sidesets")
            logger.info(f"  Total nodes: {total_points} (wells share existing mesh nodes)")
            if export_wells_as_nodesets and num_well_nodesets > 0:
                logger.info(f"  {total_well_nodes} well nodes in {num_well_nodesets} node sets (shared with mesh, for GOLEM DiracKernels)")
            elif num_well_blk > 0:
                logger.info(f"  {total_well_edges} well edges in {num_well_blk} BAR2 element blocks (shared nodes with mesh)")
            
            # Clean up custom names after successful export
            self._custom_block_names = {}
            self._custom_sideset_names = {}
            self._custom_well_names = {}
            self._well_export_type = "Node Sets"
            
            return True

        except Exception as e:
            logger.error(f"EXODUS export failed: {str(e)}", exc_info=True)
            # Clean up custom names on error too
            self._custom_block_names = {}
            self._custom_sideset_names = {}
            self._custom_well_names = {}
            self._well_export_type = "Node Sets"
            return False

    def _write_exodus_string_v2(self, var, idx, string, max_len):
        """Write a string to an EXODUS character variable with proper null-padding."""
        try:
            # Truncate and encode
            s = string[:max_len-1] if len(string) >= max_len else string
            encoded = s.encode('ascii')
            # Pad with null bytes
            padded = encoded + b'\x00' * (max_len - len(encoded))
            # Write character by character
            for i, c in enumerate(padded):
                var[idx, i] = bytes([c])
        except Exception as e:
            logger.warning(f"Failed to write EXODUS string '{string}': {e}")

    def _generate_block_name(self, material_id: int) -> str:
        """
        Generate a meaningful block name for GOLEM/MOOSE compatibility.
        
        GOLEM expects block names that combine the bounding surfaces:
        e.g., 'bottom_40m_granitoid_40m' for the domain between those surfaces.
        
        If custom block names were provided via _custom_block_names, use those instead.
        """
        # Check for custom block name first
        if hasattr(self, '_custom_block_names') and self._custom_block_names:
            if material_id in self._custom_block_names:
                return self._sanitize_surface_name(self._custom_block_names[material_id])
        
        # Try to get material name from materials list
        mat_name = self._get_material_name_by_id(material_id)
        
        # If we have surface information, try to build a descriptive name
        if hasattr(self, 'materials') and self.materials:
            for mat in self.materials:
                if mat.get('attribute') == material_id:
                    # Get associated surfaces for this material
                    mat_name = mat.get('name', f'material_{material_id}')
                    # Try to get bounding surface names
                    locations = mat.get('locations', [])
                    if locations and hasattr(self, 'datasets'):
                        # Find surfaces that bound this material
                        bounding_surfaces = self._find_bounding_surfaces_for_material(material_id)
                        if len(bounding_surfaces) >= 2:
                            # GOLEM style: lower_surface_upper_surface
                            names = [self._sanitize_surface_name(s) for s in bounding_surfaces[:2]]
                            return '_'.join(names)
                    break
        
        return self._sanitize_surface_name(mat_name)

    def _sanitize_surface_name(self, name: str) -> str:
        """Sanitize a surface/material name for EXODUS/GOLEM compatibility."""
        if not name:
            return "unnamed"
        # Replace spaces and special characters
        sanitized = name.replace(' ', '_').replace('-', '_').replace('.', '_')
        # Remove any non-alphanumeric characters except underscore
        sanitized = ''.join(c if c.isalnum() or c == '_' else '' for c in sanitized)
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = 'surface_' + sanitized
        return sanitized[:64] if sanitized else "unnamed"  # EXODUS name length limit

    def _find_bounding_surfaces_for_material(self, material_id: int) -> List[str]:
        """Find the surface names that bound a material region."""
        bounding_surfaces = []
        
        if not hasattr(self, 'datasets') or not self.datasets:
            return bounding_surfaces
        
        # Get material location
        mat_location = None
        if hasattr(self, 'materials') and self.materials:
            for mat in self.materials:
                if mat.get('attribute') == material_id:
                    locations = mat.get('locations', [])
                    if locations:
                        mat_location = np.array(locations[0])
                    break
        
        if mat_location is None:
            return bounding_surfaces
        
        # Find surfaces closest to this material location
        for s_idx in self.selected_surfaces:
            if s_idx < len(self.datasets):
                dataset = self.datasets[s_idx]
                surface_name = dataset.get('name', f'Surface_{s_idx}')
                # Add to bounding surfaces (simplified - could be improved with actual geometry)
                if dataset.get('type') in ['UNIT', 'BORDER']:
                    bounding_surfaces.append(surface_name)
        
        return bounding_surfaces[:2]  # Return at most 2 surfaces

    def _build_exodus_sidesets(self, mesh_data: pv.UnstructuredGrid, 
                               tetra_cells: np.ndarray, 
                               tetra_global_indices: List[int]) -> Dict:
        """
        Build sidesets from TetGen surface triangles following C++ MeshIt approach.
        
        In EXODUS, a sideset contains:
        - elem_list: Element (tetrahedron) indices
        - side_list: Side numbers (1-4 for tetrahedra)
        - name: Surface name for GOLEM boundary conditions
        
        C++ MeshIt approach:
        1. Use TetGen's trifaces and triface_markers directly (these are the refined boundary faces)
        2. Build a lookup from face vertex sets to tetrahedra
        3. Match boundary faces to tetrahedra to get elem_list and side_list
        """
        sidesets = {}
        
        # Get TetGen's surface triangles and markers - these are the REFINED boundary faces
        if not hasattr(self, 'tetgen_object') or self.tetgen_object is None:
            logger.warning("No TetGen object available for sideset generation")
            return sidesets
            
        try:
            tet = self.tetgen_object
            
            # Get TetGen output data directly
            trifaces = tet.trifaces if hasattr(tet, 'trifaces') else None
            triface_markers = tet.triface_markers if hasattr(tet, 'triface_markers') else None
            tetra_elements = tet.elem if hasattr(tet, 'elem') else None
            
            if trifaces is None or triface_markers is None or tetra_elements is None:
                logger.warning("TetGen output data not available for sideset generation")
                return sidesets
                
            if len(trifaces) == 0:
                logger.warning("No boundary faces in TetGen output")
                return sidesets
                
            logger.info(f"Building sidesets from {len(trifaces)} TetGen boundary faces")
            
            # Build lookup: frozenset of face nodes -> list of (tetra_idx, side_num)
            # Use TetGen's element array directly (0-based indexing)
            tetra_face_lookup = {}
            
            for tetra_idx, tetra_nodes in enumerate(tetra_elements):
                # TetGen tetrahedra have 4 nodes: c1, c2, c3, c4
                c1, c2, c3, c4 = tetra_nodes[0], tetra_nodes[1], tetra_nodes[2], tetra_nodes[3]
                
                # EXODUS side numbering (from C++ MeshIt exodus.cpp):
                # Side 1: face opposite to c3 (face contains c1, c2, c4)
                # Side 2: face opposite to c1 (face contains c2, c3, c4)
                # Side 3: face opposite to c2 (face contains c1, c3, c4)
                # Side 4: face opposite to c4 (face contains c1, c2, c3)
                faces = [
                    (frozenset([c1, c2, c4]), 1),  # opposite to c3
                    (frozenset([c2, c3, c4]), 2),  # opposite to c1
                    (frozenset([c1, c3, c4]), 3),  # opposite to c2
                    (frozenset([c1, c2, c3]), 4),  # opposite to c4
                ]
                
                for face_set, side_num in faces:
                    if face_set not in tetra_face_lookup:
                        tetra_face_lookup[face_set] = []
                    tetra_face_lookup[face_set].append((tetra_idx, side_num))
            
            # Get unique surface markers
            # With 1-based surface markers, marker 0 is truly internal/unmarked faces
            # So we can safely exclude it
            unique_markers = np.unique(triface_markers)
            unique_markers = unique_markers[unique_markers > 0]  # Exclude internal faces (marker 0)
            
            logger.info(f"Found {len(unique_markers)} unique surface markers: {list(unique_markers)}")
            
            # Process each surface marker
            matched_faces = 0
            unmatched_faces = 0
            
            for marker in unique_markers:
                marker_int = int(marker)
                surface_name = self._get_surface_name_by_marker(marker_int)
                
                # Find all triangles with this marker
                tri_indices = np.where(triface_markers == marker)[0]
                
                elem_list = []
                side_list = []
                
                for tri_idx in tri_indices:
                    tri_nodes = trifaces[tri_idx]
                    tri_set = frozenset(tri_nodes)
                    
                    # Find tetrahedron owning this face
                    if tri_set in tetra_face_lookup:
                        # For boundary faces, there should be exactly one tetrahedron
                        # Take the first (and usually only) match
                        tetra_idx, side_num = tetra_face_lookup[tri_set][0]
                        elem_list.append(tetra_idx)
                        side_list.append(side_num)
                        matched_faces += 1
                    else:
                        unmatched_faces += 1
                
                if elem_list:
                    sidesets[marker_int] = {
                        'elem_list': elem_list,
                        'side_list': side_list,
                        'name': surface_name
                    }
            
            logger.info(f"Sideset building: {matched_faces} faces matched, {unmatched_faces} unmatched")
            return sidesets
            
        except Exception as e:
            logger.error(f"Failed to build sidesets from TetGen: {e}", exc_info=True)
            return sidesets

    def _get_surface_name_by_marker(self, marker: int) -> str:
        """Get surface name from marker ID for sideset naming.
        
        If custom sideset names were provided via _custom_sideset_names, use those instead.
        """
        # Check for custom sideset name first
        if hasattr(self, '_custom_sideset_names') and self._custom_sideset_names:
            if marker in self._custom_sideset_names:
                return self._sanitize_surface_name(self._custom_sideset_names[marker])
        
        # Check if marker is a fault marker (>= 1000)
        if marker >= 1000:
            surface_idx = marker - 1000
        else:
            # Regular surface markers are 1-based (marker = s_idx + 1)
            # So surface_idx = marker - 1
            surface_idx = marker - 1
        
        # Try to get name from datasets
        if hasattr(self, 'datasets') and self.datasets:
            if 0 <= surface_idx < len(self.datasets):
                name = self.datasets[surface_idx].get('name', f'surface_{surface_idx}')
                return self._sanitize_surface_name(name)
        
        # Fallback name
        return f"surface_{marker}"

    def get_mesh_with_embedded_faults(self, mesh_data: Optional[pv.UnstructuredGrid] = None) -> Optional[pv.UnstructuredGrid]:
        """
        Get tetrahedral mesh with embedded fault surfaces (C++ MeshIt style).
        Combines volumetric tetrahedra AND fault surfaces into a single mesh.
        This is used for PZero export where faults appear as embedded constraint surfaces.
        
        Args:
            mesh_data: The volumetric tetrahedral mesh (optional, uses self.tetrahedral_mesh if not provided)
            
        Returns:
            Combined PyVista UnstructuredGrid with tetrahedra + fault triangles, or None on failure
        """
        if mesh_data is None:
            mesh_data = self.tetrahedral_mesh
        if mesh_data is None:
            logger.error("No tetrahedral mesh provided for embedded faults extraction")
            return None
            
        try:
            logger.info("Creating mesh with embedded fault surfaces (C++ MeshIt style)...")
            
            # Start with the volumetric tetrahedral mesh
            volume_mesh = mesh_data.copy()
            
            # Extract all fault surfaces from TetGen and merge with volume
            fault_surfaces_added = 0
            if hasattr(self, 'tetgen_object') and self.tetgen_object is not None:
                # Check BOTH materials lists (self.materials and tetra_materials)
                fault_materials = []
                
                # Check self.materials (from PLC generation)
                if hasattr(self, 'materials') and self.materials:
                    fault_materials.extend([m for m in self.materials if m.get('type') == 'FAULT'])
                
                # Check tetra_materials (from GUI, includes TetGen markers)
                if hasattr(self, 'tetra_materials') and self.tetra_materials:
                    tetra_faults = [m for m in self.tetra_materials if m.get('type') == 'FAULT']
                    # Add only if not already in fault_materials
                    for tf in tetra_faults:
                        if not any(f.get('attribute') == tf.get('attribute') for f in fault_materials):
                            fault_materials.append(tf)
                
                logger.info(f"Found {len(fault_materials)} fault materials for embedded faults")
                for fm in fault_materials:
                    logger.debug(f"  Fault: {fm.get('name')} (ID {fm.get('attribute')}, marker {fm.get('marker')})")
                
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
                    
                    return combined_mesh
                else:
                    logger.info("No fault surfaces found - returning volume mesh only")
                    return volume_mesh
            else:
                logger.warning("No TetGen object available - returning original mesh")
                return volume_mesh
                
        except Exception as e:
            logger.error(f"Failed to create mesh with embedded faults: {e}", exc_info=True)
            return mesh_data  # Return original mesh on failure

    def export_mesh(self, file_path: str, mesh_data: Optional[Dict] = None,
                    custom_block_names: Optional[Dict[int, str]] = None,
                    custom_sideset_names: Optional[Dict[int, str]] = None,
                    custom_well_names: Optional[Dict[int, str]] = None) -> bool:
        """
        Export tetrahedral mesh to various formats.
        
        Args:
            file_path: Output file path
            mesh_data: PyVista mesh data (uses self.tetrahedral_mesh if None)
            custom_block_names: Custom names for element blocks (3D domains)
            custom_sideset_names: Custom names for sidesets (boundary surfaces)
            custom_well_names: Custom names for well blocks (1D edge elements, C++ style)
        """
        if mesh_data is None: mesh_data = self.tetrahedral_mesh
        if not mesh_data:
            logger.error("No tetrahedral mesh to export")
            return False

        try:
            if isinstance(mesh_data, pv.UnstructuredGrid):
                # Check file extension to determine export format
                file_ext = file_path.lower().split('.')[-1]

                if file_ext in ['nc', 'nc4', 'cdf', 'exo']:
                    # Use NetCDF/EXODUS export with optional custom names
                    return self._export_netcdf(file_path, mesh_data, 
                                               custom_block_names=custom_block_names,
                                               custom_sideset_names=custom_sideset_names,
                                               custom_well_names=custom_well_names)
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
                # Check BOTH materials lists (self.materials and tetra_materials)
                fault_materials = []
                
                # Check self.materials (from PLC generation)
                if hasattr(self, 'materials') and self.materials:
                    fault_materials.extend([m for m in self.materials if m.get('type') == 'FAULT'])
                
                # Check tetra_materials (from GUI, includes TetGen markers)
                if hasattr(self, 'tetra_materials') and self.tetra_materials:
                    tetra_faults = [m for m in self.tetra_materials if m.get('type') == 'FAULT']
                    # Add only if not already in fault_materials
                    for tf in tetra_faults:
                        if not any(f.get('attribute') == tf.get('attribute') for f in fault_materials):
                            fault_materials.append(tf)
                
                logger.info(f"Found {len(fault_materials)} fault materials for export")
                for fm in fault_materials:
                    logger.debug(f"  Fault: {fm.get('name')} (ID {fm.get('attribute')}, marker {fm.get('marker')})")
                
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
            
            # =========================================================================
            # ADD 1D WELL MATERIALS (C++ MeshIt: edgemarkerlist / edgelist)
            # Wells are added as VTK_LINE cells (type 3) following C++ ExportVTU3D
            # CRITICAL FIX: Wells now share nodes with the tetra mesh - no duplicate points
            # =========================================================================
            well_edges_added = 0
            if hasattr(self, 'well_data') and self.well_data:
                logger.info(f"Processing {len(self.well_data)} wells for 1D material export (using shared mesh nodes)...")
                
                all_well_cells = []
                all_well_material_ids = []
                
                mesh_points = volume_mesh.points  # Existing mesh points
                
                for well_idx, well_info in self.well_data.items():
                    well_marker = well_info.get('marker', well_idx + 2)
                    well_name = well_info.get('name', f'Well_{well_idx}')
                    well_edges = well_info.get('edges', [])

                    # Build unique points and edge index pairs from the edges list.
                    # This correctly handles non-contiguous segments and avoids
                    # treating the flat 'points' list as a single polyline.
                    def _extract_coord(p):
                        if hasattr(p, 'x'):
                            return (float(p.x), float(p.y), float(p.z))
                        return (float(p[0]), float(p[1]), float(p[2]))

                    if well_edges:
                        unique_pts = []
                        key_to_local = {}
                        edge_pairs = []
                        for edge_pts in well_edges:
                            if len(edge_pts) < 2:
                                continue
                            local_idxs = []
                            for p in (edge_pts[0], edge_pts[1]):
                                c = _extract_coord(p)
                                key = (round(c[0], 9), round(c[1], 9), round(c[2], 9))
                                if key not in key_to_local:
                                    key_to_local[key] = len(unique_pts)
                                    unique_pts.append(list(c))
                                local_idxs.append(key_to_local[key])
                            if local_idxs[0] != local_idxs[1]:
                                edge_pairs.append((local_idxs[0], local_idxs[1]))
                    else:
                        well_pts = well_info.get('points')
                        if well_pts is None or len(well_pts) < 2:
                            continue
                        unique_pts = []
                        for p in well_pts:
                            unique_pts.append(list(_extract_coord(p)))
                        edge_pairs = [(i, i + 1) for i in range(len(unique_pts) - 1)]

                    if len(unique_pts) < 2 or not edge_pairs:
                        continue

                    pts_arr = np.array(unique_pts, dtype=np.float64)

                    try:
                        mapped_indices = map_well_points_to_mesh_nodes(
                            mesh_points, pts_arr, tolerance=1e-5, precision=9
                        )
                        logger.info(f"  Well '{well_name}': mapped {len(pts_arr)} unique points to mesh nodes")
                    except ValueError as e:
                        logger.error(f"  Well '{well_name}' mapping failed: {e}")
                        raise

                    max_node_idx = np.max(mapped_indices)
                    if max_node_idx >= volume_mesh.n_points:
                        raise ValueError(
                            f"Well '{well_name}' mapped to node {max_node_idx} "
                            f"but mesh only has {volume_mesh.n_points} nodes"
                        )

                    edge_cells = []
                    for a, b in edge_pairs:
                        edge_cells.extend([2, mapped_indices[a], mapped_indices[b]])
                    n_edges = len(edge_pairs)

                    all_well_cells.append(np.array(edge_cells, dtype=np.int64))
                    all_well_material_ids.append(np.full(n_edges, well_marker, dtype=np.int32))

                    well_edges_added += n_edges
                    logger.info(f"  Added well '{well_name}' (marker {well_marker}): {n_edges} edges (shared nodes with mesh)")
                
                # Merge well cells with volume mesh (NO new points added)
                if well_edges_added > 0:
                    logger.info(f"Merging {well_edges_added} well edges with mesh (sharing existing nodes)...")
                    
                    # Get current mesh data - points stay the same!
                    current_points = volume_mesh.points
                    current_cells = volume_mesh.cells
                    current_cell_types = volume_mesh.celltypes
                    
                    if 'MaterialID' in volume_mesh.cell_data:
                        current_material_ids = volume_mesh.cell_data['MaterialID']
                    else:
                        current_material_ids = np.zeros(volume_mesh.n_cells, dtype=np.int32)
                    
                    # Combine cells only - points are NOT modified (wells use existing nodes)
                    final_points = current_points  # NO vstack - same points
                    final_cells = np.hstack([current_cells] + all_well_cells)
                    final_cell_types = np.hstack([current_cell_types] + 
                                                  [np.full(len(ids), 3, dtype=np.uint8) for ids in all_well_material_ids])  # VTK_LINE = 3
                    final_material_ids = np.hstack([current_material_ids] + all_well_material_ids)
                    
                    # Create new combined mesh with SAME point count
                    combined_with_wells = pv.UnstructuredGrid(final_cells, final_cell_types, final_points)
                    combined_with_wells.cell_data['MaterialID'] = final_material_ids
                    
                    # Update CellType array: 0=Tetrahedra, 1=Triangle(Fault), 2=Line(Well)
                    cell_type_names = np.where(
                        final_cell_types == 10, 0,  # Tetrahedra
                        np.where(final_cell_types == 5, 1,  # Triangle (Fault)
                                 2)  # Line (Well)
                    )
                    combined_with_wells.cell_data['CellType'] = cell_type_names
                    
                    volume_mesh = combined_with_wells
                    logger.info(f"✓ Added {well_edges_added} well edges (1D materials) to mesh - n_points unchanged: {volume_mesh.n_points}")
            
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
            elif file_ext == 'stl':
                # STL: Export each PLC surface/fault as separate STL files
                return self._export_surfaces_as_separate_stl(file_path)
            elif file_ext in ['obj', 'ply']:
                # OBJ and PLY: Export each PLC surface/fault as separate files
                return self._export_surfaces_as_separate_files(file_path, file_ext)
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
                file_ext = file_path.lower().split('.')[-1]
                if file_ext in ['stl', 'obj', 'ply']:
                    # Try separate surface export first
                    if self.surface_data:
                        return self._export_surfaces_as_separate_files(file_path, file_ext)
                    else:
                        # No surface data available, extract from volume mesh
                        surface_mesh = mesh_data.extract_surface().triangulate()
                        surface_mesh.save(file_path)
                        logger.warning(f"Fell back to volume surface extraction for {file_ext.upper()} format")
                else:
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
