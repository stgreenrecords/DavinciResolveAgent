import pytest
from unittest.mock import MagicMock
from pathlib import Path

from llm.client import LlmClient, LlmRequestContext
from vision.metrics import SimilarityMetrics


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


def test_build_payload_reasoning():
    store = MagicMock()
    client = LlmClient(store)

    ctx = MagicMock(spec=LlmRequestContext)
    ctx.calibration = MagicMock()
    ctx.calibration.targets = {}
    ctx.calibration.control_metadata = {}
    ctx.reference_image_path = Path("ref.png")
    ctx.metrics = SimilarityMetrics(ssim=0.5, histogram=0.5, delta_e=0.5, overall=0.5)
    ctx.current_image = MagicMock()
    ctx.instructions = "test"
    ctx.current_state = {}

    # Mocking internal methods that use external dependencies
    client._encode_reference = MagicMock(return_value="ref_b64")
    client._encode_pil = MagicMock(return_value="cur_b64")

    # Test o1
    payload_o1 = client._build_payload(ctx, "o1-mini")
    assert payload_o1["temperature"] == 1.0
    assert payload_o1["messages"][0]["role"] == "developer"

    # Test gpt-5
    payload_gpt5 = client._build_payload(ctx, "gpt-5")
    assert payload_gpt5["temperature"] == 1.0
    assert payload_gpt5["messages"][0]["role"] == "developer"


def test_build_payload_gpt4():
    store = MagicMock()
    client = LlmClient(store)

    ctx = MagicMock(spec=LlmRequestContext)
    ctx.calibration = MagicMock()
    ctx.calibration.targets = {}
    ctx.calibration.control_metadata = {}
    ctx.reference_image_path = Path("ref.png")
    ctx.metrics = SimilarityMetrics(ssim=0.5, histogram=0.5, delta_e=0.5, overall=0.5)
    ctx.current_image = MagicMock()
    ctx.instructions = "test"
    ctx.current_state = {}

    client._encode_reference = MagicMock(return_value="ref_b64")
    client._encode_pil = MagicMock(return_value="cur_b64")

    payload = client._build_payload(ctx, "gpt-4o")

    assert payload["temperature"] == 0.2
    assert payload["messages"][0]["role"] == "system"


def test_test_connection_reasoning():
    store = MagicMock()
    # Mock settings
    settings = MagicMock()
    settings.api_key = "key"
    settings.model = "gpt-5"
    settings.endpoint = "https://api.openai.com/v1/chat/completions"
    store.load_settings.return_value = settings

    client = LlmClient(store)
    client._session = MagicMock()

    client.test_connection()

    args, kwargs = client._session.post.call_args
    payload = kwargs["json"]

    assert payload["model"] == "gpt-5"
    assert "temperature" not in payload
    assert payload["messages"][0]["role"] == "developer"


def test_test_connection_rate_limit():
    import requests
    store = MagicMock()
    settings = MagicMock()
    settings.api_key = "key"
    settings.model = "gpt-4o"
    settings.endpoint = "https://api.openai.com/v1/chat/completions"
    store.load_settings.return_value = settings

    client = LlmClient(store)
    client._session = MagicMock()

    # Mock a 429 error
    response = MagicMock()
    response.status_code = 429
    # requests.HTTPError needs a response
    exc = requests.exceptions.HTTPError("Rate Limit", response=response)
    client._session.post.side_effect = exc

    with pytest.raises(ValueError) as excinfo:
        client.test_connection()
    assert "Rate limit exceeded (HTTP 429)" in str(excinfo.value)


def test_request_actions_rate_limit():
    import requests
    store = MagicMock()
    client = LlmClient(store)
    client._session = MagicMock()

    ctx = MagicMock(spec=LlmRequestContext)
    ctx.calibration = MagicMock()
    ctx.calibration.targets = {}
    ctx.calibration.control_metadata = {}
    ctx.reference_image_path = Path("ref.png")
    ctx.metrics = SimilarityMetrics(ssim=0.5, histogram=0.5, delta_e=0.5, overall=0.5)
    ctx.current_image = MagicMock()
    ctx.instructions = "test"
    ctx.current_state = {}

    client._encode_reference = MagicMock(return_value="ref_b64")
    client._encode_pil = MagicMock(return_value="cur_b64")

    # Mock a 429 error for all retries
    response = MagicMock()
    response.status_code = 429
    exc = requests.exceptions.HTTPError("Rate Limit", response=response)
    client._session.post.side_effect = exc

    with pytest.raises(ValueError) as excinfo:
        client.request_actions(ctx)
    assert "Rate limit exceeded (HTTP 429)" in str(excinfo.value)


def test_test_connection_retry_error_429():
    import requests
    store = MagicMock()
    settings = MagicMock()
    settings.api_key = "key"
    settings.model = "gpt-4o"
    settings.endpoint = "https://api.openai.com/v1/chat/completions"
    store.load_settings.return_value = settings

    client = LlmClient(store)
    client._session = MagicMock()

    # Mock a RetryError caused by 429
    exc = requests.exceptions.RequestException("Max retries exceeded... too many 429 error responses")
    client._session.post.side_effect = exc

    with pytest.raises(ValueError) as excinfo:
        client.test_connection()
    assert "Rate limit exceeded (HTTP 429)" in str(excinfo.value)
