"""
Hybrid Search utility with Reciprocal Rank Fusion (RRF).

Combines Lexical Full-Text Search (via pg_trgm / tsvector) and Semantic Vector
Search (via pgvector HNSW cosine distance) into a unified, balanced ranking.

Theoretical Formula:
    RRF_Score(d) = \\sum_{m \\in M} \\frac{1}{k + r_m(d)}
where:
    • k is the smoothing constant (default: 60)
    • r_m(d) is the rank of document d in modality m (text vs vector)
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str) -> str:
    cleaned = name.strip()
    if not _IDENTIFIER_RE.match(cleaned):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{cleaned}"'


async def hybrid_search_rrf(
    session: AsyncSession,
    table_name: str,
    text_column: str,
    vector_column: str,
    query_text: str,
    query_vector: Sequence[float],
    select_columns: list[str],
    rrf_k: int = 60,
    limit: int = 20,
    where_clause: str | None = None,
) -> list[dict[str, Any]]:
    """
    Executes a Hybrid RRF query combining pg_trgm and pgvector.

    Parameters:
        session: Active SQLAlchemy AsyncSession.
        table_name: SQL table name.
        text_column: Text column indexed with GIN/pg_trgm.
        vector_column: Vector embedding column indexed with HNSW (vector(N)).
        query_text: User search phrase.
        query_vector: Dense embedding float array.
        select_columns: List of columns to return in result dicts.
        rrf_k: RRF smoothing constant (standard default is 60).
        limit: Max number of fused results.
        where_clause: Optional SQL filter condition (e.g. "is_active = true").
    """
    # Sanitize and quote all SQL identifiers
    safe_table = _validate_identifier(table_name)
    safe_text_col = _validate_identifier(text_column)
    safe_vector_col = _validate_identifier(vector_column)
    safe_select_cols = ", ".join(f"t.{_validate_identifier(col)}" for col in select_columns)

    if where_clause:
        # Reject semicolons, comment syntax, or DDL attempts in where clauses
        if re.search(r"[;\-\-]|(/\*)|(\*/)", where_clause):
            raise ValueError(f"Dangerous characters detected in where_clause: {where_clause!r}")
        filter_sql = f"WHERE {where_clause}"
    else:
        filter_sql = ""

    # Format query vector as PostgreSQL vector literal: '[0.1, 0.2, ...]'
    vector_literal = "[" + ", ".join(f"{val:.6f}" for val in query_vector) + "]"

    # Common Table Expressions (CTEs) to rank lexical and semantic matches separately
    query_sql = f"""
    WITH lexical_scores AS (
        SELECT
            id,
            ROW_NUMBER() OVER (ORDER BY similarity({safe_text_col}, :query_text) DESC) AS rank_lexical
        FROM {safe_table}
        {filter_sql}
        ORDER BY similarity({safe_text_col}, :query_text) DESC
        LIMIT {limit * 2}
    ),
    semantic_scores AS (
        SELECT
            id,
            ROW_NUMBER() OVER (ORDER BY {safe_vector_col} <=> :query_vector::vector ASC) AS rank_semantic
        FROM {safe_table}
        {filter_sql}
        ORDER BY {safe_vector_col} <=> :query_vector::vector ASC
        LIMIT {limit * 2}
    ),
    fused_scores AS (
        SELECT
            COALESCE(l.id, s.id) AS id,
            (
                COALESCE(1.0 / (:rrf_k + l.rank_lexical), 0.0) +
                COALESCE(1.0 / (:rrf_k + s.rank_semantic), 0.0)
            ) AS rrf_score
        FROM lexical_scores l
        FULL OUTER JOIN semantic_scores s ON l.id = s.id
    )
    SELECT
        {safe_select_cols},
        f.rrf_score
    FROM fused_scores f
    JOIN {safe_table} t ON f.id = t.id
    ORDER BY f.rrf_score DESC
    LIMIT :limit;
    """

    stmt = text(query_sql)
    result = await session.execute(
        stmt,
        {
            "query_text": query_text,
            "query_vector": vector_literal,
            "rrf_k": rrf_k,
            "limit": limit,
        },
    )

    rows = result.mappings().all()
    return [dict(row) for row in rows]
