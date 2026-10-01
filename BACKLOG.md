# Backlog

A running list of known gaps, open questions, and follow-ups. Add new items at the bottom of the right section; move an item to **Done** with the date and commit when it's resolved. Priorities: **P1** = likely to trip up a real instructor soon, **P2** = real but rarer or has a workaround, **P3** = polish.

Last updated: 2026-09-30.

## Open questions (need someone outside the code)

- **P1: Get the Word (.docx) version of the OSC 6660 syllabus.** We only have the PDF. The module-table support was built against a synthetic look-alike reconstructed from the PDF's text (`chalk/demo_content.py`), so the real table structure (merged title rows, where the focus text sits, soft line breaks) is unverified.
- **P1: Confirm the "16-week syllabus showed 10 weeks" report.** Most likely cause: the new syllabus was extracted into the demo project but not yet saved, so the Rollover tab still showed the saved 10-week demo course. The app now warns about this. Ask the teammate whether they clicked Confirm and save first.
- **P2: Collect more real syllabi.** Only two real syllabi have been tested (IS 6640, OSC 6660). PLAN.md's Section 15 test corpus (before the Nov 8 readiness meeting) is the place to find new layouts. Keep them in the git-ignored `reference/` folder, since the repo is public.

## Extraction

- **P1: PDF syllabi aren't accepted.** Uploads must be .docx or .md. Many syllabi start as Google Docs or PDFs. pypdf is already a dependency, but its text comes out one word per line with the tables lost (tested on OSC 6660), so table-level parsing would need a different approach (e.g. pdfplumber). Workaround: export to Word.
- **P2: Markdown has none of the Word path's new tolerance.** No month-name dates, no split tables, no extra columns. Markdown is Chalk's own format, so this matters less, but the README should keep saying so.
- **P2: Year inference uses the term's year for every date.** A Fall syllabus with a January row (e.g. finals week "Week 17 (1/4)") would get the wrong year.
- **P2: Grading weights aren't checked to sum to 100%.** Review should warn when they don't (e.g. a missed row, or a points-based table).
- **P3: Points-based grading tables** ("Labs — 250 pts") aren't recognized; only percentages are.
- **P3: Title guesses can include the modality**, e.g. "Networking and Servers – Online". This is editable on Review.
- **P3: Meeting pattern stays blank when it's only in a labeled line like "Time:"**. That's deliberate (in IS 6640, "Time:" is the webinar, not the class).
- **P3: The objectives list stops at any short ALL-CAPS line**, so an objective written in all caps would end it early.

## Rollover

- **P1: Word rollover with a changed duration doesn't add or remove table rows.** Added weeks appear in the preview, `course.json`, and the course brief, but not in the .docx. Dropped weeks keep their old labels in the document. Markdown rollover does handle this, because it rewrites the whole table.
- **P2: Numbered break weeks are only flagged.** In "Week 10 — Spring Break", Week 10 rolls over as an ordinary week with a flag. It isn't turned into a break row or moved.
- **P2: Single-day holidays in the University Dates table aren't replaced on a season change** (e.g. Labor Day in a Spring rollover). They're flagged for manual removal.
- **P3: Break rows in a split (per-module) schedule** are placed by date across all the tables; a break after the last week goes at the end of the last table. This is untested on a real split schedule that has break rows.
- **P3: When the instructor picked one table from an ambiguous set, the writer still updates every schedule-like table.**
- **P3: The preview always shows dates as M/D**, even when the syllabus uses "Jan. 6" (the written document keeps the original style).

## App / UX

- **P2: Course details edited on Review aren't written back into the syllabus document**, only into `course.json` and the course brief.
- **P2: There's no button to discard an unsaved extraction** (Cancel only appears after a term mismatch). Refreshing the page clears it.
- **P3: The unsaved-extraction warning appears on Rollover, Generate, and Export, but not Metrics** (Metrics doesn't depend on the course).

## Engineering

- **P2: Lint debt.** `ruff check` reports about 30 existing findings (mostly UP017 `datetime.UTC`, DTZ, ISC004) because the selected rules are stricter than the code. Either fix them in one pass or relax the config, then add a lint check to CI.
- **P3: `chalk/rollover/preview.py` is about 540 lines.** The flagging helpers could move to their own module.

## Done

- 2026-09-30: Season-change rollovers rebuild break rows from the target calendar (Spring rollovers no longer say "Fall Break").
- 2026-09-30: Loose front-matter extraction (only the term required; details editable on Review).
- 2026-09-30: Word schedules: month-name dates, module tables, Assignment Due column, text after labels; objectives and grading-table detection loosened; unsaved-extraction warning.
