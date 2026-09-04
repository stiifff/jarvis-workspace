"""
Test: cadena de filtros ffmpeg del dictado (_RECORTE en voice.py).

La cadena hace DOS cosas, en este orden:
  1. silenceremove en ambas puntas (menos audio = inferencia más corta).
  2. speechnorm: nivela la voz — el mic del usuario entra crónicamente bajo
     (diag "bajo" en dictados.log, picos < -24dBFS) y el modelo local transcribe
     peor con señal débil. El orden importa: el umbral -40dB de silenceremove
     opera sobre los niveles ORIGINALES (normalizar antes lo correría).

El test funcional corre ffmpeg de verdad sobre un WAV sintético "tipo mic bajo"
(picos -34dBFS) y verifica que la salida quede nivelada (pico >= -14dBFS) y
recortada. Se saltea si no hay ffmpeg (CI sin él): el fallback graceful de
/transcribe (reconvertir sin filtro) ya está cubierto en test_voice_translate.
"""
import asyncio
import math
import os
import shutil
import struct
import sys
import tempfile
import wave

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers import voice


def test_recorte_normaliza_despues_de_recortar():
    """speechnorm presente y DESPUÉS de los silenceremove (el orden importa)."""
    assert "speechnorm" in voice._RECORTE
    assert voice._RECORTE.index("silenceremove") < voice._RECORTE.index("speechnorm")
    assert voice._RECORTE.rstrip(",").endswith("speechnorm=e=25:r=0.001:l=1")


def test_recorte_umbral_de_silencio_50db():
    """Umbral de silencio en -50dB (pedido 2026-07-17 'que me escuche más de
    lejos'): hablando a distancia la voz entra cerca del piso y con -45dB el
    trim la descartaba como silencio. -50dB en AMBAS puntas."""
    assert voice._RECORTE.count("start_threshold=-50dB") == 2


def _escribir_wav_bajo(path: str, sr: int = 16000, amp: float = 0.02) -> None:
    """WAV mono 16k 'tipo dictado con mic bajo': 0.4s de silencio + ráfagas de
    tono modulado a `amp` (0.02 ≈ -34dBFS = mic bajo; 0.005 ≈ -46dBFS = voz
    lejana) + 0.5s de silencio final."""
    frames: list[float] = [0.0] * int(0.4 * sr)
    for i in range(3):
        f = 180 + i * 60
        frames += [
            amp * math.sin(2 * math.pi * f * t / sr) * (0.6 + 0.4 * math.sin(2 * math.pi * 3 * t / sr))
            for t in range(int(0.5 * sr))
        ]
        frames += [0.0] * int(0.15 * sr)
    frames += [0.0] * int(0.5 * sr)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in frames))


def _pico_dbfs(path: str) -> float:
    with wave.open(path) as w:
        raw = w.readframes(w.getnframes())
    muestras = struct.unpack(f"<{len(raw) // 2}h", raw)
    pico = max(abs(m) for m in muestras) / 32768.0
    return 20 * math.log10(pico) if pico > 0 else -120.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg en este entorno")
def test_convertir_a_wav_nivela_mic_bajo():
    tmp = tempfile.mkdtemp(prefix="jarvis_test_audio_")
    src = os.path.join(tmp, "in.wav")
    dst = os.path.join(tmp, "out.wav")
    try:
        _escribir_wav_bajo(src)
        assert _pico_dbfs(src) < -30, "el WAV de entrada debe ser 'mic bajo'"

        rc, stderr = asyncio.run(voice._convertir_a_wav(src, dst, voice._RECORTE))
        assert rc == 0, f"ffmpeg falló con la cadena _RECORTE: {stderr.decode(errors='replace')}"

        # Nivelado: de -34dBFS a la zona sana (>= -14dBFS con margen de codec).
        assert _pico_dbfs(dst) >= -14, "speechnorm debe levantar el mic bajo a niveles sanos"
        # Recortado: los ~0.9s de silencio de las puntas ya no están (el trim
        # deja 150ms de aire por punta a propósito — no comerse fonemas).
        dur = voice._duracion_wav(dst)
        assert dur is not None and dur < 2.5, f"el silencio de las puntas debía recortarse (dur={dur})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg en este entorno")
def test_convertir_a_wav_sobrevive_voz_lejana():
    """Voz LEJANA (pedido 2026-07-17): ráfagas a ~-46dBFS — bajo el umbral viejo
    de -45dB el trim las descartaba como silencio (dictado vacío); con -50dB
    deben SOBREVIVIR al recorte y salir niveladas por speechnorm."""
    tmp = tempfile.mkdtemp(prefix="jarvis_test_audio_")
    src = os.path.join(tmp, "in.wav")
    dst = os.path.join(tmp, "out.wav")
    try:
        _escribir_wav_bajo(src, amp=0.005)          # pico ≈ -46dBFS
        assert _pico_dbfs(src) < -44, "el WAV de entrada debe ser 'voz lejana'"

        rc, stderr = asyncio.run(voice._convertir_a_wav(src, dst, voice._RECORTE))
        assert rc == 0, f"ffmpeg falló con la cadena _RECORTE: {stderr.decode(errors='replace')}"

        dur = voice._duracion_wav(dst)
        assert dur is not None and dur >= 1.2, \
            f"la voz lejana no debe recortarse como silencio (dur={dur})"
        # speechnorm (e=25 → hasta ~+28dB) la levanta a zona utilizable.
        assert _pico_dbfs(dst) >= -22, "speechnorm debe levantar la voz lejana"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
