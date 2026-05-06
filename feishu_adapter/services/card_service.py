from __future__ import annotations


class FeishuCardService:
    def handle(self, payload: dict) -> dict:
        return {
            "success": True,
            "message": "一期版本暂未启用复杂卡片交互",
            "payload": payload,
        }


feishu_card_service = FeishuCardService()
