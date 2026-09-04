# Contributing to Jarvis Workspace

Thanks for taking the time to contribute! This project is small, vanilla, and
build-step-free on purpose — contributing is meant to be low-friction. Here's how
to get going.

## Development setup

Follow the **Native (Linux / WSL)** install in the [README](README.md#option-b--native-linux--wsl):
create the virtualenv, install `plotspace/requirements.txt`, and run the server with
`--loop asyncio` (uvloop has a periodic event-loop stall on WSL2). Don't forget to
enable the git hooks:

```bash
bash scripts/setup-hooks.sh
```

This wires up the pre-commit hooks that block secrets and enforce file ownership.

## Running the tests

Run the full suite before opening a PR and make sure everything is green:

```bash
source venv/bin/activate

# Backend (pytest, config in pytest.ini)
python -m pytest

# Frontend (pure Node test suites — native assert, no test runner)
node frontend/sections/**/__tests__/*.test.js
```

There's no build step and no linter. The frontend tests are plain Node scripts; the
remote-browser smoke test is skipped automatically if Chromium can't launch.

## Code style

- **Frontend is vanilla** — HTML/CSS/JS, no frameworks, no npm, no bundler. Keep it
  that way unless there's a discussed reason not to.
- **Use CSS tokens, never hardcoded colors.** Always reference `var(--ob-*)` so the
  7-theme system keeps working; don't drop raw hex values into new sections.
- **Use synchronous `subprocess.run` for tmux/git** control commands.
  `asyncio.create_subprocess_exec` hangs on `tmux new-session -d` in this
  environment.
- **Bump `?v=N`** on the `<script>`/`<link>` tags when you change frontend assets
  (cache busting — there's no build hash).
- Match the conventions of the code around you. The architecture and gotchas live
  in [`CLAUDE.md`](CLAUDE.md).

## Pull request flow

1. **Fork** the repo and create a branch off `main` for your change.
2. Make focused commits — [Conventional Commits](https://www.conventionalcommits.org/)
   style (`feat:`, `fix:`, `refactor:`, with a scope) is appreciated.
3. Run the full test suite and confirm it passes.
4. Open a **pull request** with a clear description of what changed and why.

## Don't commit secrets

API keys, tokens, and `.env` files must never land in the repo. The pre-commit hook
(`scripts/scan_secretos.py`) scans staged changes and **blocks** the commit if it
finds a token, a `.env`, a private key, or a known API-key pattern. Don't bypass it
with real secrets. Local state — `data/` (DB, token, account secrets) and
`plotspace/.env` — is gitignored and should stay out of version control.

Welcome aboard, and thanks again!
