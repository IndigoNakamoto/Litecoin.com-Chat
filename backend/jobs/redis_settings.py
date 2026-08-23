"""ARQ Redis settings from env.

``RedisSettings.from_dsn('redis://:password@host')`` keeps username as '' and
Redis ACL then rejects AUTH as an invalid username-password pair. Prefer the
raw ``REDIS_PASSWORD`` and omit an empty username.
"""

from __future__ import annotations

import os
from urllib.parse import unquote, urlparse


def redis_settings_from_env(default_url: str = "redis://redis:6379/0"):
    from arq.connections import RedisSettings

    url = os.getenv("REDIS_URL", default_url)
    parsed = urlparse(url)
    password = os.getenv("REDIS_PASSWORD") or (
        unquote(parsed.password) if parsed.password else None
    )
    username = parsed.username or None
    database = 0
    if parsed.path and parsed.path not in ("/", ""):
        try:
            database = int(parsed.path.lstrip("/").split("/", 1)[0] or 0)
        except ValueError:
            database = 0
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=database,
        password=password,
        username=username,
    )
