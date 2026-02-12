import pytest

from llm.client import LlmClient


def test_normalize_response_legacy_action():
    data = {
        "action": "set_slider",
        "params": {"slider": "lift", "value": "0.5"},
        "reason": "legacy",
    }
    normalized = LlmClient._normalize_response(data)
    assert normalized["summary"]
    assert normalized["actions"][0]["type"] == "set_slider"
    assert normalized["actions"][0]["target"] == "lift"
    assert normalized["actions"][0]["value"] == 0.5


def test_normalize_response_requires_actions():
    with pytest.raises(ValueError):
        LlmClient._normalize_response({"summary": "missing"})
