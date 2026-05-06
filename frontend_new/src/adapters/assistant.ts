import type {
  AIBrief,
  AIDataPreviewItem,
  AIRecommendationCard,
  AIReport,
  AIStrategy,
  ChatMessage,
  ChatSession,
} from '../types/assistant';

function adaptSentiment(tag: string) {
  if (tag === '正') return 'positive';
  if (tag === '中') return 'neutral';
  return 'negative';
}

function adaptSourceType(type: string) {
  if (type === '新闻报道') return 'news';
  if (type === '社交媒体') return 'social';
  return 'video';
}

export function adaptRecommendationCards(raw: any): AIRecommendationCard[] {
  const cards = raw?.recommendation_cards ?? [];
  return cards.map((item: any) => ({
    id: String(item.id),
    title: String(item.title ?? ''),
    summary: String(item.content ?? item.summary ?? ''),
    author: String(item.author ?? ''),
    image: String(item.image ?? ''),
    sentiment: adaptSentiment(String(item.tag ?? '负')),
  }));
}

export function adaptChatSessions(raw: any): ChatSession[] {
  const sessions = raw?.sessions ?? [];
  return sessions.map((item: any) => ({
    id: String(item.id),
    title: String(item.title ?? ''),
    updatedAt: String(item.updated_at ?? item.updatedAt ?? ''),
    createdAt: String(item.created_at ?? item.createdAt ?? ''),
    summary: item.summary ? String(item.summary) : undefined,
    hasReport: Boolean(item.report_id),
    reportId: item.report_id ? String(item.report_id) : null,
    hasStrategy: Boolean(item.strategy_id),
    strategyId: item.strategy_id ? String(item.strategy_id) : null,
  }));
}

export function adaptChatMessages(raw: any, sessionId: string): ChatMessage[] {
  const messageBucket = raw?.messages_by_session?.[sessionId] ?? [];
  return messageBucket.map((item: any) => ({
    id: String(item.id),
    sessionId: String(item.session_id ?? sessionId),
    role: item.role === 'assistant' || item.role === 'system' ? item.role : 'user',
    content: String(item.content ?? ''),
    createdAt: String(item.created_at ?? ''),
    messageType: item.messageType === 'event_report'
      ? 'event_report'
      : item.messageType === 'strategy_plan'
        ? 'strategy_plan'
        : 'plain',
    renderMode: item.renderMode === 'report_card'
      ? 'report_card'
      : item.renderMode === 'strategy_card'
        ? 'strategy_card'
        : item.renderMode === 'hidden'
          ? 'hidden'
          : 'bubble',
    status: item.status,
    tagLabel: item.tag_label,
    thinking: item.thinking,
    reportTitle: item.report_title,
    reportStatus: item.report_status,
    strategyTitle: item.strategy_title,
    strategyStatus: item.strategy_status,
    strategyId: item.strategy_id,
  }));
}

export function adaptDataPreview(raw: any, sessionId: string): AIDataPreviewItem[] {
  const items = raw?.data_preview_by_session?.[sessionId] ?? [];
  return items.map((item: any) => ({
    id: String(item.id),
    sourceType: adaptSourceType(String(item.type ?? '短视频平台')),
    title: String(item.title ?? ''),
    summary: String(item.content ?? item.summary ?? ''),
    publishedAt: String(item.time ?? item.published_at ?? ''),
    sourceLabel: String(item.type ?? ''),
  }));
}

export function adaptBrief(raw: any, sessionId: string): AIBrief | null {
  const item = raw?.brief_by_session?.[sessionId];
  if (!item) return null;
  return {
    summary: String(item.summary ?? ''),
    highlights: Array.isArray(item.highlights) ? item.highlights.map(String) : [],
  };
}

export function adaptReport(raw: any, sessionId: string): AIReport | null {
  const item = raw?.report_by_session?.[sessionId];
  if (!item) return null;
  return {
    id: String(item.report_id ?? item.id ?? ''),
    title: String(item.title ?? ''),
    createdAt: String(item.created_at ?? item.createdAt ?? ''),
    isFallback: Boolean(item.is_fallback ?? item.isFallback),
    content: item.content ?? {},
  };
}

export function adaptStrategy(raw: any, sessionId: string): AIStrategy | null {
  const item = raw?.strategy_by_session?.[sessionId];
  if (!item) return null;
  return {
    id: String(item.strategy_id ?? item.id ?? ''),
    title: String(item.title ?? ''),
    createdAt: String(item.created_at ?? item.createdAt ?? ''),
    content: item.content ?? {},
  };
}
