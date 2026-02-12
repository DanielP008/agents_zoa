"""
Timing Dashboard - Performance analytics for ZOA Agents.
Run: streamlit run test/test_latency.py
"""

import json
import os
import sys
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMING_DIR = os.getenv("TIMING_DIR", os.path.join(PROJECT_ROOT, "timings"))
JSONL_PATH = os.path.join(TIMING_DIR, "request_trace.jsonl")

# ─── KPI Defaults (ms) ───
DEFAULT_KPIS = {
    "total_ms": 2700,
    "postgres_ms": 200,
    "agent_llm_ms": 1000,
    "erp_ms": 500,
    "zoa_ms": 500,
    "wildix_ms": 500,
}

TOOL_CATEGORIES = {"erp", "zoa", "tool"}


def load_data() -> pd.DataFrame:
    """Load JSONL trace data into a DataFrame."""
    if not os.path.exists(JSONL_PATH):
        return pd.DataFrame()

    records = []
    with open(JSONL_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def explode_agents(df: pd.DataFrame) -> pd.DataFrame:
    """Explode the agents list into individual rows."""
    rows = []
    for _, row in df.iterrows():
        for agent in row.get("agents", []):
            model = agent.get("model", "") or "unknown"
            tools = [
                t for t in agent.get("tools", [])
                if t.get("category") in TOOL_CATEGORIES
            ]
            rows.append({
                "timestamp": row["timestamp"],
                "session_id": row["session_id"],
                "channel": row["channel"],
                "agent_name": agent["name"],
                "model": model,
                "agent_ms": agent["duration_ms"],
                "llm_ms": max(0, agent["duration_ms"] - sum(t["duration_ms"] for t in tools)),
                "num_tools": len(tools),
                "tool_names": ", ".join(t["name"] for t in tools),
                "tool_total_ms": sum(t["duration_ms"] for t in tools),
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def explode_tools(df: pd.DataFrame) -> pd.DataFrame:
    """Explode nested tool calls into individual rows."""
    rows = []
    for _, row in df.iterrows():
        for agent in row.get("agents", []):
            for tool in agent.get("tools", []):
                rows.append({
                    "timestamp": row["timestamp"],
                    "session_id": row["session_id"],
                    "channel": row["channel"],
                    "agent_name": agent.get("name", "unknown"),
                    "tool_name": tool.get("name", "unknown"),
                    "category": tool.get("category", "unknown"),
                    "tool_ms": tool.get("duration_ms", 0),
                })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def trimmed_mean(series: pd.Series, trim: float = 0.05) -> float:
    """Mean excluding the lowest/highest trim percent."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return 0.0
    if len(clean) < 3:
        return float(clean.mean())
    low = clean.quantile(trim)
    high = clean.quantile(1 - trim)
    trimmed = clean[(clean >= low) & (clean <= high)]
    if trimmed.empty:
        trimmed = clean
    return float(trimmed.mean())


def get_metric_series(df: pd.DataFrame, key: str) -> pd.Series:
    """Resolve metric column with backward-compatible aliases."""
    if key == "postgres_ms":
        if "postgres_ms" in df.columns and "postgres_calls" in df.columns:
            calls = pd.to_numeric(df["postgres_calls"], errors="coerce").fillna(0)
            total = pd.to_numeric(df["postgres_ms"], errors="coerce").fillna(0)
            per_call = total.div(calls.where(calls > 0), fill_value=0)
            return per_call.fillna(0)
        if "postgres_ms" in df.columns:
            return df["postgres_ms"]
        return pd.Series(dtype=float)

    if key == "agent_llm_ms":
        if "agent_pure_ms" in df.columns:
            return df["agent_pure_ms"]
        if "agent_llm_ms" in df.columns:
            return df["agent_llm_ms"]
        return pd.Series(dtype=float)

    if key in df.columns:
        return df[key]
    return pd.Series(dtype=float)


def kpi_card(label: str, value: float, target: float, unit: str = "ms"):
    """Render a KPI metric with delta against target. Green = under target, Red = over."""
    delta = value - target
    # For timing: lower is better. "inverse" flips Streamlit's default color logic:
    # negative delta (under target) shows GREEN, positive delta (over target) shows RED.
    st.metric(
        label=label,
        value=f"{value:.0f}{unit}",
        delta=f"{delta:+.0f}{unit} vs target ({target:.0f})",
        delta_color="inverse",
    )


def main():
    st.set_page_config(page_title="ZOA Timing Dashboard", layout="wide")
    st.title("ZOA Agents - Performance Dashboard")

    df = load_data()

    if df.empty:
        st.warning(f"No timing data found at `{JSONL_PATH}`. Run some requests first.")
        return

    # ─── Sidebar: Filters & KPIs ───
    st.sidebar.header("Filters")

    channels = ["All"] + sorted(df["channel"].unique().tolist())
    selected_channel = st.sidebar.selectbox("Channel", channels)
    if selected_channel != "All":
        df = df[df["channel"] == selected_channel]

    date_range = st.sidebar.date_input(
        "Date range",
        value=(df["timestamp"].min().date(), df["timestamp"].max().date()),
    )
    if len(date_range) == 2:
        df = df[(df["timestamp"].dt.date >= date_range[0]) & (df["timestamp"].dt.date <= date_range[1])]

    st.sidebar.header("KPI Targets (ms)")
    kpis = {}
    for key, default in DEFAULT_KPIS.items():
        kpis[key] = st.sidebar.number_input(f"{key}", value=default, step=100)

    if df.empty:
        st.warning("No data for the selected filters.")
        return

    # ─── KPI Cards ───
    st.header("KPIs")
    cols = st.columns(len(kpis))
    for col, (key, target) in zip(cols, kpis.items()):
        with col:
            avg = trimmed_mean(get_metric_series(df, key))
            label = key.replace("_", " ").title()
            if key == "postgres_ms":
                label = "Postgres Call Ms"
            kpi_card(label, avg, target)

    # ─── KPI Compliance ───
    st.subheader("KPI Compliance Rate")
    compliance = {}
    for key, target in kpis.items():
        metric_series = get_metric_series(df, key)
        if not metric_series.empty:
            compliance[key] = (metric_series <= target).mean() * 100
    comp_df = pd.DataFrame({"KPI": list(compliance.keys()), "Compliance %": list(compliance.values())})
    comp_df["Status"] = comp_df["Compliance %"].apply(lambda x: "PASS" if x >= 80 else "FAIL")

    fig_comp = px.bar(
        comp_df, x="KPI", y="Compliance %", color="Status",
        color_discrete_map={"PASS": "#2ecc71", "FAIL": "#e74c3c"},
        text="Compliance %"
    )
    fig_comp.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_comp.update_layout(yaxis_range=[0, 105], showlegend=False)
    st.plotly_chart(fig_comp, use_container_width=True)

    # ─── Overview Stats ───
    st.header("Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Requests", len(df))
    col2.metric("Avg Total (ms)", f"{trimmed_mean(df['total_ms']):.0f}")
    col3.metric("P95 Total (ms)", f"{df['total_ms'].quantile(0.95):.0f}")
    col4.metric("Max Total (ms)", f"{df['total_ms'].max():.0f}")

    # ─── Time Breakdown (stacked area) ───
    st.header("Time Breakdown Over Requests")
    breakdown_cols = ["postgres_ms", "agent_llm_ms", "tool_calls_ms", "wildix_ms", "other_ms"]
    existing_cols = [c for c in breakdown_cols if c in df.columns]
    if existing_cols:
        chart_df = df[["timestamp"] + existing_cols].copy()
        
        # Ensure no negative values for the area chart
        for col in existing_cols:
            chart_df[col] = chart_df[col].clip(lower=0)
            
        chart_df = chart_df.sort_values("timestamp").reset_index(drop=True)
        chart_df["request_num"] = range(1, len(chart_df) + 1)

        fig_area = go.Figure()
        colors = {"postgres_ms": "#3498db", "agent_llm_ms": "#e74c3c", "tool_calls_ms": "#f39c12", "wildix_ms": "#9b59b6", "other_ms": "#95a5a6"}
        for col_name in existing_cols:
            fig_area.add_trace(go.Scatter(
                x=chart_df["request_num"], y=chart_df[col_name],
                mode="lines", stackgroup="one",
                name=col_name.replace("_ms", "").replace("_", " ").title(),
                line=dict(color=colors.get(col_name, "#333")),
            ))
        fig_area.update_layout(xaxis_title="Request #", yaxis_title="Time (ms)")
        st.plotly_chart(fig_area, use_container_width=True)

    # ─── Distribution Histograms ───
    st.header("Distributions")
    col_left, col_right = st.columns(2)

    with col_left:
        fig_hist = px.histogram(df, x="total_ms", nbins=30, title="Total Request Time Distribution")
        if "total_ms" in kpis:
            fig_hist.add_vline(x=kpis["total_ms"], line_dash="dash", line_color="red", annotation_text=f"KPI: {kpis['total_ms']}ms")
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_right:
        fig_box = px.box(
            df.melt(value_vars=[c for c in ["postgres_ms", "agent_llm_ms", "tool_calls_ms", "erp_ms", "zoa_ms", "wildix_ms"] if c in df.columns]),
            x="variable", y="value",
            title="Time Distribution by Category",
            labels={"variable": "Category", "value": "Time (ms)"}
        )
        st.plotly_chart(fig_box, use_container_width=True)

    # ─── Per-Agent Analysis ───
    st.header("Per-Agent Performance")
    agent_df = explode_agents(df)
    if not agent_df.empty:
        agent_stats = agent_df.groupby("agent_name").agg(
            count=("agent_ms", "count"),
            avg_ms_95=("agent_ms", lambda x: x.quantile(0.95)),
            p95_ms=("agent_ms", lambda x: x.quantile(0.95)),
            max_ms=("agent_ms", "max"),
            avg_tools=("num_tools", "mean"),
            avg_tool_ms=("tool_total_ms", "mean"),
        ).round(1).sort_values("avg_ms_95", ascending=False)

        st.dataframe(agent_stats, use_container_width=True)

        fig_agents = px.bar(
            agent_stats.reset_index(), x="agent_name", y=["avg_ms_95"],
            title="Agent Duration (avg_ms_95)",
            labels={"value": "Time (ms)", "agent_name": "Agent"},
        )
        st.plotly_chart(fig_agents, use_container_width=True)

    # ─── Per-Model Performance ───
    st.header("Per-Model Performance")
    if not agent_df.empty and "model" in agent_df.columns:
        model_df = agent_df[agent_df["model"] != "unknown"]
        if not model_df.empty:
            model_stats = model_df.groupby("model").agg(
                calls=("agent_ms", "count"),
                avg_total_ms=("agent_ms", "mean"),
                avg_llm_ms=("llm_ms", "mean"),
                p95_ms=("agent_ms", lambda x: x.quantile(0.95)),
                max_ms=("agent_ms", "max"),
                min_ms=("agent_ms", "min"),
            ).round(1).sort_values("avg_llm_ms", ascending=True)

            st.dataframe(model_stats, use_container_width=True)

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                fig_model_bar = px.bar(
                    model_stats.reset_index(), x="model", y="avg_llm_ms",
                    title="Average LLM Time by Model",
                    labels={"avg_llm_ms": "Avg LLM Time (ms)", "model": "Model"},
                    color="model",
                    text="avg_llm_ms",
                )
                fig_model_bar.update_traces(texttemplate="%{text:.0f}ms", textposition="outside")
                st.plotly_chart(fig_model_bar, use_container_width=True)

            with col_m2:
                fig_model_box = px.box(
                    model_df, x="model", y="llm_ms",
                    title="LLM Time Distribution by Model",
                    labels={"llm_ms": "LLM Time (ms)", "model": "Model"},
                    color="model",
                )
                st.plotly_chart(fig_model_box, use_container_width=True)

            # Model + Agent breakdown
            st.subheader("Model x Agent Breakdown")
            model_agent_stats = model_df.groupby(["model", "agent_name"]).agg(
                calls=("agent_ms", "count"),
                avg_llm_ms=("llm_ms", "mean"),
                avg_total_ms=("agent_ms", "mean"),
            ).round(1).sort_values(["model", "avg_llm_ms"], ascending=[True, False])

            st.dataframe(model_agent_stats, use_container_width=True)
        else:
            st.info("No model data captured yet. Model tracking was added recently.")
    else:
        st.info("No agent data available.")

    # ─── Per-Tool Performance ───
    st.header("Per-Tool Performance")
    tool_df = explode_tools(df)
    if not tool_df.empty:
        tool_stats = tool_df.groupby(["tool_name", "category"]).agg(
            calls=("tool_ms", "count"),
            avg_ms=("tool_ms", "mean"),
            p95_ms=("tool_ms", lambda x: x.quantile(0.95)),
            max_ms=("tool_ms", "max"),
            min_ms=("tool_ms", "min"),
        ).round(1).sort_values("avg_ms", ascending=False)

        st.dataframe(tool_stats, use_container_width=True)

        fig_tools = px.bar(
            tool_stats.reset_index(),
            x="tool_name",
            y="avg_ms",
            color="category",
            text="avg_ms",
            title="Average Tool Duration",
            labels={"avg_ms": "Avg Time (ms)", "tool_name": "Tool"},
        )
        fig_tools.update_traces(texttemplate="%{text:.0f}ms", textposition="outside")
        st.plotly_chart(fig_tools, use_container_width=True)
    else:
        st.info("No tool calls recorded yet.")

    # ─── Postgres Breakdown ───
    st.header("Postgres Operations")
    pg_rows = []
    for _, row in df.iterrows():
        for op in row.get("postgres_detail", []):
            pg_rows.append({"op": op["op"], "duration_ms": op["duration_ms"], "timestamp": row["timestamp"]})

    if pg_rows:
        pg_df = pd.DataFrame(pg_rows)
        pg_stats = pg_df.groupby("op").agg(
            count=("duration_ms", "count"),
            avg_ms=("duration_ms", "mean"),
            p95_ms=("duration_ms", lambda x: x.quantile(0.95)),
            max_ms=("duration_ms", "max"),
        ).round(1).sort_values("avg_ms", ascending=False)
        st.dataframe(pg_stats, use_container_width=True)

    # ─── Channel Comparison ───
    if df["channel"].nunique() > 1:
        st.header("Channel Comparison")
        channel_stats = df.groupby("channel").agg(
            count=("total_ms", "count"),
            avg_total=("total_ms", "mean"),
            avg_postgres=("postgres_ms", "mean"),
            avg_agent=("agent_llm_ms", "mean"),
        ).round(1)
        st.dataframe(channel_stats, use_container_width=True)

    # ─── Raw Data ───
    with st.expander("Raw Data"):
        display_cols = [c for c in ["timestamp", "session_id", "channel", "total_ms", "postgres_ms",
                                     "agent_llm_ms", "tool_calls_ms", "erp_ms", "zoa_ms", "wildix_ms"] if c in df.columns]
        st.dataframe(df[display_cols].sort_values("timestamp", ascending=False), use_container_width=True)


if __name__ == "__main__":
    main()
