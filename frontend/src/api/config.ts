import { apiClient } from './client';
import type { AppConfig } from '../types';

export async function getConfig() {
  const { data } = await apiClient.get<AppConfig>('/config');
  return data;
}
