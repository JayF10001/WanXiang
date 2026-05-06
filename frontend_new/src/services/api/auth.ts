import { apiRequest } from './client';
import type { LoginForm, RegisterForm, User } from '../../types/auth';
import type { ApiResponse } from '../../types/common';

export async function loginWithApi(body: LoginForm): Promise<User> {
  const response = await apiRequest<ApiResponse<User>>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return response.data as User;
}

export async function registerWithApi(body: RegisterForm): Promise<User> {
  const response = await apiRequest<ApiResponse<User>>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return response.data as User;
}

export async function getCurrentUserFromApi(): Promise<User> {
  const response = await apiRequest<ApiResponse<User>>('/auth/current-user');
  return response.data as User;
}

export async function logoutFromApi(): Promise<void> {
  await apiRequest<ApiResponse<Record<string, never>>>('/auth/logout', {
    method: 'POST',
  });
}
