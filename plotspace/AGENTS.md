# plotspace/ — mapa para agentes

FastAPI + uvicorn. Organizado por sección en `routers/`.

```
plotspace/
├── main.py          # entrypoint: app, startup, mount /static, rutas HTML. Comando:
│                    #   python3 -m uvicorn plotspace.main:app --host 0.0.0.0 --port 3000
├── core/         # database, events, auth, ssrf (anti-SSRF), mantenimiento,
│                 # agent_live, agent_watch, dev_detect, fe_watch, mailbox,
│                 # puertos, web_search (YouTube de la Radio), stt_proc (worker STT en proceso
│                 # aparte — NUNCA cargar modelos ML in-proc: el GIL congela el loop)
│   ├── database.py  # SQLite WAL (DB_PATH → data/jarvis.db), get_db(), init_db(), purgar_task_events()
│   ├── events.py    # EventBroadcaster (WebSocket por project_id), singleton `broadcaster`
│   └── auth.py      # token-gate + host_permitido/origen_permitido (anti rebinding/CSWSH)
├── routers/         # un router por sección (15): orchestrator, terminals,
│   │                # projects, projects_files, plugins, voice, workspace,
│   │                # mobile_preview, memory, tasks,
│   │                # review, live, system, cuentas, fs
│   ├── orchestrator.py   # /api/orchestrator/* + workflows (el más grande)
│   ├── terminals.py      # /api/terminals/* + monitor de keywords + tmux/PTY
│   ├── projects.py       # /api/projects/*
│   ├── projects_files.py # files tab (read/write/search/upload, con safe-join)
│   └── ...
└── tests/           # pytest (config en pytest.ini) — además cada test corre
                     # como script suelto (bloque __main__). `python -m pytest`
                     # o `python3 plotspace/tests/test_<x>.py` (DB aislada en tempfile).
```

## Reglas críticas (ver CLAUDE.md para el detalle)
- **tmux/git de control:** usar `subprocess.run` (síncrono), NO asyncio (cuelga).
  Excepción: `_capture_tmux_output()` en terminals.py.
- **Import circular** orchestrator ↔ terminals: resolver con lazy import dentro de la función.
- **Imports de core:** `from plotspace.core.database import get_db`, `from plotspace.core.events import broadcaster`.
- **Paths:** siempre `os.path.join`. La `ANTHROPIC_API_KEY` se excluye del entorno PTY.

## Verificación
`python3 -c "import plotspace.main"` + correr la suite: `python -m pytest`
(o `for t in plotspace/tests/test_*.py; do python3 "$t"; done`).
