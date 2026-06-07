from datetime import datetime, timedelta
from typing import Optional
import io
import polars as pl


_TIMESTAMP_COLS = ["timestamp", "created_at", "month", "last_order_date"]


def _find_timestamp_col(df: pl.DataFrame) -> str:
    for col in _TIMESTAMP_COLS:
        if col in df.schema:
            return col
    raise ValueError(
        f"No known timestamp column found for date_window filter. "
        f"Available columns: {list(df.schema.keys())}"
    )


def apply_date_window(df: pl.DataFrame, anchor_dt: datetime, days: int) -> pl.DataFrame:
    cutoff = anchor_dt - timedelta(days=days)
    col = _find_timestamp_col(df)
    return df.filter(pl.col(col) >= cutoff)


def apply_join(df: pl.DataFrame, parent_df: pl.DataFrame, key: str) -> pl.DataFrame:
    keys = parent_df[key].unique()
    return df.filter(pl.col(key).is_in(keys))


def apply_limit(
    df: pl.DataFrame,
    limit_rows: Optional[int],
    limit_mb: Optional[float],
    seed: int,
) -> pl.DataFrame:
    if limit_rows is not None and len(df) > limit_rows:
        return df.sample(n=limit_rows, seed=seed, shuffle=True)

    if limit_mb is not None:
        target_bytes = int(limit_mb * 1_048_576)
        probe_n = min(1000, len(df))
        bytes_per_row = _parquet_bytes(df.head(probe_n)) / probe_n
        estimated_rows = int(target_bytes / bytes_per_row)
        estimated_rows = max(1, min(estimated_rows, len(df)))
        result = df.sample(n=estimated_rows, seed=seed, shuffle=True)
        # Single correction pass: if still over, trim head
        if _parquet_bytes(result) > target_bytes and len(result) > 1:
            ratio = target_bytes / _parquet_bytes(result)
            result = result.head(max(1, int(len(result) * ratio)))
        return result

    return df


def _parquet_bytes(df: pl.DataFrame) -> int:
    buf = io.BytesIO()
    df.write_parquet(buf, compression="snappy")
    return buf.tell()
