import trimesh
import numpy as np
from pathlib import Path

# STL_ROOT: env var > project data/stl > Desktop fallback
import os as _os
_project_root = Path(__file__).resolve().parents[2]
ORIGINAL_ROOT = Path(
    _os.environ.get("STL_ROOT")
    or (_project_root / "data" / "stl")
    if (_project_root / "data" / "stl").exists() and any((_project_root / "data" / "stl").rglob("*.stl"))
    else "/Users/mac/Desktop/all model"
)

# Face count for real-time display (fast morph / rendering)
DISPLAY_FACES = 5000
# Face count kept for STL export
EXPORT_FACES  = None   # None = full resolution


def get_all_mice():
    """Return [(display_name, filepath), ...] sorted by brand/name."""
    mice = []
    seen = set()
    if ORIGINAL_ROOT.exists():
        for p in sorted(ORIGINAL_ROOT.rglob("*.stl")) + \
                 sorted(ORIGINAL_ROOT.rglob("*.STL")):
            key = p.stem.lower()
            if key in seen:
                continue
            seen.add(key)
            mice.append((p.stem, str(p)))
    return mice


def _align_axes(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Rotate mesh so:  X=width  Y=length(front→back)  Z=height(up)."""
    extents = mesh.bounding_box.extents          # [ex, ey, ez]
    order   = np.argsort(extents)                # smallest → largest
    # smallest extent → Z (height), largest → Y (length), mid → X (width)
    desired = [order[1], order[2], order[0]]     # new X, Y, Z source axes
    rot = np.zeros((3, 3))
    for new_ax, src_ax in enumerate(desired):
        rot[new_ax, src_ax] = 1.0
    mesh.vertices = mesh.vertices @ rot.T
    return mesh


def load_mesh(filepath: str,
              display: bool = True) -> trimesh.Trimesh:
    """
    Load & clean an STL.
    display=True  → decimate to DISPLAY_FACES for fast rendering/morphing
    display=False → full resolution for export
    """
    mesh = trimesh.load(filepath, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(list(mesh.geometry.values()))

    trimesh.repair.fix_winding(mesh)
    trimesh.repair.fill_holes(mesh)

    # Centre
    mesh.vertices -= mesh.bounding_box.centroid

    # Align axes to canonical orientation
    mesh = _align_axes(mesh)

    # Scale so longest axis ≈ 130 mm
    scale = 130.0 / mesh.bounding_box.extents.max()
    mesh.vertices *= scale

    # Decimate for display
    if display and len(mesh.faces) > DISPLAY_FACES:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=DISPLAY_FACES)
        except Exception:
            pass   # fallback: use full mesh

    return mesh


def export_stl(mesh: trimesh.Trimesh, filepath: str):
    mesh.export(filepath)
