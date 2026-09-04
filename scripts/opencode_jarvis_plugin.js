// Jarvis — plugin de PROVENANCE para opencode (gemelo del hook PostToolUse de
// Claude Code). Reporta cada edición (edit/write) al enjambre: POST a
// /api/swarm/op con {terminal_id, tool_name, tool_input}, la MISMA forma que
// manda el hook de Claude — así opencode deja de ser un fantasma para la
// coordinación (propiedad, colisiones, jv estado, commit por hunk).
//
// Observador PASIVO: NO cambia el set de herramientas del modelo y JAMÁS tira
// (throw) — un throw en tool.execute.* bloquea la herramienta del agente. Todo
// va envuelto en try/catch y el fetch es fire-and-forget con timeout: si Jarvis
// está caído o lento, el agente sigue igual.
//
// Lo instala Jarvis al boot (plotspace/core/cli_adapters.py) en
// ~/.config/opencode/plugin/ — un solo archivo cubre a TODOS los agentes
// opencode que se lancen en tmux. La identidad viene de JARVIS_TERMINAL_ID, que
// Jarvis inyecta en el entorno de cada pane (terminals.py); sin esa var (opencode
// fuera de Jarvis) el plugin es un no-op.
import { readFile } from "node:fs/promises";

const TID = process.env.JARVIS_TERMINAL_ID;
const PORT = process.env.JARVIS_PORT || "3000";
// Devuelve la respuesta del server (o null). El caller decide si espera: para
// registrar la edición no hace falta, pero el BRIEFING viaja en esa respuesta y
// opencode no tiene hook de prompt — este es su único canal para enterarse de
// quién más está trabajando en el árbol.
async function post(tool_name, tool_input, cwd) {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/api/swarm/op`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ terminal_id: Number(TID), tool_name, tool_input, cwd, source: "opencode" }),
      signal: AbortSignal.timeout(1500),
    });
    return await r.json();
  } catch { return null; }       // Jarvis caído/lento: el agente sigue igual
}

// Texto que el agente tiene que leer: colisión de superficie (borró algo que
// otro usa) y/o briefing del enjambre. El server ya dedupea el briefing por
// firma, así que esto no repite lo mismo en cada edición.
function textoParaElAgente(r) {
  if (!r || typeof r !== "object") return "";
  return [r.aviso_texto, r.briefing].filter(Boolean).map(String).join("\n\n");
}

// Lo pega al output de la herramienta, que es lo que el modelo lee. Defensivo a
// propósito: si esta versión de opencode no expone `output` como string, no se
// toca nada — jamás romper al agente por un aviso.
function inyectar(salida, texto) {
  try {
    if (!texto || !salida || typeof salida !== "object") return;
    if (typeof salida.output === "string") salida.output += `\n\n${texto}`;
    else if (typeof salida.title === "string") salida.metadata = {
      ...(salida.metadata || {}), jarvis: texto };
  } catch { /* nunca romper */ }
}

export const JarvisSwarm = async ({ directory, worktree }) => {
  if (!TID) return {};                       // opencode fuera de Jarvis → no-op
  const cwd = worktree || directory || "";
  const before = new Map();                  // callID → contenido viejo (para write)
  return {
    // El "before" de un write (overwrite total) no viene en los args: se lee del
    // disco ANTES de que se sobrescriba. Para edit no hace falta (trae old+new).
    "tool.execute.before": async ({ tool, callID }, { args }) => {
      try {
        if (tool === "write" && args && args.filePath) {
          before.set(callID, await readFile(args.filePath, "utf8").catch(() => ""));
        }
      } catch { /* observador: jamás romper al agente */ }
    },
    // Reporte tras una edición EXITOSA (este hook no corre si la tool falló).
    // `salida` es el resultado de la herramienta: ahí se le pega el aviso de
    // colisión y el briefing del enjambre — opencode no tiene hook de prompt,
    // así que este es su único canal de entrada de contexto.
    "tool.execute.after": async ({ tool, callID, args }, salida) => {
      try {
        if (!args) return;
        let r = null;
        if (tool === "edit") {
          r = await post("edit", { filePath: args.filePath, oldString: args.oldString,
                                   newString: args.newString }, cwd);
        } else if (tool === "write") {
          r = await post("write", { filePath: args.filePath,
                                    oldString: before.get(callID) ?? "",
                                    content: args.content }, cwd);
          before.delete(callID);
        }
        // `patch` (multi-archivo) queda afuera del piloto: sus args no traen una
        // ruta limpia. edit + write cubren el 99%.
        inyectar(salida, textoParaElAgente(r));
      } catch { /* nunca romper */ }
    },
  };
};
