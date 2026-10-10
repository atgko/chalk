"""Drafts tab: the generated files saved from the Generate tab, by
content type and week, each with a preview and a download. Earlier
versions stay in each folder's .archive/ and are only counted here."""

from __future__ import annotations

import streamlit as st

from chalk.generation.document_export import can_export
from chalk.generation.library import SavedDraft, list_saved_drafts
from chalk.project import ProjectPaths
from ui import common

ALL_TYPES = "All types"


def render(paths: ProjectPaths) -> None:
    drafts = list_saved_drafts(paths)
    if not drafts:
        st.info("No saved drafts yet. Generate one on the Generate tab and click Save.")
        return

    labels = list(dict.fromkeys(d.spec.label for d in drafts))
    shown = st.selectbox("Show", [ALL_TYPES, *labels])
    if shown != ALL_TYPES:
        drafts = [d for d in drafts if d.spec.label == shown]
    count = f"{len(drafts)} saved draft{'s' if len(drafts) != 1 else ''}"
    st.caption(f"{count}. Saving a new version archives the old one.")

    for draft in drafts:
        with st.expander(draft.title):
            _render_draft(paths, draft)


def _render_draft(paths: ProjectPaths, draft: SavedDraft) -> None:
    st.caption(_describe(paths, draft))
    text = draft.path.read_text(encoding="utf-8")
    if draft.spec.key == "slides":
        st.code(text, language="markdown")
    else:
        st.markdown(text)

    if not can_export(draft.spec.key):
        common.download_button(draft.path, paths, key_prefix="drafts")
        return
    common.export_buttons(
        text,
        content_type=draft.spec.key,
        subject=draft.subject,
        base_name=draft.path.stem,
        key=f"drafts-{common.relative(draft.path, paths)}",
    )


def _describe(paths: ProjectPaths, draft: SavedDraft) -> str:
    saved = f"{draft.saved_at:%b} {draft.saved_at.day}, {draft.saved_at:%Y}"
    parts = [f"Saved {saved}", common.relative(draft.path, paths)]
    if draft.archived_versions:
        count = draft.archived_versions
        parts.append(f"{count} earlier version{'s' if count != 1 else ''} in .archive/")
    return " · ".join(parts)
