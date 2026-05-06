import { apiRequest } from './client';
import type { ApiResponse } from '../../types/common';
import type { RagAnswerResult } from '../../types/rag';

export async function getRagAnswerFromApi(body: {
  query: string;
  kbId?: string;
  sourceUrl?: string;
  platformHint?: string;
  sessionId?: string;
}): Promise<RagAnswerResult> {
  const response = await apiRequest<ApiResponse<RagAnswerResult>>('/rag/answer', {
    method: 'POST',
    body: JSON.stringify(body),
    timeoutMs: 60000,
  });
  return (response.data ?? {}) as RagAnswerResult;
}
