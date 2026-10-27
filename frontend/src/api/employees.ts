import { apiClient } from './client';
import type { AttendanceRole, Employee, PageMeta } from '../types';

export interface EmployeeListParams {
  pc_id?: string;
  area?: string;
  designation?: string;
  role?: Exclude<AttendanceRole, 'PC'>;
  parent_employee_id?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
  search?: string;
}

export interface EmployeeListResult extends PageMeta {
  employees: Employee[];
}

export async function listEmployees(params?: EmployeeListParams) {
  const { data } = await apiClient.get<EmployeeListResult>('/employees', { params });
  return data;
}

export interface CreateEmployeePayload {
  phone_number: string;
  name: string;
  role: Exclude<AttendanceRole, 'PC'>;
  pc_id?: string;
  parent_employee_id?: string;
  area?: string;
  designation?: string;
  location_check_enabled?: boolean;
  assigned_site?: {
    name: string;
    lat: number;
    long: number;
    city?: string | null;
    district?: string | null;
    district_id?: string | null;
    dataset_id?: string | null;
    match_level?: 'city' | 'district';
  } | null;
  geofence_radius_km?: number;
  shift_start?: string | null;
  shift_end?: string | null;
  shift_grace_minutes?: number | null;
}

export async function createEmployee(payload: CreateEmployeePayload) {
  const { data } = await apiClient.post<Employee>('/employees', payload);
  return data;
}

export async function updateEmployee(
  employee_id: string,
  payload: Partial<CreateEmployeePayload & { is_active: boolean }>
) {
  const { data } = await apiClient.patch<Employee>(`/employees/${employee_id}`, payload);
  return data;
}

export async function deleteEmployee(employee_id: string) {
  await apiClient.delete(`/employees/${employee_id}`);
}

export async function enrollFace(employee_id: string, photos: File[]) {
  const form = new FormData();
  form.append('employee_id', employee_id);
  photos.forEach((photo) => form.append('photos', photo));
  const { data } = await apiClient.post<{
    status: string;
    employee_id: string;
    name: string;
    embeddings_stored: number;
  }>('/enroll-face', form, { headers: { 'Content-Type': 'multipart/form-data' } });
  return data;
}
