import json
import random
import time
from datetime import datetime, timedelta
import hashlib

def safe_json_data(text):
    """
    尝试修复和处理可能损坏的JSON数据
    
    Args:
        text (str): 可能是JSON格式的文本字符串
        
    Returns:
        dict/list: 解析后的JSON数据，如果解析失败则返回空字典或原始文本
    """
    if text is None:
        return {}

    if isinstance(text, (dict, list, int, float, bool)):
        return text

    if not text:
        return {}
    
    try:
        # 首先尝试直接解析
        return json.loads(text)
    except json.JSONDecodeError:
        # 如果解析失败，尝试修复常见问题
        try:
            # 检查是否有markdown代码块格式 ```json ... ```
            if "```json" in text:
                json_block = text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_block)
            elif "```" in text:
                # 检查是否只有普通代码块
                json_block = text.split("```")[1].split("```")[0].strip()
                return json.loads(json_block)
            
            # 尝试查找最外层的花括号
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                # 提取可能的JSON部分
                potential_json = text[start_idx:end_idx+1]
                
                # 尝试将单引号替换为双引号
                potential_json = potential_json.replace("'", '"')
                
                # 尝试解析
                return json.loads(potential_json)
            
            # 所有修复尝试都失败
            return {}
        except Exception:
            # 所有尝试都失败，返回空字典
            return {}

def validate_and_fix_data(data, news_title):
    """
    验证并修复分析结果数据，确保符合规范
    
    Args:
        data (dict): 待验证的分析结果数据
        news_title (str): 新闻标题，用于生成默认值
        
    Returns:
        dict: 修复后的数据
    """
    # 确保ID存在
    if "id" not in data or not data["id"]:
        data["id"] = hashlib.md5(news_title.encode()).hexdigest()
    
    # 确保坐标在有效范围内
    if "x" not in data or not isinstance(data["x"], (int, float)) or data["x"] < -180 or data["x"] > 180:
        data["x"] = random.uniform(73, 135)  # 中国大致经度范围
    
    if "y" not in data or not isinstance(data["y"], (int, float)) or data["y"] < -90 or data["y"] > 90:
        data["y"] = random.uniform(18, 53)   # 中国大致纬度范围
    
    # 检查是否为默认北京坐标，如果是则添加随机干扰
    DEFAULT_X = 116.4074
    DEFAULT_Y = 39.9042
    
    # 检查x坐标是否为默认北京经度，添加干扰值
    if abs(data["x"] - DEFAULT_X) < 0.0001:
        # 添加±0.05度的随机偏移（约±5公里）
        data["x"] = DEFAULT_X + random.uniform(-0.05, 0.05)
    
    # 检查y坐标是否为默认北京纬度，添加干扰值
    if abs(data["y"] - DEFAULT_Y) < 0.0001:
        # 添加±0.05度的随机偏移（约±5公里）
        data["y"] = DEFAULT_Y + random.uniform(-0.05, 0.05)
    
    # 确保类型存在
    if "type" not in data or not data["type"]:
        data["type"] = "社会新闻"
    
    # 确保标题存在
    if "title" not in data or not data["title"]:
        data["title"] = news_title
    
    # 确保introduction存在
    if "introduction" not in data or not data["introduction"]:
        data["introduction"] = f"关于{news_title}的热点新闻"
    
    # 确保传播速度在0-1范围内
    if "spreadSpeed" not in data or not isinstance(data["spreadSpeed"], (int, float)) or data["spreadSpeed"] < 0 or data["spreadSpeed"] > 1:
        data["spreadSpeed"] = random.uniform(0.3, 0.8)
    
    # 确保传播范围在0-1范围内
    if "spreadRange" not in data or not isinstance(data["spreadRange"], (int, float)) or data["spreadRange"] < 0 or data["spreadRange"] > 1:
        data["spreadRange"] = random.uniform(0.4, 0.9)
    
    # 确保参与人数在0-1范围内
    if "participants" not in data or not isinstance(data["participants"], (int, float)) or data["participants"] < 0 or data["participants"] > 1:
        data["participants"] = random.uniform(0.3, 0.7)
    
    # 验证和修复情绪数据
    if "emotion" not in data:
        data["emotion"] = {}
    
    if "schema" not in data["emotion"] or not isinstance(data["emotion"]["schema"], dict):
        data["emotion"]["schema"] = {
            "喜悦": 0.15,
            "期待": 0.15,
            "平和": 0.3,
            "惊讶": 0.1,
            "悲伤": 0.1,
            "愤怒": 0.1,
            "恐惧": 0.05,
            "厌恶": 0.05
        }
    else:
        # 确保所有情绪都存在
        for emotion in ["喜悦", "期待", "平和", "惊讶", "悲伤", "愤怒", "恐惧", "厌恶"]:
            if emotion not in data["emotion"]["schema"] or not isinstance(data["emotion"]["schema"][emotion], (int, float)):
                data["emotion"]["schema"][emotion] = 0.1
        
        # 确保情绪总和为1
        total = sum(data["emotion"]["schema"].values())
        if abs(total - 1) > 0.01:  # 允许0.01的误差
            # 归一化
            for emotion in data["emotion"]["schema"]:
                data["emotion"]["schema"][emotion] = data["emotion"]["schema"][emotion] / total
    
    if "rationale" not in data["emotion"] or not data["emotion"]["rationale"]:
        data["emotion"]["rationale"] = f"基于{news_title}新闻内容的情绪分析"
    
    # 验证和修复立场数据
    if "stance" not in data:
        data["stance"] = {}
    
    if "schema" not in data["stance"] or not isinstance(data["stance"]["schema"], dict):
        data["stance"]["schema"] = {
            "积极倡导": 0.15,
            "强烈反对": 0.05,
            "中立陈述": 0.4,
            "质疑探究": 0.1,
            "理性建议": 0.1,
            "情绪宣泄": 0.05,
            "观望等待": 0.1,
            "扩散传播": 0.05
        }
    else:
        # 确保所有立场都存在
        for stance in ["积极倡导", "强烈反对", "中立陈述", "质疑探究", "理性建议", "情绪宣泄", "观望等待", "扩散传播"]:
            if stance not in data["stance"]["schema"] or not isinstance(data["stance"]["schema"][stance], (int, float)):
                data["stance"]["schema"][stance] = 0.1
        
        # 确保立场总和为1
        total = sum(data["stance"]["schema"].values())
        if abs(total - 1) > 0.01:  # 允许0.01的误差
            # 归一化
            for stance in data["stance"]["schema"]:
                data["stance"]["schema"][stance] = data["stance"]["schema"][stance] / total
    
    if "rationale" not in data["stance"] or not data["stance"]["rationale"]:
        data["stance"]["rationale"] = f"基于{news_title}新闻内容的立场分析"
    
    # 验证和修复热度趋势数据
    if "heatTrend" not in data or not isinstance(data["heatTrend"], list) or len(data["heatTrend"]) < 3:
        # 生成最近7天的热度趋势
        now = datetime.now()
        data["heatTrend"] = []
        for i in range(7):
            date = (now - timedelta(days=6-i)).strftime("%Y-%m-%d")
            # 生成一个呈现上升趋势的热度
            if i < 3:
                value = random.uniform(0.1, 0.4)
            elif i < 5:
                value = random.uniform(0.4, 0.7)
            else:
                value = random.uniform(0.7, 1.0)
            data["heatTrend"].append({"date": date, "value": value})
    else:
        # 确保每个热度趋势都有日期和值
        for trend in data["heatTrend"]:
            if "date" not in trend or not trend["date"]:
                trend["date"] = datetime.now().strftime("%Y-%m-%d")
            if "value" not in trend or not isinstance(trend["value"], (int, float)) or trend["value"] < 0 or trend["value"] > 1:
                trend["value"] = random.uniform(0, 1)
    
    # 验证和修复时间线数据
    if "timeline" not in data or not isinstance(data["timeline"], list) or len(data["timeline"]) < 2:
        # 生成简单的时间线
        now = datetime.now()
        data["timeline"] = [
            {"date": (now - timedelta(days=3)).strftime("%Y-%m-%d"), "event": f"{news_title}事件开始受到关注"},
            {"date": (now - timedelta(days=2)).strftime("%Y-%m-%d"), "event": f"{news_title}相关讨论在社交媒体迅速扩散"},
            {"date": (now - timedelta(days=1)).strftime("%Y-%m-%d"), "event": f"{news_title}事件引发广泛热议，各方观点不一"}
        ]
    else:
        # 确保每个时间线都有日期和事件
        for timeline in data["timeline"]:
            if "date" not in timeline or not timeline["date"]:
                timeline["date"] = datetime.now().strftime("%Y-%m-%d")
            if "event" not in timeline or not timeline["event"]:
                timeline["event"] = f"{news_title}相关事件发展"
    
    # 验证和修复词云数据
    if "wordCloud" not in data or not isinstance(data["wordCloud"], list) or len(data["wordCloud"]) < 20:
        # 生成默认词云
        data["wordCloud"] = generate_default_wordcloud(news_title)
    else:
        # 确保词云数量至少50个
        if len(data["wordCloud"]) < 50:
            # 补充词云数量
            default_words = generate_default_wordcloud(news_title)
            existing_words = set(item["word"] for item in data["wordCloud"])
            for word in default_words:
                if word["word"] not in existing_words and len(data["wordCloud"]) < 50:
                    data["wordCloud"].append(word)
        
        # 确保每个词云项都有权重和词
        for word in data["wordCloud"]:
            if "weight" not in word or not isinstance(word["weight"], (int, float)) or word["weight"] <= 0:
                word["weight"] = random.uniform(1, 100)
            if "word" not in word or not word["word"]:
                word["word"] = f"关键词{random.randint(1, 100)}"
    
    return data

def generate_default_wordcloud(title):
    """
    生成默认词云数据
    
    Args:
        title (str): 新闻标题
        
    Returns:
        list: 词云数据列表
    """
    # 提取标题中可能的关键词
    title_words = title.split()
    
    # 常见的新闻相关词汇
    common_words = [
        "热点", "话题", "争议", "焦点", "社会", "政治", "经济", "文化", "科技", "教育",
        "健康", "环境", "关注", "讨论", "分析", "报道", "新闻", "媒体", "舆论", "观点",
        "声音", "态度", "立场", "评论", "反馈", "回应", "解读", "解释", "调查", "研究",
        "发展", "趋势", "变化", "影响", "作用", "意义", "价值", "结果", "原因", "背景",
        "事实", "真相", "信息", "数据", "内容", "事件", "人物", "组织", "机构", "公众"
    ]
    
    # 生成词云数据
    wordcloud = []
    
    # 添加标题词为高权重词
    for word in title_words:
        if len(word) > 1:  # 忽略单字符
            wordcloud.append({"word": word, "weight": random.uniform(70, 100)})
    
    # 添加常见词
    for word in common_words:
        if len(wordcloud) < 50:
            wordcloud.append({"word": word, "weight": random.uniform(10, 70)})
    
    # 如果还不够50个，添加随机词
    while len(wordcloud) < 50:
        word = f"词{random.randint(1, 100)}"
        wordcloud.append({"word": word, "weight": random.uniform(1, 20)})
    
    return wordcloud

def generate_fallback_data(news_title):
    """
    生成后备分析数据，当API调用失败时使用
    
    Args:
        news_title (str): 新闻标题
        
    Returns:
        dict: 生成的后备数据
    """
    # 生成唯一ID，基于标题和当前时间戳
    timestamp = datetime.now().isoformat()
    unique_id = f"{news_title}_{timestamp}"
    news_id = hashlib.md5(unique_id.encode()).hexdigest()
    
    # 创建一个包含所有必要字段的空数据结构
    fallback_data = {
        "id": news_id,  # 使用基于标题和时间戳的唯一ID
        "x": random.uniform(73, 135),  # 中国大致经度范围
        "y": random.uniform(18, 53),   # 中国大致纬度范围
        "type": "社会新闻",
        "title": news_title,
        "introduction": f"这是关于{news_title}的热点新闻。大模型token开销较大，服务器欠费，这是自动生成的替代内容,如果您想体验项目的完整功能，可以发送邮件至1073175768@qq.com",
        "spreadSpeed": random.uniform(0.3, 0.8),
        "spreadRange": random.uniform(0.4, 0.9),
        "participants": random.uniform(0.3, 0.7),
        "is_fallback": True,  # 标记为后备数据
        "emotion": {
            "schema": {
                "喜悦": 0.15,
                "期待": 0.15,
                "平和": 0.3,
                "惊讶": 0.1,
                "悲伤": 0.1,
                "愤怒": 0.1,
                "恐惧": 0.05,
                "厌恶": 0.05
            },
            "rationale": f"由于分析失败，系统自动生成了均衡的情绪分布。"
        },
        "stance": {
            "schema": {
                "积极倡导": 0.15,
                "强烈反对": 0.05,
                "中立陈述": 0.4,
                "质疑探究": 0.1,
                "理性建议": 0.1,
                "情绪宣泄": 0.05,
                "观望等待": 0.1,
                "扩散传播": 0.05
            },
            "rationale": f"由于分析失败，系统自动生成了中立为主的立场分布。"
        },
        "analyzed_at": timestamp  # 添加分析时间戳
    }
    
    # 生成热度趋势数据（最近7天）
    now = datetime.now()
    fallback_data["heatTrend"] = []
    for i in range(7):
        date = (now - timedelta(days=6-i)).strftime("%Y-%m-%d")
        # 生成一个呈现上升趋势的热度
        if i < 3:
            value = random.uniform(0.1, 0.4)
        elif i < 5:
            value = random.uniform(0.4, 0.7)
        else:
            value = random.uniform(0.7, 1.0)
        fallback_data["heatTrend"].append({"date": date, "value": value})
    
    # 生成时间线数据
    fallback_data["timeline"] = [
        {"date": (now - timedelta(days=3)).strftime("%Y-%m-%d"), "event": f"{news_title}事件开始受到关注"},
        {"date": (now - timedelta(days=2)).strftime("%Y-%m-%d"), "event": f"{news_title}相关讨论在社交媒体迅速扩散"},
        {"date": (now - timedelta(days=1)).strftime("%Y-%m-%d"), "event": f"{news_title}事件引发广泛热议，各方观点不一"}
    ]
    
    # 生成词云数据
    fallback_data["wordCloud"] = generate_default_wordcloud(news_title)
    
    return fallback_data
