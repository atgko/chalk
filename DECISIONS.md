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

- **PDF parsing**: `pypdf` (pure-Python, no system deps — sufficient for instructor-authored summaries/excerpts). PDF *syllabi* use `pdfplumber` instead, which gives text positions and ruled tables (see below).
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

## Decisions made after the build (easier to run, sponsor demo)

- **Double-click launchers replace README-only setup** (reverses the earlier "no launcher script for MVP" decision). `Start Chalk.bat` / `Start Chalk.command` create the virtual environment; `chalk/launcher.py` does the rest (Python version check, installs requirements on first run and whenever requirements.txt changes, free port, opens the browser), so the logic is cross-platform and tested. `Start Chalk Demo` opens the demo course.
- **Streamlit runs headless under the launcher**, which opens the browser itself once the server answers its health check. A normal first `streamlit run` stops at an "Email:" prompt, which would make a double-clicked launcher look frozen.
- **Streamlit usage statistics are off** (`.streamlit/config.toml`, and passed explicitly by the launcher). They're on by default, which contradicted the local-first/no-telemetry promise.
- **Not hosted.** Hosting was considered and rejected for now: projects, archives, and `.env` keys live on the server's disk, and PRD 9 rules out multi-user hosting. A session-only demo mode for Streamlit Cloud remains possible later.
- **Demo course** (`chalk/demo.py`, the launch-screen buttons, `toolkit.py demo`): synthetic sample syllabi shaped like the PRD's own examples (the IS 6640 rollover worked example, the Spring-2026 term-label bug, IS 4490 markdown with the DST flag). Reset deletes only a folder carrying the `.chalk-demo` marker, and keeps its `.env` so a provider key entered before a meeting survives the reset.

## Decisions made after teammate testing with a real syllabus (Sept 30, 2026)

- **Season-change rollovers rebuild break rows from the target calendar.** Fall → Spring used to keep "Fall Break" (no name match in Spring's calendar, so it was shifted by offset). Now, when the source and target seasons differ and the target term is in the calendar, every multi-day target break overlapping the course's new dates becomes a break row and the old rows are dropped (the preview flags what changed). Same-season rollovers are unchanged. A syllabus with no break rows gets none added. University-dates entries keep their order and count (a stale break is renamed to the next unused target break; anything unmatched is flagged), so both writers pair rows by position. The Word writer reuses existing break rows, copies one for extra breaks, removes surplus, and places each before the first week that starts after it.
- **Front matter is loose; only the term is required.** A real syllabus (IS 6640) labeled only "Professor:", with the term in the title line and the course number on the next line. Extraction now accepts common label variants, reads two-column tables, and guesses title/number/term from the first 15 non-table lines. Section, credits, instructor, and meeting pattern are optional (blank / null in `course.json`) and editable on the Review tab. Rollover rewrites the term wherever it was found, changing only the season and year.
- **The Word schedule reader handles real layouts (second real syllabus, a 16-week OSC 6660 PDF).** Week labels may use month names ("Week 1 (Jan. 6)") and carry text after the date; rollover rewrites only the label's span, in its original style. Several schedule-like tables whose week numbers continue are one schedule (one table per module); duplicates are still ambiguous. Rows are classified once (`chalk.extractors._docx_schedule.classify_row`: week / dated break / other), shared by extractor and writer, so header and module-title rows are never mistaken for break rows; an undated row that names a break is still an error. A column headed "Assignment Due" is all assignments. A numbered week whose content is a break ("Week 10 — Spring Break") is flagged at rollover, not restructured.
- **Objectives and grading weights read loosely.** Objectives skip a lead-in line ending in ":" and stop at a Heading style or an all-caps line (≤60 chars). A grading table is any table with a weight/% header column, or a headerless table whose second cells are mostly percentages; "Total" rows are skipped.
- **Other tabs warn about an unsaved extraction.** Rollover/Generate/Export always use the saved `course.json`; with a newly extracted syllabus pending, they now say so. This is the likely cause of the "16-week syllabus showed 10 weeks" report (the 10-week demo course was still saved).
- **The demo ships a real-world-layout sample** (`try-these/OSC-6660-Spring-2026-real-world-layout.docx`, synthetic content), built by `chalk.demo_content.build_osc6660_module_syllabus` and reused by the tests.
- **Real syllabi live in the git-ignored `reference/` folder.** They contain instructor contact details (and the repo is public); tests use synthetic look-alikes. Open problems are tracked in BACKLOG.md.

## PDF syllabi (Oct 1, 2026)

- **A PDF is converted to Word, not parsed into `course.json` directly.** Chalk can't edit a PDF, so rollover has to write a new file anyway. Converting once, at upload, to `source/<name> (from PDF).docx` means extraction, review, rollover, and export all reuse the Word path unchanged, and rollover produces an editable `.docx`. Faculty can download the converted file. The original PDF isn't copied into `source/`, so it doesn't show up as a source material.
- **Two readers, the instructor's choice** (upload screen, or `extract --read-pdf-with local|ai`). *Local* (default): `pdfplumber` (MIT), offline, free, deterministic. *AI*: the configured LLM turns the local reader's text into a fixed JSON schema (validated with Pydantic) that's written as a Word file in the layout the Word reader expects. It's for layouts the local reader can't follow, costs money, sends the text to the provider, and isn't deterministic; Review catches its mistakes. Its prompt lives in code, not `resources/prompts/`, because it's a contract with the parser rather than a writing style. A PDF→Word converter library was considered and not adopted (quality varies by layout; licensing needs checking).
- **The local reader keeps only real tables.** pdfplumber reports every ruled box as a table; only schedules (a `Week N (date)` row) and grids with mostly filled rows stay tables, the rest is read as text. Schedule pieces split across pages are stitched together: repeated headers dropped, a row cut at a page break merged into the week above, one table per module when titles sit between them. Running headers and footers ("Page N", or a line repeated in the page margins) are dropped.
- **Wrapped lines are rejoined by position.** A line that ended with room for the next line's first word (measured from its characters) ended on purpose; bullets, gaps, and sentence-ending punctuation also break; a lowercase start always continues. Characters are assigned to the table cell their center falls in, or the nearest cell on their line, because pdfplumber's cell borders are sometimes narrower than the text.
- **An AI read is logged as a `generation` event** (`content_type: pdf_syllabus_reading`; tokens and cost, never content), so it counts toward the project's AI cost and the evaluation report. Extraction events for PDFs carry `pdf_method`, and the report counts them as format "pdf".

## Sponsor feedback (Oct 5, 2026)

- **Rollover asks which days the class meets.** Classes move days between terms, so this is a rollover input, not a saved course field. It defaults to the days in the syllabus's meeting pattern ("MW 10:45", "TTh", "Tuesdays and Thursdays"; `chalk.rollover.meeting_days`). With days chosen, a holiday or break is flagged only when it lands on a class day (a Tue/Thu class isn't warned about Labor Day, and a Thursday class is now warned about Thanksgiving, which the week's-start-date check missed). With none chosen, the old check against each week's start date still applies. Picking days that differ from the syllabus adds a reminder to update the meeting-pattern line, which rollover never rewrites.
- **Each multi-day break in the target term has an on/off toggle** (default on). Some graduate programs meet through Fall or Spring Break. A break that's switched off is removed from the schedule rows (or never added on a season change) and never flagged. Single-day holidays are still flagged, and the University Dates table still lists the break because it's the university's calendar, not the class's. CLI: `--meeting-days TR`, `--no-break "Fall Break"`.

## Providers (Oct 7, 2026)

- **Google Gemini is a fourth provider, through Google's OpenAI-compatible endpoint** (`LLM_PROVIDER=gemini`). It reuses the OpenAI SDK path in `chalk/llm_client.py` with Google's base URL, so no new dependency. Gemini 3 models always "think", and thinking tokens count against `max_tokens`, so Chalk sends `reasoning_effort="low"` for Gemini only. The dropdown offers `gemini-3.5-flash-lite` and `gemini-3.5-flash`; Google limits the 2.5 models to accounts that already used them.
- **Gemini is not sanctioned by the University of Utah.** It's labeled as not approved for student data in the provider form and README, and the privacy guardrails planned for any student-data feature (BACKLOG.md) treat it like every other unapproved provider.
- **Older projects get new providers' cost rates automatically.** `load_config` fills in any `cost_rates` provider section a project's `config.json` lacks from the bundled defaults; sections the project has are never changed.
- **Provider errors are explicit, temporarily with the provider's own text.** An OpenAI `insufficient_quota` 429 isn't retried and says to add credits; 403 and 404 name the likely causes. `_SHOW_PROVIDER_DETAILS` appends the provider's message while the team debugs setups; it's switched off before the presentation (BACKLOG.md).

## Backlog fixes (Oct 7, 2026)

- **Word rollover changes the number of week rows with the course length.** A dropped week's row is removed. An added week gets a copy of the last week row (keeping the table's formatting) with the new label, its topics, and a `Note:` line (placeholder or "AI-generated draft"), so re-extracting the document reads it back the same way. Added rows go after the last week, in the last table.
- **Dates that cross New Year get the next year.** Rows are read with the term's year, then a pass over the weeks in order adds a year from the first date that falls more than 180 days before the previous one. Using a pass after extraction keeps Word, Markdown, and PDF on the same rule.
- **Grading weights that don't add up to 100% are a warning, not an error** (Review and the CLI's extract summary), with 0.5% tolerance for rounding. No assessments at all isn't flagged, since Review already says none were found.
- **Discard on Review** drops an unsaved extraction; the saved course is never touched.

## Engineering (Oct 9, 2026)

- **Lint is enforced in CI, formatting isn't.** `ruff check .` runs on the Linux CI job. `ruff format` would rewrite about 70 files, which would conflict with every open branch for no behavior change, so it's left for a quiet moment.
- **Local dates and times are allowed** (`DTZ005`, `DTZ011` ignored; `DTZ001` in tests). Chalk runs on the instructor's own computer, so the AI-draft banner's date, the evaluation report's date, and archive timestamps are meant to be local. Code that stores a timestamp for later comparison (the metrics log) still uses UTC.

## Visual design

- **Theme**: University of Utah colors on the warm, editorial layout of the team's reference page (off-white background, cream panels, serif headings, sans-serif body), set entirely in `.streamlit/config.toml` with separate light and dark themes. No custom CSS, so Streamlit upgrades can't break it.
- **Utah Red (#BE0000) is the primary color**, per brand.utah.edu. Accent colors (Granite Peak, Red Rocks, Mountain Green, Wasatch Sunrise, Zion Cinder Cone) are used only for callouts and charts, in line with the brand's "accents under 10%" rule. Every text/background pair meets WCAG AA; dark mode uses a slightly brighter red (#D63A2F) so it passes both as a button fill and as text.
- **No University logo or wordmark.** The brand rules restrict official marks, and Chalk isn't an official University product. The header kicker reads "Syllabus & course materials toolkit", not the institution's name.
- **Streamlit's developer toolbar is hidden** (`toolbarMode = "minimal"`) so instructors and the sponsor don't see "Deploy".

## Open items deliberately deferred (not gaps, just lower-priority / resolve-when-relevant)

- `course.json` schema versioning/migration across terms and repo forks.
- Exact FAQ/error-copy wording beyond what Section 7.3/8.3 already specifies.
- Best Practices Guide and Catalog of Tools content (Section 12) — separate non-build deliverables, different owner.
- Slide content generation (F-05e) — stretch scope, timing TBD.
