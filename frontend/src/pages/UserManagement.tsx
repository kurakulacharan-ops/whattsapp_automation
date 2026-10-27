import { useCallback, useEffect, useState, type FormEvent } from 'react';
import axios from 'axios';
import { listUsers, registerUser } from '../api/auth';
import { useAuth } from '../context/AuthContext';
import type { AccountRole, UserAccount } from '../types';

export function UserManagementPage() {
  const { role } = useAuth();
  const [users, setUsers] = useState<UserAccount[] | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [newRole, setNewRole] = useState<'manual_team' | 'viewer'>('viewer');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadUsers = useCallback(async () => {
    try {
      setUsers(await listUsers());
      setError(null);
    } catch {
      setError('Could not load user accounts.');
      setUsers([]);
    }
  }, []);

  useEffect(() => {
    let active = true;
    listUsers()
      .then((accounts) => {
        if (active) setUsers(accounts);
      })
      .catch(() => {
        if (active) {
          setError('Could not load user accounts.');
          setUsers([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await registerUser({ username: username.trim(), password, role: newRole });
      setUsername('');
      setPassword('');
      setNotice('User account created. Share the credentials with the intended user.');
      await loadUsers();
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === 'string' ? detail : 'Could not create the user account.');
    } finally {
      setSubmitting(false);
    }
  }

  function roleLabel(accountRole: AccountRole) {
    if (accountRole === 'super_admin') return 'Bootstrap admin';
    return accountRole === 'manual_team' ? 'Manual team (can edit)' : 'Viewer (read-only)';
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-medium" style={{ color: 'var(--color-ink)' }}>User access</h1>
        <p className="mt-1 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
          Create credentials for staff. Viewers can see attendance and roster details but cannot change records.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="max-w-xl space-y-4 rounded-lg border p-5 shadow-sm"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}
      >
        <h2 className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>Register account</h2>
        <div>
          <label htmlFor="new-username" className="mb-1 block text-xs" style={{ color: 'var(--color-ink-muted)' }}>
            Username
          </label>
          <input
            id="new-username"
            required
            minLength={3}
            maxLength={50}
            pattern="[A-Za-z0-9_.-]+"
            autoComplete="off"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="w-full rounded-md border px-3 py-2 text-sm"
            style={{ background: 'var(--color-surface-sunken)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
          />
          <p className="mt-1 text-xs" style={{ color: 'var(--color-ink-faint)' }}>
            Use 3–50 letters, numbers, dots, dashes, or underscores.
          </p>
        </div>
        <div>
          <label htmlFor="new-password" className="mb-1 block text-xs" style={{ color: 'var(--color-ink-muted)' }}>
            Temporary password
          </label>
          <input
            id="new-password"
            type="password"
            required
            minLength={8}
            maxLength={72}
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-md border px-3 py-2 text-sm"
            style={{ background: 'var(--color-surface-sunken)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
          />
          <p className="mt-1 text-xs" style={{ color: 'var(--color-ink-faint)' }}>
            At least 8 characters. Give credentials directly to the intended user.
          </p>
        </div>
        <div>
          <label htmlFor="new-role" className="mb-1 block text-xs" style={{ color: 'var(--color-ink-muted)' }}>
            Access
          </label>
          <select
            id="new-role"
            value={newRole}
            onChange={(event) => setNewRole(event.target.value as 'manual_team' | 'viewer')}
            className="w-full rounded-md border px-3 py-2 text-sm"
            style={{ background: 'var(--color-surface-sunken)', borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
          >
            <option value="viewer">Viewer — view only</option>
            {role === 'super_admin' && <option value="manual_team">Manual team — review and edit</option>}
          </select>
        </div>
        {error && <p role="alert" className="text-sm" style={{ color: 'var(--color-absent)' }}>{error}</p>}
        {notice && <p role="status" className="text-sm" style={{ color: 'var(--color-present)' }}>{notice}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          style={{ background: 'var(--color-accent)' }}
        >
          {submitting ? 'Registering…' : 'Register user'}
        </button>
      </form>

      <section className="rounded-lg border shadow-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}>
        <h2 className="border-b px-5 py-3 text-sm font-semibold" style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-ink)' }}>
          Registered accounts
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead style={{ background: 'var(--color-surface-sunken)', color: 'var(--color-ink-faint)' }}>
              <tr>
                <th className="px-5 py-2.5 text-xs font-medium">Username</th>
                <th className="px-5 py-2.5 text-xs font-medium">Access</th>
                <th className="px-5 py-2.5 text-xs font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {(users ?? []).map((user) => (
                <tr key={user.username} className="border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
                  <td className="px-5 py-2.5" style={{ color: 'var(--color-ink)' }}>{user.username}</td>
                  <td className="px-5 py-2.5" style={{ color: 'var(--color-ink-muted)' }}>{roleLabel(user.role)}</td>
                  <td className="px-5 py-2.5" style={{ color: user.is_active ? 'var(--color-present)' : 'var(--color-inactive)' }}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </td>
                </tr>
              ))}
              {users !== null && users.length === 0 && (
                <tr><td colSpan={3} className="px-5 py-6 text-center" style={{ color: 'var(--color-ink-faint)' }}>No accounts found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {users === null && <p className="px-5 py-4 text-sm" style={{ color: 'var(--color-ink-muted)' }}>Loading accounts…</p>}
      </section>
    </div>
  );
}
