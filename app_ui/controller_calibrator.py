from PySide6 import QtCore, QtGui, QtWidgets


class ControllerCalibratorDialog(QtWidgets.QDialog):
    def __init__(self, pixmap, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrate Controllers")
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint)

        self.pixmap = pixmap
        self.config = config
        self.targets_to_calibrate = self._get_targets_to_calibrate(config)
        self.current_index = 0
        self.coordinates = {}

        self.label = QtWidgets.QLabel(self)
        self.label.setPixmap(pixmap)
        self.label.setScaledContents(True)

        self.overlay = QtWidgets.QLabel(self)
        self.overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.instr_panel = QtWidgets.QFrame(self)
        self.instr_panel.setStyleSheet(
            "background: rgba(0, 0, 0, 200); border-radius: 12px; color: white; padding: 15px;"
        )
        self.instr_panel.setFixedWidth(600)
        self.instr_panel.setFixedHeight(200)

        self.instr_layout = QtWidgets.QVBoxLayout(self.instr_panel)
        self.instr_title = QtWidgets.QLabel("Calibration")
        self.instr_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #3B82F6;")
        self.instr_text = QtWidgets.QLabel("")
        self.instr_text.setStyleSheet("font-size: 16px; line-height: 1.4;")
        self.instr_text.setWordWrap(True)
        self.instr_layout.addWidget(self.instr_title)
        self.instr_layout.addWidget(self.instr_text)

        self._update_instructions()

        # Set full screen AFTER defining UI elements to avoid resizeEvent crash
        self.setWindowState(QtCore.Qt.WindowState.WindowFullScreen)

    def _get_targets_to_calibrate(self, config):
        targets = []
        if "sliders" in config:
            for name, data in config["sliders"].items():
                if "x" in data and "y" in data:
                    targets.append(("slider", name, None))
        if "wheels" in config:
            for wheel_name, components in config["wheels"].items():
                for comp_name, data in components.items():
                    if "x" in data and "y" in data:
                        targets.append(("wheel", wheel_name, comp_name))
        if "fullResetButton" in config:
            targets.append(("button", "fullResetButton", None))
        return targets

    def _update_instructions(self):
        if self.current_index < len(self.targets_to_calibrate):
            ttype, name, sub = self.targets_to_calibrate[self.current_index]
            target_str = f"{name} {sub}" if sub else name
            self.instr_text.setText(
                f"Click the center of: \n{target_str}\n({self.current_index + 1}/{len(self.targets_to_calibrate)})"
            )
        else:
            self.accept()

    def _center_instr_panel(self):
        if hasattr(self, "instr_panel"):
            self.instr_panel.move((self.width() - self.instr_panel.width()) // 2, 50)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # We must map the click position back to the pixmap coordinates if we scale the label
            # However, if we are in full screen and label fills it, it should be 1:1 if resolutions match.
            # But let's be safe and calculate relative to label size.
            label_pos = self.label.mapFromParent(event.position().toPoint())

            # If setScaledContents is true, we need to map the label_pos to the pixmap's original size
            pix_w = self.pixmap.width()
            pix_h = self.pixmap.height()
            lbl_w = self.label.width()
            lbl_h = self.label.height()

            x = int(label_pos.x() * pix_w / lbl_w) if lbl_w > 0 else label_pos.x()
            y = int(label_pos.y() * pix_h / lbl_h) if lbl_h > 0 else label_pos.y()

            ttype, name, sub = self.targets_to_calibrate[self.current_index]

            if ttype == "slider":
                if name not in self.coordinates:
                    self.coordinates[name] = {}
                self.coordinates[name] = {"x": x, "y": y}
            elif ttype == "button":
                self.coordinates[name] = {"x": x, "y": y}
            else:
                if name not in self.coordinates:
                    self.coordinates[name] = {}
                self.coordinates[name][sub] = {"x": x, "y": y}

            self.current_index += 1
            self._draw_mark(event.position().toPoint())
            self._update_instructions()

    def _draw_mark(self, pos):
        pixmap = self.overlay.pixmap()
        if not pixmap or pixmap.size() != self.size():
            pixmap = QtGui.QPixmap(self.size())
            pixmap.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.red, 2))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 0, 0, 100)))
        painter.drawEllipse(pos, 5, 5)
        painter.end()
        self.overlay.setPixmap(pixmap)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "label"):
            self.label.setGeometry(self.rect())
        if hasattr(self, "overlay"):
            self.overlay.setGeometry(self.rect())
        self._center_instr_panel()
