# sections/home/ — landing

Página de inicio (lista de proyectos / entrada al workspace).

- **Archivos:** `home.js`, `home.css`
- **Servido en:** `/static/sections/home/` — referenciado desde `frontend/index.html`
  (que se sirve en `GET /`, NO bajo `/static`).
- Al cambiar, subir el `?v=N` en `index.html` (no en `workspace.html`).

## Verificación
Smoke manual en `localhost:3000/` (la home), no en `/workspace`.
