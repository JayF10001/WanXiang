from __future__ import annotations

from .frontend_api_client import frontend_api_client
from .session_mapping_service import session_mapping_service


class FeishuChatService:
    def _ensure_session(self, *, open_id: str | None, chat_id: str | None) -> str:
        session_id = session_mapping_service.get_session_id(open_id=open_id, chat_id=chat_id)
        if session_id:
            return session_id

        created = frontend_api_client.create_session()
        session_id = str(created.get("id") or "")
        if not session_id:
            raise RuntimeError("创建会话成功但未返回 session_id")
        session_mapping_service.bind_session(open_id=open_id, chat_id=chat_id, session_id=session_id)
        return session_id

    def chat(self, *, open_id: str | None, chat_id: str | None, message: str) -> str:
        session_id = self._ensure_session(open_id=open_id, chat_id=chat_id)
        result = frontend_api_client.analyze_chat(session_id=session_id, message=message)
        return str(result.get("response") or "已收到，但暂无可返回内容。")

    def analyze(self, *, open_id: str | None, chat_id: str | None, message: str) -> str:
        prompt = "\n".join([
            "请围绕以下问题进行深度舆情分析，并明确区分已知事实、待核实信息与分析判断。",
            message,
        ])
        return self.chat(open_id=open_id, chat_id=chat_id, message=prompt)


feishu_chat_service = FeishuChatService()
