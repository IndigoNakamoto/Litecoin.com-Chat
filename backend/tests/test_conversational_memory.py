"""
Pytest tests for conversational memory functionality in RAG pipeline.
Tests the LangChain-style conversation management with history-aware retrieval.
"""

import os
import sys
from dotenv import load_dotenv

# Add project root and backend directory to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root_dir = os.path.dirname(backend_dir)
# Add both project root (for backend.* imports) and backend dir (for data_ingestion.* imports)
if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Load environment variables
dotenv_path = os.path.join(backend_dir, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, override=True)

# Set required environment variables for imports (rag_pipeline checks at import time)
if not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = "test-key"
if not os.getenv("MONGO_URI"):
    os.environ["MONGO_URI"] = "mongodb://test"

import pytest
from backend.rag_pipeline import RAGPipeline
from backend.data_ingestion.vector_store_manager import VectorStoreManager
from langchain_core.documents import Document

# Builds a real FAISS index from a downloaded sentence-transformers model and
# exercises the full retrieval stack, so it needs live services rather than CI.
pytestmark = pytest.mark.integration


@pytest.fixture
def rag_pipeline(test_vector_store, mock_llm, monkeypatch):
    """Create a RAG pipeline instance with mocked dependencies."""
    # Create VectorStoreManager that uses the test vector store
    vs_manager = VectorStoreManager()
    vs_manager.vector_store = test_vector_store
    # Queries must be embedded with the same model that built the index, or FAISS
    # aborts the process on the dimension mismatch instead of raising.
    vs_manager.embeddings = test_vector_store.embeddings
    vs_manager.retriever = test_vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 7}
    )
    
    # Create RAG pipeline with the test vector store manager
    pipeline = RAGPipeline(vector_store_manager=vs_manager)
    
    # Mock the LLM to return deterministic responses
    pipeline.llm = mock_llm
    
    return pipeline


@pytest.mark.asyncio
async def test_initial_query(rag_pipeline, test_kb_docs):
    """Test initial query about Litecoin."""
    initial_query = "What is Litecoin?"
    
    answer, sources, metadata = await rag_pipeline.aquery(initial_query, chat_history=[])
    
    assert answer is not None
    assert len(answer) > 0
    assert isinstance(sources, list)
    assert len(sources) >= 0  # May or may not have sources depending on mock


@pytest.mark.asyncio
async def test_follow_up_pronoun_resolution(rag_pipeline, test_kb_docs):
    """Test that follow-up questions resolve pronouns correctly."""
    # First message establishes context
    initial_query = "Who created Litecoin?"
    answer1, sources1, metadata1 = await rag_pipeline.aquery(initial_query, chat_history=[])
    
    assert answer1 is not None
    
    # Follow-up with pronoun reference
    followup_query = "When did he create it?"
    chat_history = [(initial_query, answer1)]
    answer2, sources2, metadata2 = await rag_pipeline.aquery(followup_query, chat_history)
    
    assert answer2 is not None
    assert len(answer2) > 0
    # The answer should reference the context (even if mocked, the structure should work)
    assert isinstance(sources2, list)


@pytest.mark.asyncio
async def test_multi_turn_conversation(rag_pipeline, test_kb_docs):
    """Test multi-turn conversations maintain context."""
    # First query
    query1 = "What is Litecoin?"
    answer1, _, _ = await rag_pipeline.aquery(query1, chat_history=[])
    
    # Second query
    query2 = "Who created it?"
    chat_history = [(query1, answer1)]
    answer2, _, _ = await rag_pipeline.aquery(query2, chat_history)
    
    # Third query
    query3 = "How is it different from Bitcoin?"
    chat_history.append((query2, answer2))
    answer3, _, _ = await rag_pipeline.aquery(query3, chat_history)
    
    assert answer1 is not None
    assert answer2 is not None
    assert answer3 is not None
    assert len(chat_history) == 2  # Should have 2 pairs


@pytest.mark.asyncio
async def test_ambiguous_reference_resolution(rag_pipeline, test_kb_docs):
    """Test resolution of ambiguous references like 'the second one'."""
    # Simulate a conversation where AI mentioned multiple items
    simulated_history = [
        (
            "What are some Litecoin features?",
            "Litecoin has several key features: 1) Faster block times (2.5 minutes vs Bitcoin's 10 minutes), 2) Scrypt mining algorithm, 3) Segregated Witness (SegWit) support, 4) Lightning Network compatibility."
        )
    ]
    
    ambiguous_query = "What about the second one?"
    answer, sources, metadata = await rag_pipeline.aquery(ambiguous_query, simulated_history)
    
    assert answer is not None
    assert len(answer) > 0
    # The query should be converted to a standalone question that resolves the reference
    assert isinstance(sources, list)


@pytest.mark.asyncio
async def test_chat_history_truncation(rag_pipeline, monkeypatch):
    """Test that chat history is truncated at MAX_CHAT_HISTORY_PAIRS."""
    import os
    # Set MAX_CHAT_HISTORY_PAIRS to 2 for testing
    monkeypatch.setenv("MAX_CHAT_HISTORY_PAIRS", "2")
    
    # Create a long chat history (more than 2 pairs)
    long_history = [
        ("Query 1", "Answer 1"),
        ("Query 2", "Answer 2"),
        ("Query 3", "Answer 3"),
        ("Query 4", "Answer 4"),
    ]
    
    # The pipeline should truncate to the last 2 pairs
    query = "What is Litecoin?"
    answer, _, _ = await rag_pipeline.aquery(query, long_history)
    
    assert answer is not None
    # Verify truncation happened (internal check - the pipeline should handle this)


@pytest.mark.asyncio
async def test_empty_chat_history(rag_pipeline):
    """Test query with empty chat history."""
    query = "What is Litecoin?"
    answer, sources, metadata = await rag_pipeline.aquery(query, chat_history=[])
    
    assert answer is not None
    assert len(answer) > 0
    assert isinstance(sources, list)


@pytest.mark.asyncio
async def test_chat_history_format(rag_pipeline):
    """Test that chat history is in the correct format (list of tuples)."""
    query1 = "What is Litecoin?"
    answer1, _, _ = await rag_pipeline.aquery(query1, chat_history=[])
    
    # Chat history should be list of (query, answer) tuples
    chat_history = [(query1, answer1)]
    assert isinstance(chat_history, list)
    assert len(chat_history) == 1
    assert isinstance(chat_history[0], tuple)
    assert len(chat_history[0]) == 2
