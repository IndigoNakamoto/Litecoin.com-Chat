"""LRK metric intent vs blockchain / search."""

from backend.rag_graph.graph import after_prechecks
from backend.services.intent_classifier import Intent, IntentClassifier


class TestLrkMetricIntent:
    def setup_method(self):
        self.classifier = IntentClassifier(faq_questions=[])

    def test_chart_realized_price(self):
        intent, entity, _ = self.classifier.classify("chart realized price")
        assert intent == Intent.LRK_METRIC
        assert entity == "lrk_metric"

    def test_plot_over_time(self):
        intent, _, _ = self.classifier.classify("plot market cap over time")
        assert intent == Intent.LRK_METRIC

    def test_mixed_stays_search(self):
        intent, _, _ = self.classifier.classify("what is realized price and chart it")
        assert intent == Intent.SEARCH

    def test_price_spot_still_blockchain(self):
        intent, entity, _ = self.classifier.classify("What is the current price of Litecoin?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "price"

    def test_txid_still_blockchain(self):
        txid = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        intent, entity, _ = self.classifier.classify(txid)
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity.startswith("tx:")

    def test_conceptual_stays_search(self):
        intent, _, _ = self.classifier.classify("What is Litecoin?")
        assert intent == Intent.SEARCH


def test_after_prechecks_routes_lrk_metric():
    assert after_prechecks({"intent": "lrk_metric"}) == "lrk_lookup"
    assert after_prechecks({"intent": "blockchain_lookup"}) == "blockchain_lookup"
    assert after_prechecks({"intent": "search"}) == "semantic_cache"
    assert after_prechecks({"early_answer": "hi"}) != "lrk_lookup"
