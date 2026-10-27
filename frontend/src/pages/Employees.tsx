import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { deleteEmployee, listEmployees, updateEmployee } from '../api/employees';
import { listCoordinators } from '../api/coordinators';
import { downloadExport, downloadParticipantDetails } from '../api/attendance';
import type { Coordinator, Employee } from '../types';
import { EmployeeFormModal } from '../components/EmployeeFormModal';
import { EnrollFaceModal } from '../components/EnrollFaceModal';
import { Download, ScanFace, Pencil, Trash2, UserX, UserCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const PAGE_SIZE = 25;

export function EmployeesPage() {
  const { canManage } = useAuth();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [coordinators, setCoordinators] = useState<Coordinator[]>([]);
  const [areas, setAreas] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pcFilter, setPcFilter] = useState(
    () => new URLSearchParams(window.location.search).get('pc_id') ?? ''
  );
  const [areaFilter, setAreaFilter] = useState(
    () => new URLSearchParams(window.location.search).get('area') ?? ''
  );
  const [showInactive, setShowInactive] = useState(false);
  const [search, setSearch] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [exportingId, setExportingId] = useState<string | null>(null);

  const [editing, setEditing] = useState<Employee | null | 'new'>(null);
  const [enrolling, setEnrolling] = useState<Employee | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEmployees({
        pc_id: pcFilter || undefined,
        area: areaFilter || undefined,
        is_active: showInactive ? undefined : true,
        search: search || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setEmployees(data.employees);
      setTotal(data.total);
    } catch {
      setError('Could not load attendance participants.');
    } finally {
      setLoading(false);
    }
  }, [pcFilter, areaFilter, showInactive, search, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [pcFilter, areaFilter, showInactive, search]);

  useEffect(() => {
    Promise.all([
      listCoordinators({ page_size: 500 }),
      listEmployees({ pc_id: pcFilter || undefined, page_size: 100000 }),
    ])
      .then(([coordinatorResult, participantResult]) => {
        setCoordinators(coordinatorResult.coordinators);
        setAreas([...new Set(
          participantResult.employees
            .map((employee) => employee.area?.trim())
            .filter((area): area is string => Boolean(area))
        )].sort((a, b) => a.localeCompare(b)));
      })
      .catch(() => setError('Could not load coordinator or area filters.'));
  }, [pcFilter]);

  async function toggleActive(emp: Employee) {
    setError(null);
    try {
      await updateEmployee(emp.employee_id, { is_active: !emp.is_active });
      if (emp.is_active) {
        // Keep the newly inactive participant visible so deactivation is not
        // mistaken for deletion; the row is labelled with its inactive date.
        setShowInactive(true);
      } else {
        await load();
      }
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(
        typeof detail === 'string'
          ? detail
          : `Could not ${emp.is_active ? 'deactivate' : 'reactivate'} participant. Please try again.`
      );
    }
  }

  async function removeEmployee(employee: Employee) {
    if (!window.confirm(`Delete ${employee.name} (${employee.employee_id})? Current attendance records, overrides, and child assignments must be cleared first. Superseded attempt history is retained for audit.`)) {
      return;
    }

    setDeletingId(employee.employee_id);
    setError(null);
    try {
      await deleteEmployee(employee.employee_id);
      await load();
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === 'string' ? detail : 'Could not delete participant. Please try again.');
    } finally {
      setDeletingId(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const now = new Date();

  async function exportEmployeeAttendance(employee: Employee) {
    setExportingId(employee.employee_id);
    setError(null);
    try {
      await downloadExport({
        month: now.getMonth() + 1,
        year: now.getFullYear(),
        employee_id: employee.employee_id,
      });
    } catch {
      setError(`Could not export attendance for ${employee.name}. Please try again.`);
    } finally {
      setExportingId(null);
    }
  }

  async function exportFilteredAttendance() {
    setExportingId('filtered');
    setError(null);
    try {
      await downloadExport({
        month: now.getMonth() + 1,
        year: now.getFullYear(),
        pc_id: pcFilter || undefined,
        area: areaFilter || undefined,
      });
    } catch {
      setError('Could not export attendance for these filters. Please try again.');
    } finally {
      setExportingId(null);
    }
  }

  async function exportFilteredParticipantDetails() {
    setExportingId('details');
    setError(null);
    try {
      await downloadParticipantDetails({
        pc_id: pcFilter || undefined,
        area: areaFilter || undefined,
        is_active: showInactive ? undefined : true,
        search: search || undefined,
      });
    } catch {
      setError('Could not export participant details for these filters. Please try again.');
    } finally {
      setExportingId(null);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-medium" style={{ color: 'var(--color-ink)' }}>
            Attendance Participants
          </h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-ink-muted)' }}>
            Each attendance participant reports directly to a project co-ordinator.
          </p>
        </div>
        {canManage && (
          <div className="flex gap-2">
            <button
              onClick={() => void exportFilteredAttendance()}
              disabled={exportingId !== null}
              className="px-3 py-1.5 rounded-md text-sm font-medium border disabled:opacity-50"
              style={{ borderColor: 'var(--color-border)', color: 'var(--color-present)' }}
            >
              Export filtered attendance
            </button>
            <button
              onClick={() => void exportFilteredParticipantDetails()}
              disabled={exportingId !== null}
              className="px-3 py-1.5 rounded-md text-sm font-medium border disabled:opacity-50"
              style={{ borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
            >
              Export participant details
            </button>
            <button
              onClick={() => setEditing('new')}
              className="px-3 py-1.5 rounded-md text-sm font-medium"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              Add participant
            </button>
          </div>
        )}
      </div>

      <div className="flex gap-2 mb-5 items-center flex-wrap">
        <select
          value={pcFilter}
          onChange={(e) => setPcFilter(e.target.value)}
          className="px-2 py-1.5 rounded-md text-sm border"
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
        <select
          value={areaFilter}
          onChange={(e) => setAreaFilter(e.target.value)}
          aria-label="Filter by participant area"
          className="px-2 py-1.5 rounded-md text-sm border"
          style={{
            background: 'var(--color-surface-raised)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-ink-muted)',
          }}
        >
          <option value="">All areas</option>
          {areas.map((area) => <option key={area} value={area}>{area}</option>)}
        </select>
        {(pcFilter || areaFilter) && (
          <button
            onClick={() => {
              setPcFilter('');
              setAreaFilter('');
              window.history.replaceState(null, '', window.location.pathname);
            }}
            className="px-2 py-1.5 rounded-md text-sm border"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}
          >
            Clear coordinator/area
          </button>
        )}
        <label className="flex items-center gap-1.5 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          Show inactive
        </label>
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
        <p role="alert" className="mb-4 text-sm" style={{ color: 'var(--color-flagged)' }}>
          {error}
        </p>
      )}

      <div className="rounded-lg border overflow-hidden shadow-sm" style={{ borderColor: 'var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-surface-sunken)' }}>
              {['S.No', 'ID', 'Name', 'Department', 'Reports To', 'Area', 'Designation', 'Status', ...(canManage ? ['Action'] : [])].map((h) => (
                <th
                  key={h}
                  className={`px-4 py-2.5 text-xs font-medium ${h === 'Action' ? 'text-right' : 'text-left'}`}
                  style={{ color: 'var(--color-ink-faint)' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {employees.map((emp, index) => (
              <tr key={emp.employee_id} className="border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {(page - 1) * PAGE_SIZE + index + 1}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink)' }}>
                  {emp.employee_id}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink)' }}>
                  {emp.name}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {emp.role}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {coordinators.find((coordinator) => coordinator.pc_id === emp.pc_id)?.name ?? '—'}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {emp.area ?? '—'}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {emp.designation ?? '—'}
                </td>
                <td
                  className="px-4 py-2.5"
                  style={{ color: emp.is_active ? 'var(--color-present)' : 'var(--color-inactive)' }}
                >
                  {emp.is_active ? 'Active' : `Inactive since ${emp.deactivated_at}`}
                </td>
                {canManage && <td className="px-4 py-2.5 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => void exportEmployeeAttendance(emp)}
                      disabled={exportingId !== null}
                      className="p-1.5 rounded-md transition-colors hover:bg-[var(--color-accent-bg)] disabled:opacity-40"
                      style={{ color: 'var(--color-present)' }}
                      title="Export this participant's monthly attendance"
                      aria-label={`Export attendance for ${emp.name}`}
                    >
                      <Download size={16} />
                    </button>
                    <button
                      onClick={() => setEnrolling(emp)}
                      className="p-1.5 rounded-md transition-colors hover:bg-[var(--color-accent-bg)]"
                      style={{ color: 'var(--color-accent)' }}
                      title="Enroll face"
                    >
                      <ScanFace size={16} />
                    </button>
                    <button
                      onClick={() => setEditing(emp)}
                      className="p-1.5 rounded-md transition-colors hover:bg-[var(--color-accent-bg)]"
                      style={{ color: 'var(--color-accent)' }}
                      title="Edit"
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      onClick={() => toggleActive(emp)}
                      className="p-1.5 rounded-md transition-colors hover:bg-black/5"
                      style={{ color: 'var(--color-ink-muted)' }}
                      title={emp.is_active ? 'Deactivate' : 'Reactivate'}
                      aria-label={`${emp.is_active ? 'Deactivate' : 'Reactivate'} participant ${emp.name}`}
                    >
                      {emp.is_active ? <UserX size={16} /> : <UserCheck size={16} />}
                    </button>
                    <button
                      onClick={() => removeEmployee(emp)}
                      disabled={deletingId === emp.employee_id}
                      className="p-1.5 rounded-md transition-colors hover:bg-black/5 disabled:opacity-40"
                      style={{ color: 'var(--color-flagged)' }}
                      title="Delete participant"
                      aria-label={`Delete participant ${emp.name}`}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </td>}
              </tr>
            ))}
            {!loading && employees.length === 0 && (
              <tr>
                <td colSpan={canManage ? 9 : 8} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--color-ink-faint)' }}>
                  No attendance participants match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div
          className="px-4 py-2.5 border-t text-xs"
          style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-ink-muted)' }}
        >
          Total attendance participants: {total}
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

      {canManage && editing && (
        <EmployeeFormModal
          employee={editing === 'new' ? null : editing}
          coordinators={coordinators}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      {canManage && enrolling && <EnrollFaceModal employee={enrolling} onClose={() => setEnrolling(null)} />}
    </div>
  );
}