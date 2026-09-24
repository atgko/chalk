# [PROJECT NAME] — Product Requirements Document

**Project:** MSIS Capstone UU1239 DESB IS
**Version:** 0.3.1 — MVP Build (multi-provider LLM)
**Date:** September 2026
**Team:** Athavan Elangko (PM), Kianu Clements, Cody Spackman, Freddie Ng
**Sponsor:** Dave Norwood, David Eccles School of Business, University of Utah
**Faculty Advisor:** Matt Pecsok

> **Note for Claude Code:** Replace `[PROJECT NAME]` throughout this document with the confirmed project name before starting the build. The repo name, Streamlit page title, app.py title, and README heading must all use the same name consistently.

> **MVP Scope:** Build Track A (pipeline) and Track C (UI) to a working, shareable state first. Track B (generation) follows once extraction and rollover are solid. See Section 14 for build order.

---

## 1. Problem Statement

University faculty at the David Eccles School of Business maintain course syllabi and materials manually every term. Semester rollover requires updating dates throughout the document, reconciling the schedule table against the academic calendar, and re-entering content into Canvas by hand. This is error-prone — the sponsor's own Spring 2026 syllabus carries Fall 2025 schedule dates because the term label was updated but the schedule table was not. That specific bug is now a named test case.

Compounding the problem: Dave teaches courses of different lengths — 10, 12, and 16 weeks — and adapting a course to a different duration each time it runs is a significant manual effort on top of the date work.

Beyond rollover, generating course materials (quizzes, discussion prompts, rubrics, summaries) is time-intensive and ad hoc. Faculty have no structured workflow for it and no way to iterate on generated content over time.

The toolkit solves both problems with a local-first, open-source pipeline. It handles course maintenance and content generation, outputs in the instructor's own format plus Canvas-ready HTML, and persists a project workspace so faculty can return and iterate. There is no server, no accounts, and no maintenance obligation on the school after handoff.

---

## 2. Product Philosophy

**Local-first.** All data lives on the instructor's machine as files in a project folder. No accounts, no cloud database, no server. Sharing means sharing a folder or pushing to GitHub.

**Format-preserving.** Word documents come back as Word documents. Markdown comes back as markdown. The tool edits only what changes and leaves everything else untouched.

**Review before writing.** Nothing is written to disk without the instructor approving a summary of what will change. Silent rewrites destroy trust.

**Open source, forkable, instructor-owned.** The handoff is to the instructors themselves, not an operational team. The repo is the product. Documentation quality is a first-class deliverable.

**Model-agnostic by design.** All LLM calls go through a single provider abstraction. Swapping from OpenAI to a university-hosted local model requires one config change, not a code refactor.

**Honest about what AI does.** Generated content is always labeled as a draft requiring human review. Chong Oh's principle applies: the end result must show evident human effort. The tool is a starting point, not a finished artifact.

**Fails loudly, never silently.** When something goes wrong, the tool says what happened in plain English and tells the instructor how to fix it. Python tracebacks never reach the user.

---

## 3. Target Users

**Primary:** DESB faculty at the University of Utah maintaining courses in Word (.docx) or markdown (.md).

**Secondary:** Any instructor whose syllabus follows either supported format. The calendar file covers the University of Utah only. Other institutions can add their own term data by editing one JSON file — no code change required.

**Not targeted:** Students, TAs, administrators, or Canvas as an integration point. Canvas API access is explicitly out of scope.

---

## 4. Technology Stack

| Component | Choice | Notes |
|---|---|---|
| LLM — default | OpenAI `gpt-4o` | U of U licenses ChatGPT Pro; model is a config value |
| LLM — alternative A | Any OpenAI-compatible endpoint | Ollama on a university VM; base URL swap only |
| LLM — alternative B | Anthropic Claude (`claude-sonnet-5`) | Separate SDK; handled transparently in `llm_client.py` |
| Backend | Python 3.11+ | Team proficiency; strong library support |
| Word read/write | python-docx | Edits tables in place without disturbing formatting |
| Markdown parsing | Python stdlib + regex | No heavy dependency needed for structured tables |
| UI | Streamlit | Local, no-server, no deployment required |
| Canvas output | Plain HTML | No API; paste-ready artifact |
| Slides (stretch) | pandoc | Already in Matt's pipeline; we generate the markdown input only |

### 4.1 Model Provider Abstraction

All LLM calls go through a single `llm_client.py` module. The rest of the codebase calls `llm_client.complete(prompt, system)` and never imports any provider SDK directly. Swapping providers requires changing `.env` values and nothing else.

Three providers are supported. OpenAI and Ollama share the same code path because Ollama exposes an OpenAI-compatible API. Anthropic uses a separate SDK with a different response shape — this is handled entirely inside `llm_client.py`.

```python
# llm_client.py — the only file that knows about the provider
import os
import openai
import anthropic

_provider = os.getenv("LLM_PROVIDER", "openai").lower()

if _provider == "anthropic":
    _anthropic_client = anthropic.Anthropic(
        api_key=os.getenv("LLM_API_KEY")
    )
else:  # openai or ollama (ollama is openai-compatible)
    _openai_client = openai.OpenAI(
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    )


def complete(prompt: str, system: str = "", max_tokens: int = 2000) -> dict:
    """
    Send a prompt to the configured LLM provider.
    Returns {"text": str, "input_tokens": int, "output_tokens": int}
    Raises LLMProviderError with a plain-English message on failure.
    """
    try:
        if _provider == "anthropic":
            response = _anthropic_client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-sonnet-5"),
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}]
            )
            return {
                "text": response.content[0].text,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }

        else:  # openai or ollama
            response = _openai_client.chat.completions.create(
                model=os.getenv("LLM_MODEL", "gpt-4o"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens
            )
            return {
                "text": response.choices[0].message.content,
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens
            }

    except (openai.AuthenticationError, anthropic.AuthenticationError):
        raise LLMProviderError("API key was not accepted. Check your key and try again.")
    except (openai.APIConnectionError, anthropic.APIConnectionError):
        raise LLMProviderError(
            "Could not reach the LLM provider. "
            "Check your internet connection. "
            "Extraction and rollover work without a connection."
        )
    except Exception as e:
        raise LLMProviderError(f"Unexpected error from LLM provider: {type(e).__name__}")


class LLMProviderError(Exception):
    """Raised when the LLM call fails. Message is always plain English."""
    pass
```

`LLMProviderError` is the only exception that escapes `llm_client.py`. Every caller wraps the call in a try/except for this one type and surfaces the message directly in the UI. No other exception from any provider SDK should reach user-facing code.

### 4.2 Cost and Provider Options

API cost is a real concern for institutions cutting budgets. Three configurations are supported:

**OpenAI (default):** Each instructor provides their own OpenAI API key. Cost per generation run is a few cents at current `gpt-4o` pricing. The tool logs every call and shows running cost in the UI.

**Anthropic Claude:** Each instructor provides their own Anthropic API key from console.anthropic.com. Not currently licensed institution-wide at the U of U, so faculty use a personal key. Cost and quality are comparable to GPT-4o for structured generation tasks like quizzes and rubrics.

**University-hosted local model (Ollama):** If the university provisions a VM with a GPU and runs Ollama, the tool points at that endpoint instead. No API costs, no external data transmission, stronger FERPA posture. Quality varies by model size — a 70B parameter model on a 48GB GPU is competitive with GPT-4o on structured tasks; a 7B model on CPU is not. This path is documented in the README but requires UIT provisioning and is not part of the MVP build.

The `.env` variables that control which provider is active are documented in Section 11.

---

## 5. Core Concepts

### 5.1 Course Project

A course project is a directory on disk:

```
my-course/
  course.json           # Structured course schema — source of truth for all features
  config.json           # Project-level config (institution, model, output prefs)
  .env                  # LLM_API_KEY — gitignored, never committed
  source/               # Instructor-uploaded files (syllabus, readings, notes)
  outputs/
    syllabus.docx       # Updated Word syllabus (Word input path)
    syllabus.md         # Updated markdown syllabus (markdown input path)
    canvas.html         # Canvas-paste schedule HTML
    course-brief.md     # One-page course overview (generated without API call)
    quizzes/
    discussions/
    rubrics/
    summaries/
    slides/
    .archive/           # Previous versions of overwritten outputs, timestamped
  prompts/              # Editable prompt templates (.txt files)
  data/
    calendars.json      # Bundled U of U academic calendar data
  eval-log.json         # Append-only metrics log
  README.md             # Auto-generated handoff README
```

`course.json` is the structured representation of the course. Every feature reads from it. Re-running extraction after a syllabus update regenerates `course.json`. All downstream outputs can be refreshed on demand.

### 5.2 Course Schema (`course.json`)

`duration_weeks` is detected from the syllabus, not assumed. Supported values are any positive integer. Dave's courses run 10, 12, or 16 weeks — all are handled identically by the rollover logic, which reads `duration_weeks` and stops when it runs out of weeks.

```json
{
  "course": {
    "title": "IS 6640 Networking and Servers",
    "number": "IS 6640",
    "section": "090",
    "credits": 3,
    "term": "Fall 2026",
    "term_start": "2026-08-24",
    "term_end": "2026-10-26",
    "duration_weeks": 10,
    "meeting_pattern": "Online async",
    "instructor": "Dave Norwood",
    "source_format": "word",
    "source_file": "source/IS-6640-syllabus-fall-2026.docx",
    "extracted_at": "2026-09-17T10:00:00Z"
  },
  "learning_objectives": [
    "Understand the fundamentals of IT network infrastructure"
  ],
  "assessments": [
    { "name": "Video Quizzes", "weight": 0.05 },
    { "name": "Labs", "weight": 0.25 }
  ],
  "weeks": [
    {
      "week_number": 1,
      "date": "2026-08-24",
      "label": "Week 1 (8/24)",
      "is_break": false,
      "topics": ["Course Introduction", "Network+ Mod 1", "Network+ Mod 2"],
      "assignments": ["Network+ Lab A Due"],
      "notes": "Video Quizzes are Taken After Reading Each Chapter"
    },
    {
      "week_number": null,
      "date_start": "2026-10-10",
      "date_end": "2026-10-18",
      "label": "Fall Break",
      "is_break": true,
      "topics": [],
      "assignments": []
    }
  ],
  "university_dates": [
    { "event": "Classes begin", "date": "2026-08-24" },
    { "event": "Fall Break", "date_start": "2026-10-10", "date_end": "2026-10-18" },
    { "event": "Classes end", "date": "2026-10-26" }
  ],
  "source_materials": [
    { "filename": "chapter-3-summary.pdf", "added_at": "2026-09-17T10:00:00Z" }
  ]
}
```

### 5.3 Academic Calendar Data (`data/calendars.json`)

University of Utah only. Populated from the registrar's published PDFs, through the 2029-2030 academic year. This is a committed file that ships with the repo.

```json
{
  "institution": "University of Utah",
  "calendar_source": "https://registrar.utah.edu/academic-calendars/",
  "last_updated": "2026-09-17",
  "terms": [
    {
      "term": "Fall 2026",
      "start": "2026-08-24",
      "end": "2026-12-10",
      "verified_against": "https://registrar.utah.edu/academic-calendars/",
      "verified_date": "2026-09-17",
      "no_class_dates": [
        { "label": "Labor Day", "date": "2026-09-07" },
        { "label": "Fall Break", "date_start": "2026-10-10", "date_end": "2026-10-18" },
        { "label": "Thanksgiving Break", "date_start": "2026-11-26", "date_end": "2026-11-29" }
      ]
    }
  ]
}
```

**Graceful degradation:** If a requested term is not in the file, the tool prompts for a Week 1 date and proceeds normally. It never fails hard on a missing term.

**Updating the calendar:** Documented in the README as a plain JSON edit — no code required. One term block, copy-paste-update.

---

## 6. Features

### 6.1 Syllabus Extraction (F-01)

**What it does:** Parses an uploaded syllabus and writes `course.json`. Entry point for everything else.

**Word path (.docx):**
- Use `python-docx` to locate the schedule table. Pattern: first column contains "Week N (M/DD)", second column contains topics and assignments.
- Detect `duration_weeks` by counting non-break week rows in the table.
- Extract week number, date string, topics, assignments, and notes per row.
- Detect break rows (rows where the week cell contains no week number pattern).
- Extract learning objectives from the bulleted list under "Learning Objectives" or "Course Outcome and Objectives".
- Extract assessments from the grading weight table.
- Extract the university dates table if present.
- Do not modify any part of the document during extraction.

**Markdown path (.md):**
- Parse the schedule table with headers `| Week | Dates | ... | Major Work |`.
- Detect `duration_weeks` by counting non-break week rows.
- Extract week number, date range, topic, and major work per row.
- Extract break rows where the week cell is `| - |`.
- Extract university dates from a "University Academic Dates" table if present.

**Consistency check (always runs after extraction):**

Compare the term label in the document against the Week 1 date. If they conflict, surface a warning before proceeding:

```
⚠ TERM MISMATCH DETECTED
  Term label says: "Spring 2026"
  Week 1 date is:  August 18 — this is a fall semester start.

  This usually means the term label was updated but the schedule table was not.
  Check which is correct before continuing.

  [Continue anyway]  [Cancel]
```

This check exists because of a real error found in the sponsor's Spring 2026 syllabus. It is a named test case.

**Outputs:** `course.json`

---

### 6.2 Semester Rollover (F-02)

**What it does:** Takes `course.json` and a target term, shifts all dates, handles variable course lengths, and writes an updated syllabus in the original format.

**Inputs:**
- `course.json` (existing)
- Target term — dropdown in UI, typed in CLI
- If term not in `calendars.json`: prompt for Week 1 date, derive term end from `duration_weeks`

**Variable course length:**
- `duration_weeks` is read from `course.json` and respected exactly.
- A 10-week course rolled to a new term produces 10 instructional weeks.
- A 16-week course produces 16. No hardcoded assumptions.
- If Dave wants to change a 10-week course to 12 weeks, he edits `duration_weeks` in `course.json` (or corrects it during the Review step in the UI) before running rollover.

**Date logic:**
- Anchor Week 1 to the target term's start date.
- Shift each subsequent week by 7 days.
- Insert break rows where the academic calendar's no-class periods fall within the course window.
- For Word: update the date string in the week label cell only. All other cell content preserved.
- For markdown: update date columns. Flag any due date within two weeks of the DST boundary (first Sunday of November) for human review — do not automate the timezone suffix.
- Update the university dates table if present.
- Do not renumber quizzes, exams, or labs. Flag these for human review.

**Required review before any file is written:**

```
ROLLOVER PREVIEW: IS 6640 (10 weeks) → Fall 2027
────────────────────────────────────────────────
Term label:   "Fall 2026"   → "Fall 2027"    ✓
Duration:     10 weeks      → 10 weeks       ✓
Week 1:       Aug 24 (8/24) → Aug 23 (8/23)  ✓
Week 2:       Aug 31 (8/31) → Aug 30 (8/30)  ✓
Week 3:       Sep 7  (9/7)  → Sep 6  (9/6)   ✓
Week 7:       Oct 5  (10/5) → Oct 4  (10/4)  ✓
              ⚠ Fall Break 2027 is Oct 9–17 — confirm Week 8 timing
────────────────────────────────────────────────
Files to be written:
  outputs/syllabus.docx
  outputs/canvas.html
  outputs/course-brief.md

[Confirm]  [Cancel]
```

**Outputs:**
- `outputs/syllabus.docx` (Word path) — table cells updated in place
- `outputs/syllabus.md` (markdown path) — schedule table updated
- `outputs/canvas.html` — Canvas-paste HTML regenerated
- `outputs/course-brief.md` — regenerated automatically

---

### 6.3 Canvas HTML Export (F-03)

**What it does:** Generates a Canvas-paste HTML block from `course.json`. Available any time.

**Output:**
- Clean HTML table matching the schedule structure.
- Semantic markup, minimal inline styles, renders correctly pasted into Canvas's HTML editor.
- No external CSS, no JavaScript, no dependencies.
- Scoped to schedule and module content only — not the full syllabus.
- Header comment: `<!-- Generated by [PROJECT NAME] — paste into Canvas HTML editor -->`

**Outputs:** `outputs/canvas.html`

---

### 6.4 Course Brief (F-04)

**What it does:** Generates a one-page course overview from `course.json`. No API call — reads structured data only.

**Contents:**
- Course title, number, term, duration, credits, meeting pattern, instructor
- Learning objectives
- Assessment weights
- Condensed week-by-week schedule (week number, date, one-line topic)

**Generated automatically** after every extraction and rollover. Zero cost.

**Outputs:** `outputs/course-brief.md`

---

### 6.5 Content Generation (F-05)

**What it does:** Generates course materials via the LLM provider, grounded in `course.json` and instructor-uploaded source materials.

**Source materials** live in `source/`. Accepted: PDF, DOCX, MD, TXT. Indexed at project init, re-indexed when files are added. Textbook content must not be ingested wholesale — instructors supply their own summaries or excerpts.

**All generation rules:**
- Every generated file opens with: `> **AI-generated draft** — review and edit before use. Generated [date] using [model].`
- Prompt templates live in `prompts/` as editable `.txt` files with `{variable}` placeholders.
- Token usage and estimated USD cost logged to `eval-log.json` after every call.
- Model is read from `.env`, never hardcoded.

#### 6.5.1 Quizzes (F-05a)
- **Inputs:** week number(s), question count (default 5), format (multiple choice / short answer / mixed)
- **Context:** week topics and learning objectives from `course.json` plus selected source materials
- **Output:** markdown with questions and answer key in separate sections
- Questions follow Chong Oh's model: connect concepts across the week, not isolated recall
- **Saved to:** `outputs/quizzes/week-N-quiz.md`

#### 6.5.2 Discussion Prompts (F-05b)
- **Inputs:** week number(s), prompt count (default 3)
- **Output:** prompts at recall, application, and analysis levels — labeled by level
- **Saved to:** `outputs/discussions/week-N-discussion.md`

#### 6.5.3 Assignment Rubrics (F-05c)
- **Inputs:** assignment description (free text or uploaded file)
- **Output:** rubric in markdown table format with criteria, performance levels, and point values
- Per CTE policy: rubric drafting only. Grade assignment is not a feature.
- **Saved to:** `outputs/rubrics/[assignment-name]-rubric.md`

#### 6.5.4 Module Summaries (F-05d)
- **Inputs:** week number(s)
- **Output:** student-facing key concept summary grounded in that week's topics and source materials
- **Saved to:** `outputs/summaries/week-N-summary.md`

#### 6.5.5 Slide Content (F-05e — stretch)
- **Inputs:** week number, topic, bullet points or a reading excerpt
- **Output:** markdown following IS 4490 pptx pipeline conventions:
  - YAML title block at top, no `subtitle:` field
  - `##` headings as slide titles with `<!-- Slide N -->` comments
  - Two-column div syntax for image slides
  - No bare `#` headings
- Drops directly into Matt's `scripts/convert-slides-to-pptx.sh` — no conversion logic here
- **Saved to:** `outputs/slides/week-N-slides.md`

---

### 6.6 Project Persistence and Iteration (F-06)

**What it does:** Manages the workspace so instructors can return, add materials, and regenerate without starting over.

**First-run setup (Streamlit, on first launch):**
- Detect missing `.env`
- Prompt for LLM API key, write to `.env`
- Validate the key with a test call before proceeding
- If using a local endpoint: prompt for `LLM_BASE_URL` instead of an API key

**CLI commands:**
```bash
python toolkit.py init --name "IS-6640-Fall-2027"   # Create project directory
python toolkit.py add path/to/file.pdf               # Index source material
python toolkit.py generate quiz --week 3             # Regenerate with archive
python toolkit.py status                             # Show project summary
```

**Archive on overwrite:** Previous version moved to `outputs/.archive/[filename]-[timestamp]` before any new file is written to that path.

---

### 6.7 Metrics and Evaluation (F-07)

**What it does:** Collects backend metrics automatically on every operation. No instructor input required for core metrics. Required for the December presentation.

| Metric | Collected automatically |
|---|---|
| Generation count by type | Yes — incremented on every successful LLM call |
| Token usage per call | Yes — from API response |
| Estimated cost per call (USD) | Yes — calculated from token count and config rates |
| Total project cost to date | Yes — summed in status and UI footer |
| Rollover runs | Yes — logged with source term, target term, duration, timestamp |
| Extraction errors | Yes — error type and filename logged on failure |
| Consistency check results | Yes — pass/fail with mismatch detail |
| Archive events | Yes — logged with archived file path and timestamp |
| Output files generated | Yes — count by type |
| Source files indexed | Yes — count updated on add |

**Logged to:** `eval-log.json` — append-only, one JSON object per event. Content of generated files is never logged. No usage data leaves the machine.

**Reported in UI:** Metrics tab shows generation counts (bar chart), total cost, rollover history, and any extraction errors.

**For December:** The eval log from the five-syllabus test corpus is the evidence artifact — files processed, consistency check catches, cost per content type, error rate by format.

---

## 7. Streamlit UI (F-08)

**Status: Core deliverable.** The UI is a thin wrapper. All logic lives in Python modules. The UI calls the same functions the CLI does. No business logic in the UI layer.

### 7.1 First-Run Experience

On first launch, if `.env` is missing or the key is invalid:
1. Setup screen — two sentences explaining what the tool does.
2. Provider selection — three options shown as radio buttons:
   - **OpenAI** — paste API key from platform.openai.com
   - **Anthropic Claude** — paste API key from console.anthropic.com
   - **Local model (Ollama)** — enter the endpoint URL (e.g. `http://localhost:11434/v1`) and model name
3. Key or URL validated with a test call before proceeding.
4. Write `.env` and enter the main interface.

The active provider is shown in the UI footer throughout the session (e.g. "Provider: OpenAI gpt-4o" or "Provider: Anthropic claude-sonnet-5").

The instructor never needs a terminal or text editor to complete setup.

### 7.2 Views

**Upload**
- File uploader: .docx and .md accepted
- Project name field (pre-filled from filename)
- "Extract course" runs F-01
- Consistency check warnings shown inline before proceeding

**Review**
- Extracted `course.json` displayed in readable format: course details, duration, objectives, assessment weights, week-by-week
- `duration_weeks` shown and editable — instructor can correct before saving
- "Confirm and save" writes `course.json` and generates course brief

**Rollover**
- Term selector dropdown from `calendars.json`
- Manual Week 1 date input if term not found
- Duration shown from `course.json` — editable here if changing course length
- "Preview rollover" shows date diff table with flags
- "Confirm rollover" writes files and shows download buttons

**Generate**
- Content type selector (quiz, discussion, rubric, summary, slides)
- Week selector and type-specific options
- Source material checklist — instructor selects which files are relevant
- Estimated cost shown before generation runs
- Output shown inline for review before saving
- "Save" writes to `outputs/` and archives any previous version
- "Regenerate" runs a new call after confirmation

**Export**
- All `outputs/` files with individual download buttons
- "Copy Canvas HTML" button
- "Download all as zip"

**Metrics**
- Generation count by type (bar chart)
- Total API cost to date
- Rollover history
- Extraction errors (if any)
- Provider in use (OpenAI / local)

### 7.3 Error Messages

Every error is a plain-English callout box. No tracebacks.

| Error | Message |
|---|---|
| No schedule table found | "No schedule table found. Make sure your syllabus has a table with 'Week' in the first column, then try again." |
| OpenAI API key invalid | "The OpenAI API key was not accepted. Check it at platform.openai.com and try again." |
| Anthropic API key invalid | "The Anthropic API key was not accepted. Check it at console.anthropic.com and try again." |
| API unreachable | "Could not reach the LLM provider. Check your connection. Extraction and rollover work without a connection." |
| Local endpoint unreachable | "Could not reach the local model at [URL]. Check that Ollama is running and the URL in your .env is correct." |
| Term not in calendar | "That term isn't in the calendar data yet. Enter the first day of classes below and we'll calculate the rest." |
| Password-protected Word file | "This Word file is protected. Remove the password in Word (Review > Protect Document) and re-upload." |
| Overwrite confirmation | "A [type] already exists for Week [N]. Generating a new one will archive the old version. Continue?" |
| Duration mismatch | "The course has [N] weeks in the schedule but duration_weeks says [M]. Correct this in the Review tab before rolling over." |

---

## 8. README and Handoff Documentation

The README is a first-class deliverable. It is the handoff to the instructors.

### 8.1 README Structure

```
1. What this tool does (2-3 sentences)
2. Quick start
   a. Requirements (Python 3.11, pip)
   b. Clone and install
   c. First launch (streamlit run app.py)
3. How to use the UI (one paragraph per view)
4. CLI reference
5. Adding source materials
6. Understanding your outputs
7. Updating the academic calendar (JSON edit, no code)
8. Choosing and configuring your LLM provider
   a. OpenAI (default)
   b. Anthropic Claude
   c. University-hosted local model (Ollama)
9. Customizing prompt templates
10. Forking and customizing the repo
    a. How to fork on GitHub
    b. Changing the institution or calendar data
    c. Adding a new output type
11. FAQ and error reference
12. Data and privacy (what stays local, what goes to OpenAI, FERPA)
```

### 8.2 Section 8 — Provider Configuration

This section documents all three provider options in the README.

**8a. OpenAI (default)**
```
Get your key at platform.openai.com under API keys.
Note: this is separate from your ChatGPT login.

  LLM_PROVIDER=openai
  LLM_API_KEY=sk-...
  LLM_BASE_URL=https://api.openai.com/v1
  LLM_MODEL=gpt-4o

Cost: a few cents per generation run at current pricing.
The tool logs every call and shows your running total.
```

**8b. Anthropic Claude**
```
Get your key at console.anthropic.com under API keys.
Anthropic is not currently licensed institution-wide at the University of Utah.
Faculty use a personal API key and pay their own usage costs.

  LLM_PROVIDER=anthropic
  LLM_API_KEY=sk-ant-...
  LLM_BASE_URL=           (leave blank)
  LLM_MODEL=claude-sonnet-5

Cost: similar to GPT-4o. Generation quality is comparable
for structured tasks like quizzes and rubrics.
```

**8c. University-hosted local model (Ollama)**
```
Requirements:
  - A VM with an NVIDIA GPU (24GB+ VRAM recommended for useful quality)
  - Ollama installed: ollama.com
  - A model pulled: ollama pull llama3.1:70b

Configuration:
  LLM_PROVIDER=openai      (Ollama is OpenAI-compatible)
  LLM_API_KEY=ollama
  LLM_BASE_URL=http://your-vm-ip:11434/v1
  LLM_MODEL=llama3.1:70b

Cost: no API costs once the VM is provisioned.
No data leaves the university network.

Quality note:
  Smaller models (7B-13B parameters) produce noticeably weaker quiz
  and rubric drafts than GPT-4o or Claude. A 70B model on adequate
  hardware is competitive for structured generation tasks.
  Test on a sample week before using in production.
  Set cost_rates.local.default to 0.0 in config.json (already the default).
```

### 8.3 FAQ

The FAQ maps every UI error message to a cause and fix. Written during build.

Selected entries:

**"No schedule table found" — what does this mean?**
The tool looks for a table with "Week" in the first column. If your schedule is in a different format, reformat it as a standard table in Word and re-upload.

**The term label mismatch warning appeared — what do I do?**
Check whether the term label or the schedule dates are wrong. Update whichever is incorrect. This check exists because it is easy to update the label and forget the table — or vice versa.

**My OpenAI key works in ChatGPT but the tool says it is invalid.**
ChatGPT and the OpenAI API use separate credentials. Go to platform.openai.com and create an API key under "API keys." This is different from your ChatGPT login.

**I want to use Anthropic Claude instead. How do I switch?**
Go to console.anthropic.com, create an API key, and update your `.env` file: set `LLM_PROVIDER=anthropic`, paste your key as `LLM_API_KEY`, and set `LLM_MODEL=claude-sonnet-5`. The Streamlit setup screen can do this for you on first launch, or if you re-run setup from the settings panel.

**The dates look wrong after rollover.**
The review screen shows every change before anything is written. If you already confirmed and the result is wrong, the previous version is in `outputs/.archive/` with a timestamp. Copy it back to `outputs/` to restore it.

**How do I add next year's calendar?**
Open `data/calendars.json` in any text editor. Copy the block for the most recent term, paste it after, and update the term name, start, end, and no-class dates from registrar.utah.edu/academic-calendars. No code change needed.

**My course runs 12 weeks, not 10. How do I change it?**
On the Review tab after uploading your syllabus, find the `duration_weeks` field and correct it. Or edit `course.json` directly. Rollover will use the value you set.

---

## 9. Out of Scope

| Item | Reason |
|---|---|
| Canvas API integration | Access revoked once; cannot be guaranteed |
| Grading or grade assignment | CTE policy; rubric drafting only |
| Custom GPTs / Assistants API | Custom GPTs shut down December 11, 2026 — one day after handoff |
| Slides conversion | Matt's pipeline handles this; we generate the markdown input only |
| Textbook ingestion | Copyright exposure |
| Multi-user hosting | Contradicts local-first, instructor-owned handoff model |
| Student-facing features | Best Practices Guide only, not built |
| AI detection tools | CTE advises against; unreliable; FERPA risk |
| Non-U-of-U calendar data | Scoped to U of U; documented extension path in README |

---

## 10. Non-Functional Requirements

- **Offline after setup.** Only network call is the LLM provider during generation. Extraction and rollover work with no internet.
- **No silent writes.** Every file write requires confirmation.
- **Graceful API degradation.** If LLM provider is unreachable, extraction, rollover, and export still work. Generation shows a clear unavailable message.
- **Archive before overwrite.** Old output moved to `.archive/` with timestamp before new file is written.
- **FERPA safe.** No student data can be uploaded. UI and prompt templates state this explicitly.
- **Cost visible.** Token count and estimated cost shown after every generation call. Running total in UI footer.
- **Model-agnostic.** All LLM calls behind `llm_client.py`. Provider swap requires `.env` change only.

---

## 11. File and Config Conventions

**`.env` (gitignored — never committed):**

OpenAI (default):
```
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

Anthropic Claude:
```
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_BASE_URL=
LLM_MODEL=claude-sonnet-5
```

Ollama (local — OpenAI-compatible):
```
LLM_PROVIDER=openai
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1:70b
```

**`config.json` (committed):**
```json
{
  "institution": "University of Utah",
  "calendar_source": "https://registrar.utah.edu/academic-calendars/",
  "calendar_file": "data/calendars.json",
  "default_output_formats": ["docx", "html"],
  "archive_outputs": true,
  "cost_rates": {
    "openai": {
      "gpt-4o":          { "input_per_1k": 0.0025, "output_per_1k": 0.010 },
      "gpt-4o-mini":     { "input_per_1k": 0.00015, "output_per_1k": 0.0006 }
    },
    "anthropic": {
      "claude-sonnet-5": { "input_per_1k": 0.003, "output_per_1k": 0.015 },
      "claude-haiku-4-5-20251001": { "input_per_1k": 0.0008, "output_per_1k": 0.004 }
    },
    "local": {
      "default":         { "input_per_1k": 0.0, "output_per_1k": 0.0 }
    }
  }
}
```

Cost rates are in config so they can be updated when OpenAI changes pricing without touching code. Set both to 0.0 when using a local model.

**`prompts/` (committed — editable by instructors):**

One `.txt` file per generation type. `{variable}` placeholders. Instructors can edit without touching Python.

Example `prompts/quiz.txt`:
```
You are helping a university instructor create a quiz for {course_title}.

Week {week_number} covers: {topics}

Learning objectives for this course:
{learning_objectives}

Generate {question_count} questions in {format} format.
Questions should connect concepts across the week rather than test isolated recall.
Reference specific course elements (module names, tools, frameworks) where relevant.

{source_material_context}

Format: markdown with a "Questions" section and an "Answer Key" section.
Label questions Q1, Q2... and answers A1, A2...
No preamble or explanation outside the questions and answers.
```

---

## 12. Non-Build Deliverables

### 12.1 Best Practices Guide

**Owner:** Dedicated team member, single voice throughout.

**Outline:**
1. Introduction — AI in higher education, DESB "AI fluent, fundamentals strong" mandate
2. The probabilistic vs deterministic framework (Chong Oh interview)
   - Probabilistic: emails, discussion prompts, assignment drafts — human review required
   - Deterministic: date calculations, rubric scoring, Canvas formatting — automatable with guardrails
3. High-level recommendations for faculty
4. Before and after examples for each use case
5. Student-facing AI guidance — designing assignments that promote responsible use
6. AI-resistant assignment design — principles and examples
7. Preventing misuse — university position (assignment design, not detection)
8. Catalog of approved tools (summarized; full catalog is a separate document)
9. Training and peer groups at the university
10. DESB and U of U resources

**Reference:** IU Kelley AI Playbook for section structure. Kelley's Agentic AI Builder validates that a guide alone is not sufficient — the tool deliverable is equally important.

### 12.2 Catalog of Tools

**Owner:** Same as Guide, reviewed by all.

**Outline:**
- Scope and evaluation criteria
- Tool entries: name, primary use, strengths, weaknesses, compliance posture, cost, access
- Comparison table (from industry research Draft 2)
- University-provided tools (Copilot, Gemini, ChatGPT, Canvas-native)
- Commercial tools evaluated but not provided
- Decision guide: which tool for which task

**Source:** Industry Research Findings Draft 2 contains the raw content.

---

## 13. Known Risks

| Risk | Mitigation |
|---|---|
| Word format variability beyond two known syllabi | Parser targets documented structures; errors surface in plain English; README documents expected format |
| OpenAI pricing or model changes | Model and cost rates in config; one-line update |
| Anthropic pricing or model changes | Same config pattern; update `cost_rates.anthropic` and `LLM_MODEL` |
| Local model quality significantly below GPT-4o or Claude | Documented in README; quality note shown in UI when local endpoint is active |
| UIT GPU provisioning delayed or denied | Local model path is optional; OpenAI path is the default and always works |
| Markdown DST boundary | Flagged for human review; never automated |
| Scope creep into grading | Rubric drafting is the hard line. |
| Setup friction for non-technical faculty | Streamlit handles .env; README has step-by-step with screenshots |
| Calendar data stale after 2029-2030 | README documents the JSON edit update process |

---

## 14. Build Order — MVP First

Get a working, repo-shareable prototype before extending to generation.

### Track A: Pipeline — build first

1. Populate `data/calendars.json` — U of U terms through 2029-2030
2. Define `course.json` schema and write a schema validator
3. `llm_client.py` abstraction module (even if generation comes later, build this now)
   - `requirements.txt` must include both `openai` and `anthropic` packages
   - Provider is selected at runtime via `LLM_PROVIDER` env var, not at install time
4. Word extractor — F-01 Word path
5. Markdown extractor — F-01 markdown path
6. Consistency check — F-01 validation (term label vs Week 1 date)
7. Semester rollover — Word path — F-02 (respects `duration_weeks`)
8. Semester rollover — markdown path — F-02
9. Canvas HTML export — F-03
10. Course brief generator — F-04 (no API call)
11. Project init and CLI — F-06
12. Metrics logger scaffold — F-07 (write the `eval-log.json` structure early; all later steps log to it)

### Track B: Generation — after Track A steps 1-6 are solid

13. Quizzes — F-05a
14. Discussion prompts — F-05b
15. Rubrics — F-05c
16. Module summaries — F-05d
17. Evaluation metrics completion — F-07

### Track C: UI — after Track A is complete

18. Streamlit skeleton and first-run setup (provider selection)
19. Upload and Review views
20. Rollover view
21. Generate view
22. Export and Metrics views
23. Error messages and FAQ wording

### Stretch

24. Slide content generation — F-05e

---

## 15. Test Corpus

Run the full pipeline before the November 8 readiness meeting. Report per-file in December.

| File | Format | Weeks | Notes |
|---|---|---|---|
| IS 6640 Fall 2026 (Dave) | Word | 10 | Primary Word test case |
| IS 6640 Spring 2026 (Dave) | Word | 10 | Contains the term label bug — consistency check must catch it |
| IS 4490 Fall 2026 (Matt) | Markdown | 15 | Primary markdown test case; DST boundary present |
| TBD from Dave interview | TBD | 12 or 16 | Variable duration test — needed to validate duration_weeks logic |
| TBD third DESB syllabus | TBD | TBD | Additional format coverage |

Dave offered before/after syllabi at the 9/17 meeting. Collect these immediately — they are the most valuable input for the parser.

---

## 16. Deliverable Mapping to SOW

| SOW Deliverable | This Project | Status |
|---|---|---|
| Best Practices Guide | Section 12.1 — standalone document | In progress |
| Catalog of Tools | Section 12.2 — standalone document | Research complete (Draft 2) |
| AI Agent — course material generation | F-05 Content Generation | Core build |
| AI Agent — grading support | F-05c Rubric generation only | Scoped per CTE policy |
| Student-facing assignment suggestions | Best Practices Guide | Guidance only |
| Responsible AI integration | Best Practices Guide | Guidance only |
| AI-resistant assignments | Best Practices Guide | Guidance only |
| Handoff to working team | README + open source repo | Handoff is to instructors directly |

