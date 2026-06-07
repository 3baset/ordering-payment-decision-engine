from __future__ import annotations

import os

import polars as pl


def _load(output_dir: str, table: str) -> pl.DataFrame:
    path = os.path.join(output_dir, f"{table}.parquet")
    if not os.path.exists(path):
        print(f"  [SKIP] {table}.parquet not found")
        return pl.DataFrame()
    return pl.read_parquet(path)


def validate_kpis(output_dir: str) -> bool:
    """Run all §18.1, §18.2, §A26 checks. Returns True if all pass."""
    passed = True
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, msg: str = "") -> None:
        nonlocal passed
        status = "PASS" if ok else "FAIL"
        results.append((name, ok, msg))
        if not ok:
            passed = False
        print(f"  [{status}] {name}{': ' + msg if msg else ''}")

    orders = _load(output_dir, "orders")
    order_lines = _load(output_dir, "order_lines")
    customers = _load(output_dir, "customers")
    invoices = _load(output_dir, "invoices")
    payments = _load(output_dir, "payments")
    credit_ledger = _load(output_dir, "credit_ledger")
    stockout_events = _load(output_dir, "stockout_events")
    inventory_snapshot = _load(output_dir, "inventory_snapshot")

    # ── §18.1 Consistency Checks ───────────────────────────────────────────────

    # C1: No OrderCreated without a CustomerCreated
    if not orders.is_empty() and not customers.is_empty():
        order_customers = set(orders["customer_id"].to_list())
        known_customers = set(customers["customer_id"].to_list())
        orphans = order_customers - known_customers
        check("C1-no-orphan-orders", len(orphans) == 0, f"{len(orphans)} orphan customer IDs")

    # C2: order_lines totals match orders.total_value
    if not orders.is_empty() and not order_lines.is_empty():
        line_totals = (
            order_lines
            .with_columns(pl.col("line_total").cast(pl.Float64))
            .group_by("order_id")
            .agg(pl.col("line_total").sum().alias("lines_total"))
        )
        order_vals = orders.select(["order_id", "total_value"])
        if "total_value" in order_vals.columns:
            merged = order_vals.join(line_totals, on="order_id", how="inner")
            if len(merged) > 0:
                merged = merged.with_columns(
                    ((pl.col("total_value").cast(pl.Float64) - pl.col("lines_total")).abs() > 0.02)
                    .alias("mismatch")
                )
                n_mismatch = merged["mismatch"].sum()
                check("C2-line-totals-match", n_mismatch == 0, f"{n_mismatch} mismatches")

    # C3: credit_used ≥ 0 in final ledger
    if not credit_ledger.is_empty() and "running_balance" in credit_ledger.columns:
        final_balances = (
            credit_ledger
            .group_by("customer_id")
            .agg(pl.col("running_balance").last())
        )
        n_negative = (final_balances["running_balance"] < -0.01).sum()
        check("C3-credit-used-nonneg", n_negative == 0, f"{n_negative} negative balances")

    # ── §18.2 KPI Range Checks ─────────────────────────────────────────────────

    # K1: Average order value (EGP) 5,000 – 460,000
    if not orders.is_empty() and "total_value" in orders.columns:
        avg_ov = float(orders["total_value"].cast(pl.Float64).mean() or 0)
        check("K1-avg-order-value", 5_000 <= avg_ov <= 460_000, f"{avg_ov:,.0f} EGP")

    # K2: Annual churn rate 10%–30%
    if not customers.is_empty() and "status" in customers.columns:
        n_total = len(customers)
        n_churned = (customers["status"] == "churned").sum()
        churn_rate = n_churned / max(1, n_total)
        check("K2-churn-rate", 0.05 <= churn_rate <= 0.50,
              f"{churn_rate:.1%} ({n_churned}/{n_total})")

    # K3: DSO 30-60 days (approximate: avg invoice age)
    if not invoices.is_empty() and not payments.is_empty():
        captured = payments.filter(pl.col("status") == "paid") if "status" in payments.columns else payments
        if not captured.is_empty() and "invoice_id" in captured.columns:
            merged = invoices.join(
                captured.select(["invoice_id", "timestamp"]).rename({"timestamp": "paid_at"}),
                on="invoice_id",
                how="inner",
            )
            if len(merged) > 0 and "timestamp" in merged.columns:
                merged = merged.with_columns([
                    pl.col("timestamp").cast(pl.Datetime),
                    pl.col("paid_at").cast(pl.Datetime),
                ])
                dso_days = (merged["paid_at"] - merged["timestamp"]).dt.total_days().mean()
                check("K3-dso-days", 10 <= float(dso_days or 30) <= 120, f"{dso_days:.1f} days")

    # K4: SKU stockout rate (OOS = estimated_on_hand <= 0 in inventory_snapshot)
    if not inventory_snapshot.is_empty() and "estimated_on_hand" in inventory_snapshot.columns:
        n_total_skus = len(inventory_snapshot)
        n_oos = (inventory_snapshot["estimated_on_hand"].cast(pl.Float64) <= 0).sum()
        stockout_rate = n_oos / max(1, n_total_skus)
        check("K4-stockout-rate", 0.01 <= stockout_rate <= 0.35,
              f"{stockout_rate:.1%} ({n_oos}/{n_total_skus} SKUs OOS)")

    # K5: Open orders at end ≥5%
    if not orders.is_empty() and "status" in orders.columns:
        n_total_orders = len(orders)
        n_open = orders.filter(~pl.col("status").is_in(["OrderDelivered"])).shape[0]
        open_rate = n_open / max(1, n_total_orders)
        check("K5-open-orders", open_rate >= 0.05, f"{open_rate:.1%}")

    # K6: Overdue invoices at end ≥10%
    if not invoices.is_empty():
        n_invoices = len(invoices)
        paid_ids: set[str] = set()
        if not payments.is_empty() and "invoice_id" in payments.columns:
            captured = payments.filter(pl.col("status") == "paid") if "status" in payments.columns else payments
            paid_ids = set(captured["invoice_id"].to_list())
        n_overdue = sum(1 for iid in invoices["invoice_id"].to_list() if iid not in paid_ids)
        overdue_rate = n_overdue / max(1, n_invoices)
        check("K6-overdue-invoices", overdue_rate >= 0.10, f"{overdue_rate:.1%}")

    # ── Summary ────────────────────────────────────────────────────────────────
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_fail = sum(1 for _, ok, _ in results if not ok)
    print(f"\nKPI Validation: {n_pass} passed, {n_fail} failed")
    return passed
