"""
STT remoto vía Groq: whisper-large-v3-turbo corriendo en los LPUs de Groq
(~216x tiempo real). Con STT_MOTOR=groq la transcripción sale de la CPU local
por completo — cero carga de modelo, cero RAM — y el motor local (parakeet)
queda como fallback si la llamada falla (sin red, 5xx, timeout, rate limit).

API compatible con la de OpenAI: multipart a /openai/v1/audio/transcriptions
con el WAV ya recortado/normalizado por ffmpeg (el mismo que consume el motor
local). El free tier alcanza de sobra para dictado (7.200 s de audio/hora);
la key vive en plotspace/.env (GROQ_API_KEY, jamás en el repo).
"""
import os

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

_MODELO_DEFAULT = "whisper-large-v3-turbo"

# El dictado es corto (~12s) y Groq responde en <1s: el timeout acota el peor
# caso (red muerta a mitad de upload) para que el fallback local no espere de
# más. connect corto: sin internet falla al instante y el fallback arranca ya.
_TIMEOUT_TOTAL_S = 12.0
_TIMEOUT_CONNECT_S = 4.0


def modelo() -> str:
    """Modelo STT de Groq (GROQ_STT_MODEL para override, p.ej. whisper-large-v3)."""
    return (os.getenv("GROQ_STT_MODEL") or "").strip() or _MODELO_DEFAULT


def api_key() -> str | None:
    k = (os.getenv("GROQ_API_KEY") or "").strip()
    return k or None


def armar_form(modelo_nombre: str, prompt: str | None) -> dict:
    """Campos del multipart de transcripción. PURA y testeable.
    temperature=0 = decode determinista (mismo criterio que el motor local);
    language fijo es: el dictado del workspace es siempre español."""
    form = {
        "model": modelo_nombre,
        "language": "es",
        "temperature": "0",
        "response_format": "json",
    }
    if prompt:
        form["prompt"] = prompt
    return form


def parsear_respuesta(data) -> str:
    """Texto del JSON de Groq ({"text": ...}). PURA y tolerante a basura."""
    try:
        return (data.get("text") or "").strip()
    except AttributeError:
        return ""


async def transcribir(wav_path: str, prompt: str | None = None) -> str:
    """Sube el WAV a Groq y devuelve la transcripción. Levanta excepción ante
    cualquier fallo (key ausente, red, HTTP != 2xx) — el caller decide el
    fallback; acá no se degrada en silencio."""
    import httpx

    key = api_key()
    if not key:
        raise RuntimeError("GROQ_API_KEY ausente")

    with open(wav_path, "rb") as f:
        contenido = f.read()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_TIMEOUT_TOTAL_S, connect=_TIMEOUT_CONNECT_S)
    ) as client:
        r = await client.post(
            GROQ_STT_URL,
            headers={"Authorization": f"Bearer {key}"},
            data=armar_form(modelo(), prompt),
            files={"file": ("dictado.wav", contenido, "audio/wav")},
        )
        r.raise_for_status()
        return parsear_respuesta(r.json())
