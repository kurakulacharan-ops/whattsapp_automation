import { useState } from 'react';
import { downloadExport } from '../api/attendance';
import type { Coordinator } from '../types';

const now = new Date();

export function ExportPanel({
  coordinators,
  onClose,
}: {
  coordinators: Coordinator[];
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
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setDownloading(true);
    setError(null);
    try {
      if (mode === 'month') {
        await downloadExport({ month, year, pc_id: pcId || undefined });
      } else {
        await downloadExport({ date_from: dateFrom, date_to: dateTo, pc_id: pcId || undefined });
      }
      onClose();
    } catch {
      setError('Export failed. Try a narrower range.');
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div
        className="w-full max-w-sm rounded-lg border p-6 shadow-xl"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}
      >
        <h2 className="text-base font-medium mb-4" style={{ color: 'var(--color-ink)' }}>
          Export to Excel
        </h2>

        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setMode('month')}
            className="flex-1 px-3 py-1.5 rounded-md text-xs border"
            style={{
              borderColor: mode === 'month' ? 'var(--color-accent)' : 'var(--color-border)',
              color: mode === 'month' ? 'var(--color-accent)' : 'var(--color-ink-muted)',
            }}
          >
            By month
          </button>
          <button
            onClick={() => setMode('range')}
            className="flex-1 px-3 py-1.5 rounded-md text-xs border"
            style={{
              borderColor: mode === 'range' ? 'var(--color-accent)' : 'var(--color-border)',
              color: mode === 'range' ? 'var(--color-accent)' : 'var(--color-ink-muted)',
            }}
          >
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

        <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>
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
          <button onClick={onClose} className="px-3 py-1.5 rounded-md text-sm" style={{ color: 'var(--color-ink-muted)' }}>
            Cancel
          </button>
          <button
            onClick={handleExport}
            disabled={downloading || (mode === 'range' && (!dateFrom || !dateTo))}
            className="px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
            style={{ background: 'var(--color-accent)', color: 'white' }}
          >
            {downloading ? 'Preparing…' : 'Download .xlsx'}
          </button>
        </div>
      </div>
    </div>
  );
}
