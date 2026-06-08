"""
ODA Data Sampler Dashboard
Run: streamlit run sampler_dashboard.py
"""
import pathlib
import subprocess
import sys

import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from data_sampler import Sampler, SamplerConfig
from aws_pipeline_tab import render_pipeline_tab

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ODA Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("ODA — Ordering Decisioning Agent")

COLORS = px.colors.qualitative.Set2

# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _fraud_float(df: pl.DataFrame) -> pl.DataFrame:
    if "fraud_score" in df.schema and df["fraud_score"].dtype == pl.Utf8:
        df = df.with_columns(pl.col("fraud_score").cast(pl.Float64, strict=False))
    return df


def _load_sample_tables(data_dir: pathlib.Path, sample_name: str) -> dict[str, pl.DataFrame]:
    d = data_dir / sample_name
    return {p.stem: pl.read_parquet(p) for p in d.glob("*.parquet")}


def render_sample(sample_name: str, tables: dict[str, pl.DataFrame]) -> None:
    orders    = _fraud_float(tables.get("orders", pl.DataFrame()))
    payments  = tables.get("payments", pl.DataFrame())
    customers = tables.get("customers", pl.DataFrame())

    if orders.is_empty():
        st.warning(f"No orders found for {sample_name}")
        return

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Orders",           f"{len(orders):,}")
    k2.metric("GMV",              f"EGP {orders['total_value'].sum():,.0f}")
    k3.metric("Avg Order Value",  f"EGP {orders['total_value'].mean():,.0f}")
    k4.metric("Unique Customers", f"{orders['customer_id'].n_unique():,}")
    high_fraud = (orders["fraud_score"] > 0.5).sum() if "fraud_score" in orders.schema else 0
    k5.metric("High-Fraud Orders", f"{high_fraud:,}")

    total_rows = sum(len(df) for df in tables.values())
    st.caption(f"Total rows across all tables in this sample: **{total_rows:,}**")
    st.markdown("---")

    col_l, col_r = st.columns(2)
    with col_l:
        ch = orders.group_by("channel").agg(pl.len().alias("orders")).sort("orders", descending=True)
        fig = px.bar(ch.to_pandas(), x="channel", y="orders", title="Orders by Channel",
                     color="channel", color_discrete_sequence=COLORS)
        fig.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)
    with col_r:
        st_df = orders.group_by("status").agg(pl.len().alias("count"))
        fig = px.pie(st_df.to_pandas(), names="status", values="count",
                     title="Order Status", hole=0.4, color_discrete_sequence=COLORS)
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        if "fraud_score" in orders.schema:
            fs = orders["fraud_score"].drop_nulls().to_pandas()
            fig = px.histogram(fs, nbins=30, title="Fraud Score Distribution",
                               labels={"value": "Fraud Score"},
                               color_discrete_sequence=[COLORS[2]])
            fig.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with col_r2:
        if not payments.is_empty() and "payment_method" in payments.schema:
            pm = payments.group_by("payment_method").agg(pl.len().alias("count")).sort("count", descending=True)
            fig = px.bar(pm.to_pandas(), x="payment_method", y="count",
                         title="Payment Method Mix", color="payment_method",
                         color_discrete_sequence=COLORS)
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)

    col_l3, col_r3 = st.columns(2)
    with col_l3:
        mo = (orders
              .with_columns(pl.col("created_at").dt.strftime("%Y-%m").alias("month"))
              .group_by("month").agg(pl.col("total_value").sum().alias("gmv"))
              .sort("month"))
        fig = px.line(mo.to_pandas(), x="month", y="gmv", title="Monthly GMV",
                      markers=True, color_discrete_sequence=[COLORS[0]])
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    with col_r3:
        if not customers.is_empty() and "customer_type" in customers.schema:
            ct = customers.group_by("customer_type").agg(pl.len().alias("count")).sort("count", descending=True)
            fig = px.bar(ct.to_pandas(), x="customer_type", y="count",
                         title="Customer Type Breakdown", color="customer_type",
                         color_discrete_sequence=COLORS)
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)

    with st.expander("All tables in this sample"):
        st.dataframe(
            [{"Table": name, "Rows": f"{len(df):,}"} for name, df in sorted(tables.items())],
            use_container_width=True, hide_index=True,
        )


def _render_sampler_results(manifest, data_dir: pathlib.Path) -> None:
    st.divider()
    st.subheader("📋 Manifest")

    manifest_rows = [
        {"Sample": e.sample, "Table": e.table, "Rows": e.rows, "Size (MB)": round(e.size_mb, 1)}
        for e in manifest.entries
    ]
    st.dataframe(manifest_rows, use_container_width=True, hide_index=True)

    total_mb = sum(e.size_mb for e in manifest.entries)
    non_ref_entries = [e for e in manifest.entries if e.sample != "reference"]
    sample_names = sorted({e.sample for e in non_ref_entries})
    totals_str = "  |  ".join(
        f"**{s}**: {manifest.total_per_sample.get(s, 0):,} rows" for s in sample_names
    )
    st.caption(f"Total disk: **{total_mb:.1f} MB**  |  {totals_str}")

    st.divider()
    st.subheader("📊 Business Metrics")

    tab_a, tab_b, tab_cmp = st.tabs(["Sample A", "Sample B", "Compare"])

    for tab, sname in [(tab_a, "sample_a"), (tab_b, "sample_b")]:
        with tab:
            if (data_dir / sname).exists():
                render_sample(sname, _load_sample_tables(data_dir, sname))
            else:
                st.info(f"{sname} not found — run the sampler first.")

    with tab_cmp:
        if not (data_dir / "sample_a").exists() or not (data_dir / "sample_b").exists():
            st.info("Both samples must be generated to compare.")
        else:
            sa = _fraud_float(_load_sample_tables(data_dir, "sample_a").get("orders", pl.DataFrame()))
            sb = _fraud_float(_load_sample_tables(data_dir, "sample_b").get("orders", pl.DataFrame()))

            if sa.is_empty() or sb.is_empty():
                st.warning("Orders data missing for one or both samples.")
                return

            metrics = {
                "Orders":          (len(sa), len(sb)),
                "GMV":             (sa["total_value"].sum(), sb["total_value"].sum()),
                "Avg Order Value": (sa["total_value"].mean(), sb["total_value"].mean()),
                "Customers":       (sa["customer_id"].n_unique(), sb["customer_id"].n_unique()),
            }
            st.subheader("Side-by-side KPIs")
            cols = st.columns(len(metrics))
            for col, (name, (va, vb)) in zip(cols, metrics.items()):
                delta = f"{(vb - va) / va * 100:+.1f}%" if va else "—"
                col.metric(name, f"{va:,.0f}", delta=f"B: {vb:,.0f} ({delta})")

            st.markdown("**Channel Mix — A vs B**")
            ca = sa.group_by("channel").agg(pl.len().alias("count")).with_columns(pl.lit("Sample A").alias("sample"))
            cb = sb.group_by("channel").agg(pl.len().alias("count")).with_columns(pl.lit("Sample B").alias("sample"))
            fig = px.bar(pl.concat([ca, cb]).to_pandas(), x="channel", y="count",
                         color="sample", barmode="group", color_discrete_sequence=COLORS[:2])
            fig.update_layout(height=320)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("**Order Status — A vs B**")
            sa2 = sa.group_by("status").agg(pl.len().alias("count")).with_columns(pl.lit("Sample A").alias("sample"))
            sb2 = sb.group_by("status").agg(pl.len().alias("count")).with_columns(pl.lit("Sample B").alias("sample"))
            fig2 = px.bar(pl.concat([sa2, sb2]).to_pandas(), x="status", y="count",
                          color="sample", barmode="group", color_discrete_sequence=COLORS[:2])
            fig2.update_layout(height=320)
            st.plotly_chart(fig2, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR: sampler config (visible for the Sampler tab)
# ════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ Sampler Config")

    total_records = st.number_input(
        "Total records per sample (all tables)",
        min_value=10_000,
        max_value=1_000_000,
        value=100_000,
        step=10_000,
        help=(
            "Target total rows across ALL tables for each sample "
            "(orders + order_lines + invoices + payments + …). "
            "The sampler joins everything first, then proportionally trims to this number."
        ),
    )
    st.divider()

    date_window_days = st.number_input("Date window (days back)", 30, 730, 90)
    anchor_mode = st.selectbox("Anchor date", ["latest", "custom"])
    anchor_value = "latest"
    if anchor_mode == "custom":
        d = st.date_input("Custom anchor date")
        anchor_value = str(d)

    seed = st.number_input("Random seed", 0, 9999, 42)
    st.divider()

    tables_cfg = [
        {"name": "orders",            "filter": "date_window", "split_anchor": True},
        {"name": "order_lines",       "join": {"parent": "orders",   "key": "order_id"}},
        {"name": "invoices",          "join": {"parent": "orders",   "key": "order_id"}},
        {"name": "payments",          "join": {"parent": "invoices", "key": "invoice_id"}},
        {"name": "stockout_events",   "join": {"parent": "orders",   "key": "order_id"}, "filter": "date_window"},
        {"name": "credit_ledger",     "join": {"parent": "orders",   "key": "customer_id"}, "filter": "date_window"},
        {"name": "customer_history",  "join": {"parent": "orders",   "key": "customer_id"}, "filter": "date_window"},
        {"name": "rep_performance",   "join": {"parent": "orders",   "key": "rep_id"}},
        {"name": "customers",         "join": {"parent": "orders",   "key": "customer_id"}},
        {"name": "rfm_scores",        "join": {"parent": "orders",   "key": "customer_id"}},
        {"name": "inventory_snapshot",        "static": True},
        {"name": "monthly_customer_snapshot", "static": True},
        {"name": "promotion_roi",             "static": True},
    ]

    config_dict = {
        "source_dir": "simulation_engine/output/tables",
        "output_dir": "data",
        "random_seed": int(seed),
        "date_window": {"anchor": anchor_value, "days": int(date_window_days)},
        "stratify_by": ["month", "channel", "status"],
        "total_records_per_sample": int(total_records),
        "samples": [{"name": "sample_a", "split": "even"}, {"name": "sample_b", "split": "odd"}],
        "tables": tables_cfg,
    }

    with st.expander("📄 YAML preview"):
        st.code(yaml.dump(config_dict, default_flow_style=False, sort_keys=False), language="yaml")

    yaml_bytes = yaml.dump(config_dict, default_flow_style=False, sort_keys=False).encode()
    st.download_button("⬇️ Download YAML", yaml_bytes, "sampler_config.yaml", "text/yaml")

    run_btn = st.button("▶ Run Sampler", type="primary", use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════

_tab_sampler, _tab_sim, _tab_pipeline = st.tabs(
    ["📊 Sampler", "⚙️ Simulation Engine", "🚀 Live Pipeline Test"]
)

# ── Sampler tab ───────────────────────────────────────────────────────────────
with _tab_sampler:
    st.caption("Configure sampling parameters in the sidebar, run, and inspect business metrics per sample.")

    if run_btn:
        # Clear stale results before each new run
        st.session_state.pop("run_success", None)
        st.session_state.pop("manifest", None)
        st.session_state.pop("data_dir", None)

        try:
            cfg = SamplerConfig.model_validate(config_dict)
        except Exception as e:
            st.error(f"Config validation failed: {e}")
            st.stop()

        log_lines: list[str] = []
        log_area = st.empty()

        class _CapturePrint:
            def write(self, s):
                if s.strip():
                    log_lines.append(s.strip())
                    log_area.code("\n".join(log_lines[-25:]))
            def flush(self):
                pass

        _orig = sys.stdout
        sys.stdout = _CapturePrint()
        try:
            with st.spinner("Running sampler…"):
                manifest = Sampler(cfg).run()
            st.session_state["manifest"] = manifest
            st.session_state["run_success"] = True
            st.session_state["data_dir"] = config_dict["output_dir"]
            st.success("Sampler complete!")
        except Exception as e:
            st.session_state["run_success"] = False
            st.error(f"Sampler failed: {e}")
        finally:
            sys.stdout = _orig

        st.rerun()

    if not st.session_state.get("run_success"):
        st.info("Configure the sampler in the sidebar and click **▶ Run Sampler** to generate samples.")
    else:
        _render_sampler_results(
            st.session_state["manifest"],
            pathlib.Path(st.session_state["data_dir"]),
        )


# ── Simulation Engine tab ─────────────────────────────────────────────────────
with _tab_sim:
    st.header("Simulation Engine")
    st.caption(
        "Run the synthetic data generator. Produces ~3 GB of Parquet files in "
        "`simulation_engine/output/tables/`. Takes **8–12 minutes** on a typical machine."
    )

    SIM_CONFIG_PATH = pathlib.Path("simulation_engine/config/simulation_config.yaml")

    if SIM_CONFIG_PATH.exists():
        raw_yaml = SIM_CONFIG_PATH.read_text()
    else:
        raw_yaml = "# simulation_config.yaml not found\n"

    try:
        sim_cfg = yaml.safe_load(raw_yaml) or {}
    except Exception:
        sim_cfg = {}

    sim_section  = sim_cfg.get("simulation", {})
    scale_section = sim_cfg.get("scale", {})

    with st.expander("Quick Settings", expanded=True):
        q1, q2, q3, q4 = st.columns(4)
        q_start     = q1.text_input("Start date",       sim_section.get("start_date", "2023-01-01"))
        q_end       = q2.text_input("End date",         sim_section.get("end_date",   "2024-06-30"))
        q_customers = q3.number_input("Initial customers", 5, 500,  int(scale_section.get("initial_customers", 20)))
        q_skus      = q4.number_input("SKU count",         50, 2000, int(scale_section.get("sku_count", 500)))

        if st.button("Apply to YAML editor ↓"):
            try:
                updated = yaml.safe_load(raw_yaml) or {}
                updated.setdefault("simulation", {})["start_date"] = q_start
                updated["simulation"]["end_date"] = q_end
                from datetime import date as _date
                try:
                    updated["simulation"]["days"] = (_date.fromisoformat(q_end) - _date.fromisoformat(q_start)).days
                except ValueError:
                    pass
                updated.setdefault("scale", {})["initial_customers"] = int(q_customers)
                updated["scale"]["sku_count"] = int(q_skus)
                st.session_state["sim_yaml_override"] = yaml.dump(updated, default_flow_style=False, sort_keys=False)
                st.rerun()
            except Exception as e:
                st.warning(f"Could not apply quick settings: {e}")

    edit_yaml = st.text_area(
        "simulation_config.yaml",
        value=st.session_state.get("sim_yaml_override", raw_yaml),
        height=380,
        key="sim_yaml_editor",
    )

    col_save, col_run = st.columns([1, 2])
    with col_save:
        if st.button("💾 Save Config"):
            try:
                yaml.safe_load(edit_yaml)
                SIM_CONFIG_PATH.write_text(edit_yaml)
                st.session_state.pop("sim_yaml_override", None)
                st.success("Saved!")
            except Exception as e:
                st.error(f"Invalid YAML: {e}")

    with col_run:
        sim_btn = st.button("▶ Run Simulation", type="primary")

    if sim_btn:
        if not SIM_CONFIG_PATH.exists():
            st.error("Save the config first.")
        elif not pathlib.Path("simulation_engine/simulation_runner.py").exists():
            st.error("`simulation_engine/simulation_runner.py` not found.")
        else:
            st.warning("This will take 8–12 minutes. Keep this tab open.")
            with st.status("Running simulation engine…", expanded=True) as status:
                result = subprocess.run(
                    [sys.executable, "simulation_runner.py"],
                    cwd="simulation_engine",
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    status.update(label="Simulation complete!", state="complete")
                    st.success("Output written to `simulation_engine/output/tables/`. Run the sampler next.")
                else:
                    status.update(label="Simulation failed", state="error")
                    st.error("Non-zero exit code.")
                combined = (result.stdout or "") + (result.stderr or "")
                if combined.strip():
                    st.code(combined[-6000:], language="text")

    output_dir = pathlib.Path("simulation_engine/output/tables")
    if output_dir.exists():
        parquet_files = list(output_dir.glob("*.parquet"))
        if parquet_files:
            total_mb = sum(p.stat().st_size for p in parquet_files) / 1_048_576
            st.success(
                f"Output available: **{len(parquet_files)} tables**, **{total_mb:,.0f} MB** in `{output_dir}`"
            )
            with st.expander("Table inventory"):
                st.dataframe(
                    [{"Table": p.stem, "Size (MB)": round(p.stat().st_size / 1_048_576, 1)}
                     for p in sorted(parquet_files)],
                    use_container_width=True, hide_index=True,
                )
    else:
        st.info("No simulation output yet. Run the simulation to generate data.")


# ── Live Pipeline Test tab ────────────────────────────────────────────────────
with _tab_pipeline:
    render_pipeline_tab()
