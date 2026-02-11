from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets


@dataclass
class Roi:
    x: int
    y: int
    width: int
    height: int


class RoiSelectorDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select ROI")
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowState(QtCore.Qt.WindowFullScreen)
        self.setCursor(QtCore.Qt.CrossCursor)
        self._origin = None
        self._rubber = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self._rubber.setStyleSheet("border: 2px solid #00AEEF;")
        self.selected_roi: Roi | None = None

    def paintEvent(self, event: QtGui.QPaintEvent):
        # Draw a faint overlay to make the selection area visible while keeping the screen readable.
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 50))

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._rubber.setGeometry(QtCore.QRect(self._origin, QtCore.QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self._origin is None:
            return
        rect = QtCore.QRect(self._origin, event.position().toPoint()).normalized()
        self._rubber.setGeometry(rect)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton and self._origin is not None:
            rect = self._rubber.geometry()
            self.selected_roi = Roi(rect.x(), rect.y(), rect.width(), rect.height())
            self.accept()
