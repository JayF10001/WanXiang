from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Dict, List, Optional

try:
    from ChatBackend.celery_app import celery
except ImportError:
    from celery_app import celery
from flask import current_app

from ..integrations.mindspider.storage import MindSpiderStorage
from .crawler_service import CrawlerService


NEGATIVE_HINTS = (
    "塌房", "事故", "起火", "火灾", "爆炸", "身亡", "死亡", "受伤", "遇难", "坠毁", "相撞",
    "举报", "争议", "冲突", "危机", "投诉", "质疑", "处罚", "调查", "通报", "造假", "违法",
    "危险", "警告", "紧急", "失联", "失踪", "欠薪", "烂尾", "涉案", "被抓", "裁员", "风险",
    "中毒", "病亡", "制裁", "攻击",
)
POSITIVE_HINTS = (
    "获奖", "突破", "成功", "救援", "暖心", "正能量", "上涨", "增长", "发布", "落地", "创新",
    "改善", "恢复", "回暖", "签约", "合作", "幸福", "加码", "投产", "开通", "启用", "竣工",
    "交付", "通车", "开业", "首发", "夺冠", "晋级", "刷新", "提升", "上线", "支持", "利好", "上调",
)
SUPPORTED_PLATFORMS = ("weibo", "zhihu", "douyin", "bilibili", "tieba", "kuaishou", "toutiao")
PLATFORM_LABELS = {
    "weibo": "微博",
    "zhihu": "知乎",
    "douyin": "抖音",
    "bilibili": "哔哩哔哩",
    "tieba": "百度贴吧",
    "kuaishou": "快手",
    "toutiao": "今日头条",
}
PLATFORM_HINTS = {
    "weibo": "weibo",
    "zhihu": "zhihu",
    "douyin": "douyin",
    "bilibili": "bilibili",
    "tieba": "tieba",
    "kuaishou": "kuaishou",
    "toutiao": "toutiao",
}


def _infer_sentiment(*texts: str) -> str:
    combined = " ".join(str(text or "") for text in texts)
    negative_score = sum(1 for keyword in NEGATIVE_HINTS if keyword in combined)
    positive_score = sum(1 for keyword in POSITIVE_HINTS if keyword in combined)
    if negative_score >= positive_score + 0.5 and negative_score >= 1:
        return "negative"
    if positive_score >= negative_score + 0.5 and positive_score >= 1:
        return "positive"
    return "neutral"


class MindSpiderDeepSentimentService:
    """WanXiang-native minimal DeepSentimentCrawling implementation."""

    @staticmethod
    def run_deep_sentiment_sync(
        *,
        extract_date: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        max_keywords_per_platform: int = 20,
        max_candidates_per_keyword: int = 3,
    ) -> Dict:
        target_date = date.fromisoformat(extract_date) if extract_date else date.today()
        topic = MindSpiderStorage.get_daily_topics(target_date)
        if not topic:
            return {
                "success": False,
                "message": "未找到对应日期的话题关键词，请先运行 MindSpider 话题提取",
                "data": {
                    "extractDate": target_date.isoformat(),
                    "records": [],
                    "platformStats": [],
                    "sentimentDistribution": [],
                    "totalKeywords": 0,
                    "totalRecords": 0,
                },
            }

        keywords = [str(item).strip() for item in (topic.get("keywords") or []) if str(item).strip()]
        if not keywords:
            return {
                "success": False,
                "message": "未找到可用关键词",
                "data": {
                    "extractDate": target_date.isoformat(),
                    "records": [],
                    "platformStats": [],
                    "sentimentDistribution": [],
                    "totalKeywords": 0,
                    "totalRecords": 0,
                },
            }

        selected_platforms = [
            platform for platform in (platforms or list(SUPPORTED_PLATFORMS))
            if platform in SUPPORTED_PLATFORMS
        ] or list(SUPPORTED_PLATFORMS)
        selected_keywords = keywords[: max(1, min(max_keywords_per_platform, len(keywords)))]

        records: List[Dict] = []
        platform_counter: Counter[str] = Counter()
        sentiment_counter: Counter[str] = Counter()

        for platform in selected_platforms:
            platform_label = PLATFORM_LABELS.get(platform, platform)
            platform_hint = PLATFORM_HINTS.get(platform, platform)
            for keyword in selected_keywords:
                result = CrawlerService.crawl_news_context(
                    query_title=keyword,
                    source_url="",
                    platform_hint=platform_hint,
                    max_candidates=max_candidates_per_keyword,
                    force_refresh=False,
                )
                sentiment = _infer_sentiment(
                    keyword,
                    result.get("summary") or "",
                    result.get("content_excerpt") or "",
                )
                record = {
                    "platform": platform,
                    "platformLabel": platform_label,
                    "keyword": keyword,
                    "status": "ready" if result.get("success") else "failed",
                    "sentiment": sentiment,
                    "summary": str(result.get("summary") or ""),
                    "contentExcerpt": str(result.get("content_excerpt") or ""),
                    "sourceName": str(result.get("source_name") or ""),
                    "finalUrl": str(result.get("final_url") or ""),
                    "publishedAt": result.get("published_at"),
                    "candidateUrls": [str(item) for item in (result.get("candidate_urls") or [])],
                    "cached": bool(result.get("cached")),
                    "message": str(result.get("message") or ""),
                }
                records.append(record)
                platform_counter[platform_label] += 1
                sentiment_counter[sentiment] += 1

        report = {
            "extractDate": target_date.isoformat(),
            "sourceSummary": str(topic.get("summary") or ""),
            "totalKeywords": len(selected_keywords),
            "totalPlatforms": len(selected_platforms),
            "totalRecords": len(records),
            "platformStats": [
                {"name": name, "value": value}
                for name, value in platform_counter.most_common()
            ],
            "sentimentDistribution": [
                {"name": "正向", "value": sentiment_counter.get("positive", 0)},
                {"name": "中性", "value": sentiment_counter.get("neutral", 0)},
                {"name": "负向", "value": sentiment_counter.get("negative", 0)},
            ],
            "records": records,
        }
        MindSpiderStorage.save_deep_sentiment_report(report, target_date)

        current_app.logger.info(
            "MindSpider deep sentiment finished: date=%s keywords=%s platforms=%s records=%s",
            target_date.isoformat(),
            len(selected_keywords),
            len(selected_platforms),
            len(records),
        )

        return {
            "success": True,
            "message": "MindSpider 深度情感抓取完成",
            "data": report,
        }

    @staticmethod
    def run_deep_sentiment(
        *,
        extract_date: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        max_keywords_per_platform: int = 20,
        max_candidates_per_keyword: int = 3,
    ):
        return MindSpiderDeepSentimentService.run_deep_sentiment_task.delay(
            extract_date,
            platforms or [],
            max_keywords_per_platform,
            max_candidates_per_keyword,
        )

    @staticmethod
    def get_deep_sentiment_analysis(extract_date: Optional[str] = None) -> Dict:
        target_date = date.fromisoformat(extract_date) if extract_date else date.today()
        report = MindSpiderStorage.get_deep_sentiment_report(target_date)
        if not report:
            return {
                "success": False,
                "message": "未找到对应日期的深度情感抓取结果",
                "data": {
                    "extractDate": target_date.isoformat(),
                    "records": [],
                    "platformStats": [],
                    "sentimentDistribution": [],
                    "totalKeywords": 0,
                    "totalPlatforms": 0,
                    "totalRecords": 0,
                    "sourceSummary": "",
                },
            }
        return {
            "success": True,
            "message": "获取 MindSpider 深度情感结果成功",
            "data": report,
        }

    @staticmethod
    @celery.task(name="mindspider.run_deep_sentiment")
    def run_deep_sentiment_task(
        extract_date: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        max_keywords_per_platform: int = 20,
        max_candidates_per_keyword: int = 3,
    ) -> Dict:
        return MindSpiderDeepSentimentService.run_deep_sentiment_sync(
            extract_date=extract_date,
            platforms=platforms,
            max_keywords_per_platform=max_keywords_per_platform,
            max_candidates_per_keyword=max_candidates_per_keyword,
        )
