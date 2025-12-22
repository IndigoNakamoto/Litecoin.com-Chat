#!/usr/bin/env python3
"""
Script to sync all published articles from Payload CMS to the vector store.
This is useful for initial setup or after clearing the vector store.
"""
import os
import sys
import requests
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from backend.data_models import PayloadWebhookDoc
from backend.data_ingestion.embedding_processor import process_payload_documents
from backend.data_ingestion.vector_store_manager import VectorStoreManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_dotenv_safe():
    """Load .env file if it exists."""
    dotenv_path = backend_dir / '.env'
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
        logger.info(f"Loaded environment variables from: {dotenv_path}")
    else:
        dotenv_example = backend_dir / '.env.example'
        if dotenv_example.exists():
            load_dotenv(dotenv_example)
            logger.info(f"Loaded environment variables from: {dotenv_example}")

def get_published_payload_articles(payload_url=None):
    """
    Fetch all published articles from Payload CMS.
    
    Args:
        payload_url: Base URL for Payload CMS (defaults to PAYLOAD_PUBLIC_SERVER_URL or localhost:3001)
    
    Returns:
        List of PayloadWebhookDoc objects
    """
    if payload_url is None:
        payload_url = os.getenv("PAYLOAD_PUBLIC_SERVER_URL")
        if not payload_url:
            # Detect if we're in Docker
            is_docker = (
                os.path.exists('/.dockerenv') or 
                os.getenv('HOSTNAME', '').startswith(('litecoin-', 'payload-')) or
                'DOCKER_CONTAINER' in os.environ
            )
            
            if is_docker:
                # Inside Docker: use service name (port 3000 is internal port)
                payload_url = "http://payload_cms:3000"
            else:
                # Local development: use localhost with exposed port
                payload_url = "http://localhost:3001"
    
    try:
        # Query Payload CMS for all published articles
        # Using depth=1 to get full document data including relationships
        response = requests.get(
            f"{payload_url}/api/articles?where[status][equals]=published&limit=1000&depth=1",
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            docs = data.get('docs', [])
            logger.info(f"Found {len(docs)} published articles in Payload CMS")
            
            # Convert to PayloadWebhookDoc objects
            payload_docs = []
            for doc in docs:
                try:
                    # Normalize the document data to match webhook format
                    normalized_doc = normalize_payload_doc(doc)
                    payload_doc = PayloadWebhookDoc(**normalized_doc)
                    payload_docs.append(payload_doc)
                except Exception as e:
                    logger.warning(f"Failed to parse article '{doc.get('title', 'unknown')}': {e}")
                    continue
            
            return payload_docs
        else:
            logger.error(f"Failed to fetch articles from Payload CMS: {response.status_code} - {response.text}")
            return []
    
    except Exception as e:
        logger.error(f"Error fetching articles from Payload CMS: {e}")
        return []

def normalize_payload_doc(doc):
    """
    Normalize a Payload CMS document to match the webhook format expected by PayloadWebhookDoc.
    """
    normalized = doc.copy()
    
    # Handle author field - can be object or string
    if 'author' in normalized:
        author = normalized['author']
        if isinstance(author, dict):
            normalized['author'] = author.get('id', author.get('_id', None))
        elif isinstance(author, str):
            # Already a string, keep as is
            pass
        else:
            normalized['author'] = None
    
    # Handle category field - can be list of objects or list of strings
    if 'category' in normalized:
        category = normalized['category']
        if isinstance(category, list):
            normalized_category = []
            for cat in category:
                if isinstance(cat, dict):
                    normalized_category.append(cat.get('id', cat.get('_id', None)))
                elif isinstance(cat, str):
                    normalized_category.append(cat)
            normalized['category'] = normalized_category
        else:
            normalized['category'] = []
    
    return normalized

def main():
    """Main function to sync all published Payload articles."""
    load_dotenv_safe()
    
    logger.info("Fetching published articles from Payload CMS...")
    payload_docs = get_published_payload_articles()
    
    if not payload_docs:
        logger.warning("No published articles found in Payload CMS. Nothing to sync.")
        return
    
    logger.info(f"Processing {len(payload_docs)} published articles...")
    
    # Initialize vector store manager
    logger.info("Initializing VectorStoreManager...")
    vector_store_manager = VectorStoreManager()
    
    # Process all documents
    all_chunks = []
    for payload_doc in payload_docs:
        try:
            logger.info(f"Processing article: {payload_doc.title} (ID: {payload_doc.id})")
            
            # Delete existing chunks for this article (in case of re-sync)
            deleted_count = vector_store_manager.delete_documents_by_metadata_field('payload_id', payload_doc.id)
            if deleted_count > 0:
                logger.info(f"  Deleted {deleted_count} existing chunks for this article")
            
            # Process the document into chunks
            processed_chunks = process_payload_documents([payload_doc])
            
            if processed_chunks:
                all_chunks.extend(processed_chunks)
                logger.info(f"  Generated {len(processed_chunks)} chunks")
            else:
                logger.warning(f"  No chunks generated for article: {payload_doc.title}")
        
        except Exception as e:
            logger.error(f"Error processing article '{payload_doc.title}': {e}", exc_info=True)
            continue
    
    if not all_chunks:
        logger.warning("No chunks were generated from any articles.")
        return
    
    # Add all chunks to the vector store in batches
    logger.info(f"\nAdding {len(all_chunks)} total chunks to vector store...")
    vector_store_manager.add_documents(all_chunks, batch_size=5)
    
    logger.info(f"✅ Successfully synced {len(payload_docs)} articles, creating {len(all_chunks)} chunks!")

if __name__ == "__main__":
    main()

