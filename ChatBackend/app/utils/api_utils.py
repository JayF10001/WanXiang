import requests
import json
import time
import random
from datetime import datetime
from flask import current_app
import os

# API调用统计和限流控制
api_call_stats = {
    "total_calls": 0,
    "successful_calls": 0,
    "failed_calls": 0,
    "rate_limited_calls": 0,
    "last_call_time": 0,
    "consecutive_failures": 0,
    "backoff_until": 0
}

def fetch_news_titles(max_news_per_platform=None):
    """
    从imsyy.top API获取热门新闻标题，带有重试和错误处理机制
    
    Args:
        max_news_per_platform (int, optional): 每个平台最多获取的新闻数量，为None时从配置获取API_NEWS_PER_PLATFORM
        
    Returns:
        dict: 包含平台名称和对应热门新闻标题的字典
    """
    global api_call_stats
    
    # 获取配置中的每平台新闻数量
    if max_news_per_platform is None:
        max_news_per_platform = current_app.config.get('API_NEWS_PER_PLATFORM', 20)
    
    # 检查是否处于退避状态
    current_time = time.time()
    if current_time < api_call_stats["backoff_until"]:
        wait_time = api_call_stats["backoff_until"] - current_time
        print(f"⚠️ API限流保护中，等待{wait_time:.1f}秒后再试")
        time.sleep(min(wait_time, 5))  # 等待最长5秒
    
    # 添加随机延迟，防止对API发起突发请求
    if api_call_stats["total_calls"] > 0:
        jitter = random.uniform(0.1, 0.5)
        time.sleep(jitter)
    
    # 记录调用
    api_call_stats["total_calls"] += 1
    api_call_stats["last_call_time"] = time.time()
    
    # 设置超时和重试参数
    timeout = 10
    max_retries = 2
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            # 如果进行重试，增加延迟
            if retry_count > 0:
                backoff_time = retry_count * 2
                print(f"第{retry_count}次重试获取新闻标题，等待{backoff_time}秒")
                time.sleep(backoff_time)
            
            # 使用imsyy.top API获取数据
            start_time = time.time()
            from ..services.news_collection_service import NewsCollectionService
            json_data = NewsCollectionService.fetch_hot_news_imsyy()
            
            # 计算请求时间
            request_time = time.time() - start_time
            
            # 检查是否被限流（通过响应时间判断）
            if request_time > 5:
                api_call_stats["rate_limited_calls"] += 1
                api_call_stats["consecutive_failures"] += 1
                
                # 指数退避策略
                if api_call_stats["consecutive_failures"] > 3:
                    backoff_seconds = min(30, 2 ** api_call_stats["consecutive_failures"])
                    api_call_stats["backoff_until"] = time.time() + backoff_seconds
                    print(f"⚠️ 检测到可能的API限流，将退避{backoff_seconds}秒")
                
                if retry_count < max_retries:
                    retry_count += 1
                    continue
            
            # 确保数据格式正确
            if not json_data or not json_data.get('success'):
                print(f"imsyy.top API返回数据格式错误")
                api_call_stats["failed_calls"] += 1
                return {}
            
            # 提取新闻标题
            result = {}
            for platform_data in json_data.get('data', []):
                platform_name = platform_data.get('name', 'unknown')
                news_titles = []
                
                for news_item in platform_data.get('data', []):
                    title = news_item.get('title')
                    url = news_item.get('url', '')
                    hot = news_item.get('hot', 0)
                    
                    if title:
                        # 组装新闻数据，包含额外可用信息
                        news_data = {
                            "title": title,
                            "url": url,
                            "hot": hot
                        }
                        news_titles.append(news_data)
                        
                        # 达到最大数量后停止添加
                        if len(news_titles) >= max_news_per_platform:
                            break
                
                if news_titles:
                    result[platform_name] = news_titles
            
            # 重置连续失败计数
            api_call_stats["consecutive_failures"] = 0
            api_call_stats["successful_calls"] += 1
            
            # 记录统计信息到日志
            success_rate = (api_call_stats["successful_calls"] / api_call_stats["total_calls"]) * 100
            print(f"API调用成功率: {success_rate:.1f}%, 总调用次数: {api_call_stats['total_calls']}")
            
            return result
            
        except Exception as e:
            print(f"获取新闻标题失败: {str(e)}")
            api_call_stats["consecutive_failures"] += 1
            api_call_stats["failed_calls"] += 1
            
            if retry_count < max_retries:
                retry_count += 1
                continue
            else:
                return {}
    
    # 如果所有重试都失败
    return {}

# def transform_api_results(news_dict):
#     """
#     将从API获取的新闻标题转换为分析所需的格式
#     
#     Args:
#         news_dict (dict): 从API获取的新闻字典
#         
#     Returns:
#         list: 转换后的新闻列表，每项包含title和platform
#     """
#     news_items = []
#     
#     for platform, news_list in news_dict.items():
#         for news in news_list:
#             # 支持两种格式：字符串或字典
#             if isinstance(news, str):
#                 title = news
#                 url = ""
#                 hot = 0
#             elif isinstance(news, dict):
#                 title = news.get("title", "")
#                 url = news.get("url", "")
#                 hot = news.get("hot", 0)
#             else:
#                 continue
#                 
#             if title:
#                 news_items.append({
#                     "title": title,
#                     "platform": platform,
#                     "url": url,
#                     "hot": hot,
#                     "fetched_at": datetime.now()
#                 })
#     
#     return news_items

# def call_llm_api(client, messages, model, temperature=0.7, stream=True, timeout=60):

def fetch_hot_news():
    """
    从imsyy.top API获取热门新闻数据
    
    Returns:
        dict: 包含热门新闻数据的字典，如果获取失败则返回None
    """
    try:
        # 使用NewsCollectionService获取imsyy.top API数据
        from ..services.news_collection_service import NewsCollectionService
        data = NewsCollectionService.fetch_hot_news_imsyy()
        
        if not data or not data.get('success'):
            print("imsyy.top API返回非成功状态")
            return None
            
        return data
        
    except Exception as e:
        print(f"获取热门新闻数据失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None 
