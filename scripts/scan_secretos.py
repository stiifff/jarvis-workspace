#!/usr/bin/env python3
"""
Escáner de secretos — el candado anti-fuga del repo (pedido 2026-06-12).

NUNCA debe salir hacia el remoto una API key (Anthropic, MCP, la que sea),
el token de Jarvis ni credenciales de ningún proveedor: son de la persona y
cuestan plata. Este script es la pieza pura; lo corren los hooks de
.githooks/ (pre-commit sobre lo staged, pre-push sobre TODO el rango de
commits salientes) y BLOQUEAN la operación si encuentra algo.

Detecta dos cosas:
1. FORMATOS de credenciales de proveedores + asignaciones genéricas de un
   literal largo a una variable tipo secreto.
2. Los VALORES REALES de los secretos locales (data/jarvis_token.txt,
   plotspace/.env, data/telegram.json) — leídos en runtime, jamás guardados acá.

Uso: <texto por stdin> | python3 scripts/scan_secretos.py [--origen etiqueta]
Exit 0 = limpio · exit 1 = hay secretos (la salida los muestra ENMASCARADOS).

Tests: plotspace/tests/test_scan_secretos.py. Sin dependencias (stdlib pura):
los hooks tienen que andar aunque el venv no esté activado.
"""
import json
import os
import re
import sys

# Los char classes de estas regex hacen que el PROPIO archivo no se
# auto-detecte al commitearse (después de cada prefijo viene '[').
PATRONES = [
    ('api-anthropic',  re.compile(r'sk-ant-[A-Za-z0-9_-]{20,}')),
    ('api-openai',     re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9]{32,}')),
    ('aws-access-key', re.compile(r'AKIA[0-9A-Z]{16}')),
    ('github-token',   re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,}')),
    ('slack-token',    re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}')),
    ('google-api-key', re.compile(r'AIza[0-9A-Za-z_-]{35}')),
    ('telegram-bot',   re.compile(r'\b\d{8,10}:AA[A-Za-z0-9_-]{32,}')),
    ('private-key',    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY')),
    ('jwt',            re.compile(r'eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}')),
    ('asignacion-secreto', re.compile(
        r'(?i)(?:api[_-]?key|secret|token|passwd|password)["\']?\s*[:=]\s*'
        r'["\'][A-Za-z0-9+/=_-]{20,}["\']')),
]

# Claves de .env cuyo valor NO es un secreto (nombres de modelo, flags).
_ENV_NO_SECRETAS = re.compile(r'(?i)(_MODEL|_MOTOR|_ENABLED|_DEBUG|_LEVEL)$')


def valores_locales(raiz):
    """[(nombre, valor)] de los secretos reales del entorno local. Cualquier
    aparición literal de uno de estos en lo que sale del repo es fuga segura,
    tenga el formato que tenga."""
    vals = []
    try:
        tok = open(os.path.join(raiz, 'data', 'jarvis_token.txt'),
                   encoding='utf-8').read().strip()
        if len(tok) > 12:
            vals.append(('token-jarvis', tok))
    except OSError:
        pass
    try:
        for linea in open(os.path.join(raiz, 'plotspace', '.env'),
                          encoding='utf-8'):
            linea = linea.strip()
            if not linea or linea.startswith('#') or '=' not in linea:
                continue
            clave, valor = linea.split('=', 1)
            valor = valor.strip().strip('"\'')
            if len(valor) > 12 and not _ENV_NO_SECRETAS.search(clave.strip()):
                vals.append((f'env-{clave.strip()}', valor))
    except OSError:
        pass
    try:
        cfg = json.load(open(os.path.join(raiz, 'data', 'telegram.json'),
                             encoding='utf-8'))
        if isinstance(cfg.get('token'), str) and len(cfg['token']) > 12:
            vals.append(('telegram-token', cfg['token']))
    except (OSError, ValueError):
        pass
    # Snapshots de cuentas de CLIs (data/cli-accounts/<id>/*.json): los tokens
    # OAuth de claude/codex/gemini/etc. Defensa en profundidad — si alguien los
    # pega por error en un archivo TRACKEADO, el hook lo caza por valor literal.
    try:
        base = os.path.join(raiz, 'data', 'cli-accounts')
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.endswith('.json'):
                    continue
                try:
                    data = json.load(open(os.path.join(root, fn), encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                hojas = []
                _hojas_str(data, hojas)
                for h in hojas:
                    # ~/.claude.json (snapshoteado) trae hojas que NO son
                    # secretos y también viven en el repo (URLs de vendors,
                    # el email del dueño, slugs de skills, nombres humanos)
                    # → bloqueaban el push por falso positivo.
                    if _hoja_inocua(h):
                        continue
                    vals.append(('cli-account', h))
    except OSError:
        pass
    return vals


def _url_inocua(s):
    """URL simple de vendor (dominio + ≤2 segmentos de path, sin query ni
    fragment): metadata, no un secreto. Un webhook con token en el path
    (estilo Slack: /services/T…/B…/xxx, 3+ segmentos) o cualquier URL con
    query string NO es inocua y se sigue cazando por valor literal."""
    if not s.startswith(('http://', 'https://')):
        return False
    if '?' in s or '#' in s:
        return False
    resto = s.split('://', 1)[1]
    segmentos = [p for p in resto.split('/')[1:] if p]
    return len(segmentos) <= 2


_EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

# Un segmento de ruta normal: nombres de carpeta/archivo. Corto y sin la mezcla
# de mayúsculas+dígitos larga que delata un token.
_SEGMENTO_RUTA = re.compile(r'^[A-Za-z0-9._+-]{1,64}$')
_ARRANQUE_RUTA = re.compile(r'^(/|~/|\./|\.\./|[A-Za-z]:[\\/])')


def _parece_token(seg):
    """Segmento con pinta de credencial: largo y con mezcla de mayúsculas,
    minúsculas y dígitos. Ninguna carpeta real se llama así."""
    if len(seg) < 20:
        return False
    return (any(c.isupper() for c in seg) and any(c.islower() for c in seg)
            and any(c.isdigit() for c in seg))


def _ruta_inocua(s):
    """Ruta del filesystem: es metadata, no una credencial.

    Codex guarda en su snapshot los directorios donde trabajaste. Sin esto,
    esas rutas entran como "secretos" y bloquean CUALQUIER commit del repo que
    las mencione — un test, un script, un comentario — con un mensaje que habla
    de API keys y no ayuda a entender nada.

    Dos guardas contra el agujero obvio (esconder el token en la ruta):
    exige 2+ segmentos, y ninguno puede tener pinta de credencial. Y no alcanza
    con empezar con '/': el alfabeto base64 incluye la barra, así que un token
    real puede arrancar igual — por eso cada segmento tiene que ser tame.
    """
    if not _ARRANQUE_RUTA.match(s):
        return False
    # La letra de unidad ("C:") no es un segmento: sacarla antes de partir, o
    # los dos puntos hacen fallar el patrón y toda ruta de Windows queda afuera.
    resto = s[2:] if re.match(r'^[A-Za-z]:[\\/]', s) else s
    segmentos = [p for p in re.split(r'[\\/]+', resto) if p and p not in ('~', '.', '..')]
    if len(segmentos) < 2:
        return False
    return all(_SEGMENTO_RUTA.match(p) and not _parece_token(p) for p in segmentos)


def _hoja_inocua(s):
    """Hojas de snapshots que NO son tokens: URLs simples de vendors, texto
    humano con espacios ("…'s Organization"), emails, y slugs kebab-case sin
    entropía (subagent-driven-development). Un token real (mezcla de mayúsculas
    y dígitos, sin espacios) nunca cae en estas categorías."""
    if _url_inocua(s):
        return True
    if _ruta_inocua(s):                  # dónde trabajaste, no con qué te logueás
        return True
    if any(c.isspace() for c in s):      # los tokens no tienen espacios
        return True
    if _EMAIL_RE.match(s):               # email del dueño de la cuenta
        return True
    # Slug de skill/plugin: palabras minúsculas con 2+ guiones y sin dígitos
    # (subagent-driven-development). Más laxo NO: "snap-zzz…" (1 guión) debe
    # seguir cazándose — lo fija el test de snapshots.
    if re.fullmatch(r'[a-z]+(-[a-z]+){2,}', s):
        return True
    return False


def _hojas_str(obj, out, prof=0):
    """Acumula en `out` los strings hoja >= 20 chars de un JSON anidado (los
    candidatos a token). Acotado en profundidad para no colgarse."""
    if prof > 8 or len(out) > 500:
        return
    if isinstance(obj, str):
        if len(obj) >= 20:
            out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _hojas_str(v, out, prof + 1)
    elif isinstance(obj, list):
        for v in obj:
            _hojas_str(v, out, prof + 1)


def encontrar_secretos(texto, valores=()):
    """Hallazgos en `texto`: [{'patron', 'linea', 'valor'}]. `valores` son
    pares (nombre, valor_real) extra a buscar literal."""
    hallazgos = []
    for num, linea in enumerate(texto.splitlines(), 1):
        for nombre, pat in PATRONES:
            m = pat.search(linea)
            if m:
                hallazgos.append(
                    {'patron': nombre, 'linea': num, 'valor': m.group(0)})
        for nombre, valor in valores:
            if valor and valor in linea:
                hallazgos.append(
                    {'patron': nombre, 'linea': num, 'valor': valor})
    return hallazgos


def _mascara(valor):
    return valor[:8] + '…' + f'({len(valor)} chars)'


def formatear(hallazgos):
    """Reporte legible. El valor completo JAMÁS se imprime."""
    lineas = []
    for h in hallazgos:
        lineas.append(
            f"  línea {h['linea']}: [{h['patron']}] {_mascara(h['valor'])}")
    return '\n'.join(lineas)


def main():
    origen = ''
    if '--origen' in sys.argv:
        origen = sys.argv[sys.argv.index('--origen') + 1]
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    texto = sys.stdin.read()
    hallazgos = encontrar_secretos(texto, valores=valores_locales(raiz))
    if not hallazgos:
        return 0
    print(f'\n🛑 SECRETOS DETECTADOS{f" en {origen}" if origen else ""} '
          f'— operación BLOQUEADA:\n', file=sys.stderr)
    print(formatear(hallazgos), file=sys.stderr)
    print('\nLas API keys / tokens son personales y cuestan plata: NUNCA '
          'van al repo.\nSacá el secreto del cambio (usá plotspace/.env o '
          'data/, que están gitignoreados).\nSi es un falso positivo real, '
          'ajustá el patrón en scripts/scan_secretos.py\n(con su test en '
          'plotspace/tests/test_scan_secretos.py).', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
