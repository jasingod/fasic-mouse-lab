"""
FASIC Mouse Shape Lab — Flask server (lightweight)
All mesh computation moved to client-side JS.
Server only handles: static files + mouse list + STL export.
"""
import sys, os, io, threading, webbrowser, time
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request, send_file

from src.core.mesh_loader import get_all_mice, load_mesh
from src.core.morph_engine import morph_blend, apply_all_deforms

app = Flask(__name__, static_folder="web", static_url_path="")

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/api/mice")
def api_mice():
    mice = get_all_mice()
    return jsonify([{"id": i, "name": n} for i, (n, _) in enumerate(mice)])

@app.route("/api/export", methods=["POST"])
def api_export():
    """Full-resolution STL export — only heavy operation remaining."""
    import numpy as np
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

if __name__ == "__main__":
    port = 5173
    def _open():
        time.sleep(1.2)
        webbrowser.open(f"http://localhost:{port}")
    threading.Thread(target=_open, daemon=True).start()
    print(f"\n  FASIC Mouse Shape Lab → http://localhost:{port}\n")
    app.run(port=port, debug=False, threaded=True)
