from calibration.profile import CalibrationProfile
from app_ui.roi_selector import Roi


def test_calibration_roundtrip():
    roi = Roi(10, 20, 300, 200)
    profile = CalibrationProfile.from_roi(roi)
    data = profile.to_dict()
    restored = CalibrationProfile.from_dict(data)
    assert restored.roi["width"] == 300
