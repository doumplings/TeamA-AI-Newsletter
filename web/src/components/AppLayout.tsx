import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';
import { DemoBanner, Logo } from './ui';

const NAV = [
  { to: '/dashboard', label: 'Overview', end: true, icon: 'M3 12l9-8 9 8M5 10v10h14V10' },
  { to: '/dashboard/notifications', label: 'Notifications', end: false, icon: 'M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2c0 .5-.2 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0' },
  { to: '/dashboard/history', label: 'History', end: false, icon: 'M12 8v4l3 3M21 12a9 9 0 1 1-9-9 9 9 0 0 1 9 9Z' },
];

/** Shell for the signed-in pages: sidebar on desktop, tabs on phones. */
export function AppLayout() {
  const { account, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate('/', { replace: true });
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
      isActive ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
    }`;

  return (
    <div className="min-h-screen">
      <DemoBanner mode={api.mode} />
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <NavLink to="/dashboard"><Logo /></NavLink>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-600 sm:inline">{account?.email}</span>
            <button className="btn-secondary px-3 py-1.5" onClick={handleLogout}>Log out</button>
          </div>
        </div>
        {/* Phone tabs */}
        <nav className="flex gap-1 overflow-x-auto px-4 pb-2 md:hidden">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={linkClass}>{n.label}</NavLink>
          ))}
        </nav>
      </header>

      <div className="mx-auto flex max-w-6xl gap-8 px-4 py-8 sm:px-6">
        <aside className="hidden w-52 shrink-0 md:block">
          <nav className="sticky top-24 space-y-1">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={linkClass}>
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d={n.icon} />
                </svg>
                {n.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
