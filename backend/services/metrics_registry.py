"""
Curated registry of litview.space on-chain metrics.

Loads `backend/data/metrics_registry.yaml` once, validates it, and answers
"which metric is this question asking for?" with longest-phrase-wins matching.

Conceptual phrasing ("what is MVRV?", "how is MVRV calculated?", "explain
SOPR") is *not* a match: those questions belong to the knowledge base, and the
intent classifier applies its own explain-vs-lookup gate on top of this one.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "metrics_registry.yaml"

UNITS = ("usd", "ltc", "percent", "ratio", "count", "raw")
_ID_RE = re.compile(r"^[a-z0-9_]{2,48}$")

# Questions about the *concept* rather than the current value. Checked on the
# lowercased query before phrase matching.
_CONCEPTUAL_RE = re.compile(
    r"""
    ^\s*(what|whats|what's)\s+(is|are|does)\s+(a|an|the)?\s*(litecoin'?s?\s+)?[\w\s'/-]{1,40}\??\s*$   # bare "what is X?"
    | \bwhat\s+does\s+.{0,40}\b(mean|measure|indicate|tell)\b
    | \bhow\s+(is|are|do\s+you|does\s+one|can\s+i)\s+.{0,40}\b(calculated|computed|derived|defined|measured|work)\b
    | \b(explain|define|definition\s+of|meaning\s+of|describe)\b
    | \bwhy\s+(is|are|does|do)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Explicit live-value signals override a definitional-looking sentence
# ("what is litecoin's mvrv right now?").
_LIVE_SIGNAL_RE = re.compile(
    r"\b(current(ly)?|right\s+now|now|today|latest|at\s+the\s+moment|this\s+week|this\s+month|"
    r"trend|history|chart|over\s+the\s+(last|past)|last\s+\d+\s+(days?|weeks?|months?))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MetricSpec:
    id: str
    series: str
    label: str
    unit: str
    description: str
    phrases: Tuple[str, ...]
    index: str = "day1"
    chart_url: Optional[str] = None
    spark_points: int = 30
    change_windows: Tuple[int, ...] = (7, 30)
    verified_live: bool = False
    extra: Dict[str, object] = field(default_factory=dict, compare=False)


class RegistryError(ValueError):
    """Raised when the YAML is malformed; surfaces at import so bad edits fail fast."""


def _parse(raw: object) -> List[MetricSpec]:
    if not isinstance(raw, dict) or not isinstance(raw.get("metrics"), list):
        raise RegistryError("metrics_registry.yaml must have a top-level `metrics:` list")
    specs: List[MetricSpec] = []
    seen_ids: set = set()
    seen_phrases: Dict[str, str] = {}
    for i, item in enumerate(raw["metrics"]):
        if not isinstance(item, dict):
            raise RegistryError(f"metrics[{i}] is not a mapping")
        mid = str(item.get("id") or "").strip()
        if not _ID_RE.match(mid):
            raise RegistryError(f"metrics[{i}].id {mid!r} must match {_ID_RE.pattern}")
        if mid in seen_ids:
            raise RegistryError(f"duplicate metric id {mid!r}")
        seen_ids.add(mid)
        series = str(item.get("series") or "").strip()
        if not series:
            raise RegistryError(f"metric {mid!r} is missing `series`")
        unit = str(item.get("unit") or "raw").strip().lower()
        if unit not in UNITS:
            raise RegistryError(f"metric {mid!r} has unknown unit {unit!r} (allowed: {', '.join(UNITS)})")
        phrases_raw = item.get("phrases") or []
        if not isinstance(phrases_raw, list) or not phrases_raw:
            raise RegistryError(f"metric {mid!r} needs a non-empty `phrases` list")
        phrases: List[str] = []
        for p in phrases_raw:
            p_norm = re.sub(r"\s+", " ", str(p).strip().lower())
            if not p_norm:
                continue
            if p_norm in seen_phrases and seen_phrases[p_norm] != mid:
                raise RegistryError(f"phrase {p_norm!r} is claimed by both {seen_phrases[p_norm]!r} and {mid!r}")
            seen_phrases[p_norm] = mid
            phrases.append(p_norm)
        windows_raw = item.get("change_windows") or [7, 30]
        try:
            windows = tuple(sorted({int(w) for w in windows_raw if int(w) > 0}))
        except (TypeError, ValueError):
            raise RegistryError(f"metric {mid!r} has invalid change_windows {windows_raw!r}")
        specs.append(
            MetricSpec(
                id=mid,
                series=series,
                index=str(item.get("index") or "day1"),
                label=str(item.get("label") or mid.replace("_", " ").title()),
                unit=unit,
                description=str(item.get("description") or "").strip(),
                phrases=tuple(phrases),
                chart_url=(str(item["chart_url"]).strip() or None) if item.get("chart_url") else None,
                spark_points=int(item.get("spark_points") or 30),
                change_windows=windows or (7, 30),
                verified_live=bool(item.get("verified_live", False)),
            )
        )
    return specs


class MetricsRegistry:
    def __init__(self, specs: Sequence[MetricSpec]):
        self._specs: Tuple[MetricSpec, ...] = tuple(specs)
        self._by_id: Dict[str, MetricSpec] = {s.id: s for s in self._specs}
        # Longest phrase first so "market value to realized value" beats "mvrv"-style shorter overlaps.
        self._phrases: List[Tuple[str, MetricSpec]] = sorted(
            ((p, s) for s in self._specs for p in s.phrases), key=lambda ps: -len(ps[0])
        )
        self._phrase_res: List[Tuple[re.Pattern, MetricSpec]] = [
            (re.compile(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])"), s) for p, s in self._phrases
        ]

    @property
    def specs(self) -> Tuple[MetricSpec, ...]:
        return self._specs

    def get(self, metric_id: str) -> Optional[MetricSpec]:
        return self._by_id.get(metric_id)

    @staticmethod
    def is_conceptual(query_lower: str) -> bool:
        """True for definitional / mechanism questions (unless a live-value signal is present)."""
        if _LIVE_SIGNAL_RE.search(query_lower):
            return False
        return bool(_CONCEPTUAL_RE.search(query_lower))

    def find_phrase(self, query_lower: str) -> Optional[MetricSpec]:
        """Phrase match only (no conceptual gate)."""
        q = re.sub(r"\s+", " ", query_lower.strip().lower())
        for rx, spec in self._phrase_res:
            if rx.search(q):
                return spec
        return None

    def matched_phrase(self, query_lower: str, spec: MetricSpec) -> Optional[str]:
        """The (longest) registry phrase of `spec` present in the query, if any."""
        q = re.sub(r"\s+", " ", query_lower.strip().lower())
        for (phrase, s), (rx, _) in zip(self._phrases, self._phrase_res):
            if s.id == spec.id and rx.search(q):
                return phrase
        return None

    def match(self, query_lower: str) -> Optional[MetricSpec]:
        """Metric this question asks the *current value* of, or None."""
        spec = self.find_phrase(query_lower)
        if spec is None:
            return None
        if self.is_conceptual(query_lower):
            return None
        return spec


def load_registry(path: Optional[Path] = None) -> MetricsRegistry:
    p = Path(path) if path else REGISTRY_PATH
    raw = yaml.safe_load(p.read_text()) or {}
    specs = _parse(raw)
    logger.info("metrics registry loaded: %d metrics from %s", len(specs), p)
    return MetricsRegistry(specs)


@lru_cache(maxsize=1)
def get_registry() -> MetricsRegistry:
    """Process-wide registry (loaded lazily, once). Raises RegistryError on a bad YAML."""
    return load_registry()
