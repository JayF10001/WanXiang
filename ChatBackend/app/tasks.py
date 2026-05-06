"""
Simple tasks module for scheduled tasks using Celery
"""
import datetime
from flask import current_app
import traceback

# 导入 Celery 应用实例
try:
    from ChatBackend.celery_app import celery
except ImportError:
    from celery_app import celery

@celery.task(name='tasks.heartbeat')
def heartbeat():
    """Simple heartbeat task that prints the current time"""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[Celery Heartbeat] Application running at {current_time}")
    return True

@celery.task(name='tasks.collect_news')
def collect_news_task():
    """采集热搜新闻任务"""
    try:
        print(f"[{datetime.datetime.now()}] [Celery] 开始采集热搜新闻...")
        from .services.news_service import NewsService
        
        result = NewsService.collect_hot_news()
        print(f"[{datetime.datetime.now()}] [Celery] 新闻采集完成: {result}")
        return result
    except Exception as e:
        print(f"[{datetime.datetime.now()}] [Celery] 新闻采集错误: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

@celery.task(name='tasks.smart_collect')
def smart_collect_news_task():
    """智能采集热搜新闻任务"""
    try:
        print(f"[{datetime.datetime.now()}] [Celery] 启动智能热搜新闻采集...")
        from .services.news_service import NewsService
        
        result = NewsService.collect_hot_news()
        print(f"[{datetime.datetime.now()}] [Celery] 智能采集完成: {result}")
        return result
    except Exception as e:
        print(f"[{datetime.datetime.now()}] [Celery] 智能采集错误: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}



@celery.task(name='tasks.batch_analyze_news')
def batch_analyze_news_task(limit=10):
    """批量分析热搜新闻任务"""
    try:
        print(f"[{datetime.datetime.now()}] [Celery] 开始批量分析新闻...")
        from .services.news_service import NewsService
        
        result = NewsService.analyze_hot_news(limit=limit)
        print(f"[{datetime.datetime.now()}] [Celery] 批量分析完成: {result}")
        return result
    except Exception as e:
        print(f"[{datetime.datetime.now()}] [Celery] 批量分析错误: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

@celery.task(name='tasks.full_process')
def full_process_task(collect_limit=50, analyze_limit=10):
    """完整流程任务：采集 -> 分析"""
    try:
        print(f"[{datetime.datetime.now()}] [Celery] 开始完整流程...")
        from .services.news_service import NewsService
        
        result = NewsService.full_process(collect_limit, analyze_limit)
        print(f"[{datetime.datetime.now()}] [Celery] 完整流程完成: {result}")
        return result
    except Exception as e:
        print(f"[{datetime.datetime.now()}] [Celery] 完整流程错误: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)} 

# 确保移除了旧的 simple_scheduler 相关代码（例如 tasks 列表和调度函数）
# (根据阅读的文件内容，似乎没有这些旧代码，因此无需移除) 
