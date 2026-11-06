import unittest
from unittest.mock import patch

import app as chat_app
from services.llm_service import GeminiServiceError


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        chat_app.app.config.update(TESTING=True, MAX_CONTENT_LENGTH=1_000_000)
        self.client = chat_app.app.test_client()
        with chat_app._rate_limit_lock:
            chat_app._rate_limit_requests.clear()

    def post_messages(self, messages):
        return self.client.post("/api/chat", json={"messages": messages})

    def test_validates_and_forwards_conversation_history(self):
        messages = [
            {"role": "user", "content": "  My favorite color is violet.  "},
            {"role": "assistant", "content": "I will remember violet."},
            {"role": "user", "content": "What color did I say?"},
        ]
        with patch("app.generate_response", return_value="Violet.") as generate:
            response = self.post_messages(messages)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"response": "Violet."})
        generate.assert_called_once_with(
            [
                {"role": "user", "content": "My favorite color is violet."},
                {"role": "assistant", "content": "I will remember violet."},
                {"role": "user", "content": "What color did I say?"},
            ]
        )

    def test_rejects_invalid_payloads(self):
        invalid_payloads = [
            [],
            [{"role": "assistant", "content": "Hello"}],
            [
                {"role": "user", "content": "Hello"},
                {"role": "user", "content": "Again"},
            ],
            [{"role": "user", "content": " "}],
            [{"role": "user", "content": "x" * (chat_app.MAX_USER_MESSAGE_CHARS + 1)}],
            [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "x" * (chat_app.MAX_ASSISTANT_MESSAGE_CHARS + 1),
                },
                {"role": "user", "content": "Again"},
            ],
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ],
            [
                {
                    "role": "user" if index % 2 == 0 else "assistant",
                    "content": "Hello",
                }
                for index in range(chat_app.MAX_HISTORY_MESSAGES + 1)
            ],
        ]
        for messages in invalid_payloads:
            with self.subTest(messages=len(messages)):
                response = self.post_messages(messages)
                self.assertEqual(response.status_code, 400)

    def test_rejects_non_json_and_malformed_json(self):
        response = self.client.post("/api/chat", data="not json")
        self.assertEqual(response.status_code, 415)

        response = self.client.post(
            "/api/chat",
            data="{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_request_size_limit_returns_json_error(self):
        chat_app.app.config["MAX_CONTENT_LENGTH"] = 32
        response = self.client.post(
            "/api/chat",
            data='{"messages":[{"role":"user","content":"' + ("x" * 100) + '"}]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json(), {"error": "Request body is too large."})

    def test_rate_limit_returns_retry_after_header_and_expires(self):
        messages = [{"role": "user", "content": "Hello"}]
        with patch("app.generate_response", return_value="Hi"):
            with patch("app.monotonic", return_value=100):
                for _ in range(chat_app.CHAT_RATE_LIMIT_REQUESTS):
                    response = self.post_messages(messages)
                    self.assertEqual(response.status_code, 200)

                response = self.post_messages(messages)

            self.assertEqual(response.status_code, 429)
            self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)
            self.assertIn("Too many requests", response.get_json()["error"])

            with patch("app.monotonic", return_value=160):
                response = self.post_messages(messages)

        self.assertEqual(response.status_code, 200)

    def test_gemini_errors_are_returned_without_debug_details(self):
        with patch(
            "app.generate_response",
            side_effect=GeminiServiceError("Gemini is unavailable."),
        ):
            response = self.post_messages([{"role": "user", "content": "Hello"}])

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json(), {"error": "Gemini is unavailable."})

    def test_existing_routes_and_security_headers(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.headers["X-Frame-Options"], "DENY")
        self.assertEqual(home.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", home.headers["Content-Security-Policy"])

        health = self.client.get("/health")
        self.assertEqual(health.get_json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
