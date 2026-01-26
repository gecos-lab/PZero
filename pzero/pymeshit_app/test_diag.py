
import numpy as np
import triangle as tr
import sys
import os

print("--- DIAGNOSTIC V2 ---")

pts = np.array([[0,0], [10,0], [0,10]])

def try_opt(opts):
    print(f"Testing options: '{opts}'")
    try:
        if opts is None:
            res = tr.triangulate({'vertices': pts})
        else:
            res = tr.triangulate({'vertices': pts}, opts)
        
        if 'triangles' in res and len(res['triangles']) > 0:
            print(f"  SUCCESS: {len(res['triangles'])} tris")
        else:
            print(f"  FAIL: No triangles. Keys: {res.keys()}")
    except Exception as e:
        print(f"  ERROR: {e}")

try_opt(None) # Delaunay
try_opt('z')  # 0-indexed
try_opt('p')  # PSLG
try_opt('pz') # PSLG + 0-indexed
try_opt('pza10.0') # PSLG + Area

print("\n--- Project Check ---")
# Check if we can import the Pymeshit module correctly
try:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from Pymeshit.triangle_direct import DirectTriangleWrapper
    print("DirectTriangleWrapper imported.")
    wrapper = DirectTriangleWrapper()
    print("Wrapper instantiated.")
except Exception as e:
    print(f"Wrapper check failed: {e}")
