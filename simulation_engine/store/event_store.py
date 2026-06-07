from __future__ import annotations

import json
import os
from typing import Any

import duckdb
import polars as pl

from schemas.base import EventBase


class DuckDBEventStore:
    def __init__(self, path: str, batch_size: int = 10_000) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.batch_size = batch_size
        self._buffer: list[dict[str, Any]] = []
        self.conn = duckdb.connect(path)
        self._setup_schema()

    def _setup_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS event_store (
                event_id       VARCHAR PRIMARY KEY,
                event_type     VARCHAR NOT NULL,
                aggregate_id   VARCHAR NOT NULL,
                timestamp      TIMESTAMP NOT NULL,
                payload        JSON NOT NULL,
                causation_id   VARCHAR,
                correlation_id VARCHAR
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_type_agg_ts
            ON event_store (event_type, aggregate_id, timestamp)
        """)

    def emit(self, event: EventBase) -> None:
        row = self._serialize(event)
        self._buffer.append(row)
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def _serialize(self, event: EventBase) -> dict[str, Any]:
        data = event.model_dump(mode="json")
        payload = {
            k: v
            for k, v in data.items()
            if k not in {"event_id", "event_type", "aggregate_id", "timestamp",
                         "causation_id", "correlation_id"}
        }
        return {
            "event_id":       str(data["event_id"]),
            "event_type":     data["event_type"],
            "aggregate_id":   data["aggregate_id"],
            "timestamp":      data["timestamp"],
            "payload":        json.dumps(payload),
            "causation_id":   str(data["causation_id"]) if data.get("causation_id") else None,
            "correlation_id": str(data["correlation_id"]) if data.get("correlation_id") else None,
        }

    def flush(self) -> None:
        if not self._buffer:
            return
        df = pl.DataFrame(self._buffer)
        self.conn.register("_buf", df.to_arrow())
        self.conn.execute("INSERT OR IGNORE INTO event_store SELECT * FROM _buf")
        self.conn.unregister("_buf")
        self._buffer.clear()

    def read_events(self, event_type: str) -> pl.LazyFrame:
        return (
            self.conn.execute(
                "SELECT * FROM event_store WHERE event_type = ?", [event_type]
            )
            .pl()
            .lazy()
        )

    def read_events_multi(self, event_types: list[str]) -> pl.LazyFrame:
        placeholders = ", ".join("?" * len(event_types))
        return (
            self.conn.execute(
                f"SELECT * FROM event_store WHERE event_type IN ({placeholders})",
                event_types,
            )
            .pl()
            .lazy()
        )

    def count(self) -> int:
        self.flush()
        return self.conn.execute("SELECT COUNT(*) FROM event_store").fetchone()[0]

    def close(self) -> None:
        self.flush()
        self.conn.close()
