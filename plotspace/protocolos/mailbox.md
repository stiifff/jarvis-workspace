<!-- JARVIS_MAILBOX_START -->
## 📬 Mailbox entre agentes (Jarvis)

Para avisarle algo a OTRO agente del workspace (cambiaste una interfaz
que usa, un bug en su área), agregá UNA línea al final de
`.jarvis/MAILBOX.md` con este formato exacto:

    - @TuNombre -> @NombreDelOtro: mensaje corto y accionable

El mailbox es 1-a-1: 1 línea = 1 destinatario CONCRETO, con el nombre
EXACTO de su terminal (tu nombre es el de tu tarea/terminal, ej
"Backend"). NO existe el broadcast: los mensajes a "todos" no le llegan
a nadie. Cero charla ociosa — nada de anunciar avances, agradecer ni
pedir que otros prueben: lo que quieras verificar, hacelo vos mismo en
tu terminal. Para leer, LEÉ tus mensajes con `.jarvis/jv inbox` — NUNCA
releas `.jarvis/MAILBOX.md` entero (llegó a pesar ~14K tokens; el inbox
te da solo lo tuyo, sin leído).
<!-- JARVIS_MAILBOX_END -->