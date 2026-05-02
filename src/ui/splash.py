"""
FASIC splash screen — shown immediately on launch while heavy modules load.
"""
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPen, QFontDatabase


class FasicSplash(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(680, 340)
        self._center_on_screen()

        self._progress = 0       # 0–100
        self._dot_frame = 0
        self._opacity = 1.0

        # Animate progress bar
        self._bar_timer = QTimer(self)
        self._bar_timer.timeout.connect(self._tick)
        self._bar_timer.start(18)

        # Dot animation
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._dot_timer.start(400)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2,
        )

    def _tick(self):
        if self._progress < 100:
            self._progress += 1
        self.update()

    def _tick_dots(self):
        self._dot_frame = (self._dot_frame + 1) % 4
        self.update()

    def set_progress(self, value: int):
        self._progress = max(self._progress, min(100, value))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._opacity)

        W, H = self.width(), self.height()

        # ── Background ──────────────────────────────────────────────────────
        p.setBrush(QColor(8, 8, 20))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, W, H, 16, 16)

        # ── Outer border glow ───────────────────────────────────────────────
        pen = QPen(QColor(60, 90, 180, 120))
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(1, 1, W-2, H-2, 16, 16)

        # ── FASIC — main logotype ────────────────────────────────────────────
        font = QFont("Arial", 88, QFont.Black)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 12)
        p.setFont(font)

        # Shadow / glow layer
        for offset, alpha in [(4, 30), (2, 60), (1, 100)]:
            p.setPen(QColor(80, 120, 255, alpha))
            p.drawText(QRect(offset, 40 + offset, W, 160), Qt.AlignHCenter, "FASIC")

        # Main gradient text
        grad = QLinearGradient(0, 40, 0, 160)
        grad.setColorAt(0.0, QColor(220, 230, 255))
        grad.setColorAt(0.5, QColor(150, 180, 255))
        grad.setColorAt(1.0, QColor(80,  120, 220))
        p.setPen(QPen(grad, 1))
        p.drawText(QRect(0, 40, W, 160), Qt.AlignHCenter, "FASIC")

        # ── Thin divider line ────────────────────────────────────────────────
        line_grad = QLinearGradient(80, 0, W-80, 0)
        line_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        line_grad.setColorAt(0.3, QColor(80, 120, 220, 180))
        line_grad.setColorAt(0.7, QColor(80, 120, 220, 180))
        line_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(QPen(line_grad, 1))
        p.drawLine(80, 178, W-80, 178)

        # ── Subtitle ─────────────────────────────────────────────────────────
        sub_font = QFont("Arial", 13)
        sub_font.setLetterSpacing(QFont.AbsoluteSpacing, 6)
        p.setFont(sub_font)
        p.setPen(QColor(100, 130, 200, 200))
        p.drawText(QRect(0, 188, W, 30), Qt.AlignHCenter, "MOUSE SHAPE LAB")

        # ── Loading dots ─────────────────────────────────────────────────────
        dot_font = QFont("Arial", 11)
        p.setFont(dot_font)
        dots = "." * self._dot_frame
        p.setPen(QColor(80, 100, 160, 180))
        p.drawText(QRect(0, 228, W, 24), Qt.AlignHCenter, f"Loading{dots}")

        # ── Progress bar ─────────────────────────────────────────────────────
        bar_x, bar_y = 80, 272
        bar_w, bar_h = W - 160, 3

        # Track
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(25, 30, 60))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 2, 2)

        # Fill
        fill_w = int(bar_w * self._progress / 100)
        if fill_w > 0:
            fill_grad = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
            fill_grad.setColorAt(0.0, QColor(50,  80, 200))
            fill_grad.setColorAt(1.0, QColor(100, 160, 255))
            p.setBrush(fill_grad)
            p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 2, 2)

        # ── Version tag ───────────────────────────────────────────────────────
        ver_font = QFont("Arial", 9)
        p.setFont(ver_font)
        p.setPen(QColor(50, 60, 100, 160))
        p.drawText(QRect(0, H-26, W, 20), Qt.AlignHCenter, "v1.0")

        p.end()

    def fade_out(self, on_done=None):
        """Animate opacity to 0 then close."""
        self._bar_timer.stop()
        self._dot_timer.stop()
        steps = 15
        interval = 40

        def _step():
            nonlocal steps
            steps -= 1
            self._opacity = max(0.0, steps / 15)
            self.update()
            if steps <= 0:
                fade_timer.stop()
                self.close()
                if on_done:
                    on_done()

        fade_timer = QTimer(self)
        fade_timer.timeout.connect(_step)
        fade_timer.start(interval)
