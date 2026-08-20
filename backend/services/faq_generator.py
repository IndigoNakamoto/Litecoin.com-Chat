"""
FAQ Generator Service (Parent Document Pattern)

Generates synthetic questions for document chunks. The questions are
indexed for search, but retrieval returns the FULL parent chunk.

Key Insight: Decouple what you SEARCH from what you RETURN.
- Search: Synthetic questions (semantic match to user queries)
- Return: Original chunks (full context for LLM)

This addresses the "semantic distance" problem where user questions
don't match document statements well in vector space.

Example:
- User asks: "How much do LTC devs make?"
- Document contains: "The developer salary is 80k"
- Synthetic question: "What is the developer salary?"
- Result: Question matches question with high similarity

LLM Backend Options:
- "gemini": Use Google Gemini API (requires GOOGLE_API_KEY)
- "local": Use local Ollama (requires OLLAMA_URL, default localhost:11434)

Usage:
    # Use Gemini (default)
    FAQ_LLM_BACKEND=gemini python scripts/reindex_with_faq.py
    
    # Use local Ollama (no rate limits!)
    FAQ_LLM_BACKEND=local python scripts/reindex_with_faq.py
"""

import os
import logging
import hashlib
import asyncio
from typing import List, Dict, Tuple, Optional, Set
from langchain_core.documents import Document
import httpx

logger = logging.getLogger(__name__)

# Feature flag for FAQ indexing
USE_FAQ_INDEXING = os.getenv("USE_FAQ_INDEXING", "true").lower() == "true"
FAQ_QUESTIONS_PER_CHUNK = int(os.getenv("FAQ_QUESTIONS_PER_CHUNK", "3"))
# Rate limiting for LLM calls (seconds between calls, 0 = no limit)
# Default 2s for Gemini (30 RPM limit), 0 for local (no limit)
FAQ_LLM_RATE_LIMIT_DELAY = float(os.getenv("FAQ_LLM_RATE_LIMIT_DELAY", "2.0"))
# LLM backend: "gemini" or "local"
FAQ_LLM_BACKEND = os.getenv("FAQ_LLM_BACKEND", "gemini").lower()
# Local LLM settings (Ollama)
FAQ_OLLAMA_URL = os.getenv("FAQ_OLLAMA_URL", os.getenv("OLLAMA_URL", "http://host.docker.internal:11434"))
FAQ_OLLAMA_MODEL = os.getenv("FAQ_OLLAMA_MODEL", os.getenv("LOCAL_REWRITER_MODEL", "llama3.2:3b"))


class FAQGenerator:
    """
    Generates synthetic questions using Parent Document Pattern.
    
    Questions are stored with is_synthetic=True and parent_chunk_id
    pointing to the original chunk. NO content is stored in the
    question document - only the question text for embedding.
    
    CRITICAL for Payload CMS CRUD lifecycle:
    - Synthetic questions INHERIT payload_id from parent chunk
    - This ensures deletion by payload_id removes both parent AND synthetic questions
    
    Supports two LLM backends:
    - "gemini": Google Gemini API (rate limited, requires API key)
    - "local": Local Ollama (no rate limits, runs on your machine)
    """
    
    GENERATION_PROMPT = """You are a question generator for a Litecoin knowledge base.
Given the following content, generate {num_questions} natural questions that this content directly answers.

Rules:
1. Questions should be phrased as a user would naturally ask them
2. Questions should be answerable ONLY from the provided content
3. Vary question styles (what, how, why, can, does, etc.)
4. Include vocabulary variations users might use
5. Output ONLY the questions, one per line, each ending with a question mark
6. Do NOT number the questions or add any other text

Content:
{content}

Questions:"""

    def __init__(self, llm=None, num_questions: int = None, backend: str = None):
        """
        Initialize FAQ Generator.
        
        Args:
            llm: LangChain LLM instance. If None, auto-selects based on backend.
            num_questions: Number of questions to generate per chunk (default: FAQ_QUESTIONS_PER_CHUNK)
            backend: "gemini" or "local" (default: FAQ_LLM_BACKEND env var)
        """
        self.num_questions = num_questions or FAQ_QUESTIONS_PER_CHUNK
        self.backend = backend or FAQ_LLM_BACKEND
        self._llm = llm
        self._use_local = self.backend == "local"
        
        # Auto-disable rate limiting for local LLM (no API limits)
        self._rate_limit = FAQ_LLM_RATE_LIMIT_DELAY if not self._use_local else 0.0
        
        logger.info(
            f"FAQGenerator initialized: backend={self.backend}, "
            f"questions_per_chunk={self.num_questions}, "
            f"rate_limit={self._rate_limit}s"
        )
    
    @property
    def llm(self):
        """Lazy-load LLM to avoid import issues at module level."""
        if self._llm is None:
            if self._use_local:
                self._llm = "local"  # Special marker for local backend
            else:
                self._llm = self._get_gemini_llm()
        return self._llm
    
    def _get_gemini_llm(self):
        """Get Gemini LLM for question generation."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                logger.warning("GOOGLE_API_KEY not set, FAQ generation will fail")
                return None
            
            return ChatGoogleGenerativeAI(
                model="gemini-3.1-flash-lite-preview",  # Cheap for batch ingestion
                temperature=0.3,
                google_api_key=google_api_key
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM: {e}")
            return None
    
    async def _call_local_llm(self, prompt: str) -> Optional[str]:
        """
        Call local Ollama LLM for question generation.
        
        Args:
            prompt: The prompt to send to the LLM
            
        Returns:
            Generated text or None on error
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{FAQ_OLLAMA_URL}/api/generate",
                    json={
                        "model": FAQ_OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 300,  # ~100 tokens per question × 3
                        },
                    },
                )
                response.raise_for_status()
                
                data = response.json()
                return data.get("response", "").strip()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama API error: {e.response.status_code}")
                return None
            except httpx.RequestError as e:
                logger.error(f"Ollama connection error: {e}")
                return None
            except Exception as e:
                logger.error(f"Ollama error: {e}")
                return None
    
    async def health_check(self) -> bool:
        """
        Check if the LLM backend is healthy and ready.
        
        Returns:
            True if healthy, False otherwise
        """
        if self._use_local:
            return await self._check_ollama_health()
        else:
            return self._check_gemini_health()
    
    async def _check_ollama_health(self) -> bool:
        """Check if Ollama is healthy and model is available."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{FAQ_OLLAMA_URL}/api/tags")
                if response.status_code != 200:
                    logger.warning(f"Ollama health check failed: {response.status_code}")
                    return False
                
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                
                # Check if our model is available
                model_base = FAQ_OLLAMA_MODEL.split(":")[0]
                for m in models:
                    if m.startswith(model_base):
                        logger.info(f"✓ Ollama healthy, model {FAQ_OLLAMA_MODEL} available")
                        return True
                
                logger.warning(f"Model {FAQ_OLLAMA_MODEL} not found. Available: {models}")
                return False
                
            except Exception as e:
                logger.warning(f"Ollama health check failed: {e}")
                return False
    
    def _check_gemini_health(self) -> bool:
        """Check if Gemini API key is configured."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set")
            return False
        logger.info("✓ Gemini API key configured")
        return True
    
    def _generate_chunk_id(self, chunk: Document) -> str:
        """
        Generate a stable ID for a chunk based on content hash + metadata.
        
        The ID is stable across ingestion runs for the same content,
        allowing for idempotent operations.
        
        Args:
            chunk: Document chunk to generate ID for
            
        Returns:
            Stable chunk ID string
        """
        # Use content hash for uniqueness
        content_hash = hashlib.md5(chunk.page_content.encode()).hexdigest()[:12]
        
        # Include payload_id for traceability
        payload_id = chunk.metadata.get("payload_id", "unknown")
        
        # Include chunk index for ordering
        chunk_idx = chunk.metadata.get("chunk_index", 0)
        
        return f"{payload_id}_{chunk_idx}_{content_hash}"
    
    async def generate_questions(self, chunk: Document) -> List[str]:
        """
        Generate questions for a document chunk.
        
        Args:
            chunk: Document chunk to generate questions for
            
        Returns:
            List of generated questions (up to num_questions per chunk)
        """
        # Truncate content for LLM context (avoid token limits)
        content = chunk.page_content[:3000]
        
        # Skip very short content
        if len(content.strip()) < 50:
            logger.debug(f"Skipping question generation for short chunk ({len(content)} chars)")
            return []
        
        # Escape curly braces in content to prevent .format() breaking on code snippets
        # e.g., "function() { return x; }" would break without escaping
        escaped_content = content.replace('{', '{{').replace('}', '}}')
        
        prompt = self.GENERATION_PROMPT.format(
            content=escaped_content,
            num_questions=self.num_questions
        )
        
        try:
            # Call appropriate backend
            if self._use_local:
                response_text = await self._call_local_llm(prompt)
                if not response_text:
                    logger.warning("Local LLM returned empty response")
                    return []
            else:
                if not self.llm or self.llm == "local":
                    logger.warning("Gemini LLM not available")
                    return []
                response = await self.llm.ainvoke(prompt)
                response_text = response.content.strip()
            
            # Rate limiting (only for Gemini, local has no limits)
            if self._rate_limit > 0:
                await asyncio.sleep(self._rate_limit)
            
            # Parse response - one question per line
            raw_questions = response_text.split('\n')
            
            # Filter and clean questions
            questions = []
            for q in raw_questions:
                q = q.strip()
                # Remove numbering (1., 2., etc.)
                if q and q[0].isdigit() and '.' in q[:3]:
                    q = q.split('.', 1)[1].strip()
                # Remove bullet points
                if q and q.startswith(('-', '*', '•')):
                    q = q[1:].strip()
                # Keep only valid questions
                if q and q.endswith('?') and len(q) > 10:
                    questions.append(q)
            
            # Limit to requested number
            questions = questions[:self.num_questions]
            
            logger.debug(f"Generated {len(questions)} questions for chunk")
            return questions
            
        except Exception as e:
            logger.warning(f"Failed to generate questions: {e}")
            return []
    
    async def process_chunks_with_questions(
        self, 
        chunks: List[Document]
    ) -> Tuple[List[Document], Dict[str, Document]]:
        """
        Process chunks and create synthetic question documents.
        
        CRITICAL: Questions store ONLY the question text and parent_chunk_id.
        The parent_chunks_map is used at retrieval time to swap.
        
        CRITICAL for CRUD lifecycle: Synthetic questions inherit payload_id
        from parent chunk, so deletion by payload_id removes both.
        
        Args:
            chunks: Original document chunks
            
        Returns:
            Tuple of:
            - all_docs: Original chunks + synthetic question docs
            - parent_chunks_map: Dict mapping chunk_id -> full Document
        """
        if not USE_FAQ_INDEXING:
            logger.info("FAQ indexing disabled, returning original chunks")
            return chunks, {}
        
        all_docs: List[Document] = []
        parent_chunks_map: Dict[str, Document] = {}
        
        total_questions = 0
        
        for i, chunk in enumerate(chunks):
            # Generate stable ID for this chunk
            chunk_id = self._generate_chunk_id(chunk)
            
            # Store in parent map (for retrieval swap)
            parent_chunks_map[chunk_id] = chunk
            
            # Add original chunk with chunk_id and is_synthetic=False
            chunk_with_id = Document(
                page_content=chunk.page_content,
                metadata={
                    **chunk.metadata,
                    "chunk_id": chunk_id,
                    "is_synthetic": False,
                }
            )
            all_docs.append(chunk_with_id)
            
            # Generate synthetic questions
            questions = await self.generate_questions(chunk)
            
            for q_idx, question in enumerate(questions):
                # CRITICAL: Synthetic questions MUST inherit key metadata
                # especially payload_id for CRUD lifecycle support
                question_doc = Document(
                    page_content=question,  # Only the question for embedding
                    metadata={
                        # Inherit from parent for CRUD lifecycle
                        "payload_id": chunk.metadata.get("payload_id"),
                        "status": chunk.metadata.get("status", "published"),
                        "source": chunk.metadata.get("source"),
                        # Synthetic question markers
                        "doc_type": "synthetic_question",
                        "is_synthetic": True,
                        "parent_chunk_id": chunk_id,  # Points to parent
                        "question_index": q_idx,
                    }
                )
                all_docs.append(question_doc)
                total_questions += 1
            
            # Log progress for long operations
            if (i + 1) % 10 == 0:
                logger.info(f"Processed {i + 1}/{len(chunks)} chunks...")
        
        logger.info(
            f"Processed {len(chunks)} chunks → {len(all_docs)} documents "
            f"({total_questions} synthetic questions)"
        )
        return all_docs, parent_chunks_map


def resolve_parents(
    retrieved_docs: List[Document],
    parent_chunks_map: Dict[str, Document]
) -> List[Document]:
    """
    Swap synthetic question hits with their full-text parent chunks.
    
    This is the CRITICAL function that implements Parent Document Pattern.
    Called after vector search, before sending to LLM.
    
    Args:
        retrieved_docs: Documents returned from vector search
        parent_chunks_map: Dict mapping chunk_id -> full Document
        
    Returns:
        List of Documents with synthetic questions replaced by parents
    """
    resolved: List[Document] = []
    seen_parent_ids: Set[str] = set()  # Deduplicate (multiple Qs may hit same parent)
    
    for doc in retrieved_docs:
        if doc.metadata.get("is_synthetic", False):
            # This is a synthetic question - swap for parent
            parent_id = doc.metadata.get("parent_chunk_id")
            
            if parent_id and parent_id not in seen_parent_ids:
                parent_doc = parent_chunks_map.get(parent_id)
                if parent_doc:
                    resolved.append(parent_doc)
                    seen_parent_ids.add(parent_id)
                    logger.debug(f"Swapped synthetic Q for parent: {parent_id}")
                else:
                    # Parent not found in map - this shouldn't happen normally
                    # but we handle it gracefully
                    logger.warning(f"Parent chunk not found in map: {parent_id}")
                    # Fall back to including the synthetic question
                    # (better than losing the result entirely)
                    resolved.append(doc)
            elif parent_id in seen_parent_ids:
                # Already included this parent, skip duplicate
                logger.debug(f"Skipping duplicate parent: {parent_id}")
        else:
            # Regular document - keep as-is, but deduplicate
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id:
                if chunk_id not in seen_parent_ids:
                    resolved.append(doc)
                    seen_parent_ids.add(chunk_id)
                else:
                    logger.debug(f"Skipping duplicate chunk: {chunk_id}")
            else:
                # No chunk_id (legacy document?) - include anyway
                resolved.append(doc)
    
    logger.info(f"Resolved {len(retrieved_docs)} hits → {len(resolved)} unique documents")
    return resolved


def resolve_parents_from_tuples(
    retrieved_docs_with_scores: List[Tuple[Document, float]],
    parent_chunks_map: Dict[str, Document]
) -> List[Tuple[Document, float]]:
    """
    Variant of resolve_parents that handles (Document, score) tuples.
    
    Useful when working with similarity_search_with_score results.
    
    Args:
        retrieved_docs_with_scores: List of (Document, score) tuples
        parent_chunks_map: Dict mapping chunk_id -> full Document
        
    Returns:
        List of (Document, score) tuples with synthetic questions replaced
    """
    resolved: List[Tuple[Document, float]] = []
    seen_parent_ids: Set[str] = set()
    
    for doc, score in retrieved_docs_with_scores:
        if doc.metadata.get("is_synthetic", False):
            parent_id = doc.metadata.get("parent_chunk_id")
            
            if parent_id and parent_id not in seen_parent_ids:
                parent_doc = parent_chunks_map.get(parent_id)
                if parent_doc:
                    # Keep the score from the synthetic question match
                    resolved.append((parent_doc, score))
                    seen_parent_ids.add(parent_id)
                else:
                    logger.warning(f"Parent chunk not found: {parent_id}")
                    resolved.append((doc, score))
        else:
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id:
                if chunk_id not in seen_parent_ids:
                    resolved.append((doc, score))
                    seen_parent_ids.add(chunk_id)
            else:
                resolved.append((doc, score))
    
    return resolved

