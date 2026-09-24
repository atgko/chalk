# Chalk

Chalk keeps a university course syllabus current from term to term and drafts course materials from it. Upload a Word or markdown syllabus, and Chalk reads the schedule, rolls every date forward to a new term (flagging anything a human should check), and produces a Canvas-ready schedule and a one-page course brief. With an AI provider connected, it also drafts quizzes, discussion prompts, rubrics, module summaries, and slide outlines, always as clearly-labeled drafts for you to review.

Everything runs on your own computer. Your files never leave it, except for the text sent to the AI provider you choose when you generate content.

**New to the project? [GETTING-STARTED.md](GETTING-STARTED.md)** walks you through running the demo on your own computer, step by step.

---

## Contents

1. [What this tool does](#1-what-this-tool-does)
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
| **Syllabus extraction** | Reads your syllabus into `course.json`: course details, learning objectives, grading weights, and the week-by-week schedule. Checks that the term label matches the Week 1 date. | No |
| **Semester rollover** | Shifts every date to a new term, inserts that term's breaks, and shows a full preview with flags before anything is written. | No* |
| **Canvas HTML** | A schedule table you paste into Canvas's HTML editor. | No |
| **Course brief** | A one-page overview of the course, rebuilt automatically after every extraction and rollover. | No |
| **Content drafts** | Quizzes, discussion prompts, rubrics, module summaries, slide outlines. | Yes |
| **Metrics** | Cost, rollover history, consistency-check catches, extraction errors, plus a downloadable evaluation report. | No |

\*Only if you lengthen a course during rollover and ask the AI to draft topics for the new weeks. Without a provider, those weeks are added as clearly marked placeholders.

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
- **Your own course:** on the launch screen, type a name (for example `IS-6640-Fall-2027`) and click **Create project**. Projects are saved in the `projects/` folder next to the launchers. To reopen one, paste its folder path under **Open a course project**.
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

The app has seven tabs. Rollover, Generate, Export, and Metrics unlock once a course has been extracted and saved.

**Upload.** Choose your `.docx` or `.md` syllabus and click **Extract course**. If the term label doesn't match the Week 1 date (for example, "Spring 2026" with an August Week 1), you'll see a warning. Fix the syllabus and re-upload, or click **Continue anyway**. The override is recorded in the metrics log. If the document has more than one table that looks like a schedule, you'll be asked to pick the right one.

**Review.** Check what was extracted: course details, learning objectives, grading weights, and every week. `Duration (weeks)` is editable. Change it here to lengthen or shorten the course at the next rollover. Click **Confirm and save** to write `course.json` and the course brief. Nothing is saved until you do.

**Rollover.** Pick the target term. It defaults to the same season next year. For a term that isn't in the calendar data, choose **Another term** and enter the first day of classes. Click **Preview rollover** to see every week's old and new date, plus flags for anything to check by hand: a week landing on a holiday or break, a changed course length, or (markdown syllabi) due dates near the daylight-saving change. Click **Confirm rollover** to write the files. Previous versions are archived, never overwritten.

**Generate.** Choose a content type and week (or, for a rubric, the assignment name and description), then any source materials to ground the draft in. The estimated maximum cost is shown before you click **Generate**. The draft appears for review. **Save** writes it to `outputs/`, **Regenerate** makes a new call (after asking), and **Discard** throws it away. If a draft already exists for that week, you'll be asked before it's replaced (the old one is archived).

**Export.** Download any output file, or everything as a zip. The Canvas HTML is shown in a box with a copy button. **Regenerate Canvas HTML and course brief** rebuilds both from the current `course.json`.

**Metrics.** Total AI cost, rollovers, consistency-check catches, extraction errors, generations by type, and rollover history. **Download evaluation report** produces a markdown summary for reporting.

**Settings.** Change your AI provider, model, or API key. Every change is tested with a short call before it's saved.

The footer always shows the active provider and the project's AI cost to date.

## 4. Command-line reference

Everything the app does is also available from a terminal, which is useful for scripting or working without a browser. Run commands from the repo folder with the virtual environment active. Every command except `init` takes `--project <folder>` (default: the current folder).

```bash
python toolkit.py init --name "IS-6640-Fall-2027" [--dir <parent folder>]
python toolkit.py extract path/to/syllabus.docx --project IS-6640-Fall-2027 [--continue-anyway]
python toolkit.py rollover --term "Fall 2027" --project IS-6640-Fall-2027 [--weeks 12] [--week1-date 2027-08-23] [--no-llm] [--yes]
python toolkit.py export --project IS-6640-Fall-2027
python toolkit.py add path/to/chapter-3-summary.pdf --project IS-6640-Fall-2027
python toolkit.py generate quiz --week 3 --project IS-6640-Fall-2027 [--count 5] [--format mixed] [--source chapter-3-summary.pdf]
python toolkit.py generate discussion --week 3 [--count 3]
python toolkit.py generate summary --week 3
python toolkit.py generate slides --week 3 [--notes "bullet points or an excerpt"]
python toolkit.py generate rubric --assignment "Lab 3" --description-file lab3.docx [--points 100]
python toolkit.py report --project IS-6640-Fall-2027
python toolkit.py demo [--reset]
python toolkit.py status --project IS-6640-Fall-2027
```

- `extract` asks before saving past a failed term/Week-1 check. `--continue-anyway` skips the question, and the override is still logged.
- `rollover` prints the full preview and asks before writing. `--yes` skips the question. If the term isn't in the calendar, it asks for the first day of classes (or pass `--week1-date`).
- `generate` shows the estimated cost, asks before replacing an existing draft (`--yes` skips this), then saves the draft and prints tokens used and cost. `--source` can be repeated.
- `report` writes `outputs/evaluation-report.md`.
- Run `python toolkit.py <command> -h` for every option.

The CLI reads the project's `.env` for AI provider settings. Copy `.env.example` into the project folder as `.env` and fill it in (see section 8), or set it up once in the app's Settings tab.

## 5. Adding source materials

Source materials are your own summaries, notes, excerpts, and handouts that ground generated content in what you actually teach. Accepted types: PDF, DOCX, MD, TXT.

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
    canvas.html          Schedule table for Canvas's HTML editor
    course-brief.md      One-page course overview
    evaluation-report.md Metrics summary (from `report` or the Metrics tab)
    quizzes/  discussions/  rubrics/  summaries/  slides/
    .archive/            Every previous version, timestamped
  prompts/               Editable prompt templates
  data/calendars.json    Academic calendar data
  eval-log.json          Metrics log (one line per event; stays on this computer)
  README.md              A short guide to the folder
```

- **Word rollover** changes only the date inside each "Week N (M/DD)" label, the term line, break rows, and the university-dates table. Everything else in the document (formatting, other text, other tables) is untouched.
- **Markdown rollover** rewrites the schedule table and term line and leaves the rest of the file as it was.
- Rollover **never renumbers** quizzes, exams, or labs. If the course length changes, it flags this so you can check numbering yourself.
- **Every generated file starts with** `> **AI-generated draft** — review and edit before use. Generated <date> using <model>.` Slide decks carry the same line as a comment just below their title block, so it doesn't become a slide.
- **Slides** follow the IS 4490 pptx pipeline conventions (a YAML title block, `##` slide titles with `<!-- Slide N -->` comments, no `#` headings) and can be fed straight into `scripts/convert-slides-to-pptx.sh`.
- **Nothing is ever overwritten.** The previous version of any file (including `course.json`) is moved into a `.archive/` folder with a timestamp first. To restore one, copy it back and remove the timestamp from its name.

**What Chalk expects in a syllabus:**

- Near the top, one detail per line: `Course:`, `Course Number:`, `Section:`, `Credits:`, `Term:`, `Instructor:`, `Meeting Pattern:`.
- **Word:** a schedule table whose first column has labels like `Week 1 (8/24)`, with break rows like `Fall Break (10/10 - 10/18)`.
- **Markdown:** a table with header `| Week | Dates | Topic | Major Work |`, dates like `8/24 - 8/30`, and break rows with `-` as the week.
- Optional: a "Learning Objectives" (or "Course Outcome and Objectives") heading followed by a bulleted list; a table with `Assessment` and `Weight` columns (e.g. `25%`); a table with `Event` and `Date` columns for university dates.

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

(Dates above are illustrative.) Single-day holidays use `date`, and multi-day breaks use `date_start` and `date_end`. Break labels should match how your syllabus names them (e.g. "Fall Break") so rollover can move those rows. No code changes are needed. For a term that isn't in the file, rollover asks for the first day of classes instead.

## 8. Choosing and configuring your AI provider

The app's first-run screen and Settings tab write these values for you. To set them by hand, put them in the project's `.env` file (start from `.env.example`). Switching providers is only ever a `.env` change.

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

**"No schedule table found. Make sure your syllabus has a table with 'Week' in the first column, then try again."**
Chalk looks for a table with "Week" in the first column: labels like `Week 1 (8/24)` in Word, or a `| Week | Dates | ... |` header in markdown. If your schedule is in a different format, reformat it as a standard table and re-upload.

**"Multiple possible schedule tables were found. Choose the correct one below."**
More than one table looks like a schedule. Each option shows its first rows. Pick the real schedule. If you see "That table choice is no longer valid", upload the syllabus again.

**The term label mismatch warning appeared. What do I do?**
Check whether the term label or the schedule dates are wrong, and fix whichever is incorrect. The check exists because it's easy to update the label and forget the table, or vice versa. If you're sure both are right, choose Continue anyway.

**"This Word file is protected. Remove the password in Word (Review > Protect Document) and re-upload."**
Chalk can't open password-protected or damaged Word files. Remove the protection in Word, save, and upload again.

**"Could not find the following syllabus details near the top of the document: …"**
Each listed detail must be on its own line near the top, formatted like `Term: Fall 2026`. See "What Chalk expects in a syllabus" in section 6.

**"Could not determine the academic year from the term '…'."**
The `Term:` line needs a four-digit year, e.g. `Term: Fall 2026`.

**"Could not read 'Credits: …' as a whole number."**
Write credits as a number, e.g. `Credits: 3`.

**"Could not determine the dates for the break row …" / "Could not determine the date for week N …"**
Break rows need a date range such as `Fall Break (10/10 - 10/18)` (Word) or `10/10 - 10/18` in the Dates column (markdown). Week rows need dates like `8/24 - 8/30`.

**"Could not read '…' as a week number in the schedule table."**
In a markdown schedule, the Week column must hold a number, or `-` for a break row.

**"The schedule table was found but contains no week rows."**
Add at least one week row below the table's header.

**"This file doesn't look like a plain-text markdown file."**
Save the `.md` file as UTF-8 text. Most editors have this under "Save with encoding".

**"Unsupported file type '…'. Upload a .docx or .md syllabus."**
Only Word (`.docx`) and markdown (`.md`) syllabi can be extracted. Save a PDF or `.doc` syllabus as `.docx` first.

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

**"A folder named '…' already exists here and isn't empty. Pick another name."** / **"'…' isn't a usable project name."**
Choose a new name without slashes, like `IS-6640-Fall-2027`.

**"Upload and extract a syllabus first…"**
Rollover, Generate, Export, and Metrics need a saved `course.json`. Start on the Upload tab.

**"Something unexpected went wrong (…)."**
A bug. Your files were not changed. The terminal window running the app has the details. Please report them.

## 12. Data and privacy

- **Everything stays local.** Projects, syllabi, outputs, and the metrics log live in folders on your computer. There is no Chalk server, account, or telemetry, and Streamlit's own anonymous usage statistics are switched off (`.streamlit/config.toml`).
- **What goes to the AI provider:** only when you click Generate (or run `generate`), and only the filled-in prompt. That prompt contains the course title, learning objectives, the chosen week's topics, your options, and the text of the source materials you selected. With the Ollama option, nothing leaves the university network. Nothing is sent during extraction, rollover, or export, except that lengthening a course during rollover with "Draft topics for the added weeks with AI" ticked sends the recent weeks' topics.
- **Your API key** is stored only in the project's `.env` file. The repo's `.gitignore` and each project's `.gitignore` keep it out of git. Never share or commit it.
- **FERPA: course materials only.** Never upload student work, grades, rosters, emails, or anything that identifies a student. Chalk is designed for syllabi and instructor-authored materials, the app says so wherever files are uploaded, and every prompt template instructs the model not to request or invent student information.
- **The metrics log** (`eval-log.json`) records counts, token usage, costs, file names, and timestamps, never the content of your syllabus or generated drafts.
- **Grading:** Chalk drafts rubrics only. It never grades or evaluates student work (CTE policy).
- **Review everything.** Every generated file is labeled as an AI draft. You are responsible for its accuracy before sharing it with students.
