import hashlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

from ..extensions import db
from .video_service import VideoService


class CrawlerService:
    """按标题/链接抓取新闻上下文并存库，供 MCP tool 与后续 RAG 复用。"""

    COLLECTION = "news_evidence"
    CACHE_TTL_DAYS = 3
    SEARCH_PROVIDERS = (
        {
            "name": "bing",
            "url_template": "https://www.bing.com/search?q={query}",
        },
        {
            "name": "baidu",
            "url_template": "https://www.baidu.com/s?wd={query}",
        },
    )
    NOISE_TITLE_PATTERNS = (
        "百度一下",
        "bing",
        "google",
        "搜索",
        "网址大全",
        "hao123",
        "输入法",
        "地图 视频 贴吧 学术",
    )
    LISTING_HOST_HINTS = (
        "s.weibo.com",
        "weibo.com",
        "baidu.com",
        "bing.com",
    )
    STOP_TERMS = {
        "请围绕以下热点做一版深度舆情分析并明确区分已知事实待核实信息与分析判断",
        "请重点输出事件概述传播脉络风险点情绪判断关键疑点下一步建议",
        "帮我分析这个热点",
        "帮我分析",
        "请分析",
        "热点",
        "标题",
        "来源平台",
        "原始链接",
        "更新时间",
        "事件",
        "分析",
        "舆情",
        "深度",
        "进行",
        "请",
        "帮我",
        "这个",
    }

    @staticmethod
    def _collection():
        collection = getattr(db, CrawlerService.COLLECTION)
        try:
            collection.create_index("query_key", unique=True)
            collection.create_index("title_key")
            collection.create_index("session_id")
            collection.create_index("user_id")
            collection.create_index("created_at")
        except Exception:
            pass
        return collection

    @staticmethod
    def _normalize_title_key(value: str) -> str:
        return "".join(str(value or "").strip().lower().split())

    @staticmethod
    def _normalize_query_key(title: str, source_url: str = "") -> str:
        raw = f"{CrawlerService._normalize_title_key(title)}|{str(source_url or '').strip()}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _clean_text(value: str, limit: int = 1500) -> str:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]

    @staticmethod
    def _extract_focus_terms(value: str) -> List[str]:
        text = CrawlerService._clean_text(value, limit=300)
        if not text:
            return []

        candidates = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{3,}", text)
        terms: List[str] = []
        seen = set()
        for candidate in candidates:
            normalized = candidate.strip().lower()
            if not normalized or normalized in CrawlerService.STOP_TERMS:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            terms.append(candidate.strip())
        return terms[:12]

    @staticmethod
    def _score_text_relevance(query_title: str, *texts: str) -> float:
        normalized_query = CrawlerService._clean_text(query_title, limit=300)
        merged_text = CrawlerService._clean_text(" ".join(str(item or "") for item in texts), limit=3000)
        if not normalized_query or not merged_text:
            return 0.0

        title_match_score = CrawlerService._score_title_match(normalized_query, merged_text)
        query_terms = CrawlerService._extract_focus_terms(normalized_query)
        if not query_terms:
            return title_match_score

        normalized_merged = merged_text.lower()
        matched_terms = sum(1 for term in query_terms if term.lower() in normalized_merged)
        coverage_score = matched_terms / max(len(query_terms), 1)

        long_phrase_bonus = 0.0
        for term in query_terms:
            if len(term) >= 4 and term.lower() in normalized_merged:
                long_phrase_bonus = 0.08
                break

        return min(1.0, title_match_score * 0.55 + coverage_score * 0.45 + long_phrase_bonus)

    @staticmethod
    def _is_noise_page(query_title: str, page_title: str, summary: str, excerpt: str, final_url: str) -> bool:
        normalized_title = CrawlerService._clean_text(page_title, limit=300).lower()
        normalized_summary = CrawlerService._clean_text(summary, limit=500).lower()
        normalized_excerpt = CrawlerService._clean_text(excerpt, limit=1000).lower()
        normalized_url = str(final_url or "").lower()

        if any(pattern in normalized_title for pattern in CrawlerService.NOISE_TITLE_PATTERNS):
            return True
        if any(token in normalized_url for token in ("/s?", "wd=", "query=", "search?")) and "article" not in normalized_url:
            return True
        if any(pattern in normalized_summary for pattern in ("hao123", "贴吧 学术 登录", "输入法 手写 拼音", "更多产品", "设置 登录")):
            return True

        relevance_score = CrawlerService._score_text_relevance(
            query_title,
            page_title,
            summary,
            excerpt,
        )
        return relevance_score < 0.18 and len(normalized_excerpt) < 120

    @staticmethod
    def _is_listing_like_url(url: str) -> bool:
        parsed = urlparse(str(url or ""))
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        query = parsed.query or ""
        if any(hint in host for hint in CrawlerService.LISTING_HOST_HINTS):
            if host == "s.weibo.com":
                return True
            if host.endswith("baidu.com") and (path.startswith("/s") or "wd=" in query):
                return True
            if host.endswith("bing.com") and path.startswith("/search"):
                return True
            if host.endswith("weibo.com") and ("q=" in query or path.startswith("/ajax/side/search") or path.startswith("/weibo")):
                return True
        return False

    @staticmethod
    def _extract_meta_title(html: str) -> str:
        patterns = [
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
            r"<title[^>]*>(.*?)</title>",
        ]
        for pattern in patterns:
            matched = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if matched and matched.group(1):
                cleaned = CrawlerService._clean_text(matched.group(1), limit=180)
                if cleaned:
                    return cleaned
        return ""

    @staticmethod
    def _extract_site_name(html: str, final_url: str) -> str:
        patterns = [
            r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:site_name["\']',
            r'<meta[^>]+name=["\']application-name["\'][^>]+content=["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            matched = re.search(pattern, html, re.IGNORECASE)
            if matched and matched.group(1):
                cleaned = CrawlerService._clean_text(matched.group(1), limit=80)
                if cleaned:
                    return cleaned
        host = (urlparse(str(final_url or "")).netloc or "").lower()
        return host.replace("www.", "")

    @staticmethod
    def _extract_published_at(html: str) -> Optional[str]:
        patterns = [
            r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']publishdate["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+itemprop=["\']datePublished["\'][^>]+content=["\']([^"\']+)["\']',
            r'<time[^>]+datetime=["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            matched = re.search(pattern, html, re.IGNORECASE)
            if matched and matched.group(1):
                return str(matched.group(1)).strip()
        return None

    @staticmethod
    def _extract_content_excerpt(html: str, query_title: str = "") -> str:
        paragraphs: List[str] = []
        for matched in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL):
            cleaned = CrawlerService._clean_text(matched.group(1), limit=450)
            if len(cleaned) >= 24:
                paragraphs.append(cleaned)
            if len(paragraphs) >= 16:
                break

        if not paragraphs:
            summary = VideoService._extract_candidate_summary_from_html(html)
            if summary:
                return CrawlerService._clean_text(summary, limit=800)
            return ""

        best_excerpt = ""
        best_score = 0.0
        max_window = min(4, len(paragraphs))
        for window_size in range(1, max_window + 1):
            for index in range(0, len(paragraphs) - window_size + 1):
                candidate = " ".join(paragraphs[index:index + window_size]).strip()
                if len(candidate) < 60:
                    continue
                score = CrawlerService._score_text_relevance(query_title, candidate) if query_title else 0.3
                score += min(len(candidate), 900) / 6000
                if score > best_score:
                    best_score = score
                    best_excerpt = candidate[:1200]

        if best_excerpt and (not query_title or best_score >= 0.22):
            return best_excerpt

        return " ".join(paragraphs[:3])[:1000]

    @staticmethod
    def _load_cached_record(query_key: str, *, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        if force_refresh:
            return None
        cached = CrawlerService._collection().find_one({"query_key": query_key})
        if not cached:
            return None
        expires_at = cached.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at < datetime.utcnow():
            return None
        return cached

    @staticmethod
    def _find_hotnews_candidates(title: str, platform_hint: str = "", max_candidates: int = 5) -> List[Dict[str, Any]]:
        normalized_title = CrawlerService._normalize_title_key(title)
        normalized_platform_hint = CrawlerService._normalize_title_key(platform_hint)
        if not normalized_title:
            return []

        try:
            cursor = db.hot_news.find(
                {},
                {
                    "_id": 0,
                    "title": 1,
                    "url": 1,
                    "platform": 1,
                    "timestamp": 1,
                    "normalized_heat": 1,
                },
            )
            if hasattr(cursor, "sort") and hasattr(cursor, "limit"):
                records = list(cursor.sort("normalized_heat", -1).limit(200))
            else:
                records = sorted(
                    list(cursor),
                    key=lambda item: float(item.get("normalized_heat") or 0),
                    reverse=True,
                )[:200]
        except Exception:
            records = []

        scored: List[Dict[str, Any]] = []
        for item in records:
            item_title = str(item.get("title") or "").strip()
            item_url = str(item.get("url") or "").strip()
            item_platform = str(item.get("platform") or "").strip()
            if not item_title or not item_url:
                continue
            normalized_item = CrawlerService._normalize_title_key(item_title)
            normalized_item_platform = CrawlerService._normalize_title_key(item_platform)
            if not normalized_item:
                continue

            score = 0.0
            if normalized_title == normalized_item:
                score = 1.0
            elif normalized_title in normalized_item or normalized_item in normalized_title:
                score = 0.9
            else:
                common_chars = len(set(normalized_title) & set(normalized_item))
                base = max(len(set(normalized_title)), 1)
                score = common_chars / base

            if normalized_platform_hint and normalized_item_platform:
                if normalized_platform_hint == normalized_item_platform:
                    score += 0.12
                elif normalized_platform_hint in normalized_item_platform or normalized_item_platform in normalized_platform_hint:
                    score += 0.08

            if score < 0.45:
                continue

            scored.append(
                {
                    "title": item_title,
                    "url": item_url,
                    "platform": item_platform,
                    "published_at": item.get("timestamp"),
                    "score": score,
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:max_candidates]

    @staticmethod
    def _score_title_match(query_title: str, candidate_title: str) -> float:
        normalized_query = CrawlerService._normalize_title_key(query_title)
        normalized_candidate = CrawlerService._normalize_title_key(candidate_title)
        if not normalized_query or not normalized_candidate:
            return 0.0
        if normalized_query == normalized_candidate:
            return 1.0
        if normalized_query in normalized_candidate or normalized_candidate in normalized_query:
            return 0.9
        common_chars = len(set(normalized_query) & set(normalized_candidate))
        return common_chars / max(len(set(normalized_query)), 1)

    @staticmethod
    def _extract_search_result_links(html: str, page_url: str) -> List[str]:
        links: List[str] = []
        seen = set()
        for matched in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE):
            href = str(matched.group(1) or "").strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                continue
            normalized = href
            if href.startswith("/"):
                normalized = urljoin(page_url, href)
            if normalized.startswith("//"):
                normalized = f"https:{normalized}"
            host = (urlparse(normalized).netloc or "").lower()
            if not host:
                continue
            if any(blocked in host for blocked in ("bing.com", "baidu.com", "sogou.com")):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            links.append(normalized)
            if len(links) >= 12:
                break
        return links

    @staticmethod
    def _expand_source_page_candidates(source_url: str, query_title: str, platform_hint: str = "", max_candidates: int = 5) -> List[Dict[str, Any]]:
        response = VideoService._fetch_url(source_url, timeout=10, stream=False)
        if response is None:
            return []

        html = response.text or ""
        resolved_url = response.url or source_url
        results: List[Dict[str, Any]] = []
        seen = set()
        for candidate_url in CrawlerService._extract_search_result_links(html, resolved_url):
            if candidate_url in seen:
                continue
            seen.add(candidate_url)
            prefetched = CrawlerService._fetch_page_context(candidate_url, query_title)
            if not prefetched:
                continue
            candidate_title = str(prefetched.get("page_title") or "").strip()
            title_score = CrawlerService._score_title_match(query_title, candidate_title)
            relevance_score = float(prefetched.get("relevance_score") or 0)
            score = title_score * 0.6 + relevance_score * 0.4
            if score < 0.3:
                continue
            results.append(
                {
                    "title": candidate_title or query_title,
                    "url": candidate_url,
                    "platform": platform_hint or "source_page",
                    "published_at": prefetched.get("published_at"),
                    "score": score,
                    "_prefetched": prefetched,
                }
            )
            if len(results) >= max_candidates:
                break
        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return results[:max_candidates]

    @staticmethod
    def _search_external_candidates(title: str, max_candidates: int = 5) -> List[Dict[str, Any]]:
        normalized_title = str(title or "").strip()
        if not normalized_title:
            return []

        results: List[Dict[str, Any]] = []
        seen = set()
        for provider in CrawlerService.SEARCH_PROVIDERS:
            query_url = provider["url_template"].format(query=quote_plus(normalized_title))
            response = VideoService._fetch_url(query_url, timeout=8, stream=False)
            if response is None:
                continue

            html = response.text or ""
            for candidate_url in CrawlerService._extract_search_result_links(html, response.url or query_url):
                if candidate_url in seen:
                    continue
                seen.add(candidate_url)
                prefetched = CrawlerService._fetch_page_context(candidate_url, normalized_title)
                if not prefetched:
                    continue
                candidate_title = str(prefetched.get("page_title") or "").strip()
                title_score = CrawlerService._score_title_match(normalized_title, candidate_title)
                relevance_score = float(prefetched.get("relevance_score") or 0)
                score = title_score * 0.6 + relevance_score * 0.4
                if score < 0.35:
                    continue
                results.append(
                    {
                        "title": candidate_title or normalized_title,
                        "url": candidate_url,
                        "platform": provider["name"],
                        "published_at": prefetched.get("published_at"),
                        "score": score,
                        "_prefetched": prefetched,
                    }
                )
                if len(results) >= max_candidates:
                    break
            if len(results) >= max_candidates:
                break

        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return results[:max_candidates]

    @staticmethod
    def _fetch_page_context(url: str, query_title: str = "") -> Optional[Dict[str, Any]]:
        response = VideoService._fetch_url(url, timeout=10, stream=False)
        if response is None:
            return None

        html = response.text or ""
        final_url = response.url or url
        page_title = CrawlerService._extract_meta_title(html)
        summary = VideoService._extract_meta_description_from_html(html)
        if not summary:
            summary = VideoService._extract_candidate_summary_from_html(html)
        excerpt = CrawlerService._extract_content_excerpt(html, query_title=query_title)
        relevance_score = CrawlerService._score_text_relevance(query_title, page_title, summary, excerpt) if query_title else 0.0
        if CrawlerService._is_noise_page(query_title, page_title, summary, excerpt, final_url):
            summary = ""
            excerpt = ""

        return {
            "final_url": final_url,
            "page_title": page_title,
            "source_name": CrawlerService._extract_site_name(html, final_url),
            "published_at": CrawlerService._extract_published_at(html),
            "summary": summary,
            "content_excerpt": excerpt,
            "relevance_score": relevance_score,
        }

    @staticmethod
    def save_record(record: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        payload["updated_at"] = datetime.utcnow()
        payload.setdefault("created_at", payload["updated_at"])
        payload["expires_at"] = datetime.utcnow() + timedelta(days=CrawlerService.CACHE_TTL_DAYS)

        CrawlerService._collection().replace_one(
            {"query_key": payload["query_key"]},
            payload,
            upsert=True,
        )
        return payload

    @classmethod
    def search_news_overview(
        cls,
        *,
        title: str,
        source_url: str = "",
        platform_hint: str = "",
        session_id: str = "",
        user_id: str = "",
        max_results: int = 10,
    ) -> Dict[str, Any]:
        from .source_verifier_service import SourceVerifierService
        from .time_verifier_service import TimeVerifierService

        normalized_title = str(title or "").strip()
        if not normalized_title:
            return {"success": False, "query_title": "", "items": [], "message": "缺少标题"}

        normalized_source_url = str(source_url or "").strip()
        candidate_limit = max(3, min(int(max_results or 10), 15))
        candidates: List[Dict[str, Any]] = []
        seen_urls = set()

        def append_candidate(item: Dict[str, Any]) -> None:
            candidate_url = str(item.get("url") or "").strip()
            key = candidate_url.lower() if candidate_url else str(item.get("title") or "").strip().lower()
            if not key or key in seen_urls:
                return
            seen_urls.add(key)
            candidates.append(item)

        if normalized_source_url:
            initial_prefetched = cls._fetch_page_context(normalized_source_url, normalized_title)
            if initial_prefetched:
                append_candidate(
                    {
                        "title": initial_prefetched.get("page_title") or normalized_title,
                        "url": normalized_source_url,
                        "platform": platform_hint,
                        "published_at": initial_prefetched.get("published_at"),
                        "score": 1.0,
                        "_prefetched": initial_prefetched,
                    }
                )
            for item in cls._expand_source_page_candidates(
                normalized_source_url,
                normalized_title,
                platform_hint=platform_hint,
                max_candidates=candidate_limit,
            ):
                append_candidate(item)

        for item in cls._find_hotnews_candidates(normalized_title, platform_hint=platform_hint, max_candidates=candidate_limit):
            append_candidate(item)

        for item in cls._search_external_candidates(normalized_title, max_candidates=candidate_limit):
            append_candidate(item)

        enriched: List[Dict[str, Any]] = []
        for candidate in candidates:
            fetched = candidate.get("_prefetched") if isinstance(candidate, dict) else None
            if not fetched:
                fetched = cls._fetch_page_context(str(candidate.get("url") or ""), normalized_title)
            if not fetched:
                continue
            final_url = str(fetched.get("final_url") or candidate.get("url") or "").strip()
            if not final_url:
                continue
            credibility = SourceVerifierService.verify(
                url=final_url,
                source_name=str(fetched.get("source_name") or ""),
                platform=str(candidate.get("platform") or platform_hint or ""),
            )
            time_check = TimeVerifierService.verify(
                title=str(candidate.get("title") or normalized_title),
                published_at=str(fetched.get("published_at") or candidate.get("published_at") or ""),
                extracted_text=str(fetched.get("content_excerpt") or fetched.get("summary") or ""),
                hotspot_time="",
            )
            relevance_score = float(fetched.get("relevance_score") or candidate.get("score") or 0)
            enriched.append(
                {
                    "title": str(fetched.get("page_title") or candidate.get("title") or normalized_title),
                    "url": final_url,
                    "source_name": str(fetched.get("source_name") or ""),
                    "platform": str(candidate.get("platform") or platform_hint or ""),
                    "published_at": fetched.get("published_at") or candidate.get("published_at"),
                    "summary": str(fetched.get("summary") or "")[:220],
                    "content_excerpt": str(fetched.get("content_excerpt") or fetched.get("summary") or "")[:800],
                    "credibility": credibility.get("credibility_level", "medium"),
                    "source_type": credibility.get("source_type", "general_webpage"),
                    "credibility_reason": credibility.get("reason", ""),
                    "time_reason": time_check.get("reason", ""),
                    "relevance_score": relevance_score,
                }
            )

        enriched.sort(key=lambda item: float(item.get("relevance_score") or 0), reverse=True)
        return {
            "success": bool(enriched),
            "query_title": normalized_title,
            "session_id": session_id or "",
            "user_id": user_id or "",
            "items": enriched[:candidate_limit],
            "message": "检索成功" if enriched else "未检索到相关结果",
        }

    @classmethod
    def crawl_news_context(
        cls,
        *,
        title: str,
        source_url: str = "",
        platform_hint: str = "",
        session_id: str = "",
        user_id: str = "",
        max_candidates: int = 5,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        normalized_title = str(title or "").strip()
        if not normalized_title:
            return {"success": False, "status": "failed", "message": "缺少标题"}

        normalized_source_url = str(source_url or "").strip()
        query_key = cls._normalize_query_key(normalized_title, normalized_source_url)
        cached = cls._load_cached_record(query_key, force_refresh=force_refresh)
        if cached:
            cached = dict(cached)
            cached.pop("_id", None)
            cached["success"] = cached.get("status") == "ready"
            cached["cached"] = True
            return cached

        candidates: List[Dict[str, Any]] = []
        if normalized_source_url:
            initial_prefetched = cls._fetch_page_context(normalized_source_url, normalized_title)
            if initial_prefetched and not cls._is_listing_like_url(normalized_source_url) and (
                initial_prefetched.get("summary") or initial_prefetched.get("content_excerpt")
            ):
                candidates.append(
                    {
                        "title": normalized_title,
                        "url": normalized_source_url,
                        "platform": platform_hint,
                        "published_at": initial_prefetched.get("published_at"),
                        "score": 1.0,
                        "_prefetched": initial_prefetched,
                    }
                )
            else:
                for candidate in cls._expand_source_page_candidates(
                    normalized_source_url,
                    normalized_title,
                    platform_hint=platform_hint,
                    max_candidates=max_candidates,
                ):
                    if candidate["url"] not in {item["url"] for item in candidates}:
                        candidates.append(candidate)
                    if len(candidates) >= max_candidates:
                        break
                if not candidates:
                    candidates.append(
                        {
                            "title": normalized_title,
                            "url": normalized_source_url,
                            "platform": platform_hint,
                            "published_at": initial_prefetched.get("published_at") if initial_prefetched else None,
                            "score": 0.8 if cls._is_listing_like_url(normalized_source_url) else 1.0,
                            "_prefetched": initial_prefetched,
                        }
                    )

        for candidate in cls._find_hotnews_candidates(normalized_title, platform_hint=platform_hint, max_candidates=max_candidates):
            if candidate["url"] not in {item["url"] for item in candidates}:
                candidates.append(candidate)

        if len(candidates) < max_candidates:
            for candidate in cls._search_external_candidates(normalized_title, max_candidates=max_candidates):
                if candidate["url"] not in {item["url"] for item in candidates}:
                    candidates.append(candidate)
                if len(candidates) >= max_candidates:
                    break

        if not candidates:
            record = cls.save_record(
                {
                    "query_key": query_key,
                    "title_key": cls._normalize_title_key(normalized_title),
                    "query_title": normalized_title,
                    "requested_source_url": normalized_source_url,
                    "platform_hint": platform_hint,
                    "session_id": session_id or None,
                    "user_id": user_id or None,
                    "status": "failed",
                    "message": "未找到可抓取的候选链接",
                    "summary": "",
                    "content_excerpt": "",
                    "source_name": "",
                    "final_url": "",
                    "published_at": None,
                    "candidate_urls": [],
                }
            )
            record["success"] = False
            return record

        chosen_result: Optional[Dict[str, Any]] = None
        best_score = -1.0
        for candidate in candidates[:max_candidates]:
            fetched = candidate.get("_prefetched") if isinstance(candidate, dict) else None
            if not fetched:
                fetched = cls._fetch_page_context(candidate["url"], normalized_title)
            if not fetched:
                continue
            combined_score = float(candidate.get("score") or 0) * 0.5 + float(fetched.get("relevance_score") or 0) * 0.5
            has_content = bool(fetched.get("summary") or fetched.get("content_excerpt"))
            if has_content and combined_score > best_score:
                chosen_result = {**candidate, **fetched}
                best_score = combined_score
            elif chosen_result is None and combined_score > best_score:
                chosen_result = {**candidate, **fetched}
                best_score = combined_score

        if not chosen_result:
            record = cls.save_record(
                {
                    "query_key": query_key,
                    "title_key": cls._normalize_title_key(normalized_title),
                    "query_title": normalized_title,
                    "requested_source_url": normalized_source_url,
                    "platform_hint": platform_hint,
                    "session_id": session_id or None,
                    "user_id": user_id or None,
                    "status": "failed",
                    "message": "候选链接抓取失败",
                    "summary": "",
                    "content_excerpt": "",
                    "source_name": "",
                    "final_url": "",
                    "published_at": None,
                    "candidate_urls": [item["url"] for item in candidates[:max_candidates]],
                }
            )
            record["success"] = False
            return record

        record = cls.save_record(
            {
                "query_key": query_key,
                "title_key": cls._normalize_title_key(normalized_title),
                "query_title": normalized_title,
                "requested_source_url": normalized_source_url,
                "platform_hint": platform_hint,
                "session_id": session_id or None,
                "user_id": user_id or None,
                "status": "ready",
                "message": "抓取成功",
                "summary": str(chosen_result.get("summary") or "").strip(),
                "content_excerpt": str(chosen_result.get("content_excerpt") or "").strip(),
                "source_name": str(chosen_result.get("source_name") or "").strip(),
                "final_url": str(chosen_result.get("final_url") or chosen_result.get("url") or "").strip(),
                "published_at": chosen_result.get("published_at"),
                "candidate_urls": [item["url"] for item in candidates[:max_candidates]],
                "matched_title": chosen_result.get("title") or normalized_title,
                "page_title": chosen_result.get("page_title") or "",
                "relevance_score": float(chosen_result.get("relevance_score") or 0),
            }
        )
        record["success"] = True
        record["cached"] = False
        return record
