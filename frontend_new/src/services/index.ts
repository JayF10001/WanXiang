import { runtimeConfig } from '../config/runtime';
import {
  analyzeWithApi,
  createAssistantSessionInApi,
  deleteAssistantSessionInApi,
  exportAssistantReportPdfInApi,
  generateAssistantReportInApi,
  generateAssistantStrategyInApi,
  generateAssistantStrategySyncInApi,
  getAssistantHomeFromApi,
  getAssistantMessagesFromApi,
  getAssistantPanelsFromApi,
  getAssistantTaskStatusFromApi,
  getRecommendationSummaryFromApi,
  getAssistantSessionsFromApi,
  renameAssistantSessionInApi,
  saveAssistantSessionMessageInApi,
  searchOverviewApi,
  analyzeRumorApi,
  streamAssistantMessageInApi,
  uploadMultimodalAnalysisApi,
  uploadVideoAnalysisApi,
  textToSpeechApi,
  textToSpeechAsyncApi,
} from './api/assistant';
import {
  getCurrentUserFromApi,
  loginWithApi,
  logoutFromApi,
  registerWithApi,
} from './api/auth';
import {
  createKnowledgeBaseInApi,
  deleteKnowledgeFileInApi,
  getKnowledgeBasesFromApi,
  getKnowledgeFilesFromApi,
  rebuildKnowledgeBaseIndexInApi,
  retryKnowledgeFileIndexInApi,
  retryKnowledgeFileParseInApi,
  uploadKnowledgeFileInApi,
} from './api/knowledge';
import { getRagAnswerFromApi } from './api/rag';
import { getCommandCenterFromApi } from './api/dashboard';
import { getAssistantHomeMock, getAssistantMessagesMock, getAssistantPanelsMock, getAssistantSessionsMock } from './mock/assistant';
import { getCurrentUserMock } from './mock/auth';
import { getNewsListMock } from './mock/news';
import type { AnalysisInput } from '../types/assistant';
import type { LoginForm, RegisterForm } from '../types/auth';

export { runtimeConfig };

export async function getCurrentUser() {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getCurrentUserFromApi();
  }
  if (runtimeConfig.dataSourceMode === 'mock') {
    return getCurrentUserMock();
  }
  throw new Error('Real data source mode is not implemented yet.');
}

export async function login(body: LoginForm) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return loginWithApi(body);
  }
  return getCurrentUserMock();
}

export async function register(body: RegisterForm) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return registerWithApi(body);
  }
  return getCurrentUserMock();
}

export async function logout() {
  if (runtimeConfig.dataSourceMode === 'api') {
    return logoutFromApi();
  }
}

export async function getAssistantHome(options?: { refreshToken?: string }) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getAssistantHomeFromApi(options);
  }
  return getAssistantHomeMock();
}

export async function getRecommendationSummary(params: { title: string; sourceUrl?: string }) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getRecommendationSummaryFromApi(params);
  }
  return {
    summary: '',
    summarySource: 'fallback',
  };
}

export async function getAssistantSessions() {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getAssistantSessionsFromApi();
  }
  if (runtimeConfig.dataSourceMode === 'mock') {
    return getAssistantSessionsMock();
  }
  throw new Error('Real data source mode is not implemented yet.');
}

export async function createAssistantSession() {
  if (runtimeConfig.dataSourceMode === 'api') {
    return createAssistantSessionInApi();
  }
  throw new Error('Create session is only implemented for api mode.');
}

export async function deleteAssistantSession(sessionId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return deleteAssistantSessionInApi(sessionId);
  }
  throw new Error('Delete session is only implemented for api mode.');
}

export async function renameAssistantSession(sessionId: string, title: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return renameAssistantSessionInApi(sessionId, title);
  }
  throw new Error('Rename session is only implemented for api mode.');
}

export async function getAssistantMessages(sessionId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getAssistantMessagesFromApi(sessionId);
  }
  if (runtimeConfig.dataSourceMode === 'mock') {
    return getAssistantMessagesMock(sessionId);
  }
  throw new Error('Real data source mode is not implemented yet.');
}

export async function getAssistantPanels(sessionId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getAssistantPanelsFromApi(sessionId);
  }
  if (runtimeConfig.dataSourceMode === 'mock') {
    return getAssistantPanelsMock(sessionId);
  }
  throw new Error('Real data source mode is not implemented yet.');
}

export async function generateAssistantReport(sessionId: string, message?: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return generateAssistantReportInApi(sessionId, message);
  }
  throw new Error('Generate report is only implemented for api mode.');
}

export async function generateAssistantStrategy(params: {
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
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return generateAssistantStrategyInApi(params);
  }
  throw new Error('Generate strategy is only implemented for api mode.');
}

export async function generateAssistantStrategySync(params: {
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
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return generateAssistantStrategySyncInApi(params);
  }
  throw new Error('Generate strategy sync is only implemented for api mode.');
}

export async function getAssistantTaskStatus(taskId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getAssistantTaskStatusFromApi(taskId);
  }
  throw new Error('Get task status is only implemented for api mode.');
}

export async function exportAssistantReportPdf(params: { reportId?: string | null; sessionId?: string | null }) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return exportAssistantReportPdfInApi(params);
  }
  throw new Error('Export report is only implemented for api mode.');
}

export async function saveAssistantSessionMessage(params: {
  sessionId: string;
  role: 'user' | 'assistant';
  content: string;
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return saveAssistantSessionMessageInApi(params);
  }
  throw new Error('Save assistant session message is only implemented for api mode.');
}

export async function getNewsList() {
  if (runtimeConfig.dataSourceMode === 'mock') {
    return getNewsListMock();
  }
  throw new Error('Real data source mode is not implemented yet.');
}

export async function analyze(input: AnalysisInput) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return analyzeWithApi(input);
  }
  throw new Error('Analyze is only implemented for api mode.');
}

export async function getKnowledgeBases() {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getKnowledgeBasesFromApi();
  }
  throw new Error('Knowledge base is only implemented for api mode.');
}

export async function getCommandCenter() {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getCommandCenterFromApi();
  }
  throw new Error('Command center is only implemented for api mode.');
}

export async function createKnowledgeBase(body: { name: string; description?: string }) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return createKnowledgeBaseInApi(body);
  }
  throw new Error('Knowledge base is only implemented for api mode.');
}

export async function getKnowledgeFiles(kbId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getKnowledgeFilesFromApi(kbId);
  }
  throw new Error('Knowledge files are only implemented for api mode.');
}

export async function uploadKnowledgeFile(params: {
  kbId: string;
  file: File;
  remark?: string;
  tags?: string[];
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return uploadKnowledgeFileInApi(params);
  }
  throw new Error('Upload knowledge file is only implemented for api mode.');
}

export async function deleteKnowledgeFile(fileId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return deleteKnowledgeFileInApi(fileId);
  }
  throw new Error('Delete knowledge file is only implemented for api mode.');
}

export async function retryKnowledgeFileParse(fileId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return retryKnowledgeFileParseInApi(fileId);
  }
  throw new Error('Retry knowledge file parse is only implemented for api mode.');
}

export async function retryKnowledgeFileIndex(fileId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return retryKnowledgeFileIndexInApi(fileId);
  }
  throw new Error('Retry knowledge file index is only implemented for api mode.');
}

export async function rebuildKnowledgeBaseIndex(kbId: string) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return rebuildKnowledgeBaseIndexInApi(kbId);
  }
  throw new Error('Rebuild knowledge base index is only implemented for api mode.');
}

export async function getRagAnswer(params: {
  query: string;
  kbId?: string;
  sourceUrl?: string;
  platformHint?: string;
  sessionId?: string;
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return getRagAnswerFromApi(params);
  }
  throw new Error('RAG answer is only implemented for api mode.');
}

export async function streamAnalyze(
  input: AnalysisInput,
  handlers?: {
    onChunk?: (chunk: string) => void;
    onError?: (message: string, payload?: Record<string, any>) => void;
    onWarning?: (message: string, payload?: Record<string, any>) => void;
    onStart?: () => void;
    onReady?: () => void;
    onDone?: (payload: Record<string, any>) => void;
    onGrounding?: (payload: Record<string, any>) => void;
    signal?: AbortSignal;
  },
) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return streamAssistantMessageInApi(input, handlers);
  }
  throw new Error('Stream analyze is only implemented for api mode.');
}

export async function searchOverview(params: {
  sessionId: string;
  query: string;
  userPrompt?: string;
  sourceUrl?: string;
  platformHint?: string;
  maxResults?: number;
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return searchOverviewApi(params);
  }
  throw new Error('Search overview is only implemented for api mode.');
}

export async function analyzeRumor(params: {
  sessionId: string;
  query: string;
  userPrompt?: string;
  sourceUrl?: string;
  platformHint?: string;
  maxResults?: number;
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return analyzeRumorApi(params);
  }
  throw new Error('Analyze rumor is only implemented for api mode.');
}

export async function uploadVideoAnalysis(params: {
  sessionId: string;
  file: File;
  query?: string;
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return uploadVideoAnalysisApi(params);
  }
  throw new Error('Upload video analysis is only implemented for api mode.');
}

export async function uploadMultimodalAnalysis(params: {
  sessionId: string;
  files: File[];
  query?: string;
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return uploadMultimodalAnalysisApi(params);
  }
  throw new Error('Upload multimodal analysis is only implemented for api mode.');
}

export async function textToSpeech(params: {
  text: string;
  sessionId?: string;
  voiceId?: string;
  provider?: string;
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return textToSpeechApi(params);
  }
  throw new Error('Text to speech is only implemented for api mode.');
}

export async function textToSpeechAsync(params: {
  sessionId: string;
  messageId: string;
  text: string;
  voiceId?: string;
  provider?: string;
}) {
  if (runtimeConfig.dataSourceMode === 'api') {
    return textToSpeechAsyncApi(params);
  }
  throw new Error('Async text to speech is only implemented for api mode.');
}
