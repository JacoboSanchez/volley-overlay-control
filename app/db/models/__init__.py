"""ORM models — imported here so ``Base.metadata`` is fully populated.

Alembic's ``env.py`` and the test ``create_all`` both rely on importing
this package to discover every table.
"""

from __future__ import annotations

from app.db.models.overlay import OverlaySessionMeta, UserOverlay
from app.db.models.preset import Preset
from app.db.models.report import MatchReport
from app.db.models.setting import Setting
from app.db.models.team import Team, TeamGroup, TeamGroupMember, UserTeamListItem
from app.db.models.user import AuthSession, User

__all__ = [
    "AuthSession",
    "MatchReport",
    "OverlaySessionMeta",
    "Preset",
    "Setting",
    "Team",
    "TeamGroup",
    "TeamGroupMember",
    "User",
    "UserOverlay",
    "UserTeamListItem",
]
