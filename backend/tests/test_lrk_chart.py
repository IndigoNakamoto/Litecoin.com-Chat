"""Tests for LRK chart-spec validation and intent helpers."""

from backend.services.lrk_chart import (
    ChartSpecDraft,
    ChartSeriesDraft,
    is_mixed_lrk_question,
    metric_search_query,
    validate_chart_spec,
    wants_lrk_chart,
)


def test_wants_chart_verbs():
    assert wants_lrk_chart("chart realized price")
    assert wants_lrk_chart("plot market cap over time")
    assert not wants_lrk_chart("What is Litecoin?")


def test_mixed_question_needs_rag():
    assert is_mixed_lrk_question("what is realized price and chart it")
    assert is_mixed_lrk_question("explain MVRV and plot it")
    assert not is_mixed_lrk_question("chart realized price")


def test_validate_rejects_unknown_series():
    draft = ChartSpecDraft(
        title="Nope",
        unit="usd",
        view="line",
        scale="linear",
        series=[ChartSeriesDraft(path="made-up-metric", label="Nope")],
    )
    assert validate_chart_spec(draft, ["realized-price"]) is None


def test_validate_accepts_search_hit():
    draft = {
        "title": "Realized Price",
        "unit": "usd",
        "view": "line",
        "scale": "linear",
        "series": [{"path": "brk.series.realized-price", "label": "Realized Price"}],
    }
    artifact = validate_chart_spec(draft, ["realized-price", "market-cap"])
    assert artifact is not None
    assert artifact["type"] == "chart"
    assert artifact["chart"]["series"][0]["path"] == "realized-price"


def test_validate_rejects_bad_unit():
    draft = ChartSpecDraft(
        title="X",
        unit="widgets",
        view="line",
        scale="linear",
        series=[ChartSeriesDraft(path="realized-price", label="RP")],
    )
    assert validate_chart_spec(draft, ["realized-price"]) is None


def test_metric_search_query_strips_verbs():
    assert "chart" not in metric_search_query("chart realized price").lower()
    assert "realized price" in metric_search_query("chart realized price")
