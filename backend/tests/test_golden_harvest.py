"""Fixture tests for golden-set harvest classification. No Mongo."""

from backend.eval.golden_harvest import (
    GOLDEN_QUESTION_CAP,
    build_packet,
    normalize_query,
    observation_from_gap,
    slots_remaining,
)

GOLDEN = [
    {"id": "faq-what-is-litecoin", "query": "What is Litecoin?", "expected_behavior": "answer"},
    {"id": "faq-what-is-mweb", "query": "What is MWEB?", "expected_behavior": "answer"},
    {"id": "refuse-good-investment", "query": "Is Litecoin a good investment?", "expected_behavior": "refuse"},
    {"id": "gap-run-litecoin-node", "query": "How do mining pools find a Litecoin block?", "expected_behavior": "answer"},
]


def _by_query(packet, fragment):
    matches = [c for c in packet["candidates"] if fragment.lower() in c["query"].lower()]
    assert len(matches) == 1, packet["candidates"]
    return matches[0]


def test_normalize_query_folds_case_and_punctuation():
    assert normalize_query("  What   is Litecoin? ") == "what is litecoin"
    assert normalize_query("Is LTC worth buying!") == normalize_query("is ltc worth buying")


def test_slots_remaining_uses_the_scaffold_cap():
    assert GOLDEN_QUESTION_CAP == 90
    assert slots_remaining(81) == 9
    assert slots_remaining(90) == 0
    assert slots_remaining(100) == 0


def test_drops_exact_short_followup_and_cache_hit():
    rows = [
        {"source": "log", "query": "What is Litecoin?", "chat_history_length": 0},
        {"source": "log", "query": "What is LTC?", "chat_history_length": 0},
        {"source": "log", "query": "How do I back up a Litecoin wallet seed?", "chat_history_length": 2},
        {"source": "log", "query": "How do I back up a Litecoin wallet seed?", "cache_hit": True, "abstained": True},
        {"source": "log", "query": "   ", "abstained": True},
    ]
    packet = build_packet(rows, GOLDEN)
    assert packet["candidates"] == []
    assert packet["dropped"] == {"exact_cover": 1, "too_short": 1, "follow_up": 1, "cache_hit": 1, "empty": 1}
    assert packet["golden_count"] == len(GOLDEN)
    assert packet["slots_remaining"] == slots_remaining(len(GOLDEN))


def test_cache_routing_maps_to_behavior_with_empty_substrings():
    rows = [
        {"source": "log", "query": "Should I buy Litecoin before the halving?", "cache_type": "intent_refuse", "sources_count": 0},
        {"source": "log", "query": "Who should I contact about a partnership with the Litecoin Foundation?", "cache_type": "intent_escalate", "sources_count": 0},
        {"source": "log", "query": "What is the Litecoin network fee right now?", "cache_type": "blockchain_lookup:fee", "sources_count": 0},
    ]
    packet = build_packet(rows, GOLDEN)
    refuse = _by_query(packet, "buy Litecoin")
    assert refuse["suggested_behavior"] == "refuse"
    assert refuse["category"] == "refuse"
    assert refuse["expected_source_substrings"] == []
    assert refuse["yaml_ready"] is True
    escalate = _by_query(packet, "partnership")
    assert escalate["suggested_behavior"] == "escalate" and escalate["category"] == "escalate"
    lookup = _by_query(packet, "network fee")
    assert lookup["suggested_behavior"] == "lookup" and lookup["category"] == "blockchain-live"


def test_published_article_gets_a_slug_needle():
    packet = build_packet(
        [
            {
                "source": "gap",
                "query": "How do I open a Litecoin wallet?",
                "frequency": 4,
                "status": "published",
                "article_slug": "opening-a-wallet",
                "article_title": "Opening a wallet",
                "topic_cluster": "wallets",
            }
        ],
        GOLDEN,
    )
    row = packet["candidates"][0]
    assert row["suggested_behavior"] == "answer"
    assert row["category"] == "faq"
    assert row["expected_source_substrings"] == ["opening-a-wallet"]
    assert row["yaml_ready"] is True
    assert row["frequency"] == 4


def test_published_without_title_or_slug_is_not_yaml_ready():
    packet = build_packet(
        [{"source": "gap", "query": "How do I open a Litecoin wallet?", "status": "published", "frequency": 2}],
        GOLDEN,
    )
    row = packet["candidates"][0]
    assert row["suggested_behavior"] == "answer"
    assert row["expected_source_substrings"] == []
    assert row["yaml_ready"] is False
    assert "title or slug" in row["note"]


def test_open_gap_and_draft_are_not_citation_questions():
    packet = build_packet(
        [
            {
                "source": "gap",
                "query": "How do I run a Litecoin node at home?",
                "frequency": 3,
                "status": "pending",
                "payload_article_id": "draft-1",
                "article_slug": "run-a-node",
                "topic_cluster": "transactions",
                "answer_excerpt": "x" * 300,
            }
        ],
        GOLDEN,
    )
    row = packet["candidates"][0]
    assert row["suggested_behavior"] == "answer"
    assert row["category"] == "abstain"
    assert row["expected_source_substrings"] == []
    assert row["yaml_ready"] is False
    assert "must_not_contain" in row["note"]
    assert "CMS draft" in row["note"]
    assert row["proposed_id"].startswith("gap-")
    assert len(row["answer_excerpt"]) <= 240
    assert row["answer_excerpt"].endswith("…")


def test_off_topic_abstain_and_thumbs_down():
    packet = build_packet(
        [
            {"source": "log", "query": "What is the best recipe for sourdough bread?", "abstained": True, "sources_count": 0},
            {"source": "feedback", "query": "Why did the answer skip MWEB peg-ins entirely?", "feedback_reason": "wrong"},
        ],
        GOLDEN,
    )
    abstain = _by_query(packet, "sourdough")
    assert abstain["suggested_behavior"] == "abstain" and abstain["category"] == "abstain" and abstain["yaml_ready"] is True
    review = _by_query(packet, "peg-ins")
    assert review["suggested_behavior"] == "needs_review"
    assert review["category"] is None
    assert review["yaml_ready"] is False
    assert "wrong" in review["note"]


def test_feedback_merged_onto_a_gap_keeps_the_gap_behavior():
    packet = build_packet(
        [
            {"source": "gap", "query": "How do I run a Litecoin node at home?", "frequency": 5, "topic_cluster": "transactions", "status": "pending"},
            {"source": "log", "query": "how do I run a Litecoin node at home", "is_grounded": True, "sources_count": 0},
            {"source": "log", "query": "How do I run a Litecoin node at home?", "is_grounded": True},
            {"source": "feedback", "query": "How do I run a Litecoin node at home?", "feedback_reason": "missing"},
        ],
        GOLDEN,
    )
    assert len(packet["candidates"]) == 1
    row = packet["candidates"][0]
    assert row["sources"] == ["gap", "log", "feedback"]
    assert row["counts"] == {"gap": 5, "log": 2, "feedback": 1}
    assert row["frequency"] == 5
    assert row["suggested_behavior"] == "answer"
    assert row["query"] == "How do I run a Litecoin node at home?"


def test_close_match_is_kept_and_flagged():
    packet = build_packet(
        [{"source": "log", "query": "Is Litecoin a good investment right now?", "cache_type": "intent_refuse", "sources_count": 0}],
        GOLDEN,
    )
    row = packet["candidates"][0]
    assert row["close_golden_id"] == "refuse-good-investment"
    assert row["suggested_behavior"] == "refuse"


def test_proposed_id_avoids_existing_golden_ids():
    packet = build_packet(
        [{"source": "log", "query": "How do I run a Litecoin node?", "abstained": True, "sources_count": 0}],
        GOLDEN,
    )
    assert packet["candidates"][0]["proposed_id"] == "gap-run-litecoin-node-2"


def test_gap_mapper_drops_the_embedding():
    row = observation_from_gap(
        {
            "user_question": "How do I run a Litecoin node at home?",
            "question_frequency": 3,
            "question_embedding": [0.1, 0.2, 0.3],
            "status": "pending",
            "topic_cluster": "transactions",
            "generated_answer": "Run litecoind.",
        }
    )
    assert "question_embedding" not in row
    packet = build_packet([row], GOLDEN)
    assert "question_embedding" not in packet["candidates"][0]
    assert packet["candidates"][0]["frequency"] == 3


def test_refuse_wins_over_an_open_gap_on_the_same_question():
    packet = build_packet(
        [
            {"source": "gap", "query": "Should I buy Litecoin before the halving?", "topic_cluster": "halving", "frequency": 9, "status": "pending"},
            {"source": "log", "query": "Should I buy Litecoin before the halving?", "cache_type": "intent_refuse", "sources_count": 0},
        ],
        GOLDEN,
    )
    row = packet["candidates"][0]
    assert row["suggested_behavior"] == "refuse"
    assert row["expected_source_substrings"] == []


def test_candidates_sort_by_frequency():
    packet = build_packet(
        [
            {"source": "gap", "query": "How do I run a Litecoin node at home?", "frequency": 2, "topic_cluster": "transactions"},
            {"source": "gap", "query": "What does a Litecoin halving change for miners?", "frequency": 8, "topic_cluster": "halving"},
        ],
        GOLDEN,
    )
    assert [c["frequency"] for c in packet["candidates"]] == [8, 2]
