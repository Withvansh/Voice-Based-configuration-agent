"""Parser for plain-text health-check and configuration template files."""

import os
import re
from typing import Any, Dict, List, Set


OPERATOR_PATTERNS = [
    (re.compile(r"\bVodafone\s+Idea\b", re.IGNORECASE), "demo project"),
    (re.compile(r"\bVoda\s*&\s*Idea\b", re.IGNORECASE), "demo project"),
    (re.compile(r"\bVIL\b", re.IGNORECASE), "demo project"),
    (re.compile(r"\bVoda\b", re.IGNORECASE), "demo project"),
    (re.compile(r"\bIdea\b", re.IGNORECASE), "demo project"),
    (re.compile(r"\bAgra\b", re.IGNORECASE), "demo project"),
]


def sanitise_text(text: str) -> str:
    """Replace operator and project identifiers with neutral words."""
    result = text
    for pattern, replacement in OPERATOR_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def parse_health_check_file(file_path: str, sanitise: bool = True) -> List[Dict[str, Any]]:
    """Parse a plain-text health check or template file into structured chunks.

    Format rules:
    - First block with '+++' underline is the document title.
    - Subsequent blocks with '+++' underline are section headings.
    - Lines after '+++' are commands until the next heading.
    - Commands can have trailing '>> note'.
    - Deduplicates identical (source_file, command) pairs.
    """
    if not os.path.exists(file_path):
        return []

    source_file = os.path.basename(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip() for line in f]

    plus_pattern = re.compile(r"^\+{3,}\s*$")

    # Locate all banner indices
    banner_indices: List[int] = [i for i, line in enumerate(lines) if plus_pattern.match(line)]
    if not banner_indices:
        return []

    # First banner defines the file title
    first_banner = banner_indices[0]
    title_lines = [l.strip() for l in lines[:first_banner] if l.strip()]
    raw_file_title = "\n".join(title_lines)
    file_title = sanitise_text(raw_file_title) if sanitise else raw_file_title

    chunks: List[Dict[str, Any]] = []
    seen_commands: Set[str] = set()

    for idx, b_idx in enumerate(banner_indices[1:], start=1):
        prev_b_idx = banner_indices[idx - 1]

        # Heading lines are contiguous non-blank lines right before this banner
        heading_lines: List[str] = []
        cur = b_idx - 1
        while cur > prev_b_idx and lines[cur].strip():
            heading_lines.append(lines[cur].strip())
            cur -= 1
        heading_lines.reverse()
        raw_heading = "\n".join(heading_lines)

        # Lines before the heading lines (and after prev_b_idx) are commands of previous banner
        if idx > 1:
            prev_heading = current_heading  # type: ignore[name-defined]
            prev_cmd_lines = lines[prev_b_idx + 1 : cur + 1]
            _extract_commands(
                prev_cmd_lines,
                source_file,
                prev_heading,
                file_title,
                chunks,
                seen_commands,
                sanitise,
            )

        current_heading = sanitise_text(raw_heading) if sanitise else raw_heading

    # Extract commands for the final banner
    if len(banner_indices) > 1:
        last_b_idx = banner_indices[-1]
        last_cmd_lines = lines[last_b_idx + 1 :]
        _extract_commands(
            last_cmd_lines,
            source_file,
            current_heading,
            file_title,
            chunks,
            seen_commands,
            sanitise,
        )

    return chunks


def _extract_commands(
    lines: List[str],
    source_file: str,
    section_heading: str,
    file_title: str,
    chunks: List[Dict[str, Any]],
    seen_commands: Set[str],
    sanitise: bool,
) -> None:
    """Extract individual command lines and append chunks."""
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        if ">>" in cleaned:
            parts = cleaned.split(">>", 1)
            command = parts[0].strip()
            raw_note = parts[1].strip()
        else:
            command = cleaned
            raw_note = ""

        note = sanitise_text(raw_note) if sanitise else raw_note

        if not command:
            continue

        dedup_key = f"{source_file}::{command}"
        if dedup_key in seen_commands:
            continue
        seen_commands.add(dedup_key)

        chunk_id = f"{source_file}_{len(chunks) + 1}"
        chunks.append({
            "id": chunk_id,
            "source_file": source_file,
            "section_heading": section_heading,
            "command": command,
            "note": note,
            "file_title": file_title,
        })
