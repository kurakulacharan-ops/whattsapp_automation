import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { deleteCoordinator, listCoordinators, updateCoordinator } from '../api/coordinators';
import { listEmployees } from '../api/employees';
import { downloadCoordinatorDetails, downloadExport } from '../api/attendance';
import type { Coordinator, Employee } from '../types';
import { CoordinatorFormModal } from '../components/CoordinatorFormModal';
import { Download, Pencil, Trash2, UserX, UserCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const PAGE_SIZE = 25;

export function CoordinatorsPage() {
  const { canManage } = useAuth();
  const [coordinators, setCoordinators] = useState<Coordinator[]>([]);
  const [areasByCoordinator, setAreasByCoordinator] = useState<Record<string, string[]>>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Coordinator | 'new' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [exportingDetails, setExportingDetails] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, participantData] = await Promise.all([
        listCoordinators({ page, page_size: PAGE_SIZE, search: search || undefined }),
        listEmployees({ page_size: 100000 }),
      ]);
      setCoordinators(data.coordinators);
      setTotal(data.total);
      const areas: Record<string, Set<string>> = {};
      participantData.employees.forEach((employee: Employee) => {
        const area = employee.area?.trim();
        if (employee.pc_id && area) {
          (areas[employee.pc_id] ??= new Set()).add(area);
        }
      });
      setAreasByCoordinator(Object.fromEntries(
        Object.entries(areas).map(([pcId, values]) => [pcId, [...values].sort((a, b) => a.localeCompare(b))])
      ));
    } catch {
      setError('Could not load coordinators.');
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [search]);

  async function toggleActive(c: Coordinator) {
    setError(null);
    try {
      await updateCoordinator(c.pc_id, { is_active: !c.is_active });
      await load();
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(
        typeof detail === 'string'
          ? detail
          : `Could not ${c.is_active ? 'deactivate' : 'reactivate'} coordinator. Please try again.`
      );
    }
  }

  async function removeCoordinator(coordinator: Coordinator) {
    if (!window.confirm(`Delete coordinator ${coordinator.name} (${coordinator.pc_id})? Reassign all participants linked to this coordinator first. Historical attendance entries do not block deletion.`)) {
      return;
    }

    setDeletingId(coordinator.pc_id);
    setError(null);
    try {
      await deleteCoordinator(coordinator.pc_id);
      await load();
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === 'string' ? detail : 'Could not delete coordinator. Please try again.');
    } finally {
      setDeletingId(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const now = new Date();

  async function exportCoordinatorAttendance(coordinator: Coordinator) {
    setExportingId(coordinator.pc_id);
    setError(null);
    try {
      await downloadExport({
        month: now.getMonth() + 1,
        year: now.getFullYear(),
        pc_id: coordinator.pc_id,
      });
    } catch {
      setError(`Could not export attendance for ${coordinator.name}. Please try again.`);
    } finally {
      setExportingId(null);
    }
  }

  async function exportCoordinatorDetails() {
    setExportingDetails(true);
    setError(null);
    try {
      await downloadCoordinatorDetails(search || undefined);
    } catch {
      setError('Could not export project coordinator details. Please try again.');
    } finally {
      setExportingDetails(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-medium" style={{ color: 'var(--color-ink)' }}>
          Project Co-Ordinators
        </h1>
        {canManage && (
          <div className="flex gap-2">
            <button
              onClick={() => void exportCoordinatorDetails()}
              disabled={exportingDetails}
              className="px-3 py-1.5 rounded-md text-sm font-medium border disabled:opacity-50"
              style={{ borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
            >
              {exportingDetails ? 'Exporting…' : 'Export project coordinator details'}
            </button>
            <button
              onClick={() => setEditing('new')}
              className="px-3 py-1.5 rounded-md text-sm font-medium"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              Add project co-ordinator
            </button>
          </div>
        )}
      </div>

      <div className="mb-5">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name or phone…"
          className="px-3 py-1.5 rounded-md text-sm border w-64"
          style={{
            background: 'var(--color-surface-raised)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-ink)',
          }}
        />
      </div>

      {canManage && editing && (
        <CoordinatorFormModal
          coordinator={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      {error && (
        <p role="alert" className="mb-4 text-sm" style={{ color: 'var(--color-flagged)' }}>
          {error}
        </p>
      )}

      <div className="rounded-lg border overflow-hidden shadow-sm" style={{ borderColor: 'var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-surface-sunken)' }}>
              {['S.No', 'ID', 'Name', 'Phone', 'Status', 'Participant Areas', ...(canManage ? ['Action'] : [])].map((h) => (
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
            {coordinators.map((c, index) => (
              <tr key={c.pc_id} className="border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {(page - 1) * PAGE_SIZE + index + 1}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink)' }}>
                  {c.pc_id}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink)' }}>
                  {c.name}
                </td>
                <td className="px-4 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>
                  {c.phone_number ?? '—'}
                </td>
                <td
                  className="px-4 py-2.5"
                  style={{ color: c.is_active ? 'var(--color-present)' : 'var(--color-inactive)' }}
                >
                  {c.is_active ? 'Active' : `Inactive since ${c.deactivated_at ?? '—'}`}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex flex-wrap items-center justify-end gap-1">
                    {areasByCoordinator[c.pc_id]?.map((area) => (
                      <a
                        key={area}
                        href={`/employees?pc_id=${encodeURIComponent(c.pc_id)}&area=${encodeURIComponent(area)}`}
                        className="px-2 py-1 rounded border text-xs hover:bg-black/5"
                        style={{ borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
                        title={`Show ${area} participants assigned to ${c.name}`}
                      >
                        {area}
                      </a>
                    ))}
                    {canManage && <button
                      onClick={() => void exportCoordinatorAttendance(c)}
                      disabled={exportingId === c.pc_id}
                      className="p-1.5 rounded-md transition-colors hover:bg-[var(--color-accent-bg)] disabled:opacity-40"
                      style={{ color: 'var(--color-present)' }}
                      title="Export this coordinator's monthly participant attendance"
                      aria-label={`Export attendance for coordinator ${c.name}`}
                    >
                      <Download size={16} />
                    </button>}
                  </div>
                </td>
                {canManage && <td className="px-4 py-2.5 text-right">
                  {canManage && <button
                    onClick={() => setEditing(c)}
                    className="p-1.5 rounded-md transition-colors hover:bg-[var(--color-accent-bg)]"
                    style={{ color: 'var(--color-accent)' }}
                    title="Edit coordinator profile"
                  >
                    <Pencil size={16} />
                  </button>}
                  {canManage && <button
                    onClick={() => toggleActive(c)}
                    className="p-1.5 rounded-md transition-colors hover:bg-black/5"
                    style={{ color: 'var(--color-ink-muted)' }}
                    title={c.is_active ? 'Deactivate' : 'Reactivate'}
                    aria-label={`${c.is_active ? 'Deactivate' : 'Reactivate'} coordinator ${c.name}`}
                  >
                    {c.is_active ? <UserX size={16} /> : <UserCheck size={16} />}
                  </button>}
                  {canManage && <button
                    onClick={() => removeCoordinator(c)}
                    disabled={deletingId === c.pc_id}
                    className="p-1.5 rounded-md transition-colors hover:bg-black/5 disabled:opacity-40"
                    style={{ color: 'var(--color-flagged)' }}
                    title="Delete coordinator"
                    aria-label={`Delete coordinator ${c.name}`}
                  >
                    <Trash2 size={16} />
                  </button>}
                </td>}
              </tr>
            ))}
            {!loading && coordinators.length === 0 && (
              <tr>
                <td colSpan={canManage ? 7 : 6} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--color-ink-faint)' }}>
                  No coordinators match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div
          className="px-4 py-2.5 border-t text-xs"
          style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-ink-muted)' }}
        >
          Total project co-ordinators: {total}
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
    </div>
  );
}