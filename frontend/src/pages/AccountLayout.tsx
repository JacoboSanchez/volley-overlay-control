import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import './account.css';

export default function AccountLayout() {
  const { ctx, refresh } = useAuth();
  const navigate = useNavigate();
  const isAdmin = ctx?.user?.role === 'admin';

  async function onLogout() {
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    await refresh();
    navigate('/login');
  }

  return (
    <div className="acc-shell">
      <div className="acc-layout">
        <nav className="acc-nav">
          <div className="brand">🏐 Overlay Control</div>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/overlays">My overlays</NavLink>
          <NavLink to="/teams">Teams</NavLink>
          <NavLink to="/presets">Presets</NavLink>
          <NavLink to="/reports">Reports</NavLink>
          <NavLink to="/account">Account</NavLink>
          {isAdmin && <NavLink to="/admin">Admin</NavLink>}
          <div className="spacer" />
          <span className="acc-muted" style={{ padding: '6px 10px' }}>
            {ctx?.user?.display_name || ctx?.user?.username}
            {isAdmin && <span className="acc-pill" style={{ marginLeft: 6 }}>admin</span>}
          </span>
          <button className="acc-btn ghost" onClick={onLogout}>Sign out</button>
        </nav>
        <main className="acc-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
