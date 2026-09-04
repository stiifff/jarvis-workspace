# Contributing

Fork, branch, PR. Keep it small.

## Setup

Follow the [native install](README.md#install) (`./install.sh` from a clone, or the one-liner there), then:

```bash
bash scripts/setup-hooks.sh   # blocks secrets; don't skip
```

## Tests

```bash
source venv/bin/activate
python -m pytest
node frontend/sections/**/__tests__/*.test.js
```

No build step, no linter.

## Style

- Frontend: vanilla HTML/CSS/JS — no frameworks, no npm
- Colors: `var(--ob-*)`, never raw hex
- tmux/git: synchronous `subprocess.run` (async `create_subprocess_exec` hangs)
- After frontend edits, bump `?v=N` on the `<script>` / `<link>` in HTML

## Don't commit

API keys, `.env`, `data/`. The pre-commit hook (`scripts/scan_secretos.py`) will stop you.
