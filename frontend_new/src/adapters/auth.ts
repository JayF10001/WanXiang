import type { User } from '../types/auth';

export function adaptCurrentUser(raw: any): User {
  return {
    id: String(raw?.user_id ?? raw?.id ?? ''),
    name: String(raw?.username ?? raw?.name ?? ''),
    email: String(raw?.email ?? ''),
    role: raw?.role === 'admin' ? 'admin' : 'user',
    avatar: raw?.avatar_url ?? raw?.avatar,
  };
}
