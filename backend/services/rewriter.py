"""
Query Rewriter Service

Provides query rewriting to resolve context blindness in follow-up questions.
Supports both local (Ollama) and cloud (Gemini) backends.

The rewriter transforms ambiguous queries like "Does it expire?" into
context-complete queries like "Does the $21 Litecoin plan expire?" by
analyzing the chat history.

System Prompt:
    Rewrites user input into standalone, context-complete search queries.
    Handles NO_SEARCH_NEEDED for non-search queries (greetings, thanks, etc.)

Usage:
    # Local rewriter (Ollama)
    local = LocalRewriter()
    rewritten = await local.rewrite("Does it expire?", chat_history)
    
    # Cloud rewriter (Gemini)  
    gemini = GeminiRewriter()
    rewritten = await gemini.rewrite("Does it expire?", chat_history)
"""

import os
import logging
from typing import List, Tuple, Optional
from abc import ABC, abstractmethod
import httpx

logger = logging.getLogger(__name__)

# System prompt for query rewriting
REWRITER_SYSTEM_PROMPT = """You are a Query Resolution Engine. Your task is to rewrite the User's input into a standalone, context-complete search query.

Rules:
1. Analyze the Chat History to resolve pronouns and ambiguous references
2. Remove filler words and make the query concise
3. If the user's input doesn't need a search (greetings, thanks, acknowledgments), output exactly: NO_SEARCH_NEEDED
4. DO NOT answer the question - only rewrite it
5. Output ONLY the rewritten query or NO_SEARCH_NEEDED

Examples:
- Chat: "What is the $21 plan?" / User: "Does it expire?" → "Does the $21 Litecoin plan expire?"
- Chat: "Tell me about MWEB" / User: "How do I enable it?" → "How do I enable MWEB on Litecoin?"
- User: "Thanks!" → NO_SEARCH_NEEDED
- User: "Got it, appreciate the help" → NO_SEARCH_NEEDED
- User: "What is Litecoin?" → "What is Litecoin?"
"""


class BaseRewriter(ABC):
    """Abstract base class for query rewriters."""
    
    @abstractmethod
    async def rewrite(self, query: str, chat_history: List[Tuple[str, str]]) -> str:
        """
        Rewrite query to resolve context blindness.
        
        Args:
            query: The user's current query
            chat_history: List of (human_message, ai_message) tuples
            
        Returns:
            Rewritten query or "NO_SEARCH_NEEDED"
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the rewriter service is healthy."""
        pass
    
    def _build_prompt(self, query: str, chat_history: List[Tuple[str, str]]) -> str:
        """
        Build the prompt for the rewriter.
        
        Args:
            query: The user's current query
            chat_history: List of (human_message, ai_message) tuples
            
        Returns:
            Formatted prompt string
        """
        # Format chat history
        history_text = ""
        if chat_history:
            for human_msg, ai_msg in chat_history[-3:]:  # Last 3 exchanges
                if human_msg:
                    history_text += f"User: {human_msg}\n"
                if ai_msg:
                    # Truncate AI responses to avoid token overflow
                    truncated_ai = ai_msg[:500] + "..." if len(ai_msg) > 500 else ai_msg
                    history_text += f"Assistant: {truncated_ai}\n"
        
        # Build the full prompt
        prompt = f"{REWRITER_SYSTEM_PROMPT}\n\n"
        if history_text:
            prompt += f"Chat History:\n{history_text}\n"
        prompt += f"User Input: {query}\n\nRewritten Query:"
        
        return prompt


class LocalRewriter(BaseRewriter):
    """
    Local query rewriter using Ollama.
    
    Uses llama3.2:3b (or configurable model) for fast, local query rewriting.
    Optimized for M4 Silicon with Metal acceleration.
    """
    
    def __init__(
        self,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 10.0,
    ):
        """
        Initialize local Ollama rewriter.
        
        Args:
            ollama_url: Ollama API URL (default: OLLAMA_URL env var or localhost)
            model: Ollama model name (default: LOCAL_REWRITER_MODEL env var or llama3.2:3b)
            timeout: Request timeout in seconds
        """
        self.ollama_url = ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = model or os.getenv("LOCAL_REWRITER_MODEL", "llama3.2:3b")
        self.timeout = timeout
        
        logger.info(f"LocalRewriter initialized: url={self.ollama_url}, model={self.model}")
    
    async def rewrite(self, query: str, chat_history: List[Tuple[str, str]]) -> str:
        """
        Rewrite query using Ollama.
        
        Args:
            query: The user's current query
            chat_history: List of (human_message, ai_message) tuples
            
        Returns:
            Rewritten query or "NO_SEARCH_NEEDED"
        """
        prompt = self._build_prompt(query, chat_history)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,  # Low temperature for consistent output
                            "num_predict": 100,  # Short response expected
                        },
                    },
                )
                response.raise_for_status()
                
                data = response.json()
                rewritten = data.get("response", "").strip()
                
                # Clean up the response
                rewritten = self._clean_response(rewritten, query)
                
                logger.debug(f"Local rewrite: '{query}' -> '{rewritten}'")
                return rewritten
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama API error: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Ollama connection error: {e}")
                raise
    
    def _clean_response(self, response: str, original_query: str) -> str:
        """Clean up the rewriter response."""
        # Remove common prefixes/suffixes
        response = response.strip()
        
        # Handle empty response
        if not response:
            return original_query
        
        # Check for NO_SEARCH_NEEDED
        if "NO_SEARCH_NEEDED" in response.upper():
            return "NO_SEARCH_NEEDED"
        
        # Remove quotes if present
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1]
        if response.startswith("'") and response.endswith("'"):
            response = response[1:-1]
        
        # Remove "Rewritten Query:" prefix if present
        prefixes = ["Rewritten Query:", "Rewritten:", "Query:"]
        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix):].strip()
        
        return response if response else original_query
    
    async def health_check(self) -> bool:
        """Check if Ollama is healthy and model is available."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                # Check if Ollama is running
                response = await client.get(f"{self.ollama_url}/api/tags")
                if response.status_code != 200:
                    return False
                
                # Check if model is available
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                
                # Check if our model is in the list (with or without :latest tag)
                model_base = self.model.split(":")[0]
                for m in models:
                    if m.startswith(model_base):
                        return True
                
                logger.warning(f"Model {self.model} not found in Ollama. Available: {models}")
                return False
                
            except Exception as e:
                logger.warning(f"Ollama health check failed: {e}")
                return False


class GeminiRewriter(BaseRewriter):
    """
    Cloud query rewriter using Google Gemini.
    
    Used as fallback when local rewriter is unavailable or queue is full.
    Uses Gemini Flash for fast, cost-effective rewriting.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash-lite",
    ):
        """
        Initialize Gemini rewriter.
        
        Args:
            api_key: Google API key (default: GOOGLE_API_KEY env var)
            model: Gemini model name
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model
        self._client = None
        
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY not set - GeminiRewriter will fail")
        else:
            logger.info(f"GeminiRewriter initialized: model={self.model}")
    
    def _get_client(self):
        """Lazy-load Gemini client via langchain_google_genai."""
        if self._client is None:
            from langchain_google_genai import ChatGoogleGenerativeAI
            self._client = ChatGoogleGenerativeAI(
                model=self.model,
                google_api_key=self.api_key,
                temperature=0.1,
                max_output_tokens=100,
            )
        return self._client
    
    async def rewrite(self, query: str, chat_history: List[Tuple[str, str]]) -> str:
        """
        Rewrite query using Gemini.
        
        Args:
            query: The user's current query
            chat_history: List of (human_message, ai_message) tuples
            
        Returns:
            Rewritten query or "NO_SEARCH_NEEDED"
        """
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not configured")
        
        prompt = self._build_prompt(query, chat_history)
        
        try:
            client = self._get_client()
            
            response = await client.ainvoke(prompt)
            
            rewritten = response.content.strip() if response.content else query
            rewritten = self._clean_response(rewritten, query)
            
            logger.debug(f"Gemini rewrite: '{query}' -> '{rewritten}'")
            return rewritten
            
        except Exception as e:
            logger.error(f"Gemini rewrite error: {e}")
            raise
    
    def _clean_response(self, response: str, original_query: str) -> str:
        """Clean up the rewriter response."""
        response = response.strip()
        
        if not response:
            return original_query
        
        if "NO_SEARCH_NEEDED" in response.upper():
            return "NO_SEARCH_NEEDED"
        
        # Remove quotes if present
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1]
        if response.startswith("'") and response.endswith("'"):
            response = response[1:-1]
        
        # Remove common prefixes
        prefixes = ["Rewritten Query:", "Rewritten:", "Query:"]
        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix):].strip()
        
        return response if response else original_query
    
    async def health_check(self) -> bool:
        """Check if Gemini API is accessible."""
        if not self.api_key:
            return False
        
        try:
            client = self._get_client()
            # Simple test query
            response = await client.generate_content_async("Say 'ok'")
            return response.text is not None
        except Exception as e:
            logger.warning(f"Gemini health check failed: {e}")
            return False

