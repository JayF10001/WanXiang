import { apiRequest } from './client';
import type { ApiResponse } from '../../types/common';
import type { CommandCenterData } from '../../types/dashboard';

export async function getCommandCenterFromApi(): Promise<CommandCenterData> {
  const response = await apiRequest<ApiResponse<CommandCenterData>>('/dashboard/command-center', {
    timeoutMs: 45000,
  });
  return response.data as CommandCenterData;
}
