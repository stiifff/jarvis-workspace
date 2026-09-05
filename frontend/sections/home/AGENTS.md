# sections/home/ — landing

Home page (project list / entry to the workspace).

- **Files:** `home.js`, `home.css`
- **Served at:** `/static/sections/home/` — referenced from `frontend/index.html`
  (which is served at `GET /`, NOT under `/static`).
- On change, bump the `?v=N` in `index.html` (not in `workspace.html`).

## Verification
Manual smoke at `localhost:3000/` (the home), not at `/workspace`.
