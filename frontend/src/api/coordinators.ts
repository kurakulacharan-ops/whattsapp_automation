import { apiClient } from './client';
import type { AssignedSite, Coordinator, PageMeta } from '../types';

export type CoordinatorAttendanceSettings = {
  assigned_site?: AssignedSite | null;
  geofence_radius_km?: number;
  shift_start?: string | null;
  shift_end?: string | null;
  shift_grace_minutes?: number | null;
};

export interface CoordinatorListParams {
  pc_id?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
  search?: string;
}

export interface CoordinatorListResult extends PageMeta {
  coordinators: Coordinator[];
}

export async function listCoordinators(params?: CoordinatorListParams) {
  const { data } = await apiClient.get<CoordinatorListResult>('/coordinators', { params });
  return data;
}

export async function createCoordinator(
  payload: { name: string; phone_number?: string } & CoordinatorAttendanceSettings
) {
  const { data } = await apiClient.post<Coordinator>('/coordinators', payload);
  return data;
}

export async function updateCoordinator(
  pc_id: string,
  payload: Partial<Pick<Coordinator, 'name' | 'phone_number' | 'is_active'>> &
    CoordinatorAttendanceSettings
) {
  const { data } = await apiClient.patch<Coordinator>(`/coordinators/${pc_id}`, payload);
  return data;
}

export async function deleteCoordinator(pc_id: string) {
  await apiClient.delete(`/coordinators/${pc_id}`);
}
