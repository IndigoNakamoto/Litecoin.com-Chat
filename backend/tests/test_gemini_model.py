"""Generation model id and the spend-limit price card stay in sync."""

from __future__ import annotations

import pytest

from backend.monitoring.llm_observability import estimate_gemini_cost
from backend.rag_pipeline import LLM_MODEL_NAME
from backend.services.rewriter import GeminiRewriter


def test_generation_model_is_gemini_35_flash_lite():
    assert LLM_MODEL_NAME == "gemini-3.5-flash-lite"


def test_rewriter_defaults_to_the_generation_model():
    assert GeminiRewriter.__init__.__defaults__[-1] == LLM_MODEL_NAME


def test_faq_generator_uses_the_generation_model(monkeypatch):
    captured = {}

    class _FakeLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("langchain_google_genai.ChatGoogleGenerativeAI", _FakeLLM)
    from backend.services.faq_generator import FAQGenerator

    FAQGenerator(backend="gemini")._get_gemini_llm()
    assert captured["model"] == LLM_MODEL_NAME


def test_flash_lite_price_card_and_legacy_preview():
    # $0.30 / 1M input + $2.50 / 1M output.
    assert estimate_gemini_cost(1_000_000, 1_000_000, LLM_MODEL_NAME) == pytest.approx(2.80)
    assert estimate_gemini_cost(1_000_000, 0) == pytest.approx(0.30)
    # Historical log lines keep the old preview card.
    assert estimate_gemini_cost(1_000_000, 0, "gemini-3.1-flash-lite-preview") == pytest.approx(0.10)
    assert estimate_gemini_cost(1_000_000, 1_000_000, "gemini-3.1-flash-lite-preview") == pytest.approx(0.50)
