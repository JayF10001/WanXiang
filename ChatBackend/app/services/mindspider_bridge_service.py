from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from flask import current_app
try:
    from ChatBackend.celery_app import celery
except ImportError:
    from celery_app import celery

from ..integrations.mindspider.collector import MindSpiderNewsCollector
from ..integrations.mindspider.extractor import MindSpiderTopicExtractor
from ..integrations.mindspider.storage import MindSpiderStorage


class MindSpiderBridgeService:
    """Minimal bridge that vendors BroadTopicExtraction into WanXiang."""

    @staticmethod
    def run_topic_extraction_sync(sources: Optional[List[str]] = None, max_keywords: int = 100) -> Dict:
        collected = MindSpiderNewsCollector.collect_news(sources)
        news_list = collected.get("news_list") or []
        if not news_list:
            return {
                "success": False,
                "message": "未收集到可用热点新闻",
                "data": {
                    "newsCount": 0,
                    "keywords": [],
                    "summary": "",
                },
            }

        saved_news_count = MindSpiderStorage.save_daily_news(news_list, date.today())
        keywords, summary = MindSpiderTopicExtractor.extract_keywords_and_summary(news_list, max_keywords=max_keywords)
        MindSpiderStorage.save_daily_topics(keywords, summary, date.today())

        current_app.logger.info(
            "MindSpider bridge topic extraction finished: news=%s, keywords=%s",
            saved_news_count,
            len(keywords),
        )

        return {
            "success": True,
            "message": "MindSpider 话题提取完成",
            "data": {
                "extractDate": date.today().isoformat(),
                "newsCount": saved_news_count,
                "successfulSources": collected.get("successful_sources", 0),
                "totalSources": collected.get("total_sources", 0),
                "keywords": keywords,
                "summary": summary,
            },
        }

    @staticmethod
    def run_topic_extraction(sources: Optional[List[str]] = None, max_keywords: int = 100):
        return MindSpiderBridgeService.run_topic_extraction_task.delay(sources or [], max_keywords)

    @staticmethod
    def get_topic_analysis(extract_date: Optional[str] = None) -> Dict:
        target_date = date.fromisoformat(extract_date) if extract_date else date.today()
        topic = MindSpiderStorage.get_daily_topics(target_date)
        news = MindSpiderStorage.get_daily_news(target_date)
        if not topic:
            return {
                "success": False,
                "message": "未找到对应日期的话题分析",
                "data": {
                    "extractDate": target_date.isoformat(),
                    "keywords": [],
                    "summary": "",
                    "newsCount": len(news),
                    "news": news,
                },
            }
        return {
            "success": True,
            "message": "获取 MindSpider 话题分析成功",
            "data": {
                "extractDate": target_date.isoformat(),
                "keywords": topic.get("keywords") or [],
                "summary": str(topic.get("summary") or ""),
                "newsCount": len(news),
                "news": news,
            },
        }

    @staticmethod
    @celery.task(name="mindspider.run_topic_extraction")
    def run_topic_extraction_task(sources: Optional[List[str]] = None, max_keywords: int = 100) -> Dict:
        return MindSpiderBridgeService.run_topic_extraction_sync(sources=sources, max_keywords=max_keywords)
