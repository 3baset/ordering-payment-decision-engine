from __future__ import annotations

import os
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from store.event_store import DuckDBEventStore


class BaseProjector:
    def __init__(self, store: "DuckDBEventStore", output_dir: str) -> None:
        self.store = store
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def read_events(self, event_type: str) -> pl.LazyFrame:
        return self.store.read_events(event_type)

    def read_events_multi(self, event_types: list[str]) -> pl.LazyFrame:
        return self.store.read_events_multi(event_types)

    def unpack_payload(self, lf: pl.LazyFrame, fields: list[str]) -> pl.LazyFrame:
        return lf.with_columns([
            pl.col("payload").str.json_path_match(f"$.{f}").alias(f)
            for f in fields
        ])

    def write(self, lf: pl.LazyFrame, table_name: str) -> None:
        path = os.path.join(self.output_dir, f"{table_name}.parquet")
        df = lf.collect()
        df.write_parquet(path, use_pyarrow=True)
        print(f"  Wrote {len(df):,} rows → {table_name}.parquet")
