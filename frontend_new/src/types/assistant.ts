export type ChatRole = 'user' | 'assistant' | 'system';

export type MessageStatus = 'done' | 'streaming' | 'error';

export type Sentiment = 'positive' | 'neutral' | 'negative';

export type SourceType = 'news' | 'social' | 'video';

export type AnalysisMode = 'domain' | 'chat';

export interface ChatSession {
  id: string;
  title: string;
  updatedAt: string;
  createdAt: string;
  summary?: string;
  hasReport?: boolean;
  reportId?: string | null;
  hasStrategy?: boolean;
  strategyId?: string | null;
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  messageType?: 'plain' | 'event_report' | 'strategy_plan';
  renderMode?: 'bubble' | 'report_card' | 'strategy_card' | 'hidden';
  status?: MessageStatus;
  tagLabel?: string;
  thinking?: string;
  reportTitle?: string;
  reportStatus?: 'idle' | 'generating' | 'ready';
  strategyTitle?: string;
  strategyStatus?: 'idle' | 'generating' | 'ready';
  strategyId?: string;
  suggestedAction?: string | null;
  groundingStatus?: string;
  confidence?: string;
  usedRealtimeRetrieval?: boolean;
  structuredRecordCount?: number;
  structuredAggregations?: {
    totalMatchedCount?: number;
    finalistCount?: number;
    uniqueSchoolCount?: number;
    countsBySchool?: Array<{ name?: string; count?: number }>;
    countsByAward?: Array<{ name?: string; count?: number }>;
    countsBySubject?: Array<{ name?: string; count?: number }>;
    countsByGroup?: Array<{ name?: string; count?: number }>;
  };
  structuredRecords?: Array<{
    sourceId?: string;
    fileId?: string;
    title?: string;
    score?: number;
    keywordScore?: number;
    vectorScore?: number;
    record?: {
      province?: string;
      ticketNo?: string;
      schoolName?: string;
      studentName?: string;
      subjectName?: string;
      groupName?: string;
      award?: string;
      qualifiedForFinal?: boolean | null;
      qualifiedForFinalLabel?: string;
    };
  }>;
  sources?: Array<{
    title?: string;
    url?: string;
    sourceType?: string;
    summary?: string;
    snippet?: string;
    credibility?: string;
    publishedAt?: string;
    citationCount?: number;
    score?: number;
    keywordScore?: number;
    vectorScore?: number;
    record?: {
      province?: string;
      ticketNo?: string;
      schoolName?: string;
      studentName?: string;
      subjectName?: string;
      groupName?: string;
      award?: string;
      qualifiedForFinal?: boolean | null;
      qualifiedForFinalLabel?: string;
    };
  }>;
  citations?: Array<{
    id?: string;
    title?: string;
    url?: string;
    sourceType?: string;
    credibility?: string;
    publishedAt?: string;
    sourceTitle?: string;
    sourceUrl?: string;
    quote?: string;
    sourceId?: string;
    fileId?: string;
    score?: number;
    keywordScore?: number;
    vectorScore?: number;
    record?: {
      province?: string;
      ticketNo?: string;
      schoolName?: string;
      studentName?: string;
      subjectName?: string;
      groupName?: string;
      award?: string;
      qualifiedForFinal?: boolean | null;
      qualifiedForFinalLabel?: string;
    };
  }>;
  facts?: string[];
  toVerify?: string[];
  analysis?: string[];
  route?: string;
  debugMode?: boolean;
  fallbackReason?: string;
  upstreamCode?: string;
  upstreamType?: string;
  phase?: string;
  searchTimedOut?: boolean;
  searchFailed?: boolean;
  fallbackLevel?: number;
  finalModel?: string;
  degradeReason?: string;
  degradeMessage?: string;
  modelAttempts?: MultimodalModelAttempt[];
  audioUrl?: string;
  ttsStatus?: 'idle' | 'processing' | 'ready' | 'failed';
  ttsTaskId?: string;
  ttsProvider?: string;
  ttsDurationSeconds?: number;
  ttsError?: string;
  riskLevel?: string;
}

export interface MultimodalModelAttempt {
  model: string;
  status: string;
  reason?: string;
  latency_ms?: number;
}

export interface MultimodalAnalysisItem {
  file_name?: string;
  modality?: 'image' | 'audio' | 'video' | string;
  status?: 'success' | 'failed' | string;
  summary?: string;
  sentiment?: string;
  risk_level?: string;
  keywords?: string[];
  fallback_level?: number;
  final_model?: string | null;
  degrade_reason?: string | null;
  degrade_message?: string | null;
  model_attempts?: MultimodalModelAttempt[];
}

export interface AssistantTaskResultPayload {
  status?: string;
  provider?: string;
  session_id?: string;
  result?: Record<string, any> | null;
  error?: string | null;
  user_message?: string | null;
  fallback_level?: number;
  final_model?: string | null;
  degrade_reason?: string | null;
  degrade_message?: string | null;
  model_attempts?: MultimodalModelAttempt[];
  phase?: string | null;
  message_id?: string | null;
  audio_url?: string | null;
  duration_seconds?: number | null;
  tts_status?: 'processing' | 'ready' | 'failed' | null;
  tts_error?: string | null;
  file_count?: number | null;
  processed_count?: number | null;
  failed_count?: number | null;
  current_file_name?: string | null;
  current_modality?: string | null;
  items?: MultimodalAnalysisItem[];
  overall_summary?: string | null;
  overall_risk_level?: string | null;
  common_topics?: string[];
  cross_file_signals?: string[];
}

export interface AssistantTaskStatus {
  task_id: string;
  status: 'processing' | 'completed' | 'failed';
  result?: AssistantTaskResultPayload | null;
  message?: string | null;
}

export interface SearchOverviewResult {
  session_id: string;
  query: string;
  summary: string;
  total: number;
  items: Array<{
    title: string;
    url: string;
    source_name: string;
    platform: string;
    published_at: string | null;
    summary: string;
    content_excerpt: string;
    credibility: string;
    source_type: string;
    relevance_score: number;
    time_reason: string;
    credibility_reason: string;
  }>;
  assistant_message?: ChatMessage;
}

export interface AnalyzeRumorResult {
  session_id: string;
  query: string;
  verdict: string;
  risk_level: string;
  summary: string;
  known_facts: string[];
  to_verify: string[];
  suggestions: string[];
  items: Array<{
    title: string;
    url: string;
    source_name: string;
    platform: string;
    published_at: string | null;
    summary: string;
    content_excerpt: string;
    credibility: string;
    source_type: string;
    relevance_score: number;
    time_reason: string;
    credibility_reason: string;
  }>;
  assistant_message?: ChatMessage;
}

export interface AIRecommendationCard {
  id: string;
  title: string;
  summary: string;
  author: string;
  image: string;
  sentiment: Sentiment;
  sentimentLabel?: string;
  sentimentSourceLabel?: string;
  publishedAt?: string;
  sourceLabel?: string;
  sourceName?: string;
  url?: string;
  fallbackUsed?: boolean;
}

export interface AIDataPreviewItem {
  id: string;
  sourceType: SourceType;
  title: string;
  summary: string;
  publishedAt: string;
  sourceLabel: string;
}

export interface AIBrief {
  summary: string;
  highlights: string[];
}

export interface AIReport {
  id: string;
  title: string;
  createdAt: string;
  isFallback: boolean;
  content: Record<string, any>;
}

export interface AIStrategy {
  id: string;
  title: string;
  createdAt: string;
  content: Record<string, any>;
}

export interface AnalysisInput {
  mode: AnalysisMode;
  sessionId?: string;
  domain?: string;
  message?: string;
  kbId?: string;
  debugMode?: boolean;
  recommendationContext?: {
    title: string;
    sourceUrl?: string;
    platformHint?: string;
    summary?: string;
    publishedAt?: string;
    sourceLabel?: string;
  };
}

export interface AssistantHomeMock {
  recommendationCards: AIRecommendationCard[];
  defaultModel: string;
  suggestedPrompts: string[];
}

export interface AssistantSessionsMock {
  sessions: ChatSession[];
  activeSessionId: string | null;
}

export interface AssistantMessagesMock {
  messagesBySession: Record<string, ChatMessage[]>;
}

export interface AssistantPanelsMock {
  dataPreviewBySession: Record<string, AIDataPreviewItem[]>;
  briefBySession: Record<string, AIBrief>;
  reportBySession: Record<string, AIReport>;
  strategyBySession?: Record<string, AIStrategy>;
}
