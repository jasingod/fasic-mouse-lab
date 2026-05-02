"""
FASIC Mouse Shape Lab — Flask server
Run: python server.py
"""
import sys, os, io, struct, threading, webbrowser, time
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from flask import Flask, jsonify, request, send_file, Response

from src.core.mesh_loader import get_all_mice, load_mesh
from src.core.morph_engine import morph_blend, apply_all_deforms

app = Flask(__name__, static_folder="web", static_url_path="")

# ── Mesh cache ────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()

def _get(path: str):
    with _cache_lock:
        if path not in _cache:
            _cache[path] = load_mesh(path, display=True)
        return _cache[path]   # return reference — callers must .copy() if mutating

# ── Prepare cache (A_idx, B_idx) → binary payload ────────────────────────────
_prepare_cache: dict = {}
_prepare_lock  = threading.Lock()

# ── Binary mesh format ────────────────────────────────────────────────────────
def _to_binary(mesh):
    verts = mesh.vertices.astype(np.float32)
    faces = mesh.faces.astype(np.uint32)
    header = struct.pack('<II', len(verts), len(faces))
    return header + verts.tobytes() + faces.tobytes()

# ── Pre-warm: load all meshes in background so first request is fast ──────────
def _prewarm():
    mice = get_all_mice()
    print(f"[prewarm] Loading {len(mice)} meshes…", flush=True)
    for i, (name, path) in enumerate(mice):
        try:
            _get(path)
            if i % 10 == 0:
                print(f"[prewarm] {i}/{len(mice)} loaded", flush=True)
        except Exception as e:
            print(f"[prewarm] Failed {name}: {e}", flush=True)
    print("[prewarm] All meshes cached.", flush=True)

threading.Thread(target=_prewarm, daemon=True).start()

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/api/mice")
def api_mice():
    mice = get_all_mice()
    return jsonify([{"id": i, "name": n} for i, (n, _) in enumerate(mice)])

@app.route("/api/prepare", methods=["POST"])
def api_prepare():
    """
    Pre-align A and B meshes for client-side smooth morphing.
    Result is cached so repeated calls for the same pair are instant.
    Binary: [n_verts u32][n_faces u32][a_verts f32*n*3][b_verts f32*n*3][faces u32*n*3]
    """
    from scipy.spatial import cKDTree
    from src.core.morph_engine import _laplacian_smooth_verts

    data  = request.json or {}
    mice  = get_all_mice()
    a_idx = int(data.get("a", 0))
    b_idx = int(data.get("b", 1))

    cache_key = (a_idx, b_idx)
    with _prepare_lock:
        if cache_key in _prepare_cache:
            return Response(_prepare_cache[cache_key],
                            mimetype="application/octet-stream")

    # Compute (outside the lock so other requests aren't blocked)
    ma = _get(mice[a_idx][1])
    mb = _get(mice[b_idx][1])

    tree = cKDTree(ma.vertices)
    _, idx = tree.query(mb.vertices, workers=1)   # workers=1 on single-core free tier
    a_resampled = ma.vertices[idx].astype(np.float32)
    a_smooth = _laplacian_smooth_verts(
        a_resampled, mb.faces, iterations=1          # 1 pass is fast & good enough
    ).astype(np.float32)

    nv = len(mb.vertices)
    nf = len(mb.faces)
    header  = struct.pack('<II', nv, nf)
    payload = (header
               + a_smooth.tobytes()
               + mb.vertices.astype(np.float32).tobytes()
               + mb.faces.astype(np.uint32).tobytes())

    with _prepare_lock:
        _prepare_cache[cache_key] = payload

    return Response(payload, mimetype="application/octet-stream")


@app.route("/api/mesh", methods=["POST"])
def api_mesh():
    """Return binary mesh for real-time preview."""
    data   = request.json or {}
    mice   = get_all_mice()
    a_idx  = int(data.get("a", 0))
    b_idx  = int(data.get("b", 1))
    t      = float(data.get("t", 0.0))
    deform = data.get("deform", {})

    mesh_a = _get(mice[a_idx][1]).copy()
    mesh_b = _get(mice[b_idx][1]).copy()

    result = morph_blend(mesh_a, mesh_b, t)

    if deform:
        state = {tuple(k.split(",")): float(v) for k, v in deform.items()}
        result = apply_all_deforms(result, state)

    return Response(_to_binary(result), mimetype="application/octet-stream")

@app.route("/api/export", methods=["POST"])
def api_export():
    """Return full-resolution STL for download."""
    data   = request.json or {}
    mice   = get_all_mice()
    a_idx  = int(data.get("a", 0))
    b_idx  = int(data.get("b", 1))
    t      = float(data.get("t", 0.0))
    deform = data.get("deform", {})

    mesh_a = load_mesh(mice[a_idx][1], display=False)
    mesh_b = load_mesh(mice[b_idx][1], display=False)

    result = morph_blend(mesh_a, mesh_b, t)
    if deform:
        state = {tuple(k.split(",")): float(v) for k, v in deform.items()}
        result = apply_all_deforms(result, state)

    buf = io.BytesIO()
    result.export(buf, file_type="stl")
    buf.seek(0)
    return send_file(buf, mimetype="application/octet-stream",
                     as_attachment=True, download_name="fasic_custom_mouse.stl")

# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = 5173
    def _open():
        time.sleep(1.2)
        webbrowser.open(f"http://localhost:{port}")
    threading.Thread(target=_open, daemon=True).start()
    print(f"\n  FASIC Mouse Shape Lab → http://localhost:{port}\n")
    app.run(port=port, debug=False, threaded=True)
