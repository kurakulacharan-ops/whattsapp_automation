import { useEffect, useMemo, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { deleteAttendance, listAttendance, overrideAttendanceCell, saveCoordinatorAttendance } from '../api/attendance';
import { listCoordinators } from '../api/coordinators';
import { listEmployees } from '../api/employees';
import type { AttendancePersonRole, AttendanceRecord, Coordinator, Employee, Verdict } from '../types';
import { ReviewStatusBadge, ShiftStatusBadge, FaceMatchStatus } from '../components/StatusBadge';
import { ResolveModal } from '../components/ResolveModal';
import { ExportPanel } from '../components/ExportPanel';
import { ManualEntryModal } from '../components/ManualEntryModal';
import { MonthlyAttendanceGrid } from '../components/MonthlyAttendanceGrid';
import { Pencil, Trash2, Search, ChevronDown, ChevronUp, FileSpreadsheet, CalendarDays, ShieldAlert } from 'lucide-react';
import { attendanceMarker, codeMeta, tally } from '../utils/attendanceCodes';
import { DistributionBar, MiniBars, RankBars } from '../components/charts';
import { EmptyRow, Kpi, Notice, Pager, SkeletonRows, TableFooter } from '../components/ui';
import { useAuth } from '../context/AuthContext';

const VERDICT_FILTERS: { label: string; value: Verdict | '' }[] = [
  { label: 'All', value: '' },
  { label: 'Verified', value: 'verified' },
  { label: 'Flagged', value: 'flagged' },
  { label: 'Inactive account', value: 'inactive_account' },
];

const PAGE_SIZE_OPTIONS = [5, 10, 20, 25, 50, 100] as const;
type DatePreset = 'today' | 'yesterday' | 'week' | 'month' | 'range';

function todayInKolkata() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date());
}

function shiftDate(date: string, days: number) {
  const shifted = new Date(`${date}T00:00:00Z`);
  shifted.setUTCDate(shifted.getUTCDate() + days);
  return shifted.toISOString().slice(0, 10);
}

function rangeForPreset(preset: Exclude<DatePreset, 'range'>, today: string): [string, string] {
  if (preset === 'today') return [today, today];
  if (preset === 'yesterday') {
    const yesterday = shiftDate(today, -1);
    return [yesterday, yesterday];
  }
  if (preset === 'week') {
    const weekday = new Date(`${today}T00:00:00Z`).getUTCDay();
    const daysSinceMonday = (weekday + 6) % 7;
    return [shiftDate(today, -daysSinceMonday), today];
  }
  return [`${today.slice(0, 7)}-01`, today];
}

const STATUS_OVERRIDE_OPTIONS = [
  ['P', 'Present'],
  ['L', 'Late'],
  ['A', 'Absent'],
  ['AL', 'Absent late'],
  ['HD', 'Half day'],
  ['WO', 'Week off'],
  ['H', 'Holiday'],
] as const;

const istDateTime = (value?: string | null) => value
  ? new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value))
  : 'Not available';

function DateTimeCell({ value }: { value?: string | null }) {
  if (!value) return <span style={{ color: 'var(--color-ink-faint)' }}>Not available</span>;
  const d = new Date(value);
  const day = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short' }).format(d);
  const time = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit', hour12: true }).format(d);
  return (
    <div className="whitespace-nowrap leading-tight" title={istDateTime(value)}>
      <div className="font-semibold" style={{ color: 'var(--color-ink)' }}>{time}</div>
      <div className="text-xs" style={{ color: 'var(--color-ink-faint)' }}>{day}</div>
    </div>
  );
}

export function AttendancePage() {
  const { canManage } = useAuth();
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(25);
  const [coordinators, setCoordinators] = useState<Coordinator[]>([]);
  const [employeeMap, setEmployeeMap] = useState<Record<string, Employee>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [verdict, setVerdict] = useState<Verdict | ''>('');
  const [pcId, setPcId] = useState('');
  const [roleFilter, setRoleFilter] = useState<AttendancePersonRole | ''>('');
  const [datePreset, setDatePreset] = useState<DatePreset>('today');
  const [dateFrom, setDateFrom] = useState(() => todayInKolkata());
  const [dateTo, setDateTo] = useState(() => todayInKolkata());
  const [search, setSearch] = useState('');
  const [area, setArea] = useState('');
  const [attendanceStatus, setAttendanceStatus] = useState('');
  const [includeCoordinatorAttendance, setIncludeCoordinatorAttendance] = useState(false);
  const [areas, setAreas] = useState<string[]>([]);

  const [resolving, setResolving] = useState<AttendanceRecord | null>(null);
  const [editingStatus, setEditingStatus] = useState<AttendanceRecord | null>(null);
  const [statusCode, setStatusCode] = useState<string>('P');
  const [statusReason, setStatusReason] = useState('');
  const [savingStatus, setSavingStatus] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [manualEntryOpen, setManualEntryOpen] = useState(false);
  const [showMonthlyGrid, setShowMonthlyGrid] = useState(false);
  const [statsRecords, setStatsRecords] = useState<AttendanceRecord[]>([]);
  const [statsTotal, setStatsTotal] = useState(0);
  const [statsLoadedFor, setStatsLoadedFor] = useState('');
  const [statsTick, setStatsTick] = useState(0);
  const [showStats, setShowStats] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAttendance({
        verdict: verdict || undefined,
        pc_id: pcId || undefined,
        role: roleFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        search: search || undefined,
        area: area || undefined,
        attendance_status: (attendanceStatus || undefined) as 'present' | 'late' | 'absent' | 'flagged' | undefined,
        include_coordinator_attendance: canManage && (includeCoordinatorAttendance || roleFilter === 'PC'),
        page,
        page_size: pageSize,
      });
      setRecords(data.records);
      setTotal(data.total);
    } catch {
      setError('Could not load attendance records.');
    } finally {
      setLoading(false);
    }
  }, [verdict, pcId, roleFilter, dateFrom, dateTo, search, area, attendanceStatus, includeCoordinatorAttendance, canManage, page, pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  const statsKey = [verdict, pcId, roleFilter, dateFrom, dateTo, search, area, attendanceStatus, includeCoordinatorAttendance, canManage, statsTick].join('|');
  const statsLoading = statsLoadedFor !== statsKey;

  // Read-only analytics: the same filters as the table, but one wide page
  // (the API caps page_size at 500) so the summary covers every matching row.
  useEffect(() => {
    let active = true;
    const key = statsKey;
    listAttendance({
      verdict: verdict || undefined,
      pc_id: pcId || undefined,
      role: roleFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      search: search || undefined,
      area: area || undefined,
      attendance_status: (attendanceStatus || undefined) as 'present' | 'late' | 'absent' | 'flagged' | undefined,
      include_coordinator_attendance: canManage && (includeCoordinatorAttendance || roleFilter === 'PC'),
      page: 1,
      page_size: 500,
    })
      .then((data) => { if (active) { setStatsRecords(data.records); setStatsTotal(data.total); } })
      .catch(() => { if (active) { setStatsRecords([]); setStatsTotal(0); } })
      .finally(() => { if (active) setStatsLoadedFor(key); });
    return () => { active = false; };
  }, [verdict, pcId, roleFilter, dateFrom, dateTo, search, area, attendanceStatus, includeCoordinatorAttendance, canManage, statsTick, statsKey]);

  const stats = useMemo(() => {
    const t = tally(statsRecords.map(attendanceMarker));
    const pending = statsRecords.filter((r) => r.entry_type !== 'coordinator_manual' && r.verdict === 'flagged' && r.review_status === 'pending').length;
    const hours = new Array(24).fill(0) as number[];
    statsRecords.forEach((r) => {
      const stamp = r.check_in_at_ist ?? r.received_at_utc;
      if (!stamp || r.entry_type === 'coordinator_manual') return;
      const h = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', hour12: false }).format(new Date(stamp)));
      if (!Number.isNaN(h)) hours[h % 24] += 1;
    });
    const used = hours.map((v, i) => (v ? i : -1)).filter((i) => i >= 0);
    const from = used.length ? Math.max(0, Math.min(...used)) : 0;
    const to = used.length ? Math.min(23, Math.max(...used)) : 0;
    const slice = hours.slice(from, to + 1);
    const labels = slice.map((_, i) => String(from + i).padStart(2, '0'));
    const reasons = new Map<string, number>();
    statsRecords.filter((r) => r.verdict === 'flagged' && r.review_status === 'pending').forEach((r) => {
      const k = r.flag_reason?.trim() || 'Needs review';
      reasons.set(k, (reasons.get(k) ?? 0) + 1);
    });
    const topReasons = [...reasons.entries()].sort((x, y) => y[1] - x[1]).slice(0, 5)
      .map(([k, v]) => ({ key: k, label: k, value: v, display: String(v) }));
    return { t, pending, slice, labels, topReasons };
  }, [statsRecords]);

  // Any filter change resets to page 1 — staying on page 6 of a now-shorter
  // result set would just show an empty page.
  useEffect(() => {
    setPage(1);
  }, [verdict, pcId, roleFilter, dateFrom, dateTo, search, area, attendanceStatus, includeCoordinatorAttendance, pageSize]);

  useEffect(() => {
    listCoordinators().then((r) => setCoordinators(r.coordinators)).catch(() => {});
    // Attendance records only carry employee_id, not a name — join against
    // the full employee list once so the table can show names instead of
    // raw IDs. page_size is generous since there's no "get everything"
    // endpoint; fine for the scale this app runs at.
    listEmployees({ page_size: 500 })
      .then((r) => {
        const map: Record<string, Employee> = {};
        const areaSet = new Set<string>();
        r.employees.forEach((e) => {
          map[e.employee_id] = e;
          if (e.area?.trim()) areaSet.add(e.area.trim());
        });
        setEmployeeMap(map);
        setAreas([...areaSet].sort((a, b) => a.localeCompare(b)));
      })
      .catch(() => {});
  }, []);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  function selectDatePreset(preset: DatePreset) {
    setDatePreset(preset);
    if (preset === 'range') return;
    const [from, to] = rangeForPreset(preset, todayInKolkata());
    setDateFrom(from);
    setDateTo(to);
  }

  async function removeAttendance(record: AttendanceRecord) {
    const employeeName = employeeMap[record.employee_id]?.name ?? record.employee_name ?? record.employee_id;
    if (!window.confirm(`Permanently delete the attendance record for ${employeeName}?`)) return;

    setDeletingId(record._id);
    setError(null);
    try {
      await deleteAttendance(record._id);
      setStatsTick((n) => n + 1);
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
      if (editingStatus.entry_type === 'coordinator_manual') {
        await saveCoordinatorAttendance({
          pc_id: editingStatus.employee_id,
          date: editingStatus.attendance_date,
          attendance_code: statusCode === 'A' ? 'A' : 'P',
          reason: statusReason.trim() || undefined,
        });
        setEditingStatus(null);
        setStatusReason('');
        setStatsTick((n) => n + 1);
        await load();
        return;
      }
      await overrideAttendanceCell({
        employee_id: editingStatus.employee_id,
        date: editingStatus.attendance_date,
        attendance_code: statusCode,
        reason: statusReason.trim() || undefined,
      });
      setEditingStatus(null);
      setStatusReason('');
      setStatsTick((n) => n + 1);
      // Let the API return the canonical row and filtered total after the
      // override. This avoids stale client-side rows/totals when a status
      // change moves the record out of the active filter.
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

  const nameOf = (r: AttendanceRecord) => employeeMap[r.employee_id]?.name ?? r.employee_name ?? r.employee_id;
  const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('') || '?';
  const colSpan = canManage ? 12 : 11;
  const truncated = statsTotal > statsRecords.length;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[1.65rem] font-extrabold leading-tight" style={{ color: 'var(--color-ink)' }}>Attendance</h1>
          <p className="mt-1 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
            Review WhatsApp check-ins as they arrive and resolve anything the AI flagged.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setShowMonthlyGrid(true)} className="btn btn-secondary">
            <CalendarDays size={15} /> Monthly grid
          </button>
          {canManage && (
            <>
              <button onClick={() => setManualEntryOpen(true)} className="btn btn-secondary">Log manual entry</button>
              <button onClick={() => setExportOpen(true)} className="btn btn-primary">
                <FileSpreadsheet size={15} /> Export to Excel
              </button>
            </>
          )}
        </div>
      </div>

      {/* ---------- Analytics ---------- */}
      <div className="mb-5">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Kpi loading={statsLoading} label="Records in view" value={statsTotal.toLocaleString('en-IN')} accent="var(--color-accent)" hint={loading ? 'Updating…' : 'Matching your filters'} />
          <Kpi loading={statsLoading} label="Present" value={stats.t.present.toLocaleString('en-IN')} accent="var(--color-present)" hint={stats.t.rate === null ? 'P + L + M' : `${Math.round(stats.t.rate)}% attendance rate`} />
          <Kpi loading={statsLoading} label="Late" value={(stats.t.counts.L ?? 0).toLocaleString('en-IN')} accent="var(--color-late)" hint="Checked in after shift start" />
          <Kpi loading={statsLoading} label="Needs review" value={stats.pending.toLocaleString('en-IN')} accent="#d99a00" hint={stats.pending ? 'Flagged and waiting for you' : 'Nothing waiting'} />
          <Kpi loading={statsLoading} label="Absent" value={stats.t.absent.toLocaleString('en-IN')} accent="var(--color-absent)" hint="A + AL" />
        </div>

        <div className="card mt-3 overflow-hidden">
          <button
            onClick={() => setShowStats((v) => !v)}
            className="flex w-full items-center justify-between px-5 py-3 text-left text-sm font-bold"
            style={{ color: 'var(--color-ink)' }}
            aria-expanded={showStats}
          >
            Breakdown for this view
            {showStats ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {showStats && (
            <div
              className="grid gap-6 border-t px-5 py-5"
              style={{ borderColor: 'var(--color-border-subtle)', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 18rem), 1fr))' }}
            >
              <div className="min-w-0">
                <h3 className="mb-3 text-xs font-bold" style={{ color: 'var(--color-ink-muted)' }}>Status mix</h3>
                {statsLoading ? <div className="skeleton h-16" /> : <DistributionBar counts={stats.t.counts} />}
              </div>
              <div className="min-w-0">
                <h3 className="mb-1 text-xs font-bold" style={{ color: 'var(--color-ink-muted)' }}>Check-ins by hour (IST)</h3>
                <p className="mb-2 text-[11px]" style={{ color: 'var(--color-ink-faint)' }}>Each bar is an IST hour (00–23); hover for the count.</p>
                {statsLoading ? <div className="skeleton h-24" /> : <MiniBars values={stats.slice} labels={stats.labels} height={104} />}
              </div>
              <div className="min-w-0">
                <h3 className="mb-3 flex items-center gap-1.5 text-xs font-bold" style={{ color: 'var(--color-ink-muted)' }}><ShieldAlert size={13} /> Top flag reasons</h3>
                {statsLoading ? <div className="skeleton h-24" /> : <RankBars rows={stats.topReasons} color="#d99a00" empty="No flagged submissions in this view." />}
              </div>
              {truncated && (
                <p className="col-span-full text-xs" style={{ color: 'var(--color-ink-faint)' }}>
                  Charts summarise the first {statsRecords.length.toLocaleString('en-IN')} of {statsTotal.toLocaleString('en-IN')} matching records. Narrow the date range for a complete view.
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ---------- Filters ---------- */}
      <div className="card mb-4 flex flex-wrap items-center gap-2 p-3">
        {VERDICT_FILTERS.map((f) => (
          <button key={f.label} onClick={() => setVerdict(f.value)} aria-pressed={verdict === f.value} className="chip">
            {f.label}
          </button>
        ))}
        <span className="mx-1 hidden h-6 w-px sm:block" style={{ background: 'var(--color-border)' }} />

        <select aria-label="Date range preset" value={datePreset} onChange={(event) => selectDatePreset(event.target.value as DatePreset)} className="field">
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="week">This week</option>
          <option value="month">This month</option>
          <option value="range">Custom range</option>
        </select>
        {datePreset === 'range' && (
          <>
            <input aria-label="Attendance from date" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} className="field" />
            <span className="text-sm" style={{ color: 'var(--color-ink-faint)' }}>to</span>
            <input aria-label="Attendance to date" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} className="field" />
          </>
        )}

        <select aria-label="Coordinator" value={pcId} onChange={(e) => setPcId(e.target.value)} className="field">
          <option value="">All coordinators</option>
          {coordinators.map((c) => <option key={c.pc_id} value={c.pc_id}>{c.name}</option>)}
        </select>
        <select aria-label="Area" value={area} onChange={(e) => setArea(e.target.value)} className="field">
          <option value="">All areas</option>
          {areas.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        <select
          aria-label="Attendance role"
          value={roleFilter}
          onChange={(event) => {
            const role = event.target.value as AttendancePersonRole | '';
            setRoleFilter(role);
            if (role === 'PC') setIncludeCoordinatorAttendance(true);
          }}
          className="field"
        >
          <option value="">All roles</option>
          {canManage && <option value="PC">Project coordinator (PC)</option>}
          <option value="FS">Field supervisor (FS)</option>
          <option value="LS">Local supervisor (LS)</option>
          <option value="LSS">Local supervisor scanning (LSS)</option>
        </select>
        <select aria-label="Status" value={attendanceStatus} onChange={(e) => setAttendanceStatus(e.target.value)} className="field">
          <option value="">All statuses</option>
          <option value="present">Present</option>
          <option value="late">Late</option>
          <option value="absent">Absent</option>
          <option value="flagged">Flagged</option>
        </select>

        {canManage && (
          <label className="flex items-center gap-2 px-1 text-[13px] font-semibold" style={{ color: 'var(--color-ink-muted)' }}>
            <input
              type="checkbox"
              checked={includeCoordinatorAttendance}
              onChange={(event) => {
                setIncludeCoordinatorAttendance(event.target.checked);
                if (!event.target.checked && roleFilter === 'PC') setRoleFilter('');
              }}
            />
            Include project coordinators
          </label>
        )}

        <label className="flex items-center gap-1.5 text-[13px] font-semibold" style={{ color: 'var(--color-ink-muted)' }}>
          Show
          <select aria-label="Records per page" value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))} className="field !min-h-0 !py-1">
            {PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
          per page
        </label>

        <div className="relative ml-auto">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-ink-faint)' }} />
          <input aria-label="Search name or phone" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name or phone…" className="field w-56 !pl-9" />
        </div>
      </div>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="card overflow-hidden">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {['S.No', 'Employee', 'Area', 'Received (IST)', 'Photo check-in (IST)', 'Status', 'Shift', 'Location', 'Face match', 'Flag', 'Review', ...(canManage ? ['Action'] : [])].map((h) => (
                  <th key={h} className={h === 'Action' ? 'sticky-right text-right' : ''}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && records.length === 0 && <SkeletonRows cols={colSpan} />}
              {records.map((r, index) => {
                const marker = attendanceMarker(r);
                const meta = codeMeta(marker);
                const needsReview = r.entry_type !== 'coordinator_manual' && r.verdict === 'flagged' && r.review_status === 'pending';
                return (
                  <tr key={r._id} className={needsReview ? 'needs-review' : ''} style={needsReview ? { background: '#fffbec' } : undefined}>
                    <td style={{ color: 'var(--color-ink-faint)' }}>{(page - 1) * pageSize + index + 1}</td>
                    <td>
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-extrabold" style={{ background: 'var(--color-accent-bg)', color: 'var(--color-accent)' }}>
                          {initials(nameOf(r))}
                        </span>
                        <div className="min-w-0">
                          <div className="truncate font-bold" style={{ color: 'var(--color-ink)' }}>{nameOf(r)}</div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs" style={{ color: 'var(--color-ink-faint)' }}>{r.employee_id}</span>
                            {r.entry_type === 'manual' && (
                              <span className="pill !py-0 !text-[10px]" style={{ background: 'var(--color-inactive-bg)', color: 'var(--color-inactive)' }} title={`Manually logged by ${r.created_by ?? 'admin'}: ${r.reason ?? ''}`}>Manual</span>
                            )}
                            {r.entry_type === 'coordinator_manual' && (
                              <span className="pill !py-0 !text-[10px]" style={{ background: 'var(--color-accent-bg)', color: 'var(--color-accent)' }}>Project coordinator</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td style={{ color: 'var(--color-ink-muted)' }}>
                      {r.entry_type === 'coordinator_manual' ? 'Not applicable' : employeeMap[r.employee_id]?.area || '—'}
                    </td>
                    <td><DateTimeCell value={r.received_at_utc} /></td>
                    <td><DateTimeCell value={r.check_in_at_ist} /></td>
                    <td>
                      <span className="code-chip" style={{ background: meta.bg, color: meta.fg }} title={meta.label}>{marker}</span>
                      {canManage && (r.status_change_reason || r.resolution_reason || r.reason) && (
                        <details className="mt-1 text-sm">
                          <summary className="cursor-pointer select-none font-semibold" style={{ color: 'var(--color-accent)' }}>
                            View remark
                          </summary>
                          <p
                            className="mt-1 max-w-56 whitespace-pre-wrap break-words rounded-lg border p-2 text-sm leading-relaxed"
                            style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-sunken)', color: 'var(--color-ink-muted)' }}
                          >
                            {r.status_change_reason || r.resolution_reason || r.reason}
                          </p>
                        </details>
                      )}
                    </td>
                    <td>
                      {r.entry_type === 'coordinator_manual'
                        ? <span className="text-xs" style={{ color: 'var(--color-ink-faint)' }}>Not applicable</span>
                        : <ShiftStatusBadge status={r.shift_status} skipped={r.entry_type === 'manual'} />}
                    </td>
                    <td style={{ color: 'var(--color-ink-muted)' }}>
                      {r.entry_type === 'coordinator_manual' ? 'Not applicable' : r.geofence_display ?? (r.geofence_passed === true ? 'Within range' : r.geofence_passed === false ? 'Outside range' : 'Not verified')}
                    </td>
                    <td><FaceMatchStatus record={r} /></td>
                    <td>
                      {r.verdict === 'flagged' && r.review_status === 'pending' ? (
                        <span className="pill" style={{ background: 'var(--color-absent-bg)', color: 'var(--color-absent)' }} title={r.issues_display.join('; ')}>
                          {r.flag_reason ?? 'REVIEW'}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--color-ink-faint)' }}>—</span>
                      )}
                    </td>
                    <td>
                      <div>{r.review_display ?? (r.verdict === 'verified' ? <span className="text-xs font-semibold" style={{ color: 'var(--color-present)' }}>Automatically verified</span> : <ReviewStatusBadge status={r.review_status} />)}</div>
                      {!!r.previous_flagged_attempts?.length && (
                        <div
                          className="mt-1 text-[11px]"
                          style={{ color: 'var(--color-ink-faint)' }}
                          title={r.previous_flagged_attempts.map((attempt) => attempt.issues_display?.join('; ') || attempt.issues.join('; ')).join('\n')}
                        >
                          Replaced {r.previous_flagged_attempts.length} flagged photo{r.previous_flagged_attempts.length === 1 ? '' : 's'}
                        </div>
                      )}
                    </td>
                    {canManage && (
                      <td className="sticky-right text-right">
                        <div className="flex items-center justify-end gap-1">
                          {r.entry_type !== 'coordinator_manual' && r.verdict === 'flagged' && r.review_status === 'pending' && (
                            <button onClick={() => setResolving(r)} className="btn btn-primary btn-sm">Review</button>
                          )}
                          <button
                            onClick={() => {
                              setEditingStatus(r);
                              const m = attendanceMarker(r);
                              setStatusCode(STATUS_OVERRIDE_OPTIONS.some(([value]) => value === m) ? m : 'P');
                              // Keep the current note when changing status. The
                              // API stores the latest override reason, so an
                              // empty editor here would otherwise erase it on
                              // save if the operator only changes the status.
                              setStatusReason(r.status_change_reason ?? r.resolution_reason ?? r.reason ?? '');
                            }}
                            disabled={!r.attendance_date}
                            className="icon-btn"
                            title={r.attendance_date ? `Change status for ${r.attendance_date}` : 'Attendance date unavailable'}
                            aria-label={`Change status for ${nameOf(r)}`}
                          >
                            <Pencil size={15} />
                          </button>
                          {r.entry_type !== 'coordinator_manual' && (
                            <button
                              onClick={() => removeAttendance(r)}
                              disabled={deletingId === r._id}
                              className="icon-btn hover:!bg-[var(--color-absent-bg)] hover:!text-[var(--color-absent)]"
                              title="Delete attendance record"
                              aria-label={`Delete attendance record for ${employeeMap[r.employee_id]?.name ?? r.employee_id}`}
                            >
                              <Trash2 size={15} />
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
              {!loading && records.length === 0 && (
                <EmptyRow cols={colSpan}>No records match these filters. Try a wider date range or clear a filter.</EmptyRow>
              )}
            </tbody>
          </table>
        </div>

        <TableFooter>
          <span>{total.toLocaleString('en-IN')} total records</span>
          {totalPages > 1 && <Pager page={page} pages={totalPages} onPage={setPage} />}
        </TableFooter>
      </div>

      {resolving && (
        <ResolveModal
          record={resolving}
          onClose={() => setResolving(null)}
          onResolved={async () => {
            setResolving(null);
            setStatsTick((n) => n + 1);
            // Reapply the active status filter after the review decision. For
            // example, approving a flagged item removes it from an Absent or
            // Flagged view immediately and refreshes the matching total.
            await load();
          }}
        />
      )}

      {editingStatus && (
        createPortal(<div className="modal-backdrop overflow-y-auto" role="dialog" aria-modal="true" aria-label="Change attendance status" style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', overflowY: 'auto', padding: '1rem', background: 'rgba(12, 31, 63, 0.68)', backdropFilter: 'blur(2px)' }}>
          <div className="modal w-full max-w-2xl p-6" style={{ position: 'relative', display: 'block', flex: '0 0 auto', width: 'min(42rem, calc(100vw - 2rem))', minHeight: 'min(22rem, calc(100vh - 2rem))', maxHeight: 'calc(100vh - 2rem)', overflowY: 'auto', boxSizing: 'border-box', margin: 'auto', transform: 'none', animation: 'none', background: '#fff', color: '#12203a', border: '2px solid #d9e2f0', borderRadius: '1rem', opacity: 1, boxShadow: '0 24px 60px -12px rgba(12, 31, 63, 0.55)' }}>
            <h2 className="mb-1 text-lg font-extrabold" style={{ color: 'var(--color-ink)' }}>Change attendance status</h2>
            <p className="mb-5 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
              {employeeMap[editingStatus.employee_id]?.name ?? editingStatus.employee_name ?? editingStatus.employee_id}
              {' · '}{editingStatus.employee_id}{' · '}{editingStatus.attendance_date}
            </p>
            <label className="field-label">New status</label>
            <select value={statusCode} onChange={(event) => setStatusCode(event.target.value)} className="field mb-4 w-full">
              {(editingStatus.entry_type === 'coordinator_manual'
                ? STATUS_OVERRIDE_OPTIONS.filter(([value]) => value === 'P' || value === 'A')
                : STATUS_OVERRIDE_OPTIONS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <label className="field-label">Reason for change (optional)</label>
            <textarea value={statusReason} onChange={(event) => setStatusReason(event.target.value)} rows={3} className="field w-full resize-y" />
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setEditingStatus(null)} className="btn btn-ghost">Cancel</button>
              <button onClick={() => void saveStatusOverride()} disabled={savingStatus} className="btn btn-primary">
                {savingStatus ? 'Saving…' : 'Save status'}
              </button>
            </div>
          </div>
        </div>, document.body)
      )}

      {exportOpen && <ExportPanel coordinators={coordinators} includeCoordinatorAttendance={includeCoordinatorAttendance} onClose={() => setExportOpen(false)} />}

      {manualEntryOpen && (
        <ManualEntryModal
          onClose={() => setManualEntryOpen(false)}
          onCreated={() => {
            setManualEntryOpen(false);
            setStatsTick((n) => n + 1);
            load();
          }}
        />
      )}
    </div>
  );
}
