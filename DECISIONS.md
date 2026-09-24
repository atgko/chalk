# Chalk — Implementation Decisions Log

> Working name: **Chalk**. Kept behind a single config/constant so it can be renamed later without touching multiple files (repo name, `app.py` title, README heading, Canvas HTML comment all derive from one place).
>
> This document records decisions made in a pre-build interview that fill gaps or resolve ambiguities in `capstone-prd-v3.1.md`. It supplements the PRD — it does not replace it. Where a decision conflicts with literal PRD wording, this document wins; the PRD section is still noted for traceability.

## Architecture

- **course.json validation**: Pydantic models (e.g. `Course`, `Week`, `Assessment`), not raw dicts + jsonschema. Every module (extractors, rollover, generation, UI) works with typed models. (Build order step 2.)
- **eval-log.json format**: JSON Lines (JSONL) — one JSON object per line, opened in append mode. Not a single JSON array (which would require read-modify-write on every event). (Section 6.7.)
- **course.json archiving**: Archived to `.archive/` (same convention as `outputs/`) on every re-extraction/re-save from the Review tab, not just on `outputs/` writes. (Extends F-06 / Section 5.1.)
- **LLM retries**: `llm_client.complete()` retries transient errors (rate limit, timeout) 2-3 times with short exponential backoff before raising `LLMProviderError`. (Section 4.1.)
- **Source material context (F-05)**: Naive full-text concatenation of selected `source/` files into the prompt, with a token-budget truncation rule. No embeddings/vector DB for MVP.
- **Duration expansion (F-02)**: If `duration_weeks` increases during rollover beyond the originally extracted weeks, the LLM drafts placeholder topics for the new weeks, clearly labeled as an AI draft requiring review. (Section 6.2.)

## Technology choices

- **PDF parsing**: `pypdf` (pure-Python, no system deps — sufficient for instructor-authored summaries/excerpts).
- **Password-protected `.docx` detection**: Catch the exception python-docx raises (`BadZipFile`/`PackageNotFoundError`) rather than pre-checking the zip structure; surface the existing plain-English message.
- **Test stack**: `pytest` + `pytest-cov`.
- **Test fixtures for extractors**: Minimal synthetic `.docx`/`.md` documents generated programmatically (one fixture per parsing rule), not trimmed real test-corpus syllabi.
- **`.env` loading**: `python-dotenv` (standard choice, not called out explicitly in the PRD).

## UI / UX

- **Streamlit layout**: Single `app.py`, views as `st.tabs()` — not a native multipage app. Simpler shared session state.
- **Settings tab (new, 7th tab)**: Not listed in PRD Section 7.2, but required to resolve a contradiction — 7.1 promises "the instructor never needs a terminal or text editor," and FAQ 8.3 references a "settings panel," yet no such view existed. Added, scoped to **provider/model/API key only** (reuses the first-run setup form). Other `config.json` values (cost rates, archive toggle, output formats) remain plain-JSON edits per the README's existing pattern.
- **Model picker**: Dropdown populated from the keys under `config.json`'s `cost_rates` for the selected provider (OpenAI/Anthropic) — guarantees every selectable model has a matching cost rate. Ollama's model field stays free-text since it's whatever the instructor pulled on their VM.
- **Tab gating**: Rollover/Generate/Export/Metrics tabs stay visible in a fresh project but show a redirect message ("Upload and extract a syllabus first") until `course.json` exists, rather than being hidden entirely. Settings is always accessible regardless of project state.
- **No-source-materials nudge**: Generate tab shows a soft, non-blocking one-line hint when zero source materials are indexed ("generation will use course topics/objectives only") — never blocks generation, since source materials are explicitly optional (Section 6.5).
- **Word schedule-table detection (F-01)**: Auto-detect by the "Week N" heuristic; if zero or multiple tables match, show a manual-override UI listing candidate tables (first-row preview) instead of failing outright.
- **Cost estimate before generation**: Rough heuristic only — input tokens from prompt length (chars/4), output assumed at that generation type's configured `max_tokens` ceiling, shown as "up to ~$X." No reliance on `eval-log.json` history.
- **Multi-project UX**: One running Streamlit instance operates on one project folder (passed via CLI arg or a lightweight folder picker on launch). No in-app project switcher for MVP — matches CLI parity.
- **Archive retention**: Unbounded for MVP — every timestamped archive is kept, no pruning.
- **Consistency-check overrides**: When the instructor clicks "Continue anyway" past the term-mismatch warning, that override is logged as its own explicit event in `eval-log.json` (in addition to the existing pass/fail entry) — this is the flagship named test case (Section 6.1) and the December evidence artifact benefits from direct proof the check fired and was knowingly bypassed.
- **Prompt template safety (F-05)**: On load, validate that a template's required `{variable}` placeholders are present; if malformed, show a plain-English error naming the missing variable and the file path. No auto-repair/reset-to-default for MVP.

## Process / ops

- **Faculty setup**: README + pip/venv instructions only, as originally written in Section 8 — no launcher script or packaged executable for MVP.
- **Git**: Repository initialized at scaffolding time (this session), before any application code is written.
- **Build status at time of this log**: Empty — nothing built yet.

## Decisions made during the build (Milestones 4-5)

- **Duration mismatch is a preview flag, not a hard stop** (PRD 7.3 vs 6.2). 6.2 says the way to lengthen or shorten a course is to edit `duration_weeks` before rollover; 7.3's "Duration mismatch" error would block exactly that. Since the extractor always sets `duration_weeks` to the schedule's week count, a mismatch only happens when the instructor changed it deliberately — so rollover proceeds and the Rollover Preview leads with a flag naming both numbers and the resulting week count. Nothing is written until Confirm either way.
- **CLI commands beyond PRD 6.6's four**: `extract`, `rollover`, and `export` were added alongside `init`/`add`/`generate`/`status` so Track A is usable end to end without the UI. `generate` exits with a plain "not available in this build yet" message until Milestone 7.
- **Consistency-check override on the CLI** requires either an interactive "y" or an explicit `--continue-anyway` flag (never implied by a general `--yes`), and is logged as `consistency_check_override` either way.
- **CLI logic lives in `chalk/cli.py`**; `toolkit.py` is a thin shim, so the CLI sits inside the coverage gate.
- **Workflow layer (`chalk/pipeline.py`)**: extract / save-after-review / rollover preview+confirm / export are single functions both the CLI and the Streamlit UI call, so both front ends log identical metrics events and write identical files.
- **course.json archives** go to `<project>/.archive/` (sibling of course.json); outputs archive to `outputs/.archive/` per PRD 5.1.
- **Extraction copies the syllabus into `source/` only after it parses successfully**, and records `course.source_file` as a project-relative path so the project folder can be moved or shared.

## Open items deliberately deferred (not gaps, just lower-priority / resolve-when-relevant)

- `course.json` schema versioning/migration across terms and repo forks.
- Exact FAQ/error-copy wording beyond what Section 7.3/8.3 already specifies.
- Best Practices Guide and Catalog of Tools content (Section 12) — separate non-build deliverables, different owner.
- Slide content generation (F-05e) — stretch scope, timing TBD.
