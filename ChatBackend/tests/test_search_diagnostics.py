from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ChatBackend.app.services.langchain_tool_service import LangChainToolService
from ChatBackend.app.services.overview_search_service import OverviewSearchService


class LangChainToolServiceDiagnosticsTests(unittest.TestCase):
    def test_tavily_missing_key_returns_skipped_diagnostic(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            diagnostic = LangChainToolService.search_web_tavily_diagnostic("京东 外卖")

        self.assertEqual(diagnostic["provider"], "tavily")
        self.assertEqual(diagnostic["status"], "skipped")
        self.assertEqual(diagnostic["errorType"], "configuration_missing")
        self.assertEqual(diagnostic["resultCount"], 0)

    def test_tavily_error_payload_is_reported_as_failure(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            with patch.object(
                LangChainToolService,
                "_invoke_tavily_search",
                return_value={"error": "ProxyError: unable to connect to proxy"},
            ):
                diagnostic = LangChainToolService.search_web_tavily_diagnostic("京东 外卖")

        self.assertEqual(diagnostic["provider"], "tavily")
        self.assertEqual(diagnostic["status"], "failed")
        self.assertEqual(diagnostic["errorType"], "proxy_error")
        self.assertEqual(diagnostic["resultCount"], 0)

    def test_ddg_connection_error_is_reported(self):
        with patch.object(
            LangChainToolService,
            "_invoke_ddg_search",
            side_effect=RuntimeError("ConnectError: failed to establish a new connection"),
        ):
            diagnostic = LangChainToolService.search_web_diagnostic("京东 外卖")

        self.assertEqual(diagnostic["provider"], "duckduckgo")
        self.assertEqual(diagnostic["status"], "failed")
        self.assertEqual(diagnostic["errorType"], "connect_error")
        self.assertEqual(diagnostic["resultCount"], 0)

    def test_ddg_can_retry_with_proxy_env_after_direct_connect_error(self):
        call_trust_env_values = []

        def _fake_search(_query, _max_results, trust_env=None):
            call_trust_env_values.append(trust_env)
            if trust_env:
                return [{"title": "result", "url": "https://example.com", "snippet": "ok"}]
            raise RuntimeError("ConnectError: failed to establish a new connection")

        with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:7890"}, clear=False):
            with patch.object(LangChainToolService, "_invoke_ddg_search", side_effect=_fake_search):
                diagnostic = LangChainToolService.search_web_diagnostic("京东 外卖")

        self.assertEqual(diagnostic["status"], "success")
        self.assertTrue(diagnostic["fallbackAttempted"])
        self.assertEqual(diagnostic["fallbackMode"], "trust_env")
        self.assertEqual(call_trust_env_values, [None, True])

    def test_overview_query_is_normalized_for_hotspot_prompt(self):
        normalized = OverviewSearchService._normalize_search_query("帮我分析这个热点：金像奖爆冷")
        self.assertEqual(normalized, "金像奖爆冷")


if __name__ == "__main__":
    unittest.main()
