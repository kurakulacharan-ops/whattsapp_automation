import { useCallback, useEffect, useState } from 'react';
import { initializeCoordinatorAttendanceDefaults, listCoordinatorAttendance, saveCoordinatorAttendance } from '../api/attendance';
import { listCoordinators } from '../api/coordinators';
import type { AttendanceRecord, Coordinator } from '../types';

const today = () => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  return parts;
};

type DatePreset = 'today' | 'yesterday' | 'week' | 'month' | 'range';
type CoordinatorAttendanceRow = {
  coordinator: Coordinator;
  attendanceDate: string;
  saved?: AttendanceRecord;
};

function shiftDate(date: string, days: number) {
  const shifted = new Date(`${date}T00:00:00Z`);
  shifted.setUTCDate(shifted.getUTCDate() + days);
  return shifted.toISOString().slice(0, 10);
}

function rangeForPreset(preset: Exclude<DatePreset, 'range'>, currentDate: string): [string, string] {
  if (preset === 'today') return [currentDate, currentDate];
  if (preset === 'yesterday') {
    const yesterday = shiftDate(currentDate, -1);
    return [yesterday, yesterday];
  }
  if (preset === 'week') {
    const weekday = new Date(`${currentDate}T00:00:00Z`).getUTCDay();
    return [shiftDate(currentDate, -((weekday + 6) % 7)), currentDate];
  }
  return [`${currentDate.slice(0, 7)}-01`, currentDate];
}

export function CoordinatorAttendancePage() {
  const [coordinators, setCoordinators] = useState<Coordinator[]>([]);
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [pcId, setPcId] = useState('');
  const [date, setDate] = useState(today);
  const [datePreset, setDatePreset] = useState<DatePreset>('today');
  const [filterStatus, setFilterStatus] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [statuses, setStatuses] = useState<Record<string, 'P' | 'A' | 'WO' | 'H'>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [savedByCoordinator, setSavedByCoordinator] = useState<Record<string, AttendanceRecord>>({});
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  function selectDatePreset(preset: DatePreset) {
    setDatePreset(preset);
    if (preset === 'range') {
      setDateFrom((current) => current || date);
      setDateTo((current) => current || date);
      return;
    }
    const [from, to] = rangeForPreset(preset, today());
    if (preset === 'today' || preset === 'yesterday') {
      setDate(from);
      setDateFrom('');
      setDateTo('');
    } else {
      setDate(to);
      setDateFrom(from);
      setDateTo(to);
    }
  }

  useEffect(() => {
    listCoordinators({ page_size: 1000, is_active: true })
      .then((result) => { setCoordinators(result.coordinators); })
      .catch(() => setError('Could not load project coordinators.'));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      if (!dateFrom && !dateTo && date === today()) {
        await initializeCoordinatorAttendanceDefaults(date);
      }
      const result = await listCoordinatorAttendance({
        date_from: dateFrom || date, date_to: dateTo || date, pc_id: pcId || undefined,
        attendance_status: (filterStatus || undefined) as 'present' | 'absent' | 'week_off' | 'holiday' | undefined,
        search: search || undefined, page, page_size: pageSize,
      });
      setRecords(result.records);
      setTotal(result.total);
      setSavedByCoordinator(Object.fromEntries(
        [...result.records].reverse().map((record) => [record.employee_id, record])
      ));
    } catch {
      setError('Could not load coordinator attendance.');
    } finally {
      setLoading(false);
    }
  }, [date, dateFrom, dateTo, pcId, filterStatus, search, page, pageSize, coordinators]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setPage(1); }, [date, dateFrom, dateTo, pcId, filterStatus, search, pageSize]);
  useEffect(() => { setStatuses({}); setReasons({}); }, [date, dateFrom, dateTo]);

  async function save(coordinator: Coordinator, attendanceDate: string, saved?: AttendanceRecord) {
    const key = `${coordinator.pc_id}:${attendanceDate}`;
    const code = statuses[key] ?? saved?.attendance_code as 'P' | 'A' | 'WO' | 'H' | undefined;
    if (!code) return;
    setSaving(key);
    setError('');
    setNotice('');
    try {
      const savedRecord = await saveCoordinatorAttendance({
        pc_id: coordinator.pc_id, date: attendanceDate, attendance_code: code,
        reason: reasons[key]?.trim() || undefined,
      });
      setStatuses((current) => ({ ...current, [key]: code }));
      setSavedByCoordinator((current) => ({ ...current, [coordinator.pc_id]: savedRecord }));
      setNotice(`Attendance saved for ${coordinator.name}.`);
      if (filterStatus && savedRecord.attendance_status !== filterStatus) {
        await load();
      } else {
        setRecords((current) => {
          const exists = current.some((record) => record.employee_id === savedRecord.employee_id && record.attendance_date === savedRecord.attendance_date);
          return exists ? current.map((record) => record.employee_id === savedRecord.employee_id && record.attendance_date === savedRecord.attendance_date ? savedRecord : record) : [...current, savedRecord];
        });
        if (!savedByCoordinator[coordinator.pc_id]) setTotal((current) => current + 1);
      }
    } catch {
      setError(`Could not save attendance for ${coordinator.name}.`);
    } finally {
      setSaving(null);
    }
  }

  const currentPageCoordinators = coordinators.filter((item) =>
    (!pcId || item.pc_id === pcId)
    && (!search.trim() || `${item.name} ${item.pc_id}`.toLowerCase().includes(search.trim().toLowerCase()))
  );
  const matchingCoordinatorIds = [...new Set(records.map((record) => record.employee_id))];
  const isDateRange = Boolean(dateFrom || dateTo);
  const pages = Math.max(1, Math.ceil(
    (isDateRange ? total : filterStatus ? matchingCoordinatorIds.length : currentPageCoordinators.length) / pageSize
  ));
  const visibleRows: CoordinatorAttendanceRow[] = isDateRange
    ? records.flatMap((record) => {
      const coordinator = coordinators.find((item) => item.pc_id === record.employee_id);
      return coordinator ? [{ coordinator, saved: record, attendanceDate: record.attendance_date ?? date }] : [];
    })
    : (filterStatus
      ? matchingCoordinatorIds.map((id) => coordinators.find((item) => item.pc_id === id)).filter((item): item is Coordinator => !!item)
      : currentPageCoordinators.slice((page - 1) * pageSize, page * pageSize)
    ).map((coordinator) => ({
      coordinator,
      saved: savedByCoordinator[coordinator.pc_id],
      attendanceDate: date,
    }));

  return <section>
    <div className="flex flex-wrap justify-between items-start gap-3 mb-5">
      <div><h1 className="text-lg font-medium" style={{ color: 'var(--color-ink)' }}>Project Coordinator Attendance</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-ink-muted)' }}>Today defaults to Present on working days and follows the holiday/week-off calendar on closed days. Admin and manual team can change any status. Coordinator attendance does not use photo, check-in, or shift times.</p></div>
      <div className="flex flex-wrap items-center gap-2 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
        <label>Period <select aria-label="Attendance date range preset" value={datePreset} onChange={(event) => selectDatePreset(event.target.value as DatePreset)} className="ml-2 rounded-md border px-2 py-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}>
          <option value="today">Today</option><option value="yesterday">Yesterday</option><option value="week">This week</option><option value="month">This month</option><option value="range">Custom range</option>
        </select></label>
        {datePreset === 'today' || datePreset === 'yesterday' ? (
          <label>Date <input type="date" value={date} onChange={(event) => { setDatePreset('range'); setDateFrom(event.target.value); setDateTo(event.target.value); setDate(event.target.value); }} className="ml-2 rounded-md border px-2 py-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }} /></label>
        ) : (
          <><span>From</span><input aria-label="From date" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} className="rounded-md border px-2 py-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }} /><span>to</span><input aria-label="To date" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} className="rounded-md border px-2 py-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }} /></>
        )}
      </div>
    </div>
    <div className="flex flex-wrap gap-2 mb-4">
      <select value={pcId} onChange={(event) => setPcId(event.target.value)} className="rounded-md border px-2 py-1.5 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}><option value="">All coordinators</option>{coordinators.map((item) => <option key={item.pc_id} value={item.pc_id}>{item.name}</option>)}</select>
      <select value={filterStatus} onChange={(event) => setFilterStatus(event.target.value)} className="rounded-md border px-2 py-1.5 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}><option value="">All statuses</option><option value="present">Present</option><option value="absent">Absent</option><option value="week_off">Week-off</option><option value="holiday">Holiday</option></select>
      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search coordinator…" className="rounded-md border px-2 py-1.5 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }} />
      <label className="ml-auto text-sm" style={{ color: 'var(--color-ink-muted)' }}>Show <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))} className="rounded-md border px-2 py-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}>{[5, 10, 20, 25, 50, 100].map((size) => <option key={size}>{size}</option>)}</select></label>
    </div>
    {error && <p role="alert" className="mb-3 text-sm" style={{ color: 'var(--color-absent)' }}>{error}</p>}
    {notice && <p role="status" className="mb-3 text-sm" style={{ color: 'var(--color-present)' }}>{notice}</p>}
    <div className="overflow-x-auto rounded-lg border" style={{ borderColor: 'var(--color-border)' }}><table className="w-full text-sm">
      <thead style={{ background: 'var(--color-surface-sunken)' }}><tr>{['ID', 'Project Co-ordinator', 'Attendance date', 'Attendance', 'Reason / note', 'Action'].map((heading) => <th key={heading} className="px-3 py-2.5 text-left text-xs font-medium" style={{ color: 'var(--color-ink-muted)' }}>{heading}</th>)}</tr></thead>
      <tbody>{visibleRows.map(({ coordinator, saved, attendanceDate }) => {
        const rowKey = `${coordinator.pc_id}:${attendanceDate}`;
        const value = statuses[rowKey] ?? (saved?.attendance_code as 'P' | 'A' | 'WO' | 'H' | undefined) ?? '';
        const reason = reasons[rowKey] ?? saved?.reason ?? '';
        return <tr key={rowKey} className="border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
          <td className="px-3 py-2.5">{coordinator.pc_id}</td><td className="px-3 py-2.5">{coordinator.name}</td>
          <td className="px-3 py-2.5">{saved?.attendance_date ?? attendanceDate}</td>
          <td className="px-3 py-2.5"><select aria-label={`Attendance for ${coordinator.name} on ${attendanceDate}`} value={value} onChange={(event) => setStatuses((current) => ({ ...current, [rowKey]: event.target.value as 'P' | 'A' | 'WO' | 'H' }))} className="rounded-md border px-2 py-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}><option value="">Select status</option><option value="P">Present</option><option value="A">Absent</option><option value="WO">Week-off</option><option value="H">Holiday</option></select></td>
          <td className="px-3 py-2.5"><details>
            <summary className="cursor-pointer select-none text-xs" style={{ color: 'var(--color-accent)' }}>
              {reason.trim() ? 'View / edit note' : 'Add note'}
            </summary>
            <input value={reason} onChange={(event) => setReasons((current) => ({ ...current, [rowKey]: event.target.value }))} placeholder="Optional" aria-label={`Reason for ${coordinator.name} on ${attendanceDate}`} className="mt-2 w-full rounded-md border px-2 py-1.5 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }} />
          </details></td>
          <td className="px-3 py-2.5"><button disabled={!value || saving === rowKey} onClick={() => void save(coordinator, attendanceDate, saved)} className="rounded-md px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50" style={{ background: 'var(--color-accent)' }}>{saving === rowKey ? 'Saving…' : saved ? 'Update' : 'Save'}</button></td>
        </tr>;
      })}
      {!loading && visibleRows.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center" style={{ color: 'var(--color-ink-muted)' }}>No coordinator records for this date/filter.</td></tr>}</tbody>
    </table>{loading && <p className="p-3 text-sm" style={{ color: 'var(--color-ink-muted)' }}>Loading…</p>}
    {pages > 1 && <div className="flex justify-between px-3 py-2.5 text-xs" style={{ color: 'var(--color-ink-muted)' }}><span>Page {page} of {pages}</span><div className="flex gap-2"><button disabled={page <= 1} onClick={() => setPage((current) => current - 1)} className="rounded border px-2 py-1 disabled:opacity-40">Previous</button><button disabled={page >= pages} onClick={() => setPage((current) => current + 1)} className="rounded border px-2 py-1 disabled:opacity-40">Next</button></div></div>}</div>
  </section>;
}
