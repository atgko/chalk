"""Metrics tab (PRD sections 6.7 / 7.2), read entirely from eval-log.json."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from chalk.config import describe_provider, read_env
from chalk.metrics import read_events, summarize_events
from chalk.project import ProjectPaths


def render(paths: ProjectPaths) -> None:
    summary = summarize_events(read_events(paths.eval_log))

    cost, rollovers, catches, errors = st.columns(4)
    cost.metric("Total AI cost", f"${summary.total_cost_usd:.4f}")
    rollovers.metric("Rollovers", len(summary.rollovers))
    catches.metric(
        "Consistency-check catches",
        summary.consistency_failures,
        help=f"Overridden with Continue anyway: {summary.consistency_overrides}",
    )
    errors.metric("Extraction errors", len(summary.extraction_errors))
    st.caption(f"Provider in use: {describe_provider(read_env(paths.env))}")

    st.markdown("#### Generations by type")
    if summary.generation_counts:
        st.bar_chart(pd.Series(summary.generation_counts, name="Generations"))
    else:
        st.caption("No content generated yet.")

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
