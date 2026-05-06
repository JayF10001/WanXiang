import { apiRequest } from './client';
import type { ApiResponse } from '../../types/common';
import type { KnowledgeBase, KnowledgeFile } from '../../types/knowledge';

export async function getKnowledgeBasesFromApi(): Promise<KnowledgeBase[]> {
  const response = await apiRequest<ApiResponse<KnowledgeBase[]>>('/knowledge-bases');
  return response.data as KnowledgeBase[];
}

export async function createKnowledgeBaseInApi(body: { name: string; description?: string }): Promise<KnowledgeBase> {
  const response = await apiRequest<ApiResponse<KnowledgeBase>>('/knowledge-bases', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return response.data as KnowledgeBase;
}

export async function getKnowledgeFilesFromApi(kbId: string): Promise<KnowledgeFile[]> {
  const response = await apiRequest<ApiResponse<KnowledgeFile[]>>(`/knowledge-bases/${kbId}/files`);
  return response.data as KnowledgeFile[];
}

export async function uploadKnowledgeFileInApi(params: {
  kbId: string;
  file: File;
  remark?: string;
  tags?: string[];
}): Promise<KnowledgeFile> {
  const form = new FormData();
  form.append('file', params.file);
  if (params.remark) {
    form.append('remark', params.remark);
  }
  if (params.tags && params.tags.length > 0) {
    form.append('tags', JSON.stringify(params.tags));
  }

  const response = await apiRequest<ApiResponse<KnowledgeFile>>(`/knowledge-bases/${params.kbId}/files`, {
    method: 'POST',
    body: form,
    timeoutMs: 60000,
  });
  return response.data as KnowledgeFile;
}

export async function deleteKnowledgeFileInApi(fileId: string): Promise<{ id: string }> {
  const response = await apiRequest<ApiResponse<{ id: string }>>(`/knowledge-files/${fileId}`, {
    method: 'DELETE',
  });
  return response.data as { id: string };
}

export async function retryKnowledgeFileParseInApi(fileId: string): Promise<KnowledgeFile> {
  const response = await apiRequest<ApiResponse<KnowledgeFile>>(`/knowledge-files/${fileId}/retry-parse`, {
    method: 'POST',
    timeoutMs: 120000,
  });
  return response.data as KnowledgeFile;
}

export async function retryKnowledgeFileIndexInApi(fileId: string): Promise<KnowledgeFile> {
  const response = await apiRequest<ApiResponse<KnowledgeFile>>(`/knowledge-files/${fileId}/retry-index`, {
    method: 'POST',
    timeoutMs: 120000,
  });
  return response.data as KnowledgeFile;
}

export async function rebuildKnowledgeBaseIndexInApi(kbId: string): Promise<{
  kbId: string;
  totalFiles: number;
  parseQueued: number;
  indexQueued: number;
  queuedCount: number;
}> {
  const response = await apiRequest<ApiResponse<{
    kbId: string;
    totalFiles: number;
    parseQueued: number;
    indexQueued: number;
    queuedCount: number;
  }>>(`/knowledge-bases/${kbId}/rebuild-index`, {
    method: 'POST',
  });
  return response.data as {
    kbId: string;
    totalFiles: number;
    parseQueued: number;
    indexQueued: number;
    queuedCount: number;
  };
}
