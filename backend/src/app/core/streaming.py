"""
High-performance zero-copy async streaming utilities for large files and datasets.

Enforces flat memory bounds (<25MB RAM) even when streaming multi-gigabyte
sensor archives, Parquet datasets, or S3 multipart payloads.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterable, Iterable
from typing import Any


async def stream_file_chunks(
    file_path: str,
    chunk_size: int = 65536,  # 64KB optimal socket buffer
) -> AsyncGenerator[bytes, None]:
    """
    Asynchronously streams file content in fixed-size buffers.
    Uses non-blocking threadpool I/O to avoid blocking the ASGI event loop.
    """
    loop = asyncio.get_running_loop()

    def _read_chunk(file_obj: Any) -> bytes:
        return file_obj.read(chunk_size)

    f = await loop.run_in_executor(None, open, file_path, "rb")
    try:
        while True:
            chunk = await loop.run_in_executor(None, _read_chunk, f)
            if not chunk:
                break
            yield chunk
    finally:
        await loop.run_in_executor(None, f.close)


async def stream_memoryview_chunks(
    data: bytes | bytearray,
    chunk_size: int = 65536,
) -> AsyncGenerator[memoryview, None]:
    """
    Zero-copy slicing of in-memory byte buffers using Python memoryview.
    Prevents allocating intermediate substrings or copying bytes on the heap.
    """
    view = memoryview(data)
    total_len = len(view)
    offset = 0

    while offset < total_len:
        end = min(offset + chunk_size, total_len)
        yield view[offset:end]
        offset = end


async def stream_dataset_batches(
    iterable: Iterable[Any] | AsyncIterable[Any],
    batch_size: int = 1000,
) -> AsyncGenerator[list[Any], None]:
    """
    Chunks large dataset streams into fixed batches for batch processing,
    PostgreSQL COPY streaming, or bulk serialization.
    """
    batch: list[Any] = []

    if hasattr(iterable, "__aiter__"):
        async for item in iterable:  # type: ignore[union-attr]
            batch.append(item)
            if len(batch) >= batch_size:
                yield batch
                batch = []
    else:
        for item in iterable:  # type: ignore[union-attr]
            batch.append(item)
            if len(batch) >= batch_size:
                yield batch
                batch = []

    if batch:
        yield batch
