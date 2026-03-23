"""Tests for blockchain lookup intent detection in IntentClassifier."""

import pytest
from backend.services.intent_classifier import IntentClassifier, Intent


class TestBlockchainIntentDetection:
    """Verify the classifier correctly identifies blockchain data queries."""

    @pytest.fixture
    def classifier(self):
        return IntentClassifier(faq_questions=[])

    # -- Transaction ID detection ------------------------------------------

    def test_detects_transaction_id(self, classifier):
        query = "What is the status of f4184fc596403b9d638783cf57adfe4c75c605f6356fbc91338530e9831e9e16"
        intent, entity, _ = classifier.classify(query)
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity.startswith("tx:")
        assert "f4184fc596403b9d" in entity

    def test_detects_bare_txid(self, classifier):
        txid = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        intent, entity, _ = classifier.classify(txid)
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == f"tx:{txid}"

    def test_no_false_positive_short_hex(self, classifier):
        """A short hex string should NOT trigger blockchain lookup."""
        intent, _, _ = classifier.classify("What is abc123?")
        assert intent != Intent.BLOCKCHAIN_LOOKUP

    # -- Address detection -------------------------------------------------

    def test_detects_legacy_L_address(self, classifier):
        intent, entity, _ = classifier.classify(
            "Show balance for LXtkKuszAQno6mTHSWEeE74Fc8EiEUiWaQ"
        )
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity.startswith("address:")

    def test_detects_legacy_M_address(self, classifier):
        intent, entity, _ = classifier.classify(
            "Check M8T1B2Z97gVdvmfkQcAtYbEepune1tzGua"
        )
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity.startswith("address:")

    def test_detects_bech32_address(self, classifier):
        intent, entity, _ = classifier.classify(
            "What's the balance of ltc1qw508d6qejxtdg4y5r3zarvary0c5xw7kgmn4n9"
        )
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity.startswith("address:ltc1")

    # -- Block height detection --------------------------------------------

    def test_detects_block_height(self, classifier):
        intent, entity, _ = classifier.classify("Show me block 2800000")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "block_height:2800000"

    def test_detects_block_height_with_hash(self, classifier):
        intent, entity, _ = classifier.classify("What's in block height 100")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "block_height:100"

    def test_detects_block_number(self, classifier):
        intent, entity, _ = classifier.classify("block #500000")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "block_height:500000"

    # -- Fee queries -------------------------------------------------------

    def test_detects_fee_query(self, classifier):
        intent, entity, _ = classifier.classify("What are the current fees?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "fees"

    def test_detects_recommended_fee(self, classifier):
        intent, entity, _ = classifier.classify("recommended fee for litecoin")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "fees"

    # -- Mempool queries ---------------------------------------------------

    def test_detects_mempool_query(self, classifier):
        intent, entity, _ = classifier.classify("How congested is the mempool?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "mempool"

    def test_detects_pending_transactions(self, classifier):
        intent, entity, _ = classifier.classify("How many pending transactions are there?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "mempool"

    # -- Hashrate / difficulty queries -------------------------------------

    def test_detects_hashrate_query(self, classifier):
        intent, entity, _ = classifier.classify("What is the current hashrate?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "hashrate"

    def test_detects_difficulty_query(self, classifier):
        intent, entity, _ = classifier.classify("When is the next difficulty adjustment?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "hashrate"

    def test_detects_current_difficulty_query(self, classifier):
        intent, entity, _ = classifier.classify("What is the current network difficulty?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "hashrate"

    def test_mechanism_difficulty_adjustment_not_blockchain_lookup(self, classifier):
        """Conceptual questions must route to RAG, not live hashrate/difficulty API."""
        intent, entity, _ = classifier.classify(
            "How does the difficulty adjustment mechanism ensure consistent block times?"
        )
        assert intent != Intent.BLOCKCHAIN_LOOKUP
        assert entity is None

    def test_explain_difficulty_adjustment_not_blockchain_lookup(self, classifier):
        intent, _, _ = classifier.classify("Explain how difficulty adjustment works on Litecoin")
        assert intent != Intent.BLOCKCHAIN_LOOKUP

    def test_how_does_hashrate_relate_not_live_stats(self, classifier):
        intent, _, _ = classifier.classify("How does hashrate relate to mining rewards?")
        assert intent != Intent.BLOCKCHAIN_LOOKUP

    # -- Mining pools (Litecoin Space) ------------------------------------

    def test_detects_mining_pools_list(self, classifier):
        intent, entity, _ = classifier.classify("List the Litecoin mining pools")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "mining_pools"

    def test_detects_mining_pools_with_period(self, classifier):
        intent, entity, _ = classifier.classify("Top mining pools in the last 24h for LTC")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "mining_pools:24h"

    def test_detects_named_pool_hashrate(self, classifier):
        intent, entity, _ = classifier.classify(
            "How much of the network hash rate does f2pool have?"
        )
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "mining_pool:f2pool"

    def test_pool_beats_generic_hashrate(self, classifier):
        intent, entity, _ = classifier.classify("What is ViaBTC's hashrate?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "mining_pool:viabtc"

    def test_no_pool_list_on_singular_pool_advice(self, classifier):
        intent, _, _ = classifier.classify("How do I join a mining pool?")
        assert intent != Intent.BLOCKCHAIN_LOOKUP

    # -- Price queries -----------------------------------------------------

    def test_detects_price_query(self, classifier):
        intent, entity, _ = classifier.classify("What is the current Litecoin price?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "price"

    def test_detects_ltc_price(self, classifier):
        intent, entity, _ = classifier.classify("How much is LTC?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert entity == "price"

    # -- Non-blockchain queries should NOT match ---------------------------

    def test_no_match_on_kb_query(self, classifier):
        intent, _, _ = classifier.classify("What is Litecoin's block time?")
        assert intent != Intent.BLOCKCHAIN_LOOKUP

    def test_no_match_on_greeting(self, classifier):
        intent, _, _ = classifier.classify("hello")
        assert intent == Intent.GREETING

    def test_no_match_on_general_question(self, classifier):
        intent, _, _ = classifier.classify("How does Litecoin mining work?")
        assert intent != Intent.BLOCKCHAIN_LOOKUP

    def test_no_match_on_history_question(self, classifier):
        intent, _, _ = classifier.classify("What is the history of Litecoin blocks?")
        assert intent != Intent.BLOCKCHAIN_LOOKUP
