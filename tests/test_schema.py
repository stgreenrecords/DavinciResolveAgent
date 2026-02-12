from jsonschema import validate

from llm.client import ACTION_SCHEMA


def test_action_schema_valid():
    sample = {
        "summary": "test",
        "actions": [
            {"type": "drag", "target": "primaries_gamma_wheel", "dx": 1, "dy": -1, "reason": ""},
            {
                "type": "set_slider",
                "target": "saturation_slider",
                "value": 60.0,
                "reason": "absolute value when double click",
            },
        ],
        "stop": False,
        "confidence": 0.5,
    }
    validate(instance=sample, schema=ACTION_SCHEMA)
