"""Frozen obvious-dependency lists for history routing.

is_dependent === these tokens/prefixes. Do not reintroduce a Gemini
"just in case" rewrite. Known miss this slice: follow-ups that look
standalone ("the second one", "same for MWEB?") skip rewrite and drop
history from generation.
"""

from __future__ import annotations

import re
from typing import FrozenSet, Tuple

# Pronouns that GUARANTEE history dependency.
# Excludes ambiguous "IT" (Information Technology) as a standalone acronym —
# "it" as a token still matches.
STRONG_AMBIGUOUS_TOKENS: FrozenSet[str] = frozenset(
    {
        "it",
        "this",
        "that",
        "these",
        "those",
        "they",
        "them",
        "their",
        "its",
        "he",
        "she",
        "him",
        "her",
        "former",
        "latter",
        "previous",
        "following",
    }
)

STRONG_PREFIXES: Tuple[str, ...] = (
    "and ",
    "also ",
    "but ",
    "so ",
    "what about",
    "how about",
    "why is that",
    "can you elaborate",
    "continue",
    "go on",
    "explain that",
    "expand on that",
)


def is_obviously_dependent(query_text: str) -> bool:
    """True iff the query has a frozen pronoun token or a frozen prefix."""
    text = (query_text or "").strip().lower()
    if not text:
        return False
    tokens = re.findall(r"[a-z0-9']+", text)
    if any(t in STRONG_AMBIGUOUS_TOKENS for t in tokens):
        return True
    return any(text.startswith(p) for p in STRONG_PREFIXES)
