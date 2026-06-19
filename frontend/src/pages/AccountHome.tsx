import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function AccountHome() {
  const { ctx } = useAuth();
  const name = ctx?.user?.display_name || ctx?.user?.username;
  return (
    <div>
      <h2>Welcome, {name}</h2>
      <p className="acc-muted">
        Manage your scoreboards, teams, presets and match reports from here.
      </p>
      <div
        style={{
          display: 'grid',
          gap: 14,
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          marginTop: 18,
        }}
      >
        <Card to="/overlays" title="My overlays" desc="Create scoreboards and copy OBS URLs." />
        <Card to="/teams" title="Teams" desc="Build your team list from the catalog and groups." />
        <Card to="/presets" title="Presets" desc="Your saved looks and the global presets." />
        <Card to="/reports" title="Reports" desc="Per-scoreboard archived match reports." />
        <Card to="/account" title="Account" desc="Change password, edit profile, delete account." />
      </div>
    </div>
  );
}

function Card({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <Link
      to={to}
      style={{
        textDecoration: 'none',
        color: 'inherit',
        background: '#181b22',
        border: '1px solid #262b35',
        borderRadius: 12,
        padding: 16,
        display: 'block',
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{title}</div>
      <div className="acc-muted">{desc}</div>
    </Link>
  );
}
