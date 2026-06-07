from __future__ import annotations

import json
import random
from datetime import timedelta
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from store.event_store import DuckDBEventStore


class NoiseInjector:
    """Post-simulation noise pass over the event store (§16)."""

    def __init__(self, store: "DuckDBEventStore", config: dict) -> None:
        self.store = store
        self.config = config
        noise = config.get("noise", {})
        self.out_of_order_rate = noise.get("out_of_order_rate", 0.001)
        self.corruption_rate = noise.get("data_corruption_rate", 0.0001)
        self.late_arrival_rate = noise.get("late_arrival_rate", 0.020)
        self.late_arrival_days = noise.get("late_arrival_days", 2)
        self.out_of_order_hours = noise.get("out_of_order_hours", 1)

    def _get_random_ids(self, conn, n: int, where: str = "") -> list[str]:
        """Pre-fetch IDs to avoid DuckDB 0.10.3 PK index issues with RANDOM() in UPDATE/DELETE."""
        where_clause = f"WHERE {where}" if where else ""
        rows = conn.execute(
            f"SELECT event_id FROM event_store {where_clause} ORDER BY RANDOM() LIMIT {n}"
        ).fetchall()
        return [r[0] for r in rows]

    def _ids_placeholder(self, ids: list[str]) -> str:
        return ", ".join(f"'{i}'" for i in ids)

    def inject(self) -> dict[str, int]:
        self.store.flush()
        conn = self.store.conn
        total = conn.execute("SELECT COUNT(*) FROM event_store").fetchone()[0]
        print(f"  Noise injection on {total:,} events ...")
        counts: dict[str, int] = {"out_of_order": 0, "corrupt": 0, "late": 0}

        # 1. Out-of-order timestamps (0.1%) — shift back 1 hour
        # DuckDB 0.10.3 PK+UPDATE bug: use delete-and-reinsert instead of UPDATE
        n_oor = int(total * self.out_of_order_rate)
        if n_oor > 0:
            ids = self._get_random_ids(conn, n_oor, "timestamp >= '2023-01-01'")
            if ids:
                ph = self._ids_placeholder(ids)
                rows = conn.execute(f"SELECT * FROM event_store WHERE event_id IN ({ph})").pl()
                conn.execute(f"DELETE FROM event_store WHERE event_id IN ({ph})")
                modified = rows.with_columns(
                    (pl.col("timestamp").cast(pl.Datetime("us")) - pl.duration(hours=self.out_of_order_hours))
                    .alias("timestamp")
                )
                conn.register("_oor", modified.to_arrow())
                conn.execute("INSERT INTO event_store SELECT * FROM _oor")
                conn.unregister("_oor")
                counts["out_of_order"] = len(ids)

        # 2. Data corruption (0.01%) — delete-and-reinsert with corrupted payload
        n_corrupt = max(1, int(total * self.corruption_rate))
        corrupt_ids = self._get_random_ids(conn, n_corrupt)
        if corrupt_ids:
            ph = self._ids_placeholder(corrupt_ids)
            rows = conn.execute(f"SELECT * FROM event_store WHERE event_id IN ({ph})").pl()
            conn.execute(f"DELETE FROM event_store WHERE event_id IN ({ph})")
            new_payloads = []
            for payload_str in rows["payload"].to_list():
                try:
                    payload = json.loads(payload_str)
                    numeric_fields = [k for k, v in payload.items() if isinstance(v, (int, float))]
                    if numeric_fields:
                        field = random.choice(numeric_fields)
                        payload[field] = None if random.random() < 0.5 else -abs(payload[field])
                    new_payloads.append(json.dumps(payload))
                except Exception:
                    new_payloads.append(payload_str)
            rows = rows.with_columns(pl.Series("payload", new_payloads))
            conn.register("_corrupt", rows.to_arrow())
            conn.execute("INSERT INTO event_store SELECT * FROM _corrupt")
            conn.unregister("_corrupt")
            counts["corrupt"] = len(corrupt_ids)

        # 3. Late arrival (2%) — delete-and-reinsert with backdated timestamp
        n_late = int(total * self.late_arrival_rate)
        if n_late > 0:
            ids = self._get_random_ids(conn, n_late, "timestamp >= '2023-01-03'")
            if ids:
                ph = self._ids_placeholder(ids)
                rows = conn.execute(f"SELECT * FROM event_store WHERE event_id IN ({ph})").pl()
                conn.execute(f"DELETE FROM event_store WHERE event_id IN ({ph})")
                modified = rows.with_columns(
                    (pl.col("timestamp").cast(pl.Datetime("us")) - pl.duration(days=self.late_arrival_days))
                    .alias("timestamp")
                )
                conn.register("_late", modified.to_arrow())
                conn.execute("INSERT INTO event_store SELECT * FROM _late")
                conn.unregister("_late")
                counts["late"] = len(ids)

        new_total = conn.execute("SELECT COUNT(*) FROM event_store").fetchone()[0]
        print(f"  After noise injection: {new_total:,} events")
        return counts
