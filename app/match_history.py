"""Public per-overlay match-history listing at ``/matches/{public_token}``.

This is the spectator-facing index the board's "match history" share link
points at. It mirrors the access model of ``/match/{id}/report``:

* open when ``MATCH_REPORT_PUBLIC=true`` (anyone with the unguessable
  ``public_token`` can browse the overlay's archived matches), otherwise
* the overlay **owner**, authenticated by their session cookie.

The page is server-rendered (no SPA / login dependency), with server-side
sort (date or duration, ascending or descending) and pagination driven by
query params, and a per-row link to the full match report. It never offers
delete — that lives on the owner's account Reports page.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.api import match_archive
from app.env_vars_manager import EnvVarsManager
from app.match_report_i18n import resolve_locale
from app.overlay_key import make_skey

match_history_router = APIRouter()

PAGE_SIZE = 20

# Self-contained strings (kept out of the big report i18n table). One dict
# per supported locale; English is the fallback for any missing key/locale.
_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Match history — {label}", "date": "Date", "match": "Match",
        "duration": "Duration", "open": "Open report",
        "empty": "No archived matches yet.", "minutes": "{n} min",
        "prev": "Previous", "next": "Next", "pageOf": "Page {page} of {pages}",
        "allTypes": "All types", "indoor": "Indoor", "beach": "Beach",
        "table_tennis": "Table tennis",
    },
    "es": {
        "title": "Historial de partidos — {label}", "date": "Fecha", "match": "Partido",
        "duration": "Duración", "open": "Abrir informe",
        "empty": "Aún no hay partidos archivados.", "minutes": "{n} min",
        "prev": "Anterior", "next": "Siguiente", "pageOf": "Página {page} de {pages}",
        "allTypes": "Todas", "indoor": "Pista", "beach": "Playa",
        "table_tennis": "Tenis de mesa",
    },
    "pt": {
        "title": "Histórico de jogos — {label}", "date": "Data", "match": "Jogo",
        "duration": "Duração", "open": "Abrir relatório",
        "empty": "Ainda não há jogos arquivados.", "minutes": "{n} min",
        "prev": "Anterior", "next": "Seguinte", "pageOf": "Página {page} de {pages}",
        "allTypes": "Todas", "indoor": "Pista", "beach": "Praia",
        "table_tennis": "Tênis de mesa",
    },
    "it": {
        "title": "Storico partite — {label}", "date": "Data", "match": "Partita",
        "duration": "Durata", "open": "Apri report",
        "empty": "Nessuna partita archiviata.", "minutes": "{n} min",
        "prev": "Precedente", "next": "Successivo", "pageOf": "Pagina {page} di {pages}",
        "allTypes": "Tutti", "indoor": "Indoor", "beach": "Beach",
        "table_tennis": "Ping pong",
    },
    "fr": {
        "title": "Historique des matchs — {label}", "date": "Date", "match": "Match",
        "duration": "Durée", "open": "Ouvrir le rapport",
        "empty": "Aucun match archivé.", "minutes": "{n} min",
        "prev": "Précédent", "next": "Suivant", "pageOf": "Page {page} sur {pages}",
        "allTypes": "Tous", "indoor": "Indoor", "beach": "Beach",
        "table_tennis": "Tennis de table",
    },
    "de": {
        "title": "Spielverlauf — {label}", "date": "Datum", "match": "Spiel",
        "duration": "Dauer", "open": "Bericht öffnen",
        "empty": "Noch keine archivierten Spiele.", "minutes": "{n} Min",
        "prev": "Zurück", "next": "Weiter", "pageOf": "Seite {page} von {pages}",
        "allTypes": "Alle", "indoor": "Halle", "beach": "Beach",
        "table_tennis": "Tischtennis",
    },
}

_VALID_MODES = ("indoor", "beach", "table_tennis")


def _t(locale: str, key: str, **kwargs: object) -> str:
    table = _STRINGS.get(locale, _STRINGS["en"])
    template = table.get(key) or _STRINGS["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template


def _resolve_overlay(public_token: str) -> tuple[int, str, str] | None:
    """Return ``(owner_id, skey, label)`` for *public_token*, or ``None``."""
    from app import overlays_service
    from app.db.engine import session_scope

    with session_scope() as db:
        ov = overlays_service.get_by_public_token(db, public_token)
        if ov is None:
            return None
        label = ov.display_name or ov.oid
        return ov.user_id, make_skey(ov.user_id, ov.oid), label


def _cookie_owns(request: Request, owner_id: int) -> bool:
    from app.auth import sessions
    from app.db.engine import session_scope

    raw = request.cookies.get(sessions.COOKIE_NAME)
    if not raw:
        return False
    with session_scope() as db:
        user = sessions.resolve_session(db, raw)
        return user is not None and user.id == owner_id


def _sorted(matches: list[dict], sort: str, direction: str) -> list[dict]:
    key = "duration_s" if sort == "duration" else "ended_at"
    reverse = direction != "asc"
    return sorted(matches, key=lambda m: m.get(key) or 0, reverse=reverse)


def _fmt_date(ended_at: object) -> str:
    if not isinstance(ended_at, (int, float)):
        return "—"
    return datetime.fromtimestamp(ended_at, tz=UTC).strftime("%Y-%m-%d %H:%M")


def _fmt_duration(locale: str, duration_s: object) -> str:
    if not isinstance(duration_s, (int, float)) or duration_s <= 0:
        return "—"
    return _t(locale, "minutes", n=round(duration_s / 60))


def _teams_cell(locale: str, m: dict) -> str:
    n1 = html.escape(str(m.get("team_1_name") or f"{_STRINGS.get(locale, _STRINGS['en']).get('match', 'Team')} 1"))
    n2 = html.escape(str(m.get("team_2_name") or f"{_STRINGS.get(locale, _STRINGS['en']).get('match', 'Team')} 2"))
    s1 = int(m.get("team_1_sets") or 0)
    s2 = int(m.get("team_2_sets") or 0)
    w = m.get("winning_team")
    c1 = " class='win'" if w == 1 else ""
    c2 = " class='win'" if w == 2 else ""
    return f"<span{c1}>{n1}</span> <b>{s1}–{s2}</b> <span{c2}>{n2}</span>"


def _sort_link(token: str, locale: str, label: str, col: str,
               sort: str, direction: str, mode: str) -> str:
    # Toggle direction when re-clicking the active column; otherwise default
    # to descending. Always jump back to page 1 on a sort change.
    nxt = "asc" if (sort == col and direction != "asc") else "desc"
    arrow = ""
    if sort == col:
        arrow = " ▲" if direction == "asc" else " ▼"
    href = f"/matches/{token}?sort={col}&dir={nxt}&mode={mode}&page=1&lang={locale}"
    return f"<a href='{html.escape(href)}'>{html.escape(label)}{arrow}</a>"


def _filter_links(token: str, locale: str, active_mode: str,
                  sort: str, direction: str) -> str:
    """Match-type filter row: All types · Indoor · Beach · Table tennis."""
    items = [("", _t(locale, "allTypes"))] + [
        (m, _t(locale, m)) for m in _VALID_MODES
    ]
    out = []
    for value, label in items:
        href = f"/matches/{token}?sort={sort}&dir={direction}&mode={value}&page=1&lang={locale}"
        cls = " class='active'" if value == active_mode else ""
        out.append(f"<a{cls} href='{html.escape(href)}'>{html.escape(label)}</a>")
    return "<div class='filters'>" + "".join(out) + "</div>"


def _render(token: str, locale: str, label: str, rows: list[dict],
            sort: str, direction: str, active_mode: str,
            page: int, pages: int) -> str:
    title = _t(locale, "title", label=label)
    filters = _filter_links(token, locale, active_mode, sort, direction)
    if not rows:
        body = filters + f"<p class='empty'>{html.escape(_t(locale, 'empty'))}</p>"
    else:
        trs = []
        for m in rows:
            mid = html.escape(str(m.get("match_id", "")))
            report = f"/match/{mid}/report?lang={locale}"
            trs.append(
                "<tr>"
                f"<td>{html.escape(_fmt_date(m.get('ended_at')))}</td>"
                f"<td>{_teams_cell(locale, m)}</td>"
                f"<td>{html.escape(_fmt_duration(locale, m.get('duration_s')))}</td>"
                f"<td><a class='btn' href='{html.escape(report)}'>"
                f"{html.escape(_t(locale, 'open'))}</a></td>"
                "</tr>"
            )
        head = (
            "<tr>"
            f"<th>{_sort_link(token, locale, _t(locale, 'date'), 'ended', sort, direction, active_mode)}</th>"
            f"<th>{html.escape(_t(locale, 'match'))}</th>"
            f"<th>{_sort_link(token, locale, _t(locale, 'duration'), 'duration', sort, direction, active_mode)}</th>"
            "<th></th></tr>"
        )
        pager = ""
        if pages > 1:
            base = f"/matches/{token}?sort={sort}&dir={direction}&mode={active_mode}&lang={locale}"
            prev_d = f"<a class='btn' href='{html.escape(base + f'&page={page - 1}')}'>{html.escape(_t(locale, 'prev'))}</a>" if page > 1 else "<span class='btn disabled'>" + html.escape(_t(locale, "prev")) + "</span>"
            next_d = f"<a class='btn' href='{html.escape(base + f'&page={page + 1}')}'>{html.escape(_t(locale, 'next'))}</a>" if page < pages else "<span class='btn disabled'>" + html.escape(_t(locale, "next")) + "</span>"
            pager = (
                "<div class='pager'>" + prev_d
                + f"<span>{html.escape(_t(locale, 'pageOf', page=page, pages=pages))}</span>"
                + next_d + "</div>"
            )
        body = (
            filters + "<table><thead>" + head + "</thead><tbody>"
            + "".join(trs) + "</tbody></table>" + pager
        )
    return f"""<!DOCTYPE html>
<html lang="{html.escape(locale)}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ background:#0f1115; color:#e7e9ee; font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif; margin:0; padding:24px; }}
h1 {{ font-size:1.3rem; margin:0 0 16px; }}
.filters {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }}
.filters a {{ border:1px solid #2c333f; border-radius:999px; padding:4px 12px; color:#cfd4dd; text-decoration:none; font-size:0.85rem; }}
.filters a:hover {{ background:#20262f; }}
.filters a.active {{ background:#4f8cff; border-color:#4f8cff; color:#fff; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ text-align:left; padding:9px 10px; border-bottom:1px solid #232833; font-size:0.92rem; }}
th {{ color:#98a2b3; }}
th a {{ color:#98a2b3; text-decoration:none; white-space:nowrap; }}
th a:hover {{ color:#e6e9ef; }}
.win {{ font-weight:700; color:#fff; }}
.btn {{ display:inline-block; border:1px solid #2c333f; border-radius:8px; padding:5px 10px; color:#cfd4dd; text-decoration:none; font-size:0.85rem; }}
.btn:hover {{ background:#20262f; }}
.btn.disabled {{ opacity:0.45; }}
.pager {{ display:flex; gap:12px; align-items:center; margin-top:16px; }}
.pager span {{ color:#98a2b3; font-size:0.85rem; }}
.empty {{ color:#98a2b3; }}
</style></head>
<body><h1>{html.escape(title)}</h1>{body}</body></html>"""


@match_history_router.get(
    "/matches/{public_token}",
    response_class=HTMLResponse,
    summary="Public per-overlay archived-match listing",
)
async def match_history(
    public_token: str,
    request: Request,
    sort: str = Query(default="ended"),
    dir: str = Query(default="desc"),
    mode: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    lang: str | None = Query(default=None),
    accept_language: str | None = Header(default=None),
):
    resolved = _resolve_overlay(public_token)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Not found.")
    owner_id, skey, label = resolved

    public = EnvVarsManager.get_bool_env("MATCH_REPORT_PUBLIC")
    if not public and not _cookie_owns(request, owner_id):
        raise HTTPException(
            status_code=401,
            detail="Sign in as the owner to view this history.",
            headers={"WWW-Authenticate": "Cookie"},
        )

    locale = resolve_locale(lang if lang else accept_language)
    sort = "duration" if sort == "duration" else "ended"
    direction = "asc" if dir == "asc" else "desc"
    active_mode = mode if mode in _VALID_MODES else ""

    matches = match_archive.list_matches(oid=skey)
    if active_mode:
        matches = [m for m in matches if m.get("mode") == active_mode]
    matches = _sorted(matches, sort, direction)
    pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, pages)
    rows = matches[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    return HTMLResponse(
        _render(public_token, locale, label, rows, sort, direction,
                active_mode, page, pages)
    )
