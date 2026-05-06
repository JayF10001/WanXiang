import json
import hashlib
from datetime import datetime
from openai import OpenAI
from flask import current_app
from ..extensions import db

class NewsAnalysisService:
    """简化的新闻分析服务 - 从数据库获取标题，使用大模型分析，存储结构化数据"""
    
    def __init__(self, api_key, base_url, model):
        """
        初始化新闻分析服务
        
        Args:
            api_key (str): API密钥
            base_url (str): API基础URL
            model (str): 模型名称
        """
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
        
        # 分析prompt模板
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.prompt = f"""今天是{current_date}，请你扮演新闻助理，为新闻标题进行深度分析。

请以JSON格式输出结果，不要包含任何其他文字说明：

{{
    "id": "新闻ID",
    "title": "新闻标题",
    "x": 经度,
    "y": 纬度,
    "type": "新闻类型",
    "introduction": "新闻简介(100字内)",
    "spreadSpeed": 传播速度(0-1),
    "spreadRange": 传播范围(0-1),
    "participants": 参与热度(0-1),
    "emotion": {{
        "schema": {{
            "喜悦": 0.0-1.0,
            "期待": 0.0-1.0,
            "平和": 0.0-1.0,
            "惊讶": 0.0-1.0,
            "悲伤": 0.0-1.0,
            "愤怒": 0.0-1.0,
            "恐惧": 0.0-1.0,
            "厌恶": 0.0-1.0
        }}
    }},
    "stance": {{
        "schema": {{
            "积极倡导": 0.0-1.0,
            "强烈反对": 0.0-1.0,
            "中立陈述": 0.0-1.0,
            "质疑探究": 0.0-1.0,
            "理性建议": 0.0-1.0,
            "情绪宣泄": 0.0-1.0,
            "观望等待": 0.0-1.0,
            "扩散传播": 0.0-1.0
        }}
    }},
    "heatTrend": [
        {{"date": "日期", "value": 热度值}}
    ],
    "timeline": [
        {{"date": "日期", "event": "事件描述"}}
    ],
    "wordCloud": [
        {{"weight": 权重, "word": "关键词"}}
    ]
}}

要求：
- 经纬度使用合理的地理坐标
- 所有量化值在0-1范围内
- emotion各维度总和为1
- stance各维度总和为1
- 至少3个热度趋势数据点
- 至少20个词云关键词
"""
    
    def analyze_single_news(self, title):
        """
        分析单条新闻
        
        Args:
            title (str): 新闻标题
            
        Returns:
            dict: 分析结果
        """
        try:
            print(f"开始分析新闻: {title}")
            
            # 生成新闻ID
            news_id = hashlib.md5(title.encode()).hexdigest()
            
            # 检查是否已分析过
            existing = db.analyzed_news.find_one({"id": news_id})
            if existing:
                print(f"新闻已分析过，跳过: {title}")
                return existing
            
            # 调用大模型分析
            messages = [
                {'role': 'system', 'content': self.prompt},
                {'role': 'user', 'content': title}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3
            )
            
            result_text = response.choices[0].message.content
            
            # 解析JSON结果
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(result_text)
            
            # 确保必要字段存在
            result["id"] = news_id
            result["title"] = title
            result["analyzed_at"] = datetime.now().isoformat()
            
            # 保存到数据库
            db.analyzed_news.update_one(
                {"id": news_id},
                {"$set": result},
                upsert=True
            )
            
            print(f"新闻分析完成: {title}")
            return result
            
        except Exception as e:
            print(f"分析新闻失败: {title}, 错误: {str(e)}")
            return None
    
    def analyze_hot_news(self, limit=10):
        """
        分析热搜新闻
        
        Args:
            limit (int): 分析数量限制
            
        Returns:
            dict: 分析结果统计
        """
        try:
            print(f"开始分析前{limit}条热搜新闻...")
            
            # 从数据库获取热搜新闻
            hot_news = list(db.hot_news.find(
                {}, 
                {"title": 1, "_id": 0}
            ).sort("normalized_heat", -1).limit(limit))
            
            if not hot_news:
                return {"status": "error", "message": "没有找到热搜新闻数据"}
            
            success_count = 0
            fail_count = 0
            
            for news in hot_news:
                title = news.get("title", "").strip()
                if not title:
                    continue
                
                result = self.analyze_single_news(title)
                if result:
                    success_count += 1
                else:
                    fail_count += 1
            
            print(f"分析完成: 成功{success_count}条, 失败{fail_count}条")
            
            return {
                "status": "success",
                "total": len(hot_news),
                "success": success_count,
                "fail": fail_count,
                "message": f"成功分析{success_count}条新闻"
            }
            
        except Exception as e:
            print(f"分析热搜新闻失败: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_analyzed_news(self, limit=20):
        """
        获取已分析的新闻
        
        Args:
            limit (int): 限制数量
            
        Returns:
            list: 已分析的新闻列表
        """
        try:
            analyzed_list = list(db.analyzed_news.find(
                {},
                {"_id": 0}
            ).sort("participants", -1).limit(limit))
            
            return analyzed_list
            
        except Exception as e:
            print(f"获取已分析新闻失败: {str(e)}")
            return []
    
    def get_analyzed_news_paginated(self, page=1, page_size=10, sort_field="participants", sort_order=-1):
        """
        分页获取已分析的新闻
        
        Args:
            page (int): 页码，从1开始
            page_size (int): 每页数量
            sort_field (str): 排序字段
            sort_order (int): 排序顺序，-1降序，1升序
            
        Returns:
            dict: 包含分页信息和数据的字典
        """
        try:
            # 计算跳过的文档数量
            skip = (page - 1) * page_size
            
            # 获取总数
            total = db.analyzed_news.count_documents({})
            
            # 获取分页数据
            analyzed_list = list(db.analyzed_news.find(
                {},
                {"_id": 0}
            ).sort(sort_field, sort_order).skip(skip).limit(page_size))
            
            # 计算总页数
            total_pages = (total + page_size - 1) // page_size
            
            return {
                "data": analyzed_list,
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
            
        except Exception as e:
            print(f"分页获取已分析新闻失败: {str(e)}")
            return {
                "data": [],
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                    "has_next": False,
                    "has_prev": False
                }
            }
    
    @staticmethod
    def create_service():
        """
        创建分析服务实例
        
        Returns:
            NewsAnalysisService: 服务实例
        """
        try:
            api_key = current_app.config.get('QWEN_API_KEY')
            base_url = current_app.config.get('QWEN_BASE_URL')
            model = current_app.config.get('QWEN_MODEL')
            
            if not api_key or not base_url:
                raise ValueError("缺少API配置")
            
            return NewsAnalysisService(api_key, base_url, model)
            
        except Exception as e:
            print(f"创建分析服务失败: {str(e)}")
            return None
