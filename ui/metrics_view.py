"""Metrics tab (PRD sections 6.7 / 7.2), read entirely from eval-log.json."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from chalk.config import describe_provider, effective_env
from chalk.metrics import (
    MonthlyCost,
    month_key,
    monthly_costs,
    previous_month_key,
    read_events,
    summarize_events,
)
from chalk.project import ProjectPaths
from chalk.report import render_evaluation_report


def render(paths: ProjectPaths) -> None:
    events = read_events(paths.eval_log)
    summary = summarize_events(events)
    months = monthly_costs(events)
    by_month = {m.month: m.cost_usd for m in months}
    today = dt.date.today()
    this_month = by_month.get(month_key(today), 0.0)
    last_month = by_month.get(previous_month_key(today))

    cost, rollovers, catches, errors = st.columns(4)
    cost.metric(
        "AI cost this month",
        f"${this_month:.4f}",
        delta=None if last_month is None else _vs_last_month(this_month - last_month),
        delta_color="off",  # more use isn't bad news, so no red/green
        help="Calendar months in this computer's time zone.",
    )
    rollovers.metric("Rollovers", len(summary.rollovers))
    catches.metric(
        "Consistency-check catches",
        summary.consistency_failures,
        help=f"Overridden with Continue anyway: {summary.consistency_overrides}",
    )
    errors.metric("Extraction errors", len(summary.extraction_errors))
    st.caption(f"All-time AI cost: ${summary.total_cost_usd:.4f}")
    st.caption(f"Provider in use: {describe_provider(effective_env(paths.env))}")
    st.download_button(
        "Download evaluation report",
        data=render_evaluation_report(events, project_name=paths.root.name, generated_on=dt.date.today()),
        file_name=f"{paths.root.name}-evaluation-report.md",
        mime="text/markdown",
        help="Files processed, consistency-check catches, error rates, and cost per content type.",
    )

    st.markdown("#### Generations by type")
    if summary.generation_counts:
        st.bar_chart(pd.Series(summary.generation_counts, name="Generations"))
    else:
        st.caption("No content generated yet.")

    st.markdown("#### AI cost by month")
    if months:
        _render_monthly_costs(months)
    else:
        st.caption("No AI costs yet.")

    st.markdown("#### Rollover history")
    if summary.rollovers:
        st.dataframe(
            [
                {
                    "When": event["timestamp"][:16].replace("T", " "),
                    "From": event.get("source_term", ""),
                    "To": event.get("target_term", ""),
                    "Weeks": f"{event.get('source_duration_weeks')} → {event.get('target_duration_weeks')}",
                    "Flags": event.get("flag_count", 0),
                }
                for event in reversed(summary.rollovers)
            ],
            hide_index=True,
        )
    else:
        st.caption("No rollovers yet.")

    if summary.extraction_errors:
        st.markdown("#### Extraction errors")
        st.dataframe(
            [
                {
                    "When": event["timestamp"][:16].replace("T", " "),
                    "File": event.get("filename", ""),
                    "Error": event.get("error_type", ""),
                }
                for event in reversed(summary.extraction_errors)
            ],
            hide_index=True,
        )


def _vs_last_month(change: float) -> str:
    return f"{'-' if change < 0 else '+'}${abs(change):.4f} vs last month"


def _render_monthly_costs(months: list[MonthlyCost]) -> None:
    """Stacked by content type, so it's clear what the money went on; the
    table's average shows whether a spike is more use or pricier calls."""
    by_type = pd.DataFrame({m.month: m.cost_by_type for m in months}).T.fillna(0.0)
    st.bar_chart(by_type, x_label="Month", y_label="Cost (USD)")
    st.dataframe(
        [
            {
                "Month": m.month,
                "Generations": m.generations,
                "Cost": f"${m.cost_usd:.4f}",
                "Avg cost / generation": f"${m.avg_cost_usd:.4f}" if m.generations else "—",
            }
            for m in reversed(months)
        ],
        hide_index=True,
    )
