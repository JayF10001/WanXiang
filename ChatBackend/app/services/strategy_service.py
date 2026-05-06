from __future__ import annotations

import datetime
import json
import os
import re
import traceback
import uuid
from typing import Any, Dict, List, Optional

from flask import current_app
from pydantic import BaseModel, ConfigDict, Field
from pymongo import MongoClient

from ..utils.data_utils import safe_json_data


def get_db():
    try:
        from ..extensions import db

        if hasattr(db, "db") and db.db is not None:
            return db.db
    except Exception:
        pass

    mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "mongodb://localhost:27017/"
    db_name = os.getenv("DB_NAME", "chatdb")
    client = MongoClient(mongo_uri)
    return client[db_name]


class StrategyMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = "传播策略方案"
    strategyId: str = ""
    generatedAt: str = ""
    version: str = "1.0"
    confidenceLevel: float = 0.75
    scenario: str = ""
    keywords: List[str] = Field(default_factory=list)


class StrategyExecutiveSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    situation: str = ""
    coreGoal: str = ""
    summary: str = ""
    priorityActions: List[str] = Field(default_factory=list)


class StrategyAudience(BaseModel):
    model_config = ConfigDict(extra="ignore")
    audience: str = ""
    concern: str = ""
    objective: str = ""


class StrategyMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    audience: str = ""
    message: str = ""
    goal: str = ""
    tone: str = ""


class StrategyAudienceAndMessaging(BaseModel):
    model_config = ConfigDict(extra="ignore")
    primaryAudiences: List[StrategyAudience] = Field(default_factory=list)
    keyMessages: List[StrategyMessage] = Field(default_factory=list)
    spokespersonGuidance: List[str] = Field(default_factory=list)


class StrategyActionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action: str = ""
    owner: str = ""
    timing: str = ""
    objective: str = ""
    deliverable: str = ""


class StrategyActionPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    immediateActions: List[StrategyActionItem] = Field(default_factory=list)
    shortTermActions: List[StrategyActionItem] = Field(default_factory=list)
    midTermActions: List[StrategyActionItem] = Field(default_factory=list)
    longTermActions: List[StrategyActionItem] = Field(default_factory=list)


class StrategyRiskItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    risk: str = ""
    probability: int = 50
    impact: int = 50
    mitigation: str = ""


class StrategyRisksAndGuardrails(BaseModel):
    model_config = ConfigDict(extra="ignore")
    riskLevel: str = "中"
    keyRisks: List[StrategyRiskItem] = Field(default_factory=list)
    redLines: List[str] = Field(default_factory=list)


class StrategyIndicator(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    target: str = ""
    frequency: str = ""


class StrategyMonitoringAndEvaluation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    indicators: List[StrategyIndicator] = Field(default_factory=list)
    checkpoints: List[str] = Field(default_factory=list)


class StrategyAppendix(BaseModel):
    model_config = ConfigDict(extra="ignore")
    assumptions: List[str] = Field(default_factory=list)
    inputSummary: Dict[str, Any] = Field(default_factory=dict)
    evidenceSummary: List[str] = Field(default_factory=list)


class StrategyDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")
    meta: StrategyMeta = Field(default_factory=StrategyMeta)
    executiveSummary: StrategyExecutiveSummary = Field(default_factory=StrategyExecutiveSummary)
    audienceAndMessaging: StrategyAudienceAndMessaging = Field(default_factory=StrategyAudienceAndMessaging)
    actionPlan: StrategyActionPlan = Field(default_factory=StrategyActionPlan)
    risksAndGuardrails: StrategyRisksAndGuardrails = Field(default_factory=StrategyRisksAndGuardrails)
    monitoringAndEvaluation: StrategyMonitoringAndEvaluation = Field(default_factory=StrategyMonitoringAndEvaluation)
    appendix: StrategyAppendix = Field(default_factory=StrategyAppendix)


class StrategyService:
    @staticmethod
    def _extract_json_payload(text: str) -> Dict[str, Any]:
        normalized = str(text or "").strip()
        if not normalized:
            return {}

        candidates = [normalized]
        fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", normalized, flags=re.S)
        candidates.extend(fenced)

        start = normalized.find("{")
        end = normalized.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(normalized[start:end + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
        return {}

    @staticmethod
    def _normalize_strategy_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = safe_json_data(payload)
        if not isinstance(normalized, dict):
            return {}

        appendix = normalized.get("appendix")
        if isinstance(appendix, dict):
            input_summary = appendix.get("inputSummary")
            if isinstance(input_summary, dict):
                appendix["inputSummary"] = {str(key): str(value) for key, value in input_summary.items()}
            assumptions = appendix.get("assumptions")
            if isinstance(assumptions, list):
                appendix["assumptions"] = [str(item) for item in assumptions]
            evidence_summary = appendix.get("evidenceSummary")
            if isinstance(evidence_summary, list):
                appendix["evidenceSummary"] = [str(item) for item in evidence_summary]

        executive = normalized.get("executiveSummary")
        if isinstance(executive, dict) and isinstance(executive.get("priorityActions"), list):
            executive["priorityActions"] = [str(item) for item in executive.get("priorityActions", [])]

        audience = normalized.get("audienceAndMessaging")
        if isinstance(audience, dict) and isinstance(audience.get("spokespersonGuidance"), list):
            audience["spokespersonGuidance"] = [str(item) for item in audience.get("spokespersonGuidance", [])]

        risks = normalized.get("risksAndGuardrails")
        if isinstance(risks, dict) and isinstance(risks.get("redLines"), list):
            risks["redLines"] = [str(item) for item in risks.get("redLines", [])]

        monitoring = normalized.get("monitoringAndEvaluation")
        if isinstance(monitoring, dict) and isinstance(monitoring.get("checkpoints"), list):
            monitoring["checkpoints"] = [str(item) for item in monitoring.get("checkpoints", [])]

        return normalized

    @staticmethod
    def initialize_db():
        try:
            db = get_db()
            if "strategy_results" not in db.list_collection_names():
                db.create_collection("strategy_results")
            db.strategy_results.create_index(
                "strategy_id",
                unique=True,
                partialFilterExpression={"strategy_id": {"$exists": True, "$type": "string"}},
            )
            db.strategy_results.create_index("session_id")
            db.strategy_results.create_index([("created_at", -1)])
            return True
        except Exception as exc:
            current_app.logger.warning(f"初始化策略服务索引失败: {exc}")
            return False

    @staticmethod
    def link_strategy_to_session(session_id: str, strategy_id: str) -> bool:
        try:
            from bson.objectid import ObjectId

            db = get_db()
            filters = [{"_id": session_id}]
            try:
                filters.append({"_id": ObjectId(session_id)})
            except Exception:
                pass
            db.chat_sessions.update_one(
                {"$or": filters},
                {"$set": {"strategy_id": strategy_id, "updated_at": datetime.datetime.utcnow()}},
            )
            return True
        except Exception as exc:
            current_app.logger.warning(f"回写 strategy_id 到会话失败: {exc}")
            return False

    @staticmethod
    def _build_strategy_card_summary(strategy_json: Dict[str, Any]) -> str:
        executive = strategy_json.get("executiveSummary", {}) if isinstance(strategy_json.get("executiveSummary"), dict) else {}
        summary = str(executive.get("summary") or "").strip()
        if summary:
            return summary
        actions = executive.get("priorityActions") if isinstance(executive.get("priorityActions"), list) else []
        cleaned_actions = [str(item).strip() for item in actions if str(item).strip()]
        if cleaned_actions:
            return "；".join(cleaned_actions[:3])
        return "策略方案已生成"

    @staticmethod
    def save_strategy_card_message(session_id: str, strategy_id: str, strategy_json: Dict[str, Any]) -> bool:
        try:
            from .chat_service import ChatService

            meta = strategy_json.get("meta", {}) if isinstance(strategy_json.get("meta"), dict) else {}
            title = str(meta.get("title") or "传播策略方案")
            summary = StrategyService._build_strategy_card_summary(strategy_json)
            return ChatService.add_message(
                session_id,
                "assistant",
                summary,
                extra_fields={
                    "message_type": "strategy_plan",
                    "render_mode": "strategy_card",
                    "status": "done",
                    "strategy_status": "ready",
                    "strategy_title": title,
                    "strategy_id": strategy_id,
                    "saved_by": "strategy_service",
                },
            )
        except Exception as exc:
            current_app.logger.warning(f"保存策略卡消息失败: session_id={session_id}, strategy_id={strategy_id}, error={exc}")
            return False

    @staticmethod
    def _resolve_langchain_model(settings: Optional[Dict[str, Any]] = None):
        from .chat_service import ChatService

        provider_config = ChatService.resolve_chat_provider(settings or {})
        api_key = provider_config.get("api_key")
        base_url = provider_config.get("base_url")
        model = provider_config.get("model")

        if not api_key or not base_url:
            raise RuntimeError("策略模型服务尚未配置")

        try:
            from langchain_openai import ChatOpenAI
        except Exception:
            from langchain_community.chat_models import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=float((settings or {}).get("temperature", 0.2) or 0.2),
            timeout=90.0,
        )

    @staticmethod
    def _build_tool_evidence(session_id: str) -> List[str]:
        from .chat_service import ChatService

        session = ChatService.get_chat_session(session_id) or {}
        tool_results = session.get("tool_results", {}) if isinstance(session.get("tool_results"), dict) else {}
        evidence: List[str] = []

        overview = ((tool_results.get("chat.search_overview") or {}).get("result") or {}) if isinstance(tool_results.get("chat.search_overview"), dict) else {}
        items = overview.get("items") if isinstance(overview.get("items"), list) else []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            source = str(item.get("source_name") or item.get("platform") or "").strip()
            summary = str(item.get("summary") or item.get("content_excerpt") or "").strip()
            if title:
                evidence.append(f"{title}｜来源：{source or '未知'}｜摘要：{summary[:120]}")

        rumor = ((tool_results.get("chat.analyze_rumor") or {}).get("result") or {}) if isinstance(tool_results.get("chat.analyze_rumor"), dict) else {}
        verdict = str(rumor.get("verdict") or "").strip()
        explanation = str(rumor.get("explanation") or "").strip()
        if verdict or explanation:
            evidence.append(f"事实核查：{verdict or '待核实'}；{explanation[:140]}")

        return evidence

    @staticmethod
    def _generate_structured_strategy(session_id: str, strategy_data: Dict[str, Any], settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from langchain_core.exceptions import OutputParserException
        from langchain_core.output_parsers import PydanticOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        parser = PydanticOutputParser(pydantic_object=StrategyDocument)
        llm = StrategyService._resolve_langchain_model(settings)
        evidence_summary = StrategyService._build_tool_evidence(session_id)
        now_iso = datetime.datetime.utcnow().isoformat()

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一名资深舆情与传播策略顾问。请基于输入信息输出一份可执行、可落地、结构化的传播策略。"
                    "不要输出 markdown，不要输出解释文字，只返回符合要求的 JSON。"
                    "策略必须严格贴合当前事件事实、议题、传播脉络和风险，不得套用与输入无关的通用危机公关模板。"
                    "如果输入更像产品发布、品牌传播、政策沟通、活动推广或舆情研判，就按对应场景输出，不要默认写成争议澄清、道歉声明、媒体问答、KOL灭火等危机动作。"
                    "若事实中没有'官方声明/道歉/高管发言争议/谣言扩散'等信号，就不要臆造这些动作。\n{format_instructions}",
                ),
                (
                    "human",
                    "请基于以下信息生成策略：\n"
                    "事件概要：{event_summary}\n"
                    "事实核查：{fact_check}\n"
                    "已采取行动：{initial_actions}\n"
                    "短期目标：{short_term_goals}\n"
                    "中期目标：{mid_term_goals}\n"
                    "长期目标：{long_term_goals}\n"
                    "时间约束：{time_constraints}\n"
                    "预算约束：{budget_constraints}\n"
                    "补充信息：{additional_info}\n"
                    "实时检索与核查证据：\n{evidence_summary}\n"
                    "补充要求：\n"
                    "1. 动作项必须具体，避免空泛。\n"
                    "2. immediate/short/mid/long 四个阶段都要给内容。\n"
                    "3. 风险项要带概率、影响和 mitigation。\n"
                    "4. executiveSummary.summary 要用中文写成适合卡片展示的简洁总结。\n"
                    "5. meta.generatedAt 使用 {generated_at}。\n"
                    "6. meta.scenario 请概括当前事件场景。\n"
                    "7. 你的策略必须显式引用输入中的核心议题、关键发现、重点风险或传播机会；若做不到，宁可更保守，也不要泛化。\n",
                ),
            ]
        )

        default_title = f"{str(strategy_data.get('event_summary') or '').strip()[:24] or '当前事件'}传播策略"
        prompt_value = prompt.invoke(
            {
                "format_instructions": parser.get_format_instructions(),
                "event_summary": str(strategy_data.get("event_summary") or ""),
                "fact_check": str(strategy_data.get("fact_check") or ""),
                "initial_actions": str(strategy_data.get("initial_actions") or ""),
                "short_term_goals": str(strategy_data.get("short_term_goals") or ""),
                "mid_term_goals": str(strategy_data.get("mid_term_goals") or ""),
                "long_term_goals": str(strategy_data.get("long_term_goals") or ""),
                "time_constraints": str(strategy_data.get("time_constraints") or ""),
                "budget_constraints": str(strategy_data.get("budget_constraints") or ""),
                "additional_info": str(strategy_data.get("additional_info") or ""),
                "evidence_summary": "\n".join(f"- {item}" for item in evidence_summary) if evidence_summary else "- 暂无额外检索证据",
                "generated_at": now_iso,
            }
        )
        response = llm.invoke(prompt_value.to_messages())
        raw_content = getattr(response, "content", response)

        if isinstance(raw_content, StrategyDocument):
            strategy_doc = raw_content
        elif isinstance(raw_content, dict):
            strategy_doc = StrategyDocument.model_validate(raw_content)
        else:
            if isinstance(raw_content, list):
                text_parts: List[str] = []
                for item in raw_content:
                    if isinstance(item, str):
                        text_parts.append(item)
                    elif isinstance(item, dict):
                        text_value = item.get("text") or item.get("content") or ""
                        if isinstance(text_value, str):
                            text_parts.append(text_value)
                    else:
                        text_parts.append(str(item))
                normalized_content = "\n".join(part for part in text_parts if part).strip()
            else:
                normalized_content = str(raw_content or "").strip()

            try:
                strategy_doc = parser.parse(normalized_content)
            except OutputParserException:
                fallback_payload = StrategyService._extract_json_payload(normalized_content)
                if not fallback_payload:
                    raise
                strategy_doc = StrategyDocument.model_validate(
                    StrategyService._normalize_strategy_payload(fallback_payload)
                )

        strategy_json = strategy_doc.model_dump(mode="json")
        strategy_id = str(uuid.uuid4())
        strategy_json["meta"]["title"] = str(strategy_json["meta"].get("title") or "").strip() or default_title
        strategy_json["meta"]["strategyId"] = strategy_id
        strategy_json["meta"]["generatedAt"] = now_iso
        strategy_json["meta"]["sessionId"] = session_id
        if not str(strategy_json["meta"].get("scenario") or "").strip():
            strategy_json["meta"]["scenario"] = str(strategy_data.get("event_summary") or "")[:80]
        if not strategy_json["meta"].get("keywords"):
            strategy_json["meta"]["keywords"] = [
                value
                for value in [
                    str(strategy_data.get("event_summary") or "").strip()[:20],
                    str(strategy_data.get("short_term_goals") or "").strip()[:20],
                    str(strategy_data.get("fact_check") or "").strip()[:20],
                ]
                if value
            ][:5]
        strategy_json["appendix"]["inputSummary"] = {
            "eventSummary": str(strategy_data.get("event_summary") or ""),
            "factCheck": str(strategy_data.get("fact_check") or ""),
            "initialActions": str(strategy_data.get("initial_actions") or ""),
            "shortTermGoals": str(strategy_data.get("short_term_goals") or ""),
            "midTermGoals": str(strategy_data.get("mid_term_goals") or ""),
            "longTermGoals": str(strategy_data.get("long_term_goals") or ""),
            "timeConstraints": str(strategy_data.get("time_constraints") or ""),
            "budgetConstraints": str(strategy_data.get("budget_constraints") or ""),
            "additionalInfo": str(strategy_data.get("additional_info") or ""),
        }
        strategy_json["appendix"]["evidenceSummary"] = evidence_summary
        return strategy_json

    @staticmethod
    def generate_strategy(session_id: str, strategy_data: Dict[str, Any], settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            db = get_db()
            strategy_json = StrategyService._generate_structured_strategy(session_id, strategy_data, settings=settings)
            strategy_id = str(((strategy_json.get("meta") or {}).get("strategyId")) or uuid.uuid4())
            created_at = datetime.datetime.utcnow()

            db.strategy_results.insert_one(
                {
                    "strategy_id": strategy_id,
                    "session_id": session_id,
                    "input": safe_json_data(strategy_data),
                    "data": safe_json_data(strategy_json),
                    "generator": "langchain",
                    "created_at": created_at,
                }
            )

            StrategyService.link_strategy_to_session(session_id, strategy_id)
            StrategyService.save_strategy_card_message(session_id, strategy_id, strategy_json)

            return {
                "status": "success",
                "strategy_id": strategy_id,
                "session_id": session_id,
                "data": strategy_json,
            }
        except Exception as exc:
            current_app.logger.error(f"结构化策略生成失败: {exc}")
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(exc),
                "session_id": session_id,
            }

    @staticmethod
    def get_strategy(strategy_id: str):
        try:
            db = get_db()
            strategy = db.strategy_results.find_one({"strategy_id": strategy_id})
            if not strategy:
                return {"success": False, "error": f"策略不存在: {strategy_id}"}, 404
            return {
                "success": True,
                "data": strategy.get("data", {}),
                "created_at": strategy.get("created_at"),
                "strategy_id": strategy.get("strategy_id"),
                "session_id": strategy.get("session_id"),
            }, 200
        except Exception as exc:
            return {"success": False, "error": f"获取策略失败: {exc}"}, 500

    @staticmethod
    def get_latest_strategy_by_session(session_id: str):
        try:
            db = get_db()
            strategy = db.strategy_results.find_one({"session_id": session_id}, sort=[("created_at", -1)])
            if not strategy:
                return {"success": False, "error": f"会话暂无策略: {session_id}"}, 404
            return {
                "success": True,
                "data": strategy.get("data", {}),
                "created_at": strategy.get("created_at"),
                "strategy_id": strategy.get("strategy_id"),
                "session_id": strategy.get("session_id"),
            }, 200
        except Exception as exc:
            return {"success": False, "error": f"获取会话最新策略失败: {exc}"}, 500
