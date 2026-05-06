"""Chat session MCP schemas."""

from __future__ import annotations

from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class AuthContext(BaseModel):
    user_id: str
    username: Optional[str] = None
    roles: List[str] = Field(default_factory=lambda: ["user"])


class RequestContext(BaseModel):
    request_id: str
    trace_id: Optional[str] = None
    source: str = "frontend_api"
    timeout_ms: Optional[int] = None


class MCPContext(BaseModel):
    auth: AuthContext
    request: RequestContext


class MCPError(BaseModel):
    code: Literal[
        "invalid_input",
        "unauthorized",
        "forbidden",
        "not_found",
        "conflict",
        "timeout",
        "upstream_error",
        "internal_error",
        "not_implemented",
    ]
    message: str


class MCPMeta(BaseModel):
    request_id: str
    trace_id: Optional[str] = None
    duration_ms: Optional[int] = None


class MCPResponse(BaseModel, Generic[DataT]):
    success: bool
    data: Optional[DataT] = None
    error: Optional[MCPError] = None
    meta: MCPMeta


class ChatSettings(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = None
    enable_search: Optional[bool] = None


class ChatMessage(BaseModel):
    id: str = ""
    role: Literal["user", "assistant"]
    content: str
    timestamp: Optional[str] = None
    render_mode: Optional[str] = None
    message_type: Optional[str] = None
    report_title: Optional[str] = None
    report_status: Optional[str] = None
    strategy_title: Optional[str] = None
    strategy_status: Optional[str] = None
    strategy_id: Optional[str] = None
    grounding_status: Optional[str] = None
    confidence: Optional[str] = None
    used_realtime_retrieval: Optional[bool] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    facts: List[str] = Field(default_factory=list)
    to_verify: List[str] = Field(default_factory=list)
    analysis: List[str] = Field(default_factory=list)
    route: Optional[str] = None
    debug_mode: Optional[bool] = None
    fallback_reason: Optional[str] = None
    upstream_code: Optional[str] = None
    upstream_type: Optional[str] = None
    phase: Optional[str] = None
    search_timed_out: Optional[bool] = None
    search_failed: Optional[bool] = None
    fallback_level: Optional[int] = None
    final_model: Optional[str] = None
    degrade_reason: Optional[str] = None
    degrade_message: Optional[str] = None
    model_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    audio_url: Optional[str] = None
    tts_status: Optional[Literal["idle", "processing", "ready", "failed"]] = None
    tts_task_id: Optional[str] = None
    tts_provider: Optional[str] = None
    tts_duration_seconds: Optional[float] = None
    tts_error: Optional[str] = None


class ChatSession(BaseModel):
    id: str
    title: str
    title_locked: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    settings: ChatSettings = Field(default_factory=ChatSettings)
    messages: List[ChatMessage] = Field(default_factory=list)


class CreateSessionInput(BaseModel):
    initialize_conversation: bool = True


class CreateSessionData(BaseModel):
    session: ChatSession


class ListSessionsInput(BaseModel):
    pass


class ListSessionsData(BaseModel):
    sessions: List[ChatSession]


class SessionRefInput(BaseModel):
    session_id: str


class GetSessionData(BaseModel):
    session: ChatSession


class RenameSessionInput(BaseModel):
    session_id: str
    title: str


class RenameSessionData(BaseModel):
    session_id: str
    title: str
    title_locked: bool = True


class DeleteSessionInput(BaseModel):
    session_id: str


class DeleteSessionData(BaseModel):
    session_id: str
    deleted: bool


class GetMessagesInput(BaseModel):
    session_id: str


class GetMessagesData(BaseModel):
    session_id: str
    messages: List[ChatMessage]


class SendMessageInput(BaseModel):
    session_id: str
    message: str
    kb_id: Optional[str] = None
    recommendation_context: Optional[Dict[str, Any]] = None


class SendMessageData(BaseModel):
    session_id: str
    assistant_message: ChatMessage


class StreamMessageInput(BaseModel):
    session_id: str
    message: str
    kb_id: Optional[str] = None
    recommendation_context: Optional[Dict[str, Any]] = None
    debug_mode: Optional[bool] = False


class StreamEvent(BaseModel):
    event: Literal["start", "ready", "message", "done", "error"]
    data: Dict[str, Any] = Field(default_factory=dict)


class GenerateStrategyInput(BaseModel):
    session_id: str
    event_summary: str
    fact_check: str = ""
    initial_actions: str = ""
    short_term_goals: str = ""
    mid_term_goals: str = ""
    long_term_goals: str = ""
    time_constraints: str = ""
    budget_constraints: str = ""
    additional_info: str = ""


class GenerateStrategyData(BaseModel):
    task_id: str
    status: Literal["processing"] = "processing"
    session_id: str


class GenerateStrategySyncData(BaseModel):
    session_id: str
    status: Literal["completed"] = "completed"
    strategy_id: str = ""
    message: Optional[str] = None


class OverviewSearchInput(BaseModel):
    session_id: str
    query: str
    user_prompt: str = ""
    source_url: str = ""
    platform_hint: str = ""
    max_results: int = 10
    save_to_history: bool = True  # 前置工具调用时设为 False，避免污染聊天历史


class OverviewSearchItemData(BaseModel):
    title: str
    url: str = ""
    source_name: str = ""
    platform: str = ""
    published_at: Optional[str] = None
    summary: str = ""
    content_excerpt: str = ""
    credibility: str = "medium"
    source_type: str = "general_webpage"
    relevance_score: float = 0.0
    time_reason: str = ""
    credibility_reason: str = ""


class OverviewSearchData(BaseModel):
    session_id: str
    query: str
    summary: str = ""
    total: int = 0
    items: List[OverviewSearchItemData] = Field(default_factory=list)
    assistant_message: Optional[ChatMessage] = None


class RumorAnalysisInput(BaseModel):
    session_id: str
    query: str
    user_prompt: str = ""
    source_url: str = ""
    platform_hint: str = ""
    max_results: int = 8
    save_to_history: bool = True  # 前置工具调用时设为 False，避免污染聊天历史


class RumorAnalysisData(BaseModel):
    session_id: str
    query: str
    verdict: str = ""
    risk_level: str = "medium"
    summary: str = ""
    known_facts: List[str] = Field(default_factory=list)
    to_verify: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    items: List[OverviewSearchItemData] = Field(default_factory=list)
    assistant_message: Optional[ChatMessage] = None


class GenerateSessionReportInput(BaseModel):
    session_id: str


class GenerateSessionReportData(BaseModel):
    session_id: str
    report_id: str
    status: Literal["completed"] = "completed"
    warning: Optional[str] = None


class GetHotspotContextInput(BaseModel):
    title: str
    platform_hint: str = ""
    source_url: str = ""
    published_at: str = ""
    max_candidates: int = 5


class GetHotspotContextData(BaseModel):
    title: str
    platform: str = ""
    source_url: str = ""
    published_at: str = ""
    hot_value: str = ""
    rank: Optional[int] = None
    summary: str = ""
    source_trace: List[str] = Field(default_factory=list)
    relevance_score: float = 0.0
    message: Optional[str] = None


class GetTaskStatusInput(BaseModel):
    task_id: str


class GetTaskStatusData(BaseModel):
    task_id: str
    status: Literal["processing", "completed", "failed"]
    result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class VerifySourceCredibilityInput(BaseModel):
    url: str = ""
    source_name: str = ""
    platform: str = ""


class VerifySourceCredibilityData(BaseModel):
    credibility_level: str
    source_type: str
    reason: str


class VerifyTimeConsistencyInput(BaseModel):
    title: str = ""
    published_at: str = ""
    extracted_text: str = ""
    hotspot_time: str = ""


class VerifyTimeConsistencyData(BaseModel):
    is_recent: Optional[bool] = None
    time_gap: Optional[Dict[str, Any]] = None
    is_old_news_recirculation: Optional[bool] = None
    reason: str


class TimelineDocumentInput(BaseModel):
    title: str = ""
    content: str = ""
    source: str = ""
    source_name: str = ""
    published_at: str = ""
    url: str = ""


class ExtractTimelineInput(BaseModel):
    documents: List[TimelineDocumentInput] = Field(default_factory=list)


class TimelineItemData(BaseModel):
    time: str = ""
    event: str = ""
    actor: str = ""
    source: str = ""


class ExtractTimelineData(BaseModel):
    timeline: List[TimelineItemData] = Field(default_factory=list)
    count: int = 0


class ExportChatInput(BaseModel):
    session_id: str


class ExportChatData(BaseModel):
    filename: str
    content_type: Literal["application/json"] = "application/json"
    content: str


class CrawlNewsContextInput(BaseModel):
    title: str
    source_url: Optional[str] = None
    platform_hint: Optional[str] = None
    session_id: Optional[str] = None
    max_candidates: int = 5
    force_refresh: bool = False


class CrawlNewsContextData(BaseModel):
    query_title: str
    status: Literal["ready", "failed"]
    summary: str = ""
    content_excerpt: str = ""
    source_name: str = ""
    final_url: str = ""
    published_at: Optional[str] = None
    candidate_urls: List[str] = Field(default_factory=list)
    cached: bool = False
    message: Optional[str] = None


class RunMindSpiderTopicExtractionInput(BaseModel):
    sources: List[str] = Field(default_factory=list)
    max_keywords: int = 100


class RunMindSpiderTopicExtractionData(BaseModel):
    task_id: str
    status: Literal["processing"] = "processing"


class GetMindSpiderTopicAnalysisInput(BaseModel):
    extract_date: Optional[str] = None


class GetMindSpiderTopicAnalysisData(BaseModel):
    extract_date: str
    keywords: List[str] = Field(default_factory=list)
    summary: str = ""
    news_count: int = 0
    news: List[Dict[str, Any]] = Field(default_factory=list)


class RunMindSpiderDeepSentimentInput(BaseModel):
    extract_date: Optional[str] = None
    platforms: List[str] = Field(default_factory=list)
    max_keywords_per_platform: int = 20
    max_candidates_per_keyword: int = 3


class RunMindSpiderDeepSentimentData(BaseModel):
    task_id: str
    status: Literal["processing"] = "processing"


class GetMindSpiderDeepSentimentInput(BaseModel):
    extract_date: Optional[str] = None


class GetMindSpiderDeepSentimentData(BaseModel):
    extract_date: str
    source_summary: str = ""
    total_keywords: int = 0
    total_platforms: int = 0
    total_records: int = 0
    platform_stats: List[Dict[str, Any]] = Field(default_factory=list)
    sentiment_distribution: List[Dict[str, Any]] = Field(default_factory=list)
    records: List[Dict[str, Any]] = Field(default_factory=list)


class SearchWebInput(BaseModel):
    query: str
    max_results: int = 5


class SearchWebData(BaseModel):
    query: str
    results: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class LoadUrlsInput(BaseModel):
    urls: List[str]


class LoadUrlsData(BaseModel):
    urls: List[str]
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class AnalyzeVideoInput(BaseModel):
    session_id: str
    video_path: str
    query: Optional[str] = None


class AnalyzeVideoData(BaseModel):
    task_id: str
    session_id: str


class AnalyzeMultimodalInput(BaseModel):
    session_id: str
    file_paths: List[str]
    query: Optional[str] = None


class AnalyzeMultimodalData(BaseModel):
    task_id: str
    session_id: str
    file_count: int = 0


class DbAggregateInput(BaseModel):
    template_name: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = 10


class DbAggregateData(BaseModel):
    template_name: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    execution_ms: int = 0


# ===== TTS 相关 Schema =====


class TextToSpeechInput(BaseModel):
    """文字转语音输入"""
    text: str = Field(..., description="要转换为语音的文本内容，建议在 50-5000 字以内")
    session_id: Optional[str] = Field(None, description="关联的会话 ID，用于音频文件组织")
    voice_id: Optional[str] = Field(None, description="指定的声音 ID，不指定则使用默认声音")
    provider: Optional[str] = Field(None, description="TTS Provider，不指定则使用默认")


class TextToSpeechData(BaseModel):
    """文字转语音输出"""
    audio_url: str = Field(..., description="音频文件访问 URL，前端可直接用于 <audio> 标签")
    duration_seconds: float = Field(..., description="预估音频时长（秒）")
    provider: str = Field(..., description="实际使用的 TTS Provider")
    text_preview: str = Field(..., description="文本预览（前 50 字）")


class TextToSpeechAsyncInput(BaseModel):
    session_id: str = Field(..., description="关联的会话 ID")
    message_id: str = Field(..., description="目标 assistant 消息 ID")
    text: str = Field(..., description="要转换为语音的文本内容")
    voice_id: Optional[str] = Field(None, description="指定声音 ID")
    provider: Optional[str] = Field(None, description="指定 TTS Provider")


class TextToSpeechAsyncData(BaseModel):
    task_id: str = Field(..., description="异步任务 ID")
    status: Literal["processing", "completed"] = Field(..., description="任务当前状态")
    message_id: str = Field(..., description="目标消息 ID")
