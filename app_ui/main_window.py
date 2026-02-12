import logging
import os
import subprocess
from pathlib import Path

from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from config.settings import get_app_settings
from calibration.profile import CalibrationProfile
from controllers.agent_controller import AgentController
from controllers.calibration_manager import CalibrationManager
from controllers.iteration_runner import IterationRunner
from controllers.settings_manager import SettingsManager
from controllers.task_queue import TaskQueue
from llm.client import DEFAULT_VISION_MODELS
from vision.metrics import SimilarityMetrics


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
        if self.style():
            pixmap = self.style().standardPixmap(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxInformation)
            if pixmap and not pixmap.isNull():
                icon.setPixmap(
                    pixmap.scaled(
                        32,
                        32,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )

        text = QtWidgets.QLabel(message)
        text.setStyleSheet("font-size: 14px;")
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
        if self.style():
            pixmap = self.style().standardPixmap(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxQuestion)
            if pixmap and not pixmap.isNull():
                icon.setPixmap(
                    pixmap.scaled(
                        32,
                        32,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )

        text = QtWidgets.QLabel(message)
        text.setStyleSheet("font-size: 14px;")
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


class StatusOverlay(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.container = QtWidgets.QFrame()
        self.container.setObjectName("overlayContainer")
        self.container.setStyleSheet("""
            #overlayContainer {
                background-color: rgba(15, 23, 42, 230);
                border: 2px solid #3b82f6;
                border-radius: 12px;
                min-width: 300px;
                max-width: 500px;
            }
            QLabel {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 600;
            }
        """)

        container_layout = QtWidgets.QVBoxLayout(self.container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(16)

        self.spinner = QtWidgets.QProgressBar()
        self.spinner.setRange(0, 0)
        self.spinner.setTextVisible(False)
        self.spinner.setFixedHeight(4)
        self.spinner.setStyleSheet("""
            QProgressBar {
                background: #1e293b;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: #3b82f6;
            }
        """)

        self.label = QtWidgets.QLabel("AI is thinking...")
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)

        container_layout.addWidget(self.spinner)
        container_layout.addWidget(self.label)

        layout.addWidget(self.container)

    def show_message(self, message: str, show_spinner: bool = True):
        self.label.setText(message)
        self.spinner.setVisible(show_spinner)
        self.show()
        self.raise_()


class MainWindow(QtWidgets.QMainWindow):
    models_refreshed = QtCore.Signal(list)
    iteration_updated = QtCore.Signal(int, str, object, str, str)
    reference_preview_ready = QtCore.Signal(object, object, str)

    def __init__(
        self,
        settings_manager: SettingsManager,
        calibration_manager: CalibrationManager,
        agent_controller: AgentController,
        task_queue: TaskQueue,
    ):
        super().__init__()
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
        self.logger = logging.getLogger("app.ui")
        self._app_settings = get_app_settings()
        self.setWindowTitle("Resolve Color Grade Agent (v1)")
        self.settings_manager = settings_manager
        self.calibration_manager = calibration_manager
        self.agent_controller = agent_controller
        self.task_queue = task_queue
        self.calibration = self.calibration_manager.load()
        self.reference_image_path: Path | None = None
        self._build_ui()
        self.status_overlay = StatusOverlay(self)
        self._install_ui_logger()
        self.agent_controller.set_stop_callback(self.on_stop_triggered)
        self.agent_controller.set_log_callback(self._append_log)
        self._apply_theme()
        self.models_refreshed.connect(self._apply_models)
        self.model_edit.currentTextChanged.connect(self._on_model_changed)
        self.iteration_updated.connect(self._update_status)
        self.reference_preview_ready.connect(self._apply_reference_preview)
        self._load_settings()
        self._update_button_states()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "status_overlay"):
            self.status_overlay.setGeometry(self.rect())

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
            "QPushButton#calibrateButton {"
            "  background: #EF4444;"
            "  border: 1px solid #EF4444;"
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
        self.brand_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
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
        self.engine_toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        self.engine_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
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
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
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

        calib_test_row = QtWidgets.QHBoxLayout()
        self.test_button = QtWidgets.QPushButton("Test Connection")
        self.test_button.setObjectName("primaryButton")
        self.test_button.setToolTip(
            "Test the connection to the AI model API.\n" "Verifies your API key and endpoint are working correctly."
        )
        self.test_button.clicked.connect(self._test_connection)

        self.calibrate_button = QtWidgets.QPushButton("Calibrate Controllers")
        self.calibrate_button.setObjectName("calibrateButton")
        self.calibrate_button.clicked.connect(self._calibrate_controllers)
        self.calibrate_button.setToolTip("Mark center of all controllers on a full frame screenshot.")

        # Run Controller Tests button
        self.run_tests_button = QtWidgets.QPushButton("Run Controller Tests")
        self.run_tests_button.setToolTip(
            "Run the end-to-end controller test suite (sliders & wheels).\n"
            "Ensure DaVinci Resolve is open and visible."
        )
        self.run_tests_button.clicked.connect(self._run_tests)

        calib_test_row.addWidget(self.test_button, 1)
        calib_test_row.addWidget(self.calibrate_button, 1)
        calib_test_row.addWidget(self.run_tests_button, 1)
        agent_layout.addLayout(calib_test_row)

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
        self.reference_preview_large.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.reference_preview_large.setObjectName("previewTile")
        self.reference_preview_large.setFixedSize(320, 180)
        ref_grid.addWidget(self.reference_preview_large, 0, 1, 2, 1)

        info_col = QtWidgets.QVBoxLayout()
        self.reference_label = QtWidgets.QLabel("No file selected")
        self.reference_label.setStyleSheet("color: #E5E7EB; font-weight: 600;")
        info_col.addWidget(self.reference_label)
        self.reference_preview = QtWidgets.QLabel()
        self.reference_preview.setFixedSize(64, 64)
        self.reference_preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.reference_preview.setStyleSheet("border: 1px solid #1f2a37; border-radius: 8px; background: #0b1118;")
        info_col.addWidget(self.reference_preview)
        self.reference_meta_label = QtWidgets.QLabel("-")
        self.reference_meta_label.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        info_col.addWidget(self.reference_meta_label)
        info_col.addStretch(1)
        ref_grid.addLayout(info_col, 1, 0)

        layout.addLayout(ref_grid)

        live_header = QtWidgets.QHBoxLayout()
        live_title = QtWidgets.QLabel("LIVE STATUS")
        live_title.setStyleSheet("color: #64748b; font-weight: 700; letter-spacing: 2px; font-size: 10px;")
        live_header.addWidget(live_title)
        live_header.addStretch(1)
        self.rollback_button = QtWidgets.QPushButton("Rollback Step")
        self.rollback_button.setObjectName("linkButton")
        self.rollback_button.setToolTip(
            "Undo the last action performed by the agent.\n" "Attempts to reverse the most recent control adjustment."
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
        self.thumbnail_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setStyleSheet("border: 1px solid #1f2a37; border-radius: 12px; background: #0b1118;")
        layout.addWidget(self.thumbnail_label)

        controls_grid = QtWidgets.QGridLayout()

        self.continuous_checkbox = QtWidgets.QCheckBox("Auto Continue")
        self.continuous_checkbox.setToolTip(
            "If checked, the agent will keep running iterations until stopped\n"
            "or the similarity reaches 95%."
        )
        controls_grid.addWidget(self.continuous_checkbox, 0, 0)

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
        self.stop_button.setToolTip("Stop the automation immediately.\n" "Any in-progress actions will be canceled.")

        controls_grid.addWidget(self.start_button, 0, 1)
        controls_grid.addWidget(self.pause_button, 0, 2)
        controls_grid.addWidget(self.stop_button, 0, 3)
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

        self.start_button.clicked.connect(self._start_once)
        self.stop_button.clicked.connect(self._stop)
        self.rollback_button.clicked.connect(self._rollback)

    def _install_ui_logger(self):
        emitter = _LogEmitter(self)
        emitter.message.connect(self._append_log_plain)
        handler = _QtLogHandler(emitter)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root_logger = logging.getLogger()
        if not any(isinstance(h, _QtLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(handler)

    def _load_settings(self):
        settings = self.settings_manager.load()
        self.api_key_edit.setText(settings.api_key or "")
        model_value = settings.model or self._app_settings.default_model
        if self.model_edit.findText(model_value) == -1:
            self.model_edit.addItem(model_value)
        self.model_edit.setCurrentText(model_value)
        self.endpoint_edit.setText(settings.endpoint or self._app_settings.api_endpoint)
        
        # Load calibration from config if available
        config_calibration = CalibrationProfile.from_config()
        if config_calibration:
            self.calibration = config_calibration
            self.logger.info("Calibration loaded from controllerConfig.json")

        self.logger.info("Settings loaded")
        QtCore.QTimer.singleShot(0, self._refresh_models)

    def closeEvent(self, event: QtGui.QCloseEvent):
        self._save_settings()
        super().closeEvent(event)

    def _save_settings(self):
        api_key = self.api_key_edit.text().strip()
        model = self.model_edit.currentText().strip()
        endpoint = self.endpoint_edit.text().strip()
        try:
            self.settings_manager.save(api_key=api_key, model=model, endpoint=endpoint)
        except RuntimeError as exc:
            dialog = _ConfirmDialog(
                self,
                "Secure key storage is unavailable. Storing the API key in plain text is unsafe."
                "\n\nDo you want to proceed with an insecure save?",
            )
            if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                self.settings_manager.save(api_key=api_key, model=model, endpoint=endpoint, allow_insecure=True)
                self.logger.warning("Settings saved with insecure API key storage.")
            else:
                self.logger.warning("Settings not saved: %s", exc)

    def _calibrate_controllers(self):
        self._append_log("Focusing DaVinci Resolve...")
        self.calibration = self.calibration_manager.calibrate_controllers(
            parent=self,
            executor=self.agent_controller.executor,
            calibration=self.calibration,
        )
        self._update_button_states()

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
        self.reference_meta_label.setText("Loading preview...")
        self.task_queue.run(lambda: self._load_reference_preview(path))

    def _load_reference_preview(self, path: Path) -> None:
        try:
            with Image.open(path) as opened:
                img = opened.convert("RGB")
                width, height = img.size
                thumb = img.copy()
                resample = (
                    Image.Resampling.LANCZOS
                    if hasattr(Image, "Resampling")
                    else Image.BICUBIC  # type: ignore[attr-defined]
                )
                thumb.thumbnail((64, 64), resample)
                thumb_image = self._pil_to_qimage(thumb)
                full_image = self._pil_to_qimage(img)
            size_mb = path.stat().st_size / (1024 * 1024)
            meta = f"{width} x {height} • {size_mb:.1f}MB"
            self.reference_preview_ready.emit(thumb_image, full_image, meta)
        except Exception as exc:
            self.logger.warning("Failed to load reference preview: %s", exc)
            self.reference_preview_ready.emit(None, None, "Preview unavailable")

    @QtCore.Slot(object, object, str)
    def _apply_reference_preview(self, thumb_image, full_image, meta: str) -> None:
        if isinstance(thumb_image, QtGui.QImage):
            thumb_pixmap = QtGui.QPixmap.fromImage(thumb_image)
            self.reference_preview.setPixmap(thumb_pixmap)
        if isinstance(full_image, QtGui.QImage):
            full_pixmap = QtGui.QPixmap.fromImage(full_image)
            scaled = full_pixmap.scaled(
                self.reference_preview_large.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self.reference_preview_large.setPixmap(scaled)
        self.reference_meta_label.setText(meta)

    @staticmethod
    def _pil_to_qimage(image: Image.Image) -> QtGui.QImage:
        data = image.tobytes()
        qimage = QtGui.QImage(data, image.width, image.height, image.width * 3, QtGui.QImage.Format.Format_RGB888)
        return qimage.copy()

    def _is_calibration_complete(self) -> bool:
        """Check if minimum calibration requirements are met to start automation."""
        return self.reference_image_path is not None and self.calibration is not None

    def _is_controllers_calibrated(self) -> bool:
        """Check if controllers have been calibrated."""
        return self.calibration_manager.is_controllers_calibrated()

    def _update_button_states(self):
        """Update button enabled/disabled states based on current configuration."""
        # Always enable start button to allow showing warning messages when clicked
        self.start_button.setEnabled(True)

        is_calibrated = self._is_controllers_calibrated()
        self.run_tests_button.setEnabled(is_calibrated)

        # Update Calibrate Controllers button based on status
        if is_calibrated:
            self.calibrate_button.setText("ReCalibrate Controllers")
            self.calibrate_button.setStyleSheet(
                "background: #374151; border: 1px solid #374151; color: #FFFFFF; "
                "border-radius: 16px; padding: 10px 16px; font-weight: 600;"
            )
            self.run_tests_button.setToolTip("Run the end-to-end controller test suite (sliders & wheels).")
        else:
            self.calibrate_button.setText("Calibrate Controllers")
            self.calibrate_button.setStyleSheet(
                "background: #EF4444; border: 1px solid #EF4444; color: #FFFFFF; "
                "border-radius: 16px; padding: 10px 16px; font-weight: 600;"
            )
            self.run_tests_button.setToolTip("Cannot run tests: Controllers not calibrated yet.")

        # Update tooltip for start button to show what's missing
        is_ready = self._is_calibration_complete()
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
                "2. Calibrate Controllers (includes ROI drawing)\n"
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
        return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted

    def _start_once(self):
        if self.reference_image_path is None:
            msg = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Icon.Warning, "Missing reference", "Upload a reference image first.", parent=self
            )
            msg.setStyleSheet(self.styleSheet())
            msg.exec()
            return
        if self.calibration is None:
            msg = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Icon.Warning, "Missing calibration", "Calibrate ROI first.", parent=self
            )
            msg.setStyleSheet(self.styleSheet())
            msg.exec()
            return

        if not self._confirm_first_run():
            return
        self._save_settings()

        # Log session info (settings and calibration)
        self.agent_controller.ensure_session_logger()
        settings = self.settings_manager.load()
        settings_dict = {
            "model": settings.model,
            "endpoint": settings.endpoint,
        }
        calibration_dict = self.calibration.to_dict() if self.calibration else {}
        self.agent_controller.log_session_info(settings_dict, calibration_dict)

        self.start_button.setEnabled(False)
        self.continuous_checkbox.setEnabled(False)
        self.logger.info("Starting automation (continuous=%s)", self.continuous_checkbox.isChecked())
        self.task_queue.run(self._run_iteration)

    def _run_iteration(self):
        try:
            ref_path = self.reference_image_path
            if ref_path is None:
                return
            calibration = self.calibration
            if calibration is None:
                return

            def on_iteration_updated(iteration: int, metrics: SimilarityMetrics, image, raw: dict, summary: str):
                self.iteration_updated.emit(
                    iteration,
                    f"{metrics.overall:.3f}",
                    image,
                    IterationRunner.format_response_payload(raw),
                    summary,
                )

            def on_log(message: str):
                QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                    self,
                    "_append_log",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, message),
                )

            def on_thinking_started():
                QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                    self,
                    "_on_thinking_started",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                )

            def on_recommendation_received(summary: str):
                QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                    self,
                    "_on_recommendation_received",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, summary),
                )

            def on_recommendation_closed():
                QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                    self,
                    "_on_recommendation_closed",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                )

            self.agent_controller.run_iteration(
                reference_image_path=ref_path,
                calibration=calibration,
                instructions="",
                continuous=self.continuous_checkbox.isChecked(),
                on_iteration_updated=on_iteration_updated,
                on_log=on_log,
                on_thinking_started=on_thinking_started,
                on_recommendation_received=on_recommendation_received,
                on_recommendation_closed=on_recommendation_closed,
            )

        except Exception as exc:
            self.logger.exception("Iteration failed")
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_show_error",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, str(exc)),
            )
        finally:
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_finish_iteration",
                QtCore.Qt.ConnectionType.QueuedConnection,
            )

    @QtCore.Slot(str)
    def _on_model_changed(self, model_name: str):
        if model_name in DEFAULT_VISION_MODELS:
            self.endpoint_edit.setText(DEFAULT_VISION_MODELS[model_name])

    @QtCore.Slot(int, str, object, str, str)
    def _update_status(self, iteration: int, similarity: str, image, log: str, summary: str):
        self.iteration_label.setText(str(iteration))
        self.similarity_label.setText(f"{float(similarity) * 100:.1f}%")
        self.progress_bar.setValue(int(float(similarity) * 100))
        qimage = self._to_qimage(image)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        scaled = pixmap.scaled(
            self.thumbnail_label.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.thumbnail_label.setPixmap(scaled)
        self._append_log(log)

    def _to_qimage(self, image) -> QtGui.QImage:
        if isinstance(image, tuple) and len(image) == 2:
            data, size = image
            if not isinstance(size, tuple) or len(size) != 2:
                raise ValueError("Unsupported image payload for preview.")
            width, height = size
            buffer = bytes(data)
            qimage = QtGui.QImage(buffer, width, height, width * 3, QtGui.QImage.Format.Format_RGB888)
            return qimage.copy()
        if isinstance(image, Image.Image):
            if image.mode != "RGB":
                image = image.convert("RGB")
            data = image.tobytes()
            qimage = QtGui.QImage(data, image.width, image.height, image.width * 3, QtGui.QImage.Format.Format_RGB888)
            return qimage.copy()
        if isinstance(image, QtGui.QImage):
            return image
        raise ValueError("Unsupported image type for preview.")

    @QtCore.Slot()
    def _on_thinking_started(self):
        self.status_overlay.show_message("AI is thinking...", show_spinner=True)

    @QtCore.Slot(str)
    def _on_recommendation_received(self, summary: str):
        self.status_overlay.show_message(summary or "Applying adjustments...", show_spinner=False)

    @QtCore.Slot()
    def _on_recommendation_closed(self):
        self.status_overlay.hide()

    @QtCore.Slot()
    def _finish_iteration(self):
        self.start_button.setEnabled(True)
        self.continuous_checkbox.setEnabled(True)
        self.show()
        self.raise_()
        self.activateWindow()

    @QtCore.Slot(str)
    def _show_error(self, message: str):
        msg = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Icon.Critical, "Error", message, parent=self)
        msg.setStyleSheet(self.styleSheet())
        msg.exec()
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
        self.agent_controller.stop()
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
        self.agent_controller.rollback()
        self._append_log("Rollback requested.")
        self.logger.info("Rollback requested")

    def _test_connection(self):
        self._save_settings()
        self.test_button.setEnabled(False)
        self.connection_label.setText("Testing...")
        self.connection_label.setStyleSheet("color: #FBBF24; font-weight: 600;")
        self.task_queue.run(self._run_test_connection)

    def _run_test_connection(self):
        try:
            response = self.agent_controller.test_connection()
            message = response.get("choices", [{}])[0].get("message", {}).get("content", "OK")
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_set_test_status",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, f"OK: {message}"),
            )
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_show_info",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, f"Test connection status: {message}"),
            )
        except Exception as exc:
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_set_test_status",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, f"Failed: {exc}"),
            )
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_show_error",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, f"Test connection failed: {exc}"),
            )
        finally:
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_enable_test_button",
                QtCore.Qt.ConnectionType.QueuedConnection,
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
        self.engine_toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)
        self.engine_content.setVisible(expanded)

    def _refresh_models(self):
        self._save_settings()
        self.refresh_models_button.setEnabled(False)
        self.task_queue.run(self._run_refresh_models)

    def _run_refresh_models(self):
        try:
            models = self.agent_controller.list_models()
            self.models_refreshed.emit(models)
        except Exception as exc:
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_show_error",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, f"Model refresh failed: {exc}"),
            )
        finally:
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_enable_refresh_models",
                QtCore.Qt.ConnectionType.QueuedConnection,
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
        self.task_queue.run(self._run_tests_thread)

    def _run_tests_thread(self):
        try:
            root = Path(__file__).resolve().parent.parent
            script = root / "tests" / "test_controllers_median.py"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root)
            env["AGENT_E2E"] = "1"
            self.logger.info("Launching test suite: %s", script)
            proc = subprocess.Popen(
                ["python", "-u", str(script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(root),
                env=env,
            )
            if proc.stdout is not None:
                for line in proc.stdout:
                    QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                        self,
                        "_append_log_plain",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, line.rstrip()),
                    )
            code = proc.wait()
            if code == 0:
                msg = "Controller Tests PASSED"
                icon = QtWidgets.QMessageBox.Icon.Information
            elif code == 2:
                msg = "Recalibration suggested."
                icon = QtWidgets.QMessageBox.Icon.Warning
                # Trigger recalibration
                QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                    self, "_calibrate_controllers", QtCore.Qt.ConnectionType.QueuedConnection
                )
            else:
                msg = f"Controller Tests FAILED (exit={code})"
                icon = QtWidgets.QMessageBox.Icon.Critical

            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_show_message",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, msg),
                QtCore.Q_ARG(object, icon),
            )
        except Exception as exc:
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_show_error",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, f"Failed to run tests: {exc}"),
            )
        finally:
            QtCore.QMetaObject.invokeMethod(  # type: ignore[call-overload]
                self,
                "_enable_run_tests_button",
                QtCore.Qt.ConnectionType.QueuedConnection,
            )

    @QtCore.Slot(str, object)
    def _show_message(self, text, icon_type):
        msg = QtWidgets.QMessageBox(icon_type, "Test Result", text, parent=self)
        msg.setStyleSheet(self.styleSheet())
        msg.exec()

    @QtCore.Slot()
    def _enable_run_tests_button(self):
        self.run_tests_button.setEnabled(True)


def run_app(window: MainWindow):
    app = QtWidgets.QApplication([])
    window.resize(500, 620)
    window.show()
    app.exec()
