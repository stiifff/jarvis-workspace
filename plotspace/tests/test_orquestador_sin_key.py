"""Sin ANTHROPIC_API_KEY el chat del orquestador devuelve un error ESTRUCTURADO
(409 {"detail": {"error": "no_api_key", ...}}) en vez de un 500 crudo.

El valor central del producto (spawnear CLIs por tmux = BYOK) NO usa esta key:
solo la usan el chat de Jarvis y el Web Builder. Cuando falta, estos endpoints
tienen que degradar con un error limpio que el frontend muestre como empty-state,
no romper con un 500.
"""
import os
import sys
from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core.database import get_db
from plotspace.routers import orchestrator
from plotspace.tests._harness import fresh_db


def _crear_proyecto() -> int:
    now = datetime.now().isoformat()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO projects (nombre, ruta, fecha_creacion, ultimo_acceso) VALUES (?, ?, ?, ?)",
            ("test", "/tmp/proyecto-test", now, now),
        )
        pid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return pid


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(orchestrator.router)
    return TestClient(app)


# ── Helper compartido _guard_api_key ────────────────────────────────────────
def test_guard_sin_key_lanza_409_estructurado(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        orchestrator._guard_api_key()
    assert exc.value.status_code == 409
    assert exc.value.detail == {
        "error": "no_api_key",
        "message": "Configurá ANTHROPIC_API_KEY (plotspace/.env) para usar el chat "
                   "de Jarvis. Los agentes en terminales (BYOK) no la necesitan.",
    }


def test_guard_con_key_devuelve_el_valor(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 10)
    assert orchestrator._guard_api_key() == "sk-ant-" + "x" * 10


# ── Endpoints (motor API, vía de escape): sin key → 409 estructurado ────────
# Desde 2026-07-19 el motor default es 'suscripcion' (claude -p, sin key):
# el 409 no_api_key aplica SOLO cuando ORQUESTADOR_MOTOR=api.
def test_chat_sin_key_devuelve_409(client, monkeypatch):
    fresh_db()
    pid = _crear_proyecto()
    monkeypatch.setattr(orchestrator, 'ORQUESTADOR_MOTOR', 'api')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    r = client.post("/api/orchestrator/chat", json={"project_id": pid, "message": "hola"})

    assert r.status_code == 409, "sin key NO debe ser un 500 crudo"
    assert r.json()["detail"]["error"] == "no_api_key"
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]["message"]


def test_chat_stream_sin_key_devuelve_409(client, monkeypatch):
    fresh_db()
    pid = _crear_proyecto()
    monkeypatch.setattr(orchestrator, 'ORQUESTADOR_MOTOR', 'api')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # El guard corre en _preparar_contexto_chat (await) ANTES de armar el
    # StreamingResponse → el cliente recibe un 409 HTTP normal, no un SSE.
    r = client.post("/api/orchestrator/chat-stream", json={"project_id": pid, "message": "hola"})

    assert r.status_code == 409, "sin key NO debe ser un 500 crudo"
    assert r.json()["detail"]["error"] == "no_api_key"


# ── Motor suscripción (default): la key NO hace falta; el guard es el CLI ───
def test_chat_suscripcion_sin_key_no_pide_key(client, monkeypatch):
    fresh_db()
    pid = _crear_proyecto()
    monkeypatch.setattr(orchestrator, 'ORQUESTADOR_MOTOR', 'suscripcion')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Sin el binario `claude` a la vista, el guard nuevo degrada limpio
    # (y de paso el test jamás spawnea un CLI real).
    import shutil
    monkeypatch.setattr(shutil, 'which', lambda _: None)

    r = client.post("/api/orchestrator/chat", json={"project_id": pid, "message": "hola"})

    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "no_cli", \
        "en suscripción el 409 posible es por CLI ausente, jamás por API key"


def test_chat_proyecto_inexistente_sigue_404(client, monkeypatch):
    # El 404 de proyecto inexistente se evalúa ANTES del guard de key: no se rompe.
    fresh_db()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/orchestrator/chat", json={"project_id": 99999, "message": "hola"})
    assert r.status_code == 404


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
