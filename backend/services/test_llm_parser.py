import os
import unittest
from unittest.mock import Mock, patch

from backend.services.llm_parser import (
    DEFAULT_OPENROUTER_MODEL,
    MISTRAL_API_URL,
    OPENROUTER_API_URL,
    _call_llm,
)


class LLMRequestTests(unittest.TestCase):
    @patch("backend.services.llm_parser.requests.post")
    def test_openrouter_is_preferred_and_uses_configured_model(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}}]
        }
        post.return_value = response

        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "openrouter-test-key",
            "OPENROUTER_MODEL": "test/provider-model",
            "MISTRAL_API_KEY": "mistral-test-key",
        }):
            content = _call_llm([{"role": "user", "content": "test"}])

        self.assertEqual(content, '{"ok": true}')
        self.assertEqual(post.call_args.args[0], OPENROUTER_API_URL)
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer openrouter-test-key",
        )
        self.assertEqual(post.call_args.kwargs["json"]["model"], "test/provider-model")

    @patch("backend.services.llm_parser.requests.post")
    def test_openrouter_uses_default_model(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}}]
        }
        post.return_value = response

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "openrouter-test-key"}, clear=True):
            _call_llm([{"role": "user", "content": "test"}])

        self.assertEqual(post.call_args.args[0], OPENROUTER_API_URL)
        self.assertEqual(
            post.call_args.kwargs["json"]["model"],
            "openrouter/free",
        )
        self.assertEqual(DEFAULT_OPENROUTER_MODEL, "openrouter/free")

    @patch("backend.services.llm_parser.requests.post")
    def test_mistral_remains_available_as_fallback(self, post):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}}]
        }
        post.return_value = response

        with patch.dict(os.environ, {"MISTRAL_API_KEY": "mistral-test-key"}, clear=True):
            _call_llm([{"role": "user", "content": "test"}])

        self.assertEqual(post.call_args.args[0], MISTRAL_API_URL)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "mistral-small-latest")


if __name__ == "__main__":
    unittest.main()
