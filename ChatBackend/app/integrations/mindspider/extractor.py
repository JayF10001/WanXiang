from __future__ import annotations

import json
import re
from typing import Dict, List, Tuple

from flask import current_app
from openai import OpenAI

from ...services.chat_service import ChatService


class MindSpiderTopicExtractor:
    """Vendored minimal topic extractor adapted to WanXiang LLM config."""

    @staticmethod
    def extract_keywords_and_summary(news_list: List[Dict], max_keywords: int = 100) -> Tuple[List[str], str]:
        if not news_list:
            return [], "今日暂无热点新闻。"

        news_text = MindSpiderTopicExtractor._build_news_summary(news_list)
        prompt = MindSpiderTopicExtractor._build_analysis_prompt(news_text, max_keywords)

        try:
            provider_config = ChatService.resolve_chat_provider(
                {
                    "model": ChatService.get_default_chat_model(),
                    "temperature": 0.2,
                    "enable_search": False,
                }
            )
            api_key = provider_config.get("api_key")
            base_url = provider_config.get("base_url")
            model = provider_config.get("model")
            if not api_key or not base_url:
                raise RuntimeError("未配置可用模型服务")

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个专业的新闻分析师，擅长从热点新闻中提取关键词和撰写分析总结。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.3,
            )
            result_text = response.choices[0].message.content
            keywords, summary = MindSpiderTopicExtractor._parse_analysis_result(result_text)
            return keywords[:max_keywords], summary
        except Exception as exc:
            current_app.logger.warning("MindSpider topic extraction fallback used: %s", exc)
            fallback_keywords = MindSpiderTopicExtractor._extract_simple_keywords(news_list)
            fallback_summary = f"今日共收集到 {len(news_list)} 条热点新闻，涵盖多个平台的热门话题。"
            return fallback_keywords[:max_keywords], fallback_summary

    @staticmethod
    def _build_news_summary(news_list: List[Dict]) -> str:
        items = []
        for index, news in enumerate(news_list, start=1):
            title = re.sub(r"[#@]", "", str(news.get("title") or "")).strip()
            source = str(news.get("source_name") or news.get("source") or "未知")
            if title:
                items.append(f"{index}. 【{source}】{title}")
        return "\n".join(items)

    @staticmethod
    def _build_analysis_prompt(news_text: str, max_keywords: int) -> str:
        news_count = len(news_text.splitlines())
        return f"""
请分析以下{news_count}条今日热点新闻，完成两个任务：

新闻列表：
{news_text}

任务1：提取关键词（最多{max_keywords}个）
- 提取能代表今日热点话题的关键词
- 关键词应该适合用于社交媒体平台搜索
- 优先选择热度高、讨论量大的话题
- 避免过于宽泛或过于具体的词汇

任务2：撰写新闻分析总结（150-300字）
- 简要概括今日热点新闻的主要内容
- 指出当前社会关注的重点话题方向
- 分析这些热点反映的社会现象或趋势
- 语言简洁明了，客观中性

请严格按照以下JSON格式输出：
```json
{{
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "summary": "今日新闻分析总结内容..."
}}
```
请直接输出JSON格式的结果，不要包含其他文字说明。
""".strip()

    @staticmethod
    def _parse_analysis_result(result_text: str) -> Tuple[List[str], str]:
        try:
            json_match = re.search(r"```json\s*(.*?)\s*```", str(result_text or ""), re.DOTALL)
            json_text = json_match.group(1) if json_match else str(result_text or "").strip()
            data = json.loads(json_text)
            keywords = []
            for keyword in data.get("keywords", []) or []:
                cleaned = str(keyword).strip()
                if cleaned and len(cleaned) > 1 and cleaned not in keywords:
                    keywords.append(cleaned)
            summary = str(data.get("summary") or "").strip()
            if len(summary) < 10:
                summary = "今日热点新闻涵盖多个领域，反映了当前社会的多元化关注点。"
            return keywords, summary
        except Exception:
            return [], "今日热点较为分散，建议结合关键词继续做平台级深挖。"

    @staticmethod
    def _extract_simple_keywords(news_list: List[Dict]) -> List[str]:
        keywords: List[str] = []
        for news in news_list:
            title = re.sub(r"[#@【】\[\]()（）]", " ", str(news.get("title") or ""))
            for token in title.split():
                cleaned = token.strip()
                if (
                    cleaned
                    and len(cleaned) > 1
                    and cleaned not in {"的", "了", "在", "和", "与", "或", "但", "是", "有", "被", "将", "已", "正在"}
                    and cleaned not in keywords
                ):
                    keywords.append(cleaned)
        return keywords[:10]

