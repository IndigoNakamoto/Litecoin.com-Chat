import os
import asyncio
import time
import re
import logging
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import List, Tuple, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
try:
    from pydantic import BaseModel, Field
except ImportError:
    # Fallback for older pydantic versions
    from pydantic.v1 import BaseModel, Field
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from data_ingestion.vector_store_manager import VectorStoreManager
from cache_utils import query_cache, SemanticCache
from backend.utils.input_sanitizer import sanitize_query_input, detect_prompt_injection
from backend.utils.litecoin_vocabulary import normalize_ltc_keywords, expand_ltc_entities, LTC_ENTITY_EXPANSIONS
from fastapi import HTTPException
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import google.generativeai as genai
from backend.rag_graph.graph import build_rag_graph
from backend.rag_graph.nodes.factory import build_nodes

# --- Local RAG Feature Flags ---
# Enable local-first processing with cloud spillover
USE_LOCAL_REWRITER = os.getenv("USE_LOCAL_REWRITER", "false").lower() == "true"
USE_INFINITY_EMBEDDINGS = os.getenv("USE_INFINITY_EMBEDDINGS", "false").lower() == "true"
USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "false").lower() == "true"

# --- Advanced RAG Feature Flags ---
USE_INTENT_CLASSIFICATION = os.getenv("USE_INTENT_CLASSIFICATION", "true").lower() == "true"
USE_FAQ_INDEXING = os.getenv("USE_FAQ_INDEXING", "true").lower() == "true"

# --- Short-query semantic sparsity mitigations ---
# When enabled, very short queries (e.g. "MWEB", "supply") are expanded via the LLM
# before retrieval to increase semantic "surface area" for embeddings + retrieval.
USE_SHORT_QUERY_EXPANSION = os.getenv("USE_SHORT_QUERY_EXPANSION", "true").lower() == "true"
SHORT_QUERY_WORD_THRESHOLD = int(os.getenv("SHORT_QUERY_WORD_THRESHOLD", "4"))
SHORT_QUERY_EXPANSION_MAX_WORDS = int(os.getenv("SHORT_QUERY_EXPANSION_MAX_WORDS", "12"))
SHORT_QUERY_EXPANSION_CACHE_MAX = int(os.getenv("SHORT_QUERY_EXPANSION_CACHE_MAX", "512"))

# --- User-facing error messages (shared across modules) ---
GENERIC_USER_ERROR_MESSAGE = (
    "I encountered an error while processing your query. Please try again or rephrase your question."
)

# --- Conversation / history routing (Hybrid: Fast Path + LLM Router) ---
# Fast path: Only catch OBVIOUS cases to save latency
# LLM Router: Handle ambiguous cases with semantic understanding

# Strict list of pronouns that GUARANTEE history dependency
# Excludes ambiguous words like "IT" (Information Technology) to reduce false positives
_STRONG_AMBIGUOUS_TOKENS = {
    "it", "this", "that", "these", "those",
    "they", "them", "their", "its",
    "he", "she", "him", "her",
    "former", "latter", "previous", "following",
}

# Only prefixes that GUARANTEE a dependency on history
_STRONG_PREFIXES = (
    "and ", "also ", "but ", "so ",
    "what about", "how about", "why is that",
    "can you elaborate", "continue", "go on",
    "explain that", "expand on that",
)

# Structured output model for the semantic router (Canonical Intent Generator)
class QueryRouting(BaseModel):
    """Structured output for the canonical intent generator."""
    is_dependent: bool = Field(
        description="True if the query relies on history. Always True for pronouns/follow-ups."
    )
    standalone_query: str = Field(
        description=(
            "A rewritten standalone version of the user's latest query, resolving pronouns/ambiguous references "
            "using chat history while preserving the original topic and intent. "
            "If the latest query is already standalone, return it unchanged."
        )
    )

# Lazy-load local RAG services only when enabled
_inference_router = None
_infinity_embeddings = None
_redis_vector_cache = None
_intent_classifier = None
_suggested_question_cache = None

def _get_inference_router():
    """Lazy-load inference router for query rewriting."""
    global _inference_router
    if _inference_router is None and USE_LOCAL_REWRITER:
        try:
            from backend.services.router import InferenceRouter
            _inference_router = InferenceRouter()
            logging.getLogger(__name__).info("InferenceRouter initialized for local query rewriting")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to initialize InferenceRouter: {e}")
    return _inference_router

def _get_infinity_embeddings():
    """Lazy-load Infinity embeddings service."""
    global _infinity_embeddings
    if _infinity_embeddings is None and USE_INFINITY_EMBEDDINGS:
        try:
            from backend.services.infinity_adapter import InfinityEmbeddings
            _infinity_embeddings = InfinityEmbeddings()
            logging.getLogger(__name__).info("InfinityEmbeddings initialized for local 1024-dim embeddings")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to initialize InfinityEmbeddings: {e}")
    return _infinity_embeddings

def _get_redis_vector_cache():
    """Lazy-load Redis Stack vector cache."""
    global _redis_vector_cache
    if _redis_vector_cache is None and USE_REDIS_CACHE:
        try:
            from backend.services.redis_vector_cache import RedisVectorCache
            _redis_vector_cache = RedisVectorCache()
            logging.getLogger(__name__).info("RedisVectorCache initialized for semantic caching")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to initialize RedisVectorCache: {e}")
    return _redis_vector_cache

def _get_intent_classifier():
    """Lazy-load intent classifier for query routing."""
    global _intent_classifier
    if _intent_classifier is None and USE_INTENT_CLASSIFICATION:
        try:
            from backend.services.intent_classifier import IntentClassifier
            _intent_classifier = IntentClassifier()
            logging.getLogger(__name__).info("IntentClassifier initialized for query routing")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to initialize IntentClassifier: {e}")
    return _intent_classifier

def _get_suggested_question_cache():
    """Lazy-load suggested question cache."""
    global _suggested_question_cache
    if _suggested_question_cache is None:
        try:
            from backend.cache_utils import SuggestedQuestionCache
            _suggested_question_cache = SuggestedQuestionCache()
            logging.getLogger(__name__).info("SuggestedQuestionCache initialized")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to initialize SuggestedQuestionCache: {e}")
    return _suggested_question_cache

async def _load_faq_questions_for_intent_classifier():
    """Load FAQ questions from CMS and update intent classifier."""
    intent_classifier = _get_intent_classifier()
    if not intent_classifier:
        return
    
    try:
        from backend.utils.suggested_questions import fetch_suggested_questions
        questions = await fetch_suggested_questions(active_only=True)
        question_texts = [q.get("question", "") for q in questions if q.get("question")]
        intent_classifier.update_faq_questions(question_texts)
        logging.getLogger(__name__).info(f"Loaded {len(question_texts)} FAQ questions into IntentClassifier")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to load FAQ questions: {e}")

# --- Environment Variables (validated at runtime in RAGPipeline.__init__) ---
# NOTE: Do not raise at import-time; it breaks tooling/tests that import modules without runtime env.
google_api_key = os.getenv("GOOGLE_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# --- Logging ---
logger = logging.getLogger(__name__)

# Import monitoring metrics
try:
    from backend.monitoring.metrics import (
        rag_query_duration_seconds,
        rag_cache_hits_total,
        rag_cache_misses_total,
        rag_retrieval_duration_seconds,
        rag_documents_retrieved_total,
        llm_spend_limit_rejections_total,
        rag_query_rewrite_duration_seconds,
        rag_embedding_generation_duration_seconds,
        rag_vector_search_duration_seconds,
        rag_bm25_search_duration_seconds,
        rag_sparse_rerank_duration_seconds,
        rag_llm_generation_duration_seconds,
    )
    from backend.monitoring.llm_observability import track_llm_metrics, estimate_gemini_cost
    from backend.monitoring.spend_limit import check_spend_limit, record_spend
    MONITORING_ENABLED = True
except ImportError:
    # Monitoring not available, use no-op functions
    MONITORING_ENABLED = False
    def track_llm_metrics(*args, **kwargs):
        pass
    def estimate_gemini_cost(*args, **kwargs):
        return 0.0
    async def check_spend_limit(*args, **kwargs):
        return True, None, {}
    async def record_spend(*args, **kwargs):
        return {}

# --- Constants ---
DB_NAME = os.getenv("MONGO_DB_NAME", "litecoin_rag_db")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "litecoin_docs")
LLM_MODEL_NAME = "gemini-3.1-flash-lite-preview"  # 
# Maximum number of chat history pairs (human-AI exchanges) to include in context
# This prevents token overflow and keeps context manageable. Default: 4 pairs (8 messages)
MAX_CHAT_HISTORY_PAIRS = int(os.getenv("MAX_CHAT_HISTORY_PAIRS", "4"))
# Retriever k value (number of documents to retrieve)
# Increased from 8 to 14 for better context coverage (recommended in feature doc)
RETRIEVER_K = int(os.getenv("RETRIEVER_K", "14"))
# Limit for sparse re-ranking (only re-rank top N candidates to save time)
SPARSE_RERANK_LIMIT = int(os.getenv("SPARSE_RERANK_LIMIT", "14"))
COMPLEX_QUERY_RETRIEVER_BOOST = int(os.getenv("COMPLEX_QUERY_RETRIEVER_BOOST", "2"))
COMPLEX_QUERY_SPARSE_RERANK_BOOST = int(os.getenv("COMPLEX_QUERY_SPARSE_RERANK_BOOST", "2"))
NO_KB_MATCH_RESPONSE = (
    "I couldn't find any relevant content in our knowledge base yet. "
)

# Log feature flag status at module load
logger.info(
    f"Local RAG Features: rewriter={USE_LOCAL_REWRITER}, "
    f"infinity_embeddings={USE_INFINITY_EMBEDDINGS}, "
    f"redis_cache={USE_REDIS_CACHE}"
)

# --- RAG Prompt Templates ---
# 1. History-aware question rephrasing prompt
QA_WITH_HISTORY_PROMPT = ChatPromptTemplate.from_messages(
    [
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        ("human", "Given the above conversation, generate a standalone question that resolves pronouns or ambiguous references in the user's input. Use chat history ONLY to resolve ambiguity. If the user's input is already a complete standalone question or introduces a new topic, return it as-is and do not blend in prior topics. Do not add extra information or make assumptions beyond resolving ambiguity."),
    ]
)

# 2. System instruction for RAG prompt (defined separately for robustness)
SYSTEM_INSTRUCTION = """You are a neutral, factual Litecoin expert.

Rules:
- Answer only from the provided source text. If information is missing, say so clearly.
- Never mention internal retrieval mechanics (e.g., "context", "documents", "retrieved information").
- Use canonical terms: MWEB, LitVM, Charlie Lee (or Creator), Halving, Scrypt, Lightning.
- For multi-part/list/history questions, include all relevant items present in the source text.
- If asked for real-time prices/market data, state your knowledge is static and suggest a live source.

Response style:
- Start with a direct 1-2 sentence answer.
- Then use a `##` heading and concise bullet points for key details.
- Bold important Litecoin terms when natural.
"""

SYSTEM_INSTRUCTION_COMPLEX = SYSTEM_INSTRUCTION + """

For complex questions:
- Explain the reasoning chain explicitly and keep sections logically ordered.
- When comparing multiple concepts, use clear trade-offs and constraints.
- Prioritize completeness over brevity, but avoid repetition.
"""

# 3. RAG prompt for final answer generation with chat history support
RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_INSTRUCTION),
    ("system", "Context:\n{context}"),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

def format_docs(docs: List[Document]) -> str:
    """Helper function to format a list of documents into a single string."""
    return "\n\n".join(doc.page_content for doc in docs)


class RAGPipeline:
    """
    Simplified RAG Pipeline using FAISS with local embeddings and Google Flash 2.5 LLM.
    """

    # Process-level cache for BM25 doc corpus (MongoDB read is slow; corpus is small ~400 docs)
    _published_docs_cache: Dict[Tuple[str, str], List[Document]] = {}
    
    def __init__(self, vector_store_manager=None, db_name=None, collection_name=None):
        """
        Initializes the RAGPipeline.

        Args:
            vector_store_manager: An instance of VectorStoreManager. If provided, it's used.
                                  Otherwise, a new VectorStoreManager instance is created.
            db_name: Name of the database. Defaults to MONGO_DB_NAME env var or "litecoin_rag_db".
            collection_name: Name of the collection. Defaults to MONGO_COLLECTION_NAME env var or "litecoin_docs".
        """
        self.db_name = db_name or DB_NAME
        self.collection_name = collection_name or COLLECTION_NAME

        # Validate required environment variables at runtime (not import-time)
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set!")
        if not MONGO_URI and not vector_store_manager:
            # If a VectorStoreManager is injected, it may already be configured/mocked.
            raise ValueError("MONGO_URI environment variable not set!")
        
        if vector_store_manager:
            self.vector_store_manager = vector_store_manager
            logger.info(f"RAGPipeline using provided VectorStoreManager for collection: {vector_store_manager.collection_name}")
        else:
            # Initialize VectorStoreManager with local embeddings
            self.vector_store_manager = VectorStoreManager(
                db_name=self.db_name,
                collection_name=self.collection_name
            )
            logger.info(f"RAGPipeline initialized with VectorStoreManager for collection: {self.collection_name} (MongoDB: {'available' if self.vector_store_manager.mongodb_available else 'unavailable'})")
            logger.info(f"Chat history context limit: {MAX_CHAT_HISTORY_PAIRS} pairs (configure via MAX_CHAT_HISTORY_PAIRS env var)")

        # Initialize LLM with Gemini Flash-Lite
        self.llm = ChatGoogleGenerativeAI(
            model=LLM_MODEL_NAME, 
            temperature=0.2, 
            google_api_key=google_api_key,
            safety_settings={
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT:    HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,   # non-negotiable
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT:    HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,   # non-negotiable
                HarmCategory.HARM_CATEGORY_HATE_SPEECH:          HarmBlockThreshold.BLOCK_ONLY_HIGH,         # safe to loosen
                HarmCategory.HARM_CATEGORY_HARASSMENT:           HarmBlockThreshold.BLOCK_ONLY_HIGH,         # safe to loosen
            }
        )
        
        # Initialize local tokenizer for accurate token counting (faster than API calls)
        try:
            genai.configure(api_key=google_api_key)
            self.tokenizer_model = genai.GenerativeModel(LLM_MODEL_NAME)
            logger.info(f"Local tokenizer initialized for accurate token counting")
        except Exception as e:
            logger.warning(f"Failed to initialize local tokenizer: {e}. Will use fallback methods.")
            self.tokenizer_model = None

        # Setup hybrid retrievers (BM25 + semantic + history-aware)
        self._setup_retrievers()
        
        # Create document combining chains for simple/complex response profiles
        self.document_chain_simple = create_stuff_documents_chain(self.llm, RAG_PROMPT)
        complex_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_INSTRUCTION_COMPLEX),
            ("system", "Context:\n{context}"),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ])
        self.document_chain_complex = create_stuff_documents_chain(self.llm, complex_prompt)
        # Backward-compatible alias
        self.document_chain = self.document_chain_simple
        
        # Create full retrieval chain that passes chat_history to final generation
        self.rag_chain = create_retrieval_chain(
            self.history_aware_retriever,
            self.document_chain_simple
        )
        
        # Initialize semantic cache with the embedding model from VectorStoreManager
        # Skip legacy semantic cache when using Redis Stack cache (unified semantic cache provider)
        # This avoids redundant embedding calculations with different models
        if USE_REDIS_CACHE or USE_INFINITY_EMBEDDINGS:
            self.semantic_cache = None
            logger.info("Legacy semantic cache disabled (using Redis Stack vector cache as unified semantic cache provider)")
        else:
            self.semantic_cache = SemanticCache(
                embedding_model=self.vector_store_manager.embeddings,  # Reuse existing embedding model
                threshold=float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92")),
                max_size=int(os.getenv("SEMANTIC_CACHE_MAX_SIZE", "2000")),
                ttl_seconds=int(os.getenv("SEMANTIC_CACHE_TTL_SECONDS", str(3600 * 72)))  # 72 hours
            )
            logger.info(f"Legacy semantic cache initialized with threshold={self.semantic_cache.threshold}, TTL={self.semantic_cache.ttl_seconds}s")

        # --- Expose config + dependencies for LangGraph nodes (no module imports in nodes) ---
        self.query_cache = query_cache
        self.use_local_rewriter = USE_LOCAL_REWRITER
        self.use_infinity_embeddings = USE_INFINITY_EMBEDDINGS
        self.use_redis_cache = USE_REDIS_CACHE
        self.use_intent_classification = USE_INTENT_CLASSIFICATION
        self.use_faq_indexing = USE_FAQ_INDEXING
        self.use_short_query_expansion = USE_SHORT_QUERY_EXPANSION
        self.short_query_word_threshold = SHORT_QUERY_WORD_THRESHOLD
        self.short_query_expansion_max_words = SHORT_QUERY_EXPANSION_MAX_WORDS
        # Simple in-memory LRU for short-query expansions (keeps cost/latency bounded)
        # Stored as OrderedDict-like mapping in nodes; populated lazily.
        self.short_query_expansion_cache = None
        self.short_query_expansion_cache_max = SHORT_QUERY_EXPANSION_CACHE_MAX
        self.retriever_k = RETRIEVER_K
        self.sparse_rerank_limit = SPARSE_RERANK_LIMIT
        self.complex_query_retriever_boost = COMPLEX_QUERY_RETRIEVER_BOOST
        self.complex_query_sparse_rerank_boost = COMPLEX_QUERY_SPARSE_RERANK_BOOST
        self.model_name = LLM_MODEL_NAME
        self.generic_user_error_message = GENERIC_USER_ERROR_MESSAGE
        self.no_kb_match_response = NO_KB_MATCH_RESPONSE
        self.strong_ambiguous_tokens = _STRONG_AMBIGUOUS_TOKENS
        self.strong_prefixes = _STRONG_PREFIXES
        self.monitoring_enabled = MONITORING_ENABLED
        # Monitoring helpers (no-op when monitoring is disabled)
        self.track_llm_metrics = track_llm_metrics
        self.estimate_gemini_cost = estimate_gemini_cost
        self.check_spend_limit = check_spend_limit
        self.record_spend = record_spend

        # LangGraph compiled graph (lazy)
        self._rag_graph = None

    def _get_rag_graph(self):
        """Lazy-build and compile the LangGraph state machine."""
        if self._rag_graph is None:
            nodes = build_nodes(self)
            self._rag_graph = build_rag_graph(nodes)
        return self._rag_graph

    # --- LangGraph helper accessors (wrap existing lazy global getters) ---
    def get_infinity_embeddings(self):
        return _get_infinity_embeddings()

    def get_redis_vector_cache(self):
        return _get_redis_vector_cache()

    def get_intent_classifier(self):
        return _get_intent_classifier()

    def get_suggested_question_cache(self):
        return _get_suggested_question_cache()

    def _load_published_docs_from_mongo(self) -> List[Document]:
        """Safely load all published documents from MongoDB with fallback."""
        if not self.vector_store_manager.mongodb_available:
            logger.warning("MongoDB not available, skipping BM25 retriever setup")
            return []

        cache_key = (self.db_name, self.collection_name)
        cached = self.__class__._published_docs_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached published docs corpus for BM25: {len(cached)} docs")
            return cached
        
        try:
            cursor = self.vector_store_manager.collection.find(
                {"metadata.status": "published"},
                {"text": 1, "metadata": 1}
            ).limit(10000)  # Safety limit (you have ~400, so this is fine)
            
            docs = [
                Document(
                    page_content=doc["text"],
                    metadata=doc.get("metadata", {})
                )
                for doc in cursor
            ]
            logger.info(f"Loaded {len(docs)} published documents from MongoDB for hybrid retrieval")
            # Cache for future retriever refreshes
            self.__class__._published_docs_cache[cache_key] = docs
            return docs
        except Exception as e:
            logger.error(f"Failed to load documents from MongoDB for BM25: {e}", exc_info=True)
            return []

    def _load_parent_chunks_map(self) -> Dict[str, Document]:
        """
        Load parent chunks map from MongoDB for Parent Document Pattern resolution.
        
        Loads all non-synthetic documents (original chunks) and builds a map
        from chunk_id to Document. This map is used to swap synthetic question
        hits with their full-text parent chunks at retrieval time.
        
        Returns:
            Dict mapping chunk_id -> Document for all non-synthetic chunks
        """
        if not USE_FAQ_INDEXING:
            return {}
        
        if not self.vector_store_manager.mongodb_available:
            logger.warning("MongoDB not available, cannot load parent chunks map")
            return {}
        
        try:
            # Query for non-synthetic documents with chunk_id
            cursor = self.vector_store_manager.collection.find(
                {
                    "metadata.is_synthetic": {"$ne": True},
                    "metadata.chunk_id": {"$exists": True}
                },
                {"text": 1, "metadata": 1}
            ).limit(20000)  # Safety limit
            
            chunks_map: Dict[str, Document] = {}
            for doc in cursor:
                chunk_id = doc.get("metadata", {}).get("chunk_id")
                if chunk_id:
                    chunks_map[chunk_id] = Document(
                        page_content=doc.get("text", ""),
                        metadata=doc.get("metadata", {})
                    )
            
            logger.debug(f"Loaded {len(chunks_map)} parent chunks for FAQ resolution")
            return chunks_map
            
        except Exception as e:
            logger.error(f"Failed to load parent chunks map: {e}", exc_info=True)
            return {}

    def _setup_retrievers(self):
        """Setup hybrid retriever with proper document loading."""
        # 1. Load published docs from MongoDB
        all_published_docs = self._load_published_docs_from_mongo()

        # 2. Create BM25 retriever (only if we have docs)
        if all_published_docs:
            self.bm25_retriever = BM25Retriever.from_documents(
                all_published_docs,
                k=RETRIEVER_K
            )
            logger.info(f"BM25 retriever initialized with k={RETRIEVER_K}")
        else:
            self.bm25_retriever = None
            logger.warning("BM25 retriever disabled: no published documents loaded")

        # 3. Semantic retriever with filter
        search_kwargs = {"k": RETRIEVER_K}
        if self.vector_store_manager.mongodb_available:
            # Note: FAISS doesn't support metadata filtering directly, but we filter after retrieval
            pass
        
        self.semantic_retriever = self.vector_store_manager.get_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs
        )

        # 4. Hybrid retriever
        retrievers = [self.semantic_retriever]
        weights = [1.0]

        if self.bm25_retriever:
            retrievers.insert(0, self.bm25_retriever)
            weights = [0.5, 0.5]

        self.hybrid_retriever = EnsembleRetriever(
            retrievers=retrievers,
            weights=weights,
            search_type="similarity"
        )

        # 5. History-aware hybrid retriever (THIS FIXES TOPIC DRIFT)
        self.history_aware_retriever = create_history_aware_retriever(
            llm=self.llm,
            retriever=self.hybrid_retriever,
            prompt=QA_WITH_HISTORY_PROMPT
        )

        logger.info(f"Hybrid retriever ready | BM25: {'enabled' if self.bm25_retriever else 'disabled'} "
                    f"| Weights: {weights}")

    def _truncate_chat_history(self, chat_history: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        Truncates chat history to the configured maximum length, keeping the most recent exchanges.
        
        Args:
            chat_history: A list of (human_message, ai_message) tuples representing the conversation history.
            
        Returns:
            A truncated list containing at most MAX_CHAT_HISTORY_PAIRS exchanges, keeping the most recent ones.
        """
        if len(chat_history) <= MAX_CHAT_HISTORY_PAIRS:
            return chat_history
        
        # Keep only the most recent N pairs
        truncated = chat_history[-MAX_CHAT_HISTORY_PAIRS:]
        logger.warning(f"Chat history truncated from {len(chat_history)} to {len(truncated)} pairs (max: {MAX_CHAT_HISTORY_PAIRS})")
        return truncated

    def _detect_canonical_entities(self, text: str) -> List[str]:
        """
        Detect canonical Litecoin entities (e.g. 'litvm', 'mweb') in text.

        We normalize first so phrases like "Litecoin Virtual Machine" become "litvm".
        """
        if not text:
            return []
        normalized = normalize_ltc_keywords(text)
        haystack = normalized.lower()
        found: List[str] = []
        # Prefer longer entity keys first to avoid partial/shorter matches winning.
        for entity in sorted(LTC_ENTITY_EXPANSIONS.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(entity)}\b", haystack):
                found.append(entity)
        return found

    def _anchor_pronouns_to_last_entity(self, query: str, chat_history_pairs: List[Tuple[str, str]]) -> str:
        """
        Deterministically resolve 'it/this/that/they' style follow-ups to the last explicit entity.

        This is a safety net to prevent LLM-based rewrite from drifting to a different well-known topic
        (e.g., switching from LitVM to MWEB) when the user asks a follow-up like "who's working on it?".
        """
        if not query or not chat_history_pairs:
            return query

        # Only act if the current query contains obvious pronouns/follow-up markers.
        tokens = re.findall(r"[a-z0-9']+", query.lower())
        if not any(t in _STRONG_AMBIGUOUS_TOKENS for t in tokens):
            return query

        # If the query already names an entity, do nothing.
        if self._detect_canonical_entities(query):
            return query

        # Scan backwards through recent human turns to find the most recent named entity.
        last_entity: Optional[str] = None
        for human_msg, _ in reversed(chat_history_pairs):
            entities = self._detect_canonical_entities(human_msg or "")
            if entities:
                last_entity = entities[0]
                break

        if not last_entity:
            return query

        rewritten = query
        # Prefer direct replacements when grammar is clear.
        rewritten = re.sub(r"\bits\b", f"{last_entity}'s", rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bit\b", last_entity, rewritten, flags=re.IGNORECASE)

        # If we didn't actually replace anything (e.g., "can you elaborate?"), append an anchor.
        if rewritten == query:
            rewritten = f"{query} about {last_entity}"

        return rewritten

    def _build_prompt_text(
        self,
        query_text: str,
        context_text: str,
        system_instruction: str = SYSTEM_INSTRUCTION,
    ) -> str:
        """Reconstruct the prompt text fed to the LLM for token accounting."""
        # Build prompt text from the new RAG_PROMPT template structure
        return f"{system_instruction}\n\nContext:\n{context_text}\n\nUser: {query_text}"
    
    def _build_prompt_text_with_history(
        self,
        query_text: str,
        context_text: str,
        chat_history: List[BaseMessage],
        system_instruction: str = SYSTEM_INSTRUCTION,
    ) -> str:
        """Reconstruct the prompt text with chat history for token accounting."""
        # Format history as string for token counting
        history_text = ""
        for msg in chat_history:
            if isinstance(msg, HumanMessage):
                history_text += f"User: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                history_text += f"Assistant: {msg.content}\n"
        
        # Build prompt text from the new RAG_PROMPT template structure
        return f"{system_instruction}\n\nContext:\n{context_text}\n\n{history_text}User: {query_text}"

    def _select_document_chain(self, state: Dict[str, Any]):
        """Choose generation chain/profile based on routed complexity."""
        complexity_route = str(state.get("complexity_route") or "simple").lower()
        if complexity_route == "complex":
            return self.document_chain_complex, "complex", SYSTEM_INSTRUCTION_COMPLEX
        return self.document_chain_simple, "simple", SYSTEM_INSTRUCTION

    def _estimate_token_usage(self, prompt_text: str, answer_text: str) -> Tuple[int, int]:
        """
        Estimate (input_tokens, output_tokens) for an LLM call.

        Uses the local Gemini tokenizer (fast and 100% accurate) as the primary method,
        with fallbacks to LangChain's get_num_tokens and word-count estimation.
        """
        prompt_text = prompt_text or ""
        answer_text = answer_text or ""

        # Initialize with word-count fallback (least accurate, but always available)
        fallback_input_tokens = max(int(len(prompt_text.split()) * 1.3), 0)
        fallback_output_tokens = max(int(len(answer_text.split()) * 1.3), 0)

        input_tokens = fallback_input_tokens
        output_tokens = fallback_output_tokens

        # Primary method: Use local tokenizer (fastest and most accurate)
        if hasattr(self, 'tokenizer_model') and self.tokenizer_model is not None:
            try:
                input_tokens = max(self.tokenizer_model.count_tokens(prompt_text).total_tokens, 0)
            except Exception as exc:
                logger.debug("Failed to count input tokens via local tokenizer: %s", exc, exc_info=True)
            try:
                output_tokens = max(self.tokenizer_model.count_tokens(answer_text).total_tokens, 0)
            except Exception as exc:
                logger.debug("Failed to count output tokens via local tokenizer: %s", exc, exc_info=True)
        
        # Fallback: Use LangChain's get_num_tokens if local tokenizer failed
        if input_tokens == fallback_input_tokens and hasattr(self.llm, "get_num_tokens"):
            try:
                input_tokens = max(int(self.llm.get_num_tokens(prompt_text)), 0)
            except Exception as exc:
                logger.debug("Failed to count input tokens via LangChain: %s", exc, exc_info=True)
        if output_tokens == fallback_output_tokens and hasattr(self.llm, "get_num_tokens"):
            try:
                output_tokens = max(int(self.llm.get_num_tokens(answer_text)), 0)
            except Exception as exc:
                logger.debug("Failed to count output tokens via LangChain: %s", exc, exc_info=True)

        return input_tokens, output_tokens

    def _extract_token_usage_from_chain_result(self, result: Dict[str, Any]) -> Tuple[int, int]:
        """
        Extract actual token counts from LangChain chain result.
        
        The rag_chain returns a dict with "answer" that contains an AIMessage object
        which should have response_metadata with token usage information.
        
        Args:
            result: The result dict from rag_chain.invoke() or async_rag_chain.ainvoke()
        
        Returns:
            Tuple of (input_tokens, output_tokens) or (0, 0) if not available
        """
        input_tokens = 0
        output_tokens = 0
        
        try:
            answer = result.get("answer")
            if answer is None:
                return 0, 0
            
            # Check if answer is an AIMessage with response_metadata
            if hasattr(answer, 'response_metadata'):
                metadata = answer.response_metadata
                if metadata:
                    # LangChain format: response_metadata may contain token_usage
                    if 'token_usage' in metadata:
                        usage = metadata['token_usage']
                        input_tokens = usage.get('prompt_tokens', 0)
                        output_tokens = usage.get('completion_tokens', 0)
                    
                    # Also check for usage_metadata (direct Gemini API format)
                    if 'usage_metadata' in metadata:
                        usage = metadata['usage_metadata']
                        if hasattr(usage, 'prompt_token_count'):
                            input_tokens = getattr(usage, 'prompt_token_count', 0)
                        if hasattr(usage, 'candidates_token_count'):
                            output_tokens = getattr(usage, 'candidates_token_count', 0)
                
                # Check for direct usage_metadata attribute (Gemini response object)
                if hasattr(answer, 'usage_metadata'):
                    usage = answer.usage_metadata
                    input_tokens = getattr(usage, 'prompt_token_count', 0)
                    output_tokens = getattr(usage, 'candidates_token_count', 0)
        except Exception as e:
            logger.debug(f"Could not extract token usage from chain result: {e}", exc_info=True)
        
        return input_tokens, output_tokens

    def _extract_token_usage_from_llm_response(self, response: Any) -> Tuple[int, int]:
        """
        Extract actual token counts from LangChain LLM response (AIMessage).
        
        Args:
            response: The AIMessage response from LLM
        
        Returns:
            Tuple of (input_tokens, output_tokens) or (0, 0) if not available
        """
        input_tokens = 0
        output_tokens = 0
        
        try:
            if hasattr(response, 'response_metadata'):
                metadata = response.response_metadata
                if metadata:
                    # LangChain format
                    if 'token_usage' in metadata:
                        usage = metadata['token_usage']
                        input_tokens = usage.get('prompt_tokens', 0)
                        output_tokens = usage.get('completion_tokens', 0)
                    
                    # Gemini API format
                    if 'usage_metadata' in metadata:
                        usage = metadata['usage_metadata']
                        if hasattr(usage, 'prompt_token_count'):
                            input_tokens = getattr(usage, 'prompt_token_count', 0)
                        if hasattr(usage, 'candidates_token_count'):
                            output_tokens = getattr(usage, 'candidates_token_count', 0)
            
            # Direct usage_metadata attribute
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                input_tokens = getattr(usage, 'prompt_token_count', 0)
                output_tokens = getattr(usage, 'candidates_token_count', 0)
        except Exception as e:
            logger.debug(f"Could not extract token usage from LLM response: {e}", exc_info=True)
        
        return input_tokens, output_tokens

    def refresh_vector_store(self):
        """
        Refreshes the vector store by reloading from disk and recreating the RAG chain.
        This should be called after new documents are added to ensure queries use the latest content.
        
        NOTE: This does NOT rebuild from MongoDB - it only reloads the FAISS index from disk.
        The add_documents() method already saves to disk after adding, so this just picks up
        those changes. For a full rebuild from MongoDB, use vector_store_manager._create_faiss_from_mongodb().
        """
        try:
            logger.info("Refreshing vector store and hybrid retrievers...")

            # Invalidate BM25 corpus cache so changes in MongoDB are reflected
            try:
                cache_key = (self.db_name, self.collection_name)
                self.__class__._published_docs_cache.pop(cache_key, None)
            except Exception:
                pass

            # Reload the vector store from disk (fast - no rebuild!)
            if hasattr(self, 'vector_store_manager') and self.vector_store_manager:
                if self.vector_store_manager.reload_from_disk():
                    logger.info("Vector store reloaded from disk")
                else:
                    logger.warning("Failed to reload from disk, vector store unchanged")

            # RECREATE ALL RETRIEVERS (this is the critical fix!)
            self._setup_retrievers()
            
            # Rebuild the document chain and retrieval chain (in case LLM changed, though unlikely)
            document_chain = create_stuff_documents_chain(self.llm, RAG_PROMPT)
            complex_prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_INSTRUCTION_COMPLEX),
                ("system", "Context:\n{context}"),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ])
            self.document_chain_simple = document_chain
            self.document_chain_complex = create_stuff_documents_chain(self.llm, complex_prompt)
            self.document_chain = self.document_chain_simple
            self.rag_chain = create_retrieval_chain(
                self.history_aware_retriever,
                self.document_chain_simple
            )
            
            logger.info("Vector store and hybrid retrievers refreshed")

        except Exception as e:
            logger.error(f"Error refreshing vector store: {e}", exc_info=True)

    async def _semantic_history_check(self, query_text: str, chat_history: List[BaseMessage]) -> Tuple[str, bool]:
        """
        Uses the LLM to determine if history is needed and rewrite the query if dependent.
        
        Returns:
            Tuple of (rewritten_query, is_dependent)
            - rewritten_query: The fully contextualized query if dependent, or original if standalone
            - is_dependent: True if the query relies on chat history
        """
        if not chat_history:
            return query_text, False

        system_prompt = """You are a query router for a RAG system about Litecoin.
Analyze the "Latest Query". Does it refer to the "Chat History" (e.g. via pronouns like 'it', 'that', or implicit context)?

Output MUST conform to the provided schema with:
- is_dependent: boolean
- standalone_query: string

Rules:
1) If YES (Dependent): rewrite the Latest Query into a fully standalone question by resolving ONLY the ambiguous references using Chat History.
2) If NO (Standalone): return the Latest Query exactly as-is.
3) Do NOT output a "canonical intent" keyword pair. Preserve the user's natural question phrasing.
4) Do NOT switch topics. Only resolve references; keep the subject from history (e.g., if the prior turn was about LitVM, resolve "it" to LitVM).
5) Do NOT add new facts or assumptions beyond resolving what "it/this/that" refers to.

Be conservative: only mark as dependent if the query is clearly referring to prior conversation."""

        router_prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "Chat History:\n{chat_history}\n\nLatest Query: {query}"),
        ])
        
        # Format history string (prefer prior *human* turns; avoid tangents in assistant replies)
        human_msgs = [m.content for m in chat_history if isinstance(m, HumanMessage) and m.content]
        history_str = "\n".join([f"Human: {c}" for c in human_msgs[-2:]])

        start_time = time.time()
        
        # Use structured output for reliability
        try:
            structured_llm = self.llm.with_structured_output(QueryRouting)
            router_chain = router_prompt | structured_llm

            result = await router_chain.ainvoke({"chat_history": history_str, "query": query_text})
            duration = time.time() - start_time
            
            standalone_query = (result.standalone_query or "").strip()
            if not standalone_query:
                # Safety fallback: never return an empty rewrite.
                standalone_query = query_text
            
            # --- 1. ESTIMATE TOKENS (The Router result object usually doesn't have usage metadata) ---
            # Reconstruct the prompt string roughly for estimation
            prompt_text = f"{system_prompt}\nChat History:\n{history_str}\n\nLatest Query: {query_text}"
            
            # Result is a Pydantic object, convert to string for token counting
            try:
                # Try Pydantic v2 method first
                if hasattr(result, 'model_dump_json'):
                    output_text = result.model_dump_json()
                elif hasattr(result, 'model_dump'):
                    import json
                    output_text = json.dumps(result.model_dump())
                elif hasattr(result, 'dict'):
                    output_text = str(result.dict())
                else:
                    output_text = str(result)
            except Exception:
                output_text = str(result)
            
            input_tokens, output_tokens = self._estimate_token_usage(prompt_text, output_text)
            
            # --- 2. CALCULATE COST ---
            cost = estimate_gemini_cost(input_tokens, output_tokens, LLM_MODEL_NAME)
            
            # --- 3. TRACK METRICS ---
            if MONITORING_ENABLED:
                track_llm_metrics(
                    model=LLM_MODEL_NAME,
                    operation="router_classify",  # Use a distinct operation name
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    duration_seconds=duration,
                    status="success"
                )
                # Record spend against limits
                try:
                    await record_spend(cost, input_tokens, output_tokens, LLM_MODEL_NAME)
                except Exception as e:
                    logger.warning(f"Failed to record router spend: {e}")
            
            logger.info(f"🎯 Standalone query: '{query_text}' -> '{standalone_query}' (dependent={result.is_dependent})")
            return standalone_query, result.is_dependent
                
        except Exception as e:
            # Log failure metrics
            duration = time.time() - start_time
            if MONITORING_ENABLED:
                track_llm_metrics(
                    model=LLM_MODEL_NAME,
                    operation="router_classify",
                    duration_seconds=duration,
                    status="error"
                )
            logger.warning(f"Standardizer failed: {e}")
            return query_text, False

    async def aquery(self, query_text: str, chat_history: List[Tuple[str, str]]) -> Tuple[str, List[Document], Dict[str, Any]]:
        """Async query endpoint (non-stream). LangGraph handles routing/caching/retrieval; this handles generation + cache write-back."""
        start_time = time.time()
        try:
            graph = self._get_rag_graph()
            state = await graph.ainvoke({"raw_query": query_text, "chat_history_pairs": chat_history, "metadata": {}})
            metadata: Dict[str, Any] = state.get("metadata") or {}

            # Early return (intent/static or cache hits)
            if state.get("early_answer") is not None:
                metadata.setdefault("duration_seconds", time.time() - start_time)
                return state.get("early_answer") or "", state.get("early_sources") or [], metadata

            context_docs: List[Document] = state.get("context_docs") or []
            published_sources: List[Document] = state.get("published_sources") or []
            retrieval_failed = bool(state.get("retrieval_failed", False))

            if not published_sources:
                metadata.update(
                    {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "duration_seconds": time.time() - start_time,
                        "cache_hit": False,
                        "cache_type": None,
                    }
                )
                response_message = self.generic_user_error_message if retrieval_failed else self.no_kb_match_response
                logger.info(
                    "RAG returning early (no published_sources): retrieval_failed=%s, context_docs_count=%s, reason=%s",
                    retrieval_failed,
                    len(context_docs),
                    "generic_error" if retrieval_failed else "no_kb_match",
                )
                return response_message, [], metadata

            converted_history: List[BaseMessage] = state.get("converted_history_messages") or []
            sanitized_query = state.get("sanitized_query") or query_text
            active_chain, response_profile, active_instruction = self._select_document_chain(state)
            metadata["response_profile"] = response_profile

            llm_start = time.time()
            answer_result = await active_chain.ainvoke(
                {"input": sanitized_query, "context": context_docs, "chat_history": converted_history}
            )
            answer = answer_result.content if hasattr(answer_result, "content") else str(answer_result)
            llm_duration = time.time() - llm_start

            # Token usage + cost
            input_tokens, output_tokens = 0, 0
            cost_usd = 0.0
            if self.monitoring_enabled:
                input_tokens, output_tokens = self._extract_token_usage_from_llm_response(answer_result)
                if input_tokens == 0 and output_tokens == 0:
                    context_text = "\n\n".join(d.page_content for d in context_docs)
                    prompt_text = self._build_prompt_text_with_history(
                        sanitized_query,
                        context_text,
                        converted_history,
                        system_instruction=active_instruction,
                    )
                    input_tokens, output_tokens = self._estimate_token_usage(prompt_text, answer)
                cost_usd = self.estimate_gemini_cost(input_tokens, output_tokens, self.model_name)
                self.track_llm_metrics(
                    model=self.model_name,
                    operation="generate",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    duration_seconds=llm_duration,
                    status="success",
                )
                try:
                    await self.record_spend(cost_usd, input_tokens, output_tokens, self.model_name)
                except Exception as e:
                    logger.warning("Error recording spend: %s", e, exc_info=True)

            # Cache write-back
            effective_history = state.get("effective_history_pairs") or []
            self.query_cache.set(query_text, effective_history, answer, published_sources)

            query_vector = state.get("query_vector")
            rewritten_query = state.get("rewritten_query_for_cache") or state.get("rewritten_query") or ""
            if self.use_redis_cache and query_vector:
                redis_cache = self.get_redis_vector_cache()
                if redis_cache:
                    try:
                        sources_data = [{"page_content": d.page_content, "metadata": d.metadata} for d in published_sources]
                        await redis_cache.set(query_vector, rewritten_query, answer, sources_data)
                    except Exception as e:
                        logger.warning("Redis cache storage failed: %s", e)
            if self.semantic_cache and not self.use_redis_cache:
                self.semantic_cache.set(rewritten_query, [], answer, published_sources)

            metadata.update(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost_usd,
                    "duration_seconds": time.time() - start_time,
                    "cache_hit": False,
                    "cache_type": None,
                    "rewritten_query": rewritten_query if rewritten_query and rewritten_query != query_text else None,
                    "response_profile": response_profile,
                    "complexity_route": state.get("complexity_route"),
                }
            )
            return answer, published_sources, metadata
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error during async RAG query execution: %s", e, exc_info=True)
            metadata = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "duration_seconds": time.time() - start_time,
                "cache_hit": False,
                "cache_type": None,
            }
            return self.generic_user_error_message, [], metadata

    async def astream_query(self, query_text: str, chat_history: List[Tuple[str, str]]):
        """
        Streaming version of aquery that yields response chunks progressively.

        Args:
            query_text: The user's current query.
            chat_history: A list of (human_message, ai_message) tuples representing the conversation history.

        Yields:
            Dict with streaming data: {"type": "chunk", "content": "..."} or {"type": "sources", "sources": [...]} or {"type": "complete"}
        """
        start_time = time.time()
        try:
            graph = self._get_rag_graph()
            state = await graph.ainvoke({"raw_query": query_text, "chat_history_pairs": chat_history, "metadata": {}})
            metadata: Dict[str, Any] = state.get("metadata") or {}

            # Early returns (intent/static or cache hits)
            if state.get("early_answer") is not None:
                sources = state.get("early_sources") or []
                yield {"type": "sources", "sources": sources}
                answer_text = state.get("early_answer") or ""
                for i, char in enumerate(answer_text):
                    yield {"type": "chunk", "content": char}
                    if i % 10 == 0:
                        await asyncio.sleep(0.001)
                metadata.setdefault("duration_seconds", time.time() - start_time)
                yield {"type": "metadata", "metadata": metadata}
                yield {"type": "complete", "from_cache": True}
                return

            context_docs: List[Document] = state.get("context_docs") or []
            published_sources: List[Document] = state.get("published_sources") or []
            retrieval_failed = bool(state.get("retrieval_failed", False))

            if not published_sources:
                yield {"type": "sources", "sources": []}
                response_message = self.generic_user_error_message if retrieval_failed else self.no_kb_match_response
                yield {"type": "chunk", "content": response_message}
                metadata.update(
                    {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "duration_seconds": time.time() - start_time,
                        "cache_hit": False,
                        "cache_type": None,
                    }
                )
                yield {"type": "metadata", "metadata": metadata}
                yield {"type": "complete", "from_cache": False, "no_kb_results": True}
                return

            # Send sources immediately (low-latency UX)
            yield {"type": "sources", "sources": published_sources}

            converted_history: List[BaseMessage] = state.get("converted_history_messages") or []
            sanitized_query = state.get("sanitized_query") or query_text
            active_chain, response_profile, active_instruction = self._select_document_chain(state)
            metadata["response_profile"] = response_profile

            llm_start = time.time()
            full_answer = ""
            answer_obj = None
            async for chunk in active_chain.astream(
                {"input": sanitized_query, "context": context_docs, "chat_history": converted_history}
            ):
                content = ""
                if hasattr(chunk, "content"):
                    answer_obj = chunk
                    content = chunk.content
                elif isinstance(chunk, str):
                    content = chunk
                if content:
                    full_answer += content
                    yield {"type": "chunk", "content": content}

            llm_duration = time.time() - llm_start
            total_duration = time.time() - start_time

            input_tokens, output_tokens = 0, 0
            cost_usd = 0.0
            if self.monitoring_enabled:
                if answer_obj:
                    input_tokens, output_tokens = self._extract_token_usage_from_llm_response(answer_obj)
                if input_tokens == 0 and output_tokens == 0:
                    context_text = "\n\n".join(d.page_content for d in context_docs)
                    prompt_text = self._build_prompt_text_with_history(
                        sanitized_query,
                        context_text,
                        converted_history,
                        system_instruction=active_instruction,
                    )
                    input_tokens, output_tokens = self._estimate_token_usage(prompt_text, full_answer)
                cost_usd = self.estimate_gemini_cost(input_tokens, output_tokens, self.model_name)
                self.track_llm_metrics(
                    model=self.model_name,
                    operation="generate",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    duration_seconds=llm_duration,
                    status="success",
                )
                try:
                    await self.record_spend(cost_usd, input_tokens, output_tokens, self.model_name)
                except Exception as e:
                    logger.warning("Error recording spend: %s", e, exc_info=True)

            # Cache write-back
            effective_history = state.get("effective_history_pairs") or []
            self.query_cache.set(query_text, effective_history, full_answer, published_sources)

            query_vector = state.get("query_vector")
            rewritten_query = state.get("rewritten_query_for_cache") or state.get("rewritten_query") or ""
            if self.use_redis_cache and query_vector:
                redis_cache = self.get_redis_vector_cache()
                if redis_cache:
                    try:
                        sources_data = [{"page_content": d.page_content, "metadata": d.metadata} for d in published_sources]
                        await redis_cache.set(query_vector, rewritten_query, full_answer, sources_data)
                    except Exception as e:
                        logger.warning("Redis cache storage failed in stream: %s", e)
            if self.semantic_cache and not self.use_redis_cache:
                self.semantic_cache.set(rewritten_query, [], full_answer, published_sources)

            metadata.update(
                {
                    "input_tokens": input_tokens if self.monitoring_enabled else 0,
                    "output_tokens": output_tokens if self.monitoring_enabled else 0,
                    "cost_usd": cost_usd if self.monitoring_enabled else 0.0,
                    "duration_seconds": total_duration,
                    "cache_hit": False,
                    "cache_type": None,
                    "response_profile": response_profile,
                    "complexity_route": state.get("complexity_route"),
                }
            )
            yield {"type": "metadata", "metadata": metadata}
            yield {"type": "complete", "from_cache": False}
        except HTTPException as he:
            # Preserve previous streaming behavior: emit an error event instead of raising.
            if getattr(he, "status_code", None) == 429:
                detail = getattr(he, "detail", {}) or {}
                message = detail.get("message") or "We've reached our daily usage limit. Please try again later."
                yield {"type": "error", "error": message}
                yield {"type": "complete", "error": True}
                return
            raise
        except Exception as e:
            logger.error("Error during streaming RAG query execution: %s", e, exc_info=True)
            metadata = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "duration_seconds": time.time() - start_time,
                "cache_hit": False,
                "cache_type": None,
            }
            yield {"type": "metadata", "metadata": metadata}
            yield {"type": "error", "error": "An error occurred while processing your query. Please try again or rephrase your question."}


# Example of how to use the RAGPipeline class (for testing or direct script use)
if __name__ == "__main__":
    # This ensures .env is loaded if running this script directly
    from dotenv import load_dotenv
    dotenv_path_actual = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(dotenv_path_actual):
        print(f"RAGPipeline direct run: Loading .env from {dotenv_path_actual}")
        load_dotenv(dotenv_path=dotenv_path_actual, override=True)
    else:
        print("RAGPipeline direct run: .env file not found. Ensure GOOGLE_API_KEY and MONGO_URI are set.")

    async def main():
        print("Testing RAGPipeline class with local embeddings and Google Flash 2.5...")
        try:
            pipeline = RAGPipeline()  # Uses default collection

            # Test 1: Initial query
            initial_query = "What is Litecoin?"
            print(f"\nQuerying pipeline with: '{initial_query}' (initial query)")
            answer, sources, metadata = await pipeline.aquery(initial_query, chat_history=[])
            print("\n--- Answer (Initial Query) ---")
            print(answer)
            print("\n--- Sources (Initial Query) ---")
            if sources:
                for i, doc in enumerate(sources):
                    print(f"Source {i+1}: {doc.page_content[:150]}... (Metadata: {doc.metadata.get('title', 'N/A')})")
            else:
                print("No sources retrieved.")

            # Test 2: Follow-up query with history
            follow_up_query = "Who created it?"
            simulated_history = [
                ("What is Litecoin?", "Litecoin is a peer-to-peer cryptocurrency and open-source software project released under the MIT/X11 license. It was inspired by Bitcoin but designed to have a faster block generation rate and use a different hashing algorithm.")
            ]
            print(f"\nQuerying pipeline with: '{follow_up_query}' (follow-up query)")
            answer, sources, metadata = await pipeline.aquery(follow_up_query, chat_history=simulated_history)
            
            print("\n--- Answer (Follow-up Query) ---")
            print(answer)
            print("\n--- Sources (Follow-up Query) ---")
            if sources:
                for i, doc in enumerate(sources):
                    print(f"Source {i+1}: {doc.page_content[:150]}... (Metadata: {doc.metadata.get('title', 'N/A')})")
            else:
                print("No sources retrieved.")
                
        except ValueError as ve:
            print(f"Initialization Error: {ve}")
        except Exception as e:
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
    
    # Run the async main function
    asyncio.run(main())
