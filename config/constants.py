DEFAULT_API_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_FOCUS_TITLE = "DaVinci Resolve"
DEFAULT_KEYRING_SERVICE = "resolve-agent"
DEFAULT_MAX_IMAGE_DIM = 512
DEFAULT_JPEG_QUALITY = 70
DEFAULT_INTER_ACTION_DELAY = 0.1
DEFAULT_CONTINUOUS_DELAY = 1.0

ERROR_ROI_TOO_SMALL = "E101: ROI size is too small. Drag to select a larger area."
ERROR_PRIMARY_SCREEN = "E102: Primary screen not found."
ERROR_CONTROLLER_CONFIG_MISSING = "E103: controllerConfig.json not found."
ERROR_CALIBRATION_FAILED = "E104: Calibration failed: {details}"
ERROR_SECURE_STORAGE_UNAVAILABLE = (
    "E201: Secure API key storage unavailable. Please install keyring or confirm insecure save."
)
ERROR_INSECURE_STORAGE_WARNING = "E202: API key will be stored in plain text because keyring is unavailable."
