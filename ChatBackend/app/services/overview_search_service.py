from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any, Dict, List

from .crawler_service import CrawlerService
from .langchain_tool_service import LangChainToolService
from .source_verifier_service import SourceVerifierService
from .time_verifier_service import TimeVerifierService


# Query keywords that indicate the content is completely unrelated to user intent
_NOISE_TITLE_PATTERNS = (
    "蓝桥杯", "软件赛", "程序设计", "java", "python", "c/c++",
    "获奖名单", "赛区", "一等奖", "二等奖", "三等奖",
)

logger = logging.getLogger(__name__)


class OverviewSearchService:
    @staticmethod
    def _query_hash(query: str) -> str:
        return hashlib.md5(str(query or "").encode("utf-8")).hexdigest()[:10]

    @staticmethod
    def _public_provider_diagnostic(
        diagnostic: Dict[str, Any],
        *,
        include_loaded_pages: bool = False,
    ) -> Dict[str, Any]:
        public = {
            "provider": str(diagnostic.get("provider") or ""),
            "status": str(diagnostic.get("status") or ""),
            "errorType": str(diagnostic.get("errorType") or ""),
            "errorMessage": str(diagnostic.get("errorMessage") or ""),
            "durationMs": int(diagnostic.get("durationMs") or 0),
            "resultCount": int(diagnostic.get("resultCount") or 0),
            "timedOut": bool(diagnostic.get("timedOut")),
        }
        if include_loaded_pages:
            public["loadedPages"] = [
                {
                    "url": str(item.get("url") or ""),
                    "title": str(item.get("title") or ""),
                    "contentPreview": str(item.get("contentPreview") or ""),
                    "errorType": str(item.get("errorType") or ""),
                    "errorMessage": str(item.get("errorMessage") or ""),
                }
                for item in (diagnostic.get("loadedPages") or [])
            ]
        return public

    @staticmethod
    def _summarize_failure(diagnostics: List[Dict[str, Any]]) -> str:
        failed = [
            item
            for item in diagnostics
            if str(item.get("status") or "") == "failed"
            or (
                str(item.get("status") or "") == "skipped"
                and str(item.get("errorType") or "").strip()
            )
        ]
        if not failed:
            return ""
        parts = []
        for item in failed[:3]:
            provider = str(item.get("provider") or "unknown")
            error_type = str(item.get("errorType") or "unknown_error")
            parts.append(f"{provider}:{error_type}")
        return "；".join(parts)

    @staticmethod
    def _run_task_with_timeout(timeout_seconds: int, task):
        import threading

        result_holder = {"value": None}
        exc_holder = {"error": None}

        def _target():
            try:
                result_holder["value"] = task()
            except Exception as exc:  # pragma: no cover - defensive
                exc_holder["error"] = exc

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)
        if thread.is_alive():
            return {"timed_out": True, "result": None, "error": None}
        return {"timed_out": False, "result": result_holder["value"], "error": exc_holder["error"]}

    @staticmethod
    def _dedupe_candidates(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        best_by_key: Dict[tuple[str, str], Dict[str, Any]] = {}
        ordered_keys: List[tuple[str, str]] = []
        for item in items:
            key = (
                str(item.get("final_url") or item.get("url") or "").strip().lower(),
                str(item.get("page_title") or item.get("title") or "").strip().lower(),
            )
            existing = best_by_key.get(key)
            if existing is None:
                best_by_key[key] = item
                ordered_keys.append(key)
                continue

            current_score = float(item.get("relevance_score") or 0)
            existing_score = float(existing.get("relevance_score") or 0)
            if current_score > existing_score:
                best_by_key[key] = item

        return [best_by_key[key] for key in ordered_keys]

    @staticmethod
    def _normalize_search_query(query: str) -> str:
        text = str(query or "").strip()
        if not text:
            return ""

        title_line = next((line.strip() for line in text.splitlines() if line.strip().startswith("标题：")), "")
        if title_line:
            _, _, value = title_line.partition("：")
            return value.strip() or text

        patterns = (
            r"^帮我分析这个热点[:：]\s*(.+)$",
            r"^请帮我分析这个热点[:：]\s*(.+)$",
            r"^帮我分析[:：]\s*(.+)$",
            r"^请帮我分析[:：]\s*(.+)$",
            r"^标题[:：]\s*(.+)$",
        )
        for pattern in patterns:
            matched = re.match(pattern, text)
            if matched and matched.group(1):
                return matched.group(1).strip()

        return text

    @classmethod
    def _score_query_content_relevance(
        cls,
        query: str,
        title: str = "",
        content: str = "",
    ) -> float:
        """Check if query keywords appear in title/content. Returns 0-1 score."""
        query_lower = query.lower()
        title_lower = title.lower()
        content_lower = content.lower()

        # Extract meaningful Chinese words/phrases (2+ chars) and English words from query
        query_terms = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', query_lower)
        if not query_terms:
            # Fallback: single characters
            query_terms = list(query_lower)
        elif len(query_terms) == 1 and len(query_terms[0]) > 6:
            # Single long phrase - split into individual Chinese characters for matching
            # Only use chars that are actual Chinese characters or meaningful units
            chars = list(query_lower)
            query_terms = [c for c in chars if '\u4e00' <= c <= '\u9fff']

        if not query_terms:
            return 0.5  # Neutral if no terms extracted

        matched = 0
        for term in query_terms:
            if term in title_lower or term in content_lower:
                matched += 1

        return matched / max(len(query_terms), 1)

    @classmethod
    def _filter_low_relevance_items(
        cls,
        items: List[Dict[str, Any]],
        query: str,
    ) -> List[Dict[str, Any]]:
        """Drop/strongly downrank items whose title or content has zero query keyword overlap."""
        filtered: List[Dict[str, Any]] = []
        for item in items:
            title = str(item.get("title") or "")
            content = str(item.get("content_excerpt") or item.get("summary") or item.get("content") or "")
            keyword_score = cls._score_query_content_relevance(query, title, content)

            content_lower = content.lower()
            title_lower = title.lower()
            is_noise = any(
                pattern in title_lower or pattern in content_lower
                for pattern in _NOISE_TITLE_PATTERNS
            )

            current_score = float(item.get("relevance_score") or 0)

            if is_noise:
                # Knowledge base items with noise patterns are discarded directly
                # (user specifically requested this for RAG noise)
                if item.get("source_type") == "knowledge_chunk":
                    continue
                # Search engine results are downranked but kept
                item["relevance_score"] = current_score * 0.5
            elif keyword_score == 0:
                # No keyword overlap - discard
                continue

            filtered.append(item)
        return filtered

    @classmethod
    def search(
        cls,
        *,
        query: str,
        source_url: str = "",
        platform_hint: str = "",
        session_id: str = "",
        user_id: str = "",
        max_results: int = 10,
        include_loaded_pages: bool = False,
    ) -> Dict[str, Any]:
        import sys
        print(f"[OverviewSearch] query={str(query)[:40]} user_id={str(user_id)[:16]} session_id={str(session_id)[:16]}", file=sys.stderr)
        sys.stderr.flush()
        normalized_query = cls._normalize_search_query(query)
        if not normalized_query:
            return {
                "success": False,
                "query": "",
                "summary": "缺少检索关键词",
                "items": [],
                "providerDiagnostics": [],
                "selectedProviders": [],
                "partialFailure": False,
                "totalDurationMs": 0,
            }

        started_at = time.perf_counter()

        crawler_items: List[Dict[str, Any]] = []
        duckduckgo_items: List[Dict[str, Any]] = []
        tavily_items: List[Dict[str, Any]] = []
        provider_diagnostics: List[Dict[str, Any]] = []
        loaded_pages: List[Dict[str, Any]] = []

        def _collect_search_provider(search_diagnostic: Dict[str, Any], provider_name: str, provider_score: float, item_bucket: List[Dict[str, Any]]):
            candidates = list(search_diagnostic.get("results") or [])
            prefetched_pages: Dict[str, Dict[str, Any]] = {}
            if include_loaded_pages:
                load_diagnostic = LangChainToolService.load_urls_diagnostic(
                    [str(item.get("url") or "").strip() for item in candidates]
                )
                prefetched_pages = {
                    str(item.get("url") or "").strip(): item
                    for item in (load_diagnostic.get("results") or [])
                }
                loaded_pages.extend(
                    [
                        {"provider": provider_name, **item}
                        for item in (load_diagnostic.get("loadedPages") or [])
                    ]
                )
            else:
                load_diagnostic = {
                    "provider": "load_urls",
                    "status": "skipped",
                    "errorType": "",
                    "errorMessage": "loaded pages disabled unless includeLoadedPages=true",
                    "durationMs": 0,
                    "resultCount": 0,
                    "timedOut": False,
                    "loadedPages": [],
                }
            provider_diagnostics.append(
                cls._public_provider_diagnostic(search_diagnostic, include_loaded_pages=False)
            )
            provider_diagnostics.append(
                cls._public_provider_diagnostic(
                    {**load_diagnostic, "provider": f"{provider_name}_load_urls"},
                    include_loaded_pages=include_loaded_pages,
                )
            )
            for candidate in candidates:
                url = str(candidate.get("url") or "").strip()
                if not url:
                    continue
                loaded = prefetched_pages.get(url) or {}
                excerpt = str(loaded.get("content") or candidate.get("snippet") or "").strip()
                credibility = SourceVerifierService.verify(
                    url=url,
                    source_name=str(candidate.get("provider") or provider_name),
                    platform=platform_hint or "",
                )
                item_bucket.append(
                    {
                        "title": str(loaded.get("title") or candidate.get("title") or normalized_query),
                        "url": url,
                        "source_name": str(candidate.get("provider") or provider_name),
                        "platform": platform_hint or provider_name,
                        "published_at": "",
                        "summary": excerpt[:220],
                        "content_excerpt": excerpt[:800],
                        "credibility": credibility.get("credibility_level", "medium"),
                        "source_type": credibility.get("source_type", "general_webpage"),
                        "credibility_reason": credibility.get("reason", ""),
                        "time_reason": "",
                        "relevance_score": provider_score,
                    }
                )

        try:
            _collect_search_provider(
                LangChainToolService.search_web_tavily_diagnostic(normalized_query, max_results=max_results),
                "tavily",
                0.55,
                tavily_items,
            )
        except Exception as exc:
            print(f"[OverviewSearch] Tavily search failed: {exc}", file=sys.stderr)
            provider_diagnostics.append(
                cls._public_provider_diagnostic(
                    {
                        "provider": "tavily",
                        "status": "failed",
                        "errorType": type(exc).__name__,
                        "errorMessage": str(exc),
                        "durationMs": 0,
                        "resultCount": 0,
                        "timedOut": False,
                    },
                    include_loaded_pages=include_loaded_pages,
                )
            )

        try:
            _collect_search_provider(
                LangChainToolService.search_web_diagnostic(normalized_query, max_results=max_results),
                "duckduckgo",
                0.5,
                duckduckgo_items,
            )
        except Exception as exc:
            print(f"[OverviewSearch] DuckDuckGo search failed: {exc}", file=sys.stderr)
            provider_diagnostics.append(
                cls._public_provider_diagnostic(
                    {
                        "provider": "duckduckgo",
                        "status": "failed",
                        "errorType": type(exc).__name__,
                        "errorMessage": str(exc),
                        "durationMs": 0,
                        "resultCount": 0,
                        "timedOut": False,
                    },
                    include_loaded_pages=include_loaded_pages,
                )
            )

        should_run_crawler = bool(source_url or platform_hint) or (len(duckduckgo_items) + len(tavily_items) < 3)
        if should_run_crawler:
            crawler_started_at = time.perf_counter()
            crawler_run = cls._run_task_with_timeout(
                10,
                lambda: CrawlerService.search_news_overview(
                    title=normalized_query,
                    source_url=source_url or "",
                    platform_hint=platform_hint or "",
                    session_id=session_id or "",
                    user_id=user_id or "",
                    max_results=max(3, min(int(max_results or 10), 15)),
                ),
            )
            if crawler_run["timed_out"]:
                provider_diagnostics.append(
                    cls._public_provider_diagnostic(
                        {
                            "provider": "crawler",
                            "status": "failed",
                            "errorType": "timeout",
                            "errorMessage": "crawler timed out after 10s",
                            "durationMs": int((time.perf_counter() - crawler_started_at) * 1000),
                            "resultCount": 0,
                            "timedOut": True,
                        },
                        include_loaded_pages=include_loaded_pages,
                    )
                )
            elif crawler_run["error"] is not None:
                exc = crawler_run["error"]
                print(f"[OverviewSearch] CrawlerService failed: {exc}", file=sys.stderr)
                provider_diagnostics.append(
                    cls._public_provider_diagnostic(
                        {
                            "provider": "crawler",
                            "status": "failed",
                            "errorType": type(exc).__name__,
                            "errorMessage": str(exc),
                            "durationMs": int((time.perf_counter() - crawler_started_at) * 1000),
                            "resultCount": 0,
                            "timedOut": False,
                        },
                        include_loaded_pages=include_loaded_pages,
                    )
                )
            else:
                crawler_result = crawler_run["result"] or {}
                items = list(crawler_result.get("items") or [])
                crawler_items.extend(items)
                provider_diagnostics.append(
                    cls._public_provider_diagnostic(
                        {
                            "provider": "crawler",
                            "status": "success" if items else "no_results",
                            "errorType": "",
                            "errorMessage": "",
                            "durationMs": int((time.perf_counter() - crawler_started_at) * 1000),
                            "resultCount": len(items),
                            "timedOut": False,
                        },
                        include_loaded_pages=include_loaded_pages,
                    )
                )

        # Collect all items from completed threads
        items = tavily_items + duckduckgo_items + crawler_items

        # Apply relevance filtering: downrank items that don't contain query keywords
        items = cls._filter_low_relevance_items(items, normalized_query)

        # Integrate RAG knowledge base retrieval for better semantic matching
        try:
            rag_started_at = time.perf_counter()
            from rag_service.retrievers.hybrid_retriever import HybridRetriever
            rag_candidates = HybridRetriever.retrieve(
                query=normalized_query,
                kb_id=None,  # search all user knowledge bases
                user_id=user_id or "",
                source_url=source_url or "",
                platform_hint=platform_hint or "",
                session_id=session_id or "",
                include_realtime=False,  # already covered by CrawlerService
                include_internal=True,
                top_k=max(3, min(int(max_results or 10), 8)),
            )
            provider_diagnostics.append(
                cls._public_provider_diagnostic(
                    {
                        "provider": "knowledge_base",
                        "status": "success" if rag_candidates else "no_results",
                        "errorType": "",
                        "errorMessage": "",
                        "durationMs": int((time.perf_counter() - rag_started_at) * 1000),
                        "resultCount": len(rag_candidates or []),
                        "timedOut": False,
                    },
                    include_loaded_pages=include_loaded_pages,
                )
            )
            for rag_item in rag_candidates:
                rag_url = str(rag_item.get("url") or "").strip()
                rag_title = str(rag_item.get("title") or "").strip()
                if not rag_url and not rag_title:
                    continue
                items.append(
                    {
                        "title": rag_title or normalized_query,
                        "url": rag_url,
                        "source_name": "知识库",
                        "platform": platform_hint or "knowledge_base",
                        "published_at": str(rag_item.get("publishedAt") or ""),
                        "summary": str(rag_item.get("summary") or "")[:220],
                        "content_excerpt": str(rag_item.get("content") or "")[:800],
                        "credibility": str(rag_item.get("credibility") or "medium"),
                        "source_type": "knowledge_chunk",
                        "credibility_reason": f"知识库片段，关键词{int(rag_item.get('keywordScore', 0) * 100)}%，向量{int(rag_item.get('vectorScore', 0) * 100)}%",
                        "time_reason": "",
                        "relevance_score": float(rag_item.get("score") or 0.5),
                    }
                )
        except Exception as exc:
            provider_diagnostics.append(
                cls._public_provider_diagnostic(
                    {
                        "provider": "knowledge_base",
                        "status": "failed",
                        "errorType": type(exc).__name__,
                        "errorMessage": str(exc),
                        "durationMs": 0,
                        "resultCount": 0,
                        "timedOut": False,
                    },
                    include_loaded_pages=include_loaded_pages,
                )
            )

        deduped = cls._dedupe_candidates(items)
        deduped.sort(key=lambda item: float(item.get("relevance_score") or 0), reverse=True)
        selected = deduped[:max_results]
        total_duration_ms = int((time.perf_counter() - started_at) * 1000)
        has_successful_provider = any(
            str(item.get("status") or "") in {"success", "no_results"}
            for item in provider_diagnostics
        )
        partial_failure = any(
            str(item.get("status") or "") == "failed"
            or (
                str(item.get("status") or "") == "skipped"
                and str(item.get("errorType") or "").strip()
            )
            for item in provider_diagnostics
        ) and has_successful_provider
        selected_providers = [str(item.get("provider") or "") for item in provider_diagnostics if item.get("provider")]
        failure_summary = cls._summarize_failure(provider_diagnostics)

        logger.info(
            "[OverviewSearch] query_hash=%s total_duration_ms=%s partial_failure=%s selected=%s providers=%s",
            cls._query_hash(normalized_query),
            total_duration_ms,
            partial_failure,
            len(selected),
            selected_providers,
        )

        if not selected:
            if provider_diagnostics and all(
                str(item.get("status") or "") in {"failed", "skipped"}
                for item in provider_diagnostics
            ):
                summary = f"当前搜索提供方调用失败，未能获取【{normalized_query}】的可验证结果。"
                if failure_summary:
                    summary = f"{summary} 失败概览：{failure_summary}。"
            else:
                summary = f"当前未检索到与【{normalized_query}】直接相关的可验证结果。"
            return {
                "success": False,
                "query": normalized_query,
                "summary": summary,
                "items": [],
                "providerDiagnostics": provider_diagnostics,
                "selectedProviders": selected_providers,
                "partialFailure": partial_failure,
                "totalDurationMs": total_duration_ms,
                "debugVersion": LangChainToolService.DIAGNOSTIC_VERSION,
                **({"loadedPages": loaded_pages} if include_loaded_pages else {}),
            }

        for item in selected:
            if not item.get("credibility"):
                credibility = SourceVerifierService.verify(
                    url=str(item.get("url") or ""),
                    source_name=str(item.get("source_name") or ""),
                    platform=str(item.get("platform") or ""),
                )
                item["credibility"] = credibility.get("credibility_level", "medium")
                item["source_type"] = credibility.get("source_type", "general_webpage")
                item["credibility_reason"] = credibility.get("reason", "")
            if not item.get("time_reason"):
                time_check = TimeVerifierService.verify(
                    title=str(item.get("title") or normalized_query),
                    published_at=str(item.get("published_at") or ""),
                    extracted_text=str(item.get("content_excerpt") or item.get("summary") or ""),
                    hotspot_time="",
                )
                item["time_reason"] = str(time_check.get("reason") or "")

        top_titles = "；".join(str(item.get("title") or "") for item in selected[:3] if item.get("title"))
        summary = (
            f"已检索到 {len(selected)} 条与【{normalized_query}】相关的结果。"
            f"优先结果包括：{top_titles or '暂无标题'}。"
            "建议先核对高可信来源，再展开背景、传播现状与下一步分析。"
        )
        if partial_failure and failure_summary:
            summary = f"{summary} 部分搜索源异常：{failure_summary}。"
        return {
            "success": True,
            "query": normalized_query,
            "summary": summary,
            "items": selected,
            "providerDiagnostics": provider_diagnostics,
            "selectedProviders": selected_providers,
            "partialFailure": partial_failure,
            "totalDurationMs": total_duration_ms,
            "debugVersion": LangChainToolService.DIAGNOSTIC_VERSION,
            **({"loadedPages": loaded_pages} if include_loaded_pages else {}),
        }


# Debug: monkey-patch to log every search call
_original_search = OverviewSearchService.search

import logging
_logger = logging.getLogger(__name__)

@classmethod
def _logged_search(cls, *, query, source_url="", platform_hint="", session_id="", user_id="", max_results=10, include_loaded_pages=False):
    import sys
    import os
    # Print to stderr so it's always visible
    print(f"[DEBUG search] query={query[:30]}..., user_id={user_id[:20] if user_id else 'None'}", file=sys.stderr)
    sys.stderr.flush()
    return _original_search(
        query=query,
        source_url=source_url,
        platform_hint=platform_hint,
        session_id=session_id,
        user_id=user_id,
        max_results=max_results,
        include_loaded_pages=include_loaded_pages,
    )

OverviewSearchService.search = _logged_search
