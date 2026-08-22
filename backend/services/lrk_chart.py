"""
Validated LRK chart-spec planning.

Gemini only proposes a spec; every series path must appear in LRK search hits.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field, field_validator

from backend.services.lrk_client import LrkClient, normalize_series_path

logger = logging.getLogger(__name__)

CHART_UNITS = frozenset(
    {"addresses", "blocks", "btc", "number", "percent", "utxos", "usd"}
)
CHART_VIEWS = frozenset({"line", "area", "stacked", "bar", "dots"})
CHART_SCALES = frozenset({"linear", "log"})
CHART_COLORS = (
    "orange",
    "blue",
    "green",
    "violet",
    "yellow",
    "red",
)

_CHART_VERBS = (
    "chart",
    "plot",
    "graph",
    "visualize",
    "visualise",
    "draw",
)
_TIMESERIES_HINTS = (
    "over time",
    "historical",
    "time series",
    "timeseries",
    "history of",
)
_EXPLAIN_HINTS = (
    "what is",
    "what's",
    "whats",
    "explain",
    "why ",
    "how does",
    "how do ",
    "tell me about",
    "define ",
    "meaning of",
)


class ChartSeriesDraft(BaseModel):
    path: str
    label: str
    color: Optional[str] = None

    @field_validator("path", "label")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("required")
        return text


class ChartSpecDraft(BaseModel):
    title: str
    unit: str = "number"
    view: str = "line"
    scale: str = "linear"
    series: List[ChartSeriesDraft] = Field(min_length=1, max_length=6)
    narration: str = ""

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("title required")
        return text


def wants_lrk_chart(query: str) -> bool:
    """True when the user asked for a chart or historical series view."""
    q = (query or "").lower()
    if any(verb in q for verb in _CHART_VERBS):
        return True
    return any(hint in q for hint in _TIMESERIES_HINTS)


def is_mixed_lrk_question(query: str) -> bool:
    """Chart request that also wants an explanation — stay on the RAG path."""
    q = (query or "").lower()
    if not wants_lrk_chart(query):
        return False
    return any(hint in q for hint in _EXPLAIN_HINTS)


def metric_search_query(query: str) -> str:
    """Strip chart verbs so LRK search sees the metric name."""
    text = query or ""
    for verb in _CHART_VERBS:
        text = re.sub(rf"\b{re.escape(verb)}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(show me|show|please|a graph of|graph of|over time|historical|time series)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", text).strip() or (query or "").strip()


def validate_chart_spec(
    draft: ChartSpecDraft | Dict[str, Any],
    candidates: Sequence[str],
) -> Optional[Dict[str, Any]]:
    """Return a /ask-compatible chart artifact payload, or None if invalid."""
    spec = draft if isinstance(draft, ChartSpecDraft) else ChartSpecDraft.model_validate(draft)
    unit = spec.unit.strip().lower()
    view = spec.view.strip().lower()
    scale = spec.scale.strip().lower()
    if unit not in CHART_UNITS or view not in CHART_VIEWS or scale not in CHART_SCALES:
        return None

    allowed = [normalize_series_path(name) for name in candidates]
    allowed_set = set(allowed)
    series: List[Dict[str, str]] = []
    used_colors: List[str] = []
    for item in spec.series:
        normalized = normalize_series_path(item.path)
        if normalized not in allowed_set:
            logger.info("Rejecting unvalidated series path: %s", item.path)
            continue
        path = normalized
        color = (item.color or "").strip().lower()
        if color not in CHART_COLORS or color in used_colors:
            color = next((c for c in CHART_COLORS if c not in used_colors), CHART_COLORS[0])
        used_colors.append(color)
        series.append({"path": path, "label": item.label.strip(), "color": color})

    if not series or len(series) > 6:
        return None

    return {
        "type": "chart",
        "chart": {
            "title": spec.title,
            "unit": unit,
            "view": view,
            "scale": scale,
            "series": series,
        },
    }


async def search_lrk_series(client: LrkClient, query: str, limit: int = 20) -> List[str]:
    return await client.search_series(metric_search_query(query), limit=limit)


async def read_lrk_series(
    client: LrkClient,
    name: str,
    candidates: Sequence[str],
    index: str = "date",
) -> Any:
    resolved = client.validate_series(name, list(candidates))
    if resolved is None:
        raise ValueError(f"Unknown series: {name}")
    return await client.get_series_latest(resolved, index=index)


async def emit_chart(
    draft: ChartSpecDraft | Dict[str, Any],
    candidates: Sequence[str],
) -> Optional[Dict[str, Any]]:
    return validate_chart_spec(draft, candidates)


async def plan_chart_spec(
    llm: Any,
    query: str,
    candidates: Sequence[str],
) -> Optional[Dict[str, Any]]:
    """Ask Gemini for a chart-spec constrained to `candidates`."""
    if not candidates or llm is None:
        return None
    listed = "\n".join(f"- {name}" for name in candidates[:24])
    prompt = (
        "Pick 1-6 series from this exact allow-list and describe a chart. "
        "Use only those paths. Prefer line + linear unless the unit is percent.\n\n"
        f"User question:\n{query}\n\n"
        f"Allowed series paths:\n{listed}"
    )
    try:
        structured = llm.with_structured_output(ChartSpecDraft)
        draft = await structured.ainvoke(prompt)
    except Exception as exc:
        logger.warning("LRK chart planning failed: %s", exc, exc_info=True)
        return None
    return validate_chart_spec(draft, candidates)


async def plan_lrk_chart(
    pipeline: Any,
    query: str,
    client: Optional[LrkClient] = None,
) -> Optional[Dict[str, Any]]:
    """search_lrk_series → Gemini emit_chart, with validated paths only."""
    owns_client = client is None
    lrk = client or LrkClient()
    try:
        hits = await search_lrk_series(lrk, query)
        if not hits:
            return None
        llm = getattr(pipeline, "llm", None) if pipeline is not None else None
        artifact = await plan_chart_spec(llm, query, hits)
        if artifact is not None:
            return artifact
        return _fallback_chart(query, hits)
    finally:
        if owns_client:
            await lrk.close()


async def maybe_attach_lrk_chart(pipeline: Any, query: str) -> Optional[Dict[str, Any]]:
    """For mixed RAG turns: search + emit_chart when the user also asked for a chart."""
    if not wants_lrk_chart(query):
        return None
    return await plan_lrk_chart(pipeline, query)


def _fallback_chart(query: str, hits: Sequence[str]) -> Optional[Dict[str, Any]]:
    """If Gemini is unavailable, chart the top search hit."""
    if not hits:
        return None
    title = metric_search_query(query) or hits[0]
    return validate_chart_spec(
        ChartSpecDraft(
            title=title[:80],
            unit="number",
            view="line",
            scale="linear",
            series=[ChartSeriesDraft(path=hits[0], label=hits[0])],
            narration="",
        ),
        hits,
    )
