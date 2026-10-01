"""Covers _call_ai's OpenRouter response handling in both app/services/chat.py and
app/services/ai_assistant.py (duplicated by design — see their module docstrings).
No network and no database: httpx.post is mocked, and settings.openrouter_api_key
is set to a dummy value for the duration of each test so this never depends on
backend/.env actually having a real key configured.

Reproduces, with a mocked response, exactly what a live probe against OpenRouter's
free nvidia/nemotron model returned: on the 3rd of 3 real attempts, an HTTP 200
whose body was {"error": {...}} instead of {"choices": [...]} — the free-tier
upstream provider was temporarily overloaded. Before this fix, that raised a bare
KeyError on "choices", surfacing as "AI provider returned an unexpected response
format." — the exact bug this covers.
"""
from unittest.mock import patch

import pytest

from app.services import ai_assistant, chat


class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _dummy_api_key(monkeypatch):
    monkeypatch.setattr(chat.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(ai_assistant.settings, "openrouter_api_key", "test-key")


@pytest.mark.parametrize("module,error_cls", [(chat, chat.ChatError), (ai_assistant, ai_assistant.AIAssistantError)])
class TestCallAi:
    def test_error_wrapped_in_http_200_is_reported_clearly(self, module, error_cls):
        # The exact shape observed live: OpenRouter's free-tier provider was
        # overloaded and reported it as an "error" object in an HTTP 200 body.
        body = {
            "id": "gen-123",
            "error": {
                "message": "Upstream error from Nvidia: Service temporarily overloaded",
                "code": 503,
                "metadata": {"error_type": "provider_overloaded"},
            },
        }
        with patch.object(module.httpx, "post", return_value=FakeResponse(200, body)):
            with pytest.raises(error_cls, match="Service temporarily overloaded"):
                module._call_ai([{"role": "user", "content": "hi"}]) if module is chat else module._call_ai("hi")

    def test_plain_string_content_still_works(self, module, error_cls):
        body = {"choices": [{"message": {"role": "assistant", "content": "Hello there"}}]}
        with patch.object(module.httpx, "post", return_value=FakeResponse(200, body)):
            result = module._call_ai([{"role": "user", "content": "hi"}]) if module is chat else module._call_ai("hi")
        assert result == "Hello there"

    def test_list_of_content_parts_is_supported(self, module, error_cls):
        # Some providers OpenRouter proxies return multi-part content instead of
        # a plain string.
        body = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Hello "},
                            {"type": "text", "text": "there"},
                        ],
                    }
                }
            ]
        }
        with patch.object(module.httpx, "post", return_value=FakeResponse(200, body)):
            result = module._call_ai([{"role": "user", "content": "hi"}]) if module is chat else module._call_ai("hi")
        assert result == "Hello there"

    def test_missing_choices_with_no_error_key_still_reports_format_error(self, module, error_cls):
        # Genuinely malformed response, no "error" key either — must still fail
        # clearly rather than raising a raw KeyError.
        with patch.object(module.httpx, "post", return_value=FakeResponse(200, {"unexpected": "shape"})):
            with pytest.raises(error_cls, match="unexpected response format"):
                module._call_ai([{"role": "user", "content": "hi"}]) if module is chat else module._call_ai("hi")
