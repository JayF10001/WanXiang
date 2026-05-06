from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional


class TimeVerifierService:
    @staticmethod
    def _parse_datetime(value: str | None) -> Optional[datetime]:
        raw = str(value or "").strip()
        if not raw:
            return None

        normalized = (
            raw.replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
            .replace("T", " ")
            .replace("Z", "")
        )
        normalized = re.sub(r"\+\d{2}:\d{2}$", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        patterns = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        )
        for pattern in patterns:
            try:
                return datetime.strptime(normalized, pattern)
            except Exception:
                continue
        return None

    @classmethod
    def verify(
        cls,
        *,
        title: str = "",
        published_at: str = "",
        extracted_text: str = "",
        hotspot_time: str = "",
    ) -> Dict[str, Any]:
        published_dt = cls._parse_datetime(published_at)
        hotspot_dt = cls._parse_datetime(hotspot_time)

        if not published_dt:
            return {
                "is_recent": None,
                "time_gap": None,
                "is_old_news_recirculation": None,
                "reason": "未识别到可靠发布时间，暂无法完成时效性校验。",
            }

        reference_dt = hotspot_dt or datetime.utcnow()
        gap = reference_dt - published_dt
        gap_days = gap.days
        gap_hours = int(gap.total_seconds() // 3600)

        is_recent = gap_days <= 30
        is_old_news_recirculation = False
        if hotspot_dt and gap_days >= 60:
            is_old_news_recirculation = True
        elif hotspot_dt and published_dt.year < hotspot_dt.year:
            is_old_news_recirculation = True

        if is_old_news_recirculation:
            reason = (
                f"当前热点时间与材料发布时间相差约 {gap_days} 天，且发布时间为 {published_dt.strftime('%Y-%m-%d')}，"
                "更像旧闻翻炒或旧材料被重新引用。"
            )
        elif is_recent:
            reason = (
                f"材料发布时间为 {published_dt.strftime('%Y-%m-%d %H:%M') if published_dt.hour or published_dt.minute else published_dt.strftime('%Y-%m-%d')}，"
                f"与参考时间相差约 {max(gap_hours, 0)} 小时，整体仍具备较强时效性。"
            )
        else:
            reason = (
                f"材料发布时间为 {published_dt.strftime('%Y-%m-%d')}，与参考时间相差约 {gap_days} 天，"
                "可作为背景材料，但不宜直接作为当前热点的唯一事实依据。"
            )

        return {
            "is_recent": is_recent,
            "time_gap": {
                "days": gap_days,
                "hours": gap_hours,
            },
            "is_old_news_recirculation": is_old_news_recirculation,
            "reason": reason,
        }
