# Demoing Chalk

A 10–15 minute walkthrough for a sponsor or faculty audience, using the built-in demo course. Every sample file is synthetic and labeled as such.

## Before the meeting (5 minutes, the day before)

1. **Start it once.** Double-click **`Start Chalk Demo.bat`** (Windows) or **`Start Chalk Demo.command`** (macOS). The first run installs everything, which takes a couple of minutes and needs internet. Later starts take a few seconds.
2. **Connect an AI provider** on the welcome screen if you'll show generation. The key is saved only in the demo project, and it survives a demo reset. With no key, click **Skip for now**: everything except step 6 below still works.
3. **Do one practice generation** so you know the provider works from the meeting network.
4. **Reset the demo** so you start clean: on the launch screen click **Reset the demo course**, or run `Start Chalk.bat --reset-demo`.

On the day, double-click **`Start Chalk Demo`**. The browser opens on the demo course. Keep the black console window open (minimizing it is fine). Closing it stops Chalk.

Sample files for live uploads are in **`projects/Chalk-Demo/try-these/`**. Have that folder open in File Explorer or Finder so the file dialog is quick to navigate.

## The walkthrough

**1. It's local (30 s).** Point out the address bar: `localhost`. The syllabus, outputs, and API key never leave this computer. Only the text of a generation request goes to the AI provider, and only when you click Generate.

**2. What it read from the syllabus (1–2 min). Review tab.**
The IS 6640 Word syllabus was already extracted: course details, four learning objectives, grading weights that add up to 100%, and all 10 weeks, including the Fall Break row and the Week 1 note. *"Nothing is saved until you confirm, and duration is editable here if the course is changing length."*

**3. Next year's syllabus in seconds (3 min). Rollover tab.**
- The target term defaults to **Fall 2027**. Click **Preview rollover**.
- Every week moves to its new date (Week 1: Aug 24 → Aug 23), and the preview flags **"Fall Break 2027 is Oct 9–17 — confirm Week 8 timing"**. This is the exact example from the project requirements. It also flags Labor Day landing on Week 3.
- *"It never renumbers quizzes or exams, and it never writes anything until you confirm."* Click **Confirm rollover**.
- Download **outputs/syllabus.docx** and open it in Word: the formatting is untouched, and only the dates changed.

**4. Canvas in one paste (1 min). Export tab.**
Show the Canvas HTML box and its copy button, plus **Download all as zip**. The course brief is a one-page summary built automatically, with no AI and no cost.

**5. The bug it catches (1–2 min). Upload tab.**
Upload **`IS-6640-Spring-2026-term-label-bug.docx`** and click **Extract course**. The warning appears: *term label says Spring 2026, but Week 1 is August*. *"This is the real mistake that prompted the check: the label was updated but the schedule wasn't."* Click **Cancel**. The saved course is untouched. (The Metrics tab counts this as a consistency-check catch.)

**6. Drafting course materials (3 min). Generate tab.** *Needs the AI provider from setup.*
- Content type **Quiz**, **Week 3** (Protocols and subnetting), 5 questions, mixed.
- Under **Source materials to use**, tick **week-3-subnetting-notes.md**. *"It grounds the quiz in the instructor's own notes, never a whole textbook."*
- Point at **Estimated cost: up to ~$0.0x** before clicking **Generate**.
- The draft opens with the **AI-generated draft** banner, followed by questions and an answer key. Click **Save**. It's written to `outputs/quizzes/week-3-quiz.md`, and any previous version is archived.
- Optionally, show a **Rubric**: *"rubric drafting only; it never grades student work."*

**7. Evidence (1 min). Metrics tab.**
Total AI cost, rollovers, the consistency catch from step 5, and generations by type. **Download evaluation report** gives the same numbers as a document for reporting.

**8. Optional: the markdown path.** Upload **`IS-4490-Fall-2026.md`**, then Confirm and save on Review. This replaces the demo course, and you can reset afterwards. Roll it to Fall 2027: the preview flags due dates near the **daylight-saving change** for a human to check, and never edits time zones automatically.

## If something goes wrong

| Symptom | What to do |
|---|---|
| The browser didn't open | Open the address printed in the console window (usually http://localhost:8501). |
| "Could not reach the LLM provider" | The meeting network is blocking it. Skip step 6; everything else works offline. |
| You changed the demo and want it back | Launch screen → **Reset the demo course**. |
| The console window shows an error on start | Close it and double-click the launcher again. If it persists, delete the `.venv` folder so the next start reinstalls. |
