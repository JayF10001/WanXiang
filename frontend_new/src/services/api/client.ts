import { runtimeConfig } from '../../config/runtime';

type ApiRequestOptions = RequestInit & {
  timeoutMs?: number;
};

export class ApiError extends Error {
  status: number;
  payload: any;

  constructor(message: string, status: number, payload: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { timeoutMs = 15000, ...requestOptions } = options;
  const controller = new AbortController();
  const externalSignal = requestOptions.signal;
  const abortFromExternalSignal = () => controller.abort();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener('abort', abortFromExternalSignal, { once: true });
    }
  }

  const headers = new Headers((requestOptions.headers ?? {}) as HeadersInit);
  if (!(requestOptions.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${runtimeConfig.frontendApiBaseUrl}${path}`, {
    credentials: 'include',
    headers,
    signal: controller.signal,
    ...requestOptions,
  }).catch((error) => {
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (externalSignal?.aborted) {
        throw error;
      }
      throw new Error('请求超时，请稍后重试');
    }
    throw error;
  }).finally(() => {
    window.clearTimeout(timeoutId);
    externalSignal?.removeEventListener('abort', abortFromExternalSignal);
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload?.success === false) {
    throw new ApiError(
      payload?.detail || payload?.message || payload?.error || '请求失败',
      response.status,
      payload,
    );
  }
  return payload;
}
