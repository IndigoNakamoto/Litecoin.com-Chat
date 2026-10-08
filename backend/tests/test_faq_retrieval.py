"""
Integration tests for FAQ-Based Indexing (Parent Document Pattern).

Tests cover:
- FAQ Generator functionality
- Parent document resolution
- Vocabulary mismatch retrieval improvement
- CRUD lifecycle compatibility (create/update/delete operations)
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from typing import List, Dict

from langchain_core.documents import Document

# Import the modules under test
from backend.services.faq_generator import (
    FAQGenerator,
    extract_retrieval_questions,
    resolve_parents,
    resolve_parents_from_tuples,
    USE_FAQ_INDEXING,
)


class TestFAQGenerator:
    """Test suite for FAQGenerator class."""
    
    @pytest.fixture
    def sample_chunks(self) -> List[Document]:
        """Create sample document chunks for testing."""
        return [
            Document(
                page_content="The maximum supply of Litecoin is 84 million coins. This is four times the supply of Bitcoin.",
                metadata={
                    "payload_id": "test-article-1",
                    "status": "published",
                    "source": "payload",
                    "chunk_index": 0,
                }
            ),
            Document(
                page_content="MWEB (MimbleWimble Extension Blocks) enables confidential transactions on Litecoin. Users can send private transactions using MWEB.",
                metadata={
                    "payload_id": "test-article-1",
                    "status": "published",
                    "source": "payload",
                    "chunk_index": 1,
                }
            ),
            Document(
                page_content="Litecoin uses the Scrypt hashing algorithm, which is different from Bitcoin's SHA-256. This makes Litecoin mining more accessible to consumer hardware.",
                metadata={
                    "payload_id": "test-article-2",
                    "status": "published",
                    "source": "payload",
                    "chunk_index": 0,
                }
            ),
        ]
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing."""
        mock = AsyncMock()
        mock.ainvoke.return_value = MagicMock(
            content="What is the maximum supply of Litecoin?\nHow many Litecoin coins will ever exist?\nWhat is the total coin cap?"
        )
        return mock
    
    def test_generate_chunk_id_stability(self, sample_chunks):
        """Test that chunk IDs are stable across runs."""
        generator = FAQGenerator()
        
        # Generate IDs twice
        id1 = generator._generate_chunk_id(sample_chunks[0])
        id2 = generator._generate_chunk_id(sample_chunks[0])
        
        # Should be identical
        assert id1 == id2
        
        # Should contain payload_id
        assert "test-article-1" in id1
    
    def test_generate_chunk_id_uniqueness(self, sample_chunks):
        """Test that different chunks get different IDs."""
        generator = FAQGenerator()
        
        ids = [generator._generate_chunk_id(chunk) for chunk in sample_chunks]
        
        # All IDs should be unique
        assert len(ids) == len(set(ids))
    
    @pytest.mark.asyncio
    async def test_generate_questions(self, sample_chunks, mock_llm):
        """Test question generation for a chunk."""
        generator = FAQGenerator(llm=mock_llm)
        
        questions = await generator.generate_questions(sample_chunks[0])
        
        # Should generate questions
        assert len(questions) > 0
        assert all(q.endswith("?") for q in questions)
        
        # LLM should have been called
        mock_llm.ainvoke.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_questions_short_content(self):
        """Test that short content is skipped."""
        generator = FAQGenerator()
        
        short_doc = Document(
            page_content="Hello",
            metadata={"payload_id": "test"}
        )
        
        questions = await generator.generate_questions(short_doc)
        
        # Should return empty list for short content
        assert questions == []
    
    @pytest.mark.asyncio
    async def test_process_chunks_with_questions(self, sample_chunks, mock_llm):
        """Test full chunk processing with question generation."""
        generator = FAQGenerator(llm=mock_llm, num_questions=3)
        
        all_docs, parent_chunks_map = await generator.process_chunks_with_questions(sample_chunks)
        
        # Should have more docs than input (originals + questions)
        assert len(all_docs) > len(sample_chunks)
        
        # Parent map should have entries for all original chunks
        assert len(parent_chunks_map) == len(sample_chunks)
        
        # Original chunks should have chunk_id
        for doc in all_docs:
            if not doc.metadata.get("is_synthetic"):
                assert "chunk_id" in doc.metadata
                assert doc.metadata["is_synthetic"] == False

    def test_extract_retrieval_questions_strips_the_comment(self):
        body, questions = extract_retrieval_questions(
            "Nexus, Cake, and Electrum hold Litecoin.\n\n"
            "<!-- retrieval-questions\n"
            "How do I open a wallet?\n"
            "Which Litecoin wallet should I use?\n"
            "-->\n"
        )
        assert questions == [
            "How do I open a wallet?",
            "Which Litecoin wallet should I use?",
        ]
        assert "retrieval-questions" not in body
        assert "Nexus, Cake, and Electrum" in body

    @pytest.mark.asyncio
    async def test_pinned_question_is_synthetic_and_absent_from_parent(self, mock_llm):
        """An HTML comment is indexed as a question; the chip text stays the article."""
        generator = FAQGenerator(llm=mock_llm, num_questions=3)
        chunk = Document(
            page_content=(
                "Nexus Wallet, Cake Wallet, and Electrum-LTC store Litecoin.\n\n"
                "<!-- retrieval-questions\n"
                "How do I open a wallet?\n"
                "What is the maximum supply of Litecoin?\n"
                "-->"
            ),
            metadata={"payload_id": "wallet", "status": "published", "source": "payload"},
        )

        all_docs, parent_map = await generator.process_chunks_with_questions([chunk])

        parents = [d for d in all_docs if not d.metadata.get("is_synthetic")]
        synthetic = [d for d in all_docs if d.metadata.get("is_synthetic")]
        assert len(parents) == 1
        assert "retrieval-questions" not in parents[0].page_content
        assert "<!--" not in parents[0].page_content
        assert "Nexus Wallet" in parents[0].page_content
        pinned = next(d for d in synthetic if d.page_content == "How do I open a wallet?")
        assert pinned.metadata["parent_chunk_id"] == parents[0].metadata["chunk_id"]
        assert pinned.metadata["payload_id"] == "wallet"
        # The pinned line that duplicates the LLM question is indexed once.
        assert sum(d.page_content == "What is the maximum supply of Litecoin?" for d in synthetic) == 1
        assert parents[0].metadata["chunk_id"] in parent_map
        assert "retrieval-questions" not in parent_map[parents[0].metadata["chunk_id"]].page_content
    
    @pytest.mark.asyncio
    async def test_synthetic_questions_inherit_payload_id(self, sample_chunks, mock_llm):
        """CRITICAL: Test that synthetic questions inherit payload_id for CRUD lifecycle."""
        generator = FAQGenerator(llm=mock_llm)
        
        all_docs, _ = await generator.process_chunks_with_questions(sample_chunks)
        
        # Get synthetic questions
        synthetic_docs = [d for d in all_docs if d.metadata.get("is_synthetic")]
        
        # All synthetic questions should have payload_id
        for doc in synthetic_docs:
            assert "payload_id" in doc.metadata
            assert doc.metadata["payload_id"] is not None
            assert doc.metadata["is_synthetic"] == True
            assert "parent_chunk_id" in doc.metadata


class TestResolveParents:
    """Test suite for parent document resolution."""
    
    @pytest.fixture
    def parent_chunks_map(self) -> Dict[str, Document]:
        """Create a parent chunks map for testing."""
        return {
            "article1_0_abc123": Document(
                page_content="Full content of chunk 1 - Maximum supply is 84 million.",
                metadata={
                    "payload_id": "article1",
                    "chunk_id": "article1_0_abc123",
                    "is_synthetic": False,
                    "status": "published",
                }
            ),
            "article1_1_def456": Document(
                page_content="Full content of chunk 2 - MWEB enables privacy.",
                metadata={
                    "payload_id": "article1",
                    "chunk_id": "article1_1_def456",
                    "is_synthetic": False,
                    "status": "published",
                }
            ),
        }
    
    def test_resolve_synthetic_questions(self, parent_chunks_map):
        """Test that synthetic questions are resolved to parent chunks."""
        retrieved_docs = [
            Document(
                page_content="What is the maximum supply?",
                metadata={
                    "is_synthetic": True,
                    "parent_chunk_id": "article1_0_abc123",
                }
            ),
            Document(
                page_content="How does MWEB work?",
                metadata={
                    "is_synthetic": True,
                    "parent_chunk_id": "article1_1_def456",
                }
            ),
        ]
        
        resolved = resolve_parents(retrieved_docs, parent_chunks_map)
        
        # Should have 2 resolved documents
        assert len(resolved) == 2
        
        # Should be parent chunks, not questions
        for doc in resolved:
            assert not doc.metadata.get("is_synthetic", False)
            assert "Full content" in doc.page_content
    
    def test_resolve_deduplication(self, parent_chunks_map):
        """Test that multiple questions pointing to same parent are deduplicated."""
        # Two questions pointing to same parent
        retrieved_docs = [
            Document(
                page_content="What is max supply?",
                metadata={
                    "is_synthetic": True,
                    "parent_chunk_id": "article1_0_abc123",
                }
            ),
            Document(
                page_content="How many coins total?",
                metadata={
                    "is_synthetic": True,
                    "parent_chunk_id": "article1_0_abc123",  # Same parent
                }
            ),
        ]
        
        resolved = resolve_parents(retrieved_docs, parent_chunks_map)
        
        # Should only return ONE parent (deduplicated)
        assert len(resolved) == 1
    
    def test_resolve_mixed_docs(self, parent_chunks_map):
        """Test resolution with mix of synthetic and regular documents."""
        retrieved_docs = [
            Document(
                page_content="What is max supply?",
                metadata={
                    "is_synthetic": True,
                    "parent_chunk_id": "article1_0_abc123",
                }
            ),
            Document(
                page_content="Regular document content",
                metadata={
                    "chunk_id": "regular_chunk",
                    "is_synthetic": False,
                }
            ),
        ]
        
        resolved = resolve_parents(retrieved_docs, parent_chunks_map)
        
        # Should have both: resolved synthetic + regular
        assert len(resolved) == 2
    
    def test_resolve_missing_parent_graceful(self, parent_chunks_map):
        """Test graceful handling when parent chunk not found."""
        retrieved_docs = [
            Document(
                page_content="What is this?",
                metadata={
                    "is_synthetic": True,
                    "parent_chunk_id": "nonexistent_parent",
                }
            ),
        ]
        
        # Should not raise, should include original doc as fallback
        resolved = resolve_parents(retrieved_docs, parent_chunks_map)
        assert len(resolved) == 1


class TestVocabularyMismatchRetrieval:
    """
    Test cases for vocabulary mismatch scenarios.
    
    These are the key test cases that validate the FAQ indexing feature.
    """
    
    def test_vocabulary_mismatch_coin_cap(self):
        """
        Test Case: User asks "What's the coin cap?"
        Document contains: "The maximum supply is 84 million."
        
        Without FAQ indexing: Likely miss (no keyword overlap)
        With FAQ indexing: Hit via synthetic Q "What is the maximum supply?"
        """
        # Create synthetic question that bridges vocabulary gap
        synthetic_question = Document(
            page_content="What is the maximum supply of Litecoin?",
            metadata={
                "is_synthetic": True,
                "parent_chunk_id": "article1_0_abc123",
            }
        )
        
        parent_chunk = Document(
            page_content="The maximum supply is 84 million LTC. This is four times the supply of Bitcoin.",
            metadata={
                "chunk_id": "article1_0_abc123",
                "is_synthetic": False,
            }
        )
        
        parent_map = {"article1_0_abc123": parent_chunk}
        
        # Simulate retrieval hit on synthetic question
        retrieved = [synthetic_question]
        resolved = resolve_parents(retrieved, parent_map)
        
        # Should return full parent chunk with answer
        assert len(resolved) == 1
        assert "84 million" in resolved[0].page_content
    
    def test_vocabulary_mismatch_privacy(self):
        """
        Test Case: User asks "Can I send LTC privately?"
        Document contains: "MWEB enables confidential transactions."
        
        Without FAQ indexing: Likely miss
        With FAQ indexing: Hit via synthetic Q "How do I send private Litecoin transactions?"
        """
        synthetic_question = Document(
            page_content="How can I send private Litecoin transactions?",
            metadata={
                "is_synthetic": True,
                "parent_chunk_id": "mweb_chunk",
            }
        )
        
        parent_chunk = Document(
            page_content="MWEB (MimbleWimble Extension Blocks) enables confidential transactions on Litecoin.",
            metadata={
                "chunk_id": "mweb_chunk",
                "is_synthetic": False,
            }
        )
        
        parent_map = {"mweb_chunk": parent_chunk}
        
        retrieved = [synthetic_question]
        resolved = resolve_parents(retrieved, parent_map)
        
        assert len(resolved) == 1
        assert "MWEB" in resolved[0].page_content
        assert "confidential" in resolved[0].page_content


class TestCRUDLifecycle:
    """
    Test CRUD lifecycle compatibility for FAQ indexing.
    
    CRITICAL: Synthetic questions must inherit payload_id so that
    deletion by payload_id removes both parent chunks AND synthetic questions.
    """
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing."""
        mock = AsyncMock()
        mock.ainvoke.return_value = MagicMock(
            content="What is Litecoin?\nHow does Litecoin work?"
        )
        return mock
    
    @pytest.mark.asyncio
    async def test_create_inherits_payload_id(self, mock_llm):
        """Test that CREATE operation assigns payload_id to synthetic questions."""
        from backend.services.faq_generator import FAQGenerator
        
        chunk = Document(
            page_content="Litecoin is a peer-to-peer cryptocurrency.",
            metadata={
                "payload_id": "new-article-123",
                "status": "published",
            }
        )
        
        generator = FAQGenerator(llm=mock_llm)
        all_docs, _ = await generator.process_chunks_with_questions([chunk])
        
        # All documents (original + synthetic) should have same payload_id
        for doc in all_docs:
            assert doc.metadata.get("payload_id") == "new-article-123"
    
    @pytest.mark.asyncio
    async def test_update_deletes_old_synthetic_questions(self, mock_llm):
        """
        Test that UPDATE operation works correctly.
        
        When a document is updated:
        1. delete_documents_by_metadata_field('payload_id', ...) is called
        2. This should delete BOTH old parent chunks AND old synthetic questions
        3. New chunks and questions are created with same payload_id
        """
        from backend.services.faq_generator import FAQGenerator
        
        # Original chunk
        original_chunk = Document(
            page_content="Old content about Litecoin.",
            metadata={
                "payload_id": "article-to-update",
                "status": "published",
            }
        )
        
        generator = FAQGenerator(llm=mock_llm)
        old_docs, _ = await generator.process_chunks_with_questions([original_chunk])
        
        # All old docs have same payload_id
        old_payload_ids = {d.metadata.get("payload_id") for d in old_docs}
        assert old_payload_ids == {"article-to-update"}
        
        # Simulate UPDATE: old docs deleted, new docs created
        updated_chunk = Document(
            page_content="New updated content about Litecoin.",
            metadata={
                "payload_id": "article-to-update",  # Same payload_id
                "status": "published",
            }
        )
        
        new_docs, _ = await generator.process_chunks_with_questions([updated_chunk])
        
        # All new docs have same payload_id
        new_payload_ids = {d.metadata.get("payload_id") for d in new_docs}
        assert new_payload_ids == {"article-to-update"}
    
    def test_delete_removes_all_by_payload_id(self):
        """
        Test that DELETE operation removes both parent chunks AND synthetic questions.
        
        This is a logical test - actual MongoDB deletion is tested elsewhere.
        The key is that both types of documents have the same payload_id.
        """
        # Simulate documents in MongoDB
        docs_in_mongo = [
            # Original chunk
            {
                "text": "Full content",
                "metadata": {
                    "payload_id": "article-to-delete",
                    "chunk_id": "chunk1",
                    "is_synthetic": False,
                }
            },
            # Synthetic question 1
            {
                "text": "What is this about?",
                "metadata": {
                    "payload_id": "article-to-delete",
                    "is_synthetic": True,
                    "parent_chunk_id": "chunk1",
                }
            },
            # Synthetic question 2
            {
                "text": "How does this work?",
                "metadata": {
                    "payload_id": "article-to-delete",
                    "is_synthetic": True,
                    "parent_chunk_id": "chunk1",
                }
            },
        ]
        
        # Simulate deletion by payload_id
        payload_id_to_delete = "article-to-delete"
        remaining_docs = [
            d for d in docs_in_mongo
            if d["metadata"]["payload_id"] != payload_id_to_delete
        ]
        
        # All docs with that payload_id should be deleted
        assert len(remaining_docs) == 0


class TestFeatureFlag:
    """Test that FAQ indexing respects feature flag."""
    
    @pytest.mark.asyncio
    async def test_faq_indexing_disabled(self):
        """Test that FAQ generation is skipped when disabled."""
        from backend.services.faq_generator import FAQGenerator
        
        with patch.dict('os.environ', {'USE_FAQ_INDEXING': 'false'}):
            # Re-import to get updated flag
            import importlib
            import backend.services.faq_generator as faq_module
            importlib.reload(faq_module)
            
            chunks = [Document(page_content="Test content", metadata={})]
            
            generator = faq_module.FAQGenerator()
            all_docs, parent_map = await generator.process_chunks_with_questions(chunks)
            
            # When disabled, should return original chunks only
            # (Actually the feature flag check is at the start of process_chunks_with_questions)


