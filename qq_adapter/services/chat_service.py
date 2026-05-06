from __future__ import annotations

from .frontend_api_client import frontend_api_client
from .session_mapping_service import session_mapping_service
from ..config import settings
from ..utils.text_format import truncate_text


class QQChatService:
    def _ensure_session(self, *, qq_user_id: str | None) -> str:
        session_id = session_mapping_service.get_session_id(qq_user_id=qq_user_id)
        if session_id:
            return session_id

        created = frontend_api_client.create_session()
        session_id = str(created.get("id") or "")
        if not session_id:
            raise RuntimeError("创建会话成功但未返回 session_id")
        session_mapping_service.bind_session(qq_user_id=qq_user_id, session_id=session_id)
        return session_id

    def chat(self, *, qq_user_id: str | None, message: str) -> str:
        session_id = self._ensure_session(qq_user_id=qq_user_id)
        result = frontend_api_client.analyze_chat(session_id=session_id, message=message)
        return truncate_text(str(result.get("response") or "已收到，但暂无可返回内容。"), settings.reply_max_chars)

    def analyze(self, *, qq_user_id: str | None, message: str) -> str:
        prompt = "\n".join([
            "请围绕以下问题进行深度舆情分析，并明确区分已知事实、待核实信息与分析判断。",
            message,
        ])
        return self.chat(qq_user_id=qq_user_id, message=prompt)


qq_chat_service = QQChatService()
