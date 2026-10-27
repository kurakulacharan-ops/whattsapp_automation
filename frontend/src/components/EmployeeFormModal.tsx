import { useState } from 'react';
import { roleShiftDefaults } from '../utils/shiftDefaults';
import axios from 'axios';
import { createEmployee, updateEmployee, type CreateEmployeePayload } from '../api/employees';
import type { AttendanceRole, Coordinator, Employee } from '../types';
import { AssignedSiteMap, type SiteValue } from './AssignedSiteMap';

const inputStyle = {
  background: 'var(--color-surface-sunken)',
  borderColor: 'var(--color-border)',
  color: 'var(--color-ink)',
};

export function EmployeeFormModal({
  employee,
  coordinators,
  onClose,
  onSaved,
}: {
  employee: Employee | null; // null = creating new
  coordinators: Coordinator[];
  onClose: () => void;
  onSaved: () => void;
}) {
  // Phone is stored/submitted as the full "91XXXXXXXXXX" form the backend
  // expects (matches sender_phone format seen in real records), but the
  // input itself only ever shows/accepts the 10 local digits — the +91 is
  // a fixed prefix, not something the user types.
  const initialLocalDigits = (employee?.phone_number ?? '').replace(/^91/, '').slice(0, 10);

  const [form, setForm] = useState<CreateEmployeePayload>({
    phone_number: employee?.phone_number ?? '',
    name: employee?.name ?? '',
    role: employee?.role ?? 'FS',
    pc_id: employee?.pc_id ?? undefined,
    parent_employee_id: undefined,
    area: employee?.area ?? undefined,
    designation: employee?.designation ?? undefined,
    location_check_enabled: employee?.location_check_enabled ?? true,
    assigned_site: employee?.assigned_site ?? undefined,
    geofence_radius_km: employee?.geofence_radius_km ?? 8,
    shift_start: employee?.shift_start ?? roleShiftDefaults(employee?.role ?? 'FS').shift_start,
    shift_end: employee?.shift_end ?? roleShiftDefaults(employee?.role ?? 'FS').shift_end,
    shift_grace_minutes: employee?.shift_grace_minutes ?? roleShiftDefaults(employee?.role ?? 'FS').shift_grace_minutes,
  });
  const [phoneDigits, setPhoneDigits] = useState(initialLocalDigits);
  const [saving, setSaving] = useState(false);
  const [site, setSite] = useState<SiteValue | undefined>(employee?.assigned_site ?? undefined);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof CreateEmployeePayload>(key: K, value: CreateEmployeePayload[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function handlePhoneChange(raw: string) {
    const digitsOnly = raw.replace(/\D/g, '').slice(0, 10);
    setPhoneDigits(digitsOnly);
    set('phone_number', digitsOnly ? `91${digitsOnly}` : '');
  }

  function handleNameChange(raw: string) {
    set('name', raw.replace(/[^\p{L} ]/gu, ''));
  }

  const phoneValid = phoneDigits.length === 10;
  const hierarchyValid = Boolean(form.pc_id);
  function handleRoleChange(role: AttendanceRole) {
    setForm((current) => ({
      ...current,
      ...roleShiftDefaults(role),
      location_check_enabled: role === 'FS' ? (current.location_check_enabled ?? true) : true,
      role,
      parent_employee_id: undefined,
    }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...form,
        parent_employee_id: '',
        assigned_site: site ?? null,
        shift_start: form.shift_start || null,
        shift_end: form.shift_end || null,
        shift_grace_minutes: form.shift_grace_minutes ?? null,
      };
      if (employee) {
        await updateEmployee(employee.employee_id, payload);
      } else {
        await createEmployee(payload);
      }
      onSaved();
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        const message = typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((item: { msg?: string }) => item.msg ?? 'Invalid field').join('; ')
            : null;
        setError(message ?? (err.response?.status === 409
          ? 'This phone number is already registered. Edit the existing supervisor instead.'
          : `Could not save employee (HTTP ${err.response?.status ?? 'network error'}).`));
      } else {
        setError('Unexpected error while saving employee.');
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div
        className="w-full max-w-lg rounded-lg border p-6 max-h-[85vh] overflow-y-auto shadow-xl"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}
      >
        <h2 className="text-base font-medium mb-4" style={{ color: 'var(--color-ink)' }}>
          {employee ? `Edit ${employee.employee_id}` : 'New attendance participant'}
        </h2>

        <div className="grid grid-cols-2 gap-3 mb-3">
          <Field label="Department" required>
            <select
              value={form.role}
              onChange={(e) => {
                const value = e.target.value;
                if (value === 'FS' || value === 'LS' || value === 'LSS') handleRoleChange(value);
              }}
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            >
              <option value="FS">Field Supervisor (FS)</option>
              <option value="LS">Local Supervisor (LS)</option>
              <option value="LSS">Local Supervisor Scanning (LSS)</option>
            </select>
          </Field>
          <Field label="Name" required>
            <input
              value={form.name}
              onChange={(e) => handleNameChange(e.target.value)}
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            />
          </Field>
          <Field label="Phone number" required>
            <div
              className="flex items-center rounded-md border overflow-hidden"
              style={{ borderColor: inputStyle.borderColor, background: inputStyle.background }}
            >
              <span
                className="px-3 py-2 text-sm border-r"
                style={{ borderColor: inputStyle.borderColor, color: 'var(--color-ink-muted)' }}
              >
                +91
              </span>
              <input
                value={phoneDigits}
                onChange={(e) => handlePhoneChange(e.target.value)}
                inputMode="numeric"
                placeholder="10-digit number"
                className="flex-1 min-w-0 px-3 py-2 text-sm outline-none"
                style={{ background: 'transparent', color: 'var(--color-ink)' }}
              />
            </div>
            {phoneDigits.length > 0 && !phoneValid && (
              <p className="text-xs mt-1" style={{ color: 'var(--color-absent)' }}>
                Enter all 10 digits.
              </p>
            )}
            <p className="text-xs mt-1" style={{ color: 'var(--color-ink-faint)' }}>
              Use a unique WhatsApp number for each participant so image attendance maps to the right person.
            </p>
            {employee && (
              <p className="text-xs mt-1" style={{ color: 'var(--color-ink-faint)' }}>
                Changing this re-points which WhatsApp number is matched to {employee.employee_id}.
              </p>
            )}
          </Field>
          <Field label="Reports to: Project Co-ordinator" required>
            <select
              value={form.pc_id ?? ''}
              onChange={(e) => set('pc_id', e.target.value || undefined)}
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            >
              <option value="">Select project co-ordinator</option>
              {coordinators.map((c) => (
                <option key={c.pc_id} value={c.pc_id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Area">
            <input
              value={form.area ?? ''}
              onChange={(e) => set('area', e.target.value || undefined)}
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            />
          </Field>
          <Field label="Designation">
            <input
              value={form.designation ?? ''}
              onChange={(e) => set('designation', e.target.value || undefined)}
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            />
          </Field>
          <Field label="Grace period (min)">
            <input
              type="number"
              value={form.shift_grace_minutes ?? ''}
              onChange={(e) => set('shift_grace_minutes', e.target.value ? Number(e.target.value) : undefined)}
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            />
          </Field>
          <Field label="Shift start">
            <input
              type="time"
              value={form.shift_start ?? ''}
              onChange={(e) => set('shift_start', e.target.value || undefined)}
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            />
          </Field>
          <Field label="Shift end">
            <input
              type="time"
              value={form.shift_end ?? ''}
              onChange={(e) => set('shift_end', e.target.value || undefined)}
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            />
          </Field>
        </div>

        {form.role === 'FS' && (
          <label className="block mb-4 text-sm">
            <input type="checkbox" checked={form.location_check_enabled !== false}
              onChange={(e) => set('location_check_enabled', e.target.checked)} className="mr-2" />
            Enable location check
            <span className="block mt-1 text-xs">When disabled, GPS, distance and city/town do not affect attendance. Photo date/time and face checks still apply.</span>
          </label>
        )}
        {(form.role !== 'FS' || form.location_check_enabled !== false) && <>
        <label className="block mb-4 text-sm">Allowed range (km)
          <input type="number" min="0.01" step="any" value={form.geofence_radius_km ?? 8}
            onChange={(e) => set('geofence_radius_km', Number(e.target.value))}
            className="block w-full px-3 py-2 rounded-md text-sm border" style={inputStyle} />
          <span className="text-xs">Default: 8 km. Change only when needed. Outside this range, check the same city/town.</span>
        </label>
        <div className="mb-4"><AssignedSiteMap site={site} onChange={setSite} /></div>
        </>}

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
            onClick={handleSave}
            disabled={saving || !form.name.trim() || !phoneValid || !hierarchyValid || !Number.isFinite(form.geofence_radius_km) || (form.geofence_radius_km ?? 0) <= 0}
            className="px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
            style={{ background: 'var(--color-accent)', color: 'white' }}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>
        {label}
        {required && ' *'}
      </label>
      {children}
    </div>
  );
}