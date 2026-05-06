export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  message: string;
  errorCode?: string;
}

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error';
