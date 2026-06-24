import { useState } from 'react';
import type { TeamFields, TeamOut } from '../../api/client';
import { DEFAULT_COLOR, DEFAULT_TEXT_COLOR, hex } from './teamUtils';

/** Editable draft of a team's authoring fields (name / logo / colours), shared
 *  by every create form and inline editor so the field set stays identical. */
export interface TeamDraft {
  name: string;
  setName: (v: string) => void;
  icon: string;
  setIcon: (v: string) => void;
  color: string;
  setColor: (v: string) => void;
  textColor: string;
  setTextColor: (v: string) => void;
  /** Reset every field back to a team (or to blank defaults when omitted). */
  reset: (team?: TeamOut | null) => void;
  /** Normalised payload for the create/update API (trimmed, blank logo → null). */
  toFields: () => TeamFields;
}

export function useTeamDraft(initial?: TeamOut | null): TeamDraft {
  const [name, setName] = useState(initial?.name ?? '');
  const [icon, setIcon] = useState(initial?.icon ?? '');
  const [color, setColor] = useState(hex(initial?.color, DEFAULT_COLOR));
  const [textColor, setTextColor] = useState(hex(initial?.text_color, DEFAULT_TEXT_COLOR));

  function reset(team?: TeamOut | null) {
    setName(team?.name ?? '');
    setIcon(team?.icon ?? '');
    setColor(hex(team?.color, DEFAULT_COLOR));
    setTextColor(hex(team?.text_color, DEFAULT_TEXT_COLOR));
  }

  function toFields(): TeamFields {
    return {
      name: name.trim(),
      icon: icon.trim() || null,
      color,
      text_color: textColor,
    };
  }

  return {
    name, setName, icon, setIcon, color, setColor, textColor, setTextColor,
    reset, toFields,
  };
}
