"""User accounts, cookie sessions, and first-admin bootstrap.

This package replaces the env-var Bearer auth ladder with a real account
model backed by the database:

* ``passwords``     — scrypt hashing (re-exported from ``app.password_hash``)
                      plus temporary-password generation.
* ``sessions``      — opaque-token cookie sessions (stored hashed in the DB).
* ``service``       — user CRUD + authentication operations.
* ``dependencies``  — FastAPI deps: current user / require_user / require_admin.
* ``routes``        — the ``/api/v1/auth`` router.
* ``bootstrap``     — first-admin claim flow (startup-log token).
"""

from __future__ import annotations
