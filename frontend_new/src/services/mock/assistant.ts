import {
  adaptBrief,
  adaptChatMessages,
  adaptChatSessions,
  adaptDataPreview,
  adaptRecommendationCards,
  adaptReport,
  adaptStrategy,
} from '../../adapters/assistant';
import {
  assistantHomeRawMock,
  assistantMessagesRawMock,
  assistantPanelsRawMock,
  assistantSessionsRawMock,
} from '../../mocks/assistant';
import type {
  AIBrief,
  AIDataPreviewItem,
  AIRecommendationCard,
  AIReport,
  AIStrategy,
  ChatMessage,
  ChatSession,
} from '../../types/assistant';

export async function getAssistantHomeMock(): Promise<{
  recommendationCards: AIRecommendationCard[];
  defaultModel: string;
  suggestedPrompts: string[];
}> {
  return {
    recommendationCards: adaptRecommendationCards(assistantHomeRawMock),
    defaultModel: assistantHomeRawMock.default_model,
    suggestedPrompts: assistantHomeRawMock.suggested_prompts,
  };
}

export async function getAssistantSessionsMock(): Promise<{
  sessions: ChatSession[];
  activeSessionId: string | null;
}> {
  return {
    sessions: adaptChatSessions(assistantSessionsRawMock),
    activeSessionId: assistantSessionsRawMock.active_session_id ?? null,
  };
}

export async function getAssistantMessagesMock(sessionId: string): Promise<ChatMessage[]> {
  return adaptChatMessages(assistantMessagesRawMock, sessionId);
}

export async function getAssistantPanelsMock(sessionId: string): Promise<{
  dataPreview: AIDataPreviewItem[];
  brief: AIBrief | null;
  report: AIReport | null;
  strategy: AIStrategy | null;
}> {
  return {
    dataPreview: adaptDataPreview(assistantPanelsRawMock, sessionId),
    brief: adaptBrief(assistantPanelsRawMock, sessionId),
    report: adaptReport(assistantPanelsRawMock, sessionId),
    strategy: adaptStrategy(assistantPanelsRawMock, sessionId),
  };
}
