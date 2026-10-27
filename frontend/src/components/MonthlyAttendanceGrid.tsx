import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { getAttendanceGrid, overrideAttendanceCell } from '../api/attendance';
import { listCoordinators } from '../api/coordinators';
import type { AttendanceGridRow, AttendanceRole, Coordinator } from '../types';

const ROLE_OPTIONS: { label: string; value: AttendanceRole | '' }[] = [
  { label: 'All groups', value: '' },
  { label: 'Field Supervisors (FS)', value: 'FS' },
  { label: 'Local Supervisors (LS)', value: 'LS' },
  { label: 'Local Supervisor Scanning (LSS)', value: 'LSS' },
];
const ATTENDANCE_CODES = ['P', 'L', 'A', 'AL', 'HD', 'WO', 'H', 'F', 'M', 'N/A'];
const CODE_LABELS: Record<string, string> = {
  P: 'Present',
  L: 'Late',
  A: 'Absent',
  AL: 'Absent late',
  HD: 'Half day',
  WO: 'Week off',
  H: 'Holiday',
  F: 'Flagged',
  M: 'Manual',
  'N/A': 'Not applicable',
  '—': 'No result',
};

export function MonthlyAttendanceGrid({ onClose, canManage }: { onClose: () => void; canManage: boolean }) {
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [role, setRole] = useState<AttendanceRole | ''>('');
  const [pcId, setPcId] = useState('');
  const [rows, setRows] = useState<AttendanceGridRow[]>([]);
  const [days, setDays] = useState<string[]>([]);
  const [coordinators, setCoordinators] = useState<Coordinator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ row: AttendanceGridRow; date: string } | null>(null);
  const [code, setCode] = useState('P');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const requestSequence = useRef(0);

  const fetchGrid = useCallback(() => getAttendanceGrid({
    month,
    year,
    role: role || undefined,
    pc_id: pcId || undefined,
  }), [month, year, role, pcId]);

  const load = useCallback(async () => {
    const requestId = ++requestSequence.current;
    try {
      const result = await fetchGrid();
      if (requestId === requestSequence.current) {
        setError(null);
        setDays(result.days);
        setRows(result.rows);
      }
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      if (requestId === requestSequence.current) {
        setError(typeof detail === 'string' ? detail : 'Could not load the monthly attendance grid.');
      }
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [fetchGrid]);

  useEffect(() => {
    let active = true;
    const requestId = ++requestSequence.current;
    fetchGrid()
      .then((result) => {
        if (active && requestId === requestSequence.current) {
          setError(null);
          setDays(result.days);
          setRows(result.rows);
        }
      })
      .catch((err: unknown) => {
        const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
        if (active && requestId === requestSequence.current) {
          setError(typeof detail === 'string' ? detail : 'Could not load the monthly attendance grid.');
        }
      })
      .finally(() => {
        if (active && requestId === requestSequence.current) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [fetchGrid]);

  useEffect(() => {
    listCoordinators({ page_size: 1000 })
      .then((result) => setCoordinators(result.coordinators))
      .catch(() => setError('Could not load project co-ordinator filters.'));
  }, []);

  function openCell(row: AttendanceGridRow, date: string) {
    setEditing({ row, date });
    setCode(row.attendance[date] === '—' ? 'P' : row.attendance[date]);
    setReason('');
  }

  async function saveOverride() {
    if (!editing) return;
    setSaving(true);
    setError(null);
    try {
      await overrideAttendanceCell({
        employee_id: editing.row.employee_id,
        date: editing.date,
        attendance_code: code,
        reason: reason.trim() || undefined,
      });
      setEditing(null);
      setLoading(true);
      await load();
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === 'string' ? detail : 'Could not save the attendance change.');
    } finally {
      setSaving(false);
    }
  }

  const parentName = (row: AttendanceGridRow) => {
    if (row.pc_id) {
      return coordinators.find((person) => person.pc_id === row.pc_id)?.name ?? row.pc_id;
    }
    return '—';
  };

  return (
    <section>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div>
          <h1 className="text-lg font-medium" style={{ color: 'var(--color-ink)' }}>Monthly Attendance</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-ink-muted)' }}>
            Automated results remain unchanged unless an admin saves a reasoned cell override.
          </p>
        </div>
        <button
          onClick={onClose}
          className="px-3 py-1.5 rounded-md text-sm border"
          style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}
        >
          Back to submissions
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <select
          value={month}
          onChange={(event) => {
            setLoading(true);
            setError(null);
            setMonth(Number(event.target.value));
          }}
          aria-label="Attendance month"
          className="px-2 py-1.5 rounded-md text-sm border"
          style={{ background: 'var(--color-surface-raised)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
        >
          {Array.from({ length: 12 }, (_, index) => (
            <option key={index + 1} value={index + 1}>
              {new Intl.DateTimeFormat('en', { month: 'long' }).format(new Date(2025, index, 1))}
            </option>
          ))}
        </select>
        <input
          type="number"
          min="2000"
          max="2100"
          value={year}
          onChange={(event) => {
            setLoading(true);
            setError(null);
            setYear(Number(event.target.value));
          }}
          aria-label="Attendance year"
          className="w-24 px-2 py-1.5 rounded-md text-sm border"
          style={{ background: 'var(--color-surface-raised)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
        />
        <select
          value={role}
          onChange={(event) => {
            setLoading(true);
            setError(null);
            setRole(event.target.value as AttendanceRole | '');
          }}
          aria-label="Attendance department"
          className="px-2 py-1.5 rounded-md text-sm border"
          style={{ background: 'var(--color-surface-raised)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
        >
          {ROLE_OPTIONS.map((option) => <option key={option.label} value={option.value}>{option.label}</option>)}
        </select>
        <select
          value={pcId}
          onChange={(event) => {
            setLoading(true);
            setError(null);
            setPcId(event.target.value);
          }}
          aria-label="Filter by project co-ordinator"
          className="px-2 py-1.5 rounded-md text-sm border"
          style={{ background: 'var(--color-surface-raised)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
        >
          <option value="">All project co-ordinators</option>
          {coordinators.map((coordinator) => (
            <option key={coordinator.pc_id} value={coordinator.pc_id}>{coordinator.name}</option>
          ))}
        </select>
      </div>

      {error && <p role="alert" className="mb-3 text-sm" style={{ color: 'var(--color-absent)' }}>{error}</p>}
      <div className="rounded-lg border overflow-auto shadow-sm" style={{ borderColor: 'var(--color-border)' }}>
        <table className="text-sm border-collapse min-w-full">
          <thead>
            <tr style={{ background: 'var(--color-surface-sunken)' }}>
              {['S.No', 'ID', 'Name', 'Group', 'Reports to', ...days].map((header) => (
                <th key={header} className="sticky top-0 px-2 py-2 text-xs font-medium text-left border-b whitespace-nowrap"
                  style={{ background: 'var(--color-surface-sunken)', color: 'var(--color-ink-faint)', borderColor: 'var(--color-border)' }}>
                  {header.length === 10 && header.startsWith('202') ? header.slice(-2) : header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.employee_id} className="border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
                <td className="px-2 py-2 whitespace-nowrap" style={{ color: 'var(--color-ink-muted)' }}>{index + 1}</td>
                <td className="px-2 py-2 whitespace-nowrap" style={{ color: 'var(--color-ink-muted)' }}>{row.employee_id}</td>
                <td className="px-2 py-2 whitespace-nowrap" style={{ color: 'var(--color-ink)' }}>{row.name}</td>
                <td className="px-2 py-2 whitespace-nowrap" style={{ color: 'var(--color-ink-muted)' }}>{row.role}</td>
                <td className="px-2 py-2 whitespace-nowrap" style={{ color: 'var(--color-ink-muted)' }}>{parentName(row)}</td>
                {days.map((date) => {
                  const marker = row.attendance[date] ?? '—';
                  return (
                    <td key={date} className="px-1 py-1 text-center">
                      {canManage ? <button
                        type="button"
                        onClick={() => openCell(row, date)}
                        title={`${date}: ${CODE_LABELS[marker] ?? marker}. Click to edit.`}
                        aria-label={`${row.name} ${date} attendance ${marker}; edit`}
                        className="min-w-9 rounded px-1.5 py-1 text-xs font-medium hover:ring-1 hover:ring-[var(--color-accent)]"
                        style={{
                          color: ['F', 'A', 'AL'].includes(marker) ? 'var(--color-absent)' : 'var(--color-ink)',
                          background: ['F', 'A', 'AL'].includes(marker) ? 'var(--color-absent-bg)' : 'var(--color-surface-sunken)',
                        }}
                      >
                        {marker}
                      </button> : <span
                        title={`${date}: ${CODE_LABELS[marker] ?? marker}`}
                        className="inline-block min-w-9 rounded px-1.5 py-1 text-xs font-medium"
                        style={{
                          color: ['F', 'A', 'AL'].includes(marker) ? 'var(--color-absent)' : 'var(--color-ink)',
                          background: ['F', 'A', 'AL'].includes(marker) ? 'var(--color-absent-bg)' : 'var(--color-surface-sunken)',
                        }}
                      >{marker}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={5 + days.length} className="px-4 py-8 text-center" style={{ color: 'var(--color-ink-faint)' }}>No attendance participants found.</td></tr>
            )}
          </tbody>
        </table>
        {loading && <p className="p-4 text-sm" style={{ color: 'var(--color-ink-muted)' }}>Loading monthly attendance…</p>}
      </div>
      <p className="mt-2 text-xs" style={{ color: 'var(--color-ink-muted)' }}>
        Total attendance participants: {rows.length}
      </p>

      {canManage && editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-md rounded-lg border p-5 shadow-xl" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}>
            <h2 className="text-base font-medium mb-1" style={{ color: 'var(--color-ink)' }}>Edit attendance</h2>
            <p className="text-sm mb-4" style={{ color: 'var(--color-ink-muted)' }}>
              {editing.row.name} · {editing.row.employee_id} · {editing.date}
            </p>
            <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>Attendance code</label>
            <select value={code} onChange={(event) => setCode(event.target.value)} className="w-full px-3 py-2 rounded-md text-sm border mb-3"
              style={{ background: 'var(--color-surface-sunken)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}>
              {ATTENDANCE_CODES.map((value) => <option key={value} value={value}>{value} — {CODE_LABELS[value]}</option>)}
            </select>
            <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>Reason for change (optional)</label>
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3}
              className="w-full px-3 py-2 rounded-md text-sm border resize-y"
              style={{ background: 'var(--color-surface-sunken)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setEditing(null)} className="px-3 py-1.5 rounded-md text-sm" style={{ color: 'var(--color-ink-muted)' }}>Cancel</button>
              <button onClick={() => void saveOverride()} disabled={saving}
                className="px-3 py-1.5 rounded-md text-sm font-medium text-white disabled:opacity-50"
                style={{ background: 'var(--color-accent)' }}>
                {saving ? 'Saving…' : 'Save override'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
