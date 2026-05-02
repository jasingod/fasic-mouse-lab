"""
Left panel: mouse A / B selection + morph blend slider.
Overlay button removed — lightweight version.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSlider, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class _SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        f = QFont(); f.setBold(True); f.setPointSize(10)
        self.setFont(f)
        self.setStyleSheet("color: #8aaaff; padding: 4px 0px 2px 0px;")


class MorphPanel(QWidget):
    mouse_a_changed = Signal(str)   # filepath
    mouse_b_changed = Signal(str)
    morph_changed   = Signal(float) # 0.0 – 1.0

    def __init__(self, mice_list: list, parent=None):
        super().__init__(parent)
        self._mice = mice_list
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # Title
        title = QLabel("MORPH BLEND")
        title.setStyleSheet(
            "color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:2px;"
        )
        layout.addWidget(title)
        layout.addWidget(self._sep())

        # ── Base mouse A ──────────────────────────────────────────────────
        layout.addWidget(_SectionLabel("● Base Mouse  (A)"))
        self.combo_a = QComboBox()
        self._fill(self.combo_a)
        self.combo_a.currentIndexChanged.connect(
            lambda _: self.mouse_a_changed.emit(self.combo_a.currentData() or "")
        )
        layout.addWidget(self.combo_a)

        # ── Target mouse B ────────────────────────────────────────────────
        layout.addWidget(_SectionLabel("● Target Mouse  (B)"))
        self.combo_b = QComboBox()
        self._fill(self.combo_b)
        if len(self._mice) > 1:
            self.combo_b.setCurrentIndex(1)
        self.combo_b.currentIndexChanged.connect(
            lambda _: self.mouse_b_changed.emit(self.combo_b.currentData() or "")
        )
        layout.addWidget(self.combo_b)

        layout.addWidget(self._sep())

        # ── Blend slider ──────────────────────────────────────────────────
        layout.addWidget(_SectionLabel("Blend   A → B"))

        row = QHBoxLayout()
        lA = QLabel("A"); lA.setStyleSheet("color:#5b9bd5;font-weight:bold;")
        lB = QLabel("B"); lB.setStyleSheet("color:#ed7d31;font-weight:bold;")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(0)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(10)
        self.slider.valueChanged.connect(self._on_slide)
        row.addWidget(lA); row.addWidget(self.slider); row.addWidget(lB)
        layout.addLayout(row)

        self.pct_lbl = QLabel("0 %")
        self.pct_lbl.setAlignment(Qt.AlignCenter)
        self.pct_lbl.setStyleSheet("color:#cccccc;font-size:16px;")
        layout.addWidget(self.pct_lbl)
        layout.addStretch()

    def _on_slide(self, val: int):
        self.pct_lbl.setText(f"{val} %")
        self.morph_changed.emit(val / 100.0)

    def _fill(self, combo: QComboBox):
        combo.setStyleSheet(self._combo_css())
        for name, path in self._mice:
            combo.addItem(name, path)

    def current_a(self): return self.combo_a.currentData()
    def current_b(self): return self.combo_b.currentData()

    @staticmethod
    def _sep():
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color:#2a2a55;"); return f

    @staticmethod
    def _combo_css():
        return (
            "QComboBox{background:#22224a;color:#e0e0e0;border:1px solid #404080;"
            "padding:4px 8px;border-radius:4px;font-size:12px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#1a1a38;color:#e0e0e0;"
            "selection-background-color:#3a3aaa;}"
        )
