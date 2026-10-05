import re
from typing import Dict

# 1. Expanded and categorized synonym map
LTC_SYNONYM_MAP: Dict[str, str] = {
    # --- Privacy & MWEB ---
    "mimblewimble": "mweb",
    "extension blocks": "mweb",
    "privacy upgrade": "mweb",
    "confidential transactions": "mweb",
    "mw": "mweb",
    "eb": "mweb",
    
    # --- Economics, Supply & Halving ---
    "total coins": "supply",
    "circulating supply": "supply",
    "issuance": "supply",
    "inflation": "supply",
    "max supply": "supply",
    "halvening": "halving",
    "block reward reduction": "halving",
    "subsidy": "halving",
    "stock to flow": "economics",
    "scarcity": "economics",
    
    # --- Leadership, Governance & History ---
    "charlie lee": "creator",
    "coblee": "creator",
    "founder": "creator",
    "litecoin foundation": "foundation",
    "lf": "foundation",
    "genesis block": "history",
    "fair launch": "history",
    "silver to gold": "narrative",
    "digital silver": "narrative",

    
    # --- Mining & Security ---
    "mining algorithm": "scrypt",
    "hashing algorithm": "scrypt",
    "pow": "proof of work",
    "51% attack": "security",
    "double spend": "security",
    "asic": "mining hardware",
    "l7": "mining hardware", # Antminer L7 is dominant for LTC
    "merged mining": "auxpow",
    "doge mining": "auxpow",
    
    # --- Layer 2, Scaling & Assets ---
    "lightning network": "lightning",
    "l2": "lightning",
    "payment channels": "lightning",
    "omnilite": "smart contracts",
    "litvm": "litvm",
    "litecoin virtual machine": "litvm",
    "zero-knowledge omnichain": "litvm",
    "tokens": "ordinals",
    "inscriptions": "ordinals",
    "brc-20": "ltc-20",
    "taproot": "upgrades",
    "segwit": "upgrades",
    "bech32": "address format",

    # --- Transaction Policy & Fee Management ---
    "replace-by-fee": "rbf",
    "replace by fee": "rbf",
    "fee bumping": "rbf",
    "child-pays-for-parent": "cpfp",
    "child pays for parent": "cpfp",
    "0-conf": "zero-confirmation",
    "zero-conf": "zero-confirmation",
    "zero confirmation": "zero-confirmation",
    "first-seen": "first-seen policy",
    "first seen rule": "first-seen policy",

    # --- HD Wallets & Key Derivation ---
    "hd wallet": "child keys",
    "hd wallets": "child keys",
    "hierarchical deterministic": "child keys",
    "derivation path": "child keys",
    "derivation paths": "child keys",
    "seed phrase": "child keys",
    "recovery phrase": "child keys",
    "mnemonic": "child keys",
    "bip32": "hd standards",
    "bip44": "hd standards",
    "bip84": "hd standards",
    "bip86": "hd standards",
    "xpub": "extended keys",
    "extended public key": "extended keys",

    # --- Wallet & Integration ---
    "litewallet": "wallet",
    "loafwallet": "wallet",
    "electrum-ltc": "wallet",
    "cold storage": "custody",
    "hardware wallet": "custody",
    "ledger": "custody",
    "trezor": "custody",

    # --- Other ---
    "blocktime": "litecoin block time",
    "block time": "litecoin block time",
    "hashrate": "litecoin hashrate",
    "supply": "litecoin supply",
    "address": "litecoin address",
    "transaction": "litecoin transaction",
    "transactions": "litecoin transactions",
    "block": "litecoin block",
    "blocks": "litecoin blocks",
    "network": "litecoin network",
    "networks": "litecoin networks",
    "node": "litecoin node",
    "nodes": "litecoin nodes",
    "peer": "litecoin peer",
    "peers": "litecoin peers",
    "peer-to-peer": "litecoin peer-to-peer",
    "p2p": "litecoin peer-to-peer",
    "p2p network": "litecoin peer-to-peer network",
    "p2wpkh": "bech32",
    "p2wsh": "bech32",
    "lip-2": "mweb",
}

# Entity expansion map for rare terms that need synonym boosting in retrieval
# Unlike LTC_SYNONYM_MAP (which replaces terms), this APPENDS synonyms to improve
# semantic search recall for queries containing these entities.
LTC_ENTITY_EXPANSIONS: Dict[str, str] = {
    # --- Existing (Kept for context) ---
    "litvm": "litecoin virtual machine zero-knowledge omnichain smart contracts",
    "mweb": "mimblewimble extension blocks privacy confidential transactions lip-0002 lip-0003", # Added LIPs
    "scrypt": "hashing algorithm mining proof of work",
    "halving": "block reward reduction subsidy economics issuance",
    "lightning": "lightning network payment channels layer 2 scaling off-chain",
    "ordinals": "inscriptions tokens ltc-20 nft digital artifacts",
    "auxpow": "merged mining doge mining auxiliary proof of work",

    # --- NEW: Protocol & Upgrades ---
    "segwit": "segregated witness transaction malleability block weight capacity upgrade bip141",
    "taproot": "schnorr signatures mast privacy smart contracts upgrade bip341",
    "atomic swaps": "cross-chain decentralized exchange htlc interoperability swap",
    "csv": "checksequenceverify timelock relative locktime smart contract",
    "cltv": "checklocktimeverify timelock absolute locktime smart contract",
    
    # --- NEW: Addressing & Standards ---
    "bech32": "native segwit address format ltc1 prefix efficiency",
    "p2sh": "pay to script hash multisig compatibility m-address 3-address",
    "ltc-20": "brc-20 standard fungible tokens json experimental overlay protocol",
    "omnilite": "omni layer tokens stablecoin usdt assets",

    # --- Transaction Policy & Fee Management ---
    "rbf": "replace-by-fee fee bumping opt-in first-seen zero-confirmation 0-conf bip125 stuck transaction",
    "cpfp": "child-pays-for-parent fee stuck transaction change output mempool",
    "zero-confirmation": "0-conf unconfirmed instant payment merchant first-seen",

    # --- HD Wallets & Key Derivation ---
    "child keys": "hd wallet hierarchical deterministic bip32 bip44 bip84 bip86 derivation path seed phrase xpub extended keys master key",
    "hd standards": "bip32 bip44 bip84 bip86 hierarchical deterministic child keys derivation path",
    "extended keys": "xpub extended public key child keys hd wallet derivation",

    # --- Network & Infrastructure ---
    "mempool": "memory pool unconfirmed transactions fee estimation congestion",
    "difficulty": "mining difficulty retarget adjustment hashrate security",
    "litecoin core": "reference client full node daemon wallet software",
    "electrum-ltc": "spv wallet lightweight client deterministic seed",

    # --- Leadership (TTFT: vocab-first short-query / rewrite-skip smoke) ---
    "charlie": "charlie lee creator founder coblee",
    "charlie lee": "creator founder coblee",
    "foundation": "litecoin foundation lf",
    "litecoin foundation": "lf foundation",
}

# Topicality: terms that mark a question as being about Litecoin (or the crypto
# concepts the knowledge base covers). Used by the abstain path: a low-confidence
# retrieval for a question with none of these never reaches the web-search tier.
_TOPICAL_TERMS = frozenset(
    {
        "litecoin", "ltc", "lite coin", "mweb", "mimblewimble", "scrypt", "halving", "halvening",
        "charlie lee", "coblee", "litvm", "omnilite", "ltc-20", "auxpow", "merged mining",
        "litecoin core", "litecoin foundation", "electrum-ltc", "litecoinspace", "litecoin space",
        # generic chain concepts the KB documents (allowed even without the word "litecoin")
        "blockchain", "wallet", "seed phrase", "private key", "mining", "miner", "hashrate",
        "mempool", "utxo", "segwit", "taproot", "lightning network", "lightning", "node",
        "confirmation", "confirmations", "block reward", "block time", "transaction fee",
        "satoshi", "crypto", "cryptocurrency", "bitcoin", "btc", "dogecoin", "doge",
        "ordinals", "inscriptions", "atomic swap", "cold storage", "hardware wallet",
        "exchange", "merchant", "payment", "address", "txid", "block height", "difficulty",
    }
    | set(LTC_SYNONYM_MAP.keys())
    | set(LTC_ENTITY_EXPANSIONS.keys())
)
_TOPICAL_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(_TOPICAL_TERMS, key=len, reverse=True)) + r")\b",
    flags=re.IGNORECASE,
)
_LTC_ADDRESS_OR_TXID = re.compile(r"\b(?:[LM3][a-km-zA-HJ-NP-Z1-9]{26,34}|ltc1[a-z0-9]{20,}|[a-fA-F0-9]{64})\b")


def is_litecoin_related(query: str) -> bool:
    """True when the question is plausibly within the knowledge base's domain."""
    if not query:
        return False
    return bool(_TOPICAL_PATTERN.search(query) or _LTC_ADDRESS_OR_TXID.search(query))


# 2. Pre-compile the regex for O(1) invocation performance
# We sort by length descending to ensure longest matches are prioritized
_SORTED_SYNONYMS = sorted(LTC_SYNONYM_MAP.keys(), key=len, reverse=True)
_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(s) for s in _SORTED_SYNONYMS) + r')\b', 
    flags=re.IGNORECASE
)

def normalize_ltc_keywords(query: str) -> str:
    """
    Normalizes query using a single-pass regex for high-performance mapping.
    
    Args:
        query: User input string.
    Returns:
        Normalized string with canonical terms.
    """
    if not query:
        return ""

    # The lambda function looks up the lowercase match in our map
    return _PATTERN.sub(
        lambda m: LTC_SYNONYM_MAP[m.group(0).lower()], 
        query
    ).strip()


def expand_ltc_entities(query: str) -> str:
    """
    Expands known entities with synonyms to improve retrieval recall.
    
    Unlike normalize_ltc_keywords() which replaces terms, this function
    APPENDS synonyms to the query when rare entities are detected. This
    helps semantic search find relevant documents that use different
    terminology for the same concept.
    
    Example:
        "explain litvm" -> "explain litvm litecoin virtual machine zero-knowledge omnichain smart contracts"
    
    Args:
        query: User input string (typically after normalization).
    Returns:
        Query with appended synonyms for detected entities.
    """
    if not query:
        return ""
    
    query_lower = query.lower()
    expansions_to_add = []
    
    for entity, expansion in LTC_ENTITY_EXPANSIONS.items():
        # Check if entity is in query but expansion terms are not already present
        if entity in query_lower:
            # Only add expansion if it's not already in the query
            expansion_terms = expansion.split()
            new_terms = [term for term in expansion_terms if term not in query_lower]
            if new_terms:
                expansions_to_add.extend(new_terms)
    
    if expansions_to_add:
        # Append unique expansion terms to the query
        return f"{query} {' '.join(expansions_to_add)}".strip()
    
    return query.strip()