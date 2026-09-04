# Instalar en Windows

## Con el instalador

Bajá `Jarvis Workspace_x.y.z_x64-setup.exe` de
[Releases](https://github.com/stiifff/jarvis-workspace/releases) y ejecutalo.

No hace falta WSL. Tampoco Python ni Node: viajan adentro.

## Qué vas a necesitar además

**Tus propios agentes.** Jarvis Workspace los orquesta pero no los redistribuye: son
producto de Anthropic, OpenAI o Google, con su licencia y su login. Al primer
arranque la app te dice cuáles tenés y te ofrece instalar los que faltan.

**Git for Windows**, si vas a usar Claude Code: su herramienta Bash se apoya
en él. Está en prácticamente toda máquina de desarrollo.

## Shells

Las terminales nacen en **PowerShell**. En el selector también están cmd, Git
Bash y cada distro de WSL que tengas instalada — podés tener un agente en
PowerShell y otro en Ubuntu sobre el mismo proyecto.

Si tu proyecto necesita herramientas de Unix (`make`, `grep`, scripts de shell)
o tiene un `node_modules` gigante, abrilo con un perfil de WSL: el toolchain
está completo y el I/O es más rápido que en NTFS.

## Dónde queda tu cosa

| | |
|---|---|
| Tus proyectos | donde vos quieras (`C:\Users\<vos>\Proyectos`, por ejemplo) |
| Datos de la app | `%LOCALAPPDATA%\Jarvis Workspace` |

## Si venías usando la versión con WSL

Se puede traer todo: la base de datos (unos cientos de KB) tiene tus proyectos
y tu historial, y `data/cli-accounts/` tus sesiones ya iniciadas. Los proyectos
podés moverlos a `C:\` o dejarlos en la distro y abrirlos con perfil WSL.
