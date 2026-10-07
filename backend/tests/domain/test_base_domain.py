"""
Tests for shared domain base constructs:
1. PaginationEnvelope (items, total, limit, offset, pages calculation)
2. enum_check_constraint (DDL CheckConstraint creation with Enum values)
"""

from enum import StrEnum

from app.domain.base import PaginationEnvelope, enum_check_constraint


class SampleStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"


def test_pagination_envelope_pages_calculation() -> None:
    # 95 items, limit 10 -> 10 pages
    envelope = PaginationEnvelope(
        items=["a", "b", "c"],
        total=95,
        limit=10,
        offset=0,
    )
    assert envelope.pages == 10
    assert envelope.total == 95
    assert len(envelope.items) == 3

    # Exact division: 100 items, limit 20 -> 5 pages
    exact_envelope = PaginationEnvelope(
        items=[],
        total=100,
        limit=20,
        offset=20,
    )
    assert exact_envelope.pages == 5

    # 0 items -> 0 pages
    empty_envelope = PaginationEnvelope(
        items=[],
        total=0,
        limit=10,
        offset=0,
    )
    assert empty_envelope.pages == 0

    # Limit <= 0 safety
    zero_limit = PaginationEnvelope(
        items=[],
        total=10,
        limit=0,
        offset=0,
    )
    assert zero_limit.pages == 1


def test_enum_check_constraint_generation() -> None:
    ck = enum_check_constraint("status", SampleStatus)
    assert ck.name == "ck_status_enum"
    sql_text = str(ck.sqltext)
    assert "status IN ('pending', 'active', 'suspended')" in sql_text

    # Custom name
    custom_ck = enum_check_constraint("status", SampleStatus, name="custom_status_check")
    assert custom_ck.name == "custom_status_check"
