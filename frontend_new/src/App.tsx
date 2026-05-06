// [DEBUG] 如果你在浏览器刷新后仍看到这条注释，说明Vite正在加载最新代码
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Send, Home, Plus, ChevronRight, FileText, CheckCircle2, Loader2, Bot, User, ChevronUp, ChevronDown, Lock, Eye, EyeOff, Mail, ShieldCheck, ArrowRight, Activity, Shield, Share2, LineChart, X, PanelLeftClose, PanelLeftOpen, Hexagon, Gauge, BookOpen, LayoutDashboard, MoreHorizontal, HelpCircle, Languages, PauseCircle, Upload, Trash2, FolderPlus, Radar, Sparkles, Search, RotateCcw, Volume2, Bug } from 'lucide-react';
import { ComposableMap, Geographies, Geography, Graticule, Sphere, Marker } from 'react-simple-maps';
import { PieChart, Pie, Cell, ResponsiveContainer, AreaChart as RechartsAreaChart, Area, CartesianGrid, Tooltip as RechartsTooltip, XAxis, YAxis, ReferenceLine } from 'recharts';
import { AssistantMarkdownContent } from './components/AssistantMarkdownContent';
import { Sidebar } from './components/Sidebar';
import { runtimeConfig } from './config/runtime';
import { ApiError } from './services/api/client';
import worldAtlasUrl from 'world-atlas/countries-110m.json?url';
import {
  analyze,
  createAssistantSession,
  deleteAssistantSession,
  exportAssistantReportPdf,
  generateAssistantReport,
  generateAssistantStrategy,
  generateAssistantStrategySync,
  getAssistantHome,
  getAssistantMessages,
  getAssistantPanels,
  getAssistantTaskStatus,
  getRecommendationSummary,
  getAssistantSessions,
  getCurrentUser,
  getCommandCenter,
  getKnowledgeBases,
  getKnowledgeFiles,
  getRagAnswer,
  rebuildKnowledgeBaseIndex,
  login,
  logout,
  renameAssistantSession,
  register,
  retryKnowledgeFileIndex,
  retryKnowledgeFileParse,
  streamAnalyze,
  createKnowledgeBase,
  uploadKnowledgeFile,
  deleteKnowledgeFile,
  searchOverview,
  analyzeRumor,
  saveAssistantSessionMessage,
  uploadMultimodalAnalysis,
  textToSpeech,
  textToSpeechAsync,
  } from './services';
import type {
  AIBrief,
  AIDataPreviewItem,
  AIRecommendationCard,
  AIReport,
  AIStrategy,
  AssistantTaskStatus,
  ChatMessage,
  ChatSession,
} from './types/assistant';
import type { LoginForm, RegisterForm, User as AuthUser } from './types/auth';
import type { CommandCenterData, CommandCenterEvent } from './types/dashboard';
import type { KnowledgeBase, KnowledgeFile } from './types/knowledge';
import type { RagAnswerResult } from './types/rag';

const sentimentLabelMap = {
  positive: '正',
  neutral: '中',
  negative: '负',
} as const;

const sourceTypeLabelMap = {
  news: '新闻报道',
  social: '社交媒体',
  video: '短视频平台',
  knowledge_chunk: '知识库',
  knowledge_record: '结构化记录',
  web: '网页来源',
} as const;

const emptyPanels = {
  dataPreview: [] as AIDataPreviewItem[],
  brief: null as AIBrief | null,
  report: null as AIReport | null,
  strategy: null as AIStrategy | null,
};

type AssistantPanelsData = {
  dataPreview: AIDataPreviewItem[];
  brief: AIBrief | null;
  report: AIReport | null;
  strategy: AIStrategy | null;
};

const groundingLabelMap: Record<string, string> = {
  grounded: '已溯源',
  partially_grounded: '部分溯源',
  ungrounded: '未溯源',
};

const multimodalDegradeLabelMap: Record<string, string> = {
  upstream_unavailable: '服务繁忙',
  quota_exhausted: '额度紧张',
  network_timeout: '请求超时',
  invalid_response: '结果兜底解析',
  config_error: '配置异常',
  file_processing_failed: '文件处理失败',
};

const HOME_DEFAULT_MODEL = '万象智体';

const HOME_CACHE_STORAGE_KEY = 'wanxiang:assistant-home-cache:v6';
const CHAT_KB_BINDINGS_STORAGE_KEY = 'wanxiang:chat-kb-bindings:v1';
const TTS_AUTO_PLAY_STORAGE_KEY = 'wanxiang:tts-auto-play:v1';
const ALL_KNOWLEDGE_BASE_OPTION_VALUE = '__all__';
const MULTIMODAL_MAX_FILES = 10;
const MULTIMODAL_ACCEPT = 'image/jpeg,image/png,image/webp,audio/mpeg,audio/wav,audio/mp4,audio/x-m4a,audio/aac,video/mp4,video/quicktime,video/x-msvideo,.jpg,.jpeg,.png,.webp,.mp3,.wav,.m4a,.aac,.mp4,.mov,.avi';
const MULTIMODAL_SIZE_LIMITS_MB: Record<'image' | 'audio' | 'video', number> = {
  image: 20,
  audio: 50,
  video: 100,
};

const readCachedHomeData = (): {
  recommendationCards: AIRecommendationCard[];
  defaultModel: string;
  suggestedPrompts: string[];
} | null => {
  try {
    const raw = window.localStorage.getItem(HOME_CACHE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.recommendationCards)) {
      return null;
    }
    return {
      recommendationCards: parsed.recommendationCards,
      defaultModel: HOME_DEFAULT_MODEL,
      suggestedPrompts: Array.isArray(parsed.suggestedPrompts) ? parsed.suggestedPrompts : [],
    };
  } catch {
    return null;
  }
};

const writeCachedHomeData = (value: {
  recommendationCards: AIRecommendationCard[];
  defaultModel: string;
  suggestedPrompts: string[];
}) => {
  try {
    window.localStorage.setItem(HOME_CACHE_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // ignore local cache write failures
  }
};

const readChatKnowledgeBindings = (): Record<string, string> => {
  try {
    const raw = window.localStorage.getItem(CHAT_KB_BINDINGS_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
      ? Object.fromEntries(
          Object.entries(parsed)
            .map(([key, value]) => [String(key), String(value || '').trim()])
            .filter(([, value]) => Boolean(value)),
        )
      : {};
  } catch {
    return {};
  }
};

const writeChatKnowledgeBindings = (value: Record<string, string>) => {
  try {
    window.localStorage.setItem(CHAT_KB_BINDINGS_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // ignore local cache write failures
  }
};

const readTtsAutoPlay = (): boolean => {
  try {
    const raw = window.localStorage.getItem(TTS_AUTO_PLAY_STORAGE_KEY);
    return raw === 'true';
  } catch { return false; }
};

const writeTtsAutoPlay = (value: boolean): void => {
  try {
    window.localStorage.setItem(TTS_AUTO_PLAY_STORAGE_KEY, String(value));
  } catch { /* ignore */ }
};

const detectMultimodalFileType = (fileName: string): 'image' | 'audio' | 'video' | null => {
  const normalized = String(fileName || '').toLowerCase();
  if (/\.(jpg|jpeg|png|webp)$/.test(normalized)) {
    return 'image';
  }
  if (/\.(mp3|wav|m4a|aac)$/.test(normalized)) {
    return 'audio';
  }
  if (/\.(mp4|mov|avi)$/.test(normalized)) {
    return 'video';
  }
  return null;
};

const validateMultimodalFiles = (files: File[]) => {
  if (!files.length) {
    return '至少需要选择一个媒体文件';
  }
  if (files.length > MULTIMODAL_MAX_FILES) {
    return `同一轮对话最多上传 ${MULTIMODAL_MAX_FILES} 个文件`;
  }
  for (const file of files) {
    const modality = detectMultimodalFileType(file.name);
    if (!modality) {
      return `不支持的文件格式：${file.name}`;
    }
    const limitMb = MULTIMODAL_SIZE_LIMITS_MB[modality];
    if (file.size > limitMb * 1024 * 1024) {
      return `${file.name} 不能超过 ${limitMb}MB`;
    }
  }
  return '';
};

const describeMultimodalUpload = (uploadingMedia: {
  names: string[];
  size: number;
  fileCount: number;
  processedCount?: number;
  failedCount?: number;
}) => {
  const names = uploadingMedia.names || [];
  const firstName = names[0] || '媒体文件';
  const remaining = Math.max(0, Number(uploadingMedia.fileCount || names.length || 0) - 1);
  return {
    title: remaining > 0 ? `${firstName} 等 ${remaining + 1} 个文件` : firstName,
    sizeLabel: `${(Number(uploadingMedia.size || 0) / (1024 * 1024)).toFixed(1)} MB`,
    countLabel: `${Number(uploadingMedia.processedCount || 0)}/${Number(uploadingMedia.fileCount || names.length || 0)}`,
  };
};

const getRecommendationFallbackImage = ({
  author,
  sourceLabel,
}: {
  author?: string;
  sourceLabel?: string;
}) => {
  const normalized = `${author || ''} ${sourceLabel || ''}`.toLowerCase();
  if (normalized.includes('微博') || normalized.includes('weibo')) {
    return '/fallbacks/微博.jpg';
  }
  if (normalized.includes('哔哩') || normalized.includes('bilibili')) {
    return '/fallbacks/哔哩哔哩.jpg';
  }
  if (normalized.includes('百度') || normalized.includes('baidu') || normalized.includes('tieba')) {
    return '/fallbacks/百度.jpg';
  }
  if (normalized.includes('抖音') || normalized.includes('douyin') || normalized.includes('快手') || normalized.includes('kuaishou')) {
    return '/fallbacks/抖音.jpg';
  }
  if (normalized.includes('知乎') || normalized.includes('zhihu') || normalized.includes('头条') || normalized.includes('toutiao')) {
    return '/fallbacks/微博.jpg';
  }
  if (normalized.includes('少数派') || normalized.includes('sspai') || normalized.includes('it之家') || normalized.includes('ithome') || normalized.includes('澎湃') || normalized.includes('thepaper') || normalized.includes('腾讯') || normalized.includes('qq-news')) {
    return '/fallbacks/哔哩哔哩.jpg';
  }
  return '/fallbacks/微博.jpg';
};

const adaptGeneratedReportToPanel = (report: {
  reportId: string;
  sessionId: string;
  data: Record<string, any>;
  isFallback: boolean;
  createdAt?: string;
}) => ({
  id: String(report.reportId),
  title: String(report.data?.meta?.title ?? report.data?.title ?? '事件分析报告'),
  createdAt: String(report.createdAt ?? ''),
  isFallback: Boolean(report.isFallback),
  content: report.data ?? {},
});

const buildPanelsFromGeneratedReport = (report: {
  reportId: string;
  sessionId: string;
  data: Record<string, any>;
  isFallback: boolean;
  createdAt?: string;
}) => {
  const panelReport = adaptGeneratedReportToPanel(report);
  const reportData = report.data ?? {};
  const meta = reportData.meta ?? {};
  const executiveSummary = reportData.executiveSummary ?? {};
  const detailedAnalysis = reportData.detailedAnalysis ?? {};
  const analysisDetails = reportData.analysisDetails ?? {};
  const rawDataSummary = reportData.rawDataSummary ?? {};

  const keyFindings = Array.isArray(executiveSummary.keyFindings)
    ? executiveSummary.keyFindings.map(String).filter(Boolean)
    : [];
  const topTrends = Array.isArray(executiveSummary.topTrends)
    ? executiveSummary.topTrends
    : [];
  const dataSources = Array.isArray(analysisDetails.dataSources)
    ? analysisDetails.dataSources
    : [];
  const sampleData = Array.isArray(rawDataSummary.sampleData)
    ? rawDataSummary.sampleData
    : [];
  const peakEvents = Array.isArray(detailedAnalysis?.propagationAnalysis?.peakEvents)
    ? detailedAnalysis.propagationAnalysis.peakEvents
    : [];
  const topicKeywords = Array.isArray(detailedAnalysis?.topicAnalysis?.mainTopics)
    ? detailedAnalysis.topicAnalysis.mainTopics
    : [];

  const briefSummary =
    keyFindings[0]
    || String(detailedAnalysis?.propagationAnalysis?.overview || '')
    || String(detailedAnalysis?.sentimentAnalysis?.overview || '')
    || String(meta.analysisContext || '')
    || `${panelReport.title} 已生成。`;

  const briefHighlights = [
    ...keyFindings.slice(0, 3),
    ...topTrends.slice(0, 2).map((item: any) => `趋势：${item.name}（热度 ${item.value ?? '未知'}）`),
    ...peakEvents.slice(0, 2).map((item: any) => `峰值事件：${item.title || item.description || '未命名事件'}`),
  ].filter(Boolean).slice(0, 5);

  const dataPreview: AIDataPreviewItem[] = [
    ...dataSources.slice(0, 2).map((item: any, index: number) => ({
      id: `${report.sessionId}-source-${index + 1}`,
      sourceType: String(item.type || '').includes('社交') ? 'social' : 'news',
      title: String(item.name || `数据源 ${index + 1}`),
      summary: `类型：${item.type || '未标注'}；可信度：${item.reliability ?? '未知'}；覆盖度：${item.coverage ?? '未知'}`,
      publishedAt: '',
      sourceLabel: '报告数据源',
    })),
    ...sampleData.slice(0, 2).map((item: any, index: number) => ({
      id: `${report.sessionId}-sample-${index + 1}`,
      sourceType: String(item.source || '').includes('社交') ? 'social' : 'news',
      title: String(item.source || `样本 ${index + 1}`),
      summary: String(item.content || ''),
      publishedAt: String(item.timestamp || ''),
      sourceLabel: `情绪：${item.sentiment || '未知'}`,
    })),
    ...topicKeywords.slice(0, 1).map((item: any, index: number) => ({
      id: `${report.sessionId}-topic-${index + 1}`,
      sourceType: 'social',
      title: `核心话题：${item.topic || '未命名话题'}`,
      summary: `关联关键词：${Array.isArray(item.relatedKeywords) ? item.relatedKeywords.join('、') : '暂无'}；声量：${item.sourceCount ?? '未知'}`,
      publishedAt: '',
      sourceLabel: `权重：${item.weight ?? '未知'}`,
    })),
  ].filter((item) => item.summary || item.title);

  return {
    report: panelReport,
    brief: {
      summary: briefSummary,
      highlights: briefHighlights.length > 0 ? briefHighlights : ['报告已生成，但暂无可提炼的关键摘要。'],
    },
    dataPreview,
  };
};

const buildFallbackPanelReport = ({
  title,
  content,
}: {
  title?: string | null;
  content?: Record<string, any> | string | null;
}): AIReport | null => {
  if (!content || typeof content !== 'object' || Array.isArray(content)) {
    return null;
  }

  return {
    id: `fallback-report-${Date.now()}`,
    title: String(title || (content as Record<string, any>)?.meta?.title || '事件分析报告'),
    createdAt: '',
    isFallback: false,
    content,
  };
};

const isStructuredGeneratedReport = (report: AIReport | null) => Boolean(
  report?.content?.meta &&
  report?.content?.executiveSummary &&
  report?.content?.detailedAnalysis,
);

const shouldHideMessage = (message: ChatMessage) => {
  if (message.role === 'system') {
    return true;
  }
  if (message.renderMode === 'hidden') {
    return true;
  }
  if (typeof message.content !== 'string') {
    return false;
  }
  const normalized = message.content.replace(/\s+/g, '').replace(/\*/g, '');
  return (
    normalized.startsWith('基于AI对话的公关策略生成器') &&
    normalized.includes('你是一位顶级的整合策略顾问和AI助手') &&
    normalized.includes('拥有深厚的行业分析能力和丰富的策略规划经验')
  );
};

const sanitizeMessages = (items: ChatMessage[]) => items.filter((message) => !shouldHideMessage(message));

const AssistantAvatar = ({ isLoading = false }: { isLoading?: boolean }) => {
  if (isLoading) {
    return (
      <div className="relative w-9 h-9 flex-shrink-0">
        <div className="absolute inset-0 rounded-full bg-[conic-gradient(from_0deg,_#93c5fd,_#2563eb,_#60a5fa,_#38bdf8,_#93c5fd)] animate-spin shadow-[0_0_18px_rgba(59,130,246,0.35)]" />
        <div className="absolute inset-[2px] rounded-full bg-white/90 backdrop-blur-sm" />
        <div className="absolute inset-[5px] rounded-full bg-gradient-to-br from-sky-400 via-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-inner">
          <Bot size={16} />
        </div>
      </div>
    );
  }

  return (
    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex-shrink-0 flex items-center justify-center text-white shadow-sm">
      <Bot size={18} />
    </div>
  );
};

const looksLikeStrategyOutputContent = (content: string) => (
  content.length >= 180 &&
  (
    /传播策略|公关策略|动作清单|执行清单|实施步骤|时间表|短期|中期|长期|优先级/.test(content) ||
    (/一、/.test(content) && /二、/.test(content) && /三、/.test(content) && /策略|动作|执行/.test(content))
  )
);

const STRATEGY_PLACEHOLDER_TEXT = '好的，我正在整合所有信息，准备生成策略...';

const normalizeSuggestedActionText = (value: string) => String(value || '')
  .trim()
  .replace(/[“”"'`]/g, '')
  .replace(/[。！!？?,，；;：:\s]+/g, '')
  .replace(/^请继续围绕/, '')
  .replace(/^请基于当前已知信息先给我一版/, '')
  .replace(/^请基于当前对话生成/, '')
  .replace(/^请继续往下分析并给我更具体的/, '')
  .replace(/^帮我分析这个热点[:：]?/, '')
  .replace(/^标题[:：]?/, '');

type SuggestionTodoStage = 'understand_topic' | 'generate_report' | 'generate_strategy';

const classifyTodoStageFromText = (value: string): SuggestionTodoStage | null => {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return null;
  }

  if (
    /(传播策略|公关策略|策略清单|动作清单|执行清单|实施步骤|策略方案|时间表|对外口径|内部动作)/.test(normalized)
  ) {
    return 'generate_strategy';
  }

  if (
    /(分析报告|正式报告|事件报告|舆情报告|专报|简报|预览报告|查看报告|生成报告|生成简报|生成专报|出一版报告|出报告|整理成报告|整理成简报|写一版报告|输出报告)/.test(normalized)
  ) {
    return 'generate_report';
  }

  if (
    /(传播脉络|争议点|关键信息缺口|关键疑点|补充信息|待核实|风险判断|应对建议|背景信息|还有什么能补充|补充这个主题)/.test(normalized)
  ) {
    return 'understand_topic';
  }

  return null;
};

const buildSuggestedNextAction = (
  message: ChatMessage,
  workflowState: {
    hasReport: boolean;
    hasStrategy: boolean;
  },
  sessionTitle?: string,
  latestUserInput?: string,
  conversationTurns = 0,
  recentUserInputs: string[] = [],
) => {
  const content = String(message.content || '');
  if (!content || message.status === 'streaming' || message.status === 'error') {
    return null;
  }

  const normalizedSessionTitle = String(sessionTitle || '').trim();
  const normalizedUserInput = String(latestUserInput || '').trim().replace(/[。！!？?]+$/g, '');
  const suggestedAnalysisTarget = resolveSuggestedAnalysisTarget({
    latestUserInput: normalizedUserInput,
    sessionTitle: normalizedSessionTitle,
  });
  const normalizedRecentUserInputs = recentUserInputs
    .map((item) => String(item || '').trim())
    .filter(Boolean);
  const duplicatedRecentUserInputs = Array.from(new Set(
    normalizedRecentUserInputs
      .map(normalizeSuggestedActionText)
      .filter(Boolean),
  ));
  const recentTodoStages = normalizedRecentUserInputs
    .map((item) => classifyTodoStageFromText(item))
    .filter((item): item is SuggestionTodoStage => Boolean(item));
  const repeatedActionCount = (pattern: RegExp) => normalizedRecentUserInputs.filter((item) => pattern.test(item)).length;
  const repeatedReportActionCount = repeatedActionCount(/分析报告|正式报告|事件报告|舆情报告|专报|简报|生成报告|生成简报|生成专报|出一版报告|出报告/);
  const repeatedStrategyActionCount = repeatedActionCount(/传播策略|公关策略|策略清单|动作清单|执行清单|实施步骤|策略方案|时间表/);
  const currentSuggestionNormalized = normalizeSuggestedActionText(content);
  const hasSufficientBackground =
    workflowState.hasReport ||
    (/事件|舆情|传播|风险|主体|时间|经过|争议|脉络|影响/.test(content) && content.length >= 120) ||
    conversationTurns >= 2;
  const hasRepeatedStrategyPrompt =
    duplicatedRecentUserInputs.length < normalizedRecentUserInputs.length &&
    normalizedRecentUserInputs.some((item) => /风险判断|应对建议|应对策略|传播路径|阶段|动作建议|继续围绕|继续往下分析/.test(item));
  const shouldSuggestReport =
    !workflowState.hasReport &&
    Boolean(suggestedAnalysisTarget) &&
    (
      hasSufficientBackground ||
      recentTodoStages.includes('understand_topic') ||
      conversationTurns >= 4 ||
      (conversationTurns >= 3 && /研判|分析|传播|风险|回应|舆情|事件/.test(content)) ||
      hasRepeatedStrategyPrompt
    );

  const understandTopicDone =
    workflowState.hasReport ||
    recentTodoStages.includes('understand_topic') ||
    repeatedActionCount(/传播脉络|争议点|关键信息缺口|关键疑点|补充信息|待核实|风险判断|应对建议|背景信息|还有什么能补充|补充这个主题/) >= 1 ||
    conversationTurns >= 3;
  const generateReportDone =
    workflowState.hasReport ||
    recentTodoStages.includes('generate_report');
  const generateStrategyDone =
    workflowState.hasStrategy ||
    recentTodoStages.includes('generate_strategy');

  const todoSuggestions: Array<{ stage: SuggestionTodoStage; text: string | null; done: boolean }> = [
    {
      stage: 'understand_topic',
      text: suggestedAnalysisTarget
        ? `请继续围绕“${suggestedAnalysisTarget}”补充传播脉络、争议点和关键信息缺口`
        : '请继续补充这个主题的传播脉络、争议点和关键信息缺口',
      done: understandTopicDone,
    },
    {
      stage: 'generate_report',
      text: suggestedAnalysisTarget ? `请基于当前对话生成${suggestedAnalysisTarget}的分析报告` : null,
      done: generateReportDone || !suggestedAnalysisTarget || !shouldSuggestReport,
    },
    {
      stage: 'generate_strategy',
      text: '请继续把这份分析扩展成可执行的传播策略与动作清单',
      done: generateStrategyDone || !workflowState.hasReport,
    },
  ];

  if (workflowState.hasStrategy) {
    return null;
  }

  if (/待补充|待核实|请补充|缺失信息|需要补充/.test(content)) {
    todoSuggestions[0].done = false;
  }

  if (/风险|传播|回应|应对|舆情|事件/.test(content) && !workflowState.hasReport) {
    if (hasRepeatedStrategyPrompt || repeatedReportActionCount >= 2) {
      todoSuggestions[0].done = true;
      if (suggestedAnalysisTarget) {
        todoSuggestions[1].done = false;
      }
    }
  }

  if (!workflowState.hasReport && recentTodoStages.includes('understand_topic') && suggestedAnalysisTarget) {
    todoSuggestions[0].done = true;
    todoSuggestions[1].done = false;
  }

  const nextTodo = todoSuggestions.find((item) => !item.done && item.text);
  if (nextTodo) {
    const normalizedNextSuggestion = normalizeSuggestedActionText(String(nextTodo.text || ''));
    if (normalizedNextSuggestion && normalizedNextSuggestion !== currentSuggestionNormalized) {
      return nextTodo.text;
    }
  }

  if (!workflowState.hasReport && suggestedAnalysisTarget) {
    return `请基于当前对话生成${suggestedAnalysisTarget}的分析报告`;
  }

  if (workflowState.hasReport && !workflowState.hasStrategy) {
    return '请继续把这份分析扩展成可执行的传播策略与动作清单';
  }

  if (/你好|您好|很高兴见到你|请随时告诉我/.test(content)) {
    return '请基于当前热点，先推荐一个最值得深度分析的舆情议题';
  }

  return null;
};

const attachSuggestedActionsToMessages = (
  items: ChatMessage[],
  sessionTitle?: string,
) => {
  let hasReport = false;
  let hasStrategy = false;
  let userConversationTurns = 0;
  const recentUserInputs: string[] = [];

  return items.map((message) => {
    const nextMessage = { ...message, suggestedAction: null as string | null };

    if (message.role === 'user') {
      userConversationTurns += 1;
      recentUserInputs.push(String(message.content || ''));
      if (recentUserInputs.length > 4) {
        recentUserInputs.shift();
      }
      return nextMessage;
    }

    const suggestion = buildSuggestedNextAction(
      message,
      {
        hasReport,
        hasStrategy,
      },
      sessionTitle,
      recentUserInputs.at(-1),
      userConversationTurns,
      recentUserInputs,
    );

    if (message.messageType === 'event_report' || message.renderMode === 'report_card') {
      hasReport = true;
    }
    if (message.messageType === 'strategy_plan' || message.renderMode === 'strategy_card') {
      hasStrategy = true;
    }

    nextMessage.suggestedAction = suggestion;
    return nextMessage;
  });
};

const isUsableAnalysisTarget = (value?: string | null) => {
  const normalized = String(value || '').trim().replace(/[。！!？?]+$/g, '');
  if (!normalized) {
    return false;
  }

  if (normalized.length < 4 || normalized.length > 40) {
    return false;
  }

  if (/^(你好|您好|test\d*|新对话|未命名会话)$/i.test(normalized)) {
    return false;
  }

  if (/^(请|帮我|给我|继续|再|基于|按照|围绕|针对)/.test(normalized)) {
    return false;
  }

  if (/(分析|判断|建议|研判|怎么看|帮我看看|给我一版|继续往下|下一步|口径|策略|生成报告|生成简报|生成专报|预览报告|预览简报|点击查看|查看详情)/.test(normalized)) {
    return false;
  }

  return true;
};

const extractEventAnalysisTarget = (text: string) => {
  const normalized = String(text || '').trim().replace(/[。！!？?]+$/g, '');
  if (!normalized) {
    return null;
  }

  const matched = normalized.match(/^我想对(.+?)进行事件分析$/);
  if (matched?.[1]) {
    return matched[1].trim();
  }

  return null;
};

const extractAnalysisTopicCandidate = (text: string) => {
  const normalized = String(text || '').trim();
  if (!normalized) {
    return null;
  }

  const patterns = [
    /(?:帮我分析(?:这个)?热点[:：]\s*)(.+)$/i,
    /(?:请围绕以下热点.*?标题[:：]\s*)(.+?)(?:\n|$)/i,
    /(?:标题[:：]\s*)(.+?)(?:\n|$)/i,
    /(?:继续围绕[“"]?)(.+?)(?:[”"]?给我一版.*)$/i,
    /(?:围绕[“"]?)(.+?)(?:[”"]?给我一版.*)$/i,
    /(?:请基于当前对话生成)(.+?)(?:的分析报告)$/i,
  ];

  for (const pattern of patterns) {
    const matched = normalized.match(pattern);
    if (matched?.[1]) {
      return matched[1].trim().replace(/[。！!？?]+$/g, '');
    }
  }

  return null;
};

const extractExplicitReportTarget = (text: string) => {
  const normalized = String(text || '').trim().replace(/[。！!？?]+$/g, '');
  if (!normalized) {
    return null;
  }

  const patterns = [
    /^请基于(.+?)生成(?:一版)?(?:正式)?(?:事件)?(?:分析)?(?:报告|简报|专报)$/,
    /^请把(.+?)整理成(?:一版)?(?:正式)?(?:事件)?(?:分析)?(?:报告|简报|专报)$/,
    /^帮我把(.+?)整理成(?:一版)?(?:正式)?(?:事件)?(?:分析)?(?:报告|简报|专报)$/,
    /^帮我生成(.+?)的(?:正式)?(?:事件)?(?:分析)?(?:报告|简报|专报)$/,
    /^请生成(.+?)的(?:正式)?(?:事件)?(?:分析)?(?:报告|简报|专报)$/,
    /^针对(.+?)(?:生成|整理成|输出|写一版)(?:一版)?(?:正式)?(?:事件)?(?:分析)?(?:报告|简报|专报)$/,
    /^围绕(.+?)(?:生成|整理成|输出|写一版)(?:一版)?(?:正式)?(?:事件)?(?:分析)?(?:报告|简报|专报)$/,
    /^对(.+?)(?:生成|整理成|输出|写一版)(?:一版)?(?:正式)?(?:事件)?(?:分析)?(?:报告|简报|专报)$/,
  ];

  for (const pattern of patterns) {
    const matched = normalized.match(pattern);
    if (matched?.[1]) {
      return matched[1].trim();
    }
  }

  return null;
};

const resolveSuggestedAnalysisTarget = ({
  latestUserInput,
  sessionTitle,
}: {
  latestUserInput?: string;
  sessionTitle?: string;
}) => {
  const extractedUserTarget = extractEventAnalysisTarget(String(latestUserInput || ''));
  if (isUsableAnalysisTarget(extractedUserTarget)) {
    return extractedUserTarget;
  }

  const inferredUserTarget = extractAnalysisTopicCandidate(String(latestUserInput || ''));
  if (isUsableAnalysisTarget(inferredUserTarget)) {
    return inferredUserTarget;
  }

  const normalizedUserInput = String(latestUserInput || '').trim();
  if (isUsableAnalysisTarget(normalizedUserInput)) {
    return normalizedUserInput;
  }

  const inferredSessionTarget = extractAnalysisTopicCandidate(String(sessionTitle || ''));
  if (isUsableAnalysisTarget(inferredSessionTarget)) {
    return inferredSessionTarget;
  }

  const normalizedSessionTitle = String(sessionTitle || '').trim();
  if (isUsableAnalysisTarget(normalizedSessionTitle)) {
    return normalizedSessionTitle;
  }

  return null;
};

const resolveEventReportRequest = ({
  text,
  sessionTitle,
}: {
  text: string;
  sessionTitle?: string;
}) => {
  const normalized = String(text || '').trim().replace(/[。！!？?]+$/g, '');
  if (!normalized) {
    return null;
  }

  const extractedTarget =
    extractEventAnalysisTarget(normalized) ||
    extractExplicitReportTarget(normalized);
  if (isUsableAnalysisTarget(extractedTarget)) {
    const target = String(extractedTarget).trim();
    return {
      target,
      title: `${target}事件分析报告`,
    };
  }

  const hasReportIntent = /(分析报告|正式报告|事件报告|舆情报告|专报|简报|预览报告|查看报告|生成报告|生成简报|生成专报|出一版报告|出报告|整理成报告|整理成简报|写一版报告|输出报告)/.test(normalized);
  const hasNaturalReportIntent =
    /(整理成|汇总成|形成|沉淀成|输出成|做成|转成|写成|扩展成|升级成|整理出|给我一版|出一版)/.test(normalized) &&
    /(正式版|完整版|完整分析|完整研判|分析成稿|研判成稿|正式分析|正式研判|一版成稿|报告|简报|专报)/.test(normalized);
  if (!hasReportIntent && !hasNaturalReportIntent) {
    return null;
  }

  const fallbackTarget = resolveSuggestedAnalysisTarget({
    latestUserInput: normalized,
    sessionTitle,
  });
  if (!isUsableAnalysisTarget(fallbackTarget)) {
    return null;
  }

  const target = String(fallbackTarget).trim();
  return {
    target,
    title: `${target}事件分析报告`,
  };
};

const isStrategyGenerationIntent = (text: string) => {
  const normalized = String(text || '').trim().replace(/[。！!？?]+$/g, '');
  if (!normalized) {
    return false;
  }

  return /(传播策略|公关策略|策略清单|动作清单|执行清单|实施步骤|策略方案|时间表)/.test(normalized);
};

const createStrategyCardMessage = ({
  sessionId,
  title,
  content = STRATEGY_PLACEHOLDER_TEXT,
  strategyStatus = 'generating',
}: {
  sessionId: string;
  title: string;
  content?: string;
  strategyStatus?: 'idle' | 'generating' | 'ready';
}): ChatMessage => ({
  id: `${sessionId}-strategy-card-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  sessionId,
  role: 'assistant',
  content,
  createdAt: new Date().toISOString(),
  messageType: 'strategy_plan',
  renderMode: 'strategy_card',
  status: strategyStatus === 'generating' ? 'streaming' : 'done',
  strategyTitle: title,
  strategyStatus,
});

const buildStrategyPayload = ({
  panelData,
  sessionTitle,
  latestUserInput,
}: {
  panelData: AssistantPanelsData;
  sessionTitle?: string;
  latestUserInput?: string;
}) => {
  const reportContent = panelData.report?.content ?? {};
  const executiveSummary = reportContent.executiveSummary ?? {};
  const detailedAnalysis = reportContent.detailedAnalysis ?? {};
  const insightsAndRecommendations = reportContent.insightsAndRecommendations ?? {};
  const analysisDetails = reportContent.analysisDetails ?? {};
  const rawDataSummary = reportContent.rawDataSummary ?? {};
  const keyFindings = Array.isArray(executiveSummary.keyFindings)
    ? executiveSummary.keyFindings.map(String).filter(Boolean)
    : [];
  const topTrends = Array.isArray(executiveSummary.topTrends)
    ? executiveSummary.topTrends.map((item: any) => {
        if (typeof item === 'string') {
          return item;
        }
        if (item && typeof item === 'object') {
          const trend = String(item.trend || item.name || item.topic || '').trim();
          const description = String(item.description || item.summary || item.signal || '').trim();
          return [trend, description].filter(Boolean).join('：');
        }
        return String(item || '').trim();
      }).filter(Boolean)
    : [];
  const highlights = Array.isArray(panelData.brief?.highlights)
    ? panelData.brief?.highlights.map(String).filter(Boolean)
    : [];
  const dataPreviewLines = panelData.dataPreview
    .slice(0, 5)
    .map((item) => `${item.title}：${item.summary}`)
    .filter(Boolean);
  const mainTopics = Array.isArray(detailedAnalysis?.topicAnalysis?.mainTopics)
    ? detailedAnalysis.topicAnalysis.mainTopics.map((item: any) => {
        if (typeof item === 'string') {
          return item;
        }
        if (item && typeof item === 'object') {
          const topic = String(item.topic || item.name || '').trim();
          const keywords = Array.isArray(item.keywords) ? item.keywords.map(String).filter(Boolean).join('、') : '';
          return [topic, keywords ? `关键词：${keywords}` : ''].filter(Boolean).join('；');
        }
        return String(item || '').trim();
      }).filter(Boolean)
    : [];
  const keyChallenges = Array.isArray(insightsAndRecommendations?.keyChallenges)
    ? insightsAndRecommendations.keyChallenges.map(String).filter(Boolean)
    : [];
  const opportunities = Array.isArray(insightsAndRecommendations?.opportunities)
    ? insightsAndRecommendations.opportunities.map(String).filter(Boolean)
    : [];
  const potentialRisks = Array.isArray(insightsAndRecommendations?.riskAssessment?.potentialRisks)
    ? insightsAndRecommendations.riskAssessment.potentialRisks.map(String).filter(Boolean)
    : [];
  const dataSources = Array.isArray(analysisDetails?.dataSources)
    ? analysisDetails.dataSources.map((item: any) => {
        if (typeof item === 'string') {
          return item;
        }
        if (item && typeof item === 'object') {
          return String(item.name || item.source || item.title || '').trim();
        }
        return String(item || '').trim();
      }).filter(Boolean)
    : [];
  const targetTitle = resolveSuggestedAnalysisTarget({
    latestUserInput,
    sessionTitle,
  }) || sessionTitle || '当前事件';
  const eventSummary = [
    `事件主题：${targetTitle}`,
    latestUserInput ? `用户原始需求：${latestUserInput}` : '',
    panelData.report?.title ? `关联报告：${panelData.report.title}` : '',
    panelData.brief?.summary || '',
    String(detailedAnalysis?.propagationAnalysis?.overview || ''),
    String(detailedAnalysis?.sentimentAnalysis?.overview || ''),
    String(executiveSummary?.overallSentiment?.label || ''),
  ].filter(Boolean).join('\n');
  const factCheck = [
    ...keyFindings.slice(0, 4),
    ...topTrends.slice(0, 3),
    ...dataPreviewLines.slice(0, 3),
  ].filter(Boolean).join('\n');
  const additionalInfo = [
    mainTopics.length ? `核心议题：\n- ${mainTopics.slice(0, 5).join('\n- ')}` : '',
    keyChallenges.length ? `当前挑战：\n- ${keyChallenges.slice(0, 4).join('\n- ')}` : '',
    opportunities.length ? `可利用机会：\n- ${opportunities.slice(0, 4).join('\n- ')}` : '',
    potentialRisks.length ? `重点风险：\n- ${potentialRisks.slice(0, 4).join('\n- ')}` : '',
    highlights.length ? `简报高亮：\n- ${highlights.slice(0, 4).join('\n- ')}` : '',
    dataSources.length ? `数据来源：${dataSources.slice(0, 5).join('、')}` : '',
    rawDataSummary?.totalSources ? `样本来源总量：${String(rawDataSummary.totalSources)}` : '',
    rawDataSummary?.totalMessages ? `样本消息总量：${String(rawDataSummary.totalMessages)}` : '',
    '要求：策略必须紧扣以上事件事实、议题、传播脉络与风险，不要套用与当前话题无关的通用危机公关模板。',
  ].filter(Boolean).join('\n\n');

  return {
    eventSummary: eventSummary || `请围绕“${targetTitle}”生成可执行策略。`,
    factCheck,
    initialActions: keyChallenges.length
      ? `请优先围绕这些挑战设计首轮动作：${keyChallenges.slice(0, 3).join('；')}`
      : '请基于当前报告中的已知事实、传播议题和关键风险，给出可立即执行的首轮动作。',
    shortTermGoals: opportunities.length
      ? `在24小时内，围绕“${targetTitle}”把这些机会转成短期传播成果：${opportunities.slice(0, 2).join('；')}`
      : `在24小时内完成围绕“${targetTitle}”的核心回应、重点议题塑形与声量引导。`,
    midTermGoals: mainTopics.length
      ? `在3-7天内，围绕这些议题持续推进传播：${mainTopics.slice(0, 3).join('；')}`
      : '在3-7天内推进关键信息补充、重点平台传播引导与舆论重心塑造。',
    longTermGoals: `在7-30天内，围绕“${targetTitle}”形成可复用的传播主线、风险复盘机制与长期认知资产。`,
    timeConstraints: '优先按24小时、3天、7天、30天四个时间窗口输出动作，并明确负责人、目标和交付物。',
    budgetConstraints: '优先输出高相关、高确定性动作；避免为了凑完整度加入与当前事件弱相关的大型模板动作。',
    additionalInfo,
  };
};

const resolveAssistantTaskErrorMessage = (taskResult: AssistantTaskStatus) => {
  const result = taskResult.result;
  return String(
    result?.user_message
    || result?.degrade_message
    || taskResult.message
    || result?.error
    || '多模态分析失败'
  );
};

const normalizeAssistantTtsErrorMessage = (rawMessage?: string | null) => {
  const normalized = String(rawMessage || '').trim();
  if (!normalized) {
    return '语音生成失败';
  }
  const lowered = normalized.toLowerCase();
  if (
    lowered.includes('chat.generate_tts_for_message')
    || lowered.includes('notregistered')
    || lowered.includes('received unregistered task')
    || lowered.includes('unregistered task')
  ) {
    return '语音任务未成功启动，请稍后重试';
  }
  if (lowered.includes('failed to fetch')) {
    return '语音服务暂时不可用，请稍后重试';
  }
  if (lowered.includes('detected_unusual_activity') || lowered.includes('unusual activity')) {
    return '语音服务账号当前受限，请稍后重试';
  }
  return normalized;
};

const resolveAssistantTtsErrorMessage = (taskResult: AssistantTaskStatus) => {
  const result = taskResult.result;
  return normalizeAssistantTtsErrorMessage(
    result?.tts_error
    || result?.user_message
    || taskResult.message
    || result?.error
  );
};

const mergeTtsUiState = (previousItems: ChatMessage[], nextItems: ChatMessage[]) => {
  if (!previousItems.length || !nextItems.length) {
    return nextItems;
  }

  const previousById = new Map(previousItems.map((item) => [item.id, item]));
  return nextItems.map((item) => {
    const previous = previousById.get(item.id);
    if (!previous) {
      return item;
    }

    if (item.audioUrl || item.ttsStatus === 'ready' || item.ttsStatus === 'failed') {
      return item;
    }

    if (previous.audioUrl) {
      return {
        ...item,
        audioUrl: previous.audioUrl,
        ttsStatus: previous.ttsStatus || 'ready',
        ttsTaskId: previous.ttsTaskId || item.ttsTaskId,
        ttsProvider: previous.ttsProvider || item.ttsProvider,
        ttsDurationSeconds: previous.ttsDurationSeconds ?? item.ttsDurationSeconds,
        ttsError: previous.ttsError || item.ttsError,
      };
    }

    if (
      previous.ttsStatus === 'failed'
      && !item.audioUrl
      && (item.ttsStatus === 'processing' || !item.ttsStatus)
    ) {
      return {
        ...item,
        ttsStatus: 'failed',
        ttsTaskId: previous.ttsTaskId || item.ttsTaskId,
        ttsError: previous.ttsError || item.ttsError || '语音生成失败',
      };
    }

    if (
      previous.ttsStatus === 'processing'
      && !item.audioUrl
      && !item.ttsStatus
    ) {
      return {
        ...item,
        ttsStatus: 'processing',
        ttsTaskId: previous.ttsTaskId || item.ttsTaskId,
        ttsError: previous.ttsError || item.ttsError,
      };
    }

    return item;
  });
};

type TtsMessagePatch = {
  sessionId: string;
  messageId: string;
  ttsStatus?: ChatMessage['ttsStatus'];
  audioUrl?: string;
  ttsTaskId?: string;
  ttsProvider?: string;
  ttsDurationSeconds?: number;
  ttsError?: string;
};

const applyTtsMessagePatch = (items: ChatMessage[], patch: TtsMessagePatch): ChatMessage[] => {
  const targetSessionId = String(patch.sessionId || '').trim();
  const targetMessageId = String(patch.messageId || '').trim();
  if (!targetSessionId || !targetMessageId || !items.length) {
    return items;
  }

  return items.map((item) => {
    if (item.id !== targetMessageId || item.sessionId !== targetSessionId || item.role !== 'assistant') {
      return item;
    }

    if (item.audioUrl && item.ttsStatus === 'ready' && !patch.audioUrl && patch.ttsStatus !== 'ready') {
      return item;
    }

    if (item.ttsStatus === 'failed' && patch.ttsStatus === 'processing' && !patch.audioUrl) {
      return item;
    }

    const next: ChatMessage = { ...item };
    if ('ttsStatus' in patch) {
      next.ttsStatus = patch.ttsStatus;
    }
    if ('audioUrl' in patch) {
      next.audioUrl = patch.audioUrl;
    }
    if ('ttsTaskId' in patch) {
      next.ttsTaskId = patch.ttsTaskId;
    }
    if ('ttsProvider' in patch) {
      next.ttsProvider = patch.ttsProvider;
    }
    if ('ttsDurationSeconds' in patch) {
      next.ttsDurationSeconds = patch.ttsDurationSeconds;
    }
    if ('ttsError' in patch) {
      next.ttsError = patch.ttsError;
    }
    return next;
  });
};

const buildTtsMessagePatchFromTaskResult = (
  sessionId: string,
  taskId: string,
  fallbackMessageId: string,
  taskResult: AssistantTaskStatus,
): TtsMessagePatch | null => {
  const result = taskResult.result;
  const messageId = String(result?.message_id || fallbackMessageId || '').trim();
  if (!messageId) {
    return null;
  }

  if (taskResult.status === 'failed') {
    return {
      sessionId,
      messageId,
      ttsTaskId: taskId,
      ttsStatus: 'failed',
      ttsError: resolveAssistantTtsErrorMessage(taskResult),
    };
  }

  return {
    sessionId,
    messageId,
    ttsTaskId: taskId,
    ttsStatus: (result?.tts_status as ChatMessage['ttsStatus']) || 'ready',
    audioUrl: result?.audio_url || undefined,
    ttsProvider: result?.provider || undefined,
    ttsDurationSeconds: typeof result?.duration_seconds === 'number' ? result.duration_seconds : undefined,
    ttsError: undefined,
  };
};

const waitForAssistantTaskCompletion = async (
  taskId: string,
  options?: {
    onProgress?: (result: AssistantTaskStatus) => void;
  },
) => {
  const maxAttempts = 60;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const result = await getAssistantTaskStatus(taskId);
    if (result.status === 'completed' || result.status === 'failed') {
      return result;
    }
    options?.onProgress?.(result);
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
  }
  throw new Error('任务处理超时，请稍后在历史消息中查看结果');
};

const shouldFallbackToSyncStrategy = (message?: string | null) => {
  const normalized = String(message || '').trim();
  if (!normalized) {
    return true;
  }
  return !normalized.includes('缺少必要的字段')
    && !normalized.includes('聊天会话不存在')
    && !normalized.includes('无权访问');
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

const findEventReportAssistantMessage = (items: ChatMessage[], requestContent: string) => {
  let requestIndex = -1;
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const candidate = items[index];
    if (candidate.role === 'user' && String(candidate.content || '').trim() === requestContent.trim()) {
      requestIndex = index;
      break;
    }
  }

  if (requestIndex < 0) {
    return null;
  }

  for (let index = requestIndex + 1; index < items.length; index += 1) {
    const candidate = items[index];
    if (candidate.role === 'assistant') {
      return candidate;
    }
  }

  return null;
};

const applyEventReportCardToMessages = (
  items: ChatMessage[],
  eventReport: { assistantMessageId: string; title: string; reportStatus?: 'idle' | 'generating' | 'ready' } | null,
) => {
  if (!eventReport) {
    return items;
  }

  return items.map((item) => (
    item.id === eventReport.assistantMessageId
      ? {
          ...item,
          messageType: 'event_report',
          renderMode: 'report_card',
          reportTitle: eventReport.title,
          reportStatus: eventReport.reportStatus ?? item.reportStatus ?? 'idle',
        }
      : item
  ));
};

const createEventReportCardMessage = ({
  sessionId,
  title,
  content = '',
  reportStatus = 'generating',
}: {
  sessionId: string;
  title: string;
  content?: string;
  reportStatus?: 'idle' | 'generating' | 'ready';
}): ChatMessage => ({
  id: `${sessionId}-report-card-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  sessionId,
  role: 'assistant',
  content,
  createdAt: new Date().toISOString(),
  messageType: 'event_report',
  renderMode: 'report_card',
  status: 'done',
  reportTitle: title,
  reportStatus,
});

const buildReportCardSummaryFromContent = (content?: Record<string, any> | null) => {
  if (!content || typeof content !== 'object' || Array.isArray(content)) {
    return '报告已生成';
  }

  const executiveSummary = content.executiveSummary && typeof content.executiveSummary === 'object'
    ? content.executiveSummary
    : {};
  const keyFindings = Array.isArray(executiveSummary.keyFindings)
    ? executiveSummary.keyFindings.map((item: any) => String(item || '').trim()).filter(Boolean)
    : [];

  if (keyFindings.length > 0) {
    return keyFindings.slice(0, 3).join('\n');
  }

  const summaryCandidates = [
    executiveSummary.summary,
    content.overview,
    content.summary,
    content.meta?.title,
    content.title,
  ];

  const firstSummary = summaryCandidates
    .map((item) => String(item || '').trim())
    .find(Boolean);

  return firstSummary || '报告已生成';
};

const normalizeReportObjectList = (value: unknown): Record<string, any>[] =>
  Array.isArray(value) ? value.filter((item): item is Record<string, any> => isPlainObject(item)) : [];

const renderReportValue = (value: unknown, fallback = '未标注') => {
  if (value === null || value === undefined) {
    return fallback;
  }
  const normalized = String(value).trim();
  return normalized || fallback;
};

const renderPercentLike = (value: unknown, fallback = '未知') => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return `${numeric}%`;
};

const renderScoreLike = (value: unknown, fallback = '未知') => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return `${numeric}`;
};

const hydrateHistoricalReportCards = (
  items: ChatMessage[],
  options: {
    panelReport?: AIReport | null;
    sessionTitle?: string;
  } = {},
) => {
  const { panelReport = null, sessionTitle } = options;
  const hydrated: ChatMessage[] = items.map((item) => ({
    ...item,
    messageType: item.messageType ?? 'plain',
    renderMode: item.renderMode ?? 'bubble',
  }));
  const rebuilt: ChatMessage[] = [...hydrated];

  let latestEventReportCard: {
    sessionId: string;
    assistantMessageId: string;
    title: string;
    content: string | Record<string, any> | null;
  } | null = null;

  for (let index = 0; index < hydrated.length; index += 1) {
    const message = hydrated[index];
    const reportRequest = message.role === 'user'
      ? resolveEventReportRequest({ text: String(message.content || '') })
      : null;
    if (!reportRequest) {
      continue;
    }

    const title = reportRequest.title;
    const assistantOffset = hydrated.slice(index + 1).findIndex((item) => item.role === 'assistant');
    if (assistantOffset < 0) {
      continue;
    }
    const assistantIndex = index + 1 + assistantOffset;
    const assistantMessage = hydrated[assistantIndex];
    assistantMessage.renderMode = 'hidden';

    const cardMessage = createEventReportCardMessage({
      sessionId: assistantMessage.sessionId,
      title,
      content: assistantMessage.content,
      reportStatus: 'ready',
    });
    rebuilt.splice(assistantIndex + 1, 0, cardMessage);
    latestEventReportCard = {
      sessionId: cardMessage.sessionId,
      assistantMessageId: cardMessage.id,
      title,
      content: assistantMessage.content,
    };
  }

  const seenReportCardKeys = new Set<string>();
  const dedupedMessages = rebuilt.filter((item) => {
    if (item.renderMode !== 'report_card') {
      return true;
    }

    const dedupeKey = `${item.sessionId}:${item.reportTitle || item.content || ''}:${item.reportStatus || 'idle'}`;
    if (seenReportCardKeys.has(dedupeKey)) {
      return false;
    }
    seenReportCardKeys.add(dedupeKey);
    return true;
  });

  const latestReadyReportCard = [...dedupedMessages]
    .reverse()
    .find((item) => item.renderMode === 'report_card');
  if (latestReadyReportCard) {
    latestEventReportCard = {
      sessionId: latestReadyReportCard.sessionId,
      assistantMessageId: latestReadyReportCard.id,
      title: latestReadyReportCard.reportTitle || '事件分析报告',
      content: latestReadyReportCard.content,
    };
  }

  const hasPersistedReportCard = dedupedMessages.some((item) => item.renderMode === 'report_card');
  if (!hasPersistedReportCard && panelReport) {
    const synthesizedCard = createEventReportCardMessage({
      sessionId: dedupedMessages[0]?.sessionId || '',
      title: panelReport.title || sessionTitle || '事件分析报告',
      content: buildReportCardSummaryFromContent(panelReport.content),
      reportStatus: 'ready',
    });
    synthesizedCard.createdAt = panelReport.createdAt || new Date().toISOString();

    const assistantBubbleIndexes = dedupedMessages
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => item.role === 'assistant' && item.renderMode !== 'hidden' && item.renderMode !== 'report_card' && item.renderMode !== 'strategy_card');
    const synthesizedMessages = [...dedupedMessages];

    if (assistantBubbleIndexes.length === 1) {
      const anchorIndex = assistantBubbleIndexes[0].index;
      synthesizedMessages[anchorIndex] = {
        ...synthesizedMessages[anchorIndex],
        renderMode: 'hidden',
      };
      synthesizedMessages.splice(anchorIndex + 1, 0, synthesizedCard);
    } else {
      synthesizedMessages.push(synthesizedCard);
    }

    latestEventReportCard = {
      sessionId: synthesizedCard.sessionId,
      assistantMessageId: synthesizedCard.id,
      title: synthesizedCard.reportTitle || panelReport.title || sessionTitle || '事件分析报告',
      content: panelReport.content,
    };

    return {
      messages: synthesizedMessages,
      latestEventReportCard,
    };
  }

  const messagesWithHiddenSource = dedupedMessages.map((item) => ({ ...item }));
  for (let index = 1; index < messagesWithHiddenSource.length; index += 1) {
    const message = messagesWithHiddenSource[index];
    if (message.renderMode !== 'report_card') {
      continue;
    }
    const previous = messagesWithHiddenSource[index - 1];
    if (
      previous.role === 'assistant' &&
      previous.renderMode !== 'hidden' &&
      previous.renderMode !== 'report_card' &&
      previous.renderMode !== 'strategy_card'
    ) {
      messagesWithHiddenSource[index - 1] = {
        ...previous,
        renderMode: 'hidden',
      };
    }
  }

  return {
    messages: messagesWithHiddenSource,
    latestEventReportCard,
  };
};

const dedupeReportCardMessages = (items: ChatMessage[]) => {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (item.renderMode !== 'report_card') {
      return true;
    }
    const dedupeKey = `${item.sessionId}:${item.reportTitle || item.content || ''}:${item.reportStatus || 'idle'}`;
    if (seen.has(dedupeKey)) {
      return false;
    }
    seen.add(dedupeKey);
    return true;
  });
};

const hydrateHistoricalStrategyCards = (
  items: ChatMessage[],
  sessionTitle?: string,
) => {
  const hydrated: ChatMessage[] = ensureStableClientMessageIds(items).map((item) => ({
    ...item,
    messageType: item.messageType ?? 'plain',
    renderMode: item.renderMode ?? 'bubble',
  }));

  const rebuilt: ChatMessage[] = [];

  for (let index = 0; index < hydrated.length; index += 1) {
    const message = hydrated[index];

    if (message.role === 'assistant' && String(message.content || '').trim() === STRATEGY_PLACEHOLDER_TEXT) {
      const previousUser = hydrated.slice(0, index).reverse().find((item) => item.role === 'user');
      const isStrategyRequest =
        message.messageType === 'strategy_plan' ||
        message.renderMode === 'strategy_card' ||
        isStrategyGenerationIntent(String(previousUser?.content || ''));
      if (!isStrategyRequest) {
        rebuilt.push(message);
        continue;
      }
      const strategyTitleTarget = resolveSuggestedAnalysisTarget({
        latestUserInput: String(previousUser?.content || ''),
        sessionTitle,
      }) || sessionTitle || '当前事件';
      const hasCompletedStrategy = hydrated
        .slice(index + 1)
        .some((item) => item.role === 'assistant' && looksLikeStrategyOutputContent(String(item.content || '')));

      rebuilt.push({
        ...message,
        messageType: 'strategy_plan',
        renderMode: 'strategy_card',
        strategyTitle: `${strategyTitleTarget}传播策略`,
        strategyStatus: hasCompletedStrategy ? 'ready' : 'generating',
        status: hasCompletedStrategy ? 'done' : 'streaming',
      });
      continue;
    }

    rebuilt.push(message);
  }

  const hasReadyStrategyCard = rebuilt.some(
    (item) => item.renderMode === 'strategy_card' && item.strategyStatus === 'ready',
  );
  const readyStrategyTitles = new Set(
    rebuilt
      .filter((item) => item.renderMode === 'strategy_card' && item.strategyStatus === 'ready')
      .map((item) => item.strategyTitle || ''),
  );
  const seenStrategyCardKeys = new Set<string>();

  return rebuilt.filter((item) => {
    if (item.renderMode !== 'strategy_card') {
      return true;
    }

    const strategyTitle = item.strategyTitle || '';
    if (item.strategyStatus !== 'ready' && hasReadyStrategyCard) {
      return false;
    }
    if (item.strategyStatus !== 'ready' && readyStrategyTitles.has(strategyTitle)) {
      return false;
    }

    const dedupeKey = `${item.sessionId}:${strategyTitle}:${item.strategyStatus || 'idle'}`;
    if (seenStrategyCardKeys.has(dedupeKey)) {
      return false;
    }
    seenStrategyCardKeys.add(dedupeKey);
    return true;
  });
};

const recoverGeneratedReportArtifacts = async ({
  sessionId,
  sessionTitle,
}: {
  sessionId: string;
  sessionTitle?: string;
}) => {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const [sessionsResult, messagesResult, panelsResult] = await Promise.allSettled([
      getAssistantSessions(),
      getAssistantMessages(sessionId),
      getAssistantPanels(sessionId),
    ]);

    const nextMessagesFromBackend =
      messagesResult.status === 'fulfilled' ? messagesResult.value : null;
    const recoveredPanels =
      panelsResult.status === 'fulfilled' ? panelsResult.value : null;
    const hydratedMessages = nextMessagesFromBackend?.length
      ? hydrateHistoricalReportCards(sanitizeMessages(nextMessagesFromBackend), {
          panelReport: recoveredPanels?.report ?? null,
          sessionTitle,
        })
      : null;
    const hasRecoveredReport =
      Boolean(recoveredPanels?.report) ||
      Boolean(hydratedMessages?.latestEventReportCard) ||
      Boolean(
        hydratedMessages?.messages?.some((message) =>
          message.messageType === 'event_report' || message.renderMode === 'report_card',
        ),
      );

    if (hasRecoveredReport) {
      return {
        sessions: sessionsResult.status === 'fulfilled' ? sessionsResult.value : null,
        messages: hydratedMessages?.messages?.length
          ? hydrateHistoricalStrategyCards(hydratedMessages.messages, sessionTitle)
          : null,
        panels: recoveredPanels,
        latestEventReportCard: hydratedMessages?.latestEventReportCard ?? null,
      };
    }

    await sleep(1500);
  }

  return null;
};

const renderFormattedContent = (content: string) => {
  const text = String(content || '').replace(/\r\n/g, '\n').trim();
  if (!text) {
    return null;
  }

  const blocks = text.split(/\n{2,}/).filter(Boolean);

  return blocks.map((block, blockIndex) => {
    const trimmedBlock = block.trim();
    const lines = trimmedBlock.split('\n').filter(Boolean);
    const isBulletList = lines.length > 1 && lines.every((line) => /^([-*•]|\d+\.)\s+/.test(line.trim()));
    const isCodeBlock = trimmedBlock.includes('```');
    const isHeading = /^([#【\[])/.test(trimmedBlock) && lines.length <= 2;

    if (isCodeBlock) {
      return (
        <pre key={`block-${blockIndex}`} className="bg-gray-50 border border-gray-100 rounded-xl p-4 overflow-x-auto text-xs text-gray-700 whitespace-pre-wrap">
          {trimmedBlock.replace(/```/g, '')}
        </pre>
      );
    }

    if (isBulletList) {
      return (
        <ul key={`block-${blockIndex}`} className="space-y-2 pl-5 list-disc marker:text-blue-500">
          {lines.map((line, lineIndex) => (
            <li key={`line-${blockIndex}-${lineIndex}`} className="text-sm text-gray-700 leading-7">
              {line.replace(/^([-*•]|\d+\.)\s+/, '')}
            </li>
          ))}
        </ul>
      );
    }

    if (isHeading) {
      return (
        <div key={`block-${blockIndex}`} className="font-semibold text-gray-800 text-sm leading-7 whitespace-pre-wrap">
          {trimmedBlock}
        </div>
      );
    }

    return (
      <p key={`block-${blockIndex}`} className="text-sm text-gray-700 leading-8 whitespace-pre-wrap">
        {trimmedBlock}
      </p>
    );
  });
};

const buildOverviewFallbackMarkdown = (items: any[], summary: string) => {
  if (!items.length) {
    return summary || '未检索到有效结果，请换个关键词重试。';
  }

  const lines = [
    '### 总览搜索结果',
    `- 已检索到 ${items.length} 条相关信息`,
    '',
    '### 关键信息源',
  ];

  items.forEach((item: any, index: number) => {
    const title = String(item?.title || `结果 ${index + 1}`).trim();
    const url = String(item?.url || '').trim();
    const sourceName = String(item?.source_name || item?.platform || '未知来源').trim();
    const credibility = String(item?.credibility || 'medium').trim();
    const publishedAt = String(item?.published_at || '').trim();
    const excerpt = String(item?.content_excerpt || item?.summary || '').trim();
    const meta = [
      `来源：${sourceName}`,
      `可信度：${credibility}`,
      publishedAt ? `时间：${publishedAt}` : '',
    ].filter(Boolean).join(' | ');

    lines.push(url ? `- [${title}](${url})` : `- ${title}`);
    if (meta) {
      lines.push(`  - ${meta}`);
    }
    if (excerpt) {
      lines.push(`  - 摘要：${excerpt.slice(0, 200)}`);
    }
    lines.push('');
  });

  if (summary) {
    lines.push('---', '', '### 总结', summary);
  }

  return lines.join('\n');
};

const buildRumorFallbackMarkdown = (rumorData: Record<string, any>, items: any[], summary: string) => {
  if (!items.length) {
    return summary || '未检索到有效结果，请换个关键词重试。';
  }

  const verdict = String(rumorData?.verdict || '').trim();
  const riskLevel = String(rumorData?.risk_level || '').trim();
  const lines = [
    '### 谣言分析结果',
    verdict ? `- 当前判断：${verdict}` : '',
    riskLevel ? `- 风险级别：${riskLevel}` : '',
    '',
    '### 参考材料',
  ].filter(Boolean);

  items.forEach((item: any, index: number) => {
    const title = String(item?.title || `结果 ${index + 1}`).trim();
    const url = String(item?.url || '').trim();
    const sourceName = String(item?.source_name || item?.platform || '未知来源').trim();
    const credibility = String(item?.credibility || 'medium').trim();
    const publishedAt = String(item?.published_at || '').trim();
    const excerpt = String(item?.content_excerpt || item?.summary || '').trim();
    const meta = [
      `来源：${sourceName}`,
      `可信度：${credibility}`,
      publishedAt ? `时间：${publishedAt}` : '',
    ].filter(Boolean).join(' | ');

    lines.push(url ? `- [${title}](${url})` : `- ${title}`);
    if (meta) {
      lines.push(`  - ${meta}`);
    }
    if (excerpt) {
      lines.push(`  - 摘要：${excerpt.slice(0, 200)}`);
    }
    lines.push('');
  });

  if (summary) {
    lines.push('---', '', '### 总结', summary);
  }

  return lines.join('\n');
};

const createLocalFallbackMessages = (sessionId: string, userInput: string, errorMessage?: string): ChatMessage[] => {
  const timestamp = new Date().toISOString();
  const messages: ChatMessage[] = [
    {
      id: `${sessionId}-user-local`,
      sessionId,
      role: 'user',
      content: userInput,
      createdAt: timestamp,
      status: 'done',
    },
  ];

  if (errorMessage) {
    messages.push({
      id: `${sessionId}-assistant-local`,
      sessionId,
      role: 'assistant',
      content: `会话已经创建成功，但当前真实分析请求未返回完整结果：${errorMessage}`,
      createdAt: timestamp,
      status: 'error',
      tagLabel: '返回异常',
      reportStatus: 'idle',
    });
  }

  return messages;
};

const createGeneratingMessages = (sessionId: string, userInput: string): ChatMessage[] => {
  const timestamp = new Date().toISOString();
  return [
    {
      id: `${sessionId}-user-pending`,
      sessionId,
      role: 'user',
      content: userInput,
      createdAt: timestamp,
      status: 'done',
    },
    {
      id: `${sessionId}-assistant-generating`,
      sessionId,
      role: 'assistant',
      content: '正在检索相关信息并生成分析结果，请稍候...',
      createdAt: timestamp,
      status: 'streaming',
    },
  ];
};

const STREAMING_PLACEHOLDER_TEXT = '正在检索相关信息并生成分析结果，请稍候...';
const DEBUG_STREAMING_PLACEHOLDER_TEXT = 'Debug 模式：直接调用模型流式生成，请稍候...';

const buildClientFallbackMessageId = (message: ChatMessage, index: number) => {
  const raw = [
    String(message.sessionId || ''),
    String(message.role || ''),
    String(message.createdAt || ''),
    String(message.content || ''),
    String(index),
  ].join('||');

  let hash = 0;
  for (let offset = 0; offset < raw.length; offset += 1) {
    hash = ((hash << 5) - hash + raw.charCodeAt(offset)) | 0;
  }

  return `${message.sessionId || 'session'}-msg-${Math.abs(hash).toString(36)}-${index}`;
};

const ensureStableClientMessageIds = (items: ChatMessage[]) => {
  const seenIds = new Set<string>();

  return items.map((item, index) => {
    let nextId = String(item.id || '').trim() || buildClientFallbackMessageId(item, index);
    while (seenIds.has(nextId)) {
      nextId = `${nextId}-${index}`;
    }
    seenIds.add(nextId);
    return {
      ...item,
      id: nextId,
    };
  });
};

const createStreamingAssistantMessage = (sessionId: string): ChatMessage => ({
  id: `${sessionId}-assistant-streaming-${Date.now()}`,
  sessionId,
  role: 'assistant',
  content: STREAMING_PLACEHOLDER_TEXT,
  messageType: 'plain',
  renderMode: 'bubble',
  createdAt: new Date().toISOString(),
  status: 'streaming',
});

const finalizeMessageStatus = (
  items: ChatMessage[],
  messageId: string,
  updates: Partial<ChatMessage> = {},
) => items.map((item) => (
  item.id === messageId
    ? {
        ...item,
        ...updates,
      }
    : item
));

const isAbortError = (error: unknown) =>
  error instanceof DOMException && error.name === 'AbortError';

const normalizeStreamIssueMessage = (message: string, payload?: Record<string, any>) => {
  const fallbackReason = String(payload?.fallbackReason || '');
  const upstreamType = String(payload?.upstreamType || '');
  const upstreamCode = String(payload?.upstreamCode || '');
  const normalizedCode = upstreamCode.toLowerCase();

  if (
    fallbackReason === 'model_account_unavailable'
    || upstreamType === 'account_unavailable'
    || normalizedCode.includes('arrearage')
    || normalizedCode.includes('access_denied')
  ) {
    return '模型服务当前不可用或账号异常，请稍后重试。';
  }

  if (fallbackReason === 'tool_call_invalid_json' || upstreamType === 'tool_call_protocol_error') {
    return '工具调用协议异常，当前无法完成分析，请稍后重试。';
  }

  if (
    fallbackReason === 'content_safety'
    || upstreamType === 'content_safety'
    || normalizedCode.includes('inappropriate-content')
  ) {
    return '当前问题触发了上游内容安全限制，请尝试更换表述或补充更多背景信息。';
  }

  return message || '上游模型暂时未返回有效分析结果，请稍后重试。';
};

const mergeStreamPayloadMeta = (message: ChatMessage, payload?: Record<string, any>): ChatMessage => ({
  ...message,
  route: typeof payload?.route === 'string' ? payload.route : message.route,
  debugMode: typeof payload?.debugMode === 'boolean' ? payload.debugMode : message.debugMode,
  fallbackReason: typeof payload?.fallbackReason === 'string' ? payload.fallbackReason : message.fallbackReason,
  upstreamCode: typeof payload?.upstreamCode === 'string' ? payload.upstreamCode : message.upstreamCode,
  upstreamType: typeof payload?.upstreamType === 'string' ? payload.upstreamType : message.upstreamType,
  phase: typeof payload?.phase === 'string' ? payload.phase : message.phase,
  searchTimedOut: typeof payload?.searchTimedOut === 'boolean' ? payload.searchTimedOut : message.searchTimedOut,
  searchFailed: typeof payload?.searchFailed === 'boolean' ? payload.searchFailed : message.searchFailed,
});

const AnalysisWorkflowCard = ({
  title,
  panelData,
  isSendingMessage,
  isGeneratingReport,
  onShowPanel,
  isReportReady = false,
}: {
  title: string;
  panelData: AssistantPanelsData;
  isSendingMessage: boolean;
  isGeneratingReport: boolean;
  onShowPanel: (panel: 'none' | 'report' | 'data' | 'brief' | 'strategy') => void;
  isReportReady?: boolean;
}) => {
  const hasDataPreview = panelData.dataPreview.length > 0;
  const hasBrief = Boolean(panelData.brief);
  const hasReport = Boolean(panelData.report) || isReportReady;

  const renderStatusIcon = (status: 'done' | 'loading' | 'idle') => {
    if (status === 'done') {
      return <CheckCircle2 size={16} className="text-green-500" />;
    }
    if (status === 'loading') {
      return <Loader2 size={16} className="text-blue-500 animate-spin" />;
    }
    return <div className="w-4 h-4 rounded-full border-2 border-gray-300" />;
  };

  const dataStatus: 'done' | 'loading' | 'idle' = hasDataPreview ? 'done' : isSendingMessage ? 'loading' : 'idle';
  const briefStatus: 'done' | 'loading' | 'idle' = hasBrief ? 'done' : isSendingMessage && hasDataPreview ? 'loading' : 'idle';
  const reportStatus: 'done' | 'loading' | 'idle' = hasReport ? 'done' : (isGeneratingReport || (isSendingMessage && (hasBrief || hasDataPreview))) ? 'loading' : 'idle';

  return (
    <div className="mt-4 rounded-2xl border border-blue-100 bg-gradient-to-br from-slate-50 via-blue-50/70 to-white p-5">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-sky-400 text-white shadow-sm">
          <FileText size={18} />
        </div>
        <div>
          <div className="font-semibold text-gray-900">{title}</div>
          <div className="text-xs text-gray-500">已进入事件分析链路，系统将依次完成数据检索、简报生成和专报生成。</div>
        </div>
      </div>
      <div className="space-y-3 pl-13 text-sm">
        <div className="flex items-center gap-2 text-gray-700">
          {renderStatusIcon(dataStatus)}
          <span>检索数据</span>
          {hasDataPreview ? (
            <button className="ml-2 text-blue-500 hover:underline" onClick={() => onShowPanel('data')}>预览部分相关信息</button>
          ) : (
            <span className="ml-2 text-gray-400">{isSendingMessage ? '正在检索中' : '等待开始'}</span>
          )}
        </div>
        <div className="flex items-center gap-2 text-gray-700">
          {renderStatusIcon(briefStatus)}
          <span>生成简报</span>
          {hasBrief ? (
            <button className="ml-2 text-blue-500 hover:underline" onClick={() => onShowPanel('brief')}>预览简报</button>
          ) : (
            <span className="ml-2 text-gray-400">{isSendingMessage && hasDataPreview ? '正在生成中' : '等待开始'}</span>
          )}
        </div>
        <div className="flex items-center gap-2 text-gray-700">
          {renderStatusIcon(reportStatus)}
          <span>生成专报</span>
          {hasReport ? (
            <button className="ml-2 text-blue-500 hover:underline" onClick={() => onShowPanel('report')}>预览报告</button>
          ) : (
            <span className="ml-2 text-gray-400">{isSendingMessage && (hasBrief || hasDataPreview) ? '正在生成中' : '等待开始'}</span>
          )}
        </div>
      </div>
    </div>
  );
};

const EventReportPlaceholder = ({
  title,
  isPending,
  thinkingContent,
}: {
  title: string;
  isPending: boolean;
  thinkingContent?: string;
}) => (
  <div className="space-y-5">
    <div className={`inline-flex items-center rounded-full px-4 py-2 text-sm font-medium ${isPending ? 'bg-blue-50 text-blue-600' : 'bg-emerald-50 text-emerald-600'}`}>
      {isPending ? '万象智体正在生成' : '万象智体生成完毕'}
    </div>
    <p className="text-[18px] font-medium text-gray-900">
      {title}
    </p>
    {isPending ? (
      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 px-4 py-3">
        <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">
          分析过程
        </div>
        <div className="space-y-3 text-sm leading-8 text-slate-400">
          {thinkingContent
            ? renderFormattedContent(thinkingContent)
            : <p>正在基于当前输入梳理事件性质、时间前提与推演路径，请稍候...</p>}
        </div>
      </div>
    ) : (
      <p className="text-sm leading-8 text-gray-400">
        正式报告内容已经整理完成，完整正文已同步到右侧报告页，可直接查看详情。
      </p>
    )}
  </div>
);

const StrategyPlanPlaceholder = ({
  title,
  isPending,
}: {
  title: string;
  isPending: boolean;
}) => (
  <div className="space-y-5">
    <div className={`inline-flex items-center rounded-full px-4 py-2 text-sm font-medium ${isPending ? 'bg-amber-50 text-amber-600' : 'bg-emerald-50 text-emerald-600'}`}>
      {isPending ? '万象智体正在生成策略' : '万象智体策略已生成'}
    </div>
    <p className="text-[18px] font-medium text-gray-900">
      {title}
    </p>
    {isPending ? (
      <div className="rounded-2xl border border-amber-100 bg-amber-50/60 px-4 py-4 text-sm leading-8 text-amber-700">
        正在基于当前报告梳理传播路径、阶段动作和执行优先级，请稍候...
      </div>
    ) : (
      <div className="rounded-2xl border border-emerald-100 bg-emerald-50/60 px-4 py-4 text-sm leading-8 text-emerald-700">
        策略内容已经生成完成，结构化方案已同步到策略面板，可直接查看重点动作、风险与监测指标。
      </div>
    )}
  </div>
);

const TopNavbar = ({ activeTab, onSelect }: { activeTab: string, onSelect: (tab: string) => void }) => {
  const navItems = [
    { icon: <Bot size={18} className={activeTab === 'AI 舆情助手' ? "text-blue-500" : ""} />, label: 'AI 舆情助手' },
    { icon: <Gauge size={18} />, label: '智慧中枢' },
    { icon: <BookOpen size={18} />, label: '私有知识库' },
    { icon: <LayoutDashboard size={18} />, label: '可视化大屏' },
    { icon: <MoreHorizontal size={18} />, label: '' },
  ];

  return (
    <div className="fixed top-0 left-0 right-0 h-14 bg-white/80 backdrop-blur-md border-b border-gray-100 z-[60] flex items-center px-4 justify-between shadow-sm">
      <div className="flex items-center gap-4 min-w-0 flex-1">
        <button
          onClick={() => onSelect('万象智体')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all text-sm font-medium whitespace-nowrap ${
            activeTab === '万象智体' ? 'text-gray-900 bg-gray-100/80' : 'text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
          }`}
        >
          <Hexagon size={18} className={activeTab === '万象智体' ? 'text-emerald-500' : ''} />
          <span>万象智体</span>
        </button>
        <div className="flex-1 flex items-center justify-center overflow-x-auto scrollbar-hide">
          <div className="flex items-center gap-1 md:gap-4">
          {navItems.map((item, i) => (
            <button 
              key={i} 
              onClick={() => {
                if (item.label === '可视化大屏') {
                  window.open('http://1.12.225.53/mainscreen', '_blank');
                } else if (item.label) {
                  onSelect(item.label);
                }
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all text-sm font-medium whitespace-nowrap ${activeTab === item.label ? 'text-gray-900 bg-gray-100/80' : 'text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'}`}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {item.label && <span>{item.label}</span>}
            </button>
          ))}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3 text-gray-400 ml-4">
        <button className="hover:text-gray-600 transition-colors"><HelpCircle size={20} /></button>
        <button className="hover:text-gray-600 transition-colors"><Languages size={20} /></button>
      </div>
    </div>
  );
};

const BackgroundEffects = () => {
  const [mousePos, setMousePos] = useState({ x: -1000, y: -1000 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePos({ x: e.clientX, y: e.clientY });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  return (
    <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
      {/* Complex Gradient Background */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-200/40 blur-[120px]"></div>
      <div className="absolute top-[10%] right-[-5%] w-[40%] h-[60%] rounded-full bg-purple-200/40 blur-[130px]"></div>
      <div className="absolute bottom-[-20%] left-[20%] w-[60%] h-[50%] rounded-full bg-indigo-200/30 blur-[140px]"></div>
      
      {/* Base Dot Pattern */}
      <div 
        className="absolute inset-0 opacity-[0.4]"
        style={{
          backgroundImage: 'radial-gradient(circle at center, #cbd5e1 0.6px, transparent 0.6px)',
          backgroundSize: '9px 9px'
        }}
      />
      
      {/* Interactive Dot Pattern (Stitch-like effect) */}
      <div 
        className="absolute inset-0 opacity-100 transition-opacity duration-300"
        style={{
          backgroundImage: 'radial-gradient(circle at center, #60a5fa 0.75px, transparent 0.75px)',
          backgroundSize: '9px 9px',
          maskImage: `radial-gradient(circle 250px at ${mousePos.x}px ${mousePos.y}px, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%)`,
          WebkitMaskImage: `radial-gradient(circle 250px at ${mousePos.x}px ${mousePos.y}px, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%)`
        }}
      />
    </div>
  );
};

const RecommendationCard = ({ image, sentiment, title, author, sourceLabel, sentimentLabel, sentimentSourceLabel, onClick, className = "" }: { key?: string | number, image: string, sentiment: AIRecommendationCard['sentiment'], title: string, author: string, sourceLabel?: string, sentimentLabel?: string, sentimentSourceLabel?: string, onClick?: () => void, className?: string }) => {
  const fallbackImage = getRecommendationFallbackImage({ author, sourceLabel });
  const [displayImage, setDisplayImage] = useState(image || fallbackImage);

  useEffect(() => {
    setDisplayImage(image || fallbackImage);
  }, [fallbackImage, image]);

  return (
    <div 
      className={`bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden flex flex-col cursor-pointer hover:shadow-md transition-all hover:-translate-y-1 ${className}`}
      onClick={onClick}
    >
      <div className="h-32 bg-gray-200 relative">
        <img
          src={displayImage}
          alt={title}
          className="w-full h-full object-cover"
          referrerPolicy="no-referrer"
          loading="lazy"
          onError={() => {
            if (displayImage !== fallbackImage) {
              setDisplayImage(fallbackImage);
            }
          }}
        />
        <div className={`absolute top-2 right-2 text-white text-xs px-1.5 py-0.5 rounded-sm font-medium ${sentiment === 'negative' ? 'bg-red-500' : sentiment === 'positive' ? 'bg-green-500' : 'bg-yellow-500'}`}>
          {sentimentLabelMap[sentiment]}
        </div>
      </div>
      <div className="p-3 flex flex-col flex-1">
        <h4 className="text-base font-black text-gray-900 leading-7 line-clamp-2 min-h-[56px] mb-3" style={{ fontFamily: '"SimHei", "Microsoft YaHei", "PingFang SC", sans-serif' }}>{title}</h4>
        <div className="mt-auto flex items-center text-xs text-gray-500">
          <div className="w-4 h-4 rounded-full bg-gray-300 mr-1.5 overflow-hidden flex-shrink-0">
            <img src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${author}`} alt="avatar" />
          </div>
          <span className="truncate">{author}</span>
        </div>
      </div>
    </div>
  );
};

const formatRecommendationTime = (value?: string) => {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return '';
  }

  const timestamp = Date.parse(normalized);
  if (Number.isNaN(timestamp)) {
    return normalized;
  }

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp));
};

const buildRecommendationHint = (card: AIRecommendationCard) => {
  const sentimentText = card.sentiment === 'negative'
    ? '负向风险'
    : card.sentiment === 'positive'
      ? '正向传播'
      : '中性热点';

  const sourceText = card.sourceLabel || `来源平台：${card.author}`;

  return `当前卡片展示的是热榜聚合结果，可作为线索入口继续研判。建议先核对原始链接、发布时间、传播范围与上下文，再判断其是否需要进入正式分析流程。当前信号偏向${sentimentText}，请结合 ${sourceText} 做进一步核实。`;
};

const buildDeepAnalysisPrompt = (card: AIRecommendationCard) => [
  '请围绕以下热点做一版深度舆情分析，并明确区分已知事实、待核实信息与分析判断。',
  `标题：${card.title}`,
  `来源平台：${card.author}`,
  card.publishedAt ? `更新时间：${formatRecommendationTime(card.publishedAt)}` : '',
  card.url ? `原始链接：${card.url}` : '',
  '请重点输出：事件概述、传播脉络、风险点、情绪判断、关键疑点、下一步建议。',
].filter(Boolean).join('\n');

const buildRecommendationContext = (card: AIRecommendationCard) => ({
  title: card.title,
  sourceUrl: card.url || '',
  platformHint: card.author || '',
  summary: card.summary || '',
  publishedAt: card.publishedAt || '',
  sourceLabel: card.sourceLabel || '',
});

const extractRecommendationTitleFromInput = (input: string) => {
  const content = String(input || '').trim();
  if (!content) {
    return '';
  }

  const titleLine = content.split('\n').find((line) => line.trim().startsWith('标题：'));
  if (titleLine) {
    const separatorIndex = titleLine.indexOf('：');
    return separatorIndex >= 0 ? titleLine.slice(separatorIndex + 1).trim() : '';
  }

  const matched = content.match(/帮我分析这个热点[:：]\s*(.+)$/);
  if (matched?.[1]) {
    return matched[1].trim();
  }

  return '';
};

const resolveRecommendationContextFromInput = (
  input: string,
  recommendationCards: AIRecommendationCard[],
) => {
  const matchedTitle = extractRecommendationTitleFromInput(input);
  if (!matchedTitle) {
    return null;
  }

  const normalizedMatchedTitle = matchedTitle.replace(/\s+/g, '');
  const matchedCard = recommendationCards.find((card) => card.title.replace(/\s+/g, '') === normalizedMatchedTitle);
  return matchedCard ? buildRecommendationContext(matchedCard) : null;
};

const CardDetailModal = ({
  card,
  onClose,
  onDeepAnalyze,
  isAuthenticated,
}: {
  card: AIRecommendationCard | null,
  onClose: () => void,
  onDeepAnalyze: (card: AIRecommendationCard) => void,
  isAuthenticated: boolean,
}) => {
  if (!card) return null;
  const formattedPublishedAt = formatRecommendationTime(card.publishedAt);
  const recommendationHint = buildRecommendationHint(card);
  const fallbackImage = getRecommendationFallbackImage({
    author: card.author,
    sourceLabel: card.sourceLabel,
  });
  const [detailImage, setDetailImage] = useState(card.image || fallbackImage);
  const [detailSummary, setDetailSummary] = useState(card.summary || '');

  useEffect(() => {
    setDetailImage(card.image || fallbackImage);
  }, [card.image, fallbackImage]);

  useEffect(() => {
    let cancelled = false;
    setDetailSummary(card.summary || '');

    if (!card.url) {
      return () => {
        cancelled = true;
      };
    }

    void getRecommendationSummary({
      title: card.title,
      sourceUrl: card.url,
    }).then((result) => {
      if (!cancelled && result.summary) {
        setDetailSummary(result.summary);
      }
    }).catch(() => {
      // keep existing summary fallback
    });

    return () => {
      cancelled = true;
    };
  }, [card.summary, card.title, card.url]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-24 pb-6 bg-slate-100/72 backdrop-blur-md animate-in fade-in overflow-y-auto"
      style={{ backdropFilter: 'blur(14px) brightness(1.16)' }}
    >
      <div className="bg-white rounded-[28px] shadow-[0_28px_80px_rgba(15,23,42,0.22),0_12px_28px_rgba(15,23,42,0.12)] w-full max-w-3xl max-h-[calc(100vh-120px)] overflow-hidden animate-in zoom-in-95 duration-200 border border-white/80">
        <div className="relative h-52 bg-gray-200">
          <img
            src={detailImage}
            alt={card.title}
            className="w-full h-full object-cover"
            referrerPolicy="no-referrer"
            onError={() => {
              if (detailImage !== fallbackImage) {
                setDetailImage(fallbackImage);
              }
            }}
          />
          <button 
            onClick={onClose}
            className="absolute top-4 right-4 w-8 h-8 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center backdrop-blur-md transition-colors"
          >
            <X size={18} />
          </button>
          <div className={`absolute top-4 left-4 text-white text-sm px-3 py-1 rounded-full font-medium shadow-sm ${card.sentiment === 'negative' ? 'bg-red-500' : card.sentiment === 'positive' ? 'bg-green-500' : 'bg-yellow-500'}`}>
            {sentimentLabelMap[card.sentiment]}面舆情
          </div>
        </div>
        <div className="max-h-[calc(100vh-328px)] overflow-y-auto scrollbar-hide">
          <div className="p-7">
            <h2 className="text-[30px] font-bold text-gray-900 leading-tight">{card.title}</h2>
            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-gray-500 pb-6 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-gray-300 overflow-hidden">
                  <img src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${card.author}`} alt="avatar" />
                </div>
                <span className="font-medium text-gray-700">{card.author}</span>
              </div>
              {formattedPublishedAt ? <span>更新于 {formattedPublishedAt}</span> : null}
            </div>

            <div className="mt-6 rounded-2xl border border-slate-100 bg-slate-50/80 p-5">
              <div className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase mb-3">热点摘要</div>
              <p className="text-base leading-8 text-gray-700">{detailSummary}</p>
            </div>

            <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-3">
              {card.sourceLabel ? (
                <div className="text-sm text-blue-700 bg-blue-50 border border-blue-100 rounded-2xl px-4 py-3">
                  {card.sourceLabel}
                </div>
              ) : null}
              {card.sentimentLabel ? (
                <div className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-2xl px-4 py-3">
                  {card.sentimentLabel}
                </div>
              ) : null}
              {card.sentimentSourceLabel ? (
                <div className="text-sm text-purple-700 bg-purple-50 border border-purple-100 rounded-2xl px-4 py-3">
                  {card.sentimentSourceLabel}
                </div>
              ) : null}
              {card.url ? (
                <a
                  href={card.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-2xl px-4 py-3 hover:bg-emerald-100 transition-colors"
                >
                  查看原始链接
                </a>
              ) : null}
            </div>

            <div className="mt-5 p-5 bg-blue-50 rounded-2xl border border-blue-100 text-blue-900">
              <div className="text-base font-semibold mb-2">分析提示</div>
              <p className="text-sm leading-8">{recommendationHint}</p>
            </div>

            <div className="mt-8 flex items-center justify-end gap-3">
              <button
                className="px-5 py-2.5 text-gray-600 hover:text-gray-800 bg-gray-100 hover:bg-gray-200 rounded-xl font-medium transition-colors"
                onClick={onClose}
              >
                关闭
              </button>
              <button
                className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-medium transition-colors flex items-center gap-2 shadow-sm"
                onClick={() => onDeepAnalyze(card)}
              >
                <Activity size={16} />
                {isAuthenticated ? '深度分析' : '登录后深度分析'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const AuthAction = ({
  currentUser,
  authLoading,
  onGoLogin,
  onLogout,
}: {
  currentUser: AuthUser | null;
  authLoading: boolean;
  onGoLogin: () => void;
  onLogout: () => void;
}) => {
  if (authLoading) {
    return (
      <div className="flex items-center gap-2 px-5 py-2 bg-white text-gray-500 rounded-full shadow-sm border border-gray-100 text-sm font-medium">
        <Loader2 size={16} className="animate-spin" />
        加载中
      </div>
    );
  }

  if (!currentUser) {
    return (
      <button onClick={onGoLogin} className="flex items-center gap-2 px-5 py-2 bg-white text-blue-600 rounded-full shadow-sm border border-blue-100 hover:shadow-md hover:bg-blue-50 transition-all text-sm font-medium">
        <User size={16} />
        登录
      </button>
    );
  }

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-white rounded-full shadow-sm border border-gray-100">
      <div className="w-8 h-8 rounded-full overflow-hidden bg-blue-100 flex items-center justify-center">
        {currentUser.avatar ? (
          <img src={currentUser.avatar} alt={currentUser.name} className="w-full h-full object-cover" />
        ) : (
          <User size={16} className="text-blue-600" />
        )}
      </div>
      <span className="text-sm font-medium text-gray-700 max-w-28 truncate">{currentUser.name}</span>
      <button onClick={onLogout} className="text-sm text-blue-600 hover:text-blue-700 font-medium">
        退出登录
      </button>
    </div>
  );
};

const HomeView = ({ 
  onSearch, 
  onNewChat,
  activeModel,
  setActiveModel,
  onRefreshRecommendations,
  isHomeLoading,
  onGoLogin,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  onSelectHistory,
  activeHistory,
  sessions,
  recommendationCards,
  homeLoadError,
  suggestedPrompts,
  currentUser,
  authLoading,
  onLogout,
  onRenameSession,
  onDeleteSession,
}: any) => {
  const [input, setInput] = useState('');
  const [toast, setToast] = useState('');
  const [showMoreCards, setShowMoreCards] = useState(false);
  const [selectedCard, setSelectedCard] = useState<AIRecommendationCard | null>(null);

  const handleModelSwitch = (model: string) => {
    setActiveModel(model);
    setToast(`已切换至 ${model} 模型`);
    setTimeout(() => setToast(''), 3000);
  };

  const displayCards = showMoreCards ? recommendationCards : recommendationCards.slice(0, 4);
  const handleDeepAnalyze = (card: AIRecommendationCard) => {
    setSelectedCard(null);
    if (!currentUser) {
      setToast('登录后可基于当前热点发起深度分析');
      setTimeout(() => setToast(''), 3000);
      onGoLogin();
      return;
    }
    onSearch(buildDeepAnalysisPrompt(card), buildRecommendationContext(card));
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden text-gray-800 relative pt-14">
      <BackgroundEffects />
      <Sidebar onHome={() => {}} onNewChat={onNewChat} isCollapsed={isSidebarCollapsed} setIsCollapsed={setIsSidebarCollapsed} showHomeButton={false} onSelectHistory={onSelectHistory} activeHistory={null} sessions={sessions} onRenameSession={onRenameSession} onDeleteSession={onDeleteSession} />


      <div
        className={`flex-1 flex flex-col items-center px-4 relative overflow-y-auto scrollbar-hide ${
          showMoreCards ? 'justify-start pt-24 pb-20' : 'justify-center py-20'
        }`}
      >
        {/* Login Button */}
      <div className="absolute top-6 right-6 z-10">
        <AuthAction currentUser={currentUser} authLoading={authLoading} onGoLogin={onGoLogin} onLogout={onLogout} />
      </div>

      {/* Toast Notification */}
      {toast && (
        <div className="absolute top-10 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full border border-blue-200 bg-white px-6 py-2.5 text-sm text-gray-800 shadow-[0_10px_30px_rgba(59,130,246,0.12)] animate-in fade-in slide-in-from-top-4">
          <CheckCircle2 size={16} className="text-blue-500" />
          {toast}
        </div>
      )}

      <h1 className="text-4xl font-bold tracking-wider mb-12 text-gray-800 relative z-10">
        <span className="text-blue-600">万象智体</span> 你的多模态ai舆情分析助手
      </h1>
      <div className="w-full max-w-4xl relative z-10">
        <div className="flex gap-2 mb-2">
          <button 
            onClick={() => handleModelSwitch('万象智体')}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${activeModel === '万象智体' ? 'bg-blue-100 text-blue-600' : 'text-gray-500 hover:bg-gray-200'}`}
          >
            万象智体
          </button>
          <button 
            onClick={() => handleModelSwitch('DeepSeek (R1)')}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${activeModel === 'DeepSeek (R1)' ? 'bg-blue-100 text-blue-600' : 'text-gray-500 hover:bg-gray-200'}`}
          >
            DeepSeek (R1)
          </button>
        </div>
        <div className="relative rounded-2xl p-[1px] bg-gray-200 focus-within:bg-gradient-to-r focus-within:from-blue-400 focus-within:to-indigo-500 transition-all duration-300 shadow-sm focus-within:shadow-md">
          <div className="bg-white rounded-[15px] p-2 flex items-center w-full h-full">
            <input
              type="text"
              placeholder={`发消息给 ${activeModel}...`}
              className="flex-1 outline-none px-4 py-2 text-gray-700 bg-transparent"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && onSearch(input)}
            />
            <button 
              onClick={() => onSearch(input)} 
              className={`p-2 rounded-xl transition-colors ${input.trim() ? 'bg-blue-500 text-white hover:bg-blue-600' : 'bg-gray-100 text-gray-400'}`}
              disabled={!input.trim()}
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>
      
      <div className="w-full max-w-5xl mt-12 bg-white/60 backdrop-blur-md rounded-3xl p-6 border border-white/50 shadow-sm relative z-10">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center text-blue-600 font-medium">
            <div className="w-6 h-6 bg-blue-100 rounded-md flex items-center justify-center mr-2">
              <Bot size={16} />
            </div>
            关于您的舆情推荐
          </div>
          <div className="flex items-center gap-3">
            <button
              className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-sm text-blue-600 transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void onRefreshRecommendations({ refreshToken: String(Date.now()) })}
              disabled={isHomeLoading}
            >
              {isHomeLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              刷新推荐
            </button>
            <button 
              className="text-blue-500 text-sm hover:underline flex items-center"
              onClick={() => setShowMoreCards(!showMoreCards)}
            >
              {showMoreCards ? '收起推荐' : '更多 AI 推荐'} <ChevronRight size={14} className={`transition-transform ${showMoreCards ? 'rotate-90' : ''}`} />
            </button>
          </div>
        </div>
        <div className={showMoreCards ? "grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 overflow-y-auto max-h-[460px] pb-4 pr-2 scrollbar-hide" : "grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 pb-4"}>
          {isHomeLoading && displayCards.length === 0 ? (
            <div className="w-full rounded-2xl border border-dashed border-blue-100 bg-white/70 px-6 py-10 text-center text-sm text-gray-500">
              <Loader2 size={18} className="mx-auto mb-3 animate-spin text-blue-500" />
              正在刷新舆情推荐...
            </div>
          ) : displayCards.length > 0 ? displayCards.map(card => (
            <RecommendationCard
              key={card.id}
              image={card.image}
              sentiment={card.sentiment}
              title={card.title}
              author={card.author}
              sourceLabel={card.sourceLabel}
              sentimentLabel={card.sentimentLabel}
              sentimentSourceLabel={card.sentimentSourceLabel}
              onClick={() => setSelectedCard(card)}
              className="w-full"
            />
          )) : (
            <div className="w-full rounded-2xl border border-dashed border-gray-200 bg-white/70 px-6 py-10 text-center text-sm text-gray-500">
              <div>{homeLoadError || '暂无可展示的推荐内容'}</div>
              <button
                className="mt-4 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-sm text-blue-600 transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void onRefreshRecommendations({ refreshToken: String(Date.now()) })}
                disabled={isHomeLoading}
              >
                {isHomeLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                重新加载
              </button>
            </div>
          )}
        </div>
      </div>

      {selectedCard && (
        <CardDetailModal
          card={selectedCard}
          onClose={() => setSelectedCard(null)}
          onDeepAnalyze={handleDeepAnalyze}
          isAuthenticated={Boolean(currentUser)}
        />
      )}
      </div>
    </div>
  );
};

const formatKnowledgeFileSize = (size: number) => {
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${size} B`;
};

const resolveKnowledgeBaseLabel = (value: string, knowledgeBases: KnowledgeBase[]) => {
  if (!value) {
    return '不绑定知识库，仅用实时检索/普通对话';
  }
  if (value === ALL_KNOWLEDGE_BASE_OPTION_VALUE) {
    return '全部知识库';
  }
  return knowledgeBases.find((base) => base.id === value)?.name || '当前知识库';
};

const KnowledgeBaseSelector = ({
  value,
  onChange,
  knowledgeBases,
  className = '',
}: {
  value: string;
  onChange: (value: string) => void;
  knowledgeBases: KnowledgeBase[];
  className?: string;
}) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const options = [
    { value: '', label: '不绑定知识库，仅用实时检索/普通对话', description: '不检索私有知识库' },
    { value: ALL_KNOWLEDGE_BASE_OPTION_VALUE, label: '全部知识库', description: '显式检索你全部已接入知识库' },
    ...knowledgeBases.map((base) => ({
      value: base.id,
      label: base.name,
      description: base.description || '当前知识库',
    })),
  ];

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!(containerRef.current instanceof HTMLElement)) {
        return;
      }
      if (!containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-3 rounded-[22px] border border-white/80 bg-white/92 px-5 py-3 text-left text-sm text-slate-700 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-sm transition-colors hover:border-blue-200"
      >
        <span className="truncate">{resolveKnowledgeBaseLabel(value, knowledgeBases)}</span>
        <ChevronDown size={18} className={`shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open ? (
        <div className="absolute bottom-[calc(100%+10px)] left-0 right-0 z-50 overflow-hidden rounded-[22px] border border-white/80 bg-white/95 p-2 shadow-[0_4px_6px_-4px_rgba(15,23,42,0.56)] backdrop-blur-xl">
          <div className="space-y-1">
            {options.map((option) => {
              const isActive = option.value === value;
              return (
                <button
                  key={option.value || 'none'}
                  type="button"
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center justify-between gap-3 rounded-[18px] px-4 py-3 text-left transition-colors ${
                    isActive ? 'bg-slate-100 text-slate-900' : 'text-slate-600 hover:bg-slate-50/90'
                  }`}
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{option.label}</div>
                    <div className="mt-0.5 truncate text-xs text-slate-400">{option.description}</div>
                  </div>
                  {isActive ? <CheckCircle2 size={16} className="shrink-0 text-blue-600" /> : null}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
};

const formatRetrievalScore = (value?: number) => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '-';
  }
  return value.toFixed(4);
};

const downloadTextFile = (filename: string, content: string, mimeType = 'text/plain;charset=utf-8') => {
  const blob = new Blob([content], { type: mimeType });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(href);
};

const toCsvCell = (value: unknown) => {
  const normalized = String(value ?? '');
  return `"${normalized.replace(/"/g, '""')}"`;
};

type ToolMenuItem = {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  disabled?: boolean;
  active?: boolean;
  onClick?: () => void;
};

const exportStructuredRecordsToCsv = (
  records: Array<{
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
  }>,
  filename: string,
) => {
  const rows = records
    .map((item) => item.record)
    .filter((record): record is NonNullable<typeof records[number]['record']> => Boolean(record));

  if (!rows.length) {
    return false;
  }

  const header = ['省份', '准考证号', '学校', '姓名', '科目', '组别', '奖项', '是否晋级'];
  const lines = [
    header.map(toCsvCell).join(','),
    ...rows.map((record) => [
      toCsvCell(record.province),
      toCsvCell(record.ticketNo),
      toCsvCell(record.schoolName),
      toCsvCell(record.studentName),
      toCsvCell(record.subjectName),
      toCsvCell(record.groupName),
      toCsvCell(record.award),
      toCsvCell(record.qualifiedForFinalLabel || (record.qualifiedForFinal ? '是' : record.qualifiedForFinal === false ? '否' : '')),
    ].join(',')),
  ];

  downloadTextFile(filename, `\ufeff${lines.join('\n')}`, 'text/csv;charset=utf-8');
  return true;
};

const ChatToolMenu = ({
  open,
  title = '工具箱',
  items,
  onClose,
}: {
  open: boolean;
  title?: string;
  items: ToolMenuItem[];
  onClose: () => void;
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [menuDirection, setMenuDirection] = useState<'up' | 'down'>('up');

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    // Find the button element (sibling of the menu container)
    const menuContainer = containerRef.current;
    const button = menuContainer?.parentElement?.querySelector('button[type="button"]') as HTMLButtonElement | null;
    if (button) {
      const buttonRect = button.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const spaceAbove = buttonRect.top;
      const spaceBelow = viewportHeight - buttonRect.bottom;
      // If button is in top 30% of viewport OR more space below than above, open downward
      const inTopZone = spaceAbove < viewportHeight * 0.3;
      if (inTopZone || spaceBelow > spaceAbove) {
        setMenuDirection('down');
      } else {
        setMenuDirection('up');
      }
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!(containerRef.current instanceof HTMLElement)) {
        return;
      }
      if (!containerRef.current.contains(event.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div
        ref={containerRef}
        className={`absolute ${
          menuDirection === 'up' ? 'bottom-[calc(100%+10px)]' : 'top-[calc(100%+10px)]'
        } left-0 z-[70] w-[288px] overflow-hidden rounded-[22px] border border-white/80 bg-white/95 p-2 shadow-[0_4px_6px_-4px_rgba(15,23,42,0.56)] backdrop-blur-xl`}
      >
        <div className="px-3 pb-2 pt-1 text-[11px] font-medium tracking-[0.08em] text-slate-400">{title}</div>
        <div className="space-y-1">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={item.disabled ? undefined : item.onClick}
              disabled={item.disabled}
              className={`flex w-full items-center gap-3 rounded-[18px] px-3.5 py-3 text-left transition-colors ${
                item.disabled
                  ? 'cursor-not-allowed bg-slate-50/80 text-slate-300'
                  : item.active
                    ? 'bg-blue-50/90 text-blue-700'
                    : 'text-slate-700 hover:bg-slate-50/90'
              }`}
            >
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                item.disabled
                  ? 'bg-slate-100 text-slate-300'
                  : item.active
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-slate-100 text-slate-700'
              }`}>
                {item.icon}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span>{item.label}</span>
                  {item.active ? <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">当前</span> : null}
                </div>
                <div className="mt-0.5 text-[12px] text-slate-400">{item.description}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </>
  );
};

const StructuredRecordsToolPanel = ({
  title,
  records,
  aggregations,
  onClose,
  onExport,
}: {
  title?: string;
  records: Array<{
    sourceId?: string;
    score?: number;
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
  aggregations?: {
    totalMatchedCount?: number;
    finalistCount?: number;
    uniqueSchoolCount?: number;
  } | null;
  onClose: () => void;
  onExport?: () => void;
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const previewRecords = records.slice(0, 20);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!(containerRef.current instanceof HTMLElement)) {
        return;
      }
      if (!containerRef.current.contains(event.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [onClose]);

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div ref={containerRef} className="absolute bottom-[calc(100%+16px)] left-0 z-50 w-[min(920px,calc(100vw-2rem))] overflow-hidden rounded-[28px] border border-white/80 bg-white/96 shadow-[0_6px_8px_-5px_rgba(15,23,42,0.56)] backdrop-blur-xl">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            <div className="text-sm font-semibold text-slate-900">{title || '结构化结果工具'}</div>
            <div className="mt-1 text-xs text-slate-400">查看当前命中的结构化记录，并直接导出 CSV。</div>
          </div>
          <div className="flex items-center gap-2">
            {onExport ? (
              <button
                type="button"
                onClick={onExport}
                className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-100"
              >
                <FileText size={14} />
                导出 CSV
              </button>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="grid gap-4 px-5 py-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <div className="rounded-xl bg-fuchsia-50 px-3 py-3 text-sm text-fuchsia-700">总命中：{aggregations?.totalMatchedCount ?? records.length}</div>
              <div className="rounded-xl bg-blue-50 px-3 py-3 text-sm text-blue-700">晋级数：{aggregations?.finalistCount ?? records.filter((item) => item.record?.qualifiedForFinal).length}</div>
              <div className="rounded-xl bg-emerald-50 px-3 py-3 text-sm text-emerald-700">院校数：{aggregations?.uniqueSchoolCount ?? new Set(records.map((item) => item.record?.schoolName).filter(Boolean)).size}</div>
            </div>
            <div className="rounded-2xl border border-slate-100 bg-slate-50/80 px-4 py-4 text-xs leading-6 text-slate-500">
              这个工具可视化展示当前聊天命中的结构化记录。
              适合做名单核对、院校统计、奖项筛选和导出复核。
            </div>
          </div>

          {records.length ? (
            <div className="overflow-x-auto rounded-2xl border border-slate-100 bg-white">
              <table className="min-w-full divide-y divide-slate-100 text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-[0.12em] text-slate-400">
                  <tr>
                    <th className="px-3 py-3 font-medium">学校</th>
                    <th className="px-3 py-3 font-medium">姓名</th>
                    <th className="px-3 py-3 font-medium">科目</th>
                    <th className="px-3 py-3 font-medium">组别</th>
                    <th className="px-3 py-3 font-medium">奖项</th>
                    <th className="px-3 py-3 font-medium">晋级</th>
                    <th className="px-3 py-3 font-medium">综合分</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-600">
                  {previewRecords.map((item, index) => (
                    <tr key={`${item.sourceId || 'structured'}-${index}`} className="align-top">
                      <td className="px-3 py-3">{item.record?.schoolName || '-'}</td>
                      <td className="px-3 py-3">{item.record?.studentName || '-'}</td>
                      <td className="px-3 py-3">{item.record?.subjectName || '-'}</td>
                      <td className="px-3 py-3">{item.record?.groupName || '-'}</td>
                      <td className="px-3 py-3">{item.record?.award || '-'}</td>
                      <td className="px-3 py-3">{item.record?.qualifiedForFinalLabel || (item.record?.qualifiedForFinal ? '是' : item.record?.qualifiedForFinal === false ? '否' : '-')}</td>
                      <td className="px-3 py-3">{formatRetrievalScore(item.score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {records.length > 20 ? (
                <div className="border-t border-slate-100 px-4 py-3 text-xs text-slate-400">
                  当前仅展示前 20 条记录，导出 CSV 可获取当前命中的全部结构化记录。
                </div>
              ) : null}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white/80 px-6 py-12 text-center text-sm text-slate-400">
              当前会话还没有可展示的结构化结果。你可以先发起名单/表格类问题，再回到这里查看。
            </div>
          )}
        </div>
      </div>
    </>
  );
};

const isPlainObject = (value: unknown): value is Record<string, any> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const HOME_TAB_ROUTE_MAP: Record<string, string> = {
  'AI 舆情助手': '/',
  '智慧中枢': '/command-center',
  '私有知识库': '/knowledge-base',
  '可视化大屏': '/big-screen',
};

const APP_STATE_ROUTE_MAP: Record<string, string> = {
  login: '/login',
  register: '/register',
  new_chat: '/new-chat',
  chat: '/chat',
};

const CHAT_ROUTE_PREFIX = '/chat';

const buildAppPath = ({
  appState,
  activeTab,
  activeHistory,
}: {
  appState: 'home' | 'chat' | 'login' | 'register' | 'new_chat';
  activeTab: string;
  activeHistory?: string | null;
}) => {
  if (appState === 'chat') {
    const normalizedSessionId = String(activeHistory || '').trim();
    return normalizedSessionId
      ? `${CHAT_ROUTE_PREFIX}/${encodeURIComponent(normalizedSessionId)}`
      : CHAT_ROUTE_PREFIX;
  }

  if (appState === 'home') {
    return HOME_TAB_ROUTE_MAP[activeTab] ?? '/';
  }

  return APP_STATE_ROUTE_MAP[appState] ?? '/';
};

const resolveRouteState = (pathname: string) => {
  const normalizedPath = pathname === '/' ? '/' : pathname.replace(/\/+$/, '');
  if (normalizedPath === CHAT_ROUTE_PREFIX || normalizedPath.startsWith(`${CHAT_ROUTE_PREFIX}/`)) {
    const rawSessionId = normalizedPath.slice(CHAT_ROUTE_PREFIX.length + 1);
    let sessionId: string | null = null;
    if (rawSessionId) {
      try {
        sessionId = decodeURIComponent(rawSessionId);
      } catch {
        sessionId = rawSessionId;
      }
    }
    return { appState: 'chat' as const, activeTab: 'AI 舆情助手', sessionId };
  }
  if (normalizedPath === '/login') {
    return { appState: 'login' as const, activeTab: 'AI 舆情助手', sessionId: null };
  }
  if (normalizedPath === '/register') {
    return { appState: 'register' as const, activeTab: 'AI 舆情助手', sessionId: null };
  }
  if (normalizedPath === '/new-chat') {
    return { appState: 'new_chat' as const, activeTab: 'AI 舆情助手', sessionId: null };
  }
  if (normalizedPath === '/command-center') {
    return { appState: 'home' as const, activeTab: '智慧中枢', sessionId: null };
  }
  if (normalizedPath === '/knowledge-base') {
    return { appState: 'home' as const, activeTab: '私有知识库', sessionId: null };
  }
  if (normalizedPath === '/big-screen') {
    return { appState: 'home' as const, activeTab: '可视化大屏', sessionId: null };
  }
  return { appState: 'home' as const, activeTab: 'AI 舆情助手', sessionId: null };
};

const resolveModuleTitle = ({
  appState,
  activeTab,
  activeSessionTitle,
}: {
  appState: 'home' | 'chat' | 'login' | 'register' | 'new_chat';
  activeTab: string;
  activeSessionTitle?: string | null;
}) => {
  if (appState === 'login') {
    return '登录';
  }
  if (appState === 'register') {
    return '注册';
  }
  if (appState === 'new_chat') {
    return '新建分析';
  }
  if (appState === 'chat') {
    return String(activeSessionTitle || 'AI 舆情助手');
  }

  if (activeTab === '万象智体') {
    return '首页';
  }

  return String(activeTab || '首页');
};

const commandCenterSentimentColors = ['#22c55e', '#f59e0b', '#ef4444'];

const formatRatioPercent = (value?: number) => `${Math.round((Number(value || 0) || 0) * 100)}%`;

const normalizeSchemaForChart = (
  schema?: Record<string, number>,
  options?: { limit?: number; minimum?: number },
) =>
  Object.entries(schema || {})
    .map(([name, value]) => ({
      name,
      value: Math.round((Number(value || 0) || 0) * 1000) / 10,
    }))
    .sort((a, b) => b.value - a.value)
    .filter((item) => item.value > Number(options?.minimum ?? 0))
    .slice(0, options?.limit ?? 8);

const buildWordCloudLayout = (items: Array<{ word: string; weight?: number }>) => {
  const filtered = items
    .filter((item) => String(item.word || '').trim())
    .map((item) => ({
      word: String(item.word).trim(),
      weight: Math.max(Number(item.weight || 0) || 0, 0.2),
    }))
    .slice(0, 18);

  if (filtered.length === 0) {
    return [];
  }

  const maxWeight = Math.max(...filtered.map((item) => item.weight));
  const minWeight = Math.min(...filtered.map((item) => item.weight));
  const palette = ['#2563eb', '#0891b2', '#7c3aed', '#ea580c', '#0f766e', '#db2777'];

  return filtered.map((item, index) => {
    const normalizedWeight = maxWeight === minWeight
      ? 0.7
      : (item.weight - minWeight) / (maxWeight - minWeight);
    const fontSize = Math.round(16 + normalizedWeight * 18);
    const rotate = index % 5 === 0 ? -18 : index % 4 === 0 ? 16 : 0;
    const column = index % 3;
    const row = Math.floor(index / 3);
    const xBase = [18, 50, 80][column];
    const xJitter = ((index * 7) % 9) - 4;
    const yBase = 16 + row * 16;
    const yJitter = (index % 2 === 0 ? -2 : 3);

    return {
      ...item,
      fontSize,
      rotate,
      fill: palette[index % palette.length],
      x: Math.max(10, Math.min(90, xBase + xJitter)),
      y: Math.max(12, Math.min(92, yBase + yJitter)),
      opacity: 0.72 + normalizedWeight * 0.28,
    };
  });
};

const clampPercent = (value: number, min = 0, max = 100) => Math.max(min, Math.min(max, value));

const projectEventToMap = (event: Pick<CommandCenterEvent, 'x' | 'y' | 'spreadRange' | 'participants' | 'id' | 'title' | 'platform'>) => {
  const spread = clampPercent((Number(event.spreadRange || 0) || 0) * 100, 8, 100);
  const heat = clampPercent(Math.round(Number(event.participants || 0) || 0), 12, 100);
  return {
    ...event,
    radius: 10 + spread * 0.18,
    pulse: 18 + heat * 0.16,
  };
};

const getImpactScore = (event?: CommandCenterEvent | null) => {
  if (!event) {
    return 0;
  }
  const spreadScore = clampPercent((Number(event.spreadRange || 0) || 0) * 100);
  const speedScore = clampPercent((Number(event.spreadSpeed || 0) || 0) * 100);
  const participantScore = clampPercent(Math.round(Number(event.participants || 0) || 0));
  return Math.round(spreadScore * 0.4 + speedScore * 0.25 + participantScore * 0.35);
};

const getImpactTag = (score: number) => {
  if (score >= 75) {
    return '特大';
  }
  if (score >= 50) {
    return '重大';
  }
  if (score >= 25) {
    return '较大';
  }
  return '一般';
};

const buildBigScreenTrendModuleData = (
  events: CommandCenterEvent[],
  options?: { timeRange?: '12h' | '7d'; searchText?: string; limit?: number },
) => {
  const timeRange = options?.timeRange ?? '7d';
  const normalizedSearch = String(options?.searchText || '').trim().toLowerCase();
  const filteredEvents = events
    .filter((event) => Array.isArray(event.heatTrend) && event.heatTrend.length > 0)
    .filter((event) => !normalizedSearch || String(event.title || '').toLowerCase().includes(normalizedSearch))
    .slice(0, options?.limit ?? 6);

  const selectedTrendEvents = filteredEvents.map((event) => {
    const points = (event.heatTrend || [])
      .filter((item) => isPlainObject(item))
      .map((item, index) => ({
        time: String(item.date || `T-${index + 1}`),
        value: Math.round((Number(item.value || 0) || 0) * 10000),
      }));
    return {
      id: event.id,
      name: event.title,
      points: timeRange === '12h' ? points.slice(-12) : points.slice(-7),
    };
  }).filter((event) => event.points.length > 0);

  const timeline = Array.from(new Set(
    selectedTrendEvents.flatMap((event) => event.points.map((point) => point.time)),
  )).sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

  const chartData = timeline.map((time) => {
    const row: Record<string, any> = { time };
    selectedTrendEvents.forEach((event) => {
      const matched = event.points.find((point) => point.time === time);
      row[event.name] = matched?.value ?? 0;
    });
    return row;
  });

  const flattenedValues = selectedTrendEvents.flatMap((event) => event.points.map((point) => point.value)).filter((value) => value > 0);
  const averageValue = flattenedValues.length
    ? Math.round(flattenedValues.reduce((sum, value) => sum + value, 0) / flattenedValues.length)
    : 0;

  const legendItems = selectedTrendEvents.map((event, index) => ({
    id: event.id,
    name: event.name,
    latestValue: event.points[event.points.length - 1]?.value ?? 0,
    color: ['#2084f3', '#2894ea', '#31a5e2', '#34b3cb', '#4bc8c3', '#68d391'][index % 6],
  }));

  return {
    chartData,
    averageValue,
    legendItems,
  };
};

const preferredBigScreenPlatforms = ['微信', '微博', '人民网', '贴吧', '百度'];

const buildBigScreenPlatformStats = (
  platformDistribution: Array<{ name: string; value: number }>,
  events: CommandCenterEvent[],
) => {
  const sourceMap = new Map<string, number>();

  platformDistribution.forEach((item) => {
    const name = String(item.name || '').trim();
    if (!name) {
      return;
    }
    sourceMap.set(name, Number(item.value || 0) || 0);
  });

  events.forEach((event) => {
    const name = String(event.platform || '').trim();
    if (!name) {
      return;
    }
    if (!sourceMap.has(name)) {
      sourceMap.set(name, 0);
    }
    sourceMap.set(name, (sourceMap.get(name) || 0) + 1);
  });

  const ranked = Array.from(sourceMap.entries())
    .map(([name, value]) => ({ name, value: Math.round(value) }))
    .sort((a, b) => b.value - a.value);

  const usedNames = new Set<string>();
  const preferred = preferredBigScreenPlatforms.map((name) => {
    const matched = ranked.find((item) => item.name === name);
    if (matched) {
      usedNames.add(matched.name);
      return matched;
    }
    return { name, value: 0 };
  });

  ranked.forEach((item) => {
    if (usedNames.size >= 4 || usedNames.has(item.name)) {
      return;
    }
    const replacementIndex = preferred.findIndex((entry) => entry.value === 0 && !usedNames.has(entry.name));
    if (replacementIndex >= 0) {
      preferred[replacementIndex] = item;
      usedNames.add(item.name);
    }
  });

  return preferred.slice(0, 4);
};

const buildBigScreenOverviewTrend = (events: CommandCenterEvent[], range: '7d' | '30d' = '7d') => {
  const aggregate = new Map<string, number>();

  events.forEach((event) => {
    (event.heatTrend || []).forEach((point, index) => {
      const key = String(point?.date || `T-${index + 1}`);
      const value = Math.round((Number(point?.value || 0) || 0) * 1000);
      aggregate.set(key, (aggregate.get(key) || 0) + value);
    });
  });

  const items = Array.from(aggregate.entries())
    .map(([date, value]) => ({ date, value }))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  const limit = range === '30d' ? 30 : 7;
  const baseItems = items.slice(-Math.max(items.length, Math.min(limit, 7)));

  if (range === '7d') {
    return baseItems.slice(-7);
  }

  if (baseItems.length === 0) {
    return [];
  }

  const referenceDate = new Date(baseItems[baseItems.length - 1]?.date || Date.now());
  if (Number.isNaN(referenceDate.getTime())) {
    return baseItems;
  }

  const normalizedSource = baseItems.map((item, index) => ({
    value: item.value,
    index,
  }));

  if (normalizedSource.length === 1) {
    return Array.from({ length: 30 }, (_, dayIndex) => {
      const date = new Date(referenceDate);
      date.setDate(referenceDate.getDate() - (29 - dayIndex));
      return {
        date: date.toISOString().slice(0, 10),
        value: normalizedSource[0].value,
      };
    });
  }

  return Array.from({ length: 30 }, (_, dayIndex) => {
    const date = new Date(referenceDate);
    date.setDate(referenceDate.getDate() - (29 - dayIndex));

    const position = (dayIndex / 29) * (normalizedSource.length - 1);
    const leftIndex = Math.floor(position);
    const rightIndex = Math.min(Math.ceil(position), normalizedSource.length - 1);
    const progress = position - leftIndex;
    const leftValue = normalizedSource[leftIndex]?.value ?? 0;
    const rightValue = normalizedSource[rightIndex]?.value ?? leftValue;
    const value = Math.round(leftValue + (rightValue - leftValue) * progress);

    return {
      date: date.toISOString().slice(0, 10),
      value,
    };
  });
};

const buildBigScreenTextCategoryData = (events: CommandCenterEvent[]) => {
  const groups = new Map<string, number>();
  events.forEach((event) => {
    const name = String(event.type || '未分类').trim() || '未分类';
    groups.set(name, (groups.get(name) || 0) + 1);
  });

  const total = Array.from(groups.values()).reduce((sum, value) => sum + value, 0) || 1;
  return Array.from(groups.entries())
    .map(([name, count]) => ({
      name,
      value: Number(((count / total) * 100).toFixed(2)),
      count,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
};

const positiveWordHints = ['支持', '成功', '正向', '点赞', '认可', '利好', '增长', '稳定', '高效', '暖心', '助力'];
const negativeWordHints = ['问题', '争议', '负面', '危机', '风险', '处罚', '波动', '冲突', '投诉', '质疑', '事故'];

const buildBigScreenSentimentKeywords = (items: Array<{ word: string; weight?: number }>) => {
  const words = items
    .filter((item) => String(item.word || '').trim())
    .map((item) => ({ word: String(item.word).trim(), weight: Number(item.weight || 0) || 0 }))
    .sort((a, b) => b.weight - a.weight);

  const positives = words.filter((item) => positiveWordHints.some((hint) => item.word.includes(hint)));
  const negatives = words.filter((item) => negativeWordHints.some((hint) => item.word.includes(hint)));
  const neutralPool = words.filter((item) => !positives.includes(item) && !negatives.includes(item));

  while (positives.length < 5 && neutralPool.length > 0) {
    positives.push(neutralPool.shift()!);
  }
  while (negatives.length < 5 && neutralPool.length > 0) {
    negatives.push(neutralPool.shift()!);
  }

  return {
    positive: positives.slice(0, 5),
    negative: negatives.slice(0, 5),
  };
};

const BigScreenRingGauge = ({
  label,
  value,
  maxValue,
}: {
  label: string;
  value: number;
  maxValue: number;
}) => {
  const safeMax = Math.max(maxValue, 1);
  const ratio = Math.max(0.06, Math.min(value / safeMax, 1));
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - ratio);

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="text-xl font-semibold text-slate-800">{label}</div>
      <div className="relative flex h-[92px] w-[92px] items-center justify-center">
        <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle,rgba(56,189,248,0.2),transparent_68%)] blur-md" />
        <svg viewBox="0 0 96 96" className="relative h-full w-full">
          <circle cx="48" cy="48" r={radius} fill="rgba(255,255,255,0.92)" stroke="rgba(56,189,248,0.16)" strokeWidth="8" />
          <circle
            cx="48"
            cy="48"
            r={radius}
            fill="none"
            stroke="rgba(14,165,233,0.92)"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            transform="rotate(-90 48 48)"
          />
          {Array.from({ length: 24 }).map((_, index) => {
            const angle = (index / 24) * Math.PI * 2 - Math.PI / 2;
            const x1 = 48 + Math.cos(angle) * 40;
            const y1 = 48 + Math.sin(angle) * 40;
            const x2 = 48 + Math.cos(angle) * 45;
            const y2 = 48 + Math.sin(angle) * 45;
            return (
              <line
                key={`${label}-${index}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={index / 24 <= ratio ? 'rgba(14,165,233,0.92)' : 'rgba(125,211,252,0.26)'}
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            );
          })}
          <circle cx="48" cy="48" r="26" fill="rgba(248,252,255,0.96)" stroke="rgba(103,232,249,0.3)" strokeWidth="1.5" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center text-[2rem] font-semibold text-slate-900">
          {value}
        </div>
      </div>
    </div>
  );
};

const worldRegionLabels = [
  { name: '北美', coordinates: [-108, 45] as [number, number] },
  { name: '南美', coordinates: [-60, -24] as [number, number] },
  { name: '欧洲', coordinates: [18, 54] as [number, number] },
  { name: '非洲', coordinates: [20, 5] as [number, number] },
  { name: '亚洲', coordinates: [98, 32] as [number, number] },
];

const COMMAND_CENTER_MAP_ATTRIBUTION = '地图数据：Natural Earth（经 world-atlas 提供，countries-110m），渲染：react-simple-maps';

const WorldGeoMap = ({
  tone = 'light',
  points,
  selectedEventId,
  onSelectEvent,
}: {
  tone?: 'light' | 'dark';
  points: Array<Pick<CommandCenterEvent, 'id' | 'title' | 'platform' | 'x' | 'y' | 'spreadRange' | 'participants'>>;
  selectedEventId?: string | null;
  onSelectEvent: (eventId: string) => void;
}) => {
  const isDark = tone === 'dark';

  return (
    <div className={`pointer-events-none absolute inset-0 ${isDark ? 'opacity-[0.98]' : 'opacity-[0.96]'}`}>
      <ComposableMap
        projection="geoEqualEarth"
        projectionConfig={{ scale: 175 }}
        width={1000}
        height={520}
        style={{ width: '100%', height: '100%' }}
      >
        <Sphere
          fill={isDark ? 'rgba(8, 21, 40, 0.04)' : 'rgba(255,255,255,0.06)'}
          stroke={isDark ? 'rgba(34,211,238,0.08)' : 'rgba(147,197,253,0.1)'}
          strokeWidth={0.6}
        />
        <Graticule stroke={isDark ? 'rgba(34,211,238,0.08)' : 'rgba(148,163,184,0.08)'} strokeWidth={0.5} />
        <Geographies geography={worldAtlasUrl}>
          {({ geographies }) =>
            geographies.map((geo) => (
              <Geography
                key={geo.rsmKey}
                geography={geo}
                fill={isDark ? '#17324b' : '#dbeafe'}
                stroke={isDark ? '#29506c' : '#bfdbfe'}
                strokeWidth={0.65}
                style={{
                  default: { outline: 'none' },
                  hover: { outline: 'none' },
                  pressed: { outline: 'none' },
                }}
              />
            ))
          }
        </Geographies>
        {worldRegionLabels.map((label) => (
          <Marker key={label.name} coordinates={label.coordinates}>
            <text
              textAnchor="middle"
              style={{
                fontSize: 18,
                letterSpacing: '0.2em',
                fill: isDark ? 'rgba(148,163,184,0.85)' : 'rgba(100,116,139,0.72)',
                fontWeight: 500,
                pointerEvents: 'none',
              }}
            >
              {label.name}
            </text>
          </Marker>
        ))}
        {points.map((point) => {
          const projected = projectEventToMap(point);
          const isActive = point.id === selectedEventId;
          const outerRadius = Math.max(projected.radius / 2 + 4, 10);
          const pulseRadius = Math.max(projected.pulse / 2 + 6, 16);
          return (
            <Marker key={point.id} coordinates={[Number(point.x || 0), Number(point.y || 0)]}>
              <g
                onClick={() => onSelectEvent(point.id)}
                style={{ cursor: 'pointer', pointerEvents: 'auto' }}
              >
                <circle
                  r={pulseRadius}
                  fill={isDark ? (isActive ? 'rgba(34,211,238,0.18)' : 'rgba(59,130,246,0.14)') : (isActive ? 'rgba(59,130,246,0.18)' : 'rgba(56,189,248,0.14)')}
                />
                <circle
                  r={outerRadius}
                  fill={isDark ? (isActive ? 'rgba(34,211,238,0.26)' : 'rgba(59,130,246,0.2)') : (isActive ? 'rgba(59,130,246,0.26)' : 'rgba(56,189,248,0.22)')}
                />
                <circle
                  r={Math.max(projected.radius / 2, 8)}
                  fill={isDark ? (isActive ? '#22d3ee' : '#0f172a') : '#ffffff'}
                  stroke={isDark ? (isActive ? '#67e8f9' : '#60a5fa') : (isActive ? '#2563eb' : '#38bdf8')}
                  strokeWidth={2.5}
                />
                <circle
                  r={2.7}
                  fill={isDark ? (isActive ? '#082f49' : '#7dd3fc') : (isActive ? '#2563eb' : '#0ea5e9')}
                />
              </g>
            </Marker>
          );
        })}
      </ComposableMap>
    </div>
  );
};

const CommandCenterView = ({
  onGoLogin,
  currentUser,
  authLoading,
  onLogout,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  onNewChat,
  onSelectHistory,
  sessions,
  onRenameSession,
  onDeleteSession,
}: any) => {
  const [data, setData] = useState<CommandCenterData | null>(null);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadCommandCenter = async () => {
    if (!currentUser) {
      setData(null);
      setSelectedEventId('');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const next = await getCommandCenter();
      setData(next);
      setSelectedEventId((previous) => previous || next.events[0]?.id || '');
    } catch (loadError: any) {
      setError(loadError?.message || '获取指挥中枢数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadCommandCenter();
  }, [currentUser]);

  const selectedEvent = useMemo<CommandCenterEvent | null>(() => {
    if (!data?.events?.length) {
      return null;
    }
    return data.events.find((item) => item.id === selectedEventId) || data.events[0] || null;
  }, [data, selectedEventId]);

  const summary = isPlainObject(data?.summary) ? data.summary : {};
  const emotionSchema = isPlainObject(selectedEvent?.emotion) && isPlainObject(selectedEvent?.emotion?.schema)
    ? selectedEvent.emotion.schema
    : {};
  const stanceSchema = isPlainObject(selectedEvent?.stance) && isPlainObject(selectedEvent?.stance?.schema)
    ? selectedEvent.stance.schema
    : {};
  const heatTrendSource = Array.isArray(selectedEvent?.heatTrend)
    ? selectedEvent.heatTrend.filter((item) => isPlainObject(item))
    : [];
  const wordCloudSource = Array.isArray(selectedEvent?.wordCloud)
    ? selectedEvent.wordCloud.filter((item) => isPlainObject(item))
    : [];
  const timelineSource = Array.isArray(selectedEvent?.timeline)
    ? selectedEvent.timeline.filter((item) => isPlainObject(item))
    : [];
  const platformDistribution = Array.isArray(summary?.platformDistribution)
    ? summary.platformDistribution.filter((item) => isPlainObject(item))
    : [];
  const sentimentDistribution = Array.isArray(summary?.sentimentDistribution)
    ? summary.sentimentDistribution.filter((item) => isPlainObject(item))
    : [];
  const emotionChartData = normalizeSchemaForChart(emotionSchema, { limit: 8, minimum: 0.1 });
  const stanceChartData = normalizeSchemaForChart(stanceSchema, { limit: 8, minimum: 0.1 });
  const heatTrendData = heatTrendSource.slice(-7).map((item, index) => ({
    date: String(item.date || `T-${6 - index}`),
    value: Math.round((Number(item.value || 0) || 0) * 100),
  }));
  const keywordCloudLayout = buildWordCloudLayout(wordCloudSource as Array<{ word: string; weight?: number }>);
  const timelineItems = timelineSource.slice(0, 6).map((item) => ({
    date: String(item.date || ''),
    event: String(item.event || item.description || ''),
  }));
  const mapPoints = Array.isArray(data?.events) ? data.events.slice(0, 20) : [];
  const selectedMapPoint = selectedEvent ? projectEventToMap(selectedEvent) : null;
  const impactScore = getImpactScore(selectedEvent);
  const impactTag = getImpactTag(impactScore);
  const topPlatformCount = Number(platformDistribution[0]?.value || 0) || 0;

  const statCards = [
    {
      label: '监测事件',
      value: summary?.totalEvents ?? 0,
      helper: '当前热榜事件总量',
      icon: <Gauge size={18} className="text-blue-500" />,
      tone: 'from-blue-50 to-cyan-50 border-blue-100',
    },
    {
      label: '负向事件',
      value: summary?.negativeEvents ?? 0,
      helper: '需重点关注',
      icon: <Shield size={18} className="text-rose-500" />,
      tone: 'from-rose-50 to-orange-50 border-rose-100',
    },
    {
      label: '平均传播范围',
      value: formatRatioPercent(summary?.avgSpreadRange),
      helper: '按当前事件估算',
      icon: <Share2 size={18} className="text-emerald-500" />,
      tone: 'from-emerald-50 to-lime-50 border-emerald-100',
    },
    {
      label: '平均传播速度',
      value: formatRatioPercent(summary?.avgSpreadSpeed),
      helper: '按当前事件估算',
      icon: <Activity size={18} className="text-violet-500" />,
      tone: 'from-violet-50 to-fuchsia-50 border-violet-100',
    },
  ];

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden text-gray-800 relative pt-14">
      <BackgroundEffects />
      <Sidebar onHome={() => {}} onNewChat={onNewChat} isCollapsed={isSidebarCollapsed} setIsCollapsed={setIsSidebarCollapsed} showHomeButton={false} onSelectHistory={onSelectHistory} activeHistory={null} sessions={sessions} onRenameSession={onRenameSession} onDeleteSession={onDeleteSession} />

      <div className="flex-1 flex flex-col items-center px-4 py-20 relative overflow-y-auto scrollbar-hide">
        <div className="absolute top-6 right-6 z-10">
          <AuthAction currentUser={currentUser} authLoading={authLoading} onGoLogin={onGoLogin} onLogout={onLogout} />
        </div>

        <div className="w-full max-w-6xl rounded-3xl border border-white/60 bg-white/70 p-6 shadow-sm backdrop-blur-md">
          <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">智慧中枢</h1>
              <p className="mt-2 text-sm text-gray-500">聚合当前热点事件，快速查看平台分布、传播态势、情绪立场与关键演化脉络。</p>
            </div>
            <button
              onClick={() => void loadCommandCenter()}
              disabled={loading}
              className="inline-flex items-center gap-2 self-start rounded-xl border border-blue-100 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-600 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              刷新中枢数据
            </button>
          </div>

          {!currentUser ? (
            <div className="rounded-2xl border border-dashed border-gray-200 bg-white/70 px-6 py-12 text-center">
              <p className="text-base font-medium text-gray-700">登录后可查看指挥中枢中的实时事件与传播态势</p>
              <button
                onClick={onGoLogin}
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
              >
                <Lock size={16} />
                前往登录
              </button>
            </div>
          ) : (
            <div className="space-y-6">
              {error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
              ) : null}

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {statCards.map((card) => (
                  <div key={card.label} className={`rounded-2xl border bg-gradient-to-br px-5 py-4 ${card.tone}`}>
                    <div className="mb-3 flex items-center justify-between">
                      <div className="text-sm font-medium text-gray-600">{card.label}</div>
                      {card.icon}
                    </div>
                    <div className="text-3xl font-bold text-gray-900">{card.value}</div>
                    <div className="mt-2 text-xs text-gray-500">{card.helper}</div>
                  </div>
                ))}
              </div>

              {loading && !data ? (
                <div className="rounded-2xl border border-dashed border-gray-200 bg-white/70 px-6 py-10 text-center text-sm text-gray-500">
                  <Loader2 size={18} className="mx-auto mb-3 animate-spin text-blue-500" />
                  正在加载指挥中枢数据...
                </div>
              ) : !data?.events?.length ? (
                <div className="rounded-2xl border border-dashed border-gray-200 bg-white/70 px-6 py-10 text-center text-sm text-gray-500">
                  暂无可展示的事件数据。
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
                  <div className="rounded-2xl border border-gray-100 bg-white px-4 py-4 shadow-sm">
                    <div className="mb-3 flex items-center justify-between">
                      <h2 className="text-base font-semibold text-gray-900">热点事件列表</h2>
                      <span className="text-xs text-gray-400">按热榜顺序</span>
                    </div>
                    <div className="space-y-3">
                      {data.events.slice(0, 10).map((event) => (
                        <button
                          key={event.id}
                          onClick={() => setSelectedEventId(event.id)}
                          className={`w-full rounded-2xl border px-4 py-3 text-left transition-all ${
                            selectedEvent?.id === event.id
                              ? 'border-blue-200 bg-blue-50 shadow-sm'
                              : 'border-gray-100 bg-slate-50 hover:border-gray-200 hover:bg-white'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium text-gray-900">
                                #{event.rank} {event.title}
                              </div>
                              <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                                <span>{event.platform}</span>
                                <span>{event.type}</span>
                              </div>
                            </div>
                            <span
                              className={`inline-flex min-w-[3rem] flex-shrink-0 items-center justify-center whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium leading-none ${
                                event.primarySentiment === 'positive'
                                  ? 'bg-emerald-100 text-emerald-600'
                                  : event.primarySentiment === 'negative'
                                    ? 'bg-rose-100 text-rose-600'
                                    : 'bg-amber-100 text-amber-600'
                              }`}
                            >
                              {event.primarySentiment === 'positive' ? '正向' : event.primarySentiment === 'negative' ? '负向' : '中性'}
                            </span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-6">
                    <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0">
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-600">{selectedEvent?.platform}</span>
                            <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">{selectedEvent?.type}</span>
                            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-gray-600">热榜第 {selectedEvent?.rank} 位</span>
                          </div>
                          <h2 className="text-2xl font-bold text-gray-900">{selectedEvent?.title}</h2>
                          <p className="mt-3 text-sm leading-7 text-gray-600">
                            {selectedEvent?.introduction || '当前事件暂无详细摘要，可结合传播趋势与关键词继续研判。'}
                          </p>
                        </div>
                        <div className="grid min-w-[220px] grid-cols-2 gap-3">
                          <div className="rounded-2xl bg-slate-50 px-4 py-3">
                            <div className="text-xs text-gray-500">参与度</div>
                            <div className="mt-2 text-xl font-semibold text-gray-900">{Math.round(selectedEvent?.participants || 0)}</div>
                          </div>
                          <div className="rounded-2xl bg-slate-50 px-4 py-3">
                            <div className="text-xs text-gray-500">传播速度</div>
                            <div className="mt-2 text-xl font-semibold text-gray-900">{formatRatioPercent(selectedEvent?.spreadSpeed)}</div>
                          </div>
                          <div className="rounded-2xl bg-slate-50 px-4 py-3">
                            <div className="text-xs text-gray-500">传播范围</div>
                            <div className="mt-2 text-xl font-semibold text-gray-900">{formatRatioPercent(selectedEvent?.spreadRange)}</div>
                          </div>
                          <div className="rounded-2xl bg-slate-50 px-4 py-3">
                            <div className="text-xs text-gray-500">情绪倾向</div>
                            <div className="mt-2 text-xl font-semibold text-gray-900">
                              {selectedEvent?.primarySentiment === 'positive' ? '正向' : selectedEvent?.primarySentiment === 'negative' ? '负向' : '中性'}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.3fr)_320px]">
                      <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                        <div className="mb-4 flex items-center justify-between">
                          <h3 className="text-base font-semibold text-gray-900">全球热点分布图</h3>
                          <span className="text-xs text-gray-400">按事件坐标映射热点位置</span>
                        </div>
                        <div className="relative h-[360px] overflow-hidden rounded-3xl border border-sky-100 bg-[radial-gradient(circle_at_20%_20%,rgba(125,211,252,0.28),transparent_30%),radial-gradient(circle_at_80%_30%,rgba(191,219,254,0.38),transparent_30%),linear-gradient(180deg,#eaf5ff_0%,#f8fbff_42%,#eef6ff_100%)]">
                          <WorldGeoMap
                            tone="light"
                            points={mapPoints}
                            selectedEventId={selectedEvent?.id}
                            onSelectEvent={setSelectedEventId}
                          />
                          <div className="absolute inset-0">
                            {[20, 40, 60, 80].map((line) => (
                              <div key={`h-${line}`} className="absolute left-0 right-0 border-t border-white/70" style={{ top: `${line}%` }} />
                            ))}
                            {[20, 40, 60, 80].map((line) => (
                              <div key={`v-${line}`} className="absolute bottom-0 top-0 border-l border-white/70" style={{ left: `${line}%` }} />
                            ))}
                          </div>
                          {selectedMapPoint ? (
                            <div className="absolute bottom-4 left-4 rounded-2xl border border-white/70 bg-white/80 px-4 py-3 text-xs text-gray-600 shadow-sm backdrop-blur-sm">
                              <div className="font-medium text-gray-900">{selectedEvent?.title}</div>
                              <div className="mt-1 flex items-center gap-2 text-[11px] text-gray-500">
                                <span>{selectedEvent?.platform}</span>
                                <span>经度 {selectedMapPoint.x.toFixed(1)}</span>
                                <span>纬度 {selectedMapPoint.y.toFixed(1)}</span>
                              </div>
                            </div>
                          ) : null}
                        </div>
                        <div className="mt-3 text-left text-[11px] leading-5 text-gray-400">
                          {COMMAND_CENTER_MAP_ATTRIBUTION}
                        </div>
                      </div>

                      <div className="space-y-6">
                        <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                          <div className="mb-4 flex items-center justify-between">
                            <h3 className="text-base font-semibold text-gray-900">舆情事件情报卡</h3>
                            <span className="text-xs text-gray-400">当前焦点事件</span>
                          </div>
                          <div className="rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50 to-white p-4">
                            <div className="flex items-start gap-3">
                              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-xl font-bold text-white shadow-sm">
                                {selectedEvent?.title?.charAt(0) || '事'}
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="line-clamp-2 text-base font-semibold text-gray-900">{selectedEvent?.title}</div>
                                <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                                  <span>{selectedEvent?.platform}</span>
                                  <span>{selectedEvent?.type}</span>
                                  <span>热榜第 {selectedEvent?.rank} 位</span>
                                </div>
                              </div>
                            </div>
                            <p className="mt-4 text-sm leading-7 text-gray-600">
                              {selectedEvent?.introduction || '当前事件暂无详细摘要。'}
                            </p>
                            <div className="mt-5 grid grid-cols-2 gap-3">
                              <div className="rounded-2xl bg-white/90 px-3 py-3">
                                <div className="text-xs text-gray-500">事件热度</div>
                                <div className="mt-2 text-3xl font-bold text-gray-900">#{selectedEvent?.rank || 0}</div>
                              </div>
                              <div className="rounded-2xl bg-white/90 px-3 py-3">
                                <div className="text-xs text-gray-500">影响力指数</div>
                                <div className="mt-2 flex items-end gap-2">
                                  <div className="text-3xl font-bold text-gray-900">{impactScore}</div>
                                  <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-600">{impactTag}</span>
                                </div>
                              </div>
                            </div>
                            <div className="mt-4">
                              <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                                <span>事件影响力指数</span>
                                <span>{impactScore}/100</span>
                              </div>
                              <div className="h-2 rounded-full bg-slate-100">
                                <div
                                  className="h-2 rounded-full bg-gradient-to-r from-teal-400 via-blue-500 to-indigo-600"
                                  style={{ width: `${Math.max(impactScore, 8)}%` }}
                                />
                              </div>
                              <div className="mt-2 flex items-center justify-between text-[11px] text-gray-400">
                                <span>一般</span>
                                <span>较大</span>
                                <span>重大</span>
                                <span>特大</span>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                          <div className="mb-4 flex items-center justify-between">
                            <h3 className="text-base font-semibold text-gray-900">全局平台分布</h3>
                            <span className="text-xs text-gray-400">当前热点样本</span>
                          </div>
                          <div className="space-y-3">
                            {platformDistribution.slice(0, 5).map((item) => (
                              <div key={item.name}>
                                <div className="mb-1 flex items-center justify-between text-sm text-gray-600">
                                  <span>{item.name}</span>
                                  <span>{item.value}</span>
                                </div>
                                <div className="h-2 rounded-full bg-slate-100">
                                  <div
                                    className="h-2 rounded-full bg-gradient-to-r from-blue-500 to-cyan-400"
                                    style={{ width: `${topPlatformCount ? Math.max((item.value / topPlatformCount) * 100, 12) : 0}%` }}
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
                      <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                        <div className="mb-4 flex items-center justify-between">
                          <h3 className="text-base font-semibold text-gray-900">传播热度趋势</h3>
                          <span className="text-xs text-gray-400">近 {heatTrendData.length || 0} 个采样点</span>
                        </div>
                        <div className="h-64">
                          {heatTrendData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                              <RechartsAreaChart data={heatTrendData}>
                                <defs>
                                  <linearGradient id="commandCenterHeat" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#2563eb" stopOpacity={0.35} />
                                    <stop offset="95%" stopColor="#2563eb" stopOpacity={0.04} />
                                  </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                                <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                                <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }} width={36} />
                                <RechartsTooltip />
                                <Area type="monotone" dataKey="value" stroke="#2563eb" fill="url(#commandCenterHeat)" strokeWidth={2} />
                              </RechartsAreaChart>
                            </ResponsiveContainer>
                          ) : (
                            <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-slate-50 text-sm text-gray-400">
                              暂无趋势数据
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="space-y-6">
                        <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                          <div className="mb-4 flex items-center justify-between">
                            <h3 className="text-base font-semibold text-gray-900">全局情绪分布</h3>
                            <span className="text-xs text-gray-400">按全体事件情绪值汇总</span>
                          </div>
                          <div className="h-56">
                            <ResponsiveContainer width="100%" height="100%">
                              <PieChart>
                                <Pie data={sentimentDistribution} dataKey="value" nameKey="name" outerRadius={78} innerRadius={44} paddingAngle={4}>
                                  {sentimentDistribution.map((entry, index) => (
                                    <Cell key={`${entry.name}-${index}`} fill={commandCenterSentimentColors[index % commandCenterSentimentColors.length]} />
                                  ))}
                                </Pie>
                                <RechartsTooltip />
                              </PieChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                      <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                        <div className="mb-4 flex items-center justify-between">
                          <h3 className="text-base font-semibold text-gray-900">事件情绪分布</h3>
                          <span className="text-xs text-gray-400">当前事件</span>
                        </div>
                        <div className="h-56">
                          {emotionChartData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                              <PieChart>
                                <Pie data={emotionChartData} dataKey="value" nameKey="name" outerRadius={76} innerRadius={40} paddingAngle={3}>
                                  {emotionChartData.map((entry, index) => (
                                    <Cell key={`${entry.name}-${index}`} fill={['#3b82f6', '#14b8a6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'][index % 6]} />
                                  ))}
                                </Pie>
                                <RechartsTooltip />
                              </PieChart>
                            </ResponsiveContainer>
                          ) : (
                            <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-slate-50 text-sm text-gray-400">
                              暂无情绪分布
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                        <div className="mb-4 flex items-center justify-between">
                          <h3 className="text-base font-semibold text-gray-900">事件立场分布</h3>
                          <span className="text-xs text-gray-400">当前事件</span>
                        </div>
                        <div className="space-y-3">
                          {stanceChartData.length > 0 ? stanceChartData.map((item) => (
                            <div key={item.name}>
                              <div className="mb-1 flex items-center justify-between text-sm text-gray-600">
                                <span>{item.name}</span>
                                <span>{item.value}%</span>
                              </div>
                              <div className="h-2 rounded-full bg-slate-100">
                                <div
                                  className="h-2 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-400"
                                  style={{ width: `${Math.max(item.value, 6)}%` }}
                                />
                              </div>
                            </div>
                          )) : (
                            <div className="flex h-56 items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-slate-50 text-sm text-gray-400">
                              暂无立场分布
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                      <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                        <div className="mb-4 flex items-center justify-between">
                          <h3 className="text-base font-semibold text-gray-900">时间线</h3>
                          <span className="text-xs text-gray-400">当前事件演化摘要</span>
                        </div>
                        {timelineItems.length > 0 ? (
                          <div className="space-y-4">
                            {timelineItems.map((item, index) => (
                              <div key={`${item.date}-${index}`} className="relative pl-6">
                                <span className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full bg-blue-500" />
                                <div className="text-xs font-medium text-blue-600">{item.date || `节点 ${index + 1}`}</div>
                                <div className="mt-1 text-sm leading-6 text-gray-600">{item.event || '暂无事件描述'}</div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="rounded-2xl border border-dashed border-gray-200 bg-slate-50 px-6 py-10 text-center text-sm text-gray-400">
                            暂无时间线数据
                          </div>
                        )}
                      </div>

                      <div className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                        <div className="mb-4 flex items-center justify-between">
                          <h3 className="text-base font-semibold text-gray-900">关键词云</h3>
                          <span className="text-xs text-gray-400">当前事件高频词</span>
                        </div>
                        {keywordCloudLayout.length > 0 ? (
                          <div className="h-72 rounded-2xl border border-blue-50 bg-gradient-to-br from-sky-50 via-white to-indigo-50 p-2">
                            <svg viewBox="0 0 100 100" className="h-full w-full">
                              {keywordCloudLayout.map((item, index) => (
                                <text
                                  key={`${item.word}-${index}`}
                                  x={item.x}
                                  y={item.y}
                                  fontSize={item.fontSize / 3.2}
                                  fill={item.fill}
                                  fillOpacity={item.opacity}
                                  textAnchor="middle"
                                  transform={`rotate(${item.rotate} ${item.x} ${item.y})`}
                                  style={{ fontWeight: 600 }}
                                >
                                  {item.word}
                                </text>
                              ))}
                            </svg>
                          </div>
                        ) : (
                          <div className="rounded-2xl border border-dashed border-gray-200 bg-slate-50 px-6 py-10 text-center text-sm text-gray-400">
                            暂无关键词数据
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const BigScreenView = ({
  onGoLogin,
  currentUser,
  authLoading,
  onLogout,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  onNewChat,
  onSelectHistory,
  sessions,
  onRenameSession,
  onDeleteSession,
}: any) => {
  const [data, setData] = useState<CommandCenterData | null>(null);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [trendTimeRange, setTrendTimeRange] = useState<'7d' | '30d'>('7d');
  const [hotPlatformTab, setHotPlatformTab] = useState('全部');
  const [screenReady, setScreenReady] = useState(false);
  const [isHotListPaused, setIsHotListPaused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadBigScreenData = async () => {
    if (!currentUser) {
      setData(null);
      setSelectedEventId('');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const next = await getCommandCenter();
      setData(next);
      setSelectedEventId((previous) => previous || next.events[0]?.id || '');
    } catch (loadError: any) {
      setError(loadError?.message || '获取可视化大屏数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadBigScreenData();
  }, [currentUser]);

  useEffect(() => {
    const timer = window.setTimeout(() => setScreenReady(true), 80);
    return () => window.clearTimeout(timer);
  }, []);

  const selectedEvent = useMemo<CommandCenterEvent | null>(() => {
    if (!data?.events?.length) {
      return null;
    }
    return data.events.find((item) => item.id === selectedEventId) || data.events[0] || null;
  }, [data, selectedEventId]);

  const summary = isPlainObject(data?.summary) ? data.summary : {};
  const platformDistribution = Array.isArray(summary?.platformDistribution)
    ? summary.platformDistribution.filter((item) => isPlainObject(item))
    : [];
  const sentimentDistribution = Array.isArray(summary?.sentimentDistribution)
    ? summary.sentimentDistribution.filter((item) => isPlainObject(item))
    : [];
  const wordCloudSource = Array.isArray(selectedEvent?.wordCloud)
    ? selectedEvent.wordCloud.filter((item) => isPlainObject(item))
    : [];
  const keywordCloudLayout = buildWordCloudLayout(wordCloudSource as Array<{ word: string; weight?: number }>).map((item, index) => ({
    ...item,
    fill: ['#8fe9ff', '#7dd3fc', '#67e8f9', '#93c5fd', '#a5f3fc', '#c4b5fd'][index % 6],
    opacity: Math.max(item.opacity, 0.82),
  }));
  const mapPoints = Array.isArray(data?.events) ? data.events.slice(0, 12) : [];
  const selectedMapPoint = selectedEvent ? projectEventToMap(selectedEvent) : null;
  const platformStats = useMemo(
    () => buildBigScreenPlatformStats(platformDistribution as Array<{ name: string; value: number }>, Array.isArray(data?.events) ? data.events : []),
    [platformDistribution, data?.events],
  );
  const platformMaxValue = Math.max(...platformStats.map((item) => item.value), 1);
  const platformBarMax = Math.max(...platformStats.map((item) => item.value), 1);
  const overviewTrendData = useMemo(
    () => buildBigScreenOverviewTrend(Array.isArray(data?.events) ? data.events : [], trendTimeRange),
    [data?.events, trendTimeRange],
  );
  const sentimentKeywordGroups = useMemo(
    () => buildBigScreenSentimentKeywords(wordCloudSource as Array<{ word: string; weight?: number }>),
    [wordCloudSource],
  );
  const textCategoryData = useMemo(
    () => buildBigScreenTextCategoryData(Array.isArray(data?.events) ? data.events : []),
    [data?.events],
  );
  const hotPlatforms = useMemo(() => ['全部', ...platformStats.map((item) => item.name)], [platformStats]);
  const hotEvents = useMemo(() => {
    const items = Array.isArray(data?.events) ? data.events : [];
    return items
      .filter((event) => hotPlatformTab === '全部' || event.platform === hotPlatformTab)
      .slice(0, 6);
  }, [data?.events, hotPlatformTab]);
  const topSentimentCount = Math.max(...sentimentDistribution.map((item: any) => Number(item.value || 0) || 0), 1);
  const panelClass = 'relative overflow-hidden rounded-[24px] border border-sky-200/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.9),rgba(243,249,255,0.82))] px-5 py-5 shadow-[0_18px_48px_rgba(148,163,184,0.14),inset_0_1px_0_rgba(255,255,255,0.92)] backdrop-blur-[18px]';
  const panelTitleClass = 'text-[1.05rem] font-semibold tracking-[0.08em] text-slate-900';
  const textCategoryColors = ['#9ae6ff', '#58d4ff', '#4f9cff', '#7c7dff', '#53f2c7'];
  const getPanelRevealStyle = (index: number) => ({
    opacity: screenReady ? 1 : 0,
    transform: screenReady ? 'translateY(0px)' : 'translateY(18px)',
    transition: `opacity 0.55s ease ${index * 90}ms, transform 0.55s ease ${index * 90}ms`,
  });

  useEffect(() => {
    if (!hotEvents.length || isHotListPaused) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setSelectedEventId((previous) => {
        const currentIndex = hotEvents.findIndex((event) => event.id === previous);
        const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % hotEvents.length : 0;
        return hotEvents[nextIndex]?.id || previous;
      });
    }, 6000);

    return () => window.clearInterval(timer);
  }, [hotEvents, isHotListPaused]);

  return (
    <div className="flex h-screen overflow-hidden bg-[#eef6ff] text-slate-800 relative pt-14">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(191,219,254,0.36),transparent_30%),radial-gradient(circle_at_20%_20%,rgba(125,211,252,0.18),transparent_22%),radial-gradient(circle_at_80%_0%,rgba(186,230,253,0.24),transparent_24%),linear-gradient(180deg,#edf6ff_0%,#f7fbff_54%,#eef5ff_100%)]" />
      <div className="pointer-events-none absolute inset-0 opacity-30 bg-[radial-gradient(#bfdbfe_0.7px,transparent_0.7px)] [background-size:18px_18px]" />
      <Sidebar onHome={() => {}} onNewChat={onNewChat} isCollapsed={isSidebarCollapsed} setIsCollapsed={setIsSidebarCollapsed} showHomeButton={false} onSelectHistory={onSelectHistory} activeHistory={null} sessions={sessions} onRenameSession={onRenameSession} onDeleteSession={onDeleteSession} />

      <div className="flex-1 overflow-y-auto px-5 pb-6 pt-6 relative z-10 scrollbar-hide">
        <div className="absolute right-6 top-6 z-20">
          <AuthAction currentUser={currentUser} authLoading={authLoading} onGoLogin={onGoLogin} onLogout={onLogout} />
        </div>

        <div className="mx-auto flex w-full max-w-[1780px] flex-col gap-5">
          <div className="relative px-4 pt-3 text-center">
            <div className="pointer-events-none absolute left-0 top-5 h-px w-[26%] bg-gradient-to-r from-transparent via-sky-300/90 to-transparent" />
            <div className="pointer-events-none absolute right-0 top-5 h-px w-[26%] bg-gradient-to-r from-transparent via-sky-300/90 to-transparent" />
            <div className="mx-auto inline-flex items-center gap-3 rounded-full border border-sky-200/90 bg-white/70 px-5 py-1.5 text-xs tracking-[0.36em] text-sky-600 backdrop-blur-xl">
              WANXIANG ANALYSIS SCREEN
            </div>
            <h1 className="mt-4 text-[2.6rem] font-semibold tracking-[0.12em] text-slate-900">
              舆情分析大屏
            </h1>
          </div>
          {!currentUser ? (
            <div className={`${panelClass} px-6 py-16 text-center`}>
              <p className="text-lg font-medium text-slate-800">登录后可查看可视化大屏中的实时事件分布与传播态势</p>
              <button
                onClick={onGoLogin}
                className="mt-5 inline-flex items-center gap-2 rounded-2xl border border-sky-200 bg-white/70 px-5 py-3 text-sm font-medium text-sky-700 transition hover:bg-sky-50"
              >
                <Lock size={16} />
                前往登录
              </button>
            </div>
          ) : loading && !data ? (
            <div className={`${panelClass} px-6 py-16 text-center text-sm text-slate-500`}>
              <Loader2 size={20} className="mx-auto mb-4 animate-spin text-sky-500" />
              正在加载大屏数据...
            </div>
          ) : !data?.events?.length ? (
            <div className={`${panelClass} px-6 py-16 text-center text-sm text-slate-500`}>
              {error || '当前暂无可展示的事件数据。'}
            </div>
          ) : (
            <>
              {error ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                  {error}
                </div>
              ) : null}
              <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[360px_minmax(0,1fr)_360px]">
                <div className="space-y-4">
                  <div className={panelClass} style={getPanelRevealStyle(0)}>
                    <div className="mb-5 flex items-center gap-2">
                      <Gauge size={18} className="text-sky-500" />
                      <h2 className={panelTitleClass}>今日舆情数量（千）</h2>
                    </div>
                    <div className="grid grid-cols-2 gap-y-6">
                      {platformStats.map((item) => (
                        <div key={item.name}>
                          <BigScreenRingGauge label={item.name} value={item.value} maxValue={platformMaxValue} />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className={panelClass} style={getPanelRevealStyle(1)}>
                    <div className="mb-4 flex items-center gap-2">
                      <Sparkles size={18} className="text-sky-500" />
                      <h2 className={panelTitleClass}>情感分析</h2>
                    </div>
                    <div className="grid grid-cols-[160px_minmax(0,1fr)] gap-4">
                      <div className="h-[190px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie data={sentimentDistribution} dataKey="value" nameKey="name" outerRadius={70} innerRadius={0}>
                              {sentimentDistribution.map((entry, index) => (
                                <Cell key={`${entry.name}-${index}`} fill={['#8fdfff', '#67e8f9', '#38bdf8'][index % 3]} />
                              ))}
                            </Pie>
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="space-y-5">
                        <div>
                          <div className="mb-2 text-sm font-semibold text-slate-700">正面高频词语</div>
                          <div className="flex flex-wrap gap-2">
                            {sentimentKeywordGroups.positive.map((item) => (
                              <span key={`positive-${item.word}`} className="rounded-md border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm text-sky-700">
                                {item.word}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <div className="mb-2 text-sm font-semibold text-slate-700">负面高频词语</div>
                          <div className="flex flex-wrap gap-2">
                            {sentimentKeywordGroups.negative.map((item) => (
                              <span key={`negative-${item.word}`} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700">
                                {item.word}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 space-y-2">
                      {sentimentDistribution.map((item: any, index) => (
                        <div key={item.name} className="flex items-center gap-3 text-sm text-slate-600">
                          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: ['#8fdfff', '#67e8f9', '#38bdf8'][index % 3] }} />
                          <span>{item.name}</span>
                          <div className="h-px flex-1 bg-sky-100" />
                          <span>{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className={panelClass} style={getPanelRevealStyle(2)}>
                    <div className="mb-5 flex items-center gap-2">
                      <Share2 size={18} className="text-sky-500" />
                      <h2 className={panelTitleClass}>多平台来源统计（千）</h2>
                    </div>
                    <div className="space-y-4">
                      {platformStats.map((item) => (
                        <div key={`source-${item.name}`}>
                          <div className="mb-1 flex items-center justify-between text-sm text-slate-700">
                            <span>{item.name}</span>
                            <span>{item.value}</span>
                          </div>
                          <div className="h-3 overflow-hidden rounded-full bg-sky-100 shadow-[inset_0_0_18px_rgba(56,189,248,0.08)]">
                            <div
                              className="h-full rounded-full bg-[linear-gradient(90deg,rgba(186,230,253,0.95),rgba(14,165,233,0.88))] shadow-[0_0_14px_rgba(56,189,248,0.24)]"
                              style={{ width: `${Math.max((item.value / platformBarMax) * 100, item.value > 0 ? 8 : 0)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className={`${panelClass} min-h-[480px]`} style={getPanelRevealStyle(3)}>
                    <div className="mb-4 flex items-center justify-between gap-4">
                      <h2 className={panelTitleClass}>地理位置分布</h2>
                      <button
                        onClick={() => void loadBigScreenData()}
                        disabled={loading}
                        className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white/72 px-4 py-2 text-xs tracking-[0.12em] text-sky-700 transition hover:bg-sky-50 disabled:opacity-60"
                      >
                        {loading ? <Loader2 size={14} className="animate-spin" /> : <Radar size={14} />}
                        刷新大屏
                      </button>
                    </div>
                    <div className="relative h-[400px] overflow-hidden rounded-[18px] border border-sky-100 bg-[radial-gradient(circle_at_30%_30%,rgba(125,211,252,0.22),transparent_34%),linear-gradient(180deg,rgba(255,255,255,0.84),rgba(241,248,255,0.76))]">
                      <WorldGeoMap tone="light" points={mapPoints} selectedEventId={selectedEvent?.id} onSelectEvent={setSelectedEventId} />
                      <div className="pointer-events-none absolute inset-0">
                        {[20, 40, 60, 80].map((line) => (
                          <div key={`screen-h-${line}`} className="absolute left-0 right-0 border-t border-white/70" style={{ top: `${line}%` }} />
                        ))}
                        {[20, 40, 60, 80].map((line) => (
                          <div key={`screen-v-${line}`} className="absolute bottom-0 top-0 border-l border-white/70" style={{ left: `${line}%` }} />
                        ))}
                      </div>
                      {selectedMapPoint ? (
                        <div className="absolute bottom-4 left-4 rounded-2xl border border-white/80 bg-white/70 px-4 py-3 text-xs text-slate-600 shadow-[0_16px_40px_rgba(148,163,184,0.14)] backdrop-blur-sm">
                          <div className="font-medium text-slate-800">{selectedEvent?.title}</div>
                          <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-500">
                            <span>{selectedEvent?.platform}</span>
                            <span>经度 {selectedMapPoint.x.toFixed(1)}</span>
                            <span>纬度 {selectedMapPoint.y.toFixed(1)}</span>
                          </div>
                        </div>
                      ) : null}
                    </div>
                    <div className="mt-3 text-left text-[11px] leading-5 text-slate-400">
                      {COMMAND_CENTER_MAP_ATTRIBUTION}
                    </div>
                  </div>

                  <div className={`${panelClass} min-h-[290px]`} style={getPanelRevealStyle(4)}>
                    <div className="mb-5 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <LineChart size={18} className="text-sky-500" />
                        <h2 className={panelTitleClass}>舆情趋势</h2>
                      </div>
                      <div className="inline-flex items-center rounded-full border border-sky-200 bg-white/70 p-1 text-sm backdrop-blur-sm">
                        <button
                          onClick={() => setTrendTimeRange('7d')}
                          className={`rounded-full px-4 py-1.5 transition ${trendTimeRange === '7d' ? 'bg-sky-500 text-white shadow-[0_8px_18px_rgba(56,189,248,0.22)]' : 'text-slate-500'}`}
                        >
                          一周
                        </button>
                        <button
                          onClick={() => setTrendTimeRange('30d')}
                          className={`rounded-full px-4 py-1.5 transition ${trendTimeRange === '30d' ? 'bg-sky-500 text-white shadow-[0_8px_18px_rgba(56,189,248,0.22)]' : 'text-slate-500'}`}
                        >
                          一个月
                        </button>
                      </div>
                    </div>
                    <div className="mb-4 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                      <span className="rounded-full border border-sky-200 bg-white/80 px-3 py-1.5">
                        当前焦点：{selectedEvent?.title || '暂无'}
                      </span>
                      <span className="rounded-full border border-slate-200 bg-white/70 px-3 py-1.5">
                        平台：{selectedEvent?.platform || '未标注'}
                      </span>
                      <span className="rounded-full border border-slate-200 bg-white/70 px-3 py-1.5">
                        采样点：{overviewTrendData.length}
                      </span>
                    </div>
                    <div className="h-[210px]">
                      {overviewTrendData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <RechartsAreaChart data={overviewTrendData}>
                            <defs>
                              <linearGradient id="screenTrendFill" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#8fdfff" stopOpacity={0.38} />
                                <stop offset="95%" stopColor="#8fdfff" stopOpacity={0.03} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="4 4" stroke="rgba(125,211,252,0.18)" />
                            <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#cbd5e1' }} axisLine={{ stroke: 'rgba(125,211,252,0.18)' }} tickLine={false} />
                            <YAxis tick={{ fontSize: 12, fill: '#cbd5e1' }} axisLine={false} tickLine={false} width={42} />
                            <RechartsTooltip
                              contentStyle={{
                                backgroundColor: 'rgba(255,255,255,0.96)',
                                borderColor: 'rgba(191,219,254,0.9)',
                                color: '#1e293b',
                                borderRadius: '14px',
                              }}
                              formatter={(value: number) => [Number(value).toLocaleString(), '热度']}
                            />
                            <Area
                              type="monotone"
                              dataKey="value"
                              stroke="#7dd3fc"
                              fill="url(#screenTrendFill)"
                              strokeWidth={2.5}
                              dot={{ r: 3, strokeWidth: 1.5, fill: '#7dd3fc', stroke: '#cffafe' }}
                              activeDot={{ r: 4.5, fill: '#a5f3fc', stroke: '#ecfeff', strokeWidth: 2 }}
                            />
                          </RechartsAreaChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-sky-200 bg-white/45 text-sm text-slate-500">
                          暂无趋势数据
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div
                    className={`${panelClass} min-h-[280px]`}
                    style={getPanelRevealStyle(5)}
                    onMouseEnter={() => setIsHotListPaused(true)}
                    onMouseLeave={() => setIsHotListPaused(false)}
                  >
                    <div className="mb-4 flex items-center justify-between">
                      <h2 className={panelTitleClass}>热点舆情</h2>
                      <span className="text-xs tracking-[0.16em] text-slate-400">
                        {isHotListPaused ? '已暂停轮播' : `TOP ${hotEvents.length}`}
                      </span>
                    </div>
                    <div className="mb-4 flex flex-wrap gap-2">
                      {hotPlatforms.map((platform) => (
                        <button
                          key={platform}
                          onClick={() => setHotPlatformTab(platform)}
                          className={`rounded-full border px-3 py-1.5 text-sm transition ${
                            hotPlatformTab === platform
                              ? 'border-sky-200 bg-sky-50 text-sky-700 shadow-[0_8px_20px_rgba(56,189,248,0.14)]'
                              : 'border-slate-200 bg-white/55 text-slate-500 hover:border-sky-200'
                          }`}
                        >
                          {platform}
                        </button>
                      ))}
                    </div>
                    <div className="space-y-3">
                      {hotEvents.map((event) => (
                        <button
                          key={event.id}
                          onClick={() => setSelectedEventId(event.id)}
                          className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                            selectedEvent?.id === event.id
                              ? 'border-sky-200 bg-sky-50/85'
                              : 'border-slate-200 bg-white/45 hover:bg-white/75'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className={`inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold ${
                                  selectedEvent?.id === event.id ? 'bg-sky-500 text-white' : 'bg-slate-100 text-slate-500'
                                }`}>
                                  {event.rank}
                                </span>
                                <div className="truncate text-sm font-medium text-slate-800">{event.title}</div>
                              </div>
                              <div className="mt-1 text-xs text-slate-500">{event.platform} · {event.type}</div>
                              <div className="mt-2 h-1.5 rounded-full bg-sky-100">
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-sky-400 to-cyan-400 transition-all duration-500"
                                  style={{ width: `${Math.max(16, 100 - event.rank * 8)}%` }}
                                />
                              </div>
                            </div>
                            <span className={`rounded-full px-2.5 py-1 text-xs ${
                              event.primarySentiment === 'positive'
                                ? 'bg-emerald-100 text-emerald-700'
                                : event.primarySentiment === 'negative'
                                  ? 'bg-rose-100 text-rose-700'
                                  : 'bg-amber-100 text-amber-700'
                            }`}>
                              {event.primarySentiment === 'positive' ? '正向' : event.primarySentiment === 'negative' ? '负向' : '中性'}
                            </span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className={`${panelClass} min-h-[300px]`} style={getPanelRevealStyle(6)}>
                    <div className="mb-4 flex items-center justify-between">
                      <h2 className={panelTitleClass}>热点词云</h2>
                      <span className="text-xs text-slate-400">{selectedEvent?.title || '当前事件'}</span>
                    </div>
                    <div className="relative h-[260px] overflow-hidden rounded-[18px] border border-sky-100 bg-[radial-gradient(circle_at_center,rgba(125,211,252,0.18),transparent_48%),linear-gradient(180deg,rgba(255,255,255,0.7),rgba(241,248,255,0.5))]">
                      {keywordCloudLayout.length > 0 ? (
                        <svg viewBox="0 0 100 100" className="h-full w-full">
                          {keywordCloudLayout.map((item, index) => (
                            <text
                              key={`${item.word}-${index}`}
                              x={item.x}
                              y={item.y}
                              fontSize={item.fontSize / 3.1}
                              fill={item.fill}
                              fillOpacity={item.opacity}
                              textAnchor="middle"
                              transform={`rotate(${item.rotate} ${item.x} ${item.y})`}
                              style={{ fontWeight: 600 }}
                            >
                              {item.word}
                            </text>
                          ))}
                        </svg>
                      ) : (
                        <div className="flex h-full items-center justify-center text-sm text-slate-500">
                          暂无关键词数据
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={`${panelClass} min-h-[300px]`} style={getPanelRevealStyle(7)}>
                    <div className="mb-4 flex items-center justify-between">
                      <h2 className={panelTitleClass}>文本分类</h2>
                      <span className="text-xs text-slate-400">按事件类型聚合</span>
                    </div>
                    <div className="grid grid-cols-[170px_minmax(0,1fr)] gap-3">
                      <div className="relative h-[220px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie data={textCategoryData} dataKey="value" nameKey="name" outerRadius={76} innerRadius={44} paddingAngle={3}>
                              {textCategoryData.map((entry, index) => (
                                <Cell key={`${entry.name}-${index}`} fill={textCategoryColors[index % textCategoryColors.length]} />
                              ))}
                            </Pie>
                          </PieChart>
                        </ResponsiveContainer>
                        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                          <div className="rounded-full border border-sky-200 bg-white/72 px-3 py-1.5 text-center backdrop-blur-sm">
                            <div className="text-xs text-slate-400">分类数</div>
                            <div className="text-lg font-semibold text-slate-800">{textCategoryData.length}</div>
                          </div>
                        </div>
                      </div>
                      <div className="space-y-3 pt-4">
                        {textCategoryData.map((item, index) => (
                          <div key={`type-${item.name}`} className="text-sm text-slate-700">
                            <div className="mb-1 flex items-center justify-between gap-3">
                              <div className="flex items-center gap-2">
                                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: textCategoryColors[index % textCategoryColors.length] }} />
                                <span>{item.name}</span>
                              </div>
                              <span>{item.value}%</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-sky-100">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${Math.max(item.value, 8)}%`,
                                  backgroundColor: textCategoryColors[index % textCategoryColors.length],
                                  boxShadow: `0 0 12px ${textCategoryColors[index % textCategoryColors.length]}`,
                                }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const KnowledgeBaseView = ({
  onGoLogin,
  currentUser,
  authLoading,
  onLogout,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  onNewChat,
  onSelectHistory,
  sessions,
  onRenameSession,
  onDeleteSession,
}: any) => {
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [files, setFiles] = useState<KnowledgeFile[]>([]);
  const [selectedBaseId, setSelectedBaseId] = useState('');
  const [newKbName, setNewKbName] = useState('');
  const [newKbDescription, setNewKbDescription] = useState('');
  const [remark, setRemark] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loadingBases, setLoadingBases] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [fileActionTarget, setFileActionTarget] = useState('');
  const [batchRebuilding, setBatchRebuilding] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');
  const [ragQuery, setRagQuery] = useState('');
  const [ragSourceUrl, setRagSourceUrl] = useState('');
  const [ragPlatformHint, setRagPlatformHint] = useState('');
  const [ragLoading, setRagLoading] = useState(false);
  const [ragError, setRagError] = useState('');
  const [ragResult, setRagResult] = useState<RagAnswerResult | null>(null);

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 3000);
  };

  const loadBases = async () => {
    if (!currentUser) {
      setBases([]);
      setFiles([]);
      setSelectedBaseId('');
      return;
    }

    setLoadingBases(true);
    setError('');
    try {
      const items = await getKnowledgeBases();
      setBases(items);
      setSelectedBaseId((previous) => previous || items[0]?.id || '');
    } catch (loadError: any) {
      setError(loadError?.message || '获取知识库列表失败');
    } finally {
      setLoadingBases(false);
    }
  };

  const loadFiles = async (kbId: string) => {
    if (!kbId) {
      setFiles([]);
      return;
    }

    setLoadingFiles(true);
    setError('');
    try {
      const items = await getKnowledgeFiles(kbId);
      setFiles(items);
    } catch (loadError: any) {
      setError(loadError?.message || '获取知识库文件失败');
    } finally {
      setLoadingFiles(false);
    }
  };

  useEffect(() => {
    void loadBases();
  }, [currentUser]);

  useEffect(() => {
    if (selectedBaseId) {
      void loadFiles(selectedBaseId);
    } else {
      setFiles([]);
    }
  }, [selectedBaseId]);

  useEffect(() => {
    if (!selectedBaseId) {
      return undefined;
    }
    const shouldPoll = files.some(
      (file) =>
        file.parseStatus === 'pending' ||
        file.parseStatus === 'processing' ||
        file.indexStatus === 'pending' ||
        file.indexStatus === 'processing',
    );
    if (!shouldPoll) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      void loadFiles(selectedBaseId);
    }, 2000);

    return () => window.clearInterval(timer);
  }, [selectedBaseId, files]);

  const handleCreateBase = async () => {
    if (!newKbName.trim()) {
      showToast('请先输入知识库名称');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const created = await createKnowledgeBase({
        name: newKbName.trim(),
        description: newKbDescription.trim(),
      });
      setNewKbName('');
      setNewKbDescription('');
      await loadBases();
      setSelectedBaseId(created.id);
      showToast('知识库创建成功');
    } catch (submitError: any) {
      setError(submitError?.message || '创建知识库失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpload = async () => {
    if (!selectedBaseId) {
      showToast('请先选择知识库');
      return;
    }
    if (!selectedFile) {
      showToast('请先选择文件');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await uploadKnowledgeFile({
        kbId: selectedBaseId,
        file: selectedFile,
        remark: remark.trim(),
      });
      setSelectedFile(null);
      setRemark('');
      await loadFiles(selectedBaseId);
      showToast('文件上传成功');
    } catch (submitError: any) {
      setError(submitError?.message || '上传文件失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (fileId: string) => {
    setSubmitting(true);
    setError('');
    try {
      await deleteKnowledgeFile(fileId);
      await loadFiles(selectedBaseId);
      showToast('文件已删除');
    } catch (submitError: any) {
      setError(submitError?.message || '删除文件失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetryParse = async (fileId: string) => {
    setFileActionTarget(`parse:${fileId}`);
    setError('');
    try {
      await retryKnowledgeFileParse(fileId);
      await loadFiles(selectedBaseId);
      showToast('已提交重新解析任务');
    } catch (submitError: any) {
      setError(submitError?.message || '重新解析文件失败');
    } finally {
      setFileActionTarget('');
    }
  };

  const handleRetryIndex = async (fileId: string) => {
    setFileActionTarget(`index:${fileId}`);
    setError('');
    try {
      await retryKnowledgeFileIndex(fileId);
      await loadFiles(selectedBaseId);
      showToast('已提交重试索引任务');
    } catch (submitError: any) {
      setError(submitError?.message || '重试文件索引失败');
    } finally {
      setFileActionTarget('');
    }
  };

  const handleBatchRebuildIndex = async () => {
    if (!selectedBaseId) {
      showToast('请先选择知识库');
      return;
    }

    setBatchRebuilding(true);
    setError('');
    try {
      const result = await rebuildKnowledgeBaseIndex(selectedBaseId);
      await loadFiles(selectedBaseId);
      showToast(`已提交批量任务：共 ${result.queuedCount} 个，解析 ${result.parseQueued} 个，索引 ${result.indexQueued} 个`);
    } catch (submitError: any) {
      setError(submitError?.message || '批量重建索引失败');
    } finally {
      setBatchRebuilding(false);
    }
  };

  const handleRagDebug = async () => {
    if (!ragQuery.trim()) {
      showToast('请先输入调试问题');
      return;
    }

    setRagLoading(true);
    setRagError('');
    try {
      const result = await getRagAnswer({
        query: ragQuery.trim(),
        kbId: selectedBaseId || undefined,
        sourceUrl: ragSourceUrl.trim() || undefined,
        platformHint: ragPlatformHint.trim() || undefined,
      });
      setRagResult(result);
      showToast('RAG 调试返回成功');
    } catch (requestError: any) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        setRagError('当前调试接口需要登录。请先确认登录状态，再重试。');
      } else if (requestError instanceof ApiError && requestError.status === 404) {
        setRagError('当前 frontend_api 还没有加载到最新代码，/api/rag/answer 未生效。请重启 frontend_api 或执行 ./start_chatboard_stack.sh restart 后重试。');
      } else if (requestError instanceof ApiError && requestError.status >= 500) {
        setRagError(`RAG 调试链路返回 ${requestError.status}。通常是 ChatBackend 或 rag_service 暂时异常，请查看 .runtime/frontend_api.log 与 .runtime/chatbackend.log。`);
      } else {
        setRagError(requestError?.message || 'RAG 调试失败');
      }
    } finally {
      setRagLoading(false);
    }
  };

  const handleExportStructuredRecords = () => {
    const rows = (ragResult?.structuredRecords || [])
      .map((item) => item.record)
      .filter((record): record is NonNullable<typeof ragResult>['structuredRecords'][number]['record'] => Boolean(record));

    if (!rows.length) {
      showToast('当前没有可导出的结构化记录');
      return;
    }

    const header = ['省份', '准考证号', '学校', '姓名', '科目', '组别', '奖项', '是否晋级'];
    const lines = [
      header.map(toCsvCell).join(','),
      ...rows.map((record) => [
        toCsvCell(record?.province),
        toCsvCell(record?.ticketNo),
        toCsvCell(record?.schoolName),
        toCsvCell(record?.studentName),
        toCsvCell(record?.subjectName),
        toCsvCell(record?.groupName),
        toCsvCell(record?.award),
        toCsvCell(record?.qualifiedForFinalLabel || (record?.qualifiedForFinal ? '是' : record?.qualifiedForFinal === false ? '否' : '')),
      ].join(',')),
    ];

    const kbName = bases.find((base) => base.id === selectedBaseId)?.name || 'knowledge';
    downloadTextFile(`structured-records-${kbName}.csv`, `\ufeff${lines.join('\n')}`, 'text/csv;charset=utf-8');
    showToast('结构化记录已导出为 CSV');
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden text-gray-800 relative pt-14">
      <BackgroundEffects />
      <Sidebar onHome={() => {}} onNewChat={onNewChat} isCollapsed={isSidebarCollapsed} setIsCollapsed={setIsSidebarCollapsed} showHomeButton={false} onSelectHistory={onSelectHistory} activeHistory={null} sessions={sessions} onRenameSession={onRenameSession} onDeleteSession={onDeleteSession} />

      <div className="flex-1 flex flex-col items-center px-4 py-20 relative overflow-y-auto scrollbar-hide">
        <div className="absolute top-6 right-6 z-10">
          <AuthAction currentUser={currentUser} authLoading={authLoading} onGoLogin={onGoLogin} onLogout={onLogout} />
        </div>

        {toast && (
          <div className="absolute top-10 left-1/2 z-50 -translate-x-1/2 rounded-full bg-gray-800/90 px-6 py-2.5 text-sm text-white shadow-lg flex items-center gap-2">
            <CheckCircle2 size={16} className="text-green-400" />
            {toast}
          </div>
        )}

        <div className="w-full max-w-5xl rounded-3xl border border-white/60 bg-white/70 p-6 shadow-sm backdrop-blur-md">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-gray-900">私有知识库</h1>
            <p className="mt-2 text-sm text-gray-500">当前已支持文件上传、解析和分块索引；结构化结果工具与导出能力已迁移到对话页工具箱。</p>
          </div>

          {!currentUser ? (
            <div className="rounded-2xl border border-dashed border-gray-200 bg-white/70 px-6 py-12 text-center">
              <p className="text-base font-medium text-gray-700">登录后可创建知识库并上传文件</p>
              <button
                onClick={onGoLogin}
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
              >
                <Lock size={16} />
                前往登录
              </button>
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
                <div className="rounded-2xl border border-gray-100 bg-white/80 p-5">
                  <div className="mb-4 flex items-center gap-2 text-sm font-medium text-gray-700">
                    <FolderPlus size={16} className="text-blue-500" />
                    创建知识库
                  </div>
                  <div className="space-y-3">
                    <input
                      value={newKbName}
                      onChange={(event) => setNewKbName(event.target.value)}
                      placeholder="知识库名称，例如：品牌公关手册"
                      className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                    />
                    <textarea
                      value={newKbDescription}
                      onChange={(event) => setNewKbDescription(event.target.value)}
                      rows={3}
                      placeholder="知识库说明（可选）"
                      className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                    />
                    <button
                      onClick={() => void handleCreateBase()}
                      disabled={submitting}
                      className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {submitting ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                      新建知识库
                    </button>
                  </div>
                </div>

                <div className="rounded-2xl border border-gray-100 bg-white/80 p-5">
                  <div className="mb-4 flex items-center gap-2 text-sm font-medium text-gray-700">
                    <Upload size={16} className="text-emerald-500" />
                    上传文件
                  </div>
                  <div className="space-y-3">
                    <select
                      value={selectedBaseId}
                      onChange={(event) => setSelectedBaseId(event.target.value)}
                      className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                    >
                      <option value="">请选择知识库</option>
                      {bases.map((base) => (
                        <option key={base.id} value={base.id}>
                          {base.name}
                        </option>
                      ))}
                    </select>
                    <input
                      type="file"
                      onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                      className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm"
                    />
                    <input
                      value={remark}
                      onChange={(event) => setRemark(event.target.value)}
                      placeholder="备注（可选）"
                      className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                    />
                    <button
                      onClick={() => void handleUpload()}
                      disabled={submitting || !selectedFile}
                      className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {submitting ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                      上传到知识库
                    </button>
                  </div>
                </div>
              </div>

              <div className="hidden rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50/80 via-white to-cyan-50/70 p-5 shadow-sm">
                <div className="mb-4 flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-base font-semibold text-gray-900">RAG 调试入口</h2>
                    <p className="mt-1 text-sm text-gray-500">
                      临时验证链路：`frontend_new -&gt; frontend_api -&gt; ChatBackend -&gt; rag_service`。当前不会改聊天主链路，只用于观察检索与 grounding 返回结构。
                    </p>
                  </div>
                  <span className="rounded-full bg-blue-600 px-3 py-1 text-xs font-medium text-white">临时调试</span>
                </div>

                <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
                  <div className="space-y-3">
                    <textarea
                      value={ragQuery}
                      onChange={(event) => setRagQuery(event.target.value)}
                      rows={4}
                      placeholder="输入一个想验证的提问，例如：基于当前知识库，总结品牌危机回应的标准动作，并标出可直接引用的事实。"
                      className="w-full rounded-2xl border border-blue-100 bg-white px-4 py-3 text-sm leading-6 outline-none focus:border-blue-400"
                    />
                    <div className="grid gap-3 md:grid-cols-2">
                      <input
                        value={ragSourceUrl}
                        onChange={(event) => setRagSourceUrl(event.target.value)}
                        placeholder="可选：实时检索源 URL"
                        className="w-full rounded-xl border border-blue-100 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                      />
                      <input
                        value={ragPlatformHint}
                        onChange={(event) => setRagPlatformHint(event.target.value)}
                        placeholder="可选：平台提示，例如 微博 / 小红书"
                        className="w-full rounded-xl border border-blue-100 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-sm text-gray-500">
                      <span className="rounded-full bg-white px-3 py-1.5 shadow-sm">
                        当前知识库：{bases.find((base) => base.id === selectedBaseId)?.name || '不使用知识库，仅做实时检索/空检索验证'}
                      </span>
                      <button
                        onClick={() => void handleRagDebug()}
                        disabled={ragLoading}
                        className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {ragLoading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
                        发送调试请求
                      </button>
                    </div>
                    {ragError ? (
                      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                        {ragError}
                      </div>
                    ) : null}
                  </div>

                  <div className="rounded-2xl border border-white/80 bg-white/80 p-4 shadow-sm">
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-600">
                        grounding：{ragResult?.groundingStatus || '-'}
                      </span>
                      <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-600">
                        confidence：{ragResult?.confidence || '-'}
                      </span>
                      <span className="rounded-full bg-amber-50 px-3 py-1.5 text-amber-600">
                        realtime：{ragResult?.usedRealtimeRetrieval ? 'yes' : 'no'}
                      </span>
                    </div>
                    <div className="mt-4 text-sm leading-7 text-gray-600">
                      {ragResult?.answer ? ragResult.answer : '调试结果会显示在这里，方便直接核对回答、事实、待核实项与来源。'}
                    </div>
                  </div>
                </div>

                {ragResult ? (
                  <div className="mt-5 grid gap-4 xl:grid-cols-2">
                    <div className="space-y-4">
                      <div className="rounded-2xl border border-gray-100 bg-white/85 p-4">
                        <div className="text-sm font-medium text-gray-800">事实摘要</div>
                        <div className="mt-3 space-y-2 text-sm text-gray-600">
                          {ragResult.facts && ragResult.facts.length > 0 ? ragResult.facts.map((item, index) => (
                            <div key={`fact-${index}`} className="rounded-xl bg-slate-50 px-3 py-2">{item}</div>
                          )) : <div className="text-gray-400">暂无事实摘要</div>}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-gray-100 bg-white/85 p-4">
                        <div className="text-sm font-medium text-gray-800">待核实项</div>
                        <div className="mt-3 space-y-2 text-sm text-gray-600">
                          {ragResult.toVerify && ragResult.toVerify.length > 0 ? ragResult.toVerify.map((item, index) => (
                            <div key={`verify-${index}`} className="rounded-xl bg-amber-50 px-3 py-2 text-amber-700">{item}</div>
                          )) : <div className="text-gray-400">暂无待核实项</div>}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-gray-100 bg-white/85 p-4">
                        <div className="text-sm font-medium text-gray-800">分析判断</div>
                        <div className="mt-3 space-y-2 text-sm text-gray-600">
                          {ragResult.analysis && ragResult.analysis.length > 0 ? ragResult.analysis.map((item, index) => (
                            <div key={`analysis-${index}`} className="rounded-xl bg-blue-50 px-3 py-2 text-blue-700">{item}</div>
                          )) : <div className="text-gray-400">暂无分析判断</div>}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      {ragResult.structuredAggregations ? (
                        <div className="rounded-2xl border border-gray-100 bg-white/85 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-medium text-gray-800">结构化聚合</div>
                            {ragResult.structuredRecords && ragResult.structuredRecords.length > 0 ? (
                              <button
                                type="button"
                                onClick={handleExportStructuredRecords}
                                className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-100"
                              >
                                <FileText size={14} />
                                导出 CSV
                              </button>
                            ) : null}
                          </div>
                          <div className="mt-3 grid gap-3 sm:grid-cols-3">
                            <div className="rounded-xl bg-fuchsia-50 px-3 py-3 text-sm text-fuchsia-700">
                              总命中：{ragResult.structuredAggregations.totalMatchedCount ?? 0}
                            </div>
                            <div className="rounded-xl bg-blue-50 px-3 py-3 text-sm text-blue-700">
                              晋级数：{ragResult.structuredAggregations.finalistCount ?? 0}
                            </div>
                            <div className="rounded-xl bg-emerald-50 px-3 py-3 text-sm text-emerald-700">
                              院校数：{ragResult.structuredAggregations.uniqueSchoolCount ?? 0}
                            </div>
                          </div>

                          <div className="mt-4 grid gap-4 lg:grid-cols-3">
                            <div>
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-400">学校分布</div>
                              <div className="mt-2 space-y-2">
                                {ragResult.structuredAggregations.countsBySchool?.length ? ragResult.structuredAggregations.countsBySchool.slice(0, 5).map((item, index) => (
                                  <div key={`agg-school-${index}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                                    {item.name || '-'}：{item.count ?? 0}
                                  </div>
                                )) : <div className="text-sm text-gray-400">暂无学校聚合</div>}
                              </div>
                            </div>
                            <div>
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-400">奖项分布</div>
                              <div className="mt-2 space-y-2">
                                {ragResult.structuredAggregations.countsByAward?.length ? ragResult.structuredAggregations.countsByAward.slice(0, 5).map((item, index) => (
                                  <div key={`agg-award-${index}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                                    {item.name || '-'}：{item.count ?? 0}
                                  </div>
                                )) : <div className="text-sm text-gray-400">暂无奖项聚合</div>}
                              </div>
                            </div>
                            <div>
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-400">组别分布</div>
                              <div className="mt-2 space-y-2">
                                {ragResult.structuredAggregations.countsByGroup?.length ? ragResult.structuredAggregations.countsByGroup.slice(0, 5).map((item, index) => (
                                  <div key={`agg-group-${index}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                                    {item.name || '-'}：{item.count ?? 0}
                                  </div>
                                )) : <div className="text-sm text-gray-400">暂无组别聚合</div>}
                              </div>
                            </div>
                          </div>

                          {ragResult.structuredRecords && ragResult.structuredRecords.length > 0 ? (
                            <div className="mt-4">
                              <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-400">结构化记录表</div>
                              <div className="mt-2 overflow-x-auto rounded-xl border border-slate-100 bg-white">
                                <table className="min-w-full divide-y divide-slate-100 text-left text-sm">
                                  <thead className="bg-slate-50 text-xs uppercase tracking-[0.12em] text-slate-400">
                                    <tr>
                                      <th className="px-3 py-3 font-medium">学校</th>
                                      <th className="px-3 py-3 font-medium">姓名</th>
                                      <th className="px-3 py-3 font-medium">科目</th>
                                      <th className="px-3 py-3 font-medium">组别</th>
                                      <th className="px-3 py-3 font-medium">奖项</th>
                                      <th className="px-3 py-3 font-medium">晋级</th>
                                      <th className="px-3 py-3 font-medium">综合分</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-100 text-slate-600">
                                    {ragResult.structuredRecords.slice(0, 20).map((item, index) => (
                                      <tr key={`structured-row-${index}`} className="align-top">
                                        <td className="px-3 py-3">{item.record?.schoolName || '-'}</td>
                                        <td className="px-3 py-3">{item.record?.studentName || '-'}</td>
                                        <td className="px-3 py-3">{item.record?.subjectName || '-'}</td>
                                        <td className="px-3 py-3">{item.record?.groupName || '-'}</td>
                                        <td className="px-3 py-3">{item.record?.award || '-'}</td>
                                        <td className="px-3 py-3">{item.record?.qualifiedForFinalLabel || (item.record?.qualifiedForFinal ? '是' : item.record?.qualifiedForFinal === false ? '否' : '-')}</td>
                                        <td className="px-3 py-3">{formatRetrievalScore(item.score)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                              {ragResult.structuredRecords.length > 20 ? (
                                <div className="mt-2 text-xs text-slate-400">
                                  当前仅展示前 20 条记录，导出 CSV 可获取当前命中的全部结构化记录。
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      ) : null}

                      <div className="rounded-2xl border border-gray-100 bg-white/85 p-4">
                        <div className="text-sm font-medium text-gray-800">来源列表</div>
                        <div className="mt-3 space-y-3 text-sm text-gray-600">
                          {typeof ragResult.structuredRecordCount === 'number' && ragResult.structuredRecordCount > 0 ? (
                            <div className="rounded-xl border border-fuchsia-100 bg-fuchsia-50/70 px-3 py-3 text-sm text-fuchsia-700">
                              当前命中结构化记录：{ragResult.structuredRecordCount}
                            </div>
                          ) : null}
                          {ragResult.sources && ragResult.sources.length > 0 ? ragResult.sources.map((source, index) => (
                            <div key={`source-${index}`} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
                              <div className="font-medium text-gray-800">{source.title || '未命名来源'}</div>
                              <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-400">
                                {source.sourceType ? <span>类型：{source.sourceType}</span> : null}
                                {source.credibility ? <span>可信度：{source.credibility}</span> : null}
                                {typeof source.citationCount === 'number' ? (
                                  <span>{source.sourceType === 'knowledge_record' ? '总命中记录' : '展示片段数'}：{source.citationCount}</span>
                                ) : null}
                                {typeof source.score === 'number' ? <span>综合分：{formatRetrievalScore(source.score)}</span> : null}
                                {typeof source.keywordScore === 'number' ? <span>关键词：{formatRetrievalScore(source.keywordScore)}</span> : null}
                                {typeof source.vectorScore === 'number' ? <span>向量：{formatRetrievalScore(source.vectorScore)}</span> : null}
                              </div>
                              {source.url ? <div className="mt-1 break-all text-xs text-blue-600">{source.url}</div> : null}
                              {source.record ? (
                                <div className="mt-2 grid gap-2 rounded-xl border border-fuchsia-100 bg-white px-3 py-3 text-xs text-slate-600 sm:grid-cols-2">
                                  {source.record.schoolName ? <div>学校：{source.record.schoolName}</div> : null}
                                  {source.record.studentName ? <div>姓名：{source.record.studentName}</div> : null}
                                  {source.record.subjectName ? <div>科目：{source.record.subjectName}</div> : null}
                                  {source.record.groupName ? <div>组别：{source.record.groupName}</div> : null}
                                  {source.record.award ? <div>奖项：{source.record.award}</div> : null}
                                  {typeof source.record.qualifiedForFinal !== 'undefined' || source.record.qualifiedForFinalLabel ? (
                                    <div>晋级：{source.record.qualifiedForFinalLabel || (source.record.qualifiedForFinal ? '是' : '否')}</div>
                                  ) : null}
                                </div>
                              ) : null}
                              {(source.snippet || source.summary) ? <div className="mt-2 text-sm text-gray-500">{source.snippet || source.summary}</div> : null}
                            </div>
                          )) : <div className="text-gray-400">暂无来源列表</div>}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-gray-100 bg-white/85 p-4">
                        <div className="text-sm font-medium text-gray-800">引用片段</div>
                        <div className="mt-3 space-y-3 text-sm text-gray-600">
                          {ragResult.citations && ragResult.citations.length > 0 ? ragResult.citations.map((citation, index) => (
                            <div key={`citation-${index}`} className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-3">
                              <div className="font-medium text-gray-800">{citation.sourceTitle || citation.sourceUrl || '未命名引用'}</div>
                              <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-emerald-700">
                                {citation.sourceId ? <span>片段：{citation.sourceId}</span> : null}
                                {citation.credibility ? <span>可信度：{citation.credibility}</span> : null}
                                {typeof citation.score === 'number' ? <span>综合分：{formatRetrievalScore(citation.score)}</span> : null}
                                {typeof citation.keywordScore === 'number' ? <span>关键词：{formatRetrievalScore(citation.keywordScore)}</span> : null}
                                {typeof citation.vectorScore === 'number' ? <span>向量：{formatRetrievalScore(citation.vectorScore)}</span> : null}
                              </div>
                              {citation.sourceUrl ? <div className="mt-1 break-all text-xs text-emerald-700">{citation.sourceUrl}</div> : null}
                              {citation.quote ? <div className="mt-2 text-sm text-gray-600">{citation.quote}</div> : null}
                            </div>
                          )) : <div className="text-gray-400">暂无引用片段</div>}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-gray-100 bg-slate-950 p-4 text-xs text-slate-100 shadow-sm">
                        <div className="mb-2 font-medium text-white">原始返回</div>
                        <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all leading-6">
                          {JSON.stringify(ragResult, null, 2)}
                        </pre>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="rounded-2xl border border-gray-100 bg-white/80 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-base font-semibold text-gray-900">文件列表</h2>
                    <p className="mt-1 text-sm text-gray-500">当前展示文件台账、解析状态与索引状态。</p>
                  </div>
                  <div className="flex items-center gap-3">
                    {selectedBaseId && files.length > 0 ? (
                      <button
                        onClick={() => void handleBatchRebuildIndex()}
                        disabled={batchRebuilding || submitting || loadingFiles}
                        className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {batchRebuilding ? <Loader2 size={16} className="animate-spin" /> : <RotateCcw size={16} />}
                        批量重建索引
                      </button>
                    ) : null}
                    {loadingBases || loadingFiles ? <Loader2 size={18} className="animate-spin text-blue-500" /> : null}
                  </div>
                </div>

                {error ? (
                  <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
                ) : null}

                {bases.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-gray-200 bg-white/70 px-6 py-10 text-center text-sm text-gray-500">
                    还没有知识库，请先创建一个。
                  </div>
                ) : files.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-gray-200 bg-white/70 px-6 py-10 text-center text-sm text-gray-500">
                    当前知识库还没有文件。
                  </div>
                ) : (
                  <div className="space-y-3">
                    {files.map((file) => (
                      <div key={file.id} className="rounded-2xl border border-gray-100 bg-white px-5 py-5 shadow-sm">
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-xl font-medium text-gray-900">{file.originalFilename}</div>
                            <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
                              <span className="rounded-full bg-blue-50 px-3 py-1.5 text-blue-600">{file.contentType || '未知类型'}</span>
                              <span className="rounded-full bg-gray-100 px-3 py-1.5">{formatKnowledgeFileSize(file.size)}</span>
                              <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-600">状态：{file.status}</span>
                              <span className="rounded-full bg-amber-50 px-3 py-1.5 text-amber-600">解析：{file.parseStatus}</span>
                              {file.indexStatus ? <span className="rounded-full bg-cyan-50 px-3 py-1.5 text-cyan-700">索引：{file.indexStatus}</span> : null}
                            </div>
                          </div>
                          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 self-start">
                            <button
                              onClick={() => void handleRetryParse(file.id)}
                              disabled={submitting || fileActionTarget === `parse:${file.id}` || fileActionTarget === `index:${file.id}`}
                              className="inline-flex items-center justify-center gap-1 rounded-lg border border-amber-200 px-3 py-2 text-sm font-medium text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {fileActionTarget === `parse:${file.id}` ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
                              重新解析
                            </button>
                            <button
                              onClick={() => void handleRetryIndex(file.id)}
                              disabled={submitting || file.parseStatus !== 'ready' || fileActionTarget === `parse:${file.id}` || fileActionTarget === `index:${file.id}`}
                              className="inline-flex items-center justify-center gap-1 rounded-lg border border-cyan-200 px-3 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {fileActionTarget === `index:${file.id}` ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
                              重试索引
                            </button>
                            <button
                              onClick={() => void handleDelete(file.id)}
                              disabled={submitting || fileActionTarget === `parse:${file.id}` || fileActionTarget === `index:${file.id}`}
                              className="inline-flex items-center justify-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-red-500 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              <Trash2 size={15} />
                              删除
                            </button>
                          </div>
                        </div>

                        {file.remark ? <div className="mt-3 text-sm text-gray-500">备注：{file.remark}</div> : null}
                        {file.parseError ? <div className="mt-3 text-sm text-red-500">解析失败：{file.parseError}</div> : null}
                        {file.indexError ? <div className="mt-3 text-sm text-red-500">索引失败：{file.indexError}</div> : null}
                        <div className="mt-3 text-sm text-gray-400">上传时间：{file.createdAt || '-'}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const NewChatView = ({
  onSearch,
  onHome,
  activeModel,
  setActiveModel,
  onGoLogin,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  onSelectHistory,
  activeHistory,
  setActiveHistory,
  isSendingMessage,
  setIsSendingMessage,
  uploadingVideo,
  setUploadingVideo,
  sessions,
  suggestedPrompts,
  currentUser,
  authLoading,
  onLogout,
  onRenameSession,
  onDeleteSession,
  knowledgeBases,
  selectedKnowledgeBaseId,
  onSelectKnowledgeBase,
  ttsAutoPlay,
  setTtsAutoPlay,
}: any) => {
  const [input, setInput] = useState('');
  const [toast, setToast] = useState('');
  const [showToolMenu, setShowToolMenu] = useState(false);
  const [selectedTool, setSelectedTool] = useState<'none' | 'report' | 'strategy' | 'structured' | 'overview' | 'rumor' | 'video' | 'debug'>('none');

  const handleModelSwitch = (model: string) => {
    setActiveModel(model);
    setToast(`已切换至 ${model} 模型`);
    setTimeout(() => setToast(''), 3000);
  };

  const toolConfigMap: Record<'report' | 'strategy' | 'structured' | 'overview' | 'rumor' | 'video' | 'debug', { label: string; placeholder: string; buildPrompt: (value: string) => string }> = {
    report: {
      label: '报告生成',
      placeholder: '输入事件或分析需求，系统将优先整理成正式报告...',
      buildPrompt: (value: string) => `请基于以下内容展开分析，并生成正式分析报告：\n${value}`,
    },
    strategy: {
      label: '策略生成',
      placeholder: '输入事件或任务目标，系统将优先产出策略动作清单...',
      buildPrompt: (value: string) => `请围绕以下内容先完成分析，再输出可执行的传播策略与动作清单：\n${value}`,
    },
    structured: {
      label: '结构化结果',
      placeholder: '输入名单、表格或统计类问题，系统将优先尝试结构化结果...',
      buildPrompt: (value: string) => `请优先按结构化结果方式回答以下问题，尽量返回可核对的字段和统计口径：\n${value}`,
    },
    overview: {
      label: '总览搜索',
      placeholder: '输入主题、主体或关键词，系统将优先做总览搜索与信息汇总...',
      buildPrompt: (value: string) => `请先进行总览搜索，汇总主题背景、传播现状、关键信息源和下一步建议：\n${value}`,
    },
    rumor: {
      label: '谣言分析',
      placeholder: '输入待核验说法或传播内容，系统将优先做谣言识别与核查...',
      buildPrompt: (value: string) => `请按谣言分析方式处理以下内容，重点区分已知事实、待核实信息、传播风险和澄清建议：\n${value}`,
    },
    video: {
      label: '多模态分析',
      placeholder: '支持同一轮最多上传 10 个文件，系统会优先基于当前会话最近的多模态分析结果回答...',
      buildPrompt: (value: string) => `请优先基于当前会话中最近上传并已完成分析的多模态结果回答；如果当前会话没有相关上下文，再明确说明缺少图片、音频、视频或文件内容信息。\n用户请求：${value}`,
    },
    debug: {
      label: 'Debug 模式',
      placeholder: '纯 LLM 对照链路：跳过搜索、grounding 和 RAG...',
      buildPrompt: (value: string) => value,
    },
  };

  const resolveNewChatPrompt = (value: string) => {
    const trimmedValue = value.trim();
    if (!trimmedValue) {
      return '';
    }
    if (selectedTool === 'none') {
      return trimmedValue;
    }
    return toolConfigMap[selectedTool].buildPrompt(trimmedValue);
  };

  const handleSubmitNewChat = (value: string) => {
    const trimmedValue = value.trim();
    if (!trimmedValue || isSendingMessage) {
      return;
    }
    console.log('[handleSubmitNewChat] selectedTool =', selectedTool, 'value =', trimmedValue?.slice(0, 30));
    // Pass original trimmedValue to handleSearch, NOT the buildPrompt result
    // For overview/rumor, handleSearch will apply buildPrompt internally
    onSearch(trimmedValue, selectedKnowledgeBaseId || undefined, selectedTool);
  };

  const newChatToolItems: ToolMenuItem[] = [
    {
      id: 'report',
      label: '报告生成',
      description: '首轮即按正式报告模式组织分析内容',
      icon: <FileText size={18} />,
      active: selectedTool === 'report',
      onClick: () => {
        setSelectedTool((current) => current === 'report' ? 'none' : 'report');
        setShowToolMenu(false);
      },
    },
    {
      id: 'strategy',
      label: '策略生成',
      description: '首轮即按策略规划模式组织任务目标',
      icon: <Radar size={18} />,
      active: selectedTool === 'strategy',
      onClick: () => {
        setSelectedTool((current) => current === 'strategy' ? 'none' : 'strategy');
        setShowToolMenu(false);
      },
    },
    {
      id: 'structured',
      label: '结构化结果',
      description: '适合名单、表格、统计类问题的首轮提问',
      icon: <LayoutDashboard size={18} />,
      active: selectedTool === 'structured',
      onClick: () => {
        setSelectedTool((current) => current === 'structured' ? 'none' : 'structured');
        setShowToolMenu(false);
      },
    },
    {
      id: 'overview',
      label: '总览搜索',
      description: '汇总主题背景、传播现状与关键信息源',
      icon: <Search size={18} />,
      active: selectedTool === 'overview',
      onClick: () => {
        setSelectedTool((current) => current === 'overview' ? 'none' : 'overview');
        setShowToolMenu(false);
      },
    },
    {
      id: 'rumor',
      label: '谣言分析',
      description: '优先做真伪辨析、风险判断与澄清建议',
      icon: <Shield size={18} />,
      active: selectedTool === 'rumor',
      onClick: () => {
        setSelectedTool((current) => current === 'rumor' ? 'none' : 'rumor');
        setShowToolMenu(false);
      },
    },
    {
      id: 'video',
      label: '多模态分析',
      description: '上传图片、音频或视频进行多模态舆情分析',
      icon: <Upload size={18} />,
      active: selectedTool === 'video',
      onClick: () => {
        setSelectedTool((current) => current === 'video' ? 'none' : 'video');
        setShowToolMenu(false);
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.accept = MULTIMODAL_ACCEPT;
        input.onchange = async (e) => {
          const selectedFiles = Array.from((e.target as HTMLInputElement).files || []);
          if (!selectedFiles.length) return;
          setShowToolMenu(false);
          const validationError = validateMultimodalFiles(selectedFiles);
          if (validationError) {
            alert(validationError);
            return;
          }
          const totalSize = selectedFiles.reduce((sum, file) => sum + file.size, 0);
          let sessionId = activeHistory;
          if (!sessionId) {
            const createdSession = await createAssistantSession();
            sessionId = createdSession.id;
            onSelectHistory(createdSession.id);
          }
          setUploadingVideo({
            names: selectedFiles.map((file) => file.name),
            size: totalSize,
            status: 'uploading',
            sessionId,
            fileCount: selectedFiles.length,
            processedCount: 0,
            failedCount: 0,
          });
          setIsSendingMessage(true);
          try {
            const taskStart = await uploadMultimodalAnalysis({ sessionId, files: selectedFiles });
            setUploadingVideo(prev => prev ? {
              ...prev,
              status: 'processing',
              taskId: taskStart.task_id,
              hint: '正在进行多模态分析',
              fileCount: Number(taskStart.file_count || prev.fileCount || selectedFiles.length),
            } : null);
            const taskResult = await waitForAssistantTaskCompletion(taskStart.task_id, {
              onProgress: (progress) => {
                setUploadingVideo((prev) => {
                  if (!prev || prev.taskId !== taskStart.task_id) return prev;
                  const fallbackLevel = Number(progress.result?.fallback_level || 0);
                  return {
                    ...prev,
                    status: 'processing',
                    fileCount: Number(progress.result?.file_count || prev.fileCount || selectedFiles.length),
                    processedCount: Number(progress.result?.processed_count || prev.processedCount || 0),
                    failedCount: Number(progress.result?.failed_count || prev.failedCount || 0),
                    currentFileName: String(progress.result?.current_file_name || prev.currentFileName || ''),
                    currentModality: String(progress.result?.current_modality || prev.currentModality || ''),
                    fallbackLevel,
                    finalModel: String(progress.result?.final_model || prev.finalModel || ''),
                    degradeReason: String(progress.result?.degrade_reason || prev.degradeReason || ''),
                    hint: String(
                      progress.result?.degrade_message
                      || (fallbackLevel > 0 ? '已自动切换分析通道，继续处理中' : '正在进行多模态分析')
                    ),
                  };
                });
              },
            });
            if (taskResult.status === 'failed') {
              throw new Error(resolveAssistantTaskErrorMessage(taskResult));
            }
            setUploadingVideo(prev => prev ? {
              ...prev,
              status: 'done',
              fileCount: Number(taskResult.result?.file_count || prev.fileCount || selectedFiles.length),
              processedCount: Number(taskResult.result?.processed_count || taskResult.result?.file_count || prev.fileCount || selectedFiles.length),
              failedCount: Number(taskResult.result?.failed_count || prev.failedCount || 0),
              fallbackLevel: Number(taskResult.result?.fallback_level || 0),
              finalModel: String(taskResult.result?.final_model || prev.finalModel || ''),
              degradeReason: String(taskResult.result?.degrade_reason || prev.degradeReason || ''),
              hint: Number(taskResult.result?.fallback_level || 0) > 0 ? '已自动降级完成' : '分析完成',
            } : null);
          } catch (err) {
            const msg = err instanceof Error ? err.message : '多模态分析失败';
            console.error('[multimodal upload]', msg);
            setUploadingVideo(prev => prev ? {
              ...prev,
              status: 'error',
              hint: msg,
              processedCount: prev.processedCount || 0,
            } : null);
          } finally {
            setIsSendingMessage(false);
          }
        };
        input.click();
      },
    },
    {
      id: 'debug',
      label: 'Debug 模式',
      description: '纯 LLM 对照链路：跳过搜索、grounding 和 RAG',
      icon: <Bug size={18} />,
      active: selectedTool === 'debug',
      onClick: () => {
        setSelectedTool((current) => current === 'debug' ? 'none' : 'debug');
        setShowToolMenu(false);
      },
    },
  ];

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden text-gray-800 relative pt-14">
      <BackgroundEffects />
      <Sidebar onHome={onHome} onNewChat={() => {}} isCollapsed={isSidebarCollapsed} setIsCollapsed={setIsSidebarCollapsed} showHomeButton={true} onSelectHistory={onSelectHistory} activeHistory={activeHistory} sessions={sessions} onRenameSession={onRenameSession} onDeleteSession={onDeleteSession} />

      <div className="flex-1 flex flex-col items-center px-4 pt-28 pb-12 relative overflow-y-auto scrollbar-hide">
        {/* Login Button */}
      <div className="absolute top-6 right-6 z-10">
        <AuthAction currentUser={currentUser} authLoading={authLoading} onGoLogin={onGoLogin} onLogout={onLogout} />
      </div>

      {/* Toast Notification */}
      {toast && (
        <div className="absolute top-10 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full border border-blue-200 bg-white px-6 py-2.5 text-sm text-gray-800 shadow-[0_10px_30px_rgba(59,130,246,0.12)] animate-in fade-in slide-in-from-top-4">
          <CheckCircle2 size={16} className="text-blue-500" />
          {toast}
        </div>
      )}

      <div className="flex flex-col items-center text-center mb-14 relative z-10">
        <h1 className="text-4xl font-bold tracking-wider mb-4 text-gray-800">
          开启 <span className="text-blue-600">深度舆情分析</span>
        </h1>
        <p className="text-gray-500 text-lg">输入事件关键词、URL或描述，为您生成全维度舆情报告</p>
      </div>

      <div className="w-full max-w-3xl relative z-10">
        <div className="flex gap-2 mb-2">
          <button 
            onClick={() => handleModelSwitch('万象智体')}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${activeModel === '万象智体' ? 'bg-blue-100 text-blue-600' : 'text-gray-500 hover:bg-gray-200'}`}
          >
            万象智体
          </button>
          <button 
            onClick={() => handleModelSwitch('DeepSeek (R1)')}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${activeModel === 'DeepSeek (R1)' ? 'bg-blue-100 text-blue-600' : 'text-gray-500 hover:bg-gray-200'}`}
          >
            DeepSeek (R1)
          </button>
        </div>
        {uploadingVideo && (
          (() => {
            const uploadMeta = describeMultimodalUpload(uploadingVideo);
            return (
          <div className={`mb-2 flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm ${
            uploadingVideo.status === 'error'
              ? 'bg-red-50 border border-red-200'
              : 'bg-gray-50 border border-gray-200'
          }`}>
            <Upload size={16} className={`flex-shrink-0 ${
              uploadingVideo.status === 'error' ? 'text-red-400' : 'text-gray-400'
            }`} />
            <div className="min-w-0 flex-1">
              <div className={`truncate font-medium ${
                uploadingVideo.status === 'error' ? 'text-red-700' : 'text-gray-700'
              }`}>{uploadMeta.title}</div>
              {uploadingVideo.hint ? (
                <div className={`mt-0.5 truncate text-xs ${
                  uploadingVideo.status === 'error' ? 'text-red-500' : 'text-slate-500'
                }`}>{uploadingVideo.hint}</div>
              ) : null}
            </div>
            <span className={`text-xs flex-shrink-0 ${
              uploadingVideo.status === 'error' ? 'text-red-300' : 'text-gray-400'
            }`}>
              {uploadMeta.sizeLabel}
            </span>
            <span className={`text-xs flex-shrink-0 ${
              uploadingVideo.status === 'error' ? 'text-red-300' : 'text-gray-400'
            }`}>
              {uploadMeta.countLabel}
            </span>
            <span className={
              uploadingVideo.status === 'uploading' ? 'text-blue-500' :
              uploadingVideo.status === 'processing' ? 'text-yellow-500' :
              uploadingVideo.status === 'done' ? 'text-green-500' : 'text-red-500'
            }>
              {uploadingVideo.status === 'uploading' ? '上传中...' :
               uploadingVideo.status === 'processing' ? '分析中...' :
               uploadingVideo.status === 'done' ? '完成' : '失败'}
            </span>
            <button onClick={() => setUploadingVideo(null)} className="text-gray-400 hover:text-gray-600">
              <X size={14} />
            </button>
          </div>
            );
          })()
        )}
        <div className="relative rounded-2xl p-[1px] bg-gray-200 focus-within:bg-gradient-to-r focus-within:from-blue-400 focus-within:to-indigo-500 transition-all duration-300 shadow-sm focus-within:shadow-md">
          <div className={`bg-white rounded-[15px] p-2 flex items-center w-full ${uploadingVideo ? 'h-24' : 'h-full'}`}>
            <div className="relative mr-1">
              <button
                ref={undefined}
                type="button"
                onClick={() => setShowToolMenu((current) => !current)}
                className={`flex h-10 w-10 items-center justify-center rounded-xl text-gray-400 transition-all hover:text-gray-600 ${
                  showToolMenu ? 'bg-gray-100 text-gray-500 shadow-inner' : 'hover:bg-gray-100'
                }`}
                title={showToolMenu ? '关闭工具箱' : '打开工具箱'}
              >
                <Plus size={18} className={`transition-transform duration-200 ease-out ${showToolMenu ? 'rotate-45' : 'rotate-0'}`} />
              </button>
              <ChatToolMenu
                open={showToolMenu}
                title="对话工具"
                items={newChatToolItems}
                onClose={() => setShowToolMenu(false)}
              />
            </div>
            {selectedTool !== 'none' ? (
              <div className="mr-2 flex items-center gap-1 rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-700">
                <span>{toolConfigMap[selectedTool].label}</span>
                <button
                  type="button"
                  onClick={() => setSelectedTool('none')}
                  className="inline-flex h-5 w-5 items-center justify-center rounded-full text-blue-500 hover:bg-blue-100 hover:text-blue-700"
                  title="清除当前工具"
                >
                  <X size={13} />
                </button>
              </div>
            ) : null}
            <button
              type="button"
              onClick={() => { console.log('[TTS toggle] before toggle, ttsAutoPlay=', ttsAutoPlay); setTtsAutoPlay((prev) => !prev); }}
              className={`mr-2 flex items-center gap-1 rounded-xl px-3 py-2 text-sm transition-colors ${
                ttsAutoPlay
                  ? 'bg-green-50 text-green-700'
                  : 'bg-gray-50 text-gray-500'
              }`}
              title="开启后，报告/策略生成完毕后将自动转为语音播报"
            >
              <Volume2 size={16} />
              <span>语音播报</span>
              <span className={`ml-1 text-xs font-medium ${ttsAutoPlay ? 'text-green-600' : 'text-gray-400'}`}>
                {ttsAutoPlay ? '开' : '关'}
              </span>
            </button>
            <KnowledgeBaseSelector
              value={selectedKnowledgeBaseId || ''}
              onChange={onSelectKnowledgeBase}
              knowledgeBases={knowledgeBases}
              className="w-[140px] sm:w-[180px] flex-shrink-0"
            />
            <input
              type="text"
              placeholder={selectedTool === 'none' ? '输入舆情事件关键词或分析需求...' : toolConfigMap[selectedTool].placeholder}
              className="flex-1 outline-none px-4 py-2 text-gray-700 bg-transparent"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmitNewChat(input)}
            />
            <button
              onClick={() => handleSubmitNewChat(input)}
              className={`p-2 rounded-xl transition-colors ${
                isSendingMessage
                  ? 'bg-blue-50 text-blue-300 cursor-not-allowed'
                  : input.trim()
                    ? 'bg-blue-500 text-white hover:bg-blue-600'
                    : 'bg-gray-100 text-gray-400'
              }`}
              disabled={isSendingMessage || !input.trim()}
            >
              <Send size={18} />
            </button>
          </div>
        </div>

        <div className="mt-10 grid grid-cols-1 sm:grid-cols-3 gap-3">
          {suggestedPrompts.map((suggestion: string, i: number) => (
            <button 
              key={i}
              onClick={() => handleSubmitNewChat(suggestion)}
              disabled={isSendingMessage}
              className={`px-4 py-3 border rounded-xl text-sm text-left transition-all ${
                isSendingMessage
                  ? 'bg-white/40 border-gray-100 text-gray-300 cursor-not-allowed'
                  : 'bg-white/50 hover:bg-white border-gray-100 text-gray-600 hover:shadow-sm hover:border-blue-200'
              }`}
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
      </div>
    </div>
  );
};


const ReportPanel = ({
  onClose,
  onExport,
  report,
  streamingTitle,
  streamingContent,
  isStreaming,
  isGeneratingReport,
}: {
  onClose: () => void;
  onExport?: () => void;
  report: AIReport | null;
  streamingTitle?: string | null;
  streamingContent?: Record<string, any> | string | null;
  isStreaming?: boolean;
  isGeneratingReport?: boolean;
}) => {
  const resolvedReport = report || buildFallbackPanelReport({
    title: streamingTitle,
    content: !isStreaming && !isGeneratingReport ? streamingContent : null,
  });
  const hasStreamingReport = Boolean(streamingTitle) && !resolvedReport;

  if (resolvedReport) {
    const isStructuredReport = isStructuredGeneratedReport(resolvedReport);
    const pieData = resolvedReport.content?.sourceDistribution ?? [];
    const timeline = resolvedReport.content?.timeline ?? [];
    const wordCloud = resolvedReport.content?.wordCloud ?? [];
    const executiveSummary = resolvedReport.content?.executiveSummary ?? {};
    const detailedAnalysis = resolvedReport.content?.detailedAnalysis ?? {};
    const insightsAndRecommendations = resolvedReport.content?.insightsAndRecommendations ?? {};
    const analysisDetails = resolvedReport.content?.analysisDetails ?? {};
    const rawDataSummary = resolvedReport.content?.rawDataSummary ?? {};
    const recommendations = normalizeReportObjectList(insightsAndRecommendations?.recommendations);
    const keyChallenges = normalizeReportObjectList(insightsAndRecommendations?.keyChallenges);
    const opportunities = normalizeReportObjectList(insightsAndRecommendations?.opportunities);
    const topTrends = normalizeReportObjectList(executiveSummary?.topTrends);
    const sentimentDetails = normalizeReportObjectList(detailedAnalysis?.sentimentAnalysis?.details);
    const emotionalFactors = normalizeReportObjectList(detailedAnalysis?.sentimentAnalysis?.emotionalFactors);
    const mainTopics = normalizeReportObjectList(detailedAnalysis?.topicAnalysis?.mainTopics);
    const propagationChannels = normalizeReportObjectList(detailedAnalysis?.propagationAnalysis?.channels);
    const peakEvents = normalizeReportObjectList(detailedAnalysis?.propagationAnalysis?.peakEvents);
    const methodologies = Array.isArray(analysisDetails?.methodologies)
      ? analysisDetails.methodologies.map((item: any) => String(item || '').trim()).filter(Boolean)
      : [];
    const limitations = Array.isArray(analysisDetails?.limitations)
      ? analysisDetails.limitations.map((item: any) => String(item || '').trim()).filter(Boolean)
      : [];
    const dataSources = normalizeReportObjectList(analysisDetails?.dataSources);
    const sampleData = normalizeReportObjectList(rawDataSummary?.sampleData);
    const riskAssessment = isPlainObject(insightsAndRecommendations?.riskAssessment)
      ? insightsAndRecommendations.riskAssessment
      : {};
    const potentialRisks = normalizeReportObjectList(riskAssessment?.potentialRisks);

    return (
      <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
        <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
          <span className="font-medium text-gray-800 truncate min-w-0 flex-1">{resolvedReport.title}</span>
          <div className="flex items-center gap-2 shrink-0">
            {onExport ? (
              <button onClick={onExport} className="flex items-center gap-1.5 text-blue-600 hover:text-blue-700 px-3 py-1.5 rounded-md hover:bg-blue-50 transition-colors whitespace-nowrap">
                <FileText size={16} />
                <span className="text-sm">导出</span>
              </button>
            ) : null}
            <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors whitespace-nowrap">
              <X size={16} />
              <span className="text-sm">收起</span>
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-6 space-y-8 scrollbar-hide">
          {isStructuredReport ? (
            <>
              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">一、执行摘要</h3>
                <div className="space-y-3 text-sm text-gray-700 leading-7">
                  {Array.isArray(executiveSummary.keyFindings) && executiveSummary.keyFindings.length > 0 ? (
                    <ul className="space-y-2 pl-5 list-disc marker:text-blue-500">
                      {executiveSummary.keyFindings.map((item: string) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-gray-500">暂无执行摘要。</p>
                  )}
                </div>
                {topTrends.length > 0 ? (
                  <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
                    <div className="text-sm font-semibold text-gray-800 mb-3">热门趋势</div>
                    <div className="space-y-3">
                      {topTrends.map((item, index) => (
                        <div key={`${item.name || item.title || 'trend'}-${index}`}>
                          <div className="flex items-center justify-between gap-3 text-sm text-gray-700">
                            <span className="font-medium text-gray-800">{renderReportValue(item.name || item.title, `趋势 ${index + 1}`)}</span>
                            <span className="text-xs text-gray-500">
                              热度 {renderScoreLike(item.value)} / 情绪 {renderReportValue(item.sentiment, '未标注')}
                            </span>
                          </div>
                          <div className="mt-2 h-2 rounded-full bg-white/80 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                String(item.sentiment || '').includes('负') ? 'bg-red-400' : String(item.sentiment || '').includes('正') ? 'bg-emerald-400' : 'bg-blue-500'
                              }`}
                              style={{ width: `${Math.max(8, Math.min(Number(item.value || 0) || 0, 100))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </section>

              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">二、总体判断</h3>
                <div className="space-y-2 text-sm text-gray-700 leading-7">
                  <p>情绪标签：{executiveSummary?.overallSentiment?.label ?? '未知'}</p>
                  <p>情绪分数：{renderScoreLike(executiveSummary?.overallSentiment?.score)}</p>
                  <p>
                    情绪分布：正面 {renderPercentLike(executiveSummary?.overallSentiment?.distribution?.positive)} / 中性 {renderPercentLike(executiveSummary?.overallSentiment?.distribution?.neutral)} / 负面 {renderPercentLike(executiveSummary?.overallSentiment?.distribution?.negative)}
                  </p>
                  <p>热度等级：{executiveSummary?.heatLevel ?? '未知'}</p>
                  <p>影响等级：{executiveSummary?.impactLevel ?? '未知'}</p>
                  {detailedAnalysis?.propagationAnalysis?.overview ? (
                    <p>{detailedAnalysis.propagationAnalysis.overview}</p>
                  ) : null}
                </div>

                <div className="mt-4 space-y-4">
                  {detailedAnalysis?.sentimentAnalysis?.overview ? (
                    <div className="rounded-2xl border border-gray-100 bg-gray-50/80 p-4">
                      <div className="text-sm font-semibold text-gray-800 mb-2">情绪分析</div>
                      <p className="text-sm text-gray-700 leading-7">{detailedAnalysis.sentimentAnalysis.overview}</p>
                    </div>
                  ) : null}

                  {sentimentDetails.length > 0 ? (
                    <div className="rounded-2xl border border-gray-100 bg-white p-4">
                      <div className="text-sm font-semibold text-gray-800 mb-3">情绪维度</div>
                      <div className="space-y-3">
                        {sentimentDetails.map((item, index) => (
                          <div key={`${item.dimension || 'dimension'}-${index}`} className="rounded-xl bg-gray-50/80 px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-sm font-medium text-gray-800">{renderReportValue(item.dimension, `维度 ${index + 1}`)}</span>
                              <span className="text-xs text-gray-500">得分 {renderScoreLike(item.score)}</span>
                            </div>
                            {item.description ? (
                              <p className="mt-2 text-sm text-gray-600 leading-6">{renderReportValue(item.description, '')}</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {emotionalFactors.length > 0 ? (
                    <div className="rounded-2xl border border-gray-100 bg-white p-4">
                      <div className="text-sm font-semibold text-gray-800 mb-3">情绪影响因素</div>
                      <ul className="space-y-3">
                        {emotionalFactors.map((item, index) => (
                          <li key={`${item.factor || 'factor'}-${index}`} className="rounded-xl bg-gray-50/80 px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-sm font-medium text-gray-800">{renderReportValue(item.factor, `因素 ${index + 1}`)}</span>
                              <span className={`text-xs font-medium ${Number(item.impact || 0) > 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                影响 {renderScoreLike(item.impact)}
                              </span>
                            </div>
                            {item.description ? (
                              <p className="mt-2 text-sm text-gray-600 leading-6">{renderReportValue(item.description, '')}</p>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {detailedAnalysis?.topicAnalysis?.overview ? (
                    <div className="rounded-2xl border border-gray-100 bg-gray-50/80 p-4">
                      <div className="text-sm font-semibold text-gray-800 mb-2">话题分析</div>
                      <p className="text-sm text-gray-700 leading-7">{detailedAnalysis.topicAnalysis.overview}</p>
                    </div>
                  ) : null}

                  {mainTopics.length > 0 ? (
                    <div className="space-y-3">
                      {mainTopics.map((item, index) => (
                        <div key={`${item.topic || 'topic'}-${index}`} className="rounded-2xl border border-gray-100 bg-white p-4">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-semibold text-gray-800">{renderReportValue(item.topic, `话题 ${index + 1}`)}</div>
                            <div className="text-xs text-gray-500">
                              权重 {renderScoreLike(item.weight)} / 声量 {renderScoreLike(item.sourceCount)}
                            </div>
                          </div>
                          <div className="mt-2 text-xs text-gray-500">情绪倾向：{renderReportValue(item.sentiment, '未标注')}</div>
                          {Array.isArray(item.relatedKeywords) && item.relatedKeywords.length > 0 ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {item.relatedKeywords.map((keyword: any, keywordIndex: number) => (
                                <span key={`${keyword}-${keywordIndex}`} className="rounded-full bg-blue-50 px-2.5 py-1 text-xs text-blue-700">
                                  {String(keyword)}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {propagationChannels.length > 0 ? (
                    <div className="rounded-2xl border border-gray-100 bg-white p-4">
                      <div className="text-sm font-semibold text-gray-800 mb-3">传播渠道</div>
                      <div className="space-y-3">
                        {propagationChannels.map((item, index) => (
                          <div key={`${item.name || 'channel'}-${index}`} className="rounded-xl bg-gray-50/80 px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-sm font-medium text-gray-800">{renderReportValue(item.name, `渠道 ${index + 1}`)}</span>
                              <span className="text-xs text-gray-500">
                                数量 {renderScoreLike(item.volume)} / 影响力 {renderScoreLike(item.influence)}/10
                              </span>
                            </div>
                            <div className="mt-2 text-xs text-gray-500">
                              正面 {renderPercentLike(item?.sentiment?.positive)} / 中性 {renderPercentLike(item?.sentiment?.neutral)} / 负面 {renderPercentLike(item?.sentiment?.negative)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {peakEvents.length > 0 ? (
                    <div className="rounded-2xl border border-gray-100 bg-white p-4">
                      <div className="text-sm font-semibold text-gray-800 mb-3">传播高峰事件</div>
                      <div className="space-y-3">
                        {peakEvents.map((item, index) => (
                          <div key={`${item.title || 'peak'}-${index}`} className="rounded-xl border border-gray-100 bg-gray-50/80 px-3 py-3">
                            <div className="text-sm font-medium text-gray-800">{renderReportValue(item.title || item.description, `峰值事件 ${index + 1}`)}</div>
                            <div className="mt-1 text-xs text-gray-500">
                              时间 {renderReportValue(item.timestamp)} / 影响度 {renderScoreLike(item.impact)}/10
                            </div>
                            {item.description ? (
                              <p className="mt-2 text-sm text-gray-600 leading-6">{renderReportValue(item.description, '')}</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </section>

              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">三、建议动作</h3>
                {Array.isArray(recommendations) && recommendations.length > 0 ? (
                  <ul className="space-y-3">
                    {recommendations.map((item: any, index: number) => (
                      <li key={`${item.title}-${index}`} className="rounded-xl border border-gray-100 bg-gray-50/80 p-4">
                        <div className="font-semibold text-gray-800">{item.title || `建议 ${index + 1}`}</div>
                        <div className="mt-1 text-xs text-gray-500">优先级：{item.priority || '未标注'} / 时段：{item.timeframe || '未标注'}</div>
                        <p className="mt-2 text-sm text-gray-700 leading-7">{item.description || '暂无详细描述。'}</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">暂无建议动作。</p>
                )}
              </section>

              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">四、关键挑战与机会</h3>
                <div className="space-y-4">
                  {keyChallenges.length > 0 ? (
                    <div>
                      <div className="text-sm font-semibold text-gray-800 mb-3">关键挑战</div>
                      <div className="space-y-3">
                        {keyChallenges.map((item, index) => (
                          <div key={`${item.challenge || item.title || 'challenge'}-${index}`} className="rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
                            <div className="text-sm font-semibold text-gray-800">{renderReportValue(item.challenge || item.title || item.description, `挑战 ${index + 1}`)}</div>
                            <div className="mt-1 text-xs text-amber-700">严重度：{renderScoreLike(item.severity)}</div>
                            {item.description ? (
                              <p className="mt-2 text-sm text-gray-700 leading-6">{renderReportValue(item.description, '')}</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {opportunities.length > 0 ? (
                    <div>
                      <div className="text-sm font-semibold text-gray-800 mb-3">机会点</div>
                      <div className="space-y-3">
                        {opportunities.map((item, index) => (
                          <div key={`${item.opportunity || item.title || 'opportunity'}-${index}`} className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4">
                            <div className="text-sm font-semibold text-gray-800">{renderReportValue(item.opportunity || item.title || item.description, `机会 ${index + 1}`)}</div>
                            <div className="mt-1 text-xs text-emerald-700">潜力：{renderScoreLike(item.potential)}</div>
                            {item.description ? (
                              <p className="mt-2 text-sm text-gray-700 leading-6">{renderReportValue(item.description, '')}</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {keyChallenges.length === 0 && opportunities.length === 0 ? (
                    <p className="text-sm text-gray-500">暂无关键挑战与机会点。</p>
                  ) : null}
                </div>
              </section>

              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">五、风险评估</h3>
                <div className="rounded-2xl border border-rose-100 bg-rose-50/70 p-4">
                  <div className="text-sm font-semibold text-gray-800">总体风险等级：{renderReportValue(riskAssessment.riskLevel, '未知')}</div>
                  {potentialRisks.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      {potentialRisks.map((item, index) => (
                        <div key={`${item.risk || 'risk'}-${index}`} className="rounded-xl border border-white/80 bg-white/80 px-3 py-3">
                          <div className="text-sm font-medium text-gray-800">{renderReportValue(item.risk, `风险 ${index + 1}`)}</div>
                          <div className="mt-1 text-xs text-gray-500">
                            概率 {renderPercentLike(item.probability)} / 影响 {renderPercentLike(item.impact)}
                          </div>
                          {item.mitigationStrategy ? (
                            <p className="mt-2 text-sm text-gray-700 leading-6">缓解策略：{renderReportValue(item.mitigationStrategy, '')}</p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-gray-500">暂无潜在风险明细。</p>
                  )}
                </div>
              </section>

              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">六、分析方法与数据摘要</h3>
                <div className="space-y-4">
                  {(methodologies.length > 0 || limitations.length > 0 || dataSources.length > 0) ? (
                    <div className="rounded-2xl border border-gray-100 bg-white p-4">
                      {methodologies.length > 0 ? (
                        <div>
                          <div className="text-sm font-semibold text-gray-800 mb-2">分析方法</div>
                          <ul className="space-y-2 pl-5 list-disc marker:text-blue-500 text-sm text-gray-700">
                            {methodologies.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}

                      {dataSources.length > 0 ? (
                        <div className={methodologies.length > 0 ? 'mt-4' : ''}>
                          <div className="text-sm font-semibold text-gray-800 mb-3">数据来源</div>
                          <div className="space-y-3">
                            {dataSources.map((item, index) => (
                              <div key={`${item.name || item.source || 'source'}-${index}`} className="rounded-xl bg-gray-50/80 px-3 py-3">
                                <div className="flex items-center justify-between gap-3">
                                  <span className="text-sm font-medium text-gray-800">{renderReportValue(item.name || item.source, `来源 ${index + 1}`)}</span>
                                  <span className="text-xs text-gray-500">{renderReportValue(item.type, '未标注')}</span>
                                </div>
                                <div className="mt-2 text-xs text-gray-500">
                                  可靠性 {renderPercentLike(item.reliability)} / 覆盖度 {renderPercentLike(item.coverage)}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      {limitations.length > 0 ? (
                        <div className={methodologies.length > 0 || dataSources.length > 0 ? 'mt-4' : ''}>
                          <div className="text-sm font-semibold text-gray-800 mb-2">分析局限性</div>
                          <ul className="space-y-2 pl-5 list-disc marker:text-amber-500 text-sm text-gray-700">
                            {limitations.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="rounded-2xl border border-gray-100 bg-gray-50/80 p-4">
                    <div className="text-sm font-semibold text-gray-800 mb-3">数据摘要</div>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="rounded-xl bg-white px-3 py-3">
                        <div className="text-lg font-semibold text-gray-800">{renderScoreLike(rawDataSummary.totalSources, '0')}</div>
                        <div className="mt-1 text-xs text-gray-500">数据来源总数</div>
                      </div>
                      <div className="rounded-xl bg-white px-3 py-3">
                        <div className="text-lg font-semibold text-gray-800">{renderScoreLike(rawDataSummary.totalMessages, '0')}</div>
                        <div className="mt-1 text-xs text-gray-500">消息总数</div>
                      </div>
                      <div className="rounded-xl bg-white px-3 py-3">
                        <div className="text-lg font-semibold text-gray-800">{sampleData.length}</div>
                        <div className="mt-1 text-xs text-gray-500">样本数量</div>
                      </div>
                    </div>

                    {sampleData.length > 0 ? (
                      <div className="mt-4 space-y-3">
                        {sampleData.slice(0, 5).map((item, index) => (
                          <div key={`${item.source || 'sample'}-${index}`} className="rounded-xl border border-white/80 bg-white/80 px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-sm font-medium text-gray-800">{renderReportValue(item.source, `样本 ${index + 1}`)}</span>
                              <span className="text-xs text-gray-500">{renderReportValue(item.sentiment, '未标注')}</span>
                            </div>
                            <div className="mt-1 text-xs text-gray-500">{renderReportValue(item.timestamp)}</div>
                            {item.content ? (
                              <p className="mt-2 text-sm text-gray-700 leading-6">{renderReportValue(item.content, '')}</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              </section>
            </>
          ) : (
            <>
              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">一、 事件概览</h3>
                <p className="text-sm text-gray-600 leading-relaxed">
                  {resolvedReport.content?.overview}
                </p>
              </section>

              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">二、 传播分析</h3>
                <h4 className="text-sm font-bold text-gray-700 mb-3">1. 事件脉络</h4>
                <div className="space-y-4 pl-2 border-l-2 border-blue-100 ml-2">
                  {timeline.map((item: any, i: number) => (
                    <div key={i} className="relative">
                      <div className="absolute -left-[13px] top-1 w-2 h-2 rounded-full border-2 border-blue-500 bg-white"></div>
                      <div className="pl-4">
                        <div className="text-xs text-blue-500 bg-blue-50 inline-block px-2 py-0.5 rounded mb-1">{item.date}</div>
                        <div className="text-sm text-gray-700 bg-gray-50 p-2 rounded border border-gray-100">
                          {item.text}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <h4 className="text-sm font-bold text-gray-700 mt-6 mb-2">2. 首发信息</h4>
                <p className="text-sm text-gray-600 leading-relaxed">
                  {resolvedReport.content?.firstSource}
                </p>

                <h4 className="text-sm font-bold text-gray-700 mt-6 mb-2">3. 传播概述</h4>
                <p className="text-sm text-gray-600 leading-relaxed">
                  {resolvedReport.content?.propagationOverview}
                </p>
              </section>

              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">三、 词云分析</h3>
                <div className="h-48 bg-gray-50 rounded-lg border border-gray-100 flex items-center justify-center relative overflow-hidden p-4">
                  {wordCloud.map((item: any) => (
                    <span
                      key={item.text}
                      className={`absolute ${item.size === 'xl' ? 'text-3xl' : item.size === 'lg' ? 'text-2xl' : item.size === 'md' ? 'text-xl' : item.size === 'sm' ? 'text-lg' : 'text-sm'} font-bold`}
                      style={{ top: item.top, left: item.left, color: item.color }}
                    >
                      {item.text}
                    </span>
                  ))}
                </div>
              </section>

              <section>
                <h3 className="text-lg font-bold text-gray-800 mb-3">四、 信源分布</h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={80}
                        paddingAngle={2}
                        dataKey="value"
                        stroke="none"
                      >
                        {pieData.map((entry: any, index: number) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    );
  }

  if (hasStreamingReport) {
    const statusLabel = isStreaming
      ? '万象智体正在生成'
      : isGeneratingReport
        ? '正式报告生成中'
        : '万象智体生成完毕';
    const statusClassName = isStreaming
      ? 'bg-blue-50 text-blue-600'
      : isGeneratingReport
        ? 'bg-amber-50 text-amber-600'
        : 'bg-emerald-50 text-emerald-600';

    return (
      <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
        <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
          <span className="font-medium text-gray-800 truncate min-w-0 flex-1">{streamingTitle}</span>
          <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors shrink-0 whitespace-nowrap">
            <X size={16} />
            <span className="text-sm">收起</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 scrollbar-hide">
          <div className="mb-4 flex items-center gap-2">
            <div className={`rounded-full px-3 py-1 text-sm font-medium ${statusClassName}`}>
              {statusLabel}
            </div>
          </div>
          <div className="space-y-4 text-sm leading-8 text-gray-700">
            <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
              <p className="text-sm text-gray-700">
                {isStreaming
                  ? '正在基于当前对话结果整理报告输入，并准备进入正式报告生成阶段。'
                  : isGeneratingReport
                    ? '聊天回复已经结束，系统正在调用正式报告生成模块，请稍候...'
                    : '当前会话暂无可展示的正式报告内容。'}
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
        <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
          <span className="font-medium text-gray-800 truncate min-w-0 flex-1">报告预览</span>
          <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors shrink-0 whitespace-nowrap">
            <X size={16} />
            <span className="text-sm">收起</span>
          </button>
        </div>
        <div className="flex-1 flex items-center justify-center p-8 text-sm text-gray-500">
          当前会话暂无报告。
        </div>
      </div>
    );
  }

};

const DataPanel = ({ onClose, dataPreview }: { onClose: () => void; dataPreview: AIDataPreviewItem[] }) => {
  return (
    <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
      <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
        <span className="font-medium text-gray-800 truncate min-w-0 flex-1">检索数据预览</span>
        <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors shrink-0 whitespace-nowrap">
          <X size={16} />
          <span className="text-sm">收起</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-hide">
        {dataPreview.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-gray-500">
            当前会话暂无数据预览。
          </div>
        ) : dataPreview.map((item) => (
          <div key={item.id} className="p-4 border border-gray-100 rounded-xl bg-gray-50/80">
            <div className="flex justify-between items-center mb-2 gap-3">
              <span className={`px-2 py-1 text-xs rounded font-medium ${item.sourceType === 'news' ? 'bg-blue-50 text-blue-600' : item.sourceType === 'social' ? 'bg-orange-50 text-orange-600' : 'bg-green-50 text-green-600'}`}>{sourceTypeLabelMap[item.sourceType]}</span>
              <span className="text-gray-400 text-xs">{item.publishedAt}</span>
            </div>
            <h3 className="font-bold text-gray-800 mb-2">{item.title}</h3>
            <p className="text-sm text-gray-600 line-clamp-3">{item.summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

const BriefPanel = ({ onClose, brief }: { onClose: () => void; brief: AIBrief | null }) => {
  if (!brief) {
    return (
      <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
        <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
          <span className="font-medium text-gray-800 truncate min-w-0 flex-1">事件简报</span>
          <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors shrink-0 whitespace-nowrap">
            <X size={16} />
            <span className="text-sm">收起</span>
          </button>
        </div>
        <div className="flex-1 flex items-center justify-center p-8 text-sm text-gray-500">
          当前会话暂无简报。
        </div>
      </div>
    );
  }
  return (
    <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
      <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
        <span className="font-medium text-gray-800 truncate min-w-0 flex-1">事件简报</span>
        <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors shrink-0 whitespace-nowrap">
          <X size={16} />
          <span className="text-sm">收起</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide">
        <div className="bg-blue-50 p-5 rounded-xl border border-blue-100">
          <h3 className="font-bold text-blue-900 mb-3 flex items-center gap-2"><FileText size={18}/> 核心摘要</h3>
          <p className="text-sm text-blue-800 leading-relaxed">
            {brief.summary}
          </p>
        </div>
        
        <div>
          <h3 className="font-bold text-gray-800 mb-4 border-l-4 border-blue-500 pl-3">关键信息点</h3>
          <ul className="space-y-3">
            {brief.highlights.map((highlight) => (
              <li key={highlight} className="flex items-start gap-3 text-sm text-gray-700">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0"></div>
                <p>{highlight}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};

const StrategyPanel = ({
  onClose,
  strategy,
  streamingTitle,
  isGeneratingStrategy = false,
}: {
  onClose: () => void;
  strategy: AIStrategy | null;
  streamingTitle?: string | null;
  isGeneratingStrategy?: boolean;
}) => {
  if (!strategy && isGeneratingStrategy) {
    return (
      <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
        <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
          <span className="font-medium text-gray-800 truncate min-w-0 flex-1">策略预览</span>
          <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors shrink-0 whitespace-nowrap">
            <X size={16} />
            <span className="text-sm">收起</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 scrollbar-hide">
          <div className="mb-4 flex items-center gap-2">
            <div className="rounded-full bg-amber-50 px-3 py-1 text-sm font-medium text-amber-600">
              万象智体正在生成策略
            </div>
          </div>
          <div className="space-y-4 text-sm leading-8 text-gray-700">
            <div className="rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
              <div className="mb-2 text-base font-semibold text-gray-900">
                {streamingTitle || '策略预览'}
              </div>
              <p className="text-sm text-amber-800">
                正在基于当前输入整理策略目标、阶段动作与监测指标，请稍候...
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!strategy) {
    return (
      <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
        <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
          <span className="font-medium text-gray-800 truncate min-w-0 flex-1">策略预览</span>
          <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors shrink-0 whitespace-nowrap">
            <X size={16} />
            <span className="text-sm">收起</span>
          </button>
        </div>
        <div className="flex-1 flex items-center justify-center p-8 text-sm text-gray-500">
          当前会话暂无策略。
        </div>
      </div>
    );
  }

  const content = strategy.content ?? {};
  const executiveSummary = content.executiveSummary ?? {};
  const audienceAndMessaging = content.audienceAndMessaging ?? {};
  const actionPlan = content.actionPlan ?? {};
  const risksAndGuardrails = content.risksAndGuardrails ?? {};
  const monitoringAndEvaluation = content.monitoringAndEvaluation ?? {};

  const primaryAudiences = normalizeReportObjectList(audienceAndMessaging.primaryAudiences);
  const keyMessages = normalizeReportObjectList(audienceAndMessaging.keyMessages);
  const immediateActions = normalizeReportObjectList(actionPlan.immediateActions);
  const shortTermActions = normalizeReportObjectList(actionPlan.shortTermActions);
  const midTermActions = normalizeReportObjectList(actionPlan.midTermActions);
  const longTermActions = normalizeReportObjectList(actionPlan.longTermActions);
  const keyRisks = normalizeReportObjectList(risksAndGuardrails.keyRisks);
  const indicators = normalizeReportObjectList(monitoringAndEvaluation.indicators);

  const renderActionList = (items: Array<Record<string, any>>, emptyText: string) => (
    items.length > 0 ? (
      <div className="space-y-3">
        {items.map((item, index) => (
          <div key={`${item.action || item.owner || 'action'}-${index}`} className="rounded-2xl border border-gray-100 bg-gray-50/70 px-4 py-3">
            <div className="font-medium text-gray-900">{item.action || '未命名动作'}</div>
            <div className="mt-1 text-sm text-gray-600">
              {[
                item.owner ? `负责人：${item.owner}` : null,
                item.timing ? `时点：${item.timing}` : null,
                item.objective ? `目标：${item.objective}` : null,
                item.deliverable ? `交付物：${item.deliverable}` : null,
              ].filter(Boolean).join('；')}
            </div>
          </div>
        ))}
      </div>
    ) : (
      <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50/40 px-4 py-4 text-sm text-gray-500">{emptyText}</div>
    )
  );

  return (
    <div className="w-[450px] bg-white border-l border-gray-100 flex flex-col shadow-xl z-10 flex-shrink-0 overflow-hidden animate-in slide-in-from-right duration-300 pt-14">
      <div className="h-14 border-b border-gray-100 bg-white flex items-center justify-between gap-3 px-6 flex-shrink-0">
        <span className="font-medium text-gray-800 truncate min-w-0 flex-1">{strategy.title || '策略预览'}</span>
        <button onClick={onClose} className="flex items-center gap-1.5 text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-md hover:bg-gray-100 transition-colors shrink-0 whitespace-nowrap">
          <X size={16} />
          <span className="text-sm">收起</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide">
        <div className="rounded-2xl border border-amber-100 bg-amber-50/60 px-5 py-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-amber-600">执行摘要</div>
          <div className="text-sm leading-7 text-amber-900">{executiveSummary.summary || '暂无执行摘要。'}</div>
          {Array.isArray(executiveSummary.priorityActions) && executiveSummary.priorityActions.length > 0 && (
            <div className="mt-3 space-y-2">
              {executiveSummary.priorityActions.map((item: string, index: number) => (
                <div key={`${item}-${index}`} className="text-sm text-amber-800">• {item}</div>
              ))}
            </div>
          )}
        </div>

        <div>
          <h3 className="font-bold text-gray-800 mb-4 border-l-4 border-amber-500 pl-3">受众与话术</h3>
          <div className="space-y-3">
            {primaryAudiences.map((item, index) => (
              <div key={`${item.audience || 'audience'}-${index}`} className="rounded-2xl border border-gray-100 bg-white px-4 py-3">
                <div className="font-medium text-gray-900">{item.audience || '未命名受众'}</div>
                <div className="mt-1 text-sm text-gray-600">
                  {[
                    item.concern ? `关切：${item.concern}` : null,
                    item.objective ? `目标：${item.objective}` : null,
                  ].filter(Boolean).join('；') || '暂无补充信息'}
                </div>
              </div>
            ))}
            {keyMessages.slice(0, 3).map((item, index) => (
              <div key={`${item.audience || 'message'}-${index}`} className="rounded-2xl border border-blue-100 bg-blue-50/60 px-4 py-3">
                <div className="text-sm font-medium text-blue-900">{item.audience || '通用受众'}</div>
                <div className="mt-1 text-sm leading-7 text-blue-800">{item.message || '暂无话术内容'}</div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h3 className="font-bold text-gray-800 mb-4 border-l-4 border-emerald-500 pl-3">阶段动作</h3>
          <div className="space-y-4">
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-gray-500">立即动作</div>
              {renderActionList(immediateActions, '暂无立即动作')}
            </div>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-gray-500">短期动作</div>
              {renderActionList(shortTermActions, '暂无短期动作')}
            </div>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-gray-500">中期动作</div>
              {renderActionList(midTermActions, '暂无中期动作')}
            </div>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-gray-500">长期动作</div>
              {renderActionList(longTermActions, '暂无长期动作')}
            </div>
          </div>
        </div>

        <div>
          <h3 className="font-bold text-gray-800 mb-4 border-l-4 border-rose-500 pl-3">风险与监测</h3>
          <div className="rounded-2xl border border-rose-100 bg-rose-50/60 px-4 py-3 text-sm text-rose-800">
            风险等级：{risksAndGuardrails.riskLevel || '未标注'}
          </div>
          <div className="mt-3 space-y-3">
            {keyRisks.map((item, index) => (
              <div key={`${item.risk || 'risk'}-${index}`} className="rounded-2xl border border-gray-100 bg-white px-4 py-3">
                <div className="font-medium text-gray-900">{item.risk || '未命名风险'}</div>
                <div className="mt-1 text-sm text-gray-600">
                  {[
                    item.probability !== undefined ? `概率：${item.probability}` : null,
                    item.impact !== undefined ? `影响：${item.impact}` : null,
                    item.mitigation ? `缓解：${item.mitigation}` : null,
                  ].filter(Boolean).join('；')}
                </div>
              </div>
            ))}
            {indicators.map((item, index) => (
              <div key={`${item.name || 'indicator'}-${index}`} className="rounded-2xl border border-emerald-100 bg-emerald-50/50 px-4 py-3">
                <div className="font-medium text-emerald-900">{item.name || '未命名指标'}</div>
                <div className="mt-1 text-sm text-emerald-800">
                  {[
                    item.target ? `目标：${item.target}` : null,
                    item.frequency ? `频率：${item.frequency}` : null,
                  ].filter(Boolean).join('；') || '暂无监测说明'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const ChatView = ({
  onHome,
  onNewChat,
  chatStep,
  setChatStep,
  activePanel,
  onShowPanel,
  activeModel,
  setActiveModel,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  onSelectHistory,
  activeHistory,
  sessions,
  messages,
  setMessages,
  panelData,
  isSessionLoading,
  isSendingMessage,
  setIsSendingMessage,
  onSendMessage,
  onRenameSession,
  onDeleteSession,
  anchorMessageId,
  input,
  onInputChange,
  onPauseGeneration,
  eventReportCard,
  isGeneratingReport,
  isGeneratingStrategy,
  knowledgeBases,
  selectedKnowledgeBaseId,
  onSelectKnowledgeBase,
  selectedTool: selectedToolProp,
  setSelectedTool: setSelectedToolProp,
  ttsAutoPlay: ttsAutoPlayProp,
  setTtsAutoPlay: setTtsAutoPlayProp,
  uploadingVideo,
  setUploadingVideo,
}: any) => {
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [showToolMenu, setShowToolMenu] = useState(false);
  const [activeToolPanel, setActiveToolPanel] = useState<'none' | 'structured'>('none');
  const [selectedTool, setSelectedTool] = useState<'none' | 'report' | 'strategy' | 'structured' | 'overview' | 'rumor' | 'video' | 'debug'>(selectedToolProp ?? 'none');
  const [activeRoundId, setActiveRoundId] = useState<string | null>(null);
  const [hoveredRoundId, setHoveredRoundId] = useState<string | null>(null);

  // Sync selectedTool from App component when it changes (e.g., after switching views)
  const lastSelectedToolPropRef = useRef(selectedToolProp);
  useEffect(() => {
    if (selectedToolProp !== undefined && selectedToolProp !== selectedTool && selectedToolProp !== lastSelectedToolPropRef.current) {
      setSelectedTool(selectedToolProp);
      lastSelectedToolPropRef.current = selectedToolProp;
    }
  }, [selectedToolProp]);

  // Sync selectedTool to App component when user changes it locally
  const lastSelectedToolRef = useRef(selectedTool);
  useEffect(() => {
    if (selectedTool !== lastSelectedToolRef.current && selectedToolProp !== selectedTool) {
      setSelectedToolProp(selectedTool);
      lastSelectedToolRef.current = selectedTool;
    }
  }, [selectedTool]);

  const [ttsAutoPlay, setTtsAutoPlay] = useState<boolean>(ttsAutoPlayProp ?? false);
  const lastTtsAutoPlayPropRef = useRef(ttsAutoPlayProp);
  useEffect(() => {
    if (ttsAutoPlayProp !== undefined && ttsAutoPlayProp !== ttsAutoPlay && ttsAutoPlayProp !== lastTtsAutoPlayPropRef.current) {
      setTtsAutoPlay(ttsAutoPlayProp);
      lastTtsAutoPlayPropRef.current = ttsAutoPlayProp;
    }
  }, [ttsAutoPlayProp]);

  const lastTtsAutoPlayRef = useRef(ttsAutoPlay);
  useEffect(() => {
    if (ttsAutoPlay !== lastTtsAutoPlayRef.current && ttsAutoPlayProp !== ttsAutoPlay) {
      setTtsAutoPlayProp(ttsAutoPlay);
      lastTtsAutoPlayRef.current = ttsAutoPlay;
    }
  }, [ttsAutoPlay]);

  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const audioRefs = useRef<Record<string, HTMLAudioElement | null>>({});
  const ttsPollingTaskIdsRef = useRef<Set<string>>(new Set());
  const playedTtsMessageIdsRef = useRef<Set<string>>(new Set());
  const previousTtsStateRef = useRef<Record<string, string>>({});
  const containerRef = useRef<HTMLDivElement | null>(null);
  const anchoredMessageIdRef = useRef<string | null>(null);

  const pollTtsTask = (taskId: string, sessionId: string, messageId: string) => {
    if (!taskId || ttsPollingTaskIdsRef.current.has(taskId)) {
      return;
    }
    ttsPollingTaskIdsRef.current.add(taskId);
    void (async () => {
      try {
        const result = await waitForAssistantTaskCompletion(taskId);
        const patch = buildTtsMessagePatchFromTaskResult(sessionId, taskId, messageId, result);
        if (!patch) {
          return;
        }
        setMessages((previous) => applyTtsMessagePatch(previous, patch));
      } catch (error) {
        const fallbackError = normalizeAssistantTtsErrorMessage(error instanceof Error ? error.message : '语音生成失败');
        setMessages((previous) => applyTtsMessagePatch(previous, {
          sessionId,
          messageId,
          ttsTaskId: taskId,
          ttsStatus: 'failed',
          ttsError: fallbackError,
        }));
      } finally {
        ttsPollingTaskIdsRef.current.delete(taskId);
      }
    })();
  };

  const startAsyncTtsForMessage = (message: ChatMessage | null | undefined) => {
    if (!message || message.role !== 'assistant') {
      return;
    }
    if (message.renderMode === 'hidden' || !String(message.content || '').trim()) {
      return;
    }
    if (message.audioUrl || message.ttsStatus === 'ready' || message.ttsStatus === 'processing' || message.ttsStatus === 'failed') {
      if (message.ttsStatus === 'processing' && message.ttsTaskId) {
        pollTtsTask(message.ttsTaskId, message.sessionId, message.id);
      }
      return;
    }

    setMessages((previous) => previous.map((item) => (
      item.id === message.id
        ? { ...item, ttsStatus: 'processing', ttsError: undefined }
        : item
    )));

    void (async () => {
      try {
        const task = await textToSpeechAsync({
          sessionId: message.sessionId,
          messageId: message.id,
          text: message.content,
        });
        setMessages((previous) => previous.map((item) => (
          item.id === message.id
            ? { ...item, ttsStatus: 'processing', ttsTaskId: task.task_id }
            : item
        )));
        pollTtsTask(task.task_id, message.sessionId, message.id);
      } catch (error) {
        const errorMessage = normalizeAssistantTtsErrorMessage(error instanceof Error ? error.message : '语音生成失败');
        setMessages((previous) => previous.map((item) => (
          item.id === message.id
            ? { ...item, ttsStatus: 'failed', ttsError: errorMessage }
            : item
        )));
      }
    })();
  };

  const startAsyncTtsForLatestAssistant = (sessionId: string, items: ChatMessage[]) => {
    if (!sessionId) {
      return;
    }
    const targetMessage = [...items].reverse().find((item) => (
      item.role === 'assistant' &&
      item.renderMode !== 'hidden' &&
      String(item.content || '').trim()
    )) ?? null;
    startAsyncTtsForMessage(targetMessage);
  };

  const sanitizedMessages = sanitizeMessages(messages);
  const visibleMessages = sanitizedMessages.slice(0, chatStep >= 2 ? sanitizedMessages.length : 2);
  const visibleMessageIds = useMemo(() => new Set(visibleMessages.map((message: ChatMessage) => message.id)), [visibleMessages]);
  const decoratedVisibleMessages = useMemo(
    () => attachSuggestedActionsToMessages(
      hydrateHistoricalStrategyCards(
        dedupeReportCardMessages(visibleMessages),
        sessions.find((item: ChatSession) => item.id === activeHistory)?.title,
      ),
      sessions.find((item: ChatSession) => item.id === activeHistory)?.title,
    ),
    [visibleMessages, sessions, activeHistory],
  );
  const conversationRounds = useMemo(
    () => decoratedVisibleMessages
      .filter((item: ChatMessage) => item.role === 'user')
      .map((item: ChatMessage, index: number) => ({
        uid: `${item.id}-${index}`,
        anchorId: item.id,
        order: index + 1,
        preview: String(item.content || '').replace(/\s+/g, ' ').trim().slice(0, 18) || `第 ${index + 1} 轮`,
      })),
    [decoratedVisibleMessages],
  );
  const latestAssistantMessage = [...decoratedVisibleMessages].reverse().find((item: ChatMessage) => item.role === 'assistant') ?? null;
  const latestStructuredMessage = [...decoratedVisibleMessages].reverse().find((item: ChatMessage) => (
    item.role === 'assistant' &&
    Array.isArray(item.structuredRecords) &&
    item.structuredRecords.length > 0
  )) ?? null;
  const hasStrategyWorkflow = decoratedVisibleMessages.some((item: ChatMessage) => item.renderMode === 'strategy_card' || item.messageType === 'strategy_plan');
  const activeEventReportMessage = eventReportCard?.assistantMessageId
    ? decoratedVisibleMessages.find((item: ChatMessage) => item.id === eventReportCard.assistantMessageId) ?? null
    : null;
  const activeStrategyMessage = [...decoratedVisibleMessages]
    .reverse()
    .find((item: ChatMessage) => item.renderMode === 'strategy_card' && item.strategyStatus === 'generating') ?? null;
  const analysisWorkflowTitle = eventReportCard?.title ?? '';
  const hasStructuredToolData = Boolean(latestStructuredMessage?.structuredRecords?.length);

  useEffect(() => {
    for (const message of messages) {
      if (message.role !== 'assistant' || message.renderMode === 'hidden') {
        continue;
      }
      if (message.ttsStatus === 'processing' && message.ttsTaskId) {
        pollTtsTask(message.ttsTaskId, message.sessionId, message.id);
      }
    }
  }, [messages]);

  useEffect(() => {
    if (!ttsAutoPlay) {
      return;
    }
    for (const message of messages) {
      const previousState = previousTtsStateRef.current[message.id];
      previousTtsStateRef.current[message.id] = `${message.ttsStatus || ''}|${message.audioUrl || ''}`;
      if (
        message.role === 'assistant'
        && message.audioUrl
        && message.ttsStatus === 'ready'
        && previousState !== `${message.ttsStatus || ''}|${message.audioUrl || ''}`
        && !playedTtsMessageIdsRef.current.has(message.id)
      ) {
        const audio = audioRefs.current[message.id];
        if (audio) {
          playedTtsMessageIdsRef.current.add(message.id);
          void audio.play().catch(() => {
            playedTtsMessageIdsRef.current.delete(message.id);
          });
        }
      }
    }
  }, [messages, ttsAutoPlay]);

  const toolConfigMap: Record<'report' | 'strategy' | 'structured' | 'overview' | 'rumor' | 'video' | 'debug', { label: string; placeholder: string; buildPrompt: (value: string) => string }> = {
    report: {
      label: '报告生成',
      placeholder: '输入事件或分析需求，系统将优先整理成正式报告...',
      buildPrompt: (value: string) => `请基于以下内容展开分析，并生成正式分析报告：\n${value}`,
    },
    strategy: {
      label: '策略生成',
      placeholder: '输入事件或任务目标，系统将优先产出策略动作清单...',
      buildPrompt: (value: string) => `请围绕以下内容先完成分析，再输出可执行的传播策略与动作清单：\n${value}`,
    },
    structured: {
      label: '结构化结果',
      placeholder: '输入名单、表格或统计类问题，系统将优先尝试结构化结果...',
      buildPrompt: (value: string) => `请优先按结构化结果方式回答以下问题，尽量返回可核对的字段和统计口径：\n${value}`,
    },
    overview: {
      label: '总览搜索',
      placeholder: '输入主题、主体或关键词，系统将优先做总览搜索与信息汇总...',
      buildPrompt: (value: string) => `请先进行总览搜索，汇总主题背景、传播现状、关键信息源和下一步建议：\n${value}`,
    },
    rumor: {
      label: '谣言分析',
      placeholder: '输入待核验说法或传播内容，系统将优先做谣言识别与核查...',
      buildPrompt: (value: string) => `请按谣言分析方式处理以下内容，重点区分已知事实、待核实信息、传播风险和澄清建议：\n${value}`,
    },
    video: {
      label: '多模态分析',
      placeholder: '支持同一轮最多上传 10 个文件，系统会优先基于当前会话最近的多模态分析结果回答...',
      buildPrompt: (value: string) => `请优先基于当前会话中最近上传并已完成分析的多模态结果回答；如果当前会话没有相关上下文，再明确说明缺少图片、音频、视频或文件内容信息。\n用户请求：${value}`,
    },
    debug: {
      label: 'Debug 模式',
      placeholder: '纯 LLM 对照链路：跳过搜索、grounding 和 RAG...',
      buildPrompt: (value: string) => value,
    },
  };

  const handleExportStructuredToolRecords = () => {
    const records = latestStructuredMessage?.structuredRecords || [];
    if (!records.length) {
      return;
    }
    const exported = exportStructuredRecordsToCsv(records, `structured-records-${activeHistory || 'chat-session'}.csv`);
    if (exported) {
      setShowToolMenu(false);
    }
  };

  const handleSelectTool = (toolId: string) => {
    setShowToolMenu(false);
    if (toolId === 'report') {
      setSelectedTool((current) => current === 'report' ? 'none' : 'report');
      return;
    }
    if (toolId === 'strategy') {
      setSelectedTool((current) => current === 'strategy' ? 'none' : 'strategy');
      return;
    }
    if (toolId === 'structured') {
      setSelectedTool((current) => current === 'structured' ? 'none' : 'structured');
      return;
    }
    if (toolId === 'overview') {
      setSelectedTool((current) => current === 'overview' ? 'none' : 'overview');
      return;
    }
    if (toolId === 'rumor') {
      setSelectedTool((current) => current === 'rumor' ? 'none' : 'rumor');
      return;
    }
    if (toolId === 'export_structured') {
      handleExportStructuredToolRecords();
    }
  };

  const toolItems: ToolMenuItem[] = [
    {
      id: 'report',
      label: '报告生成',
      description: '发送后按正式报告模式组织分析内容',
      icon: <FileText size={18} />,
      disabled: isSendingMessage,
      active: selectedTool === 'report',
      onClick: () => handleSelectTool('report'),
    },
    {
      id: 'strategy',
      label: '策略生成',
      description: '发送后按策略规划模式组织任务目标',
      icon: <Radar size={18} />,
      disabled: isSendingMessage,
      active: selectedTool === 'strategy',
      onClick: () => handleSelectTool('strategy'),
    },
    {
      id: 'structured',
      label: '结构化结果',
      description: '发送后优先以结构化记录与统计口径回答',
      icon: <LayoutDashboard size={18} />,
      disabled: isSendingMessage,
      active: selectedTool === 'structured',
      onClick: () => handleSelectTool('structured'),
    },
    {
      id: 'overview',
      label: '总览搜索',
      description: '发送后优先做总览搜索与背景梳理',
      icon: <Search size={18} />,
      disabled: isSendingMessage,
      active: selectedTool === 'overview',
      onClick: () => handleSelectTool('overview'),
    },
    {
      id: 'rumor',
      label: '谣言分析',
      description: '发送后优先做真伪核查与澄清建议',
      icon: <Shield size={18} />,
      disabled: isSendingMessage,
      active: selectedTool === 'rumor',
      onClick: () => handleSelectTool('rumor'),
    },
    {
      id: 'video',
      label: '多模态分析',
      description: '上传图片、音频或视频进行多模态舆情分析',
      icon: <Upload size={18} />,
      disabled: isSendingMessage,
      active: selectedTool === 'video',
      onClick: () => {
        setShowToolMenu(false);
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.accept = MULTIMODAL_ACCEPT;
        input.onchange = async (e) => {
          const selectedFiles = Array.from((e.target as HTMLInputElement).files || []);
          if (!selectedFiles.length) return;
          const validationError = validateMultimodalFiles(selectedFiles);
          if (validationError) {
            alert(validationError);
            return;
          }
          if (!activeHistory) {
            alert('请先选择或创建一个会话');
            return;
          }
          try {
            setUploadingVideo({
              names: selectedFiles.map((file) => file.name),
              size: selectedFiles.reduce((sum, file) => sum + file.size, 0),
              status: 'uploading',
              sessionId: activeHistory,
              fileCount: selectedFiles.length,
              processedCount: 0,
              failedCount: 0,
            });
            setIsSendingMessage(true);
            const taskStart = await uploadMultimodalAnalysis({ sessionId: activeHistory, files: selectedFiles });
            setUploadingVideo(prev => prev ? {
              ...prev,
              status: 'processing',
              taskId: taskStart.task_id,
              hint: '正在进行多模态分析',
              fileCount: Number(taskStart.file_count || prev.fileCount || selectedFiles.length),
            } : null);
            const taskResult = await waitForAssistantTaskCompletion(taskStart.task_id, {
              onProgress: (progress) => {
                setUploadingVideo((prev) => {
                  if (!prev || prev.taskId !== taskStart.task_id) return prev;
                  const fallbackLevel = Number(progress.result?.fallback_level || 0);
                  return {
                    ...prev,
                    status: 'processing',
                    fileCount: Number(progress.result?.file_count || prev.fileCount || selectedFiles.length),
                    processedCount: Number(progress.result?.processed_count || prev.processedCount || 0),
                    failedCount: Number(progress.result?.failed_count || prev.failedCount || 0),
                    currentFileName: String(progress.result?.current_file_name || prev.currentFileName || ''),
                    currentModality: String(progress.result?.current_modality || prev.currentModality || ''),
                    fallbackLevel,
                    finalModel: String(progress.result?.final_model || prev.finalModel || ''),
                    degradeReason: String(progress.result?.degrade_reason || prev.degradeReason || ''),
                    hint: String(
                      progress.result?.degrade_message
                      || (fallbackLevel > 0 ? '已自动切换分析通道，继续处理中' : '正在进行多模态分析')
                    ),
                  };
                });
              },
            });
            if (taskResult.status === 'failed') {
              throw new Error(resolveAssistantTaskErrorMessage(taskResult));
            }
            setUploadingVideo(prev => prev ? {
              ...prev,
              status: 'done',
              fileCount: Number(taskResult.result?.file_count || prev.fileCount || selectedFiles.length),
              processedCount: Number(taskResult.result?.processed_count || taskResult.result?.file_count || prev.fileCount || selectedFiles.length),
              failedCount: Number(taskResult.result?.failed_count || prev.failedCount || 0),
              fallbackLevel: Number(taskResult.result?.fallback_level || 0),
              finalModel: String(taskResult.result?.final_model || prev.finalModel || ''),
              degradeReason: String(taskResult.result?.degrade_reason || prev.degradeReason || ''),
              hint: Number(taskResult.result?.fallback_level || 0) > 0 ? '已自动降级完成' : '分析完成',
            } : null);
            // Reload messages for context (user can still see video info row)
            setTimeout(async () => {
              const msgs = await getAssistantMessages(activeHistory);
              if (msgs.length > 0) {
                setMessages(sanitizeMessages(msgs));
              }
            }, 2000);
          } catch (err) {
            const msg = err instanceof Error ? err.message : '多模态分析失败';
            console.error('[multimodal upload]', msg);
            setUploadingVideo(prev => prev ? { ...prev, status: 'error', hint: msg } : null);
            setTimeout(async () => {
              const msgs = await getAssistantMessages(activeHistory);
              if (msgs.length > 0) {
                setMessages(sanitizeMessages(msgs));
              }
            }, 1200);
          } finally {
            setIsSendingMessage(false);
          }
        };
        input.click();
      },
    },
    {
      id: 'export_structured',
      label: '导出 CSV',
      description: hasStructuredToolData ? '导出当前命中的结构化记录 CSV' : '需当前聊天命中结构化记录后可用',
      icon: <BookOpen size={18} />,
      disabled: !hasStructuredToolData,
      onClick: () => handleSelectTool('export_structured'),
    },
  ];

  const handleSubmit = () => {
    const trimmedValue = input.trim();
    if (!trimmedValue || isSendingMessage) {
      return;
    }
    const nextSelectedTool = selectedTool;
    console.log('[handleSubmit] forcedTool =', nextSelectedTool);
    const finalPrompt = selectedTool === 'none'
      ? trimmedValue
      : toolConfigMap[selectedTool].buildPrompt(trimmedValue);
    // NOTE: Do NOT reset selectedTool here - tool selection should persist until user explicitly deselects
    onSendMessage(finalPrompt, nextSelectedTool, trimmedValue);
    onInputChange('');
  };

  const clampScrollTarget = (target: HTMLElement, container: HTMLElement, offset = 12) => {
    const maxScrollTop = Math.max(0, container.scrollHeight - container.clientHeight);
    const rawTarget = target.offsetTop - offset;
    return Math.min(maxScrollTop, Math.max(0, rawTarget));
  };

  useLayoutEffect(() => {
    if (!anchorMessageId || !visibleMessageIds.has(anchorMessageId)) {
      return;
    }
    if (anchoredMessageIdRef.current === anchorMessageId) {
      return;
    }

    const target = messageRefs.current[anchorMessageId];
    if (!target) {
      return;
    }

    requestAnimationFrame(() => {
      const container = containerRef.current;
      if (!(container instanceof HTMLElement)) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }

      const nextScrollTop = clampScrollTarget(target, container, 16);
      container.scrollTo({
        top: nextScrollTop,
        behavior: 'smooth',
      });
      anchoredMessageIdRef.current = anchorMessageId;
    });
  }, [anchorMessageId, visibleMessageIds]);

  useEffect(() => {
    if (!anchorMessageId) {
      anchoredMessageIdRef.current = null;
    }
  }, [anchorMessageId]);

  useEffect(() => {
    anchoredMessageIdRef.current = null;
    setActiveRoundId(null);
    setHoveredRoundId(null);
    setShowToolMenu(false);
    setActiveToolPanel('none');
    // NOTE: Do NOT reset selectedTool here - it should persist across sessions
    messageRefs.current = {};

    const container = containerRef.current;
    if (container instanceof HTMLElement) {
      container.scrollTo({
        top: 0,
        behavior: 'auto',
      });
    }
  }, [activeHistory]);

  useEffect(() => {
    const container = containerRef.current;
    if (!(container instanceof HTMLElement)) {
      return;
    }

    const updateActiveRound = () => {
      if (!conversationRounds.length) {
        setActiveRoundId(null);
        return;
      }

      const containerTop = container.scrollTop;
      let nextActiveId = conversationRounds[0]?.uid ?? null;
      let smallestDistance = Number.POSITIVE_INFINITY;

      conversationRounds.forEach((round) => {
        const node = messageRefs.current[round.anchorId];
        if (!(node instanceof HTMLElement)) {
          return;
        }
        const distance = Math.abs(node.offsetTop - containerTop - 24);
        if (distance < smallestDistance) {
          smallestDistance = distance;
          nextActiveId = round.uid;
        }
      });

      setActiveRoundId(nextActiveId);
    };

    updateActiveRound();
    container.addEventListener('scroll', updateActiveRound, { passive: true });
    return () => {
      container.removeEventListener('scroll', updateActiveRound);
    };
  }, [conversationRounds]);

  const scrollToRound = (messageId: string) => {
    const container = containerRef.current;
    if (!(container instanceof HTMLElement)) {
      return;
    }
    const target =
      container.querySelector(`[data-user-anchor-id="${messageId}"]`) as HTMLElement | null
      || messageRefs.current[messageId];
    if (!(target instanceof HTMLElement)) {
      return;
    }
    container.scrollTo({
      top: clampScrollTarget(target, container, 16),
      behavior: 'smooth',
    });
    const matchedRound = conversationRounds.find((round) => round.anchorId === messageId);
    setActiveRoundId(matchedRound?.uid ?? messageId);
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden text-gray-800 relative pt-14">
      <BackgroundEffects />
      <Sidebar onHome={onHome} onNewChat={onNewChat} isCollapsed={isSidebarCollapsed} setIsCollapsed={setIsSidebarCollapsed} onSelectHistory={onSelectHistory} activeHistory={activeHistory} sessions={sessions} onRenameSession={onRenameSession} onDeleteSession={onDeleteSession} />

      <div className="flex-1 flex flex-col relative overflow-hidden z-10">
        <div className="h-14 border-b border-white/50 bg-white/40 backdrop-blur-md flex items-center px-6 justify-between flex-shrink-0">
           <div className="flex items-center gap-2">
             <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center text-blue-600"><Bot size={14}/></div>
             <span className="font-medium text-sm">AI 舆情助手</span>
           </div>
           <div className="flex items-center gap-3">
             {chatStep >= 1 && activeHistory && (
               <div className="bg-blue-50 text-blue-600 px-3 py-1 rounded-md text-sm font-medium">
                 {sessions.find((item: ChatSession) => item.id === activeHistory)?.title ?? '会话'}
               </div>
             )}
             <button
               onClick={() => setTtsAutoPlay((prev) => !prev)}
               className={`flex items-center gap-1 rounded-xl px-3 py-2 text-sm transition-colors ${
                 ttsAutoPlay ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-500'
               }`}
               title="开启后，报告/策略生成完毕后将自动转为语音播报"
             >
               <Volume2 size={16} />
               <span>语音播报</span>
               <span className={`ml-1 text-xs font-medium ${ttsAutoPlay ? 'text-green-600' : 'text-gray-400'}`}>
                 {ttsAutoPlay ? '开' : '关'}
               </span>
             </button>
           </div>
        </div>

        <div ref={containerRef} className="chat-scroll-container flex-1 overflow-y-scroll p-6 space-y-6 native-scrollbar force-scrollbar pr-10">
          {!activeHistory ? (
            <div className="h-full flex items-center justify-center">
              <div className="bg-white/80 border border-gray-100 rounded-2xl px-8 py-6 text-center shadow-sm">
                <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mx-auto mb-3">
                  <Bot size={18} />
                </div>
                <h3 className="text-base font-semibold text-gray-800 mb-1">暂无激活会话</h3>
                <p className="text-sm text-gray-500">请从左侧选择历史会话，或返回新建分析开始一条新的分析链路。</p>
              </div>
            </div>
          ) : isSessionLoading && visibleMessages.length === 0 && uploadingVideo?.sessionId !== activeHistory ? (
            <div className="h-full flex items-center justify-center">
              <div className="bg-white/80 border border-gray-100 rounded-2xl px-8 py-6 text-center shadow-sm">
                <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mx-auto mb-3">
                  <Loader2 size={18} className="animate-spin" />
                </div>
                <h3 className="text-base font-semibold text-gray-800 mb-1">正在加载会话内容</h3>
                <p className="text-sm text-gray-500">请稍候，正在同步消息与侧边面板数据。</p>
              </div>
            </div>
          ) : visibleMessages.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="bg-white/80 border border-gray-100 rounded-2xl px-8 py-6 text-center shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-1">
                  {uploadingVideo?.sessionId === activeHistory ? '多模态文件已关联到当前会话' : '当前会话暂无消息'}
                </h3>
                <p className="text-sm text-gray-500">
                  {uploadingVideo?.sessionId === activeHistory
                    ? '多模态分析会在后台完成并写入会话上下文，你可以直接在底部输入框继续提问。'
                    : '你可以直接在底部输入框继续发消息，或切换到其他历史会话。'}
                </p>
              </div>
            </div>
          ) : decoratedVisibleMessages.map((message: ChatMessage) =>
            message.renderMode === 'hidden' ? null :
            message.role === 'user' ? (
              <div
                key={message.id}
                ref={(node) => {
                  messageRefs.current[message.id] = node;
                }}
                data-user-anchor-id={message.id}
                className="flex justify-end animate-in fade-in slide-in-from-bottom-2"
              >
                <div className="bg-blue-100 text-blue-900 px-4 py-3 rounded-2xl rounded-tr-sm max-w-2xl text-sm">
                  <div className="whitespace-pre-wrap">{message.content}</div>
                </div>
              </div>
            ) : (
              (() => {
                const isReportCardMessage = message.renderMode === 'report_card';
                const isStrategyCardMessage = message.renderMode === 'strategy_card';
                const isReportCardPending = isReportCardMessage && (message.status === 'streaming' || message.reportStatus === 'generating');
                const isReportCardReady = isReportCardMessage && !isReportCardPending;
                const isStrategyCardPending = isStrategyCardMessage && (message.status === 'streaming' || message.strategyStatus === 'generating');
                const isStrategyCardReady = isStrategyCardMessage && !isStrategyCardPending;

                return (
              <div
                key={message.id}
                ref={(node) => {
                  messageRefs.current[message.id] = node;
                }}
                className="flex gap-4 max-w-3xl animate-in fade-in slide-in-from-bottom-2"
              >
                <AssistantAvatar isLoading={message.status === 'streaming' || message.reportStatus === 'generating'} />
                {isReportCardMessage ? (
                  <div className="flex-1 space-y-4">
                    <div className="rounded-[28px] border border-blue-100 bg-white shadow-[0_6px_8px_-5px_rgba(15,23,42,0.56)] p-7">
                    <EventReportPlaceholder
                      title={message.reportTitle || analysisWorkflowTitle}
                      isPending={isReportCardPending}
                      thinkingContent={message.content}
                    />
                    <AnalysisWorkflowCard
                      title={message.reportTitle || analysisWorkflowTitle}
                      panelData={panelData}
                      isSendingMessage={isSendingMessage}
                      isGeneratingReport={isGeneratingReport}
                      onShowPanel={onShowPanel}
                      isReportReady={isReportCardReady}
                    />
                    </div>
                    {isReportCardReady && latestAssistantMessage?.id === message.id && !hasStrategyWorkflow && (
                      <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 px-5 py-4 shadow-sm">
                        <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-emerald-500">
                          Todo
                        </div>
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                          <div className="text-sm leading-7 text-emerald-800">
                            报告已经生成完成。下一步建议进入“生成策略”，把分析结果扩展成可执行的传播策略与动作清单。
                          </div>
                          <button
                            className={`inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium transition-colors ${
                              isSendingMessage
                                ? 'cursor-not-allowed border-emerald-100 bg-white/70 text-emerald-300'
                                : 'border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-100/60'
                            }`}
                            onClick={() => {
                              if (isSendingMessage) {
                                return;
                              }
                              onSendMessage('请继续把这份分析扩展成可执行的传播策略与动作清单');
                            }}
                            disabled={isSendingMessage}
                          >
                            <span>请继续把这份分析扩展成可执行的传播策略与动作清单</span>
                            <ChevronRight size={16} />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ) : isStrategyCardMessage ? (
                  <div className="flex-1 rounded-[28px] border border-amber-100 bg-white shadow-[0_6px_8px_-5px_rgba(15,23,42,0.56)] p-7">
                    <StrategyPlanPlaceholder
                      title={message.strategyTitle || '传播策略'}
                      isPending={isStrategyCardPending}
                    />
                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 px-4 py-3">
                        <div className="text-xs text-slate-400 mb-1">策略任务</div>
                        <div className="text-sm font-medium text-slate-700">{isStrategyCardReady ? '已完成' : '生成中'}</div>
                      </div>
                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 px-4 py-3">
                        <div className="text-xs text-slate-400 mb-1">当前阶段</div>
                        <div className="text-sm font-medium text-slate-700">生成策略</div>
                      </div>
                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 px-4 py-3">
                        <div className="text-xs text-slate-400 mb-1">查看方式</div>
                        <div className="text-sm font-medium text-slate-700">右侧策略面板</div>
                      </div>
                    </div>
                    {isStrategyCardReady && panelData.strategy && (
                      <div className="mt-5 space-y-4">
                        <div className="rounded-2xl border border-amber-100 bg-amber-50/60 px-4 py-4">
                          <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-amber-600">策略摘要</div>
                          <div className="text-sm leading-7 text-amber-900">
                            {String(panelData.strategy.content?.executiveSummary?.summary || message.content || '策略已生成，可打开右侧面板查看。')}
                          </div>
                        </div>
                        {Array.isArray(panelData.strategy.content?.executiveSummary?.priorityActions) && panelData.strategy.content.executiveSummary.priorityActions.length > 0 && (
                          <div className="rounded-2xl border border-gray-100 bg-gray-50/70 px-4 py-4">
                            <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.18em] text-gray-500">优先动作</div>
                            <div className="space-y-2">
                              {panelData.strategy.content.executiveSummary.priorityActions.slice(0, 3).map((item: string, index: number) => (
                                <div key={`${item}-${index}`} className="text-sm text-gray-700">• {item}</div>
                              ))}
                            </div>
                          </div>
                        )}
                        <button
                          className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-white px-4 py-2 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-50"
                          onClick={() => onShowPanel('strategy')}
                        >
                          <span>查看完整策略</span>
                          <ChevronRight size={16} />
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="bg-white border border-gray-100 shadow-sm rounded-2xl p-5 flex-1">
                    {message.tagLabel && (
                      <div className="flex items-center text-blue-500 text-sm mb-3 bg-blue-50 w-fit px-3 py-1 rounded-full">
                        <CheckCircle2 size={14} className="mr-1" />
                        {`${activeModel}${message.tagLabel}`}
                      </div>
                    )}
                    <div className="text-gray-700 text-sm leading-relaxed space-y-4">
                      {message.thinking && (
                        <div className="bg-gray-50 p-4 rounded-xl border border-gray-100 text-xs text-gray-500">
                          <div className="whitespace-pre-wrap">{message.thinking}</div>
                        </div>
                      )}
                      <div className="space-y-4">
                        <AssistantMarkdownContent content={message.content} />
                      </div>
                      {message.ttsStatus === 'processing' && !message.audioUrl && (
                        <div className="mt-3 inline-flex items-center gap-2 rounded-xl bg-slate-50 px-4 py-2 text-sm text-slate-500">
                          <Loader2 size={16} className="animate-spin" />
                          <span>正在生成语音</span>
                        </div>
                      )}
                      {message.audioUrl && (
                        <audio
                          controls
                          src={message.audioUrl}
                          ref={(node) => {
                            audioRefs.current[message.id] = node;
                          }}
                          className="mt-3 w-full"
                          style={{ height: '40px' }}
                        />
                      )}
                      {message.ttsStatus === 'failed' && !message.audioUrl && (
                        <div className="mt-3 inline-flex items-center gap-2 rounded-xl bg-red-50 px-4 py-2 text-sm text-red-600">
                          <Volume2 size={16} />
                          <span>{message.ttsError || '语音生成失败'}</span>
                        </div>
                      )}
                      {message.riskLevel === 'high' && !message.audioUrl && (
                        <button
                          type="button"
                          className="mt-3 inline-flex items-center gap-2 rounded-xl bg-red-50 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100 transition-colors"
                          onClick={async () => {
                            if (!message.content) return;
                            try {
                              const ttsResult = await textToSpeech({
                                text: message.content,
                                sessionId: message.sessionId,
                              });
                              if (ttsResult?.audio_url) {
                                setMessages((prev) => prev.map((msg) =>
                                  msg.id === message.id ? { ...msg, audioUrl: ttsResult.audio_url } : msg
                                ));
                              }
                            } catch (ttsErr) {
                              console.warn('[rumor] TTS play failed:', ttsErr);
                            }
                          }}
                        >
                          <Volume2 size={16} />
                          播报预警
                        </button>
                      )}
                    </div>
                    {Boolean(
                      (typeof message.fallbackLevel === 'number' && message.fallbackLevel > 0)
                      || message.finalModel
                      || message.degradeReason
                    ) && (
                      <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/90 px-4 py-4">
                        <div className="flex flex-wrap gap-2 text-xs">
                          {typeof message.fallbackLevel === 'number' && message.fallbackLevel > 0 ? (
                            <span className="rounded-full bg-amber-50 px-3 py-1.5 text-amber-700">
                              已自动降级完成
                            </span>
                          ) : null}
                          {message.finalModel ? (
                            <span className="rounded-full bg-sky-50 px-3 py-1.5 text-sky-700">
                              模型：{message.finalModel}
                            </span>
                          ) : null}
                          {message.degradeReason ? (
                            <span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-600">
                              {multimodalDegradeLabelMap[message.degradeReason] || message.degradeReason}
                            </span>
                          ) : null}
                        </div>
                        {message.degradeMessage && typeof message.fallbackLevel === 'number' && message.fallbackLevel > 0 ? (
                          <div className="mt-3 text-xs leading-6 text-slate-500">{message.degradeMessage}</div>
                        ) : null}
                      </div>
                    )}
                    {Boolean(message.groundingStatus || message.citations?.length || message.sources?.length) && (
                      <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/90 px-4 py-4">
                        <div className="flex flex-wrap gap-2 text-xs">
                          {message.groundingStatus ? (
                            <span className="rounded-full bg-blue-50 px-3 py-1.5 text-blue-600">
                              {groundingLabelMap[message.groundingStatus] || message.groundingStatus}
                            </span>
                          ) : null}
                          {message.confidence ? (
                            <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-600">
                              可信度：{message.confidence}
                            </span>
                          ) : null}
                          {typeof message.usedRealtimeRetrieval === 'boolean' ? (
                            <span className="rounded-full bg-amber-50 px-3 py-1.5 text-amber-700">
                              实时检索：{message.usedRealtimeRetrieval ? '已启用' : '未启用'}
                            </span>
                          ) : null}
                        </div>

                        {message.facts && message.facts.length > 0 ? (
                          <div className="mt-3">
                            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">已知事实</div>
                            <div className="mt-2 space-y-2">
                              {message.facts.slice(0, 3).map((item, index) => (
                                <div key={`fact-${message.id}-${index}`} className="rounded-xl bg-white px-3 py-2 text-xs leading-6 text-slate-600">
                                  {item}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        {message.toVerify && message.toVerify.length > 0 ? (
                          <div className="mt-3">
                            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">待核实</div>
                            <div className="mt-2 space-y-2">
                              {message.toVerify.slice(0, 2).map((item, index) => (
                                <div key={`verify-${message.id}-${index}`} className="rounded-xl bg-amber-50 px-3 py-2 text-xs leading-6 text-amber-700">
                                  {item}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        {message.citations && message.citations.length > 0 ? (
                          <div className="mt-3">
                            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">来源引用</div>
                            <div className="mt-2 space-y-2">
                              {message.citations.slice(0, 3).map((item, index) => (
                                <div key={`citation-${message.id}-${index}`} className="rounded-xl border border-slate-100 bg-white px-3 py-3">
                                  <div className="text-xs font-medium text-slate-700">{item.title || item.sourceTitle || `来源 ${index + 1}`}</div>
                                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-400">
                                    {item.sourceId ? <span>片段：{item.sourceId}</span> : null}
                                    {item.credibility ? <span>可信度：{item.credibility}</span> : null}
                                    {typeof item.score === 'number' ? <span>综合分：{formatRetrievalScore(item.score)}</span> : null}
                                    {typeof item.keywordScore === 'number' ? <span>关键词：{formatRetrievalScore(item.keywordScore)}</span> : null}
                                    {typeof item.vectorScore === 'number' ? <span>向量：{formatRetrievalScore(item.vectorScore)}</span> : null}
                                  </div>
                                  {(item.url || item.sourceUrl) ? (
                                    <div className="mt-1 break-all text-[11px] text-blue-600">{item.url || item.sourceUrl}</div>
                                  ) : null}
                                  {item.publishedAt ? <div className="mt-1 text-[11px] text-slate-400">时间：{item.publishedAt}</div> : null}
                                  {item.credibility ? <div className="mt-1 text-[11px] text-slate-400">可信度：{item.credibility}</div> : null}
                                  {item.quote ? <div className="mt-2 text-xs leading-6 text-slate-600">{item.quote}</div> : null}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : message.sources && message.sources.length > 0 ? (
                          <div className="mt-3">
                            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">来源列表</div>
                            <div className="mt-2 space-y-2">
                              {message.sources.slice(0, 3).map((item, index) => (
                                <div key={`source-${message.id}-${index}`} className="rounded-xl border border-slate-100 bg-white px-3 py-3">
                                  <div className="text-xs font-medium text-slate-700">{item.title || `来源 ${index + 1}`}</div>
                                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-400">
                                    {item.sourceType ? (
                                      <span>类型：{sourceTypeLabelMap[item.sourceType as keyof typeof sourceTypeLabelMap] || item.sourceType}</span>
                                    ) : null}
                                    {item.credibility ? <span>可信度：{item.credibility}</span> : null}
                                    {typeof item.citationCount === 'number' ? (
                                      <span>{item.sourceType === 'knowledge_record' ? '总命中记录' : '展示片段数'}：{item.citationCount}</span>
                                    ) : null}
                                    {typeof item.score === 'number' ? <span>综合分：{formatRetrievalScore(item.score)}</span> : null}
                                  </div>
                                  {item.url ? <div className="mt-1 break-all text-[11px] text-blue-600">{item.url}</div> : null}
                                  {(item.snippet || item.summary) ? (
                                    <div className="mt-2 text-xs leading-6 text-slate-600">{item.snippet || item.summary}</div>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )}
                    {latestAssistantMessage?.id === message.id && message.suggestedAction && (
                      <button
                        className={`mt-5 inline-flex items-center gap-2 text-sm font-medium border rounded-xl px-4 py-2 transition-colors ${
                          isSendingMessage
                            ? 'cursor-not-allowed border-blue-100 bg-blue-50/60 text-blue-300'
                            : 'border-blue-200 text-blue-600 hover:bg-blue-50 hover:text-blue-700'
                        }`}
                        onClick={() => {
                          if (isSendingMessage) {
                            return;
                          }
                          onSendMessage(String(message.suggestedAction || ''));
                        }}
                        disabled={isSendingMessage}
                      >
                        <span>{message.suggestedAction}</span>
                        <ChevronRight size={16} />
                      </button>
                    )}
                    {chatStep === 1 && message.id === 'msg-002' && (
                      <button
                        className="mt-4 text-blue-600 text-sm flex items-center hover:underline font-medium"
                        onClick={() => setChatStep(2)}
                      >
                        我想对任泽经济开发区财政金融局局长杨某酒后闹事进行事件分析 <ChevronRight size={16} className="ml-1" />
                      </button>
                    )}
                  </div>
                )}
              </div>
                );
              })()
            ),
          )}
          <div className={isSendingMessage ? 'h-[48vh] shrink-0' : 'h-[28vh] shrink-0'} />
        </div>

        {activeHistory && conversationRounds.length > 1 && (
          <div className="pointer-events-none absolute right-6 top-24 bottom-24 hidden xl:flex items-center z-20">
            <div className="pointer-events-auto relative h-full w-8">
              <div className="relative z-10 flex h-full w-full flex-col items-center justify-center gap-2.5 py-2">
                {conversationRounds.map((round) => {
                  const isActive = activeRoundId === round.uid;
                  const isHovered = hoveredRoundId === round.uid;
                  return (
                    <div
                      key={round.uid}
                      className="relative flex w-full items-center justify-center"
                      onMouseEnter={() => setHoveredRoundId(round.uid)}
                      onMouseLeave={() => setHoveredRoundId((current) => (current === round.uid ? null : current))}
                    >
                      <button
                        type="button"
                        onClick={() => scrollToRound(round.anchorId)}
                        className="group flex h-4 w-full items-center justify-center"
                        aria-label={`跳转到第 ${round.order} 轮对话`}
                      >
                        <span className={`h-0.5 rounded-full transition-all ${
                          isActive
                            ? 'w-4 bg-blue-500'
                            : isHovered
                              ? 'w-3 bg-slate-900'
                              : 'w-2 bg-slate-300'
                        }`} />
                      </button>
                      {isHovered && (
                        <div className="absolute right-8 top-1/2 w-52 -translate-y-1/2 rounded-xl border border-white/80 bg-white/94 px-3 py-2 text-[12px] shadow-[0_12px_30px_rgba(15,23,42,0.08)] backdrop-blur-xl">
                          <div className={`leading-5 truncate ${
                            isActive ? 'text-blue-600 font-medium' : 'text-slate-900'
                          }`}>{round.preview}</div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="p-4 bg-white/40 backdrop-blur-md border-t border-white/50 flex-shrink-0">
          <div className="max-w-4xl mx-auto">
            {uploadingVideo ? (
              (() => {
                const uploadMeta = describeMultimodalUpload(uploadingVideo);
                return (
              <div className={`mb-2 flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm ${
                uploadingVideo.status === 'error'
                  ? 'bg-red-50 border border-red-200'
                  : 'bg-gray-50 border border-gray-200'
              }`}>
                <Upload size={16} className={`flex-shrink-0 ${
                  uploadingVideo.status === 'error' ? 'text-red-400' : 'text-gray-400'
                }`} />
                <div className="min-w-0 flex-1">
                  <div className={`truncate font-medium ${
                    uploadingVideo.status === 'error' ? 'text-red-700' : 'text-gray-700'
                  }`}>{uploadMeta.title}</div>
                  {uploadingVideo.hint ? (
                    <div className={`mt-0.5 truncate text-xs ${
                      uploadingVideo.status === 'error' ? 'text-red-500' : 'text-slate-500'
                    }`}>{uploadingVideo.hint}</div>
                  ) : null}
                </div>
                <span className={`text-xs flex-shrink-0 ${
                  uploadingVideo.status === 'error' ? 'text-red-300' : 'text-gray-400'
                }`}>
                  {uploadMeta.sizeLabel}
                </span>
                <span className={`text-xs flex-shrink-0 ${
                  uploadingVideo.status === 'error' ? 'text-red-300' : 'text-gray-400'
                }`}>
                  {uploadMeta.countLabel}
                </span>
                <span className={
                  uploadingVideo.status === 'uploading' ? 'text-blue-500' :
                  uploadingVideo.status === 'processing' ? 'text-yellow-500' :
                  uploadingVideo.status === 'done' ? 'text-green-500' : 'text-red-500'
                }>
                  {uploadingVideo.status === 'uploading' ? '上传中' :
                   uploadingVideo.status === 'processing' ? '分析中' :
                   uploadingVideo.status === 'done' ? '完成' : '失败'}
                </span>
                <button onClick={() => setUploadingVideo(null)} className="text-gray-400 hover:text-gray-600">
                  <X size={14} />
                </button>
              </div>
                );
              })()
            ) : null}
            <div className="relative rounded-2xl p-[1px] bg-white/50 focus-within:bg-gradient-to-r focus-within:from-blue-400 focus-within:to-indigo-500 transition-all duration-300 shadow-sm focus-within:shadow-md">
              {activeToolPanel === 'structured' && latestStructuredMessage?.structuredRecords?.length ? (
                <StructuredRecordsToolPanel
                  title="结构化结果工具"
                  records={latestStructuredMessage.structuredRecords}
                  aggregations={latestStructuredMessage.structuredAggregations}
                  onClose={() => setActiveToolPanel('none')}
                  onExport={handleExportStructuredToolRecords}
                />
              ) : null}
              <div className="bg-white/80 backdrop-blur-sm rounded-[15px] p-2 flex items-center w-full h-full">
                  <div className="relative mr-1">
                    <button
                  type="button"
                  onClick={() => {
                    if (activeToolPanel !== 'none') {
                      setActiveToolPanel('none');
                      return;
                    }
                    setShowToolMenu((current) => !current);
                  }}
                  className={`flex h-10 w-10 items-center justify-center rounded-xl text-gray-400 transition-all hover:text-gray-600 ${
                    (showToolMenu || activeToolPanel !== 'none') ? 'bg-gray-100 text-gray-500 shadow-inner' : 'hover:bg-gray-100'
                  }`}
                  title={showToolMenu || activeToolPanel !== 'none' ? '关闭工具箱' : '打开工具箱'}
                >
                  <Plus
                    size={18}
                    className={`transition-transform duration-200 ease-out ${(showToolMenu || activeToolPanel !== 'none') ? 'rotate-45' : 'rotate-0'}`}
                  />
                </button>
                <ChatToolMenu
                  open={showToolMenu}
                  title="对话工具"
                  items={toolItems}
                  onClose={() => setShowToolMenu(false)}
                />
              </div>
              {selectedTool !== 'none' ? (
                <div className="mr-2 flex items-center gap-1 rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-700">
                  <span>{toolConfigMap[selectedTool].label}</span>
                  <button
                    type="button"
                    onClick={() => setSelectedTool('none')}
                    className="inline-flex h-5 w-5 items-center justify-center rounded-full text-blue-500 hover:bg-blue-100 hover:text-blue-700"
                    title="清除当前工具"
                  >
                    <X size={13} />
                  </button>
                </div>
              ) : null}
              <div className="relative">
              <button 
                onClick={() => setShowModelMenu(!showModelMenu)}
                className="p-2 text-gray-400 hover:text-gray-600 flex items-center"
              >
                <span className="text-xs font-medium bg-gray-200 px-2 py-1 rounded flex items-center gap-1">
                  {activeModel} <ChevronUp size={12} />
                </span>
              </button>
              {showModelMenu && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowModelMenu(false)}></div>
                  <div className="absolute bottom-full left-0 mb-2 w-36 overflow-hidden rounded-xl border border-white/80 bg-white/95 py-1 shadow-[0_4px_6px_-4px_rgba(15,23,42,0.56)] backdrop-blur-xl z-50 animate-in fade-in slide-in-from-bottom-2">
                    <button onClick={() => { setActiveModel('万象智体'); setShowModelMenu(false); }} className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-100 ${activeModel === '万象智体' ? 'text-blue-600 font-medium' : 'text-gray-700'}`}>万象智体</button>
                    <button onClick={() => { setActiveModel('DeepSeek (R1)'); setShowModelMenu(false); }} className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-100 ${activeModel === 'DeepSeek (R1)' ? 'text-blue-600 font-medium' : 'text-gray-700'}`}>DeepSeek (R1)</button>
                  </div>
                </>
              )}
            </div>
            <KnowledgeBaseSelector
              value={selectedKnowledgeBaseId || ''}
              onChange={onSelectKnowledgeBase}
              knowledgeBases={knowledgeBases}
              className="w-[140px] sm:w-[180px] flex-shrink-0"
            />
            <input
              type="text"
              placeholder={selectedTool === 'none' ? `发消息给 ${activeModel}...` : toolConfigMap[selectedTool].placeholder}
              className="flex-1 bg-transparent outline-none px-2 py-2 text-gray-700 text-sm"
              value={input}
              onChange={e => onInputChange(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            />
            <button
              onClick={isSendingMessage ? onPauseGeneration : handleSubmit}
              className={`p-2 rounded-xl transition-colors ${
                isSendingMessage
                  ? 'bg-blue-50 text-blue-600 hover:bg-blue-100'
                  : input.trim()
                    ? 'bg-blue-500 text-white hover:bg-blue-600'
                    : 'bg-gray-100 text-gray-400'
              }`}
              disabled={!isSendingMessage && !input.trim()}
              title={isSendingMessage ? '暂停生成' : '发送消息'}
            >
              {isSendingMessage ? <PauseCircle size={16} /> : <Send size={16} />}
            </button>
            </div>
            </div>
          </div>
        </div>
      </div>

      {activePanel === 'report' && (
        <ReportPanel
          onClose={() => onShowPanel('none')}
          onExport={panelData.report ? () => {
            void exportAssistantReportPdf({
              reportId: panelData.report?.id ?? null,
              sessionId: activeHistory,
            }).catch(() => {});
          } : undefined}
          report={panelData.report}
          streamingTitle={eventReportCard ? analysisWorkflowTitle : null}
          streamingContent={eventReportCard?.content || activeEventReportMessage?.content || null}
          isStreaming={activeEventReportMessage?.status === 'streaming'}
          isGeneratingReport={Boolean(
            isGeneratingReport || activeEventReportMessage?.reportStatus === 'generating',
          )}
        />
      )}
      {activePanel === 'strategy' && (
        <StrategyPanel
          onClose={() => onShowPanel('none')}
          strategy={panelData.strategy}
          streamingTitle={activeStrategyMessage?.strategyTitle || null}
          isGeneratingStrategy={Boolean(
            isGeneratingStrategy || activeStrategyMessage?.strategyStatus === 'generating',
          )}
        />
      )}
      {activePanel === 'data' && <DataPanel onClose={() => onShowPanel('none')} dataPreview={panelData.dataPreview} />}
      {activePanel === 'brief' && <BriefPanel onClose={() => onShowPanel('none')} brief={panelData.brief} />}
    </div>
  );
};

const LoginView = ({
  onLogin,
  onGoRegister,
  authLoading,
  authError
}: {
  onLogin: (values: LoginForm) => void;
  onGoRegister: () => void;
  authLoading: boolean;
  authError: string;
}) => {
  const [showPwd, setShowPwd] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-5xl bg-white rounded-3xl shadow-2xl overflow-hidden flex min-h-[600px]">
        {/* Left Panel */}
        <div className="w-1/2 bg-gray-50 p-12 flex flex-col relative overflow-hidden">
          <div className="flex items-center gap-3 mb-16 z-10">
            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white">
              <Activity size={24} />
            </div>
            <span className="text-xl font-bold text-gray-800">Analytics AI</span>
          </div>
          <div className="z-10">
            <h1 className="text-5xl font-bold text-gray-900 mb-4 tracking-tight">万象智体</h1>
            <h2 className="text-4xl font-bold text-blue-600 mb-6 tracking-tight">你的多模态ai舆情分析助手</h2>
            <p className="text-gray-600 text-lg leading-relaxed mb-12">
              基于深度学习与大数据分析，为您提供实时、精准的舆情监控与智能洞察服务。
            </p>
            <div className="flex gap-4">
              <div className="flex items-center gap-2 bg-white px-4 py-2 rounded-full shadow-sm text-sm font-medium text-gray-700">
                <div className="w-2 h-2 bg-green-500 rounded-full"></div> 系统运行正常
              </div>
              <div className="flex items-center gap-2 bg-white px-4 py-2 rounded-full shadow-sm text-sm font-medium text-gray-700">
                <Shield size={16} className="text-blue-600" /> 企业级加密
              </div>
            </div>
          </div>
          {/* Decorative background */}
          <div className="absolute -bottom-20 -right-20 text-gray-200 opacity-50">
            <Share2 size={300} strokeWidth={1} />
          </div>
        </div>
        {/* Right Panel */}
        <div className="w-1/2 p-12 flex flex-col justify-center relative">
          <div className="max-w-md w-full mx-auto">
            <h2 className="text-3xl font-bold text-gray-900 mb-2">欢迎回来</h2>
            <p className="text-gray-500 mb-10">请输入您的凭据以访问控制面板</p>

            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">账号/邮箱</label>
                <div className="relative flex items-center">
                  <User size={20} className="absolute left-4 text-gray-400" />
                  <input value={email} onChange={(e) => setEmail(e.target.value)} type="text" placeholder="用户名或电子邮箱" className="w-full bg-gray-50 border border-transparent focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-200 rounded-xl py-3 pl-12 pr-4 outline-none transition-all" />
                </div>
              </div>
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="block text-sm font-medium text-gray-700">密码</label>
                  <a href="#" className="text-sm text-blue-600 hover:underline font-medium">忘记密码？</a>
                </div>
                <div className="relative flex items-center">
                  <Lock size={20} className="absolute left-4 text-gray-400" />
                  <input value={password} onChange={(e) => setPassword(e.target.value)} type={showPwd ? "text" : "password"} placeholder="请输入您的密码" className="w-full bg-gray-50 border border-transparent focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-200 rounded-xl py-3 pl-12 pr-12 outline-none transition-all" />
                  <button onClick={() => setShowPwd(!showPwd)} className="absolute right-4 text-gray-400 hover:text-gray-600">
                    {showPwd ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </div>
              </div>
              {authError && <div className="text-sm text-red-500">{authError}</div>}
              <div className="flex items-center">
                <input type="checkbox" id="remember" className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500" />
                <label htmlFor="remember" className="ml-2 text-sm text-gray-600">30天内自动登录</label>
              </div>
              <button onClick={() => onLogin({ email, password, type: 'account' })} disabled={authLoading} className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-70 text-white font-medium py-3.5 rounded-xl transition-colors flex items-center justify-center gap-2 shadow-lg shadow-blue-600/20">
                {authLoading ? '登录中...' : '登录系统'} <ArrowRight size={18} />
              </button>
            </div>

            <div className="mt-10 text-center text-sm text-gray-600">
              还没有账号？ <button onClick={onGoRegister} className="text-blue-600 font-bold hover:underline">立即注册</button>
            </div>
          </div>
          <div className="absolute bottom-6 left-0 right-0 text-center flex items-center justify-center gap-4 text-xs text-gray-400 font-medium tracking-widest uppercase">
            <div className="w-6 h-6 bg-gray-200 rounded flex items-center justify-center"><Activity size={12} /></div>
            SECURE AI POWERED
          </div>
        </div>
      </div>
    </div>
  );
};

const RegisterView = ({
  onRegister,
  onGoLogin,
  authLoading,
  authError,
}: {
  onRegister: (values: RegisterForm) => void;
  onGoLogin: () => void;
  authLoading: boolean;
  authError: string;
}) => {
  const [showPwd, setShowPwd] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-5xl bg-white rounded-3xl shadow-2xl overflow-hidden flex min-h-[600px]">
        {/* Left Panel */}
        <div className="w-1/2 bg-gray-50 p-12 flex flex-col relative overflow-hidden">
          <div className="z-10 mb-16">
            <h1 className="text-3xl font-bold text-gray-900 mb-1 tracking-tight">万象智体</h1>
            <h2 className="text-sm font-bold text-blue-600 tracking-widest uppercase">Analytics AI</h2>
          </div>
          
          <div className="z-10 space-y-6">
            <div className="bg-white p-6 rounded-2xl shadow-sm border-l-4 border-blue-600">
              <div className="text-blue-600 mb-4"><Share2 size={24} /></div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">全要素数据感知</h3>
              <p className="text-sm text-gray-500 leading-relaxed">融合多源异构数据，构建全方位舆情智能监测体系。</p>
            </div>
            <div className="bg-white/60 backdrop-blur-sm p-6 rounded-2xl border border-white">
              <div className="text-gray-700 mb-4"><LineChart size={24} /></div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">AI 深度洞察</h3>
              <p className="text-sm text-gray-500 leading-relaxed">利用先进自然语言处理技术，自动化提炼核心舆情趋势。</p>
            </div>
          </div>

          {/* Decorative background */}
          <div className="absolute bottom-0 left-0 right-0 h-64 bg-gradient-to-t from-gray-200/50 to-transparent"></div>
        </div>
        {/* Right Panel */}
        <div className="w-1/2 p-12 flex flex-col justify-center relative overflow-y-auto scrollbar-hide">
          <div className="max-w-md w-full mx-auto">
            <h2 className="text-3xl font-bold text-gray-900 mb-2">创建新账户</h2>
            <p className="text-gray-500 mb-8">欢迎加入全要素AI舆情分析平台</p>

            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">姓名 / 机构名称</label>
                <div className="relative flex items-center">
                  <User size={20} className="absolute left-4 text-gray-400" />
                  <input value={username} onChange={(e) => setUsername(e.target.value)} type="text" placeholder="请输入真实姓名或机构名" className="w-full bg-gray-50 border border-transparent focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-200 rounded-xl py-3 pl-12 pr-4 outline-none transition-all" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">电子邮箱</label>
                <div className="relative flex items-center">
                  <Mail size={20} className="absolute left-4 text-gray-400" />
                  <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="example@domain.com" className="w-full bg-gray-50 border border-transparent focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-200 rounded-xl py-3 pl-12 pr-4 outline-none transition-all" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">设置密码</label>
                <div className="relative flex items-center">
                  <Lock size={20} className="absolute left-4 text-gray-400" />
                  <input value={password} onChange={(e) => setPassword(e.target.value)} type={showPwd ? "text" : "password"} placeholder="至少8位字符" className="w-full bg-gray-50 border border-transparent focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-200 rounded-xl py-3 pl-12 pr-12 outline-none transition-all" />
                  <button onClick={() => setShowPwd(!showPwd)} className="absolute right-4 text-gray-400 hover:text-gray-600">
                    {showPwd ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">邀请码（可选）</label>
                <div className="relative flex items-center">
                  <ShieldCheck size={20} className="absolute left-4 text-gray-400" />
                  <input value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} type="text" placeholder="输入邀请码可注册管理员" className="w-full bg-gray-50 border border-transparent focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-200 rounded-xl py-3 pl-12 pr-4 outline-none transition-all" />
                </div>
              </div>
              {authError && <div className="text-sm text-red-500">{authError}</div>}
              <div className="flex items-start mt-2">
                <input type="checkbox" id="terms" className="mt-1 w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500" />
                <label htmlFor="terms" className="ml-2 text-xs text-gray-600 leading-relaxed">
                  我已阅读并同意 <a href="#" className="text-blue-600 hover:underline">《万象智体用户服务协议》</a> 与 <a href="#" className="text-blue-600 hover:underline">《隐私政策》</a>
                </label>
              </div>
              <button onClick={() => onRegister({ username, email, password, inviteCode })} disabled={authLoading} className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-70 text-white font-medium py-3.5 rounded-xl transition-colors mt-4 shadow-lg shadow-blue-600/20">
                {authLoading ? '注册中...' : '注册账户'}
              </button>
            </div>

            <div className="mt-6 text-center text-sm text-gray-600">
              已有账号？ <button onClick={onGoLogin} className="text-blue-600 font-bold hover:underline">返回登录</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default function App() {
  const initialRouteState = resolveRouteState(window.location.pathname);
  const initialCachedHomeData = readCachedHomeData();
  const [appState, setAppState] = useState<'home' | 'chat' | 'login' | 'register' | 'new_chat'>(initialRouteState.appState);
  const [chatStep, setChatStep] = useState(0);
  const [activePanel, setActivePanel] = useState<'none' | 'data' | 'brief' | 'report' | 'strategy'>('none');
  const [activeModel, setActiveModel] = useState(HOME_DEFAULT_MODEL);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const [activeHistory, setActiveHistory] = useState<string | null>(initialRouteState.sessionId);
  const [activeTab, setActiveTab] = useState(initialRouteState.activeTab);
  const [homeData, setHomeData] = useState<{ recommendationCards: AIRecommendationCard[]; defaultModel: string; suggestedPrompts: string[] }>(
    initialCachedHomeData || {
      recommendationCards: [],
      defaultModel: HOME_DEFAULT_MODEL,
      suggestedPrompts: [],
    },
  );
  const [isHomeLoading, setIsHomeLoading] = useState(false);
  const [homeLoadError, setHomeLoadError] = useState('');
  const [sessionsData, setSessionsData] = useState<{ sessions: ChatSession[]; activeSessionId: string | null }>({
    sessions: [],
    activeSessionId: null,
  });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [panelData, setPanelData] = useState(emptyPanels);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');
  const [isSessionLoading, setIsSessionLoading] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [isGeneratingStrategy, setIsGeneratingStrategy] = useState(false);
  const [pendingInitialSessionId, setPendingInitialSessionId] = useState<string | null>(null);
  const [anchorMessageId, setAnchorMessageId] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState('');
  const [draftKnowledgeBaseId, setDraftKnowledgeBaseId] = useState(ALL_KNOWLEDGE_BASE_OPTION_VALUE);
  const [sessionKnowledgeBindings, setSessionKnowledgeBindings] = useState<Record<string, string>>(readChatKnowledgeBindings);
  const [lastSubmittedInput, setLastSubmittedInput] = useState('');
  const [activeStreamController, setActiveStreamController] = useState<AbortController | null>(null);
  const sendMessageLockRef = useRef(false);
  const [eventReportCard, setEventReportCard] = useState<{
    sessionId: string;
    assistantMessageId: string;
    title: string;
    content: string | Record<string, any> | null;
    reportStatus?: 'idle' | 'generating' | 'ready';
  } | null>(null);
  const sessionLoadRequestIdRef = useRef(0);
  const debugSkipFetchRef = useRef<string | null>(null);
  const [isStreamingGuard, setIsStreamingGuard] = useState(false);
  const [selectedTool, setSelectedTool] = useState<'none' | 'report' | 'strategy' | 'structured' | 'overview' | 'rumor' | 'video' | 'debug'>('none');
  const [ttsAutoPlay, setTtsAutoPlay] = useState<boolean>(readTtsAutoPlay());
  useEffect(() => { writeTtsAutoPlay(ttsAutoPlay); }, [ttsAutoPlay]);
  const [uploadingVideo, setUploadingVideo] = useState<{
    names: string[];
    size: number;
    status: 'uploading' | 'processing' | 'done' | 'error';
    sessionId?: string;
    taskId?: string;
    hint?: string;
    fileCount: number;
    processedCount?: number;
    failedCount?: number;
    currentFileName?: string;
    currentModality?: string;
    fallbackLevel?: number;
    finalModel?: string;
    degradeReason?: string;
  } | null>(null);
  const isAuthenticated = Boolean(currentUser);
  const activeKnowledgeBaseId = activeHistory
    ? (sessionKnowledgeBindings[activeHistory] || ALL_KNOWLEDGE_BASE_OPTION_VALUE)
    : (draftKnowledgeBaseId || ALL_KNOWLEDGE_BASE_OPTION_VALUE);
  const ttsStartLockRef = useRef<Set<string>>(new Set());
  const latestMessagesRef = useRef<ChatMessage[]>([]);

  useEffect(() => {
    latestMessagesRef.current = messages;
  }, [messages]);

  const startAsyncTtsForMessage = (message: ChatMessage | null | undefined) => {
    if (!message || message.role !== 'assistant') {
      return;
    }
    if (message.renderMode === 'hidden' || !String(message.content || '').trim()) {
      return;
    }
    if (
      message.audioUrl
      || message.ttsStatus === 'ready'
      || message.ttsStatus === 'processing'
      || message.ttsStatus === 'failed'
      || ttsStartLockRef.current.has(message.id)
    ) {
      return;
    }

    ttsStartLockRef.current.add(message.id);
    setMessages((previous) => previous.map((item) => (
      item.id === message.id
        ? { ...item, ttsStatus: 'processing', ttsError: undefined }
        : item
    )));

    void (async () => {
      try {
        const task = await textToSpeechAsync({
          sessionId: message.sessionId,
          messageId: message.id,
          text: message.content,
        });
        setMessages((previous) => previous.map((item) => (
          item.id === message.id
            ? { ...item, ttsStatus: 'processing', ttsTaskId: task.task_id }
            : item
        )));
      } catch (error) {
        const errorMessage = normalizeAssistantTtsErrorMessage(error instanceof Error ? error.message : '语音生成失败');
        setMessages((previous) => previous.map((item) => (
          item.id === message.id
            ? { ...item, ttsStatus: 'failed', ttsError: errorMessage }
            : item
        )));
      } finally {
        ttsStartLockRef.current.delete(message.id);
      }
    })();
  };

  const startAsyncTtsForLatestAssistant = (sessionId: string, items: ChatMessage[]) => {
    if (!sessionId) {
      return;
    }
    const targetMessage = [...items].reverse().find((item) => (
      item.role === 'assistant'
      && item.renderMode !== 'hidden'
      && String(item.content || '').trim()
    )) ?? null;
    startAsyncTtsForMessage(targetMessage);
  };

  const loadHomeData = async ({ silent = false, refreshToken }: { silent?: boolean; refreshToken?: string } = {}) => {
    if (!silent) {
      setIsHomeLoading(true);
    }
    setHomeLoadError('');

    let lastError: unknown = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const home = await getAssistantHome({ refreshToken });
        setHomeData(home);
        setActiveModel(HOME_DEFAULT_MODEL);
        if (!refreshToken) {
          writeCachedHomeData({
            ...home,
            defaultModel: HOME_DEFAULT_MODEL,
          });
        }
        setHomeLoadError('');
        setIsHomeLoading(false);
        return;
      } catch (error) {
        lastError = error;
        if (attempt < 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 800));
        }
      }
    }

    setHomeData({
      recommendationCards: [],
      defaultModel: HOME_DEFAULT_MODEL,
      suggestedPrompts: [],
    });
    setHomeLoadError(lastError instanceof Error ? lastError.message : '首页推荐加载失败');
    setIsHomeLoading(false);
  };

  useEffect(() => {
    const handlePopState = () => {
      const routeState = resolveRouteState(window.location.pathname);
      setAppState(routeState.appState);
      setActiveTab(routeState.activeTab);
      if (routeState.appState === 'chat') {
        setActiveHistory(routeState.sessionId);
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    const nextPath = buildAppPath({
      appState,
      activeTab,
      activeHistory,
    });

    if (window.location.pathname !== nextPath) {
      window.history.pushState({}, '', nextPath);
    }
  }, [appState, activeTab, activeHistory]);

  useEffect(() => {
    const activeSessionTitle = sessionsData.sessions.find((item) => item.id === activeHistory)?.title ?? null;
    const moduleTitle = resolveModuleTitle({
      appState,
      activeTab,
      activeSessionTitle,
    });
    document.title = `${moduleTitle} - 万象智体`;
  }, [appState, activeTab, activeHistory, sessionsData.sessions]);

  useEffect(() => {
    const initializeApp = async () => {
      const cachedHome = readCachedHomeData();
      if (cachedHome && cachedHome.recommendationCards.length > 0) {
        setHomeData(cachedHome);
        setActiveModel(HOME_DEFAULT_MODEL);
      }

      setIsHomeLoading(true);

      const homePromise = loadHomeData({ silent: true });
      const userPromise = getCurrentUser()
        .then((user) => {
          setCurrentUser(user);
          setAuthError('');
        })
        .catch(() => {
          setCurrentUser(null);
        });

      await Promise.allSettled([homePromise, userPromise]);
    };

    void initializeApp();
  }, []);

  useEffect(() => {
    if (!currentUser) {
      setKnowledgeBases([]);
      setDraftKnowledgeBaseId(ALL_KNOWLEDGE_BASE_OPTION_VALUE);
      return;
    }

    getKnowledgeBases()
      .then((items) => {
        setKnowledgeBases(items);
        setSessionKnowledgeBindings((previous) => {
          const validIds = new Set(items.map((item) => item.id));
          const next: Record<string, string> = {};
          Object.entries(previous).forEach(([sessionId, boundKbId]) => {
            if (String(boundKbId) === ALL_KNOWLEDGE_BASE_OPTION_VALUE || validIds.has(String(boundKbId))) {
              next[sessionId] = String(boundKbId);
            }
          });
          writeChatKnowledgeBindings(next);
          return next;
        });
        setDraftKnowledgeBaseId((previous) => (
          previous === ALL_KNOWLEDGE_BASE_OPTION_VALUE || (previous && items.some((item) => item.id === previous))
            ? previous
            : ALL_KNOWLEDGE_BASE_OPTION_VALUE
        ));
      })
      .catch(() => {
        setKnowledgeBases([]);
      });
  }, [currentUser]);

  useEffect(() => {
    writeChatKnowledgeBindings(sessionKnowledgeBindings);
  }, [sessionKnowledgeBindings]);

  useEffect(() => {
    const loadSessionsData = async () => {
      if (runtimeConfig.dataSourceMode === 'api' && !currentUser) {
        setSessionsData({ sessions: [], activeSessionId: null });
        setActiveHistory(null);
        return;
      }
      try {
        const sessions = await getAssistantSessions();
        setSessionsData(sessions);
        setActiveHistory((previous) => {
          if (previous && sessions.sessions.some((item) => item.id === previous)) {
            return previous;
          }
          return sessions.activeSessionId;
        });
      } catch {
        setSessionsData({ sessions: [], activeSessionId: null });
      }
    };

    void loadSessionsData();
  }, [currentUser]);

  useEffect(() => {
    const loadSessionData = async () => {
      const requestId = ++sessionLoadRequestIdRef.current;
      const sessionTitle = sessionsData.sessions.find((item) => item.id === activeHistory)?.title;
      if (!activeHistory) {
        setMessages([]);
        setPanelData(emptyPanels);
        setIsSessionLoading(false);
        setEventReportCard(null);
        return;
      }
      if (runtimeConfig.dataSourceMode === 'api' && !currentUser) {
        setMessages([]);
        setPanelData(emptyPanels);
        setIsSessionLoading(false);
        setEventReportCard(null);
        return;
      }
      if (isStreamingGuard) {
        return;
      }
      if (pendingInitialSessionId && pendingInitialSessionId === activeHistory) {
        return;
      }
      // Skip fetch if debug mode set messages locally for this session
      if (debugSkipFetchRef.current === activeHistory) {
        debugSkipFetchRef.current = null;
        return;
      }
      setIsSessionLoading(true);
      setAuthError('');

      try {
        const [messagesResult, panelsResult] = await Promise.allSettled([
          getAssistantMessages(activeHistory),
          getAssistantPanels(activeHistory),
        ]);
        if (sessionLoadRequestIdRef.current !== requestId) {
          return;
        }
        const sessionMessages = messagesResult.status === 'fulfilled' ? messagesResult.value : [];
        console.log('[useEffect loadSessionData] fetched', sessionMessages.length, 'messages from backend for session', activeHistory);
        const nextPanels = panelsResult.status === 'fulfilled' ? panelsResult.value : emptyPanels;
        const hydrated = hydrateHistoricalReportCards(sanitizeMessages(sessionMessages), {
          panelReport: nextPanels.report,
          sessionTitle,
        });
        const hydratedMessages = hydrateHistoricalStrategyCards(hydrated.messages, sessionTitle);
        const mergedMessages = mergeTtsUiState(latestMessagesRef.current, hydratedMessages);
        console.log('[useEffect loadSessionData] backend audioUrl count=', mergedMessages.filter((m: ChatMessage) => m.audioUrl).length);
        setMessages(mergedMessages);
        setPanelData(nextPanels);
        setEventReportCard(hydrated.latestEventReportCard);
      } catch (error) {
        if (sessionLoadRequestIdRef.current !== requestId) {
          return;
        }
        setMessages([]);
        setPanelData(emptyPanels);
        setEventReportCard(null);
        setAuthError(error instanceof Error ? error.message : '加载会话失败');
      } finally {
        if (sessionLoadRequestIdRef.current === requestId) {
          setIsSessionLoading(false);
        }
      }
    };

    void loadSessionData();
  }, [activeHistory, currentUser, pendingInitialSessionId, sessionsData.sessions]);

  const handleSearch = async (
    val: string,
    knowledgeBaseId?: string,
    selectedTool?: 'none' | 'report' | 'strategy' | 'structured' | 'overview' | 'rumor' | 'video' | 'debug',
    recommendationContext?: {
      title: string;
      sourceUrl?: string;
      platformHint?: string;
      summary?: string;
      publishedAt?: string;
      sourceLabel?: string;
    } | null,
  ) => {
    const trimmedValue = val.trim();
    if (!trimmedValue) {
      return;
    }
    const resolvedKnowledgeBaseId = String(knowledgeBaseId || draftKnowledgeBaseId || '').trim();
    const resolvedRecommendationContext = recommendationContext || resolveRecommendationContextFromInput(trimmedValue, homeData.recommendationCards);

    if (runtimeConfig.dataSourceMode === 'api') {
      if (!isAuthenticated) {
        setAuthError('请先登录后再开始真实分析。');
        setAppState('login');
        return;
      }

      setAuthError('');
      // Persist selectedTool BEFORE switching to ChatView so ChatView gets correct value on first render
      console.log('[handleSearch] selectedTool =', selectedTool, 'trimmedValue =', trimmedValue?.slice(0, 30), 'ttsAutoPlay=', ttsAutoPlay);
      setSelectedTool(selectedTool || 'none');
      setAppState('chat');
      setChatStep(1);
      setActivePanel('none');
      setIsSidebarCollapsed(false);
      setIsSessionLoading(true);
      setIsSendingMessage(true);
      setChatInput('');
      setLastSubmittedInput(trimmedValue);
      setMessages([]);
      setPanelData(emptyPanels);
      setEventReportCard(null);

      let createdSessionId: string | null = null;
      let analyzeError = '';
      let wasAborted = false;
      // Abort any existing SSE stream before starting a new one
      if (activeStreamController) {
        activeStreamController.abort();
      }
      const streamController = new AbortController();
      setActiveStreamController(streamController);

      try {
        const createdSession = await createAssistantSession();
        createdSessionId = createdSession.id;
        if (resolvedKnowledgeBaseId) {
          setSessionKnowledgeBindings((previous) => ({
            ...previous,
            [createdSession.id]: resolvedKnowledgeBaseId,
          }));
        }
        const initialGeneratingMessages = createGeneratingMessages(createdSession.id, trimmedValue);
        // Create streamingAssistantMessage with matching ID for onChunk to work correctly
        const streamingAssistantMessage = selectedTool === 'debug'
          ? {
              ...createStreamingAssistantMessage(createdSession.id),
              content: DEBUG_STREAMING_PLACEHOLDER_TEXT,
              route: 'debug_llm_stream',
              debugMode: true,
            }
          : createStreamingAssistantMessage(createdSession.id);
        const streamingMessageId = streamingAssistantMessage.id;
        // Set pendingInitialSessionId BEFORE activeHistory to ensure useEffect skips loading
        setPendingInitialSessionId(createdSessionId);
        setActiveHistory(createdSessionId);
        setMessages([initialGeneratingMessages[0], streamingAssistantMessage]);
        setAnchorMessageId(initialGeneratingMessages[0]?.id ?? null);
        setIsStreamingGuard(true);

        // Handle overview, rumor, and debug tools specially
        if (selectedTool === 'overview' || selectedTool === 'rumor' || selectedTool === 'debug') {
          // Keep pendingInitialSessionId set during API call to prevent useEffect from overwriting messages
          // DO NOT call setSessionsData here - it would trigger useEffect
          console.log('[handleSearch] overview/rumor branch selectedTool =', selectedTool, 'createdSession.id =', createdSession.id);
          const userMsg: ChatMessage = {
            id: `${createdSession.id}-user-overview-${Date.now()}`,
            sessionId: createdSession.id,
            role: 'user',
            content: trimmedValue,
            createdAt: new Date().toISOString(),
            status: 'done',
          };

          try {
            if (selectedTool === 'overview') {
              console.log('[handleSearch] calling searchOverview API with sessionId =', createdSession.id, 'query =', trimmedValue);
              const overviewResult = await searchOverview({
                sessionId: createdSession.id,
                query: trimmedValue,
                maxResults: 10,
              });
              console.log('[handleSearch] searchOverview returned:', JSON.stringify(overviewResult)?.slice(0, 500));
              const overviewData = (overviewResult as any)?.data || overviewResult || {};
              console.log('[handleSearch] overviewData:', JSON.stringify(overviewData)?.slice(0, 500));
              const items: any[] = overviewData?.items || [];
              console.log('[handleSearch] items.length =', items.length);
              const summary: string = overviewData?.summary || '';
              let content: string;
              if (items.length > 0) {
                const itemList = items.map((item: any, i: number) => {
                  const title = item.title ? `[${i + 1}] ${item.title}` : '';
                  const url = item.url || '';
                  const src = item.source_name || item.platform || '';
                  const cred = item.credibility || 'medium';
                  const excerpt = item.content_excerpt || item.summary || '';
                  return `${title}\n来源: ${src} | 可信度: ${cred}${url ? `\n链接: ${url}` : ''}${excerpt ? `\n摘要: ${excerpt.slice(0, 200)}` : ''}`;
                }).join('\n\n');
                content = `【总览搜索结果】已检索到 ${items.length} 条相关信息：\n\n${itemList}\n\n---\n${summary}`;
              } else {
                content = summary || '未检索到有效结果，请换个关键词重试。';
              }
              console.log('[handleSearch] content length =', content.length);
              const assistantMsg: ChatMessage = {
                id: `${createdSession.id}-assistant-overview-${Date.now()}`,
                sessionId: createdSession.id,
                role: 'assistant',
                content,
                createdAt: new Date().toISOString(),
                status: 'done',
                groundingStatus: 'grounded',
                confidence: items.some((item: any) => item.credibility === 'high') ? 'high' : 'medium',
                usedRealtimeRetrieval: true,
              };
              console.log('[handleSearch] setting messages with [userMsg, assistantMsg]');
              setMessages([userMsg, assistantMsg]);
              // TTS is handled in the setTimeout below (after backend messages are fetched)
            } else if (selectedTool === 'rumor') {
              const rumorResult = await analyzeRumor({
                sessionId: createdSession.id,
                query: trimmedValue,
                maxResults: 8,
              });
              const rumorData = (rumorResult as any)?.data || rumorResult || {};
              const items: any[] = rumorData?.items || [];
              const summary: string = rumorData?.summary || '';
              let content: string;
              if (items.length > 0) {
                const itemList = items.map((item: any, i: number) => {
                  const title = item.title ? `[${i + 1}] ${item.title}` : '';
                  const url = item.url || '';
                  const src = item.source_name || item.platform || '';
                  const cred = item.credibility || 'medium';
                  const excerpt = item.content_excerpt || item.summary || '';
                  return `${title}\n来源: ${src} | 可信度: ${cred}${url ? `\n链接: ${url}` : ''}${excerpt ? `\n摘要: ${excerpt.slice(0, 200)}` : ''}`;
                }).join('\n\n');
                content = `【谣言分析结果】\n\n${itemList}\n\n---\n${summary}`;
              } else {
                content = summary || '未检索到有效结果，请换个关键词重试。';
              }
              const assistantMsg: ChatMessage = {
                id: `${createdSession.id}-assistant-rumor-${Date.now()}`,
                sessionId: createdSession.id,
                role: 'assistant',
                content,
                createdAt: new Date().toISOString(),
                status: 'done',
                groundingStatus: 'grounded',
                confidence: items.some((item: any) => item.credibility === 'high') ? 'high' : 'medium',
                usedRealtimeRetrieval: true,
                riskLevel: String(rumorData?.risk_level || 'medium'),
              };
              setMessages([userMsg, assistantMsg]);
            } else if (selectedTool === 'debug') {
              // Debug 模式：真实 LLM 流式输出
              setIsStreamingGuard(true);
              await streamAnalyze({
                mode: 'chat',
                sessionId: createdSession.id,
                message: trimmedValue,
                debugMode: true,
              }, {
                signal: streamController.signal,
                onChunk: (chunk) => {
                  setMessages((previous) => {
                    return previous.map((message, index) => {
                      if (index !== previous.length - 1 || message.role !== 'assistant') {
                        return message;
                      }
                      const nextContent = message.content === DEBUG_STREAMING_PLACEHOLDER_TEXT
                        ? chunk
                        : `${message.content}${chunk}`;
                      return {
                        ...message,
                        content: nextContent,
                        status: 'streaming',
                      };
                    });
                  });
                },
                onDone: () => {
                  setIsStreamingGuard(false);
                  setChatStep(3);
                },
                onError: (error, payload) => {
                  const displayError = normalizeStreamIssueMessage(error, payload);
                  console.error('[handleSearch] streamAnalyze failed:', displayError, payload);
                  setAuthError(displayError);
                  setIsStreamingGuard(false);
                },
              });
            }
          } catch (err) {
            console.error(`[${selectedTool}] search failed:`, err);
          }
          console.log('[handleSearch] completed, setting isSendingMessage=false, chatStep=3');
          setIsSendingMessage(false);
          setActiveStreamController(null);
          setChatStep(3); // Ensure messages are visible
          // Fetch backend messages and update sessions list (for overview/rumor)
          setTimeout(async () => {
            try {
              console.log('[handleSearch] fetching messages from backend for session', createdSession.id);
              const msgs = await getAssistantMessages(createdSession.id);
              console.log('[handleSearch] backend messages count:', msgs.length);
              if (msgs.length > 0) {
                setMessages(msgs);
                startAsyncTtsForLatestAssistant(createdSession.id, msgs);
              }
              // Update sessions list so new session appears in sidebar
              const sessionsResult = await getAssistantSessions();
              setSessionsData(sessionsResult);
              // Clear pendingInitialSessionId after all updates are done
              setPendingInitialSessionId(null);
            } catch (e) {
              console.error('[handleSearch] failed to fetch messages:', e);
              setPendingInitialSessionId(null);
            }
          }, 100);
          console.log('[handleSearch] returning, messages should now be visible');
          return;
        }

        if (selectedTool === 'report') {
          const userMsg: ChatMessage = {
            id: `${createdSession.id}-user-report-${Date.now()}`,
            sessionId: createdSession.id,
            role: 'user',
            content: trimmedValue,
            createdAt: new Date().toISOString(),
            status: 'done',
          };
          const reportTitle = `${trimmedValue}事件分析报告`;
          const reportCardMessage = createEventReportCardMessage({
            sessionId: createdSession.id,
            title: reportTitle,
            reportStatus: 'generating',
          });

          setMessages([userMsg, reportCardMessage]);
          setAnchorMessageId(userMsg.id);
          setActivePanel('report');
          setEventReportCard({
            sessionId: createdSession.id,
            assistantMessageId: reportCardMessage.id,
            title: reportTitle,
            content: '',
            reportStatus: 'generating',
          });
          setIsGeneratingReport(true);

          try {
            await saveAssistantSessionMessage({
              sessionId: createdSession.id,
              role: 'user',
              content: trimmedValue,
            });

            const reportResult = await generateAssistantReport(createdSession.id);
            const nextPanelData = buildPanelsFromGeneratedReport(reportResult);

            const [sessionsResult, messagesResult, panelsResult] = await Promise.allSettled([
              getAssistantSessions(),
              getAssistantMessages(createdSession.id),
              getAssistantPanels(createdSession.id),
            ]);

            if (sessionsResult.status === 'fulfilled') {
              setSessionsData(sessionsResult.value);
            }

            const resolvedPanels = panelsResult.status === 'fulfilled' && (panelsResult.value.report || panelsResult.value.strategy)
              ? panelsResult.value
              : nextPanelData;
            const hydrated = messagesResult.status === 'fulfilled'
              ? hydrateHistoricalReportCards(sanitizeMessages(messagesResult.value), {
                  panelReport: resolvedPanels.report,
                  sessionTitle: reportTitle,
                })
              : null;
            const nextMessages = hydrated?.messages?.length
              ? hydrateHistoricalStrategyCards(hydrated.messages, reportTitle)
              : [userMsg, {
                  ...reportCardMessage,
                  reportStatus: 'ready',
                  content: buildReportCardSummaryFromContent(reportResult.data),
                }];

            setActiveHistory(createdSession.id);
            setMessages(nextMessages);
            setPanelData(resolvedPanels);
            setActivePanel('report');
            setEventReportCard(
              hydrated?.latestEventReportCard
                ? {
                    ...hydrated.latestEventReportCard,
                    content: resolvedPanels.report?.content || reportResult.data,
                    reportStatus: 'ready',
                    reportId: resolvedPanels.report?.id || reportResult.reportId,
                  }
                : {
                    sessionId: createdSession.id,
                    assistantMessageId: reportCardMessage.id,
                    title: reportTitle,
                    content: resolvedPanels.report?.content || reportResult.data,
                    reportStatus: 'ready',
                    reportId: resolvedPanels.report?.id || reportResult.reportId,
                  },
            );
            setChatStep(3);
            setAuthError('');
          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : '报告生成失败';
            setMessages([
              userMsg,
              {
                ...reportCardMessage,
                status: 'error',
                reportStatus: 'idle',
                content: errorMessage,
              },
            ]);
            setPanelData(emptyPanels);
            setActivePanel('none');
            setAuthError(errorMessage);
          } finally {
            setIsGeneratingReport(false);
            setIsGeneratingStrategy(false);
            setPendingInitialSessionId(null);
            setIsStreamingGuard(false);
            setIsSessionLoading(false);
            setIsSendingMessage(false);
            setActiveStreamController(null);
          }
          return;
        }

        if (selectedTool === 'strategy') {
          const strategyTitle = `${resolveSuggestedAnalysisTarget({
            latestUserInput: trimmedValue,
            sessionTitle: trimmedValue,
          }) || trimmedValue || '当前事件'}传播策略`;
          const userMsg: ChatMessage = {
            id: `${createdSession.id}-user-strategy-${Date.now()}`,
            sessionId: createdSession.id,
            role: 'user',
            content: trimmedValue,
            createdAt: new Date().toISOString(),
            status: 'done',
          };
          const strategyCardMessage = createStrategyCardMessage({
            sessionId: createdSession.id,
            title: strategyTitle,
            strategyStatus: 'generating',
          });

          setMessages([userMsg, strategyCardMessage]);
          setAnchorMessageId(userMsg.id);
          setActivePanel('strategy');
          setIsGeneratingStrategy(true);

          try {
            await saveAssistantSessionMessage({
              sessionId: createdSession.id,
              role: 'user',
              content: trimmedValue,
            });

            const strategyPayload = buildStrategyPayload({
              panelData: emptyPanels,
              sessionTitle: trimmedValue,
              latestUserInput: trimmedValue,
            });
            const strategyStart = await generateAssistantStrategy({
              sessionId: createdSession.id,
              ...strategyPayload,
            });
            const taskResult = await waitForAssistantTaskCompletion(strategyStart.task_id);
            if (taskResult.status === 'failed' && shouldFallbackToSyncStrategy(taskResult.message)) {
              await generateAssistantStrategySync({
                sessionId: createdSession.id,
                ...strategyPayload,
              });
            } else if (taskResult.status === 'failed') {
              throw new Error(taskResult.message || '策略生成失败');
            }

            const [sessionsResult, messagesResult, panelsResult] = await Promise.allSettled([
              getAssistantSessions(),
              getAssistantMessages(createdSession.id),
              getAssistantPanels(createdSession.id),
            ]);

            if (sessionsResult.status === 'fulfilled') {
              setSessionsData(sessionsResult.value);
            }

            const nextPanels = panelsResult.status === 'fulfilled' ? panelsResult.value : emptyPanels;
            const nextMessagesFromBackend =
              messagesResult.status === 'fulfilled' ? messagesResult.value : null;
            const hydratedMessages = nextMessagesFromBackend?.length
              ? hydrateHistoricalReportCards(sanitizeMessages(nextMessagesFromBackend), {
                  panelReport: nextPanels.report,
                  sessionTitle: trimmedValue,
                })
              : null;

            setActiveHistory(createdSession.id);
            if (hydratedMessages?.messages?.length) {
              const nextMessages = hydrateHistoricalStrategyCards(hydratedMessages.messages, trimmedValue);
              setMessages(nextMessages);
              startAsyncTtsForLatestAssistant(createdSession.id, nextMessages);
            } else {
              setMessages([userMsg, { ...strategyCardMessage, strategyStatus: 'ready', status: 'done' }]);
            }
            setPanelData(nextPanels);
            setActivePanel(nextPanels.strategy ? 'strategy' : 'none');
            setChatStep(3);
            setAuthError('');
          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : '策略生成失败';
            setMessages([
              userMsg,
              {
                ...strategyCardMessage,
                status: 'error',
                strategyStatus: 'idle',
                content: errorMessage,
              },
            ]);
            setPanelData(emptyPanels);
            setActivePanel('none');
            setAuthError(errorMessage);
          } finally {
            setIsGeneratingStrategy(false);
            setPendingInitialSessionId(null);
            setIsStreamingGuard(false);
            setIsSessionLoading(false);
            setIsSendingMessage(false);
            setActiveStreamController(null);
          }
          return;
        }

        let streamWarningMessage = '';
        let streamResult: { status: 'complete' | 'partial_complete'; warning?: string | null } | null = null;
        try {
          streamResult = await streamAnalyze({
            mode: 'chat',
            sessionId: createdSession.id,
            message: trimmedValue,
            kbId: resolvedKnowledgeBaseId || undefined,
            recommendationContext: resolvedRecommendationContext || undefined,
          }, {
            signal: streamController.signal,
            onGrounding: (payload) => {
              setMessages((previous) => previous.map((message, index) => {
                if (index !== previous.length - 1 || message.role !== 'assistant') {
                  return message;
                }
                return mergeStreamPayloadMeta({
                  ...message,
                  groundingStatus: String(payload?.groundingStatus || ''),
                  confidence: String(payload?.confidence || ''),
                  usedRealtimeRetrieval: Boolean(payload?.usedRealtimeRetrieval),
                  structuredRecordCount: Number(payload?.structuredRecordCount || 0),
                  structuredAggregations: payload?.structuredAggregations || {},
                  structuredRecords: Array.isArray(payload?.structuredRecords) ? payload.structuredRecords : [],
                  sources: Array.isArray(payload?.sources) ? payload.sources : [],
                  citations: Array.isArray(payload?.citations) ? payload.citations : [],
                  facts: Array.isArray(payload?.facts) ? payload.facts : [],
                  toVerify: Array.isArray(payload?.toVerify) ? payload.toVerify : [],
                  analysis: Array.isArray(payload?.analysis) ? payload.analysis : [],
                }, payload);
              }));
            },
            onWarning: (warning, payload) => {
              streamWarningMessage = normalizeStreamIssueMessage(warning, payload);
            },
            onChunk: (chunk) => {
              setMessages((previous) => previous.map((message, index) => {
                if (index !== previous.length - 1 || message.role !== 'assistant') {
                  return message;
                }
                const nextContent = message.content === STREAMING_PLACEHOLDER_TEXT
                  ? chunk
                  : `${message.content}${chunk}`;
                return {
                  ...message,
                  content: nextContent,
                  status: 'streaming',
                };
              }));
            },
          });
        } catch (error) {
          if (isAbortError(error)) {
            wasAborted = true;
          } else {
            analyzeError = error instanceof Error ? error.message : '分析失败';
          }
        }

        if (!analyzeError && streamResult?.status === 'partial_complete' && streamWarningMessage) {
          setAuthError('');
        }

        setMessages((previous) => finalizeMessageStatus(
          previous,
          streamingMessageId,
          { status: analyzeError ? 'error' : 'done' },
        ));

        // Auto TTS will be triggered after messages are fetched from backend below
        setIsStreamingGuard(false);

        const [sessionsResult, messagesResult, panelsResult] = await Promise.allSettled([
          getAssistantSessions(),
          getAssistantMessages(createdSession.id),
          getAssistantPanels(createdSession.id),
        ]);

        if (sessionsResult.status === 'fulfilled') {
          setSessionsData(sessionsResult.value);
        }

        const nextMessagesFromBackend =
          messagesResult.status === 'fulfilled' && messagesResult.value.length > 0
            ? sanitizeMessages(messagesResult.value)
            : null;
        const nextMessages =
          nextMessagesFromBackend
            ?? (analyzeError ? createLocalFallbackMessages(createdSession.id, trimmedValue, analyzeError || undefined) : null);

        const nextPanels =
          !wasAborted && panelsResult.status === 'fulfilled' ? panelsResult.value : emptyPanels;

        setActiveHistory(createdSession.id);
        if (nextMessagesFromBackend) {
          setMessages(nextMessagesFromBackend);
          startAsyncTtsForLatestAssistant(createdSession.id, nextMessagesFromBackend);
        } else if (analyzeError && nextMessages) {
          setMessages(nextMessages);
          if (messagesResult.status === 'fulfilled') {
            startAsyncTtsForLatestAssistant(createdSession.id, messagesResult.value);
          }
        } else {
          const msgs = messagesResult.status === 'fulfilled' ? messagesResult.value : [];
          startAsyncTtsForLatestAssistant(createdSession.id, msgs);
        }
        setPanelData(nextPanels);
        setChatStep(3);
        setActivePanel('none');
        setAnchorMessageId(
          nextMessages?.filter((message) => message.role === 'user').at(-1)?.id
            ?? initialGeneratingMessages[0]?.id
            ?? null,
        );

        if (wasAborted) {
          setAuthError('');
          setChatInput(trimmedValue);
        } else if (analyzeError) {
          setAuthError(analyzeError);
        } else {
          setAuthError('');
        }
        setPendingInitialSessionId(null);
      } catch (error) {
        if (createdSessionId) {
          const fallbackMessages = createLocalFallbackMessages(createdSessionId, trimmedValue, error instanceof Error ? error.message : '分析失败');
          setActiveHistory(createdSessionId);
          setMessages(fallbackMessages);
          setAnchorMessageId(fallbackMessages.find((message) => message.role === 'user')?.id ?? null);
        } else {
          setActiveHistory(null);
          setMessages([]);
          setAnchorMessageId(null);
        }
        setPanelData(emptyPanels);
        setAuthError(error instanceof Error ? error.message : '分析失败');
        setPendingInitialSessionId(null);
      } finally {
        setIsStreamingGuard(false);
        setIsSessionLoading(false);
        setIsSendingMessage(false);
        setActiveStreamController(null);
      }
      return;
    }

    setAppState('chat');
    setChatStep(1);
    setActivePanel('none');
    setIsSidebarCollapsed(false);
    setActiveHistory(sessionsData.activeSessionId);
  };

  const handleHome = () => {
    setAppState('home');
    setChatStep(0);
    setActivePanel('none');
    setIsSidebarCollapsed(true);
    setActiveHistory(sessionsData.activeSessionId);
    setAuthError('');
    setAnchorMessageId(null);
    setEventReportCard(null);
    setIsGeneratingStrategy(false);
  };

  const handleNewChat = () => {
    if (runtimeConfig.dataSourceMode === 'api' && !isAuthenticated) {
      setAuthError('请先登录后再创建新的分析会话。');
      setAppState('login');
      return;
    }
    setAppState('new_chat');
    setChatStep(0);
    setActivePanel('none');
    setIsSidebarCollapsed(false);
    setActiveHistory(null);
    setIsSessionLoading(false);
    setMessages([]);
    setPanelData(emptyPanels);
    setAuthError('');
    setAnchorMessageId(null);
    setEventReportCard(null);
    setIsGeneratingStrategy(false);
  };

  const handleSelectHistory = (sessionId: string) => {
    setAuthError('');
    setAppState('chat');
    setChatStep(3);
    setActivePanel('none');
    setIsSidebarCollapsed(false);

    if (sessionId === activeHistory) {
      setIsSessionLoading(false);
      return;
    }

    setIsSessionLoading(true);
    sessionLoadRequestIdRef.current += 1;
    setMessages([]);
    setPanelData(emptyPanels);
    setActiveHistory(sessionId);
    setAnchorMessageId(null);
    setEventReportCard(null);
    setIsGeneratingStrategy(false);
  };

  const handleSelectKnowledgeBaseForSession = (kbId: string) => {
    const normalizedKbId = String(kbId || '').trim();
    if (!activeHistory) {
      setDraftKnowledgeBaseId(normalizedKbId);
      return;
    }
    setSessionKnowledgeBindings((previous) => {
      const next = { ...previous };
      if (normalizedKbId) {
        next[activeHistory] = normalizedKbId;
      } else {
        delete next[activeHistory];
      }
      return next;
    });
  };

  const handleRenameSession = async (sessionId: string, currentTitle: string) => {
    const nextTitle = window.prompt('请输入新的会话名称', currentTitle)?.trim();
    if (!nextTitle || nextTitle === currentTitle) {
      return;
    }

    try {
      await renameAssistantSession(sessionId, nextTitle);
      setSessionsData((previous) => ({
        ...previous,
        sessions: previous.sessions.map((session) =>
          session.id === sessionId ? { ...session, title: nextTitle } : session,
        ),
      }));
      setAuthError('');
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : '重命名会话失败');
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    const targetSession = sessionsData.sessions.find((session) => session.id === sessionId);
    const confirmed = window.confirm(`确定删除会话“${targetSession?.title ?? '未命名会话'}”吗？`);
    if (!confirmed) {
      return;
    }

    try {
      await deleteAssistantSession(sessionId);
      const remainingSessions = sessionsData.sessions.filter((session) => session.id !== sessionId);
      setSessionsData({
        sessions: remainingSessions,
        activeSessionId: remainingSessions[0]?.id ?? null,
      });

      if (activeHistory === sessionId) {
        setActiveHistory(null);
        setMessages([]);
        setPanelData(emptyPanels);
        setIsGeneratingStrategy(false);
        if (appState === 'chat') {
          setAppState('home');
          setChatStep(0);
          setActivePanel('none');
        }
      }

      setSessionKnowledgeBindings((previous) => {
        if (!(sessionId in previous)) {
          return previous;
        }
        const next = { ...previous };
        delete next[sessionId];
        return next;
      });

      setAuthError('');
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : '删除会话失败');
    }
  };

  const handleSendMessage = async (
    value: string,
    forcedTool: 'none' | 'report' | 'strategy' | 'structured' | 'overview' | 'rumor' | 'debug' = 'none',
    rawInput?: string,
  ) => {
    console.log('[handleSendMessage] forcedTool =', forcedTool, 'value =', value.slice(0, 50), 'rawInput =', rawInput?.slice(0, 50));
    const trimmedValue = value.trim();
    if (!trimmedValue || !activeHistory || !isAuthenticated || isSendingMessage || sendMessageLockRef.current) {
      return;
    }
    sendMessageLockRef.current = true;
    const resolvedRecommendationContext = resolveRecommendationContextFromInput(trimmedValue, homeData.recommendationCards);
    const activeSessionTitle = sessionsData.sessions.find((item) => item.id === activeHistory)?.title;
    const strategyTitle = `${resolveSuggestedAnalysisTarget({
      latestUserInput: trimmedValue,
      sessionTitle: activeSessionTitle,
    }) || activeSessionTitle || '当前事件'}传播策略`;
    const resolvedReportRequest = resolveEventReportRequest({
      text: trimmedValue,
      sessionTitle: activeSessionTitle,
    });
    const forcedReportTarget = resolveSuggestedAnalysisTarget({
      latestUserInput: trimmedValue,
      sessionTitle: activeSessionTitle,
    }) || activeSessionTitle || '当前事件';
    const reportRequest = forcedTool === 'report'
      ? {
          target: forcedReportTarget,
          title: `${forcedReportTarget}事件分析报告`,
        }
      : resolvedReportRequest;
    const isStrategyRequest = forcedTool === 'strategy'
      ? true
      : (!reportRequest && isStrategyGenerationIntent(trimmedValue) && Boolean(panelData.report || panelData.brief || panelData.dataPreview.length));
    const isEventReportRequest = forcedTool === 'report' || Boolean(reportRequest);
    const eventReportTitle = reportRequest?.title ?? (forcedTool === 'report' ? `${forcedReportTarget}事件分析报告` : null);

    const optimisticMessage: ChatMessage = {
      id: `${activeHistory}-user-pending-${Date.now()}`,
      sessionId: activeHistory,
      role: 'user',
      content: trimmedValue,
      createdAt: new Date().toISOString(),
      status: 'done',
    };

    setIsSendingMessage(true);
    setAuthError('');
    setChatInput('');
    setLastSubmittedInput(trimmedValue);
    const streamController = new AbortController();
    setActiveStreamController(streamController);
    const streamingAssistantMessage = createStreamingAssistantMessage(activeHistory);
    if (isEventReportRequest) {
      streamingAssistantMessage.renderMode = 'hidden';
    } else if (isStrategyRequest) {
      streamingAssistantMessage.messageType = 'strategy_plan';
      streamingAssistantMessage.renderMode = 'strategy_card';
      streamingAssistantMessage.content = STRATEGY_PLACEHOLDER_TEXT;
      streamingAssistantMessage.strategyTitle = strategyTitle;
      streamingAssistantMessage.strategyStatus = 'generating';
    }
    const reportCardMessage = isEventReportRequest
      ? createEventReportCardMessage({
          sessionId: activeHistory,
          title: eventReportTitle ?? '事件分析报告',
          reportStatus: 'generating',
        })
      : null;
    const nextEventReportCard = isEventReportRequest
      ? {
          sessionId: activeHistory,
          assistantMessageId: reportCardMessage?.id ?? streamingAssistantMessage.id,
          title: eventReportTitle ?? '事件分析报告',
          content: '',
        }
      : null;
    // Overview, rumor, and debug tools handle their own output - do NOT start SSE stream
    if (forcedTool === 'overview' || forcedTool === 'rumor' || forcedTool === 'debug') {
      // Add user message immediately (debug handles its own, so skip here)
      if (forcedTool !== 'debug') {
        setMessages((previous) => [...previous, optimisticMessage]);
      }
      try {
        if (forcedTool === 'overview') {
          console.log('[handleSendMessage] forcedTool === "overview" - calling searchOverview API');
          let overviewData: Record<string, any> = {};
          try {
            // Use rawInput (original user input) instead of trimmedValue (which may be pre-processed with buildPrompt)
            const searchQuery = rawInput?.trim() || trimmedValue;
            const overviewResult = await searchOverview({
              sessionId: activeHistory,
              query: searchQuery,
              maxResults: 10,
            });
            console.log('[DEBUG overview] overviewResult:', JSON.stringify(overviewResult)?.slice(0, 300));
            overviewData = (overviewResult as any)?.data || overviewResult || {};
            console.log('[DEBUG overview] overviewData.items?.length:', overviewData?.items?.length);
          } catch (err) {
            console.error('[overview] search failed:', err);
          }
          const items: any[] = overviewData?.items || [];
          const summary: string = overviewData?.summary || '';
          const content = buildOverviewFallbackMarkdown(items, summary);
          const assistantMsg: ChatMessage = {
            id: `${activeHistory}-assistant-overview-${Date.now()}`,
            sessionId: activeHistory,
            role: 'assistant',
            content,
            createdAt: new Date().toISOString(),
            status: 'done',
            groundingStatus: 'grounded',
            confidence: items.some((item: any) => item.credibility === 'high') ? 'high' : 'medium',
            usedRealtimeRetrieval: true,
            sources: items.map((item: any, index: number) => ({
              title: item.title || '',
              url: item.url || '',
              sourceType: 'realtime_web',
              summary: item.summary || '',
              snippet: item.content_excerpt || '',
              credibility: item.credibility || 'medium',
              publishedAt: item.published_at || '',
              score: item.relevance_score || 0,
              citationCount: 0,
              keywordScore: item.relevance_score || 0,
              vectorScore: 0,
            })),
            citations: items.map((item: any, index: number) => ({
              id: `overview-citation-${index}`,
              title: item.title || '',
              url: item.url || '',
              sourceType: 'realtime_web',
              credibility: item.credibility || 'medium',
              publishedAt: item.published_at || '',
              sourceTitle: item.title || '',
              sourceUrl: item.url || '',
              quote: item.content_excerpt || '',
              score: item.relevance_score || 0,
              keywordScore: item.relevance_score || 0,
              vectorScore: 0,
            })),
          };
          setMessages((previous) => [...previous, assistantMsg]);
          setTimeout(async () => {
            try {
              const msgs = await getAssistantMessages(activeHistory);
              if (msgs.length > 0) {
                setMessages(sanitizeMessages(msgs));
                startAsyncTtsForLatestAssistant(activeHistory, msgs);
              }
            } catch (e) {
              console.warn('[handleSendMessage overview] fetch messages failed:', e);
            }
          }, 0);
          setIsSendingMessage(false);
          setActiveStreamController(null);
          setAuthError('');
          console.log('[DEBUG overview] About to return - SSE stream should NOT start');
          return;
        }
        if (forcedTool === 'rumor') {
          console.log('[handleSendMessage] forcedTool === "rumor" - calling analyzeRumor API');
          // Use rawInput (original user input) instead of trimmedValue (which may be pre-processed with buildPrompt)
          const searchQuery = rawInput?.trim() || trimmedValue;
          const rumorResult = await analyzeRumor({
            sessionId: activeHistory,
            query: searchQuery,
            maxResults: 8,
          });
          const rumorData = (rumorResult as any)?.data || rumorResult || {};
          const items: any[] = rumorData?.items || [];
          const summary: string = rumorData?.summary || '';
          const content = buildRumorFallbackMarkdown(rumorData, items, summary);
          const assistantMsg: ChatMessage = {
            id: `${activeHistory}-assistant-rumor-${Date.now()}`,
            sessionId: activeHistory,
            role: 'assistant',
            content,
            createdAt: new Date().toISOString(),
            status: 'done',
            groundingStatus: 'grounded',
            confidence: items.some((item: any) => item.credibility === 'high') ? 'high' : 'medium',
            usedRealtimeRetrieval: true,
            sources: items.map((item: any, index: number) => ({
              title: item.title || '',
              url: item.url || '',
              sourceType: 'realtime_web',
              summary: item.summary || '',
              snippet: item.content_excerpt || '',
              credibility: item.credibility || 'medium',
              publishedAt: item.published_at || '',
              score: item.relevance_score || 0,
              citationCount: 0,
              keywordScore: item.relevance_score || 0,
              vectorScore: 0,
            })),
            citations: items.map((item: any, index: number) => ({
              id: `rumor-citation-${index}`,
              title: item.title || '',
              url: item.url || '',
              sourceType: 'realtime_web',
              credibility: item.credibility || 'medium',
              publishedAt: item.published_at || '',
              sourceTitle: item.title || '',
              sourceUrl: item.url || '',
              quote: item.content_excerpt || '',
              score: item.relevance_score || 0,
              keywordScore: item.relevance_score || 0,
              vectorScore: 0,
            })),
          };
          setMessages((previous) => [...previous, assistantMsg]);
          setTimeout(async () => {
            try {
              const msgs = await getAssistantMessages(activeHistory);
              if (msgs.length > 0) {
                setMessages(sanitizeMessages(msgs));
                startAsyncTtsForLatestAssistant(activeHistory, msgs);
              }
            } catch (e) {
              console.warn('[handleSendMessage rumor] fetch messages failed:', e);
            }
          }, 0);
          setIsSendingMessage(false);
          setActiveStreamController(null);
          setAuthError('');
          return;
        }
        if (forcedTool === 'debug') {
          // Debug 模式：真实 LLM 流式输出
          // 创建明确的占位消息，用 flushSync 强制同步渲染，避免 React 19 并发模式延迟
          const placeholderMsg: ChatMessage = {
            id: `${activeHistory}-assistant-streaming-${Date.now()}`,
            sessionId: activeHistory,
            role: 'assistant',
            content: DEBUG_STREAMING_PLACEHOLDER_TEXT,
            messageType: 'plain',
            renderMode: 'bubble',
            createdAt: new Date().toISOString(),
            status: 'streaming',
            route: 'debug_llm_stream',
            debugMode: true,
          };
          flushSync(() => {
            setMessages((previous) => [...previous, optimisticMessage, placeholderMsg]);
          });
          flushSync(() => {
            setIsStreamingGuard(true);
          });
          await streamAnalyze({
            mode: 'chat',
            sessionId: activeHistory,
            message: trimmedValue,
            debugMode: true,
          }, {
            signal: streamController.signal,
            onChunk: (chunk) => {
              flushSync(() => {
                setMessages((previous) => {
                  return previous.map((message, index) => {
                    if (index !== previous.length - 1 || message.role !== 'assistant') {
                      return message;
                    }
                    const nextContent = message.content === DEBUG_STREAMING_PLACEHOLDER_TEXT
                      ? chunk
                      : `${message.content}${chunk}`;
                    return { ...message, content: nextContent, status: 'streaming' };
                  });
                });
              });
            },
            onDone: () => {
              setIsStreamingGuard(false);
              setChatStep(3);
              // 从后端拉取最新消息，确保持久化和状态一致
              setTimeout(async () => {
                try {
                  const msgs = await getAssistantMessages(activeHistory);
                  if (msgs.length > 0) {
                    setMessages(msgs);
                    startAsyncTtsForLatestAssistant(activeHistory, msgs);
                  }
                } catch (e) {
                  console.warn('[handleSendMessage] fetch messages failed:', e);
                }
              }, 0);
            },
            onError: (error, payload) => {
              const displayError = normalizeStreamIssueMessage(error, payload);
              if (!isAbortError(error)) {
                console.error('[handleSendMessage] streamAnalyze failed:', displayError, payload);
              }
              setAuthError(displayError);
              setIsStreamingGuard(false);
              sendMessageLockRef.current = false;
            },
          });
          setAuthError('');
          return;
        }
      } finally {
        // Always release lock - critical for unblocking subsequent messages
        sendMessageLockRef.current = false;
        // Use setTimeout to flush state update before next handleSubmit guard check
        setTimeout(() => setIsSendingMessage(false), 0);
        setActiveStreamController(null);
      }
    }

    // Report tool: call the dedicated generate report API, do NOT go through SSE stream
    if (forcedTool === 'report') {
      const reportTitle = eventReportTitle ?? '事件分析报告';
      const reportCardMessage = createEventReportCardMessage({
        sessionId: activeHistory,
        title: reportTitle,
        reportStatus: 'generating',
      });
      setMessages((previous) => [...previous, optimisticMessage, reportCardMessage]);
      setActivePanel('report');
      setEventReportCard({
        sessionId: activeHistory,
        assistantMessageId: reportCardMessage.id,
        title: reportTitle,
        content: '',
        reportStatus: 'generating',
      });
setIsGeneratingReport(true);
      try {
        console.log('[handleSendMessage] forcedTool === "report" - 开始生成报告');
        console.log('[handleSendMessage] activeHistory (sessionId):', activeHistory);
        console.log('[handleSendMessage] trimmedValue:', trimmedValue);

        // 获取调用前的消息上下文
        console.log('[handleSendMessage] 调用报告API前的消息状态:');
        console.log('[handleSendMessage] current messages count:', messages.length);
        console.log('[handleSendMessage] current messages:', JSON.stringify(messages.map((m: ChatMessage) => ({
          role: m.role,
          content: String(m.content).slice(0, 80),
          messageType: m.messageType,
          renderMode: m.renderMode,
        }))));

        await saveAssistantSessionMessage({
          sessionId: activeHistory,
          role: 'user',
          content: trimmedValue,
        });

console.log('[handleSendMessage] 调用 generateAssistantReport API...');

        const reportResult = await generateAssistantReport(activeHistory);
        console.log('[handleSendMessage] generateAssistantReport 返回结果:');
        console.log('[handleSendMessage] - reportId:', reportResult?.reportId);
        console.log('[handleSendMessage] - isFallback:', reportResult?.isFallback);
        console.log('[handleSendMessage] - warning:', reportResult?.warning);
        console.log('[handleSendMessage] - meta.title:', reportResult?.data?.meta?.title);
        console.log('[handleSendMessage] - keyFindings:', JSON.stringify(reportResult?.data?.executiveSummary?.keyFindings));
        console.log('[handleSendMessage] - topTrends:', JSON.stringify(reportResult?.data?.executiveSummary?.topTrends));

        console.log('[handleSendMessage] 调用后从后端拉取最新状态...');

        const generatedReportData = reportResult?.data || {};
        const nextPanelData = buildPanelsFromGeneratedReport(reportResult);
        const [sessionsResult, messagesResult, panelsResult] = await Promise.allSettled([
          getAssistantSessions(),
          getAssistantMessages(activeHistory),
          getAssistantPanels(activeHistory),
        ]);

        if (sessionsResult.status === 'fulfilled') {
          setSessionsData(sessionsResult.value);
        }

const resolvedPanels = panelsResult.status === 'fulfilled' && (panelsResult.value.report || panelsResult.value.strategy)
          ? panelsResult.value
          : nextPanelData;
        console.log('[handleSendMessage] 后端返回的 panelsResult:', JSON.stringify({
          status: panelsResult.status,
          hasReport: panelsResult.status === 'fulfilled' && Boolean(panelsResult.value.report),
          reportTitle: panelsResult.status === 'fulfilled' && panelsResult.value.report?.title,
          hasStrategy: panelsResult.status === 'fulfilled' && Boolean(panelsResult.value.strategy),
          strategyTitle: panelsResult.status === 'fulfilled' && panelsResult.value.strategy?.title,
        }));
        console.log('[handleSendMessage] 后端返回的 messagesResult:', JSON.stringify({
          status: messagesResult.status,
          messageCount: messagesResult.status === 'fulfilled' ? messagesResult.value.length : 0,
        }));

        const hydrated = messagesResult.status === 'fulfilled'
          ? hydrateHistoricalReportCards(sanitizeMessages(messagesResult.value), {
              panelReport: resolvedPanels.report,
              sessionTitle: activeSessionTitle || reportTitle,
            })
          : null;
        const nextMessages = hydrated?.messages?.length
          ? hydrateHistoricalStrategyCards(hydrated.messages, activeSessionTitle)
          : [
              optimisticMessage,
              createEventReportCardMessage({
                sessionId: activeHistory,
                title: reportResult?.data?.meta?.title || reportTitle,
                content: buildReportCardSummaryFromContent(generatedReportData),
                reportStatus: 'ready',
              }),
            ];

        setMessages(nextMessages);
        setPanelData(resolvedPanels);
        setActivePanel('report');
        setEventReportCard(
          hydrated?.latestEventReportCard
            ? {
                ...hydrated.latestEventReportCard,
                content: resolvedPanels.report?.content || generatedReportData,
                reportStatus: 'ready',
                reportId: resolvedPanels.report?.id || reportResult?.reportId || '',
              }
            : {
                sessionId: activeHistory,
                assistantMessageId: nextMessages.find((message) => message.renderMode === 'report_card')?.id || '',
                title: reportResult?.data?.meta?.title || reportTitle,
                content: resolvedPanels.report?.content || generatedReportData,
                reportStatus: 'ready',
                reportId: resolvedPanels.report?.id || reportResult?.reportId || '',
              },
        );
      } catch (err) {
        console.error('[report] generate failed:', err);
        const errorMsg: ChatMessage = {
          id: `${activeHistory}-assistant-report-error-${Date.now()}`,
          sessionId: activeHistory,
          role: 'assistant',
          content: `报告生成失败: ${String(err)}`,
          createdAt: new Date().toISOString(),
          status: 'done',
        };
        setMessages((previous) => [...previous, errorMsg]);
      } finally {
        setIsGeneratingReport(false);
        setIsSendingMessage(false);
        setActiveStreamController(null);
        setAuthError('');
      }
      return;  // 重要：不继续走 SSE 流
    }

    setMessages((previous) => ([
      ...previous,
      optimisticMessage,
      streamingAssistantMessage,
      ...(reportCardMessage ? [reportCardMessage] : []),
    ]));
    setAnchorMessageId(optimisticMessage.id);
    if (isEventReportRequest) {
      setActivePanel('report');
      setEventReportCard(nextEventReportCard);
      setIsGeneratingReport(true);
      setIsGeneratingStrategy(false);
    } else if (isStrategyRequest) {
      setActivePanel('strategy');
      setEventReportCard(null);
      setIsGeneratingReport(false);
      setIsGeneratingStrategy(true);
    } else {
      setEventReportCard(null);
      setIsGeneratingReport(false);
      setIsGeneratingStrategy(false);
    }
    let wasAborted = false;

    try {
      if (isStrategyRequest) {
        const strategyPayload = buildStrategyPayload({
          panelData,
          sessionTitle: activeSessionTitle,
          latestUserInput: trimmedValue,
        });
        await saveAssistantSessionMessage({
          sessionId: activeHistory,
          role: 'user',
          content: trimmedValue,
        });
        const strategyStart = await generateAssistantStrategy({
          sessionId: activeHistory,
          ...strategyPayload,
        });
        const taskResult = await waitForAssistantTaskCompletion(strategyStart.task_id);
        if (taskResult.status === 'failed' && shouldFallbackToSyncStrategy(taskResult.message)) {
          await generateAssistantStrategySync({
            sessionId: activeHistory,
            ...strategyPayload,
          });
        } else if (taskResult.status === 'failed') {
          throw new Error(taskResult.message || '策略生成失败');
        }
        setIsSendingMessage(false);
        setIsGeneratingReport(false);
        setIsGeneratingStrategy(false);
        setActiveStreamController(null);

        const [sessionsResult, messagesResult, panelsResult] = await Promise.allSettled([
          getAssistantSessions(),
          getAssistantMessages(activeHistory),
          getAssistantPanels(activeHistory),
        ]);
        if (sessionsResult.status === 'fulfilled') {
          setSessionsData(sessionsResult.value);
        }
        const nextPanels = panelsResult.status === 'fulfilled' ? panelsResult.value : emptyPanels;
        const nextMessagesFromBackend =
          messagesResult.status === 'fulfilled' ? messagesResult.value : null;
        const hydratedMessages = nextMessagesFromBackend?.length
          ? hydrateHistoricalReportCards(sanitizeMessages(nextMessagesFromBackend), {
              panelReport: nextPanels.report,
              sessionTitle: activeSessionTitle,
            })
          : null;
        if (hydratedMessages?.messages?.length) {
          const nextMessages = hydrateHistoricalStrategyCards(hydratedMessages.messages, activeSessionTitle);
          setMessages(nextMessages);
          startAsyncTtsForLatestAssistant(activeHistory, nextMessages);
        }
        setPanelData(nextPanels);
        if (nextPanels.strategy) {
          setActivePanel('strategy');
        }
        setChatStep(3);
        setAuthError('');
        setAnchorMessageId(
          hydratedMessages?.messages?.filter((message) => message.role === 'user').at(-1)?.id ?? optimisticMessage.id,
        );
        return;
      }

      let streamWarningMessage = '';
      setIsStreamingGuard(true);
      const streamResult = await streamAnalyze({
        mode: 'chat',
        sessionId: activeHistory,
        message: trimmedValue,
        kbId: activeKnowledgeBaseId || undefined,
        recommendationContext: resolvedRecommendationContext || undefined,
      }, {
        signal: streamController.signal,
        onGrounding: (payload) => {
          setMessages((previous) => previous.map((message) => {
            if (message.id !== streamingAssistantMessage.id) {
              return message;
            }
            return mergeStreamPayloadMeta({
              ...message,
              groundingStatus: String(payload?.groundingStatus || ''),
              confidence: String(payload?.confidence || ''),
              usedRealtimeRetrieval: Boolean(payload?.usedRealtimeRetrieval),
              structuredRecordCount: Number(payload?.structuredRecordCount || 0),
              structuredAggregations: payload?.structuredAggregations || {},
              structuredRecords: Array.isArray(payload?.structuredRecords) ? payload.structuredRecords : [],
              sources: Array.isArray(payload?.sources) ? payload.sources : [],
              citations: Array.isArray(payload?.citations) ? payload.citations : [],
              facts: Array.isArray(payload?.facts) ? payload.facts : [],
              toVerify: Array.isArray(payload?.toVerify) ? payload.toVerify : [],
              analysis: Array.isArray(payload?.analysis) ? payload.analysis : [],
            }, payload);
          }));
        },
        onWarning: (warning, payload) => {
          streamWarningMessage = normalizeStreamIssueMessage(warning, payload);
        },
        onChunk: (chunk) => {
          let latestContent = '';
          setMessages((previous) => previous.map((message) => {
            if (message.id !== streamingAssistantMessage.id && message.id !== reportCardMessage?.id) {
              return message;
            }
            const nextContent = message.content === STREAMING_PLACEHOLDER_TEXT
              ? chunk
              : `${message.content}${chunk}`;
            latestContent = nextContent;
            return {
              ...message,
              content: nextContent,
              status: message.id === streamingAssistantMessage.id ? 'streaming' : 'done',
            };
          }));
          if (isEventReportRequest) {
            setEventReportCard((previous) => (
              previous
                ? { ...previous, content: latestContent || previous.content }
                : previous
            ));
          }
        },
      });

      setMessages((previous) => finalizeMessageStatus(
        finalizeMessageStatus(
          previous,
          streamingAssistantMessage.id,
          {
            status: 'done',
            reportStatus: isEventReportRequest ? 'generating' : 'idle',
          },
        ),
        reportCardMessage?.id || '',
        isEventReportRequest
          ? {
              status: 'done',
              reportStatus: 'generating',
            }
          : {},
      ));
      setIsStreamingGuard(false);
      setIsSendingMessage(false);
      setActiveStreamController(null);
      let nextPanelData = panelData;
      const shouldGenerateFormalReport = isEventReportRequest && streamResult.status !== 'partial_complete';
      console.log('[handleSendMessage SSE后] shouldGenerateFormalReport:', shouldGenerateFormalReport);
      console.log('[handleSendMessage SSE后] isEventReportRequest:', isEventReportRequest);
      console.log('[handleSendMessage SSE后] streamResult.status:', streamResult.status);
      if (shouldGenerateFormalReport) {
        console.log('[handleSendMessage SSE后] 开始生成正式报告...');
        console.log('[handleSendMessage SSE后] activeHistory (sessionId):', activeHistory);
        const generatedReport = await generateAssistantReport(activeHistory);
        console.log('[handleSendMessage SSE后] generateAssistantReport 返回结果:');
        console.log('[handleSendMessage SSE后] - reportId:', generatedReport?.reportId);
        console.log('[handleSendMessage SSE后] - isFallback:', generatedReport?.isFallback);
        console.log('[handleSendMessage SSE后] - warning:', generatedReport?.warning);
        console.log('[handleSendMessage SSE后] - meta.title:', generatedReport?.data?.meta?.title);
        console.log('[handleSendMessage SSE后] - keyFindings:', JSON.stringify(generatedReport?.data?.executiveSummary?.keyFindings));
        nextPanelData = buildPanelsFromGeneratedReport(generatedReport);
        setPanelData(nextPanelData);
        setMessages((previous) => finalizeMessageStatus(
          previous,
          reportCardMessage?.id || '',
          {
            status: 'done',
            reportStatus: 'ready',
            content: String(generatedReport.data?.executiveSummary?.summary || ''),
          },
        ));
        setIsGeneratingReport(false);
        setIsGeneratingStrategy(false);
      } else if (isEventReportRequest) {
        setIsGeneratingReport(false);
        setIsGeneratingStrategy(false);
        const warningContent = streamWarningMessage || '当前回复已部分生成，但尾部被上游模型安全策略拦截，暂不继续生成正式报告。';
        setMessages((previous) => finalizeMessageStatus(
          previous,
          reportCardMessage?.id || '',
          {
            status: 'done',
            reportStatus: 'idle',
            content: warningContent,
          },
        ));
      }

      const recoveredArtifacts = isEventReportRequest
        ? await recoverGeneratedReportArtifacts({
            sessionId: activeHistory,
            sessionTitle: activeSessionTitle,
          })
        : null;

      const [sessionsResult, messagesResult, panelsResult] = await Promise.allSettled([
        getAssistantSessions(),
        getAssistantMessages(activeHistory),
        getAssistantPanels(activeHistory),
      ]);

      const nextMessagesFromBackend =
        recoveredArtifacts?.messages?.length
          ? recoveredArtifacts.messages
          : (messagesResult.status === 'fulfilled' ? messagesResult.value : null);
      const nextPanels =
        recoveredArtifacts?.panels
          ? recoveredArtifacts.panels
          : (panelsResult.status === 'fulfilled' && (panelsResult.value.report || panelsResult.value.strategy)
            ? panelsResult.value
            : nextPanelData);

      if (sessionsResult.status === 'fulfilled') {
        setSessionsData(sessionsResult.value);
      }
      const hydratedMessages = nextMessagesFromBackend?.length
        ? hydrateHistoricalReportCards(sanitizeMessages(nextMessagesFromBackend), {
            panelReport: nextPanels?.report ?? null,
            sessionTitle: activeSessionTitle,
          })
        : null;
      const hydratedEventReportResult = isEventReportRequest
        ? (recoveredArtifacts?.messages?.length
          ? {
              messages: recoveredArtifacts.messages,
              latestEventReportCard: recoveredArtifacts.latestEventReportCard ?? null,
            }
          : hydrateHistoricalReportCards(sanitizeMessages(nextMessagesFromBackend ?? []), {
              panelReport: nextPanels?.report ?? null,
              sessionTitle: activeSessionTitle,
            }))
        : null;
      if (isEventReportRequest) {
        setMessages((previous) => (
          hydratedEventReportResult?.messages?.length
            ? hydrateHistoricalStrategyCards(hydratedEventReportResult.messages, activeSessionTitle)
            : applyEventReportCardToMessages(previous, {
                assistantMessageId: reportCardMessage?.id || streamingAssistantMessage.id,
                title: eventReportTitle ?? '事件分析报告',
                reportStatus: 'ready',
              })
        ));
      } else if (hydratedMessages?.messages?.length) {
        const nextMessages = hydrateHistoricalStrategyCards(hydratedMessages.messages, activeSessionTitle);
        setMessages(nextMessages);
        startAsyncTtsForLatestAssistant(activeHistory, nextMessages);
      }
      setPanelData(nextPanels);
      setChatStep(3);
      setAuthError('');
      setAnchorMessageId(
        isEventReportRequest
          ? nextMessagesFromBackend?.filter((message) => message.role === 'user').at(-1)?.id ?? optimisticMessage.id
          : hydratedMessages?.messages?.filter((message) => message.role === 'user').at(-1)?.id ?? optimisticMessage.id,
      );
      if (isEventReportRequest) {
        const recoveredReportContent =
          nextPanels?.report?.content
          || (eventReportCard?.content && typeof eventReportCard.content === 'object' ? eventReportCard.content : null);
        setEventReportCard(
          hydratedEventReportResult?.latestEventReportCard
            ? {
                ...hydratedEventReportResult.latestEventReportCard,
                content: recoveredReportContent || hydratedEventReportResult.latestEventReportCard.content,
                reportStatus: shouldGenerateFormalReport ? 'ready' : 'idle',
              }
            : nextEventReportCard
              ? {
                  ...nextEventReportCard,
                  reportStatus: shouldGenerateFormalReport ? 'ready' : 'idle',
                  content: !shouldGenerateFormalReport && streamWarningMessage
                    ? streamWarningMessage
                    : nextEventReportCard.content,
                }
              : null,
        );
      }
    } catch (error) {
      setIsSendingMessage(false);
      setIsGeneratingReport(false);
      setIsGeneratingStrategy(false);
      if (isAbortError(error)) {
        wasAborted = true;
        setAuthError('');
        setChatInput(trimmedValue);
        setMessages((previous) => previous.filter((message) =>
          message.id !== streamingAssistantMessage.id && message.id !== reportCardMessage?.id,
        ));
        if (isEventReportRequest) {
          setEventReportCard(null);
        }
      } else {
        setAuthError(error instanceof Error ? error.message : '继续对话失败');
      }
      if (wasAborted) {
        return;
      }
      if (isEventReportRequest) {
        const recoveredReport = await recoverGeneratedReportArtifacts({
          sessionId: activeHistory,
          sessionTitle: activeSessionTitle,
        });
        if (recoveredReport) {
          if (recoveredReport.sessions) {
            setSessionsData(recoveredReport.sessions);
          }
          if (recoveredReport.messages?.length) {
            setMessages(recoveredReport.messages);
          }
          if (recoveredReport.panels) {
            setPanelData(recoveredReport.panels);
          }
          setEventReportCard(
            recoveredReport.latestEventReportCard
              ? {
                  ...recoveredReport.latestEventReportCard,
                  reportStatus: 'ready',
                }
              : nextEventReportCard
                ? {
                    ...nextEventReportCard,
                    reportStatus: 'ready',
                  }
                : null,
          );
          setAnchorMessageId(optimisticMessage.id);
          setAuthError('');
          return;
        }
      }
      const fallbackAssistantMessage: ChatMessage = {
        id: streamingAssistantMessage.id,
        sessionId: activeHistory,
        role: 'assistant',
        content: `当前消息已发送，但返回异常：${error instanceof Error ? error.message : (isStrategyRequest ? '策略生成失败' : '继续对话失败')}`,
        createdAt: new Date().toISOString(),
        messageType: isEventReportRequest ? 'event_report' : 'plain',
        renderMode: isEventReportRequest ? 'report_card' : 'bubble',
        status: 'error',
        tagLabel: '返回异常',
        reportStatus: 'idle',
        reportTitle: isEventReportRequest ? (eventReportTitle ?? '事件分析报告') : undefined,
      };
      setMessages((previous) => {
        const withoutStreaming = previous.filter((message) => message.id !== streamingAssistantMessage.id);
        return withoutStreaming.map((message) => (
          message.id === optimisticMessage.id ? message : message
        )).concat(fallbackAssistantMessage);
      });
      setAnchorMessageId(optimisticMessage.id);
      if (isEventReportRequest) {
        setEventReportCard({
          sessionId: activeHistory,
          assistantMessageId: fallbackAssistantMessage.id,
          title: eventReportTitle ?? '事件分析报告',
          content: fallbackAssistantMessage.content,
        });
      }
    } finally {
      sendMessageLockRef.current = false;
      setActiveStreamController(null);
    }
  };

  const handlePauseGeneration = () => {
    sendMessageLockRef.current = false;
    if (activeStreamController) {
      activeStreamController.abort();
    }
    setIsSendingMessage(false);
    setIsSessionLoading(false);
    setPendingInitialSessionId(null);
    setActivePanel('none');
    if (lastSubmittedInput.trim()) {
      setChatInput(lastSubmittedInput);
    }
  };

  const handleLogin = async (values: LoginForm, targetState: 'home' | 'new_chat' = 'home') => {
    setAuthLoading(true);
    setAuthError('');
    try {
      const user = await login(values);
      setCurrentUser(user);
      setAppState(targetState);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : '登录失败');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleRegister = async (values: RegisterForm, targetState: 'home' | 'new_chat' = 'home') => {
    setAuthLoading(true);
    setAuthError('');
    try {
      const user = await register(values);
      setCurrentUser(user);
      setAppState(targetState);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : '注册失败');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    setCurrentUser(null);
    setAppState('home');
    setActivePanel('none');
  };

  const handleTopNavSelect = (tab: string) => {
    setActiveTab(tab);
    if (tab !== 'AI 舆情助手') {
      setAppState('home');
      setActivePanel('none');
    }
  };

  const showNavbar = appState !== 'login' && appState !== 'register';

  return (
    <div className="font-sans text-gray-900">
      {showNavbar && <TopNavbar activeTab={activeTab} onSelect={handleTopNavSelect} />}
      {showNavbar && authError && appState !== 'login' && appState !== 'register' && (
        <div className="fixed top-16 left-1/2 z-[70] -translate-x-1/2 rounded-full border border-red-200 bg-white/95 px-5 py-2 text-sm text-red-600 shadow-lg backdrop-blur-md">
          {authError}
        </div>
      )}

      {appState === 'login' ? (
        <LoginView
          onLogin={(values) => void handleLogin(values, 'home')}
          onGoRegister={() => setAppState('register')}
          authLoading={authLoading}
          authError={authError}
        />
      ) : appState === 'register' ? (
        <RegisterView
          onRegister={(values) => void handleRegister(values, 'home')}
          onGoLogin={() => setAppState('login')}
          authLoading={authLoading}
          authError={authError}
        />
      ) : appState === 'home' ? (
        activeTab === '智慧中枢' ? (
          <CommandCenterView
            onGoLogin={() => setAppState('login')}
            currentUser={currentUser}
            authLoading={authLoading}
            onLogout={() => void handleLogout()}
            isSidebarCollapsed={isSidebarCollapsed}
            setIsSidebarCollapsed={setIsSidebarCollapsed}
            onNewChat={handleNewChat}
            onSelectHistory={handleSelectHistory}
            sessions={sessionsData.sessions}
            onRenameSession={(sessionId: string, currentTitle: string) => void handleRenameSession(sessionId, currentTitle)}
            onDeleteSession={(sessionId: string) => void handleDeleteSession(sessionId)}
          />
        ) : activeTab === '可视化大屏' ? (
          <BigScreenView
            onGoLogin={() => setAppState('login')}
            currentUser={currentUser}
            authLoading={authLoading}
            onLogout={() => void handleLogout()}
            isSidebarCollapsed={isSidebarCollapsed}
            setIsSidebarCollapsed={setIsSidebarCollapsed}
            onNewChat={handleNewChat}
            onSelectHistory={handleSelectHistory}
            sessions={sessionsData.sessions}
            onRenameSession={(sessionId: string, currentTitle: string) => void handleRenameSession(sessionId, currentTitle)}
            onDeleteSession={(sessionId: string) => void handleDeleteSession(sessionId)}
          />
        ) : activeTab === '私有知识库' ? (
          <KnowledgeBaseView
            onGoLogin={() => setAppState('login')}
            currentUser={currentUser}
            authLoading={authLoading}
            onLogout={() => void handleLogout()}
            isSidebarCollapsed={isSidebarCollapsed}
            setIsSidebarCollapsed={setIsSidebarCollapsed}
            onNewChat={handleNewChat}
            onSelectHistory={handleSelectHistory}
            sessions={sessionsData.sessions}
            onRenameSession={(sessionId: string, currentTitle: string) => void handleRenameSession(sessionId, currentTitle)}
            onDeleteSession={(sessionId: string) => void handleDeleteSession(sessionId)}
          />
        ) : (
          <HomeView 
            onSearch={handleSearch} 
            onNewChat={handleNewChat}
            activeModel={activeModel} 
            setActiveModel={setActiveModel} 
            onRefreshRecommendations={loadHomeData}
            isHomeLoading={isHomeLoading}
            onGoLogin={() => setAppState('login')}
            currentUser={currentUser}
            authLoading={authLoading}
            onLogout={() => void handleLogout()}
            isSidebarCollapsed={isSidebarCollapsed}
            setIsSidebarCollapsed={setIsSidebarCollapsed}
            onSelectHistory={handleSelectHistory}
            activeHistory={activeHistory}
            sessions={sessionsData.sessions}
            recommendationCards={homeData.recommendationCards}
            homeLoadError={homeLoadError}
            suggestedPrompts={homeData.suggestedPrompts}
            onRenameSession={(sessionId: string, currentTitle: string) => void handleRenameSession(sessionId, currentTitle)}
            onDeleteSession={(sessionId: string) => void handleDeleteSession(sessionId)}
          />
        )
      ) : appState === 'new_chat' ? (
        <NewChatView
          onSearch={handleSearch}
          onHome={handleHome}
          activeModel={activeModel}
          setActiveModel={setActiveModel}
          onGoLogin={() => setAppState('login')}
          currentUser={currentUser}
          authLoading={authLoading}
          onLogout={() => void handleLogout()}
          isSidebarCollapsed={isSidebarCollapsed}
          setIsSidebarCollapsed={setIsSidebarCollapsed}
          onSelectHistory={handleSelectHistory}
          activeHistory={activeHistory}
          setActiveHistory={setActiveHistory}
          isSendingMessage={isSendingMessage}
          setIsSendingMessage={setIsSendingMessage}
          uploadingVideo={uploadingVideo}
          setUploadingVideo={setUploadingVideo}
          sessions={sessionsData.sessions}
          suggestedPrompts={homeData.suggestedPrompts}
          knowledgeBases={knowledgeBases}
          selectedKnowledgeBaseId={draftKnowledgeBaseId}
          onSelectKnowledgeBase={setDraftKnowledgeBaseId}
          onRenameSession={(sessionId: string, currentTitle: string) => void handleRenameSession(sessionId, currentTitle)}
          onDeleteSession={(sessionId: string) => void handleDeleteSession(sessionId)}
          ttsAutoPlay={ttsAutoPlay}
          setTtsAutoPlay={setTtsAutoPlay}
        />
      ) : (
        <ChatView 
          key={activeHistory ?? 'chat-empty'}
          onHome={handleHome} 
          onNewChat={handleNewChat}
          chatStep={chatStep} 
          setChatStep={setChatStep} 
          activePanel={activePanel}
          onShowPanel={setActivePanel}
          activeModel={activeModel}
          setActiveModel={setActiveModel}
          isSidebarCollapsed={isSidebarCollapsed}
          setIsSidebarCollapsed={setIsSidebarCollapsed}
          onSelectHistory={handleSelectHistory}
          activeHistory={activeHistory}
          sessions={sessionsData.sessions}
          messages={messages}
          setMessages={setMessages}
          panelData={panelData}
          isSessionLoading={isSessionLoading}
          isSendingMessage={isSendingMessage}
          setIsSendingMessage={setIsSendingMessage}
          uploadingVideo={uploadingVideo}
          setUploadingVideo={setUploadingVideo}
          isGeneratingReport={isGeneratingReport}
          isGeneratingStrategy={isGeneratingStrategy}
          anchorMessageId={anchorMessageId}
          input={chatInput}
          onInputChange={setChatInput}
          onPauseGeneration={handlePauseGeneration}
          eventReportCard={eventReportCard}
          selectedTool={selectedTool}
          setSelectedTool={setSelectedTool}
          onSendMessage={(value: string, tool?: 'none' | 'report' | 'strategy' | 'structured' | 'overview' | 'rumor', rawInput?: string) => void handleSendMessage(value, tool ?? 'none', rawInput)}
          knowledgeBases={knowledgeBases}
          selectedKnowledgeBaseId={activeKnowledgeBaseId}
          onSelectKnowledgeBase={handleSelectKnowledgeBaseForSession}
          onRenameSession={(sessionId: string, currentTitle: string) => void handleRenameSession(sessionId, currentTitle)}
          onDeleteSession={(sessionId: string) => void handleDeleteSession(sessionId)}
          ttsAutoPlay={ttsAutoPlay}
          setTtsAutoPlay={setTtsAutoPlay}
        />
      )}
    </div>
  );
}
