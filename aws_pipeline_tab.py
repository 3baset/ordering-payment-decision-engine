"""
Live Pipeline Test tab for the ODA Streamlit dashboard.

Lets you pick a record from Sample A or B, send it to the live oda-orders
DynamoDB table, and watch the Decision + Action Lambdas process it in real time.

Requirements:
  AWS credentials configured in your environment (same profile used for cdk deploy).
  pip install boto3 pyarrow polars
"""

import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

import polars as pl
import streamlit as st

# ── Constants ─────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
ORDERS_TABLE   = "oda-orders"
ACTION_LOG_TABLE = "oda-action-log"
POLL_INTERVAL  = 2          # seconds between DynamoDB reads
POLL_TIMEOUT   = 45         # seconds before giving up


def _safe_decimal(value) -> Decimal:
    try:
        return Decimal(str(float(value)))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal("0")


def _to_dynamo_item(row: dict) -> dict:
    """Convert a Polars row dict to a DynamoDB-compatible item."""
    item = {}
    for k, v in row.items():
        if v is None:
            continue
        if isinstance(v, float):
            item[k] = _safe_decimal(v)
        elif isinstance(v, int):
            item[k] = _safe_decimal(v)
        else:
            s = str(v)
            if s not in ("", "None", "nan", "null"):
                item[k] = s
    # Stamp a fresh order_id so each test send is unique and won't collide
    item["order_id"] = f"TEST-{uuid.uuid4().hex[:12].upper()}"
    return item


@st.cache_data(ttl=300)
def _load_sample(sample: str) -> pl.DataFrame:
    path = DATA_DIR / sample / "orders.parquet"
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _get_dynamo():
    """Return a boto3 DynamoDB resource; return None if credentials not configured."""
    try:
        import boto3
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        # Probe connectivity by calling describe_table (cheap and auth-checked)
        resource.meta.client.describe_table(TableName=ORDERS_TABLE)
        return resource
    except Exception:
        return None


def _poll_for_decision(ddb, order_id: str, deadline: float) -> dict | None:
    """Poll oda-orders until 'decision' attribute appears or deadline passes."""
    table = ddb.Table(ORDERS_TABLE)
    while time.time() < deadline:
        resp = table.get_item(Key={"order_id": order_id})
        item = resp.get("Item", {})
        if item.get("decision"):
            return item
        time.sleep(POLL_INTERVAL)
    return None


def _fetch_action_log(ddb, order_id: str) -> dict | None:
    """Scan action-log for the matching order_id (small scan; demo only)."""
    table = ddb.Table(ACTION_LOG_TABLE)
    resp  = table.scan(
        FilterExpression="order_id = :oid",
        ExpressionAttributeValues={":oid": order_id},
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def _outcome_badge(outcome: str) -> str:
    colours = {"AUTO_APPROVE": "🟢", "MANUAL_REVIEW": "🟡", "DECLINE": "🔴"}
    return f"{colours.get(outcome, '⚪')} **{outcome}**"


def render_pipeline_tab() -> None:
    st.header("Live Pipeline Test")
    st.caption(
        "Select a record from the pre-generated sample data, send it to the live "
        "AWS pipeline, and watch the Decision + Action Lambdas process it in real time."
    )

    # ── Credentials check ─────────────────────────────────────────────────────
    ddb = _get_dynamo()
    if ddb is None:
        st.error(
            "AWS credentials not found or `oda-orders` table unreachable. "
            "Configure credentials with the same AWS profile used for `cdk deploy` "
            "(`aws configure` or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars)."
        )
        return

    st.success("AWS connection OK — `oda-orders` table reachable.")

    # ── Sample & filter controls ──────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        sample = st.selectbox("Sample", ["sample_a", "sample_b"])
    with col2:
        segment_filter = st.selectbox("Segment", ["All", "premium", "standard", "at-risk", "new", "churned"])
    with col3:
        payment_filter = st.selectbox("Payment method", ["All", "cash", "credit", "cheque", "bank_transfer", "cod"])
    with col4:
        fraud_max = st.slider("Max fraud score", 0.0, 1.0, 1.0, 0.05)

    df = _load_sample(sample)
    if df.is_empty():
        st.warning(f"No data found in `data/{sample}/orders.parquet`. Run the sampler first.")
        return

    # Map simulation segment labels to Lambda labels for display consistency
    segment_map = {"premium": "premium", "regular": "standard", "low_volume": "at-risk"}
    if "customer_segment" in df.columns:
        df = df.with_columns(
            pl.col("customer_segment").replace(segment_map).alias("customer_segment")
        )

    # Apply filters
    filtered = df
    if segment_filter != "All" and "customer_segment" in df.columns:
        filtered = filtered.filter(pl.col("customer_segment") == segment_filter)
    if payment_filter != "All" and "payment_method" in df.columns:
        filtered = filtered.filter(pl.col("payment_method") == payment_filter)
    if "fraud_score" in df.columns:
        filtered = filtered.filter(pl.col("fraud_score").cast(pl.Float64, strict=False) <= fraud_max)

    st.caption(f"{len(filtered):,} records match your filters (showing first 10).")

    if filtered.is_empty():
        st.info("No records match the current filters. Adjust and try again.")
        return

    preview_df = filtered.head(10)

    # ── Record selector ───────────────────────────────────────────────────────
    display_cols = [c for c in ("order_id", "customer_segment", "payment_method", "fraud_score", "total_value")
                    if c in preview_df.columns]
    st.dataframe(preview_df.select(display_cols), use_container_width=True, hide_index=True)

    order_ids = preview_df["order_id"].to_list()
    selected_id = st.selectbox("Select an order to send →", order_ids)

    selected_row = preview_df.filter(pl.col("order_id") == selected_id).to_dicts()[0]

    with st.expander("Preview: DynamoDB item that will be inserted"):
        display_item = {k: str(v) for k, v in selected_row.items() if v is not None}
        st.json(display_item)

    # ── Send button ───────────────────────────────────────────────────────────
    send_btn = st.button("▶ Send to Pipeline", type="primary")

    if send_btn:
        st.session_state["pipeline_pending"] = True
        st.session_state["pipeline_item"]    = _to_dynamo_item(selected_row)
        st.session_state["pipeline_sent_at"] = time.time()
        st.session_state["pipeline_result"]  = None

    # ── Polling loop ──────────────────────────────────────────────────────────
    if st.session_state.get("pipeline_pending"):
        item     = st.session_state["pipeline_item"]
        order_id = item["order_id"]
        sent_at  = st.session_state["pipeline_sent_at"]

        if not st.session_state.get("pipeline_inserted"):
            try:
                ddb.Table(ORDERS_TABLE).put_item(Item=item)
                st.session_state["pipeline_inserted"] = True
            except Exception as e:
                st.error(f"Failed to insert record: {e}")
                st.session_state["pipeline_pending"] = False
                return

        elapsed = int(time.time() - sent_at)
        deadline = sent_at + POLL_TIMEOUT
        result = _poll_for_decision(ddb, order_id, min(time.time() + POLL_INTERVAL, deadline))

        if result:
            st.session_state["pipeline_result"]  = result
            st.session_state["pipeline_pending"] = False
            st.session_state["pipeline_inserted"] = False
        elif time.time() >= deadline:
            st.session_state["pipeline_pending"] = False
            st.session_state["pipeline_inserted"] = False
            st.warning(f"Decision Lambda did not respond within {POLL_TIMEOUT}s. Check CloudWatch logs.")
            return
        else:
            with st.spinner(f"Waiting for Decision Lambda… ({elapsed}s elapsed)"):
                time.sleep(POLL_INTERVAL)
            st.rerun()

    # ── Result display ────────────────────────────────────────────────────────
    result = st.session_state.get("pipeline_result")
    if result:
        order_id = result.get("order_id", "")
        outcome  = result.get("decision", "UNKNOWN")
        score    = float(result.get("decision_score", 0))

        st.divider()
        st.subheader(f"Result for `{order_id}`")

        col_out, col_score = st.columns([2, 3])
        with col_out:
            st.markdown(f"**Decision:** {_outcome_badge(outcome)}")
            st.metric("Composite score", f"{score:.3f}")
        with col_score:
            import plotly.graph_objects as go
            ltv_s  = float(result.get("ltv_score", 0))
            fac    = float(result.get("fraud_approval_component", 0))
            pay_s  = float(result.get("payment_score", 0))
            fig = go.Figure(go.Bar(
                x=[ltv_s, fac, pay_s],
                y=["LTV (40%)", "Fraud approval (35%)", "Payment (25%)"],
                orientation="h",
                marker_color=["#4C78A8", "#F58518", "#54A24B"],
                text=[f"{v:.3f}" for v in [ltv_s, fac, pay_s]],
                textposition="auto",
            ))
            fig.update_layout(
                xaxis=dict(range=[0, 1], title="Score"),
                height=180,
                margin=dict(l=0, r=0, t=10, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

        # Try fetching action log entry
        try:
            action_entry = _fetch_action_log(ddb, order_id)
            if action_entry:
                st.markdown(
                    f"**Action:** `{action_entry.get('action')}` "
                    f"(priority: **{action_entry.get('priority')}**)"
                )
                st.caption(action_entry.get("action_detail", ""))
            else:
                st.info("Action Lambda has not yet processed this order (or action log scan returned empty).")
        except Exception:
            pass

        st.caption(
            f"Order `{order_id}` processed at "
            f"{result.get('decision_at', 'n/a')} ms epoch. "
            f"Model version: `{result.get('model_version', 'v1.0')}`"
        )

        if st.button("↺ Send another record"):
            st.session_state.pop("pipeline_result", None)
            st.rerun()
