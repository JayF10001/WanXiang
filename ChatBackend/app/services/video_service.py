import os
import json
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import subprocess
import re
import requests
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

import yt_dlp
from pytube import Search, YouTube
import pysrt
from bson import ObjectId
from pymongo import MongoClient

# 获取MongoDB连接
from ..models import db

class VideoService:
    """
    视频服务类，用于根据新闻标题搜索视频，下载音频和字幕，并保存到MongoDB
    """

    THUMBNAIL_CACHE_COLLECTION = "recommendation_thumbnails"
    SUMMARY_CACHE_COLLECTION = "recommendation_summaries"
    TRUSTED_IMAGE_HOST_KEYWORDS = (
        "sinaimg",
        "wbimg",
        "zhimg",
        "douyinpic",
        "douyin",
        "toutiaoimg",
        "byteimg",
        "bdimg",
        "baijiahao",
        "hiphotos",
        "bcebos",
        "alicdn",
        "bilivideo",
        "hdslb",
        "ytimg",
    )
    IMAGE_URL_HINTS = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".bmp",
        ".avif",
        "imageView",
        "x-bce-process=image",
        "format=webp",
    )
    BAD_IMAGE_HINTS = (
        ".svg",
        "logo",
        "icon",
        "avatar",
        "sprite",
        "favicon",
        "brand",
        "result_logo",
        "index_logo",
        "baidu_logo",
    )

    @staticmethod
    def _normalize_title_key(value: str) -> str:
        return "".join(str(value or "").strip().lower().split())

    @staticmethod
    def _normalize_image_url(value: str, base_url: Optional[str] = None) -> str:
        url = str(value or "").strip()
        if not url:
            return ""
        if url.startswith("//"):
            return f"https:{url}"
        if base_url and url.startswith("/"):
            return urljoin(base_url, url)
        return url

    @staticmethod
    def _platform_from_url(url: str) -> str:
        host = (urlparse(str(url or "")).netloc or "").lower()
        if "weibo.com" in host:
            return "weibo"
        if "zhihu.com" in host:
            return "zhihu"
        if "douyin.com" in host or "iesdouyin.com" in host or "douyinpic.com" in host:
            return "douyin"
        if "bilibili.com" in host or "hdslb.com" in host:
            return "bilibili"
        if "toutiao.com" in host or "toutiaoimg.com" in host or "ixigua.com" in host:
            return "toutiao"
        if "baidu.com" in host or "baijiahao.baidu.com" in host:
            return "baidu"
        return ""

    @staticmethod
    def _build_request_headers(url: str) -> Dict[str, str]:
        platform = VideoService._platform_from_url(url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        }
        if platform == "weibo":
            headers["Referer"] = "https://weibo.com/"
        elif platform == "zhihu":
            headers["Referer"] = "https://www.zhihu.com/"
        elif platform == "douyin":
            headers["Referer"] = "https://www.douyin.com/"
        elif platform == "bilibili":
            headers["Referer"] = "https://www.bilibili.com/"
        elif platform == "toutiao":
            headers["Referer"] = "https://www.toutiao.com/"
        elif platform == "baidu":
            headers["Referer"] = "https://www.baidu.com/"
        return headers

    @staticmethod
    def _looks_like_image_url(url: str) -> bool:
        lowered = str(url or "").strip().lower()
        if not lowered:
            return False
        return any(token in lowered for token in VideoService.IMAGE_URL_HINTS)

    @staticmethod
    def _looks_like_bad_image_url(url: str) -> bool:
        lowered = str(url or "").strip().lower()
        if not lowered:
            return True
        return any(token in lowered for token in VideoService.BAD_IMAGE_HINTS)

    @staticmethod
    def _is_trusted_image_host(url: str) -> bool:
        host = (urlparse(str(url or "")).netloc or "").lower()
        if not host:
            return False
        return any(keyword in host for keyword in VideoService.TRUSTED_IMAGE_HOST_KEYWORDS)

    @staticmethod
    def _fetch_url(url: str, *, timeout: int = 8, stream: bool = False) -> Optional[requests.Response]:
        session = requests.Session()
        session.trust_env = False
        try:
            response = session.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                stream=stream,
                headers=VideoService._build_request_headers(url),
            )
            if response.status_code >= 400:
                return None
            return response
        except Exception:
            return None
        finally:
            session.close()

    @staticmethod
    def _is_accessible_image_url(url: str) -> bool:
        normalized = VideoService._normalize_image_url(url)
        if not normalized:
            return False
        if VideoService._looks_like_bad_image_url(normalized):
            return False

        response = VideoService._fetch_url(normalized, timeout=5, stream=True)
        if response is None:
            return VideoService._is_trusted_image_host(normalized) or VideoService._looks_like_image_url(normalized)

        content_type = str(response.headers.get("Content-Type") or "").lower()
        final_url = response.url or normalized
        content_length = str(response.headers.get("Content-Length") or "").strip()
        try:
            response.close()
        except Exception:
            pass

        if content_type.startswith("image/"):
            return True

        if VideoService._is_trusted_image_host(final_url):
            if not content_type:
                return True
            if "octet-stream" in content_type or "binary" in content_type:
                return True
            if "text/plain" in content_type and VideoService._looks_like_image_url(final_url):
                return True

        if content_length.isdigit() and int(content_length) > 2048 and VideoService._looks_like_image_url(final_url):
            return True

        return VideoService._looks_like_image_url(final_url)

    @staticmethod
    def _extract_meta_image_from_html(html: str, page_url: str) -> str:
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]
        for pattern in patterns:
            matched = re.search(pattern, html, re.IGNORECASE)
            if matched and matched.group(1):
                return VideoService._normalize_image_url(matched.group(1), page_url)
        return ""

    @staticmethod
    def _clean_summary_text(value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        text = re.sub(r"\s+", " ", text).strip()
        return text[:220]

    @staticmethod
    def _extract_meta_description_from_html(html: str) -> str:
        patterns = [
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
            r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:description["\']',
        ]
        for pattern in patterns:
            matched = re.search(pattern, html, re.IGNORECASE)
            if matched and matched.group(1):
                cleaned = VideoService._clean_summary_text(matched.group(1))
                if cleaned and len(cleaned) >= 16:
                    return cleaned
        return ""

    @staticmethod
    def _extract_candidate_summary_from_html(html: str) -> str:
        paragraph_patterns = [
            r'<p[^>]*>(.*?)</p>',
            r'<div[^>]+class=["\'][^"\']*(?:summary|desc|content|article)[^"\']*["\'][^>]*>(.*?)</div>',
        ]
        for pattern in paragraph_patterns:
            for matched in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
                cleaned = VideoService._clean_summary_text(matched.group(1))
                if cleaned and len(cleaned) >= 24:
                    return cleaned
        return ""

    @staticmethod
    def _extract_platform_specific_image_from_html(html: str, page_url: str) -> str:
        platform = VideoService._platform_from_url(page_url)
        if not platform:
            return ""

        platform_patterns = {
            "weibo": [
                r'"page_pic"\s*:\s*"([^"]+)"',
                r'"pic"\s*:\s*"([^"]+)"',
                r'"url"\s*:\s*"([^"]+sinaimg\.[^"]+)"',
                r'data-src=["\']([^"\']+sinaimg\.[^"\']+)["\']',
            ],
            "zhihu": [
                r'itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\']',
                r'"image"\s*:\s*"([^"]+)"',
                r'data-original=["\']([^"\']+)["\']',
                r'"thumbnail"\s*:\s*"([^"]+)"',
            ],
            "douyin": [
                r'"dynamic_cover"\s*:\s*"([^"]+)"',
                r'"origin_cover"\s*:\s*"([^"]+)"',
                r'"cover"\s*:\s*"([^"]+douyinpic\.com[^"]+)"',
                r'"url_list"\s*:\s*\[\s*"([^"]+(?:douyinpic|byteimg)[^"]+)"',
            ],
            "bilibili": [
                r'"pic"\s*:\s*"([^"]+hdslb[^"]+)"',
                r'"cover"\s*:\s*"([^"]+hdslb[^"]+)"',
            ],
            "toutiao": [
                r'"share_image"\s*:\s*"([^"]+)"',
                r'"image_url"\s*:\s*"([^"]+)"',
                r'"url"\s*:\s*"([^"]+toutiaoimg\.com[^"]+)"',
                r'"cover_image_url"\s*:\s*"([^"]+)"',
            ],
            "baidu": [
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'"thumbnailUrl"\s*:\s*"([^"]+(?:bdimg|baijiahao|hiphotos)[^"]+)"',
                r'"coverImage"\s*:\s*"([^"]+(?:bdimg|baijiahao|hiphotos)[^"]+)"',
                r'"image"\s*:\s*"([^"]+(?:bdimg|baijiahao|hiphotos)[^"]+)"',
            ],
        }

        for pattern in platform_patterns.get(platform, []):
            matched = re.search(pattern, html, re.IGNORECASE)
            if matched and matched.group(1):
                return VideoService._normalize_image_url(matched.group(1), page_url)
        return ""

    @staticmethod
    def _extract_candidate_images_from_html(html: str, page_url: str) -> List[str]:
        candidates: List[str] = []
        seen = set()
        platform = VideoService._platform_from_url(page_url)

        for matched in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE):
            raw_url = matched.group(1)
            normalized = VideoService._normalize_image_url(raw_url, page_url)
            if not normalized or normalized in seen:
                continue
            if VideoService._looks_like_bad_image_url(normalized):
                continue
            seen.add(normalized)
            candidates.append(normalized)
            if len(candidates) >= 8:
                break

        preferred_host_keywords = {
            "weibo": ("sinaimg", "wbimg"),
            "zhihu": ("zhimg",),
            "douyin": ("douyinpic", "byteimg", "douyin"),
            "bilibili": ("hdslb", "bilivideo"),
            "toutiao": ("toutiaoimg", "byteimg", "toutiao"),
            "baidu": ("bdimg", "baijiahao", "hiphotos"),
        }
        preferred = preferred_host_keywords.get(platform, ())
        if preferred:
            candidates.sort(
                key=lambda candidate: (
                    0 if any(keyword in candidate.lower() for keyword in preferred) else 1,
                    len(candidate),
                )
            )

        return candidates

    @staticmethod
    def _resolve_page_thumbnail(source_url: str) -> str:
        normalized = str(source_url or "").strip()
        if not normalized:
            return ""

        response = VideoService._fetch_url(normalized, timeout=8, stream=False)
        if response is None:
            return ""

        content_type = str(response.headers.get("Content-Type") or "").lower()
        if content_type.startswith("image/"):
            return normalized

        html = response.text or ""
        platform_image = VideoService._extract_platform_specific_image_from_html(html, response.url or normalized)
        if platform_image and VideoService._is_accessible_image_url(platform_image):
            return platform_image

        image_url = VideoService._extract_meta_image_from_html(html, response.url or normalized)
        if image_url and VideoService._is_accessible_image_url(image_url):
            return image_url

        for candidate in VideoService._extract_candidate_images_from_html(html, response.url or normalized):
            if VideoService._is_accessible_image_url(candidate):
                return candidate

        # 平台站点常见会把真实图片 URL 以 JSON 字段形式埋在页面里，补一轮宽松提取。
        loose_patterns = [
            r'https?:\/\/[^"\']+(?:sinaimg|wbimg|zhimg|toutiaoimg|byteimg|bdimg|baidu|baijiahao|hiphotos)[^"\']+',
            r'\/\/[^"\']+(?:sinaimg|wbimg|zhimg|toutiaoimg|byteimg|bdimg|baidu|baijiahao|hiphotos)[^"\']+',
        ]
        seen = set()
        for pattern in loose_patterns:
            for matched in re.finditer(pattern, html, re.IGNORECASE):
                candidate = VideoService._normalize_image_url(matched.group(0), response.url or normalized)
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                if VideoService._is_accessible_image_url(candidate):
                    return candidate
        return ""

    @staticmethod
    def _score_video_candidate(news_title: str, candidate: Dict[str, Any]) -> float:
        title = str(candidate.get("title") or "").strip()
        if not title:
            return 0.0

        normalized_target = VideoService._normalize_title_key(news_title)
        normalized_title = VideoService._normalize_title_key(title)
        if not normalized_target or not normalized_title:
            return 0.0

        similarity = SequenceMatcher(None, normalized_target, normalized_title).ratio()
        source_bonus = 0.06 if candidate.get("source") == "bilibili" else 0.03 if candidate.get("source") == "youtube" else 0
        views = float(candidate.get("views") or 0)
        views_bonus = min(views / 1000000, 0.08)
        return similarity + source_bonus + views_bonus

    @staticmethod
    def _get_thumbnail_cache_collection():
        return getattr(db, VideoService.THUMBNAIL_CACHE_COLLECTION)

    @staticmethod
    def _get_summary_cache_collection():
        return getattr(db, VideoService.SUMMARY_CACHE_COLLECTION)

    @staticmethod
    def get_cached_thumbnail(news_title: str) -> Optional[Dict[str, Any]]:
        title_key = VideoService._normalize_title_key(news_title)
        if not title_key:
            return None

        cached = VideoService._get_thumbnail_cache_collection().find_one({"title_key": title_key})
        if not cached:
            return None

        expires_at = cached.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at < datetime.utcnow():
            return None
        return cached

    @staticmethod
    def save_thumbnail_cache(
        news_title: str,
        *,
        source_url: str = "",
        image_url: str = "",
        image_source: str = "",
        score: float = 0.0,
        status: str = "ready",
        error_message: str = "",
        ttl_hours: int = 24,
    ) -> Dict[str, Any]:
        title_key = VideoService._normalize_title_key(news_title)
        now = datetime.utcnow()
        document = {
            "title_key": title_key,
            "raw_title": str(news_title or "").strip(),
            "source_url": str(source_url or "").strip(),
            "image_url": str(image_url or "").strip(),
            "image_source": str(image_source or "").strip(),
            "score": round(float(score or 0), 4),
            "status": status,
            "error_message": error_message,
            "updated_at": now,
            "expires_at": now if ttl_hours <= 0 else now.replace(microsecond=0) + timedelta(hours=ttl_hours),
        }
        VideoService._get_thumbnail_cache_collection().replace_one(
            {"title_key": title_key},
            document,
            upsert=True,
        )
        return document

    @staticmethod
    def get_cached_summary(news_title: str) -> Optional[Dict[str, Any]]:
        title_key = VideoService._normalize_title_key(news_title)
        if not title_key:
            return None

        cached = VideoService._get_summary_cache_collection().find_one({"title_key": title_key})
        if not cached:
            return None

        expires_at = cached.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at < datetime.utcnow():
            return None
        return cached

    @staticmethod
    def save_summary_cache(
        news_title: str,
        *,
        source_url: str = "",
        summary: str = "",
        summary_source: str = "",
        status: str = "ready",
        error_message: str = "",
        ttl_hours: int = 24,
    ) -> Dict[str, Any]:
        title_key = VideoService._normalize_title_key(news_title)
        now = datetime.utcnow()
        document = {
            "title_key": title_key,
            "raw_title": str(news_title or "").strip(),
            "source_url": str(source_url or "").strip(),
            "summary": str(summary or "").strip(),
            "summary_source": str(summary_source or "").strip(),
            "status": status,
            "error_message": error_message,
            "updated_at": now,
            "expires_at": now if ttl_hours <= 0 else now.replace(microsecond=0) + timedelta(hours=ttl_hours),
        }
        VideoService._get_summary_cache_collection().replace_one(
            {"title_key": title_key},
            document,
            upsert=True,
        )
        return document

    @staticmethod
    def resolve_recommendation_summary(
        news_title: str,
        source_url: str = "",
        *,
        force_refresh: bool = False,
        cache_only: bool = False,
    ) -> Dict[str, Any]:
        normalized_title = str(news_title or "").strip()
        if not normalized_title:
            return {"success": False, "summary": "", "status": "failed", "message": "缺少标题"}

        if not force_refresh:
            cached = VideoService.get_cached_summary(normalized_title)
            if cached:
                if cached.get("status") == "ready" and cached.get("summary"):
                    return {
                        "success": True,
                        "summary": cached.get("summary") or "",
                        "summary_source": cached.get("summary_source") or "cache",
                        "cached": True,
                        "status": "ready",
                    }
                if cached.get("status") == "failed":
                    return {
                        "success": False,
                        "summary": "",
                        "summary_source": "",
                        "cached": True,
                        "status": "failed",
                        "message": cached.get("error_message") or "未命中可用摘要",
                    }

        if cache_only:
            return {"success": False, "summary": "", "status": "failed", "cached": False, "message": "cache-only miss"}

        if not source_url:
            VideoService.save_summary_cache(
                normalized_title,
                source_url=source_url,
                summary="",
                summary_source="",
                status="failed",
                error_message="缺少原始链接",
                ttl_hours=6,
            )
            return {"success": False, "summary": "", "status": "failed", "message": "缺少原始链接"}

        response = VideoService._fetch_url(source_url, timeout=8, stream=False)
        if response is None:
            return {"success": False, "summary": "", "status": "failed", "message": "页面请求失败"}

        html = response.text or ""
        summary = VideoService._extract_meta_description_from_html(html)
        summary_source = "meta_description"
        if not summary:
            summary = VideoService._extract_candidate_summary_from_html(html)
            summary_source = "page_content"

        if summary:
            VideoService.save_summary_cache(
                normalized_title,
                source_url=source_url,
                summary=summary,
                summary_source=summary_source,
                status="ready",
                ttl_hours=24,
            )
            return {
                "success": True,
                "summary": summary,
                "summary_source": summary_source,
                "cached": False,
                "status": "ready",
            }

        VideoService.save_summary_cache(
            normalized_title,
            source_url=source_url,
            summary="",
            summary_source="",
            status="failed",
            error_message="未命中可用摘要",
            ttl_hours=6,
        )
        return {"success": False, "summary": "", "status": "failed", "message": "未命中可用摘要"}

    @staticmethod
    def resolve_recommendation_thumbnail(
        news_title: str,
        source_url: str = "",
        *,
        platform_hint: str = "",
        max_results: int = 5,
        force_refresh: bool = False,
        skip_youtube: bool = False,
        cache_only: bool = False,
    ) -> Dict[str, Any]:
        normalized_title = str(news_title or "").strip()
        if not normalized_title:
            return {"success": False, "message": "缺少标题", "image_url": "", "status": "failed"}

        if not force_refresh:
            cached = VideoService.get_cached_thumbnail(normalized_title)
            if cached:
                if cached.get("status") == "ready" and cached.get("image_url"):
                    return {
                        "success": True,
                        "image_url": cached.get("image_url") or "",
                        "image_source": cached.get("image_source") or "cache",
                        "score": float(cached.get("score") or 0),
                        "cached": True,
                        "status": "ready",
                    }
                if cached.get("status") == "failed":
                    return {
                        "success": False,
                        "image_url": "",
                        "image_source": "",
                        "score": float(cached.get("score") or 0),
                        "cached": True,
                        "status": "failed",
                        "message": cached.get("error_message") or "未命中可用缩略图",
                    }

        if cache_only:
            return {"success": False, "image_url": "", "image_source": "", "status": "failed", "cached": False, "message": "cache-only miss"}

        platform_hint_normalized = str(platform_hint or "").strip().lower()
        page_thumbnail = ""
        if source_url:
            page_thumbnail = VideoService._resolve_page_thumbnail(source_url)
            if page_thumbnail:
                VideoService.save_thumbnail_cache(
                    normalized_title,
                    source_url=source_url,
                    image_url=page_thumbnail,
                    image_source="og_image",
                    score=1.0,
                    status="ready",
                    ttl_hours=24,
                )
                return {
                    "success": True,
                    "image_url": page_thumbnail,
                    "image_source": "og_image",
                    "score": 1.0,
                    "cached": False,
                    "status": "ready",
                }

        if "哔哩" in platform_hint or "bilibili" in platform_hint_normalized:
            candidates = VideoService.search_bilibili_videos(normalized_title, max_results=max_results)
        elif "抖音" in platform_hint or "douyin" in platform_hint_normalized:
            candidates = VideoService.search_bilibili_videos(normalized_title, max_results=max_results)
        elif skip_youtube:
            candidates = VideoService.search_bilibili_videos(normalized_title, max_results=max_results)
        else:
            candidates = VideoService.search_video_by_news_title(normalized_title, max_results=max_results)
        best_candidate = None
        best_score = 0.0
        for candidate in candidates:
            thumbnail_url = VideoService._normalize_image_url(candidate.get("thumbnail_url"))
            if not thumbnail_url or not VideoService._is_accessible_image_url(thumbnail_url):
                continue
            score = VideoService._score_video_candidate(normalized_title, candidate)
            if score > best_score:
                best_score = score
                best_candidate = {
                    **candidate,
                    "thumbnail_url": thumbnail_url,
                }

        score_threshold = 0.28
        if "哔哩" in platform_hint or "bilibili" in platform_hint_normalized:
            score_threshold = 0.2
        elif "抖音" in platform_hint or "douyin" in platform_hint_normalized:
            score_threshold = 0.18

        if best_candidate and best_score >= score_threshold:
            VideoService.save_thumbnail_cache(
                normalized_title,
                source_url=source_url,
                image_url=best_candidate["thumbnail_url"],
                image_source=str(best_candidate.get("source") or "video_search"),
                score=best_score,
                status="ready",
                ttl_hours=12,
            )
            return {
                "success": True,
                "image_url": best_candidate["thumbnail_url"],
                "image_source": best_candidate.get("source") or "video_search",
                "score": round(best_score, 4),
                "cached": False,
                "status": "ready",
            }

        VideoService.save_thumbnail_cache(
            normalized_title,
            source_url=source_url,
            image_url="",
            image_source="",
            score=best_score,
            status="failed",
            error_message="未命中可用缩略图",
            ttl_hours=6,
        )
        return {
            "success": False,
            "image_url": "",
            "image_source": "",
            "score": round(best_score, 4),
            "cached": False,
            "status": "failed",
            "message": "未命中可用缩略图",
        }
    
    @staticmethod
    def search_bilibili_videos(news_title: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        使用B站API搜索视频
        
        Args:
            news_title: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            视频信息列表
        """
        try:
            url = "https://api.bilibili.com/x/web-interface/search/all/v2"
            params = {
                "keyword": news_title,
                "page": 1,
                "page_size": max_results
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
                "Accept": "application/json"
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"B站API响应错误: {response.status_code}")
                return []
            
            data = response.json()
            
            if data['code'] != 0:
                print(f"B站API返回错误: {data['message']}")
                return []
            
            # 提取视频数据
            result_list = []
            for item in data.get('data', {}).get('result', []):
                if item.get('result_type') == 'video':
                    for video in item.get('data', []):
                        video_info = {
                            "title": video.get('title', '').replace('<em class="keyword">', '').replace('</em>', ''),
                            "video_id": str(video.get('aid')),
                            "bvid": video.get('bvid'),
                            "url": f"https://www.bilibili.com/video/{video.get('bvid')}",
                            "channel": video.get('author'),
                            "views": video.get('play', 0),
                            "publish_date": video.get('pubdate', ''),
                            "thumbnail_url": video.get('pic'),
                            "duration": video.get('duration', ''),
                            "source": "bilibili"
                        }
                        result_list.append(video_info)
                        
                        if len(result_list) >= max_results:
                            break
                            
                    if len(result_list) >= max_results:
                        break
            
            # 按播放量排序
            result_list.sort(key=lambda x: x.get('views', 0), reverse=True)
            
            return result_list
        
        except Exception as e:
            print(f"搜索B站视频时出错: {str(e)}")
            return []

    @staticmethod
    def search_video_by_news_title(news_title: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        根据新闻标题搜索相关视频，先尝试YouTube，失败后尝试B站
        
        Args:
            news_title: 新闻标题
            max_results: 最大结果数量
            
        Returns:
            包含视频信息的列表
        """
        print(f"搜索与标题相关的视频: {news_title}")
        
        # 首先尝试YouTube
        try:
            videos = VideoService._search_youtube_videos(news_title, max_results)
            if videos:
                return videos
        except Exception as e:
            print(f"YouTube搜索失败: {str(e)}")
        
        # 如果YouTube失败，尝试B站
        print("尝试使用B站搜索视频...")
        bilibili_videos = VideoService.search_bilibili_videos(news_title, max_results)
        
        return bilibili_videos

    @staticmethod
    def _search_youtube_videos(news_title: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        使用yt-dlp搜索YouTube视频
        
        Args:
            news_title: 新闻标题
            max_results: 最大结果数
            
        Returns:
            视频信息列表
        """
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'force_generic_extractor': True,
                'format': 'best',
                'ignoreerrors': True,
                'no_warnings': True,
                'playlistend': max_results + 5  # 多获取几个以防有些获取不到信息
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 搜索YouTube
                search_url = f"ytsearch{max_results + 5}:{news_title}"
                info = ydl.extract_info(search_url, download=False)
                
                if 'entries' not in info:
                    print(f"未找到视频: {info}")
                    return []
                
                videos_info = []
                
                # 提取基本信息
                for entry in info['entries']:
                    if entry is None:
                        continue
                    
                    # 从flat info中获取基本信息
                    try:
                        video_id = entry.get('id')
                        if not video_id:
                            continue
                        
                        # 构建简化的视频信息
                        video_info = {
                            "title": entry.get('title'),
                            "video_id": video_id,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "channel": entry.get('uploader', entry.get('channel')),
                            "views": entry.get('view_count', 0),
                            "publish_date": entry.get('upload_date'),
                            "thumbnail_url": entry.get('thumbnail'),
                            "duration": entry.get('duration'),
                            "source": "youtube"
                        }
                        
                        # 仅添加有必要信息的视频
                        if video_info["title"] and video_info["video_id"]:
                            videos_info.append(video_info)
                            
                            # 如果已经获取了足够的视频，停止
                            if len(videos_info) >= max_results:
                                break
                    
                    except Exception as e:
                        print(f"处理视频信息时出错: {str(e)}")
                        continue
                
                # 按播放量排序
                videos_info.sort(key=lambda x: x.get("views", 0), reverse=True)
                
                return videos_info
        
        except Exception as e:
            print(f"搜索YouTube视频时出错: {str(e)}")
            return []

    @staticmethod
    def download_audio_and_subtitles(video_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        下载视频的音频和字幕
        
        Args:
            video_url: 视频URL
            
        Returns:
            包含音频文件路径和字幕文件路径的元组
        """
        temp_dir = tempfile.mkdtemp()
        audio_output = os.path.join(temp_dir, "audio.mp3")
        subtitle_output = os.path.join(temp_dir, "subtitles")
        
        try:
            # 识别视频平台
            is_bilibili = "bilibili.com" in video_url
            
            # 使用yt-dlp下载音频和字幕
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': audio_output,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'writeautomaticsub': True,  # 获取自动生成的字幕
                'subtitleslangs': ['zh-Hans', 'zh-CN', 'en'],  # 优先获取中文字幕
                'subtitlesformat': 'srt',
                'skip_download': False,
                'quiet': True,
                'verbose': False,
            }
            
            if is_bilibili:
                # B站特殊处理
                ydl_opts['extractor_args'] = {
                    'bilibili': {
                        'cookies': os.path.join(os.path.dirname(__file__), 'cookies.txt')
                    }
                }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                
                # 查找字幕文件
                subtitle_files = [f for f in os.listdir(temp_dir) if f.endswith('.srt')]
                subtitle_path = os.path.join(temp_dir, subtitle_files[0]) if subtitle_files else None
                
                if not subtitle_path:
                    print("没有找到字幕文件，尝试使用自动生成的字幕")
                    # 尝试获取自动生成的字幕
                    ydl_opts['writeautomaticsub'] = True
                    ydl_opts['skip_download'] = True
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                        ydl2.extract_info(video_url, download=True)
                        
                    # 再次查找字幕文件
                    subtitle_files = [f for f in os.listdir(temp_dir) if f.endswith('.srt')]
                    subtitle_path = os.path.join(temp_dir, subtitle_files[0]) if subtitle_files else None
                
                # 如果找不到字幕，尝试其他方式
                if not subtitle_path and is_bilibili:
                    print("尝试直接提取B站视频字幕...")
                    subtitle_path = VideoService._extract_bilibili_subtitle(video_url, temp_dir)
                
            return audio_output, subtitle_path
        
        except Exception as e:
            print(f"下载音频和字幕时出错: {str(e)}")
            return None, None

    @staticmethod
    def _extract_bilibili_subtitle(video_url: str, temp_dir: str) -> Optional[str]:
        """
        直接从B站API提取字幕
        
        Args:
            video_url: B站视频URL
            temp_dir: 临时目录
            
        Returns:
            字幕文件路径
        """
        try:
            # 提取BV号或AV号
            if "BV" in video_url:
                bvid = re.search(r"BV\w+", video_url).group(0)
                params = {"bvid": bvid}
            else:
                aid = re.search(r"av(\d+)", video_url).group(1)
                params = {"aid": aid}
            
            # 获取视频信息
            cid_api = "https://api.bilibili.com/x/web-interface/view"
            r = requests.get(cid_api, params=params, timeout=10)
            if r.status_code != 200:
                print(f"获取B站视频信息失败: {r.status_code}")
                return None
            
            data = r.json()
            if data['code'] != 0:
                print(f"B站API返回错误: {data['message']}")
                return None
            
            cid = data['data']['cid']
            
            # 获取字幕信息
            subtitle_api = f"https://api.bilibili.com/x/player/v2"
            params["cid"] = cid
            r = requests.get(subtitle_api, params=params, timeout=10)
            
            if r.status_code != 200:
                print(f"获取B站字幕信息失败: {r.status_code}")
                return None
            
            subtitle_data = r.json()
            if subtitle_data['code'] != 0:
                print(f"B站字幕API返回错误: {subtitle_data['message']}")
                return None
            
            subtitles = subtitle_data.get('data', {}).get('subtitle', {}).get('subtitles', [])
            
            if not subtitles:
                print("该B站视频没有字幕")
                return None
            
            # 获取第一个字幕
            subtitle_url = "https:" + subtitles[0]['subtitle_url']
            r = requests.get(subtitle_url, timeout=10)
            
            if r.status_code != 200:
                print(f"下载B站字幕失败: {r.status_code}")
                return None
            
            # B站字幕是JSON格式，需要转换为SRT格式
            subtitle_json = r.json()
            subtitle_path = os.path.join(temp_dir, "bilibili_subtitle.srt")
            
            # 转换为SRT格式
            with open(subtitle_path, "w", encoding="utf-8") as f:
                for i, sub in enumerate(subtitle_json.get('body', [])):
                    start_time = VideoService._format_time(float(sub['from']))
                    end_time = VideoService._format_time(float(sub['to']))
                    
                    f.write(f"{i+1}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{sub['content']}\n\n")
            
            return subtitle_path
        
        except Exception as e:
            print(f"提取B站字幕时出错: {str(e)}")
            return None

    @staticmethod
    def _format_time(seconds: float) -> str:
        """
        将秒数转换为SRT时间格式
        
        Args:
            seconds: 秒数
            
        Returns:
            SRT格式时间字符串
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds - int(seconds)) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

    @staticmethod
    def parse_srt_to_json(srt_file_path: str) -> List[Dict[str, Any]]:
        """
        将SRT字幕文件解析为JSON格式
        
        Args:
            srt_file_path: SRT文件路径
            
        Returns:
            包含字幕信息的JSON列表
        """
        try:
            subtitles = pysrt.open(srt_file_path)
            
            result = []
            for sub in subtitles:
                subtitle_item = {
                    "index": sub.index,
                    "start_time": {
                        "hours": sub.start.hours,
                        "minutes": sub.start.minutes,
                        "seconds": sub.start.seconds,
                        "milliseconds": sub.start.milliseconds,
                        "total_seconds": sub.start.hours * 3600 + sub.start.minutes * 60 + sub.start.seconds + sub.start.milliseconds / 1000
                    },
                    "end_time": {
                        "hours": sub.end.hours,
                        "minutes": sub.end.minutes,
                        "seconds": sub.end.seconds,
                        "milliseconds": sub.end.milliseconds,
                        "total_seconds": sub.end.hours * 3600 + sub.end.minutes * 60 + sub.end.seconds + sub.end.milliseconds / 1000
                    },
                    "text": sub.text,
                    "position": sub.position
                }
                result.append(subtitle_item)
            
            return result
        
        except Exception as e:
            print(f"解析SRT文件时出错: {str(e)}")
            return []

    @staticmethod
    def save_subtitles_to_mongodb(
        video_info: Dict[str, Any], 
        subtitles_json: List[Dict[str, Any]], 
        news_title: str,
        collection_name: str = "video_subtitles"
    ) -> Optional[str]:
        """
        将字幕JSON保存到MongoDB
        
        Args:
            video_info: 视频信息
            subtitles_json: 字幕JSON数据
            news_title: 相关新闻标题
            collection_name: MongoDB集合名称
            
        Returns:
            插入的文档ID
        """
        try:
            # 准备要保存的文档
            document = {
                "news_title": news_title,
                "video_info": video_info,
                "subtitles": subtitles_json,
                "created_at": datetime.utcnow()
            }
            
            # 插入到MongoDB
            result = db[collection_name].insert_one(document)
            
            print(f"字幕数据已保存到MongoDB, ID: {result.inserted_id}")
            return str(result.inserted_id)
        
        except Exception as e:
            print(f"保存到MongoDB失败: {str(e)}")
            return None

    @staticmethod
    def process_news_video(news_title: str, platform: str = 'all') -> Dict[str, Any]:
        """
        处理新闻视频的完整流程
        
        Args:
            news_title: 新闻标题
            platform: 指定平台 ('youtube', 'bilibili', 'all')
            
        Returns:
            处理结果
        """
        try:
            # 1. 搜索相关视频
            if platform == 'youtube':
                videos = VideoService._search_youtube_videos(news_title)
            elif platform == 'bilibili':
                videos = VideoService.search_bilibili_videos(news_title)
            else:
                videos = VideoService.search_video_by_news_title(news_title)
            
            if not videos:
                return {"success": False, "message": "未找到相关视频", "platform": platform}
            
            # 选择播放量最高的视频
            top_video = videos[0]
            
            # 2. 下载音频和字幕
            audio_path, subtitle_path = VideoService.download_audio_and_subtitles(top_video["url"])
            
            if not audio_path or not subtitle_path:
                return {
                    "success": False, 
                    "message": "下载音频或字幕失败", 
                    "video_info": top_video,
                    "platform": platform
                }
            
            # 3. 解析字幕为JSON
            subtitles_json = VideoService.parse_srt_to_json(subtitle_path)
            
            if not subtitles_json:
                return {
                    "success": False, 
                    "message": "解析字幕失败", 
                    "video_info": top_video, 
                    "audio_path": audio_path,
                    "subtitle_path": subtitle_path,
                    "platform": platform
                }
            
            # 4. 保存到MongoDB
            doc_id = VideoService.save_subtitles_to_mongodb(top_video, subtitles_json, news_title)
            
            if not doc_id:
                return {
                    "success": False, 
                    "message": "保存到MongoDB失败", 
                    "video_info": top_video,
                    "subtitles_count": len(subtitles_json),
                    "platform": platform
                }
            
            # 清理临时文件
            try:
                os.remove(audio_path)
                os.remove(subtitle_path)
            except:
                pass
            
            return {
                "success": True,
                "message": "处理成功",
                "video_info": top_video,
                "subtitles_count": len(subtitles_json),
                "mongodb_id": doc_id,
                "platform": platform
            }
            
        except Exception as e:
            print(f"处理视频时出错: {str(e)}")
            return {"success": False, "message": f"处理视频时出错: {str(e)}", "platform": platform} 
