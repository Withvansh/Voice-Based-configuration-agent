"""Tests for health check file parser and sanitisation."""

import os
import tempfile
import pytest
from app.parser import parse_health_check_file, sanitise_text


def test_sanitise_text() -> None:
    """Verify operator and city names are replaced with neutral terms."""
    raw = "Vodafone Idea network in Agra site with VIL and Voda & Idea subscribers"
    cleaned = sanitise_text(raw)
    assert "Vodafone Idea" not in cleaned
    assert "VIL" not in cleaned
    assert "Agra" not in cleaned
    assert "Voda" not in cleaned
    assert "Idea" not in cleaned
    assert "demo project" in cleaned


def test_parse_health_check_file() -> None:
    """Verify section headings, commands, notes, and deduplication."""
    content = """Sample Router Document
++++++++++++++++++++++

BGP Peering Section
(Note: Verify all VIL peers)
++++++++++++++++++++++++++++
show router bgp summary >> check BGP status
show router bgp summary >> duplicate should be dropped

Interface Section
+++++++++++++++++
show router interface
"""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        chunks = parse_health_check_file(tmp_path, sanitise=True)
        # Should have 2 unique commands
        assert len(chunks) == 2

        bgp_chunk = chunks[0]
        assert bgp_chunk["file_title"] == "Sample Router Document"
        assert "BGP Peering Section" in bgp_chunk["section_heading"]
        assert "demo project" in bgp_chunk["section_heading"]  # VIL sanitised
        assert bgp_chunk["command"] == "show router bgp summary"
        assert bgp_chunk["note"] == "check BGP status"

        iface_chunk = chunks[1]
        assert iface_chunk["command"] == "show router interface"
        assert iface_chunk["note"] == ""
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
