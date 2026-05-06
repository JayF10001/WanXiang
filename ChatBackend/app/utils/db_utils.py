from datetime import datetime, timedelta
from bson import ObjectId
from flask import current_app

def ensure_indexes():
    """
    确保所有必要的MongoDB索引已创建
    Returns:
        bool: 如果所有索引创建成功则返回True，否则返回False
    """
    try:
        from flask import current_app
        from ..extensions import db
        from ..services.report_service import ReportService
        from ..services.strategy_service import StrategyService
    
        # 用户集合索引
        db.users.create_index([("email", 1)], unique=True)
        db.users.create_index([("username", 1)], unique=True)
        
        # 新闻分析相关索引
        db.news_sources.create_index([("platform", 1)])
        db.news_sources.create_index([("updated_at", -1)])
        
        db.raw_news.create_index([("platform", 1)])
        db.raw_news.create_index([("title", 1)])
        db.raw_news.create_index([("collected_at", -1)])
        
        db.processed_news.create_index([("platform", 1)])
        db.processed_news.create_index([("type", 1)])
        db.processed_news.create_index([("rank", 1)])
        db.processed_news.create_index([("analyzed_at", -1)])
        
        db.analysis_queue.create_index([("status", 1)])
        db.analysis_queue.create_index([("created_at", -1)])
        
        # 聊天相关索引
        db.chat_sessions.create_index([("user_id", 1)])
        db.chat_sessions.create_index([("updated_at", -1)])
        
        db.messages.create_index([("session_id", 1)])
        db.messages.create_index([("created_at", 1)])
        
        db.news_analysis.create_index([("vertical_domain", 1)])
        db.news_analysis.create_index([("created_at", -1)])
        
        db.strategy_results.create_index([("session_id", 1)])
        db.strategy_results.create_index([("created_at", -1)])
        
        db.token_usage.create_index([("timestamp", -1)])
        db.token_usage.create_index([("model", 1)])

        # 私有知识库索引
        db.knowledge_bases.create_index([("owner_user_id", 1)])
        db.knowledge_bases.create_index([("updated_at", -1)])

        db.knowledge_files.create_index([("kb_id", 1)])
        db.knowledge_files.create_index([("owner_user_id", 1)])
        db.knowledge_files.create_index([("created_at", -1)])
        db.knowledge_files.create_index([("sha256", 1)])
        db.knowledge_files.create_index([("parse_status", 1)])
        db.knowledge_files.create_index([("index_status", 1)])
        db.knowledge_files.create_index([("embedding_version", 1)])

        db.knowledge_chunks.create_index([("file_id", 1)])
        db.knowledge_chunks.create_index([("kb_id", 1)])
        db.knowledge_chunks.create_index([("owner_user_id", 1)])
        db.knowledge_chunks.create_index([("chunk_index", 1)])
        db.knowledge_chunks.create_index([("embedding_version", 1)])
        db.knowledge_chunks.create_index([("updated_at", -1)])

        db.knowledge_records.create_index([("file_id", 1)])
        db.knowledge_records.create_index([("kb_id", 1)])
        db.knowledge_records.create_index([("owner_user_id", 1)])
        db.knowledge_records.create_index([("record_type", 1)])
        db.knowledge_records.create_index([("school_name", 1)])
        db.knowledge_records.create_index([("student_name", 1)])
        db.knowledge_records.create_index([("award", 1)])
        db.knowledge_records.create_index([("group_name", 1)])
        db.knowledge_records.create_index([("subject_name", 1)])
        db.knowledge_records.create_index([("qualified_for_final", 1)])
        db.knowledge_records.create_index([("updated_at", -1)])
        
        # 视频处理索引
        db.video_processing.create_index([("video_id", 1)])
        db.video_processing.create_index([("status", 1)])
        db.video_processing.create_index([("created_at", -1)])
        
        # 初始化报告服务索引
        try:
            current_app.logger.info("正在初始化报告服务数据库...")
            init_result = ReportService.initialize_db()
            if init_result:
                current_app.logger.info("报告服务数据库初始化成功")
            else:
                current_app.logger.warning("报告服务数据库初始化返回失败")
        except Exception as report_init_error:
            current_app.logger.error(f"报告服务数据库初始化时发生错误: {str(report_init_error)}")
            # 继续执行，不要因为报告服务初始化失败而中断整个索引创建过程

        try:
            current_app.logger.info("正在初始化策略服务数据库...")
            init_result = StrategyService.initialize_db()
            if init_result:
                current_app.logger.info("策略服务数据库初始化成功")
            else:
                current_app.logger.warning("策略服务数据库初始化返回失败")
        except Exception as strategy_init_error:
            current_app.logger.error(f"策略服务数据库初始化时发生错误: {str(strategy_init_error)}")

        current_app.logger.info("MongoDB indexes created successfully.")
        return True
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error creating MongoDB indexes: {str(e)}")
        return False

# def get_news_by_platform(platform=None, limit=10, skip=0):
#     """
#     按平台获取新闻数据
#     
#     Args:
#         platform (str, optional): 平台名称，如果为None则获取所有平台
#         limit (int): 限制返回的记录数
#         skip (int): 跳过的记录数
#     
#     Returns:
#         list: 新闻数据列表
#     """
#     from ..models import db
#     
#     query = {}
#     if platform:
#         query["platforms"] = platform
#     
#     return list(db.news_hourly.find(
#         query, 
#         {'_id': 0}
#     ).sort("heat_sum", -1).skip(skip).limit(limit))

# def get_news_by_id(news_id):
#     """
#     按ID获取单条新闻
#     
#     Args:
#         news_id (str): 新闻ID
#     
#     Returns:
#         dict: 新闻数据
#     """
#     from ..models import db
#     
#     news = db.news_hourly.find_one({"id": news_id}, {'_id': 0})
#     
#     # 如果找到了新闻，检查是否有分析数据
#     if news:
#         analysis = db.news_daily_analysis.find_one({"news_id": news_id}, {'_id': 0})
#         if analysis:
#             news["analysis"] = analysis["analysis"]
#     
#     return news

# def search_news(query, limit=10):
#     """
#     搜索新闻
#     
#     Args:
#         query (str): 搜索关键词
#         limit (int): 限制返回的记录数
#     
#     Returns:
#         list: 符合条件的新闻数据
#     """
#     from ..models import db
#     
#     if not query:
#         return []
#     
#     # 使用文本索引搜索
#     text_results = list(db.news_hourly.find(
#         {"$text": {"$search": query}},
#         {'_id': 0, 'score': {'$meta': "textScore"}}
#     ).sort([('score', {'$meta': 'textScore'})]).limit(limit))
#     
#     # 如果文本搜索没有结果，尝试正则表达式搜索
#     if not text_results:
#         regex_query = {
#             "title": {"$regex": query, "$options": "i"}
#         }
#         text_results = list(db.news_hourly.find(regex_query, {'_id': 0}).sort("composite_hot", -1).limit(limit))
#     
#     # 为每条新闻添加分析数据（如果有）
#     for news in text_results:
#         analysis = db.news_daily_analysis.find_one({"news_id": news["id"]}, {'_id': 0, "analysis": 1})
#         if analysis:
#             news["analysis"] = analysis["analysis"]
#     
#     return text_results

# def get_news_stats():
#     """
#     获取新闻统计信息
#     
#     Returns:
#         dict: 统计信息
#     """
#     from ..models import db
#     
#     stats = {
#         "hourly_news": db.news_hourly.count_documents({}),
#         "analyzed_news": db.news_daily_analysis.count_documents({}),
#         "platforms": [],
#         "latest_collection": None,
#         "latest_analysis": None
#     }
#     
#     # 获取平台统计
#     platforms = db.news_hourly.aggregate([
#         {"$unwind": "$platforms"},
#         {"$group": {"_id": "$platforms", "count": {"$sum": 1}}},
#         {"$sort": {"count": -1}}
#     ])
#     stats["platforms"] = [{"name": p["_id"], "count": p["count"]} for p in platforms]
#     
#     # 获取最后收集时间
#     latest = db.news_hourly.find_one({}, sort=[("collected_at", -1)])
#     if latest and "collected_at" in latest:
#         stats["latest_collection"] = latest["collected_at"]
#     
#     # 获取最后分析时间
#     latest_analysis = db.news_daily_analysis.find_one({}, sort=[("analyzed_at", -1)])
#     if latest_analysis and "analyzed_at" in latest_analysis:
#         stats["latest_analysis"] = latest_analysis["analyzed_at"]
#     
#     return stats

def get_top_news_for_analysis(limit=20):
    """
    获取需要分析的热门新闻
    
    Args:
        limit (int): 限制返回的记录数
    
    Returns:
        list: 待分析的新闻列表
    """
    from ..models import db
    
    # 查询今天尚未分析的热门新闻
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 查找已分析的新闻ID
    analyzed_ids = set()
    analyzed_cursor = db.news_daily_analysis.find(
        {"analyzed_at": {"$gte": today}},
        {"news_id": 1}
    )
    for doc in analyzed_cursor:
        analyzed_ids.add(doc["news_id"])
    
    # 查找正在队列中的新闻ID
    queued_ids = set()
    queued_cursor = db.news_analysis_queue.find(
        {"created_at": {"$gte": today}},
        {"news_id": 1}
    )
    for doc in queued_cursor:
        queued_ids.add(doc["news_id"])
    
    # 合并已处理的ID
    processed_ids = analyzed_ids.union(queued_ids)
    
    # 查询尚未分析的热门新闻
    query = {
        "id": {"$nin": list(processed_ids)},
        "collected_at": {"$gte": today - timedelta(days=1)}  # 只分析最近24小时的新闻
    }
    
    news_for_analysis = list(db.news_hourly.find(
        query,
        {"_id": 0, "id": 1, "title": 1, "update_time": 1, "composite_hot": 1}
    ).sort("composite_hot", -1).limit(limit))
    
    # 将新闻添加到分析队列
    now = datetime.now()
    for news in news_for_analysis:
        db.news_analysis_queue.update_one(
            {"news_id": news["id"]},
            {
                "$set": {
                    "news_id": news["id"],
                    "title": news["title"],
                    "status": "pending",
                    "created_at": now,
                    "updated_at": now
                }
            },
            upsert=True
        )
    
    return news_for_analysis

def update_analysis_status(news_id, status, result=None):
    """
    更新分析状态
    
    Args:
        news_id (str): 新闻ID
        status (str): 状态 (pending, processing, completed, failed)
        result (dict, optional): 分析结果
        
    Returns:
        bool: 是否成功
    """
    from ..models import db
    
    try:
        now = datetime.now()
        update = {
            "status": status,
            "updated_at": now
        }
        
        if status == "completed" and result:
            # 保存分析结果
            db.news_daily_analysis.update_one(
                {"news_id": news_id},
                {
                    "$set": {
                        "news_id": news_id,
                        "title": result.get("title", ""),
                        "analysis": result,
                        "analyzed_at": now
                    }
                },
                upsert=True
            )
        
        # 更新队列状态
        db.news_analysis_queue.update_one(
            {"news_id": news_id},
            {"$set": update}
        )
        
        return True
    except Exception as e:
        print(f"更新分析状态失败: {str(e)}")
        return False

def get_pending_analysis_tasks(limit=5):
    """
    获取待处理的分析任务
    
    Args:
        limit (int): 限制返回的记录数
        
    Returns:
        list: 待处理的任务列表
    """
    from ..models import db
    
    # 查询状态为pending的任务
    tasks = list(db.news_analysis_queue.find(
        {"status": "pending"},
        {"_id": 0}
    ).sort("created_at", 1).limit(limit))
    
    # 将任务状态更新为processing
    now = datetime.now()
    for task in tasks:
        db.news_analysis_queue.update_one(
            {"news_id": task["news_id"]},
            {"$set": {"status": "processing", "updated_at": now}}
        )
    
    # 获取完整的新闻数据
    for task in tasks:
        news = db.news_hourly.find_one({"id": task["news_id"]}, {"_id": 0})
        if news:
            task["news_data"] = news 
