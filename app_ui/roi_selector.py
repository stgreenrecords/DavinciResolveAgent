from PySide6 import QtCore, QtGui, QtWidgets

from core.roi import Roi


class RoiSelectorDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select ROI")
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowState(QtCore.Qt.WindowState.WindowFullScreen)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self._origin = None
        self._rubber = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Shape.Rectangle, self)
        self._rubber.setStyleSheet("border: 2px solid #00AEEF;")
        self.selected_roi: Roi | None = None

    def paintEvent(self, event: QtGui.QPaintEvent):
        # Draw a faint overlay to make the selection area visible while keeping the screen readable.
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 50))

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._rubber.setGeometry(QtCore.QRect(self._origin, QtCore.QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self._origin is None:
            return
        rect = QtCore.QRect(self._origin, event.position().toPoint()).normalized()
        self._rubber.setGeometry(rect)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._origin is not None:
            rect = self._rubber.geometry()
            self.selected_roi = Roi(rect.x(), rect.y(), rect.width(), rect.height())
            self.accept()
