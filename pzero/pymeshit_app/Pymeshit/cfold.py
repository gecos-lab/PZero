import numpy as np

def c_fold_surface(
    nx=200,
    ny=50,
    length=200,
    width=80,
    A=30,
    B=40,
    C=0.15,
    k=2*np.pi/120
):
    s = np.linspace(-length/2, length/2, nx)
    w = np.linspace(-width/2, width/2, ny)

    points = []

    for wi in w:
        for si in s:
            x = si
            y = A * np.sin(k * si) + wi
            z = B * np.cos(k * si) - C * si
            points.append([x, y, z])

    return np.array(points)

pts = c_fold_surface()
np.savetxt("c_fold_middle.dat", pts, fmt="%.4f")
def isoclinal_fold(
    nx=250,
    ny=60,
    wavelength=100,
    amplitude=50,
    thickness=25
):
    x = np.linspace(-150, 150, nx)
    y = np.linspace(-thickness, thickness, ny)

    points = []
    for yi in y:
        for xi in x:
            z = amplitude * np.sin(2*np.pi*xi/wavelength)
            z += 0.03 * xi  # tilt
            points.append([xi, yi, z])

    return np.array(points)

np.savetxt("isoclinal_fold.dat", isoclinal_fold(), fmt="%.4f")
