import { afterEach, describe, expect, it, vi } from 'vitest';
import APP_SRC from '../../../overlay_static/js/app.js?raw';
import { stylePreviewAppearance } from '../styles/preview';

const previewWindow = window as typeof window & { OVERLAY_PREVIEW_STATE?: Record<string, any> };
afterEach(() => {
  delete previewWindow.OVERLAY_PREVIEW_STATE;
});

function sample() {
  return {
    team_home: { name: 'Team A', points: 25 },
    team_away: { name: 'Team B', points: 21 },
    overlay_control: { show_logos: true, points_by_set: { 3: [1, 2, 1] } },
    raw_remote_customization: {},
    match_info: { summary_set_num: 3 },
  };
}

function renderer() {
  const render = vi.fn();
  const handler = new Function(
    'render',
    APP_SRC +
      `
    processStateUpdate = render;
    return applyStylePreviewAppearance;
  `,
  )(render) as (event: MessageEvent) => void;
  return { render, handler };
}

function message(appearance: unknown, origin = window.location.origin, source = window.parent) {
  return new MessageEvent('message', {
    origin,
    source,
    data: { type: 'stylePreviewAppearance', appearance },
  });
}

describe('isolated style appearance', () => {
  it('uses the configured teams, colours and logos while keeping sample scores and history', () => {
    const model = {
      'Team 1 Text Name': '東京 VC',
      'Team 1 Name': 'old name',
      'Team 2 Name': 'São Paulo',
      'Team 1 Color': '#00aa66',
      'Team 2 Color': '#9933cc',
      'Team 1 Logo': '/media/icons/home.webp',
      'Team 2 Logo': '',
      Logos: 'false',
      'Color 1': '#123456',
      verticalAnchor: 'bottom',
      control_token: 'private-secret',
    };
    const appearance = stylePreviewAppearance(model, (key) => key);
    expect(appearance.team_home.name).toBe('東京 VC');
    expect(JSON.stringify(appearance)).not.toContain('private-secret');
    const base = sample();
    previewWindow.OVERLAY_PREVIEW_STATE = base;
    const { handler, render } = renderer();
    handler(
      message({
        ...appearance,
        team_home: { ...appearance.team_home, points: 999 },
        match_info: { summary_set_num: 1 },
      }),
    );
    const state = render.mock.calls[0]![0];
    expect(state.team_home).toMatchObject({ ...appearance.team_home, points: 25 });
    expect(state.team_away).toMatchObject({ ...appearance.team_away, points: 21 });
    expect(state.overlay_control).toMatchObject({
      show_logos: false,
      colors: { set_bg: '#123456' },
      points_by_set: { 3: [1, 2, 1] },
    });
    expect(state.match_info.summary_set_num).toBe(3);
    expect(state.raw_remote_customization.verticalAnchor).toBe('bottom');
    expect(base.team_home.name).toBe('Team A');
  });

  it('rejects other origins, siblings and malformed messages, and ignores messages on live outputs', () => {
    previewWindow.OVERLAY_PREVIEW_STATE = sample();
    const { handler, render } = renderer();
    handler(message({}, 'https://other.example'));
    const sibling = document.createElement('iframe');
    document.body.appendChild(sibling);
    handler(message({}, window.location.origin, sibling.contentWindow!));
    sibling.remove();
    handler(message(null));
    handler(message('not an object'));
    delete previewWindow.OVERLAY_PREVIEW_STATE;
    handler(message({}));
    expect(render).not.toHaveBeenCalled();
  });

  it('keeps deliberately empty team names and uses neutral translated fallbacks only when missing', () => {
    const t = (key: string) => (key === 'stylePicker.team1' ? 'Equipo A' : 'Equipo B');
    expect(stylePreviewAppearance({}, t).team_home.name).toBe('Equipo A');
    expect(
      stylePreviewAppearance({ 'Team 1 Text Name': '', 'Team 1 Name': 'ignored' }, t).team_home
        .name,
    ).toBe('');
  });
});
