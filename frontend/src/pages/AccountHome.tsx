import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';

export default function AccountHome() {
  const { ctx } = useAuth();
  const name = ctx?.user?.display_name || ctx?.user?.username;
  const [overlayCount, setOverlayCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const ovs = await api.getOverlays();
        if (!cancelled) setOverlayCount(ovs.length);
      } catch {
        /* leave unknown — don't push an error onto the dashboard */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div>
      <h2>Welcome, {name}</h2>
      <p className="acc-muted">
        Manage your scoreboards, teams, presets and match reports from here.
      </p>
      {overlayCount === 0 && (
        <div className="acc-info" style={{ marginTop: 16 }}>
          <strong>Get started:</strong> create your first scoreboard, then copy its OBS URL to put it
          on stream. <Link to="/overlays">Create a scoreboard →</Link>
        </div>
      )}
      <div className="acc-tile-grid">
        <Tile to="/overlays" title="My overlays" desc="Create scoreboards and copy OBS URLs." />
        <Tile to="/teams" title="Teams" desc="Build your team list from the catalog and groups." />
        <Tile to="/presets" title="Presets" desc="Your saved looks and the global presets." />
        <Tile to="/reports" title="Reports" desc="Per-scoreboard archived match reports." />
        <Tile to="/account" title="Account" desc="Change password, edit profile, delete account." />
      </div>
    </div>
  );
}

function Tile({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <Link to={to} className="acc-tile">
      <div className="acc-tile-title">{title}</div>
      <div className="acc-muted">{desc}</div>
    </Link>
  );
}
