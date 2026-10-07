"""Tests for RAG semantic search and command indexing."""

import shutil
import tempfile
import pytest
from app.rag import CommandRAG


@pytest.fixture(scope="module")
def temp_rag() -> CommandRAG:
    """Create a temporary CommandRAG instance populated with test commands."""
    temp_dir = tempfile.mkdtemp()
    rag = CommandRAG(persist_dir=temp_dir, collection_name="test_commands", threshold=0.40)

    test_chunks = [
        {
            "id": "chunk_bgp",
            "source_file": "health_check_core.txt",
            "section_heading": "To check BGP status, they must be UP and connected",
            "command": "show router bgp summary",
            "note": "bgp check",
        },
        {
            "id": "chunk_iface",
            "source_file": "health_check_core.txt",
            "section_heading": "Verify router interfaces and operational state",
            "command": "show router interface",
            "note": "interface check",
        },
        {
            "id": "chunk_mtu_tpl",
            "source_file": "config_templates.txt",
            "section_heading": "Set MTU on an interface",
            "command": "configure port {interface} ethernet mtu {value}",
            "note": "",
        },
    ]
    rag.index_chunks(test_chunks)
    yield rag
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_rag_semantic_search_bgp(temp_rag: CommandRAG) -> None:
    """Verify semantic search retrieves bgp command with source_file."""
    results = temp_rag.search("show BGP neighbour summary", k=1)
    assert len(results) > 0
    match = results[0]
    assert "show router bgp summary" in match["command"]
    assert match["source_file"] == "health_check_core.txt"
    assert match["score"] >= 0.40


def test_rag_nonsense_query_returns_not_found(temp_rag: CommandRAG) -> None:
    """Verify nonsense query does not meet threshold and returns empty list."""
    results = temp_rag.search("quantum celestial banana spaceship warp drive", k=3)
    assert results == []
