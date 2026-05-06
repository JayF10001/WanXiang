import os
import json
import datetime
import traceback
import uuid
from bson import ObjectId
from flask import current_app
from openai import OpenAI
from ..extensions import db

try:
    from pydantic import BaseModel
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
try:
    from ChatBackend.celery_app import celery
except ImportError:
    from celery_app import celery
import logging
import re
import time
from .crawler_service import CrawlerService
from .news_service import NewsService
from .source_verifier_service import SourceVerifierService
from .time_verifier_service import TimeVerifierService
from .timeline_service import TimelineService

LOGGER = logging.getLogger(__name__)

# 添加自定义JSON编码器，处理datetime对象序列化
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

# 安全的JSON序列化辅助函数
def safe_json_data(data):
    """将任何无法序列化的对象转换为可序列化的格式"""
    if isinstance(data, dict):
        return {k: safe_json_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [safe_json_data(item) for item in data]
    elif isinstance(data, (datetime.datetime, datetime.date)):
        return data.isoformat()
    elif isinstance(data, ObjectId):
        return str(data)
    elif HAS_PYDANTIC and isinstance(data, BaseModel):
        # Pydantic v2: 递归转换为 JSON 兼容的 dict
        return safe_json_data(data.model_dump(mode="json"))
    else:
        return data

class ChatService:
    """
    Service for handling chat operations including PR strategy generation using LLM
    """
    
    @staticmethod
    def get_repo_root():
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

    @staticmethod
    def resolve_prompt_file_path(config_value):
        if not config_value:
            return None

        if os.path.isabs(config_value):
            return config_value

        repo_root = ChatService.get_repo_root()
        chatbackend_root = os.path.abspath(os.path.join(repo_root, 'ChatBackend'))
        candidates = [
            os.path.join(repo_root, config_value),
            os.path.join(chatbackend_root, config_value),
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

        # Return repo-relative candidate for better error messages even if missing
        return candidates[0]

    @staticmethod
    def load_prompt_file(config_key, default_path, label):
        configured_path = current_app.config.get(config_key, default_path)
        resolved_path = ChatService.resolve_prompt_file_path(configured_path)
        if not resolved_path:
            current_app.logger.warning(f"{label} 未配置")
            return None

        try:
            with open(resolved_path, 'r', encoding='utf-8') as file:
                content = file.read().strip()
                if not content:
                    current_app.logger.warning(f"{label} 文件为空: {resolved_path}")
                    return None
                return content
        except FileNotFoundError:
            current_app.logger.warning(f"{label} 文件不存在: {resolved_path}")
            return None
        except Exception as exc:
            current_app.logger.error(f"无法加载{label}: {exc}")
            return None

    @staticmethod
    def get_prompt_template():
        """Load combined system prompt and skill rules for chat generation."""
        system_prompt = ChatService.load_prompt_file(
            'SYSTEM_PROMPT_FILE',
            '系统提示词.md',
            '系统提示词'
        )
        skill_prompt = ChatService.load_prompt_file(
            'SKILL_PROMPT_FILE',
            'skill.md',
            '技能规则'
        )

        sections = []
        if system_prompt:
            sections.append(f"[系统角色与回答规范]\n{system_prompt}")
        if skill_prompt:
            sections.append(f"[能力与规则补充]\n{skill_prompt}")

        if sections:
            return "\n\n".join(sections)

        legacy_prompt = ChatService.load_prompt_file(
            'PR_STRATEGY_PROMPT_FILE',
            'templates/pr_strategy_prompt.txt',
            '旧版提示词'
        )
        if legacy_prompt:
            current_app.logger.warning("系统提示词.md 和 skill.md 均缺失，已回退到旧版 pr_strategy_prompt.txt")
            return legacy_prompt

        current_app.logger.warning("未找到任何可用提示词文件，将回退到内置默认提示词")
        return None

    @staticmethod
    def get_default_chat_model():
        return current_app.config.get('QWEN_MODEL') or os.getenv('QWEN_MODEL') or 'qwen3-max'

    @staticmethod
    def get_qwen_fallback_model():
        return current_app.config.get('QWEN_FALLBACK_MODEL') or os.getenv('QWEN_FALLBACK_MODEL') or 'qwen-max'

    @staticmethod
    def normalize_prompt_text(content):
        if not isinstance(content, str):
            return ''
        return re.sub(r'\s+', '', content).replace('*', '')

    @staticmethod
    def is_legacy_system_prompt(content):
        normalized = ChatService.normalize_prompt_text(content)
        return (
            normalized.startswith('基于AI对话的公关策略生成器') or
            normalized.startswith('基于AI对话的舆情分析与公关策略生成器-交互提示词')
        )

    @staticmethod
    def is_greeting_like_input(text):
        normalized = str(text or '').strip().lower()
        if not normalized:
            return False

        greeting_inputs = {
            '你好', '您好', 'hi', 'hello', 'hey', '在吗', '有人吗',
            '嗨', '哈喽', 'hello?', 'hi?', '你好啊', '您好啊'
        }
        return normalized in greeting_inputs

    @staticmethod
    def is_generic_ambiguous_input(text):
        normalized = str(text or '').strip().lower()
        if not normalized:
            return False

        generic_inputs = {
            '帮我看看', '帮我分析', '怎么处理', '怎么看', '啥情况', '发生了什么'
        }
        return normalized in generic_inputs

    @staticmethod
    def build_greeting_response(messages):
        user_messages = [
            m for m in (messages or [])
            if m.get('role') == 'user' and str(m.get('content') or '').strip()
        ]
        if not user_messages:
            return None

        latest_user_message = str(user_messages[-1].get('content') or '').strip()
        if not ChatService.is_greeting_like_input(latest_user_message):
            return None

        substantive_user_messages = [
            m for m in user_messages
            if not ChatService.is_greeting_like_input(m.get('content'))
        ]
        if substantive_user_messages:
            return None

        return "您好，请告诉我您想研判的具体事件、主体或传播线索，我可以直接帮您做舆情分析。"

    @staticmethod
    def build_structured_first_turn_context(messages, settings=None):
        settings = settings or {}
        user_messages = [m for m in messages if m.get('role') == 'user' and str(m.get('content') or '').strip()]
        if len(user_messages) != 1:
            return None

        latest_user_message = str(user_messages[-1].get('content') or '').strip()
        if ChatService.is_greeting_like_input(latest_user_message):
            return (
                "【首轮轻量引导上下文】\n"
                "- 当前用户输入属于寒暄/问候，不构成具体舆情任务。\n"
                "- 本轮不要展开近期热点示例、通用分析框架或大段模板化研判。\n"
                "- 请只用 1 到 2 句话简短回应，并主动收集最关键任务信息。\n"
                "- 优先引导用户补充：事件主体、发生了什么、在哪个平台/媒体发酵。\n"
                "- 不要使用标题、列表、示例、项目符号、引用块或分段模板。\n"
                "- 不要说“系统已识别”“为避免无效交互”这类生硬措辞。\n"
                "- 语气保持专业、自然、克制，像顾问式接待，而不是表单引导。"
            )

        lower_input = latest_user_message.lower()
        current_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        detected_input_type = '事件描述/主题关键词'
        if 'http://' in lower_input or 'https://' in lower_input:
            detected_input_type = 'URL/链接线索'
        elif len(latest_user_message) <= 12:
            detected_input_type = '短关键词/主题词'

        industry_hints = []
        keyword_map = {
            '汽车': ['汽车', '新能源', '智驾', '车企', '比亚迪', '特斯拉'],
            '科技互联网': ['科技', 'ai', '人工智能', '互联网', '芯片', '手机', '平台'],
            '消费品牌': ['食品', '饮料', '奶茶', '咖啡', '零食', '快消', '美妆'],
            '金融资本市场': ['a股', '港股', '股市', '证券', '基金', '银行', '金融'],
            '政务公共事件': ['局长', '政府', '公安', '通报', '干部', '区委', '市监'],
        }
        for label, keywords in keyword_map.items():
            if any(keyword in latest_user_message for keyword in keywords):
                industry_hints.append(label)

        if not industry_hints:
            industry_hints.append('待模型结合上下文判断')

        extra_background = ChatService.build_news_background_context(latest_user_message)
        background_block = f"\n{extra_background}\n" if extra_background else "\n"

        if ChatService.is_generic_ambiguous_input(latest_user_message):
            return (
                "【首轮模糊任务引导上下文】\n"
                f"- 当前时间: {current_time}\n"
                f"- 对话阶段: 首轮分析\n"
                f"- 当前模型: {settings.get('model') or ChatService.get_default_chat_model()}\n"
                f"- 用户原始输入: {latest_user_message}\n"
                f"- 输入类型判断: {detected_input_type}\n"
                f"- 可能涉及行业/领域: {', '.join(industry_hints)}\n"
                "- 输出要求:\n"
                "  1. 可以先给一句非常简短的分析方向判断，但不要展开完整报告式结构。\n"
                "  2. 重点是收集任务关键信息，而不是罗列通用框架。\n"
                "  3. 最多提出 3 个最关键澄清问题，优先问主体、事件、传播平台。\n"
                "  4. 不要虚构近期热点，不要输出与用户无关的示例新闻。\n"
                "  5. 不要写成公文式模板，不要使用过多项目符号。"
                f"{background_block}"
            )

        return (
            "【首轮结构化背景上下文】\n"
            f"- 当前时间: {current_time}\n"
            f"- 对话阶段: 首轮分析\n"
            f"- 当前模型: {settings.get('model') or ChatService.get_default_chat_model()}\n"
            f"- 用户原始输入: {latest_user_message}\n"
            f"- 输入类型判断: {detected_input_type}\n"
            f"- 可能涉及行业/领域: {', '.join(industry_hints)}\n"
            "- 输出要求:\n"
            "  1. 先给出基于当前信息的专业分析，不要只做寒暄。\n"
            "  2. 明确区分【已知事实】【合理推断】【待补充信息】。\n"
            "  3. 若信息不足，可在给出初步判断后补充 1-3 个最关键澄清问题。\n"
            "  4. 优先从舆情传播、风险级别、利益相关方、回应策略四个维度组织回答。\n"
            "  5. 避免泛泛而谈，尽量输出可执行建议。"
            f"{background_block}"
        )

    @staticmethod
    def build_news_background_context(user_input):
        text = str(user_input or '').strip()
        if not text:
            return None

        if ChatService.is_greeting_like_input(text):
            return None

        lower_text = text.lower()
        likely_ambiguous = len(text) <= 12 or ChatService.is_generic_ambiguous_input(text)
        if not likely_ambiguous:
            return None

        try:
            news_items = NewsService.get_current_news_cached(limit=5)
            if not news_items:
                collect_result = NewsService.collect_hot_news()
                if collect_result.get('status') == 'success':
                    news_items = NewsService.get_current_news_cached(limit=5)
            if not news_items:
                return None

            lines = []
            for idx, item in enumerate(news_items[:5], start=1):
                title = str(item.get('title') or '').strip()
                intro = str(item.get('introduction') or '').strip()
                platform = str(item.get('platform') or item.get('type') or '综合').strip()
                if not title:
                    continue
                summary = intro[:60] if intro else '暂无简介'
                lines.append(f"{idx}. [{platform}] {title} - {summary}")

            if not lines:
                return None

            return (
                "【近期可参考背景热搜】\n"
                "用户当前输入较模糊，可优先结合以下近期热点线索，判断其是否可能与用户意图相关；"
                "若仍无法判断，需先给出初步分析框架，再请用户补充最关键的信息。\n"
                + "\n".join(lines)
            )
        except Exception as exc:
            current_app.logger.warning(f"构建新闻背景上下文失败: {exc}")
            return None

    @staticmethod
    def extract_first_url(text):
        matched = re.search(r"https?://[^\s]+", str(text or ""))
        return str(matched.group(0)).strip() if matched else ""

    @staticmethod
    def parse_recommendation_context_message(content):
        text = str(content or "").strip()
        if not text.startswith("【推荐热点上下文】"):
            return None

        data = {
            "title": "",
            "platform": "",
            "source_url": "",
            "published_at": "",
            "summary": "",
        }
        field_map = {
            "标题": "title",
            "来源平台": "platform",
            "原始链接": "source_url",
            "更新时间": "published_at",
            "热点摘要": "summary",
        }
        for raw_line in text.splitlines():
            line = str(raw_line or "").strip()
            if "：" not in line:
                continue
            key, value = line.split("：", 1)
            target_key = field_map.get(key.strip())
            if target_key:
                data[target_key] = value.strip()
        return data if data["title"] or data["source_url"] else None

    @staticmethod
    def extract_recommendation_context(messages):
        for item in reversed(messages or []):
            if item.get("role") != "system":
                continue
            parsed = ChatService.parse_recommendation_context_message(item.get("content"))
            if parsed:
                return parsed
        return None

    @staticmethod
    def build_recommendation_fact_context(messages):
        recommendation_context = ChatService.extract_recommendation_context(messages) or {}
        if not recommendation_context:
            return None

        title = str(recommendation_context.get("title") or "").strip()
        platform = str(recommendation_context.get("platform") or "").strip()
        source_url = str(recommendation_context.get("source_url") or "").strip()
        published_at = str(recommendation_context.get("published_at") or "").strip()
        summary = str(recommendation_context.get("summary") or "").strip()
        if not any([title, platform, source_url, published_at, summary]):
            return None

        lines = [
            "【推荐链路已知事实】",
            "- 以下内容来自首页/推荐卡片本身，属于当前系统已经确认的热榜线索，应优先纳入【已知事实】。",
            "- 若外部抓取结果与这里冲突，需明确说明“推荐链路线索”和“外部页面证据”的差异，不要直接忽略推荐链路已知事实。",
        ]
        if title:
            lines.append(f"- 热点标题: {title}")
        if platform:
            lines.append(f"- 热榜来源平台: {platform}")
        if published_at:
            lines.append(f"- 推荐链路更新时间: {published_at}")
        if source_url:
            lines.append(f"- 推荐链路原始链接: {source_url}")
        if summary:
            lines.append(f"- 推荐链路热点摘要: {summary}")
        return "\n".join(lines)

    @staticmethod
    def parse_analysis_prompt_context(text):
        content = str(text or "").strip()
        if not content:
            return None

        context = {
            "title": "",
            "platform": "",
            "source_url": "",
            "published_at": "",
        }
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if line.startswith("标题："):
                context["title"] = line.split("：", 1)[1].strip()
            elif line.startswith("来源平台："):
                context["platform"] = line.split("：", 1)[1].strip()
            elif line.startswith("原始链接："):
                context["source_url"] = line.split("：", 1)[1].strip()
            elif line.startswith("更新时间："):
                context["published_at"] = line.split("：", 1)[1].strip()

        if not context["title"]:
            matched = re.search(r"帮我分析这个热点[:：]\s*(.+)$", content)
            if matched:
                context["title"] = matched.group(1).strip()
        if not context["source_url"]:
            context["source_url"] = ChatService.extract_first_url(content)
        return context if context["title"] or context["source_url"] else None

    @staticmethod
    def should_fetch_fact_context(messages):
        user_messages = [
            m for m in (messages or [])
            if m.get('role') == 'user' and str(m.get('content') or '').strip()
        ]
        if not user_messages:
            return False

        latest_user_message = str(user_messages[-1].get('content') or '').strip()
        recommendation_context = ChatService.extract_recommendation_context(messages)
        parsed_prompt_context = ChatService.parse_analysis_prompt_context(latest_user_message)
        if not latest_user_message or ChatService.is_greeting_like_input(latest_user_message):
            return False
        if recommendation_context or parsed_prompt_context:
            return True
        if ChatService.extract_first_url(latest_user_message):
            return True
        if len(latest_user_message) <= 4:
            return False

        event_signals = (
            '爆', '火', '事故', '热搜', '回应', '通报', '争议', '处罚', '翻车',
            '坠毁', '相撞', '外交部', '微博', '抖音', '百度', '知乎', '头条',
        )
        if any(token in latest_user_message for token in event_signals):
            return True

        return 6 <= len(latest_user_message) <= 60

    @staticmethod
    def build_crawler_fact_context(messages, fact_payload=None):
        fact_payload = fact_payload or ChatService.get_auto_fact_context_payload(messages)
        if not fact_payload:
            return None

        crawl_result = fact_payload.get("crawl_result") or {}
        summary = str(crawl_result.get('summary') or '').strip()
        excerpt = str(crawl_result.get('content_excerpt') or '').strip()
        final_url = str(crawl_result.get('final_url') or '').strip()
        source_name = str(crawl_result.get('source_name') or '').strip()
        published_at = str(crawl_result.get('published_at') or '').strip()
        relevance_score = float(crawl_result.get('relevance_score') or 0)
        if not summary and not excerpt:
            return None

        lines = [
            "【自动抓取的外部事实线索】",
            "- 以下内容来自标题相关页面抓取结果，应优先作为【已知事实】写入回答开头。",
            "- 回答时必须明确区分：页面可见事实、基于事实的推断、尚待确认的信息。",
            "- 若已抓到来源、时间、机制、数值、查询渠道等具体信息，至少引用其中两项，不要忽略后只输出泛化常识。",
            "- 若页面材料已经解释原因或机制，不要再把同一问题当作主要未知点；只能补充“仍待官方进一步确认/交叉验证”的边界说明。",
        ]
        if source_name:
            lines.append(f"- 来源站点: {source_name}")
        if published_at:
            lines.append(f"- 页面时间: {published_at}")
        if final_url:
            lines.append(f"- 原始链接: {final_url}")
        if relevance_score > 0:
            lines.append(f"- 相关性评分: {relevance_score:.2f}")
        if summary:
            lines.append(f"- 页面摘要: {summary}")
        if excerpt:
            lines.append(f"- 正文片段: {excerpt}")
        return "\n".join(lines)

    @staticmethod
    def get_auto_fact_context_payload(messages):
        if not ChatService.should_fetch_fact_context(messages):
            return None

        user_messages = [
            m for m in (messages or [])
            if m.get('role') == 'user' and str(m.get('content') or '').strip()
        ]
        if not user_messages:
            return None

        latest_user_message = str(user_messages[-1].get('content') or '').strip()
        structured_prompt_context = ChatService.parse_analysis_prompt_context(latest_user_message) or {}
        recommendation_context = ChatService.extract_recommendation_context(messages) or {}
        source_url = (
            structured_prompt_context.get("source_url")
            or recommendation_context.get("source_url")
            or ChatService.extract_first_url(latest_user_message)
        )
        title = (
            structured_prompt_context.get("title")
            or recommendation_context.get("title")
            or (latest_user_message.replace(source_url, '').strip() if source_url else latest_user_message)
        )
        platform_hint = (
            structured_prompt_context.get("platform")
            or recommendation_context.get("platform")
            or ""
        )
        if not title and not source_url:
            return None

        try:
            crawl_result = CrawlerService.crawl_news_context(
                title=title or latest_user_message,
                source_url=source_url,
                platform_hint=platform_hint,
                max_candidates=5,
                force_refresh=False,
            )
        except Exception as exc:
            current_app.logger.warning(f"自动抓取事实材料失败: {exc}")
            return None

        if not crawl_result.get('success'):
            return None

        if not any([
            str(crawl_result.get('summary') or '').strip(),
            str(crawl_result.get('content_excerpt') or '').strip(),
        ]):
            return None

        return {
            "latest_user_message": latest_user_message,
            "title": title or latest_user_message,
            "source_url": source_url,
            "platform_hint": platform_hint,
            "recommendation_context": recommendation_context,
            "crawl_result": crawl_result,
        }

    @staticmethod
    def build_verification_fact_context(messages, fact_payload=None):
        fact_payload = fact_payload or ChatService.get_auto_fact_context_payload(messages)
        if not fact_payload:
            return None

        recommendation_context = fact_payload.get("recommendation_context") or {}
        crawl_result = fact_payload.get("crawl_result") or {}
        title = str(fact_payload.get("title") or "").strip()
        final_url = str(crawl_result.get("final_url") or fact_payload.get("source_url") or "").strip()
        source_name = str(crawl_result.get("source_name") or "").strip()
        platform_hint = str(fact_payload.get("platform_hint") or "").strip()
        published_at = str(crawl_result.get("published_at") or "").strip()
        hotspot_time = str(recommendation_context.get("published_at") or "").strip()
        summary = str(crawl_result.get("summary") or "").strip()
        excerpt = str(crawl_result.get("content_excerpt") or "").strip()

        source_verification = SourceVerifierService.verify(
            url=final_url,
            source_name=source_name,
            platform=platform_hint,
        )
        time_verification = TimeVerifierService.verify(
            title=title,
            published_at=published_at,
            extracted_text=f"{summary}\n{excerpt}",
            hotspot_time=hotspot_time,
        )

        documents = []
        if recommendation_context:
            documents.append(
                {
                    "title": str(recommendation_context.get("title") or title),
                    "content": str(recommendation_context.get("summary") or ""),
                    "source": str(recommendation_context.get("platform") or "推荐链路"),
                    "published_at": str(recommendation_context.get("published_at") or ""),
                }
            )
        if summary or excerpt:
            documents.append(
                {
                    "title": title,
                    "content": summary or excerpt,
                    "source": source_name or final_url or "外部页面",
                    "published_at": published_at,
                }
            )
        timeline_result = TimelineService.extract(documents=documents)

        lines = [
            "【来源与时效校验】",
            "- 以下内容用于帮助你判断抓取材料能否直接进入【已知事实】。",
            f"- 来源可信度: {source_verification.get('credibility_level')} ({source_verification.get('source_type')})",
            f"- 可信度说明: {source_verification.get('reason')}",
            f"- 时效性结论: {time_verification.get('reason')}",
        ]
        if time_verification.get("is_old_news_recirculation") is True:
            lines.append("- 校验提醒: 当前材料疑似旧闻翻炒或时间错配，不得将其直接作为当前热点的唯一事实依据。")
        elif time_verification.get("is_recent") is False:
            lines.append("- 校验提醒: 当前材料更适合作为背景资料使用，回答时需明确其与当前热点的时间差。")

        timeline_items = timeline_result.get("timeline") or []
        if timeline_items:
            lines.append("- 可参考时间线:")
            for item in timeline_items[:3]:
                time_text = str(item.get("time") or "时间待核实").strip()
                event_text = str(item.get("event") or "").strip()
                source_text = str(item.get("source") or "").strip()
                actor_text = str(item.get("actor") or "").strip()
                detail = f"{time_text} - {event_text}"
                if actor_text:
                    detail += f"（主体: {actor_text}）"
                if source_text:
                    detail += f" [{source_text}]"
                lines.append(f"  - {detail}")

        lines.append("- 回答要求: 只有高/中可信且时间基本一致的材料，才优先写入【已知事实】；其余内容应转入【待核实信息】或【分析判断】。")
        return "\n".join(lines)

    @staticmethod
    def filter_client_visible_messages(messages):
        """Hide internal system messages from client-facing payloads."""
        visible_messages = []
        for item in messages or []:
            if item.get('role') == 'system':
                continue
            visible_messages.append(item)
        return visible_messages

    @staticmethod
    def sanitize_session_for_client(session):
        """Return a client-safe copy of a session payload."""
        if not session:
            return session

        sanitized = dict(session)
        if 'messages' in sanitized:
            sanitized['messages'] = ChatService.filter_client_visible_messages(
                sanitized.get('messages', [])
            )
        return sanitized

    @staticmethod
    def references_recent_video(text):
        normalized = str(text or '').strip().lower()
        if not normalized:
            return False

        direct_tokens = (
            '视频', '该视频', '这个视频', '刚才上传', '刚上传', '这段视频', '这条视频',
            '视频里', '画面', '镜头', '音频', '配音', '字幕', '片段',
            '图片', '这张图', '这个图', '截图', '图里', '图中',
            '录音', '语音', '这段音频', '这个音频',
            '素材', '文件', '这批文件', '刚上传的内容', '上面这些素材'
        )
        if any(token in normalized for token in direct_tokens):
            return True

        follow_up_tokens = ('分析', '解读', '总结', '继续', '补充', '判断', '研判')
        return len(normalized) <= 24 and any(token in normalized for token in follow_up_tokens)

    @staticmethod
    def _extract_video_analysis_snapshot(message):
        if not isinstance(message, dict):
            return None
        route = str(message.get('route') or '')
        if route not in ('video_multimodal_analysis', 'multimodal_analysis'):
            return None

        items = message.get('items') if isinstance(message.get('items'), list) else []
        if items:
            first_item = items[0] if isinstance(items[0], dict) else {}
            return {
                'summary': str(message.get('overall_summary') or message.get('summary') or '').strip(),
                'risk_level': str(message.get('overall_risk_level') or message.get('risk_level') or '').strip(),
                'final_model': str(message.get('final_model') or message.get('finalModel') or '').strip(),
                'fallback_level': message.get('fallback_level') if message.get('fallback_level') is not None else message.get('fallbackLevel'),
                'degrade_reason': str(message.get('degrade_reason') or message.get('degradeReason') or '').strip(),
                'items': [
                    {
                        'file_name': str(item.get('file_name') or item.get('fileName') or '').strip(),
                        'modality': str(item.get('modality') or '').strip(),
                        'summary': str(item.get('summary') or '').strip(),
                        'sentiment': str(item.get('sentiment') or '').strip(),
                        'risk_level': str(item.get('risk_level') or item.get('riskLevel') or '').strip(),
                    }
                    for item in items if isinstance(item, dict)
                ],
                'cross_file_signals': [str(item).strip() for item in (message.get('cross_file_signals') or message.get('crossFileSignals') or []) if str(item).strip()],
            }

        summary = ''
        analysis_items = message.get('analysis') or []
        if analysis_items:
            summary = str(analysis_items[0] or '').strip()

        content = str(message.get('content') or '')
        if not summary:
            matched = re.search(r"\*\*核心摘要\*\*:\s*(.+)", content)
            if matched:
                summary = matched.group(1).strip()

        sentiment = ''
        risk_level = ''
        sentiment_match = re.search(r"\*\*情感极性\*\*:\s*(.+)", content)
        if sentiment_match:
            sentiment = sentiment_match.group(1).strip()
        risk_match = re.search(r"\*\*风险等级\*\*:\s*(.+)", content)
        if risk_match:
            risk_level = risk_match.group(1).strip()

        return {
            'summary': summary,
            'sentiment': sentiment,
            'risk_level': risk_level,
            'final_model': str(message.get('final_model') or message.get('finalModel') or '').strip(),
            'fallback_level': message.get('fallback_level') if message.get('fallback_level') is not None else message.get('fallbackLevel'),
            'degrade_reason': str(message.get('degrade_reason') or message.get('degradeReason') or '').strip(),
            'items': [],
            'cross_file_signals': [],
        }

    @staticmethod
    def build_recent_video_context(messages):
        latest_user_message = ''
        for item in reversed(messages or []):
            if item.get('role') == 'user' and str(item.get('content') or '').strip():
                latest_user_message = str(item.get('content') or '').strip()
                break
        if not ChatService.references_recent_video(latest_user_message):
            return None

        latest_video_snapshot = None
        for item in reversed(messages or []):
            latest_video_snapshot = ChatService._extract_video_analysis_snapshot(item)
            if latest_video_snapshot:
                break
        if not latest_video_snapshot:
            return None

        lines = [
            "【当前会话最近多模态分析结果】",
            "- 以下内容来自当前会话最近一轮已完成的多模态分析，应视为本轮追问的已知上下文，而不是缺失信息。",
            "- 当用户使用“这张图 / 这段音频 / 这个视频 / 这批文件 / 刚上传的内容”等指代时，默认优先指向这里。",
        ]
        if latest_video_snapshot.get('summary'):
            lines.append(f"- 综合摘要: {latest_video_snapshot['summary']}")
        if latest_video_snapshot.get('risk_level'):
            lines.append(f"- 综合风险等级: {latest_video_snapshot['risk_level']}")
        for item in latest_video_snapshot.get('items') or []:
            file_name = item.get('file_name') or '未知文件'
            modality = item.get('modality') or 'media'
            summary = item.get('summary') or ''
            risk_level = item.get('risk_level') or ''
            sentiment = item.get('sentiment') or ''
            detail_parts = [f"{file_name}（{modality}）"]
            if summary:
                detail_parts.append(f"摘要: {summary}")
            if sentiment:
                detail_parts.append(f"情感: {sentiment}")
            if risk_level:
                detail_parts.append(f"风险: {risk_level}")
            lines.append(f"- 文件结果: {'；'.join(detail_parts)}")
        for signal in latest_video_snapshot.get('cross_file_signals') or []:
            lines.append(f"- 跨文件信号: {signal}")
        if latest_video_snapshot.get('final_model'):
            lines.append(f"- 分析模型: {latest_video_snapshot['final_model']}")
        if latest_video_snapshot.get('fallback_level') not in (None, '', 0, '0'):
            lines.append(f"- 降级层级: {latest_video_snapshot['fallback_level']}")
        if latest_video_snapshot.get('degrade_reason'):
            lines.append(f"- 降级原因: {latest_video_snapshot['degrade_reason']}")
        lines.append("- 回答要求: 优先基于上述多模态分析结果继续回答；若还需要补充信息，只补真正缺失的细节，不要再把“未提供媒体内容”当作主要结论。")
        return "\n".join(lines)

    @staticmethod
    def prepare_messages_for_generation(messages, settings=None, debug_mode=False):
        settings = settings or {}
        system_prompt = ChatService.get_prompt_template()
        if not system_prompt:
            system_prompt = (
                "你是专业的企业舆情分析与公关策略顾问。"
                "你的回答必须专业、结构化、可执行，并优先围绕事件概述、舆情判断、风险点、传播链路、应对建议展开。"
            )

        normalized_messages = []
        inserted_system_prompt = False
        for item in messages:
            role = item.get('role')
            if role == 'system':
                if not inserted_system_prompt:
                    normalized_messages.append({'role': 'system', 'content': system_prompt})
                    inserted_system_prompt = True
                continue
            normalized_messages.append(item)

        if not inserted_system_prompt:
            normalized_messages.insert(0, {'role': 'system', 'content': system_prompt})

        # DEBUG MODE: Skip all context injection
        if debug_mode:
            return normalized_messages

        recent_video_context = ChatService.build_recent_video_context(normalized_messages)

        first_turn_context = None if recent_video_context else ChatService.build_structured_first_turn_context(normalized_messages, settings)
        if first_turn_context:
            normalized_messages.insert(1, {'role': 'system', 'content': first_turn_context})

        if recent_video_context:
            insert_index = 2 if first_turn_context else 1
            normalized_messages.insert(insert_index, {'role': 'system', 'content': recent_video_context})

        recommendation_fact_context = ChatService.build_recommendation_fact_context(normalized_messages)
        if recommendation_fact_context:
            insert_index = 3 if first_turn_context and recent_video_context else 2 if (first_turn_context or recent_video_context) else 1
            normalized_messages.insert(insert_index, {'role': 'system', 'content': recommendation_fact_context})

        fact_payload = ChatService.get_auto_fact_context_payload(normalized_messages)

        fact_context = ChatService.build_crawler_fact_context(normalized_messages, fact_payload=fact_payload)
        if fact_context:
            insert_index = 3 if first_turn_context and recommendation_fact_context else 2 if (first_turn_context or recommendation_fact_context) else 1
            normalized_messages.insert(insert_index, {'role': 'system', 'content': fact_context})

        verification_context = ChatService.build_verification_fact_context(normalized_messages, fact_payload=fact_payload)
        if verification_context:
            insert_index = 4 if first_turn_context and recommendation_fact_context and fact_context else 3 if sum(bool(item) for item in [first_turn_context, recommendation_fact_context, fact_context]) >= 2 else 2 if any([first_turn_context, recommendation_fact_context, fact_context]) else 1
            normalized_messages.insert(insert_index, {'role': 'system', 'content': verification_context})

        return normalized_messages

    @staticmethod
    def should_retry_with_qwen_fallback(error):
        error_text = str(error).lower()
        retry_signals = [
            'model_not_found',
            'does not exist',
            'no access to it',
            'not support',
            'invalid_request_error',
        ]
        return any(signal in error_text for signal in retry_signals)
    
    @staticmethod
    def create_chat_session(user_id):
        """Create a new chat session for a user"""
        try:
            # Get the system prompt
            system_prompt = ChatService.get_prompt_template()
            if not system_prompt:
                system_prompt = """**基于AI对话的公关策略生成器**

你是一位顶级的整合策略顾问和AI助手，拥有深厚的行业分析能力和丰富的策略规划经验。通过引导式对话理解用户需求，结合实时热点分析，自动生成专业、全面的公关与商业整合策略方案。

你有能力通过互联网搜索实时信息。当涉及到公司背景信息、最新舆情事件和行业动态时，请主动利用搜索功能获取最新信息，提供更准确的分析。"""
            
            # Create initial message array with system prompt
            messages = [{"role": "system", "content": system_prompt}]
            default_model = ChatService.get_default_chat_model()
            
            # Insert into database
            result = db.chat_sessions.insert_one({
                'user_id': ObjectId(user_id),
                'messages': messages,
                'created_at': datetime.datetime.utcnow(),
                'updated_at': datetime.datetime.utcnow(),
                'title': "新对话", # Default title
                'title_locked': False,
                'settings': {
                    'model': default_model,
                    'temperature': 0.2,
                    'enable_search': True
                }
            })
            
            return str(result.inserted_id)
        except Exception as e:
            current_app.logger.error(f"创建聊天会话失败: {str(e)}")
            traceback.print_exc()
            return None
    
    @staticmethod
    def get_chat_sessions(user_id):
        """Get all chat sessions for a user"""
        try:
            sessions = list(db.chat_sessions.find(
                {'user_id': ObjectId(user_id)},
                {'messages': 0} # Exclude messages to reduce payload
            ).sort('updated_at', -1))
            
            # Convert ObjectId to string
            for session in sessions:
                session['_id'] = str(session['_id'])
                session['user_id'] = str(session['user_id'])
            
            return sessions
        except Exception as e:
            current_app.logger.error(f"获取聊天会话列表失败: {str(e)}")
            traceback.print_exc()
            return []
    
    @staticmethod
    def get_chat_session(session_id):
        """Get a chat session by ID"""
        try:
            session = db.chat_sessions.find_one({'_id': ObjectId(session_id)})
            if not session:
                return None
            
            # Convert ObjectId to string
            session['_id'] = str(session['_id'])
            session['user_id'] = str(session['user_id'])
            
            return session
        except Exception as e:
            current_app.logger.error(f"获取聊天会话失败: {str(e)}")
            traceback.print_exc()
            return None
    
    @staticmethod
    def update_session_title(session_id, title, manual=True):
        """Update a chat session title"""
        try:
            update_fields = {
                'title': title,
                'updated_at': datetime.datetime.utcnow()
            }
            if manual:
                update_fields['title_locked'] = True

            db.chat_sessions.update_one(
                {'_id': ObjectId(session_id)},
                {'$set': update_fields}
            )
            return True
        except Exception as e:
            current_app.logger.error(f"更新聊天会话标题失败: {str(e)}")
            traceback.print_exc()
            return False
    
    @staticmethod
    def update_session_settings(session_id, settings):
        """Update a chat session settings"""
        try:
            db.chat_sessions.update_one(
                {'_id': ObjectId(session_id)},
                {'$set': {'settings': settings, 'updated_at': datetime.datetime.utcnow()}}
            )
            return True
        except Exception as e:
            current_app.logger.error(f"更新聊天会话设置失败: {str(e)}")
            traceback.print_exc()
            return False
    
    @staticmethod
    def delete_chat_session(session_id):
        """Delete a chat session"""
        try:
            db.chat_sessions.delete_one({'_id': ObjectId(session_id)})
            return True
        except Exception as e:
            current_app.logger.error(f"删除聊天会话失败: {str(e)}")
            traceback.print_exc()
            return False

    @staticmethod
    def build_message_payload(role, content, timestamp=None, extra_fields=None):
        payload = {
            'id': str(uuid.uuid4()),
            'role': role,
            'content': content,
            'timestamp': timestamp or datetime.datetime.utcnow().isoformat(),
        }
        if extra_fields:
            payload.update(extra_fields)
        return payload

    @staticmethod
    def ensure_session_message_ids(session_id, messages):
        normalized_messages = []
        updated = False

        for item in messages or []:
            normalized_item = dict(item or {})
            if not normalized_item.get('id'):
                normalized_item['id'] = str(uuid.uuid4())
                updated = True
            normalized_messages.append(normalized_item)

        if updated:
            try:
                db.chat_sessions.update_one(
                    {'_id': ObjectId(session_id)},
                    {
                        '$set': {
                            'messages': normalized_messages,
                            'updated_at': datetime.datetime.utcnow(),
                        }
                    }
                )
            except Exception as exc:
                current_app.logger.warning(f"回写历史消息 ID 失败: session_id={session_id}, error={exc}")

        return normalized_messages
    
    @staticmethod
    def add_message(session_id, role, content, retry_count=3, extra_fields=None):
        """Add a message to a chat session with retry mechanism"""
        current_app.logger.debug(f"添加消息到会话 {session_id}, 角色: {role}, 内容长度: {len(content)}")
        
        # 重试计数器
        attempt = 0
        last_error = None
        
        while attempt < retry_count:
            try:
                # Get the first user message to set as title if this is the first user message
                is_first_user_message = False
                title_locked = False
                session = db.chat_sessions.find_one({'_id': ObjectId(session_id)})
                if session:
                    user_messages = [m for m in session.get('messages', []) if m.get('role') == 'user']
                    is_first_user_message = len(user_messages) == 0 and role == 'user'
                    title_locked = bool(session.get('title_locked'))
                else:
                    current_app.logger.error(f"会话 {session_id} 不存在")
                    return False
            
                # Add message to session with timestamp for better tracking
                message_payload = ChatService.build_message_payload(role, content, extra_fields=extra_fields)
                result = db.chat_sessions.update_one(
                    {'_id': ObjectId(session_id)},
                    {
                        '$push': {'messages': message_payload},
                        '$set': {'updated_at': datetime.datetime.utcnow()}
                    }
                )
            
                # If this is the first user message, update the title
                if is_first_user_message and content and not title_locked:
                    title = content[:30] + ('...' if len(content) > 30 else '')
                    ChatService.update_session_title(session_id, title, manual=False)
            
                if result.modified_count > 0:
                    current_app.logger.debug(f"成功添加消息到会话 {session_id}")
                    return True
                else:
                    current_app.logger.warning(f"消息添加操作未修改任何文档，会话ID: {session_id}")
                    # 检查会话是否仍然存在，可能在我们尝试添加消息时被删除
                    session_exists = db.chat_sessions.count_documents({'_id': ObjectId(session_id)})
                    if not session_exists:
                        current_app.logger.error(f"无法添加消息：会话 {session_id} 不存在")
                        return False
                    
                    # 会话存在但未修改，可能是重复消息或其他问题
                    attempt += 1
                    # 如果已达到最大重试次数，仍然返回True(假定消息已存在)
                    if attempt >= retry_count:
                        current_app.logger.warning(f"达到最大重试次数({retry_count})，假定消息已存在于会话中")
                        return True
                    
                    # 短暂等待后重试
                    time.sleep(0.5)
            except Exception as e:
                last_error = e
                current_app.logger.error(f"添加消息失败 (尝试 {attempt+1}/{retry_count}): {str(e)}")
                traceback.print_exc()
                attempt += 1
                
                # 如果还有重试机会，等待一段时间后重试
                if attempt < retry_count:
                    time.sleep(0.5 * attempt)  # 使用指数退避策略
                else:
                    break
        
        # 所有重试都失败
        current_app.logger.error(f"添加消息到会话 {session_id} 失败，已尝试 {retry_count} 次: {str(last_error)}")
        return False

    @staticmethod
    def get_message_by_id(session_id, message_id):
        """Get a single message from a session by message ID."""
        try:
            session = db.chat_sessions.find_one(
                {'_id': ObjectId(session_id)},
                {'messages': 1}
            )
            if not session:
                return None

            for item in session.get('messages', []) or []:
                if str(item.get('id') or '') == str(message_id or ''):
                    return dict(item)
            return None
        except Exception as e:
            current_app.logger.error(f"按 ID 获取消息失败: session_id={session_id}, message_id={message_id}, error={e}")
            traceback.print_exc()
            return None

    @staticmethod
    def update_message_fields(session_id, message_id, fields):
        """Update a persisted session message by message ID."""
        try:
            normalized_fields = dict(fields or {})
            if not normalized_fields:
                return False

            update_fields = {
                f"messages.$.{key}": value
                for key, value in normalized_fields.items()
            }
            update_fields["updated_at"] = datetime.datetime.utcnow()

            result = db.chat_sessions.update_one(
                {
                    '_id': ObjectId(session_id),
                    'messages.id': str(message_id),
                },
                {'$set': update_fields}
            )
            return result.modified_count > 0
        except Exception as e:
            current_app.logger.error(
                f"更新消息字段失败: session_id={session_id}, message_id={message_id}, fields={list((fields or {}).keys())}, error={e}"
            )
            traceback.print_exc()
            return False
    
    @staticmethod
    def get_chat_history(session_id):
        """Get chat history for a session"""
        try:
            session = db.chat_sessions.find_one({'_id': ObjectId(session_id)})
            if not session:
                return []
            
            return ChatService.ensure_session_message_ids(session_id, session.get('messages', []))
        except Exception as e:
            current_app.logger.error(f"获取聊天历史失败: {str(e)}")
            traceback.print_exc()
            return []

    @staticmethod
    def add_tool_result(session_id, tool_name, result):
        """存储工具执行结果到会话"""
        try:
            # 确保 Pydantic 对象等无法直接序列化的内容被转换
            serializable_result = safe_json_data(result)
            db.chat_sessions.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {f"tool_results.{tool_name}": {
                    "executed": True,
                    "executed_at": datetime.datetime.utcnow(),
                    "result": serializable_result
                }}}
            )
        except Exception as e:
            current_app.logger.error(f"存储工具结果失败: {e}")

    @staticmethod
    def get_tool_result(session_id, tool_name):
        """获取工具执行结果"""
        session = ChatService.get_chat_session(session_id)
        return session.get('tool_results', {}).get(tool_name, {}).get('result')

    @staticmethod
    def resolve_chat_provider(settings=None):
        """Resolve provider configuration for chat generation.

        Provider selection:
        1. If ACTIVE_PROVIDER env var is set, use that provider directly.
        2. Otherwise, fall back to QWEN -> OpenRouter chain.
        """
        settings = settings or {}
        requested_model = settings.get('model')

        # Check ACTIVE_PROVIDER first
        active_provider = (
            current_app.config.get('ACTIVE_PROVIDER') or
            os.getenv('ACTIVE_PROVIDER') or
            ''
        ).strip().lower()

        # --- Active provider short-circuit ---
        if active_provider == 'deepseek':
            deepseek_api_key = (
                current_app.config.get('DEEPSEEK_API_KEY') or
                os.getenv('DEEPSEEK_API_KEY')
            )
            deepseek_base_url = (
                current_app.config.get('DEEPSEEK_BASE_URL') or
                os.getenv('DEEPSEEK_BASE_URL') or
                'https://api.deepseek.com'
            )
            deepseek_model = (
                current_app.config.get('DEEPSEEK_MODEL') or
                os.getenv('DEEPSEEK_MODEL') or
                'deepseek-chat'
            )
            if deepseek_api_key:
                return {
                    'provider': 'deepseek',
                    'api_key': deepseek_api_key,
                    'base_url': deepseek_base_url,
                    'model': deepseek_model,
                }

        if active_provider == 'openrouter':
            openrouter_api_key = (
                current_app.config.get('OPENROUTER_API_KEY') or
                os.getenv('OPENROUTER_API_KEY')
            )
            openrouter_base_url = (
                current_app.config.get('OPENROUTER_BASE_URL') or
                os.getenv('OPENROUTER_BASE_URL') or
                'https://openrouter.ai/api/v1'
            )
            openrouter_model = (
                requested_model or
                current_app.config.get('LLM_MODEL') or
                os.getenv('LLM_MODEL') or
                'deepseek/deepseek-chat-v3-0324:online'
            )
            if openrouter_api_key:
                return {
                    'provider': 'openrouter',
                    'api_key': openrouter_api_key,
                    'base_url': openrouter_base_url,
                    'model': openrouter_model,
                }

        if active_provider == 'qwen':
            qwen_api_key = (
                current_app.config.get('QWEN_API_KEY') or
                os.getenv('QWEN_API_KEY')
            )
            qwen_base_url = (
                current_app.config.get('QWEN_BASE_URL') or
                os.getenv('QWEN_BASE_URL') or
                'https://dashscope.aliyuncs.com/compatible-mode/v1'
            )
            qwen_default_model = ChatService.get_default_chat_model()
            if qwen_api_key:
                return {
                    'provider': 'qwen',
                    'api_key': qwen_api_key,
                    'base_url': qwen_base_url,
                    'model': qwen_default_model,
                }

        # --- Default fallback chain (QWEN -> OpenRouter) ---
        qwen_default_model = ChatService.get_default_chat_model()

        def should_use_qwen_default(model_name):
            if not model_name:
                return True
            normalized = str(model_name).strip().lower()
            legacy_models = {
                'deepseek/deepseek-chat-v3-0324:online',
                'qwen-plus',
                'qwen-turbo',
            }
            return (
                normalized.startswith('deepseek/') or
                normalized.startswith('openai/') or
                normalized in legacy_models
            )

        qwen_api_key = current_app.config.get('QWEN_API_KEY') or os.getenv('QWEN_API_KEY')
        qwen_base_url = current_app.config.get('QWEN_BASE_URL') or os.getenv('QWEN_BASE_URL') or 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        qwen_model = qwen_default_model if should_use_qwen_default(requested_model) else requested_model

        if qwen_api_key:
            return {
                'provider': 'qwen',
                'api_key': qwen_api_key,
                'base_url': qwen_base_url,
                'model': qwen_model,
            }

        openrouter_api_key = current_app.config.get('OPENROUTER_API_KEY') or os.getenv('OPENROUTER_API_KEY')
        openrouter_base_url = current_app.config.get('OPENROUTER_BASE_URL') or os.getenv('OPENROUTER_BASE_URL') or 'https://openrouter.ai/api/v1'
        openrouter_model = requested_model or current_app.config.get('LLM_MODEL') or os.getenv('LLM_MODEL') or 'deepseek/deepseek-chat-v3-0324:online'

        if openrouter_api_key:
            return {
                'provider': 'openrouter-fallback',
                'api_key': openrouter_api_key,
                'base_url': openrouter_base_url,
                'model': openrouter_model,
            }

        return {
            'provider': 'unconfigured',
            'api_key': None,
            'base_url': None,
            'model': qwen_model,
        }
    
    @staticmethod
    def get_model_response(messages, settings=None):
        """
        Get a response from the AI model
        Non-streaming version for simple requests
        """
        greeting_response = ChatService.build_greeting_response(messages)
        if greeting_response:
            return greeting_response

        if settings is None:
            settings = {
                'model': ChatService.get_default_chat_model(),
                'temperature': 0.2,
                'enable_search': True
            }
        
        try:
            messages = ChatService.prepare_messages_for_generation(messages, settings)
            provider_config = ChatService.resolve_chat_provider(settings)
            provider = provider_config['provider']
            api_key = provider_config['api_key']
            base_url = provider_config['base_url']
            model = provider_config['model']

            if not api_key or not base_url:
                current_app.logger.error("Chat provider is not configured.")
                return "很抱歉，聊天模型服务尚未配置，请检查 .env.local 中的 QWEN_API_KEY / QWEN_BASE_URL / QWEN_MODEL。"

            current_app.logger.info(
                f"Chat completion provider={provider}, base_url={base_url}, model={model}, "
                f"search_enabled={settings.get('enable_search', True)}"
            )

            # Create OpenAI client
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=90.0  # 设置较长的超时时间
            )
            
            # Setup extra body for optional features like web search
            extra_body = {}
            
            # Add web search if enabled
            if settings.get('enable_search', True):
                extra_body['enable_search'] = True
            
            # Call the API
            response = None
            used_model = model
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=settings.get('temperature', 0.2),
                    extra_body=extra_body
                )
            except Exception as first_error:
                qwen_fallback_model = ChatService.get_qwen_fallback_model()
                should_retry = (
                    provider == 'qwen' and
                    model != qwen_fallback_model and
                    ChatService.should_retry_with_qwen_fallback(first_error)
                )
                if not should_retry:
                    raise
                current_app.logger.warning(
                    f"Primary qwen model unavailable, retrying with fallback model={qwen_fallback_model}: {first_error}"
                )
                used_model = qwen_fallback_model
                response = client.chat.completions.create(
                    model=qwen_fallback_model,
                    messages=messages,
                    temperature=settings.get('temperature', 0.2),
                    extra_body=extra_body
                )
            
            # Log token usage
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                ChatService.log_token_usage(
                    used_model,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens
                )
            
            return response.choices[0].message.content
        except Exception as e:
            current_app.logger.error(
                f"Chat completion failed provider={provider_config.get('provider')}, "
                f"base_url={provider_config.get('base_url')}, model={provider_config.get('model')}: {str(e)}"
            )
            traceback.print_exc()
            return f"模型服务调用失败（provider={provider_config.get('provider')}）: {str(e)}"
    
    @staticmethod
    def stream_model_response(messages, settings=None):
        """
        Stream a response from the AI model using Server-Sent Events (SSE).
        Yields dictionaries representing SSE events:
        {'event': 'message', 'data': 'content chunk'}
        {'event': 'thinking', 'data': {'status': '...', 'message': '...'}} # Example, adjust as needed
        {'event': 'error', 'data': {'error': '...'}}
        """
        greeting_response = ChatService.build_greeting_response(messages)
        if greeting_response:
            yield {'event': 'ready', 'data': {'status': 'ready'}}
            yield {'event': 'message', 'data': greeting_response}
            return

        default_settings = {
            'model': ChatService.get_default_chat_model(),
            'temperature': 0.2,
            'enable_search': True # Default search setting
        }
        if settings is None:
            settings = default_settings
        else:
            # Merge user settings with defaults, user settings take precedence
            merged_settings = default_settings.copy()
            merged_settings.update(settings)
            settings = merged_settings

        try:
            messages = ChatService.prepare_messages_for_generation(messages, settings)
            provider_config = ChatService.resolve_chat_provider(settings)
            api_key = provider_config['api_key']
            base_url = provider_config['base_url']
            model = provider_config['model']
            provider = provider_config['provider']

            if not api_key or not base_url:
                current_app.logger.error("API Key or Base URL is not configured.")
                yield {'event': 'error', 'data': {'error': 'API 服务未配置'}}
                return

            current_app.logger.info(
                f"Streaming API Request: provider={provider}, Model={model}, BaseURL={base_url}, "
                f"SearchEnabled={settings.get('enable_search')}, Messages={len(messages)}"
            )

            # 从配置获取超时设置，默认为60秒
            timeout = current_app.config.get('LLM_REQUEST_TIMEOUT') or os.getenv('LLM_REQUEST_TIMEOUT') or 90.0
            try:
                timeout = float(timeout)
            except (ValueError, TypeError):
                timeout = 90.0
                current_app.logger.warning(f"Invalid LLM_REQUEST_TIMEOUT value, using default: {timeout}")
                
            client = OpenAI(
                api_key=api_key, 
                base_url=base_url,
                timeout=timeout  # 设置较长的超时时间
            )

            # 从配置或环境变量获取参数
            max_tokens = current_app.config.get('MAX_TOKENS') or os.getenv('MAX_TOKENS') or 2048
            try:
                max_tokens = int(max_tokens)
            except (ValueError, TypeError):
                max_tokens = 2048
                current_app.logger.warning(f"Invalid MAX_TOKENS value, using default: {max_tokens}")

            # Prepare request parameters
            request_params = {
                'messages': messages,
                'temperature': settings.get('temperature'),
                'stream': True,
            }
            
            # 只有在不为0的情况下添加 max_tokens 参数
            if max_tokens > 0:
                request_params['max_tokens'] = max_tokens
                current_app.logger.debug(f"Setting max_tokens={max_tokens}")

            # 处理额外参数，通过配置指定不同供应商的特殊参数
            provider_specific_params = current_app.config.get('PROVIDER_SPECIFIC_PARAMS', {})
            # 从环境变量获取额外参数，JSON格式
            env_specific_params = os.getenv('PROVIDER_SPECIFIC_PARAMS')
            if env_specific_params:
                try:
                    import json
                    env_params = json.loads(env_specific_params)
                    if isinstance(env_params, dict):
                        provider_specific_params.update(env_params)
                except Exception as e:
                    current_app.logger.error(f"Failed to parse PROVIDER_SPECIFIC_PARAMS: {e}")
            
            # 添加额外参数到请求
            for key, value in provider_specific_params.items():
                # 确保不添加datetime类型的参数
                if not isinstance(value, (datetime.datetime, datetime.date)):
                    request_params[key] = value
                else:
                    # 如果是日期时间类型，转换为ISO格式字符串
                    request_params[key] = value.isoformat()
                current_app.logger.debug(f"Adding provider-specific parameter: {key}={value}")

            # 添加 web_search 参数到 extra_body
            extra_body = {}
            if settings.get('enable_search', False):
                # 根据 OpenRouter 文档设置 web_search 参数
                web_search_config = current_app.config.get('WEB_SEARCH_CONFIG', {'enable': True})
                # 从环境变量获取替代配置
                env_web_search = os.getenv('WEB_SEARCH_CONFIG')
                if env_web_search:
                    try:
                        web_search_config = json.loads(env_web_search)
                    except Exception as e:
                        current_app.logger.error(f"Failed to parse WEB_SEARCH_CONFIG: {e}")
                
                # 确保web_search_config中没有datetime对象
                web_search_config = safe_json_data(web_search_config)
                extra_body['web_search'] = web_search_config
                current_app.logger.debug(f"Web search enabled with config: {web_search_config}")
                
                # 确保extra_body中没有datetime对象
                extra_body = safe_json_data(extra_body)
                request_params['extra_body'] = extra_body
                
            # 最后检查所有请求参数，确保不含datetime对象
            request_params = safe_json_data(request_params)

            # 发送就绪事件，告知前端准备接收数据
            yield {'event': 'ready', 'data': {'status': 'ready'}}

            # 创建响应流
            current_app.logger.debug(f"Starting API stream request with params: {request_params}")
            used_model = model
            request_params['model'] = model
            try:
                response = client.chat.completions.create(**request_params)
            except Exception as first_error:
                qwen_fallback_model = ChatService.get_qwen_fallback_model()
                should_retry = (
                    provider == 'qwen' and
                    model != qwen_fallback_model and
                    ChatService.should_retry_with_qwen_fallback(first_error)
                )
                if not should_retry:
                    raise
                current_app.logger.warning(
                    f"Primary qwen stream model unavailable, retrying with fallback model={qwen_fallback_model}: {first_error}"
                )
                used_model = qwen_fallback_model
                request_params['model'] = qwen_fallback_model
                response = client.chat.completions.create(**request_params)
            current_app.logger.debug("API stream response started.")

            # 使用更小的缓冲区，更频繁地发送数据
            buffer = ""
            buffer_max_size = 5  # 更小的缓冲区，每5个字符发送一次，提高实时性
            chunk_count = 0
            last_send_time = time.time()
            max_interval = 0.1  # 100ms最大间隔，确保实时性
            
            try:
                for chunk in response:
                    chunk_count += 1
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content is not None:
                            content_chunk = delta.content
                            buffer += content_chunk
                            
                            current_time = time.time()
                            # 只要达到缓冲区大小，是首个响应块，或者达到最大时间间隔，立即发送
                            if (len(buffer) >= buffer_max_size or 
                                chunk_count <= 2 or 
                                (current_time - last_send_time) >= max_interval):
                                # 发送当前缓冲区内容
                                yield {'event': 'message', 'data': buffer}
                                if chunk_count % 50 == 0:  # 减少日志频率
                                    current_app.logger.debug(f"Yielding message chunk {chunk_count}: {buffer[:30]}...")
                                buffer = ""  # 清空缓冲区
                                last_send_time = current_time
            except Exception as e:
                error_message = f"Error processing API response chunk: {str(e)}"
                current_app.logger.error(error_message, exc_info=True)
                yield {'event': 'error', 'data': safe_json_data({'error': error_message})}
                # 退出循环，但会继续执行后续代码发送剩余缓冲区

            # 发送剩余的缓冲区内容
            if buffer:
                yield {'event': 'message', 'data': buffer}

            current_app.logger.debug(f"API stream finished after {chunk_count} chunks.")
            # The 'done' event will be sent by the calling generate() function in chat.py

        except Exception as e:
            error_message = (
                f"Streaming API call failed (provider={provider_config.get('provider')}, "
                f"model={provider_config.get('model')}): {str(e)}"
            )
            current_app.logger.error(error_message, exc_info=True)
            # Yield an error event
            yield {'event': 'error', 'data': safe_json_data({'error': error_message})}
    
    @staticmethod
    def log_token_usage(model, prompt_tokens, completion_tokens, total_tokens):
        """Log token usage for billing and monitoring"""
        try:
            db.token_usage.insert_one({
                'timestamp': datetime.datetime.utcnow(),
                'model': model,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens
            })
        except Exception as e:
            current_app.logger.error(f"记录Token使用量失败: {str(e)}")
            traceback.print_exc()
            return None
    
    @staticmethod
    @celery.task(name='chat.save_response', bind=True, max_retries=5)
    def save_response_task(self, session_id, role, content):
        """Celery task to save message to database asynchronously with retry mechanism"""
        try:
            current_app.logger.debug(f"异步保存消息到会话 {session_id}, 角色: {role}, 内容长度: {len(content)}")
            
            # 验证会话存在
            session = db.chat_sessions.find_one({'_id': ObjectId(session_id)})
            if not session:
                current_app.logger.error(f"异步保存消息失败: 会话 {session_id} 不存在")
                return False
                
            # 添加消息到会话
            message_payload = ChatService.build_message_payload(
                role,
                content,
                extra_fields={'saved_by': 'async_task'}
            )
            result = db.chat_sessions.update_one(
                {'_id': ObjectId(session_id)},
                {
                    '$push': {'messages': message_payload},
                    '$set': {'updated_at': datetime.datetime.utcnow()}
                }
            )
            
            if result.modified_count > 0:
                current_app.logger.debug(f"异步保存消息成功: session_id={session_id}, role={role}")
                return True
            else:
                current_app.logger.warning(f"异步保存消息操作未修改任何文档: session_id={session_id}")
                
                # 检查消息是否已存在（可能是重复保存）
                existing_msg_count = db.chat_sessions.count_documents({
                    '_id': ObjectId(session_id),
                    'messages': {'$elemMatch': {'role': role, 'content': content}}
                })
                
                if existing_msg_count > 0:
                    current_app.logger.debug(f"消息已存在于会话中，无需重复保存: session_id={session_id}")
                    return True
                else:
                    current_app.logger.error(f"异步保存消息失败: 会话存在但消息未被添加: session_id={session_id}")
                    return False
            
        except Exception as e:
            current_app.logger.error(f"异步保存消息时发生错误: {str(e)}")
            traceback.print_exc()
            
            # 使用Celery内置的重试机制
            try:
                # 使用指数退避策略，最多重试5次
                retry_count = self.request.retries
                countdown = 2 ** retry_count  # 1, 2, 4, 8, 16秒
                self.retry(exc=e, countdown=countdown, max_retries=5)
            except self.MaxRetriesExceededError:
                current_app.logger.error(f"异步保存消息重试次数已达上限: session_id={session_id}")
                return False
                
            return False

    @staticmethod
    @celery.task(name='chat.analyze_hot_news')
    def analyze_hot_news(vertical_domain):
        """
        Analyze hot news for a specific industry domain
        This is a Celery task that performs background analysis
        """
        try:
            current_app.logger.info(f"开始分析 {vertical_domain} 领域的热点新闻...")
            
            # Get recent news from the database
            recent_news = list(db.processed_news.find(
                {"type": {"$regex": vertical_domain, "$options": "i"}},
                {"_id": 0}
            ).sort("rank", 1).limit(5))
            
            # If no domain-specific news found, get general hot news
            if not recent_news:
                recent_news = list(db.processed_news.find(
                    {},
                    {"_id": 0}
                ).sort("rank", 1).limit(5))
            
            # Format news for analysis
            news_text = "\n\n".join([
                f"标题: {news.get('title', '')}\n"
                f"简介: {news.get('introduction', '')}\n"
                f"类型: {news.get('type', '')}\n"
                f"平台: {news.get('platform', '')}"
                for news in recent_news
            ])
            
            # System prompt for analysis
            system_prompt = """你是一位专业的舆情分析助手。请分析以下热点新闻，提取关键信息:
1. 行业风险点: 这些新闻反映了哪些潜在的行业风险?
2. 整体舆情态势: 当前舆论环境的总体特点和倾向
3. 核心关注点: 公众和媒体最关注的问题
4. 最需要关注的事件: 最值得关注的热点事件概述

请简明扼要地提供分析结果，每部分不超过100字。"""
            
            # Create messages for analysis
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下{vertical_domain}行业的热点新闻:\n\n{news_text}"}
            ]
            
            # Get analysis from model
            analysis = ChatService.get_model_response(messages)
            
            # Store analysis result
            result_id = db.news_analysis.insert_one({
                'vertical_domain': vertical_domain,
                'analysis': analysis,
                'news_count': len(recent_news),
                'created_at': datetime.datetime.utcnow()
            }).inserted_id
            
            return {
                'status': 'success',
                'analysis_id': str(result_id),
                'vertical_domain': vertical_domain
            }
            
        except Exception as e:
            current_app.logger.error(f"热点新闻分析失败: {str(e)}")
            traceback.print_exc()
            return {
                'status': 'error',
                'error': str(e),
                'vertical_domain': vertical_domain
            }
    
    @staticmethod
    def get_latest_analysis(vertical_domain):
        """Get the latest analysis for a domain"""
        try:
            analysis = db.news_analysis.find_one(
                {'vertical_domain': vertical_domain},
                {'_id': 0}
            )
            
            if not analysis:
                return None
                
            return analysis
        except Exception as e:
            current_app.logger.error(f"获取分析结果失败: {str(e)}")
            traceback.print_exc()
            return None
    
    @staticmethod
    @celery.task(name='chat.generate_pr_strategy')
    def generate_pr_strategy(session_id, strategy_data):
        """
        Generate PR strategy based on collected information
        This is a Celery task that performs background strategy generation
        """
        try:
            current_app.logger.info(f"开始生成公关策略，会话ID: {session_id}")
            session = ChatService.get_chat_session(session_id)
            settings = session.get('settings', {}) if session else None

            from .strategy_service import StrategyService

            result = StrategyService.generate_strategy(session_id, strategy_data, settings=settings)
            if str(result.get('status') or '').lower() != 'success':
                raise RuntimeError(str(result.get('error') or '策略生成失败'))

            return result
            
        except Exception as e:
            current_app.logger.error(f"生成公关策略失败: {str(e)}")
            traceback.print_exc()
            
            # Add error message to chat session
            error_msg = f"很抱歉，在生成策略时遇到了问题: {str(e)}"
            ChatService.add_message(session_id, 'assistant', error_msg)
            
            return {
                'status': 'error',
                'error': str(e),
                'session_id': session_id
            }
 
