from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING

import numpy as np

from engines.ordering_engine import compute_order_probability, sample_order_interval
from schemas.order_events import OrderCreated, OrderLine, OrderRejected
from store.shared_state import sim_time_to_dt
from validators.business_rules import check_credit_rule, check_customer_status

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import CustomerState, InventoryState, SharedSimulationState


class CustomerOrderProcess:
    """Per-customer order loop using exponential inter-arrival times."""

    def __init__(
        self,
        env: "simpy.Environment",
        customer: "CustomerState",
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
    ) -> None:
        self.env = env
        self.customer = customer
        self.state = state
        self.store = store
        self.config = config

    def run(self):
        while True:
            # Compute order probability and sample inter-arrival
            p = compute_order_probability(self.customer, self.state, self.env.now, self.config)
            interval = sample_order_interval(p)
            yield self.env.timeout(interval)

            if self.customer.status == "churned":
                break

            now = self.env.now
            ts = sim_time_to_dt(now)

            # Business rule checks
            cr2 = check_customer_status(self.customer)
            if not cr2.passed:
                break

            # Build order
            order_lines, order_total = self._build_order_lines()
            if not order_lines:
                continue

            # Apply best available promotion (if any).
            # OrderCreated.total_value keeps the original undiscounted total (so the
            # line-total validator passes). discounted_total drives credit and invoice.
            from engines.promotion_engine import find_best_promotion, get_discount_amount
            applied_promo = None
            original_total = order_total
            discounted_total = order_total
            if self.state.active_promotions:
                applied_promo = find_best_promotion(
                    self.customer, self.state.active_promotions, order_total
                )
                if applied_promo:
                    discount = get_discount_amount(order_total, applied_promo)
                    candidate = round(order_total - discount, 2)
                    if candidate > 0.0:
                        discounted_total = candidate
                    else:
                        applied_promo = None  # discount exceeds order value — skip

            cr1 = check_credit_rule(self.customer, discounted_total)
            if not cr1.passed:
                self.store.emit(OrderRejected(
                    aggregate_id=self.customer.customer_id,
                    timestamp=ts,
                    customer_id=self.customer.customer_id,
                    reason="credit_limit",
                    attempted_value=order_total,
                ))
                continue

            # Fraud check
            recent = self.state.recent_order_times.get(self.customer.customer_id, [])
            recent_24h = [t for t in recent if now - t <= 1.0]
            history = self.state.order_value_history.get(self.customer.customer_id, [])
            avg_90d = sum(history[-90:]) / max(1, len(history[-90:])) if history else 0.0
            from engines.fraud_engine import score_order
            fraud_score = score_order(
                self.customer,
                order_total,
                len(recent_24h),
                avg_90d,
                self.config.get("fraud", {}).get("velocity_threshold", 3),
                self.config.get("fraud", {}).get("amount_multiplier_threshold", 5),
            )
            reject_threshold = self.config.get("fraud", {}).get("reject_score_threshold", 0.9)
            if fraud_score >= reject_threshold:
                self.store.emit(OrderRejected(
                    aggregate_id=self.customer.customer_id,
                    timestamp=ts,
                    customer_id=self.customer.customer_id,
                    reason="fraud",
                    attempted_value=order_total,
                ))
                continue

            # Choose channel
            channel = self._pick_channel()

            order_id = f"ORD-{str(uuid.uuid4())[:8].upper()}"
            self.store.emit(OrderCreated(
                aggregate_id=self.customer.customer_id,
                timestamp=ts,
                customer_id=self.customer.customer_id,
                order_id=order_id,
                total_value=order_total,
                lines=order_lines,
                channel=channel,
                rep_id=self.customer.rep_id,
                fraud_score=round(fraud_score, 4),
            ))

            # Emit promotion event if a discount was applied
            if applied_promo:
                from schemas.promotion_events import PromotionApplied
                self.store.emit(PromotionApplied(
                    aggregate_id=self.customer.customer_id,
                    timestamp=ts,
                    promotion_id=applied_promo["id"],
                    order_id=order_id,
                    customer_id=self.customer.customer_id,
                    discount_amount=round(original_total - discounted_total, 2),
                    original_value=round(original_total, 2),
                ))

            # Update state — credit and history use discounted total (actual cash exposure)
            self.customer.credit_used += discounted_total
            self.customer.last_order_time = now
            if self.customer.status in ("new", "inactive", "dormant"):
                self.customer.status = "active"

            # Track for fraud detection (use original total for anomaly baseline)
            recent_24h.append(now)
            self.state.recent_order_times[self.customer.customer_id] = recent_24h
            history.append(order_total)
            self.state.order_value_history[self.customer.customer_id] = history

            # Spawn fulfillment process — invoice is for the discounted amount
            from processes.order_fulfillment_process import OrderFulfillmentProcess
            self.env.process(OrderFulfillmentProcess(
                self.env,
                self.customer,
                order_id,
                discounted_total,
                order_lines,
                self.state,
                self.store,
                self.config,
            ).run())

    def _build_order_lines(self) -> tuple[list[OrderLine], float]:
        skus = list(self.state.skus.values())
        if not skus:
            return [], 0.0

        from engines.ordering_engine import BASKET_LOGNORMAL
        params = BASKET_LOGNORMAL.get(self.customer.segment, BASKET_LOGNORMAL["regular"])
        total_target = float(np.random.lognormal(params["mean_log"], params["sigma"]))
        total_target *= self.state.inflation_factor

        n_lines = random.randint(
            self.config.get("orders", {}).get("min_lines", 1),
            self.config.get("orders", {}).get("max_lines", 8),
        )

        # Affinity-weighted SKU selection
        sku_categories = {inv.sku_id: inv.category for inv in skus}
        anchor = random.choice(skus)
        from engines.affinity_engine import sample_basket_skus
        sku_ids = sample_basket_skus(
            anchor.sku_id,
            [inv.sku_id for inv in skus],
            sku_categories,
            n_lines,
        )
        chosen_invs = [self.state.skus[sid] for sid in sku_ids if sid in self.state.skus]
        if not chosen_invs:
            return [], 0.0

        lines: list[OrderLine] = []
        remaining = total_target
        for i, inv in enumerate(chosen_invs):
            if i == len(chosen_invs) - 1:
                line_budget = remaining
            else:
                frac = random.uniform(0.15, 0.55)
                line_budget = remaining * frac
                remaining -= line_budget

            qty = max(1, round(line_budget / inv.unit_price))
            unit_price = round(inv.unit_price * self.state.inflation_factor, 2)
            line_total = round(qty * unit_price, 2)

            lines.append(OrderLine(
                sku_id=inv.sku_id,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
                demand_class=inv.demand_class,
            ))

        order_total = round(sum(l.line_total for l in lines), 2)
        return lines, order_total

    def _pick_channel(self) -> str:
        if self.customer.digital_active and random.random() < 0.35:
            return "app"
        if self.customer.rep_id:
            key = f"{self.customer.rep_id}:{self.customer.customer_id}"
            last_visit = self.state.rep_last_visit.get(key, -999.0)
            if self.env.now - last_visit <= 7:
                return "rep"
        return random.choice(["direct", "organic"])
