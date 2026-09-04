<!-- JARVIS_PUERTOS_START -->
## 🔌 Regla de puertos (Jarvis)

El **puerto 3000 está PROHIBIDO**: ahí corre Jarvis Workspace (el dashboard
que te está orquestando). Levantar cualquier cosa en el 3000 lo rompe.

Antes de levantar CUALQUIER servidor (dev server, API, preview, http.server):

1. Mirá qué puertos ya están ocupados:

       ss -tlnp 2>/dev/null || lsof -iTCP -sTCP:LISTEN -P -n

2. Elegí un puerto LIBRE que no pise ninguno de los ocupados (para dev
   servers usá el rango 5000-5999 u 8081-8999 si está libre).
3. Pasale el puerto explícito al comando (`--port`, `-p`, `PORT=`); no
   confíes en el default de la herramienta.

NUNCA mates un proceso de un puerto que no levantaste vos: puede ser
Jarvis, otro agente o un preview en uso.
<!-- JARVIS_PUERTOS_END -->