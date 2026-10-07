"""Ingest script to parse raw files and populate ChromaDB."""

import glob
import os
import sys

# Ensure app package is importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.parser import parse_health_check_file
from app.rag import CommandRAG


def ingest_all(
    raw_dir: str = os.path.join(PROJECT_ROOT, "data", "raw"),
    chroma_dir: str = os.path.join(PROJECT_ROOT, "chroma_db"),
) -> None:
    """Parse all .txt files in raw_dir and index into ChromaDB."""
    rag = CommandRAG(persist_dir=chroma_dir)
    txt_files = sorted(glob.glob(os.path.join(raw_dir, "*.txt")))

    if not txt_files:
        print(f"No .txt files found in {raw_dir}")
        return

    total_chunks = 0
    print(f"Starting ingestion from {raw_dir}...")
    for file_path in txt_files:
        filename = os.path.basename(file_path)
        chunks = parse_health_check_file(file_path, sanitise=True)
        if chunks:
            count = rag.index_chunks(chunks)
            print(f"Loaded {count} chunks from {filename}")
            total_chunks += count
        else:
            print(f"No valid chunks parsed from {filename}")

    print(f"Ingestion complete. Total chunks indexed: {total_chunks}")


if __name__ == "__main__":
    ingest_all()
