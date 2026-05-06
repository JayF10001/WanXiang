from .news_collection_service import NewsCollectionService
from .news_analysis_service import NewsAnalysisService
from .redis_cache_service import get_cache_service
import logging

logger = logging.getLogger(__name__)

class NewsService:
    """统一的新闻服务接口 - 支持Redis缓存"""
    
    @staticmethod
    def collect_hot_news():
        """
        采集热搜新闻
        
        Returns:
            dict: 采集结果
        """
        result = NewsCollectionService.fetch_and_save_hot_news()
        
        # 采集成功后，清除相关缓存
        if result.get("status") == "success":
            cache_service = get_cache_service()
            cache_service.invalidate_news_cache()
            logger.info("新闻采集完成，已清除相关缓存")
        
        return result
    
    @staticmethod
    def analyze_hot_news(limit=10):
        """
        分析热搜新闻
        
        Args:
            limit (int): 分析数量限制
            
        Returns:
            dict: 分析结果
        """
        analysis_service = NewsAnalysisService.create_service()
        if not analysis_service:
            return {"status": "error", "message": "创建分析服务失败"}
        
        result = analysis_service.analyze_hot_news(limit)
        
        # 分析成功后，清除已分析新闻的缓存
        if result.get("status") == "success" and result.get("success", 0) > 0:
            cache_service = get_cache_service()
            # 清除已分析新闻缓存
            cache_service.delete_cache(cache_service._get_cache_key("analyzed_news", limit=20))
            cache_service.delete_cache(cache_service._get_cache_key("current_news"))
            logger.info(f"新闻分析完成，分析了{result.get('success', 0)}条新闻，已清除相关缓存")
        
        return result
    
    @staticmethod
    def get_hot_news(limit=20):
        """
        获取热搜新闻（未分析）- 支持Redis缓存
        
        Args:
            limit (int): 限制数量
            
        Returns:
            list: 热搜新闻列表
        """
        cache_service = get_cache_service()
        
        # 尝试从缓存获取
        cached_data = cache_service.get_cached_hot_news(limit)
        if cached_data is not None:
            logger.info(f"从缓存获取热搜新闻: {len(cached_data)} 条")
            return cached_data
        
        # 缓存未命中，从数据库获取
        news_data = NewsCollectionService.get_hot_news_from_db(limit)
        
        # 存入缓存
        if news_data:
            cache_service.cache_hot_news(news_data, limit)
            logger.info(f"热搜新闻已存入缓存: {len(news_data)} 条")
        
        return news_data
    
    @staticmethod
    def get_analyzed_news(limit=20):
        """
        获取已分析的新闻 - 支持Redis缓存
        
        Args:
            limit (int): 限制数量
            
        Returns:
            list: 已分析的新闻列表
        """
        cache_service = get_cache_service()
        
        # 尝试从缓存获取
        cached_data = cache_service.get_cached_analyzed_news(limit)
        if cached_data is not None:
            logger.info(f"从缓存获取已分析新闻: {len(cached_data)} 条")
            return cached_data
        
        # 缓存未命中，从数据库获取
        analysis_service = NewsAnalysisService.create_service()
        if not analysis_service:
            return []
        
        news_data = analysis_service.get_analyzed_news(limit)
        
        # 存入缓存
        if news_data:
            cache_service.cache_analyzed_news(news_data, limit)
            logger.info(f"已分析新闻已存入缓存: {len(news_data)} 条")
        
        return news_data
    
    @staticmethod
    def full_process(collect_limit=50, analyze_limit=10):
        """
        完整流程：采集 -> 分析
        
        Args:
            collect_limit (int): 采集数量限制  
            analyze_limit (int): 分析数量限制
            
        Returns:
            dict: 处理结果
        """
        # 1. 采集热搜新闻
        collect_result = NewsService.collect_hot_news()
        if collect_result.get("status") != "success":
            return collect_result
        
        # 2. 分析热搜新闻
        analyze_result = NewsService.analyze_hot_news(analyze_limit)
        
        return {
            "status": "success",
            "collect_result": collect_result,
            "analyze_result": analyze_result,
            "message": f"完成采集{collect_result.get('count', 0)}条新闻，分析{analyze_result.get('success', 0)}条新闻"
        }
    
    @staticmethod
    def get_current_news_cached(limit=20):
        """
        获取当前新闻数据（优先从缓存获取）
        
        Args:
            limit (int): 限制数量
            
        Returns:
            list: 格式化后的新闻数据
        """
        cache_service = get_cache_service()
        
        # 尝试从缓存获取
        cached_data = cache_service.get_cached_current_news()
        if cached_data is not None:
            logger.info(f"从缓存获取当前新闻: {len(cached_data)} 条")
            return cached_data
        
        # 缓存未命中，获取数据并格式化
        news_data = NewsService.get_analyzed_news(limit)
        
        # 如果没有已分析数据，获取热搜数据
        if not news_data:
            hot_news = NewsService.get_hot_news(limit)
            if hot_news:
                # 转换格式
                formatted_data = []
                for idx, news in enumerate(hot_news):
                    news_item = {
                        "id": str(idx + 1),
                        "title": news.get("title", ""),
                        "platform": news.get("platform", ""),
                        "url": news.get("url", ""),
                        "normalized_heat": news.get("normalized_heat", 0),
                        "rank": idx + 1,
                        "x": 116.4074,
                        "y": 39.9042,
                        "type": "热搜",
                        "introduction": f"来自{news.get('platform', '')}的热搜新闻",
                        "participants": news.get("normalized_heat", 0),
                        "emotion": {"schema": {"平和": 1.0}},
                        "stance": {"schema": {"中立陈述": 1.0}},
                        "heatTrend": [],
                        "timeline": [],
                        "wordCloud": []
                    }
                    formatted_data.append(news_item)
                
                # 存入缓存
                cache_service.cache_current_news(formatted_data)
                logger.info(f"当前新闻（热搜）已存入缓存: {len(formatted_data)} 条")
                return formatted_data
        else:
            # 格式化已分析的数据
            formatted_data = []
            for idx, news in enumerate(news_data):
                news_item = {
                    "id": news.get("id", ""),
                    "title": news.get("title", ""),
                    "x": news.get("x", 116.4074),
                    "y": news.get("y", 39.9042),
                    "type": news.get("type", "社会"),
                    "platform": news.get("platform", "综合"),
                    "introduction": news.get("introduction", ""),
                    "spreadSpeed": news.get("spreadSpeed", 0),
                    "spreadRange": news.get("spreadRange", 0),
                    "participants": news.get("participants", 0),
                    "emotion": news.get("emotion", {"schema": {"平和": 1.0}}),
                    "stance": news.get("stance", {"schema": {"中立陈述": 1.0}}),
                    "heatTrend": news.get("heatTrend", []),
                    "timeline": news.get("timeline", []),
                    "wordCloud": news.get("wordCloud", []),
                    "rank": idx + 1
                }
                formatted_data.append(news_item)
            
            # 存入缓存
            cache_service.cache_current_news(formatted_data)
            logger.info(f"当前新闻（已分析）已存入缓存: {len(formatted_data)} 条")
            return formatted_data
        
        return []
    
    @staticmethod
    def clear_news_cache():
        """
        清除所有新闻缓存
        
        Returns:
            dict: 清除结果
        """
        cache_service = get_cache_service()
        
        if cache_service.clear_news_cache():
            return {"status": "success", "message": "新闻缓存已清除"}
        else:
            return {"status": "error", "message": "清除新闻缓存失败"}
    
    @staticmethod
    def get_cache_info():
        """
        获取缓存状态信息
        
        Returns:
            dict: 缓存信息
        """
        cache_service = get_cache_service()
        return cache_service.get_cache_info()
