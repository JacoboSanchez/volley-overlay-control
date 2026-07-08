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

import calendar as _calmod
import html
import re
from datetime import date, datetime

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
        "day": "Day", "filter": "Filter", "allDays": "All days",
        "prevMonth": "Previous month", "nextMonth": "Next month",
    },
    "es": {
        "title": "Historial de partidos — {label}", "date": "Fecha", "match": "Partido",
        "duration": "Duración", "open": "Abrir informe",
        "empty": "Aún no hay partidos archivados.", "minutes": "{n} min",
        "prev": "Anterior", "next": "Siguiente", "pageOf": "Página {page} de {pages}",
        "allTypes": "Todas", "indoor": "Pista", "beach": "Playa",
        "table_tennis": "Tenis de mesa",
        "day": "Día", "filter": "Filtrar", "allDays": "Todos los días",
        "prevMonth": "Mes anterior", "nextMonth": "Mes siguiente",
    },
    "pt": {
        "title": "Histórico de jogos — {label}", "date": "Data", "match": "Jogo",
        "duration": "Duração", "open": "Abrir relatório",
        "empty": "Ainda não há jogos arquivados.", "minutes": "{n} min",
        "prev": "Anterior", "next": "Seguinte", "pageOf": "Página {page} de {pages}",
        "allTypes": "Todas", "indoor": "Pista", "beach": "Praia",
        "table_tennis": "Tênis de mesa",
        "day": "Dia", "filter": "Filtrar", "allDays": "Todos os dias",
        "prevMonth": "Mês anterior", "nextMonth": "Mês seguinte",
    },
    "it": {
        "title": "Storico partite — {label}", "date": "Data", "match": "Partita",
        "duration": "Durata", "open": "Apri report",
        "empty": "Nessuna partita archiviata.", "minutes": "{n} min",
        "prev": "Precedente", "next": "Successivo", "pageOf": "Pagina {page} di {pages}",
        "allTypes": "Tutti", "indoor": "Indoor", "beach": "Beach",
        "table_tennis": "Ping pong",
        "day": "Giorno", "filter": "Filtra", "allDays": "Tutti i giorni",
        "prevMonth": "Mese precedente", "nextMonth": "Mese successivo",
    },
    "fr": {
        "title": "Historique des matchs — {label}", "date": "Date", "match": "Match",
        "duration": "Durée", "open": "Ouvrir le rapport",
        "empty": "Aucun match archivé.", "minutes": "{n} min",
        "prev": "Précédent", "next": "Suivant", "pageOf": "Page {page} sur {pages}",
        "allTypes": "Tous", "indoor": "Indoor", "beach": "Beach",
        "table_tennis": "Tennis de table",
        "day": "Jour", "filter": "Filtrer", "allDays": "Tous les jours",
        "prevMonth": "Mois précédent", "nextMonth": "Mois suivant",
    },
    "de": {
        "title": "Spielverlauf — {label}", "date": "Datum", "match": "Spiel",
        "duration": "Dauer", "open": "Bericht öffnen",
        "empty": "Noch keine archivierten Spiele.", "minutes": "{n} Min",
        "prev": "Zurück", "next": "Weiter", "pageOf": "Seite {page} von {pages}",
        "allTypes": "Alle", "indoor": "Halle", "beach": "Beach",
        "table_tennis": "Tischtennis",
        "day": "Tag", "filter": "Filtern", "allDays": "Alle Tage",
        "prevMonth": "Voriger Monat", "nextMonth": "Nächster Monat",
    },
}

_VALID_MODES = ("indoor", "beach", "table_tennis")

# Localized month names and Monday-first short weekday names for the
# server-rendered calendar (no ``babel`` dependency available).
_MONTHS: dict[str, list[str]] = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
}
_WEEKDAYS: dict[str, list[str]] = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
    "pt": ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"],
    "it": ["lun", "mar", "mer", "gio", "ven", "sab", "dom"],
    "fr": ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"],
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
}

_CAL_RE = re.compile(r"^\d{4}-\d{2}$")


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    m = month - 1 + delta
    return year + m // 12, m % 12 + 1


def _view_month(cal: str, selected_day: str, available_days: list[str]) -> tuple[int, int]:
    """Year/month the calendar should display."""
    if cal and _CAL_RE.match(cal):
        y, m = int(cal[:4]), int(cal[5:7])
        if 1 <= m <= 12:
            return y, m
    anchor = selected_day or (available_days[0] if available_days else "")
    if anchor:
        return int(anchor[:4]), int(anchor[5:7])
    now = datetime.now()
    return now.year, now.month


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
        label = ov.description or ov.oid
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


_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fmt_date(ended_at: object) -> str:
    if not isinstance(ended_at, (int, float)):
        return "—"
    # Server-local time, to match the account Reports page (which formats in
    # the viewer's local zone) — a self-hosted league usually runs in the
    # operator's timezone.
    return datetime.fromtimestamp(ended_at).strftime("%Y-%m-%d %H:%M")


def _day_key(ended_at: object) -> str | None:
    """Server-local ``YYYY-MM-DD`` for *ended_at*, or ``None`` — matches the
    date the day-filter input submits."""
    if not isinstance(ended_at, (int, float)):
        return None
    return datetime.fromtimestamp(ended_at).strftime("%Y-%m-%d")


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
               sort: str, direction: str, mode: str, day: str) -> str:
    # Toggle direction when re-clicking the active column; otherwise default
    # to descending. Always jump back to page 1 on a sort change.
    nxt = "asc" if (sort == col and direction != "asc") else "desc"
    arrow = ""
    if sort == col:
        arrow = " ▲" if direction == "asc" else " ▼"
    href = _url(token, sort=col, direction=nxt, mode=mode, day=day, locale=locale)
    return f"<a href='{html.escape(href)}'>{html.escape(label)}{arrow}</a>"


def _url(token: str, *, sort: str, direction: str, mode: str, day: str,
         locale: str, page: int = 1, cal: str = "") -> str:
    """Build a ``/matches/{token}`` URL carrying the active view state."""
    from urllib.parse import urlencode

    params: dict[str, object] = {"sort": sort, "dir": direction}
    if mode:
        params["mode"] = mode
    if day:
        params["day"] = day
    if cal:
        params["cal"] = cal
    if page and page != 1:
        params["page"] = page
    params["lang"] = locale
    return f"/matches/{token}?{urlencode(params)}"


def _filter_links(token: str, locale: str, active_mode: str,
                  sort: str, direction: str, day: str) -> str:
    """Match-type filter row: All types · Indoor · Beach · Table tennis."""
    items = [("", _t(locale, "allTypes"))] + [
        (m, _t(locale, m)) for m in _VALID_MODES
    ]
    out = []
    for value, label in items:
        href = _url(token, sort=sort, direction=direction, mode=value, day=day,
                    locale=locale)
        cls = " class='active'" if value == active_mode else ""
        out.append(f"<a{cls} href='{html.escape(href)}'>{html.escape(label)}</a>")
    return "<div class='filters'>" + "".join(out) + "</div>"


def _calendar(token: str, locale: str, available_days: list[str],
              selected_day: str, cal: str, sort: str, direction: str,
              mode: str) -> str:
    """A month calendar rendered server-side: days with matches are clickable
    links (others are dimmed), month navigation is plain links — the
    no-JS equivalent of the account page's calendar."""
    have = set(available_days)
    year, month = _view_month(cal, selected_day, available_days)
    months = _MONTHS.get(locale, _MONTHS["en"])
    weekdays = _WEEKDAYS.get(locale, _WEEKDAYS["en"])
    this_cal = f"{year:04d}-{month:02d}"

    py, pm = _month_shift(year, month, -1)
    ny, nm = _month_shift(year, month, 1)

    def _nav(y: int, m: int, sym: str, key: str) -> str:
        href = _url(token, sort=sort, direction=direction, mode=mode,
                    day=selected_day, locale=locale, cal=f"{y:04d}-{m:02d}")
        return (f"<a class='cal-nav' href='{html.escape(href)}' "
                f"title='{html.escape(_t(locale, key))}'>{sym}</a>")

    head = (
        "<div class='cal-head'>"
        + _nav(py, pm, "‹", "prevMonth")
        + f"<span class='cal-month'>{html.escape(months[month - 1])} {year}</span>"
        + _nav(ny, nm, "›", "nextMonth")
        + "</div>"
    )
    week = ("<div class='cal-grid cal-week'>"
            + "".join(f"<span>{html.escape(w)}</span>" for w in weekdays)
            + "</div>")

    offset = date(year, month, 1).weekday()  # 0 = Monday
    cells = ["<span class='cal-cell blank'></span>"] * offset
    for d in range(1, _calmod.monthrange(year, month)[1] + 1):
        key = f"{year:04d}-{month:02d}-{d:02d}"
        if key in have:
            sel = key == selected_day
            href = _url(token, sort=sort, direction=direction, mode=mode,
                        day=("" if sel else key), locale=locale, cal=this_cal)
            cls = "cal-cell has" + (" sel" if sel else "")
            cells.append(f"<a class='{cls}' href='{html.escape(href)}'>{d}</a>")
        else:
            cells.append(f"<span class='cal-cell'>{d}</span>")
    grid = "<div class='cal-grid'>" + "".join(cells) + "</div>"

    reset = ""
    if selected_day:
        href = _url(token, sort=sort, direction=direction, mode=mode, day="",
                    locale=locale, cal=this_cal)
        reset = (f"<a class='btn' href='{html.escape(href)}'>"
                 f"{html.escape(_t(locale, 'allDays'))}</a>")

    return "<div class='cal'>" + head + week + grid + reset + "</div>"


def _render(token: str, locale: str, label: str, rows: list[dict],
            sort: str, direction: str, active_mode: str, day: str,
            available_days: list[str], cal: str, page: int, pages: int) -> str:
    title = _t(locale, "title", label=label)
    controls = (
        _filter_links(token, locale, active_mode, sort, direction, day)
        + _calendar(token, locale, available_days, day, cal, sort, direction,
                    active_mode)
    )
    if not rows:
        body = controls + f"<p class='empty'>{html.escape(_t(locale, 'empty'))}</p>"
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
            f"<th>{_sort_link(token, locale, _t(locale, 'date'), 'ended', sort, direction, active_mode, day)}</th>"
            f"<th>{html.escape(_t(locale, 'match'))}</th>"
            f"<th>{_sort_link(token, locale, _t(locale, 'duration'), 'duration', sort, direction, active_mode, day)}</th>"
            "<th></th></tr>"
        )
        pager = ""
        if pages > 1:
            def _page_btn(target: int, key: str, on: bool) -> str:
                if not on:
                    return f"<span class='btn disabled'>{html.escape(_t(locale, key))}</span>"
                href = _url(token, sort=sort, direction=direction, mode=active_mode,
                            day=day, locale=locale, page=target)
                return f"<a class='btn' href='{html.escape(href)}'>{html.escape(_t(locale, key))}</a>"
            pager = (
                "<div class='pager'>"
                + _page_btn(page - 1, "prev", page > 1)
                + f"<span>{html.escape(_t(locale, 'pageOf', page=page, pages=pages))}</span>"
                + _page_btn(page + 1, "next", page < pages) + "</div>"
            )
        body = (
            controls + "<table><thead>" + head + "</thead><tbody>"
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
.cal {{ margin-bottom:18px; max-width:280px; }}
.cal-head {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }}
.cal-month {{ font-weight:600; text-transform:capitalize; }}
.cal-nav {{ color:#cfd4dd; text-decoration:none; border:1px solid #2c333f; border-radius:8px; padding:0 10px; font-size:1.1rem; line-height:1.7; }}
.cal-nav:hover {{ background:#20262f; }}
.cal-grid {{ display:grid; grid-template-columns:repeat(7,1fr); gap:4px; }}
.cal-week span {{ text-align:center; color:#98a2b3; font-size:0.72rem; padding:2px 0; }}
.cal-cell {{ display:flex; align-items:center; justify-content:center; aspect-ratio:1; border-radius:8px; font-size:0.82rem; color:#5b6472; text-decoration:none; }}
.cal-cell.blank {{ visibility:hidden; }}
.cal-cell.has {{ color:#e7e9ee; border:1px solid #2c5a3c; background:#142a1c; }}
.cal-cell.has:hover {{ background:#1c3a28; }}
.cal-cell.sel {{ background:#4f8cff; border-color:#4f8cff; color:#fff; }}
.cal .btn {{ margin-top:10px; }}
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
def match_history(
    public_token: str,
    request: Request,
    sort: str = Query(default="ended"),
    dir: str = Query(default="desc"),
    mode: str = Query(default=""),
    day: str = Query(default=""),
    cal: str = Query(default=""),
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
    active_day = day if _DAY_RE.match(day or "") else ""

    matches = match_archive.list_matches(oid=skey)
    if active_mode:
        matches = [m for m in matches if m.get("mode") == active_mode]
    # Days that actually have matches (for the current type filter) — the
    # day dropdown only offers these, like the account calendar dots them.
    available_days = sorted(
        {d for m in matches if (d := _day_key(m.get("ended_at")))},
        reverse=True,
    )
    if active_day:
        matches = [m for m in matches if _day_key(m.get("ended_at")) == active_day]
    matches = _sorted(matches, sort, direction)
    pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, pages)
    rows = matches[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    active_cal = cal if _CAL_RE.match(cal or "") else ""
    return HTMLResponse(
        _render(public_token, locale, label, rows, sort, direction,
                active_mode, active_day, available_days, active_cal, page, pages)
    )
