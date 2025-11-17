# This file is intentionally empty to make the directory a Python package

"""
Core C++ bindings for MeshIt
"""

try:
    from ._meshit import (
        MeshItModel,
        Vector3D,
        Surface,
        Polyline,
        create_surface,
        create_polyline,
        Triangle,
        Intersection,
        TriplePoint,
        GradientControl
    )
except ImportError as e:
    import sys
    print(f"Warning: C++ extensions not available: {e}", file=sys.stderr)
    print("Using Python fallback implementations", file=sys.stderr)

    # Provide dummy classes when C++ extensions are not available
    class Vector3D:
        def __init__(self, x=0, y=0, z=0):
            self.x, self.y, self.z = x, y, z

        def __repr__(self):
            return f"Vector3D({self.x}, {self.y}, {self.z})"

    class Surface:
        def __init__(self, points=None, edges=None, name="Surface", stype="Scattered"):
            self.points = points or []
            self.edges = edges or []
            self.name = name
            self.stype = stype
            self.convex_hull = []

        def calculate_convex_hull(self):
            # Dummy implementation
            self.convex_hull = [Vector3D(*p) for p in self.points[:min(10, len(self.points))]]

    class GradientControl:
        def __init__(self):
            pass

    class Polyline:
        def __init__(self, points=None, name="Polyline"):
            self.points = points or []
            self.name = name

    class Triangle:
        def __init__(self, v1=None, v2=None, v3=None):
            self.v1, self.v2, self.v3 = v1, v2, v3

    class Intersection:
        def __init__(self):
            self.points = []

    class TriplePoint:
        def __init__(self):
            self.position = Vector3D()

    class MeshItModel:
        def __init__(self):
            self.surfaces = []
            self.model_polylines = []
            self.intersections = []
            self.triple_points = []

        def __str__(self):
            return f"MeshItModel(surfaces: {len(self.surfaces)}, polylines: {len(self.model_polylines)})"

    def create_surface(points, edges=None, name="Surface", stype="Scattered"):
        return Surface(points, edges, name, stype)

    def create_polyline(points, name="Polyline"):
        return Polyline(points, name)

__all__ = [
    'MeshItModel',
    'Vector3D',
    'Surface',
    'Polyline',
    'create_surface',
    'create_polyline',
    'Triangle',
    'Intersection',
    'TriplePoint',
    'GradientControl'
]
