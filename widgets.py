from collections import deque
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QFont, QPainterPath, QBrush
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QLabel, QStackedWidget, QGraphicsOpacityEffect

def mix(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t), int(a.blue() + (b.blue() - a.blue()) * t))

class Gauge(QWidget):
    """Circular gauge with an animated value."""
    def __init__(s, label, unit="%", c1="#2d6bff", c2="#8a3dff", maxv=100):
        super().__init__(); s._v = 0.0; s.label, s.unit, s.c1, s.c2, s.maxv, s.text, s.na = label, unit, c1, c2, maxv, None, True
        s.anim = QPropertyAnimation(s, b"value"); s.anim.setDuration(500); s.anim.setEasingCurve(QEasingCurve.OutCubic); s.setMinimumSize(150, 150)
    def _get(s): return s._v
    def _set(s, v): s._v = v; s.update()
    value = Property(float, _get, _set)
    def setValue(s, v, text=None):
        s.na, s.text = v is None, text
        s.anim.stop(); s.anim.setStartValue(s._v); s.anim.setEndValue(0.0 if v is None else float(v)); s.anim.start()
    def paintEvent(s, e):
        p = QPainter(s); p.setRenderHint(QPainter.Antialiasing)
        side = min(s.width(), s.height()) - 22; r = QRectF((s.width() - side) / 2, (s.height() - side) / 2 - 4, side, side)
        pen = QPen(QColor("#1c1c2b"), 11); pen.setCapStyle(Qt.RoundCap); p.setPen(pen); p.drawArc(r, 225 * 16, -270 * 16)
        frac = max(0.0, min(1.0, s._v / s.maxv))
        if frac > 0.004: pen.setColor(mix(s.c1, s.c2, frac)); p.setPen(pen); p.drawArc(r, 225 * 16, int(-270 * 16 * frac))
        txt = "n/a" if s.na and s.text is None else (s.text if s.text is not None else f"{s._v:.0f}{s.unit}")
        p.setPen(QColor("#f2f2ff")); p.setFont(QFont("Segoe UI", max(12, int(side / 6)), QFont.Bold)); p.drawText(r, Qt.AlignCenter, txt)
        p.setPen(QColor("#8d8da8")); p.setFont(QFont("Segoe UI", 9, QFont.Bold)); p.drawText(QRectF(r.x(), r.bottom() - 14, r.width(), 18), Qt.AlignHCenter, s.label)

class Spark(QWidget):
    """Area line chart. maxv=None auto-scales."""
    def __init__(s, color="#3d7bff", maxv=100, n=90, minh=70):
        super().__init__(); s.d = deque([0.0] * n, maxlen=n); s.c = QColor(color); s.maxv = maxv; s.setMinimumHeight(minh)
    def push(s, v): s.d.append(float(v or 0)); s.update()
    def paintEvent(s, e):
        p = QPainter(s); p.setRenderHint(QPainter.Antialiasing); w, h = s.width(), s.height()
        top = s.maxv or max(max(s.d), 1.0) * 1.15; n = len(s.d)
        pts = [QPointF(i * w / (n - 1), h - 3 - min(v / top, 1.0) * (h - 8)) for i, v in enumerate(s.d)]
        path = QPainterPath(QPointF(0, h))
        for pt in pts: path.lineTo(pt)
        path.lineTo(w, h); path.closeSubpath()
        g = QLinearGradient(0, 0, 0, h); a = QColor(s.c); a.setAlpha(110); b = QColor(s.c); b.setAlpha(0); g.setColorAt(0, a); g.setColorAt(1, b)
        p.fillPath(path, QBrush(g)); p.setPen(QPen(s.c, 2)); p.drawPolyline(pts)

class Tile(QFrame):
    def __init__(s, label):
        super().__init__(); s.setObjectName("card"); l = QVBoxLayout(s); l.setContentsMargins(16, 12, 16, 12); l.setSpacing(2)
        a = QLabel(label.upper()); a.setObjectName("sub"); s.v = QLabel("—"); s.v.setObjectName("tile"); l.addWidget(a); l.addWidget(s.v)
    def set(s, t): s.v.setText(t)

class FadeStack(QStackedWidget):
    """QStackedWidget that fades the incoming page in."""
    def fade_to(s, i):
        if i == s.currentIndex(): return
        s.setCurrentIndex(i); w = s.currentWidget(); eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", w); a.setDuration(280); a.setStartValue(0.0); a.setEndValue(1.0); a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: w.setGraphicsEffect(None)); a.start(); s._a = a
