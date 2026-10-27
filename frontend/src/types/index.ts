export interface Coordinator {
  pc_id: string;
  name: string;
  phone_number?: string;
  is_active: boolean;
  deactivated_at: string | null;
}

export interface PageMeta {
  count: number;
  total: number;
  page: number;
  page_size: number;
}

export interface AssignedSite {
  name: string;
  lat: number;
  long: number;
  city?: string | null;
  district?: string | null;
  district_id?: string | null;
  dataset_id?: string | null;
  match_level?: 'city' | 'district';
}

export interface Employee {
  employee_id: string;
  phone_number: string;
  name: string;
  is_active: boolean;
  deactivated_at: string | null;
  role: AttendanceRole;
  pc_id: string | null;
  parent_employee_id: string | null;
  area: string | null;
  designation: string | null;
  location_check_enabled?: boolean;
  assigned_site: AssignedSite | null;
  geofence_radius_km: number;
  shift_start: string | null;
  shift_end: string | null;
  shift_grace_minutes: number | null;
}

export type AttendanceRole = 'FS' | 'LS' | 'LSS';

export interface AttendanceGridRow {
  employee_id: string;
  name: string;
  role: AttendanceRole;
  pc_id: string | null;
  parent_employee_id: string | null;
  area: string | null;
  designation: string | null;
  is_active: boolean;
  attendance: Record<string, string>;
}

export interface AttendanceGrid {
  month: number;
  year: number;
  days: string[];
  rows: AttendanceGridRow[];
}

export type ShiftStatus =
  | 'on_time'
  | 'late'
  | 'after_grace'
  | 'before_window'
  | 'after_window'
  | 'unparseable'
  | null;

export type Verdict = 'verified' | 'flagged' | 'inactive_account';

export type ReviewStatus = 'n/a' | 'pending' | 'approved' | 'rejected';

export type EntryType = 'whatsapp' | 'manual' | 'system';

export interface AttendanceRecord {
  _id: string;
  employee_id: string;
  employee_name?: string | null;
  person_role?: AttendanceRole | null;
  sender_phone: string | null;
  caption: string | null;
  media_url: string | null;
  image_hash: string | null;
  overlay: Record<string, unknown> | null;
  geofence_passed: boolean | null;
  geofence_distance_m: number | null;
  geofence_radius_meters?: number | null;
  face_present: boolean | null;
  face_count: number | null;
  identity_verdict: string | null;
  identity_score: number | null;
  shift_status: ShiftStatus;
  attendance_date?: string;
  photo_date?: string;
  photo_timestamp?: string;
  attendance_code?: string;
  check_in_at_ist?: string | null;
  geofence_display?: string;
  location_match_status?: 'disabled' | 'in_range' | 'in_area' | 'out_of_area' | 'unavailable' | null;
  location_match_level?: 'city' | 'district' | null;
  attendance_city?: string | null;
  attendance_district?: string | null;
  expected_city?: string | null;
  expected_district?: string | null;
  review_display?: string;
  attendance_status: 'present' | 'absent' | 'pending' | 'late' | 'absent_late' | null;
  flag_reason: string | null;
  verdict: Verdict;
  review_status: ReviewStatus;
  issues: string[];
  issues_display: string[];
  previous_flagged_attempts?: {
    submission_id: string;
    event_id?: string | null;
    attendance_date?: string | null;
    photo_date?: string | null;
    flag_reason?: string | null;
    issues: string[];
    issues_display?: string[];
    received_at_utc?: string | null;
  }[];
  entry_type: EntryType;
  created_by: string | null;
  reason: string | null;
  received_at_utc: string;
}

export type AccountRole = 'super_admin' | 'manual_team' | 'viewer';

export interface AdminUser {
  username: string;
  role: AccountRole;
  pc_id: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
  role: AccountRole;
}

export interface UserAccount {
  username: string;
  role: AccountRole;
  is_active: boolean;
}

export interface AppConfig {
  geofence_radius_meters: number;
  shift_window_start: string;
  shift_window_end: string;
  shift_grace_minutes: number;
  duplicate_hash_hamming_threshold: number;
}
