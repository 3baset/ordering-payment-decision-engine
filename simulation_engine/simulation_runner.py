"""simulation_runner.py — Main entry point for the simulation engine."""
from __future__ import annotations

import os
import sys
import time

import simpy
import yaml

# ── Seeding must happen before any random/numpy/faker calls ──────────────────
from config.seeds import SEED, fake  # noqa: F401 (side-effect: seeds all RNGs)


def load_config(path: str = "config/simulation_config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_simulation(config: dict | None = None, days: int | None = None) -> dict:
    if config is None:
        config = load_config()

    sim_days = days if days is not None else config["simulation"]["days"]
    db_path = config["event_store"]["path"]
    output_dir = config["output"]["parquet_dir"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    from store.event_store import DuckDBEventStore
    from store.shared_state import SharedSimulationState, InventoryState

    if os.path.exists(db_path):
        os.unlink(db_path)
    store = DuckDBEventStore(db_path, batch_size=config["event_store"]["batch_size"])
    state = SharedSimulationState()

    print(f"Generating {config['scale']['sku_count']} SKUs ...")
    from generators.product_generator import generate_skus
    sku_records = generate_skus(config["scale"]["sku_count"])

    print(f"Generating {config['scale']['initial_customers']} customers ...")
    from generators.rep_generator import generate_reps
    reps = generate_reps(fake)
    for rep in reps:
        state.reps[rep.rep_id] = rep

    rep_ids = list(state.reps.keys())
    from generators.customer_generator import generate_customers
    customers = generate_customers(
        config["scale"]["initial_customers"],
        fake,
        rep_ids=rep_ids,
        digital_active_prob=config["customers"]["digital_active_probability"],
    )
    for c in customers:
        state.customers[c.customer_id] = c
        state.pending_pos[c.customer_id] = False

    # Queue planned promotions — MacroProcess activates them at their start_day
    # (do NOT put them in active_promotions; they would be filtered out immediately)
    state.pending_promotions = [
        {"id": "PROMO-RAMADAN-2023",  "name": "Ramadan Premium Push",       "promotion_type": "percentage", "value": 12.0, "target_segments": ["premium"],    "start_day": 80,  "end_day": 110, "active": True, "trigger": "planned"},
        {"id": "PROMO-LOYALTY-Q1",    "name": "Q1 Regular Loyalty",          "promotion_type": "percentage", "value":  7.0, "target_segments": ["regular"],     "start_day": 30,  "end_day":  90, "active": True, "trigger": "planned"},
        {"id": "PROMO-LV-ACTIVATE",   "name": "Low Volume Activation",       "promotion_type": "fixed",      "value": 500.0, "target_segments": ["low_volume"], "start_day": 120, "end_day": 150, "active": True, "trigger": "planned"},
        {"id": "PROMO-MID-YEAR",      "name": "Mid-Year Volume Push",        "promotion_type": "percentage", "value":  8.0, "target_segments": [],              "start_day": 180, "end_day": 210, "active": True, "trigger": "planned"},
        {"id": "PROMO-BOGO-Q3",       "name": "Q3 Premium BOGO",             "promotion_type": "bogo",       "value":  0.0, "target_segments": ["premium"],    "start_day": 250, "end_day": 280, "active": True, "trigger": "planned"},
        {"id": "PROMO-YEAR-END",      "name": "Year-End Regular Special",    "promotion_type": "percentage", "value": 10.0, "target_segments": ["regular"],     "start_day": 350, "end_day": 380, "active": True, "trigger": "planned"},
        {"id": "PROMO-SPRING-2024-LV","name": "Spring 2024 Low Volume Boost","promotion_type": "percentage", "value":  6.0, "target_segments": ["low_volume"], "start_day": 450, "end_day": 480, "active": True, "trigger": "planned"},
    ]

    # Create SimPy environment and containers
    env = simpy.Environment()
    for sku in sku_records:
        capacity = max(sku["initial_stock"] * 10, 10_000)
        container = simpy.Container(env, capacity=capacity, init=sku["initial_stock"])
        inv = InventoryState(
            sku_id=sku["sku_id"],
            container=container,
            avg_daily_demand=sku["avg_daily_demand"],
            demand_std=sku["demand_std"],
            lead_time=sku["lead_time"],
            eoq=sku["eoq"],
            reorder_point=sku["reorder_point"],
            safety_stock=sku["safety_stock"],
            category=sku["category"],
            subcategory=sku["subcategory"],
            brand_code=sku["brand_code"],
            demand_class=sku["demand_class"],
            unit_price=sku["unit_price"],
        )
        state.skus[sku["sku_id"]] = inv
        state.pending_pos[sku["sku_id"]] = False

    # Assign customers to reps
    for customer in customers:
        if customer.rep_id and customer.rep_id in state.reps:
            state.reps[customer.rep_id].assigned_customers.append(customer.customer_id)

    # Register macro and global processes
    from processes.macro_process import MacroProcess
    from processes.fraud_monitor_process import FraudMonitorProcess
    from processes.customer_arrival_process import CustomerArrivalProcess
    from processes.bootstrap_process import BootstrapProcess

    env.process(MacroProcess(env, state, store, config).run())
    env.process(FraudMonitorProcess(env, state, store, config).run())
    env.process(CustomerArrivalProcess(env, state, store, config, fake).run())
    env.process(BootstrapProcess(env, state, store, config, fake).run())

    print(f"Running simulation for {sim_days} days ...")
    t0 = time.time()
    env.run(until=sim_days)  # DO NOT add cleanup — open processes are intentional

    store.flush()
    elapsed = time.time() - t0
    n_events = store.count()
    print(f"Simulation complete: {n_events:,} events in {elapsed:.1f}s")

    print("\nRunning noise injection ...")
    from projections.noise_injector import NoiseInjector
    noise_counts = NoiseInjector(store, config).inject()

    # Append noise summary to DATA_QUALITY_REPORT
    report_path = os.path.join(os.path.dirname(db_path), "DATA_QUALITY_REPORT.md")
    with open(report_path, "a") as f:
        f.write("\n## Noise Injection\n")
        f.write(f"- Out-of-order shifts:     {noise_counts.get('out_of_order', 0):,}\n")
        f.write(f"- Data corruption:         {noise_counts.get('corrupt', 0):,}\n")
        f.write(f"- Late arrival backdates:  {noise_counts.get('late', 0):,}\n")

    print("\nProjecting to Parquet ...")
    from projections import project_all
    project_all(store, output_dir)

    print("\nValidating KPIs ...")
    from validators.kpi_validator import validate_kpis
    validate_kpis(output_dir)

    store.close()
    return {"events": n_events, "elapsed_s": elapsed, "output_dir": output_dir}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the ODA synthetic simulation engine.")
    parser.add_argument("--config", default="config/simulation_config.yaml",
                        help="Path to simulation_config.yaml (default: config/simulation_config.yaml)")
    parser.add_argument("--days", type=int, default=None,
                        help="Override simulation days from config")
    args = parser.parse_args()

    cfg = load_config(args.config)
    result = run_simulation(config=cfg, days=args.days)
    print(f"\nDone. {result['events']:,} events → {result['output_dir']}")
