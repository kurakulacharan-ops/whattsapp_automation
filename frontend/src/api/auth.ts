import axios from 'axios';
import { apiClient } from './client';
import type { AccountRole, LoginResponse, UserAccount } from '../types';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api';

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await axios.post<LoginResponse>(
    `${baseURL}/auth/login`,
    { username, password }
  );
  return data;
}

export async function getCurrentUser(): Promise<Pick<UserAccount, 'username' | 'role'>> {
  const { data } = await apiClient.get<Pick<UserAccount, 'username' | 'role'>>('/auth/me');
  return data;
}

export async function listUsers(): Promise<UserAccount[]> {
  const { data } = await apiClient.get<{ users: UserAccount[] }>('/auth/users');
  return data.users;
}

export async function registerUser(payload: {
  username: string;
  password: string;
  role: Extract<AccountRole, 'manual_team' | 'viewer'>;
}): Promise<UserAccount> {
  const { data } = await apiClient.post<UserAccount>('/auth/users', payload);
  return data;
}
