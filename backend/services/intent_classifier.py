"""
Intent Classification Service

Routes queries to the optimal handler based on detected intent.
Reduces unnecessary RAG calls for common queries like greetings,
thanks, and FAQ matches.

The classifier uses fuzzy string matching (no LLM calls) for fast,
cost-effective intent detection.
"""

import os
import re
import logging
from typing import Tuple, Optional, List, Set
from enum import Enum

try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

logger = logging.getLogger(__name__)

_NORMALIZE_RE = re.compile(r"[a-z0-9]+")


class Intent(Enum):
    """User intent categories."""
    GREETING = "greeting"
    THANKS = "thanks"
    FAQ_MATCH = "faq_match"
    BLOCKCHAIN_LOOKUP = "blockchain_lookup"
    SEARCH = "search"


class IntentClassifier:
    """
    Lightweight intent classifier for query routing.
    
    Uses fuzzy matching and keyword detection to classify user queries
    without requiring LLM calls. This enables fast routing of common
    queries (greetings, thanks) and FAQ matches.
    
    Attributes:
        faq_questions: List of suggested questions from CMS
        faq_match_threshold: Minimum similarity score for FAQ matching (0-100)
    """
    
    # Greeting patterns - short phrases that indicate a greeting
    GREETING_PATTERNS = [
        "hello", "hi", "hey", "good morning", "good afternoon",
        "good evening", "what's up", "howdy", "greetings", "yo",
        "hiya", "sup", "hi there", "hello there", "hey there"
    ]
    
    # Thanks patterns - phrases that indicate gratitude
    THANKS_PATTERNS = [
        "thanks", "thank you", "thx", "appreciate", "helpful",
        "got it", "understood", "makes sense", "perfect", "great",
        "awesome", "cool", "nice", "cheers", "ty", "tyvm",
        "thank you so much", "thanks a lot", "much appreciated"
    ]
    
    # Static response for greetings
    GREETING_RESPONSE = (
        "Hello! I'm here to help you learn about Litecoin. "
        "Feel free to ask me anything about Litecoin's technology, "
        "history, wallets, or how to get started!"
    )
    
    # Static response for thanks
    THANKS_RESPONSE = (
        "You're welcome! Is there anything else you'd like to know about Litecoin?"
    )

    # Litecoin transaction ID: 64 hex characters
    _TX_RE = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)

    # Litecoin addresses: Legacy (L/M prefix, 26-35 chars) or Bech32 (ltc1, 42-62 chars)
    _ADDR_RE = re.compile(r"\b(?:[LM][1-9A-HJ-NP-Za-km-z]{25,34}|ltc1[a-z0-9]{39,59})\b")

    # Block height: digits optionally preceded by "block" context words
    _BLOCK_HEIGHT_RE = re.compile(
        r"(?:block\s*(?:height|number|#)?\s*#?\s*)(\d{1,9})\b", re.IGNORECASE
    )

    # Mining pool list: rankings / names of pools (Litecoin Space /api/v1/mining/pools)
    _MINING_POOL_LIST_RES = (
        # Plural only — avoids "join a mining pool" (recommendation-style queries)
        re.compile(r"\bmining\s+pools\b", re.IGNORECASE),
        re.compile(
            r"\b(list|lists|show|name|names|give|what\s+are|which|all|every)\b.{0,48}\bpools?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(top|largest|biggest|rank(?:ed|ing)?s?|order(?:ed)?)\b.{0,48}\b(?:mining\s+)?pools?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bpools?\b.{0,32}\b(rank|ranking|largest|biggest|top|order)\b",
            re.IGNORECASE,
        ),
    )

    # Recognized pool name → API slug (litecoinspace.org); longer / more specific first
    _MINING_POOL_SLUG_RES: List[Tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bfoundry\s*usa\b|\bfoundryusa\b", re.I), "foundryusa"),
        (re.compile(r"\bbinance\s*pool\b|\bbinancepool\b", re.I), "binancepool"),
        (re.compile(r"\blitecoin\s*pool(?:\.org)?\b|\blitecoinpoolorg\b", re.I), "litecoinpoolorg"),
        (re.compile(r"\bluxor(?:\s*labs)?\b|\bluxorlabs\b", re.I), "luxorlabs"),
        (re.compile(r"\bmining\s*dutch\b|\bminingdutch\b", re.I), "miningdutch"),
        (re.compile(r"\bsbi\s*crypto\b|\bsbicrypto\b", re.I), "sbicrypto"),
        (re.compile(r"\bsigma\s*pool\b|\bsigmapoolcom\b", re.I), "sigmapoolcom"),
        (re.compile(r"\bsolopool\b", re.I), "solopoolorg"),
        (re.compile(r"\bprohashing\b", re.I), "prohashing"),
        (re.compile(r"\bf2\s*pool\b|\bf2pool\b", re.I), "f2pool"),
        (re.compile(r"\bvia\s*btc\b|\bviabtc\b", re.I), "viabtc"),
        (re.compile(r"\bant\s*pool\b|\bantpool\b", re.I), "antpool"),
        (re.compile(r"\bnice\s*hash\b|\bnicehash\b", re.I), "nicehash"),
        (re.compile(r"\bslush\s*pool\b|\bslushpool\b", re.I), "slushpool"),
        (re.compile(r"\bpoolin\b", re.I), "poolin"),
    ]

    _POOL_HISTORY_PERIOD_RES = re.compile(
        r"\b(24h|3d|1w|1m|3m|6m|1y|2y|3y)\b", re.IGNORECASE
    )

    _POOL_DETAIL_SIGNAL_RES = re.compile(
        r"\b(hashrate|hash\s*rate|hashing|blocks?\s+found|block\s+share|share\s+of|"
        r"dominan|percent|percentage|how\s+much|proportion|estimated|reported|"
        r"mine\b|mining\b|miners?\b|statistics|stats|details|about|who\s+runs)\b",
        re.IGNORECASE,
    )

    _POOL_FEE_FOCUS_RES = re.compile(
        r"\b(fee|fees|payout|payouts|payment|payments|cost|charge)\b", re.IGNORECASE
    )

    # Keyword sets for live-data queries
    _FEE_KEYWORDS: Set[str] = {
        "fee", "fees", "transaction fee", "recommended fee", "current fee",
        "fee rate", "fee estimate", "sat per byte", "litoshi per byte",
    }
    _MEMPOOL_KEYWORDS: Set[str] = {
        "mempool", "unconfirmed transactions", "pending transactions",
        "mempool congestion", "mempool status",
    }
    _HASHRATE_KEYWORDS: Set[str] = {
        "hashrate", "hash rate", "mining hashrate", "network hashrate",
        "mining difficulty", "difficulty adjustment",
    }
    _PRICE_KEYWORDS: Set[str] = {
        "litecoin price", "ltc price", "current price", "price of litecoin",
        "price of ltc", "how much is litecoin", "how much is ltc",
        "ltc usd", "ltc eur",
    }
    _BLOCK_TIP_KEYWORDS: Set[str] = {
        "block height", "block tip", "current block", "latest block",
        "newest block", "last block", "tip height", "chain height",
        "how tall is the blockchain", "how many blocks",
    }
    
    @staticmethod
    def _normalize(text: str) -> str:
        """
        Normalize text for robust intent matching.
        
        - Lowercases
        - Strips punctuation
        - Collapses to space-separated alphanumeric tokens
        
        This avoids substring false positives like 'sup' matching 'supply'.
        """
        if not text:
            return ""
        return " ".join(_NORMALIZE_RE.findall(text.lower()))

    def __init__(self, faq_questions: Optional[List[str]] = None):
        """
        Initialize the classifier.
        
        Args:
            faq_questions: List of suggested questions from CMS for FAQ matching
        """
        if not RAPIDFUZZ_AVAILABLE:
            logger.warning(
                "rapidfuzz not installed. FAQ matching will be disabled. "
                "Install with: pip install rapidfuzz"
            )
        
        self.faq_questions = faq_questions or []
        self.faq_match_threshold = float(os.getenv("FAQ_MATCH_THRESHOLD", "85"))
        
        logger.info(
            f"IntentClassifier initialized with {len(self.faq_questions)} FAQ questions, "
            f"threshold={self.faq_match_threshold}"
        )
    
    def update_faq_questions(self, questions: List[str]) -> None:
        """
        Update the FAQ questions list.
        
        Call this when suggested questions are refreshed from CMS.
        
        Args:
            questions: New list of FAQ question strings
        """
        self.faq_questions = questions
        logger.info(f"Updated FAQ questions: {len(questions)} loaded")
    
    def classify(self, query: str) -> Tuple[Intent, Optional[str], Optional[str]]:
        """
        Classify user query intent.
        
        Args:
            query: The user's query string
            
        Returns:
            Tuple of:
            - Intent enum value
            - Matched FAQ question (if FAQ_MATCH) or None
            - Static response (if GREETING/THANKS) or None
        """
        if not query or not query.strip():
            return Intent.SEARCH, None, None
        
        query_lower = query.lower().strip()
        
        # Check for greeting (short queries only)
        if self._is_greeting(query_lower):
            logger.debug(f"Classified as GREETING: {query[:50]}")
            return Intent.GREETING, None, self.GREETING_RESPONSE
        
        # Check for thanks (short queries only)
        if self._is_thanks(query_lower):
            logger.debug(f"Classified as THANKS: {query[:50]}")
            return Intent.THANKS, None, self.THANKS_RESPONSE
        
        # Check for blockchain data lookup (live API queries)
        blockchain_entity = self._detect_blockchain_lookup(query_lower, query)
        if blockchain_entity:
            logger.debug(f"Classified as BLOCKCHAIN_LOOKUP: {query[:50]} -> {blockchain_entity}")
            return Intent.BLOCKCHAIN_LOOKUP, blockchain_entity, None
        
        # Check for FAQ match (if rapidfuzz available)
        matched_faq = self._match_faq(query)
        if matched_faq:
            logger.debug(f"Classified as FAQ_MATCH: {query[:50]} -> {matched_faq[:50]}")
            return Intent.FAQ_MATCH, matched_faq, None
        
        # Default to search
        return Intent.SEARCH, None, None
    
    def _is_greeting(self, query: str) -> bool:
        """
        Check if query is a greeting.
        
        Only considers short queries (3 words or less) to avoid
        false positives on longer questions that happen to contain
        greeting words.
        
        Args:
            query: Lowercase, stripped query string
            
        Returns:
            True if query is classified as a greeting
        """
        # Only check short queries
        word_count = len(query.split())
        if word_count > 3:
            return False
        
        q = self._normalize(query)
        if not q:
            return False

        # Check for exact (normalized) or fuzzy matches
        for pattern in self.GREETING_PATTERNS:
            p = self._normalize(pattern)
            if not p:
                continue
            
            # Exact match only (prevents 'sup' matching 'supply')
            if q == p:
                return True
            
            # Use fuzzy matching for short, similar-length strings to catch typos
            if RAPIDFUZZ_AVAILABLE:
                if len(q) >= 3 and abs(len(q) - len(p)) <= 3:
                    if fuzz.ratio(q, p) > 80:
                        return True
        
        return False
    
    def _is_thanks(self, query: str) -> bool:
        """
        Check if query is a thank you message.
        
        Only considers short queries (5 words or less) to avoid
        false positives.
        
        Args:
            query: Lowercase, stripped query string
            
        Returns:
            True if query is classified as thanks
        """
        # Only check short queries
        word_count = len(query.split())
        if word_count > 5:
            return False
        
        q = self._normalize(query)
        if not q:
            return False

        # Check for exact (normalized) or fuzzy matches
        for pattern in self.THANKS_PATTERNS:
            p = self._normalize(pattern)
            if not p:
                continue
            
            # Exact match only (prevents accidental substring matches)
            if q == p:
                return True
            
            # Use fuzzy matching for short, similar-length strings to catch typos
            if RAPIDFUZZ_AVAILABLE:
                if len(q) >= 3 and abs(len(q) - len(p)) <= 4:
                    if fuzz.ratio(q, p) > 80:
                        return True
        
        return False
    
    def _detect_blockchain_lookup(self, query_lower: str, query_raw: str) -> Optional[str]:
        """
        Detect if the query is requesting live blockchain data.

        Returns an entity string encoding the lookup type and value,
        e.g. "tx:abc123...", "address:ltc1q...", "fees", "price".
        Returns None if this is not a blockchain data query.
        """
        # Transaction ID (64-char hex)
        tx_match = self._TX_RE.search(query_raw)
        if tx_match:
            return f"tx:{tx_match.group(0)}"

        # Litecoin address
        addr_match = self._ADDR_RE.search(query_raw)
        if addr_match:
            return f"address:{addr_match.group(0)}"

        # Block height with explicit context ("block 12345", "block height 12345")
        height_match = self._BLOCK_HEIGHT_RE.search(query_raw)
        if height_match:
            return f"block_height:{height_match.group(1)}"

        # Named mining pool stats (before generic network hashrate)
        slug = self._detect_mining_pool_slug(query_lower)
        if slug and self._wants_specific_pool_stats(query_lower):
            return f"mining_pool:{slug}"

        # Block tip (no specific height — e.g. "current block height?")
        if any(kw in query_lower for kw in self._BLOCK_TIP_KEYWORDS):
            return "block_tip"

        # Keyword-based lookups (check longest matches first)
        if any(kw in query_lower for kw in self._PRICE_KEYWORDS):
            return "price"
        if any(kw in query_lower for kw in self._FEE_KEYWORDS):
            return "fees"
        if any(kw in query_lower for kw in self._MEMPOOL_KEYWORDS):
            return "mempool"
        if self._wants_mining_pool_ranking(query_lower):
            period = self._extract_mining_pool_period(query_lower)
            if period == "all":
                return "mining_pools:all"
            if period:
                return f"mining_pools:{period}"
            return "mining_pools"
        if any(kw in query_lower for kw in self._HASHRATE_KEYWORDS):
            return "hashrate"

        return None

    def _detect_mining_pool_slug(self, query_lower: str) -> Optional[str]:
        for pattern, slug in self._MINING_POOL_SLUG_RES:
            if pattern.search(query_lower):
                return slug
        return None

    def _wants_specific_pool_stats(self, query_lower: str) -> bool:
        if not self._POOL_DETAIL_SIGNAL_RES.search(query_lower):
            return False
        if self._POOL_FEE_FOCUS_RES.search(query_lower) and not re.search(
            r"\b(hashrate|hash\s*rate|block\s+share|share\s+of|how\s+much\s+of|"
            r"percent|percentage|dominan|proportion)\b",
            query_lower,
            re.IGNORECASE,
        ):
            return False
        return True

    def _wants_mining_pool_ranking(self, query_lower: str) -> bool:
        if self._MINING_POOL_LIST_RES[0].search(query_lower):
            return True
        loose = any(p.search(query_lower) for p in self._MINING_POOL_LIST_RES[1:])
        if not loose:
            return False
        return bool(
            re.search(
                r"\b(litecoin|ltc|mining|mine|miners?|scrypt|blocks?|hashrate|hash\s*rate)\b",
                query_lower,
                re.IGNORECASE,
            )
        )

    def _extract_mining_pool_period(self, query_lower: str) -> Optional[str]:
        if re.search(r"\b(all[\s-]?time|overall|entire\s+history)\b", query_lower):
            return "all"
        m = self._POOL_HISTORY_PERIOD_RES.search(query_lower)
        if m:
            return m.group(1).lower()
        return None

    def _match_faq(self, query: str) -> Optional[str]:
        """
        Fuzzy match against FAQ questions.
        
        Uses token_sort_ratio which is more robust to word order differences.
        For example, "what is litecoin" and "litecoin what is" would score highly.
        
        Args:
            query: The user's query string
            
        Returns:
            Matched FAQ question if similarity >= threshold, else None
        """
        if not RAPIDFUZZ_AVAILABLE:
            return None
        
        if not self.faq_questions:
            return None
        
        # Use extractOne for best match with token_sort_ratio scorer
        result = process.extractOne(
            query,
            self.faq_questions,
            scorer=fuzz.token_sort_ratio
        )
        
        if result and result[1] >= self.faq_match_threshold:
            matched_question = result[0]
            score = result[1]
            logger.debug(f"FAQ match: '{query}' -> '{matched_question}' (score: {score})")
            return matched_question
        
        return None


