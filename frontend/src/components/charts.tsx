import { useState, type ReactNode } from 'react';
import { STACK_ORDER, codeMeta } from '../utils/attendanceCodes';

// Lightweight SVG charts. No chart library: keeps the bundle small and lets
// every mark use the attendance-code legend colors directly.

/* ---------- Stacked columns: one column per day ---------- */
export interface DayStack { key: string; label: string; counts: Record<string, number> }

export function StackedColumns({ data, height = 190, emptyLabel = 'No data for this period.' }: {
  data: DayStack[]; height?: number; emptyLabel?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const totals = data.map((d) => STACK_ORDER.reduce((s, c) => s + (d.counts[c] ?? 0), 0));
  const max = Math.max(1, ...totals);
  if (!data.length || totals.every((t) => t === 0)) {
    return <div className="flex items-center justify-center text-sm" style={{ height, color: 'var(--color-ink-faint)' }}>{emptyLabel}</div>;
  }
  const W = Math.max(data.length * 22, 320), padL = 28, padB = 22, padT = 8;
  const innerH = height - padB - padT, slot = (W - padL) / data.length, bw = Math.min(slot * 0.68, 26);
  const ticks = [0, 0.5, 1].map((t) => Math.round(max * t));
  const hovered = hover !== null ? data[hover] : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full" style={{ height }} role="img" aria-label="Daily attendance breakdown">
        {ticks.map((t) => {
          const y = padT + innerH - (t / max) * innerH;
          return <g key={t}><line x1={padL} x2={W} y1={y} y2={y} stroke="var(--color-border-subtle)" /><text x={padL - 6} y={y + 3} textAnchor="end" fontSize="9" fill="var(--color-ink-faint)">{t}</text></g>;
        })}
        {data.map((d, i) => {
          let y = padT + innerH;
          const x = padL + i * slot + (slot - bw) / 2;
          return (
            <g key={d.key} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} opacity={hover === null || hover === i ? 1 : 0.45}>
              <rect x={padL + i * slot} y={padT} width={slot} height={innerH} fill="transparent" />
              <g className="grow-up" style={{ animationDelay: `${Math.min(i * 12, 300)}ms`, transformBox: 'fill-box' }}>
                {STACK_ORDER.map((c) => {
                  const v = d.counts[c] ?? 0;
                  if (!v) return null;
                  const h = (v / max) * innerH; y -= h;
                  return <rect key={c} x={x} y={y} width={bw} height={Math.max(h - 1, 1)} rx={2} fill={codeMeta(c).solid} />;
                })}
              </g>
              {(data.length <= 16 || i % Math.ceil(data.length / 16) === 0) && (
                <text x={x + bw / 2} y={height - 6} textAnchor="middle" fontSize="9" fill="var(--color-ink-faint)">{d.label}</text>
              )}
            </g>
          );
        })}
      </svg>
      {hovered && (
        <div className="pointer-events-none absolute top-1 right-1 rounded-lg px-3 py-2 text-xs shadow-lg" style={{ background: 'var(--color-navy)', color: '#fff' }}>
          <div className="font-bold mb-1">{hovered.key}</div>
          {STACK_ORDER.filter((c) => hovered.counts[c]).map((c) => (
            <div key={c} className="flex items-center gap-2"><span className="h-2 w-2 rounded-sm" style={{ background: codeMeta(c).solid }} />{codeMeta(c).label}<b className="ml-auto pl-4">{hovered.counts[c]}</b></div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- Ring (donut) with center label ---------- */
export function Ring({ value, size = 132, stroke = 14, color = 'var(--color-present)', label, sub }: {
  value: number | null; size?: number; stroke?: number; color?: string; label?: ReactNode; sub?: string;
}) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-border-subtle)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`} style={{ transition: 'stroke-dasharray .8s cubic-bezier(.2,.8,.2,1)' }} />
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-extrabold leading-none" style={{ color: 'var(--color-ink)' }}>{label ?? (value === null ? '—' : `${Math.round(value)}%`)}</div>
        {sub && <div className="mt-1 text-[11px] font-semibold" style={{ color: 'var(--color-ink-faint)' }}>{sub}</div>}
      </div>
    </div>
  );
}

/* ---------- Proportion bar by code ---------- */
export function DistributionBar({ counts, order = STACK_ORDER as readonly string[] }: { counts: Record<string, number>; order?: readonly string[] }) {
  const total = order.reduce((s, c) => s + (counts[c] ?? 0), 0);
  if (!total) return <div className="h-3 rounded-full" style={{ background: 'var(--color-border-subtle)' }} />;
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full" style={{ background: 'var(--color-border-subtle)' }} role="img" aria-label="Status distribution">
        {order.map((c) => counts[c] ? <div key={c} title={`${codeMeta(c).label}: ${counts[c]}`} style={{ width: `${(counts[c] / total) * 100}%`, background: codeMeta(c).solid }} /> : null)}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {order.filter((c) => counts[c]).map((c) => (
          <span key={c} className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: 'var(--color-ink-muted)' }}>
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: codeMeta(c).solid }} />{codeMeta(c).label}
            <b style={{ color: 'var(--color-ink)' }}>{counts[c]}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

/* ---------- Ranked horizontal bars ---------- */
export interface RankRow { key: string; label: string; sub?: string; value: number; display: string; color?: string }

export function RankBars({ rows, color = 'var(--color-accent)', empty = 'Nothing to show yet.' }: { rows: RankRow[]; color?: string; empty?: string }) {
  if (!rows.length) return <p className="py-6 text-center text-sm" style={{ color: 'var(--color-ink-faint)' }}>{empty}</p>;
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.key}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
            <span className="truncate font-semibold" style={{ color: 'var(--color-ink)' }}>{r.label}{r.sub && <span className="ml-2 text-xs font-medium" style={{ color: 'var(--color-ink-faint)' }}>{r.sub}</span>}</span>
            <span className="shrink-0 font-bold">{r.display}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full" style={{ background: 'var(--color-border-subtle)' }}>
            <div className="h-full rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: r.color ?? color, transition: 'width .6s cubic-bezier(.2,.8,.2,1)' }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ---------- Simple single-series bars (e.g. check-in hour) ---------- */
export function MiniBars({ values, labels, color = 'var(--color-accent)', height = 110 }: { values: number[]; labels: string[]; color?: string; height?: number }) {
  const max = Math.max(1, ...values);
  if (values.every((v) => v === 0)) return <div className="flex items-center justify-center text-sm" style={{ height, color: 'var(--color-ink-faint)' }}>No check-in times in this view.</div>;
  return (
    <div className="grid min-w-0 w-full items-end gap-0.5 overflow-hidden" style={{ height, gridTemplateColumns: `repeat(${values.length}, minmax(0, 1fr))` }}>
      {values.map((v, i) => (
        <div key={i} className="flex min-w-0 flex-col items-center justify-end gap-1" style={{ height: '100%' }} title={`${labels[i]}: ${v}`}>
          <span className="whitespace-nowrap text-[7px] font-bold leading-none tracking-[-0.08em]" style={{ color: 'var(--color-ink-muted)' }}>{v || ''}</span>
          <div className="grow-up w-full rounded-t-md" style={{ height: `${Math.max((v / max) * (height - 34), v ? 3 : 0)}px`, background: color, animationDelay: `${i * 30}ms` }} />
          <span className="whitespace-nowrap text-[7px] leading-none tracking-[-0.06em]" style={{ color: 'var(--color-ink-faint)' }}>{labels[i]}</span>
        </div>
      ))}
    </div>
  );
}
