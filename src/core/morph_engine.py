"""
Morph engine
  • morph_blend   : smooth A→B interpolation
  • apply_all_deforms : per-part sliders
"""
import numpy as np
import trimesh
from scipy.spatial import cKDTree


# ── Part definitions (normalised 0-1 bounding box coords) ────────────────────
# X = width, Y = length (front=low Y), Z = height (top=high Z)

PARTS = {
    "front":   {"y": (0.00, 0.28)},
    "back":    {"y": (0.72, 1.00)},
    "left":    {"x": (0.00, 0.35)},
    "right":   {"x": (0.65, 1.00)},
    "top":     {"z": (0.62, 1.00)},
    "buttons": {"y": (0.00, 0.42), "z": (0.52, 1.00)},
    "thumb":   {"x": (0.00, 0.32), "z": (0.12, 0.68)},
}

PART_LIMITS = {
    "width":  (0.80, 1.25),
    "height": (0.75, 1.30),
    "length": (0.85, 1.20),
    "flare":  (-0.15, 0.15),
    "curve":  (-0.20, 0.20),
}


# ── Smooth morph A → B ────────────────────────────────────────────────────────

def morph_blend(mesh_a: trimesh.Trimesh,
                mesh_b: trimesh.Trimesh,
                t: float) -> trimesh.Trimesh:
    """
    Blend mesh_a → mesh_b at parameter t ∈ [0, 1].

    Improvements over naive nearest-neighbour:
      1. Mutual KDTree: each B-vertex finds its nearest A-vertex
         AND each A-vertex finds its nearest B-vertex; we use the
         B→A direction for blending so the result keeps B's topology.
      2. After blending, one pass of Laplacian smoothing removes
         surface noise caused by imperfect correspondence.
    """
    t = float(np.clip(t, 0.0, 1.0))
    if t == 0.0:
        return mesh_a.copy()
    if t == 1.0:
        return mesh_b.copy()

    # ── Step 1: find A-position for every B-vertex (B topology kept) ──────
    tree_a = cKDTree(mesh_a.vertices)
    _, idx  = tree_a.query(mesh_b.vertices, workers=-1)
    a_mapped = mesh_a.vertices[idx]           # A verts in B-vertex order

    # ── Step 2: smooth the A positions a little before blending ───────────
    #   This smears out quantisation artefacts from the NN lookup.
    a_smooth = _laplacian_smooth_verts(a_mapped, mesh_b.faces, iterations=2)

    # ── Step 3: linear blend ──────────────────────────────────────────────
    blended = (1.0 - t) * a_smooth + t * mesh_b.vertices

    # ── Step 4: light post-blend smoothing for silky transitions ──────────
    blended = _laplacian_smooth_verts(blended, mesh_b.faces, iterations=1)

    result = mesh_b.copy()
    result.vertices = blended
    return result


def _laplacian_smooth_verts(verts: np.ndarray,
                             faces: np.ndarray,
                             iterations: int = 1,
                             lam: float = 0.5) -> np.ndarray:
    """
    Fast in-memory Laplacian smoothing (vertex-averaging).
    lam = blend factor towards neighbour average (0=no change, 1=full).
    """
    n = len(verts)
    # Build edge list from faces
    edges = np.vstack([
        faces[:, [0, 1]],
        faces[:, [1, 2]],
        faces[:, [2, 0]],
        faces[:, [1, 0]],
        faces[:, [2, 1]],
        faces[:, [0, 2]],
    ])

    v = verts.copy()
    for _ in range(iterations):
        # Sum neighbour positions
        sums   = np.zeros_like(v)
        counts = np.zeros(n, dtype=np.float32)
        np.add.at(sums,   edges[:, 0], v[edges[:, 1]])
        np.add.at(counts, edges[:, 0], 1)
        counts = np.maximum(counts, 1)[:, None]
        neighbour_avg = sums / counts
        v = v * (1.0 - lam) + neighbour_avg * lam
    return v


# ── Part mask helpers ─────────────────────────────────────────────────────────

def _norm01(verts):
    mn = verts.min(axis=0); mx = verts.max(axis=0)
    ext = mx - mn; ext[ext == 0] = 1.0
    return (verts - mn) / ext, mn, ext


def _part_mask(vn, key):
    spec = PARTS[key]
    ax   = {"x": 0, "y": 1, "z": 2}
    mask = np.ones(len(vn), bool)
    for a, (lo, hi) in spec.items():
        mask &= (vn[:, ax[a]] >= lo) & (vn[:, ax[a]] <= hi)
    return mask


def _weight_mask(verts, hard_mask, radius=0.18):
    w = hard_mask.astype(float)
    if hard_mask.sum() in (0, len(verts)):
        return w
    tree = cKDTree(verts[hard_mask])
    dists, _ = tree.query(verts[~hard_mask], workers=-1)
    span = (verts.max(0) - verts.min(0)).max()
    w[~hard_mask] = np.clip(1.0 - dists / (span * radius), 0.0, 1.0)
    return w


# ── Per-part deformation ──────────────────────────────────────────────────────

def apply_part_deform(mesh: trimesh.Trimesh,
                      part_key: str,
                      dim: str,
                      value: float) -> trimesh.Trimesh:
    lo, hi = PART_LIMITS[dim]
    value  = float(np.clip(value, lo, hi))

    verts = mesh.vertices.copy()
    vn, mn, ext = _norm01(verts)
    hard  = _part_mask(vn, part_key)
    w     = _weight_mask(verts, hard)

    c = verts[hard].mean(axis=0) if hard.any() else verts.mean(axis=0)

    if dim == "width":
        verts[:, 0] += (verts[:, 0] - c[0]) * (value - 1.0) * w
    elif dim == "height":
        verts[:, 2] += (verts[:, 2] - c[2]) * (value - 1.0) * w
    elif dim == "length":
        verts[:, 1] += (verts[:, 1] - c[1]) * (value - 1.0) * w
    elif dim == "flare":
        cx   = verts[:, 0].mean()
        sign = np.sign(verts[:, 0] - cx)
        verts[:, 0] += sign * value * ext[0] * w
    elif dim == "curve":
        yn = (verts[:, 1] - verts[:, 1].min()) / \
             (verts[:, 1].max() - verts[:, 1].min() + 1e-9)
        verts[:, 2] += value * ext[2] * 4.0 * yn * (1.0 - yn) * w

    result = mesh.copy()
    result.vertices = verts
    return result


def apply_all_deforms(mesh: trimesh.Trimesh, state: dict) -> trimesh.Trimesh:
    for (part, dim), val in state.items():
        default = 1.0 if dim in ("width", "height", "length") else 0.0
        if abs(val - default) > 1e-6:
            mesh = apply_part_deform(mesh, part, dim, val)
    return mesh
