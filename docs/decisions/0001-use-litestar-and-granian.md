# ADR 0001: Use Litestar and Granian for Asynchronous Web API

- **Status:** Accepted
- **Date:** 2026-08-20
- **Deciders:** Principal Systems Architect, Backend Engineering Team

---

## Context

The platform requires an asynchronous, high-throughput Python web foundation capable of ingesting high-frequency IoT telemetry streams while providing clean architectural abstractions, automatic OpenAPI generation, and performant dependency injection.

Previous architectures built on FastAPI and Uvicorn encountered key limitations at scale:
1. **Concurrency Bottlenecks:** Python-based ASGI servers (Uvicorn) introduce GIL-bound event-loop bottlenecks under heavy concurrent I/O.
2. **Framework Coupling:** FastAPI's dependency injection and routing mechanisms tightly couple domain logic to HTTP request lifecycles.
3. **Serialization Overhead:** Default reliance on Pydantic v1/v2 introduces measurable CPU latency when parsing high-velocity batch telemetry payloads.

---

## Decision

We chose **[Litestar](https://litestar.dev/)** as the core web framework paired with **[Granian](https://github.com/emmett-framework/granian)** (a Rust-based HTTP/ASGI server) as the production application server.

### Key Architectural Drivers

1. **Rust-Powered HTTP/ASGI Engine (Granian):** Granian offloads HTTP parsing, TLS/HTTP2 framing, and event loop thread management to Rust (`hyper` and `tokio`), providing 2x–3x throughput improvements over pure Python ASGI servers.
2. **Decoupled Class-Based Dependency Injection:** Litestar's `Provide()` and hierarchical DI system cleanly separate controller routing from domain service construction.
3. **Pluggable Architecture:** Native plugins for Advanced-Alchemy, Structlog, OpenAPI (Scalar / Swagger), and stores (Valkey) provide unified lifecycle management.

---

## Consequences

### Positive
- **High Request Throughput:** Significantly reduced latency for concurrent IoT payload ingestion.
- **Strict Layer Decoupling:** Facilitates pure domain modeling without HTTP framework dependencies.
- **Multiple Documentation Renderers:** Built-in decoupled support for Scalar, Swagger, and OpenAPI schema exports.

### Negative / Trade-offs
- **Smaller Community Ecosystem:** Smaller ecosystem of third-party plugins compared to Flask/FastAPI, requiring direct implementation of custom adapters when needed.
- **Learning Curve:** Requires developers to understand Litestar's controller structures and dependency scopes rather than procedural route functions.
