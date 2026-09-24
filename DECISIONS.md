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
- **Build status**: see the Status section at the top of PLAN.md.

## Decisions made during the build (Milestones 4-5)

- **Duration mismatch is a preview flag, not a hard stop** (PRD 7.3 vs 6.2). 6.2 says the way to lengthen or shorten a course is to edit `duration_weeks` before rollover; 7.3's "Duration mismatch" error would block exactly that. Since the extractor always sets `duration_weeks` to the schedule's week count, a mismatch only happens when the instructor changed it deliberately — so rollover proceeds and the Rollover Preview leads with a flag naming both numbers and the resulting week count. Nothing is written until Confirm either way.
- **CLI commands beyond PRD 6.6's four**: `extract`, `rollover`, and `export` were added alongside `init`/`add`/`generate`/`status` so Track A is usable end to end without the UI. `generate` exits with a plain "not available in this build yet" message until Milestone 7.
- **Consistency-check override on the CLI** requires either an interactive "y" or an explicit `--continue-anyway` flag (never implied by a general `--yes`), and is logged as `consistency_check_override` either way.
- **CLI logic lives in `chalk/cli.py`**; `toolkit.py` is a thin shim, so the CLI sits inside the coverage gate.
- **Workflow layer (`chalk/pipeline.py`)**: extract / save-after-review / rollover preview+confirm / export are single functions both the CLI and the Streamlit UI call, so both front ends log identical metrics events and write identical files.
- **course.json archives** go to `<project>/.archive/` (sibling of course.json); outputs archive to `outputs/.archive/` per PRD 5.1.
- **Extraction copies the syllabus into `source/` only after it parses successfully**, and records `course.source_file` as a project-relative path so the project folder can be moved or shared.

## Decisions made during the build (Milestone 6 — Streamlit UI)

- **Project chosen at launch, not on the Upload tab.** PRD 7.2 puts a "project name field (pre-filled from filename)" on Upload, but DECISIONS' one-instance-one-project rule means the project already exists by then. The launch screen opens or creates a project (`streamlit run app.py -- --project <folder>` skips it); Upload just uploads.
- **First-run setup can be skipped.** Extraction, rollover, and export work offline (PRD 10), so an instructor can start without a provider and connect one later in Settings. The footer then reads "Provider: Not configured".
- **Settings keeps the saved API key when the key field is left blank**, so switching model doesn't mean re-pasting the key. Every save still re-validates with a test call.
- **LLM error messages now match PRD 7.3 exactly**, per provider (OpenAI / Anthropic / local endpoint with its URL).
- **"Copy Canvas HTML"** is Streamlit's built-in copy button on a code block — Streamlit has no clipboard API.
- **A rollover preview is tied to the inputs that produced it**: changing term, date, or duration hides the old preview, so a stale preview can never be confirmed.
- **Unexpected errors are contained per tab**: a plain notice on screen, the traceback to the terminal, the other tabs unaffected.
- **Manual Week 1 dates accept 2000–2100**, overriding Streamlit's default ±10-year date range.

## Decisions made during the build (Milestones 7-8 — generation)

- **One generation engine, content types as data.** Instead of five near-identical modules (PLAN's quiz.py/discussion.py/…), `chalk/generation/specs.py` describes each type (template, required variables, output folder, max_tokens) and `engine.py` runs them all. Adding a type is a spec plus a template.
- **Generate returns a draft; Save writes it.** Matches PRD 7.2's "output shown inline for review before saving". Every successful LLM call is logged, whether or not the draft is saved (PRD 6.7 counts calls). The CLI saves immediately, after the overwrite confirmation.
- **Template filling replaces only known `{variable}` names**, so other braces (including Pandoc's `{.columns}` in the slides template) never break a template. Validation is still strict about required variables (DECISIONS: name the variable and file, no auto-repair).
- **A project with no copy of a template uses the bundled default** (e.g. projects created before generation existed). An instructor-edited template is never replaced.
- **Unknown cost is recorded as unknown, not $0**: a hosted model with no `cost_rates` entry logs `cost_usd: null` and the UI/CLI say so. Local/Ollama endpoints always use `cost_rates.local.default` (PLAN Risk #10).
- **Single week per request** for quizzes/discussions/summaries/slides ("week number(s)" in PRD 6.5) — multi-week requests deferred.
- **Slides banner**: the PRD's "every generated file opens with the AI-draft banner" conflicts with F-05e's "YAML title block at top", so slide decks carry the banner as an HTML comment directly after the YAML block. Slide output is post-processed to enforce the pipeline conventions (no `subtitle:`, no bare `#`, `<!-- Slide N -->` numbering) regardless of what the model returns.
- **Rubric descriptions** can be typed or uploaded (PDF/DOCX/MD/TXT), read with the same text extraction as source materials. The prompt and system message both forbid grading student work (CTE policy).
- **Source context**: 6,000-token budget (~24k characters), truncated with an explicit "[truncated]" note; source files are selected by name from `source/` only, never as arbitrary paths.

## Decisions made during the build (Milestone 9 — hardening & handoff)

- **FERPA statement (PRD 10)** appears wherever files are uploaded (Upload tab, Generate tab's source uploader, CLI `add`), and every prompt template tells the model the materials contain no student records and not to request or invent student information.
- **Evaluation report** (`toolkit.py report`, and a download on the Metrics tab) is the December evidence artifact: files processed and error rate by format, consistency catches and overrides, rollovers, and cost per content type — computed only from eval-log.json metadata.
- **Source materials can be added in the app** (Generate tab → Add source materials), not only via CLI `add`, so the no-terminal promise (PRD 7.1) holds for generation too.
- **Dependency pins**: each direct dependency is pinned from the tested version up to (not including) its next major version, rather than a full `pip freeze`. A full freeze would pin platform-specific transitive packages and break installs on the other OS.

## Open items deliberately deferred (not gaps, just lower-priority / resolve-when-relevant)

- `course.json` schema versioning/migration across terms and repo forks.
- Exact FAQ/error-copy wording beyond what Section 7.3/8.3 already specifies.
- Best Practices Guide and Catalog of Tools content (Section 12) — separate non-build deliverables, different owner.
- Slide content generation (F-05e) — stretch scope, timing TBD.
