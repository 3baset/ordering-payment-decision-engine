"""
ODA Data Sampler Dashboard
Run: streamlit run sampler_dashboard.py
"""
import pathlib
import sys
import yaml
import polars as pl
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from data_sampler import Sampler, SamplerConfig
from aws_pipeline_tab import render_pipeline_tab


def _t(name: str, **kwargs) -> dict:
    """Build a table config dict, dropping None-valued kwargs (avoids Streamlit magic rendering)."""
    return {"name": name, **{k: v for k, v in kwargs.items() if v is not None}}

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ODA Data Sampler",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("ODA Data Sampler")
st.caption("Configure sampling from the simulation engine, run, and inspect business metrics per sample.")

# ── Sidebar: Config panel ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Config")

    target_rows = st.number_input("Target rows per sample", 50_000, 250_000, 100_000, 5_000,
                                   help="Approximate order count per sample. null = full 50/50 split.")
    tolerance_pct = st.slider("Tolerance ±%", 5, 25, 10,
                               help="Accepted band around target_rows.")
    st.divider()

    date_window_days = st.number_input("Date window (days back)", 30, 730, 90)
    anchor_mode = st.selectbox("Anchor date", ["latest", "custom"])
    anchor_value = "latest"
    if anchor_mode == "custom":
        d = st.date_input("Custom anchor date")
        anchor_value = str(d)

    seed = st.number_input("Random seed", 0, 9999, 42)
    st.divider()

    st.subheader("Per-table limits (optional)")
    st.caption("Leave blank to apply no limit to that table.")
    stockout_limit_rows = st.number_input("stockout_events limit_rows", 0, 2_000_000, 0,
                                          help="0 = no limit")
    credit_limit_rows   = st.number_input("credit_ledger limit_rows",   0, 1_000_000, 0)
    stockout_limit_rows = int(stockout_limit_rows) or None
    credit_limit_rows   = int(credit_limit_rows)   or None

    st.divider()

    # ── Build config dict from UI state ──────────────────────────────────────
    # Use _t() helper so None-valued kwargs are never added to the dict,
    # avoiding Streamlit's magic from rendering their return values.
    tables_cfg = [
        _t("orders",           filter="date_window", split_anchor=True),
        _t("order_lines",      join={"parent": "orders",   "key": "order_id"}),
        _t("invoices",         join={"parent": "orders",   "key": "order_id"}),
        _t("payments",         join={"parent": "invoices", "key": "invoice_id"}),
        _t("stockout_events",  join={"parent": "orders",   "key": "order_id"},
           filter="date_window", limit_rows=stockout_limit_rows),
        _t("credit_ledger",    join={"parent": "orders",   "key": "customer_id"},
           filter="date_window", limit_rows=credit_limit_rows),
        _t("customer_history", join={"parent": "orders",   "key": "customer_id"},
           filter="date_window"),
        _t("rep_performance",  join={"parent": "orders",   "key": "rep_id"}),
        _t("customers",        join={"parent": "orders",   "key": "customer_id"}),
        _t("rfm_scores",       join={"parent": "orders",   "key": "customer_id"}),
        _t("inventory_snapshot",        static=True),
        _t("monthly_customer_snapshot", static=True),
        _t("promotion_roi",             static=True),
    ]

    config_dict = {
        "source_dir": "simulation_engine/output/tables",
        "output_dir": "data",
        "random_seed": int(seed),
        "date_window": {"anchor": anchor_value, "days": int(date_window_days)},
        "stratify_by": ["month", "channel", "status"],
        "target_rows": int(target_rows),
        "tolerance": tolerance_pct / 100,
        "samples": [{"name": "sample_a", "split": "even"}, {"name": "sample_b", "split": "odd"}],
        "tables": tables_cfg,
    }

    with st.expander("📄 YAML preview"):
        st.code(yaml.dump(config_dict, default_flow_style=False, sort_keys=False), language="yaml")

    yaml_bytes = yaml.dump(config_dict, default_flow_style=False, sort_keys=False).encode()
    st.download_button("⬇️ Download YAML", yaml_bytes, "sampler_config.yaml", "text/yaml")

    run_btn = st.button("▶ Run Sampler", type="primary", use_container_width=True)

# ── Run logic ─────────────────────────────────────────────────────────────────
if run_btn:
    try:
        cfg = SamplerConfig.model_validate(config_dict)
    except Exception as e:
        st.error(f"Config validation failed: {e}")
        st.stop()

    progress = st.progress(0, "Initialising sampler…")
    log_area = st.empty()
    log_lines: list[str] = []

    class _CapturePrint:
        def write(self, s):
            if s.strip():
                log_lines.append(s.strip())
                log_area.code("\n".join(log_lines[-20:]))
        def flush(self): pass

    import sys as _sys
    _orig = _sys.stdout
    _sys.stdout = _CapturePrint()
    try:
        manifest = Sampler(cfg).run()
        st.session_state["manifest"] = manifest
        st.session_state["run_success"] = True
        st.session_state["data_dir"] = config_dict["output_dir"]
    except Exception as e:
        st.session_state["run_success"] = False
        st.error(f"Sampler failed: {e}")
    finally:
        _sys.stdout = _orig
        progress.progress(100, "Done")

# ── Helpers (defined before tabs so they're available inside both) ─────────────

COLORS = px.colors.qualitative.Set2


def _fraud_float(df: pl.DataFrame) -> pl.DataFrame:
    if "fraud_score" in df.schema and df["fraud_score"].dtype == pl.Utf8:
        df = df.with_columns(pl.col("fraud_score").cast(pl.Float64, strict=False))
    return df


def _load_sample_tables(data_dir: pathlib.Path, sample_name: str) -> dict[str, pl.DataFrame]:
    d = data_dir / sample_name
    tables = {}
    for p in d.glob("*.parquet"):
        tables[p.stem] = pl.read_parquet(p)
    return tables


def render_sample(sample_name: str, tables: dict[str, pl.DataFrame]) -> None:
    orders    = _fraud_float(tables.get("orders", pl.DataFrame()))
    payments  = tables.get("payments", pl.DataFrame())
    customers = tables.get("customers", pl.DataFrame())

    if orders.is_empty():
        st.warning(f"No orders found for {sample_name}")
        return

    # ── KPI row ──────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Orders",           f"{len(orders):,}")
    k2.metric("GMV",              f"EGP {orders['total_value'].sum():,.0f}")
    k3.metric("Avg Order Value",  f"EGP {orders['total_value'].mean():,.0f}")
    k4.metric("Unique Customers", f"{orders['customer_id'].n_unique():,}")
    high_fraud = (orders["fraud_score"] > 0.5).sum() if "fraud_score" in orders.schema else 0
    k5.metric("High-Fraud Orders", f"{high_fraud:,}")

    st.markdown("---")
    col_l, col_r = st.columns(2)

    with col_l:
        ch = (orders.group_by("channel").agg(pl.len().alias("orders"))
              .sort("orders", descending=True))
        fig = px.bar(ch.to_pandas(), x="channel", y="orders",
                     title="Orders by Channel", color="channel",
                     color_discrete_sequence=COLORS)
        fig.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st_df = orders.group_by("status").agg(pl.len().alias("count"))
        fig = px.pie(st_df.to_pandas(), names="status", values="count",
                     title="Order Status", hole=0.4,
                     color_discrete_sequence=COLORS)
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
            pm = (payments.group_by("payment_method").agg(pl.len().alias("count"))
                  .sort("count", descending=True))
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
        fig = px.line(mo.to_pandas(), x="month", y="gmv",
                      title="Monthly GMV", markers=True,
                      color_discrete_sequence=[COLORS[0]])
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col_r3:
        if not customers.is_empty() and "customer_type" in customers.schema:
            ct = (customers.group_by("customer_type").agg(pl.len().alias("count"))
                  .sort("count", descending=True))
            fig = px.bar(ct.to_pandas(), x="customer_type", y="count",
                         title="Customer Type Breakdown", color="customer_type",
                         color_discrete_sequence=COLORS)
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)


def _render_sampler_results(manifest, data_dir: pathlib.Path) -> None:
    st.divider()
    st.subheader("📋 Manifest")

    manifest_rows = [
        {"Sample": e.sample, "Table": e.table, "Rows": e.rows, "Size (MB)": round(e.size_mb, 1)}
        for e in manifest.entries
    ]
    st.dataframe(manifest_rows, use_container_width=True, hide_index=True)

    total_mb = sum(e.size_mb for e in manifest.entries)
    non_ref  = [e for e in manifest.entries if e.sample != "reference"]
    st.caption(f"Total size: **{total_mb:.1f} MB** across {len(manifest.entries)} files "
               f"({sum(e.rows for e in non_ref):,} non-reference rows).")

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
            else:
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
                    col.metric(f"{name}", f"{va:,.0f}", delta=f"B: {vb:,.0f} ({delta})")

                st.markdown("**Channel Mix — A vs B**")
                ca = (sa.group_by("channel").agg(pl.len().alias("count"))
                      .with_columns(pl.lit("Sample A").alias("sample")))
                cb = (sb.group_by("channel").agg(pl.len().alias("count"))
                      .with_columns(pl.lit("Sample B").alias("sample")))
                cmp_df = pl.concat([ca, cb]).to_pandas()
                fig = px.bar(cmp_df, x="channel", y="count", color="sample",
                             barmode="group", color_discrete_sequence=COLORS[:2])
                fig.update_layout(height=320)
                st.plotly_chart(fig, use_container_width=True)

                st.markdown("**Order Status — A vs B**")
                sa2 = (sa.group_by("status").agg(pl.len().alias("count"))
                       .with_columns(pl.lit("Sample A").alias("sample")))
                sb2 = (sb.group_by("status").agg(pl.len().alias("count"))
                       .with_columns(pl.lit("Sample B").alias("sample")))
                cmp2 = pl.concat([sa2, sb2]).to_pandas()
                fig2 = px.bar(cmp2, x="status", y="count", color="sample",
                              barmode="group", color_discrete_sequence=COLORS[:2])
                fig2.update_layout(height=320)
                st.plotly_chart(fig2, use_container_width=True)


# ── Main tabs (always visible) ────────────────────────────────────────────────
_tab_sampler, _tab_pipeline = st.tabs(["📊 Sampler Results", "🚀 Live Pipeline Test"])

with _tab_pipeline:
    render_pipeline_tab()

with _tab_sampler:
    if not st.session_state.get("run_success"):
        st.info("Configure the sampler in the sidebar and click **▶ Run Sampler** to generate samples.")
    else:
        _render_sampler_results(
            st.session_state["manifest"],
            pathlib.Path(st.session_state["data_dir"]),
        )
