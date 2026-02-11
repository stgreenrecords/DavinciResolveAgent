from llm.client import ACTION_SCHEMA
from jsonschema import validate


def test_action_schema_valid():
    sample = {
        "summary": "test",
        "actions": [
            {"type": "drag", "target": "primaries_gamma_wheel", "dx": 1, "dy": -1, "reason": ""}
        ],
        "stop": False,
        "confidence": 0.5,
    }
    validate(instance=sample, schema=ACTION_SCHEMA)
