import os
import sys
from dotenv import load_dotenv

# --- Load environment variables FIRST ---
# This section must be at the very top, before any other imports that might
# depend on these environment variables (especially GOOGLE_API_KEY).

# Determine the base directory (backend/)
backend_dir = os.path.dirname(os.path.abspath(__file__))

# Path to the actual .env file
dotenv_path_actual = os.path.join(backend_dir, '.env')
# Path to the example .env file
dotenv_path_example = os.path.join(backend_dir, '.env.example')

# Prioritize .env over .env.example
if os.path.exists(dotenv_path_actual):
    print(f"Loading environment variables from: {dotenv_path_actual}")
    load_dotenv(dotenv_path=dotenv_path_actual, override=True)
elif os.path.exists(dotenv_path_example):
    print(f"Loading environment variables from: {dotenv_path_example} (as .env was not found)")
    load_dotenv(dotenv_path=dotenv_path_example, override=True)
else:
    print("Warning: No .env or .env.example file found in the backend directory. Critical environment variables might be missing.")

# --- Modify sys.path to allow direct imports from project root and data_ingestion ---
# Add project root (parent of backend/) to sys.path for rag_pipeline import
project_root_dir = os.path.dirname(backend_dir)
sys.path.insert(0, project_root_dir)
# Add backend directory itself if needed, though direct imports from data_ingestion should work if backend is in PYTHONPATH
# sys.path.insert(0, backend_dir) # Usually covered by project_root_dir for submodules

# --- Now proceed with other imports ---
import pytest
import requests
import json
import traceback # Added for detailed error printing
import time # Added for sleep
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Local project imports (should now find modules and have .env loaded)
from backend.data_ingestion.vector_store_manager import VectorStoreManager
from backend.data_ingestion.embedding_processor import MarkdownTextSplitter
# Try to import litecoin_docs_loader, skip tests if not available
try:
    from backend.data_ingestion.litecoin_docs_loader import load_litecoin_docs
    LITECOIN_DOCS_LOADER_AVAILABLE = True
except ImportError:
    LITECOIN_DOCS_LOADER_AVAILABLE = False
    load_litecoin_docs = None
from backend.rag_pipeline import RAGPipeline # RAGPipeline checks for GOOGLE_API_KEY at import time


# Define the URL of the FastAPI chat endpoint (for the original test)
BACKEND_BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_URL = f"{BACKEND_BASE_URL}/api/v1/chat"

# Define a sample query for the original test
SAMPLE_QUERY = "What is Litecoin?"

# Constants for the new hierarchical test
TEST_MD_FILENAME = "sample_for_hierarchical_test.md"
TEST_MD_PATH = os.path.join(backend_dir, "data_ingestion", "test_data", TEST_MD_FILENAME) # Corrected path
TEST_QUERY_HIERARCHICAL = "Deeper Detail Alpha"
EXPECTED_HIERARCHICAL_PREFIX = f"Title: Main Document Title\nSection: Section 2: Second Major Topic\nSubsection: Subsection 2.1: Detail C\nSub-subsection: Sub-subsection 2.1.1: Deeper Detail Alpha"

# Constants for the new metadata filtering test
TEST_METADATA_MD_FILENAME = "sample_for_metadata_test.md"
TEST_METADATA_MD_PATH = os.path.join(backend_dir, "data_ingestion", "test_data", TEST_METADATA_MD_FILENAME)
TEST_METADATA_AUTHOR = "Test Author"
TEST_METADATA_TAG = "testing"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hierarchical_chunking_and_retrieval():
    """
    Tests the hierarchical chunking and retrieval for Markdown documents.
    
    This is an integration test that requires:
    - Google API key for embeddings
    - MongoDB connection
    - NOT using Infinity embeddings mode (USE_INFINITY_EMBEDDINGS=false)
    """
    # Skip if using Infinity embeddings (incompatible with this test)
    if os.getenv("USE_INFINITY_EMBEDDINGS", "false").lower() == "true":
        pytest.skip("Test requires Google embeddings, not compatible with Infinity embeddings mode")
    
    # Skip if no Google API key
    if not os.getenv("GOOGLE_API_KEY"):
        pytest.skip("Test requires GOOGLE_API_KEY environment variable")
    
    print("\n--- Starting Hierarchical Chunking and Retrieval Test ---")

    # 1. Initialize components
    print("Initializing components...")
    vector_store_manager = None # Define before try block
    try:
        # VectorStoreManager and RAGPipeline will use env vars loaded at the start
        # Using the default collection "litecoin_docs" as per user suggestion for testing
        vector_store_manager = VectorStoreManager(collection_name="litecoin_docs") 
        
        rag_pipeline_instance = RAGPipeline(vector_store_manager=vector_store_manager)
        
        doc_embeddings_model = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            task_type="retrieval_document"
        )
        markdown_splitter = MarkdownTextSplitter(
            chunk_size=1000, 
            chunk_overlap=200
        )

    except Exception as e:
        print(f"Error initializing components: {e}")
        print("Traceback:")
        print(traceback.format_exc())
        print("Ensure your .env file is correctly set up with API keys (GOOGLE_API_KEY) and MongoDB URI (MONGO_URI).")
        return

    try:
        # 2. Clear the vector store for a clean base
        print(f"Clearing test collection: '{vector_store_manager.collection_name}'...")
        vector_store_manager.clear_all_documents() # Clear the dedicated test collection
        print(f"Cleared test collection.")

        # 3. Ingest the sample_for_hierarchical_test.md file
        print(f"Ingesting test Markdown file: {TEST_MD_PATH}")
        if not os.path.exists(TEST_MD_PATH):
            print(f"Test file not found: {TEST_MD_PATH}")
            return

        with open(TEST_MD_PATH, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # Initial metadata passed to the splitter
        initial_doc_metadata = {"source": TEST_MD_FILENAME, "title": "Main Document Title"}
        print(f"Initial metadata for splitting: {initial_doc_metadata}")
        documents = markdown_splitter.split_text(md_content, metadata=initial_doc_metadata)
        
        if not documents:
            print("No documents were created after splitting. Check the splitter logic and MD file.")
            return

        print(f"Generated {len(documents)} chunks for ingestion.")

        # --- Debug: Print metadata of documents just before adding to vector store ---
        print("\n--- Documents to be Ingested (with metadata) ---")
        for i, doc_to_add in enumerate(documents):
            print(f"Doc {i+1} to add - Metadata: {doc_to_add.metadata}")
            # print(f"Doc {i+1} to add - Content: {doc_to_add.page_content[:100]}...") # Optional: print content snippet
        print("--- End of Documents to be Ingested ---")
        # --- End Debug ---

        vector_store_manager.add_documents(documents, embeddings_model=doc_embeddings_model)
        print("Test document ingested into dedicated test collection.")
        
        # Add a more significant delay to allow for potential eventual consistency and vector indexing
        # print("Waiting for 60 seconds for indexing...")
        time.sleep(10) # Wait for 60 seconds

        # --- Debug: Print all ingested chunks and their metadata using direct pymongo find ---
        print("\n--- Ingested Chunks for Debugging (Direct MongoDB Find) ---")
        try:
            # Access the pymongo collection directly from the VectorStoreManager
            mongo_collection = vector_store_manager.collection 
            # Try to find ALL documents in the collection first
            all_docs_in_collection_cursor = mongo_collection.find({})
            all_docs_in_collection_list = list(all_docs_in_collection_cursor)
            print(f"Direct find found {len(all_docs_in_collection_list)} documents in collection '{mongo_collection.name}' before filtering.")

            # Then, filter for our specific test documents from this list or re-query
            debug_docs_cursor = mongo_collection.find({"metadata.source": TEST_MD_FILENAME}) 
            retrieved_debug_docs = list(debug_docs_cursor)
            
            if not retrieved_debug_docs:
                print(f"Could not retrieve ingested documents for debugging using specific find for source: {TEST_MD_FILENAME}.")
                if all_docs_in_collection_list:
                    print("However, some documents were found in the collection without the source filter. Listing their metadata:")
                    for i, doc_data in enumerate(all_docs_in_collection_list):
                        print(f"  Unfiltered Doc {i+1} Metadata: {doc_data.get('metadata')}")
            else:
                print(f"Retrieved {len(retrieved_debug_docs)} documents for debugging using specific find for source: {TEST_MD_FILENAME} from collection '{vector_store_manager.collection_name}'.")
                for i, doc_data in enumerate(retrieved_debug_docs):
                    print(f"Doc {i+1} Metadata: {doc_data.get('metadata')}")
                    text_key = getattr(vector_store_manager.vector_store, 'text_key', 'text') 
                    print(f"Doc {i+1} Content (from '{text_key}' field):\n'''\n{doc_data.get(text_key)}\n'''\n")
        except Exception as debug_e:
            print(f"Error during direct MongoDB find for debugging: {debug_e}")
            print(traceback.format_exc())
        print("--- End of Ingested Chunks (Direct MongoDB Find) ---")
        # --- End Debug ---

        # 4. Verify that the chunks stored in the vector database contain the prepended hierarchical titles
        print("Verifying chunk content in vector store...")
        retrieved_docs_for_verification = vector_store_manager.vector_store.similarity_search(
            query=TEST_QUERY_HIERARCHICAL, 
            k=1
        )

        if not retrieved_docs_for_verification:
            print(f"Verification failed: No documents retrieved for query '{TEST_QUERY_HIERARCHICAL}'.")
        else:
            retrieved_chunk_content = retrieved_docs_for_verification[0].page_content
            print(f"Content of retrieved chunk for verification: '{retrieved_chunk_content[:400]}...'")
            if retrieved_chunk_content.startswith(EXPECTED_HIERARCHICAL_PREFIX) and \
               "Deeper Detail Alpha" in retrieved_chunk_content:
                print("Verification successful: Hierarchical prefix and content found in the retrieved chunk.")
            else:
                print("Verification failed: Hierarchical prefix NOT found or content mismatch.")
                print(f"Expected prefix part: '{EXPECTED_HIERARCHICAL_PREFIX}'")
                print(f"Actual start of content: '{retrieved_chunk_content[:len(EXPECTED_HIERARCHICAL_PREFIX) + 50]}'")
            
        # 5. Formulate a specific query and assert that the correct, context-rich chunk is retrieved via RAGPipeline
        print(f"Performing RAG query via RAGPipeline: '{TEST_QUERY_HIERARCHICAL}'")
        answer, sources, metadata = await rag_pipeline_instance.aquery(TEST_QUERY_HIERARCHICAL, chat_history=[])
        
        print(f"RAG Answer: {answer}")
        if sources:
            print(f"Retrieved source content for RAG: '{sources[0].page_content[:400]}...'")
            if sources[0].page_content.startswith(EXPECTED_HIERARCHICAL_PREFIX) and \
               "Deeper Detail Alpha" in sources[0].page_content:
                print("Assertion successful: Correct context-rich chunk retrieved by RAG pipeline.")
            else:
                print("Assertion failed: RAG pipeline did not retrieve the expected chunk or prefix is missing.")
        else:
            print("Assertion failed: RAG pipeline did not return any sources for the specific query.")

    except Exception as e:
        print(f"An error occurred during test execution: {e}")
        print("Traceback:")
        print(traceback.format_exc())
    finally:
        # 6. Clean up: Delete the temporary test data from the vector store
        if vector_store_manager: 
            print(f"Cleaning up: Deleting all documents from test collection '{vector_store_manager.collection_name}'...")
            vector_store_manager.clear_all_documents()
            print("Test data cleanup completed.")

    print("--- Hierarchical Chunking and Retrieval Test Finished ---")


@pytest.mark.skipif(not LITECOIN_DOCS_LOADER_AVAILABLE, reason="litecoin_docs_loader module not available")
def test_metadata_filtering():
    """
    Tests the ability to filter vector searches based on document metadata.
    This test uses the main 'litecoin_docs' collection, assuming the necessary
    vector search index with filterable fields has been created on it.
    """
    print("\n--- Starting Metadata Filtering Test ---")
    vector_store_manager = None
    try:
        print("Initializing components for metadata test...")
        # Reason: Using the main collection where the user has been instructed to create the index.
        vector_store_manager = VectorStoreManager(collection_name="litecoin_docs")
        doc_embeddings_model = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            task_type="retrieval_document"
        )
        # markdown_splitter = MarkdownTextSplitter() # No longer needed for this test

        # 1. Clean up any previous test runs for this specific file
        print(f"Cleaning up any pre-existing test data for source: {TEST_METADATA_MD_FILENAME}...")
        vector_store_manager.delete_documents_by_metadata({"source": TEST_METADATA_MD_FILENAME})

        # 2. Ingest the sample metadata test file using the correct loader
        print(f"Ingesting test Markdown file: {TEST_METADATA_MD_PATH} using load_litecoin_docs")
        # Use the dedicated loader which handles frontmatter parsing
        documents = load_litecoin_docs(TEST_METADATA_MD_PATH)

        if not documents:
            print(f"No documents loaded from {TEST_METADATA_MD_PATH}. Check file path and content.")
            assert False, "Failed to load test document."

        # The loader returns a list of Documents, each with parsed metadata.
        # We still need to split these documents into smaller chunks if necessary,
        # but the metadata is now correctly attached to the initial Document objects.
        # The add_documents method in VectorStoreManager should handle the splitting
        # and embedding, preserving the metadata for each chunk.

        # --- Debug: Print metadata of documents just before adding to vector store ---
        print("\n--- Documents to be Ingested (with parsed metadata) ---")
        for i, doc_to_add in enumerate(documents):
            print(f"Doc {i+1} to add - Metadata: {doc_to_add.metadata}")
            # print(f"Doc {i+1} to add - Content: {doc_to_add.page_content[:100]}...") # Optional: print content snippet
        print("--- End of Documents to be Ingested ---")
        # --- End Debug ---

        # Add the documents. The add_documents method will handle splitting and embedding.
        vector_store_manager.add_documents(documents, embeddings_model=doc_embeddings_model)
        # Add again to test deletion logic later
        vector_store_manager.add_documents(documents, embeddings_model=doc_embeddings_model)
        print("Test document with metadata ingested.")

        # Add a delay to allow for potential indexing of metadata fields
        print("Waiting for 10 seconds for potential metadata indexing...")
        time.sleep(10)

        # 3. Test filtering by 'author'
        # Reason: Metadata is stored at the top level in the MongoDB document.
        print(f"\nTesting filter: author == '{TEST_METADATA_AUTHOR}'")
        retrieved_docs_author = vector_store_manager.vector_store.similarity_search(
            "filtering", k=5, pre_filter={"author": {"$eq": TEST_METADATA_AUTHOR}}
        )

        print(f"Retrieved {len(retrieved_docs_author)} documents with author filter.")
        assert len(retrieved_docs_author) > 0, "Should retrieve documents with author filter"
        for doc in retrieved_docs_author:
            print(f"  - Doc author: {doc.metadata.get('author')}")
            assert doc.metadata.get('author') == TEST_METADATA_AUTHOR
        print("Assertion successful: All retrieved documents have the correct author.")

        # 4. Test filtering by 'tags' (which is an array)
        print(f"\nTesting filter: tags contains '{TEST_METADATA_TAG}'")
        retrieved_docs_tags = vector_store_manager.vector_store.similarity_search(
            "filtering", k=5, pre_filter={"tags": {"$in": [TEST_METADATA_TAG]}}
        )

        print(f"Retrieved {len(retrieved_docs_tags)} documents with tags filter.")
        assert len(retrieved_docs_tags) > 0, "Should retrieve documents with tags filter"
        for doc in retrieved_docs_tags:
            print(f"  - Doc tags: {doc.metadata.get('tags')}")
            assert TEST_METADATA_TAG in doc.metadata.get('tags', [])
        print("Assertion successful: All retrieved documents contain the correct tag.")

        # 5. Test filtering with a non-matching author
        print(f"\nTesting filter: author == 'NonExistent Author'")
        retrieved_docs_no_match = vector_store_manager.vector_store.similarity_search(
            "filtering", k=5, pre_filter={"author": {"$eq": "NonExistent Author"}}
        )
        print(f"Retrieved {len(retrieved_docs_no_match)} documents with non-matching filter.")
        assert len(retrieved_docs_no_match) == 0, "Should retrieve 0 documents with non-matching filter"
        print("Assertion successful: No documents retrieved for non-matching author.")

    except Exception as e:
        print(f"An error occurred during metadata filtering test: {e}")
        print(traceback.format_exc())
        assert False, "Test failed due to an exception."
    finally:
        if vector_store_manager:
            # Clean up by deleting only the documents created during this test run.
            print(f"Cleaning up: Deleting test documents for source: {TEST_METADATA_MD_FILENAME}...")
            vector_store_manager.delete_documents_by_metadata({"source": TEST_METADATA_MD_FILENAME})
            print("Test data cleanup completed.")

    print("--- Metadata Filtering Test Finished ---")


def run_original_test():
    """
    Sends a sample query to the RAG pipeline via HTTP API and prints the response.
    This test requires the FastAPI server to be running.
    """
    print(f"\n--- Starting Original RAG Pipeline Test (via API) ---")
    print(f"Sending query to RAG pipeline API: '{SAMPLE_QUERY}'")
    
    payload = {"query": SAMPLE_QUERY}
    
    try:
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        response_data = response.json()
        
        print("\n--- Answer from RAG Pipeline API ---")
        print(response_data.get("answer", "N/A"))
        print("\n--- Sources from API ---")
        sources_api = response_data.get("sources", [])
        if sources_api:
            for i, source_doc in enumerate(sources_api):
                page_content = source_doc.get('page_content', 'N/A')
                metadata = source_doc.get('metadata', {})
                print(f"\nSource {i+1}:")
                print(f"  Content: {page_content[:200]}...")
                print(f"  Metadata: {metadata}")
        else:
            print("No sources provided by API.")
        
    except requests.exceptions.RequestException as e:
        print(f"\nError connecting to the API at {API_URL}: {e}")
        print("Please ensure the FastAPI backend server is running.")
    except json.JSONDecodeError:
        print("\nError: Could not decode JSON response from the server.")
        print(f"Raw response content: {response.text if 'response' in locals() else 'Response object not available'}")
    finally:
        print("--- Original RAG Pipeline Test (via API) Finished ---")


if __name__ == "__main__":
    print("--- Starting RAG Pipeline Test Script ---")

    # Test query for content ingested from the deep_research directory
    print("\n--- Starting Direct RAG Pipeline Query Test for Deep Research Content ---")
    try:
        print("Initializing RAGPipeline for validation test...")
        # VectorStoreManager will use the default 'litecoin_docs' collection
        vs_manager = VectorStoreManager() 
        rag_pipeline = RAGPipeline(vector_store_manager=vs_manager)
        
        # This query targets content that should only exist in the deep_research articles
        validation_query = "What is Mimblewimble CoinSwap?"
        print(f"Sending validation query to RAG pipeline: '{validation_query}'")
        
        import asyncio
        answer, sources, metadata = asyncio.run(rag_pipeline.aquery(validation_query, chat_history=[]))
        
        print("\n--- Answer from RAG Pipeline (Validation Query) ---")
        print(answer)
        print("\n--- Sources (Validation Query) ---")
        if sources:
            for i, source_doc in enumerate(sources):
                print(f"\nSource {i+1}:")
                print(f"  Content: {source_doc.page_content[:400]}...")
                print(f"  Metadata: {source_doc.metadata}")
        else:
            print("No sources returned for the validation query. This may indicate an issue with ingestion or retrieval.")
            
    except Exception as e:
        print(f"Error during direct RAG pipeline query test: {e}")
        print(traceback.format_exc())
    finally:
        print("--- Direct RAG Pipeline Query Test for Deep Research Content Finished ---")
    
    print("\n--- RAG Pipeline Test Script Finished ---")
