#!/usr/bin/env python3
"""
Simple script to rebuild the vector store by processing all markdown files
from the knowledge base directories.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from langchain_core.documents import Document
from data_ingestion.embedding_processor import process_documents
from data_ingestion.vector_store_manager import VectorStoreManager

def load_dotenv_safe():
    """Load .env file if it exists."""
    dotenv_path = backend_dir / '.env'
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
        print(f"Loaded environment variables from: {dotenv_path}")
    else:
        dotenv_example = backend_dir / '.env.example'
        if dotenv_example.exists():
            load_dotenv(dotenv_example)
            print(f"Loaded environment variables from: {dotenv_example}")

def find_markdown_files(root_dir: Path):
    """Find all markdown files in the knowledge base directories."""
    markdown_files = []
    knowledge_base_dirs = [
        root_dir / "docs" / "knowledge_base" / "articles",
        root_dir / "docs" / "knowledge_base" / "deep_research"
    ]
    
    for kb_dir in knowledge_base_dirs:
        if kb_dir.exists():
            print(f"Scanning directory: {kb_dir}")
            for file_path in kb_dir.glob("*.md"):
                if not file_path.name.startswith("_"):
                    markdown_files.append(file_path)
            for file_path in kb_dir.glob("*.markdown"):
                if not file_path.name.startswith("_"):
                    markdown_files.append(file_path)
        else:
            print(f"Directory not found: {kb_dir}")
    
    return markdown_files

def main():
    """Main function to rebuild the vector store."""
    # Determine project root (two levels up from this script)
    project_root = backend_dir.parent
    
    load_dotenv_safe()
    
    print("Initializing VectorStoreManager...")
    vector_store_manager = VectorStoreManager()
    
    print("Clearing existing vector store...")
    deleted_count = vector_store_manager.clear_all_documents()
    print(f"Cleared {deleted_count} documents from vector store.")
    
    print("\nFinding markdown files...")
    markdown_files = find_markdown_files(project_root)
    print(f"Found {len(markdown_files)} markdown files to process.")
    
    if not markdown_files:
        print("No markdown files found. Exiting.")
        return
    
    # Load all markdown files as Documents
    documents = []
    for file_path in markdown_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create Document with metadata
            doc = Document(
                page_content=content,
                metadata={
                    "source": str(file_path.relative_to(project_root)),
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "status": "published"  # Mark as published so RAG pipeline includes it
                }
            )
            documents.append(doc)
            print(f"Loaded: {file_path.name}")
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    if not documents:
        print("No documents to process. Exiting.")
        return
    
    print(f"\nProcessing {len(documents)} documents into chunks...")
    processed_chunks = process_documents(documents)
    print(f"Generated {len(processed_chunks)} chunks from {len(documents)} documents.")
    
    print("\nAdding chunks to vector store...")
    vector_store_manager.add_documents(processed_chunks, batch_size=5)
    
    print(f"\n✅ Successfully rebuilt vector store with {len(processed_chunks)} chunks!")

if __name__ == "__main__":
    main()

