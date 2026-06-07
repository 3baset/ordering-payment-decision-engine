from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from store.event_store import DuckDBEventStore


def project_all(store: "DuckDBEventStore", output_dir: str) -> None:
    """Run all projectors and write Parquet tables."""
    from projections.order_projector import OrderProjector
    from projections.customer_projector import CustomerProjector
    from projections.inventory_projector import InventoryProjector
    from projections.financial_projector import FinancialProjector
    from projections.rfm_projector import RFMProjector
    from projections.analytics_projector import AnalyticsProjector

    os.makedirs(output_dir, exist_ok=True)
    store.flush()

    print("Projecting orders ...")
    op = OrderProjector(store, output_dir)
    op.project_orders()
    op.project_order_lines()

    print("Projecting customers ...")
    cp = CustomerProjector(store, output_dir)
    cp.project_customers()
    cp.project_customer_history()

    print("Projecting inventory ...")
    ip = InventoryProjector(store, output_dir)
    ip.project_inventory_snapshot()
    ip.project_stockout_events()

    print("Projecting financials ...")
    fp = FinancialProjector(store, output_dir)
    fp.project_invoices()
    fp.project_payments()
    fp.project_credit_ledger()

    print("Projecting RFM ...")
    rfm = RFMProjector(store, output_dir)
    rfm.project_rfm_scores()

    print("Projecting analytics ...")
    ap = AnalyticsProjector(store, output_dir)
    ap.project_monthly_customer_snapshot()
    ap.project_rep_performance()
    ap.project_promotion_performance()

    print("All projections complete.")
