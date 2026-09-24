# Getting started: run the Chalk demo yourself

A step-by-step guide for teammates. Follow it top to bottom and you'll have Chalk running on your own computer with a sample course loaded, and you'll have walked through everything we show the sponsor. It takes about 20 minutes, most of it the first-time install.

Each step ends with a ✅ **Check**: what you should see before moving on. If you don't see it, jump to [Troubleshooting](#troubleshooting).

---

## 1. What you need

- A Windows or Mac computer.
- **Python 3.11 or newer.** Open a terminal (Windows: PowerShell; Mac: Terminal) and run `python --version` (Mac: `python3 --version`). If it's missing or older than 3.11, install it from [python.org/downloads](https://www.python.org/downloads/).
  - **Windows:** on the installer's first screen, tick **"Add python.exe to PATH"**.
- About **1 GB of free disk space** and **internet for the first start** (it downloads Chalk's components once).
- **Optional:** an OpenAI or Anthropic API key, only for step 6 (generating quizzes and other drafts). Everything else works without one. If you use a key, it's your own, and generating costs a few cents per draft.

## 2. Get the code

Pick one:

- **With Git:**
  ```bash
  git clone https://github.com/atgko/chalk.git
  ```
- **Without Git:** on [github.com/atgko/chalk](https://github.com/atgko/chalk), click **Code → Download ZIP**, then unzip it. On Windows, right-click the ZIP → **Extract All**. Don't run anything from inside the ZIP.

> **Tip: keep it out of OneDrive, iCloud Drive, or Dropbox.** Put it in a plain folder like `C:\Users\<you>\chalk` or `~/chalk`. Sync apps try to upload the thousands of files Chalk installs, which can make everything (including the app) very slow.

✅ **Check:** the folder contains `Start Chalk.bat`, `Start Chalk Demo.bat`, `README.md`, and a `chalk` folder.

## 3. Start the demo

**Windows:** double-click **`Start Chalk Demo.bat`**.
- If a blue **"Windows protected your PC"** box appears, click **More info → Run anyway**. It appears because the file came from the internet.

**Mac:** right-click **`Start Chalk Demo.command`** → **Open** → **Open** again. You only need to right-click the first time, to get past Gatekeeper.
- If you downloaded the ZIP and nothing happens, open Terminal in the folder and run `chmod +x "Start Chalk.command" "Start Chalk Demo.command"`, then try again.

A console window opens. **The first start takes a few minutes** while it installs components; you'll see `Installing Chalk's components...`. Later starts take seconds.

✅ **Check:** the console says `Chalk is running at http://localhost:8501` (the number may differ), and your browser opens a page with **Welcome to Chalk** in a large serif font under a red line of text.

> Keep the console window open while you use Chalk. Minimizing it is fine; closing it stops Chalk.

## 4. Get past the welcome screen

The welcome screen asks for an AI provider.

- **No API key?** Click **Skip for now** at the bottom.
- **Have a key?** Choose OpenAI or Anthropic Claude, paste the key, pick a model, and click **Test connection and continue**. The key is saved only in the demo project on your computer.

✅ **Check:** you see seven tabs: **Upload, Review, Rollover, Generate, Export, Metrics, Settings**.

## 5. Walk through the demo

Do these in order. They're the same steps we show the sponsor. [DEMO.md](DEMO.md) has the talking points that go with each one.

The sample files for uploading are in the project folder at **`projects/Chalk-Demo/try-these/`**. Open that folder in File Explorer or Finder now so it's easy to find.

1. **Review tab.** The sample syllabus (IS 6640 Networking and Servers) is already loaded.
   ✅ **Check:** 4 learning objectives, 6 grading weights, and 10 weeks plus a Fall Break row in the week-by-week table.

2. **Rollover tab.** Leave the target term on **Fall 2027** and click **Preview rollover**.
   ✅ **Check:** Week 1 goes from Aug 24 to Aug 23, and two yellow flags appear: *Labor Day 2027 is Sep 6 — confirm Week 3 timing* and *Fall Break 2027 is Oct 9–17 — confirm Week 8 timing*.
   Then click **Confirm rollover**. ✅ **Check:** *"Rollover complete"* with download buttons.

3. **Export tab.** Download **outputs/syllabus.docx** and open it in Word.
   ✅ **Check:** the dates in the schedule now start 8/23, the term says Fall 2027, and nothing else about the document changed. The **Canvas HTML** box at the bottom has a copy button.

4. **Upload tab.** Choose **`IS-6640-Spring-2026-term-label-bug.docx`** from `try-these` and click **Extract course**.
   ✅ **Check:** a warning says the term label is Spring 2026 but Week 1 is in August. Click **Cancel**. This is the bug the tool is built to catch.

5. **Generate tab** (only if you entered an API key). Content type **Quiz**, Week **3**, and under *Source materials to use* tick **week-3-subnetting-notes.md**. Note the estimated cost, then click **Generate**.
   ✅ **Check:** a draft appears starting with **AI-generated draft — review and edit before use**. Click **Save**.

6. **Metrics tab.**
   ✅ **Check:** Rollovers shows **1** and Consistency-check catches shows **1**. Try **Download evaluation report**.

7. **Optional, the markdown path.** Upload **`IS-4490-Fall-2026.md`**, go to **Review**, click **Confirm and save**, then preview a rollover to Fall 2027.
   ✅ **Check:** flags about due dates near the daylight-saving change.

## 6. Start over whenever you like

To put the demo back to its original state: close the browser tab, stop Chalk (close the console window), start **`Start Chalk.bat`** / **`Start Chalk.command`** (not the Demo one), and click **Reset the demo course** on the launch screen. A saved API key is kept.

## 7. Getting updates

When the team pushes changes:

- **Git:** in the folder, run `git pull`.
- **ZIP:** download and unzip the new version. To keep your demo progress, copy the `projects` folder across.

Then start Chalk as usual. It notices new requirements and installs them automatically.

---

## Troubleshooting

| What you see | What to do |
|---|---|
| **"Chalk needs Python 3.11 or newer"** | Install Python from python.org (Windows: tick "Add python.exe to PATH"). Delete the `.venv` folder inside the Chalk folder, then start again. |
| Double-clicking the `.bat` opens the Microsoft Store | Windows is using its Python placeholder. Install Python from python.org, then turn off *Settings → Apps → Advanced app settings → App execution aliases → python.exe*. |
| **"Installing Chalk's components failed"** | Check your internet connection (some campus or VPN networks block downloads), then start again. |
| The console says it's running but no browser opened | Open the address it printed (e.g. `http://localhost:8501`) yourself. |
| Everything is very slow | Move the Chalk folder out of OneDrive, iCloud, or Dropbox (see step 2), and close other heavy apps. |
| The page shows grey placeholder bars for a long time | Give it a few seconds; it's still loading. If it never finishes, close the console window and start again. |
| **"Could not reach the LLM provider"** on Generate | Network problem or wrong key. Everything except Generate still works. Check the key under **Settings**. |
| A red error box says *"Something unexpected went wrong"* | Copy the text from the console window and send it to the team (see below). Your files weren't changed. |
| Anything else | See the FAQ in [README.md](README.md#11-faq-and-error-reference), which lists every error message and its fix. |

**Reporting a problem:** open an issue on [GitHub](https://github.com/atgko/chalk/issues), or message the team with (1) which step you were on, (2) your operating system, and (3) the last 20 or so lines of the console window.

---

## For teammates working on the code

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows    (Mac: source .venv/bin/activate)
pip install -r requirements-dev.txt
pytest                           # full suite, including the Streamlit UI tests; enforces 80% coverage
streamlit run app.py -- --project projects/Chalk-Demo
```

- Business logic lives in `chalk/`. The Streamlit UI (`ui/`) and the CLI (`chalk/cli.py`) are thin layers over `chalk/pipeline.py` and `chalk/generation/`.
- Colors, fonts, and the theme are in `.streamlit/config.toml` (University of Utah palette; see the comments there).
- `DECISIONS.md` explains why things are the way they are; read it before changing behavior.
