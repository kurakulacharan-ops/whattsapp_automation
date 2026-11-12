import { useCallback, useEffect, useState } from 'react';
import { deleteCalendarEvent, getAttendanceCalendar, saveCalendarEvent, type AttendanceCalendarEvent } from '../api/attendance';

const EVENT_LABELS: Record<AttendanceCalendarEvent['kind'], string> = {
  holiday: 'Holiday', weekoff: 'Week-off', other: 'Other non-working day', working_day: 'Working-day exception',
};
const EVENT_OPTIONS: AttendanceCalendarEvent['kind'][] = ['weekoff', 'holiday', 'other', 'working_day'];
const todayInIndia = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const isSunday = (date: string) => Boolean(date) && new Date(`${date}T00:00:00Z`).getUTCDay() === 0;
const changedAtInIndia = (value?: string) => {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
};

export function AttendanceCalendarPage() {
  const [monthDate, setMonthDate] = useState(() => `${todayInIndia().slice(0, 7)}-01`);
  const [events, setEvents] = useState<AttendanceCalendarEvent[]>([]);
  const [eventDate, setEventDate] = useState(todayInIndia);
  const [eventKind, setEventKind] = useState<AttendanceCalendarEvent['kind']>('weekoff');
  const [eventName, setEventName] = useState('');
  const [editingDate, setEditingDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const month = Number(monthDate.slice(5, 7));
  const year = Number(monthDate.slice(0, 4));
  const selectedSunday = isSunday(eventDate);
  const selectedDateHasEntry = events.some((item) => item.event_date === eventDate);
  const weekoffAlreadyDefaulted = selectedSunday && eventKind === 'weekoff' && !selectedDateHasEntry;
  const eventOptions = EVENT_OPTIONS.filter((kind) => kind !== 'working_day' || selectedSunday || eventKind === 'working_day');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const result = await getAttendanceCalendar(month, year);
      setEvents(result.events);
    } catch { setError('Could not load the attendance calendar.'); }
    finally { setLoading(false); }
  }, [month, year]);

  useEffect(() => { void load(); }, [load]);

  async function submitEvent(event: React.FormEvent) {
    event.preventDefault();
    if (!eventDate || !eventName.trim()) return;
    if (eventKind === 'working_day' && !selectedSunday) {
      setError('A Working-day exception can only be added to a Sunday.');
      return;
    }
    if (weekoffAlreadyDefaulted) {
      setError('Sunday is already a week-off by default. Add another date-specific entry only if needed.');
      return;
    }
    setSaving(true); setError(''); setNotice('');
    try {
      const movingDate = Boolean(editingDate && editingDate !== eventDate);
      if (movingDate) {
        const targetMonth = await getAttendanceCalendar(Number(eventDate.slice(5, 7)), Number(eventDate.slice(0, 4)));
        if (targetMonth.events.some((item) => item.event_date === eventDate)) {
          setError('That date already has a calendar entry. Edit or remove it first.');
          return;
        }
      }
      const saved = await saveCalendarEvent({ event_date: eventDate, kind: eventKind, name: eventName.trim() });
      if (movingDate && editingDate) {
        try {
          await deleteCalendarEvent(editingDate);
        } catch {
          await deleteCalendarEvent(eventDate);
          throw new Error('Could not move the calendar entry. The original entry was kept.');
        }
      }
      setEventName('');
      setEditingDate(null);
      setNotice(movingDate ? 'Calendar entry updated and moved.' : editingDate ? 'Calendar entry updated.' : 'Calendar date saved.');
      setMonthDate(`${eventDate.slice(0, 7)}-01`);
      setEvents((current) => [saved, ...current.filter((item) => item.event_date !== saved.event_date && item.event_date !== editingDate)]
        .sort((left, right) => left.event_date.localeCompare(right.event_date)));
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save the calendar date.'); }
    finally { setSaving(false); }
  }

  function cancelEdit() {
    setEditingDate(null);
    setEventDate(todayInIndia());
    setEventKind('weekoff');
    setEventName('');
    setError('');
    setNotice('');
  }

  async function removeEvent(date: string) {
    setError(''); setNotice('');
    try { await deleteCalendarEvent(date); setNotice('Calendar date removed.'); await load(); }
    catch { setError('Could not remove the calendar date.'); }
  }

  return <section className="mx-auto max-w-5xl space-y-5">
    <header><h1 className="text-lg font-medium" style={{ color: 'var(--color-ink)' }}>Holiday &amp; Week-off Calendar</h1>
      <p className="mt-1 text-sm" style={{ color: 'var(--color-ink-muted)' }}>Sunday is always a week-off by default. To make one particular Sunday a working day, add a Working-day exception for that date. Extra week-offs and holidays can also be added by date.</p></header>

    {error && <p role="alert" className="text-sm" style={{ color: 'var(--color-absent)' }}>{error}</p>}
    {notice && <p role="status" className="text-sm" style={{ color: 'var(--color-present)' }}>{notice}</p>}

    <div className="rounded-lg border px-4 py-3 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)', color: 'var(--color-ink-muted)' }}>
      <strong style={{ color: 'var(--color-ink)' }}>Default: Sundays are week-offs.</strong> This default stays on. A Working-day exception changes only the selected Sunday.
    </div>

    <div className="rounded-lg border p-4" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}>
      <h2 className="font-medium" style={{ color: 'var(--color-ink)' }}>{editingDate ? `Editing entry for ${editingDate}` : 'Add a calendar date'}</h2>
      <p className="mt-1 text-xs" style={{ color: 'var(--color-ink-muted)' }}>{editingDate ? 'Change the date, type, or note, then select Update entry. Cancel edit discards your form changes.' : 'Use Edit beside an entry to change its date, type, or note. Use Remove to undo it.'}</p>
      <form onSubmit={(event) => void submitEvent(event)} className="mt-3 flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs" style={{ color: 'var(--color-ink-muted)' }}>Date<input required type="date" value={eventDate} onChange={(e) => setEventDate(e.target.value)} className="rounded-md border px-2 py-2 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }} /></label>
        <label className="grid gap-1 text-xs" style={{ color: 'var(--color-ink-muted)' }}>Type<select value={eventKind} onChange={(e) => setEventKind(e.target.value as AttendanceCalendarEvent['kind'])} className="rounded-md border px-2 py-2 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}>{eventOptions.map((value) => <option key={value} value={value}>{EVENT_LABELS[value]}</option>)}</select></label>
        <label className="grid min-w-52 flex-1 gap-1 text-xs" style={{ color: 'var(--color-ink-muted)' }}>Name / note<input required maxLength={120} value={eventName} onChange={(e) => setEventName(e.target.value)} placeholder="For example, Diwali" className="rounded-md border px-2 py-2 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }} /></label>
        <button disabled={saving || weekoffAlreadyDefaulted || (eventKind === 'working_day' && !selectedSunday)} className="rounded-md px-3 py-2 text-sm font-medium text-white disabled:opacity-50" style={{ background: 'var(--color-accent)' }}>{saving ? 'Saving…' : editingDate ? 'Update entry' : 'Save date'}</button>
        {editingDate && <button type="button" disabled={saving} onClick={cancelEdit} className="rounded-md border px-3 py-2 text-sm disabled:opacity-50" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}>Cancel edit</button>}
      </form>
      {selectedSunday && eventKind === 'weekoff' && !selectedDateHasEntry && <p className="mt-2 text-xs" style={{ color: 'var(--color-ink-muted)' }}>This Sunday is already a week-off by default. To make it a working day, choose Working-day exception.</p>}
      {eventKind === 'working_day' && !selectedSunday && <p className="mt-2 text-xs" style={{ color: 'var(--color-absent)' }}>Working-day exceptions apply only to Sundays. This selected date is not a Sunday.</p>}
    </div>

    <div className="rounded-lg border" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4" style={{ borderColor: 'var(--color-border)' }}><h2 className="font-medium" style={{ color: 'var(--color-ink)' }}>Date entries <span className="text-xs" style={{ color: 'var(--color-ink-muted)' }}>({events.length})</span></h2><label className="text-sm" style={{ color: 'var(--color-ink-muted)' }}>Month <input aria-label="Calendar month" type="month" value={monthDate.slice(0, 7)} onChange={(e) => setMonthDate(`${e.target.value}-01`)} className="ml-2 rounded-md border px-2 py-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }} /></label></div>
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead style={{ background: 'var(--color-surface-sunken)' }}><tr>{['Date', 'Type', 'Name / note', 'Last changed by', 'Last changed (IST)', 'Action'].map((heading) => <th key={heading} className="px-4 py-2.5 text-left text-xs" style={{ color: 'var(--color-ink-muted)' }}>{heading}</th>)}</tr></thead><tbody>
        {events.map((event) => <tr key={event.event_date} className="border-t" style={{ borderColor: 'var(--color-border-subtle)' }}><td className="px-4 py-2.5">{event.event_date}</td><td className="px-4 py-2.5">{EVENT_LABELS[event.kind]}</td><td className="px-4 py-2.5">{event.name || '—'}</td><td className="px-4 py-2.5">{event.updated_by || event.created_by || '—'}</td><td className="px-4 py-2.5">{changedAtInIndia(event.updated_at_utc)}</td><td className="px-4 py-2.5"><button onClick={() => { setEventDate(event.event_date); setEventKind(event.kind); setEventName(event.name); setEditingDate(event.event_date); setError(''); setNotice(''); window.scrollTo({ top: 0, behavior: 'smooth' }); }} className="mr-3 text-xs" style={{ color: 'var(--color-accent)' }}>Edit</button><button onClick={() => void removeEvent(event.event_date)} className="text-xs" style={{ color: 'var(--color-absent)' }}>Remove</button></td></tr>)}
        {!loading && !events.length && <tr><td colSpan={6} className="px-4 py-8 text-center" style={{ color: 'var(--color-ink-muted)' }}>No date-specific entries for this month. Sundays are still week-offs by default.</td></tr>}
      </tbody></table>{loading && <p className="p-3 text-sm" style={{ color: 'var(--color-ink-muted)' }}>Loading…</p>}</div>
    </div>
  </section>;
}
