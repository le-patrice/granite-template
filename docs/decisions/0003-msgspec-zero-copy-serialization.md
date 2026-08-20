# ADR 0003: Zero-Copy Serialization via msgspec for High-Throughput Telemetry

- **Status:** Accepted
- **Date:** 2026-08-20
- **Deciders:** Principal Backend Architect, Performance Engineering Team

---

## Context

The platform is designed to ingest massive streams of IoT transformer telemetry data (voltage, current, power factor, frequency) in batches exceeding thousands of records per request.

Standard Python data modeling libraries present measurable performance trade-offs during continuous batch ingestion:
1. **Pydantic Validation Latency:** While Pydantic v2 includes a Rust core (`pydantic-core`), converting raw JSON bytes into full Python class instances creates significant memory allocations.
2. **Garbage Collection Pressure:** Instantiating and discarding hundreds of thousands of short-lived Python objects per second triggers frequent generational garbage collection cycles, causing latency spikes (GC pauses).

---

## Decision

We adopted **[`msgspec`](https://jcristharif.com/msgspec/)** as the primary schema and serialization engine for all high-velocity telemetry pipelines and data transfer objects.

```python
import msgspec

class TelemetryRecord(msgspec.Struct, frozen=True, gc=False):
    transformer_id: str
    voltage_v: float
    current_a: float
    power_factor: float
    frequency_hz: float
    timestamp_epoch: int
```

### Key Architectural Drivers

1. **Native C/Cython Zero-Copy Parsing:** `msgspec` decodes directly from memory buffers without intermediate string or dictionary allocations.
2. **`gc=False` Structs:** Setting `gc=False` on immutable (`frozen=True`) structs informs the CPython runtime that instances contain no cyclic references, completely exempting them from garbage collector tracking.
3. **Speed & Memory Efficiency:** Benchmarks demonstrate `msgspec` is 10x–20x faster than standard library `json` and 2x–4x faster than Pydantic v2 for structured decoding.

---

## Consequences

### Positive
- **Deterministic Low Latency:** Eliminates GC latency spikes during heavy continuous IoT ingestion bursts.
- **Minimal Memory Footprint:** Drastically reduced RAM consumption per worker process.
- **Native Litestar Support:** Litestar natively supports `msgspec.Struct` as request bodies and response types with automatic OpenAPI schema extraction.

### Negative / Trade-offs
- **Strict Typing:** `msgspec` enforces strict schema matching without loose type coercions (e.g. string numbers are not automatically cast to floats unless explicitly configured).
- **Dual Schema Paradigms:** Relational models use SQLAlchemy declarative entities while high-speed ingestion DTOs use `msgspec.Struct`.
