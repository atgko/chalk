# Backlog

A running list of known gaps, open questions, and follow-ups. Add new items at the bottom of the right section; move an item to **Done** with the date and commit when it's resolved. Priorities: **P1** = likely to trip up a real instructor soon, **P2** = real but rarer or has a workaround, **P3** = polish.

Last updated: 2026-10-26.

## Open questions (need someone outside the code)

- **P3: Get the Word (.docx) version of the OSC 6660 syllabus, if it turns up.** It may not be available (Oct 15); the faculty test syllabi (below) can cover module-table layouts instead. We only have the PDF. The module-table support was built against a synthetic look-alike reconstructed from the PDF's text (`chalk/demo_content.py`), so the real table structure (merged title rows, where the focus text sits, soft line breaks) is unverified.
- **P1: Confirm the "16-week syllabus showed 10 weeks" report.** Most likely cause: the new syllabus was extracted into the demo project but not yet saved, so the Rollover tab still showed the saved 10-week demo course. The app now warns about this. Ask the teammate whether they clicked Confirm and save first.
- **P1: Collect more real syllabi.** Only two real syllabi have been tested (IS 6640, OSC 6660). As of Oct 15, the team is collecting more from faculty, who will also try Chalk themselves. The PRD's Section 15 test corpus (before the Nov 8 readiness meeting) lists what's still missing: a markdown syllabus with the DST boundary, the IS 6640 Spring copy with the term-label bug, and a 12- or 16-week course. Run each through extraction and rollover, then `toolkit.py report`, for the December evidence. Keep them in the git-ignored `reference/` folder, since the repo is public.
- **P2: Confirm the session dates with a program that uses sessions.** The registrar publishes no session dates, so Chalk assumes three 5-week sessions counted in class weeks around Fall/Spring Break (Fall 2026: Aug 24, Sep 28, Nov 9), and 10- or 12-week summer courses (DECISIONS.md, Oct 21). If a program has its own session calendar, `session_start` in `chalk/sessions.py` is the one place to change.
- **P1: Line up pilot testers (sponsor meeting, Oct 15).** Dave may find 2-3 professors to try Chalk. Also find pilot testers among technical staff. For both groups, find out which parts of the app they actually use, so the next steps focus there. The eval log already records which operations run; a short feedback form or a follow-up conversation would cover the rest.

## AI providers and student data (sponsor discussion, Oct 5)

Raised at the Oct 5 sponsor meeting. Nothing student-related is sent to an AI today (only syllabi and the instructor's own source materials). A teammate is building the grading feature (Oct 15); the guardrails below go in once it lands, before it's used on real student work. Next step: a discussion within the team, then with the sponsor.

- **P1: Confirm which AI providers are approved for student work.** The University of Utah currently sanctions only ChatGPT. Grading could be built on it if licensing is approved; other frontier providers don't have that approval.
  - "Sanctioned ChatGPT" most likely means the U's licensed ChatGPT Edu workspace, which runs under a university contract. Chalk calls the OpenAI API with an individual's key, and that contract doesn't automatically cover it.
  - "APIs don't store data" isn't quite right. OpenAI's and Anthropic's APIs don't train on API data by default, but both keep requests for a period (typically up to ~30 days, for abuse monitoring). Zero-data-retention is a separate agreement. Check each provider's current terms before relying on this.
  - Student work is an education record under FERPA, so the deciding question is contractual, not technical: which services have a data agreement with the university. The U's IT/privacy office owns that answer.
  - Question to bring to the sponsor: "Which AI services and contract terms are approved for student work, and can Chalk use them through an API?"
- **P1: Privacy guardrails before any text is sent to an AI (follow-up to the grading feature).** If student data ever leaves the computer, enforce protection in code, configured on the Settings page. Chalk has to do this itself, before the request is sent: the provider sees whatever text arrives, so asking the model to hide student details doesn't protect anything.
  - Classify each provider in Settings: university-approved, not approved (public), or local (a model running on the instructor's computer, so nothing leaves it). Google Gemini (added Oct 7) and Anthropic are "not approved" today and get the same rules.
  - Block, or redact before sending, any student information going to a provider that isn't approved.
  - Names: exact-match against an uploaded Canvas roster. This is far more reliable than guessing which words are names.
  - IDs and contact details: strip uNIDs (`u` + 7 digits) and email addresses with pattern matching.
  - Log what was redacted (counts only, never the content) in the existing metadata-only eval log, so the evaluation report can show the guardrail working.
  - Redaction reduces the risk but doesn't settle the approval question above. A submission can identify its author through its content (a personal story, a named workplace, a file name or header), so the redacted text is still student work. Use redaction as a second layer on top of an approved provider, not as a substitute for one.
- **P2: Grading feature scope (in progress, Oct 15).** The PRD (Sections 9, 13 and 16) puts grading out of scope per CTE policy ("rubric drafting only"), so confirm the change with the sponsor. A defensible scope: rubric-based draft feedback that the instructor reviews, never a final grade. Use it on real submissions only with an approved provider and the guardrails above.
- **P2: Find the most token-efficient way to grade.** Token cost is a main concern for the department, so compare approaches before building: grade each rubric criterion separately or all at once; send only the relevant parts of a submission; use a smaller model (e.g. `gpt-4o-mini`) for a first pass and a larger one only for borderline cases; reuse the fixed rubric and instructions across submissions with prompt caching or batch APIs where the provider offers them. Measure the cost per submission with the existing cost tracking (Metrics tab) and set a target.
- **P1: Try Gemini with a real API key.** Gemini is built (Settings → Google Gemini) but only tested with simulated replies. With a key from aistudio.google.com, run Test connection and one generation of each type; check the answers aren't cut short (Gemini 3 models "think", and that counts against Chalk's token limits; Chalk asks for low thinking) and compare the recorded cost with Google's billing page.
- **Gemini is NOT sanctioned by the University of Utah.** It has no university data agreement, so it's for course materials only (syllabi, the instructor's own files), never student work. The provider form and README say so, and any student-data feature must apply the privacy guardrails above to it like every other unapproved provider.
- **P2: Let instructors choose any model, and keep the model list from going stale.** Today the dropdown only lists the models that have a cost rate in `config.json` (e.g. `gpt-4o`, `claude-sonnet-5`, `gemini-3.5-flash`), so when a provider releases a better model or retires one, Chalk lags until someone edits the file. Ideas to compare:
  - An "Other model…" choice where the instructor types any model name. Test connection already proves it works; its cost would show as "unknown" unless they also enter a rate.
  - Ask the provider for its current model list (OpenAI, Anthropic, and Gemini all have a list-models API) when the key is tested, and offer those.
  - Keep the bundled rates current: review `resources/config.json` each term, with a "prices last checked" date in the file. Gemini's were checked 2026-10-07.
  - When a saved model is retired, the new 404 message already says to choose another one in Settings; a startup check could warn sooner.
- **P2: Read submissions from Canvas's SpeedGrader zip (sponsor meeting, Oct 15).** SpeedGrader can download all of an assignment's submissions as one zip file, which makes a natural input for the grading feature. Canvas puts the student's name and ID in each file name inside the zip, so the guardrails above have to cover file names as well as file contents.

## Grounding, validation, and audit trail (faculty meeting with Chong Oh, Oct 23)

Chalk should make the instructor's work easier and keep a human in the loop, not replace the instructor. What it produces should come from what the instructor uploads, not from what the model happens to know. That keeps the instructor responsible for the content and makes results less dependent on which model is used. The team also needs a record of how each feature was tested and validated, in case deans or the department have concerns about AI use.

- **P1: Make grading consistent.** The Grading Assistant (PR #20) gives different results when the same submission is graded again; consistent, evidence-based results are the "grounding" the meeting asked for. Try different approaches and measure each with the consistency test below. Ideas to start with: a low temperature (`chalk/llm_client.py` doesn't set one today), a quote from the submission as evidence for every criterion, and the default instructions below.
- **P1: Test grading consistency, once it's grounded.** Testing now focuses on this. After the rules and prompting above are in place, grade a fixed set of test submissions several times each, and report the spread of the total and per-criterion scores, plus the cost. The results show that grading is consistent and back up the validation record below. Comparing models is a second step. This is a one-off test the team runs, not a feature: re-grading every submission 2-4 times would multiply the cost of grading a class (e.g. 30 students) by the same amount (decided Oct 26).
- **P2: Default grading instructions.** Pre-fill "Additional grading instructions" with standing rules such as "be consistent across submissions" and "cite evidence from the submission for every score". The team decides the exact wording, based on the framework below.
- **P2 (research): Choose an educational framework.** Base Chalk on an established framework from education. Use it to structure what Chalk does, how its quizzes, assignments, and content are validated, and how it supports better learning outcomes for students. The group will research this and decide later.
- **P1: A validation record (paper trail).** For each feature, record how it was built, how it was tested, and how it was validated against the framework, like a certification or audit report. It shows that AI-assisted development followed a sound process (tests first, CI, the eval log, the variation results) and was checked. It depends on the framework above.

## Handoff and sustainability (sponsor meeting, Oct 15)

The meeting with TIR emphasized the handoff: what the sponsor needs to keep Chalk running after December.

- **P1: Write down what the sponsor needs to keep Chalk running.** Security, maintenance, and documentation are all required. Cover who updates the academic calendar and model prices each term, how to update Python and the packages, where to report problems, and what an API key costs per term.
- **P1: A how-to manual alongside the Best Practices Guide and Catalog of Tools.** A step-by-step guide for instructors, with screenshots. README.md, GETTING-STARTED.md, and DEMO.md are the starting point, but they're written partly for developers.

## Extraction

- **P1: Try the AI PDF reader with OpenAI.** IS 6490 (10 pages) read correctly with Claude Sonnet on Oct 22: 2 parts, 51 s, $0.22. Run OSC 6660 through it with OpenAI (gpt-4o-mini, the recommended model) too, and compare the real cost per page with the hint's assumption (~800 tokens in / ~1,200 out per page).
- **P2: Test the local PDF reader on more real PDFs.** Only OSC 6660 has been tried. Watch for schedules without ruling lines (pdfplumber can't see them as tables; the AI reader is the fallback), two-column page layouts, and Google Docs exports.
- **P2: Rows cut at a page break are rejoined by a guess.** The first paragraph carried onto the next page is joined to the one above unless that ended a sentence. A complete line like "Project Artifact #2A: Scope Plan" followed by a new item on the next page would be wrongly joined. Keeping the previous page's line positions would make this exact.
- **P3: Scanned PDFs (OCR).** Out of scope; Chalk explains and suggests saving as Word.
- **P3: A sample PDF in the demo course** so teammates can try the PDF path without their own syllabus. Needs a small PDF writer (the tests hand-build theirs in `tests/fixtures/pdf_layout_builder.py`).
- **P2: Markdown has none of the Word path's new tolerance.** No month-name dates, no split tables, no extra columns. Markdown is Chalk's own format, so this matters less, but the README should keep saying so.
- **P3: A Spring syllabus with a December row** (e.g. an orientation "Week 0 (12/15)") still gets the term's year for that row. Rows only move forward a year when the schedule crosses New Year after them.
- **P3: Title guesses can include the modality**, e.g. "Networking and Servers – Online". This is editable on Review.
- **P3: Meeting pattern stays blank when it's only in a labeled line like "Time:"**. That's deliberate (in IS 6640, "Time:" is the webinar, not the class).
- **P3: The objectives list stops at any short ALL-CAPS line**, so an objective written in all caps would end it early.

## Rollover

- **P3: Changing the length of a split (per-module) Word schedule.** Added weeks go after the last week of the last module table; dropped weeks can leave a module table with only its title and header rows. Untested on a real split schedule.
- **P2: Numbered break weeks are only flagged.** In "Week 10 — Spring Break", Week 10 rolls over as an ordinary week with a flag. It isn't turned into a break row or moved.
- **P3: Break rows in a split (per-module) schedule** are placed by date across all the tables; a break after the last week goes at the end of the last table. This is untested on a real split schedule that has break rows.
- **P3: When the instructor picked one table from an ambiguous set, the writer still updates every schedule-like table.**
- **P3: The preview always shows dates as M/D**, even when the syllabus uses "Jan. 6" (the written document keeps the original style).
- **P2: Classes that meet twice a week (sponsor meeting, Oct 15).** Undergraduate courses often meet twice a week. Rollover already asks which days the class meets, but only to decide which holidays to warn about: every schedule row is still one week with one date. Test a syllabus with one row per class session (e.g. Tue and Thu rows) and decide how rollover should handle it, especially when the meeting days change between terms.

## App / UX

- **P2: Course details edited on Review aren't written back into the syllabus document**, only into `course.json` and the course brief.
- **P2: Try the launch screen's Browse… buttons on a real Mac.** The folder dialog runs as a separate Python process so that Tk gets its own main thread, which macOS requires. That design is meant for macOS but has only been tried on Windows (PR #5). On a Mac, click each Browse…, check the dialog appears in front of the browser, pick a folder, and check it fills the field. Then cancel one, and check the page stays usable while the dialog is open. If it fails, the typed path still works.
- **P1: Paste the Canvas page into a real Canvas course.** Export's Canvas HTML is now the whole U of U syllabus template, filled in, with paste steps and a preview (Oct 22). It's been checked in a browser, not in Canvas itself. Since Oct 28 it uses the template's DesignPLUS markup and relies on the DesignPLUS theme for the banner and grey section bars: check that the theme styles the pasted page like the template, that the page opens in the DesignPLUS sidebar, that the steps match its editor (some versions use a `</>` button instead of View → HTML Editor), and that the "Insert…" placeholders are easy to find.
- **P3: The unsaved-extraction warning appears on Rollover, Generate, and Export, but not Metrics** (Metrics doesn't depend on the course).
- **P3 Currently, the 'Open Project' button only lets you open a project if you manually enter in the file path. What should happen is that clicking on 'Open Project' assuming Windows OS is that it opens the file browser and you can navigate that way.** 

## Engineering

- **P1: Before the presentation, turn off raw provider error text.** `_SHOW_PROVIDER_DETAILS` in `chalk/llm_client.py` adds the provider's own explanation (e.g. "Provider said: …") to refused-request errors, to debug teammates' setup problems. Set it to `False` for the presentation, so only the plain-English messages show.
- **P2: Bundle Python with the download (sponsor meeting, Oct 15).** Today the launchers need Python 3.11+ already installed. Shipping Python inside the download (e.g. the official Windows embeddable package, or python-build-standalone on macOS) removes that step. To keep the bundle from going stale, pin the Python and package versions, build the bundle in GitHub Actions for each release instead of by hand, and add a check to the maintenance notes for when that Python version reaches end of life.

## Done

- 2026-10-28: The Canvas page follows the template's own DesignPLUS HTML (wrapper, banner, one block per section, indented paragraphs, closing rule) and lets the theme style it. The Instructor section adds TA open and scheduled hours. The preview can't be copied by mistake.

- 2026-10-28: A "Jump to…" dropdown at the end of the course line opens any tab, or Generate with a content type already selected, as soon as you pick it. Typing filters the list, and labels carry the words people use ("Export for Canvas", "Generate slides (PowerPoint)"). It replaces the workflow search bar from PR #10, which was taken out in #15 (PR #23).
- 2026-10-26: Every grading is logged in the eval log (model, AI calls, tokens, cost; never the submission, rubric, or file name) as content type "grading", so its cost shows on the Metrics tab, in the footer, and in `toolkit.py report` (PR #22).
- 2026-10-26: Generation needs at least one instructor source file besides the syllabus, in the app and the CLI (`--source`); the Generate button appears once one is selected (PR #22).
- 2026-10-26: The Metrics tab sits just left of Settings again (PR #22).

- 2026-10-22: Sessions: rollover (and Review, for an undated schedule) can start a course in Session 1, 2, or 3 and run one, two, or all three 5-week sessions; summer courses run 10 or 12 weeks; credits can be 1.5 (PR #19).
- 2026-10-22: UAT fixes: a recommended model in the model dropdown; long PDFs read with AI in parts; undated schedules don't assume a break the syllabus doesn't mention; the Canvas HTML is the whole syllabus page with paste steps and a preview; an "All courses" button returns to the course list; the API key is saved once for every course; tabs that need a course are dimmed (PR #18).
- 2026-10-22: Long operations (generation, extraction, the rollover preview) keep running when you switch tabs, shown on the tab's label, with a toast when they finish elsewhere (PR #18).
- 2026-10-22: Progress bars that show real progress: the AI's reply streaming in against its expected length, the parts of a PDF read, and each week rollover drafts. Steps that can't be measured show their name and elapsed time instead (PR #18).
- 2026-10-22: Generated content takes a course level (lower-division, upper-division, graduate; guessed from the course number), and assignments can include a task where students use AI and reflect on it (PR #18).
- 2026-10-22: The launch screen lists existing projects with an Open button, and creating a project that already exists offers to open it (PR #18).
- 2026-10-22: Docstrings on about 50 functions where a maintainer needs the reason explained (PR #18).
- 2026-10-10: Lint debt cleared: `ruff check .` passes, and CI runs it (on the Linux job). Local "today"/"now" is allowed in the ruff config, since Chalk runs on the instructor's own computer.
- 2026-10-10: New projects create `outputs/assignments/`, and `toolkit.py status` counts saved assignments.
- 2026-10-10: Quizzes, discussion prompts, rubrics, and summaries download as Word or PDF in the assignment creator's layout (type header, title, upper-case sections), on Generate and Drafts. Rubric tables become real tables, and the AI-draft banner is left out of Word/PDF.
- 2026-10-09: A Drafts tab lists the drafts saved from Generate by type and week, with a preview, a download (assignments as Word/PDF/markdown), the save date, and how many earlier versions are archived. A draft can be deleted (it moves to `.archive/`).
- 2026-10-09: A mixed quiz asks how many questions are multiple choice and how many short answer (Generate tab; `--multiple-choice`/`--short-answer` in the CLI), and the prompt asks for exactly that split. Existing projects' quiz templates carry it through `{format}`.
- 2026-10-09: Browse… buttons next to "Project folder" and "Create it inside" open the system folder dialog and fill in the field (hidden if this Python has no Tk). The page keeps running while the dialog is open, with a Cancel button, and only one dialog can be open at a time.
- 2026-10-09: The launch screen no longer fades while you type: Open and Create read their fields on click (or Enter), show a "Creating…/Opening…" spinner, and confirm on the next screen. An empty field gets a plain message instead of a greyed-out button.
- 2026-10-09: Points-based grading tables ("Labs — 250 pts", or a "Points" column) are read in Word and markdown syllabi. Points become fractions of the table's Total row (or of the rows' sum when there's none). Markdown grading tables no longer list their Total row as an assessment.
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
