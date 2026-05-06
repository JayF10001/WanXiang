from typing import Optional, Literal
from pydantic import BaseModel


class RecommendationContext(BaseModel):
    title: str
    sourceUrl: Optional[str] = None
    platformHint: Optional[str] = None
    summary: Optional[str] = None
    publishedAt: Optional[str] = None
    sourceLabel: Optional[str] = None


class AnalyzeRequest(BaseModel):
    mode: Literal["domain", "chat"]
    sessionId: Optional[str] = None
    domain: Optional[str] = None
    message: Optional[str] = None
    kbId: Optional[str] = None
    debugMode: Optional[bool] = False
    recommendationContext: Optional[RecommendationContext] = None
