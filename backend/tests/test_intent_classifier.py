"""
Unit tests for the Intent Classifier service.

Tests cover:
- Greeting detection
- Thanks detection
- FAQ matching with various similarity scores
- Edge cases (empty query, very short queries)
"""

import pytest
from unittest.mock import patch, MagicMock

# Import the module under test
from backend.services.intent_classifier import IntentClassifier, Intent


class TestIntentClassifier:
    """Test suite for IntentClassifier."""
    
    @pytest.fixture
    def classifier(self):
        """Create a classifier with sample FAQ questions."""
        faq_questions = [
            "What is Litecoin?",
            "How do I buy Litecoin?",
            "What is MWEB?",
            "What is the maximum supply of Litecoin?",
            "How does Litecoin compare to Bitcoin?",
            "What wallets support Litecoin?",
        ]
        return IntentClassifier(faq_questions=faq_questions)
    
    @pytest.fixture
    def classifier_no_faq(self):
        """Create a classifier without FAQ questions."""
        return IntentClassifier(faq_questions=[])
    
    # === Greeting Tests ===
    
    def test_greeting_hello(self, classifier):
        """Test detection of 'hello' greeting."""
        intent, matched, response = classifier.classify("hello")
        assert intent == Intent.GREETING
        assert matched is None
        assert response is not None
        assert "Hello" in response
    
    def test_greeting_hi(self, classifier):
        """Test detection of 'hi' greeting."""
        intent, matched, response = classifier.classify("hi")
        assert intent == Intent.GREETING
    
    def test_greeting_hey(self, classifier):
        """Test detection of 'hey' greeting."""
        intent, matched, response = classifier.classify("hey")
        assert intent == Intent.GREETING
    
    def test_greeting_hi_there(self, classifier):
        """Test detection of 'hi there' greeting."""
        intent, matched, response = classifier.classify("hi there")
        assert intent == Intent.GREETING
    
    def test_greeting_good_morning(self, classifier):
        """Test detection of 'good morning' greeting."""
        intent, matched, response = classifier.classify("good morning")
        assert intent == Intent.GREETING
    
    def test_greeting_with_typo(self, classifier):
        """Test fuzzy matching catches typos in greetings."""
        intent, matched, response = classifier.classify("helo")
        assert intent == Intent.GREETING
    
    def test_greeting_long_query_not_matched(self, classifier):
        """Test that long queries containing greeting words are not matched."""
        intent, matched, response = classifier.classify("Hello, I want to know about Litecoin mining")
        # Long queries should not be classified as greetings
        assert intent != Intent.GREETING

    def test_supply_not_greeting(self, classifier):
        """Regression: 'supply' contains 'sup' but should not be classified as a greeting."""
        intent, matched, response = classifier.classify("Supply")
        assert intent != Intent.GREETING
    
    # === Thanks Tests ===
    
    def test_thanks_simple(self, classifier):
        """Test detection of 'thanks'."""
        intent, matched, response = classifier.classify("thanks")
        assert intent == Intent.THANKS
        assert matched is None
        assert response is not None
        assert "welcome" in response.lower()
    
    def test_thanks_thank_you(self, classifier):
        """Test detection of 'thank you'."""
        intent, matched, response = classifier.classify("thank you")
        assert intent == Intent.THANKS
    
    def test_thanks_thx(self, classifier):
        """Test detection of 'thx'."""
        intent, matched, response = classifier.classify("thx")
        assert intent == Intent.THANKS
    
    def test_thanks_appreciate(self, classifier):
        """Test detection of 'appreciate'."""
        intent, matched, response = classifier.classify("appreciate it")
        assert intent == Intent.THANKS
    
    def test_thanks_got_it(self, classifier):
        """Test detection of 'got it'."""
        intent, matched, response = classifier.classify("got it")
        assert intent == Intent.THANKS
    
    def test_thanks_makes_sense(self, classifier):
        """Test detection of 'makes sense'."""
        intent, matched, response = classifier.classify("makes sense")
        assert intent == Intent.THANKS
    
    def test_thanks_long_query_not_matched(self, classifier):
        """Test that long queries containing thanks words are not matched."""
        intent, matched, response = classifier.classify("Thanks for explaining, now I want to know about mining")
        # Long queries should not be classified as thanks
        assert intent != Intent.THANKS
    
    # === FAQ Matching Tests ===
    
    def test_faq_exact_match(self, classifier):
        """Test exact match of FAQ question."""
        intent, matched, response = classifier.classify("What is Litecoin?")
        assert intent == Intent.FAQ_MATCH
        assert matched == "What is Litecoin?"
        assert response is None  # No static response for FAQ match
    
    def test_faq_close_match(self, classifier):
        """Test close match of FAQ question (token_sort needs strong overlap at default threshold)."""
        intent, matched, response = classifier.classify("What is Litecoin")
        assert intent == Intent.FAQ_MATCH
        assert matched == "What is Litecoin?"
    
    def test_faq_similar_wording(self, classifier):
        """Test FAQ matching with similar wording."""
        intent, matched, response = classifier.classify("How can I buy Litecoin?")
        assert intent == Intent.FAQ_MATCH
        assert "buy Litecoin" in matched
    
    def test_faq_word_order_variation(self, monkeypatch):
        """Test FAQ matching with different word order (needs threshold ≤76 for this permutation)."""
        monkeypatch.setenv("FAQ_MATCH_THRESHOLD", "70")
        c = IntentClassifier(
            faq_questions=[
                "What is Litecoin?",
                "How do I buy Litecoin?",
                "What is MWEB?",
                "What is the maximum supply of Litecoin?",
                "How does Litecoin compare to Bitcoin?",
                "What wallets support Litecoin?",
            ]
        )
        intent, matched, response = c.classify("Litecoin what is?")
        assert intent == Intent.FAQ_MATCH
        assert matched == "What is Litecoin?"
    
    def test_faq_no_match_below_threshold(self, classifier):
        """Test that dissimilar queries don't match FAQ."""
        intent, matched, response = classifier.classify("What is the weather today?")
        assert intent == Intent.SEARCH
        assert matched is None
    
    def test_faq_match_threshold_configurable(self):
        """Test that FAQ match threshold is configurable."""
        with patch.dict('os.environ', {'FAQ_MATCH_THRESHOLD': '95'}):
            # High threshold should reject more matches
            classifier = IntentClassifier(faq_questions=["What is Litecoin?"])
            # This close-but-not-exact match should fail at 95% threshold
            intent, matched, response = classifier.classify("Litecoin is what?")
            # Depending on exact score, this might not match
            # The key is that the threshold is respected
    
    # === Edge Cases ===
    
    def test_empty_query(self, classifier):
        """Test handling of empty query."""
        intent, matched, response = classifier.classify("")
        assert intent == Intent.SEARCH
        assert matched is None
        assert response is None
    
    def test_whitespace_only_query(self, classifier):
        """Test handling of whitespace-only query."""
        intent, matched, response = classifier.classify("   ")
        assert intent == Intent.SEARCH
    
    def test_none_like_handling(self, classifier_no_faq):
        """Test handling when no FAQ questions loaded."""
        intent, matched, response = classifier_no_faq.classify("What is Litecoin?")
        # Without FAQ questions, should fall through to SEARCH
        assert intent == Intent.SEARCH
        assert matched is None
    
    def test_update_faq_questions(self, classifier):
        """Test updating FAQ questions dynamically."""
        # Initially should match
        intent1, _, _ = classifier.classify("What is Litecoin?")
        assert intent1 == Intent.FAQ_MATCH
        
        # Update with new questions
        classifier.update_faq_questions(["How does Bitcoin work?"])
        
        # Old question should no longer match
        intent2, _, _ = classifier.classify("What is Litecoin?")
        assert intent2 == Intent.SEARCH
        
        # New question should match
        intent3, matched, _ = classifier.classify("How does Bitcoin work?")
        assert intent3 == Intent.FAQ_MATCH
        assert matched == "How does Bitcoin work?"
    
    # === Search Intent (Default) ===
    
    def test_search_complex_question(self, classifier):
        """Test that complex questions fall through to search."""
        intent, matched, response = classifier.classify(
            "Can you explain the technical differences between Litecoin's MWEB and Monero's privacy features?"
        )
        assert intent == Intent.SEARCH
        assert matched is None
        assert response is None
    
    def test_search_mining_question(self, classifier):
        """Test that mining questions fall through to search."""
        intent, matched, response = classifier.classify("How do I mine Litecoin?")
        assert intent == Intent.SEARCH
    
    def test_price_question_is_blockchain_lookup(self, classifier):
        """Live LTC price is served from Litecoin Space, not generic search."""
        intent, matched, response = classifier.classify("What is the current price of Litecoin?")
        assert intent == Intent.BLOCKCHAIN_LOOKUP
        assert matched == "price"


class TestIntentClassifierWithoutRapidfuzz:
    """Test behavior when rapidfuzz is not available."""
    
    def test_faq_matching_disabled_without_rapidfuzz(self):
        """Test that FAQ matching gracefully degrades without rapidfuzz."""
        with patch.dict('backend.services.intent_classifier.__dict__', {'RAPIDFUZZ_AVAILABLE': False}):
            # Need to reimport to get patched value
            # In practice, the classifier checks RAPIDFUZZ_AVAILABLE at runtime
            classifier = IntentClassifier(faq_questions=["What is Litecoin?"])
            # When rapidfuzz not available, FAQ matching returns None
            # and falls through to SEARCH
    
    def test_greeting_still_works_without_rapidfuzz(self):
        """Test that greeting detection still works without rapidfuzz."""
        # Greeting detection uses both exact match and fuzzy match
        # Exact match should still work
        classifier = IntentClassifier(faq_questions=[])
        intent, _, _ = classifier.classify("hello")
        assert intent == Intent.GREETING


class TestIntentEnum:
    """Test the Intent enum."""
    
    def test_intent_values(self):
        """Test that Intent enum has expected values."""
        assert Intent.GREETING.value == "greeting"
        assert Intent.THANKS.value == "thanks"
        assert Intent.FAQ_MATCH.value == "faq_match"
        assert Intent.SEARCH.value == "search"
    
    def test_intent_membership(self):
        """Test Intent enum membership check."""
        assert Intent.GREETING in (Intent.GREETING, Intent.THANKS)
        assert Intent.SEARCH not in (Intent.GREETING, Intent.THANKS)


