import pytest

from automation import executor as executor_module


class DummyCalibration:
    def __init__(self, targets):
        self.targets = targets


def test_action_validator_clamps_drag():
    action = executor_module.Action(type="drag", target="t", dx=500, dy=-500)
    clamped = executor_module.ActionValidator.clamp_drag(action)
    assert clamped.dx == 200
    assert clamped.dy == -200


def test_action_validator_disallows_keys():
    action = executor_module.Action(type="keypress", target="keyboard", keys=["alt", "f4"])
    is_valid, reason = executor_module.ActionValidator.validate(action, DummyCalibration({}))
    assert is_valid is False
    assert reason is not None
    assert "Disallowed" in reason


def test_execute_actions_fail_fast_rolls_back(monkeypatch):
    class DummyListener:
        def __init__(self, on_press=None):
            self.on_press = on_press

        def start(self):
            return None

    monkeypatch.setattr(executor_module.keyboard, "Listener", DummyListener)
    monkeypatch.setattr(executor_module.time, "sleep", lambda *_: None)

    executor = executor_module.ActionExecutor(lambda: None)
    monkeypatch.setattr(executor, "_has_focus", lambda: True)

    call_count = {"count": 0}

    def fake_execute(*_args, **_kwargs):
        call_count["count"] += 1
        return call_count["count"] == 1

    undo_calls = []
    monkeypatch.setattr(executor, "_execute", fake_execute)
    monkeypatch.setattr(executor, "undo_last", lambda: undo_calls.append(True))

    calibration = DummyCalibration({"target": {"x": 1, "y": 2}})
    actions = [
        {"type": "drag", "target": "target", "dx": 1, "dy": 1},
        {"type": "drag", "target": "target", "dx": 1, "dy": 1},
    ]

    with pytest.raises(executor_module.ActionExecutionError):
        executor.execute_actions(actions, calibration, inter_action_delay=0.0, fail_fast=True, rollback_on_fail=True)

    assert len(undo_calls) == 1
