"""知识库时间戳服务 - Knowledge Base Timestamp Service

检查知识库内容的新鲜度，判断是否需要触发聚合搜索。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ChatBackend.app.extensions import db


@dataclass(frozen=True)
class TimestampCheckResult:
    """时间戳检查结果"""
    is_stale: bool  # 是否陈旧（> 30天）
    age_days: int  # 年龄（天）
    latest_update: Optional[datetime]  # 最新更新时间
    kb_has_content: bool  # 知识库是否有内容
    should_trigger_search: bool  # 是否应触发搜索


class KnowledgeTimestampService:
    """知识库时间戳比对服务"""

    STALE_THRESHOLD_DAYS: int = 30  # 30天阈值

    @classmethod
    def check_knowledge_freshness(
        cls,
        kb_id: Optional[str] = None,
        user_id: str = "",
    ) -> TimestampCheckResult:
        """检查知识库内容新鲜度

        Args:
            kb_id: 知识库ID，如果为 None 则检查用户所有知识库
            user_id: 用户ID

        Returns:
            TimestampCheckResult: 包含新鲜度评估结果
        """
        now = datetime.utcnow()

        # 构建查询条件
        query = {}
        if kb_id:
            query["kb_id"] = str(kb_id)
        if user_id:
            query["owner_user_id"] = str(user_id)

        try:
            # 查找该知识库/用户最新的 indexed_at 时间戳
            latest_doc = db.knowledge_files.find_one(
                query,
                sort=[("indexed_at", -1)]
            )

            if not latest_doc or not latest_doc.get("indexed_at"):
                # 没有索引记录，返回陈旧
                return TimestampCheckResult(
                    is_stale=True,
                    age_days=999,
                    latest_update=None,
                    kb_has_content=False,
                    should_trigger_search=True,
                )

            latest_indexed_at = latest_doc.get("indexed_at")
            if isinstance(latest_indexed_at, str):
                latest_indexed_at = datetime.fromisoformat(latest_indexed_at)

            age_days = (now - latest_indexed_at).days
            is_stale = age_days > cls.STALE_THRESHOLD_DAYS

            return TimestampCheckResult(
                is_stale=is_stale,
                age_days=age_days,
                latest_update=latest_indexed_at,
                kb_has_content=True,
                should_trigger_search=is_stale,
            )

        except Exception:
            # 出错时默认触发搜索
            return TimestampCheckResult(
                is_stale=True,
                age_days=999,
                latest_update=None,
                kb_has_content=False,
                should_trigger_search=True,
            )

    @classmethod
    def check_chunk_freshness(
        cls,
        kb_id: Optional[str] = None,
        user_id: str = "",
    ) -> TimestampCheckResult:
        """检查知识块(chunk)的新鲜度

        用于更细粒度的内容新鲜度检查。
        如果最新 chunk 的更新时间也超过阈值，说明整个知识库内容陈旧。
        """
        query = {"index_status": "ready"}
        if kb_id:
            query["kb_id"] = str(kb_id)
        if user_id:
            query["owner_user_id"] = str(user_id)

        try:
            latest_chunk = db.knowledge_chunks.find_one(
                query,
                sort=[("updated_at", -1)]
            )

            if not latest_chunk or not latest_chunk.get("updated_at"):
                return TimestampCheckResult(
                    is_stale=True,
                    age_days=999,
                    latest_update=None,
                    kb_has_content=False,
                    should_trigger_search=True,
                )

            latest_updated = latest_chunk.get("updated_at")
            if isinstance(latest_updated, str):
                latest_updated = datetime.fromisoformat(latest_updated)

            age_days = (datetime.utcnow() - latest_updated).days
            is_stale = age_days > cls.STALE_THRESHOLD_DAYS

            return TimestampCheckResult(
                is_stale=is_stale,
                age_days=age_days,
                latest_update=latest_updated,
                kb_has_content=True,
                should_trigger_search=is_stale,
            )

        except Exception:
            return TimestampCheckResult(
                is_stale=True,
                age_days=999,
                latest_update=None,
                kb_has_content=False,
                should_trigger_search=True,
            )

    @classmethod
    def get_knowledge_stats(
        cls,
        kb_id: Optional[str] = None,
        user_id: str = "",
    ) -> dict:
        """获取知识库的统计信息

        Returns:
            dict: 包含 file_count, chunk_count, latest_indexed_at 等
        """
        query = {}
        if kb_id:
            query["kb_id"] = str(kb_id)
        if user_id:
            query["owner_user_id"] = str(user_id)

        try:
            file_count = db.knowledge_files.count_documents(query)
            chunk_query = dict(query)
            chunk_query["index_status"] = "ready"
            chunk_count = db.knowledge_chunks.count_documents(chunk_query)

            latest_doc = db.knowledge_files.find_one(
                query,
                sort=[("indexed_at", -1)]
            )
            latest_indexed_at = None
            if latest_doc and latest_doc.get("indexed_at"):
                latest_indexed_at = latest_doc.get("indexed_at")
                if isinstance(latest_indexed_at, str):
                    latest_indexed_at = datetime.fromisoformat(latest_indexed_at)

            return {
                "file_count": file_count,
                "chunk_count": chunk_count,
                "latest_indexed_at": latest_indexed_at,
                "has_content": file_count > 0 or chunk_count > 0,
            }
        except Exception:
            return {
                "file_count": 0,
                "chunk_count": 0,
                "latest_indexed_at": None,
                "has_content": False,
            }
