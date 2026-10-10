# Working on Chalk as a team

Four of us share this repo. `master` is what we demo from, so every change reaches it through a pull request.

## The loop

1. **Pick one thing.** Take an item from BACKLOG.md (or a GitHub issue) and say in the team chat that you're on it, so two people don't build the same fix.
2. **Branch from an up-to-date master.**
   ```
   git checkout master
   git pull
   git checkout -b fix/short-description
   ```
   Prefixes: `feat/`, `fix/`, `docs/`, `chore/`. One branch per change. Aim to merge within a day or two.
3. **Commit as you go**, in the `type: description` style (`feat: …`, `fix: …`, `docs: …`). Write tests with the change.
4. **Run the tests and the linter locally** before pushing: `python -m pytest -q` (the run fails if coverage drops under 80%) and `python -m ruff check .` (`ruff check . --fix` fixes most findings).
5. **Stay current.** If master moves while you work, merge it in (`git pull origin master`) and rerun the tests. Small, frequent catch-ups beat one big conflict at the end.
6. **Push and open a PR.** `git push -u origin <branch>`, then open the PR on GitHub. Fill in the template's test plan, including any manual check in the app.
7. **Wait for a green CI.** The **Tests** workflow runs on Windows, macOS, and Linux, and master only accepts a PR once it passes. No approval is needed, so merge your own PR. Ask a teammate to look first only if you want a second opinion.
8. **Merge, then delete the branch.** Use **Merge pull request** (GitHub deletes the branch on GitHub for you). The branch is done once merged. Start the next change from master again.

## Things that conflict easily

- **BACKLOG.md and DECISIONS.md.** Everyone edits these. Add your lines in the right section and expect to resolve small text conflicts. Keep every side's lines when you do.
- **`requirements.txt`.** Say in the PR when you add a package, and give it a short comment like the other lines.

## Secrets and student data

Never commit API keys or `.env` files. Real syllabi go in the git-ignored `reference/` folder, because the repo is public.
