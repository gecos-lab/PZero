"""
MeshIt Intersection Utilities

This module provides functionality for computing intersections between 
surfaces and polylines, following the MeshIt workflow.
"""

import numpy as np
import concurrent.futures
from typing import List, Dict, Tuple, Optional, Union, Any
import math # Ensure math is imported for floor
import logging
# Try to import triangle with fallback
try:
    import triangle as tr_standard
    HAVE_TRIANGLE = True
except ImportError:
    print("WARNING: triangle package not available, some functionality will be limited")
    HAVE_TRIANGLE = False
    tr_standard = None
from dataclasses import dataclass, field
try:
    from Pymeshit.triangle_direct import DirectTriangleWrapper
    HAVE_DIRECT_WRAPPER_INTERSECTION_UTILS = True
except ImportError:
    HAVE_DIRECT_WRAPPER_INTERSECTION_UTILS = False
    print("WARNING (intersection_utils): DirectTriangleWrapper not found. Constrained triangulation might be limited.")
    # tr_standard is already imported above
# Attempt to import PyVista for an alternative triangulation method
try:
    import pyvista as pv
    HAVE_PYVISTA_UTILS = True
    logging.info("PyVista imported successfully in intersection_utils.")
except ImportError:
    HAVE_PYVISTA_UTILS = False
    logging.warning("PyVista not available in intersection_utils. PyVista triangulation fallback disabled.")

logger = logging.getLogger("MeshIt-Workflow")

class Vector3D:
    """Simple 3D vector class compatible with MeshIt's Vector3D"""
    
    def __init__(self, x=0.0, y=0.0, z=0.0, point_type=None):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.type = "DEFAULT" 
        self.type = point_type  # Store type information # Point type: DEFAULT, CORNER, INTERSECTION_POINT, TRIPLE_POINT, COMMON_INTERSECTION_CONVEXHULL_POINT
    
    # Add property for compatibility with MeshIt's Vector3D
    @property
    def type(self):
        return self.point_type
    
    @type.setter
    def type(self, value):
        self.point_type = value

    def __add__(self, other):
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)
    
    def __sub__(self, other):
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)
    
    def __mul__(self, scalar):
        return Vector3D(self.x * scalar, self.y * scalar, self.z * scalar)
    
    def __truediv__(self, scalar):
        return Vector3D(self.x / scalar, self.y / scalar, self.z / scalar)
    
    def dot(self, other):
        return self.x * other.x + self.y * other.y + self.z * other.z
    
    def cross(self, other):
        return Vector3D(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x
        )
    
    def length(self):
        return np.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)
    
    def length_squared(self):
        """Return the squared length of the vector (avoids sqrt operation)"""
        return self.x * self.x + self.y * self.y + self.z * self.z
    
    def normalized(self):
        length = self.length()
        if length < 1e-10:
            return Vector3D(0, 0, 0)
        return Vector3D(self.x / length, self.y / length, self.z / length)
    
    def to_numpy(self):
        return np.array([self.x, self.y, self.z])
    
    @staticmethod
    def from_numpy(array):
        return Vector3D(array[0], array[1], array[2])
    
    def __repr__(self):
        return f"Vector3D({self.x}, {self.y}, {self.z}, {self.type})"


class Intersection:
    """Represents an intersection between two objects (surfaces or polylines)"""
    
    def __init__(self, id1: int, id2: int, is_polyline_mesh: bool = False):
        self.id1 = id1
        self.id2 = id2
        self.is_polyline_mesh = is_polyline_mesh
        self.points: List[Vector3D] = []
    
    def add_point(self, point: Vector3D):
        """Add intersection point"""
        self.points.append(point)
    
    def __repr__(self):
        return f"Intersection(id1={self.id1}, id2={self.id2}, points={len(self.points)})"


class TriplePoint:
    """Represents a triple point where three or more intersections meet"""
    
    def __init__(self, point: Vector3D):
        self.point = point
        self.intersection_ids: List[int] = []
    
    def add_intersection(self, intersection_id: int):
        """Associate intersection with this triple point"""
        if intersection_id not in self.intersection_ids:
            self.intersection_ids.append(intersection_id)
    
    def __repr__(self):
        return f"TriplePoint(point={self.point}, intersections={len(self.intersection_ids)})"


class Triangle:
    """Triangle in 3D space"""
    
    def __init__(self, v1: Vector3D, v2: Vector3D, v3: Vector3D):
        self.v1 = v1
        self.v2 = v2
        self.v3 = v3
    
    def normal(self) -> Vector3D:
        """Calculate the normal vector of the triangle"""
        edge1 = self.v2 - self.v1
        edge2 = self.v3 - self.v1
        return edge1.cross(edge2).normalized()
    
    def centroid(self) -> Vector3D:
        """Calculate the centroid of the triangle"""
        return (self.v1 + self.v2 + self.v3) * (1.0/3.0)
    
    def contains_point(self, point: Vector3D) -> bool:
        """Check if the point lies within the triangle (approximate)"""
        # Barycentric coordinate approach
        v0 = self.v2 - self.v1
        v1 = self.v3 - self.v1
        v2 = point - self.v1
        
        d00 = v0.dot(v0)
        d01 = v0.dot(v1)
        d11 = v1.dot(v1)
        d20 = v2.dot(v0)
        d21 = v2.dot(v1)
        
        denom = d00 * d11 - d01 * d01
        if abs(denom) < 1e-10:
            return False
        
        v = (d11 * d20 - d01 * d21) / denom
        w = (d00 * d21 - d01 * d20) / denom
        u = 1.0 - v - w
        
        # Point is in triangle if u, v, w are all between 0 and 1
        return (u >= -1e-5) and (v >= -1e-5) and (w >= -1e-5) and (u + v + w <= 1.0 + 1e-5)


class Box:
    """Spatial subdivision box for efficient intersection calculations"""
    
    def __init__(self):
        self.min = Vector3D()
        self.max = Vector3D()
        self.center = Vector3D()
        self.T1s = []  # Triangles from surface 1
        self.T2s = []  # Triangles from surface 2
        self.N1s = []  # Segments from intersection 1
        self.N2s = []  # Segments from intersection 2
        self.Box = [None] * 8  # Subboxes for octree subdivision
    
    def calculate_center(self):
        """Calculate the center of the box"""
        self.center = (self.min + self.max) * 0.5
    
    def generate_subboxes(self):
        """Create 8 child boxes (octree subdivision)"""
        self.calculate_center()
        
        # Create 8 subboxes spanning the octants, octant means the 8 subboxes of the box
        for i in range(8):
            self.Box[i] = Box()
            
            # Set min coordinates based on octant
            self.Box[i].min.x = self.min.x if (i & 1) == 0 else self.center.x # if i is 0 or 1, set min.x to min.x, otherwise set it to center.x
            self.Box[i].min.y = self.min.y if (i & 2) == 0 else self.center.y # if i is 0 or 2, set min.y to min.y, otherwise set it to center.y
            self.Box[i].min.z = self.min.z if (i & 4) == 0 else self.center.z # if i is 0 or 4, set min.z to min.z, otherwise set it to center.z
            
            # Set max coordinates based on octant
            self.Box[i].max.x = self.center.x if (i & 1) == 0 else self.max.x # if i is 0 or 1, set max.x to center.x, otherwise set it to max.x
            self.Box[i].max.y = self.center.y if (i & 2) == 0 else self.max.y # if i is 0 or 2, set max.y to center.y, otherwise set it to max.y
            self.Box[i].max.z = self.center.z if (i & 4) == 0 else self.max.z # if i is 0 or 4, set max.z to center.z, otherwise set it to max.z
    
    def tri_in_box(self, triangle):
        """
        Check if a triangle intersects this box using C++ MeshIt logic.
        Returns False only if ALL vertices are on the same side of any box boundary.
        """
        # Check X axis - return False only if ALL vertices are on same side
        if ((triangle.v1.x < self.min.x) and (triangle.v2.x < self.min.x) and (triangle.v3.x < self.min.x)):
            return False
        if ((triangle.v1.x > self.max.x) and (triangle.v2.x > self.max.x) and (triangle.v3.x > self.max.x)):
            return False
            
        # Check Y axis - return False only if ALL vertices are on same side  
        if ((triangle.v1.y < self.min.y) and (triangle.v2.y < self.min.y) and (triangle.v3.y < self.min.y)):
            return False
        if ((triangle.v1.y > self.max.y) and (triangle.v2.y > self.max.y) and (triangle.v3.y > self.max.y)):
            return False
            
        # Check Z axis - return False only if ALL vertices are on same side
        if ((triangle.v1.z < self.min.z) and (triangle.v2.z < self.min.z) and (triangle.v3.z < self.min.z)):
            return False
        if ((triangle.v1.z > self.max.z) and (triangle.v2.z > self.max.z) and (triangle.v3.z > self.max.z)):
            return False
            
        # If not all vertices are on the same side of any boundary, triangle intersects box
        return True
    
    def seg_in_box(self, v1, v2):
        """Check if a line segment intersects this box"""
        # Simple AABB-segment overlap test
        # First check if either endpoint is inside the box
        for vertex in [v1, v2]:
            if (self.min.x <= vertex.x <= self.max.x and
                self.min.y <= vertex.y <= self.max.y and
                self.min.z <= vertex.z <= self.max.z):
                return True
        
        # TODO: Implement more sophisticated AABB-segment intersection test
        # For simplicity, we'll use a conservative test checking if segment's bounding box
        # overlaps with our box
        seg_min = Vector3D(
            min(v1.x, v2.x),
            min(v1.y, v2.y),
            min(v1.z, v2.z)
        )
        seg_max = Vector3D(
            max(v1.x, v2.x),
            max(v1.y, v2.y),
            max(v1.z, v2.z)
        )
        
        # Check if bounding boxes overlap
        return not (seg_max.x < self.min.x or seg_min.x > self.max.x or
                    seg_max.y < self.min.y or seg_min.y > self.max.y or
                    seg_max.z < self.min.z or seg_min.z > self.max.z)
    
    def too_much_tri(self):
        """Check if this box contains too many triangles for direct testing"""
        # Match C++ MeshIt threshold of 48 triangles per surface
        return len(self.T1s) > 48 or len(self.T2s) > 48
    
    def too_much_seg(self):
        """Check if this box contains too many segments for direct testing"""
        # Match C++ MeshIt threshold of 48 segments per surface
        return len(self.N1s) > 48 or len(self.N2s) > 48
    
    def split_tri(self, int_segments):
        """
        Recursively subdivide box and test triangle intersections.
        
        This implements the spatial subdivision approach of the C++ version.
        
        Args:
            int_segments: A collection to store intersection segments
        """
        self.generate_subboxes()
        
        # Place triangles in appropriate subboxes
        for tri1 in self.T1s:
            for b in range(8):
                if self.Box[b].tri_in_box(tri1):
                    self.Box[b].T1s.append(tri1)
        
        for tri2 in self.T2s:
            for b in range(8):
                if self.Box[b].tri_in_box(tri2):
                    self.Box[b].T2s.append(tri2)
        
        # Process each subbox
        for b in range(8):
            # Only process if both lists have triangles
            if self.Box[b].T1s and self.Box[b].T2s:
                if self.Box[b].too_much_tri():
                    # Further subdivide this box
                    self.Box[b].split_tri(int_segments)
                else:
                    # Perform direct triangle-triangle tests
                    for tri1 in self.Box[b].T1s:
                        for tri2 in self.Box[b].T2s:
                            # Use the optimized triangle-triangle intersection test
                            isectpt1, isectpt2 = tri_tri_intersect_with_isectline(tri1, tri2)
                            if isectpt1 and isectpt2:
                                # Avoid duplicate segments
                                append_non_existing_segment(int_segments, isectpt1, isectpt2)
    
    def split_seg(self, triple_points, i1, i2):
        """
        Recursively subdivide box and test segment intersections for triple points.
        
        This implements the spatial subdivision approach of the C++ version.
        
        Args:
            triple_points: Collection to store triple points
            i1: Index of first intersection
            i2: Index of second intersection
        """
        self.generate_subboxes()
        
        # Place segments in appropriate subboxes
        for seg1 in self.N1s:
            for b in range(8):
                if self.Box[b].seg_in_box(seg1[0], seg1[1]):
                    self.Box[b].N1s.append(seg1)
        
        for seg2 in self.N2s:
            for b in range(8):
                if self.Box[b].seg_in_box(seg2[0], seg2[1]):
                    self.Box[b].N2s.append(seg2)
        
        # Process each subbox
        for b in range(8):
            # Only process if both lists have segments
            if self.Box[b].N1s and self.Box[b].N2s:
                if self.Box[b].too_much_seg():
                    # Further subdivide this box
                    self.Box[b].split_seg(triple_points, i1, i2)
                else:
                    # Perform direct segment-segment tests
                    tolerance = 1e-5 # Use the same default tolerance
                    for seg1 in self.Box[b].N1s:
                        p1a, p1b = seg1[0], seg1[1]
                        for seg2 in self.Box[b].N2s:
                            p2a, p2b = seg2[0], seg2[1]

                            # Calculate distance and closest points between segments FIRST
                            dist, closest1, closest2 = segment_segment_distance(p1a, p1b, p2a, p2b)

                            # Check if distance is within tolerance
                            if dist < tolerance:
                                # Calculate triple point as the midpoint
                                tp_point = (closest1 + closest2) * 0.5
                                # Just append the raw point coordinate to the list passed by reference
                                triple_points.append(tp_point)

                                # --- REMOVED duplicate check and TriplePoint object creation ---
                                # # Check for duplicates within the accumulating list
                                # is_duplicate = False
                                # for existing_tp in triple_points:
                                #     # This check is problematic here, should be done after collecting all points
                                #     # if (existing_tp.point - tp_point).length() < tolerance:
                                #     #     # Merge intersection IDs into the existing TP
                                #     #     existing_tp.add_intersection(i1)
                                #     #     existing_tp.add_intersection(i2)
                                #     #     is_duplicate = True
                                #     #     break
                                #
                                # if not is_duplicate:
                                #     # Create a new TriplePoint object
                                #     # This creation should happen after merging
                                #     # triple_point_obj = TriplePoint(tp_point)
                                #     # triple_point_obj.add_intersection(i1)
                                #     # triple_point_obj.add_intersection(i2)
                                #     # found_triple_points.append(triple_point_obj)
                                # --- END REMOVAL ---


def append_non_existing_segment(segments, p1, p2):
    """
    Add a segment to the collection if it doesn't already exist.
    
    Args:
        segments: Collection of segments
        p1: First endpoint
        p2: Second endpoint
    """
    # Check if segment already exists
    for existing_segment in segments:
        # Check if either (p1,p2) or (p2,p1) already exists
        if (((existing_segment[0] - p1).length() < 1e-8 and 
             (existing_segment[1] - p2).length() < 1e-8) or
            ((existing_segment[0] - p2).length() < 1e-8 and 
             (existing_segment[1] - p1).length() < 1e-8)):
            return  # Segment already exists
    
    # Add new segment
    segments.append((p1, p2))


# ####################################################################
# START OF MODIFIED SECTION 1: tri_tri_intersect_with_isectline
# ####################################################################
def tri_tri_intersect_with_isectline(tri1, tri2):
    """
    Fast triangle-triangle intersection test matching C++ MeshIt implementation.
    
    Based on Tomas Möller's algorithm with proper epsilon handling.
    
    Args:
        tri1: First triangle
        tri2: Second triangle
        
    Returns:
        Tuple of (point1, point2) defining the intersection line, or (None, None) if no intersection
    """
    # C++ MeshIt constants - use adaptive epsilon for curved surfaces
    # Start with tighter epsilon and adjust based on triangle size
    base_epsilon = 1e-14
    
    # Calculate triangle sizes to adapt epsilon
    tri1_size = max((tri1.v2 - tri1.v1).length(), (tri1.v3 - tri1.v1).length(), (tri1.v3 - tri1.v2).length())
    tri2_size = max((tri2.v2 - tri2.v1).length(), (tri2.v3 - tri2.v1).length(), (tri2.v3 - tri2.v2).length())
    avg_tri_size = (tri1_size + tri2_size) * 0.5
    
    # Adaptive epsilon based on triangle size (helps with curved surfaces)
    EPSILON = max(base_epsilon, avg_tri_size * 1e-12)
    
    # 1. Compute plane equation (p1) of triangle T1=(V0,V1,V2)
    # p1: N1.X+d1=0
    E1 = tri1.v2 - tri1.v1
    E2 = tri1.v3 - tri1.v1
    N1 = E1.cross(E2)
    d1 = -N1.dot(tri1.v1)
    
    # 2.a Compute signed distance of triangle T2=(U0,U1,U2) to plane p1
    du0 = N1.dot(tri2.v1) + d1
    du1 = N1.dot(tri2.v2) + d1
    du2 = N1.dot(tri2.v3) + d1
    
    # 2.b Coplanarity robustness check (USE_EPSILON_TEST)
    if abs(du0) < EPSILON:
        du0 = 0.0
    if abs(du1) < EPSILON:
        du1 = 0.0  
    if abs(du2) < EPSILON:
        du2 = 0.0
    
    du0du1 = du0 * du1
    du0du2 = du0 * du2
    
    # If all points of T2 are on same side of p1, no intersection
    if du0du1 > 0.0 and du0du2 > 0.0:
        return None, None
    
    # 3. Compute plane equation (p2) of triangle T2=(U0,U1,U2)
    # p2: N2.X+d2=0
    E1 = tri2.v2 - tri2.v1
    E2 = tri2.v3 - tri2.v1
    N2 = E1.cross(E2)
    d2 = -N2.dot(tri2.v1)
    
    # 4.a Compute signed distance of triangle T1=(V0,V1,V2) to plane p2
    dv0 = N2.dot(tri1.v1) + d2
    dv1 = N2.dot(tri1.v2) + d2
    dv2 = N2.dot(tri1.v3) + d2
    
    # 4.b Coplanarity robustness check (USE_EPSILON_TEST)
    if abs(dv0) < EPSILON:
        dv0 = 0.0
    if abs(dv1) < EPSILON:
        dv1 = 0.0
    if abs(dv2) < EPSILON:
        dv2 = 0.0
    
    dv0dv1 = dv0 * dv1
    dv0dv2 = dv0 * dv2
    
    # If all points of T1 are on same side of p2, no intersection
    if dv0dv1 > 0.0 and dv0dv2 > 0.0:
        return None, None
    
    # 5. Compute direction of intersection line
    D = N1.cross(N2)
    
    # 6. Project triangles onto largest coordinate of D
    max_axis = 0
    max_val = abs(D.x)
    if abs(D.y) > max_val:
        max_axis = 1
        max_val = abs(D.y)
    if abs(D.z) > max_val:
        max_axis = 2
    
    # Project vertices onto the chosen axis
    if max_axis == 0:  # X axis is largest
        vv0 = tri1.v1.x
        vv1 = tri1.v2.x
        vv2 = tri1.v3.x
        uu0 = tri2.v1.x
        uu1 = tri2.v2.x
        uu2 = tri2.v3.x
    elif max_axis == 1:  # Y axis is largest
        vv0 = tri1.v1.y
        vv1 = tri1.v2.y
        vv2 = tri1.v3.y
        uu0 = tri2.v1.y
        uu1 = tri2.v2.y
        uu2 = tri2.v3.y
    else:  # Z axis is largest
        vv0 = tri1.v1.z
        vv1 = tri1.v2.z
        vv2 = tri1.v3.z
        uu0 = tri2.v1.z
        uu1 = tri2.v2.z
        uu2 = tri2.v3.z
    
    # 7. Compute intervals for triangle 1
    isect1 = [0.0, 0.0]
    isectpoint1 = [Vector3D(), Vector3D()]
    compute_intervals_isectline(tri1, vv0, vv1, vv2, dv0, dv1, dv2, dv0dv1, dv0dv2, isect1, isectpoint1)
    
    # 8. Compute intervals for triangle 2
    isect2 = [0.0, 0.0]
    isectpoint2 = [Vector3D(), Vector3D()]
    compute_intervals_isectline(tri2, uu0, uu1, uu2, du0, du1, du2, du0du1, du0du2, isect2, isectpoint2)
    
    # 9. Sort intervals so that isect1[0] <= isect1[1] and isect2[0] <= isect2[1]
    if isect1[0] > isect1[1]:
        isect1[0], isect1[1] = isect1[1], isect1[0]
        isectpoint1[0], isectpoint1[1] = isectpoint1[1], isectpoint1[0]
    
    if isect2[0] > isect2[1]:
        isect2[0], isect2[1] = isect2[1], isect2[0]
        isectpoint2[0], isectpoint2[1] = isectpoint2[1], isectpoint2[0]
    
    # 10. Check for overlap
    if isect1[1] < isect2[0] or isect2[1] < isect1[0]:
        return None, None  # No overlap
    
    # 11. Compute actual intersection points
    if isect2[0] < isect1[0]:
        if isect1[0] < isect2[1]:
            if isect1[1] < isect2[1]:
                pt1 = isectpoint1[0]
                pt2 = isectpoint1[1]
            else:
                pt1 = isectpoint1[0]
                pt2 = isectpoint2[1]
        else:
            return None, None
    else:
        if isect2[0] < isect1[1]:
            if isect2[1] < isect1[1]:
                pt1 = isectpoint2[0]
                pt2 = isectpoint2[1]
            else:
                pt1 = isectpoint2[0]
                pt2 = isectpoint1[1]
        else:
            return None, None
    
    # Set intersection point types
    pt1.type = "INTERSECTION_POINT"
    pt2.type = "INTERSECTION_POINT"
    
    return pt1, pt2
# ##################################################################
# END OF MODIFIED SECTION 1
# ##################################################################


def compute_intervals_isectline(tri, vv0, vv1, vv2, d0, d1, d2, d0d1, d0d2, isect, isectpoint):
    """
    Helper function to compute intersection intervals for triangle-triangle intersection.
    """
    if d0d1 > 0.0:
        # d0, d1 are on the same side, d2 on the other side
        isect2(tri.v3, tri.v1, tri.v2, vv2, vv0, vv1, d2, d0, d1, isect, isectpoint)
    elif d0d2 > 0.0:
        # d0, d2 are on the same side, d1 on the other side
        isect2(tri.v2, tri.v1, tri.v3, vv1, vv0, vv2, d1, d0, d2, isect, isectpoint)
    elif d1 * d2 > 0.0 or d0 != 0.0:
        # d1, d2 are on the same side, d0 on the other side
        isect2(tri.v1, tri.v2, tri.v3, vv0, vv1, vv2, d0, d1, d2, isect, isectpoint)
    elif d1 != 0.0:
        isect2(tri.v2, tri.v1, tri.v3, vv1, vv0, vv2, d1, d0, d2, isect, isectpoint)
    elif d2 != 0.0:
        isect2(tri.v3, tri.v1, tri.v2, vv2, vv0, vv1, d2, d0, d1, isect, isectpoint)
    else:
        # Triangles are coplanar
        return 1
    return 0


def isect2(v0, v1, v2, vv0, vv1, vv2, d0, d1, d2, isect, isectpoint):
    """
    Helper function for computing intersection points on triangle edges.
    """
    tmp = d0 / (d0 - d1)
    isect[0] = vv0 + (vv1 - vv0) * tmp
    diff = v1 - v0
    isectpoint[0] = v0 + diff * tmp
    
    tmp = d0 / (d0 - d2)
    isect[1] = vv0 + (vv2 - vv0) * tmp
    diff = v2 - v0
    isectpoint[1] = v0 + diff * tmp


def triangle_triangle_intersection(tri1: Triangle, tri2: Triangle) -> List[Vector3D]:
    """
    C++-like tri-tri intersection:
    - No near-parallel prefilter
    - Coplanar overlap handled via 2D projection and polygon-overlap sampling
    - Only drop true slivers
    """
    import numpy as np

    n1 = tri1.normal(); n2 = tri2.normal()
    l1 = n1.length(); l2 = n2.length()
    if l1 < 1e-14 or l2 < 1e-14:
        return []

    n1u = n1 * (1.0 / l1); n2u = n2 * (1.0 / l2)
    align = abs(n1u.dot(n2u))

    # Characteristic scale for tolerances
    edges = [
        (tri1.v2 - tri1.v1).length(),
        (tri1.v3 - tri1.v1).length(),
        (tri1.v3 - tri1.v2).length(),
        (tri2.v2 - tri2.v1).length(),
        (tri2.v3 - tri2.v1).length(),
        (tri2.v3 - tri2.v2).length(),
    ]
    L = max(edges) if edges else 1.0
    sliver_tol = 1e-12
    plane_tol = 1e-8 * L + 1e-12
    if align > 0.95:
        # Calculate minimum distance between triangle planes
        plane_dist1 = abs(n1u.dot(tri2.v1 - tri1.v1))
        plane_dist2 = abs(n1u.dot(tri2.v2 - tri1.v1)) 
        plane_dist3 = abs(n1u.dot(tri2.v3 - tri1.v1))
        min_plane_dist = min(plane_dist1, plane_dist2, plane_dist3)
        
        # If surfaces are parallel and separated by more than a small multiple of characteristic length,
        # reject intersection to prevent ghost lines
        separation_threshold = max(L * 1e-6, 1e-10)  # Adaptive threshold based on triangle size
        if min_plane_dist > separation_threshold:
            return []

    def as_np(p: Vector3D):
        return np.array([p.x, p.y, p.z], dtype=float)

    # Coplanar handling
    # If near-parallel normals and plane-to-vertex distances are tiny both ways,
    # treat as coplanar and compute overlap segment in-plane.
    if align > 0.999999:
        p0 = as_np(tri1.v1)
        n = as_np(n1u)
        def min_sep_to_plane(nu, p0, a, b, c):
            return min(abs(nu.dot(as_np(a) - p0)),
                       abs(nu.dot(as_np(b) - p0)),
                       abs(nu.dot(as_np(c) - p0)))
        if min_sep_to_plane(n, p0, tri2.v1, tri2.v2, tri2.v3) <= plane_tol and \
           min_sep_to_plane(as_np(n2u), as_np(tri2.v1), tri1.v1, tri1.v2, tri1.v3) <= plane_tol:
            # Build an orthonormal in-plane basis (u,v,n)
            a = as_np(tri1.v2) - p0
            if np.linalg.norm(a) < 1e-14:
                a = as_np(tri1.v3) - p0
            if np.linalg.norm(a) < 1e-14:
                a = np.array([1.0, 0.0, 0.0])
            u = a / np.linalg.norm(a)
            v = np.cross(n, u)
            v_norm = np.linalg.norm(v)
            if v_norm < 1e-14:
                # pick any orthogonal to n
                tmp = np.array([1.0, 0.0, 0.0])
                if abs(n.dot(tmp)) > 0.9:
                    tmp = np.array([0.0, 1.0, 0.0])
                u = np.cross(tmp, n); u /= np.linalg.norm(u)
                v = np.cross(n, u); v /= np.linalg.norm(v)
            else:
                v /= v_norm

            def proj2(p):
                w = as_np(p) - p0
                return np.array([u.dot(w), v.dot(w)], dtype=float)

            t1 = [proj2(tri1.v1), proj2(tri1.v2), proj2(tri1.v3)]
            t2 = [proj2(tri2.v1), proj2(tri2.v2), proj2(tri2.v3)]

            # Collect overlap polygon samples: vertices inside the other + edge-edge 2D intersections
            def inside(pt, tri):
                # barycentric test in 2D
                A, B, C = tri
                v0 = C - A; v1 = B - A; v2 = pt - A
                den = v0[0]*v1[1] - v1[0]*v0[1]
                if abs(den) < 1e-16:
                    return False
                a = (v2[0]*v1[1] - v1[0]*v2[1]) / den
                b = (v0[0]*v2[1] - v2[0]*v0[1]) / den
                c = 1.0 - a - b
                return a >= -1e-12 and b >= -1e-12 and c >= -1e-12

            P = []
            for pt in t1:
                if inside(pt, t2): P.append(pt)
            for pt in t2:
                if inside(pt, t1): P.append(pt)

            def segseg(p, q, r, s):
                # segment intersection in 2D; returns list of intersection points (0,1 or 2 for colinear overlap endpoints)
                def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                def on_seg(a,b,c):
                    return min(a[0],b[0]) - 1e-12 <= c[0] <= max(a[0],b[0]) + 1e-12 and \
                           min(a[1],b[1]) - 1e-12 <= c[1] <= max(a[1],b[1]) + 1e-12
                o1 = orient(p,q,r); o2 = orient(p,q,s); o3 = orient(r,s,p); o4 = orient(r,s,q)
                out = []
                if abs(o1) < 1e-12 and on_seg(p,q,r): out.append(r)
                if abs(o2) < 1e-12 and on_seg(p,q,s): out.append(s)
                if abs(o3) < 1e-12 and on_seg(r,s,p): out.append(p)
                if abs(o4) < 1e-12 and on_seg(r,s,q): out.append(q)
                if (o1*o2 < 0) and (o3*o4 < 0):
                    # proper intersection
                    A = q - p; B = s - r; C = r - p
                    den = A[0]*B[1] - A[1]*B[0]
                    if abs(den) > 1e-16:
                        t = (C[0]*B[1] - C[1]*B[0]) / den
                        out.append(p + t*A)
                return out

                # Done

            e1 = [(t1[0],t1[1]), (t1[1],t1[2]), (t1[2],t1[0])]
            e2 = [(t2[0],t2[1]), (t2[1],t2[2]), (t2[2],t2[0])]
            for a0,a1 in e1:
                for b0,b1 in e2:
                    for ip in segseg(a0,a1,b0,b1):
                        P.append(ip)

            if len(P) < 2:
                return []

            # Deduplicate and pick the farthest pair
            Q = []
            for pt in P:
                if not any(np.linalg.norm(pt - q) <= 1e-12 for q in Q):
                    Q.append(pt)
            if len(Q) < 2:
                return []

            # farthest pair
            maxd = 0.0; best = (Q[0], Q[0])
            for i in range(len(Q)):
                for j in range(i+1, len(Q)):
                    d = np.linalg.norm(Q[i] - Q[j])
                    if d > maxd:
                        maxd = d; best = (Q[i], Q[j])
            if maxd <= sliver_tol:
                return []

            # Map back to 3D: p = p0 + u*x + v*y
            a3 = Vector3D(*(p0 + u*best[0][0] + v*best[0][1]))
            b3 = Vector3D(*(p0 + u*best[1][0] + v*best[1][1]))
            return [a3, b3]

    # Non-coplanar: use the robust C++-ported routine
    pt1, pt2 = tri_tri_intersect_with_isectline(tri1, tri2)
    if pt1 is None or pt2 is None:
        return []
    if (pt1 - pt2).length() <= sliver_tol:
        return []
    return [pt1, pt2]


def line_triangle_intersection(
    p1: Vector3D, p2: Vector3D, triangle: Triangle
) -> Optional[Vector3D]:
    """
    Calculate intersection between a line segment and a triangle.
    
    Args:
        p1: First endpoint of the line segment
        p2: Second endpoint of the line segment
        triangle: Triangle to check for intersection
        
    Returns:
        Intersection point or None if no intersection
    """
    # Line direction vector
    dir_vec = p2 - p1
    
    # Triangle normal
    normal = triangle.normal()
    
    # Check if line and triangle are parallel (dot product of normal and line direction is zero)
    dot_product = normal.dot(dir_vec)
    if abs(dot_product) < 1e-10:
        return None  # Line and triangle are parallel
    
    # Calculate distance from p1 to triangle plane
    plane_point = triangle.v1
    d = normal.dot(plane_point - p1) / dot_product
    
    # Check if intersection is within line segment bounds
    if d < 0 or d > 1:
        return None  # Intersection outside line segment
    
    # Calculate intersection point
    intersection = p1 + dir_vec * d
    
    # Check if intersection point is inside triangle
    if triangle.contains_point(intersection):
        return intersection
    
    return None


def calculate_surface_surface_intersection(surface1_idx: int, surface2_idx: int, model):
    """
    Calculate intersections between two surfaces using spatial subdivision for efficiency.
    
    Args:
        surface1_idx: Index of first surface
        surface2_idx: Index of second surface
        model: MeshItModel instance containing surfaces
        
    Returns:
        Single Intersection object, list of Intersection objects, or None if no intersections found
    """
    logger.info(f"=== PYTHON FUNCTION CALLED: calculate_surface_surface_intersection({surface1_idx}, {surface2_idx}) ===")
    
    surface1 = model.surfaces[surface1_idx]
    surface2 = model.surfaces[surface2_idx]
    
    logger.info(f"Surface1 vertices: {len(surface1.vertices)}, triangles: {len(surface1.triangles)}")
    logger.info(f"Surface2 vertices: {len(surface2.vertices)}, triangles: {len(surface2.triangles)}")
    
    # Early rejection test using bounding boxes
    if hasattr(surface1, 'bounds') and hasattr(surface2, 'bounds'):
        if (surface1.bounds[1].x < surface2.bounds[0].x or 
            surface1.bounds[0].x > surface2.bounds[1].x or
            surface1.bounds[1].y < surface2.bounds[0].y or 
            surface1.bounds[0].y > surface2.bounds[1].y or
            surface1.bounds[1].z < surface2.bounds[0].z or 
            surface1.bounds[0].z > surface2.bounds[1].z):
            return None  # No intersection possible
    
    # Convert surface triangles to Triangle objects
    tri1_list = []
    for tri_idx in surface1.triangles:
        if len(tri_idx) >= 3:
            v1 = surface1.vertices[tri_idx[0]]
            v2 = surface1.vertices[tri_idx[1]]
            v3 = surface1.vertices[tri_idx[2]]
            tri1_list.append(Triangle(v1, v2, v3))
    
    tri2_list = []
    for tri_idx in surface2.triangles:
        if len(tri_idx) >= 3:
            v1 = surface2.vertices[tri_idx[0]]
            v2 = surface2.vertices[tri_idx[1]]
            v3 = surface2.vertices[tri_idx[2]]
            tri2_list.append(Triangle(v1, v2, v3))
    
    # Set up the spatial subdivision box
    box = Box()
    
    # Initialize box bounds to encompass both surfaces
    if tri1_list and tri2_list:
        # Get min/max for surface 1
        s1_min = Vector3D(
            min(min(t.v1.x, t.v2.x, t.v3.x) for t in tri1_list),
            min(min(t.v1.y, t.v2.y, t.v3.y) for t in tri1_list),
            min(min(t.v1.z, t.v2.z, t.v3.z) for t in tri1_list)
        )
        s1_max = Vector3D(
            max(max(t.v1.x, t.v2.x, t.v3.x) for t in tri1_list),
            max(max(t.v1.y, t.v2.y, t.v3.y) for t in tri1_list),
            max(max(t.v1.z, t.v2.z, t.v3.z) for t in tri1_list)
        )
        
        # Get min/max for surface 2
        s2_min = Vector3D(
            min(min(t.v1.x, t.v2.x, t.v3.x) for t in tri2_list),
            min(min(t.v1.y, t.v2.y, t.v3.y) for t in tri2_list),
            min(min(t.v1.z, t.v2.z, t.v3.z) for t in tri2_list)
        )
        s2_max = Vector3D(
            max(max(t.v1.x, t.v2.x, t.v3.x) for t in tri2_list),
            max(max(t.v1.y, t.v2.y, t.v3.y) for t in tri2_list),
            max(max(t.v1.z, t.v2.z, t.v3.z) for t in tri2_list)
        )
        
        # Set box to intersection of bounding boxes
        box.min.x = max(s1_min.x, s2_min.x)
        box.min.y = max(s1_min.y, s2_min.y)
        box.min.z = max(s1_min.z, s2_min.z)
        box.max.x = min(s1_max.x, s2_max.x)
        box.max.y = min(s1_max.y, s2_max.y)
        box.max.z = min(s1_max.z, s2_max.z)
        
        # Check if there's no overlap in the bounding boxes
        if (box.min.x > box.max.x or 
            box.min.y > box.max.y or 
            box.min.z > box.max.z):
            return None  # No overlap, cannot have intersections
    else:
        return None  # No triangles in one of the surfaces
    
    # Add triangles to the box
    for tri in tri1_list:
        if box.tri_in_box(tri):
            box.T1s.append(tri)
    
    for tri in tri2_list:
        if box.tri_in_box(tri):
            box.T2s.append(tri)
    
    # If no triangles in the intersection box, return None
    if not box.T1s or not box.T2s:
        return None
    
    # Container for intersection segments
    intersection_segments = []
    
    # Use spatial subdivision to find intersections
    if box.too_much_tri():
        box.split_tri(intersection_segments)
    else:
        # Direct testing for small number of triangles
        for tri1 in box.T1s:
            for tri2 in box.T2s:
                # Use the robust triangle-triangle intersection 
                intersection_points = triangle_triangle_intersection(tri1, tri2)
                if len(intersection_points) >= 2:
                    # Check if this is a meaningful intersection (not just touching at edges)
                    p1, p2 = intersection_points[0], intersection_points[1]
                    segment_length_squared = (p2 - p1).length_squared()
                    
                    # Only accept intersections with meaningful length (not just point contacts)
                    if segment_length_squared > 1e-20:
                        append_non_existing_segment(intersection_segments, p1, p2)
                # Skip single point intersections - they're usually just edge contacts
    
    # If we found any intersections, create an Intersection object
    if intersection_segments:
        logger.info(f"Surface {surface1_idx}-{surface2_idx}: Found {len(intersection_segments)} intersection segments")
        for i, seg in enumerate(intersection_segments):
            if len(seg) >= 2:
                logger.info(f"  Segment {i}: ({seg[0].x:.3f},{seg[0].y:.3f},{seg[0].z:.3f}) -> ({seg[1].x:.3f},{seg[1].y:.3f},{seg[1].z:.3f})")
        
        # Connect intersection segments into continuous curves (like C++ does)
        # Connect intersection segments into continuous curves (like C++ does)
        connected_curves = connect_intersection_segments(intersection_segments)

        # Optional post-connection regularization (C++-like RefineByLength)

        # logger.info(f"Surface {surface1_idx}-{surface2_idx}: Connected into {len(connected_curves)} curves")
        
        # Return multiple intersection objects - one for each curve
        # This matches the C++ behavior where each curve is a separate intersection
        if len(connected_curves) == 1:
            # Single curve - return as single intersection (backward compatibility)
            intersection = Intersection(surface1_idx, surface2_idx, False)
            for point in connected_curves[0]:
                intersection.add_point(point)
            return intersection
        else:
            # Multiple curves - return as list of intersections
            # Note: This changes the return type, but it's necessary for correct visualization
            intersections = []
            for curve_idx, curve in enumerate(connected_curves):
                intersection = Intersection(surface1_idx, surface2_idx, False)
                for point in curve:
                    intersection.add_point(point)
                intersections.append(intersection)
            return intersections
    
    return None

# ####################################################################
# START OF MODIFIED SECTION 2: connect_intersection_segments
# ####################################################################
def connect_intersection_segments(segments, tolerance=1e-10):
    """
    Connect intersection segments into continuous curves, following C++ MeshIt approach.
    This processes segments iteratively like C++ GenerateFirstSplineOfSegments, creating
    separate intersection lines for disconnected regions.
    """
    if not segments:
        return []
    
    logger.info(f"Starting segment connection with {len(segments)} input segments")
    
    validated_points = []
    for i, segment in enumerate(segments):
        if len(segment) >= 2:
            p1, p2 = segment[0], segment[1]
            if (p1 - p2).length_squared() < 1e-24:
                logger.info(f"Segment {i} rejected: identical points")
                continue
            is_duplicate = False
            for j in range(0, len(validated_points), 2):
                if j + 1 < len(validated_points):
                    ep1, ep2 = validated_points[j], validated_points[j + 1]
                    if ((p1 - ep1).length_squared() < 1e-24 and (p2 - ep2).length_squared() < 1e-24) or \
                       ((p2 - ep1).length_squared() < 1e-24 and (p1 - ep2).length_squared() < 1e-24):
                        is_duplicate = True
                        break
            if not is_duplicate:
                validated_points.extend([p1, p2])
                logger.info(f"Segment {i} accepted: ({p1.x:.3f},{p1.y:.3f},{p1.z:.3f}) -> ({p2.x:.3f},{p2.y:.3f},{p2.z:.3f})")
            else:
                logger.info(f"Segment {i} rejected: duplicate")
    
    if not validated_points:
        logger.info("No valid segments found after filtering")
        return []
    
    logger.info(f"After filtering: {len(validated_points)//2} valid segments")
    
    # Much stricter compatibility: avoid jumping to nearby but different lines
    def is_direction_compatible(tangent: Vector3D, candidate_vec: Vector3D, min_dot: float = 0.10) -> bool:
        t_len = tangent.length()
        c_len = candidate_vec.length()
        if t_len < 1e-14 or c_len < 1e-14:
            return False
        t = tangent * (1.0 / t_len)
        c = candidate_vec * (1.0 / c_len)
        return t.dot(c) > min_dot
    curves = []
    curve_count = 0
    connect_tolerance_squared = 1e-12
    
    while len(validated_points) >= 2:
        curve_count += 1
        logger.info(f"Starting curve {curve_count} with {len(validated_points)//2} segments remaining")
        curve = [validated_points[0], validated_points[1]]
        logger.info(f"Curve {curve_count} initial segment: ({curve[0].x:.3f},{curve[0].y:.3f},{curve[0].z:.3f}) -> ({curve[1].x:.3f},{curve[1].y:.3f},{curve[1].z:.3f})")
        validated_points.pop(1)
        validated_points.pop(0)
        
        extended_count = 0
        extended = True
        while extended:
            extended = False
            n = 0
            while n < len(validated_points):
                dist_squared = (validated_points[n] - curve[0]).length_squared()
                if dist_squared < connect_tolerance_squared:
                    tangent = curve[0] - curve[1]
                    if n % 2 == 0:
                        meeting = validated_points[n]
                        other = validated_points[n + 1]
                    else:
                        meeting = validated_points[n]
                        other = validated_points[n - 1]
                    candidate_vec = other - meeting
                    if is_direction_compatible(tangent, candidate_vec):
                        if n % 2 == 0:
                            curve.insert(0, other)
                            validated_points.pop(n + 1); validated_points.pop(n)
                        else:
                            curve.insert(0, other)
                            validated_points.pop(n); validated_points.pop(n - 1)
                        extended = True; extended_count += 1
                        logger.info(f"Curve {curve_count} extended at beginning (#{extended_count})")
                        break
                n += 1
        
        extended = True
        while extended:
            extended = False
            n = 0
            while n < len(validated_points):
                dist_squared = (validated_points[n] - curve[-1]).length_squared()
                if dist_squared < connect_tolerance_squared:
                    tangent = curve[-1] - curve[-2]
                    if n % 2 == 0:
                        meeting = validated_points[n]
                        other = validated_points[n + 1]
                    else:
                        meeting = validated_points[n]
                        other = validated_points[n - 1]
                    candidate_vec = other - meeting
                    if is_direction_compatible(tangent, candidate_vec):
                        if n % 2 == 0:
                            curve.append(other)
                            validated_points.pop(n + 1); validated_points.pop(n)
                        else:
                            curve.append(other)
                            validated_points.pop(n); validated_points.pop(n - 1)
                        extended = True; extended_count += 1
                        logger.info(f"Curve {curve_count} extended at end (#{extended_count})")
                        break
                n += 1
        
        cleaned_curve = [curve[0]]
        for point in curve[1:]:
            if (point - cleaned_curve[-1]).length_squared() > tolerance * tolerance:
                cleaned_curve.append(point)
        
        if len(cleaned_curve) >= 2:
            curves.append(cleaned_curve)
            logger.info(f"Curve {curve_count} completed: {len(cleaned_curve)} points, {extended_count} extensions")
            logger.info(f"  Start: ({cleaned_curve[0].x:.3f},{cleaned_curve[0].y:.3f},{cleaned_curve[0].z:.3f})")
            logger.info(f"  End: ({cleaned_curve[-1].x:.3f},{cleaned_curve[-1].y:.3f},{cleaned_curve[-1].z:.3f})")
        else:
            logger.info(f"Curve {curve_count} rejected: too short after cleanup")
    
    logger.info(f"Segment connection complete: {len(curves)} curves created from original {len(segments)} segments")
    return curves
# ##################################################################
# END OF MODIFIED SECTION 2
# ##################################################################


def calculate_skew_line_transversal(p1: Vector3D, p2: Vector3D, p3: Vector3D, p4: Vector3D) -> Optional[Vector3D]:
    """
    Calculate the skew line transversal between two 3D line segments.
    
    This is a port of C_Line::calculateSkewLineTransversal from C++.
    It calculates the point of closest approach between two non-coplanar segments.
    
    Args:
        p1: First point of first segment
        p2: Second point of first segment
        p3: First point of second segment
        p4: Second point of second segment
        
    Returns:
        Vector3D representing the point of closest approach, or None if the lines are parallel
    """
    # Direction vectors for the two lines
    d1 = p2 - p1
    d2 = p4 - p3
    
    # Check if the lines are parallel
    cross_d1d2 = d1.cross(d2)
    len_cross = cross_d1d2.length()
    if len_cross < 1e-10:
        return None  # Lines are parallel, no unique transversal
    
    # Calculate parameters for the closest point
    n = cross_d1d2.normalized()
    
    # Calculate distance between the lines
    p_diff = p3 - p1
    
    # Calculate t values for closest points on the two lines
    # Compute determinants for the linear system
    det1 = p_diff.dot(d2.cross(n))
    det2 = p_diff.dot(d1.cross(n))
    
    # Denominator is the square of the sin of the angle between d1 and d2
    denom = len_cross * len_cross
    
    # Parameters along the two lines for the closest points
    t1 = det1 / denom
    t2 = det2 / denom
    
    # Check if the closest points are within the segments
    if 0 <= t1 <= 1 and 0 <= t2 <= 1:
        # Calculate the two closest points
        c1 = p1 + d1 * t1
        c2 = p3 + d2 * t2
        
        # Check if the points are close enough to be considered an intersection
        if (c1 - c2).length() < 1e-5:
            # Return midpoint
            return (c1 + c2) * 0.5
    
    return None


def sort_intersection_points(points: List[Vector3D]) -> List[Vector3D]:
    """
    Sort intersection points to form a continuous polyline.
    
    This is a port of C_Line::SortByType from C++. It sorts intersection points
    spatially rather than using PCA projection.
    
    Args:
        points: List of intersection points to sort
        
    Returns:
        Sorted list of intersection points
    """
    if len(points) <= 2:
        return points
        
    # Find special points (endpoints or triple points) to use as fixed anchors
    special_points = []
    normal_points = []
    
    for p in points:
        if p.type != "DEFAULT" and p.type != "INTERSECTION_POINT":
            special_points.append(p)
        else:
            normal_points.append(p)
    
    # If we have special points, use them as anchors
    if len(special_points) >= 2:
        # Start with the first special point
        result = [special_points[0]]
        used_points = {0}
        
        # Find the next closest point until we've used all points
        while len(result) < len(points):
            last_point = result[-1]
            
            # Find closest point among remaining points
            best_dist = float('inf')
            best_idx = -1
            best_point = None
            
            # First priority: check remaining special points
            for i, p in enumerate(special_points):
                if i not in used_points:
                    dist = (p - last_point).length()
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = i
                        best_point = p
            
            # If we found a special point, use it
            if best_idx != -1:
                result.append(best_point)
                used_points.add(best_idx)
                continue
            
            # Second priority: find closest normal point
            best_dist = float('inf')
            best_idx = -1
            
            for i, p in enumerate(normal_points):
                if i + len(special_points) not in used_points:
                    dist = (p - last_point).length()
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = i
            
            if best_idx != -1:
                result.append(normal_points[best_idx])
                used_points.add(best_idx + len(special_points))
            else:
                # This shouldn't happen, but just in case
                break
        
        return result
    else:
        # No special points, use the old PCA method as fallback
        return sort_intersection_points_pca(points)


def sort_intersection_points_pca(points: List[Vector3D]) -> List[Vector3D]:
    """
    Sort intersection points using PCA projection for better linearity.
    This is a fallback method when no special points are available.
    """
    if len(points) <= 2:
        return points

    # Convert points to numpy array
    points_np = np.array([p.to_numpy() for p in points])

    # Center the points
    centroid = np.mean(points_np, axis=0)
    centered_points = points_np - centroid

    # Perform SVD to find the principal axis (first singular vector)
    try:
        _, _, vh = np.linalg.svd(centered_points, full_matrices=False)
        principal_axis = vh[0] # Direction of greatest variance
    except np.linalg.LinAlgError:
         # Fallback if SVD fails (e.g., all points are identical)
         print("Warning: SVD failed in sort_intersection_points_pca. Using original order.")
         return points

    # Project points onto the principal axis
    projected_distances = centered_points @ principal_axis

    # Sort original points based on projected distances
    sorted_indices = np.argsort(projected_distances)
    sorted_points = [points[i] for i in sorted_indices]

    return sorted_points


def calculate_polyline_surface_intersection(polyline_idx: int, surface_idx: int, model) -> Optional[Intersection]:
    """
    Calculate intersections between a polyline and a surface using spatial subdivision.
    
    Args:
        polyline_idx: Index of polyline
        surface_idx: Index of surface
        model: MeshItModel instance containing polylines and surfaces
        
    Returns:
        Intersection object or None if no intersections found
    """
    polyline = model.model_polylines[polyline_idx]
    surface = model.surfaces[surface_idx]
    
    # Early rejection test using bounding boxes
    if hasattr(polyline, 'bounds') and hasattr(surface, 'bounds'):
        if (polyline.bounds[1].x < surface.bounds[0].x or 
            polyline.bounds[0].x > surface.bounds[1].x or
            polyline.bounds[1].y < surface.bounds[0].y or 
            polyline.bounds[0].y > surface.bounds[1].y or
            polyline.bounds[1].z < surface.bounds[0].z or 
            polyline.bounds[0].z > surface.bounds[1].z):
            return None  # No intersection possible
    
    # Convert surface triangles to Triangle objects
    triangles = []
    for tri_idx in surface.triangles:
        if len(tri_idx) >= 3:
            v1 = surface.vertices[tri_idx[0]]
            v2 = surface.vertices[tri_idx[1]]
            v3 = surface.vertices[tri_idx[2]]
            triangles.append(Triangle(v1, v2, v3))
    
    # Convert polyline segments to segment pairs
    segments = []
    for segment_idx in polyline.segments:
        if len(segment_idx) < 2:
            continue
        
        p1 = polyline.vertices[segment_idx[0]]
        p2 = polyline.vertices[segment_idx[1]]
        segments.append((p1, p2))
    
    # If no segments or triangles, return None
    if not segments or not triangles:
        return None
    
    # Set up the spatial subdivision box
    box = Box()
    
    # Initialize box bounds to the intersection of polyline and surface bounds
    # Get min/max for polyline
    p_min = Vector3D(
        min(min(s[0].x, s[1].x) for s in segments),
        min(min(s[0].y, s[1].y) for s in segments),
        min(min(s[0].z, s[1].z) for s in segments)
    )
    p_max = Vector3D(
        max(max(s[0].x, s[1].x) for s in segments),
        max(max(s[0].y, s[1].y) for s in segments),
        max(max(s[0].z, s[1].z) for s in segments)
    )
    
    # Get min/max for surface
    s_min = Vector3D(
        min(min(t.v1.x, t.v2.x, t.v3.x) for t in triangles),
        min(min(t.v1.y, t.v2.y, t.v3.y) for t in triangles),
        min(min(t.v1.z, t.v2.z, t.v3.z) for t in triangles)
    )
    s_max = Vector3D(
        max(max(t.v1.x, t.v2.x, t.v3.x) for t in triangles),
        max(max(t.v1.y, t.v2.y, t.v3.y) for t in triangles),
        max(max(t.v1.z, t.v2.z, t.v3.z) for t in triangles)
    )
    
    # Set box to intersection of bounding boxes
    box.min.x = max(p_min.x, s_min.x)
    box.min.y = max(p_min.y, s_min.y)
    box.min.z = max(p_min.z, s_min.z)
    box.max.x = min(p_max.x, s_max.x)
    box.max.y = min(p_max.y, s_max.y)
    box.max.z = min(p_max.z, s_max.z)
    
    # Check if there's no overlap in the bounding boxes
    if (box.min.x > box.max.x or 
        box.min.y > box.max.y or 
        box.min.z > box.max.z):
        return None  # No overlap, cannot have intersections
    
    # Add segments and triangles to the box if they intersect
    for segment in segments:
        if box.seg_in_box(segment[0], segment[1]):
            box.N1s.append(segment)
    
    for tri in triangles:
        if box.tri_in_box(tri):
            box.T2s.append(tri)
    
    # If no segments or triangles in the intersection box, return None
    if not box.N1s or not box.T2s:
        return None
    
    # Find intersections between line segments and triangles
    intersection_points = []
    
    # Check each segment against each triangle in the box
    for segment in box.N1s:
        p1, p2 = segment
        
        for triangle in box.T2s:
            intersection = line_triangle_intersection(p1, p2, triangle)
            if intersection:
                # Mark as intersection point
                intersection.type = "INTERSECTION_POINT"
                
                # Check if this point is already in our intersection list (with tolerance)
                is_duplicate = False
                for existing_point in intersection_points:
                    if (existing_point - intersection).length() < 1e-8:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    intersection_points.append(intersection)
    
    # If we found any intersections, create an Intersection object
    if intersection_points:
        intersection = Intersection(polyline_idx, surface_idx, True)
        
        # For polyline-surface intersections, we sort the points along the polyline
        # to maintain the original structure of the polyline
        sorted_points = sort_intersection_points(intersection_points)
        
        for point in sorted_points:
            intersection.add_point(point)
        return intersection
    
    return None


def closest_point_on_segment(p: Vector3D, a: Vector3D, b: Vector3D) -> Vector3D:
    """Find the closest point on the line segment [a, b] to point p."""
    ap = p - a
    ab = b - a
    ab_len_sq = ab.dot(ab)
    if ab_len_sq < 1e-10:
        return a # Segment is a point
    t = ap.dot(ab) / ab_len_sq
    t = max(0, min(1, t)) # Clamp t to [0, 1] for segment
    return a + ab * t


def segment_segment_distance(a1: Vector3D, b1: Vector3D, a2: Vector3D, b2: Vector3D) -> Tuple[float, Vector3D, Vector3D]:
    """Calculate the minimum distance between two 3D line segments [a1, b1] and [a2, b2],
       and the closest points on each segment.

       Uses the algorithm described by Dan Sunday:
       http://geomalgorithms.com/a07-_distance.html#dist3D_Segment_to_Segment
    """
    u = b1 - a1
    v = b2 - a2
    w = a1 - a2

    a = u.dot(u)  # always >= 0
    b = u.dot(v)
    c = v.dot(v)  # always >= 0
    d = u.dot(w)
    e = v.dot(w)
    D = a * c - b * b  # always >= 0
    sc, sN, sD = D, D, D  # sc = sN / sD, default sD = D >= 0
    tc, tN, tD = D, D, D  # tc = tN / tD, default tD = D >= 0

    # compute the line parameters of the two closest points
    if D < 1e-10:  # the lines are almost parallel
        sN = 0.0  # force using point a1 on segment S1
        sD = 1.0  # to prevent possible division by 0
        tN = e
        tD = c
    else:  # get the closest points on the infinite lines
        sN = (b * e - c * d)
        tN = (a * e - b * d)
        if sN < 0.0:  # sc < 0 => the s=0 edge is visible
            sN = 0.0
            tN = e
            tD = c
        elif sN > sD:  # sc > 1 => the s=1 edge is visible
            sN = sD
            tN = e + b
            tD = c

    if tN < 0.0:  # tc < 0 => the t=0 edge is visible
        tN = 0.0
        # recompute sc for this edge
        if -d < 0.0:
            sN = 0.0
        elif -d > a:
            sN = sD
        else:
            sN = -d
            sD = a
    elif tN > tD:  # tc > 1 => the t=1 edge is visible
        tN = tD
        # recompute sc for this edge
        if (-d + b) < 0.0:
            sN = 0
        elif (-d + b) > a:
            sN = sD
        else:
            sN = (-d + b)
            sD = a

    # finally do the division to get sc and tc
    sc = 0.0 if abs(sN) < 1e-10 else sN / sD
    tc = 0.0 if abs(tN) < 1e-10 else tN / tD

    # get the difference of the two closest points
    dP = w + (u * sc) - (v * tc)
    closest_p1 = a1 + u * sc
    closest_p2 = a2 + v * tc

    return dP.length(), closest_p1, closest_p2


def calculate_triple_points(intersection1_idx: int, intersection2_idx: int, model, tolerance=1e-7) -> List[TriplePoint]:
    """
    Calculate triple points between two intersection polylines using
    spatial subdivision and skew line transversal.

    Args:
        intersection1_idx: Index of first intersection polyline in model.intersections
        intersection2_idx: Index of second intersection polyline in model.intersections
        model: MeshItModel instance containing intersections
        tolerance: Distance tolerance to consider segments intersecting

    Returns:
        List of TriplePoint objects found at the intersections.
    """
    intersection1 = model.intersections[intersection1_idx]
    intersection2 = model.intersections[intersection2_idx]

    # Both lines must share one common parent (typical: A∩B with A∩C → common A)
    ids1 = {intersection1.id1, intersection1.id2}
    ids2 = {intersection2.id1, intersection2.id2}
    if not ids1.intersection(ids2):
        return []  # No common parent object, cannot form a triple point
    
    # Spatial box on the overlap of their bounds
    box = Box()
    if len(intersection1.points) > 0:
        min1 = Vector3D(
            min(p.x for p in intersection1.points),
            min(p.y for p in intersection1.points),
            min(p.z for p in intersection1.points)
        )
        max1 = Vector3D(
            max(p.x for p in intersection1.points),
            max(p.y for p in intersection1.points),
            max(p.z for p in intersection1.points)
        )
        min2 = Vector3D(
            min(p.x for p in intersection2.points),
            min(p.y for p in intersection2.points),
            min(p.z for p in intersection2.points)
        )
        max2 = Vector3D(
            max(p.x for p in intersection2.points),
            max(p.y for p in intersection2.points),
            max(p.z for p in intersection2.points)
        )
        box.min.x = max(min1.x, min2.x)
        box.min.y = max(min1.y, min2.y)
        box.min.z = max(min1.z, min2.z)
        box.max.x = min(max1.x, max2.x)
        box.max.y = min(max1.y, max2.y)
        box.max.z = min(max1.z, max2.z)
        if (box.min.x > box.max.x or 
            box.min.y > box.max.y or 
            box.min.z > box.max.z):
            return []
    else:
        return []
    
    # Populate candidate segments
    for i in range(len(intersection1.points) - 1):
        p1 = intersection1.points[i]
        p2 = intersection1.points[i + 1]
        if box.seg_in_box(p1, p2):
            box.N1s.append((p1, p2))
    for i in range(len(intersection2.points) - 1):
        p1 = intersection2.points[i]
        p2 = intersection2.points[i + 1]
        if box.seg_in_box(p1, p2):
            box.N2s.append((p1, p2))
    if not box.N1s or not box.N2s:
        return []
    
    found_triple_points = []

    # Reject near-parallel segments to prevent false positives along close, parallel lines
    # e.g., require at least ~10 degrees between directions (|dot| <= 0.985 ≈ cos(10°))
    parallel_dot_threshold = 0.985

    if box.too_much_seg():
        box.split_seg(found_triple_points, intersection1_idx, intersection2_idx)
    else:
        for seg1_idx, seg1 in enumerate(box.N1s):
            p1a, p1b = seg1[0], seg1[1]
            d1 = (p1b - p1a).normalized()
            for seg2_idx, seg2 in enumerate(box.N2s):
                p2a, p2b = seg2[0], seg2[1]
                d2 = (p2b - p2a).normalized()

                # Calculate shortest distance between segments and their closest points
                dist, closest1, closest2 = segment_segment_distance(p1a, p1b, p2a, p2b)

                if dist < tolerance:
                    # Use midpoint as triple point candidate
                    tp_point = (closest1 + closest2) * 0.5
                    found_triple_points.append(tp_point)

    return found_triple_points


def insert_triple_points(model, tolerance=1e-5):
    """
    Ensure every TRIPLE_POINT is physically present (and marked) in *all*
    intersection polylines that cross it.

    Works in two passes
    1)  original logic – insert into the two lines recorded in
        tp.intersection_ids  (fast path)
    2)  completeness pass – walk over every remaining poly-line and insert the
        point wherever the orthogonal distance to any segment < tolerance.
    """
    from Pymeshit.intersection_utils import closest_point_on_segment

    if not getattr(model, "triple_points", None):
        return                                           # nothing to do

    # ------------------------------------------------------------------ PASS 1
    #         original ID-based insertion (kept as-is)
    # ------------------------------------------------------------------
    for tp in model.triple_points:
        for int_idx in tp.intersection_ids:
            if 0 <= int_idx < len(model.intersections):
                _insert_point_into_polyline(model.intersections[int_idx].points,
                                            tp.point, tolerance)

    # ------------------------------------------------------------------ PASS 2
    #         completeness – make sure *every* line owns the TP
    # ------------------------------------------------------------------
    for tp in model.triple_points:
        p_tp = tp.point
        for i, inter in enumerate(model.intersections):
            if i in tp.intersection_ids:
                continue                                 # already done

            # quick BB check ---------------------------------------------------
            xs = [v.x for v in inter.points]
            ys = [v.y for v in inter.points]
            zs = [v.z for v in inter.points]
            if not (min(xs) - tolerance <= p_tp.x <= max(xs) + tolerance and
                    min(ys) - tolerance <= p_tp.y <= max(ys) + tolerance and
                    min(zs) - tolerance <= p_tp.z <= max(zs) + tolerance):
                continue

            # precise distance to each segment --------------------------------
            on_line = False
            for a, b in zip(inter.points[:-1], inter.points[1:]):
                dist = (closest_point_on_segment(p_tp, a, b) - p_tp).length()
                if dist < tolerance:
                    on_line = True
                    break

            if on_line:
                _insert_point_into_polyline(inter.points, p_tp, tolerance)
                tp.add_intersection(i)                  # keep bookkeeping

# --------------------------------------------------------------------------
#  tiny helper -------------------------------------------------------------
# --------------------------------------------------------------------------
def _insert_point_into_polyline(pts, p_new, tol):
    """
    Insert p_new between the two vertices of *pts* whose segment is closest
    to the point (unless a vertex at the same XYZ already exists).
    """
    import math
    # duplicate check ------------------------------------------------------
    for v in pts:
        if ( (v - p_new).length() < tol ):
            # Same coordinate already there → keep the *special* flag
            if getattr(p_new, "type", "DEFAULT") == "TRIPLE_POINT":
                v.type = "TRIPLE_POINT"
            return

    # find best host segment ----------------------------------------------
    best_k = None
    best_d = math.inf
    for k in range(len(pts) - 1):
        d = (closest_point_on_segment(p_new, pts[k], pts[k+1]) - p_new).length()
        if d < best_d:
            best_d, best_k = d, k

    if best_k is not None:
        p_new.type = "TRIPLE_POINT"
        pts.insert(best_k + 1, p_new)


def clean_identical_points(points_list: List[Vector3D], tolerance=1e-10) -> List[Vector3D]:
    """Removes duplicate points from a list, preserving order and special types."""
    if not points_list:
        return []
    
    cleaned_list = []
    for point_to_add in points_list:
        if not cleaned_list:
            cleaned_list.append(point_to_add)
            continue

        # Check against the last added point in the cleaned list
        if (point_to_add - cleaned_list[-1]).length() > tolerance:
            cleaned_list.append(point_to_add)
        else:
            # Points are identical or very close
            # Prioritize special types over DEFAULT or if types differ, log it (or define priority)
            if point_to_add.type != "DEFAULT" and cleaned_list[-1].type == "DEFAULT":
                cleaned_list[-1] = point_to_add # Replace default with special
            elif point_to_add.type != "DEFAULT" and cleaned_list[-1].type != "DEFAULT" and point_to_add.type != cleaned_list[-1].type:
                # Both are special but different. For now, keep the one already in cleaned_list.
                # logger.warning(f"CleanIdenticalPoints: Conflicting special types for merged points: {cleaned_list[-1].type} and {point_to_add.type}. Keeping first.")
                pass # Keep the existing special point in cleaned_list
            # If point_to_add.type is DEFAULT and cleaned_list[-1] is special, do nothing.
            # If both are DEFAULT, or both are the same special type, do nothing.
            
    return cleaned_list


def make_corners_special(convex_hull: List[Vector3D], angle_threshold_deg: float = 135.0):
    """
    Identify and mark corner points on a convex hull based on angle analysis.
    This follows the C++ MeshIt MakeCornersSpecial function.
    
    Args:
        convex_hull: List of Vector3D points forming the convex hull
        angle_threshold_deg: Angle threshold in degrees (points with angles < this are marked special/CORNER)
    
    Returns:
        Modified convex hull with special points marked
    """
    if len(convex_hull) < 3:
        return convex_hull
    
    # Convert threshold to radians and to dot product value
    # For sharp angles < threshold, the dot product will be > cos(threshold)
    angle_threshold_rad = math.radians(angle_threshold_deg)
    dot_threshold = math.cos(angle_threshold_rad)
    
    logger.info(f"Making corners special with angle threshold {angle_threshold_deg}° (dot > {dot_threshold:.3f} for sharp corners)")
    
    special_count = 0
    
    # Check each point in the convex hull
    for n in range(len(convex_hull)):
        # Get the three points for angle calculation
        if n == 0:
            # First point: use last-2, current, and next
            prev_pt = convex_hull[-2] if len(convex_hull) > 2 else convex_hull[-1]
            curr_pt = convex_hull[0]
            next_pt = convex_hull[1]
        else:
            prev_pt = convex_hull[n - 1]
            curr_pt = convex_hull[n]
            next_pt = convex_hull[(n + 1) % len(convex_hull)]
        
        # Calculate vectors from current point
        diff1 = prev_pt - curr_pt
        diff2 = next_pt - curr_pt
        
        # Normalize the vectors
        len1 = diff1.length()
        len2 = diff2.length()
        
        if len1 > 1e-10 and len2 > 1e-10:
            diff1_norm = diff1 / len1
            diff2_norm = diff2 / len2
            
            # Calculate dot product
            dot_product = diff1_norm.dot(diff2_norm)
            
            # Check if angle is sharp enough (C++ condition: alpha > -0.707 means angle < 135°)
            # In C++: if (alpha > (-0.5*SQUAREROOTTWO)) marks SHARP corners (< 135°)
            # So we need: dot_product > dot_threshold for angles < 135°
            if dot_product > dot_threshold:
                curr_pt.point_type = "CORNER"
                if hasattr(curr_pt, 'type'):
                    curr_pt.type = "CORNER"
                special_count += 1
                
                # If this is the first point, also mark the last point (closed polygon)
                if n == 0 and len(convex_hull) > 2:
                    convex_hull[-1].point_type = "CORNER"
                    if hasattr(convex_hull[-1], 'type'):
                        convex_hull[-1].type = "CORNER"
                
                angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot_product))))
                logger.info(f"*** Found CORNER point at ({curr_pt.x:.3f}, {curr_pt.y:.3f}, {curr_pt.z:.3f}) with sharp angle {angle_deg:.1f}° ***")
    
    logger.info(f"Identified {special_count} corner points on convex hull")
    return convex_hull


def refine_hull_with_interpolation(raw_hull_points: List[Vector3D], 
                                   scattered_data_points: List[Vector3D], 
                                   config: Dict) -> List[Vector3D]:
    """
    Refine convex hull points by projecting them onto an interpolated surface model.
    
    This implements the missing C++ MeshIt workflow step that creates a smooth interpolated
    surface from the scattered data and then projects the raw hull points onto this surface
    to create a refined, geometrically accurate boundary.
    
    Args:
        raw_hull_points: Original 3D boundary points calculated from scattered data
        scattered_data_points: Full cloud of 3D scattered data points for the surface
        config: Configuration dictionary containing interpolation settings
        
    Returns:
        List of refined hull points projected onto the interpolated surface
    """
    if not raw_hull_points or not scattered_data_points:
        logger.warning("Empty hull or scattered data points provided for hull refinement")
        return raw_hull_points
    
    if len(scattered_data_points) < 3:
        logger.warning("Insufficient scattered data points for interpolation")
        return raw_hull_points
        
    try:
        # Import required scipy modules
        from scipy.interpolate import griddata, RBFInterpolator
        from scipy.spatial.distance import pdist
        
        # Try to import sklearn PCA, fallback to manual PCA if not available
        try:
            from sklearn.decomposition import PCA
            use_sklearn_pca = True
        except ImportError:
            logger.warning("scikit-learn not available, using manual PCA implementation")
            use_sklearn_pca = False
        
        logger.info(f"Refining hull with {len(raw_hull_points)} points using {len(scattered_data_points)} scattered data points")
        
        # Convert scattered data to numpy arrays
        scattered_3d = np.array([[p.x, p.y, p.z] for p in scattered_data_points])
        hull_3d = np.array([[p.x, p.y, p.z] for p in raw_hull_points])
        
        # Step 1: Perform PCA on scattered data to establish local 2D coordinate system
        if use_sklearn_pca:
            pca = PCA(n_components=3)
            pca.fit(scattered_3d)
            scattered_pca = pca.transform(scattered_3d)
            hull_pca = pca.transform(hull_3d)
        else:
            # Manual PCA implementation
            # Center the data
            mean_point = np.mean(scattered_3d, axis=0)
            centered_data = scattered_3d - mean_point
            
            # Compute covariance matrix
            cov_matrix = np.cov(centered_data.T)
            
            # Compute eigenvalues and eigenvectors
            eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)
            
            # Sort by eigenvalues (descending)
            idx = np.argsort(eigenvalues)[::-1]
            eigenvalues = eigenvalues[idx]
            eigenvectors = eigenvectors[:, idx]
            
            # Transform data to PCA space
            scattered_pca = np.dot(centered_data, eigenvectors)
            hull_centered = hull_3d - mean_point
            hull_pca = np.dot(hull_centered, eigenvectors)
            
            # Store transformation info for inverse transform
            pca_mean = mean_point
            pca_components = eigenvectors
        
        # Use first two PCA components as 2D coordinates, third as Z values
        scattered_2d = scattered_pca[:, :2]
        scattered_z = scattered_pca[:, 2]
        hull_2d = hull_pca[:, :2]
        
        # Step 2: Create interpolation model based on configuration
        interp_method = config.get('interp', 'Thin Plate Spline (TPS)')
        smoothing = config.get('smoothing', 0.0)
        
        logger.info(f"Using interpolation method: {interp_method}")
        
        # Check for sufficient data density
        if len(scattered_data_points) < 10:
            logger.warning("Low data density - using IDW interpolation")
            interp_method = "IDW (p=4)"
        
        refined_hull_pca = np.zeros_like(hull_pca)
        refined_hull_pca[:, :2] = hull_2d  # Keep X,Y coordinates in PCA space
        
        if interp_method == "Thin Plate Spline (TPS)":
            try:
                # Use RBF with thin plate spline kernel
                rbf = RBFInterpolator(
                    scattered_2d, scattered_z,
                    kernel='thin_plate_spline',
                    smoothing=0.0  # C++-equivalent: pure interpolation
                )
                refined_hull_pca[:, 2] = rbf(hull_2d)
            except Exception as e:
                logger.warning(f"TPS interpolation failed: {e}, falling back to IDW")
                # IDW fallback implementation
                refined_z = []
                for hull_pt_2d in hull_2d:
                    distances = np.sqrt(np.sum((scattered_2d - hull_pt_2d)**2, axis=1))
                    exact_match_idx = np.where(distances < 1e-12)[0]
                    if len(exact_match_idx) > 0:
                        refined_z.append(scattered_z[exact_match_idx[0]])
                    else:
                        weights = 1.0 / (distances**4.0)  # Default power of 4
                        weighted_sum = np.sum(weights * scattered_z)
                        weight_sum = np.sum(weights)
                        refined_z.append(weighted_sum / weight_sum)
                refined_hull_pca[:, 2] = np.array(refined_z)
                
        elif interp_method.startswith("IDW"):
            # Extract power parameter (default p=4)
            try:
                power = float(interp_method.split('p=')[1].rstrip(')'))
            except:
                power = 4.0

            # Manual IDW implementation
            refined_z = []
            for hull_pt_2d in hull_2d:
                distances = np.sqrt(np.sum((scattered_2d - hull_pt_2d)**2, axis=1))

                # Handle exact matches
                exact_match_idx = np.where(distances < 1e-12)[0]
                if len(exact_match_idx) > 0:
                    refined_z.append(scattered_z[exact_match_idx[0]])
                else:
                    weights = 1.0 / (distances**power)
                    weighted_sum = np.sum(weights * scattered_z)
                    weight_sum = np.sum(weights)
                    refined_z.append(weighted_sum / weight_sum)

            refined_hull_pca[:, 2] = np.array(refined_z)
        else:
            # Default to IDW for unrecognized methods
            logger.warning(f"Unknown interpolation method {interp_method}, using IDW")
            # IDW implementation
            refined_z = []
            for hull_pt_2d in hull_2d:
                distances = np.sqrt(np.sum((scattered_2d - hull_pt_2d)**2, axis=1))
                exact_match_idx = np.where(distances < 1e-12)[0]
                if len(exact_match_idx) > 0:
                    refined_z.append(scattered_z[exact_match_idx[0]])
                else:
                    weights = 1.0 / (distances**4.0)  # Default power of 4
                    weighted_sum = np.sum(weights * scattered_z)
                    weight_sum = np.sum(weights)
                    refined_z.append(weighted_sum / weight_sum)
            refined_hull_pca[:, 2] = np.array(refined_z)
        
        # Handle any NaN values by falling back to original Z coordinates
        nan_mask = np.isnan(refined_hull_pca[:, 2])
        if np.any(nan_mask):
            logger.warning(f"Interpolation produced {np.sum(nan_mask)} NaN values, using original Z coordinates")
            refined_hull_pca[nan_mask, 2] = hull_pca[nan_mask, 2]
        
        # Step 3: Transform refined hull points back to original 3D coordinate system
        if use_sklearn_pca:
            refined_hull_3d = pca.inverse_transform(refined_hull_pca)
        else:
            # Manual inverse transform
            refined_hull_3d = np.dot(refined_hull_pca, pca_components.T) + pca_mean
        
        # Step 4: Create refined Vector3D objects preserving point types
        refined_hull_points = []
        for i, (orig_pt, refined_3d) in enumerate(zip(raw_hull_points, refined_hull_3d)):
            refined_pt = Vector3D(refined_3d[0], refined_3d[1], refined_3d[2])
            # Preserve original point type information
            refined_pt.point_type = getattr(orig_pt, 'point_type', 'DEFAULT')
            if hasattr(orig_pt, 'type'):
                refined_pt.type = orig_pt.type
            refined_hull_points.append(refined_pt)
        
        # Calculate refinement statistics
        displacement_distances = [
            (orig - refined).length() 
            for orig, refined in zip(raw_hull_points, refined_hull_points)
        ]
        max_displacement = max(displacement_distances) if displacement_distances else 0.0
        avg_displacement = np.mean(displacement_distances) if displacement_distances else 0.0
        
        logger.info(f"Hull refinement complete: max displacement = {max_displacement:.6f}, "
                   f"avg displacement = {avg_displacement:.6f}")
        
        return refined_hull_points
        
    except ImportError as e:
        logger.error(f"Required interpolation libraries not available: {e}")
        logger.warning("Hull refinement skipped - returning original hull points")
        return raw_hull_points
        
    except Exception as e:
        logger.error(f"Error during hull interpolation refinement: {e}", exc_info=True)
        logger.warning("Hull refinement failed - returning original hull points")
        return raw_hull_points


def align_intersections_to_convex_hull(surface_idx: int, model):
    """
    Geometry-preserving alignment only (no resampling here).
    - Snap intersection endpoints to any hull vertex (not just special)
    - If not snapped, project to closest hull edge and INSERT a new special vertex on that edge
    """
    surface = model.surfaces[surface_idx]
    if not hasattr(surface, "convex_hull") or not surface.convex_hull or len(surface.convex_hull) < 3:
        logger.warning(f"Surface {surface_idx} has no valid convex hull for alignment.")
        return

    snap_tol = 1e-4  # <<--- increased
    proj_tol = 1e-1   # <<--- increased

    for inter in model.intersections:
        is_surface1 = not model.is_polyline.get(inter.id1, True)
        is_surface2 = not model.is_polyline.get(inter.id2, True)
        if not ((is_surface1 and inter.id1 == surface_idx) or (is_surface2 and inter.id2 == surface_idx)):
            continue
        if not inter.points:
            continue

        endpoints = [(0, inter.points[0])] if len(inter.points) == 1 else [(0, inter.points[0]), (-1, inter.points[-1])]
        for ep_idx, ep in endpoints:
            # Try snap to any hull vertex (not just special)
            snapped = False
            for v in surface.convex_hull:
                if (ep - v).length() < snap_tol:
                    inter.points[0 if ep_idx == 0 else -1] = v
                    snapped = True
                    logger.info(f"Snapped endpoint to hull vertex at ({v.x:.3f}, {v.y:.3f}, {v.z:.3f})")
                    break
            if snapped:
                continue

            # Otherwise project to closest edge; insert a special vertex there
            best_d, best_i, best_p = float("inf"), None, None
            n = len(surface.convex_hull)
            for i in range(n):
                a = surface.convex_hull[i]
                b = surface.convex_hull[(i + 1) % n]
                p = closest_point_on_segment(ep, a, b)
                d = (p - ep).length()
                if d < best_d:
                    best_d, best_i, best_p = d, i, p

            if best_p is not None and best_d < proj_tol:
                # If point already exists at the projection location, snap
                for v in surface.convex_hull:
                    if (best_p - v).length() < snap_tol:
                        inter.points[0 if ep_idx == 0 else -1] = v
                        logger.info(f"Snapped endpoint to existing hull vertex at ({v.x:.3f}, {v.y:.3f}, {v.z:.3f})")
                        break
                else:
                    # Insert a new special vertex on the hull edge
                    nv = Vector3D(best_p.x, best_p.y, best_p.z, point_type="COMMON_INTERSECTION_CONVEXHULL_POINT")
                    surface.convex_hull.insert(int(best_i) + 1, nv)
                    inter.points[0 if ep_idx == 0 else -1] = nv
                    logger.info(f"Inserted new special vertex at ({nv.x:.3f}, {nv.y:.3f}, {nv.z:.3f}) on hull edge {best_i}")

    # Remove true duplicates only (no geometry changes)
    surface.convex_hull = clean_identical_points(surface.convex_hull, tolerance=1e-12)

    # Bookkeeping
    surface.hull_points = surface.convex_hull[:]
    special_count = sum(1 for p in surface.convex_hull if getattr(p, "point_type", getattr(p, "type", "DEFAULT")) != "DEFAULT")
    logger.info(f"Convex hull alignment complete for surface {surface_idx}: {special_count} special / {len(surface.convex_hull)} total")
def calculate_size_of_intersections(model):
    """
    Calculate sizes for intersections based on the associated objects.
    
    Args:
        model: MeshItModel instance
    """
    for intersection in model.intersections:
        # Get the associated objects
        if intersection.is_polyline_mesh:
            # Polyline-surface intersection
            polyline = model.model_polylines[intersection.id1]
            surface = model.surfaces[intersection.id2]
            
            # Set size based on objects
            intersection_size = min(
                getattr(polyline, 'size', 1.0),
                getattr(surface, 'size', 1.0)
            ) * 0.5  # Smaller size for intersections
            
            # Store size with each point
            for point in intersection.points:
                setattr(point, 'size', intersection_size)
        else:
            # Surface-surface intersection
            surface1 = model.surfaces[intersection.id1]
            surface2 = model.surfaces[intersection.id2]
            
            # Set size based on surfaces
            intersection_size = min(
                getattr(surface1, 'size', 1.0),
                getattr(surface2, 'size', 1.0)
            ) * 0.5  # Smaller size for intersections
            
            # Store size with each point
            for point in intersection.points:
                setattr(point, 'size', intersection_size)


def cluster_points(points: List[Vector3D], tolerance: float) -> List[List[Vector3D]]:
    """Groups points that are within tolerance of each other."""
    clusters = []
    used = [False] * len(points)
    for i in range(len(points)):
        if used[i]:
            continue
        current_cluster = [points[i]]
        used[i] = True
        # Check subsequent points
        for j in range(i + 1, len(points)):
            if not used[j]:
                # Check distance to any point already in the current cluster
                is_close = False
                for cluster_point in current_cluster:
                     if (points[j] - cluster_point).length() < tolerance:
                          is_close = True
                          break
                if is_close:
                    current_cluster.append(points[j])
                    used[j] = True
        clusters.append(current_cluster)
    return clusters


def calculate_cluster_center(cluster: List[Vector3D]) -> Vector3D:
    """Calculates the average coordinate of points in a cluster."""
    if not cluster:
        return Vector3D() # Should not happen
    sum_vec = Vector3D()
    for p in cluster:
        sum_vec += p
    return sum_vec / len(cluster)


def run_intersection_workflow(model, progress_callback=None, tolerance=1e-5, config=None):
    """
    Run the complete intersection workflow, including:
    1. Surface-Surface intersections
    2. Polyline-Surface intersections (if polylines exist)
    3. Calculating and merging Triple Points
    4. Inserting Triple Points into intersection lines
    5. NEW: Constraint processing and size assignment

    Args:
        model: MeshItModel instance
        progress_callback: Optional callback function for progress updates
        tolerance: Distance tolerance for finding intersections and merging points
        config: Configuration dictionary for constraint processing

    Returns:
        The updated model instance
    """
    def report_progress(message):
        if progress_callback:
            progress_callback(message)
        else:
            print(message)

    if config is None:
        config = {
            'gradient': 2.0,
            'use_constraint_processing': True,
            'type_based_sizing': True,
            'hierarchical_constraints': True
        }

    report_progress(">Calculating Surface-Surface Intersections...")
    model.intersections.clear() # Start fresh
    n_surfaces = len(model.surfaces)
    # ... (Surface-Surface intersection calculation using executor) ...
    # --- Assume this part correctly populates model.intersections ---
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures_ss = []
        for s1 in range(n_surfaces - 1):
            for s2 in range(s1 + 1, n_surfaces):
                futures_ss.append(executor.submit(calculate_surface_surface_intersection, s1, s2, model))
        for future in concurrent.futures.as_completed(futures_ss):
            result = future.result()
            if result:
                # Handle both single intersection and list of intersections
                if isinstance(result, list):
                    # Multiple curves - add each intersection separately
                    model.intersections.extend(result)
                else:
                    # Single curve - add as before
                    model.intersections.append(result)
    report_progress(">...Surface-Surface finished")

    # --- Optional: Polyline-Surface Intersections ---
    if hasattr(model, 'model_polylines') and model.model_polylines:
        report_progress(">Calculating Polyline-Surface Intersections...")
        # ... (Polyline-Surface intersection calculation using executor) ...
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures_ps = []
            for p_idx in range(len(model.model_polylines)):
                for s_idx in range(n_surfaces):
                    futures_ps.append(executor.submit(calculate_polyline_surface_intersection, p_idx, s_idx, model))
            for future in concurrent.futures.as_completed(futures_ps):
                result = future.result()
                if result: model.intersections.append(result)
        report_progress(">...Polyline-Surface finished")

    # --- Calculate Triple Points --- 
    report_progress(">Calculating Intersection Triple Points...")
    model.triple_points.clear()
    potential_tp_coords = [] # Store raw coordinates first
    num_intersections = len(model.intersections)
    
    if num_intersections >= 2:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures_tp = []
            # Submit tasks for each intersection pair
            for i1 in range(num_intersections - 1):
                for i2 in range(i1 + 1, num_intersections):
                    # Pass the tolerance down
                    futures_tp.append(executor.submit(calculate_triple_points, i1, i2, model, tolerance))
            
            # Collect all potential points
            for future in concurrent.futures.as_completed(futures_tp):
                potential_tp_coords.extend(future.result()) # result is now a list of Vector3D

    report_progress(f">  Found {len(potential_tp_coords)} potential triple point candidates.")

    # --- Cluster and Merge Triple Points --- 
    if potential_tp_coords:
        report_progress(">  Clustering and merging triple points...")
        clusters = cluster_points(potential_tp_coords, tolerance)
        final_triple_points = []
        for cluster in clusters:
            if not cluster: continue
            # Calculate the center of the cluster
            center_point = calculate_cluster_center(cluster)
            center_point.type = "TRIPLE_POINT" # Set type
            
            # Create the final TriplePoint object
            final_tp_obj = TriplePoint(center_point)
            
            # Find which original intersections contributed to this cluster 
            # (Requires relating raw points back or re-checking proximity)
            # For simplicity now, we won't store intersection_ids accurately here.
            # A more robust implementation would track origins or re-calculate.
            # We will add dummy intersection IDs for now to maintain structure.
            # TODO: Implement accurate tracking/calculation of involved intersection IDs
            final_tp_obj.add_intersection(-1) # Placeholder ID
            final_tp_obj.add_intersection(-2) # Placeholder ID

            final_triple_points.append(final_tp_obj)
            
        model.triple_points = final_triple_points # Store the final merged points
        report_progress(f">  Resulted in {len(model.triple_points)} final triple points after merging.")
    else:
         report_progress(">  No potential triple points found to cluster.")

    # --- Insert Triple Points into Intersection Lines --- 
    # The insert_triple_points function might still be useful 
    # to snap the final averaged points exactly onto the lines.
    report_progress(">Inserting Triple Points into Intersection Lines...")
    insert_triple_points(model, tolerance)
    report_progress(">...Triple Points finished")


    return model


def compute_angle_between_segments(p1, p2, p3):
    """
    Calculate the angle in degrees between two line segments p1-p2 and p2-p3
    
    Args:
        p1, p2, p3: Vector3D points forming two segments
        
    Returns:
        Angle in degrees
    """
    if p1 is None or p2 is None or p3 is None:
        return 0.0
        
    # Create vectors for the two segments
    v1 = Vector3D(p2.x - p1.x, p2.y - p1.y, p2.z - p1.z)
    v2 = Vector3D(p3.x - p2.x, p3.y - p2.y, p3.z - p2.z)
    
    # Normalize the vectors
    len1 = v1.length()
    len2 = v2.length()
    
    if len1 < 1e-6 or len2 < 1e-6:
        return 0.0
    
    v1 = v1 / len1
    v2 = v2 / len2
    
    # Calculate the dot product
    dot_product = v1.dot(v2)
    
    # Clamp dot product to [-1, 1] to avoid numerical issues
    dot_product = max(-1.0, min(1.0, dot_product))
    
    # Calculate angle in degrees
    angle_rad = math.acos(dot_product)
    angle_deg = angle_rad * 180.0 / math.pi
    
    return angle_deg


import math # Ensure math is imported
# Ensure logger is configured if you use logger.info, e.g.:
# import logging
# logger = logging.getLogger(__name__) # Or your specific logger

# ... (Vector3D, Intersection, compute_angle_between_segments, clean_identical_points - assumed to be present) ...

def refine_intersection_line_by_length(intersection,
                                       target_length,
                                       min_angle_deg: float = 20.0,
                                       uniform_meshing: bool = True):
    """
    Python re-implementation of C++ MeshIt::C_Line::RefineByLength()
    enhanced for curved / circular intersection lines.

    • Removes intermediary DEFAULT points, keeping “special” anchors
    • Sub-divides between anchors so that chord length ≈ target_length
      – **Subdivision is carried out on the original poly-line arc-length
        (like getPointAtPos in C++), so curved geometry is preserved.**
    • Handles closed loops and huge convex-hulls automatically.

    Returns
    -------
    List[Vector3D]  (also written back to intersection.points)
    """

    # ------------------------------------------------------------------
    # quick sanity
    # ------------------------------------------------------------------
    if not getattr(intersection, "points", None) or len(intersection.points) < 2:
        return intersection.points

    original_pts: list[Vector3D] = intersection.points

    # ------------------------------------------------------------------
    # helpers  –  miniature versions of C++  NsPos & getPointAtPos
    # ------------------------------------------------------------------
    def _cum_dist(pts):
        """Cumulative arc-length positions of the poly-line."""
        out = [0.0]
        for i in range(1, len(pts)):
            out.append(out[-1] + (pts[i] - pts[i - 1]).length())
        return out

    def _point_at_pos(pts, cum, s):
        """
        Interpolated point at cumulative position *s* (0 ≤ s ≤ cum[-1]).
        """
        if s <= 0.0:
            base = pts[0]
            return Vector3D(base.x, base.y, base.z, point_type="DEFAULT")
        if s >= cum[-1]:
            base = pts[-1]
            return Vector3D(base.x, base.y, base.z, point_type="DEFAULT")

        import bisect
        idx = bisect.bisect_left(cum, s)
        # exact hit
        if cum[idx] == s:
            base = pts[idx]
            return Vector3D(base.x, base.y, base.z, point_type="DEFAULT")

        s0, s1 = cum[idx - 1], cum[idx]
        t = (s - s0) / (s1 - s0)
        p0, p1 = pts[idx - 1], pts[idx]
        interp = p0 + (p1 - p0) * t
        return Vector3D(interp.x, interp.y, interp.z, point_type="DEFAULT")

    cum_dist = _cum_dist(original_pts)
    if cum_dist[-1] < 1e-9:                 # degenerate
        return original_pts

    # ------------------------------------------------------------------
    # STEP-1  build anchor list  (keep first/last, all non-DEFAULT between)
    # ------------------------------------------------------------------
    anchors: list[Vector3D] = []
    anchors.append(original_pts[0])         # first – even if DEFAULT

    for p in original_pts[1:-1]:
        ptype = getattr(p, "point_type", getattr(p, "type", "DEFAULT"))
        if ptype and ptype != "DEFAULT":
            anchors.append(p)

    anchors.append(original_pts[-1])        # last

    # extra safeguard for near-circular curves where all pts were DEFAULT
    if len(anchors) < 3 and len(original_pts) > 6:
        span = max(1, len(original_pts)//8)
        anchors = [original_pts[i] for i in range(0, len(original_pts), span)]
        anchors.append(original_pts[-1])

    # ------------------------------------------------------------------
    # map each anchor → its cumulative arc-length pos
    # ------------------------------------------------------------------
    anchor_pos = []
    pos_lookup = {id(pt): idx for idx, pt in enumerate(original_pts)}
    for a in anchors:
        idx = pos_lookup.get(id(a))
        # fallback on coordinate match
        if idx is None:
            idx = next((i for i, q in enumerate(original_pts)
                        if (q - a).length() < 1e-9), 0)
        anchor_pos.append(cum_dist[idx])

    # ------------------------------------------------------------------
    # STEP-2  produce refined list
    # ------------------------------------------------------------------
    refined: list[Vector3D] = [anchors[0]]
    for i in range(len(anchors) - 1):
        s0, s1 = anchor_pos[i], anchor_pos[i + 1]
        seg_len = s1 - s0
        if seg_len < 1e-7:
            continue

        ratio = seg_len / max(target_length, 1e-9)
        pts_cnt = (round(ratio) if uniform_meshing
                   else math.ceil(ratio))
        pts_cnt = max(1, pts_cnt)
        step = seg_len / pts_cnt

        # insert intermediate samples
        for k in range(1, pts_cnt):
            s = s0 + step * k
            refined.append(_point_at_pos(original_pts, cum_dist, s))

        refined.append(anchors[i + 1])

    refined = clean_identical_points(refined)

    # ------------------------------------------------------------------
        # ------------------------------------------------------------------
    # STEP-3  tag start / end  (and guarantee closed-loop duplication)
    # ------------------------------------------------------------------
    if refined:
        refined[0].point_type = refined[0].type = "START_POINT"

        closed = (refined[-1] - refined[0]).length() < 1e-8
        if closed:
            # keep BOTH points: first = START_POINT, last = LOOP_END
            if refined[-1] is refined[0]:
                # they are actually the same object – append a clone
                p0 = refined[0]
                refined.append(
                    Vector3D(p0.x, p0.y, p0.z, point_type="LOOP_END")
                )
            else:
                refined[-1].point_type = refined[-1].type = "LOOP_END"
        else:
            refined[-1].point_type = refined[-1].type = "END_POINT"

    # write back & return
    intersection.points = refined
    return refined

def prepare_plc_for_surface_triangulation(surface_data,
                                          intersections_on_surface_data,
                                          config):
    """
    Build a PLC (Planar Straight–Line Complex) for one surface, ready to be
    triangulated with Triangle / TetGen.

    Differences from the earlier version
    ------------------------------------
    1.  Detects *closed* intersection polylines (first-point ≈ last-point).
        These represent interior holes in C++ MeshIt and **must NOT** be treated
        as ordinary intersection edge constraints.
    2.  For every closed loop:
        • the closing segment (last → first) is inserted so the loop is a proper
          polygon;
        • a point strictly inside the polygon is computed (simple centroid) and
          stored in ``holes_2d``.  Triangle removes triangles containing that
          point, and TetGen inherits the hole automatically – identical to the
          C++ workflow.
    3.  Open polylines are kept exactly as before.
    4.  Function still returns 2-D points, segments, holes and the original
        3-D points.

    Parameters
    ----------
    surface_data : dict
        Contains keys like ``'hull_points'`` and ``'projection_params'``.
    intersections_on_surface_data : list[dict]
        Each item has at least ``'points'`` (Vector3D list).
    config : dict
        Gui / workflow settings (only ``'target_size'`` is used here).

    Returns
    -------
    points_2d : (N, 2) float64 ndarray
    segments   : (M, 2) int32 ndarray
    holes_2d   : (H, 2) float64 ndarray  – may be empty if no holes
    points_3d  : (N, 3) float64 ndarray
    """
    logger = logging.getLogger(__name__)
    tgt_size = config.get("target_size", 20.0)

    # ------------------------------------------------------------------ helpers
    def key_of(p: Vector3D):
        return (round(p.x, 9), round(p.y, 9), round(p.z, 9))

    def add_point(pt: Vector3D) -> int:
        """Insert unique 3-D point, return its global index."""
        k = key_of(pt)
        idx = point_map.get(k)
        if idx is None:
            idx = len(points_3d)
            point_map[k] = idx
            points_3d.append(pt)
        return idx

    # --------------------------- storage for global PLC -----------------------
    point_map: Dict[Tuple[float, float, float], int] = {}
    points_3d: List[Vector3D] = []
    segments:   List[List[int]] = []
    closed_loops_pts: List[List[Vector3D]] = []   # for hole centroids later

    # --------------------------- 1. hull (outer boundary) ---------------------
    hull_pts: List[Vector3D] = surface_data.get("hull_points",
                           surface_data.get("convex_hull", []))
    if hull_pts and len(hull_pts) > 1:
        hull_idx = [add_point(p) for p in hull_pts]
        for i in range(len(hull_idx)):
            segments.append([hull_idx[i], hull_idx[(i + 1) % len(hull_idx)]])

    # --------------------------- 2. intersection polylines --------------------
    tol_sq = 1e-16  # squared tolerance for "same point" check
    for inter in intersections_on_surface_data:
        pts: List[Vector3D] = inter.get("points", [])
        if len(pts) < 2:
            continue

        # Detect closed loop – first and last coincide within tolerance
        is_closed = (pts[0] - pts[-1]).length_squared() < tol_sq

        idx_list = [add_point(p) for p in pts]

        # Add polyline segments
        for i in range(len(idx_list) - 1):
            if idx_list[i] != idx_list[i + 1]:
                segments.append([idx_list[i], idx_list[i + 1]])

        # Close the loop if necessary and remember to create a hole
        if is_closed and idx_list[0] != idx_list[-1]:
            segments.append([idx_list[-1], idx_list[0]])
            closed_loops_pts.append(pts)  # keep 3-D pts for centroid

    logger.info(
        f"PLC construction – raw counts: {len(points_3d)} pts, "
        f"{len(segments)} segments, {len(closed_loops_pts)} holes detected"
    )

    # --------------------------- 3. project everything to 2-D -----------------
    proj = surface_data.get("projection_params")
    if not proj:
        raise RuntimeError("Missing projection parameters for surface.")

    centroid = np.asarray(proj["centroid"])
    basis    = np.asarray(proj["basis"])        # (2×3) ortho basis stored row-wise

    pts_3d_arr = np.array([[p.x, p.y, p.z] for p in points_3d])
    pts_2d_arr = (pts_3d_arr - centroid) @ basis.T
    pts_2d_arr = pts_2d_arr[:, :2]              # drop z in local coords

    # --------------------------- 4. hole centroids ----------------------------
    hole_pts_2d: List[np.ndarray] = []
    for loop in closed_loops_pts:
        # simple arithmetic centroid – sufficient for reasonably convex loops
        cx = sum(p.x for p in loop) / len(loop)
        cy = sum(p.y for p in loop) / len(loop)
        cz = sum(p.z for p in loop) / len(loop)
        p3d = np.array([cx, cy, cz])
        p2d = (p3d - centroid) @ basis.T
        hole_pts_2d.append(p2d[:2])

    holes_2d_arr = (
        np.vstack(hole_pts_2d).astype(float)
        if hole_pts_2d else
        np.empty((0, 2), dtype=float)
    )

    logger.info(
        f"PLC ready: {pts_2d_arr.shape[0]} pts, {len(segments)} segments, "
        f"{holes_2d_arr.shape[0]} holes"
    )

    return (
        pts_2d_arr.astype(float),
        np.asarray(segments, dtype=np.int32),
        holes_2d_arr,
        pts_3d_arr.astype(float),
    )


def run_constrained_triangulation_py(
    plc_points_2d: np.ndarray,
    plc_segments_indices: np.ndarray,
    plc_holes_2d: np.ndarray,
    surface_projection_params: dict,
    original_3d_points_for_plc: np.ndarray,
    config: dict,
):
    import numpy as np
    from Pymeshit.triangle_direct import DirectTriangleWrapper
    from scipy.spatial import Delaunay, cKDTree
    from scipy.interpolate import RBFInterpolator, CloughTocher2DInterpolator

    if plc_points_2d is None or len(plc_points_2d) < 3:
        raise ValueError("Not enough PLC points")
    if plc_segments_indices is None or len(plc_segments_indices) < 3:
        raise ValueError("Not enough PLC segments")

    gradient  = float(config.get('gradient', 2.0))
    min_angle = float(config.get('min_angle', 20.0))
    target_sz = float(config.get('target_size', 20.0))
    interp    = str(config.get('interp', 'Thin Plate Spline (TPS)'))
    smoothing = float(config.get('smoothing', 0.0))

    # clamp target size
    bb_min = np.min(plc_points_2d, axis=0); bb_max = np.max(plc_points_2d, axis=0)
    diagonal = float(np.linalg.norm(bb_max - bb_min))
    if target_sz > diagonal/10.0: target_sz = diagonal/10.0

    tri = DirectTriangleWrapper(gradient=gradient, min_angle=min_angle, base_size=target_sz)
    tri.set_cpp_compatible_mode(True)
    tri_res = tri.triangulate(points=plc_points_2d, segments=plc_segments_indices, holes=plc_holes_2d,
                              uniform=True, create_transition=False, create_feature_points=False)
    if tri_res is None or 'vertices' not in tri_res or 'triangles' not in tri_res:
        raise RuntimeError("Constrained triangulation failed")

    vertices_uv = np.asarray(tri_res['vertices'], float)
    triangles   = np.asarray(tri_res['triangles'], int)

    # projection (use basis exactly as provided)
    proj = surface_projection_params or {}
    centroid = np.asarray(proj.get("centroid"), float)
    basis    = np.asarray(proj.get("basis"), float)
    if basis.shape != (2,3): raise RuntimeError("projection_params['basis'] must be (2,3)")
    ex, ey = basis[0], basis[1]
    ez = proj.get("normal");  ez = np.cross(ex, ey) if ez is None else np.asarray(ez, float)
    ez /= max(np.linalg.norm(ez), 1e-15)

    # local samples (u,v,w)
    P = np.asarray(original_3d_points_for_plc, float)
    C = P - centroid
    sample_xy = np.column_stack([C @ ex, C @ ey])
    sample_w  = C @ ez

    # interpolators in local frame



    def z_idw(q, power=2):
        tree = cKDTree(sample_xy); k = min(64, len(sample_xy))
        d, idx = tree.query(q, k=k)
        if k == 1: d = d[:, None]; idx = idx[:, None]
        r2 = np.maximum(d*d, 1e-24)
        w = 1.0 / (r2**power)   # same as interp_idw
        wsum = np.sum(w, axis=1)
        return np.sum(w * sample_w[idx], axis=1) / wsum

    def z_tps(q):
        try:
            rbf = RBFInterpolator(
                sample_xy, sample_w,
                kernel='thin_plate_spline',
                smoothing=0.0  # C++-equivalent
            )
            return rbf(q)
        except Exception:
            return z_idw(q)





    
    # choose method (Legacy maps to IDW + PLC snap)
    if "Legacy" in interp:
        w_out = z_idw(vertices_uv)
    elif "Thin Plate" in interp:
        w_out = z_tps(vertices_uv)
    elif "IDW" in interp:
        w_out = z_idw(vertices_uv)
    else:
        # Default to IDW for any unrecognized method
        w_out = z_idw(vertices_uv)

    # map back to world
    final_vertices_3d = centroid + np.outer(vertices_uv[:,0], ex) + np.outer(vertices_uv[:,1], ey) + np.outer(w_out, ez)

    # PLC snap (keeps TetGen happy)
    tol_uv = 1e-10
    plc_kd = cKDTree(plc_points_2d)
    dists, nn = plc_kd.query(vertices_uv, k=1)
    snap_mask = dists <= tol_uv
    if np.any(snap_mask):
        final_vertices_3d[snap_mask] = original_3d_points_for_plc[nn[snap_mask]]

    # dedupe + drop degenerates
    def vkey(vec): return (round(vec[0],12), round(vec[1],12), round(vec[2],12))
    uniq_map, uniq_verts, remap = {}, [], {}
    for i, v in enumerate(final_vertices_3d):
        k = vkey(v)
        if k in uniq_map: remap[i] = uniq_map[k]
        else:
            j = len(uniq_verts); uniq_map[k] = j; remap[i] = j; uniq_verts.append(v)
    final_vertices_3d = np.asarray(uniq_verts)
    triangles = np.vectorize(remap.get)(triangles)

    good = []
    for t in triangles:
        if len({int(t[0]),int(t[1]),int(t[2])}) < 3: continue
        a,b,c = final_vertices_3d[t[0]], final_vertices_3d[t[1]], final_vertices_3d[t[2]]
        if 0.5*np.linalg.norm(np.cross(b-a, c-a)) > 1e-12:
            good.append(t)
    triangles = np.asarray(good, int)

    return final_vertices_3d, triangles, []


def _run_basic_triangle_fallback(plc_points_2d, plc_segments_indices, plc_holes_2d, 
                                surface_projection_params, original_3d_points_for_plc, config):
    """PERFORMANCE-OPTIMIZED fallback to basic Triangle library if DirectTriangleWrapper is not available"""
    logger.warning("Using FAST basic Triangle fallback (DirectTriangleWrapper not available)")
    
    import triangle as tr
    tri_input = {"vertices": plc_points_2d, "segments": plc_segments_indices}
    if plc_holes_2d is not None and len(plc_holes_2d) > 0:
        tri_input["holes"] = plc_holes_2d

    # PERFORMANCE: Use fast Triangle options similar to DirectTriangleWrapper
    target_size = config.get('target_size', 20.0)
    min_angle = config.get('min_angle', 20.0)
    area_constraint = target_size * target_size * 0.5
    
    # Simplified fast options - no complex callbacks
    opts = f"pzq{min_angle:.1f}a{area_constraint:.8f}"
    logger.info(f"Running FAST basic triangle with options: {opts}")
    tri_res = tr.triangulate(tri_input, opts=opts)

    vertices_2d = tri_res.get("vertices")
    triangles = tri_res.get("triangles")

    if vertices_2d is None or triangles is None:
        raise RuntimeError("Basic Triangle triangulation failed")

    # Basic 3D reconstruction
    if surface_projection_params is None:
        if vertices_2d.shape[1] == 2:
            final_vertices = np.zeros((len(vertices_2d), 3))
            final_vertices[:, :2] = vertices_2d
        else:
            final_vertices = vertices_2d
    else:
        centroid = np.asarray(surface_projection_params["centroid"])
        basis = np.asarray(surface_projection_params["basis"])
        
        final_vertices = np.zeros((len(vertices_2d), 3))
        for i, v2d in enumerate(vertices_2d):
            final_vertices[i] = centroid + v2d[0] * basis[0] + v2d[1] * basis[1]

    return final_vertices, triangles, []

# Configure logger
#logger = logging.getLogger(__name__)

@dataclass
class ConstraintSegment:
    """Represents a constraint segment with points and properties"""
    points: List[Vector3D]
    constraint_type: str = "UNDEFINED"  # UNDEFINED, SEGMENTS, HOLES
    size: float = 1.0
    rgb: Tuple[int, int, int] = (0, 0, 0)
    object_ids: List[int] = None
    
    def __post_init__(self):
        if self.object_ids is None:
            self.object_ids = []

class GradientControl:
    """Singleton class for gradient control in mesh generation"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            self.gradient = 2.0
            self.base_size = 1.0
            self.point_sizes = {}
            self.initialized = True
    
    def update(self, gradient: float, base_size: float, points_2d: np.ndarray, point_sizes: List[float]):
        """Update gradient control parameters"""
        self.gradient = gradient
        self.base_size = base_size
        
        # Store point-specific sizes
        self.point_sizes = {}
        for i, size in enumerate(point_sizes):
            if i < len(points_2d):
                key = (round(points_2d[i][0], 6), round(points_2d[i][1], 6))
                self.point_sizes[key] = size
    
    def get_size_at_point(self, point_2d: Tuple[float, float]) -> float:
        """Get the mesh size at a specific 2D point"""
        key = (round(point_2d[0], 6), round(point_2d[1], 6))
        return self.point_sizes.get(key, self.base_size)
    
    def apply_gradient_transition(self, points_2d: np.ndarray, sizes: List[float]) -> List[float]:
        """Apply gradient-based size transitions between points"""
        if len(points_2d) != len(sizes):
            return sizes
        
        adjusted_sizes = sizes.copy()
        
        # Apply gradient control between adjacent points
        for i in range(len(points_2d) - 1):
            p1 = points_2d[i]
            p2 = points_2d[i + 1]
            s1 = sizes[i]
            s2 = sizes[i + 1]
            
            distance = np.linalg.norm(p2 - p1)
            
            # Calculate maximum allowed size difference based on gradient
            max_size_diff = distance * self.gradient
            
            # Adjust sizes if they violate gradient constraint
            if abs(s2 - s1) > max_size_diff:
                if s2 > s1:
                    adjusted_sizes[i + 1] = s1 + max_size_diff
                else:
                    adjusted_sizes[i + 1] = s1 - max_size_diff
        
        return adjusted_sizes

def calculate_constraints_for_surface(surface_data: Dict,
                                      intersections_on_surface: List[Dict]
                                      ) -> List[ConstraintSegment]:
    """
    Build ConstraintSegment objects for one surface.

    Enhancements
    ------------
    • Uses surface_data['hull_points'] (refined hull from
      align_intersections_to_convex_hull) when available, otherwise falls
      back to surface_data['convex_hull'].
    • Resamples very long hull edges so that every edge ≈ surface.size.
    • Splits both hull and intersection lines at every non-DEFAULT point
      using split_line_at_special_points().
    """
    logger = logging.getLogger(__name__)
    constraints: List[ConstraintSegment] = []
    rgb = [0, 0, 0]          # simple colour counter ─ R→G→B rollover

    def bump():
        rgb[0] += 1
        if rgb[0] > 255:
            rgb[0] = 0; rgb[1] += 1
            if rgb[1] > 255:
                rgb[1] = 0; rgb[2] = (rgb[2] + 1) % 256

    # ──────────────────────────────────────────────────────────
    # 1.  HULL
    # ──────────────────────────────────────────────────────────
    hull_pts = (surface_data.get("hull_points")
                or surface_data.get("convex_hull")
                or [])
    if hull_pts and len(hull_pts) > 1:
        tgt = surface_data.get("size", 1.0)

        # resample long edges
        resampled = []
        for i in range(len(hull_pts)):
            p1 = hull_pts[i]
            p2 = hull_pts[(i + 1) % len(hull_pts)]
            resampled.append(p1)
            seg_len = (p2 - p1).length()
            if seg_len > tgt * 1.2:
                n = max(1, round(seg_len / tgt))
                step = (p2 - p1) / n
                for k in range(1, n):
                    resampled.append(p1 + step * k)
        hull_pts = clean_identical_points(resampled)

        for seg_pts in split_line_at_special_points(hull_pts, tgt):
            constraints.append(
                ConstraintSegment(points=seg_pts,
                                  constraint_type="SEGMENTS",
                                  size=tgt,
                                  rgb=tuple(rgb))
            )
            bump()

    # ──────────────────────────────────────────────────────────
    # 2.  INTERSECTION LINES
    # ──────────────────────────────────────────────────────────
    for inter in intersections_on_surface:
        pts = inter.get("points", [])
        if len(pts) < 2:
            continue
        size = inter.get("size", surface_data.get("size", 1.0))
        for seg_pts in split_line_at_special_points(pts, size):
            constraints.append(
                ConstraintSegment(points=seg_pts,
                                  constraint_type="SEGMENTS",
                                  size=size,
                                  rgb=tuple(rgb))
            )
            bump()

    logger.info(f"Generated {len(constraints)} constraint segments "
                f"for surface '{surface_data.get('name', '?')}'")
    return constraints

def split_line_at_special_points(points: List[Vector3D], default_size: float) -> List[List[Vector3D]]:
    """
    Split a line at special points (non-DEFAULT types) following C++ logic.
    Enhanced to handle circular/closed loop intersections properly.
    
    This implements the C++ constraint segmentation logic where lines are split
    at points that have special types (TRIPLE_POINT, INTERSECTION_POINT, etc.)
    
    Args:
        points: List of Vector3D points forming a line
        default_size: Default size for points without specific size
        
    Returns:
        List of point lists, each representing a constraint segment
    """
    if len(points) < 2:
        return [points] if points else []
    
    # Check if this is a closed loop (circular intersection)
    is_closed_loop = False
    if len(points) > 2:
        # Handle both Vector3D objects and [x,y,z,type] arrays
        first_point = points[0]
        last_point = points[-1]
        
        # Convert to Vector3D if needed for distance calculation
        if isinstance(first_point, list):
            first_vec = Vector3D(first_point[0], first_point[1], first_point[2])
            last_vec = Vector3D(last_point[0], last_point[1], last_point[2])
            distance_first_to_last = (first_vec - last_vec).length()
            
            # Check for special loop markers in the type field
            last_point_type = last_point[3] if len(last_point) > 3 else "DEFAULT"
        else:
            # Vector3D objects
            distance_first_to_last = (first_point - last_point).length()
            last_point_type = getattr(last_point, 'point_type', getattr(last_point, 'type', "DEFAULT"))
        
        # ENHANCED CIRCULAR DETECTION: Multiple criteria for circular intersections
        
        # Criteria 1: Very close first and last points (mathematical closure)
        close_endpoints = distance_first_to_last < 1e-4
        
        # Criteria 2: Special loop markers from refinement
        has_loop_markers = ("LOOP_END" in last_point_type or "CIRCULAR" in last_point_type or
                           "CIRCULAR_SAMPLE" in last_point_type)
        
        # Criteria 3: Geometric analysis - check if points form a roughly circular path
        is_geometric_circle = False
        if len(points) > 10:  # Need enough points for geometric analysis
            try:
                # Calculate centroid of all points
                if isinstance(points[0], list):
                    coords = [[p[0], p[1], p[2]] for p in points]
                else:
                    coords = [[p.x, p.y, p.z] for p in points]
                
                import numpy as np
                coords_array = np.array(coords)
                centroid = np.mean(coords_array, axis=0)
                
                # Calculate distances from centroid to each point
                distances = [np.linalg.norm(coord - centroid) for coord in coords_array]
                
                # Check if distances are roughly consistent (circular pattern)
                mean_radius = np.mean(distances)
                radius_std = np.std(distances)
                radius_variation = radius_std / mean_radius if mean_radius > 0 else float('inf')
                
                # If variation in radius is small, it's likely a circle
                if radius_variation < 0.2:  # 20% variation tolerance
                    # Additional check: first and last points should be close when projected onto circle
                    first_radius = distances[0]
                    last_radius = distances[-1]
                    if abs(first_radius - last_radius) / mean_radius < 0.1:  # Radii are similar
                        is_geometric_circle = True
                        logger.info(f"SEGMENTATION: Detected geometric circle - radius_variation: {radius_variation:.3f}, mean_radius: {mean_radius:.3f}")
                        
            except Exception as e:
                logger.warning(f"SEGMENTATION: Error in geometric circle detection: {e}")
        
        # Combine all criteria
        is_closed_loop = close_endpoints or has_loop_markers or is_geometric_circle
        
        logger.info(f"SEGMENTATION: Distance first to last: {distance_first_to_last:.6e}, threshold: 1e-4")
        logger.info(f"SEGMENTATION: Close endpoints: {close_endpoints}, Loop markers: {has_loop_markers}, Geometric circle: {is_geometric_circle}")
        
        # Additional check: if we have CIRCULAR_SAMPLE points anywhere in the line, it's likely circular
        if not is_closed_loop:
            for point in points:
                if isinstance(point, list):
                    point_type = point[3] if len(point) > 3 else "DEFAULT"
                else:
                    point_type = getattr(point, 'point_type', getattr(point, 'type', "DEFAULT"))
                
                if "CIRCULAR" in point_type:
                    is_closed_loop = True
                    logger.info(f"SEGMENTATION: Detected circular intersection from point type: {point_type}")
                    break
    
    logger.info(f"SEGMENTATION: Processing {len(points)} points, closed_loop={is_closed_loop}")
    if is_closed_loop:
        logger.info("SEGMENTATION: *** CIRCULAR INTERSECTION DETECTED - Will add closing segment ***")
    
    segments = []
    last_pos = 0
    
    # Iterate through points looking for special points or end of line
    for n in range(1, len(points)):
        point = points[n]
        
        # Handle both Vector3D objects and [x,y,z,type] arrays
        if isinstance(point, list):
            point_type = point[3] if len(point) > 3 else "DEFAULT"
        else:
            point_type = getattr(point, 'point_type', getattr(point, 'type', "DEFAULT"))
        
        # Split at special points or at the end of the line
        if point_type != "DEFAULT" or n == len(points) - 1:
            # Create segment from last_pos to current position (inclusive)
            segment_points = points[last_pos:n+1]
            if len(segment_points) >= 2:
                segments.append(segment_points)
                logger.info(f"SEGMENTATION: Added segment {len(segments)} with {len(segment_points)} points")
            last_pos = n
    
    # CRITICAL FIX: For closed loops, add the closing segment
    if is_closed_loop and len(points) > 2:
        # Create the closing segment from last point back to first point
        # Handle both Vector3D objects and [x,y,z,type] arrays
        if isinstance(points[0], list):
            # For [x,y,z,type] arrays, create Vector3D objects for the closing segment
            last_vec = Vector3D(points[-1][0], points[-1][1], points[-1][2])
            first_vec = Vector3D(points[0][0], points[0][1], points[0][2])
            # Copy type information if available
            if len(points[-1]) > 3:
                last_vec.point_type = points[-1][3]
            if len(points[0]) > 3:
                first_vec.point_type = points[0][3]
            closing_segment = [last_vec, first_vec]
        else:
            # For Vector3D objects, use directly
            closing_segment = [points[-1], points[0]]
        
        segments.append(closing_segment)
        logger.info(f"SEGMENTATION: Added CLOSING segment for circular intersection with {len(closing_segment)} points")
    
    # Handle case where no special points were found
    if not segments and len(points) >= 2:
        segments.append(points)
    
    logger.info(f"SEGMENTATION: Generated {len(segments)} total segments")
    return segments

def calculate_constraint_sizes(constraints: List[ConstraintSegment], 
                             surface_data: Dict, 
                             other_surfaces: List[Dict] = None,
                             polylines: List[Dict] = None) -> None:
    """
    Calculate sizes for constraint segments based on intersecting features.
    
    This implements the C++ calculate_size_of_constraints() logic where
    intersection constraints take the smallest size of intersecting features.
    
    Args:
        constraints: List of constraint segments to update
        surface_data: Current surface data
        other_surfaces: List of other surface data for cross-surface constraints
        polylines: List of polyline data for polyline-surface constraints
    """
    if other_surfaces is None:
        other_surfaces = []
    if polylines is None:
        polylines = []
    
    surface_size = surface_data.get('size', 1.0)
    
    # Update constraint sizes based on intersecting features
    for constraint in constraints:
        min_size = constraint.size
        
        # Check against other surfaces
        for other_surface in other_surfaces:
            other_size = other_surface.get('size', 1.0)
            if constraint_intersects_surface(constraint, other_surface):
                min_size = min(min_size, other_size)
        
        # Check against polylines
        for polyline in polylines:
            polyline_size = polyline.get('size', 1.0)
            if constraint_intersects_polyline(constraint, polyline):
                min_size = min(min_size, polyline_size)
        
        # Update constraint size
        constraint.size = min_size
        
        # Update individual point sizes
        for point in constraint.points:
            if hasattr(point, 'size'):
                point.size = min(point.size, min_size)
            else:
                setattr(point, 'size', min_size)

def constraint_intersects_surface(constraint: ConstraintSegment, surface_data: Dict) -> bool:
    """Check if a constraint intersects with a surface"""
    # Simplified intersection check - in practice this would be more sophisticated
    surface_bounds = surface_data.get('bounds')
    if not surface_bounds or not constraint.points:
        return False
    
    # Check if any constraint points are within surface bounds
    for point in constraint.points:
        if (surface_bounds[0].x <= point.x <= surface_bounds[1].x and
            surface_bounds[0].y <= point.y <= surface_bounds[1].y and
            surface_bounds[0].z <= point.z <= surface_bounds[1].z):
            return True
    
    return False

def constraint_intersects_polyline(constraint: ConstraintSegment, polyline_data: Dict) -> bool:
    """Check if a constraint intersects with a polyline"""
    # Simplified intersection check
    polyline_points = polyline_data.get('points', [])
    if not polyline_points or not constraint.points:
        return False
    
    # Check for point proximity (simplified)
    tolerance = 1e-6
    for c_point in constraint.points:
        for p_point in polyline_points:
            if isinstance(p_point, Vector3D):
                if (c_point - p_point).length() < tolerance:
                    return True
    
    return False

def assign_point_types_and_sizes(points: List[Vector3D], 
                                base_size: float,
                                point_type_sizes: Dict[str, float] = None) -> None:
    """
    Assign sizes to points based on their types following C++ logic.
    
    Args:
        points: List of points to process
        base_size: Base mesh size
        point_type_sizes: Dictionary mapping point types to specific sizes
    """
    if point_type_sizes is None:
        point_type_sizes = {
            "TRIPLE_POINT": base_size * 0.5,
            "INTERSECTION_POINT": base_size * 0.7,
            "CORNER": base_size * 0.8,
            "SPECIAL_POINT": base_size * 0.6,
            "DEFAULT": base_size
        }
    
    for point in points:
        point_type = getattr(point, 'point_type', getattr(point, 'type', "DEFAULT"))
        assigned_size = point_type_sizes.get(point_type, base_size)
        
        # Set size attribute
        if hasattr(point, 'size'):
            point.size = min(point.size, assigned_size)
        else:
            setattr(point, 'size', assigned_size)

def prepare_constrained_triangulation_input(surface_data: Dict, 
        intersections_on_surface: List[Dict],
                                           config: Dict) -> Tuple[np.ndarray, np.ndarray, List[float], np.ndarray]:
    """
    Prepare input for constrained triangulation with protected triple points.
    
    This function implements the C++ calculate_triangles() constraint processing with
    enhanced triple point protection:
    1. Calculate constraint segments
    2. Register protected triple points with high precision
    3. Apply specialized deduplication preserving triple points
    4. Prepare points and segments for triangulation
    
    Args:
        surface_data: Surface data dictionary
        intersections_on_surface: List of intersections on this surface
        config: Configuration dictionary (should include 'triple_points' for protection)
        
    Returns:
        Tuple of (points_2d, segments, point_sizes, holes_2d)
    """
    # DEBUG: Show what we received for constraint processing
    protected_triple_points = config.get('triple_points', [])
    logger.info(f"🔧 CONSTRAINT PROCESSING: Received {len(protected_triple_points)} protected triple points")
    logger.info(f"🔧 CONSTRAINT PROCESSING: Hull points: {len(surface_data.get('hull_points', []))}")
    logger.info(f"🔧 CONSTRAINT PROCESSING: Intersection lines: {len(intersections_on_surface)}")
    
    # Calculate constraint segments
    constraints = calculate_constraints_for_surface(surface_data, intersections_on_surface)
    logger.info(f"🔧 CONSTRAINT PROCESSING: Generated {len(constraints)} constraint segments")
    
    # Calculate constraint sizes
    calculate_constraint_sizes(constraints, surface_data)
    
    # NO DEDUPLICATION - Collect ALL points to preserve every point including triple points
    all_points = []  # List to store ALL points without deduplication
    segments = []
    point_index = 0
    
    logger.info("🔧 CONSTRAINT PROCESSING: Starting point collection WITHOUT deduplication to preserve triple points")
    
    # Process constraints to build point list and segments
    # CRITICAL FIX: C++ uses constraints where Type != "UNDEFINED"
    # We need to mark intersection constraints as "SEGMENTS" not "UNDEFINED"
    for constraint in constraints:
        # Mark intersection constraints as SEGMENTS (not UNDEFINED)
        if len(constraint.points) > 1:
            constraint.constraint_type = "SEGMENTS"  # Mark as active constraint
        
        if constraint.constraint_type == "UNDEFINED":
            continue  # Skip undefined constraints in triangulation
            
        if len(constraint.points) == 1:
            # Single point constraint - add without deduplication
            point = constraint.points[0]
            all_points.append({
                'point': point,
                'size': constraint.size,
                'index': point_index
            })
            point_index += 1
            
        elif len(constraint.points) > 1:
            # Multi-point constraint - add ALL points without deduplication
            # Check if this is a circular constraint (closing segment needed)
            is_circular = False
            if len(constraint.points) > 2:
                first_point = constraint.points[0]
                last_point = constraint.points[-1]
                
                # Check distance between first and last points
                distance = (first_point - last_point).length()
                
                # Check for loop markers from refinement
                last_point_type = getattr(last_point, 'point_type', getattr(last_point, 'type', "DEFAULT"))
                
                # Mark as circular if close distance or special loop markers
                if (distance < 1e-4 or "LOOP_END" in last_point_type or 
                    "CIRCULAR" in last_point_type):
                    is_circular = True
                    logger.info(f"🔄 CIRCULAR CONSTRAINT DETECTED: distance={distance:.6e}, last_type={last_point_type}")
            
            # Process regular segments (i to i+1)
            for i in range(len(constraint.points) - 1):
                p1 = constraint.points[i]
                p2 = constraint.points[i + 1]
                
                # DEBUG: Check if these are triple points
                p1_type = getattr(p1, 'type', 'DEFAULT')
                p2_type = getattr(p2, 'type', 'DEFAULT')
                if p1_type == 'TRIPLE_POINT':
                    logger.info(f"🎯 FOUND TRIPLE POINT in constraint processing: [{p1.x:.6f}, {p1.y:.6f}, {p1.z:.6f}]")
                if p2_type == 'TRIPLE_POINT':
                    logger.info(f"🎯 FOUND TRIPLE POINT in constraint processing: [{p2.x:.6f}, {p2.y:.6f}, {p2.z:.6f}]")
                
                # Add p1 (without checking if it exists)
                p1_index = point_index
                all_points.append({
                    'point': p1,
                    'size': constraint.size,
                    'index': p1_index
                })
                point_index += 1
                
                # Add p2 (without checking if it exists)
                p2_index = point_index
                all_points.append({
                    'point': p2,
                    'size': constraint.size,
                    'index': p2_index
                })
                point_index += 1
                
                # Add segment
                segments.append([p1_index, p2_index])
            
            # CRITICAL FIX: Add closing segment for circular constraints
            if is_circular and len(constraint.points) > 2:
                # Add closing segment from last point back to first point
                last_point = constraint.points[-1]
                first_point = constraint.points[0]
                
                # Add last point
                last_index = point_index
                all_points.append({
                    'point': last_point,
                    'size': constraint.size,
                    'index': last_index
                })
                point_index += 1
                
                # Add first point (as closing point)
                first_index = point_index
                all_points.append({
                    'point': first_point,
                    'size': constraint.size,
                    'index': first_index
                })
                point_index += 1
                
                # Add closing segment
                segments.append([last_index, first_index])
                logger.info(f"🔄 ADDED CLOSING SEGMENT for circular constraint: last->first")
    
    # If no constraints were processed, fall back to convex hull
    if not all_points:
        hull_points = surface_data.get('hull_points', [])
        for i, point in enumerate(hull_points):
            all_points.append({
                'point': point,
                'size': surface_data.get('size', 1.0),
                'index': i
            })
            # Add hull segments (connect sequential points and close the loop)
            if i > 0:
                segments.append([i-1, i])
            if i == len(hull_points) - 1 and len(hull_points) > 2:
                segments.append([i, 0])  # Close the hull
    
    # Convert to arrays - NO DEDUPLICATION
    points_list = []
    sizes_list = []
    
    for point_data in all_points:
        points_list.append(point_data['point'])
        sizes_list.append(point_data['size'])
    
    # Project to 2D
    points_2d = []
    projection_params = surface_data.get('projection_params')
    if projection_params:
        centroid = np.array(projection_params['centroid'])
        basis = np.array(projection_params['basis'])
        for point in points_list:
            centered_pt = np.array([point.x, point.y, point.z]) - centroid
            pt_2d = np.dot(centered_pt, basis.T)
            points_2d.append(pt_2d[:2])
    else:
        for point in points_list:
            points_2d.append([point.x, point.y])
    
    points_2d = np.array(points_2d)
    segments = np.array(segments) if segments else np.empty((0, 2), dtype=int)
    
    # Apply gradient control
    gradient = config.get('gradient', 2.0)
    gc = GradientControl()
    gc.update(gradient, surface_data.get('size', 1.0), points_2d, sizes_list)
    adjusted_sizes = gc.apply_gradient_transition(points_2d, sizes_list)
    
    # Prepare holes (empty for now)
    holes_2d = np.empty((0, 2))
    
    logger.info(f"NO DEDUPLICATION: Prepared constrained triangulation input: {len(points_2d)} points, {len(segments)} segments")
    logger.info(f"ALL POINTS PRESERVED: No points were lost to deduplication")
    
    # DEBUG: Count triple points in final result
    triple_count_final = 0
    for point_data in all_points:
        point = point_data['point']
        if hasattr(point, 'type') and point.type == 'TRIPLE_POINT':
            triple_count_final += 1
            logger.info(f"🎯 TRIPLE POINT in final result: [{point.x:.6f}, {point.y:.6f}, {point.z:.6f}]")
    
    logger.info(f"🎯 FINAL RESULT: {triple_count_final} triple points preserved in triangulation input")
    
    return points_2d, segments, adjusted_sizes, holes_2d

# Add this function after the existing functions

def integrate_constraint_processing_workflow(model, config: Dict = None) -> None:
    """
    Integrate the new constraint processing workflow into the existing MeshIt model.
    
    This function applies the C++ MeshIt constraint processing logic:
    1. Calculate constraints for all surfaces
    2. Apply type-based size assignment
    3. Calculate constraint sizes based on intersections
    4. Apply gradient control
    
    Args:
        model: MeshItModel instance
        config: Configuration dictionary
    """
    if config is None:
        config = {
            'gradient': 2.0,
            'use_constraint_processing': True,
            'type_based_sizing': True,
            'hierarchical_constraints': True
        }
    
    if not config.get('use_constraint_processing', False):
        logger.info("Constraint processing disabled in config")
        return
    
    logger.info("Starting integrated constraint processing workflow")
    
    # Process each surface
    for surface_idx, surface in enumerate(model.surfaces):
        try:
            # Prepare surface data
            surface_data = {
                'hull_points': getattr(surface, 'convex_hull', []),
                'size': getattr(surface, 'size', 1.0),
                'bounds': getattr(surface, 'bounds', None),
                'projection_params': getattr(surface, 'projection_params', None)
            }
            
            # Find intersections on this surface
            intersections_on_surface = []
            for intersection in model.intersections:
                # Check if this surface is involved in the intersection
                if (intersection.id1 == surface_idx or intersection.id2 == surface_idx):
                    intersection_data = {
                        'points': intersection.points,
                        'size': getattr(intersection, 'size', surface_data['size'] * 0.5),
                        'type': getattr(intersection, 'type', 'INTERSECTION')
                    }
                    intersections_on_surface.append(intersection_data)
            
            # Calculate constraints for this surface
            constraints = calculate_constraints_for_surface(surface_data, intersections_on_surface)
            
            # Store constraints on the surface
            if not hasattr(surface, 'constraints'):
                surface.constraints = []
            surface.constraints = constraints
            
            # Apply type-based sizing if enabled
            if config.get('type_based_sizing', False):
                all_points = []
                if hasattr(surface, 'convex_hull'):
                    all_points.extend(surface.convex_hull)
                for intersection_data in intersections_on_surface:
                    all_points.extend(intersection_data['points'])
                
                assign_point_types_and_sizes(all_points, surface_data['size'])
            
            # logger.info(f"Processed constraints for surface {surface_idx}: {len(constraints)} constraint segments")
            
        except Exception as e:
            logger.error(f"Error processing constraints for surface {surface_idx}: {e}")
            continue
    
    # Calculate constraint sizes based on intersections
    if config.get('hierarchical_constraints', False):
        try:
            for surface_idx, surface in enumerate(model.surfaces):
                if hasattr(surface, 'constraints'):
                    surface_data = {
                        'size': getattr(surface, 'size', 1.0),
                        'bounds': getattr(surface, 'bounds', None)
                    }
                    
                    # Prepare other surfaces data
                    other_surfaces = []
                    for other_idx, other_surface in enumerate(model.surfaces):
                        if other_idx != surface_idx:
                            other_surfaces.append({
                                'size': getattr(other_surface, 'size', 1.0),
                                'bounds': getattr(other_surface, 'bounds', None)
                            })
                    
                    # Prepare polylines data if available
                    polylines = []
                    if hasattr(model, 'model_polylines'):
                        for polyline in model.model_polylines:
                            polylines.append({
                                'size': getattr(polyline, 'size', 1.0),
                                'points': getattr(polyline, 'vertices', [])
                            })
                    
                    # Calculate constraint sizes
                    calculate_constraint_sizes(surface.constraints, surface_data, other_surfaces, polylines)
                    
        except Exception as e:
            logger.error(f"Error calculating constraint sizes: {e}")
    
    logger.info("Integrated constraint processing workflow completed")

def update_refinement_with_constraints(intersection, target_length: float, config: Dict = None) -> List[Vector3D]:
    """
    Update intersection refinement to use the new constraint processing logic.
    
    Args:
        intersection: Intersection object to refine
        target_length: Target segment length
        config: Configuration dictionary
        
    Returns:
        List of refined points
    """
    if config is None:
        config = {'gradient': 2.0, 'min_angle': 20.0, 'uniform_meshing': True}
    
    # Use the new refinement function with constraint processing
    refined_points = refine_intersection_line_by_length(
        intersection, 
        target_length, 
        config.get('min_angle', 20.0),
        config.get('uniform_meshing', True)
    )
    
    # Apply type-based sizing
    if config.get('type_based_sizing', True):
        assign_point_types_and_sizes(refined_points, target_length)
    
    return refined_points

def validate_surfaces_for_tetgen(datasets, config=None):
    """
    Validate constrained surfaces to ensure they are ready for tetgen tetrahedralization.
    
    This function performs comprehensive checks on triangulated surfaces to verify:
    - Mesh quality and topology
    - Proper constraint processing
    - Surface intersection handling
    - Tetgen compatibility requirements
    
    Args:
        datasets: List of dataset dictionaries with triangulated surfaces
        config: Configuration dictionary
        
    Returns:
        Dict with validation results and recommendations
    """
    if config is None:
        config = {}
    
    validation_results = {
        'overall_status': 'UNKNOWN',
        'ready_for_tetgen': False,
        'surface_count': len(datasets),
        'surfaces': [],
        'issues': [],
        'recommendations': [],
        'statistics': {}
    }
    
    logger.info("=== TETGEN SURFACE VALIDATION ===")
    
    total_vertices = 0
    total_triangles = 0
    valid_surfaces = 0
    
    for i, dataset in enumerate(datasets):
        surface_name = dataset.get('name', f'Surface_{i}')
        surface_result = {
            'name': surface_name,
            'index': i,
            'status': 'UNKNOWN',
            'vertices': 0,
            'triangles': 0,
            'issues': [],
            'quality_metrics': {}
        }
        
        logger.info(f"Validating surface: {surface_name}")
        
        # Check if surface has triangulation data
        if 'constrained_vertices' not in dataset or 'constrained_triangles' not in dataset:
            surface_result['status'] = 'MISSING_TRIANGULATION'
            surface_result['issues'].append('No constrained triangulation data found')
            validation_results['issues'].append(f'{surface_name}: Missing triangulation data')
        else:
            vertices = dataset['constrained_vertices']
            triangles = dataset['constrained_triangles']
            
            surface_result['vertices'] = len(vertices)
            surface_result['triangles'] = len(triangles)
            total_vertices += len(vertices)
            total_triangles += len(triangles)
            
            # 1. Basic topology checks
            topology_issues = []
            
            # Check minimum requirements
            if len(vertices) < 3:
                topology_issues.append('Insufficient vertices (< 3)')
            if len(triangles) < 1:
                topology_issues.append('No triangles found')
            
            # Check triangle validity
            invalid_triangles = 0
            for tri in triangles:
                if len(tri) != 3:
                    invalid_triangles += 1
                elif max(tri) >= len(vertices):
                    invalid_triangles += 1
            
            if invalid_triangles > 0:
                topology_issues.append(f'{invalid_triangles} invalid triangles (bad indices)')
            
            # 2. Mesh quality checks
            quality_metrics = {}
            
            if len(vertices) > 0 and len(triangles) > 0:
                try:
                    import numpy as np
                    vertices_np = np.array(vertices)
                    
                    # Calculate triangle areas and aspect ratios
                    areas = []
                    aspect_ratios = []
                    min_angles = []
                    
                    for tri in triangles:
                        if max(tri) < len(vertices):
                            v1, v2, v3 = vertices_np[tri[0]], vertices_np[tri[1]], vertices_np[tri[2]]
                            
                            # Triangle area
                            edge1 = v2 - v1
                            edge2 = v3 - v1
                            cross = np.cross(edge1, edge2)
                            area = 0.5 * np.linalg.norm(cross)
                            areas.append(area)
                            
                            # Edge lengths
                            e1_len = np.linalg.norm(edge1)
                            e2_len = np.linalg.norm(v3 - v2)
                            e3_len = np.linalg.norm(edge2)
                            
                            # Aspect ratio (longest edge / shortest edge)
                            edge_lengths = [e1_len, e2_len, e3_len]
                            if min(edge_lengths) > 1e-12:
                                aspect_ratio = max(edge_lengths) / min(edge_lengths)
                                aspect_ratios.append(aspect_ratio)
                            
                            # Minimum angle (using law of cosines)
                            if e1_len > 1e-12 and e2_len > 1e-12 and e3_len > 1e-12:
                                # Angle at vertex 1
                                cos_angle = (e1_len**2 + e3_len**2 - e2_len**2) / (2 * e1_len * e3_len)
                                cos_angle = max(-1, min(1, cos_angle))  # Clamp to valid range
                                angle = np.arccos(cos_angle) * 180 / np.pi
                                min_angles.append(angle)
                    
                    if areas:
                        quality_metrics['min_area'] = min(areas)
                        quality_metrics['max_area'] = max(areas)
                        quality_metrics['avg_area'] = sum(areas) / len(areas)
                        
                        # Check for degenerate triangles
                        degenerate_count = sum(1 for area in areas if area < 1e-12)
                        if degenerate_count > 0:
                            topology_issues.append(f'{degenerate_count} degenerate triangles (area < 1e-12)')
                    
                    if aspect_ratios:
                        quality_metrics['min_aspect_ratio'] = min(aspect_ratios)
                        quality_metrics['max_aspect_ratio'] = max(aspect_ratios)
                        quality_metrics['avg_aspect_ratio'] = sum(aspect_ratios) / len(aspect_ratios)
                        
                        # Check for poor quality triangles
                        poor_quality_count = sum(1 for ar in aspect_ratios if ar > 10.0)
                        if poor_quality_count > 0:
                            topology_issues.append(f'{poor_quality_count} poor quality triangles (aspect ratio > 10)')
                    
                    if min_angles:
                        quality_metrics['min_angle'] = min(min_angles)
                        quality_metrics['max_angle'] = max(min_angles)
                        quality_metrics['avg_min_angle'] = sum(min_angles) / len(min_angles)
                        
                        # Check for very small angles
                        small_angle_count = sum(1 for angle in min_angles if angle < 5.0)
                        if small_angle_count > 0:
                            topology_issues.append(f'{small_angle_count} triangles with very small angles (< 5°)')
                    
                except Exception as e:
                    topology_issues.append(f'Quality analysis failed: {str(e)}')
            
            # 3. Constraint processing validation
            constraint_issues = []
            
            # Check if constraint processing was used
            if 'constraint_processing_used' in dataset:
                if dataset['constraint_processing_used']:
                    logger.info(f'{surface_name}: Constraint processing was used ✓')
                else:
                    constraint_issues.append('Constraint processing was not used')
            else:
                constraint_issues.append('Constraint processing status unknown')
            
            # Check for intersection constraints
            if 'intersection_constraints' in dataset:
                intersection_count = len(dataset['intersection_constraints'])
                if intersection_count > 0:
                    logger.info(f'{surface_name}: {intersection_count} intersection constraints found ✓')
                else:
                    constraint_issues.append('No intersection constraints found')
            
            # 4. Tetgen compatibility checks
            tetgen_issues = []
            
            # Check for manifold surface (each edge shared by at most 2 triangles)
            if len(triangles) > 0:
                edge_count = {}
                for tri in triangles:
                    if max(tri) < len(vertices):
                        edges = [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]
                        for edge in edges:
                            edge_key = tuple(sorted(edge))
                            edge_count[edge_key] = edge_count.get(edge_key, 0) + 1
                
                non_manifold_edges = sum(1 for count in edge_count.values() if count > 2)
                if non_manifold_edges > 0:
                    tetgen_issues.append(f'{non_manifold_edges} non-manifold edges (shared by > 2 triangles)')
                
                boundary_edges = sum(1 for count in edge_count.values() if count == 1)
                quality_metrics['boundary_edges'] = boundary_edges
                quality_metrics['total_edges'] = len(edge_count)
            
            # Combine all issues
            all_issues = topology_issues + constraint_issues + tetgen_issues
            surface_result['issues'] = all_issues
            surface_result['quality_metrics'] = quality_metrics
            
            # Determine surface status
            if not all_issues:
                surface_result['status'] = 'READY'
                valid_surfaces += 1
                logger.info(f'{surface_name}: READY for tetgen ✓')
            elif len(topology_issues) == 0 and len(tetgen_issues) == 0:
                surface_result['status'] = 'WARNING'
                logger.warning(f'{surface_name}: Has warnings but may work with tetgen')
            else:
                surface_result['status'] = 'ERROR'
                logger.error(f'{surface_name}: Has critical issues, not ready for tetgen')
            
            # Log quality metrics
            if quality_metrics:
                logger.info(f'{surface_name} quality: vertices={len(vertices)}, triangles={len(triangles)}')
                if 'avg_aspect_ratio' in quality_metrics:
                    logger.info(f'  Aspect ratio: avg={quality_metrics["avg_aspect_ratio"]:.2f}, max={quality_metrics["max_aspect_ratio"]:.2f}')
                if 'avg_min_angle' in quality_metrics:
                    logger.info(f'  Min angles: avg={quality_metrics["avg_min_angle"]:.1f}°, min={quality_metrics["min_angle"]:.1f}°')
        
        validation_results['surfaces'].append(surface_result)
    
    # Overall validation summary
    validation_results['statistics'] = {
        'total_vertices': total_vertices,
        'total_triangles': total_triangles,
        'valid_surfaces': valid_surfaces,
        'surfaces_with_warnings': sum(1 for s in validation_results['surfaces'] if s['status'] == 'WARNING'),
        'surfaces_with_errors': sum(1 for s in validation_results['surfaces'] if s['status'] == 'ERROR')
    }
    
    # Determine overall status
    if valid_surfaces == len(datasets) and len(datasets) > 0:
        validation_results['overall_status'] = 'READY'
        validation_results['ready_for_tetgen'] = True
        logger.info("=== ALL SURFACES READY FOR TETGEN ✓ ===")
    elif valid_surfaces > 0:
        validation_results['overall_status'] = 'PARTIAL'
        validation_results['ready_for_tetgen'] = False
        logger.warning(f"=== PARTIAL READINESS: {valid_surfaces}/{len(datasets)} surfaces ready ===")
    else:
        validation_results['overall_status'] = 'NOT_READY'
        validation_results['ready_for_tetgen'] = False
        logger.error("=== SURFACES NOT READY FOR TETGEN ===")
    
    # Generate recommendations
    recommendations = []
    if validation_results['statistics']['surfaces_with_errors'] > 0:
        recommendations.append("Fix critical topology and manifold issues before tetgen")
    if validation_results['statistics']['surfaces_with_warnings'] > 0:
        recommendations.append("Review constraint processing warnings")
    if total_vertices < 10:
        recommendations.append("Consider refining surfaces for better tetgen results")
    if validation_results['ready_for_tetgen']:
        recommendations.append("Surfaces are ready for tetgen tetrahedralization")
    
    validation_results['recommendations'] = recommendations
    
    return validation_results



def prepare_constrained_triangulation_input(surface_data: Dict,
                                           intersections_on_surface: List[Dict],
                                           config: Dict) -> Tuple[np.ndarray, np.ndarray, List[float], np.ndarray]:
    """
    Prepare input for constrained triangulation following C++ MeshIt logic.
    
    This function implements the C++ calculate_triangles() constraint processing:
    1. Calculate constraint segments
    2. Assign sizes based on constraint types and intersections
    3. Apply gradient control
    4. Prepare points and segments for triangulation
    
    Args:
        surface_data: Surface data dictionary
        intersections_on_surface: List of intersections on this surface
        config: Configuration dictionary
        
    Returns:
        Tuple of (points_2d, segments, point_sizes, holes_2d)
    """
    # Calculate constraint segments
    constraints = calculate_constraints_for_surface(surface_data, intersections_on_surface)
    
    # Calculate constraint sizes
    calculate_constraint_sizes(constraints, surface_data)
    
    # Collect all unique points and their properties
    unique_points = {}  # Dict to store unique points with their properties
    segments = []
    point_sizes = []
    
    # Process constraints to build point list and segments
    # CRITICAL FIX: C++ uses constraints where Type != "UNDEFINED"
    # We need to mark intersection constraints as "SEGMENTS" not "UNDEFINED"
    for constraint in constraints:
        # Mark intersection constraints as SEGMENTS (not UNDEFINED)
        if len(constraint.points) > 1:
            constraint.constraint_type = "SEGMENTS"  # Mark as active constraint
        
        if constraint.constraint_type == "UNDEFINED":
            continue  # Skip undefined constraints in triangulation
            
        if len(constraint.points) == 1:
            # Single point constraint
            point = constraint.points[0]
            point_key = (round(point.x, 8), round(point.y, 8), round(point.z, 8))
            if point_key not in unique_points:
                unique_points[point_key] = {
                    'point': point,
                    'size': constraint.size,
                    'index': len(unique_points)
                }
        elif len(constraint.points) > 1:
            # Multi-point constraint - create segments
            for i in range(len(constraint.points) - 1):
                p1 = constraint.points[i]
                p2 = constraint.points[i + 1]
                
                # Add points to unique collection
                p1_key = (round(p1.x, 8), round(p1.y, 8), round(p1.z, 8))
                p2_key = (round(p2.x, 8), round(p2.y, 8), round(p2.z, 8))
                
                if p1_key not in unique_points:
                    unique_points[p1_key] = {
                        'point': p1,
                        'size': constraint.size,
                        'index': len(unique_points)
                    }
                
                if p2_key not in unique_points:
                    unique_points[p2_key] = {
                        'point': p2,
                        'size': constraint.size,
                        'index': len(unique_points)
                    }
                
                # Add segment
                idx1 = unique_points[p1_key]['index']
                idx2 = unique_points[p2_key]['index']
                segments.append([idx1, idx2])
    
    # If no constraints were processed, fall back to convex hull
    if not unique_points:
        hull_points = surface_data.get('hull_points', [])
        for i, point in enumerate(hull_points[:-1]):  # Exclude last point if it's duplicate of first
            point_key = (round(point.x, 8), round(point.y, 8), round(point.z, 8))
            unique_points[point_key] = {
                'point': point,
                'size': surface_data.get('size', 1.0),
                'index': i
            }
            # Add hull segments
            if i < len(hull_points) - 2:
                segments.append([i, i + 1])
            else:
                segments.append([i, 0])  # Close the hull
    
    # Convert to arrays
    points_list = [None] * len(unique_points)
    sizes_list = [0.0] * len(unique_points)
    
    for point_data in unique_points.values():
        idx = point_data['index']
        points_list[idx] = point_data['point']
        sizes_list[idx] = point_data['size']
    
    # Project to 2D
    points_2d = []
    projection_params = surface_data.get('projection_params')
    if projection_params:
        centroid = np.array(projection_params['centroid'])
        basis = np.array(projection_params['basis'])
        for point in points_list:
            centered_pt = np.array([point.x, point.y, point.z]) - centroid
            pt_2d = np.dot(centered_pt, basis.T)
            points_2d.append(pt_2d[:2])
    else:
        for point in points_list:
            points_2d.append([point.x, point.y])
    
    points_2d = np.array(points_2d)
    segments = np.array(segments) if segments else np.empty((0, 2), dtype=int)
    
    # Apply gradient control
    gradient = config.get('gradient', 2.0)
    gc = GradientControl()
    gc.update(gradient, surface_data.get('size', 1.0), points_2d, sizes_list)
    adjusted_sizes = gc.apply_gradient_transition(points_2d, sizes_list)
    
    # Prepare holes (empty for now)
    holes_2d = np.empty((0, 2))
    
    logger.info(f"Prepared constrained triangulation input: {len(points_2d)} points, {len(segments)} segments")
    
    return points_2d, segments, adjusted_sizes, holes_2d