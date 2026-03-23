import os
import logging
import time
import datetime
from typing import List
import yaml # Added for frontmatter parsing
import re   # Added for regex-based heading parsing

from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    # Fallback to deprecated import for backward compatibility
    from langchain_community.embeddings import HuggingFaceEmbeddings
from data_models import PayloadWebhookDoc, PayloadArticleMetadata

# --- Setup Logger ---
logger = logging.getLogger(__name__)

# Import Google embeddings if available
try:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    GOOGLE_EMBEDDINGS_AVAILABLE = True
except ImportError:
    GOOGLE_EMBEDDINGS_AVAILABLE = False
    logger.warning("langchain_google_genai not available. Google embeddings will not work.")
logger.setLevel(logging.INFO) # Reverted to INFO
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s:%(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

# --- Custom Text Splitter for Markdown ---
class MarkdownTextSplitter:
    """
    A text splitter that processes Markdown content hierarchically.
    It uses the parse_markdown_hierarchically function to create Document chunks
    with prepended titles and section context. Each paragraph under a heading
    becomes a single semantic chunk without further splitting.
    """
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100, **kwargs):
        """
        Initializes the MarkdownTextSplitter.
        
        Note: chunk_size and chunk_overlap are kept for backward compatibility
        but are not used, as chunks are not further split.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str, metadata: dict = None) -> List[Document]:
        """
        Splits Markdown text into a list of Document objects.

        Args:
            text: The Markdown content to split.
            metadata: Optional initial metadata to associate with the created documents.
                      This metadata can be augmented by the parsing process.

        Returns:
            A list of Document objects, where each document is a chunk
            with prepended hierarchical context.
        """
        initial_metadata = metadata or {}
        if 'source' not in initial_metadata:
            initial_metadata['source'] = 'unknown_markdown_source'
            
        # Parse hierarchically to get semantic chunks (one per paragraph under headings)
        hierarchical_sections = parse_markdown_hierarchically(text, initial_metadata)
        
        return hierarchical_sections

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        Splits a list of Documents, applying hierarchical Markdown parsing to each.
        """
        all_chunks = []
        for doc in documents:
            doc_metadata_copy = doc.metadata.copy() if doc.metadata else {}
            chunks_from_doc = self.split_text(doc.page_content, metadata=doc_metadata_copy)
            all_chunks.extend(chunks_from_doc)
        return all_chunks

# --- Configuration Constants ---
# Default embedding model - best quality for semantic search (recommended: all-mpnet-base-v2)
# Can be overridden with EMBEDDING_MODEL environment variable
# Google models: gemini-embedding-001, text-embedding-004
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
EMBEDDING_MODEL_KWARGS = {"device": "cpu"}
ENCODE_KWARGS = {"normalize_embeddings": True}

# Google embedding models (detected by model name)
GOOGLE_EMBEDDING_MODELS = {
    "gemini-embedding-001",
    "text-embedding-004",
    "models/gemini-embedding-001",
    "models/text-embedding-004",
}

def is_google_embedding_model(model_name: str) -> bool:
    """Check if the model name is a Google embedding model."""
    # Remove 'models/' prefix if present for comparison
    model_base = model_name.replace("models/", "")
    return model_base in GOOGLE_EMBEDDING_MODELS or model_name.startswith("gemini-") or model_name.startswith("text-embedding-")

# --- Custom Exception ---
class PayloadTooLargeError(Exception):
    """Custom exception for payload size errors."""
    pass

# --- Embedding Service ---
class EmbeddingService:
    """
    Handles generating embeddings using local sentence-transformers models or Google embeddings.
    Automatically detects if the model is a Google model and uses the appropriate class.
    """
    def __init__(self, model_name=None):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        model_type = "Google" if is_google_embedding_model(self.model_name) else "local"
        logger.info(f"EmbeddingService initialized with {model_type} model: {self.model_name}")

    def get_embeddings_client(self):
        """
        Returns an instance of the Langchain embeddings client (HuggingFace or Google).
        Automatically detects if the model is a Google model and uses the appropriate class.
        """
        # Check if this is a Google embedding model
        if is_google_embedding_model(self.model_name):
            if not GOOGLE_EMBEDDINGS_AVAILABLE:
                raise ImportError(
                    f"Google embedding model '{self.model_name}' requires langchain_google_genai. "
                    "Install it with: pip install langchain-google-genai"
                )
            
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                raise ValueError(
                    f"Google embedding model '{self.model_name}' requires GOOGLE_API_KEY environment variable"
                )
            
            try:
                # Format model name for Google API (add 'models/' prefix if not present)
                if not self.model_name.startswith("models/"):
                    google_model_name = f"models/{self.model_name}"
                else:
                    google_model_name = self.model_name
                
                # Determine task type based on model
                # gemini-embedding-001 supports task_type parameter
                task_type = "retrieval_document" if "gemini" in self.model_name.lower() else None
                
                embeddings_kwargs = {
                    "model": google_model_name,
                    "google_api_key": google_api_key,
                }
                
                if task_type:
                    embeddings_kwargs["task_type"] = task_type
                
                embeddings = GoogleGenerativeAIEmbeddings(**embeddings_kwargs)
                logger.info(f"Google embedding model '{google_model_name}' initialized successfully")
                return embeddings
            except Exception as e:
                logger.error(f"Failed to initialize Google embedding model '{self.model_name}': {e}")
                raise
        
        # Use local HuggingFace embeddings
        try:
            return HuggingFaceEmbeddings(
                model_name=self.model_name,
                model_kwargs=EMBEDDING_MODEL_KWARGS,
                encode_kwargs=ENCODE_KWARGS
            )
        except Exception as e:
            logger.error(f"Failed to initialize local embedding model '{self.model_name}': {e}")
            raise


def parse_markdown_hierarchically(content: str, initial_metadata: dict) -> List[Document]:
    """
    Parses Markdown content hierarchically, creating chunks with prepended titles.
    Handles YAML frontmatter for legacy files and extracts metadata from Payload documents.
    Each paragraph under a heading becomes a single semantic chunk.
    """
    chunks = []
    current_metadata = initial_metadata.copy()
    is_payload_doc = current_metadata.get('source') == 'payload'

    current_h1 = current_metadata.get("doc_title", "")
    current_h2 = ""
    current_h3 = ""
    current_h4 = ""

    if not is_payload_doc:
        try:
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter_str = parts[1]
                    content_after_frontmatter = parts[2].lstrip()
                    parsed_frontmatter = yaml.safe_load(frontmatter_str)
                    if isinstance(parsed_frontmatter, dict):
                        if 'last_updated' in parsed_frontmatter:
                            last_updated_date = parsed_frontmatter['last_updated']
                            if isinstance(last_updated_date, str):
                                try:
                                    parsed_frontmatter['last_updated'] = datetime.datetime.fromisoformat(last_updated_date.replace('Z', '+00:00'))
                                except (ValueError, TypeError) as e:
                                    logger.warning(f"Could not parse 'last_updated' date string '{last_updated_date}' for source: {initial_metadata.get('source', 'Unknown')}. Error: {e}. Keeping as string.")
                            elif isinstance(last_updated_date, datetime.date) and not isinstance(last_updated_date, datetime.datetime):
                                parsed_frontmatter['last_updated'] = datetime.datetime.combine(last_updated_date, datetime.time.min)

                        current_metadata.update(parsed_frontmatter)
                        if "title" in parsed_frontmatter:
                            current_h1 = parsed_frontmatter["title"]
                        content = content_after_frontmatter
                    else:
                        logger.warning(f"Parsed frontmatter is not a dictionary for source: {initial_metadata.get('source', 'Unknown')}. Skipping.")
                else:
                    logger.debug(f"No valid YAML frontmatter block found for source: {initial_metadata.get('source', 'Unknown')}")
        except yaml.YAMLError as e:
            logger.warning(f"Could not parse YAML frontmatter for {initial_metadata.get('source', 'Unknown')}: {e}")
        except Exception as e:
            logger.warning(f"Error processing frontmatter for {initial_metadata.get('source', 'Unknown')}: {e}")

    lines = content.splitlines()
    current_paragraph_lines = []

    def create_document_chunk(paragraph_lines_list, h1, h2, h3, h4, meta):
        """
        Creates ONE document chunk from a list of paragraph lines,
        prepending the hierarchical headings.
        This replaces the 'create_and_split_chunk' function.
        """
        if not paragraph_lines_list:
            return []
        
        text = "\n".join(paragraph_lines_list).strip()
        if not text:
            return []

        # 1. Create the prepended header
        prepended_text_parts = []
        if h1: prepended_text_parts.append(f"Title: {h1}")
        if h2: prepended_text_parts.append(f"Section: {h2}")
        if h3: prepended_text_parts.append(f"Subsection: {h3}")
        if h4: prepended_text_parts.append(f"Sub-subsection: {h4}")
        
        prepended_header = "\n".join(prepended_text_parts)

        # 2. Create the final page content
        final_page_content = f"{prepended_header}\n\n{text}" if prepended_header else text

        # 3. Create the final metadata
        final_metadata = meta.copy()
        if h1: final_metadata['doc_title_hierarchical'] = h1
        if h2: final_metadata['section_title'] = h2
        if h3: final_metadata['subsection_title'] = h3
        if h4: final_metadata['subsubsection_title'] = h4
        final_metadata['chunk_type'] = 'section' if h2 or h3 or h4 else 'text'
        final_metadata['content_length'] = len(text)
        
        # 4. Clean up any bad date objects (from your original code)
        for key, value in final_metadata.items():
            if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
                logger.debug(f"Converting datetime.date to datetime.datetime for key '{key}' in source: {final_metadata.get('source', 'Unknown')}")
                final_metadata[key] = datetime.datetime.combine(value, datetime.time.min)

        # 5. Return a list containing just this ONE chunk
        return [Document(page_content=final_page_content, metadata=final_metadata)]

    for line_number, line in enumerate(lines):
        h1_match = re.match(r"^#\s+(.*)", line)
        h2_match = re.match(r"^##\s+(.*)", line)
        h3_match = re.match(r"^###\s+(.*)", line)
        h4_match = re.match(r"^####\s+(.*)", line)

        if h1_match and not is_payload_doc:
            if current_paragraph_lines:
                chunks.extend(create_document_chunk(current_paragraph_lines, current_h1, current_h2, current_h3, current_h4, current_metadata))
                current_paragraph_lines = []
            current_h1 = h1_match.group(1).strip()
            current_h2, current_h3, current_h4 = "", "", ""
        elif h1_match and is_payload_doc:
            if current_paragraph_lines:
                chunks.extend(create_document_chunk(current_paragraph_lines, current_h1, current_h2, current_h3, current_h4, current_metadata))
                current_paragraph_lines = []
            current_h2 = h1_match.group(1).strip()
            current_h3, current_h4 = "", ""
        elif h2_match:
            if current_paragraph_lines:
                chunks.extend(create_document_chunk(current_paragraph_lines, current_h1, current_h2, current_h3, current_h4, current_metadata))
                current_paragraph_lines = []
            current_h2 = h2_match.group(1).strip()
            current_h3, current_h4 = "", ""
        elif h3_match:
            if current_paragraph_lines:
                chunks.extend(create_document_chunk(current_paragraph_lines, current_h1, current_h2, current_h3, current_h4, current_metadata))
                current_paragraph_lines = []
            current_h3 = h3_match.group(1).strip()
            current_h4 = ""
        elif h4_match:
            if current_paragraph_lines:
                chunks.extend(create_document_chunk(current_paragraph_lines, current_h1, current_h2, current_h3, current_h4, current_metadata))
                current_paragraph_lines = []
            current_h4 = h4_match.group(1).strip()
        elif line.strip() or (not line.strip() and current_paragraph_lines and line_number < len(lines) -1 and lines[line_number+1].strip()):
            current_paragraph_lines.append(line)
        elif current_paragraph_lines:
            chunks.extend(create_document_chunk(current_paragraph_lines, current_h1, current_h2, current_h3, current_h4, current_metadata))
            current_paragraph_lines = []

    if current_paragraph_lines:
        chunks.extend(create_document_chunk(current_paragraph_lines, current_h1, current_h2, current_h3, current_h4, current_metadata))
    
    if not chunks and content.strip():
        page_content = content.strip()
        prepended_text_parts = []
        if current_h1: prepended_text_parts.append(f"Title: {current_h1}")
        prepended_header = "\n".join(prepended_text_parts)
        final_page_content = f"{prepended_header}\n\n{page_content}" if prepended_header else page_content
        
        final_metadata = current_metadata.copy()
        if current_h1: final_metadata['doc_title_hierarchical'] = current_h1
        final_metadata['content_length'] = len(page_content)
        final_metadata['chunk_type'] = 'title_summary'
        
        # Clean up any bad date objects
        for key, value in final_metadata.items():
            if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
                logger.debug(f"Converting datetime.date to datetime.datetime for key '{key}' in source: {final_metadata.get('source', 'Unknown')}")
                final_metadata[key] = datetime.datetime.combine(value, datetime.time.min)
        
        # Create a single chunk if no headings were found
        chunks.append(Document(page_content=final_page_content, metadata=final_metadata))

    elif not chunks and not content.strip():
        logger.info(f"No content to chunk for source: {initial_metadata.get('source', 'Unknown')}")

    for i, chunk in enumerate(chunks):
        chunk.metadata['chunk_index'] = i
        chunk.metadata['is_title_chunk'] = (i == 0 and chunk.metadata.get('chunk_type') == 'title_summary')

    return chunks

def process_payload_documents(payload_docs: List[PayloadWebhookDoc]) -> List[Document]:
    """
    Processes a list of documents from Payload, converting them into Langchain Documents
    and then splitting them hierarchically.
    
    Note: This synchronous version does NOT generate FAQ synthetic questions.
    Use process_payload_documents_with_faq() for FAQ generation support.
    """
    all_chunks = []
    markdown_splitter = MarkdownTextSplitter()

    for payload_doc in payload_docs:
        published_date_dt = None
        if payload_doc.publishedDate:
            try:
                published_date_dt = datetime.datetime.fromisoformat(payload_doc.publishedDate.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                logger.warning(f"Could not parse 'publishedDate' string '{payload_doc.publishedDate}' for Payload doc ID {payload_doc.id}. Skipping date.")

        updated_at_dt = None
        raw_updated = getattr(payload_doc, "updatedAt", None)
        if raw_updated is not None:
            if isinstance(raw_updated, datetime.datetime):
                updated_at_dt = raw_updated
            elif isinstance(raw_updated, str):
                try:
                    updated_at_dt = datetime.datetime.fromisoformat(raw_updated.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    logger.warning(
                        "Could not parse 'updatedAt' for Payload doc ID %s. Skipping.",
                        payload_doc.id,
                    )

        initial_metadata = {
            "payload_id": payload_doc.id,
            "source": "payload",
            "content_type": "article",
            "doc_title": payload_doc.title,
            "author": payload_doc.author,
            "categories": payload_doc.category or [],
            "status": payload_doc.status,
            "published_date": published_date_dt,
            "updated_at": updated_at_dt,
            "slug": payload_doc.slug,
            "locale": "en"
        }
        
        langchain_doc = Document(
            page_content=payload_doc.markdown,
            metadata=initial_metadata
        )
        
        hierarchical_chunks = markdown_splitter.split_documents([langchain_doc])
        all_chunks.extend(hierarchical_chunks)
        
    logger.info(f"Processed {len(payload_docs)} Payload document(s) into {len(all_chunks)} chunks.")
    return all_chunks


async def process_payload_documents_with_faq(
    payload_docs: List[PayloadWebhookDoc],
    generate_faq: bool = True
) -> List[Document]:
    """
    Async version that processes Payload documents with optional FAQ generation.
    
    Uses the Parent Document Pattern: synthetic questions are indexed for search,
    but retrieval returns the full parent chunk.
    
    CRITICAL for CRUD lifecycle: Synthetic questions inherit payload_id from
    parent chunk, ensuring deletion by payload_id removes both.
    
    Args:
        payload_docs: List of Payload CMS documents to process
        generate_faq: Whether to generate synthetic FAQ questions (default: True)
        
    Returns:
        List of Document chunks (original + synthetic questions if enabled)
    """
    import os
    USE_FAQ_INDEXING = os.getenv("USE_FAQ_INDEXING", "true").lower() == "true"
    
    # First, get the base chunks using the standard processing
    base_chunks = process_payload_documents(payload_docs)
    
    # If FAQ generation is disabled, return base chunks
    if not generate_faq or not USE_FAQ_INDEXING:
        logger.info("FAQ generation disabled, returning base chunks only")
        return base_chunks
    
    # Generate synthetic questions
    try:
        from backend.services.faq_generator import FAQGenerator
        
        faq_generator = FAQGenerator()
        all_docs, parent_chunks_map = await faq_generator.process_chunks_with_questions(base_chunks)
        
        # Note: parent_chunks_map is not returned here but is built from MongoDB at retrieval time
        # The synthetic questions include parent_chunk_id in metadata for resolution
        
        logger.info(
            f"FAQ generation complete: {len(base_chunks)} base chunks → "
            f"{len(all_docs)} total docs ({len(all_docs) - len(base_chunks)} synthetic questions)"
        )
        return all_docs
        
    except Exception as e:
        logger.error(f"FAQ generation failed, returning base chunks only: {e}", exc_info=True)
        return base_chunks


def process_documents(docs: List[Document]) -> List[Document]:
    """
    Splits documents into smaller, hierarchically structured chunks for processing.
    Optimized for Markdown content by prepending titles/sections.
    Falls back to RecursiveCharacterTextSplitter for non-Markdown content.

    Args:
        docs: A list of documents to process.

    Returns:
        A list of split documents (chunks).
    """
    all_chunks = []
    markdown_splitter = MarkdownTextSplitter()

    for doc_idx, doc in enumerate(docs):
        source_identifier = doc.metadata.get('source', f'doc_index_{doc_idx}')
        
        is_markdown_like = False
        if doc.page_content:
            first_few_lines = doc.page_content.splitlines()[:20]
            if any("---" in line for line in first_few_lines[:5]):
                 is_markdown_like = True
            if not is_markdown_like and any(line.strip().startswith("#") for line in first_few_lines):
                 is_markdown_like = True
        
        if not is_markdown_like and 'source' in doc.metadata and isinstance(doc.metadata['source'], str) \
           and doc.metadata['source'].lower().endswith(('.md', '.markdown')):
            is_markdown_like = True

        if is_markdown_like:
            logger.info(f"Processing document '{source_identifier}' with MarkdownTextSplitter.")
            hierarchical_chunks = markdown_splitter.split_documents([doc]) 
            all_chunks.extend(hierarchical_chunks)
        else:
            logger.info(f"Processing document '{source_identifier}' with RecursiveCharacterTextSplitter (not identified as Markdown).")
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            split_docs_from_current = text_splitter.split_documents([doc])
            all_chunks.extend(split_docs_from_current)

    logger.info(f"Processed {len(docs)} original document(s) into {len(all_chunks)} chunks.")
    return all_chunks

# This function is kept for compatibility with how vector_store_manager expects to get the embeddings client.
def get_embedding_client():
    """
    Initializes and returns the local embedding service client.
    """
    service = EmbeddingService()
    return service.get_embeddings_client()


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.example'))


    sample_md_content = """---
title: Test Document
author: Cline
---
# Main Title from Content

This is the first paragraph.

## Section One

Some text in section one.

### Subsection A

Details for subsection A.

## Section Two

Text for section two.
"""
    sample_doc = Document(page_content=sample_md_content, metadata={"source": "sample_test.md"})
    
    processed_docs = process_documents([sample_doc])
    
    print(f"Number of documents after splitting: {len(processed_docs)}")
    for i, p_doc in enumerate(processed_docs):
        print(f"\n--- Chunk {i+1} ---")
        print(f"Content:\n{p_doc.page_content}")
        print(f"Metadata: {p_doc.metadata}")
    
    try:
        embeddings_client = get_embedding_client()
        print(f"\nSuccessfully initialized embeddings client for model: {embeddings_client.model}")
    except ValueError as e:
        print(f"\nError initializing embedding client: {e}")
        print("Ensure GOOGLE_API_KEY is set in your .env.example file.")
