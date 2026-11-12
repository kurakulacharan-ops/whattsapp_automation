import { useState } from 'react';
import { createPortal } from 'react-dom';
import { downloadExport } from '../api/attendance';
import type { Coordinator } from '../types';

const now = new Date();

export function ExportPanel({
  coordinators,
  includeCoordinatorAttendance: initialIncludeCoordinatorAttendance,
  onClose,
}: {
  coordinators: Coordinator[];
  includeCoordinatorAttendance: boolean;
  onClose: () => void;
}) {
  // The API accepts EITHER month+year OR a date range, never both — the mode
  // toggle here exists so the UI can't accidentally send both.
  const [mode, setMode] = useState<'month' | 'range'>('month');
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [pcId, setPcId] = useState('');
  const [includeCoordinatorAttendance, setIncludeCoordinatorAttendance] = useState(initialIncludeCoordinatorAttendance);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setDownloading(true);
    setError(null);
    try {
      if (mode === 'month') {
        await downloadExport({ month, year, pc_id: pcId || undefined, include_coordinator_attendance: includeCoordinatorAttendance });
      } else {
        await downloadExport({ date_from: dateFrom, date_to: dateTo, pc_id: pcId || undefined, include_coordinator_attendance: includeCoordinatorAttendance });
      }
      onClose();
    } catch {
      setError('Export failed. Try a narrower range.');
    } finally {
      setDownloading(false);
    }
  }

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Export to Excel"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflowY: 'auto',
        padding: '1rem',
        boxSizing: 'border-box',
        background: 'rgba(12, 31, 63, 0.68)',
        backdropFilter: 'blur(3px)',
      }}
    >
      <div
        className="attendance-export-dialog"
        style={{
          position: 'relative',
          display: 'block',
          flex: '0 0 auto',
          width: 'min(36rem, calc(100vw - 2rem))',
          maxWidth: '100%',
          maxHeight: 'calc(100vh - 2rem)',
          overflowY: 'auto',
          boxSizing: 'border-box',
          padding: '1.5rem',
          background: '#fff',
          color: '#12203a',
          border: '1px solid #dfe5ee',
          borderRadius: '1.15rem',
          boxShadow: '0 24px 60px -12px rgba(12, 31, 63, 0.45)',
          transform: 'none',
          animation: 'none',
          opacity: 1,
        }}
      >
        <h2 className="text-lg font-extrabold mb-4" style={{ color: 'var(--color-ink)' }}>
          Export to Excel
        </h2>

        <div className="flex gap-2 mb-4">
          <button onClick={() => setMode('month')} aria-pressed={mode === 'month'} className="chip flex-1">
            By month
          </button>
          <button onClick={() => setMode('range')} aria-pressed={mode === 'range'} className="chip flex-1">
            Date range
          </button>
        </div>

        {mode === 'month' ? (
          <div className="flex gap-2 mb-4">
            <select
              value={month}
              onChange={(e) => setMonth(Number(e.target.value))}
              className="flex-1 px-2 py-1.5 rounded-md text-sm border"
              style={{
                background: 'var(--color-surface-sunken)',
                borderColor: 'var(--color-border)',
                color: 'var(--color-ink)',
              }}
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>
                  {new Date(2000, m - 1).toLocaleString(undefined, { month: 'long' })}
                </option>
              ))}
            </select>
            <input
              type="number"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="w-24 px-2 py-1.5 rounded-md text-sm border"
              style={{
                background: 'var(--color-surface-sunken)',
                borderColor: 'var(--color-border)',
                color: 'var(--color-ink)',
              }}
            />
          </div>
        ) : (
          <div className="flex gap-2 mb-4">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="flex-1 px-2 py-1.5 rounded-md text-sm border"
              style={{
                background: 'var(--color-surface-sunken)',
                borderColor: 'var(--color-border)',
                color: 'var(--color-ink)',
              }}
            />
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="flex-1 px-2 py-1.5 rounded-md text-sm border"
              style={{
                background: 'var(--color-surface-sunken)',
                borderColor: 'var(--color-border)',
                color: 'var(--color-ink)',
              }}
            />
          </div>
        )}

        <label className="field-label">
          Coordinator (optional — narrows to one)
        </label>
        <select
          value={pcId}
          onChange={(e) => setPcId(e.target.value)}
          className="w-full mb-4 px-2 py-1.5 rounded-md text-sm border"
          style={{
            background: 'var(--color-surface-sunken)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-ink)',
          }}
        >
          <option value="">All coordinators</option>
          {coordinators.map((c) => (
            <option key={c.pc_id} value={c.pc_id}>
              {c.name}
            </option>
          ))}
        </select>

        <label className="flex items-center gap-2 mb-4 text-sm font-semibold cursor-pointer" style={{ color: 'var(--color-ink-muted)' }}>
          <input
            type="checkbox"
            checked={includeCoordinatorAttendance}
            onChange={(event) => setIncludeCoordinatorAttendance(event.target.checked)}
          />
          Include project coordinator attendance sheet
        </label>

        <div
          className="text-xs mb-4 px-3 py-2 rounded-md space-y-0.5"
          style={{ background: 'var(--color-surface-sunken)', color: 'var(--color-ink-faint)' }}
        >
          <p>P/L present · F flagged · A absent (past dates only) · N/A inactive · blank = no data yet</p>
          <p>Each sheet includes Total Present (P+L) and Total Absent (A only) columns.</p>
        </div>

        {error && (
          <p className="text-xs mb-3" style={{ color: 'var(--color-absent)' }}>
            {error}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn btn-ghost">
            Cancel
          </button>
          <button
            onClick={handleExport}
            disabled={downloading || (mode === 'range' && (!dateFrom || !dateTo))}
            className="btn btn-primary"
          >
            {downloading ? 'Preparing…' : 'Download .xlsx'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
