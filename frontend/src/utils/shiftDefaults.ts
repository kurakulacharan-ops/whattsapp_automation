export function roleShiftDefaults(role: string) {
  return role === 'LSS'
    ? { shift_start: '07:00', shift_end: '15:00', shift_grace_minutes: 60 }
    : { shift_start: '09:00', shift_end: '19:00', shift_grace_minutes: 240 };
}
