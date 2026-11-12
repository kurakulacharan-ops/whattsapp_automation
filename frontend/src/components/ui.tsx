import type { CSSProperties, ReactNode } from 'react';

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[1.65rem] font-extrabold leading-tight" style={{ color: 'var(--color-ink)' }}>{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm" style={{ color: 'var(--color-ink-muted)' }}>{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Kpi({ label, value, hint, accent, loading }: { label: string; value: ReactNode; hint?: ReactNode; accent?: string; loading?: boolean }) {
  return (
    <div className="card relative overflow-hidden px-4 py-3.5">
      <span className="absolute inset-y-3 left-0 w-1 rounded-r" style={{ background: accent ?? 'var(--color-border)' }} />
      <div className="text-xs font-semibold" style={{ color: 'var(--color-ink-muted)' }}>{label}</div>
      {loading ? <div className="skeleton mt-2 h-8 w-16" /> : <div className="mt-1 text-[1.75rem] font-extrabold leading-none" style={{ color: 'var(--color-ink)' }}>{value}</div>}
      {hint && <div className="mt-1.5 text-xs" style={{ color: 'var(--color-ink-faint)' }}>{hint}</div>}
    </div>
  );
}

export function Panel({ title, subtitle, children, action, className = '', style }: { title: string; subtitle?: ReactNode; children: ReactNode; action?: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <section className={`card p-5 ${className}`} style={style}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div><h2 className="text-[0.95rem] font-bold" style={{ color: 'var(--color-ink)' }}>{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs" style={{ color: 'var(--color-ink-faint)' }}>{subtitle}</p>}</div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Notice({ tone, children }: { tone: 'error' | 'warn' | 'ok' | 'info'; children: ReactNode }) {
  const t = { error: ['var(--color-absent)', 'var(--color-absent-bg)'], warn: ['var(--color-flagged)', 'var(--color-flagged-bg)'], ok: ['var(--color-present)', 'var(--color-present-bg)'], info: ['var(--color-accent)', 'var(--color-accent-bg)'] }[tone];
  return <p role={tone === 'error' || tone === 'warn' ? 'alert' : 'status'} className="mb-4 rounded-xl px-4 py-2.5 text-sm font-semibold" style={{ color: t[0], background: t[1] }}>{children}</p>;
}

export function TableFooter({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-3 text-xs font-medium" style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-ink-muted)' }}>{children}</div>;
}

export function Pager({ page, pages, onPage }: { page: number; pages: number; onPage: (p: number) => void }) {
  return (
    <div className="flex items-center gap-2">
      <button className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => onPage(Math.max(1, page - 1))}>Previous</button>
      <span className="px-1 font-semibold">Page {page} of {pages}</span>
      <button className="btn btn-secondary btn-sm" disabled={page >= pages} onClick={() => onPage(Math.min(pages, page + 1))}>Next</button>
    </div>
  );
}

export function EmptyRow({ cols, children }: { cols: number; children: ReactNode }) {
  return <tr><td colSpan={cols} className="!py-14 text-center text-sm" style={{ color: 'var(--color-ink-faint)' }}>{children}</td></tr>;
}

export function SkeletonRows({ cols, rows = 6 }: { cols: number; rows?: number }) {
  return <>{Array.from({ length: rows }, (_, r) => <tr key={r}>{Array.from({ length: cols }, (_, c) => <td key={c}><div className="skeleton h-4" style={{ width: `${55 + ((r + c) % 4) * 11}%` }} /></td>)}</tr>)}</>;
}

export function StatusPill({ tone, children }: { tone: 'ok' | 'bad' | 'warn' | 'mute'; children: ReactNode }) {
  const t = { ok: ['var(--color-present)', 'var(--color-present-bg)'], bad: ['var(--color-absent)', 'var(--color-absent-bg)'], warn: ['var(--color-flagged)', 'var(--color-flagged-bg)'], mute: ['var(--color-inactive)', 'var(--color-inactive-bg)'] }[tone];
  return <span className="pill" style={{ color: t[0], background: t[1] }}><span className="h-1.5 w-1.5 rounded-full" style={{ background: t[0] }} />{children}</span>;
}
