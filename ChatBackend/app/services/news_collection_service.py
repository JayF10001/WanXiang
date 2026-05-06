import requests
import re
import os
from datetime import datetime
from ..extensions import db

class NewsCollectionService:
    """简化的新闻采集服务 - 从API获取热搜新闻，热度归一化后保存到数据库"""

    @staticmethod
    def _normalize_base_url(value, default):
        normalized = (value or default).strip()
        return normalized.rstrip("/")

    @staticmethod
    def _dailyhot_base_url():
        return NewsCollectionService._normalize_base_url(
            os.getenv("HOTNEWS_DAILYHOT_BASE_URL", ""),
            "https://api-hot.imsyy.top",
        )

    @staticmethod
    def _build_dailyhot_endpoints():
        dailyhot_base = NewsCollectionService._dailyhot_base_url()
        if not dailyhot_base:
            return {}

        return {
            "weibo": f"{dailyhot_base}/weibo?cache=true",
            "baidu": f"{dailyhot_base}/baidu?cache=true",
            "douyin": f"{dailyhot_base}/douyin?cache=true",
            "bilibili": f"{dailyhot_base}/bilibili?cache=true",
            "toutiao": f"{dailyhot_base}/toutiao?cache=true",
            "zhihu": f"{dailyhot_base}/zhihu?cache=true",
        }

    @staticmethod
    def fetch_hot_news_imsyy():
        """
        获取兼容旧调用方的聚合热榜数据。

        历史上这里依赖 vvhan / imsyy 的聚合接口，现在改为从可配置的
        dailyhot 平台接口逐个平台拉取并组装，避免继续写死外部域名。
        """
        api_endpoints = NewsCollectionService._build_dailyhot_endpoints()
        if not api_endpoints:
            return {
                "success": False,
                "message": "未配置可用的 HOTNEWS_DAILYHOT_BASE_URL",
                "data": [],
            }

        platform_names = {
            "weibo": "微博",
            "baidu": "百度热点",
            "douyin": "抖音",
            "bilibili": "哔哩哔哩",
            "toutiao": "今日头条",
            "zhihu": "知乎热榜",
        }

        all_platform_data = []
        upstream_errors = []

        with requests.Session() as session:
            session.trust_env = False

            for platform_key, api_url in api_endpoints.items():
                try:
                    response = session.get(api_url, timeout=10)
                    response.raise_for_status()
                    payload = response.json()
                    items = payload.get("data")

                    if payload.get("code") != 200 or not isinstance(items, list):
                        raise ValueError(f"{platform_key} 返回异常，code={payload.get('code')}")

                    all_platform_data.append(
                        {
                            "name": platform_names.get(platform_key, platform_key),
                            "subtitle": payload.get("subtitle") or "热榜",
                            "update_time": payload.get("update_time") or "",
                            "data": [
                                {
                                    "title": item.get("title", ""),
                                    "url": item.get("url", ""),
                                    "hot": item.get("hot", 0),
                                    "mobileUrl": item.get("mobileUrl") or item.get("mobilUrl") or item.get("url", ""),
                                }
                                for item in items
                                if isinstance(item, dict) and item.get("title")
                            ],
                        }
                    )
                except Exception as exc:
                    upstream_errors.append(f"{platform_key}: {exc}")
                    continue

        if not all_platform_data:
            return {
                "success": False,
                "message": "未获取到任何热榜数据",
                "errors": upstream_errors,
                "data": [],
            }

        return {
            "success": True,
            "data": all_platform_data,
            "errors": upstream_errors or None,
        }
    
    @staticmethod
    def fetch_and_save_hot_news():
        """
        从API获取热搜新闻，热度归一化后保存到数据库
        
        Returns:
            dict: 处理结果
        """
        try:
            print("开始获取热搜新闻...")
            
            # API端点
            api_endpoints = NewsCollectionService._build_dailyhot_endpoints()
            if not api_endpoints:
                return {"status": "error", "message": "未配置可用的 HOTNEWS_DAILYHOT_BASE_URL"}
            
            # 平台权重
            platform_weights = {
                "weibo": 1.2,
                "baidu": 1.0, 
                "douyin": 0.9,
                "bilibili": 0.8,
                "toutiao": 0.9,
                "zhihu": 0.8
            }
            
            all_news = []
            
            # 获取各平台数据
            with requests.Session() as session:
                session.trust_env = False

                for platform_key, api_url in api_endpoints.items():
                    try:
                        response = session.get(api_url, timeout=10)
                        response.raise_for_status()
                        data = response.json()

                        if data.get("code") == 200:
                            for news in data.get("data", []):
                                heat_value = NewsCollectionService._parse_heat(news.get("hot", 0))
                                weighted_heat = heat_value * platform_weights.get(platform_key, 1.0)

                                all_news.append({
                                    "title": news.get("title", ""),
                                    "url": news.get("url", ""),
                                    "platform": platform_key,
                                    "raw_heat": heat_value,
                                    "weighted_heat": weighted_heat
                                })
                    except Exception as e:
                        print(f"获取{platform_key}数据失败: {str(e)}")
                        continue
            
            if not all_news:
                return {"status": "error", "message": "未获取到任何新闻数据"}
            
            # 热度归一化
            max_heat = max(news["weighted_heat"] for news in all_news)
            for news in all_news:
                news["normalized_heat"] = news["weighted_heat"] / max_heat if max_heat > 0 else 0
            
            # 按热度排序
            all_news.sort(key=lambda x: x["normalized_heat"], reverse=True)
            
            # 保存到数据库
            timestamp = datetime.now().isoformat()
            
            # 清空旧数据并插入新数据
            db.hot_news.delete_many({})
            
            for news in all_news:
                news["timestamp"] = timestamp
                db.hot_news.insert_one(news)
            
            print(f"成功保存{len(all_news)}条热搜新闻到数据库")
            
            return {
                "status": "success",
                "count": len(all_news),
                "message": f"成功获取并保存{len(all_news)}条热搜新闻"
            }
            
        except Exception as e:
            print(f"获取热搜新闻失败: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def _parse_heat(hot_value):
        """
        解析热度值为数字
        
        Args:
            hot_value: 热度值
            
        Returns:
            float: 数字热度值
        """
        if isinstance(hot_value, (int, float)):
            return float(hot_value)
        
        if not hot_value or not isinstance(hot_value, str):
            return 0
            
        # 清理字符串并匹配数字和单位
        cleaned = str(hot_value).strip().replace(',', '')
        match = re.search(r'([\d\.]+)([亿万千])?', cleaned)
        
        if not match:
            return 0
            
        base_num = float(match.group(1))
        unit = match.group(2) if match.group(2) else ''
        
        multipliers = {'': 1, '千': 1000, '万': 10000, '亿': 100000000}
        return base_num * multipliers.get(unit, 1)
    
    @staticmethod
    def get_hot_news_from_db(limit=20):
        """
        从数据库获取热搜新闻
        
        Args:
            limit (int): 限制数量
            
        Returns:
            list: 热搜新闻列表
        """
        try:
            news_list = list(db.hot_news.find(
                {}, 
                {"_id": 0}
            ).sort("normalized_heat", -1).limit(limit))
            
            return news_list
            
        except Exception as e:
            print(f"从数据库获取热搜新闻失败: {str(e)}")
            return []
