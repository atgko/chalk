# Keeping Chalk running

This is for whoever looks after Chalk once the capstone team hands it over in December 2026. It says what has to be done each term, what to do once a year, where problems go, and roughly what Chalk costs to run. You don't need to be a developer for the per-term tasks: they're edits to text files. Updating Python or the packages, and building a new download, need someone comfortable with a terminal and GitHub.

Chalk has no server. Every instructor runs it on their own computer, from the zip they downloaded, and their courses live in their own Documents\Chalk Courses folder. So "maintenance" means keeping the download current, not running anything.

## Each term (about an hour)

| Task | File | How |
| --- | --- | --- |
| Check the academic calendar | `resources/data/calendars.json` | Covers Fall 2026 to Summer 2030. Each term records the PDF it was checked against and when (`verified_against`, `verified_date`). When the registrar publishes a new year, add its terms ([README section 7](README.md#7-updating-the-academic-calendar)), and check that published dates haven't changed. A term that isn't in the file still works: Rollover asks for the first day of classes. |
| Check the AI prices | `resources/config.json` (`cost_rates`) | Prices are US dollars per 1,000 tokens, input and output. Compare each model with the provider's pricing page. Add a model by adding a line; it appears in the Model dropdown automatically. Remove a model the provider has retired. |
| Check the links | `resources/links.json` | Every outside page Chalk links to, with what it's for. Open each one; fix any that moved. Settings → More settings shows the same list in the app. |
| Before the first day of term | — | Try one rollover into the new term with the demo course (Start Chalk Demo), and one generation with a real API key, so a broken calendar or a retired model is found by you rather than an instructor. |

**What an update reaches.** A change to these files goes out with the next download. It doesn't change courses instructors already made, because each course keeps its own copy of the calendar, prices, and prompt templates from when it was created (`data/calendars.json`, `config.json`, `prompts/` in the course folder):

- **Calendar:** an existing course uses its own copy. If an instructor's course is missing a new term, they can copy `calendars.json` from the new download into their course's `data` folder, or start a new course and upload the syllabus again.
- **Prices:** a provider's prices come from the course's copy whenever the course has that provider's section, so a new or re-priced OpenAI model doesn't show in an older course's dropdown. The **Other model…** choice still lets them type its name; its cost shows as unknown.
- **Links:** read from the download each time, so link fixes reach everyone (except a link an instructor changed for themselves under More settings).

## Once a year, or when something forces it

- **Python.** The download carries its own Python (`PYTHON_VERSION` and `PBS_RELEASE` in `bundle/build_bundle.py`, with a SHA-256 checksum for each file it downloads). Check for a new 3.14 patch release, update the version, release tag, and checksums, and build a new download. Python 3.14 is supported until October 2030; move to a newer Python before then.
- **Packages.** `requirements.txt` lists each package with the range of versions Chalk is tested with, so a new major version can't arrive by surprise. To move up: raise the range, run `python -m pytest -q` and `python -m ruff check .` on Windows and a Mac (the GitHub **Tests** workflow does both, plus Linux, on every pull request), and build a new download. Do this at least once a year, and straight away for a security fix in a package Chalk uses: `pip install pip-audit` then `pip-audit -r requirements.txt` lists any known ones.
- **A new download.** Push a tag like `v1.3.0`. The **Bundle** workflow builds the Windows, Apple-silicon Mac, and Intel Mac zips and puts them on a *draft* GitHub Release. Download one, start Chalk from it on a real computer (ideally a university-managed one), then publish the release.
- **AI provider changes.** Providers retire models and change their APIs. Chalk explains a retired model in plain English (it says to choose another in Settings), but a changed API needs a code change in `chalk/llm_client.py`.

## Where problems go

Report problems as GitHub issues on the repository (github.com/atgko/chalk, or wherever it moves to at handover). Ask the reporter for:

- what they did and what they expected,
- the message Chalk showed, word for word,
- Windows or Mac, and the version of the download,
- the syllabus, if it's about reading or rolling over a syllabus, **sent privately** (the repository is public; never attach a syllabus with names or anything about students to an issue).

`toolkit.py report` (or **Download evaluation report** on the Metrics tab) summarizes a course's eval log: what ran, what failed, and what it cost. It holds counts, costs, and file names, never syllabus text, drafts, or student work, so it's safe to attach once you've checked the file names.

## What it costs

Most of Chalk is free: uploading, reviewing, rolling over, and exporting never call an AI. Only these do, and each shows its estimated maximum cost before it runs:

| What | Cheaper model (Claude Haiku 4.5, GPT-4o mini) | Most capable model (Claude Sonnet 5, GPT-4o) |
| --- | --- | --- |
| A quiz, discussion, rubric, or summary | under 1¢ each | 2–4¢ each |
| Reading a 10-page PDF syllabus with AI | about 4¢ | about 26¢ |
| Grading one submission | not measured yet | not measured yet |

These are what the team's own test runs cost in November 2026 (from the eval logs), so treat them as a rough guide. For a course that generates a quiz and a discussion for each of 15 weeks, that's about 20¢ a term on a cheaper model and about $1 on the most capable one. Grading is the unknown: it sends each whole submission, so measure the cost per submission with the Metrics tab before a whole class is graded (BACKLOG.md, "Find the most token-efficient way to grade").

An Ollama model running on the instructor's computer or a university server costs nothing per use.

**Keys and billing.** Each instructor (or department) uses their own API key and pays the provider directly; Chalk never sees a bill. A department that wants a spending cap should set it in the provider's own billing settings, since Chalk can't enforce one.

## Security and privacy, in short

- No Chalk server, account, or telemetry. Everything stays on the instructor's computer except what's sent to the AI provider they chose ([README section 12](README.md#12-data-and-privacy)).
- API keys are kept in the operating system's password store (Windows Credential Manager, macOS Keychain), not in files.
- Student work goes only to a provider the university has approved for it. Today that's none of the API providers Chalk supports (see "AI providers and student data" in BACKLOG.md); check before the Grading Assistant is used on real submissions.
- Before giving a download to faculty, set `_SHOW_PROVIDER_DETAILS` in `chalk/llm_client.py` to `False`, so errors show only Chalk's plain-English message and not the provider's raw text.
