#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis缓存服务
提供新闻数据的Redis缓存功能，提高API响应速度
"""

import json
import redis
from datetime import datetime, timedelta
from flask import current_app
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class RedisCacheService:
    """Redis缓存服务类"""
    
    def __init__(self):
        """初始化Redis连接"""
        self.redis_client = None
        self._connected = False
        self.mode = "uninitialized"
        self.connection_label = "not-initialized"
        try:
            self._connect()
        except Exception as e:
            logging.warning(f"Redis 连接失败: {e} - 使用内存缓存模式")
            self.redis_client = None
            self._connected = False
            self.mode = "memory-fallback"
            self.connection_label = "memory-fallback"
    
    def _connect(self):
        """连接到Redis"""
        try:
            import os
            
            # 从环境变量或Flask配置获取Redis连接信息
            redis_url = os.environ.get('CELERY_BROKER_URL') or \
                       (current_app.config.get('CELERY_BROKER_URL') if current_app else None) or \
                       'redis://redis:6379/0'  # Docker环境默认
            
            logger.info(f"尝试连接Redis: {redis_url}")
            
            # 解析Redis URL
            if redis_url.startswith('redis://'):
                # 简单解析redis://host:port/db格式
                url_parts = redis_url.replace('redis://', '').split('/')
                host_port = url_parts[0].split(':')
                host = host_port[0] if host_port[0] else 'redis'  # 默认使用redis主机名
                port = int(host_port[1]) if len(host_port) > 1 else 6379
                db = int(url_parts[1]) if len(url_parts) > 1 else 0
                
                self.redis_client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
            else:
                # 使用默认配置（Docker环境）
                self.redis_client = redis.Redis(
                    host='redis',  # Docker服务名
                    port=6379,
                    db=0,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
            
            # 测试连接
            self.redis_client.ping()
            self._connected = True
            self.mode = "redis"
            self.connection_label = f"{host}:{port}/db{db}"
            logger.info(f"Redis缓存服务连接成功 - {host}:{port}")
            
        except Exception as e:
            logger.error(f"Redis连接失败: {str(e)}")
            # 尝试本地连接作为后备
            try:
                logger.info("尝试连接本地Redis服务器...")
                self.redis_client = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True,
                    socket_timeout=3,
                    socket_connect_timeout=3
                )
                self.redis_client.ping()
                self._connected = True
                self.mode = "redis"
                self.connection_label = "localhost:6379/db0"
                logger.info("本地Redis缓存服务连接成功")
            except Exception as local_e:
                logger.error(f"本地Redis连接也失败: {str(local_e)}")
                self.redis_client = None
                self._connected = False
                self.mode = "memory-fallback"
                self.connection_label = "memory-fallback"
    
    def is_connected(self) -> bool:
        """检查Redis是否连接正常"""
        try:
            if self.redis_client:
                self.redis_client.ping()
                self._connected = True
                return True
        except:
            self._connected = False
            pass
        return False
    
    def _get_cache_key(self, data_type: str, **kwargs) -> str:
        """生成缓存键名"""
        base_key = f"news_cache:{data_type}"
        
        if kwargs:
            # 添加参数到键名中
            params = ":".join([f"{k}={v}" for k, v in sorted(kwargs.items())])
            return f"{base_key}:{params}"
        
        return base_key
    
    def set_cache(self, key: str, data: Any, expire_seconds: int = 300) -> bool:
        """
        设置缓存数据
        
        Args:
            key (str): 缓存键
            data (Any): 要缓存的数据
            expire_seconds (int): 过期时间（秒），默认5分钟
            
        Returns:
            bool: 是否设置成功
        """
        if not self.is_connected():
            return False
            
        try:
            # 序列化数据
            if isinstance(data, (dict, list)):
                json_data = json.dumps(data, ensure_ascii=False, default=str)
            else:
                json_data = str(data)
            
            # 设置缓存并设置过期时间
            result = self.redis_client.setex(key, expire_seconds, json_data)
            
            logger.info(f"缓存设置成功: {key}, 过期时间: {expire_seconds}秒")
            return result
            
        except Exception as e:
            logger.error(f"设置缓存失败: {key}, 错误: {str(e)}")
            return False
    
    def get_cache(self, key: str) -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            key (str): 缓存键
            
        Returns:
            Optional[Any]: 缓存的数据，如果不存在或过期返回None
        """
        if not self.is_connected():
            return None
            
        try:
            cached_data = self.redis_client.get(key)
            
            if cached_data is None:
                logger.debug(f"缓存未命中: {key}")
                return None
            
            # 尝试解析JSON数据
            try:
                data = json.loads(cached_data)
                logger.debug(f"缓存命中: {key}")
                return data
            except json.JSONDecodeError:
                # 如果不是JSON，返回原始字符串
                return cached_data
                
        except Exception as e:
            logger.error(f"获取缓存失败: {key}, 错误: {str(e)}")
            return None
    
    def delete_cache(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key (str): 缓存键
            
        Returns:
            bool: 是否删除成功
        """
        if not self.is_connected():
            return False
            
        try:
            result = self.redis_client.delete(key)
            logger.info(f"缓存删除: {key}")
            return bool(result)
        except Exception as e:
            logger.error(f"删除缓存失败: {key}, 错误: {str(e)}")
            return False
    
    def clear_news_cache(self) -> bool:
        """
        清除所有新闻相关缓存
        
        Returns:
            bool: 是否清除成功
        """
        if not self.is_connected():
            return False
            
        try:
            # 获取所有新闻缓存键
            pattern = "news_cache:*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                deleted_count = self.redis_client.delete(*keys)
                logger.info(f"清除新闻缓存: {deleted_count} 个键")
                return True
            else:
                logger.info("没有找到新闻缓存")
                return True
                
        except Exception as e:
            logger.error(f"清除新闻缓存失败: {str(e)}")
            return False
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        获取缓存信息
        
        Returns:
            Dict: 缓存信息统计
        """
        if not self.is_connected():
            return {"connected": False, "error": "Redis未连接"}
            
        try:
            info = self.redis_client.info()
            
            # 获取新闻缓存键统计
            news_keys = self.redis_client.keys("news_cache:*")
            
            return {
                "connected": True,
                "redis_version": info.get("redis_version"),
                "used_memory_human": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed"),
                "news_cache_keys_count": len(news_keys),
                "news_cache_keys": news_keys[:10] if news_keys else []  # 只返回前10个键名
            }
            
        except Exception as e:
            logger.error(f"获取缓存信息失败: {str(e)}")
            return {"connected": False, "error": str(e)}

    # 新闻数据相关的专用缓存方法
    
    def cache_analyzed_news(self, news_data: List[Dict], limit: int = 20) -> bool:
        """
        缓存已分析的新闻数据
        
        Args:
            news_data (List[Dict]): 新闻数据列表
            limit (int): 数据限制数量
            
        Returns:
            bool: 是否缓存成功
        """
        cache_key = self._get_cache_key("analyzed_news", limit=limit)
        # 已分析新闻缓存10分钟
        return self.set_cache(cache_key, news_data, expire_seconds=600)
    
    def get_cached_analyzed_news(self, limit: int = 20) -> Optional[List[Dict]]:
        """
        获取缓存的已分析新闻数据
        
        Args:
            limit (int): 数据限制数量
            
        Returns:
            Optional[List[Dict]]: 缓存的新闻数据，如果不存在返回None
        """
        cache_key = self._get_cache_key("analyzed_news", limit=limit)
        return self.get_cache(cache_key)
    
    def cache_hot_news(self, news_data: List[Dict], limit: int = 20) -> bool:
        """
        缓存热搜新闻数据
        
        Args:
            news_data (List[Dict]): 新闻数据列表
            limit (int): 数据限制数量
            
        Returns:
            bool: 是否缓存成功
        """
        cache_key = self._get_cache_key("hot_news", limit=limit)
        # 热搜新闻缓存5分钟
        return self.set_cache(cache_key, news_data, expire_seconds=300)
    
    def get_cached_hot_news(self, limit: int = 20) -> Optional[List[Dict]]:
        """
        获取缓存的热搜新闻数据
        
        Args:
            limit (int): 数据限制数量
            
        Returns:
            Optional[List[Dict]]: 缓存的新闻数据，如果不存在返回None
        """
        cache_key = self._get_cache_key("hot_news", limit=limit)
        return self.get_cache(cache_key)
    
    def cache_current_news(self, news_data: List[Dict]) -> bool:
        """
        缓存当前新闻数据（用于/currentnews接口）
        
        Args:
            news_data (List[Dict]): 新闻数据列表
            
        Returns:
            bool: 是否缓存成功
        """
        cache_key = self._get_cache_key("current_news")
        # 当前新闻缓存2分钟
        return self.set_cache(cache_key, news_data, expire_seconds=120)
    
    def get_cached_current_news(self) -> Optional[List[Dict]]:
        """
        获取缓存的当前新闻数据
        
        Returns:
            Optional[List[Dict]]: 缓存的新闻数据，如果不存在返回None
        """
        cache_key = self._get_cache_key("current_news")
        return self.get_cache(cache_key)
    
    def invalidate_news_cache(self) -> bool:
        """
        使新闻缓存失效（在数据更新后调用）
        
        Returns:
            bool: 是否成功
        """
        return self.clear_news_cache()
    
    # 热搜代理接口缓存方法
    
    def cache_proxy_hotnews(self, platform: str, data: Any) -> bool:
        """
        缓存单个平台的热搜代理数据
        
        Args:
            platform (str): 平台名称 (weibo, baidu, douyin, bilibili, toutiao, zhihu)
            data (Any): 热搜数据
            
        Returns:
            bool: 是否缓存成功
        """
        cache_key = self._get_cache_key("proxy_hotnews", platform=platform)
        # 热搜代理数据缓存3分钟（因为是第三方API，相对稳定）
        return self.set_cache(cache_key, data, expire_seconds=180)
    
    def get_cached_proxy_hotnews(self, platform: str) -> Optional[Any]:
        """
        获取缓存的单个平台热搜代理数据
        
        Args:
            platform (str): 平台名称
            
        Returns:
            Optional[Any]: 缓存的热搜数据，如果不存在返回None
        """
        cache_key = self._get_cache_key("proxy_hotnews", platform=platform)
        return self.get_cache(cache_key)
    
    def cache_proxy_hotnews_all(self, data: Any) -> bool:
        """
        缓存所有平台的热搜代理数据
        
        Args:
            data (Any): 所有平台的热搜数据
            
        Returns:
            bool: 是否缓存成功
        """
        cache_key = self._get_cache_key("proxy_hotnews_all")
        # 所有平台热搜数据缓存3分钟
        return self.set_cache(cache_key, data, expire_seconds=180)
    
    def get_cached_proxy_hotnews_all(self) -> Optional[Any]:
        """
        获取缓存的所有平台热搜代理数据
        
        Returns:
            Optional[Any]: 缓存的热搜数据，如果不存在返回None
        """
        cache_key = self._get_cache_key("proxy_hotnews_all")
        return self.get_cache(cache_key)
    
    def clear_proxy_cache(self) -> bool:
        """
        清除所有代理缓存
        
        Returns:
            bool: 是否清除成功
        """
        if not self.is_connected():
            return False
            
        try:
            # 获取所有代理缓存键
            pattern = "news_cache:proxy_*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                deleted_count = self.redis_client.delete(*keys)
                logger.info(f"清除代理缓存: {deleted_count} 个键")
                return True
            else:
                logger.info("没有找到代理缓存")
                return True
                
        except Exception as e:
            logger.error(f"清除代理缓存失败: {str(e)}")
            return False

# 创建全局缓存服务实例
_cache_service = None

def get_cache_service() -> RedisCacheService:
    """
    获取缓存服务实例（单例模式）
    
    Returns:
        RedisCacheService: 缓存服务实例
    """
    global _cache_service
    
    if _cache_service is None:
        _cache_service = RedisCacheService()
    
    return _cache_service

def init_redis_cache(app=None) -> bool:
    """
    初始化Redis缓存服务
    
    Args:
        app: Flask应用实例（可选）
        
    Returns:
        bool: 是否初始化成功
    """
    try:
        cache_service = get_cache_service()
        return cache_service.is_connected()
    except Exception as e:
        logger.error(f"Redis缓存初始化失败: {str(e)}")
        return False

# 为了向后兼容，创建redis_cache别名
redis_cache = None

def get_redis_cache() -> RedisCacheService:
    """获取Redis缓存实例，与get_cache_service功能相同"""
    return get_cache_service()

# 在模块加载时初始化redis_cache
try:
    redis_cache = get_cache_service()
except Exception as e:
    logger.warning(f"Redis缓存服务初始化失败: {str(e)}")
    redis_cache = None
