"""
Main window — smooth morph + animation timer.
"""
import numpy as np
import trimesh
from pathlib import Path
from scipy.spatial import cKDTree

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFileDialog, QSplitter, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer

from src.core.mesh_loader import get_all_mice, load_mesh
from src.core.morph_engine import morph_blend, apply_all_deforms, _laplacian_smooth_verts
from src.core.exporter import export_mesh
from src.ui.viewport import Viewport3D
from src.ui.morph_panel import MorphPanel
from src.ui.parts_panel import PartsPanel


# ── Background loader ─────────────────────────────────────────────────────────
class _Loader(QObject):
    done  = Signal(object, str)
    error = Signal(str)
    def __init__(self, path, tag):
        super().__init__()
        self.path, self.tag = path, tag
    def run(self):
        try:
            self.done.emit(load_mesh(self.path, display=True), self.tag)
        except Exception as e:
            self.error.emit(str(e))


def _ease_out_quart(t):
    return 1 - (1 - t) ** 4


# ── Main window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):

    first_mesh_ready = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FASIC — Mouse Shape Lab")
        self.resize(1380, 820)
        self._theme()

        # Meshes
        self._mesh_a: trimesh.Trimesh | None = None
        self._mesh_b: trimesh.Trimesh | None = None

        # Pre-aligned verts for instant client-side morph
        self._a_aligned: np.ndarray | None = None   # A resampled to B topology
        self._b_verts:   np.ndarray | None = None   # B verts
        self._b_ref:     trimesh.Trimesh | None = None  # B mesh (topology ref)

        self._morph_t   = 0.0
        self._deform    = {}
        self._threads   = []
        self._workers   = []
        self._ready     = False

        # Smooth animation (for parts deform updates)
        self._anim_from:  np.ndarray | None = None
        self._anim_to:    np.ndarray | None = None
        self._anim_t      = 1.0
        self._anim_dur    = 0.20   # seconds
        self._anim_timer  = QTimer(self)
        self._anim_timer.setInterval(16)   # ~60 fps
        self._anim_timer.timeout.connect(self._anim_tick)

        # Debounce for parts deform
        self._deform_timer = QTimer(self)
        self._deform_timer.setSingleShot(True)
        self._deform_timer.setInterval(140)
        self._deform_timer.timeout.connect(self._apply_deform)

        self._build_ui()
        self._wire()

        mice = get_all_mice()
        if mice:          self._load(mice[0][1], "a")
        if len(mice) > 1: self._load(mice[1][1], "b")

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)

        sp = QSplitter(Qt.Horizontal)
        sp.setHandleWidth(2)
        sp.setStyleSheet("QSplitter::handle{background:#1e1e44;}")

        mice = get_all_mice()

        self.morph_panel = MorphPanel(mice)
        self.morph_panel.setFixedWidth(258)
        self.morph_panel.setStyleSheet("background:#10101e;")
        sp.addWidget(self.morph_panel)

        self.viewport = Viewport3D()
        self.viewport.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sp.addWidget(self.viewport)

        self.parts_panel = PartsPanel()
        self.parts_panel.setFixedWidth(278)
        self.parts_panel.setStyleSheet("background:#10101e;")
        sp.addWidget(self.parts_panel)

        sp.setStretchFactor(0,0); sp.setStretchFactor(1,1); sp.setStretchFactor(2,0)
        root.addWidget(sp)

        # Bottom bar
        bar_w = QWidget()
        bar_w.setFixedHeight(42)
        bar_w.setStyleSheet("background:#08080f;border-top:1px solid #1e1e44;")
        bar = QHBoxLayout(bar_w)
        bar.setContentsMargins(14,4,14,4)

        self.status = QLabel("Loading…")
        self.status.setStyleSheet("color:#50508a;font-size:12px;")
        bar.addWidget(self.status)
        bar.addStretch()

        self.export_btn = QPushButton("Export STL")
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet(
            "QPushButton{background:#1e4488;color:#fff;border:none;"
            "padding:6px 22px;border-radius:4px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#2a5aaa;}"
            "QPushButton:disabled{background:#181830;color:#333366;}"
        )
        self.export_btn.clicked.connect(self._export)
        bar.addWidget(self.export_btn)
        root.addWidget(bar_w)

    def _wire(self):
        self.morph_panel.mouse_a_changed.connect(lambda p: self._load(p, "a"))
        self.morph_panel.mouse_b_changed.connect(lambda p: self._load(p, "b"))
        self.morph_panel.morph_changed.connect(self._on_morph)
        self.parts_panel.deform_changed.connect(self._on_deform)

    # ── Loading ───────────────────────────────────────────────────────────────
    def _load(self, path, tag):
        if not path: return
        self.status.setText(f"Loading {'A' if tag=='a' else 'B'}…")
        th = QThread(self); w = _Loader(path, tag)
        w.moveToThread(th)
        th.started.connect(w.run)
        w.done.connect(self._on_loaded); w.done.connect(th.quit)
        w.error.connect(lambda m: self.status.setText(f"Error: {m}"))
        w.error.connect(th.quit)
        th.finished.connect(th.deleteLater)
        self._threads.append(th); self._workers.append(w)
        th.start()

    def _on_loaded(self, mesh, tag):
        if tag == "a": self._mesh_a = mesh
        else:          self._mesh_b = mesh

        # Pre-compute correspondence whenever both meshes are available
        if self._mesh_a and self._mesh_b:
            self._precompute_morph()

        if not self._ready and self._mesh_a:
            self._ready = True
            self.first_mesh_ready.emit()

        self._show_current(reset=True)
        self.status.setText(
            f"{'A' if tag=='a' else 'B'}: {mesh.vertices.shape[0]:,} verts"
        )

    # ── Pre-compute A→B correspondence (once per A/B change) ─────────────────
    def _precompute_morph(self):
        a, b = self._mesh_a, self._mesh_b
        tree = cKDTree(a.vertices)
        _, idx = tree.query(b.vertices, workers=-1)
        a_raw = a.vertices[idx].astype(np.float32)
        self._a_aligned = _laplacian_smooth_verts(a_raw, b.faces, iterations=2)
        self._b_verts   = b.vertices.astype(np.float32)
        self._b_ref     = b

    def _lerp_verts(self, t) -> np.ndarray | None:
        if self._a_aligned is None or self._b_verts is None:
            return None
        t = float(np.clip(t, 0, 1))
        return (1 - t) * self._a_aligned + t * self._b_verts

    # ── Show ──────────────────────────────────────────────────────────────────
    def _show_current(self, reset=False, animate=False):
        mesh = self._build_display_mesh()
        if mesh is None: return
        if animate:
            self._start_anim(mesh)
        else:
            self.viewport.show_mesh(mesh)
        self.export_btn.setEnabled(True)

    def _build_display_mesh(self) -> trimesh.Trimesh | None:
        if self._mesh_a is None: return None

        # Use pre-aligned lerp if available, else fall back to engine morph
        lerped = self._lerp_verts(self._morph_t)
        if lerped is not None and self._b_ref is not None:
            base = self._b_ref.copy()
            base.vertices = lerped
        else:
            base = (morph_blend(self._mesh_a, self._mesh_b, self._morph_t)
                    if self._mesh_b and self._morph_t > 0
                    else self._mesh_a.copy())

        if self._deform:
            base = apply_all_deforms(base, self._deform)
        return base

    # ── Smooth animation (for deform updates) ─────────────────────────────────
    def _start_anim(self, target_mesh: trimesh.Trimesh):
        # Snapshot current GL verts as anim start
        mesh = self._build_display_mesh()
        if mesh:
            self._anim_from = np.array(mesh.vertices, dtype=np.float32)
        self._anim_to_mesh = target_mesh
        self._anim_to      = np.array(target_mesh.vertices, dtype=np.float32)
        self._anim_t       = 0.0
        self._anim_timer.start()

    def _anim_tick(self):
        self._anim_t = min(1.0, self._anim_t + 16 / (self._anim_dur * 1000))
        et = _ease_out_quart(self._anim_t)

        if self._anim_from is not None and self._anim_to is not None:
            verts = (1 - et) * self._anim_from + et * self._anim_to
            self.viewport.show_verts(verts, self._anim_to_mesh)

        if self._anim_t >= 1.0:
            self._anim_timer.stop()

    # ── Signal handlers ───────────────────────────────────────────────────────
    def _on_morph(self, t: float):
        self._morph_t = t
        # Instant client-side lerp (no animation needed — it IS the animation)
        lerped = self._lerp_verts(t)
        if lerped is not None and self._b_ref is not None:
            if self._deform:
                self._deform_timer.start()   # deform recalc debounced
            else:
                self.viewport.show_verts(lerped, self._b_ref)
        else:
            self._show_current()

    def _on_deform(self, state: dict):
        self._deform = state
        self._deform_timer.start()

    def _apply_deform(self):
        self._show_current(animate=True)

    # ── Export ────────────────────────────────────────────────────────────────
    def _export(self):
        mesh = self._build_display_mesh()
        if not mesh: return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save STL",
            str(Path.home() / "Desktop" / "fasic_custom.stl"),
            "STL Files (*.stl)"
        )
        if path:
            export_mesh(mesh, path)
            self.status.setText(f"Saved → {path}")

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _theme(self):
        self.setStyleSheet("""
            QMainWindow,QWidget{background:#12121e;color:#d8d8f0;
              font-family:'SF Pro Display','Segoe UI',Arial;}
            QLabel{color:#d8d8f0;}
            QSlider::groove:horizontal{height:5px;background:#1e1e40;border-radius:3px;}
            QSlider::handle:horizontal{width:14px;height:14px;margin:-5px 0;
              background:#4466ff;border-radius:7px;}
            QSlider::sub-page:horizontal{background:#3355bb;border-radius:3px;}
            QComboBox{background:#1a1a38;color:#d8d8f0;border:1px solid #303060;
              padding:4px;border-radius:4px;}
            QScrollArea{border:none;}
            QScrollBar:vertical{width:6px;background:#0e0e1e;}
            QScrollBar::handle:vertical{background:#2a2a55;border-radius:3px;}
        """)
