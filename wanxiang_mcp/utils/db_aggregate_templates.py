"""预定义的 MongoDB 聚合查询模板，供 chat.db_aggregate 工具调用。

每个模板包含：
- description: 模板功能描述
- collection: 目标集合名
- pipeline_template: 聚合管道（支持 {{start_date}}、{{end_date}}、{{limit}} 占位符）
"""

from typing import Dict, List, Any

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "hot_topics_by_platform": {
        "description": "按平台统计热门话题数量和平均参与度",
        "collection": "transformed_news",
        "pipeline_template": [
            {
                "$match": {
                    "analyzed_at": {"$gte": "{{start_date}}"},
                    "participants": {"$exists": True, "$ne": None}
                }
            },
            {
                "$group": {
                    "_id": "$platform",
                    "count": {"$sum": 1},
                    "avg_participants": {"$avg": "$participants"},
                    "max_participants": {"$max": "$participants"}
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
    },
    "news_trend_daily": {
        "description": "按天统计新闻数量趋势",
        "collection": "raw_news",
        "pipeline_template": [
            {
                "$match": {
                    "collected_at": {"$gte": {"$date": "{{start_date}}"}}
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$collected_at"
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]
    },
    "top_participants_news": {
        "description": "获取参与度最高的话题",
        "collection": "transformed_news",
        "pipeline_template": [
            {
                "$match": {
                    "analyzed_at": {"$gte": "{{start_date}}"},
                    "participants": {"$exists": True, "$ne": None}
                }
            },
            {"$sort": {"participants": -1}},
            {"$limit": "{{limit}}"},
            {
                "$project": {
                    "title": 1,
                    "participants": 1,
                    "analyzed_at": 1,
                    "platform": 1,
                    "_id": 0
                }
            }
        ]
    },
    "session_message_stats": {
        "description": "统计会话消息数量",
        "collection": "chat_sessions",
        "pipeline_template": [
            {
                "$match": {
                    "created_at": {"$gte": {"$date": "{{start_date}}"}}
                }
            },
            {
                "$project": {
                    "title": 1,
                    "message_count": {"$size": "$messages"},
                    "created_at": 1,
                    "updated_at": 1
                }
            },
            {"$sort": {"message_count": -1}},
            {"$limit": "{{limit}}"}
        ]
    },
    "token_usage_by_model": {
        "description": "按模型统计 token 消耗",
        "collection": "token_usage",
        "pipeline_template": [
            {
                "$match": {
                    "timestamp": {"$gte": {"$date": "{{start_date}}"}}
                }
            },
            {
                "$group": {
                    "_id": "$model",
                    "total_tokens": {"$sum": "$total_tokens"},
                    "total_prompt_tokens": {"$sum": "$prompt_tokens"},
                    "total_completion_tokens": {"$sum": "$completion_tokens"},
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"total_tokens": -1}}
        ]
    },
    "queue_status_summary": {
        "description": "分析队列状态汇总",
        "collection": "analysis_queue",
        "pipeline_template": [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "latest_queued": {"$max": "$updated_at"},
                    "earliest_queued": {"$min": "$created_at"}
                }
            },
            {"$sort": {"count": -1}}
        ]
    },
    "news_source_distribution": {
        "description": "新闻来源分布统计",
        "collection": "raw_news",
        "pipeline_template": [
            {
                "$match": {
                    "collected_at": {"$gte": {"$date": "{{start_date}}"}}
                }
            },
            {
                "$group": {
                    "_id": "$source",
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 20}
        ]
    },
    "analysis_success_rate": {
        "description": "分析任务成功率统计",
        "collection": "analysis_queue",
        "pipeline_template": [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"count": -1}}
        ]
    }
}

# 允许的集合名单（安全白名单）
ALLOWED_COLLECTIONS = {t["collection"] for t in TEMPLATES.values()}

# limit 默认值和最大值
DEFAULT_LIMIT = 10
MAX_LIMIT = 100
