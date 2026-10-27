import { useEffect, useState, useCallback } from 'react';
import { deleteAttendance, listAttendance, overrideAttendanceCell } from '../api/attendance';
import { listCoordinators } from '../api/coordinators';
import { listEmployees } from '../api/employees';
import type { AttendanceRecord, Coordinator, Employee, Verdict } from '../types';
import { ReviewStatusBadge, ShiftStatusBadge, FaceMatchStatus } from '../components/StatusBadge';
import { ResolveModal } from '../components/ResolveModal';
import { ExportPanel } from '../components/ExportPanel';
import { ManualEntryModal } from '../components/ManualEntryModal';
import { MonthlyAttendanceGrid } from '../components/MonthlyAttendanceGrid';
import { Pencil, Trash2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const VERDICT_FILTERS: { label: string; value: Verdict | '' }[] = [
  { label: 'All', value: '' },
  { label: 'Verified', value: 'verified' },
  { label: 'Flagged', value: 'flagged' },
  { label: 'Inactive account', value: 'inactive_account' },
];

const PAGE_SIZE = 25;
const STATUS_OVERRIDE_OPTIONS = [
  ['P', 'Present'],
  ['L', 'Late'],
  ['A', 'Absent'],
  ['AL', 'Absent late'],
  ['HD', 'Half day'],
  ['WO', 'Week off'],
  ['H', 'Holiday'],
] as const;

function attendanceMarker(record: AttendanceRecord): string {
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
const istDateTime = (value?: string | null) => value
  ? new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value))
  : 'Not available';

export function AttendancePage() {
  const { canManage } = useAuth();
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [coordinators, setCoordinators] = useState<Coordinator[]>([]);
  const [employeeMap, setEmployeeMap] = useState<Record<string, Employee>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [verdict, setVerdict] = useState<Verdict | ''>('');
  const [pcId, setPcId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [search, setSearch] = useState('');

  const [resolving, setResolving] = useState<AttendanceRecord | null>(null);
  const [editingStatus, setEditingStatus] = useState<AttendanceRecord | null>(null);
  const [statusCode, setStatusCode] = useState<string>('P');
  const [statusReason, setStatusReason] = useState('');
  const [savingStatus, setSavingStatus] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [manualEntryOpen, setManualEntryOpen] = useState(false);
  const [showMonthlyGrid, setShowMonthlyGrid] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAttendance({
        verdict: verdict || undefined,
        pc_id: pcId || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        search: search || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setRecords(data.records);
      setTotal(data.total);
    } catch {
      setError('Could not load attendance records.');
    } finally {
      setLoading(false);
    }
  }, [verdict, pcId, dateFrom, dateTo, search, page]);

  useEffect(() => {
    load();
  }, [load]);

  // Any filter change resets to page 1 — staying on page 6 of a now-shorter
  // result set would just show an empty page.
  useEffect(() => {
    setPage(1);
  }, [verdict, pcId, dateFrom, dateTo, search]);

  useEffect(() => {
    listCoordinators().then((r) => setCoordinators(r.coordinators)).catch(() => {});
    // Attendance records only carry employee_id, not a name — join against
    // the full employee list once so the table can show names instead of
    // raw IDs. page_size is generous since there's no "get everything"
    // endpoint; fine for the scale this app runs at.
    listEmployees({ page_size: 500 })
      .then((r) => {
        const map: Record<string, Employee> = {};
        r.employees.forEach((e) => {
          map[e.employee_id] = e;
        });
        setEmployeeMap(map);
      })
      .catch(() => {});
  }, []);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  async function removeAttendance(record: AttendanceRecord) {
    const employeeName = employeeMap[record.employee_id]?.name ?? record.employee_name ?? record.employee_id;
    if (!window.confirm(`Permanently delete the attendance record for ${employeeName}?`)) return;

    setDeletingId(record._id);
    setError(null);
    try {
      await deleteAttendance(record._id);
      setRecords((current) => current.filter((item) => item._id !== record._id));
      setTotal((current) => Math.max(0, current - 1));
      if (records.length === 1 && page > 1) {
        setPage((current) => current - 1);
      }
    } catch {
      setError('Could not delete the attendance record. Please try again.');
    } finally {
      setDeletingId(null);
    }
  }

  async function saveStatusOverride() {
    if (!editingStatus?.attendance_date) return;
    setSavingStatus(true);
    setError(null);
    try {
      await overrideAttendanceCell({
        employee_id: editingStatus.employee_id,
        date: editingStatus.attendance_date,
        attendance_code: statusCode,
        reason: statusReason.trim() || undefined,
      });
      setEditingStatus(null);
      setStatusReason('');
      await load();
    } catch {
      setError('Could not change this attendance status. Please try again.');
    } finally {
      setSavingStatus(false);
    }
  }

  if (showMonthlyGrid) {
    return <MonthlyAttendanceGrid onClose={() => setShowMonthlyGrid(false)} canManage={canManage} />;
  }

  return (
    <div>
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-lg font-medium" style={{ color: 'var(--color-ink)' }}>
            Attendance
          </h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-ink-muted)' }}>
            {loading ? 'Loading…' : `${total} record${total === 1 ? '' : 's'}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowMonthlyGrid(true)}
            className="px-3 py-1.5 rounded-md text-sm font-medium border"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}
          >
            Monthly grid
          </button>
          {canManage && (
            <>
              <button
                onClick={() => setManualEntryOpen(true)}
                className="px-3 py-1.5 rounded-md text-sm font-medium text-white transition-colors bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)]"
              >
                Log manual entry
              </button>
              <button
                onClick={() => setExportOpen(true)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium text-white transition-colors bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)]"
              >
                <img src="/brand/excel-icon.png" alt="" className="h-4 w-4" />
                Export to Excel
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-5 items-center">
        {VERDICT_FILTERS.map((f) => (
          <button
            key={f.label}
            onClick={() => setVerdict(f.value)}
            className="px-3 py-1.5 rounded-full text-sm border transition-colors hover:bg-black/5"
            style={{
              borderColor: verdict === f.value ? 'var(--color-accent)' : 'var(--color-border)',
              color: verdict === f.value ? 'var(--color-accent)' : 'var(--color-ink-muted)',
            }}
          >
            {f.label}
          </button>
        ))}

        <select
          value={pcId}
          onChange={(e) => setPcId(e.target.value)}
          className="px-2 py-1.5 rounded-md text-sm border ml-2"
          style={{
            background: 'var(--color-surface-raised)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-ink-muted)',
          }}
        >
          <option value="">All coordinators</option>
          {coordinators.map((c) => (
            <option key={c.pc_id} value={c.pc_id}>
              {c.name}
            </option>
          ))}
        </select>

        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="px-2 py-1.5 rounded-md text-sm border"
          style={{
            background: 'var(--color-surface-raised)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-ink-muted)',
          }}
        />
        <span className="text-sm" style={{ color: 'var(--color-ink-faint)' }}>
          to
        </span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="px-2 py-1.5 rounded-md text-sm border"
          style={{
            background: 'var(--color-surface-raised)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-ink-muted)',
          }}
        />

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name or phone…"
          className="px-2 py-1.5 rounded-md text-sm border ml-auto w-48"
          style={{
            background: 'var(--color-surface-raised)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-ink)',
          }}
        />
      </div>

      {error && (
        <p className="text-sm mb-4" style={{ color: 'var(--color-absent)' }}>
          {error}
        </p>
      )}

      <div className="rounded-lg border overflow-hidden shadow-sm" style={{ borderColor: 'var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-surface-sunken)' }}>
              {['S.No', 'Employee', 'Received (IST)', 'Check-in (IST)', 'Status', 'Shift', 'Geofence', 'Face match', 'Flag', 'Review', ...(canManage ? ['Action'] : [])].map(
                (h) => (
                  <th
                    key={h}
                    className="text-left px-4 py-2.5 text-xs font-medium"
                    style={{ color: 'var(--color-ink-faint)' }}
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {records.map((r, index) => (
              <tr
                key={r._id}
                className="border-t"
                style={{ borderColor: 'var(--color-border-subtle)' }}
              >
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {(page - 1) * PAGE_SIZE + index + 1}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink)' }}>
                  <div className="font-medium">{employeeMap[r.employee_id]?.name ?? r.employee_name ?? r.employee_id}</div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs" style={{ color: 'var(--color-ink-faint)' }}>
                      {r.employee_id}
                    </span>
                    {r.entry_type === 'manual' && (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{ background: 'var(--color-surface-sunken)', color: 'var(--color-ink-faint)' }}
                        title={`Manually logged by ${r.created_by ?? 'admin'}: ${r.reason ?? ''}`}
                      >
                        Manual
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {istDateTime(r.received_at_utc)}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {istDateTime(r.check_in_at_ist)}
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className="px-1.5 py-0.5 rounded text-[11px] font-medium"
                    style={{
                      background:
                        ['F', 'A', 'AL'].includes(attendanceMarker(r))
                          ? 'var(--color-absent-bg)'
                          : 'var(--color-surface-sunken)',
                      color:
                        ['F', 'A', 'AL'].includes(attendanceMarker(r))
                          ? 'var(--color-absent)'
                          : attendanceMarker(r) === 'L'
                            ? 'var(--color-accent)'
                            : 'var(--color-present)',
                    }}
                  >
                    {attendanceMarker(r)}
                  </span>
                </td>
                <td className="px-4 py-2.5">
                  <ShiftStatusBadge status={r.shift_status} skipped={r.entry_type === 'manual'} />
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {r.geofence_display ?? (r.geofence_passed === true ? 'Within range' : r.geofence_passed === false ? 'Outside range' : 'Not verified')}
                </td>
                <td className="px-4 py-2.5">
                  <FaceMatchStatus record={r} />
                </td>
                <td className="px-4 py-2.5">
                  {r.verdict === 'flagged' ? (
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                      style={{
                        background: 'var(--color-absent-bg)',
                        color: 'var(--color-absent)',
                      }}
                      title={r.issues_display.join('; ')}
                    >
                      {r.flag_reason ?? 'REVIEW'}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--color-ink-faint)' }}>—</span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  <div>{r.review_display ?? (r.verdict === 'verified' ? 'Automatically verified' : <ReviewStatusBadge status={r.review_status} />)}</div>
                  {!!r.previous_flagged_attempts?.length && (
                    <div
                      className="mt-1 text-[10px]"
                      style={{ color: 'var(--color-ink-faint)' }}
                      title={r.previous_flagged_attempts
                        .map((attempt) => attempt.issues_display?.join('; ') || attempt.issues.join('; '))
                        .join('\n')}
                    >
                      Replaced {r.previous_flagged_attempts.length} flagged photo{r.previous_flagged_attempts.length === 1 ? '' : 's'}
                    </div>
                  )}
                </td>
                {canManage && <td className="px-4 py-2.5 text-right">
                  <button
                    onClick={() => {
                      setEditingStatus(r);
                      const marker = attendanceMarker(r);
                      setStatusCode(
                        STATUS_OVERRIDE_OPTIONS.some(([value]) => value === marker) ? marker : 'P'
                      );
                      setStatusReason('');
                    }}
                    disabled={!r.attendance_date}
                    className="mr-2 inline-flex items-center gap-1 text-xs font-medium disabled:opacity-40"
                    style={{ color: 'var(--color-accent)' }}
                    title={r.attendance_date ? `Change status for ${r.attendance_date}` : 'Attendance date unavailable'}
                  >
                    <Pencil size={13} />
                    Change status
                  </button>
                  {r.verdict === 'flagged' && r.review_status === 'pending' && (
                    <button
                      onClick={() => setResolving(r)}
                      className="text-xs font-medium"
                      style={{ color: 'var(--color-accent)' }}
                    >
                      Review
                    </button>
                  )}
                  <button
                    onClick={() => removeAttendance(r)}
                    disabled={deletingId === r._id}
                    className="ml-2 p-1 rounded transition-colors hover:bg-black/5 disabled:opacity-50"
                    style={{ color: 'var(--color-absent)' }}
                    title="Delete attendance record"
                    aria-label={`Delete attendance record for ${employeeMap[r.employee_id]?.name ?? r.employee_id}`}
                  >
                    <Trash2 size={15} />
                  </button>
                </td>}
              </tr>
            ))}
            {!loading && records.length === 0 && (
              <tr>
                <td colSpan={canManage ? 11 : 10} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--color-ink-faint)' }}>
                  No records match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div
          className="px-4 py-2.5 border-t text-xs"
          style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-ink-muted)' }}
        >
          Total attendance records: {total}
        </div>

        {totalPages > 1 && (
          <div
            className="flex items-center justify-between px-4 py-2.5 border-t text-xs"
            style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-ink-muted)' }}
          >
            <span>
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-2 py-1 rounded disabled:opacity-40"
                style={{ border: '1px solid var(--color-border)' }}
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-2 py-1 rounded disabled:opacity-40"
                style={{ border: '1px solid var(--color-border)' }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {resolving && (
        <ResolveModal
          record={resolving}
          onClose={() => setResolving(null)}
          onResolved={(updated) => {
            setRecords((prev) => prev.map((r) => (r._id === updated._id ? updated : r)));
            setResolving(null);
          }}
        />
      )}

      {editingStatus && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-md rounded-lg border p-5 shadow-xl" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}>
            <h2 className="text-base font-medium mb-1" style={{ color: 'var(--color-ink)' }}>Change attendance status</h2>
            <p className="text-sm mb-4" style={{ color: 'var(--color-ink-muted)' }}>
              {employeeMap[editingStatus.employee_id]?.name ?? editingStatus.employee_name ?? editingStatus.employee_id}
              {' · '}{editingStatus.employee_id}{' · '}{editingStatus.attendance_date}
            </p>
            <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>New status</label>
            <select
              value={statusCode}
              onChange={(event) => setStatusCode(event.target.value)}
              className="w-full px-3 py-2 rounded-md text-sm border mb-3"
              style={{ background: 'var(--color-surface-sunken)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
            >
              {STATUS_OVERRIDE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>Reason for change (optional)</label>
            <textarea
              value={statusReason}
              onChange={(event) => setStatusReason(event.target.value)}
              rows={3}
              className="w-full px-3 py-2 rounded-md text-sm border resize-y"
              style={{ background: 'var(--color-surface-sunken)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setEditingStatus(null)}
                className="px-3 py-1.5 rounded-md text-sm"
                style={{ color: 'var(--color-ink-muted)' }}
              >
                Cancel
              </button>
              <button
                onClick={() => void saveStatusOverride()}
                disabled={savingStatus}
                className="px-3 py-1.5 rounded-md text-sm font-medium text-white disabled:opacity-50"
                style={{ background: 'var(--color-accent)' }}
              >
                {savingStatus ? 'Saving…' : 'Save status'}
              </button>
            </div>
          </div>
        </div>
      )}

      {exportOpen && <ExportPanel coordinators={coordinators} onClose={() => setExportOpen(false)} />}

      {manualEntryOpen && (
        <ManualEntryModal
          onClose={() => setManualEntryOpen(false)}
          onCreated={() => {
            setManualEntryOpen(false);
            load();
          }}
        />
      )}
    </div>
  );
}