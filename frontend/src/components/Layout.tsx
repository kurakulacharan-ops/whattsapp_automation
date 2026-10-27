import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { CalendarCheck, Users, Share2, PanelLeftClose, PanelLeftOpen, LogOut, UserRoundCog } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const NAV_ITEMS = [
  { to: '/attendance', label: 'Attendance', icon: CalendarCheck },
  { to: '/employees', label: 'Attendance Participants', icon: Users },
  { to: '/coordinators', label: 'Project Co-Ordinators', icon: Share2 },
];

export function Layout() {
  const { logout, canManage } = useAuth();
  const navItems = canManage
    ? [...NAV_ITEMS, { to: '/users', label: 'User access', icon: UserRoundCog }]
    : NAV_ITEMS;
  // "pinned" is the toggle-button state (persists until clicked again).
  // "hovered" is a temporary expand-on-hover while collapsed — mirrors the
  // request for hover-to-open + a manual open/close control, without one
  // overriding the other: pinned always wins, hover only matters when not.
  const [pinned, setPinned] = useState(true);
  const [hovered, setHovered] = useState(false);
  // Clicking the toggle button while the mouse is still resting on the
  // sidebar shouldn't be overridden by the hover-expand behavior — so a
  // click "disarms" hover until the mouse actually leaves and comes back.
  const [hoverArmed, setHoverArmed] = useState(true);
  const expanded = pinned || (hoverArmed && hovered);

  function togglePinned() {
    setPinned((p) => {
      const next = !p;
      if (!next) setHoverArmed(false); // unpinning while hovered: collapse now, re-arm on mouseleave
      return next;
    });
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--color-surface)' }}>
      <header
        className="flex items-center justify-between px-6 py-3 border-b"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}
      >
        <div className="flex items-center gap-4">
          <img src="/brand/bigv-logo-tight.png" alt="bigV telecom" className="h-12 w-auto" />
          <div className="w-px h-8" style={{ background: 'var(--color-border)' }} />
          <span className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
            Attendance Admin Console
          </span>
        </div>
        <div
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
          style={{ background: 'var(--color-present-bg)', color: 'var(--color-present)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-present)' }} />
          System online
        </div>
      </header>

      <div className="flex flex-1">
        <aside
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => {
            setHovered(false);
            setHoverArmed(true); // re-arm for the next hover
          }}
          className="shrink-0 flex flex-col border-r transition-all duration-200"
          style={{
            width: expanded ? '15rem' : '4rem',
            borderColor: 'var(--color-border)',
            background: 'var(--color-surface-raised)',
          }}
        >
          <div className="px-3 py-3 flex justify-end border-b" style={{ borderColor: 'var(--color-border-subtle)' }}>
            <button
              onClick={togglePinned}
              className="p-1.5 rounded-md transition-colors hover:bg-black/5"
              style={{ color: 'var(--color-ink-muted)' }}
              title={pinned ? 'Collapse sidebar' : 'Pin sidebar open'}
            >
              {pinned ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </button>
          </div>

          {expanded && (
            <div className="px-5 pt-4 pb-2">
              <p className="text-[11px] font-medium tracking-wide uppercase" style={{ color: 'var(--color-ink-faint)' }}>
                Operations
              </p>
            </div>
          )}

          <nav className="flex-1 px-3 space-y-0.5">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className="flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors hover:bg-black/5"
                  style={({ isActive }) => ({
                    color: isActive ? 'white' : 'var(--color-ink-muted)',
                    // Only set a background when active — leaving it unset
                    // otherwise lets the hover:bg-black/5 class actually take
                    // effect. An inline "transparent" here would silently
                    // block :hover from ever applying, since inline styles
                    // always beat stylesheet rules regardless of pseudo-class.
                    background: isActive ? 'var(--color-accent)' : undefined,
                    justifyContent: expanded ? 'flex-start' : 'center',
                  })}
                  title={item.label}
                >
                  <Icon size={18} className="shrink-0" />
                  {expanded && <span>{item.label}</span>}
                </NavLink>
              );
            })}
          </nav>

          <div className="px-3 pb-4">
            <button
              onClick={logout}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-white transition-colors bg-[var(--color-absent)] hover:bg-[#b91c1c]"
              style={{ justifyContent: expanded ? 'flex-start' : 'center' }}
              title="Sign out"
            >
              <LogOut size={18} className="shrink-0" />
              {expanded && <span>Sign out</span>}
            </button>
          </div>
        </aside>

        <div className="flex-1 min-w-0 flex flex-col">
          <main className="flex-1">
            <div className="max-w-6xl mx-auto px-8 py-8">
              <Outlet />
            </div>
          </main>

          <footer
            className="px-8 py-2.5 border-t text-center text-[11px]"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)', color: 'var(--color-ink-faint)' }}
          >
            Attendance Review AI Agent · © 2026 Big V Telecom · Internal Operations Tool
          </footer>
        </div>
      </div>
    </div>
  );
}