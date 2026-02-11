import json
import logging
import threading
import time
from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6 import QtCore, QtGui, QtWidgets

from automation.executor import ActionExecutor
from calibration.profile import CalibrationProfile
from llm.client import LlmClient, LlmRequestContext
from app_logging.session_logger import SessionLogger
from storage.settings import SettingsStore
from vision.metrics import SimilarityMetrics, compute_metrics
from vision.screenshot import capture_roi
from app_ui.roi_selector import RoiSelectorDialog
import subprocess, os


class _LogEmitter(QtCore.QObject):
    message = QtCore.Signal(str)


class _QtLogHandler(logging.Handler):
    def __init__(self, emitter: _LogEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.emitter.message.emit(msg)
        except Exception:
            return


class _InfoDialog(QtWidgets.QDialog):
    def __init__(self, parent, message: str):
        super().__init__(parent)
        self.setWindowTitle("Info")
        self.setModal(True)
        self.setFixedSize(360, 140)
        self.setStyleSheet(
            "QDialog { background: #1a1a1a; color: #E5E7EB; }"
            "QLabel { color: #E5E7EB; }"
            "QPushButton {"
            "  background: #2b2b2b;"
            "  border: 1px solid #3a3a3a;"
            "  border-radius: 12px;"
            "  padding: 6px 18px;"
            "  color: #E5E7EB;"
            "  font-weight: 600;"
            "}"
        )

        icon = QtWidgets.QLabel()
        pixmap = self.style().standardPixmap(QtWidgets.QStyle.SP_MessageBoxInformation)
        icon.setPixmap(pixmap.scaled(32, 32, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

        text = QtWidgets.QLabel(message)
        text.setWordWrap(True)

        content = QtWidgets.QHBoxLayout()
        content.addWidget(icon)
        content.addWidget(text, 1)

        ok_button = QtWidgets.QPushButton("OK")
        ok_button.clicked.connect(self.accept)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(ok_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(content)
        layout.addStretch(1)
        layout.addLayout(buttons)


class _ConfirmDialog(QtWidgets.QDialog):
    def __init__(self, parent, message: str):
        super().__init__(parent)
        self.setWindowTitle("Confirm Control")
        self.setModal(True)
        self.setFixedSize(380, 150)
        self.setStyleSheet(
            "QDialog { background: #1a1a1a; color: #E5E7EB; }"
            "QLabel { color: #E5E7EB; }"
            "QPushButton {"
            "  background: #2b2b2b;"
            "  border: 1px solid #3a3a3a;"
            "  border-radius: 12px;"
            "  padding: 6px 18px;"
            "  color: #E5E7EB;"
            "  font-weight: 600;"
            "}"
            "QPushButton#confirmYes { background: #3B82F6; border: 1px solid #3B82F6; color: #FFFFFF; }"
        )

        icon = QtWidgets.QLabel()
        pixmap = self.style().standardPixmap(QtWidgets.QStyle.SP_MessageBoxQuestion)
        icon.setPixmap(pixmap.scaled(32, 32, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

        text = QtWidgets.QLabel(message)
        text.setWordWrap(True)

        content = QtWidgets.QHBoxLayout()
        content.addWidget(icon)
        content.addWidget(text, 1)

        yes_button = QtWidgets.QPushButton("Yes")
        yes_button.setObjectName("confirmYes")
        yes_button.clicked.connect(self.accept)
        no_button = QtWidgets.QPushButton("No")
        no_button.clicked.connect(self.reject)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(yes_button)
        buttons.addWidget(no_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(content)
        layout.addStretch(1)
        layout.addLayout(buttons)


class MainWindow(QtWidgets.QMainWindow):
    models_refreshed = QtCore.Signal(list)
    iteration_updated = QtCore.Signal(int, str, object, str, str)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("app.ui")
        self.setWindowTitle("Resolve Color Grade Agent (v1)")
        self.settings_store = SettingsStore()
        self.calibration = self.settings_store.load_calibration()
        self.reference_image_path: Path | None = None
        self.session_logger: SessionLogger | None = None
        self.executor = ActionExecutor(self.on_stop_triggered, log_callback=self._append_log)
        self.llm_client = LlmClient(self.settings_store)
        self.iteration = 0
        self.last_metrics: SimilarityMetrics | None = None
        self._build_ui()
        self._install_ui_logger()
        self._apply_theme()
        self.models_refreshed.connect(self._apply_models)
        self.iteration_updated.connect(self._update_status)
        self._load_settings()
        self._update_button_states()

    def _apply_theme(self):
        self.setStyleSheet(
            ""
            "QMainWindow { background: #121212; color: #E5E7EB; }"
            "QLabel { color: #E5E7EB; }"
            "QLineEdit, QTextEdit, QComboBox {"
            "  background: #1b1b1b;"
            "  border: 1px solid #2b2b2b;"
            "  border-radius: 12px;"
            "  padding: 8px 12px;"
            "  color: #E5E7EB;"
            "}"
            "QPushButton {"
            "  background: #1f1f1f;"
            "  border: 1px solid #2b2b2b;"
            "  border-radius: 16px;"
            "  padding: 10px 16px;"
            "  color: #E5E7EB;"
            "  font-weight: 600;"
            "}"
            "QPushButton#primaryButton {"
            "  background: #3B82F6;"
            "  border: 1px solid #3B82F6;"
            "  color: #FFFFFF;"
            "}"
            "QPushButton:disabled { color: #6B7280; background: #1a1a1a; }"
            "QFrame#card {"
            "  background: #1a1a1a;"
            "  border: 1px solid #2b2b2b;"
            "  border-radius: 18px;"
            "}"
            "QProgressBar {"
            "  border: 1px solid #2b2b2b;"
            "  border-radius: 6px;"
            "  background: #101010;"
            "  height: 10px;"
            "}"
            "QProgressBar::chunk { background: #3B82F6; border-radius: 6px; }"
            "QTextEdit { background: #0f0f0f; }"
            "QDialog, QMessageBox { background: #1a1a1a; color: #E5E7EB; }"
            "QMessageBox QLabel { color: #E5E7EB; }"
            "QMessageBox QPushButton {"
            "  background: #2b2b2b;"
            "  border: 1px solid #3a3a3a;"
            "  border-radius: 12px;"
            "  padding: 6px 18px;"
            "  color: #E5E7EB;"
            "  font-weight: 600;"
            "}"
            "QCheckBox { color: #FFFFFF; font-weight: 600; spacing: 8px; }"
            "QCheckBox::indicator {"
            "  width: 18px;"
            "  height: 18px;"
            "  background: #1b1b1b;"
            "  border: 1px solid #3b82f6;"
            "  border-radius: 4px;"
            "}"
            "QCheckBox::indicator:checked {"
            "  background: #3b82f6;"
            "}"
            ""
        )

    def _build_ui(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        header = QtWidgets.QHBoxLayout()
        brand_box = QtWidgets.QHBoxLayout()
        self.brand_icon = QtWidgets.QLabel("GA")
        self.brand_icon.setAlignment(QtCore.Qt.AlignCenter)
        self.brand_icon.setFixedSize(36, 36)
        self.brand_icon.setStyleSheet("background: #12324A; color: #137fec; border-radius: 10px; font-weight: 700;")
        brand_box.addWidget(self.brand_icon)

        brand_text = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel("GradeAgent AI")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.status_label = QtWidgets.QLabel("o ONLINE - RESOLVE LINKED")
        self.status_label.setStyleSheet("color: #22c55e; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        brand_text.addWidget(self.title_label)
        brand_text.addWidget(self.status_label)
        brand_box.addLayout(brand_text)

        header.addLayout(brand_box)
        header.addStretch(1)
        self.connection_label = QtWidgets.QLabel("OK: OK")
        self.connection_label.setStyleSheet("color: #22c55e; font-weight: 600;")
        header.addWidget(self.connection_label)
        layout.addLayout(header)

        agent_header = QtWidgets.QHBoxLayout()
        self.engine_toggle = QtWidgets.QToolButton()
        self.engine_toggle.setText("AGENT SETTINGS")
        self.engine_toggle.setCheckable(True)
        self.engine_toggle.setChecked(True)
        self.engine_toggle.setArrowType(QtCore.Qt.DownArrow)
        self.engine_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.engine_toggle.clicked.connect(self._toggle_engine_section)
        self.engine_toggle.setStyleSheet(
            "color: #FFFFFF; background: #000000; font-weight: 700; letter-spacing: 2px; font-size: 10px; "
            "padding: 4px 8px; border-radius: 6px;"
        )
        agent_header.addWidget(self.engine_toggle)
        agent_header.addStretch(1)
        self.refresh_models_button = QtWidgets.QPushButton("Refresh Models")
        self.refresh_models_button.setObjectName("linkButton")
        self.refresh_models_button.setToolTip(
            "Refresh the list of available AI models from your API endpoint.\n"
            "Use this to see newly available models or after changing endpoints."
        )
        self.refresh_models_button.clicked.connect(self._refresh_models)
        agent_header.addWidget(self.refresh_models_button)
        layout.addLayout(agent_header)

        self.engine_content = QtWidgets.QWidget()
        engine_content_layout = QtWidgets.QVBoxLayout(self.engine_content)
        engine_content_layout.setContentsMargins(0, 0, 0, 0)
        engine_content_layout.setSpacing(12)

        agent_card = QtWidgets.QFrame()
        agent_card.setObjectName("card")
        agent_layout = QtWidgets.QVBoxLayout(agent_card)
        agent_layout.setSpacing(12)

        api_label = QtWidgets.QLabel("API Key")
        api_label.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        agent_layout.addWidget(api_label)
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        agent_layout.addWidget(self.api_key_edit)

        form_row = QtWidgets.QHBoxLayout()
        model_col = QtWidgets.QVBoxLayout()
        model_col.addWidget(QtWidgets.QLabel("Model Selection"))
        self.model_edit = QtWidgets.QComboBox()
        self.model_edit.setEditable(False)
        model_col.addWidget(self.model_edit)
        endpoint_col = QtWidgets.QVBoxLayout()
        endpoint_col.addWidget(QtWidgets.QLabel("Endpoint"))
        self.endpoint_edit = QtWidgets.QLineEdit()
        endpoint_col.addWidget(self.endpoint_edit)
        form_row.addLayout(model_col, 1)
        form_row.addLayout(endpoint_col, 1)
        agent_layout.addLayout(form_row)

        self.test_button = QtWidgets.QPushButton("Test Connection")
        self.test_button.setObjectName("primaryButton")
        self.test_button.setToolTip(
            "Test the connection to the AI model API.\n"
            "Verifies your API key and endpoint are working correctly."
        )
        self.test_button.clicked.connect(self._test_connection)
        agent_layout.addWidget(self.test_button)
        engine_content_layout.addWidget(agent_card)
        layout.addWidget(self.engine_content)

        ref_header = QtWidgets.QHBoxLayout()
        ref_title = QtWidgets.QLabel("REFERENCE IMAGE")
        ref_title.setStyleSheet("color: #64748b; font-weight: 700; letter-spacing: 2px; font-size: 10px;")
        ref_header.addWidget(ref_title)
        ref_header.addStretch(1)
        self.reference_status = QtWidgets.QLabel("EMPTY")
        self.reference_status.setStyleSheet("color: #FBBF24; font-weight: 700;")
        ref_header.addWidget(self.reference_status)
        layout.addLayout(ref_header)

        ref_grid = QtWidgets.QGridLayout()
        self.reference_upload = QtWidgets.QPushButton("UPLOAD REFERENCE")
        self.reference_upload.setObjectName("uploadTile")
        self.reference_upload.setToolTip(
            "Upload a reference image showing the desired color grade.\n"
            "The agent will try to match the current frame to this look.\n"
            "Supports: PNG, JPG, JPEG, BMP formats."
        )
        self.reference_upload.clicked.connect(self._select_reference)
        ref_grid.addWidget(self.reference_upload, 0, 0)

        self.reference_preview_large = QtWidgets.QLabel("No reference selected")
        self.reference_preview_large.setAlignment(QtCore.Qt.AlignCenter)
        self.reference_preview_large.setObjectName("previewTile")
        self.reference_preview_large.setFixedSize(320, 180)
        ref_grid.addWidget(self.reference_preview_large, 0, 1, 2, 1)

        info_col = QtWidgets.QVBoxLayout()
        self.reference_label = QtWidgets.QLabel("No file selected")
        self.reference_label.setStyleSheet("color: #E5E7EB; font-weight: 600;")
        info_col.addWidget(self.reference_label)
        self.reference_preview = QtWidgets.QLabel()
        self.reference_preview.setFixedSize(64, 64)
        self.reference_preview.setAlignment(QtCore.Qt.AlignCenter)
        self.reference_preview.setStyleSheet("border: 1px solid #1f2a37; border-radius: 8px; background: #0b1118;")
        info_col.addWidget(self.reference_preview)
        self.reference_meta_label = QtWidgets.QLabel("-")
        self.reference_meta_label.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        info_col.addWidget(self.reference_meta_label)
        info_col.addStretch(1)
        ref_grid.addLayout(info_col, 1, 0)

        layout.addLayout(ref_grid)

        # Instructions Section
        instr_header = QtWidgets.QHBoxLayout()
        instr_title = QtWidgets.QLabel("GPT INSTRUCTIONS")
        instr_title.setStyleSheet("color: #64748b; font-weight: 700; letter-spacing: 2px; font-size: 10px;")
        instr_header.addWidget(instr_title)
        instr_header.addStretch(1)
        layout.addLayout(instr_header)

        self.instructions_edit = QtWidgets.QTextEdit()
        self.instructions_edit.setPlaceholderText("e.g. Add saturation, decrease shadows...")
        self.instructions_edit.setFixedHeight(60)
        self.instructions_edit.setToolTip("Enter short instructions for the AI to follow (e.g. from ChatGPT).")
        layout.addWidget(self.instructions_edit)

        live_header = QtWidgets.QHBoxLayout()
        live_title = QtWidgets.QLabel("LIVE STATUS")
        live_title.setStyleSheet("color: #64748b; font-weight: 700; letter-spacing: 2px; font-size: 10px;")
        live_header.addWidget(live_title)
        live_header.addStretch(1)
        self.rollback_button = QtWidgets.QPushButton("Rollback Step")
        self.rollback_button.setObjectName("linkButton")
        self.rollback_button.setToolTip(
            "Undo the last action performed by the agent.\n"
            "Attempts to reverse the most recent control adjustment."
        )
        live_header.addWidget(self.rollback_button)
        live_header.addSpacing(12)
        live_stats = QtWidgets.QHBoxLayout()
        self.iteration_label = QtWidgets.QLabel("0000")
        self.iteration_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #137fec;")
        self.similarity_label = QtWidgets.QLabel("0.0%")
        self.similarity_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #137fec;")
        live_stats.addWidget(QtWidgets.QLabel("Iteration"))
        live_stats.addWidget(self.iteration_label)
        live_stats.addSpacing(12)
        live_stats.addWidget(QtWidgets.QLabel("Similarity"))
        live_stats.addWidget(self.similarity_label)
        live_header.addLayout(live_stats)
        layout.addLayout(live_header)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.thumbnail_label = QtWidgets.QLabel()
        self.thumbnail_label.setFixedHeight(220)
        self.thumbnail_label.setAlignment(QtCore.Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("border: 1px solid #1f2a37; border-radius: 12px; background: #0b1118;")
        layout.addWidget(self.thumbnail_label)

        controls_grid = QtWidgets.QGridLayout()

        self.calibrate_button = QtWidgets.QPushButton("Calibrate ROI")
        self.calibrate_button.setToolTip(
            "Define the Region of Interest (ROI) in DaVinci Resolve.\n"
            "Click to open a full-screen overlay, then drag to draw a box\n"
            "around the video preview area you want to match."
        )

        self.continuous_checkbox = QtWidgets.QCheckBox("Continuous Mode")
        self.continuous_checkbox.setToolTip("If checked, the agent will keep running iterations until stopped or the goal is reached.")
        controls_grid.addWidget(self.continuous_checkbox, 0, 1)

        self.start_button = QtWidgets.QPushButton("Start")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setToolTip(
            "Start one iteration of AI-powered color grading.\n"
            "The agent will capture the current frame, compare it to your reference,\n"
            "ask the AI what adjustments to make, and execute those actions.\n"
            "Requires: Reference image + ROI calibration."
        )

        self.pause_button = QtWidgets.QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.setToolTip(
            "Pause the automation process.\n"
            "The agent will stop after completing the current action.\n"
            "You can also press the PAUSE/BREAK key to stop immediately."
        )

        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.setToolTip(
            "Stop the automation immediately.\n"
            "Any in-progress actions will be canceled."
        )

        # Run Controller Tests button
        self.run_tests_button = QtWidgets.QPushButton("Run Controller Tests")
        self.run_tests_button.setToolTip(
            "Run the end-to-end controller test suite (sliders & wheels).\n"
            "Ensure DaVinci Resolve is open and visible."
        )

        controls_grid.addWidget(self.calibrate_button, 0, 0)
        controls_grid.addWidget(self.start_button, 0, 2)
        controls_grid.addWidget(self.pause_button, 0, 3)
        controls_grid.addWidget(self.stop_button, 0, 4)
        controls_grid.addWidget(self.run_tests_button, 0, 5)
        layout.addLayout(controls_grid)

        log_header = QtWidgets.QHBoxLayout()
        log_title = QtWidgets.QLabel("ACTION LOG")
        log_title.setStyleSheet("color: #64748b; font-weight: 700; letter-spacing: 2px; font-size: 10px;")
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        self.clear_log_button = QtWidgets.QPushButton("Clear Log")
        self.clear_log_button.setObjectName("linkButton")
        self.clear_log_button.setToolTip("Clear all messages from the action log.")
        self.clear_log_button.clicked.connect(self._clear_log)
        log_header.addWidget(self.clear_log_button)
        layout.addLayout(log_header)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(200)
        layout.addWidget(self.log_view)

        self.setCentralWidget(central)

        self.calibrate_button.clicked.connect(self._calibrate)
        self.start_button.clicked.connect(self._start_once)
        self.stop_button.clicked.connect(self._stop)
        self.rollback_button.clicked.connect(self._rollback)
        self.run_tests_button.clicked.connect(self._run_tests)

    def _install_ui_logger(self):
        emitter = _LogEmitter(self)
        emitter.message.connect(self._append_log_plain)
        handler = _QtLogHandler(emitter)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root_logger = logging.getLogger()
        if not any(isinstance(h, _QtLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(handler)

    def _load_settings(self):
        settings = self.settings_store.load_settings()
        self.api_key_edit.setText(settings.api_key or "")
        model_value = settings.model or "gpt-4o-mini"
        if self.model_edit.findText(model_value) == -1:
            self.model_edit.addItem(model_value)
        self.model_edit.setCurrentText(model_value)
        self.endpoint_edit.setText(settings.endpoint or "https://api.openai.com/v1/chat/completions")
        self.logger.info("Settings loaded")
        QtCore.QTimer.singleShot(0, self._refresh_models)

    def closeEvent(self, event: QtGui.QCloseEvent):
        self._save_settings()
        super().closeEvent(event)

    def _save_settings(self):
        self.settings_store.save_settings(
            api_key=self.api_key_edit.text().strip(),
            model=self.model_edit.currentText().strip(),
            endpoint=self.endpoint_edit.text().strip(),
        )
        self.logger.info("Settings saved")

    def _select_reference(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Reference Image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if not path:
            return
        self.reference_image_path = Path(path)
        self.reference_label.setText(self.reference_image_path.name)
        self._update_reference_preview(self.reference_image_path)
        self.reference_status.setText("SELECTED")
        self.reference_status.setStyleSheet("color: #34D399; font-weight: 700;")
        self.logger.info("Reference selected: %s", self.reference_image_path)
        self._update_button_states()

    def _update_reference_preview(self, path: Path):
        try:
            with Image.open(path) as img:
                width, height = img.size
                img = img.convert("RGB")
                thumb = img.copy()
                thumb.thumbnail((64, 64), Image.LANCZOS)
                qimage_thumb = QtGui.QImage(thumb.tobytes(), thumb.width, thumb.height, QtGui.QImage.Format_RGB888)
                thumb_pixmap = QtGui.QPixmap.fromImage(qimage_thumb.copy())
                self.reference_preview.setPixmap(thumb_pixmap)

                qimage_full = QtGui.QImage(img.tobytes(), img.width, img.height, QtGui.QImage.Format_RGB888)
                full_pixmap = QtGui.QPixmap.fromImage(qimage_full.copy())
                scaled = full_pixmap.scaled(
                    self.reference_preview_large.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self.reference_preview_large.setPixmap(scaled)
            size_mb = path.stat().st_size / (1024 * 1024)
            self.reference_meta_label.setText(f"{width} x {height} • {size_mb:.1f}MB")
        except Exception as exc:
            self.reference_meta_label.setText("Preview unavailable")
            self.logger.warning("Failed to load reference preview: %s", exc)

    def _calibrate(self):
        self.hide()
        try:
            dialog = RoiSelectorDialog(self)
            if dialog.exec() == QtWidgets.QDialog.Accepted:
                roi = dialog.selected_roi
                if roi is None:
                    return
                if roi.width <= 1 or roi.height <= 1:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Invalid ROI",
                        "ROI size is too small. Drag to select a larger area.",
                    )
                    return
                if self.calibration:
                    self.calibration.update_roi(roi)
                else:
                    self.calibration = CalibrationProfile.from_roi(roi)
                self.settings_store.save_calibration(self.calibration)
                self._append_log(f"Calibrated ROI: {self.calibration.roi}")
                self.logger.info("Calibrated ROI: %s", self.calibration.roi)
                self._update_button_states()
        finally:
            self.show()

    def _is_calibration_complete(self) -> bool:
        """Check if minimum calibration requirements are met to start automation."""
        return self.reference_image_path is not None and self.calibration is not None

    def _update_button_states(self):
        """Update button enabled/disabled states based on current configuration."""
        is_ready = self._is_calibration_complete()
        self.start_button.setEnabled(is_ready)

        # Update tooltip for start button to show what's missing
        if not is_ready:
            missing = []
            if self.reference_image_path is None:
                missing.append("reference image")
            if self.calibration is None:
                missing.append("ROI calibration")

            self.start_button.setToolTip(
                f"Cannot start: Missing {', '.join(missing)}.\n\n"
                "To enable:\n"
                "1. Upload a reference image\n"
                "2. Calibrate ROI (draw box around video preview)\n"
                "3. Optionally calibrate controls for better accuracy"
            )
        else:
            self.start_button.setToolTip(
                "Start one iteration of AI-powered color grading.\n"
                "The agent will capture the current frame, compare it to your reference,\n"
                "ask the AI what adjustments to make, and execute those actions.\n"
                "Requires: Reference image + ROI calibration."
            )

    def _confirm_first_run(self) -> bool:
        dialog = _ConfirmDialog(self, "This will control your mouse/keyboard. Continue?")
        return dialog.exec() == QtWidgets.QDialog.Accepted

    def _start_once(self):
        if not self._confirm_first_run():
            return
        self._save_settings()
        if self.reference_image_path is None:
            QtWidgets.QMessageBox.warning(self, "Missing reference", "Upload a reference image first.")
            return
        if self.calibration is None:
            QtWidgets.QMessageBox.warning(self, "Missing calibration", "Calibrate ROI first.")
            return

        if self.session_logger is None:
            self.session_logger = SessionLogger()
        
        # Log session info (settings and calibration)
        settings = self.settings_store.load_settings()
        settings_dict = {
            "model": settings.model,
            "endpoint": settings.endpoint,
        }
        calibration_dict = self.calibration.to_dict() if self.calibration else {}
        self.session_logger.log_session_info(settings_dict, calibration_dict)

        self.hide()
        self.start_button.setEnabled(False)
        self.continuous_checkbox.setEnabled(False)
        self.logger.info("Starting automation (continuous=%s)", self.continuous_checkbox.isChecked())
        thread = threading.Thread(target=self._run_iteration, daemon=True)
        thread.start()

    def _run_iteration(self):
        try:
            self.executor.ensure_safe_mode()
            while True:
                if self.executor._stop:
                    break
                
                roi_image = capture_roi(self.calibration.roi)
                ref_path = self.reference_image_path
                if ref_path is None:
                    break
                
                metrics = compute_metrics(ref_path, roi_image)
                ctx = LlmRequestContext(
                    reference_image_path=ref_path,
                    current_image=roi_image,
                    previous_image=None,
                    metrics=metrics,
                    calibration=self.calibration,
                    instructions=self.instructions_edit.toPlainText().strip()
                )
                
                self.logger.info("Requesting LLM actions")
                response = self.llm_client.request_actions(ctx)
                
                if response.stop:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_append_log",
                        QtCore.Qt.QueuedConnection,
                        QtCore.Q_ARG(str, "LLM requested stop or low confidence."),
                    )
                    break
                
                actions = response.actions[:3]
                self.logger.info("Executing %d actions", len(actions))
                self.executor.execute_actions(actions, self.calibration, self.iteration, self.session_logger)
                
                after_image = capture_roi(self.calibration.roi)
                after_metrics = compute_metrics(ref_path, after_image)
                self.iteration += 1
                self.last_metrics = after_metrics
                
                if self.session_logger:
                    self.session_logger.log_iteration(self.iteration, roi_image, after_image, metrics, response)
                
                after_payload = (after_image.tobytes(), (after_image.width, after_image.height))
                self.iteration_updated.emit(
                    self.iteration,
                    f"{after_metrics.overall:.3f}",
                    after_payload,
                    json.dumps(response.raw, indent=2),
                    response.raw.get("summary", "")
                )

                if not self.continuous_checkbox.isChecked():
                    break
                    
                # Small delay between iterations in continuous mode
                time.sleep(1.0)
                
        except Exception as exc:
            self.logger.exception("Iteration failed")
            QtCore.QMetaObject.invokeMethod(
                self,
                "_show_error",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, str(exc)),
            )
        finally:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_finish_iteration",
                QtCore.Qt.QueuedConnection,
            )

    @QtCore.Slot(int, str, object, str, str)
    def _update_status(self, iteration: int, similarity: str, image, log: str, summary: str):
        self.iteration_label.setText(str(iteration))
        self.similarity_label.setText(f"{float(similarity) * 100:.1f}%")
        self.progress_bar.setValue(int(float(similarity) * 100))
        qimage = self._to_qimage(image)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        scaled = pixmap.scaled(self.thumbnail_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.thumbnail_label.setPixmap(scaled)
        self._append_log(log)
        if summary:
            self.instructions_edit.setText(summary)

    def _to_qimage(self, image) -> QtGui.QImage:
        if isinstance(image, tuple) and len(image) == 2:
            data, size = image
            if not isinstance(size, tuple) or len(size) != 2:
                raise ValueError("Unsupported image payload for preview.")
            width, height = size
            buffer = bytes(data)
            qimage = QtGui.QImage(buffer, width, height, width * 3, QtGui.QImage.Format_RGB888)
            return qimage.copy()
        if isinstance(image, Image.Image):
            if image.mode != "RGB":
                image = image.convert("RGB")
            data = image.tobytes()
            qimage = QtGui.QImage(data, image.width, image.height, image.width * 3, QtGui.QImage.Format_RGB888)
            return qimage.copy()
        if isinstance(image, QtGui.QImage):
            return image
        raise ValueError("Unsupported image type for preview.")

    @QtCore.Slot()
    def _finish_iteration(self):
        self.start_button.setEnabled(True)
        self.continuous_checkbox.setEnabled(True)
        self.show()
        self.raise_()
        self.activateWindow()

    @QtCore.Slot(str)
    def _show_error(self, message: str):
        QtWidgets.QMessageBox.critical(self, "Error", message)
        self._append_log(message)

    @QtCore.Slot(str)
    def _set_test_status(self, message: str):
        self.connection_label.setText(message)
        if message.startswith("OK"):
            self.connection_label.setStyleSheet("color: #34D399; font-weight: 600;")
        else:
            self.connection_label.setStyleSheet("color: #F87171; font-weight: 600;")

    @QtCore.Slot(str)
    def _append_log_plain(self, text: str):
        self.log_view.append(text)

    def _append_log(self, text: str):
        self.log_view.append(text)
        self.logger.info(text)

    def _stop(self):
        self.executor.trigger_stop()
        self._append_log("Stop requested.")
        self.logger.info("Stop triggered")
        # Ensure we can re-enable UI if it was hidden
        self.start_button.setEnabled(True)
        self.continuous_checkbox.setEnabled(True)
        self.show()

    def on_stop_triggered(self):
        self._append_log("Global stop triggered.")
        self.logger.info("Global stop triggered")

    def _rollback(self):
        self.executor.undo_last()
        self._append_log("Rollback requested.")
        self.logger.info("Rollback requested")

    def _test_connection(self):
        self._save_settings()
        self.test_button.setEnabled(False)
        self.connection_label.setText("Testing...")
        self.connection_label.setStyleSheet("color: #FBBF24; font-weight: 600;")
        thread = threading.Thread(target=self._run_test_connection, daemon=True)
        thread.start()

    def _run_test_connection(self):
        try:
            response = self.llm_client.test_connection()
            message = response.get("choices", [{}])[0].get("message", {}).get("content", "OK")
            QtCore.QMetaObject.invokeMethod(
                self,
                "_set_test_status",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, f"OK: {message}"),
            )
            QtCore.QMetaObject.invokeMethod(
                self,
                "_show_info",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, f"Test connection OK: {message}"),
            )
        except Exception as exc:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_set_test_status",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, f"Failed: {exc}"),
            )
            QtCore.QMetaObject.invokeMethod(
                self,
                "_show_error",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, f"Test connection failed: {exc}"),
            )
        finally:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_enable_test_button",
                QtCore.Qt.QueuedConnection,
            )

    @QtCore.Slot()
    def _enable_test_button(self):
        self.test_button.setEnabled(True)

    @QtCore.Slot(str)
    def _show_info(self, message: str):
        dialog = _InfoDialog(self, message)
        dialog.exec()
        self._append_log(message)

    @QtCore.Slot()
    def _toggle_engine_section(self):
        expanded = self.engine_toggle.isChecked()
        self.engine_toggle.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.engine_content.setVisible(expanded)

    def _refresh_models(self):
        self._save_settings()
        self.refresh_models_button.setEnabled(False)
        thread = threading.Thread(target=self._run_refresh_models, daemon=True)
        thread.start()

    def _run_refresh_models(self):
        try:
            models = self.llm_client.list_models()
            self.models_refreshed.emit(models)
        except Exception as exc:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_show_error",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, f"Model refresh failed: {exc}"),
            )
        finally:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_enable_refresh_models",
                QtCore.Qt.QueuedConnection,
            )

    @QtCore.Slot(list)
    def _apply_models(self, models: list):
        current = self.model_edit.currentText()
        self.model_edit.clear()
        if models:
            self.model_edit.addItems(models)
        if current and self.model_edit.findText(current) != -1:
            self.model_edit.setCurrentText(current)
        elif self.model_edit.count() > 0:
            self.model_edit.setCurrentIndex(0)
        self._append_log(f"Models refreshed: {self.model_edit.count()} available")

    @QtCore.Slot()
    def _enable_refresh_models(self):
        self.refresh_models_button.setEnabled(True)

    @QtCore.Slot()
    def _clear_log(self):
        self.log_view.clear()
        self._append_log("Log cleared.")

    @QtCore.Slot()
    def _run_tests(self):
        # Disable button and run in background to keep UI responsive
        self._append_log("Starting Controller Test Suite...")
        self.run_tests_button.setEnabled(False)
        thread = threading.Thread(target=self._run_tests_thread, daemon=True)
        thread.start()

    def _run_tests_thread(self):
        try:
            root = Path(__file__).resolve().parent.parent
            script = root / "tests" / "test_suite_e2e.py"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root)
            self.logger.info("Launching test suite: %s", script)
            proc = subprocess.Popen([
                "python",
                str(script)
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(root), env=env)
            if proc.stdout is not None:
                for line in proc.stdout:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_append_log_plain",
                        QtCore.Qt.QueuedConnection,
                        QtCore.Q_ARG(str, line.rstrip())
                    )
            code = proc.wait()
            msg = "Controller Tests PASSED" if code == 0 else f"Controller Tests FAILED (exit={code})"
            QtCore.QMetaObject.invokeMethod(
                self,
                "_show_info" if code == 0 else "_show_error",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, msg)
            )
        except Exception as exc:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_show_error",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, f"Failed to run tests: {exc}")
            )
        finally:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_enable_run_tests_button",
                QtCore.Qt.QueuedConnection,
            )

    @QtCore.Slot()
    def _enable_run_tests_button(self):
        self.run_tests_button.setEnabled(True)


def run_app():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.resize(700, 720)
    window.show()
    app.exec()
