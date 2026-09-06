# Security

Jarvis Workspace **runs arbitrary commands** on your machine. Anyone who can
talk to the engine can run anything as your user.

- Default bind is **127.0.0.1**. `0.0.0.0` is explicit and warned.

CLI credentials live in `data/cli-accounts/` (mode 0600), never in git. The
pre-commit/pre-push scanner (`scripts/scan_secretos.py`) blocks keys, `.env`
files, and known secret patterns. Don't bypass it with `--no-verify`.

## Report a vulnerability

Open a [private advisory](https://github.com/celsiusm/jarvis-workspace/security/advisories/new),
not a public issue. We aim to reply within 7 days.
