# Chalk — Implementation Plan

Read in full: `capstone-prd-v3.1.md` (v0.3.1) and `DECISIONS.md`. DECISIONS.md is authoritative on conflicts (pydantic models, JSONL eval log, synthetic docx/md fixtures, single `app.py` with `st.tabs()`, 7th Settings tab, branding constant, etc.). Repo root is `C:\Users\athav\OneDrive\Documents\Capstone`, currently holding only the two source docs + `.gitignore` (already staged, no commits yet). `.gitignore` already excludes `/projects/` and `/sandbox/` — good landing spot for real test-corpus syllabi and manually-created course projects, keeping them out of git history alongside the existing `.env` exclusion.

---

## 0. Research & Reuse (brief pass)

- **python-docx table editing**: Stick with python-docx per PRD 4 (the only library that edits tables in place without disturbing formatting; alternatives like `docx2python` are read-only extraction tools, not viable for F-02's in-place rewrite). Important known issue to design around: **python-openxml/python-docx#290** — replacing a cell's text by clearing the paragraph and adding a new run drops existing run formatting (bold, font, size). Implementation must locate the existing run in the week-label cell and mutate `run.text` directly, never `cell.text = "..."` or paragraph-clear-and-rebuild, to satisfy PRD 6.2's "all other cell content preserved."
- **pydantic structured schema**: No single reusable "course schema" repo, but the pattern is standard (Instructor / PydanticAI style): nested `BaseModel` classes matching the JSON shape 1:1, `field_validator`/`model_validator` for cross-field rules (e.g. term-label vs date), `.model_dump_json(indent=2)` / `.model_validate_json()` for round-tripping to `course.json`. Confirms DECISIONS' choice over raw dict + jsonschema.
- **Streamlit wizard/session-state**: Confirmed pattern from `streamlit-wizard-form` and Streamlit's own session-state docs — centralize state under dedicated accessor functions (not scattered `st.session_state["key"]` string literals) and drive tab-gating off state, not `st.tabs()` navigation events (Streamlit's tabs don't have programmatic on-select callbacks). Matches DECISIONS' tab-gating requirement.
- **Provider-agnostic LLM clients**: Multiple prior-art examples (AbstractCore, llm_api_adapter, llmwrapper) validate the PRD's own `llm_client.py` sketch (§4.1) as a reasonable, right-sized abstraction — a single module with an `if provider == "anthropic"` branch is preferable here to pulling in a heavyweight router like LiteLLM, consistent with "local-first, minimal footprint."
- **Streamlit testing**: `streamlit.testing.v1.AppTest` (introduced Streamlit 1.28, present in all current releases) is the way to get real coverage on `app.py` without a browser — needed for the 80% coverage target to mean anything for Track C.

---

## 1. Repo / File Structure

```
Capstone/                          (repo root)
├── app.py                         # Streamlit entry point (single file; views via st.tabs())
├── toolkit.py                     # CLI entry point (init/add/generate/status)
├── requirements.txt
├── requirements-dev.txt           # pytest, pytest-cov, freezegun, ruff (optional)
├── .env.example                   # documents LLM_PROVIDER/LLM_API_KEY/LLM_BASE_URL/LLM_MODEL
├── pytest.ini                     # or [tool.pytest.ini_options] in pyproject.toml
├── pyproject.toml                 # coverage config: --cov=chalk --cov-fail-under=80
├── README.md                      # Section 8 deliverable
├── LICENSE
├── .gitignore                     # already present
├── DECISIONS.md / capstone-prd-v3.1.md  (already present)
│
├── chalk/                         # importable package — all business logic (no UI/CLI logic here)
│   ├── __init__.py
│   ├── branding.py                # PROJECT_NAME = "Chalk" — single source of truth (DECISIONS)
│   ├── errors.py                  # ChalkError base; LLMProviderError; ExtractionError; AmbiguousTableError; ProtectedFileError
│   ├── models.py                  # pydantic: CourseInfo, Assessment, Week, UniversityDate, SourceMaterialRef, CourseData
│   ├── config.py                  # load/write config.json + .env (dotenv), first-run key validation
│   ├── calendar_data.py           # load_calendars(), find_term() — graceful degradation (§5.3)
│   ├── llm_client.py              # provider abstraction per PRD §4.1, + DECISIONS retry/backoff
│   ├── metrics.py                 # eval-log.json JSONL append/read, event-type registry, cost calc
│   ├── project.py                 # F-06: init/add/status, archive_and_write() generic helper
│   ├── canvas_export.py           # F-03
│   ├── course_brief.py            # F-04 (no API call)
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── docx_extractor.py      # F-01 Word path
│   │   ├── markdown_extractor.py  # F-01 markdown path
│   │   └── consistency.py         # term-label vs Week-1-date check (§6.1, named test case)
│   ├── rollover/
│   │   ├── __init__.py
│   │   ├── docx_rollover.py       # F-02 Word path
│   │   ├── markdown_rollover.py   # F-02 markdown path (incl. DST-boundary flag)
│   │   └── preview.py             # builds the Rollover Preview table/flags structure shared by CLI+UI
│   └── generation/
│       ├── __init__.py
│       ├── prompts.py             # loads prompts/*.txt, validates {variable} placeholders (DECISIONS)
│       ├── source_context.py      # naive concat + token-budget truncation (DECISIONS)
│       ├── quiz.py                # F-05a
│       ├── discussion.py          # F-05b
│       ├── rubric.py              # F-05c
│       ├── summary.py             # F-05d
│       └── slides.py              # F-05e (stretch)
│
├── ui/                             # Streamlit view-render helpers imported by app.py (still "one app.py" — no st multipage/pages/ dir)
│   ├── session.py                  # typed accessors over st.session_state (get_course_data, set_project_dir, ...)
│   ├── upload_view.py
│   ├── review_view.py
│   ├── rollover_view.py
│   ├── generate_view.py
│   ├── export_view.py
│   ├── metrics_view.py
│   └── settings_view.py            # 7th tab (DECISIONS)
│
├── resources/                      # canonical files shipped with the TOOLKIT repo, copied into new course projects on `init`
│   ├── config.json                 # template — matches PRD §11 shape
│   ├── data/
│   │   └── calendars.json          # U of U terms through 2029-2030 (PRD §5.3)
│   └── prompts/
│       ├── quiz.txt
│       ├── discussion.txt
│       ├── rubric.txt
│       ├── summary.txt
│       └── slides.txt
│
└── tests/
    ├── conftest.py                 # shared fixtures (see Test Strategy)
    ├── fixtures/
    │   ├── docx_builder.py         # programmatic synthetic .docx factory functions
    │   └── md_builder.py           # programmatic synthetic .md factory functions
    ├── test_models.py
    ├── test_calendar_data.py
    ├── test_llm_client.py
    ├── test_metrics.py
    ├── test_docx_extractor.py
    ├── test_markdown_extractor.py
    ├── test_consistency.py
    ├── test_docx_rollover.py
    ├── test_markdown_rollover.py
    ├── test_canvas_export.py
    ├── test_course_brief.py
    ├── test_project.py
    ├── test_prompts.py
    ├── test_generation_*.py
    ├── test_cli_toolkit.py         # integration tests against a tmp_path project dir
    └── test_app_smoke.py           # streamlit.testing.v1.AppTest smoke tests per tab
```

Course *project* directories (per PRD §5.1) are a separate runtime concept — created by `toolkit.py init` under wherever the instructor points it (e.g. `/projects/<course-name>/` locally, already gitignored). `resources/` in the toolkit repo is what `project.py`'s init routine copies from into a fresh project's `data/`, `prompts/`, and `config.json`.

---

## 2. `requirements.txt`

```
streamlit>=1.38          # UI framework, local no-server app; pin floor high enough for streamlit.testing.v1.AppTest (needs 1.28+)
openai>=1.40             # OpenAI SDK; also serves the Ollama path (OpenAI-compatible endpoint via base_url swap)
anthropic>=0.34          # Anthropic SDK — separate response shape, isolated inside llm_client.py
python-docx>=1.1         # Word (.docx) table read/write for extraction and rollover, in place
pypdf>=4.0               # Pure-Python PDF text extraction for instructor-supplied source material summaries (DECISIONS)
pydantic>=2.7            # course.json schema as typed models with validation (DECISIONS)
python-dotenv>=1.0       # loads .env (LLM_PROVIDER/LLM_API_KEY/LLM_BASE_URL/LLM_MODEL) (DECISIONS)
```

`requirements-dev.txt` (not shipped to instructors as a runtime dependency, but needed by contributors/CI):
```
pytest>=8.0              # test runner
pytest-cov>=5.0          # coverage measurement, --cov-fail-under=80 gate
freezegun>=1.5           # deterministic timestamps for extracted_at / archive filenames / eval-log entries
ruff>=0.5                # lint (optional but cheap; catches unused imports before they hit review)
```

Deliberately **not** included, with reasons tied to PRD wording:
- No markdown-parsing library (`markdown`, `mistune`) — PRD §4 explicitly calls for "stdlib + regex," no heavy dependency needed for structured tables.
- No `python-dateutil` — all rollover date math is fixed 7-day week shifts and calendar lookups; stdlib `datetime`/`timedelta` covers it, including the "first Sunday of November" DST check.
- No embeddings/vector-DB package — DECISIONS explicitly rules out embeddings for MVP source-material context.
- No `docx2python` — read-only extraction tool; doesn't support the in-place edit F-02 requires.

---

## 3. Build Order / Task List

Sequenced **Track A → Track C → Track B → Stretch**, per the PRD's MVP-priority note (which overrides the raw Track A/B/C numbering in §14 — Track B is listed with lower section numbers than Track C but must ship after it). Each numbered task is sized for a single red/green/refactor TDD cycle.

### Milestone 0 — Scaffolding
1. Create the directory skeleton above; empty `__init__.py`s; `branding.py` with `PROJECT_NAME = "Chalk"`.
2. `pyproject.toml`/`pytest.ini` with `--cov=chalk --cov-report=term-missing --cov-fail-under=80`; `tests/conftest.py` stub; verify `pytest` collects/runs green with one placeholder test.
3. `.env.example` documenting the three provider configurations from PRD §11.

### Milestone 1 — Foundations (PRD build-order steps 1–3, + metrics moved earlier)
4. `chalk/errors.py` — define `ChalkError`, `LLMProviderError`, `ExtractionError`, `AmbiguousTableError`, `ProtectedFileError`, each carrying a plain-English `.user_message` matching PRD §7.3's table verbatim where applicable.
5. `chalk/models.py` — TDD round-trip test: parse the PRD §5.2 example JSON into `CourseData`, dump back out, assert equality. Add field validators (`duration_weeks > 0`; `Week` requires `week_number` OR `is_break` with `date_start`/`date_end`).
6. `chalk/metrics.py` — JSONL append/read (`append_event(event_type, payload)`, `read_events()`); define the event-type vocabulary up front: `extraction`, `consistency_check`, `consistency_check_override`, `rollover`, `generation`, `extraction_error`, `archive`, `source_indexed` (mirrors PRD §6.7's table + DECISIONS' override event). Building this now (ahead of PRD's literal step-12 position) because the consistency check (step 6 below) needs to log both of its outcomes immediately.
7. `chalk/calendar_data.py` — `load_calendars(path)`, `find_term(calendars, term_name)`; tests for found term, not-found term (graceful degradation per §5.3), malformed file.
8. Populate `resources/data/calendars.json` with real U of U terms through 2029–2030 from registrar data; add a structural test (chronological ordering, required keys per term) rather than hand-checking each entry.
9. `chalk/llm_client.py` — implement per PRD §4.1's sketch. Tests via monkeypatched `openai.OpenAI`/`anthropic.Anthropic`: correct provider branch selection from `LLM_PROVIDER`; return-shape contract (`text`/`input_tokens`/`output_tokens`); auth-error and connection-error message mapping matching PRD §7.3 exactly.
10. Add DECISIONS' retry/backoff: 2–3 retries with short exponential backoff on transient rate-limit/timeout errors before raising `LLMProviderError`; test via a mocked side-effect sequence (fail, fail, succeed) and a fully-exhausted-retries case.
11. `chalk/config.py` — `.env` read/write via `python-dotenv`; `config.json` load; first-run test-call validation function used by both CLI first-run and Streamlit first-run setup (§6.6/§7.1).

### Milestone 2 — Extraction (PRD steps 4–6)
12. `tests/fixtures/docx_builder.py` — programmatic minimal syllabus builder (schedule table with "Week N (M/DD)" rows + one break row, Learning Objectives bullets, grading-weight table, university-dates table) per DECISIONS' synthetic-fixture approach.
13. `chalk/extractors/docx_extractor.py` — schedule-table auto-detection by "Week N" heuristic; happy-path test producing a `CourseData` matching the fixture.
14. Zero/multiple-candidate-table case → raise `AmbiguousTableError` carrying candidate table previews (feeds the DECISIONS manual-override UI later); test both branches.
15. Break-row detection (no week-number pattern); test.
16. Learning-objectives extraction under both heading variants ("Learning Objectives" / "Course Outcome and Objectives"); test both.
17. Assessments (grading-weight) table extraction; test.
18. University-dates table extraction, present and absent cases; test.
19. Password-protected `.docx` handling — catch `BadZipFile`/`PackageNotFoundError` (DECISIONS), surface `ProtectedFileError` with PRD §7.3's exact message.
20. Non-destructive guarantee test: source file's bytes/mtime unchanged after extraction (extractor never calls `.save()` on the input document).
21. `tests/fixtures/md_builder.py` — synthetic markdown builder (`| Week | Dates | ... | Major Work |` table, `| - |` break row, university-dates table).
22. `chalk/extractors/markdown_extractor.py` — regex-based table parse, `duration_weeks` detection, break rows, optional university-dates table; one test per rule.
23. `chalk/extractors/consistency.py` — `check_term_consistency(course_data)`; test reproduces the exact Spring-2026/August-Week-1 named test case from PRD §3/§6.1.
24. Wire consistency check into both extractors (always runs post-extraction); log both `consistency_check` (pass/fail) and, when the UI/CLI records an override, `consistency_check_override` events.

### Milestone 3 — Rollover (PRD steps 7–8)
25. `chalk/rollover/preview.py` — shared data structure for the Rollover Preview table (per-week old/new date, generic `flags: list[str]` per week — used by both the Fall-Break-timing flag and the DST-boundary flag so there is one flagging mechanism, not two ad hoc ones).
26. `chalk/rollover/docx_rollover.py` — anchor Week 1 to target term start, shift subsequent weeks by 7 days, respect `duration_weeks` exactly; test against a 10-week and a 16-week fixture.
27. Implement in-place cell text mutation for the Word week-label date (mutate existing `run.text`, not clear-and-rebuild) to avoid the python-docx#290 formatting-loss trap; test that a bolded/colored run keeps its formatting after rollover.
28. Insert/skip break rows using `calendar_data.find_term()`'s no-class-date ranges; test.
29. Duration-expansion path (DECISIONS): when target `duration_weeks` exceeds originally-extracted weeks, call `llm_client` for placeholder topics, clearly labeled as an AI draft; test the happy path (mocked LLM) and the graceful-degradation path (LLM unavailable → insert empty placeholder weeks labeled "no LLM available," rollover still completes — this is the one rollover sub-case that touches the network, so it must degrade rather than fail the whole rollover per NFR §10).
30. `chalk/rollover/markdown_rollover.py` — same date-shift logic for markdown tables; DST-boundary flag (`first Sunday of November` check) as a pure function, tested independently of any LLM call; never auto-applies a timezone suffix (§6.2).
31. Do-not-renumber guarantee: quizzes/exams/labs mentioned in assignments/notes are left untouched and flagged for human review, not renumbered; test.
32. Rollover Preview → Confirm flow: writes `outputs/syllabus.{docx,md}`, `outputs/canvas.html`, `outputs/course-brief.md` only after confirmation; archive-before-write via the generic helper from task 34.

### Milestone 4 — Derived, zero/low-cost outputs (PRD steps 9–10)
33. `chalk/canvas_export.py` — F-03; semantic HTML table, header comment sourced from `branding.PROJECT_NAME` (not a hardcoded literal); test HTML structure and the comment text.
34. `chalk/course_brief.py` — F-04; no API call; test output contains title/term/duration/objectives/assessment weights/condensed week list; test it's regenerated automatically after both extraction and rollover.

### Milestone 5 — Project persistence & CLI (PRD step 11, completes Track A)
35. `chalk/project.py` — `archive_and_write(path, content)` generic helper (archives existing file to `.archive/[name]-[timestamp]` before overwrite); used uniformly for `outputs/*` **and** top-level `course.json` (DECISIONS extends F-06 to cover course.json re-saves, not just outputs/).
36. `project.init(name, source_format)` — creates the full §5.1 directory layout, copies `resources/config.json`, `resources/data/calendars.json`, `resources/prompts/*.txt` into the new project.
37. `project.add(path)` — indexes a source file into `source/`, logs a `source_indexed` metrics event; validates accepted types (pdf/docx/md/txt).
38. `project.status()` — summarizes project state (course loaded? counts of outputs, source files, total cost from `eval-log.json`).
39. `toolkit.py` — CLI wiring for `init`/`add`/`generate`/`status` (generate can stub through to Milestone 7's real implementation once it exists); integration tests against a `tmp_path` project directory exercising the full extract → review-save → rollover → export loop without a UI.

**End of Milestone 5 = Track A complete: a working, shareable CLI pipeline.**

### Milestone 6 — Track C: Streamlit UI (PRD steps 18–23)
40. `ui/session.py` — typed accessors (`get_course_data()`, `set_project_dir()`, `is_project_loaded()`, etc.) wrapping `st.session_state`, avoiding scattered string keys.
41. `app.py` skeleton — single-file `st.tabs()` layout (Upload, Review, Rollover, Generate, Export, Metrics, **Settings** — 7th tab per DECISIONS); project-directory resolution at startup (CLI arg or folder picker, no in-app project switcher per DECISIONS' single-instance/single-project MVP scope).
42. First-run setup flow (§7.1/§6.6): missing/invalid `.env` → provider radio (OpenAI/Anthropic/Ollama) → key or URL + model → test-call validation via `chalk.config` → write `.env`. Test via `AppTest`.
43. `ui/upload_view.py` + `ui/review_view.py` — file uploader, "Extract course" calling `extractors.*`, inline consistency-check warning with Continue-anyway/Cancel (logs the override event per DECISIONS), editable `duration_weeks`, "Confirm and save" → `archive_and_write` + course-brief regeneration.
44. `ui/rollover_view.py` — term dropdown from `calendars.json` (or manual Week‑1 date), editable duration, Preview table (from `rollover/preview.py`) showing flags, Confirm → writes files + download buttons.
45. `ui/generate_view.py` — **shell only** at this milestone: content-type selector, week/source-material pickers, cost estimate UI, wired to `chalk.generation` behind a "coming soon" placeholder response until Milestone 7 lands the real generators (see Risk #2 below for why this is deliberately split).
46. `ui/export_view.py` — list `outputs/` with per-file download buttons, "Copy Canvas HTML," "Download all as zip."
47. `ui/metrics_view.py` — generation-count bar chart, total cost, rollover history, extraction errors, active provider — all read from `eval-log.json` via `chalk.metrics`.
48. `ui/settings_view.py` — reuses the first-run form; provider/model/API key only; model dropdown sourced from `config.json`'s `cost_rates` keys for OpenAI/Anthropic, free-text for Ollama (DECISIONS).
49. Tab-gating: Rollover/Generate/Export/Metrics show a redirect message until `course.json` exists; Settings always accessible (DECISIONS).
50. Error-message audit pass: every callout in the UI matches PRD §7.3's table verbatim; no tracebacks reach the screen (wrap all module calls in `try/except` on `ChalkError` subtypes).
51. `tests/test_app_smoke.py` — `AppTest`-based smoke test per tab (renders without exception, happy-path interaction).

**End of Milestone 6 = Track A + Track C at a working, shareable state — the MVP priority target.**

### Milestone 7 — Track B: Generation (PRD steps 13–17)
52. `chalk/generation/prompts.py` — load `prompts/*.txt`; define a required-variable registry per content type; validate on load, raise a plain-English error naming the missing variable and file path (DECISIONS — no auto-repair).
53. `chalk/generation/source_context.py` — naive full-text concatenation of selected `source/` files with a token-budget truncation rule (DECISIONS, no embeddings).
54. `chalk/generation/quiz.py` (F-05a) — test with mocked `llm_client.complete`; verify output includes the required "AI-generated draft" banner (§6.5) and a Questions/Answer-Key structure; saved to `outputs/quizzes/week-N-quiz.md` via `archive_and_write`.
55. `chalk/generation/discussion.py` (F-05b) — recall/application/analysis-labeled prompts; same banner/save conventions.
56. `chalk/generation/rubric.py` (F-05c) — markdown table rubric; explicitly test that no grade/score is assigned, only criteria/levels/points (CTE line).
57. `chalk/generation/summary.py` (F-05d) — student-facing summary grounded in week topics + source context.
58. Cost estimation (DECISIONS heuristic: input tokens from prompt length/4, output = configured `max_tokens` ceiling) wired into `ui/generate_view.py`'s "up to ~$X" display, replacing the Milestone-6 placeholder.
59. Wire `toolkit.py generate <type> --week N` to the real generators; overwrite-confirmation message and archive event per PRD §7.3's "already exists for Week N" table row.
60. `chalk/metrics.py` completion — token usage, per-call cost, running project total, all appended to `eval-log.json` after every real generation call (F-07 completion).
61. Replace Milestone-6's Generate-tab placeholder with real calls end-to-end; re-run `AppTest` smoke tests.

### Milestone 8 — Stretch
62. `chalk/generation/slides.py` (F-05e) — YAML title block, `##` slide headings with `<!-- Slide N -->` comments, two-column div syntax, no bare `#`; validate against Matt's `convert-slides-to-pptx.sh` input conventions.

### Milestone 9 — Hardening & Handoff
63. README.md (PRD §8's 12-section structure) — first-class deliverable; all three provider configs, calendar-update instructions, forking guide.
64. FAQ content (§8.3) mapped 1:1 to every UI error message.
65. Run the five-syllabus test corpus (PRD §15) — real files live under gitignored `/sandbox/` or `/projects/`, never committed; produce the December evidence artifact from `eval-log.json`.
66. Coverage audit to the 80% gate; close gaps, especially in `ui/*` via `AppTest`.
67. Packaging polish: `.env.example` completeness check, `requirements.txt` version pin freeze (`pip freeze` after a clean install), LICENSE, final branding-constant sweep (grep for any hardcoded "Chalk" string outside `branding.py`).

---

## 4. Key Architectural Risks / Decisions to Flag

1. **python-docx run-formatting loss on cell rewrite** (PRD §6.2, GitHub python-docx#290). Rollover must mutate the existing run's `.text`, never clear-and-rebuild the paragraph, or the "all other cell content preserved" requirement silently breaks on any styled date text.
2. **Generate-tab UI vs. Generate-function ordering mismatch**. PRD §14 numbers Track C's "Generate view" (step 21) before Track B's generation functions (steps 13–17), but the MVP-priority note demands Track A+C ship before Track B. Resolved above by building the Generate tab as a wired-but-placeholder shell in Milestone 6 and swapping in real calls in Milestone 7 — call this out explicitly so it isn't read as a contradiction mid-build.
3. **Duration-expansion breaks the offline NFR for one rollover sub-case** (DECISIONS vs. PRD §10 "extraction and rollover work with no internet"). Only the duration-*increase* path touches `llm_client`; it must degrade gracefully (placeholder weeks, explicit "no LLM available" label) rather than fail rollover outright when offline.
4. **Ambiguous schedule-table detection changes the extractor's return contract from day one** (DECISIONS' manual-override UI for zero/multiple table matches). Design `AmbiguousTableError` (carrying candidate table previews) into the extractor API in Milestone 2, not as a later retrofit — the UI needs that data shape to render the override picker.
5. **course.json archiving scope** (DECISIONS extends F-06 beyond `outputs/`). Build one generic `archive_and_write()` helper used for both `course.json` re-saves and `outputs/*` writes — two divergent archive code paths would be an easy accidental drift.
6. **eval-log.json event-type vocabulary must be designed up front**, not evolved feature-by-feature — the override-logging decision (DECISIONS) and the December evidence-artifact requirement (§6.7 "For December") both depend on a stable, filterable `event_type` field across `consistency_check`, `consistency_check_override`, `rollover`, `generation`, etc.
7. **Rollover Preview flags need one generic mechanism**, not two — the Fall-Break-timing flag (§6.2's worked example) and the markdown DST-boundary flag (§6.2) should populate the same per-week `flags: list[str]`, not separate ad hoc UI branches.
8. **Streamlit rerun model demands stateless business logic**. Since "the UI calls the same functions the CLI does" (§7) and Streamlit reruns the whole script per interaction, every `chalk/*` function must be pure (explicit args in, values out) — `ui/session.py` exists specifically to prevent session-state key drift from leaking business-logic assumptions into `app.py`.
9. **Branding constant discipline** (DECISIONS). The Canvas HTML header comment, Streamlit page title, and README heading must all import `branding.PROJECT_NAME` — flag `canvas_export.py` specifically, since a hardcoded `<!-- Generated by Chalk -->` string is the easiest place for this to regress.
10. **Provider-dependent model-picker branching** (DECISIONS: Ollama stays free-text). Cost-calculation code must key off a fixed `local.default` rate for the Ollama branch rather than trying to match a free-text model name against `config.json`'s `cost_rates` table — don't let this collapse into a single "look up by model name" code path that silently returns None/0 costs for local models with a typo'd name.

---

## 5. Test Strategy

**Fixtures (`tests/conftest.py`)**
- `sample_course_data` — a `CourseData` instance matching PRD §5.2's example JSON, reused across extractor/rollover/generation tests as the canonical known-good object.
- `tmp_project_dir` — `tmp_path`-based fixture scaffolding the full §5.1 project layout, used by `project.py`, CLI, and archive tests.
- `synthetic_docx_factory` / `synthetic_md_factory` (`tests/fixtures/docx_builder.py`, `md_builder.py`) — programmatic minimal-document builders, **one factory function per parsing rule** (schedule table, break row, learning-objectives heading variant ×2, assessments table, university-dates table, password-protected/corrupt file, DST-boundary date), per DECISIONS' explicit choice over trimmed real syllabi.
- `mock_llm_client` — monkeypatches `chalk.llm_client.complete` to return canned `{"text", "input_tokens", "output_tokens"}` dicts, so generation and rollover-duration-expansion tests never hit a real API in CI.
- `frozen_time` (freezegun) — deterministic `extracted_at` timestamps and `.archive/[name]-[timestamp]` filenames.

**Coverage**: `pytest-cov` configured via `pyproject.toml`/`pytest.ini` with `--cov=chalk --cov-report=term-missing --cov-fail-under=80`, matching the user's 80% global target. `ui/*` and `app.py` are included in the same coverage run via `streamlit.testing.v1.AppTest` smoke tests (Milestone 6, task 51) rather than excluded — otherwise the 80% figure would be meaningless for half the MVP scope (Track C).

**Fixture-to-task mapping**: each Milestone-2 extractor task (13–22) pairs 1:1 with a dedicated synthetic-fixture factory function and a single-rule unit test — this is the direct implementation of DECISIONS' "minimal synthetic documents... one fixture per parsing rule." The five real test-corpus syllabi (PRD §15) are treated as a separate, later acceptance tier (Milestone 9, task 65) run against the finished pipeline ahead of the November 8 readiness meeting — they live in the already-gitignored `/sandbox/` or `/projects/` folders, not `tests/fixtures/`, since they're real (if non-student) faculty content that shouldn't enter git history.

**Test tiers**:
1. **Unit** — `models.py`, `calendar_data.py`, `consistency.py`, DST-flag function, cost-calculation, metrics event shape. Pure functions, no I/O beyond tmp files.
2. **Component** — extractors and rollover against synthetic fixtures; generation modules against `mock_llm_client`.
3. **Integration** — `toolkit.py` CLI commands end-to-end against `tmp_project_dir`; `AppTest` smoke tests per Streamlit tab.
4. **Acceptance** — the five-syllabus test corpus, run manually/scripted, not gated by the 80% coverage threshold (external, real-world inputs), feeding the December evidence artifact.

---

### Critical Files for Implementation
- C:\Users\athav\OneDrive\Documents\Capstone\chalk\models.py
- C:\Users\athav\OneDrive\Documents\Capstone\chalk\llm_client.py
- C:\Users\athav\OneDrive\Documents\Capstone\chalk\extractors\docx_extractor.py
- C:\Users\athav\OneDrive\Documents\Capstone\chalk\rollover\docx_rollover.py
- C:\Users\athav\OneDrive\Documents\Capstone\app.py
- C:\Users\athav\OneDrive\Documents\Capstone\toolkit.py
- C:\Users\athav\OneDrive\Documents\Capstone\tests\fixtures\docx_builder.py
