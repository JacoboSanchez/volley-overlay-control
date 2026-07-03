import { useState } from 'react';
import type { TeamOut } from '../../api/client';

/** The coloured square that previews a team's logo (or its initial) on its
 *  background + text colours. Shared by the cards and the inline editors.
 *  A logo URL that fails to load (deleted library icon, dead external link)
 *  falls back to the initial instead of a broken-image glyph. */
export function SwatchBox({
  color, textColor, icon, name, size = 30,
}: {
  color?: string | null;
  textColor?: string | null;
  icon?: string | null;
  name: string;
  size?: number;
}) {
  // Track which URL failed so a later icon change retries the <img>.
  const [failedFor, setFailedFor] = useState<string | null>(null);
  const showImage = Boolean(icon) && failedFor !== icon;
  return (
    <span
      className="acc-tswatch"
      style={{ width: size, height: size, background: color || '#444', color: textColor || '#fff' }}
      title={`bg ${color || '—'} / text ${textColor || '—'}`}
    >
      {showImage ? (
        <img src={icon!} alt="" onError={() => setFailedFor(icon!)} />
      ) : (
        (name.trim()[0] || '?').toUpperCase()
      )}
    </span>
  );
}

export function TeamSwatch({ team }: { team: TeamOut }) {
  return <SwatchBox color={team.color} textColor={team.text_color} icon={team.icon} name={team.name} />;
}
