#!/usr/bin/env bash
# Activa los git hooks versionados de Jarvis (guard anti-secretos).
# Corré esto UNA vez después de clonar:  bash scripts/setup-hooks.sh
set -euo pipefail
cd "$(dirname "$0")/.."
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "✓ Hooks activados (core.hooksPath = .githooks)."
echo "  pre-commit: bloquea secretos en lo staged (rutas + patrones + valores reales)"
echo "              + candado de propiedad (no commitear archivos de otro agente, vía LIVE.md)."
echo "  pre-push:   re-escanea TODOS los commits salientes antes de publicar."
