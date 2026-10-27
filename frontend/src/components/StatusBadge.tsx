import type { AttendanceRecord, ReviewStatus, ShiftStatus, Verdict } from '../types';

// Single source of truth for status -> {label, color} across the app. If the
// backend adds a new value to any of these enums, TS will flag every switch
// below as non-exhaustive (see the `never` fallthrough) instead of silently
// rendering nothing.
function badge(label: string, fg: string, bg: string) {
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
      style={{ color: fg, background: bg }}
    >
      {label}
    </span>
  );
}

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  switch (verdict) {
    case 'verified':
      return badge('Verified', 'var(--color-present)', 'var(--color-present-bg)');
    case 'flagged':
      return badge('Flagged', 'var(--color-flagged)', 'var(--color-flagged-bg)');
    case 'inactive_account':
      return badge('Inactive account', 'var(--color-inactive)', 'var(--color-inactive-bg)');
    default: {
      const _exhaustive: never = verdict;
      return _exhaustive;
    }
  }
}

export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  switch (status) {
    case 'n/a':
      return badge('—', 'var(--color-ink-faint)', 'transparent');
    case 'pending':
      return badge('Pending review', 'var(--color-flagged)', 'var(--color-flagged-bg)');
    case 'approved':
      return badge('Approved', 'var(--color-present)', 'var(--color-present-bg)');
    case 'rejected':
      return badge('Rejected', 'var(--color-absent)', 'var(--color-absent-bg)');
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

// Face-match UI, by explicit backend policy, never shows identity_score or
// any percentage/progress-bar — pass/fail-style labels only. We also still
// don't have the documented value set for identity_verdict, so rather than
// guess a color mapping for values we haven't confirmed, this renders the
// verdict string as-is in neutral styling and leans on face_present/
// entry_type for the cases we DO know how to interpret confidently.

export function AttendanceStatusBadge({ status }: { status: AttendanceRecord['attendance_status'] }) {
  switch (status) {
    case 'present':
      return badge('P · Present', 'var(--color-present)', 'var(--color-present-bg)');
    case 'pending':
      return badge('F · Flagged', 'var(--color-flagged)', 'var(--color-flagged-bg)');
    case 'absent':
      return badge('A · Absent', 'var(--color-absent)', 'var(--color-absent-bg)');
    case null:
      return badge('—', 'var(--color-ink-faint)', 'transparent');
  }
}

export function FaceMatchStatus({ record }: { record: AttendanceRecord }) {
  if (record.entry_type === 'manual' || record.face_present === null) {
    return badge('Skipped (manual entry)', 'var(--color-ink-faint)', 'transparent');
  }
  if (record.face_present === false) {
    return badge('No face detected', 'var(--color-absent)', 'var(--color-absent-bg)');
  }
  if (!record.identity_verdict) {
    return badge('—', 'var(--color-ink-faint)', 'transparent');
  }
  // Neutral styling until backend confirms the identity_verdict enum — once
  // we know the values, split this into a proper switch like the others above.
  return badge(record.identity_verdict, 'var(--color-ink-muted)', 'var(--color-surface-raised)');
}

export function ShiftStatusBadge({ status, skipped }: { status: ShiftStatus | undefined; skipped?: boolean }) {
  // Backend appears to only set shift_status for the exceptional cases
  // (late, before/after window, unparseable) and leaves it null/undefined
  // for a normal on-time submission — so anything not explicitly one of the
  // known exceptions is treated as on-time, rather than rendering blank.
  // Manual entries are the one real exception: the shift check was
  // deliberately skipped, not assumed on-time, so that's called out separately.
  if (skipped) {
    return badge('Skipped (manual entry)', 'var(--color-ink-faint)', 'transparent');
  }
  switch (status) {
    case 'late':
      return badge('Late', 'var(--color-late)', 'var(--color-late-bg)');
    case 'after_grace':
      return badge('After grace', 'var(--color-absent)', 'var(--color-absent-bg)');
    case 'before_window':
      return badge('Before shift', 'var(--color-ink-muted)', 'var(--color-surface-raised)');
    case 'after_window':
      return badge('After shift', 'var(--color-ink-muted)', 'var(--color-surface-raised)');
    case 'unparseable':
      return badge('Unparseable', 'var(--color-absent)', 'var(--color-absent-bg)');
    default:
      return badge('On time', 'var(--color-present)', 'var(--color-present-bg)');
  }
}