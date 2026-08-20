"""
Valkey (Redis-compatible) caching adapter.

ValkeyStore  – Litestar-native store backed by Valkey, registered on the
               Litestar app as stores={"valkey": valkey_store}.

Hot-path helpers
----------------
set_transformer_state(transformer_id, payload)
    Serialise and cache the latest TelemetryRecord for a transformer.
    TTL defaults to 24 h so stale entries self-expire.

get_transformer_state(transformer_id)
    Deserialise and return the cached TelemetryRecord, or None if the
    key has expired / never been set.
"""
import msgspec
from litestar.stores.valkey import ValkeyStore

from app.core.settings import settings
from app.domain.telemetry.schemas import TelemetryRecord

# ---------------------------------------------------------------------------
# Exported store – registered on the Litestar app in app/__init__.py
# ---------------------------------------------------------------------------
valkey_store = ValkeyStore.with_client(
    url=f"valkey://{settings.VALKEY_HOST}:{settings.VALKEY_PORT}",
)

# ---------------------------------------------------------------------------
# Codec (reused across calls – msgspec encoders are thread-safe)
# ---------------------------------------------------------------------------
_encoder = msgspec.json.Encoder()
_decoder = msgspec.json.Decoder(TelemetryRecord)

# Cache key namespace
_KEY_PREFIX = "transformer:state:"

# Default TTL: 24 hours (seconds)
_DEFAULT_TTL_SECONDS = 86_400


async def set_transformer_state(
    transformer_id: str,
    payload: TelemetryRecord,
    ttl: int = _DEFAULT_TTL_SECONDS,
) -> None:
    """
    Serialise *payload* to JSON and store it in Valkey under
    ``transformer:state:<transformer_id>``.

    Parameters
    ----------
    transformer_id:
        Unique device tag (e.g. ``"TRF-042"``).
    payload:
        The latest TelemetryRecord received from the transformer.
    ttl:
        Key expiry in seconds (default 86 400 = 24 h).
    """
    key = f"{_KEY_PREFIX}{transformer_id}"
    raw: bytes = _encoder.encode(payload)
    await valkey_store.set(key, raw, expires_in=ttl)


async def get_transformer_state(transformer_id: str) -> TelemetryRecord | None:
    """
    Retrieve and deserialise the cached TelemetryRecord for *transformer_id*.

    Returns ``None`` if the key does not exist or has expired.
    """
    key = f"{_KEY_PREFIX}{transformer_id}"
    raw: bytes | None = await valkey_store.get(key)
    if raw is None:
        return None
    return _decoder.decode(raw)
