from calibration.profile import CalibrationProfile
from core.roi import Roi


def test_from_dict_adds_roi_center():
    data = {
        "roi": {"x": 10, "y": 20, "width": 100, "height": 50},
        "targets": {},
    }
    profile = CalibrationProfile.from_dict(data)
    assert "roi_center" in profile.targets
    assert profile.targets["roi_center"]["x"] == 60
    assert profile.targets["roi_center"]["y"] == 45
    assert profile.control_metadata is not None
    assert profile.control_metadata["roi_center"]["type"] == "point"


def test_update_roi_updates_center():
    profile = CalibrationProfile.from_roi(Roi(0, 0, 10, 10))
    profile.update_roi(Roi(10, 20, 30, 40))
    assert profile.targets["roi_center"]["x"] == 25
    assert profile.targets["roi_center"]["y"] == 40
