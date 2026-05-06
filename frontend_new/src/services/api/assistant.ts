import { apiRequest } from './client';
import type {
  AnalysisInput,
  AIBrief,
  AIDataPreviewItem,
  AIReport,
  AIStrategy,
  AssistantTaskStatus,
  ChatMessage,
  ChatSession,
} from '../../types/assistant';
import type { ApiResponse } from '../../types/common';
import { runtimeConfig } from '../../config/runtime';

export async function getAssistantHomeFromApi(options: {
  refreshToken?: string;
} = {}): Promise<{
  recommendationCards: Array<{
    id: string;
    title: string;
    summary: string;
    author: string;
    image: string;
    sentiment: 'positive' | 'neutral' | 'negative';
    sentimentLabel?: string;
    sentimentSourceLabel?: string;
    publishedAt?: string;
    sourceLabel?: string;
    sourceName?: string;
    fallbackUsed?: boolean;
  }>;
  defaultModel: string;
  suggestedPrompts: string[];
}> {
  const query = options.refreshToken
    ? `?refresh_token=${encodeURIComponent(options.refreshToken)}`
    : '';
  const response = await apiRequest<ApiResponse<{
    recommendationCards: Array<{
      id: string;
      title: string;
      summary: string;
      author: string;
      image: string;
      sentiment: 'positive' | 'neutral' | 'negative';
      sentimentLabel?: string;
      sentimentSourceLabel?: string;
      publishedAt?: string;
      sourceLabel?: string;
      sourceName?: string;
      fallbackUsed?: boolean;
    }>;
    defaultModel: string;
    suggestedPrompts: string[];
  }>>(`/assistant/home${query}`, {
    timeoutMs: 30000,
  });
  return response.data as {
    recommendationCards: Array<{
      id: string;
      title: string;
      summary: string;
      author: string;
      image: string;
      sentiment: 'positive' | 'neutral' | 'negative';
      sentimentLabel?: string;
      sentimentSourceLabel?: string;
      publishedAt?: string;
      sourceLabel?: string;
      sourceName?: string;
      fallbackUsed?: boolean;
    }>;
    defaultModel: string;
    suggestedPrompts: string[];
  };
}

export async function getRecommendationSummaryFromApi(params: {
  title: string;
  sourceUrl?: string;
}): Promise<{
  summary: string;
  summarySource: string;
}> {
  const query = new URLSearchParams({
    title: params.title,
    source_url: params.sourceUrl || '',
  }).toString();
  const response = await apiRequest<ApiResponse<{
    summary: string;
    summarySource: string;
  }>>(`/assistant/recommendation-summary?${query}`, {
    timeoutMs: 12000,
  });
  return response.data as {
    summary: string;
    summarySource: string;
  };
}

export async function createAssistantSessionInApi(): Promise<ChatSession> {
  const response = await apiRequest<ApiResponse<ChatSession>>('/assistant/sessions', {
    method: 'POST',
  });
  return response.data as ChatSession;
}

export async function deleteAssistantSessionInApi(sessionId: string): Promise<{ id: string }> {
  const response = await apiRequest<ApiResponse<{ id: string }>>(`/assistant/sessions/${sessionId}`, {
    method: 'DELETE',
  });
  return response.data as { id: string };
}

export async function renameAssistantSessionInApi(sessionId: string, title: string): Promise<{ id: string; title: string }> {
  const response = await apiRequest<ApiResponse<{ id: string; title: string }>>(`/assistant/sessions/${sessionId}/title`, {
    method: 'PUT',
    body: JSON.stringify({ title }),
  });
  return response.data as { id: string; title: string };
}

export async function getAssistantSessionsFromApi(): Promise<{ sessions: ChatSession[]; activeSessionId: string | null }> {
  const response = await apiRequest<ApiResponse<{ sessions: ChatSession[]; activeSessionId: string | null }>>('/assistant/sessions');
  return response.data as { sessions: ChatSession[]; activeSessionId: string | null };
}

export async function getAssistantMessagesFromApi(sessionId: string): Promise<ChatMessage[]> {
  const response = await apiRequest<ApiResponse<ChatMessage[]>>(`/assistant/sessions/${sessionId}/messages`);
  const messages = (response.data as ChatMessage[]).map((item) => {
    const next = { ...item };
    if (next.audioUrl && !next.audioUrl.startsWith('http')) {
      const normalizedPath = next.audioUrl.replace(/^\/api\//, '/');
      next.audioUrl = `${runtimeConfig.frontendApiBaseUrl.replace(/\/$/, '')}${normalizedPath}`;
    }
    return next;
  });
  return messages;
}

export async function saveAssistantSessionMessageInApi(params: {
  sessionId: string;
  role: 'user' | 'assistant';
  content: string;
}): Promise<{ success: boolean; message: string }> {
  const response = await apiRequest<ApiResponse<{ success?: boolean; message?: string }>>(
    `/assistant/sessions/${params.sessionId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({
        role: params.role,
        content: params.content,
      }),
      timeoutMs: 30000,
    },
  );
  return {
    success: Boolean((response.data as any)?.success ?? response.success),
    message: String((response.data as any)?.message ?? response.message ?? ''),
  };
}

export async function getAssistantPanelsFromApi(sessionId: string): Promise<{
  dataPreview: AIDataPreviewItem[];
  brief: AIBrief | null;
  report: AIReport | null;
  strategy: AIStrategy | null;
}> {
  const response = await apiRequest<ApiResponse<{
    dataPreview: AIDataPreviewItem[];
    brief: AIBrief | null;
    report: AIReport | null;
    strategy: AIStrategy | null;
  }>>(`/assistant/sessions/${sessionId}/panels`);
  return response.data as {
    dataPreview: AIDataPreviewItem[];
    brief: AIBrief | null;
    report: AIReport | null;
    strategy: AIStrategy | null;
  };
}

export async function generateAssistantReportInApi(sessionId: string, message?: string): Promise<{
  reportId: string;
  sessionId: string;
  data: Record<string, any>;
  isFallback: boolean;
  createdAt?: string;
  warning?: string | null;
}> {
  console.log('[Report API] ========== 报告生成请求开始 ==========');
  console.log('[Report API] sessionId:', sessionId);
  console.log('[Report API] message:', message);
  console.log('[Report API] 调用后端 /reports/generate...');

  const response = await apiRequest<ApiResponse<{
    reportId: string;
    sessionId: string;
    data: Record<string, any>;
    isFallback: boolean;
    createdAt?: string;
    warning?: string | null;
  }>>('/reports/generate', {
    method: 'POST',
    body: JSON.stringify({ sessionId, message }),
    timeoutMs: 300000,
  });

  const result = response.data as {
    reportId: string;
    sessionId: string;
    data: Record<string, any>;
    isFallback: boolean;
    createdAt?: string;
    warning?: string | null;
  };

  console.log('[Report API] ========== 报告生成响应 ==========');
  console.log('[Report API] success:', response.success);
  console.log('[Report API] reportId:', result.reportId);
  console.log('[Report API] isFallback:', result.isFallback);
  console.log('[Report API] warning:', result.warning);
  console.log('[Report API] data.meta.title:', result.data?.meta?.title);
  console.log('[Report API] data.executiveSummary.keyFindings:', result.data?.executiveSummary?.keyFindings);
  console.log('[Report API] data 完整结构 keys:', Object.keys(result.data || {}));

  if (result.isFallback) {
    console.warn('[Report API] ⚠️ 报告使用了兜底数据！isFallback = true');
  }

  console.log('[Report API] ========== 报告生成请求结束 ==========');

  return result;
}

export async function generateAssistantStrategyInApi(params: {
  sessionId: string;
  eventSummary: string;
  factCheck?: string;
  initialActions?: string;
  shortTermGoals?: string;
  midTermGoals?: string;
  longTermGoals?: string;
  timeConstraints?: string;
  budgetConstraints?: string;
  additionalInfo?: string;
}): Promise<{
  task_id: string;
  status: 'processing';
  session_id: string;
}> {
  const response = await apiRequest<ApiResponse<{
    task_id: string;
    status: 'processing';
    session_id: string;
  }>>(`/assistant/sessions/${params.sessionId}/strategy`, {
    method: 'POST',
    body: JSON.stringify({
      event_summary: params.eventSummary,
      fact_check: params.factCheck || '',
      initial_actions: params.initialActions || '',
      short_term_goals: params.shortTermGoals || '',
      mid_term_goals: params.midTermGoals || '',
      long_term_goals: params.longTermGoals || '',
      time_constraints: params.timeConstraints || '',
      budget_constraints: params.budgetConstraints || '',
      additional_info: params.additionalInfo || '',
    }),
    timeoutMs: 30000,
  });
  return response.data as {
    task_id: string;
    status: 'processing';
    session_id: string;
  };
}

export async function generateAssistantStrategySyncInApi(params: {
  sessionId: string;
  eventSummary: string;
  factCheck?: string;
  initialActions?: string;
  shortTermGoals?: string;
  midTermGoals?: string;
  longTermGoals?: string;
  timeConstraints?: string;
  budgetConstraints?: string;
  additionalInfo?: string;
}): Promise<{
  session_id: string;
  status: 'completed';
  strategy_id?: string;
  message?: string | null;
}> {
  const response = await apiRequest<ApiResponse<{
    session_id: string;
    status: 'completed';
    strategy_id?: string;
    message?: string | null;
  }>>(`/assistant/sessions/${params.sessionId}/strategy-sync`, {
    method: 'POST',
    body: JSON.stringify({
      event_summary: params.eventSummary,
      fact_check: params.factCheck || '',
      initial_actions: params.initialActions || '',
      short_term_goals: params.shortTermGoals || '',
      mid_term_goals: params.midTermGoals || '',
      long_term_goals: params.longTermGoals || '',
      time_constraints: params.timeConstraints || '',
      budget_constraints: params.budgetConstraints || '',
      additional_info: params.additionalInfo || '',
    }),
    timeoutMs: 300000,
  });
  return response.data as {
    session_id: string;
    status: 'completed';
    strategy_id?: string;
    message?: string | null;
  };
}

export async function getAssistantTaskStatusFromApi(taskId: string): Promise<AssistantTaskStatus> {
  const response = await apiRequest<ApiResponse<AssistantTaskStatus>>(`/assistant/tasks/${taskId}`, {
    timeoutMs: 30000,
  });
  const data = response.data as AssistantTaskStatus;
  const audioUrl = data?.result?.audio_url;
  if (audioUrl && !audioUrl.startsWith('http') && data.result) {
    const normalizedPath = audioUrl.replace(/^\/api\//, '/');
    data.result.audio_url = `${runtimeConfig.frontendApiBaseUrl.replace(/\/$/, '')}${normalizedPath}`;
  }
  return data;
}

export async function exportAssistantReportPdfInApi(params: {
  reportId?: string | null;
  sessionId?: string | null;
}): Promise<void> {
  const response = await fetch(`${runtimeConfig.frontendApiBaseUrl}/reports/export-pdf`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      reportId: params.reportId ?? undefined,
      sessionId: params.sessionId ?? undefined,
    }),
  });

  if (!response.ok) {
    let detail = '报告导出失败';
    try {
      const payload = await response.json();
      detail = payload?.detail || payload?.message || detail;
    } catch {
      detail = await response.text().catch(() => detail);
    }
    throw new Error(detail);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const matched = disposition.match(/filename=([^;]+)/i);
  const filename = matched?.[1]?.replace(/["']/g, '') || 'report_export.pdf';
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
}

export async function analyzeWithApi(body: AnalysisInput): Promise<any> {
  const response = await apiRequest<ApiResponse<any>>('/assistant/analyze', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return response.data;
}

export async function searchOverviewApi(params: {
  sessionId: string;
  query: string;
  userPrompt?: string;
  sourceUrl?: string;
  platformHint?: string;
  maxResults?: number;
}): Promise<any> {
  // Use real endpoint which properly saves messages via MCP
  const response = await apiRequest<ApiResponse<any>>('/assistant/tools/search-overview', {
    method: 'POST',
    body: JSON.stringify({
      session_id: params.sessionId,
      query: params.query,
      user_prompt: params.userPrompt || '',
      source_url: params.sourceUrl || '',
      platform_hint: params.platformHint || '',
      max_results: params.maxResults || 10,
    }),
    timeoutMs: 30000,
  });
  return response.data;
}

export async function analyzeRumorApi(params: {
  sessionId: string;
  query: string;
  userPrompt?: string;
  sourceUrl?: string;
  platformHint?: string;
  maxResults?: number;
}): Promise<any> {
  const response = await apiRequest<ApiResponse<any>>('/assistant/tools/analyze-rumor', {
    method: 'POST',
    body: JSON.stringify({
      session_id: params.sessionId,
      query: params.query,
      user_prompt: params.userPrompt || '',
      source_url: params.sourceUrl || '',
      platform_hint: params.platformHint || '',
      max_results: params.maxResults || 8,
    }),
  });
  return response.data;
}

export async function textToSpeechApi(params: {
  text: string;
  sessionId?: string;
  voiceId?: string;
  provider?: string;
}): Promise<{
  audio_url: string;
  duration_seconds: number;
  provider: string;
  text_preview: string;
}> {
  const estimatedTimeoutMs = Math.min(
    120000,
    Math.max(30000, Math.ceil((params.text || '').length * 35)),
  );
  const response = await apiRequest<ApiResponse<{
    audio_url: string;
    duration_seconds: number;
    provider: string;
    text_preview: string;
  }>>('/assistant/tts', {
    method: 'POST',
    body: JSON.stringify({
      text: params.text,
      session_id: params.sessionId || '',
      voice_id: params.voiceId || '',
      provider: params.provider || '',
    }),
    timeoutMs: estimatedTimeoutMs,
  });
  const data = response.data as {
    audio_url: string;
    duration_seconds: number;
    provider: string;
    text_preview: string;
  };
  // Ensure audio_url is absolute (browsers resolve relative URLs from page origin)
  if (data.audio_url && !data.audio_url.startsWith('http')) {
    // frontendApiBaseUrl ends with /api, so strip leading /api from returned path to avoid double /api/api
    const normalizedPath = data.audio_url.replace(/^\/api\//, '/');
    data.audio_url = `${runtimeConfig.frontendApiBaseUrl.replace(/\/$/, '')}${normalizedPath}`;
  }
  return data;
}

export async function textToSpeechAsyncApi(params: {
  sessionId: string;
  messageId: string;
  text: string;
  voiceId?: string;
  provider?: string;
}): Promise<{
  task_id: string;
  status: 'processing' | 'completed';
  message_id: string;
}> {
  const response = await apiRequest<ApiResponse<{
    task_id: string;
    status: 'processing' | 'completed';
    message_id: string;
  }>>('/assistant/tts/async', {
    method: 'POST',
    body: JSON.stringify({
      session_id: params.sessionId,
      message_id: params.messageId,
      text: params.text,
      voice_id: params.voiceId || '',
      provider: params.provider || '',
    }),
    timeoutMs: 30000,
  });
  return response.data as {
    task_id: string;
    status: 'processing' | 'completed';
    message_id: string;
  };
}

export async function uploadMultimodalAnalysisApi(params: {
  sessionId: string;
  files: File[];
  query?: string;
}): Promise<{
  task_id: string;
  status: 'processing';
  session_id: string;
  file_count?: number;
}> {
  const formData = new FormData();
  params.files.forEach((file) => {
    formData.append('files', file);
  });
  if (params.query) formData.append('query', params.query);
  const response = await apiRequest<ApiResponse<{
    task_id: string;
    status: 'processing';
    session_id: string;
    file_count?: number;
  }>>(`/assistant/sessions/${params.sessionId}/multimodal-analysis`, {
    method: 'POST',
    body: formData,
    timeoutMs: 120000,
  });
  return response.data;
}

export async function uploadVideoAnalysisApi(params: {
  sessionId: string;
  file: File;
  query?: string;
}): Promise<{
  task_id: string;
  status: 'processing';
  session_id: string;
}> {
  const result = await uploadMultimodalAnalysisApi({
    sessionId: params.sessionId,
    files: [params.file],
    query: params.query,
  });
  return {
    task_id: result.task_id,
    status: result.status,
    session_id: result.session_id,
  };
}

type StreamHandlers = {
  onChunk?: (chunk: string) => void;
  onError?: (message: string, payload?: Record<string, any>) => void;
  onWarning?: (message: string, payload?: Record<string, any>) => void;
  onStart?: () => void;
  onReady?: () => void;
  onDone?: (payload: Record<string, any>) => void;
  onGrounding?: (payload: Record<string, any>) => void;
  signal?: AbortSignal;
};

export type StreamAnalyzeResult = {
  status: 'complete' | 'partial_complete';
  warning?: string | null;
};

function parseSseEvents(buffer: string): { events: Array<{ event: string; data: string }>; remainder: string } {
  const parts = buffer.split('\n\n');
  const remainder = parts.pop() ?? '';
  const events = parts
    .map((part) => {
      const lines = part.split('\n').filter(Boolean);
      let event = 'message';
      const dataLines: string[] = [];

      for (const line of lines) {
        if (line.startsWith('event:')) {
          event = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5));
        }
      }

      return { event, data: dataLines.join('\n') };
    })
    .filter((item) => item.data !== '' || item.event !== 'message');

  return { events, remainder };
}

export async function streamAssistantMessageInApi(body: AnalysisInput, handlers: StreamHandlers = {}): Promise<StreamAnalyzeResult> {
  console.log('[streamAnalyze] START, calling fetch to', `${runtimeConfig.frontendApiBaseUrl}/assistant/stream`, 'body:', JSON.stringify(body).slice(0, 100));
  let response: Response;
  try {
    response = await fetch(`${runtimeConfig.frontendApiBaseUrl}/assistant/stream`, {
    method: 'POST',
    credentials: 'include',
    signal: handlers.signal,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  } catch (fetchErr) {
    console.error('[streamAnalyze] fetch threw:', fetchErr);
    throw fetchErr;
  }
  console.log('[streamAnalyze] fetch returned, status:', response?.status, 'body:', response?.body ? 'exists' : 'NULL');

  if (!response.ok || !response.body) {
    let detail = '流式请求失败';
    try {
      const payload = await response.json();
      detail = payload?.detail || payload?.message || detail;
    } catch {
      detail = await response.text().catch(() => detail);
    }
    throw new Error(detail);
  }

  const decoder = new TextDecoder('utf-8');
  const reader = response.body.getReader();
  let buffer = '';
  let latestWarning: string | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseEvents(buffer);
    buffer = parsed.remainder;

    for (const event of parsed.events) {
      if (event.event === 'start') {
        handlers.onStart?.();
        continue;
      }
      if (event.event === 'ready') {
        handlers.onReady?.();
        continue;
      }
      if (event.event === 'error') {
        let errorMessage = event.data || '流式输出失败';
        let errorPayload: Record<string, any> | undefined;
        try {
          const payload = JSON.parse(event.data);
          errorPayload = payload && typeof payload === 'object' ? payload : undefined;
          errorMessage = payload?.error || errorMessage;
        } catch {
          // Keep original text
        }
        handlers.onError?.(errorMessage, errorPayload);
        throw new Error(errorMessage);
      }
      if (event.event === 'warning') {
        let warningMessage = event.data || '流式输出出现异常';
        let warningPayload: Record<string, any> | undefined;
        try {
          const payload = JSON.parse(event.data);
          warningPayload = payload && typeof payload === 'object' ? payload : undefined;
          warningMessage = payload?.warning || warningMessage;
        } catch {
          // Keep original text
        }
        latestWarning = warningMessage;
        handlers.onWarning?.(warningMessage, warningPayload);
        continue;
      }
      if (event.event === 'done') {
        try {
          const payload = JSON.parse(event.data);
          const result = payload && typeof payload === 'object' ? payload : {};
          // 打印最终文本（用于调试）
          const content = (result as any)?.content;
          if (content) {
            console.log('[streamAnalyze] FINAL TEXT:', String(content).slice(0, 200));
          }
          handlers.onDone?.(result);
          return {
            status: payload?.status === 'partial_complete' ? 'partial_complete' : 'complete',
            warning: payload?.warning || latestWarning,
          };
        } catch (e) {
          handlers.onDone?.({});
          return {
            status: 'complete',
            warning: latestWarning,
          };
        }
      }
      if (event.event === 'grounding') {
        try {
          const payload = JSON.parse(event.data);
          handlers.onGrounding?.(payload && typeof payload === 'object' ? payload : {});
        } catch {
          handlers.onGrounding?.({});
        }
        continue;
      }
      if (event.event === 'message') {
        let chunk = event.data;
        try {
          const payload = JSON.parse(event.data);
          chunk = payload?.chunk ?? chunk;
        } catch {
          // Keep raw chunk for backward compatibility.
        }
        handlers.onChunk?.(chunk);
      }
    }
  }

  return {
    status: 'complete',
    warning: latestWarning,
  };
}
