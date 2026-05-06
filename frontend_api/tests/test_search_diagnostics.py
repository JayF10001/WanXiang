from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from frontend_api.main import app


class SearchDiagnosticsRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_search_diagnostics_requires_login(self):
        response = self.client.post(
            "/api/assistant/debug/search-diagnostics",
            json={"query": "京东 外卖"},
        )
        self.assertEqual(response.status_code, 401)

    @patch("frontend_api.routers.assistant._require_backend_cookies", return_value={"session": "cookie"})
    @patch("frontend_api.routers.assistant._resolve_backend_user_id", return_value="user-1")
    @patch("frontend_api.routers.assistant._run_search_diagnostics")
    def test_search_diagnostics_returns_expected_payload(
        self,
        mock_run_search_diagnostics,
        _mock_resolve_user_id,
        _mock_require_backend_cookies,
    ):
        mock_run_search_diagnostics.return_value = {
            "query": "京东 外卖",
            "items": [{"title": "示例结果", "url": "https://example.com"}],
            "summary": "已检索到结果",
            "providerDiagnostics": [
                {
                    "provider": "tavily",
                    "status": "failed",
                    "errorType": "proxy_error",
                    "errorMessage": "proxy failed",
                    "durationMs": 123,
                    "resultCount": 0,
                    "timedOut": False,
                }
            ],
            "selectedProviders": ["crawler", "duckduckgo", "tavily"],
            "totalDurationMs": 456,
            "partialFailure": True,
            "debugVersion": "search-diagnostics-v1",
        }

        response = self.client.post(
            "/api/assistant/debug/search-diagnostics",
            json={"query": "京东 外卖", "includeLoadedPages": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["normalizedQuery"], "京东 外卖")
        self.assertTrue(payload["partialFailure"])
        self.assertEqual(payload["debugVersion"], "search-diagnostics-v1")
        self.assertIn("providerDiagnostics", payload)
        self.assertNotIn("loadedPages", payload)

    @patch("frontend_api.routers.assistant._require_backend_cookies", return_value={"session": "cookie"})
    @patch("frontend_api.routers.assistant._resolve_backend_user_id", return_value="user-1")
    @patch("frontend_api.routers.assistant._run_search_diagnostics")
    def test_search_diagnostics_can_include_loaded_pages(
        self,
        mock_run_search_diagnostics,
        _mock_resolve_user_id,
        _mock_require_backend_cookies,
    ):
        mock_run_search_diagnostics.return_value = {
            "query": "京东 外卖",
            "items": [],
            "summary": "无结果",
            "providerDiagnostics": [],
            "selectedProviders": ["tavily"],
            "totalDurationMs": 100,
            "partialFailure": False,
            "debugVersion": "search-diagnostics-v1",
            "loadedPages": [
                {
                    "provider": "tavily",
                    "url": "https://example.com",
                    "title": "Example",
                    "contentPreview": "preview",
                    "errorType": "",
                    "errorMessage": "",
                }
            ],
        }

        response = self.client.post(
            "/api/assistant/debug/search-diagnostics",
            json={"query": "京东 外卖", "includeLoadedPages": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertIn("loadedPages", payload)
        self.assertEqual(payload["loadedPages"][0]["provider"], "tavily")


if __name__ == "__main__":
    unittest.main()
