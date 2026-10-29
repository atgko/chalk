# Chalk

Chalk keeps a university course syllabus current from term to term and drafts course materials from it. Upload a Word or markdown syllabus, and Chalk reads the schedule, rolls every date forward to a new term (flagging anything a human should check), and produces a Canvas-ready schedule and a one-page course brief. With an AI provider connected, it also drafts quizzes, discussion prompts, rubrics, module summaries, and slide outlines, always as clearly-labeled drafts for you to review.

Everything runs on your own computer. Your files never leave it, except for the text sent to the AI provider you choose when you generate content.

**New to the project? [GETTING-STARTED.md](GETTING-STARTED.md)** walks you through running the demo on your own computer, step by step.

---

## Contents

1. [What this tool does](#1-what-this-tool-does)
   - [What works without an API key (free)](#1a-what-works-without-an-api-key-free)
2. [Quick start](#2-quick-start)
3. [How to use the app](#3-how-to-use-the-app)
4. [Command-line reference](#4-command-line-reference)
5. [Adding source materials](#5-adding-source-materials)
6. [Understanding your outputs](#6-understanding-your-outputs)
7. [Updating the academic calendar](#7-updating-the-academic-calendar)
8. [Choosing and configuring your AI provider](#8-choosing-and-configuring-your-ai-provider)
9. [Customizing prompt templates](#9-customizing-prompt-templates)
10. [Forking and customizing the repo](#10-forking-and-customizing-the-repo)
11. [FAQ and error reference](#11-faq-and-error-reference)
12. [Data and privacy](#12-data-and-privacy)

---

## 1. What this tool does

| Feature | What you get | Needs an AI provider? |
|---|---|---|
| **Syllabus extraction** | Reads your syllabus into `course.json`: course details, learning objectives, grading weights, and the week-by-week schedule. Checks that the term label matches the Week 1 date. | No (a PDF can optionally be read with AI) |
| **Semester rollover** | Shifts every date to a new term, inserts that term's breaks, and shows a full preview with flags before anything is written. | No* |
| **Canvas HTML** | Your Canvas syllabus page, filled in: the course banner, instructor details, objectives, grading, the schedule, and the standard help and accessibility sections. Paste it into the syllabus page's HTML editor in place of the template. | No |
| **Course brief** | A one-page overview of the course, rebuilt automatically after every extraction and rollover. | No |
| **Content drafts** | Quizzes, discussion prompts, rubrics, module summaries, slide outlines. | Yes |
| **Metrics** | Cost, rollover history, consistency-check catches, extraction errors, plus a downloadable evaluation report. | No |

\*Only if you lengthen a course during rollover and ask the AI to draft topics for the new weeks. Without a provider, those weeks are added as clearly marked placeholders.

### 1a. What works without an API key (free)

Most of Chalk never calls an AI model, so it costs nothing and nothing leaves your computer. You can use all of this without entering an API key: on the welcome screen, click **Skip for now**.

| Free: no API key, no cost, works offline | Tab |
|---|---|
| Reading a Word (.docx) or markdown (.md) syllabus | Upload |
| Reading a PDF syllabus with **Read it on this computer** (the default) | Upload |
| Checking that the term label matches the Week 1 date | Upload |
| Reviewing and correcting course details, grading weights, and every week, including dating a schedule that has no dates | Review |
| Rolling a course over to a new term: new dates, the new term's breaks, holiday warnings, a full preview, and the updated Word or markdown syllabus | Rollover |
| Lengthening or shortening a course at rollover (added weeks get placeholder topics to fill in) | Rollover |
| Canvas HTML and the course brief | Export |
| Reading, downloading (Word, PDF, markdown), and deleting drafts you've already saved | Drafts |
| Costs, rollover history, error counts, and the evaluation report | Metrics |
| Opening, creating, and switching between courses | Launch screen, **All courses** (top left, above the tabs) |

These need an AI provider, and each one says so before it runs:

| Uses the AI provider (costs a few cents, sends course text to the provider) | Tab |
|---|---|
| Generating or regenerating a quiz, discussion prompts, an assignment, a rubric, a summary, or slides. The estimated maximum cost is shown before you click **Generate**. | Generate |
| **Read it with AI** for a PDF whose layout the free reader can't follow. The cost per page is shown next to the option. | Upload |
| "Draft topics for the added weeks with AI" when you lengthen a course. Untick it to add placeholder weeks for free. | Rollover |

Every AI call's cost is added to the footer's "Project cost to date" and the Metrics tab. To use the AI features without paying per call, run a model on your own computer or a university server with Ollama (section 8c). It's free to use, but needs a powerful machine, is slower, and usually writes weaker drafts than OpenAI or Anthropic models.

## 2. Quick start

### 2a. Requirements

- **Python 3.11 or newer.** Check with `python --version`. Get it from [python.org](https://www.python.org/downloads/). On Windows, tick "Add python.exe to PATH" in the installer.
- An AI provider account is optional; see [section 8](#8-choosing-and-configuring-your-ai-provider).

### 2b. Get the code

Download it from GitHub (**Code → Download ZIP**, then unzip it), or clone it:

```bash
git clone https://github.com/atgko/chalk.git
```

### 2c. Start it

**Double-click `Start Chalk.bat`** (Windows) or **`Start Chalk.command`** (macOS; the first time, right-click it and choose **Open**). On Linux, run `./"Start Chalk.command"`.

The first start sets everything up, which takes a couple of minutes and needs internet. After that, it opens in seconds. Your browser opens on Chalk. A console window stays open while Chalk runs: minimize it, but don't close it, because closing it stops Chalk.

- **Want to look around first?** Double-click **`Start Chalk Demo`** instead, or click **Open the demo course** on the launch screen. It opens a sample course with a syllabus already loaded. See [DEMO.md](DEMO.md) for a guided walkthrough.
- **Your own course:** on the launch screen, type a name (for example `IS-6640-Fall-2027`) and click **Create project**. Projects are saved in the `projects/` folder next to the launchers. To reopen one, pick it under **Your projects** (most recently used first) and click **Open**. For a project kept somewhere else, paste or browse to its folder under **Open a course project**.
- **AI provider:** connect one on the welcome screen, or click **Skip for now**. Extraction, rollover, and export work without one, and you can connect later in the **Settings** tab.

### 2d. Manual setup (optional)

The launchers do this for you. To set up by hand instead (for development, say):

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
source .venv/bin/activate      # macOS / Linux
pip install -r requirements.txt
streamlit run app.py                                  # launch screen
streamlit run app.py -- --project "path/to/project"   # open a project directly
```

## 3. How to use the app

The app has eight tabs. Rollover, Generate, Export, and Metrics unlock once a course has been extracted and saved.

**Upload.** Choose your `.docx`, `.md`, or `.pdf` syllabus and click **Extract course**. For a PDF, first pick how Chalk should read it (see *PDF syllabi* in section 6). If the term label doesn't match the Week 1 date (for example, "Spring 2026" with an August Week 1), you'll see a warning. Fix the syllabus and re-upload, or click **Continue anyway**. The override is recorded in the metrics log. If the document has more than one table that looks like a schedule, you'll be asked to pick the right one.

**Review.** Check what was extracted: course details, learning objectives, grading weights, and every week. If the schedule has no dates (e.g. "Meeting 1" to "Meeting 10"), pick the **Session** the course starts in, or type the **Week 1 date**, and the other weeks follow, one week apart, skipping breaks. Credits can be a decimal, like 1.5. `Duration (weeks)` is editable. Change it here to lengthen or shorten the course at the next rollover. Click **Confirm and save** to write `course.json` and the course brief. Nothing is saved until you do.

**Rollover.** Pick the target term. It defaults to the same season next year. For a term that isn't in the calendar data, choose **Another term** and enter the first day of classes. **Session** is for programs that split the term into three 5-week sessions: pick **Session 1**, **2**, or **3** (5 weeks, e.g. a 1.5-credit course), **Sessions 1–2** or **2–3** (10 weeks), or **Full term**. Week 1 moves to that session's first day and the duration to 5 or 10 weeks; you can still change the duration. Sessions are counted as five class weeks each from the term's first day, not counting multi-day breaks like Fall Break (Fall 2026: Aug 24, Sep 28, Nov 9). Summer has no sessions: it's a compressed term, so the choice there is **Summer length**, either the **Full summer term (12 weeks)** or **10 weeks**, both starting on the term's first day. It defaults to one session for a 1.5-credit or 5-week course, Sessions 1–2 for a 10-week course, and the full term otherwise. Under **Class meets on**, pick the days the class meets in the new term (pre-filled from the syllabus's meeting pattern, or, when the schedule has a row per class meeting, from the days those rows fall on). Holiday and break warnings then appear only when one lands on a class day. A schedule with a row per class meeting (`Week 2 (1/13)`, `Week 2 (1/15)`) has each meeting dated on its day: pick one day per meeting, e.g. Tue and Thu, and Week 1's meetings land on the first Tuesday and Thursday on or after Week 1's start. With a different number of days picked, each meeting keeps its spacing from the week's first meeting, and the preview says so. Each of the term's breaks has a toggle: switch one off if the class meets through it (some graduate programs do), and it's left out of the schedule. Click **Preview rollover** to see every week's old and new date, plus flags for anything to check by hand: a week landing on a holiday or break, a changed course length, or (markdown syllabi) due dates near the daylight-saving change. Click **Confirm rollover** to write the files. Previous versions are archived, never overwritten.

**Generate.** Choose a content type and week (or, for a rubric, the assignment name and description), then any source materials to ground the draft in. **Course level** sets how demanding the draft is: lower-division undergraduate, upper-division undergraduate, or graduate. It starts from the course number (1000–2000 level, 3000–5000 level, 6000 and up), and you can change it. For an assignment, tick **Include a task where students use AI as part of their learning** to add one task where students use an AI tool, document how they used it, and reflect on its limits. The task gets its own section, **AI-USE TASK** (printed in red in the Word and PDF downloads), and is marked "(AI-use task)" in the task list; if a draft comes back without that section, Generate says so. The estimated maximum cost is shown before you click **Generate**. The draft appears for review. **Save** writes it to `outputs/`, **Regenerate** makes a new call (after asking), and **Discard** throws it away. If a draft already exists for that week, you'll be asked before it's replaced (the old one is archived). Under **Export**, download any draft except slides as Word or PDF, laid out like the assignment creator's documents (a header naming the document type, a title, and tables for rubrics), or as the markdown itself. Word and PDF leave out the AI-draft banner, since they're meant for students; the saved markdown keeps it.

**Drafts.** Every draft you've saved from Generate, grouped by type and in week order. Open one to read it and download it as Word, PDF, or markdown, as on Generate (slides as markdown only). **Show** narrows the list to one type. Each draft says when it was saved and how many earlier versions are in its folder's `.archive/`. To delete a draft, tick the confirm box and click **Delete**. The file moves to `.archive/` too, so it can still be recovered.

**Export.** Download any output file, or everything as a zip. The Canvas HTML is shown in a box with a copy button. **Regenerate Canvas HTML and course brief** rebuilds both from the current `course.json`.

**Metrics.** Total AI cost, rollovers, consistency-check catches, extraction errors, generations by type, and rollover history. **Download evaluation report** produces a markdown summary for reporting.

**Settings.** Change your AI provider, model, or API key. Every change is tested with a short call before it's saved. You enter your key once: it's saved in this computer's password store (Windows Credential Manager, or the Keychain on a Mac) and every course uses it.

The footer always shows the active provider and the project's AI cost to date.

## 4. Command-line reference

Everything the app does is also available from a terminal, which is useful for scripting or working without a browser. Run commands from the repo folder with the virtual environment active. Every command except `init` takes `--project <folder>` (default: the current folder).

```bash
python toolkit.py init --name "IS-6640-Fall-2027" [--dir <parent folder>]
python toolkit.py extract path/to/syllabus.docx --project IS-6640-Fall-2027 [--continue-anyway]
python toolkit.py extract path/to/syllabus.pdf --project IS-6640-Fall-2027 [--read-pdf-with local|ai]
python toolkit.py rollover --term "Fall 2027" --project IS-6640-Fall-2027 [--session 2-3] [--weeks 12] [--week1-date 2027-08-23] [--meeting-days TR] [--no-break "Fall Break"] [--no-llm] [--yes]
python toolkit.py export --project IS-6640-Fall-2027
python toolkit.py add path/to/chapter-3-summary.pdf --project IS-6640-Fall-2027
python toolkit.py generate quiz --week 3 --source chapter-3-summary.pdf --project IS-6640-Fall-2027 [--count 5] [--format mixed]
python toolkit.py generate quiz --week 3 --source notes.md --multiple-choice 4 --short-answer 2   # a mixed quiz with a set split
python toolkit.py generate discussion --week 3 --source notes.md [--count 3] [--level graduate]   # level defaults from the course number
python toolkit.py generate assignment --assignment "Design Brief" --assignment-goal "Defend a design." --source notes.md [--ai-component]
python toolkit.py generate summary --week 3 --source notes.md
python toolkit.py generate slides --week 3 --source notes.md [--notes "bullet points or an excerpt"]
python toolkit.py generate rubric --assignment "Lab 3" --description-file lab3.docx --source notes.md [--points 100]
python toolkit.py report --project IS-6640-Fall-2027
python toolkit.py demo [--reset]
python toolkit.py status --project IS-6640-Fall-2027
```

- `extract` asks before saving past a failed term/Week-1 check. `--continue-anyway` skips the question, and the override is still logged. A PDF is read on this computer unless you pass `--read-pdf-with ai`.
- `rollover` prints the full preview and asks before writing. `--yes` skips the question. If the term isn't in the calendar, it asks for the first day of classes (or pass `--week1-date`). `--session` (`1`, `2`, `3`, `1-2`, `2-3`, or `1-3`) rolls into those 5-week sessions: it sets Week 1 to the session's first day and, unless you pass `--weeks`, the length to 5 or 10 weeks. `--week1-date` overrides it. Summer terms have no sessions; use `--weeks 10` or `--weeks 12`. `--meeting-days` (e.g. `TR`, `MW`, `"Mon,Wed"`) limits holiday warnings to class days; `--no-break` (repeatable) drops a break the class meets through.
- `generate` shows the estimated cost, asks before replacing an existing draft (`--yes` skips this), then saves the draft and prints tokens used and cost. It needs at least one `--source` file of your own besides the syllabus (see section 5); `--source` can be repeated.
- `report` writes `outputs/evaluation-report.md`.
- Run `python toolkit.py <command> -h` for every option.

The CLI uses the AI provider saved in the app's Settings tab (one for every course). A project's own `.env` overrides it (see section 8), and so does any `LLM_*` variable already set in your shell.

## 5. Adding source materials

Source materials are your own summaries, notes, excerpts, and handouts that ground generated content in what you actually teach. Accepted types: PDF, DOCX, MD, TXT. Every draft needs at least one (the syllabus doesn't count), so the content comes from you rather than the AI's general knowledge.

- **In the app:** on the Generate tab, open **Add source materials**, choose files, and click **Add to project**. They're copied into the project's `source/` folder and appear in the **Source materials to use** list. (Files you copy into `source/` yourself appear there too.)
- **From the CLI:** `python toolkit.py add path/to/file.pdf --project <folder>` copies the file into `source/` and records it.

Pick only the files relevant to the week you're generating for. Their text is included in the prompt up to about 6,000 tokens (~24,000 characters), and anything beyond that is cut off with a note. Scanned PDFs have no extractable text and contribute nothing.

**Don't add whole textbooks** (copyright). Add your own summaries or short excerpts instead. **Never add student work, grades, or rosters** (see [section 12](#12-data-and-privacy)).

## 6. Understanding your outputs

A course project folder looks like this:

```
IS-6640-Fall-2027/
  course.json            The structured course; every output is built from it
  config.json            Institution, calendar file, cost rates
  .env                   Your AI provider settings (never share or commit this)
  source/                Your syllabus and source materials
  outputs/
    syllabus.docx        Rolled-over Word syllabus (Word input)
    syllabus.md          Rolled-over markdown syllabus (markdown input)
    canvas.html          Canvas syllabus page, for its HTML editor
    course-brief.md      One-page course overview
    evaluation-report.md Metrics summary (from `report` or the Metrics tab)
    quizzes/  discussions/  assignments/  rubrics/  summaries/  slides/
    .archive/            Every previous version, timestamped
  prompts/               Editable prompt templates
  data/calendars.json    Academic calendar data
  eval-log.json          Metrics log (one line per event; stays on this computer)
  README.md              A short guide to the folder
```

- **Word rollover** changes only the date inside each "Week N (M/DD)" label, the term (wherever it was found), break rows, and the university-dates table. Everything else in the document (formatting, other text, other tables) is untouched.
- **Markdown rollover** rewrites the schedule table and term line and leaves the rest of the file as it was.
- Rollover **never renumbers** quizzes, exams, or labs. If the course length changes, it flags this so you can check numbering yourself.
- **Every generated file starts with** `> **AI-generated draft** — review and edit before use. Generated <date> using <model>.` Slide decks carry the same line as a comment just below their title block, so it doesn't become a slide.
- **Slides** follow the IS 4490 pptx pipeline conventions (a YAML title block, `##` slide titles with `<!-- Slide N -->` comments, no `#` headings) and can be fed straight into `scripts/convert-slides-to-pptx.sh`.
- **Nothing is ever overwritten.** The previous version of any file (including `course.json`) is moved into a `.archive/` folder with a timestamp first. To restore one, copy it back and remove the timestamp from its name.

**What Chalk expects in a syllabus:**

- **The term near the top**, with a four-digit year (e.g. `Fall 2026`). That's the only required detail. It can be in a `Term:` / `Semester:` line or in the title line (e.g. `Networking and Servers – Online Fall 2026`).
- Other details are picked up when present, as `Label: value` lines or a two-column table near the top: course title and number (also guessed from the title lines, e.g. `IS 6640`), section, credits (also from a line like `3 Credit Hours`), instructor (`Instructor:`, `Professor:`, `Professors:`), and meeting pattern (also from a line like `Tuesday 6:00-9:00 pm`). Anything Chalk can't find is left blank for you to fill in on the Review tab.
- **Word:** a schedule table whose first column has labels like `Week 1 (8/24)` or `Week 1 (Jan. 6)` (text after the label is fine), with break rows like `Fall Break (10/10 - 10/18)`. The schedule can be split across several tables (one per module), as long as the week numbers continue from table to table; title and header rows are skipped. A column headed like `Assignment Due` is read as assignments. Rollover keeps each label's date style (`Jan. 6` stays a month name).
- **Markdown:** a table with header `| Week | Dates | Topic | Major Work |`, dates like `8/24 - 8/30`, and break rows with `-` as the week.
- Optional: a "Learning Objectives" (or "Course Outcome and Objectives") heading followed by the objectives, up to the next heading (a Word heading style or an ALL-CAPS line); a lead-in like "By the end of this course, you will be able to:" is skipped. A grading table: one with a `Weight` (or `%`) or `Points` column, or a two-column table of percentages or points (`250 pts`) with no header row. Points become each item's share of the `Total` row's points, or of all the rows' points when there's no `Total` row; a `Total` row is never listed as an assessment. A table with `Event` and `Date` columns for university dates.
- **PDF:** see below.

**PDF syllabi.** Chalk reads the PDF once into a Word file, `source/<name> (from PDF).docx`, and works from that: Review, Generate, Export, and rollover all behave as for a Word upload, and a rollover gives you an editable `outputs/syllabus.docx`. You can download the Word file from the Upload tab right after extracting. Rollover also writes `outputs/syllabus.pdf`, a copy of your PDF with only the dates and term changed, so it looks exactly like the original (the uploaded PDF is kept in `source/original/` for this). The new dates are drawn in the PDF's own font; if that font lacks a character the new text needs (a syllabus with no capital F can't spell "Fall" in it), that piece uses the closest standard font. There's no PDF copy when the course's weeks or breaks are added, removed, or change places, since a PDF can't move rows, or when Chalk can't change every date exactly; the rollover preview or a note says so, and the Word file has the full rollover. Two ways to read the PDF:

- **Read it on this computer** (the default). Free, and nothing leaves your computer. Works when the schedule is a table with ruled lines and `Week N (date)` labels, like the Word layout above; a schedule that runs across pages is joined back up. Takes a few seconds per page.
- **Read it with AI.** Uses your AI provider, so it needs one set up (section 8). For layouts the first option can't follow, such as a schedule that isn't a table. It sends the syllabus text to your provider and costs a few cents per page (the app shows an estimate for your model, and the actual cost afterwards; it counts toward the project's AI cost). The result can differ slightly from one run to the next.

Either way, check the Review tab: a line that wrapped at a page break may be joined to, or split from, the line above. Scanned PDFs (pictures of pages) have no text to read; save the original document as Word or as a text PDF instead. Exporting to Word yourself (Google Docs: File → Download → Microsoft Word) is still a good option, and keeps your original formatting.

## 7. Updating the academic calendar

Calendar data lives in `data/calendars.json` inside each project. The toolkit's master copy is `resources/data/calendars.json`, which new projects copy from. It covers University of Utah terms through the 2029–2030 academic year. To add a term, open the file in any text editor, copy the last term block, paste it after (mind the comma between blocks), and update the values from [registrar.utah.edu/academic-calendars](https://registrar.utah.edu/academic-calendars/):

```json
{
  "term": "Fall 2030",
  "start": "2030-08-26",
  "end": "2030-12-12",
  "verified_against": "https://registrar.utah.edu/academic-calendars/",
  "verified_date": "2029-06-01",
  "no_class_dates": [
    { "label": "Labor Day", "date": "2030-09-02" },
    { "label": "Fall Break", "date_start": "2030-10-12", "date_end": "2030-10-20" }
  ]
}
```

(Dates above are illustrative.) Single-day holidays use `date`, and multi-day breaks use `date_start` and `date_end`. Break labels should match how your syllabus names them (e.g. "Fall Break") so rollover can move those rows. When rolling into a different season (e.g. Fall → Spring), the syllabus's break rows are replaced with the target term's own breaks that fall within the course, and the preview says what was removed and added. No code changes are needed. For a term that isn't in the file, rollover asks for the first day of classes instead.

## 8. Choosing and configuring your AI provider

The app's first-run screen and Settings tab save these values for you, once for every course, in this computer's password store. To give one course different settings by hand, put all four in that project's `.env` file (start from `.env.example`); a complete `.env` overrides the saved provider for that course.

### 8a. OpenAI (default)

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

### 8b. Anthropic Claude

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

### 8c. University-hosted local model (Ollama)

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

### 8d. Google Gemini

```
Get your key at aistudio.google.com under "Get API key".
Gemini is NOT sanctioned by the University of Utah. Like Anthropic,
it has no university data agreement: use it only for course materials
(syllabi, your own source files), never for student work. Any future
feature that sends student data applies the same privacy rules to
Gemini as to every other unapproved provider.
Faculty use a personal API key and pay their own usage costs.

  LLM_PROVIDER=gemini
  LLM_API_KEY=AIza...
  LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
  LLM_MODEL=gemini-3.5-flash-lite

Cost: gemini-3.5-flash-lite is among the cheapest hosted options;
gemini-3.5-flash costs a little less than GPT-4o.
Chalk uses Google's OpenAI-compatible endpoint, so no extra
package is needed.
```

**Cost rates.** Costs are calculated from the per-1,000-token rates in each project's `config.json` under `cost_rates`. When a provider changes its prices, edit the numbers there. The app's model dropdown lists exactly the models that have a rate. If you set a model by hand that has no rate, its cost is shown as "unknown" rather than $0.

## 9. Customizing prompt templates

Each project has a `prompts/` folder with one plain-text template per content type: `quiz.txt`, `discussion.txt`, `rubric.txt`, `summary.txt`, `slides.txt`. Edit them in any text editor to change tone, structure, or emphasis. No Python is involved.

Words in `{curly braces}` are filled in automatically. Each template must keep its required placeholders. If one is removed, Chalk refuses to generate and names the missing placeholder and the file.

| Template | Required placeholders |
|---|---|
| all | `{course_title}`, `{learning_objectives}`, `{source_material_context}` |
| quiz | `{week_number}`, `{topics}`, `{question_count}`, `{format}` |
| discussion | `{week_number}`, `{topics}`, `{prompt_count}` |
| rubric | `{assignment_name}`, `{assignment_description}`, `{total_points}` |
| summary | `{week_number}`, `{topics}` |
| slides | `{week_number}`, `{topics}`, `{slide_notes}` |

Two placeholders are optional: `{course_level_guidance}` (every template) and `{ai_component_guidance}` (the assignment template) mark where the course-level and AI-use instructions go. Templates from before they existed still work: Chalk adds those instructions at the end of the prompt instead.

Other braces, such as Pandoc's `{.columns}`, are left alone. If a project's template file is deleted, the toolkit's default (in `resources/prompts/`) is used.

## 10. Forking and customizing the repo

### 10a. How to fork on GitHub

Click **Fork** on the repository page to get your own copy, then clone it as in section 2b. Pull upstream changes with `git remote add upstream https://github.com/atgko/chalk.git` and `git pull upstream master`.

### 10b. Changing the institution or calendar data

- Replace `resources/data/calendars.json` with your institution's terms (same shape as section 7), and update `institution` and `calendar_source` in `resources/config.json`. New projects pick these up. Existing projects keep their own copies.
- Renaming the tool: change `PROJECT_NAME` in `chalk/branding.py`. The app title, CLI help, and Canvas HTML comment all use it. Update this README's heading by hand.

### 10c. Adding a new output type

1. Add a `ContentSpec` to `chalk/generation/specs.py` (key, label, output folder, required placeholders, max tokens).
2. Add `resources/prompts/<key>.txt` containing those placeholders.
3. If it needs inputs beyond a week number, add them to `GenerationRequest` and `_type_variables` in `chalk/generation/engine.py`, the Generate tab (`ui/generate_view.py`), and the `generate` command (`chalk/cli.py`).

**Developing.** Install dev tools with `pip install -r requirements-dev.txt` and run `pytest`. The suite (including Streamlit UI tests) enforces 80% coverage. All logic lives in the `chalk` package; `ui/` and `chalk/cli.py` are thin layers over `chalk/pipeline.py` and `chalk/generation/`. See `DECISIONS.md` for design decisions and `PLAN.md` for the build plan.

## 11. FAQ and error reference

### Syllabus extraction

**"No schedule table found. Make sure your syllabus has a table with 'Week' (or a numbered 'Meeting' column) in the first column, then try again."**
Chalk looks for a table with "Week" in the first column: labels like `Week 1 (8/24)` in Word, or a `| Week | Dates | ... |` header in markdown. A Word or PDF schedule with no dates works too, if its first column is headed Week, Meeting, Session, Module, Class, Lesson, or Unit and numbered 1, 2, 3; the Review tab then asks for the date of the first class. If your schedule is in a different format, reformat it as a standard table and re-upload.

**"This syllabus's schedule has no dates" on the Review tab**
The schedule numbers its weeks or meetings without dates. Chalk dated them one week apart from the term's first day of classes (the first day the class meets, if the syllabus says), skipping multi-day breaks like Fall Break. Change **Week 1 date** if the course starts later, e.g. in the second session, and the other weeks follow.

**"Multiple possible schedule tables were found. Choose the correct one below."**
More than one table looks like a schedule. Each option shows its first rows. Pick the real schedule. If you see "That table choice is no longer valid", upload the syllabus again.

**The term label mismatch warning appeared. What do I do?**
Check whether the term label or the schedule dates are wrong, and fix whichever is incorrect. The check exists because it's easy to update the label and forget the table, or vice versa. If you're sure both are right, choose Continue anyway.

**"This Word file is protected. Remove the password in Word (Review > Protect Document) and re-upload."**
Chalk can't open password-protected or damaged Word files. Remove the protection in Word, save, and upload again.

**"Could not find the term (for example 'Fall 2026') near the top of the syllabus."**
Add a line like `Term: Fall 2026` near the top, or put the term in the title line. See "What Chalk expects in a syllabus" in section 6.

**"Could not determine the academic year from the term '…'."**
The `Term:` line needs a four-digit year, e.g. `Term: Fall 2026`.

**"Could not determine the dates for the break row …" / "Could not determine the date for week N …"**
Break rows need a date range such as `Fall Break (10/10 - 10/18)` (Word) or `10/10 - 10/18` in the Dates column (markdown). Week rows need dates like `8/24 - 8/30`.

**"Could not read '…' as a week number in the schedule table."**
In a markdown schedule, the Week column must hold a number, or `-` for a break row.

**"The schedule table was found but contains no week rows."**
Add at least one week row below the table's header.

**"This file doesn't look like a plain-text markdown file."**
Save the `.md` file as UTF-8 text. Most editors have this under "Save with encoding".

**"Unsupported file type '…'. Upload a .docx, .md, or .pdf syllabus."**
Only Word (`.docx`), markdown (`.md`), and PDF syllabi can be extracted. Save a `.doc` syllabus as `.docx` first.

**"This PDF has no text Chalk can read — it's probably a scanned image."**
The PDF is pictures of pages. Open the original document and save it as Word, or as a PDF with text.

**"Chalk couldn't open this PDF."**
It's password-protected or damaged. Save a copy without the password, or save the original as Word.

**"No schedule table found…" after reading a PDF on this computer**
The schedule isn't a ruled table Chalk can follow. The message suggests **Read it with AI** if you haven't tried it on this PDF; otherwise save the PDF as Word and fix the table there.

**"The AI's reading of this PDF didn't come back in a form Chalk can use."**
The AI's answer wasn't usable. Trying again often works. The message suggests **Read it on this computer** only if you haven't tried it on this PDF. Either way, the read's cost is counted.

**"This syllabus is too long for the AI to read in one go…"**
The AI's reply hit its length limit and was cut off. Choose **Read it on this computer**, or save the original as Word and upload that.

**"Chalk couldn't read this PDF either way."**
Both ways of reading this PDF failed. Open the original document (Word, Google Docs, Pages) and save it as .docx, then upload that. Chalk reads Word files most reliably.

**"The AI couldn't find a week-by-week schedule in this PDF."**
Check that the syllabus has a schedule. If it does, save it as Word and upload that.

**"course.json couldn't be read — it may have been edited by hand."**
A hand edit broke the file's format. Restore the previous version from `.archive/`, or re-extract the syllabus.

### Rollover

**"That term isn't in the calendar data yet. Enter the first day of classes below and we'll calculate the rest."**
The term isn't in `data/calendars.json`. Enter the first day of classes and rollover works normally, or add the term to the calendar (section 7).

**My course runs 12 weeks, not 10. How do I change it?**
Change `Duration (weeks)` on the Review tab (then Confirm and save) or on the Rollover tab, or edit `duration_weeks` in `course.json`. Rollover uses the value you set, adds or drops weeks, and flags the change.

**"The course has N weeks in the schedule but duration_weeks says M…"**
This is a flag in the rollover preview, not an error. You (or a hand edit) set a course length different from the schedule, so rollover will add or drop weeks. Check them before confirming.

**The dates look wrong after rollover.**
The preview shows every change before anything is written. If you already confirmed and the result is wrong, the previous versions are in `outputs/.archive/` (and `.archive/` for `course.json`) with timestamps. Copy them back to restore.

**"The original syllabus (…) is missing, so the rolled-over copy can't be written."**
Rollover edits a copy of the syllabus you extracted, which lives in `source/`. If it was deleted or moved, extract the syllabus again.

### AI provider

**"The OpenAI API key was not accepted. Check it at platform.openai.com and try again."**
Also: **My OpenAI key works in ChatGPT but the tool says it is invalid.** ChatGPT and the OpenAI API use separate credentials. Create an API key at platform.openai.com under "API keys". This is different from your ChatGPT login.

**"The Anthropic API key was not accepted. Check it at console.anthropic.com and try again."**
Create or copy a key at console.anthropic.com under API keys and enter it in Settings.

**I want to use Anthropic Claude instead. How do I switch?**
In the app: Settings → Anthropic Claude → paste your key → choose a model → Test connection and save. By hand: in `.env`, set `LLM_PROVIDER=anthropic`, `LLM_API_KEY=<your key>`, `LLM_BASE_URL=` (blank), and `LLM_MODEL=claude-sonnet-5`.

**"The Gemini API key was not accepted. Check it at aistudio.google.com and try again."**
Create a key in Google AI Studio and enter it in Settings. Keys usually start with `AIza`.

**"… refused this request (error 403) …"**
The provider recognized the key but won't run the request. Usually the key is restricted, the project doesn't allow the chosen model, or the service isn't offered in your region or network (try without a VPN). The "Provider said:" part gives the exact reason.

**"Your OpenAI account has no API credits…"**
API use is billed separately from a ChatGPT subscription. Add credits at platform.openai.com under Billing.

**"Could not reach the LLM provider. Check your connection. Extraction and rollover work without a connection."**
No internet, or the provider is down. Everything except generation still works.

**"Could not reach the local model at … Check that Ollama is running and the URL in your .env is correct."**
Make sure the Ollama server is running and reachable from your computer, and that `LLM_BASE_URL` ends in `/v1`.

**"The LLM provider is temporarily unavailable after several attempts."**
The provider was rate-limiting or timing out. Chalk already retried. Wait a minute and try again.

**"Unexpected error from LLM provider: …"**
Usually a model name the provider doesn't recognize, or a request it rejected. Check `LLM_MODEL` in Settings.

**"No LLM provider is configured…" (CLI) / "Connect an AI provider in the Settings tab to generate content." (app)**
Set up a provider (section 8). Extraction, rollover, and export don't need one.

**"Paste your … API key to continue." / "Choose a model to continue."**
The Settings form needs both a key and a model for OpenAI and Anthropic.

**The cost says "unknown (no cost rate for this model in config.json)".**
The model you're using has no entry under `cost_rates` in `config.json`. Add one (per-1,000-token input and output prices) to track its cost.

### Content generation

**"A [type] already exists for Week [N]. Generating a new one will archive the old version. Continue?"**
Confirm to generate a replacement. The old draft moves to `.archive/` and isn't lost.

**"The prompt template … is missing {…}. Add it back where that information should go, then try again."**
An edited template lost a required placeholder (see the table in section 9). Put it back, or delete the project's copy to use the default.

**"The prompt template … couldn't be read."**
Save the template as UTF-8 plain text.

**"A rubric needs an assignment name and a description of the assignment."**
Enter both, or upload the assignment description as a file.

**"Week N isn't in this course's schedule."**
Choose a week that exists in `course.json`.

**"These source files aren't in this project's source/ folder: …"**
With `--source`, give file names that are in `source/`. Add new files with `toolkit.py add` first.

**"'…' can't be added. Supported source files: .pdf, .docx, .md, .txt."**
Convert the file to one of those types first.

### Projects

**"'…' isn't a Chalk course project (no config.json)."**
Point at the project folder itself (the one containing `course.json` and `config.json`), or create a new project.

**"There's already a course project named … in …"**
You tried to create a project that already exists. Click **Open …** to open it, or choose another name. Chalk never overwrites a project: to start over, rename or delete that folder first.

**"A folder named '…' already exists here and isn't empty. Pick another name."** / **"'…' isn't a usable project name."**
Choose a new name without slashes, like `IS-6640-Fall-2027`.

**"Upload and extract a syllabus first…"**
Rollover, Generate, Export, and Metrics need a saved `course.json`. Start on the Upload tab.

**"Something unexpected went wrong (…)."**
A bug. Your files were not changed. The terminal window running the app has the details. Please report them.

## 12. Data and privacy

- **Everything stays local.** Projects, syllabi, outputs, and the metrics log live in folders on your computer. There is no Chalk server, account, or telemetry, and Streamlit's own anonymous usage statistics are switched off (`.streamlit/config.toml`).
- **What goes to the AI provider:** only when you click Generate (or run `generate`), and only the filled-in prompt. That prompt contains the course title, learning objectives, the chosen week's topics, your options, and the text of the source materials you selected. With the Ollama option, nothing leaves the university network. Nothing is sent during extraction, rollover, or export, with two exceptions you choose: reading a PDF syllabus with **Read it with AI** sends the syllabus's full text, and lengthening a course during rollover with "Draft topics for the added weeks with AI" ticked sends the recent weeks' topics. Reading a PDF on this computer (the default) sends nothing.
- **Your API key** is stored in your operating system's password store (Windows Credential Manager or the macOS Keychain), encrypted under your login, not in a file. If the store isn't available, or you set a key by hand, it goes in the project's `.env` instead, which the repo's and each project's `.gitignore` keep out of git. Never share or commit it. To remove the saved key, delete the **Chalk** entry in Windows Credential Manager (Windows credentials) or Keychain Access.
- **FERPA: course materials only.** Never upload student work, grades, rosters, emails, or anything that identifies a student. Chalk is designed for syllabi and instructor-authored materials, the app says so wherever files are uploaded, and every prompt template instructs the model not to request or invent student information.
- **The metrics log** (`eval-log.json`) records counts, token usage, costs, file names, and timestamps, never the content of your syllabus or generated drafts.
- **Grading:** Chalk drafts rubrics only. It never grades or evaluates student work (CTE policy).
- **Review everything.** Every generated file is labeled as an AI draft. You are responsible for its accuracy before sharing it with students.
