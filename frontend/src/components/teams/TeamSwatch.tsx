import type { TeamOut } from '../../api/client';

/** The coloured square that previews a team's logo (or its initial) on its
 *  background + text colours. Shared by the cards and the inline editors. */
export function SwatchBox({
  color, textColor, icon, name, size = 30,
}: {
  color?: string | null;
  textColor?: string | null;
  icon?: string | null;
  name: string;
  size?: number;
}) {
  return (
    <span
      className="acc-tswatch"
      style={{ width: size, height: size, background: color || '#444', color: textColor || '#fff' }}
      title={`bg ${color || '—'} / text ${textColor || '—'}`}
    >
      {icon ? (
        <img src={icon} alt="" />
      ) : (
        (name.trim()[0] || '?').toUpperCase()
      )}
    </span>
  );
}

export function TeamSwatch({ team }: { team: TeamOut }) {
  return <SwatchBox color={team.color} textColor={team.text_color} icon={team.icon} name={team.name} />;
}
