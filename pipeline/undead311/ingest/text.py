"""Free-text clean-up at ingest (REQ-ING-2, ops#214).

The city's street names arrive HTML-escaped ("INTERSECTION Call St &amp; Carolina Ave"). `decode_entities` turns
them back into plain text once, at ingest, so every later table, card and map label shows "&". It decodes a single
level only: "&amp;amp;" becomes "&amp;", never "&". `register_text_udfs` adds it to a DuckDB connection as
`undead_unescape(varchar)`, which the full-data normalizer and the sample loaders call on the street column.
"""

from __future__ import annotations

import html

import duckdb


def decode_entities(text: str | None) -> str | None:
    """Plain text for an HTML-escaped value, decoded one level; None and "" pass through (REQ-ING-2, ops#214)."""
    if not text:
        return text
    return html.unescape(text) if "&" in text else text


def register_text_udfs(con: duckdb.DuckDBPyConnection) -> None:
    """Register `undead_unescape` on `con`; a second call on the same connection is a no-op."""
    try:
        con.create_function("undead_unescape", decode_entities, ["VARCHAR"], "VARCHAR")
    except duckdb.NotImplementedException:
        pass  # already registered on this connection
