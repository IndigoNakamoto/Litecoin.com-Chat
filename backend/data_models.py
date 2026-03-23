# backend/data_models.py

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import List, Literal, Optional, Dict, Any
from backend.utils.input_sanitizer import sanitize_query_input, MAX_QUERY_LENGTH

class PayloadArticleMetadata(BaseModel):
    """
    Pydantic model for the metadata of a single document chunk derived from Payload CMS.
    """
    # Core Identifiers
    payload_id: str = Field(..., description="The Payload ID of the source article.")
    document_id: Optional[str] = Field(None, description="A unique ID for the document chunk.")
    source: str = Field("payload", description="The source of the content.")
    content_type: str = Field("article", description="The type of content.")

    # Content Classification
    chunk_type: Literal["title_summary", "section", "text"] = Field(..., description="The type of the content chunk.")
    chunk_index: int = Field(..., description="The index of the chunk within the article.")
    is_title_chunk: bool = Field(False, description="Indicates if this chunk represents the main title and summary.")
    doc_title: str = Field(..., description="The main title of the article (from Payload's 'title').")
    section_title: Optional[str] = Field(None, description="The title of the section this chunk belongs to.")
    subsection_title: Optional[str] = Field(None, description="The title of the subsection.")
    subsubsection_title: Optional[str] = Field(None, description="The title of the sub-subsection.")

    # Searchable Fields
    author: Optional[str] = Field(None, description="The author's name or ID.")
    categories: List[str] = Field([], description="A list of category names or IDs.")
    
    # Filtering & Sorting
    status: Literal["draft", "published"] = Field(..., description="The publication status.")
    published_date: Optional[datetime] = Field(None, description="The date the article was published.")
    updated_at: Optional[datetime] = Field(
        None,
        description="Last update time from Payload CMS (updatedAt), propagated to each chunk.",
    )
    locale: str = Field("en", description="The locale of the content.")
    content_length: int = Field(..., description="The character length of the content in this chunk.")

    # Technical
    slug: Optional[str] = Field(None, description="The URL slug for the article.")

class ChatMessage(BaseModel):
    """
    Pydantic model for a single chat message in the conversation history.
    """
    role: Literal["human", "ai"] = Field(..., description="The role of the sender, either 'human' or 'ai'.")
    content: str = Field(..., description="The content of the chat message.")
    
    @field_validator('content')
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        """Sanitize chat message content for prompt injection, NoSQL injection, and length."""
        if not v:
            return v
        return sanitize_query_input(v, MAX_QUERY_LENGTH)

class ChatRequest(BaseModel):
    """
    Pydantic model for a chat request, including the current query and chat history.
    """
    query: str = Field(..., description="The user's current query.")
    chat_history: List[ChatMessage] = Field([], description="A list of previous chat messages in the conversation.")
    turnstile_token: Optional[str] = Field(None, description="Optional Cloudflare Turnstile verification token.")
    
    @field_validator('query')
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """Sanitize query for prompt injection, NoSQL injection, and length."""
        if not v:
            return v
        return sanitize_query_input(v, MAX_QUERY_LENGTH)

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is Litecoin?",
                "chat_history": [
                    {"role": "human", "content": "Hi, how are you?"},
                    {"role": "ai", "content": "I'm doing well, thank you! How can I help you with Litecoin today?"}
                ]
            }
        }

class PayloadWebhookDoc(BaseModel):
    """
    Represents the 'doc' object received from a Payload CMS 'afterChange' hook.
    This model validates the incoming webhook payload for an article.
    """
    id: str
    createdAt: datetime # Add createdAt
    updatedAt: datetime # Add updatedAt
    title: str
    author: Optional[str] = None # This will be the user ID
    publishedDate: Optional[str] = None # Payload sends date as a string, make it optional
    category: Optional[List[str]] = Field(None, description="List of category IDs") # Make optional and explicitly set default to None
    content: Dict[str, Any] # This is the Lexical JSON structure
    markdown: str # This is the auto-generated markdown from the hook in Payload
    status: Literal["draft", "published"]
    slug: Optional[str] = None # Make optional

    class Config:
        extra = "allow" # Allow any other fields from Payload

class UserQuestion(BaseModel):
    """
    Pydantic model for logging user questions for later analysis.
    This will be used to categorize and group questions to understand user needs.
    """
    id: Optional[str] = Field(None, description="MongoDB document ID (assigned when retrieved from database).")
    question: str = Field(..., description="The user's question/query.")
    chat_history_length: int = Field(0, description="Number of previous messages in the conversation.")
    endpoint_type: Literal["chat", "stream"] = Field(..., description="Which endpoint was used (chat or stream).")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the question was asked.")
    # Fields for future LLM categorization/analysis
    category: Optional[str] = Field(None, description="Category assigned by LLM analysis (to be populated later).")
    tags: List[str] = Field(default_factory=list, description="Tags assigned by LLM analysis (to be populated later).")
    analyzed: bool = Field(False, description="Whether this question has been analyzed by LLM yet.")
    analyzed_at: Optional[datetime] = Field(None, description="When the question was analyzed.")
    
    @field_validator('question')
    @classmethod
    def sanitize_question(cls, v: str) -> str:
        """Sanitize question for prompt injection, NoSQL injection, and length."""
        if not v:
            return v
        return sanitize_query_input(v, MAX_QUERY_LENGTH)

    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is Litecoin?",
                "chat_history_length": 0,
                "endpoint_type": "chat",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }

class LLMRequestLog(BaseModel):
    """
    Pydantic model for logging complete LLM request/response data.
    Stores user questions, assistant responses, token counts, costs, and metadata
    for historical analysis, cost recalculation, and audit trails.
    """
    id: Optional[str] = Field(None, description="MongoDB document ID (assigned when retrieved from database).")
    request_id: str = Field(..., description="Unique request identifier (UUID).")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the request was processed.")
    
    # User input
    user_question: str = Field(..., description="The user's question/query.")
    chat_history_length: int = Field(0, description="Number of previous messages in the conversation.")
    endpoint_type: Literal["chat", "stream"] = Field(..., description="Which endpoint was used (chat or stream).")
    
    # LLM response
    assistant_response: str = Field(..., description="Full assistant response text.")
    response_length: int = Field(..., description="Character count of the response.")
    
    # Token usage (actual from API)
    input_tokens: int = Field(0, description="Number of input tokens (actual from API).")
    output_tokens: int = Field(0, description="Number of output tokens (actual from API).")
    
    # Cost calculation
    cost_usd: float = Field(0.0, description="Calculated cost in USD.")
    pricing_version: str = Field(..., description="Pricing version used (date string).")
    model: str = Field(..., description="LLM model name.")
    operation: str = Field(..., description="Operation type (e.g., 'generate').")
    
    # Performance
    duration_seconds: float = Field(0.0, description="Request duration in seconds.")
    status: Literal["success", "error"] = Field("success", description="Request status.")
    
    # Source documents
    sources_count: int = Field(0, description="Number of source documents retrieved.")
    
    # Caching
    cache_hit: bool = Field(False, description="Whether this was a cache hit.")
    cache_type: Optional[str] = Field(None, description="Cache type: 'query', 'suggested_question', or null.")
    
    # Error handling
    error_message: Optional[str] = Field(None, description="Error message if status is 'error'.")
    
    @field_validator('user_question', 'assistant_response')
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        """Sanitize text fields for prompt injection, NoSQL injection, and length."""
        if not v:
            return v
        # For assistant_response, allow longer content (responses can be long)
        max_length = MAX_QUERY_LENGTH * 10  # Allow 10x for responses
        sanitized = sanitize_query_input(v, max_length)
        return sanitized
    
    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2025-01-15T10:30:00Z",
                "user_question": "What is Litecoin?",
                "chat_history_length": 0,
                "endpoint_type": "chat",
                "assistant_response": "Litecoin is a peer-to-peer cryptocurrency...",
                "response_length": 1250,
                "input_tokens": 1250,
                "output_tokens": 450,
                "cost_usd": 0.000325,
                "pricing_version": "2025-01-15",
                "model": "gemini-3.1-flash-lite-preview",
                "operation": "generate",
                "duration_seconds": 1.2,
                "status": "success",
                "sources_count": 3,
                "cache_hit": False,
                "cache_type": None,
                "error_message": None
            }
        }


class KnowledgeCandidate(BaseModel):
    """
    Represents a knowledge gap detected when search grounding supplements KB content.
    Queued for admin review; approved candidates become Payload CMS draft articles.
    """
    id: Optional[str] = Field(None, description="MongoDB document ID.")
    user_question: str = Field(..., description="The user question that triggered a KB gap.")
    request_id: str = Field(..., description="Request ID from the originating LLM call.")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the gap was detected.")
    generated_answer: str = Field(..., description="The full answer generated (including search-grounded content).")
    grounding_sources: List[Dict[str, Any]] = Field(default_factory=list, description="Web sources used by search grounding.")
    kb_sources_used: List[Dict[str, Any]] = Field(default_factory=list, description="KB sources that were available.")
    kb_coverage_score: float = Field(0.0, description="Ratio of KB sources to retriever_k (0.0-1.0).")
    topic_cluster: Optional[str] = Field(None, description="Detected topic cluster (e.g. 'mweb', 'mining').")
    question_frequency: int = Field(1, description="Number of similar questions that mapped to this candidate.")
    question_embedding: Optional[List[float]] = Field(None, description="Embedding vector for dedup comparisons.")
    status: Literal["pending", "approved", "rejected", "published"] = Field("pending", description="Review status.")
    reviewed_by: Optional[str] = Field(None, description="Admin who reviewed the candidate.")
    reviewed_at: Optional[datetime] = Field(None, description="When the candidate was reviewed.")
    admin_notes: Optional[str] = Field(None, description="Notes from the admin reviewer.")
    payload_article_id: Optional[str] = Field(None, description="Payload CMS article ID once published as draft.")
    similar_candidate_ids: List[str] = Field(default_factory=list, description="IDs of deduplicated similar candidates.")

    class Config:
        json_schema_extra = {
            "example": {
                "user_question": "What is Litecoin's block time?",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "generated_answer": "Litecoin has a block time of 2.5 minutes...",
                "kb_coverage_score": 0.0,
                "question_frequency": 3,
                "status": "pending",
            }
        }
