"""
Telemetry validation schemas (zero-copy msgspec).

TelemetryRecord  – single sensor reading from one transformer.
TelemetryBatch   – envelope wrapping a list of records for bulk ingestion.
"""

import msgspec


class TelemetryRecord(msgspec.Struct, frozen=True, gc=False):
    """
    Immutable, GC-exempt struct for maximum throughput.

    Fields
    ------
    transformer_id  : Unique device identifier (string tag, e.g. "TRF-042")
    voltage_v       : Line voltage in Volts
    current_a       : Current in Amperes
    power_factor    : Power factor (0.0 – 1.0)
    frequency_hz    : Grid frequency in Hertz (nominally 50 or 60)
    timestamp_epoch : Unix epoch seconds (UTC) of the measurement
    """

    transformer_id: str
    voltage_v: float
    current_a: float
    power_factor: float
    frequency_hz: float
    timestamp_epoch: float


class TelemetryBatch(msgspec.Struct, frozen=True, gc=False):
    """Envelope for bulk ingestion — wraps multiple records in one HTTP body."""

    records: list[TelemetryRecord]
