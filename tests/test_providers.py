import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import providers


class ProviderTests(unittest.TestCase):
    def test_gemini_request_converts_chat_history_and_system_prompt(self):
        messages = [
            {"role": "system", "content": "Use grounded context."},
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Prior answer"},
        ]
        response = {
            "candidates": [
                {"content": {"parts": [{"text": "Gemini answer"}]}}
            ]
        }
        with (
            patch("config.GEMINI_API_KEY", "test-key"),
            patch("providers._request_json", return_value=response) as request_json,
        ):
            answer = providers.generate("gemini", "gemini-test", messages)

        self.assertEqual(answer, "Gemini answer")
        url, payload, headers = request_json.call_args.args[:3]
        self.assertIn("gemini-test:generateContent", url)
        self.assertEqual(headers["x-goog-api-key"], "test-key")
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "Use grounded context.")
        self.assertEqual(
            [item["role"] for item in payload["contents"]],
            ["user", "model"],
        )

    def test_openai_request_uses_configured_chat_completions_api(self):
        response = {
            "choices": [{"message": {"content": "GPT answer"}}]
        }
        with (
            patch("config.OPENAI_API_KEY", "test-key"),
            patch("providers._request_json", return_value=response) as request_json,
        ):
            answer = providers.generate(
                "openai",
                "gpt-test",
                [{"role": "user", "content": "Question"}],
            )

        self.assertEqual(answer, "GPT answer")
        url, payload, headers = request_json.call_args.args[:3]
        self.assertEqual(url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(headers["Authorization"], "Bearer test-key")

    def test_transient_http_error_retries_then_returns_json(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"ok": True}
        ).encode()
        response.__enter__.return_value.__exit__.return_value = None
        rate_limit = HTTPError(
            "https://example.test",
            429,
            "Rate limited",
            {},
            io.BytesIO(b""),
        )
        with (
            patch("providers.urlopen", side_effect=[rate_limit, response]) as urlopen,
            patch("providers.time.sleep"),
        ):
            result = providers._request_json(
                "https://example.test", {"prompt": "test"}, {}
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(providers.ProviderError):
            providers.generate("unsupported", "model", [])
