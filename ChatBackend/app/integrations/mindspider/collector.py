from __future__ import annotations

import requests
from datetime import datetime
from typing import Dict, List, Optional


BASE_URL = "https://newsnow.busiyi.world"

SOURCE_NAMES = {
    "weibo": "微博热搜",
    "zhihu": "知乎热榜",
    "bilibili-hot-search": "B站热搜",
    "toutiao": "今日头条",
    "douyin": "抖音热榜",
    "github-trending-today": "GitHub趋势",
    "coolapk": "酷安热榜",
    "tieba": "百度贴吧",
    "wallstreetcn": "华尔街见闻",
    "thepaper": "澎湃新闻",
    "cls-hot": "财联社",
    "xueqiu": "雪球热榜",
    "kuaishou": "快手热榜",
}


class MindSpiderNewsCollector:
    """Vendored minimal news collector from MindSpider BroadTopicExtraction."""

    supported_sources = list(SOURCE_NAMES.keys())

    @staticmethod
    def fetch_news(source: str) -> Dict:
        url = f"{BASE_URL}/api/s?id={source}&latest"
        try:
            response = requests.get(
                url,
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            return {
                "source": source,
                "status": "success",
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            return {
                "source": source,
                "status": "error",
                "error": str(exc),
                "timestamp": datetime.utcnow().isoformat(),
            }

    @classmethod
    def get_popular_news(cls, sources: Optional[List[str]] = None) -> List[Dict]:
        selected_sources = sources or cls.supported_sources
        return [cls.fetch_news(source) for source in selected_sources]

    @classmethod
    def collect_news(cls, sources: Optional[List[str]] = None) -> Dict:
        results = cls.get_popular_news(sources)
        news_list: List[Dict] = []
        successful_sources = 0
        total_news = 0

        for result in results:
            if result.get("status") != "success":
                continue
            successful_sources += 1
            payload = result.get("data") or {}
            items = payload.get("items") if isinstance(payload.get("items"), list) else []
            for rank, item in enumerate(items, start=1):
                processed = cls._process_news_item(item, result.get("source") or "unknown", rank)
                if processed is None:
                    continue
                news_list.append(processed)
                total_news += 1

        return {
            "success": True,
            "news_list": news_list,
            "successful_sources": successful_sources,
            "total_sources": len(results),
            "total_news": total_news,
            "collection_time": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _process_news_item(item: Dict, source: str, rank: int) -> Optional[Dict]:
        try:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                if not title:
                    return None
                return {
                    "id": f"{source}_{item.get('id', f'rank_{rank}')}",
                    "title": title,
                    "url": str(item.get("url") or "").strip(),
                    "source": source,
                    "source_name": SOURCE_NAMES.get(source, source),
                    "rank": rank,
                }
            title = str(item or "").strip()
            if not title:
                return None
            return {
                "id": f"{source}_rank_{rank}",
                "title": title,
                "url": "",
                "source": source,
                "source_name": SOURCE_NAMES.get(source, source),
                "rank": rank,
            }
        except Exception:
            return None

