"""Curated litview metrics registry: YAML validity, phrase matching, conceptual gate."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backend.services.metrics_registry import (
    MetricsRegistry,
    RegistryError,
    get_registry,
    load_registry,
)


def test_shipped_registry_loads_and_is_well_formed():
    reg = get_registry()
    ids = {s.id for s in reg.specs}
    # The two series verified live on litview in Oct 2026 plus the computed set.
    assert {"price_close", "mvrv", "realized_price", "circulating_supply", "market_cap"} <= ids
    for s in reg.specs:
        assert s.series and s.phrases and s.unit in ("usd", "ltc", "percent", "ratio", "count", "raw")
        assert s.index == "day1"
        assert all(w > 0 for w in s.change_windows)
    assert reg.get("mvrv").series == "mvrv"
    assert reg.get("sopr").series == "sopr_1w"
    assert reg.get("nope") is None


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Litecoin MVRV right now", "mvrv"),
        ("what is litecoin's mvrv right now?", "mvrv"),          # live signal beats "what is"
        ("current realized price", "realized_price"),
        ("What's the realised price of LTC today?", "realized_price"),
        ("litecoin market cap", "market_cap"),
        ("How many LTC are in circulation?", None),              # not a registry phrase: FAQ/KB territory
        ("circulating supply of litecoin", "circulating_supply"),
        ("show me the puell multiple", "puell_multiple"),
        ("ltc sopr", "sopr"),
        ("daily close price", "price_close"),
        ("difficulty trend over the last month", "difficulty_trend"),
        ("hashrate history", "hashrate_trend"),
        ("How many addresses hold litecoin?", "address_count"),
        ("stock-to-flow", "stock_to_flow"),
        ("nvt ratio", "nvt"),
        ("what is the network value to transactions ratio now", "nvt"),  # longest phrase + live signal
        ("Tell me about Litecoin", None),
        ("mvrvs", None),                                           # token boundary: no partial-word hits
    ],
)
def test_match_live_value_questions(query, expected):
    reg = get_registry()
    got = reg.match(query.lower())
    assert (got.id if got else None) == expected


@pytest.mark.parametrize(
    "query",
    [
        "What is MVRV?",
        "what is the mvrv ratio",
        "What is Litecoin's realized price?",      # bare definitional, no live signal
        "How is MVRV calculated?",
        "how is the puell multiple computed",
        "Explain SOPR",
        "What does NVT mean?",
        "Why is the inflation rate falling?",
        "definition of stock to flow",
    ],
)
def test_conceptual_questions_do_not_match(query):
    reg = get_registry()
    assert reg.find_phrase(query.lower()) is not None  # the phrase is there...
    assert reg.match(query.lower()) is None              # ...but it is a KB question


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "reg.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_registry_rejects_bad_unit_duplicate_id_and_shared_phrase(tmp_path):
    with pytest.raises(RegistryError, match="unknown unit"):
        load_registry(_write(tmp_path, """
            metrics:
              - {id: aa, series: a, unit: dollars, phrases: [a]}
        """))
    with pytest.raises(RegistryError, match="duplicate metric id"):
        load_registry(_write(tmp_path, """
            metrics:
              - {id: aa, series: a, unit: usd, phrases: [a]}
              - {id: aa, series: b, unit: usd, phrases: [b]}
        """))
    with pytest.raises(RegistryError, match="claimed by both"):
        load_registry(_write(tmp_path, """
            metrics:
              - {id: aa, series: a, unit: usd, phrases: [same]}
              - {id: bb, series: b, unit: usd, phrases: [same]}
        """))
    with pytest.raises(RegistryError, match="phrases"):
        load_registry(_write(tmp_path, """
            metrics:
              - {id: aa, series: a, unit: usd}
        """))
    with pytest.raises(RegistryError, match="must match"):
        load_registry(_write(tmp_path, """
            metrics:
              - {id: "Bad-Id", series: a, unit: usd, phrases: [a]}
        """))


def test_registry_defaults_and_longest_phrase_wins(tmp_path):
    reg = load_registry(_write(tmp_path, """
        metrics:
          - id: short
            series: s
            unit: ratio
            phrases: ["cap"]
          - id: long
            series: l
            unit: usd
            phrases: ["market cap"]
            change_windows: [30, 7, 7]
            chart_url: "https://litview.space/charts/x"
    """))
    assert isinstance(reg, MetricsRegistry)
    assert reg.match("litecoin market cap now").id == "long"
    assert reg.match("cap now").id == "short"
    long = reg.get("long")
    assert long.index == "day1" and long.spark_points == 30
    assert long.change_windows == (7, 30)
    assert long.chart_url == "https://litview.space/charts/x"
    assert reg.get("short").label == "Short"
