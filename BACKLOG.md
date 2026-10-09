# Backlog

A running list of known gaps, open questions, and follow-ups. Add new items at the bottom of the right section; move an item to **Done** with the date and commit when it's resolved. Priorities: **P1** = likely to trip up a real instructor soon, **P2** = real but rarer or has a workaround, **P3** = polish.

Last updated: 2026-10-08 @ 9:00 AM MST.

## Open questions (need someone outside the code)

- **P1: Get the Word (.docx) version of the OSC 6660 syllabus.** We only have the PDF. The module-table support was built against a synthetic look-alike reconstructed from the PDF's text (`chalk/demo_content.py`), so the real table structure (merged title rows, where the focus text sits, soft line breaks) is unverified.
- **P1: Confirm the "16-week syllabus showed 10 weeks" report.** Most likely cause: the new syllabus was extracted into the demo project but not yet saved, so the Rollover tab still showed the saved 10-week demo course. The app now warns about this. Ask the teammate whether they clicked Confirm and save first.
- **P2: Collect more real syllabi.** Only two real syllabi have been tested (IS 6640, OSC 6660). PLAN.md's Section 15 test corpus (before the Nov 8 readiness meeting) is the place to find new layouts. Keep them in the git-ignored `reference/` folder, since the repo is public.

## AI providers and student data (sponsor discussion, Oct 5)

Raised at the Oct 5 sponsor meeting. Nothing student-related is sent to an AI today (only syllabi and the instructor's own source materials), so these are prerequisites for a future grading feature, not current gaps. Next step: a discussion within the team, then with the sponsor.

- **P1: Confirm which AI providers are approved for student work.** The University of Utah currently sanctions only ChatGPT. Grading could be built on it if licensing is approved; other frontier providers don't have that approval.
  - "Sanctioned ChatGPT" most likely means the U's licensed ChatGPT Edu workspace, which runs under a university contract. Chalk calls the OpenAI API with an individual's key, and that contract doesn't automatically cover it.
  - "APIs don't store data" isn't quite right. OpenAI's and Anthropic's APIs don't train on API data by default, but both keep requests for a period (typically up to ~30 days, for abuse monitoring). Zero-data-retention is a separate agreement. Check each provider's current terms before relying on this.
  - Student work is an education record under FERPA, so the deciding question is contractual, not technical: which services have a data agreement with the university. The U's IT/privacy office owns that answer.
  - Question to bring to the sponsor: "Which AI services and contract terms are approved for student work, and can Chalk use them through an API?"
- **P2: Privacy guardrails before any text is sent to an AI.** If student data ever leaves the computer, enforce protection in code, configured on the Settings page.
  - Classify each provider in Settings: university-approved, not approved (public), or local (a model running on the instructor's computer, so nothing leaves it). Google Gemini (added Oct 7) and Anthropic are "not approved" today and get the same rules.
  - Block, or redact before sending, any student information going to a provider that isn't approved.
  - Names: exact-match against an uploaded Canvas roster. This is far more reliable than guessing which words are names.
  - IDs and contact details: strip uNIDs (`u` + 7 digits) and email addresses with pattern matching.
  - Log what was redacted (counts only, never the content) in the existing metadata-only eval log, so the evaluation report can show the guardrail working.
- **P3: Grading feature (blocked on the two items above).** Scope it only once a provider is approved: e.g. rubric-based draft feedback that the instructor reviews, never a final grade.
- **P2: Find the most token-efficient way to grade.** Token cost is a main concern for the department, so compare approaches before building: grade each rubric criterion separately or all at once; send only the relevant parts of a submission; use a smaller model (e.g. `gpt-4o-mini`) for a first pass and a larger one only for borderline cases; reuse the fixed rubric and instructions across submissions with prompt caching or batch APIs where the provider offers them. Measure the cost per submission with the existing cost tracking (Metrics tab) and set a target.
- **P1: Try Gemini with a real API key.** Gemini is built (Settings → Google Gemini) but only tested with simulated replies. With a key from aistudio.google.com, run Test connection and one generation of each type; check the answers aren't cut short (Gemini 3 models "think", and that counts against Chalk's token limits; Chalk asks for low thinking) and compare the recorded cost with Google's billing page.
- **Gemini is NOT sanctioned by the University of Utah.** It has no university data agreement, so it's for course materials only (syllabi, the instructor's own files), never student work. The provider form and README say so, and any student-data feature must apply the privacy guardrails above to it like every other unapproved provider.
- **P2: Let instructors choose any model, and keep the model list from going stale.** Today the dropdown only lists the models that have a cost rate in `config.json` (e.g. `gpt-4o`, `claude-sonnet-5`, `gemini-3.5-flash`), so when a provider releases a better model or retires one, Chalk lags until someone edits the file. Ideas to compare:
  - An "Other model…" choice where the instructor types any model name. Test connection already proves it works; its cost would show as "unknown" unless they also enter a rate.
  - Ask the provider for its current model list (OpenAI, Anthropic, and Gemini all have a list-models API) when the key is tested, and offer those.
  - Keep the bundled rates current: review `resources/config.json` each term, with a "prices last checked" date in the file. Gemini's were checked 2026-10-07.
  - When a saved model is retired, the new 404 message already says to choose another one in Settings; a startup check could warn sooner.

## Extraction

- **P1: Try the AI PDF reader against a real provider.** It's only been tested with canned replies. Run OSC 6660 through it with Claude and OpenAI; check the weeks come through and record the real cost per page (the hint assumes ~800 tokens in / ~1,200 out per page).
- **P2: Test the local PDF reader on more real PDFs.** Only OSC 6660 has been tried. Watch for schedules without ruling lines (pdfplumber can't see them as tables; the AI reader is the fallback), two-column page layouts, and Google Docs exports.
- **P2: Rows cut at a page break are rejoined by a guess.** The first paragraph carried onto the next page is joined to the one above unless that ended a sentence. A complete line like "Project Artifact #2A: Scope Plan" followed by a new item on the next page would be wrongly joined. Keeping the previous page's line positions would make this exact.
- **P3: Scanned PDFs (OCR).** Out of scope; Chalk explains and suggests saving as Word.
- **P3: A sample PDF in the demo course** so teammates can try the PDF path without their own syllabus. Needs a small PDF writer (the tests hand-build theirs in `tests/fixtures/pdf_layout_builder.py`).
- **P2: Markdown has none of the Word path's new tolerance.** No month-name dates, no split tables, no extra columns. Markdown is Chalk's own format, so this matters less, but the README should keep saying so.
- **P3: A Spring syllabus with a December row** (e.g. an orientation "Week 0 (12/15)") still gets the term's year for that row. Rows only move forward a year when the schedule crosses New Year after them.
- **P3: Points-based grading tables** ("Labs — 250 pts") aren't recognized; only percentages are.
- **P3: Title guesses can include the modality**, e.g. "Networking and Servers – Online". This is editable on Review.
- **P3: Meeting pattern stays blank when it's only in a labeled line like "Time:"**. That's deliberate (in IS 6640, "Time:" is the webinar, not the class).
- **P3: The objectives list stops at any short ALL-CAPS line**, so an objective written in all caps would end it early.

## Rollover

- **P3: Changing the length of a split (per-module) Word schedule.** Added weeks go after the last week of the last module table; dropped weeks can leave a module table with only its title and header rows. Untested on a real split schedule.
- **P2: Numbered break weeks are only flagged.** In "Week 10 — Spring Break", Week 10 rolls over as an ordinary week with a flag. It isn't turned into a break row or moved.
- **P3: Break rows in a split (per-module) schedule** are placed by date across all the tables; a break after the last week goes at the end of the last table. This is untested on a real split schedule that has break rows.
- **P3: When the instructor picked one table from an ambiguous set, the writer still updates every schedule-like table.**
- **P3: The preview always shows dates as M/D**, even when the syllabus uses "Jan. 6" (the written document keeps the original style).

## App / UX

- **P2: Course details edited on Review aren't written back into the syllabus document**, only into `course.json` and the course brief.
- **P3: The unsaved-extraction warning appears on Rollover, Generate, and Export, but not Metrics** (Metrics doesn't depend on the course).

## Generation

- **P2: Use the assignment generator's formatting for the other documents** (quizzes, discussion prompts, rubrics, summaries) so all generated files look consistent. The assignment generator is merged (PR #1).
- **P2: A tab for saved generated files.** Generated files are written to the project's output folders (older versions go to `.archive/`), but the app has no place to browse, open, or download them. The tab should list them by type and week.
- **P2: Choose how many quiz questions are multiple choice vs. long form when the format is "mixed".** Today "mixed" only passes the total count and the word "mixed" to the prompt, so the model decides the split. Add two counts (shown only for "mixed") to `GenerationRequest` and the quiz prompt, and check they add up to the total.

## Engineering

- **P1: Before the presentation, turn off raw provider error text.** `_SHOW_PROVIDER_DETAILS` in `chalk/llm_client.py` adds the provider's own explanation (e.g. "Provider said: …") to refused-request errors, to debug teammates' setup problems. Set it to `False` for the presentation, so only the plain-English messages show.
- **P2: Lint debt.** `ruff check` reports about 30 existing findings (mostly UP017 `datetime.UTC`, DTZ, ISC004) because the selected rules are stricter than the code. Either fix them in one pass or relax the config, then add a `ruff check` step to `.github/workflows/tests.yml`.

## Done

- 2026-10-09: Browse… buttons next to "Project folder" and "Create it inside" open the system folder dialog and fill in the field (hidden if this Python has no Tk).
- 2026-10-09: The launch screen no longer fades while you type: Open and Create read their fields on click (or Enter), show a "Creating…/Opening…" spinner, and confirm on the next screen. An empty field gets a plain message instead of a greyed-out button.
- 2026-10-09: GitHub Actions runs the tests on every pull request (Windows, macOS, and Linux on Python 3.11), and a PR template asks for a test plan. Team workflow is in CONTRIBUTING.md.
- 2026-10-09: A University Dates deadline that names a break (e.g. "Last day before Fall Break") keeps its single date instead of taking the break's dates.
- 2026-10-09: The teammate's assignment creator and enhancer is merged (PR #1).
- 2026-10-08: The rollover flag helpers moved from `chalk/rollover/preview.py` (now ~515 lines) to `chalk/rollover/flags.py`.
- 2026-10-08: Season-change rollovers replace single-day holidays in the University Dates table (Labor Day becomes Martin Luther King Jr. Day in a Fall → Spring rollover) and flag any target-term holiday left without a row. Every rollover now takes a holiday's date from the calendar by name, and "Independence Day" is no longer read as the end of term.
- 2026-10-08: A successful extraction opens the Review tab (also after picking a schedule table or clicking Continue anyway). A failed extraction, or a term/schedule warning still to resolve, stays on Upload.
- 2026-10-07: Google Gemini as a fourth provider (through Google's OpenAI-compatible endpoint, no new package); labeled as not university-approved. Older projects pick up new providers' cost rates automatically.
- 2026-10-07: Word rollover with a changed course length adds rows for new weeks (a copy of the last week's row, with placeholder or AI-drafted topics) and removes rows for dropped weeks.
- 2026-10-07: Review and the CLI warn when assessment weights don't add up to 100%.
- 2026-10-07: Schedules that cross New Year (e.g. a January finals week in a Fall syllabus) get the next year for the later dates.
- 2026-10-07: A Discard button on Review drops an unsaved extraction.
- 2026-10-07: Clearer provider errors: an OpenAI account with no API credits is no longer retried and reported as "temporarily unavailable"; 403 and 404 errors explain the likely causes (restricted key, blocked model or region, unknown model) and, for now, show the provider's own message.
- 2026-10-05: Rollover asks which days the class meets (holiday warnings only on class days) and lets the instructor switch off breaks the class meets through.
- 2026-10-01: PDF syllabi: read on this computer (pdfplumber) or with AI, converted to a Word file that the existing Word path extracts and rolls over.
- 2026-09-30: Season-change rollovers rebuild break rows from the target calendar (Spring rollovers no longer say "Fall Break").
- 2026-09-30: Loose front-matter extraction (only the term required; details editable on Review).
- 2026-09-30: Word schedules: month-name dates, module tables, Assignment Due column, text after labels; objectives and grading-table detection loosened; unsaved-extraction warning.
