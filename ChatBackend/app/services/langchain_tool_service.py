from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List

from dotenv import load_dotenv


logger = logging.getLogger(__name__)


def _load_search_env() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    for env_name in (".env.local", ".env.docker", ".env.production", ".env"):
        env_path = repo_root / env_name
        if env_path.exists():
            load_dotenv(env_path, override=False)
            return
    load_dotenv(override=False)


_load_search_env()


class LangChainToolService:
    # 全局搜索超时（秒），防止 LangChain 工具挂起
    SEARCH_TIMEOUT_SECONDS = 8
    DDG_SEARCH_TIMEOUT_SECONDS = 4
    TAVILY_SEARCH_TIMEOUT_SECONDS = 8
    LOAD_URLS_TIMEOUT_SECONDS = 10
    DIAGNOSTIC_VERSION = "search-diagnostics-v1"
    _PROXY_ENV_VARS = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    )
    _ENV_LOCK = threading.Lock()

    """Optional LangChain-based search/loader helpers."""

    @staticmethod
    def _normalize_search_results(raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            if "results" in raw and isinstance(raw["results"], list):
                return [item for item in raw["results"] if isinstance(item, dict)]
            return [raw]
        return []

    @staticmethod
    def _sanitize_error_message(message: str, limit: int = 240) -> str:
        sanitized = " ".join(str(message or "").strip().split())
        sensitive_tokens = ("tvly-", "sk-", "Bearer ", "session=")
        for token in sensitive_tokens:
            if token in sanitized:
                prefix, _, suffix = sanitized.partition(token)
                sanitized = f"{prefix}{token}***{suffix[suffix.find(' ') if ' ' in suffix else len(suffix):]}"
        return sanitized[:limit]

    @staticmethod
    def _classify_error(raw_error: str, exc: BaseException | None = None) -> str:
        message = f"{type(exc).__name__ if exc else ''} {raw_error}".lower()
        if "api key" in message or "configuration_missing" in message or "missing tavily_api_key" in message:
            return "configuration_missing"
        if "proxyerror" in message or "unable to connect to proxy" in message or "proxy" in message:
            return "proxy_error"
        if "nameresolutionerror" in message or "failed to resolve" in message or "name or service not known" in message:
            return "dns_error"
        if "timeout" in message or "timed out" in message:
            return "timeout"
        if "modulenotfounderror" in message or "no module named" in message:
            return "dependency_missing"
        if "connecterror" in message or "connectionerror" in message or "failed to establish a new connection" in message:
            return "connect_error"
        if "connection reset by peer" in message or "connection reset" in message:
            return "connect_error"
        if "permission denied" in message or "operation not permitted" in message:
            return "permission_error"
        return "unknown_error"

    @classmethod
    def _query_hash(cls, query: str) -> str:
        return hashlib.md5(str(query or "").encode("utf-8")).hexdigest()[:10]

    @classmethod
    def _log_provider_result(cls, provider: str, query: str, diagnostic: Dict[str, Any]) -> None:
        payload = {
            "provider": provider,
            "query_hash": cls._query_hash(query),
            "status": diagnostic.get("status"),
            "error_type": diagnostic.get("errorType"),
            "timed_out": diagnostic.get("timedOut"),
            "duration_ms": diagnostic.get("durationMs"),
            "result_count": diagnostic.get("resultCount"),
        }
        if diagnostic.get("status") in {"failed", "skipped"}:
            logger.warning("[SearchProvider] %s", payload)
        else:
            logger.info("[SearchProvider] %s", payload)

    @classmethod
    def _build_diagnostic(
        cls,
        *,
        provider: str,
        status: str,
        results: List[Dict[str, Any]] | None = None,
        duration_ms: int = 0,
        timed_out: bool = False,
        error_type: str = "",
        error_message: str = "",
        loaded_pages: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        return {
            "provider": provider,
            "status": status,
            "results": list(results or []),
            "resultCount": len(results or []),
            "durationMs": int(duration_ms),
            "timedOut": bool(timed_out),
            "errorType": error_type,
            "errorMessage": cls._sanitize_error_message(error_message),
            "loadedPages": list(loaded_pages or []),
        }

    @classmethod
    def _has_proxy_env(cls) -> bool:
        return any(os.environ.get(key) for key in cls._PROXY_ENV_VARS)

    @classmethod
    def _should_trust_env(cls, provider: str) -> bool:
        normalized_provider = "ddg" if provider in {"ddg", "duckduckgo"} else provider
        global_value = (
            os.getenv("WANXIANG_SEARCH_TRUST_ENV")
            or os.getenv("ZHIMO_SEARCH_TRUST_ENV")
            or ""
        ).strip().lower()
        provider_value = (
            os.getenv(f"WANXIANG_{normalized_provider.upper()}_TRUST_ENV")
            or os.getenv(f"ZHIMO_{normalized_provider.upper()}_TRUST_ENV")
            or ""
        ).strip().lower()
        raw = provider_value or global_value
        return raw in {"1", "true", "yes", "on"}

    @classmethod
    @contextmanager
    def _proxy_env_override(cls, provider: str, *, trust_env: bool | None = None) -> Iterator[None]:
        effective_trust_env = cls._should_trust_env(provider) if trust_env is None else bool(trust_env)
        if effective_trust_env:
            yield
            return

        with cls._ENV_LOCK:
            backup = {key: os.environ.get(key) for key in cls._PROXY_ENV_VARS}
            try:
                for key in cls._PROXY_ENV_VARS:
                    os.environ.pop(key, None)
                yield
            finally:
                for key, value in backup.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    @classmethod
    def _run_with_timeout(
        cls,
        *,
        provider: str,
        timeout_seconds: int,
        runner: Callable[[], List[Dict[str, Any]]],
        query: str,
        trust_env: bool | None = None,
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        result_holder: Dict[str, Any] = {"results": []}
        exc_holder: Dict[str, BaseException | None] = {"exc": None}

        def _target() -> None:
            try:
                result_holder["results"] = runner()
            except BaseException as exc:  # pragma: no cover - defensive
                exc_holder["exc"] = exc

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)
        duration_ms = int((time.perf_counter() - start) * 1000)

        if thread.is_alive():
            diagnostic = cls._build_diagnostic(
                provider=provider,
                status="failed",
                duration_ms=duration_ms,
                timed_out=True,
                error_type="timeout",
                error_message=f"{provider} timed out after {timeout_seconds}s",
                results=list(result_holder.get("results") or []),
            )
            cls._log_provider_result(provider, query, diagnostic)
            return diagnostic

        exc = exc_holder.get("exc")
        if exc is not None:
            error_message = f"{type(exc).__name__}: {exc}"
            diagnostic = cls._build_diagnostic(
                provider=provider,
                status="failed",
                duration_ms=duration_ms,
                error_type=cls._classify_error(str(exc), exc),
                error_message=error_message,
            )
            cls._log_provider_result(provider, query, diagnostic)
            return diagnostic

        results = list(result_holder.get("results") or [])
        diagnostic = cls._build_diagnostic(
            provider=provider,
            status="success" if results else "no_results",
            duration_ms=duration_ms,
            results=results,
        )
        cls._log_provider_result(provider, query, diagnostic)
        return diagnostic

    @classmethod
    def _invoke_ddg_search(cls, query: str, max_results: int, *, trust_env: bool | None = None) -> Any:
        with cls._proxy_env_override("ddg", trust_env=trust_env):
            from langchain_community.tools import DuckDuckGoSearchResults

            tool = DuckDuckGoSearchResults(output_format="list", max_results=max_results)
            return tool.invoke(query)

    @classmethod
    def _invoke_tavily_search(cls, query: str, max_results: int, api_key: str, *, trust_env: bool | None = None) -> Any:
        with cls._proxy_env_override("tavily", trust_env=trust_env):
            from langchain_tavily import TavilySearch

            tool = TavilySearch(api_key=api_key, max_results=max_results)
            return tool.invoke(query)

    @classmethod
    def _invoke_web_loader(cls, web_paths: tuple[str, ...], *, trust_env: bool | None = None) -> List[Dict[str, Any]]:
        with cls._proxy_env_override("load_urls", trust_env=trust_env):
            os.environ.setdefault("USER_AGENT", "WanXiangLangChainLoader/1.0")
            from langchain_community.document_loaders import WebBaseLoader

            loader = WebBaseLoader(web_paths=web_paths)
            documents = loader.load()
            results: List[Dict[str, Any]] = []
            for index, document in enumerate(documents):
                metadata = getattr(document, "metadata", {}) or {}
                page_content = str(getattr(document, "page_content", "") or "").strip()
                results.append(
                    {
                        "url": str(metadata.get("source") or (web_paths[index] if index < len(web_paths) else "")),
                        "title": str(metadata.get("title") or "").strip(),
                        "content": page_content,
                    }
                )
            return results

    @classmethod
    def _maybe_retry_with_alternate_proxy_mode(
        cls,
        *,
        provider: str,
        diagnostic: Dict[str, Any],
        query: str,
        timeout_seconds: int,
        runner_factory: Callable[[bool | None], Callable[[], List[Dict[str, Any]]]],
    ) -> Dict[str, Any]:
        if str(diagnostic.get("status") or "") not in {"failed", "skipped"}:
            return diagnostic

        error_type = str(diagnostic.get("errorType") or "")
        default_trust_env = cls._should_trust_env(provider)
        has_proxy_env = cls._has_proxy_env()

        retry_with_trust_env = (not default_trust_env) and has_proxy_env and error_type in {"dns_error", "connect_error", "timeout"}
        retry_without_trust_env = default_trust_env and error_type in {"proxy_error", "permission_error"}

        if not retry_with_trust_env and not retry_without_trust_env:
            return diagnostic

        retry_trust_env = True if retry_with_trust_env else False
        retry_diagnostic = cls._run_with_timeout(
            provider=provider,
            timeout_seconds=timeout_seconds,
            runner=runner_factory(retry_trust_env),
            query=query,
            trust_env=retry_trust_env,
        )
        retry_diagnostic["fallbackAttempted"] = True
        retry_diagnostic["fallbackMode"] = "trust_env" if retry_trust_env else "direct"
        retry_diagnostic["initialStatus"] = diagnostic.get("status")
        retry_diagnostic["initialErrorType"] = diagnostic.get("errorType")
        retry_diagnostic["initialErrorMessage"] = diagnostic.get("errorMessage")
        return retry_diagnostic

    @classmethod
    def search_web_diagnostic(cls, query: str, max_results: int = 5) -> Dict[str, Any]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            diagnostic = cls._build_diagnostic(provider="duckduckgo", status="no_results")
            cls._log_provider_result("duckduckgo", normalized_query, diagnostic)
            return diagnostic

        def _runner_factory(trust_env: bool | None) -> Callable[[], List[Dict[str, Any]]]:
            def _runner() -> List[Dict[str, Any]]:
                raw = cls._invoke_ddg_search(normalized_query, max_results, trust_env=trust_env)
                results: List[Dict[str, Any]] = []
                for item in cls._normalize_search_results(raw):
                    title = str(item.get("title") or "").strip()
                    link = str(item.get("link") or item.get("url") or "").strip()
                    snippet = str(item.get("snippet") or item.get("body") or "").strip()
                    if not title or not link:
                        continue
                    results.append(
                        {
                            "title": title,
                            "url": link,
                            "snippet": snippet,
                            "provider": "duckduckgo",
                        }
                    )
                    if len(results) >= max_results:
                        break
                return results

            return _runner

        diagnostic = cls._run_with_timeout(
            provider="duckduckgo",
            timeout_seconds=cls.DDG_SEARCH_TIMEOUT_SECONDS,
            runner=_runner_factory(None),
            query=normalized_query,
        )
        diagnostic = cls._maybe_retry_with_alternate_proxy_mode(
            provider="duckduckgo",
            diagnostic=diagnostic,
            query=normalized_query,
            timeout_seconds=cls.DDG_SEARCH_TIMEOUT_SECONDS,
            runner_factory=_runner_factory,
        )
        return diagnostic

    @classmethod
    def search_web(cls, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        return list(cls.search_web_diagnostic(query, max_results=max_results).get("results") or [])

    @classmethod
    def search_web_tavily_diagnostic(cls, query: str, max_results: int = 5) -> Dict[str, Any]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            diagnostic = cls._build_diagnostic(provider="tavily", status="no_results")
            cls._log_provider_result("tavily", normalized_query, diagnostic)
            return diagnostic

        api_key = os.getenv("TAVILY_API_KEY", "").strip()
        if not api_key:
            diagnostic = cls._build_diagnostic(
                provider="tavily",
                status="skipped",
                error_type="configuration_missing",
                error_message="TAVILY_API_KEY is not configured",
            )
            cls._log_provider_result("tavily", normalized_query, diagnostic)
            return diagnostic

        def _runner_factory(trust_env: bool | None) -> Callable[[], List[Dict[str, Any]]]:
            def _runner() -> List[Dict[str, Any]]:
                raw = cls._invoke_tavily_search(normalized_query, max_results, api_key=api_key, trust_env=trust_env)
                if isinstance(raw, dict) and raw.get("error"):
                    raise RuntimeError(str(raw.get("error")))

                results: List[Dict[str, Any]] = []
                for item in cls._normalize_search_results(raw):
                    title = str(item.get("title") or "").strip()
                    url = str(item.get("url") or "").strip()
                    snippet = str(item.get("content") or item.get("snippet") or "").strip()
                    if not title or not url:
                        continue
                    results.append(
                        {
                            "title": title,
                            "url": url,
                            "snippet": snippet,
                            "provider": "tavily",
                        }
                    )
                    if len(results) >= max_results:
                        break
                return results

            return _runner

        diagnostic = cls._run_with_timeout(
            provider="tavily",
            timeout_seconds=cls.TAVILY_SEARCH_TIMEOUT_SECONDS,
            runner=_runner_factory(None),
            query=normalized_query,
        )
        diagnostic = cls._maybe_retry_with_alternate_proxy_mode(
            provider="tavily",
            diagnostic=diagnostic,
            query=normalized_query,
            timeout_seconds=cls.TAVILY_SEARCH_TIMEOUT_SECONDS,
            runner_factory=_runner_factory,
        )
        return diagnostic

    @classmethod
    def search_web_tavily(cls, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        return list(cls.search_web_tavily_diagnostic(query, max_results=max_results).get("results") or [])

    @classmethod
    def load_urls_diagnostic(cls, urls: List[str]) -> Dict[str, Any]:
        web_paths = tuple(str(item or "").strip() for item in urls if str(item or "").strip())
        if not web_paths:
            diagnostic = cls._build_diagnostic(provider="load_urls", status="no_results")
            cls._log_provider_result("load_urls", "", diagnostic)
            return diagnostic

        def _runner_factory(trust_env: bool | None) -> Callable[[], List[Dict[str, Any]]]:
            def _runner() -> List[Dict[str, Any]]:
                return cls._invoke_web_loader(web_paths, trust_env=trust_env)

            return _runner

        diagnostic = cls._run_with_timeout(
            provider="load_urls",
            timeout_seconds=cls.LOAD_URLS_TIMEOUT_SECONDS,
            runner=_runner_factory(None),
            query="|".join(web_paths[:3]),
        )
        diagnostic = cls._maybe_retry_with_alternate_proxy_mode(
            provider="load_urls",
            diagnostic=diagnostic,
            query="|".join(web_paths[:3]),
            timeout_seconds=cls.LOAD_URLS_TIMEOUT_SECONDS,
            runner_factory=_runner_factory,
        )
        diagnostic["loadedPages"] = [
            {
                "url": str(item.get("url") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "contentPreview": str(item.get("content") or "")[:500],
                "errorType": "",
                "errorMessage": "",
            }
            for item in diagnostic.get("results") or []
        ]
        return diagnostic

    @classmethod
    def load_urls(cls, urls: List[str]) -> List[Dict[str, Any]]:
        return list(cls.load_urls_diagnostic(urls).get("results") or [])
