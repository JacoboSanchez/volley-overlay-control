"""Machine-readable exports of an archived match's point log.

Split out of :mod:`app.match_report` like the other ``match_report_*``
siblings. The CSV renderer consumes the same collapsed + trimmed audit
slice the HTML report's timeline renders, so both surfaces always tell
the same story. Column headers are stable machine identifiers and are
deliberately not localized.
"""

from __future__ import annotations

import csv
import datetime
import io
import re

from app.match_report_stats import (
    _coerce_int,
    _result_score,
    _result_set,
)

CSV_COLUMNS = (
    "ts_utc",
    "rel_time_s",
    "set",
    "action",
    "team",
    "point_type",
    "error_type",
    "score_t1",
    "score_t2",
    "sets_t1",
    "sets_t2",
    "serve_after",
)

# ``serve_after`` maps the audit's "A"/"B" onto the same numeric team
# ids the ``team`` column uses, so a spreadsheet can join the two
# without a legend.
_SERVE_LABELS = {"A": "1", "B": "2"}

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")
_SLUG_MAX_LEN = 60


def _fmt_iso_utc(ts: object) -> str:
    if not isinstance(ts, (int, float)):
        return ""
    try:
        dt = datetime.datetime.fromtimestamp(float(ts), datetime.UTC)
    except (ValueError, OverflowError, OSError):
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cell(value: object) -> str:
    return "" if value is None else str(value)


def render_point_log_csv(audit: list[dict], *, base_ts: float | None) -> str:
    """Render the audit slice as CSV text (header always present).

    *base_ts* is the match anchor the report uses (Start-match button
    or first scored point); ``rel_time_s`` clamps negatives to zero the
    same way the timeline's relative stamps do. Missing fields render
    as empty cells — never guessed. The leading BOM keeps Excel from
    misreading UTF-8 team-name-adjacent exports.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for record in audit:
        params = record.get("params") or {}
        result = record.get("result") or {}
        serve = result.get("serve")
        ts = record.get("ts")
        rel: object = None
        if isinstance(ts, (int, float)) and base_ts is not None:
            rel = max(0, int(float(ts) - float(base_ts)))
        team = params.get("team")
        writer.writerow([
            _fmt_iso_utc(ts),
            _cell(rel),
            _cell(_result_set(record)),
            _cell(record.get("action")),
            _cell(team if team in (1, 2) else None),
            _cell(params.get("point_type")),
            _cell(params.get("error_type")),
            _cell(_result_score(record, 1)),
            _cell(_result_score(record, 2)),
            _cell(_coerce_int((result.get("team_1") or {}).get("sets"))),
            _cell(_coerce_int((result.get("team_2") or {}).get("sets"))),
            _SERVE_LABELS.get(serve, "") if isinstance(serve, str) else "",
        ])
    return "\ufeff" + buffer.getvalue()


def csv_filename(match_label: str, match_id: str) -> str:
    """Attachment filename from the match label (ASCII slug).

    The slug restricts to ``[a-z0-9-]`` — that both reads well and
    keeps header-unsafe bytes (quotes, newlines, non-ASCII) out of the
    ``Content-Disposition`` line. Falls back to the (already strictly
    validated) match id when the label slugs away to nothing.
    """
    slug = _SLUG_RE.sub("-", match_label).strip("-").lower()[:_SLUG_MAX_LEN]
    slug = slug.strip("-") or match_id
    return f"match-report-{slug}.csv"
