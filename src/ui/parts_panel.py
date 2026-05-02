"""
Right panel: per-part dimension sliders (width / height / length / flare / curve).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QFrame, QScrollArea, QGridLayout, QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from src.core.morph_engine import PARTS, PART_LIMITS


PART_LABELS = {
    "front":   "Front",
    "back":    "Back / Hump",
    "left":    "Left Side",
    "right":   "Right Side",
    "top":     "Top Surface",
    "buttons": "Button Area",
    "thumb":   "Thumb Rest",
}

DIM_LABELS = {
    "width":  "Width",
    "height": "Height",
    "length": "Length",
    "flare":  "Flare",
    "curve":  "Curve",
}

# Which dims apply to which parts (not all combos make physical sense)
PART_DIMS = {
    "front":   ["width", "height", "length", "flare"],
    "back":    ["width", "height", "length", "curve"],
    "left":    ["width", "flare"],
    "right":   ["width", "flare"],
    "top":     ["height", "curve"],
    "buttons": ["height", "length", "curve"],
    "thumb":   ["width", "height", "flare"],
}


def _default(dim):
    return 1.0 if dim in ("width", "height", "length") else 0.0


def _slider_int(dim, value):
    """Convert float value to int slider position (0–200 range)."""
    lo, hi = PART_LIMITS[dim]
    return int((value - lo) / (hi - lo) * 200)


def _slider_float(dim, int_val):
    """Convert int slider position back to float."""
    lo, hi = PART_LIMITS[dim]
    return lo + (int_val / 200.0) * (hi - lo)


class PartSliderRow(QWidget):
    changed = Signal(str, str, float)  # part_key, dim, value

    def __init__(self, part_key: str, dim: str, parent=None):
        super().__init__(parent)
        self.part_key = part_key
        self.dim = dim

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)

        lbl = QLabel(DIM_LABELS[dim])
        lbl.setFixedWidth(58)
        lbl.setStyleSheet("color: #aaaacc; font-size: 11px;")
        row.addWidget(lbl)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 200)
        default_int = _slider_int(dim, _default(dim))
        self.slider.setValue(default_int)
        self.slider.valueChanged.connect(self._emit)
        row.addWidget(self.slider)

        self.val_lbl = QLabel(self._fmt(_default(dim), dim))
        self.val_lbl.setFixedWidth(44)
        self.val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.val_lbl.setStyleSheet("color: #88ddff; font-size: 11px;")
        row.addWidget(self.val_lbl)

        # Reset button
        btn = QPushButton("↺")
        btn.setFixedSize(22, 22)
        btn.setStyleSheet("QPushButton{background:#2a2a4a;color:#8888cc;border:none;border-radius:3px;}"
                          "QPushButton:hover{background:#4444aa;}")
        btn.clicked.connect(self.reset)
        row.addWidget(btn)

    def _emit(self, int_val):
        val = _slider_float(self.dim, int_val)
        self.val_lbl.setText(self._fmt(val, self.dim))
        self.changed.emit(self.part_key, self.dim, val)

    def reset(self):
        default_int = _slider_int(self.dim, _default(self.dim))
        self.slider.setValue(default_int)

    @staticmethod
    def _fmt(val, dim):
        if dim in ("width", "height", "length"):
            return f"{val:.2f}×"
        return f"{val:+.2f}"

    def value(self) -> float:
        return _slider_float(self.dim, self.slider.value())


class PartSection(QWidget):
    changed = Signal(str, str, float)

    def __init__(self, part_key: str, parent=None):
        super().__init__(parent)
        self.part_key = part_key
        self.rows: dict[str, PartSliderRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Header
        hdr = QLabel(PART_LABELS[part_key].upper())
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        hdr.setFont(font)
        hdr.setStyleSheet("color: #a0c4ff; padding-bottom: 2px;")
        layout.addWidget(hdr)

        for dim in PART_DIMS.get(part_key, []):
            row = PartSliderRow(part_key, dim)
            row.changed.connect(self.changed)
            layout.addWidget(row)
            self.rows[dim] = row

        # Bottom separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #333355; margin-top: 4px;")
        layout.addWidget(sep)

    def reset_all(self):
        for row in self.rows.values():
            row.reset()

    def get_state(self) -> dict:
        return {dim: row.value() for dim, row in self.rows.items()}


class PartsPanel(QWidget):
    deform_changed = Signal(dict)  # full deform state {(part, dim): value}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sections: dict[str, PartSection] = {}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar
        hdr = QLabel("PARTS CUSTOMIZE")
        hdr.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;"
                          " letter-spacing: 2px; padding: 10px 12px;")
        outer.addWidget(hdr)

        # Reset all
        btn_reset = QPushButton("Reset All")
        btn_reset.setStyleSheet(
            "QPushButton{background:#2a2a4a;color:#aaaadd;border:1px solid #444488;"
            "padding:4px;border-radius:4px;margin:0 12px 6px 12px;}"
            "QPushButton:hover{background:#3a3a6a;}"
        )
        btn_reset.clicked.connect(self.reset_all)
        outer.addWidget(btn_reset)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;} QScrollBar:vertical{width:8px;background:#1a1a2e;}"
                             "QScrollBar::handle:vertical{background:#444488;border-radius:4px;}")

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        for part_key in PARTS.keys():
            section = PartSection(part_key)
            section.changed.connect(self._on_change)
            container_layout.addWidget(section)
            self._sections[part_key] = section

        container_layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _on_change(self, part_key, dim, value):
        self.deform_changed.emit(self.get_full_state())

    def get_full_state(self) -> dict:
        state = {}
        for part_key, section in self._sections.items():
            for dim, val in section.get_state().items():
                state[(part_key, dim)] = val
        return state

    def reset_all(self):
        for section in self._sections.values():
            section.reset_all()
