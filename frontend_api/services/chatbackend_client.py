from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Union
import requests

from ..core.config import settings


class ChatBackendClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
        with requests.Session() as session:
            # Backend-to-backend local calls should not inherit machine proxy settings.
            session.trust_env = False
            return session.request(method=method, url=url, **kwargs)

    def request_json(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        session_cookie: Optional[Union[str, Dict[str, str]]] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[requests.Response, Dict[str, Any]]:
        cookies = {}
        if session_cookie:
            if isinstance(session_cookie, dict):
                cookies.update(session_cookie)
            else:
                cookies[settings.chatbackend_session_cookie_name] = session_cookie

        response = self._request(
            method=method,
            url=f"{self.base_url}{path}",
            json=json_data,
            cookies=cookies,
            timeout=timeout or settings.chatbackend_request_timeout,
            allow_redirects=False,
        )
        try:
            payload = response.json()
        except Exception:
            payload = {}
        return response, payload

    def request_stream(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        session_cookie: Optional[Union[str, Dict[str, str]]] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        cookies = {}
        if session_cookie:
            if isinstance(session_cookie, dict):
                cookies.update(session_cookie)
            else:
                cookies[settings.chatbackend_session_cookie_name] = session_cookie

        return self._request(
            method=method,
            url=f"{self.base_url}{path}",
            json=json_data,
            cookies=cookies,
            timeout=timeout or settings.chatbackend_request_timeout,
            allow_redirects=False,
            stream=True,
        )

    def request_multipart(
        self,
        method: str,
        path: str,
        *,
        files: Dict[str, Any],
        data: Optional[Dict[str, Any]] = None,
        session_cookie: Optional[Union[str, Dict[str, str]]] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[requests.Response, Dict[str, Any]]:
        cookies = {}
        if session_cookie:
            if isinstance(session_cookie, dict):
                cookies.update(session_cookie)
            else:
                cookies[settings.chatbackend_session_cookie_name] = session_cookie

        response = self._request(
            method=method,
            url=f"{self.base_url}{path}",
            files=files,
            data=data or {},
            cookies=cookies,
            timeout=timeout or settings.chatbackend_request_timeout,
            allow_redirects=False,
        )
        try:
            payload = response.json()
        except Exception:
            payload = {}
        return response, payload

    @staticmethod
    def extract_session_cookie(response: requests.Response) -> Optional[str]:
        return response.cookies.get(settings.chatbackend_session_cookie_name)

    @staticmethod
    def extract_session_cookies(response: requests.Response) -> Dict[str, str]:
        cookies = response.cookies.get_dict()
        return {str(key): str(value) for key, value in cookies.items() if value}


client = ChatBackendClient(settings.chatbackend_base_url)
