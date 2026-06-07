from __future__ import annotations
import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Union
import polars as pl

from .config import SamplerConfig, load_config
from .filters import apply_date_window, apply_join, apply_limit


@dataclass
class ManifestEntry:
    sample: str
    table: str
    rows: int
    size_mb: float


@dataclass
class Manifest:
    entries: list[ManifestEntry] = field(default_factory=list)

    def add(self, sample: str, table: str, rows: int, size_mb: float) -> None:
        self.entries.append(ManifestEntry(sample, table, rows, size_mb))

    def print_summary(self) -> None:
        print(f"\n{'Sample':<12} {'Table':<28} {'Rows':>10} {'MB':>8}")
        print("-" * 62)
        for e in self.entries:
            print(f"{e.sample:<12} {e.table:<28} {e.rows:>10,} {e.size_mb:>8.1f}")
        total_mb = sum(e.size_mb for e in self.entries)
        print(f"\nTotal size: {total_mb:.1f} MB")


class Sampler:
    def __init__(self, config: Union[str, SamplerConfig]):
        self.config = load_config(config) if isinstance(config, str) else config

    def run(self) -> Manifest:
        cfg = self.config
        source = pathlib.Path(cfg.source_dir)
        output = pathlib.Path(cfg.output_dir)
        manifest = Manifest()

        # ── 1. Load and filter anchor table ─────────────────────────────────
        anchor_cfg = next(t for t in cfg.tables if t.split_anchor)
        anchor_df = pl.read_parquet(source / f"{anchor_cfg.name}.parquet")

        anchor_dt = self._resolve_anchor_dt(anchor_df, cfg.date_window.anchor)
        anchor_df = apply_date_window(anchor_df, anchor_dt, cfg.date_window.days)

        # ── 2. Stratified 50/50 split ────────────────────────────────────────
        anchor_df, strat_cols = self._add_strat_cols(anchor_df)
        anchor_df = (
            anchor_df
            .with_columns(
                pl.int_range(pl.len(), dtype=pl.Int64).shuffle(seed=cfg.random_seed).alias("_rnd")
            )
            .with_columns(
                pl.col("_rnd").rank(method="ordinal").over(strat_cols).alias("_rank")
            )
            .with_columns((pl.col("_rank") % 2).alias("_split"))
            .drop(["_rnd", "_rank"] + [c for c in strat_cols if c.startswith("_strat_")])
        )

        # ── 3. Build per-sample anchor slices ────────────────────────────────
        sample_orders: dict[str, pl.DataFrame] = {}
        for sc in cfg.samples:
            split_val = 0 if sc.split == "even" else 1
            df = anchor_df.filter(pl.col("_split") == split_val).drop("_split")
            df = self._apply_target_rows(df, cfg.target_rows, cfg.tolerance, cfg.random_seed)
            sample_orders[sc.name] = df

        # ── 4. Resolved cache (per sample, for join lookups) ─────────────────
        resolved: dict[str, dict[str, pl.DataFrame]] = {s: {} for s in sample_orders}

        # ── 5. Process all tables ────────────────────────────────────────────
        for tc in cfg.tables:
            if tc.static:
                df = pl.read_parquet(source / f"{tc.name}.parquet")
                df = apply_limit(df, tc.limit_rows, tc.limit_mb, cfg.random_seed)
                ref_dir = output / "reference"
                ref_dir.mkdir(parents=True, exist_ok=True)
                out_path = ref_dir / f"{tc.name}.parquet"
                df.write_parquet(out_path, compression="snappy")
                mb = out_path.stat().st_size / 1_048_576
                manifest.add("reference", tc.name, len(df), mb)
                print(f"  [reference] {tc.name}: {len(df):,} rows ({mb:.1f} MB)")
                continue

            if tc.split_anchor:
                for sample_name, df in sample_orders.items():
                    resolved[sample_name][tc.name] = df
                    out_path = self._write(df, output / sample_name / f"{tc.name}.parquet")
                    mb = out_path.stat().st_size / 1_048_576
                    manifest.add(sample_name, tc.name, len(df), mb)
                    print(f"  [{sample_name}] {tc.name}: {len(df):,} rows ({mb:.1f} MB)")
                continue

            # Non-anchor, non-static: load full table once, filter per sample
            df_full = pl.read_parquet(source / f"{tc.name}.parquet")

            for sample_name in sample_orders:
                df = df_full

                # Apply date_window FIRST (reduces the universe), then join
                if tc.filter == "date_window":
                    df = apply_date_window(df, anchor_dt, cfg.date_window.days)

                if tc.join is not None:
                    parent_name = tc.join.parent
                    if parent_name not in resolved[sample_name]:
                        raise ValueError(
                            f"Parent table '{parent_name}' not yet resolved for "
                            f"sample '{sample_name}'. Check table ordering in config."
                        )
                    df = apply_join(df, resolved[sample_name][parent_name], tc.join.key)

                df = apply_limit(df, tc.limit_rows, tc.limit_mb, cfg.random_seed)
                resolved[sample_name][tc.name] = df
                out_path = self._write(df, output / sample_name / f"{tc.name}.parquet")
                mb = out_path.stat().st_size / 1_048_576
                manifest.add(sample_name, tc.name, len(df), mb)
                print(f"  [{sample_name}] {tc.name}: {len(df):,} rows ({mb:.1f} MB)")

        manifest.print_summary()
        return manifest

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_anchor_dt(df: pl.DataFrame, anchor: str) -> datetime:
        if anchor == "latest":
            for col in ["created_at", "timestamp"]:
                if col in df.schema:
                    return df[col].max()
            raise ValueError("Cannot resolve 'latest' anchor — no created_at/timestamp column")
        return datetime.fromisoformat(anchor)

    def _add_strat_cols(self, df: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
        """Resolve stratify_by names, deriving _strat_month if 'month' is specified."""
        actual: list[str] = []
        for col in self.config.stratify_by:
            if col == "month":
                df = df.with_columns(
                    pl.col("created_at").dt.strftime("%Y-%m").alias("_strat_month")
                )
                actual.append("_strat_month")
            elif col in df.schema:
                actual.append(col)
            else:
                raise ValueError(
                    f"Stratify column '{col}' not found in anchor table. "
                    f"Available: {list(df.schema.keys())}"
                )
        return df, actual

    def _apply_target_rows(
        self,
        df: pl.DataFrame,
        target_rows: int | None,
        tolerance: float,
        seed: int,
    ) -> pl.DataFrame:
        if target_rows is None:
            return df
        lo = int(target_rows * (1 - tolerance))
        hi = int(target_rows * (1 + tolerance))
        if lo <= len(df) <= hi:
            return df
        if len(df) < lo:
            raise ValueError(
                f"Split has {len(df):,} rows, below minimum {lo:,} "
                f"(target={target_rows:,} ±{tolerance:.0%}). "
                f"Increase date_window.days or reduce target_rows."
            )
        return df.sample(n=target_rows, seed=seed, shuffle=True)

    @staticmethod
    def _write(df: pl.DataFrame, path: pathlib.Path) -> pathlib.Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(path, compression="snappy")
        return path


def main(config_path: str) -> None:
    sampler = Sampler(config_path)
    sampler.run()


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python -m data_sampler <config.yaml>")
        sys.exit(1)
    main(sys.argv[1])
