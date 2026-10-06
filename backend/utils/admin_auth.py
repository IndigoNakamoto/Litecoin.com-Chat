"""
Admin bearer-token verification shared by every admin router.

Tokens come from two environment variables:

    ADMIN_TOKENS="alice:tok1,bob:tok2"   named per-operator tokens (preferred)
    ADMIN_TOKEN="tok"                    legacy single shared token (operator name "admin")

Both may be set at once; revoking one operator is removing their entry from
ADMIN_TOKENS and recreating the backend. `admin_operator()` returns the name
behind a valid token so admin log lines can carry `operator=<name>`;
`verify_admin_token()` keeps the boolean shape every existing call site uses.

Comparison is constant-time per token. Names and tokens are stripped; empty
entries are ignored; a token may not contain ':' or ','.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

LEGACY_OPERATOR = "admin"


def parse_admin_tokens(
    named: Optional[str] = None,
    legacy: Optional[str] = None,
) -> Dict[str, str]:
    """Return {token: operator_name} from ADMIN_TOKENS plus the legacy ADMIN_TOKEN."""
    named = os.getenv("ADMIN_TOKENS", "") if named is None else named
    legacy = os.getenv("ADMIN_TOKEN", "") if legacy is None else legacy

    tokens: Dict[str, str] = {}
    for entry in (named or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            logger.warning("ADMIN_TOKENS entry without 'name:token' shape ignored")
            continue
        name, token = entry.split(":", 1)
        name, token = name.strip(), token.strip()
        if not name or not token:
            logger.warning("ADMIN_TOKENS entry with empty name or token ignored")
            continue
        if token in tokens and tokens[token] != name:
            logger.warning("ADMIN_TOKENS: the same token is listed for %r and %r; keeping %r", tokens[token], name, tokens[token])
            continue
        tokens[token] = name
    legacy = (legacy or "").strip()
    if legacy:
        tokens.setdefault(legacy, LEGACY_OPERATOR)
    return tokens


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError:
        return None
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def admin_operator(authorization: Optional[str]) -> Optional[str]:
    """Operator name for a valid `Authorization: Bearer <token>` header, else None."""
    presented = _bearer_token(authorization)
    if presented is None:
        return None
    tokens = parse_admin_tokens()
    if not tokens:
        logger.warning("Neither ADMIN_TOKENS nor ADMIN_TOKEN is set, admin endpoint authentication disabled")
        return None
    # Compare against every token so timing does not reveal which (if any) matched.
    matched: Optional[str] = None
    for token, name in tokens.items():
        if hmac.compare_digest(presented, token):
            matched = name
    return matched


def verify_admin_token(authorization: Optional[str] = None) -> bool:
    """
    Verify admin token from Authorization header.

    Args:
        authorization: Authorization header value (e.g., "Bearer <token>")

    Returns:
        True if token is valid, False otherwise
    """
    return admin_operator(authorization) is not None


def operator_from_request(request) -> str:  # type: ignore[no-untyped-def]
    """Operator name for an already-authenticated request (for log lines); 'unknown' if absent."""
    try:
        return admin_operator(request.headers.get("Authorization")) or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"
