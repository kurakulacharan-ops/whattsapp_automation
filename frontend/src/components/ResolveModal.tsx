import { useState } from 'react';
import { resolveAttendance } from '../api/attendance';
import type { AttendanceRecord } from '../types';

export function ResolveModal({
  record,
  onClose,
  onResolved,
}: {
  record: AttendanceRecord;
  onClose: () => void;
  onResolved: (updated: AttendanceRecord) => void | Promise<void>;
}) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState<'approved' | 'rejected' | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDecision(decision: 'approved' | 'rejected') {
    setSubmitting(decision);
    setError(null);
    try {
      const updated = await resolveAttendance(record._id, decision, reason || undefined);
      await onResolved(updated);
    } catch {
      setError('Could not save this decision. Try again.');
      setSubmitting(null);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div
        className="modal w-full max-w-md p-6"
      >
        <h2 className="text-lg font-extrabold mb-1" style={{ color: 'var(--color-ink)' }}>
          Review flagged submission
        </h2>
        <p className="text-sm mb-4" style={{ color: 'var(--color-ink-muted)' }}>
          {record.employee_id} · {new Date(record.received_at_utc).toLocaleString()}
        </p>

        <div className="text-sm font-medium mb-4 space-y-1" style={{ color: 'var(--color-absent)' }}>
          {record.issues_display.length > 0 ? (
            record.issues_display.map((issue, i) => <p key={i}>· {issue}</p>)
          ) : (
            <p style={{ color: 'var(--color-ink-muted)', fontWeight: 400 }}>No specific issues recorded.</p>
          )}
        </div>

        <label className="field-label">
          Reason (optional)
        </label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          className="w-full mb-4 px-3 py-2 rounded-md text-sm border outline-none resize-none"
          style={{
            background: 'var(--color-surface-sunken)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-ink)',
          }}
        />

        {error && (
          <p className="text-xs mb-3" style={{ color: 'var(--color-absent)' }}>
            {error}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="btn btn-ghost"
          >
            Cancel
          </button>
          <button
            onClick={() => handleDecision('rejected')}
            disabled={submitting !== null}
            className="btn btn-danger"
          >
            {submitting === 'rejected' ? 'Marking absent…' : 'Mark absent'}
          </button>
          <button
            onClick={() => handleDecision('approved')}
            disabled={submitting !== null}
            className="btn btn-success"
          >
            {submitting === 'approved' ? 'Marking present…' : 'Mark present'}
          </button>
        </div>
      </div>
    </div>
  );
}
