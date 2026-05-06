from __future__ import annotations

import json
from datetime import date, datetime
from typing import Dict, List, Optional

from ...extensions import db


class MindSpiderStorage:
    """Mongo-backed storage adapted from MindSpider DB layer."""

    NEWS_COLLECTION = "mindspider_daily_news"
    TOPICS_COLLECTION = "mindspider_daily_topics"
    DEEP_SENTIMENT_COLLECTION = "mindspider_deep_sentiment"

    @staticmethod
    def _news_collection():
        collection = getattr(db, MindSpiderStorage.NEWS_COLLECTION)
        try:
            collection.create_index([("crawl_date", 1), ("source", 1), ("rank", 1)])
            collection.create_index("news_id", unique=True)
        except Exception:
            pass
        return collection

    @staticmethod
    def _topics_collection():
        collection = getattr(db, MindSpiderStorage.TOPICS_COLLECTION)
        try:
            collection.create_index("extract_date", unique=True)
            collection.create_index("created_at")
        except Exception:
            pass
        return collection

    @staticmethod
    def save_daily_news(news_data: List[Dict], crawl_date: Optional[date] = None) -> int:
        crawl_date = crawl_date or date.today()
        collection = MindSpiderStorage._news_collection()
        collection.delete_many({"crawl_date": crawl_date.isoformat()})
        payloads = []
        for item in news_data:
            payloads.append(
                {
                    "news_id": str(item.get("id") or ""),
                    "source": str(item.get("source") or ""),
                    "source_name": str(item.get("source_name") or item.get("source") or ""),
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "rank": int(item.get("rank") or 0),
                    "crawl_date": crawl_date.isoformat(),
                    "created_at": datetime.utcnow(),
                }
            )
        if payloads:
            collection.insert_many(payloads)
        return len(payloads)

    @staticmethod
    def get_daily_news(crawl_date: Optional[date] = None) -> List[Dict]:
        crawl_date = crawl_date or date.today()
        cursor = MindSpiderStorage._news_collection().find({"crawl_date": crawl_date.isoformat()}, {"_id": 0}).sort("rank", 1)
        return list(cursor)

    @staticmethod
    def save_daily_topics(keywords: List[str], summary: str, extract_date: Optional[date] = None) -> bool:
        extract_date = extract_date or date.today()
        MindSpiderStorage._topics_collection().replace_one(
            {"extract_date": extract_date.isoformat()},
            {
                "extract_date": extract_date.isoformat(),
                "keywords": list(keywords or []),
                "keywords_json": json.dumps(list(keywords or []), ensure_ascii=False),
                "summary": str(summary or "").strip(),
                "updated_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            },
            upsert=True,
        )
        return True

    @staticmethod
    def get_daily_topics(extract_date: Optional[date] = None) -> Optional[Dict]:
        extract_date = extract_date or date.today()
        result = MindSpiderStorage._topics_collection().find_one({"extract_date": extract_date.isoformat()}, {"_id": 0})
        return result

    @staticmethod
    def get_recent_topics(days: int = 7) -> List[Dict]:
        cursor = MindSpiderStorage._topics_collection().find({}, {"_id": 0}).sort("extract_date", -1).limit(max(days, 1))
        return list(cursor)

    @staticmethod
    def _deep_sentiment_collection():
        collection = getattr(db, MindSpiderStorage.DEEP_SENTIMENT_COLLECTION)
        try:
            collection.create_index("extract_date", unique=True)
            collection.create_index("updated_at")
        except Exception:
            pass
        return collection

    @staticmethod
    def save_deep_sentiment_report(report: Dict, extract_date: Optional[date] = None) -> bool:
        extract_date = extract_date or date.today()
        MindSpiderStorage._deep_sentiment_collection().replace_one(
            {"extract_date": extract_date.isoformat()},
            {
                **dict(report or {}),
                "extract_date": extract_date.isoformat(),
                "updated_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            },
            upsert=True,
        )
        return True

    @staticmethod
    def get_deep_sentiment_report(extract_date: Optional[date] = None) -> Optional[Dict]:
        extract_date = extract_date or date.today()
        return MindSpiderStorage._deep_sentiment_collection().find_one(
            {"extract_date": extract_date.isoformat()},
            {"_id": 0},
        )
