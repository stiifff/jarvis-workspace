<!-- JARVIS_LIVE_START -->
## 🔴 Coordinación del enjambre — `.jarvis/jv`

Trabajás con otros agentes sobre el MISMO árbol. No leas archivos de estado
para enterarte: preguntá cuando haga falta.

    .jarvis/jv estado      qué tocan los otros y qué te llegó
    .jarvis/jv inbox       tus mensajes nuevos (NO leas .jarvis/MAILBOX.md entero)
    .jarvis/jv msg "<agente>" "<texto>"    dejarle un aviso (NO lo interrumpe)
    .jarvis/jv ask "<agente>" "<pregunta>" preguntarle y ESPERAR la respuesta
    .jarvis/jv claim "<simbolo|archivo|carpeta>"   reservar TU zona
    .jarvis/jv commit -m "<mensaje>"       commitear SOLO lo tuyo, por hunk

Las reglas que sí importan:

1. **Reclamá tu zona antes de empezar**: `jv claim` sobre las funciones, ids o
   archivos que vas a tocar. Se reclama por NOMBRE, nunca por número de línea
   (las líneas se mueven). Lo que nadie reclamó se te concede al instante; si
   necesitás algo más sobre la marcha, también.
2. **Nunca reescribas un archivo entero** que no sea tuyo (`Write` sobre algo
   existente). Editá por zona: dos agentes en zonas distintas del mismo
   archivo conviven bien, pero una sobrescritura con tu copia vieja le borra
   el trabajo al otro sin dejar rastro. Jarvis te frena si pasa.
3. **No borres ni renombres lo que otro reclamó.** Jarvis te lo va a frenar
   antes de escribir, con el nombre del dueño. Si de verdad tiene que irse,
   avisale por `jv msg` y que lo adapte él — sacarlo de golpe le rompe el
   código sin que se entere. (Usar su función está perfecto; nadie te frena.)
4. **Commiteá con `jv commit`**: stagea solo lo tuyo, hunk por hunk. `git add`
   a secas se lleva el trabajo sin commitear del otro que vive en ese archivo.

5. **`msg` deja el aviso; `ask` es el que INTERRUMPE.** Un `jv msg` cae en el
   inbox del otro y se lo lleva cuando retome: **NO lo despierta** (si ya cerró
   su tarea, sigue tranquilo). Si necesitás que reaccione AHORA usá `jv ask`, y
   si le estás pasando trabajo empezá el mensaje con `HANDOFF` — esos dos sí lo
   despiertan. Se hizo así porque el 38% de los mensajes caía en agentes con la
   tarea ya cerrada y les quemaba un turno entero para nada.
   Y el destinatario es **otra terminal, por su nombre EXACTO**: escribirle a
   `@jarvis` o "al sistema" no le llega a NADIE (36 mensajes murieron así).

6. **Un agente 💀 caído no va a volver.** Si `jv estado` te lo marca así, su
   territorio ya está libre y el guard no te bloquea por sus archivos: no le
   pidas permiso ni lo esperes. Y si te aparece una **⚠ Herencia**, eso es
   trabajo sin commitear de alguien que se fue — nadie lo va a venir a buscar:
   si tocás uno de esos archivos, commitealo vos con un mensaje que diga qué es.

7. **Commiteá antes de cerrar tu tarea.** Trabajo real terminado que queda sin
   commitear en este árbol es trabajo que otro barre o hereda. Lo que NO se
   commitea: pruebas de localhost, mockups, capturas y artefactos de build —
   eso va al `.gitignore`, no a un commit.

8. **Tu tarea es TU tarea — no te empecines con la del otro.** Verificás TU
   trabajo; el ajeno solo si su dueño te lo pide o tu tarea depende de él, y
   UNA sola vez. Los acuses (OK/gracias/recibido/"verificado, todo bien") NO
   se contestan: cada mensaje le quema al otro un turno entero. Tope:
   2 mensajes tuyos por hilo con el mismo agente sobre el mismo tema — después
   decidís solo con lo que hay, y si el desacuerdo importa lo dejás en una
   memoria. (Medido acá: 74 mensajes entre DOS agentes en un feature, la
   mayoría re-verificaciones cruzadas y cortesía.)

9. **Jamás esperes el commit ajeno.** ¿Quedaron entrelazados sin commitear en
   el mismo archivo? `jv commit` stagea SOLO tus hunks (usa la provenance
   real): commiteá YA y seguí con lo tuyo. Pedir «commiteá primero y avisame»
   es esperar en promedio UNA HORA (la entrega idle del mailbox tarda eso)
   algo que la herramienta resuelve sola.

`.jarvis/LIVE.md` sigue existiendo (quién es dueño de qué, permisos y
reservas) por si querés el detalle, pero `jv estado` te da lo que necesitás.
<!-- JARVIS_LIVE_END -->