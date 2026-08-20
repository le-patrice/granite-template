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

from typing import Any, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
    where_clause: Optional[str] = None,
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
    # Format query vector as PostgreSQL vector literal: '[0.1, 0.2, ...]'
    vector_literal = "[" + ", ".join(f"{val:.6f}" for val in query_vector) + "]"

    select_cols_str = ", ".join(f"t.{col}" for col in select_columns)
    filter_sql = f"WHERE {where_clause}" if where_clause else ""

    # Common Table Expressions (CTEs) to rank lexical and semantic matches separately
    query_sql = f"""
    WITH lexical_scores AS (
        SELECT
            id,
            ROW_NUMBER() OVER (ORDER BY similarity({text_column}, :query_text) DESC) AS rank_lexical
        FROM {table_name}
        {filter_sql}
        ORDER BY similarity({text_column}, :query_text) DESC
        LIMIT {limit * 2}
    ),
    semantic_scores AS (
        SELECT
            id,
            ROW_NUMBER() OVER (ORDER BY {vector_column} <=> :query_vector::vector ASC) AS rank_semantic
        FROM {table_name}
        {filter_sql}
        ORDER BY {vector_column} <=> :query_vector::vector ASC
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
        {select_cols_str},
        f.rrf_score
    FROM fused_scores f
    JOIN {table_name} t ON f.id = t.id
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
