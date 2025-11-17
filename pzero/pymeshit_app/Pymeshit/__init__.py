"""
PyMeshit - Complete mesh generation and manipulation package with GUI

This package provides a comprehensive solution for mesh generation and manipulation,
including a graphical user interface for the complete workflow.
"""

import sys  # Import sys for error handling

# Define main_wrapper early to ensure it's always available
def main_wrapper():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QSplashScreen
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import Qt
    import os, sys

    app = QApplication(sys.argv)  # MUST be first

    from Pymeshit_workflow_gui import MeshItWorkflowGUI  # import GUI after app

    # optional: icon/splash
    icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'images', 'app_logo_small.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    splash_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'images', 'app_logo.png')
    pixmap = QPixmap(splash_path) if os.path.exists(splash_path) else QPixmap(400, 300)
    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.show(); app.processEvents()

    window = MeshItWorkflowGUI()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())

# Import core components with fallback
try:
    from .core import (
        MeshItModel,
        Vector3D,
        Surface,
        Polyline,
        create_surface,
        create_polyline,
        Triangle,
        Intersection,
        TriplePoint,
        GradientControl,
    )
except ImportError as e:
    print(f"Warning: Could not import core components: {e}", file=sys.stderr)
    print("Using Python fallback implementations", file=sys.stderr)

    # Minimal fallback classes
    class MeshItModel:
        def __init__(self):
            self.surfaces = []
            self.model_polylines = []
        def __str__(self):
            return "MeshItModel(fallback)"

    class Vector3D:
        def __init__(self, x=0, y=0, z=0):
            self.x, self.y, self.z = x, y, z

    class Surface:
        def __init__(self, points=None, edges=None, name="Surface", stype="Scattered"):
            self.vertices = points or []
            self.triangles = []
            self.name = name

    class Polyline:
        def __init__(self, points=None, name="Polyline"):
            self.vertices = points or []
            self.segments = []
            self.name = name

    def create_surface(points, edges, name="Surface", stype="Scattered"):
        return Surface(points, edges, name, stype)

    def create_polyline(points, name="Polyline"):
        return Polyline(points, name)

    class Triangle:
        def __init__(self, v1, v2, v3):
            self.v1, self.v2, self.v3 = v1, v2, v3

    class Intersection:
        def __init__(self, id1, id2, is_polyline_mesh=False):
            self.id1, self.id2 = id1, id2
            self.is_polyline_mesh = is_polyline_mesh
            self.points = []

    class TriplePoint:
        def __init__(self, point):
            self.point = point
            self.intersection_ids = []

    class GradientControl:
        _instance = None
        def __new__(cls):
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

# Try to import our direct Triangle wrapper (Python-only)
try:
    from . import triangle_direct
    HAS_DIRECT_TRIANGLE = True
except ImportError:
    HAS_DIRECT_TRIANGLE = False

# Define version
__version__ = '0.2.0'

# Helper functions for adding geometries to a model
def add_surface_to_model(model, surface):
    """Add a surface to a MeshItModel instance.
    
    Args:
        model: A MeshItModel instance
        surface: A Surface instance to add
    """
    try:
        model.surfaces = list(model.surfaces) + [surface]
    except Exception as e:
        print(f"Warning: Failed to add surface to model: {e}", file=sys.stderr)
    
def add_polyline_to_model(model, polyline):
    """Add a polyline to a MeshItModel instance.
    
    Args:
        model: A MeshItModel instance
        polyline: A Polyline instance to add
    """
    try:
        model.model_polylines = list(model.model_polylines) + [polyline]
    except Exception as e:
        print(f"Warning: Failed to add polyline to model: {e}", file=sys.stderr)

# Helper functions for accessing model results
def get_intersections(model):
    """Get the intersections from a MeshItModel instance.
    
    Args:
        model: A MeshItModel instance
    
    Returns:
        A list of Intersection objects or an empty list if not available
    """
    try:
        return model.intersections
    except AttributeError:
        return []

def get_triple_points(model):
    """Get the triple points from a MeshItModel instance.
    
    Args:
        model: A MeshItModel instance
    
    Returns:
        A list of TriplePoint objects or an empty list if not available
    """
    try:
        return model.triple_points
    except AttributeError:
        return []

def compute_convex_hull(points):
    """Compute the convex hull of a set of 3D points.
    
    Args:
        points: A list of 3D points, where each point is a list of 3 coordinates [x, y, z]
    
    Returns:
        A list of 3D points representing the convex hull
    """
    try:
        # Create a surface from the points
        surface = create_surface(points, [], "TempSurface", "Scattered")
        
        # Calculate the convex hull
        surface.calculate_convex_hull()
        
        # Convert the convex hull points to a list of lists
        hull_points = []
        for point in surface.convex_hull:
            hull_points.append([point.x, point.y, point.z])
        
        return hull_points
    except Exception as e:
        print(f"Warning: Failed to compute convex hull: {e}", file=sys.stderr)
        
        # Fall back to scipy for convex hull if available
        try:
            import numpy as np
            from scipy.spatial import ConvexHull
            
            points_array = np.array(points)
            if points_array.shape[1] == 3:  # 3D points
                hull = ConvexHull(points_array)
                return points_array[hull.vertices].tolist()
            return []
        except ImportError:
            return []

# Duplicate main_wrapper function removed

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
    'add_surface_to_model',
    'add_polyline_to_model',
    'get_intersections',
    'get_triple_points',
    'compute_convex_hull',
    'main_wrapper'
]
