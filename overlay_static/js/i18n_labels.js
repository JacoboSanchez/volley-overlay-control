/* ─────────────────────────────────────────────────────────────────
   Shared overlay label bundle.

   Translations used by more than one overlay-side script
   (set_summary.js, spectator.js) live here so a wording fix lands
   everywhere at once. Only strings that are byte-identical across
   every locale in both consumers belong in this bundle — labels
   whose translation legitimately differs per surface (e.g. the
   spectator's "Saques ganados" vs the recap's "Servicios ganados")
   stay in the consumer's local dictionary.

   Contract:
   * Plain non-module script. Must be loaded via a <script> tag
     BEFORE any consumer (see overlay_templates/base.html and
     overlay_templates/_spectator.html).
   * Consumers must look the bundle up defensively
     (``window.OVERLAY_LABELS || {}``) so a stale cached page that
     missed this file degrades to its local/English labels instead
     of crashing.
   * Keys are flat camelCase; each consumer maps its own key
     scheme onto these via a small alias table.
   ───────────────────────────────────────────────────────────────── */

window.OVERLAY_LABELS = {
  en: {
    set: 'Set', match: 'Match', totalPoints: 'Total points',
    kill: 'Kill', block: 'Block',
  },
  es: {
    set: 'Set', match: 'Partido', totalPoints: 'Puntos totales',
    kill: 'Ataque', block: 'Bloqueo',
  },
  pt: {
    set: 'Set', match: 'Partida', totalPoints: 'Pontos totais',
    kill: 'Ataque', block: 'Bloco',
  },
  it: {
    set: 'Set', match: 'Partita', totalPoints: 'Punti totali',
    kill: 'Attacco', block: 'Muro',
  },
  fr: {
    set: 'Set', match: 'Match', totalPoints: 'Points totaux',
    kill: 'Attaque', block: 'Contre',
  },
  de: {
    set: 'Satz', match: 'Spiel', totalPoints: 'Punkte gesamt',
    kill: 'Angriff', block: 'Block',
  },
};
