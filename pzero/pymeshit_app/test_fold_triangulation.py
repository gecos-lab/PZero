
import numpy as np
import sys
import os
import logging

# Setup logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test_debug.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("TestFold")

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Pymeshit.triangle_direct import DirectTriangleWrapper

def create_recumbent_fold():
    """
    Create a 'sandwich' fold points data.
    Top limb: Z=1, X=0..1
    Bottom limb: Z=0, X=0..1
    Hinge: Connects X=1 ends.
    """
    points = []
    ys = np.linspace(0, 1, 10)
    
    # Top limb
    logger.info("Generating Top Limb...")
    for x in np.linspace(0, 1, 20):
        for y in ys:
            points.append([x, y, 1.0])
            
    # Bottom limb
    logger.info("Generating Bottom Limb...")
    for x in np.linspace(0, 1, 20):
        for y in ys:
            points.append([x, y, 0.0])
            
    # Hinge (Bulge out in +X)
    logger.info("Generating Hinge...")
    # Angles from pi/2 (Top) to -pi/2 (Bottom)
    thetas = np.linspace(np.pi/2, -np.pi/2, 20) 
    
    for t in thetas:
        # z goes 1.0 -> 0.0
        # x goes 1.0 -> 1.5 -> 1.0
        x_val = 1.0 + 0.5 * np.cos(t) # cos(pi/2)=0, cos(0)=1 -> Max bulge at Z=0.5
        z_val = 0.5 + 0.5 * np.sin(t)
        
        # Avoid duplicating the exact start/end points of limbs to prevent zero-area issues
        if abs(t - np.pi/2) < 0.1 or abs(t + np.pi/2) < 0.1:
            continue
            
        for y in ys:
            points.append([x_val, y, z_val])
            
    pts = np.array(points)
    # Add some noise to avoid perfect alignment issues
    pts += np.random.normal(0, 0.005, pts.shape)
    
    return pts

def test_fold_triangulation():
    logger.info("Starting Fold Triangulation Test")
    
    points = create_recumbent_fold()
    logger.info(f"Generated {len(points)} points")
    
    wrapper = DirectTriangleWrapper(base_size=0.1)
    
    logger.info("--- Testing _compute_local_normals ---")
    normals = wrapper._compute_local_normals(points, k=15)
    
    if normals is None:
        logger.error("FAIL: Normals computation returned None")
        return
    
    # Check consistency
    top_points_mask = points[:, 2] > 0.8
    bottom_points_mask = points[:, 2] < 0.2
    
    avg_top_normal = np.mean(normals[top_points_mask], axis=0) # Should be roughly (0,0,1)
    avg_bot_normal = np.mean(normals[bottom_points_mask], axis=0) # Should be roughly (0,0,-1)
    
    logger.info(f"Avg Top Normal: {avg_top_normal}")
    logger.info(f"Avg Bottom Normal: {avg_bot_normal}")
    
    # In a consistent orientation, they should be opposite or at least consistently flow
    # If the surface is oriented "outwards", Top -> +Z, Bottom -> -Z.
    # Dot product should be negative approx -1.
    
    dot_check = np.dot(avg_top_normal, avg_bot_normal)
    logger.info(f"Dot product of Top/Bottom normals: {dot_check}")
    
    if dot_check > 0.5:
        logger.warning("WARNING: Normals seem to point in same direction (Validation might fail if we expected closed surface orientation)")
    
    logger.info("--- Testing _detect_fold_regions ---")
    # Use strict threshold
    regions = wrapper._detect_fold_regions(points, normals, angle_threshold=80.0)
    logger.info(f"Detected Regions: {len(regions)}")
    
    for i, r in enumerate(regions):
        logger.info(f"Region {i}: {len(r)} points")
        
    if len(regions) < 2:
        logger.warning("WARNING: Only 1 region detected. Expecting at least 2 or 3 for recumbent fold.")

    logger.info("--- Testing triangulate_folded_surface ---")
    result = wrapper.triangulate_folded_surface(points, fold_angle_threshold=80.0)
    
    if result and 'vertices' in result and 'triangles' in result:
        n_tris = len(result['triangles'])
        n_verts = len(result['vertices'])
        logger.info(f"SUCCESS: Triangulation created {n_tris} triangles and {n_verts} vertices.")
        
        # Validate vertices count (should be close to input, maybe more due to refinement)
        if n_verts < len(points) * 0.5:
             logger.warning("WARNING: Result has significantly fewer vertices than input!")
    else:
        logger.error("FAIL: Triangulation returned empty or invalid result.")

if __name__ == "__main__":
    test_fold_triangulation()
