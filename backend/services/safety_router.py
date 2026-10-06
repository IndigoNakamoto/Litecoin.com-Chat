"""
Safety router: Refuse / Escalate / Audience classification.

Runs before caching and retrieval. Regex-first so it costs nothing and is
deterministic; an optional small LLM fallback can be enabled with
USE_LLM_SAFETY_FALLBACK=true for borderline phrasing.

Categories
----------
REFUSE (never answered, templated reply):
  financial_advice   buy/sell/hold, price targets, "should I invest"
  seed_phrase        seed/private-key handling, recovery-phrase walkthroughs
  legal_tax          tax or legal *conclusions* ("do I owe", "is it legal in X")
  impersonation      speak *as* Charlie Lee / the Foundation, or invent a position
  prompt_injection   ignore-previous-instructions, system-prompt dumps
  harm               theft, malware, draining wallets

ESCALATE (hand off; link block from env, editable without a deploy):
  bug | scam_report | partnership | press

AUDIENCE (changes answer length / tone, never scope):
  newcomer | holder | merchant | developer | journalist
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

AUDIENCES = ("newcomer", "holder", "merchant", "developer", "journalist")

# --- Refuse patterns ---------------------------------------------------------

_REFUSE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "financial_advice",
        re.compile(
            r"\b(should i|shall i|is it (a )?good (time|idea) to|worth) (buy|sell|hold|invest|short|long)\b"
            # "Should I buy Litecoin?" / "buy Litecoin now?" — but not "How do I buy Litecoin?"
            r"|\b(should|shall) (i|we) (buy|sell|hold) (ltc|litecoin)\b"
            r"|\b(buy|sell|hold) (ltc|litecoin) (now|today|right now|this (week|month|year))\b"
            r"|\bprice (target|prediction|forecast)s?\b"
            r"|\b(will|is|does) (ltc|litecoin) (hit|reach|go to|moon|pump|dump|crash|be worth)\b"
            r"|\b(how (much|high|low) will (ltc|litecoin))\b"
            r"|\bwhen (should i|to) (buy|sell|exit|enter)\b"
            # Paraphrases: "a good investment", "worth buying", "will it go up", "good time to get in"
            r"|\b(is|would be|be) (ltc|litecoin|it) (still )?a (good|bad|smart|safe|wise|sound) (investment|buy|bet)\b"
            r"|\b(a )?(good|bad|smart|safe|wise|sound) (investment|buy|bet)\b.*\b(ltc|litecoin)\b"
            r"|\bworth (buying|investing in|holding|getting into)\b"
            r"|\b(will|is|could|would) (ltc|litecoin|the price|it) (go|going) (up|down|higher|lower)\b"
            r"|\b(good|right|bad|best) time to (buy|sell|get in(to)?|invest|enter|exit)\b"
            r"|\b(should|shall) (i|we) (get into|invest in|put (my )?money in(to)?)\b"
            r"|\b(ltc|litecoin) (price|value) (in|by) (20\d\d|next year)\b"
            r"|\binvestment advice\b|\bfinancial advice\b",
            re.IGNORECASE,
        ),
    ),
    (
        "seed_phrase",
        re.compile(
            r"\b(my|the|this) (seed|recovery|mnemonic|backup) (phrase|words)\b"
            r"|\b(private|secret) key(s)?\b.*\b(send|share|give|enter|paste|recover|is|are)\b"
            r"|\b(send|share|give|paste|enter|type|dm) (me |you |us )?(your|my|the) (seed|private key|recovery phrase|mnemonic|passphrase)\b"
            r"|\b(seed|recovery|mnemonic) (phrase|words)\b.*\b(here|below|is|are|:)\b"
            r"|\b(12|24)[- ]word\b.*\b(phrase|seed|backup)\b"
            r"|\brecover (my )?(wallet|funds|coins|ltc).*\b(seed|phrase|key)\b"
            r"|\b(walk me through|help me) (enter(ing)?|input(ting)?|typ(e|ing)) (my )?(seed|phrase|private key)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "legal_tax",
        re.compile(
            r"\b(do i|will i|must i|am i required to) (have to |need to )?(pay|owe|report|declare|file)\b.*\b(tax|taxes|irs|hmrc|capital gains)\b"
            r"|\b(how much|what) tax (do|will|must) i\b"
            r"|\bis (it|litecoin|ltc|this) (legal|illegal|lawful|allowed|banned)\b"
            r"|\bcan i (legally|lawfully)\b"
            r"|\b(tax|legal) (advice|opinion|liability)\b"
            r"|\bshould i (report|declare)\b.*\b(tax|irs)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "impersonation",
        re.compile(
            r"\b(pretend|act|speak|answer|respond|write|reply|role[- ]?play)\b.*\b(as|like|you are|you're) (charlie lee|charlie|the (litecoin )?foundation|a foundation (spokesperson|official|director)|litecoin foundation)\b"
            r"|\b(you are|you're) (now )?(charlie lee|the litecoin foundation)\b"
            r"|\bwhat (does|would) (charlie lee|the foundation) (think|say|believe|want)\b.*\b(about|on)\b"
            r"|\b(official|foundation'?s?) (position|stance|statement|opinion) on\b"
            # "endorse / approve / back" are always a request for a position. "recommend / support"
            # only when the object is a specific project/coin/exchange ("Does the Foundation
            # recommend any wallet?" is a practical question and is answered from the KB).
            r"|\b(does|will) the (litecoin )?foundation (endorse|approve|back)\b"
            r"|\b(does|will) the (litecoin )?foundation (recommend|support) (this|that|my|our|the) (project|coin|token|exchange|etf|company|proposal|product)\b"
            r"|\bon behalf of (charlie lee|the (litecoin )?foundation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_injection",
        re.compile(
            r"\bignore (all |any |the )?(previous|prior|above|earlier) (instructions?|prompts?|rules?)\b"
            r"|\b(dump|print|reveal|show|repeat|output) (me )?(your|the) (system|hidden|secret|initial) (prompt|instructions?|message)\b"
            r"|\byou are now (dan|an? unrestricted|jailbroken)\b"
            r"|\bdeveloper mode\b|\bjailbreak\b",
            re.IGNORECASE,
        ),
    ),
    (
        "harm",
        re.compile(
            r"\b(steal|drain|hack|phish|hijack|siphon)\b.*\b(wallet|coins|litecoin|ltc|funds|someone)\b"
            r"|\b(write|build|create|make|code)\b.*\b(malware|ransomware|keylogger|drainer|phishing (site|page|kit))\b"
            r"|\bhow (do|can|to) i (steal|rob|scam|defraud)\b"
            r"|\bdouble[- ]spend attack\b.*\bhow (do|can) i\b",
            re.IGNORECASE,
        ),
    ),
]

# --- Escalate patterns -------------------------------------------------------

_ESCALATE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "scam_report",
        re.compile(
            r"\b(report|flag|reporting)\b.*\b(scam|scammer|fraud|phishing|fake (wallet|site|app|airdrop|giveaway))\b"
            r"|\b(i|we) (got|was|were|have been|think i('ve| have) been) (scammed|phished|defrauded|hacked|robbed)\b"
            r"|\b(is this|this looks like|i found) a (scam|phishing|fake) (site|wallet|app|giveaway|airdrop|email|message)\b"
            r"|\bsomeone (stole|took|drained|is impersonating)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "bug",
        re.compile(
            r"\b(report|found|file|submit|log) (a |an )?(bug|issue|crash|vulnerability|exploit|security (hole|flaw))\b"
            r"|\b(bug|issue|crash|vulnerability) (report|tracker|in litecoin core|in the (node|wallet|client))\b"
            r"|\blitecoin core (crashes|crashed|is crashing|won'?t (start|sync|open))\b"
            r"|\bresponsible disclosure\b|\bsecurity (contact|disclosure|@)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "partnership",
        re.compile(
            r"\b(partner(ship)?|sponsor(ship)?|collaborat(e|ion)|integrat(e|ion) (with|request)|business (proposal|inquiry|development)|list(ing)? (ltc|litecoin) on (our|my|an?) (exchange|platform|app))\b"
            r".*\b(foundation|with you|with litecoin|contact|who (do|should) i)\b"
            r"|\bwho (do|should|can) i (contact|talk to|email|reach)\b.*\b(partnership|sponsorship|business|listing|integration|grant|funding)\b"
            r"|\b(grant|funding) (program|application|request)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "press",
        re.compile(
            r"\b(press|media|journalist|reporter|interview|quote|comment|statement)\b.*\b(request|inquiry|enquiry|contact|for (an? )?(article|story|piece|publication))\b"
            r"|\b(i'?m|i am|we are) (a |an )?(journalist|reporter|writer|editor) (at|with|for|from)\b"
            r"|\bpress (contact|kit|release|office|team)\b"
            r"|\b(can|could|may) (i|we) (quote|interview|get a (comment|statement) from)\b",
            re.IGNORECASE,
        ),
    ),
]

# --- Audience patterns -------------------------------------------------------

_AUDIENCE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "developer",
        re.compile(
            r"\b(rpc|json-rpc|api|sdk|library|endpoint|regtest|testnet|signet|bip\d*|psbt|script(pub|sig)?|opcode|op_\w+|descriptor|"
            r"compile|build from source|git(hub)?|pull request|commit|node (software|binary)|daemon|litecoind|litecoin-cli|litecoin-qt|"
            r"config(uration)? file|litecoin\.conf|zmq|raw ?transaction|hex|serializ|merkle|consensus rule|soft ?fork|"
            r"mweb (spec|protocol|peg|kernel|stealth)|extension block|docker|python|javascript|typescript|rust|go(lang)?|c\+\+|code (sample|snippet|example))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "merchant",
        re.compile(
            r"\b(merchant|accept(ing)? (litecoin|ltc|payments?)|point[- ]of[- ]sale|pos (system|terminal)|checkout|"
            r"invoice|e-?commerce|shopify|woocommerce|btcpay|payment (processor|gateway|button|plugin)|"
            r"my (store|shop|business|customers)|refund|settlement|chargeback)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "journalist",
        re.compile(
            r"\b(journalist|reporter|press|media|article|story|publication|cite|citation|source for|"
            r"on (the )?record|fact[- ]check|verify (that|this|the claim)|official (figure|number|date)s?|"
            r"for (an? )?(article|piece|report|story))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "holder",
        re.compile(
            r"\b(my (ltc|litecoin|coins|wallet|holdings|bag)|hodl|holding|long[- ]term|cold storage|hardware wallet|"
            r"ledger|trezor|staking|stake|yield|airdrop|dividend|portfolio|store of value|"
            r"supply (cap|schedule)|halving (date|schedule|countdown)|scarcity)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "newcomer",
        re.compile(
            r"\b(what is|what'?s|explain|eli5|beginner|new to|just (started|getting started|heard)|"
            r"where (do|should|can) i (start|begin)|how (do|does|to) (i |you )?(get|buy|start|begin|set ?up|create|use)|"
            r"first (wallet|time|steps?)|simple (terms|explanation)|in plain english|getting started|"
            r"is litecoin (dead|safe|legit|real|a scam|still around|worth)|difference between)\b",
            re.IGNORECASE,
        ),
    ),
]


@dataclass
class SafetyDecision:
    intent: Optional[str]  # "refuse" | "escalate" | None
    category: Optional[str]
    audience: Optional[str]
    answer: Optional[str]  # templated early answer when intent is set


# --- Templated answers -------------------------------------------------------

REFUSE_TEMPLATES: Dict[str, str] = {
    "financial_advice": (
        "I can't give buy, sell, or price-target guidance. The Litecoin Knowledge Hub explains how "
        "Litecoin works, not what it will be worth or what you should do with your money.\n\n"
        "## What I can help with\n"
        "- How Litecoin's supply, halving, and issuance schedule work\n"
        "- What MWEB, Lightning, and other protocol features do\n"
        "- Live network data: fees, hashrate, blocks, and the current price (as a quoted number, not a forecast)"
    ),
    "seed_phrase": (
        "I won't help with seed phrases or private keys, and you should never share them with anyone, including a chatbot.\n\n"
        "## Keep your keys safe\n"
        "- Your recovery phrase is the only thing that controls your coins; anyone who sees it can take them\n"
        "- The Litecoin Foundation will never ask for it\n"
        "- For wallet recovery, use your wallet software's official documentation and offline device"
    ),
    "legal_tax": (
        "I can't tell you what the law or your tax obligations are. Rules differ by country and change often, "
        "and getting this wrong has real consequences.\n\n"
        "## What I can do\n"
        "- Explain how Litecoin transactions, addresses, and the public ledger work so you can describe them accurately\n"
        "- Point you to live, verifiable chain data\n\n"
        "For a conclusion about your situation, speak with a qualified tax or legal professional in your jurisdiction."
    ),
    "impersonation": (
        "I can't speak as Charlie Lee or as the Litecoin Foundation, and I won't invent an official position.\n\n"
        "## What I can do\n"
        "- Explain documented facts about Litecoin from the Foundation's published knowledge base\n"
        "- Point you to the Foundation's official channels for statements and press inquiries"
    ),
    "prompt_injection": (
        "I'll keep answering questions about Litecoin within the knowledge base's scope. "
        "Ask me about MWEB, the halving, fees, wallets, or live network data and I'm glad to help."
    ),
    "harm": (
        "I can't help with that. Stealing funds, building malware, or defrauding people is out of scope here and illegal.\n\n"
        "If you're trying to protect yourself from these attacks, ask me how Litecoin wallets, addresses, and confirmations work."
    ),
}

ESCALATE_INTRO: Dict[str, str] = {
    "scam_report": (
        "I'm sorry you ran into this. I can't investigate a scam myself, but here is where to report it:"
    ),
    "bug": "Thanks for flagging it. Bugs and security issues go to the Litecoin Core maintainers, not to this assistant:",
    "partnership": "Partnership, listing, and sponsorship conversations go to the Foundation's team rather than this assistant:",
    "press": "For press and media, please reach the Foundation directly so you get an attributable statement:",
}


def _escalate_links(category: str) -> str:
    """Hand-off links are env-configurable so they can change without a deploy."""
    defaults = {
        "scam_report": (
            "- Report to the Litecoin Foundation: https://litecoin.net/contact\n"
            "- If money was taken, file a report with your local police and your exchange or wallet provider\n"
            "- Warn others: https://www.reddit.com/r/litecoin/"
        ),
        "bug": (
            "- Litecoin Core issues: https://github.com/litecoin-project/litecoin/issues\n"
            "- Security-sensitive reports: see the SECURITY policy in that repository before posting publicly"
        ),
        "partnership": "- Litecoin Foundation contact: https://litecoin.net/contact",
        "press": "- Press and media inquiries: https://litecoin.net/contact",
    }
    override = os.getenv(f"ESCALATE_LINKS_{category.upper()}")
    return override.replace("\\n", "\n") if override else defaults.get(category, "- https://litecoin.net/contact")


def build_escalate_answer(category: str) -> str:
    intro = ESCALATE_INTRO.get(category, "This is better handled by a person at the Foundation:")
    return f"{intro}\n\n{_escalate_links(category)}\n\nI won't speculate on the Foundation's position; the links above reach the people who can."


def classify_audience(query: str, history_pairs: Optional[List[Tuple[str, str]]] = None) -> Optional[str]:
    """Pick the strongest audience signal; earlier conversation turns count too."""
    text = query or ""
    if history_pairs:
        text = " ".join(h for h, _ in history_pairs[-3:] if isinstance(h, str)) + " " + text
    for label, pattern in _AUDIENCE_PATTERNS:
        if pattern.search(text):
            return label
    return None


def classify_safety(query: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (intent, category) for refuse/escalate, or (None, None)."""
    q = (query or "").strip()
    if not q:
        return None, None
    for category, pattern in _REFUSE_PATTERNS:
        if pattern.search(q):
            return "refuse", category
    for category, pattern in _ESCALATE_PATTERNS:
        if pattern.search(q):
            return "escalate", category
    return None, None


async def classify_safety_llm(llm: Any, query: str) -> Tuple[Optional[str], Optional[str]]:
    """Optional LLM fallback for borderline phrasing. Only used when USE_LLM_SAFETY_FALLBACK=true."""
    if llm is None or not query:
        return None, None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        sys = (
            "Classify a user message to a Litecoin reference bot. Reply with exactly one token from: "
            "financial_advice, seed_phrase, legal_tax, impersonation, harm, scam_report, bug, partnership, press, none. "
            "Use 'none' unless the message clearly asks for investment advice, key/seed handling, a legal or tax conclusion, "
            "to speak as a real person or the Foundation, to cause harm, or to reach a human for a scam, bug, partnership, or press matter."
        )
        result = await llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=query[:500])])
        label = (getattr(result, "content", None) or str(result)).strip().lower().split()[0].strip(".,")
    except Exception as e:  # noqa: BLE001
        logger.debug("LLM safety fallback failed: %s", e)
        return None, None
    if label in REFUSE_TEMPLATES:
        return "refuse", label
    if label in ESCALATE_INTRO:
        return "escalate", label
    return None, None


async def decide(
    query: str,
    history_pairs: Optional[List[Tuple[str, str]]] = None,
    llm: Any = None,
    injection_detected: bool = False,
) -> SafetyDecision:
    """Full decision: refuse/escalate (regex, then optional LLM) plus audience label."""
    audience = classify_audience(query, history_pairs)

    if injection_detected:
        return SafetyDecision("refuse", "prompt_injection", audience, REFUSE_TEMPLATES["prompt_injection"])

    intent, category = classify_safety(query)
    if intent is None and os.getenv("USE_LLM_SAFETY_FALLBACK", "false").lower() == "true":
        intent, category = await classify_safety_llm(llm, query)

    if intent == "refuse" and category:
        return SafetyDecision("refuse", category, audience, REFUSE_TEMPLATES[category])
    if intent == "escalate" and category:
        return SafetyDecision("escalate", category, audience, build_escalate_answer(category))
    return SafetyDecision(None, None, audience, None)
