"""
Telemetry domain repository contract.

Keeps the domain layer independent of any persistence technology.
"""
from abc import ABC, abstractmethod

from app.domain.telemetry.schemas import TelemetryRecord


class ITelemetryRepository(ABC):
    @abstractmethod
    async def add_batch(self, records: list[TelemetryRecord]) -> None:
        """
        Persist a batch of telemetry records.

        Implementations must use bulk insertion to minimise round-trips.
        The method intentionally returns None – callers do not need
        the persisted IDs on the hot ingest path.
        """
        ...
