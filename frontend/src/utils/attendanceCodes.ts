import type { AttendanceRecord } from '../types';

// One source of truth for attendance codes. Colors mirror the Excel export
// legend (backend MARKER_FILLS) so on-screen and exported sheets read alike.
export interface CodeMeta { label: string; fg: string; bg: string; solid: string }

export const CODE_META: Record<string, CodeMeta> = {
  P:   { label: 'Present',        fg: '#1f6b24', bg: '#c6efce', solid: '#4caf50' },
  L:   { label: 'Late',           fg: '#0b6aa6', bg: '#d6eaf8', solid: '#4aa3df' },
  M:   { label: 'Manual present', fg: '#1f6b24', bg: '#d9f2dc', solid: '#86c98b' },
  H:   { label: 'Holiday',        fg: '#3d6b2f', bg: '#d9ead3', solid: '#a9cf9a' },
  HD:  { label: 'Half day',       fg: '#8a4f0c', bg: '#ffe4b5', solid: '#f2b45a' },
  F:   { label: 'Flagged',        fg: '#7a5200', bg: '#ffeb9c', solid: '#f0c419' },
  A:   { label: 'Absent',         fg: '#a61e2b', bg: '#ffc7ce', solid: '#e5535f' },
  AL:  { label: 'Absent late',    fg: '#8f1020', bg: '#ff9999', solid: '#c8283a' },
  WO:  { label: 'Week off',       fg: '#4b5563', bg: '#dcdfe4', solid: '#aab1bd' },
  'N/A': { label: 'Not applicable', fg: '#4b5563', bg: '#e6e9ef', solid: '#c5cbd6' },
  '—': { label: 'No result yet',  fg: '#b3bccb', bg: 'transparent', solid: '#e3e7ee' },
};

export const codeMeta = (code: string): CodeMeta => CODE_META[code] ?? CODE_META['—'];

// Same logic as before, moved here so the table and analytics agree.
export function attendanceMarker(record: AttendanceRecord): string {
  if (record.attendance_code) return record.attendance_code;
  if (record.verdict === 'inactive_account') return 'N/A';
  if (record.review_status === 'rejected') return 'A';
  if (record.verdict === 'flagged' && record.review_status !== 'approved') return 'F';
  if (record.shift_status === 'after_window' || record.attendance_status === 'absent_late') return 'AL';
  if (record.shift_status === 'late' || record.attendance_status === 'late') return 'L';
  if (record.attendance_status === 'absent') return 'A';
  if (record.attendance_status === 'pending') return 'F';
  return record.verdict === 'verified' ? 'P' : 'F';
}

export interface CodeTally { counts: Record<string, number>; present: number; absent: number; rate: number | null; working: number }

// Mirrors Excel totals: Present = P+L+M, Absent = A+AL. Half days count 0.5.
// WO, H, N/A, F (awaiting review) and "no result" stay out of the denominator.
export function tally(codes: Iterable<string>): CodeTally {
  const counts: Record<string, number> = {};
  for (const c of codes) counts[c] = (counts[c] ?? 0) + 1;
  const present = (counts.P ?? 0) + (counts.L ?? 0) + (counts.M ?? 0);
  const absent = (counts.A ?? 0) + (counts.AL ?? 0);
  const hd = counts.HD ?? 0;
  const working = present + absent + hd;
  return { counts, present, absent, working, rate: working ? ((present + hd * 0.5) / working) * 100 : null };
}

// Stacking order for charts: good outcomes at the base, problems on top.
export const STACK_ORDER = ['P', 'M', 'L', 'HD', 'F', 'AL', 'A'] as const;
