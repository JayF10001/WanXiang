export type UserRole = 'admin' | 'user';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
}

export interface LoginForm {
  email: string;
  password: string;
  type?: string;
}

export interface RegisterForm {
  email: string;
  password: string;
  username: string;
  inviteCode?: string;
}
