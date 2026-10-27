import { useState } from 'react';
import {
  createManualEntry,
  DuplicateSubmissionError,
  overrideAttendanceCell,
  searchAttendancePeople,
} from '../api/attendance';
import type { AttendanceRecord, Employee } from '../types';

const today = new Date().toISOString().slice(0, 10);
const STATUS_OPTIONS = [
  ['P', 'Present'],
  ['L', 'Late'],
  ['A', 'Absent'],
  ['AL', 'Absent late'],
  ['HD', 'Half day'],
  ['WO', 'Week off'],
  ['H', 'Holiday'],
] as const;

export function ManualEntryModal({
  onClose,
  onCreated,
  onStatusChanged,
}: {
  onClose: () => void;
  onCreated: (record: AttendanceRecord) => void;
  onStatusChanged?: (date: string) => void;
}) {
  const [employeeQuery, setEmployeeQuery] = useState('');
  const [employeeOptions, setEmployeeOptions] = useState<Employee[]>([]);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [date, setDate] = useState(today);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [statusOverrideExists, setStatusOverrideExists] = useState(false);
  const [statusCode, setStatusCode] = useState('P');
  const [statusReason, setStatusReason] = useState('');
  const [savingStatus, setSavingStatus] = useState(false);

  async function handleSearch(query: string) {
    setEmployeeQuery(query);
    setSelectedEmployee(null);
    setStatusOverrideExists(false);
    setError(null);
    if (query.trim().length < 2) {
      setEmployeeOptions([]);
      return;
    }
    setSearching(true);
    try {
      const { people } = await searchAttendancePeople(query, 8);
      setEmployeeOptions(people);
    } finally {
      setSearching(false);
    }
  }

  async function handleSubmit() {
    if (!selectedEmployee || !reason.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const record = await createManualEntry({
        employee_id: selectedEmployee.employee_id,
        date,
        reason: reason.trim(),
      });
      onCreated(record);
    } catch (err) {
      if (err instanceof DuplicateSubmissionError) {
        setStatusOverrideExists(err.statusOverrideExists);
        setStatusCode(err.attendanceCode ?? 'P');
        setError(err.message);
      } else {
        setError('Could not create this entry. Check the details and try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStatusChange() {
    if (!selectedEmployee) return;
    setSavingStatus(true);
    setError(null);
    try {
      await overrideAttendanceCell({
        employee_id: selectedEmployee.employee_id,
        date,
        attendance_code: statusCode,
        reason: statusReason.trim() || undefined,
      });
      if (onStatusChanged) onStatusChanged(date);
      else onClose();
    } catch {
      setError('Could not change the saved attendance status. Please try again.');
    } finally {
      setSavingStatus(false);
    }
  }

  const inputStyle = {
    background: 'var(--color-surface-sunken)',
    borderColor: 'var(--color-border)',
    color: 'var(--color-ink)',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div
        className="w-full max-w-md rounded-lg border p-6 shadow-xl"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}
      >
        <h2 className="text-base font-medium mb-1" style={{ color: 'var(--color-ink)' }}>
          Log manual entry
        </h2>
        <p className="text-sm mb-4" style={{ color: 'var(--color-ink-muted)' }}>
          Use only when the WhatsApp/verification pipeline couldn't be used — this bypasses
          geofence, face and shift checks entirely and is marked Present directly.
        </p>

        <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>
          Attendance participant
        </label>
        {selectedEmployee ? (
          <div
            className="flex items-center justify-between px-3 py-2 rounded-md text-sm border mb-4"
            style={inputStyle}
          >
            <span>{selectedEmployee.name} · {selectedEmployee.employee_id}</span>
            <button
              onClick={() => {
                setSelectedEmployee(null);
                setEmployeeQuery('');
                setStatusOverrideExists(false);
                setError(null);
              }}
              className="text-xs"
              style={{ color: 'var(--color-accent)' }}
            >
              Change
            </button>
          </div>
        ) : (
          <div className="mb-4 relative">
            <input
              value={employeeQuery}
              onChange={(event) => void handleSearch(event.target.value)}
              placeholder="Search by name or phone…"
              className="w-full px-3 py-2 rounded-md text-sm border"
              style={inputStyle}
            />
            {employeeOptions.length > 0 && (
              <div
                className="absolute z-10 w-full mt-1 rounded-md border max-h-48 overflow-y-auto"
                style={{ background: 'var(--color-surface-raised)', borderColor: 'var(--color-border)' }}
              >
                {employeeOptions.map((employee) => (
                  <button
                    key={employee.employee_id}
                    onClick={() => {
                      setSelectedEmployee(employee);
                      setEmployeeOptions([]);
                    }}
                    className="block w-full text-left px-3 py-2 text-sm hover:bg-black/5"
                    style={{ color: 'var(--color-ink)' }}
                  >
                    {employee.name} · {employee.employee_id}
                  </button>
                ))}
              </div>
            )}
            {searching && (
              <p className="text-xs mt-1" style={{ color: 'var(--color-ink-faint)' }}>Searching…</p>
            )}
          </div>
        )}

        <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>Date</label>
        <input
          type="date"
          value={date}
          max={today}
          onChange={(event) => {
            setDate(event.target.value);
            setStatusOverrideExists(false);
            setError(null);
          }}
          className="w-full mb-4 px-3 py-2 rounded-md text-sm border"
          style={inputStyle}
        />

        {statusOverrideExists ? (
          <div className="mb-4 rounded-md border p-3" style={{ borderColor: 'var(--color-border)' }}>
            <p className="text-sm font-medium mb-3" style={{ color: 'var(--color-ink)' }}>
              Change the saved status instead
            </p>
            <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>
              Attendance status
            </label>
            <select
              value={statusCode}
              onChange={(event) => setStatusCode(event.target.value)}
              className="w-full px-3 py-2 rounded-md text-sm border mb-3"
              style={inputStyle}
            >
              {STATUS_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>
              Reason for change (optional)
            </label>
            <textarea
              value={statusReason}
              onChange={(event) => setStatusReason(event.target.value)}
              rows={2}
              className="w-full px-3 py-2 rounded-md text-sm border resize-none"
              style={inputStyle}
            />
          </div>
        ) : (
          <>
            <label className="block text-xs mb-1" style={{ color: 'var(--color-ink-muted)' }}>
              Reason *
            </label>
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={2}
              placeholder="e.g. Phone died, confirmed present by call"
              className="w-full mb-4 px-3 py-2 rounded-md text-sm border outline-none resize-none"
              style={inputStyle}
            />
          </>
        )}

        {error && (
          <p className="text-xs mb-3" role="alert" style={{ color: 'var(--color-absent)' }}>
            {error}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-md text-sm"
            style={{ color: 'var(--color-ink-muted)' }}
          >
            Cancel
          </button>
          {statusOverrideExists ? (
            <button
              onClick={() => void handleStatusChange()}
              disabled={savingStatus}
              className="px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              {savingStatus ? 'Saving…' : 'Save status'}
            </button>
          ) : (
            <button
              onClick={() => void handleSubmit()}
              disabled={!selectedEmployee || !reason.trim() || submitting}
              className="px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              {submitting ? 'Saving…' : 'Log entry'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
