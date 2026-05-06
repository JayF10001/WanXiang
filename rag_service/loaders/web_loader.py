from __future__ import annotations

from typing import Any, Dict

from ChatBackend.app.services.crawler_service import CrawlerService


class WebLoader:
    @staticmethod
    def load_context(
        *,
        title: str,
        source_url: str = "",
        platform_hint: str = "",
        session_id: str = "",
        user_id: str = "",
        max_candidates: int = 3,
    ) -> Dict[str, Any]:
        return CrawlerService.crawl_news_context(
            title=title,
            source_url=source_url,
            platform_hint=platform_hint,
            session_id=session_id,
            user_id=user_id,
            max_candidates=max_candidates,
        )

