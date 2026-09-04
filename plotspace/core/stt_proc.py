"""STT en un PROCESO worker aparte — el fix del freeze post-"Actualizar ahora".

Por qué existe: onnxruntime retiene el GIL mientras crea la InferenceSession
del modelo de voz (medido acá: 5-7s con el modelo en page cache del SO, 20s+ en
frío — deep work 2026-07-12, evidencia en data/diag_stall.log + diag_boot.jsonl).
Cargarlo "en un thread aparte" NO alcanza: el GIL es DEL PROCESO, así que el
event loop de uvicorn —que da eco/scroll a TODAS las terminales— se congelaba
entero durante la carga. Era el freeze de 5-10s tras cada update aplicado (el
primer movimiento de mouse dispara el prewarm por actividad) y tras cada
regreso al workspace después de la descarga por ocio.

En un proceso hijo el GIL es suyo: el server no puede stallearse por la voz,
nunca. Bonus: "descargar el modelo" pasa a ser matar el worker — la RAM vuelve
al SO garantizada, sin gc ni malloc_trim. El worker corre con nice(5) para no
pelearle CPU al workspace en este box de 4 threads.

Protocolo (JSON-lines por stdin/stdout del worker):
  server → worker: {"id": 1, "wav": "/ruta.wav", "translate": false}
  worker → server: {"id": 1, "ok": true, "motor": "parakeet", "texto": "..."}
                   {"id": 1, "ok": false, "error": "..."}
  worker → server al terminar la carga: {"ev": "listo", "motor": "parakeet"}
El audio viaja por RUTA (mismo filesystem); el server limpia su tmp_dir después
de recibir la respuesta, igual que siempre. El worker muere solo cuando el
server cierra el pipe (shutdown o re-exec del update: los fds son CLOEXEC).

Vía de escape: STT_WORKER=off en plotspace/.env vuelve al modo in-proc viejo
(carga y corre el modelo DENTRO del server — puede congelar el event loop).
"""
import asyncio
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── Lado worker (proceso hijo: python -m backend.core.stt_proc) ─────────────

def _atender(req: dict, inferir) -> dict:
    """Un request del protocolo → response. PURA respecto de I/O (el `inferir`
    inyectable devuelve (motor, texto) o levanta)."""
    try:
        motor, texto = inferir(req.get('wav') or '', bool(req.get('translate')))
        return {'id': req.get('id'), 'ok': True, 'motor': motor, 'texto': texto}
    except Exception as e:
        return {'id': req.get('id'), 'ok': False, 'error': str(e)[:500]}


def main() -> int:
    # Prioridad amable: la carga/inferencia no compite de igual a igual con el
    # server ni las terminales (la latencia del dictado apenas cambia; la
    # fluidez del workspace sí). Best-effort.
    # `os.nice` NO existe en Windows: sin el hasattr esto era un AttributeError
    # —que el `except OSError` no atrapaba— y el worker de voz moría al arrancar
    # (visible en motor.log, 2026-07-27). En Windows el equivalente sería
    # SetPriorityClass; no vale la pena para un best-effort.
    try:
        if hasattr(os, 'nice'):
            os.nice(5)
    except OSError:
        pass
    # Si el server muere, morir con él (PR_SET_PDEATHSIG): un worker huérfano
    # retiene ~1GB de modelo en silencio. Complementa el EOF del stdin (que
    # cubre shutdown/re-exec) para el caso de un padre que murió sin cerrar
    # el pipe. Best-effort (Linux-only, que es el único entorno soportado).
    try:
        import ctypes
        import signal as _signal
        ctypes.CDLL('libc.so.6', use_errno=True).prctl(1, _signal.SIGTERM)
    except Exception:
        pass

    def emitir(obj: dict):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
        sys.stdout.flush()

    # Lazy import: voice.py arrastra FastAPI y demás; acá solo se usan sus
    # motores (misma carga y mismo despacho whisper/parakeet que in-proc).
    from plotspace.routers import voice
    try:
        modelo = voice._cargar_whisper()
    except Exception as e:
        emitir({'ev': 'error_carga', 'error': str(e)[:500]})
        return 1
    emitir({'ev': 'listo',
            'motor': 'whisper' if hasattr(modelo, 'transcribe') else 'parakeet'})

    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            req = json.loads(linea)
        except ValueError:
            continue
        emitir(_atender(req, lambda wav, tr: voice._inferir_wav(modelo, wav, tr)))
    return 0     # EOF del stdin = el server se fue (shutdown/re-exec) → morir


# ─── Lado server (manager asíncrono del worker) ──────────────────────────────

_CMD_WORKER = [sys.executable, '-m', 'plotspace.core.stt_proc']


class WorkerSTT:
    """Maneja UN worker STT: spawn perezoso, requests con future por id,
    respawn tras muerte, kill por ocio. Toda la clase vive en el event loop."""

    def __init__(self, cmd=None):
        self._cmd = cmd or _CMD_WORKER
        self._proc = None            # asyncio.subprocess.Process | None
        self._listo = False
        self._pendientes = {}        # id → Future (del spawn vigente)
        self._prox_id = 1
        self._lock = None            # asyncio.Lock perezoso (spawn/kill/envío)
        self._reader = None

    def _asegurar_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def vivo(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def listo(self) -> bool:
        return self.vivo and self._listo

    def proc_actual(self):
        """El Process vivo (o None). Lo usa el kill sync del re-exec."""
        return self._proc if self.vivo else None

    async def asegurar(self):
        """Spawnea el worker si no está vivo. La carga del modelo corre DENTRO
        del hijo: esto retorna al toque (fork+exec, milisegundos)."""
        async with self._asegurar_lock():
            if self.vivo:
                return
            self._listo = False
            pendientes: dict = {}
            self._pendientes = pendientes
            self._proc = await asyncio.create_subprocess_exec(
                *self._cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=None,             # los logs de carga van a la consola del server
                cwd=_REPO_ROOT,
            )
            self._reader = asyncio.create_task(
                self._leer_salida(self._proc, pendientes))

    async def _leer_salida(self, proc, pendientes: dict):
        """Reader único del stdout del worker: resuelve futures por id y marca
        el 'listo'. Al EOF (worker muerto) falla todos los pendientes."""
        try:
            while True:
                linea = await proc.stdout.readline()
                if not linea:
                    break
                try:
                    msg = json.loads(linea)
                except ValueError:
                    continue
                ev = msg.get('ev')
                if ev == 'listo':
                    self._listo = True
                    print(f"[stt-proc] worker STT listo (motor {msg.get('motor')}, "
                          f"pid {proc.pid})")
                elif ev == 'error_carga':
                    print(f"[stt-proc] la carga del modelo en el worker falló: "
                          f"{msg.get('error')}")
                elif 'id' in msg:
                    fut = pendientes.pop(msg['id'], None)
                    if fut is not None and not fut.done():
                        fut.set_result(msg)
        finally:
            try:
                await proc.wait()
            except Exception:
                pass
            if self._proc is proc:
                self._proc = None
                self._listo = False
            for fut in pendientes.values():
                if not fut.done():
                    fut.set_exception(RuntimeError('el worker STT murió'))
            pendientes.clear()

    async def transcribir(self, wav: str, translate: bool, timeout: float = 180.0):
        """(motor, texto) del WAV vía el worker. Puede tardar la carga entera
        si el worker está frío (igual que hoy: la inferencia encola detrás de
        la carga) — pero el event loop del server NUNCA se entera."""
        await self.asegurar()
        fut = asyncio.get_running_loop().create_future()
        async with self._asegurar_lock():
            # proc y pendientes se leen JUNTOS bajo el lock: pertenecen a la
            # misma generación de worker (asegurar los setea en pareja).
            proc = self._proc
            if proc is None or proc.returncode is not None:
                raise RuntimeError('no se pudo levantar el worker STT')
            rid = self._prox_id
            self._prox_id += 1
            self._pendientes[rid] = fut
            try:
                proc.stdin.write((json.dumps(
                    {'id': rid, 'wav': wav, 'translate': bool(translate)},
                    ensure_ascii=False) + '\n').encode())
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                self._pendientes.pop(rid, None)
                raise RuntimeError(f'el worker STT no recibe pedidos: {e}')
        try:
            msg = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pendientes.pop(rid, None)
            raise RuntimeError('timeout esperando al worker STT')
        if not msg.get('ok'):
            raise RuntimeError(msg.get('error') or 'el worker STT falló')
        return msg.get('motor') or '', (msg.get('texto') or '')

    async def terminar(self) -> bool:
        """Mata el worker (descarga por ocio / shutdown). True si había uno."""
        async with self._asegurar_lock():
            proc = self._proc
            if proc is None or proc.returncode is not None:
                return False
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
            return True


if __name__ == '__main__':
    sys.exit(main())
