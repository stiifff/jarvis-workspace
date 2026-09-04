# Instalar en Linux

## Con el instalador

```bash
sudo apt install ./plotspace_x.y.z_amd64.deb      # Debian / Ubuntu
chmod +x Jarvis Workspace_x.y.z_amd64.AppImage && ./Jarvis Workspace_x.y.z_amd64.AppImage
```

## Sin instalador (el camino corto para devs)

```bash
uvx plotspace                 # corre sin instalar nada permanente
pipx install plotspace        # o queda como comando
```

Extras, solo si los querés:

```bash
pipx install 'plotspace[voice]'    # dictado con el modelo en tu máquina
pipx install 'plotspace[browser]'  # browser remoto del Web Preview
```

Sin ellos el paquete pesa ~30 MB. Con todos, más de 1 GB — y el dictado
funciona igual usando Groq, que es remoto.

## Desde el repo

```bash
git clone https://github.com/stiifff/jarvis-workspace && cd jarvis-workspace
python3 -m venv venv && source venv/bin/activate
pip install -e .
bash scripts/setup-hooks.sh        # el candado anti-fuga de secretos
plotspace
```

## Qué vas a necesitar además

**Tus propios agentes.** Al primer arranque la app te dice cuáles tenés.

**tmux**, si usás el motor de terminales clásico (el default en Linux hoy).
El motor nuevo no lo necesita: `TERMINALES_MOTOR=conpty`.

## Dónde queda tu cosa

| | |
|---|---|
| Datos de la app | `~/.local/share/plotspace` (o `JARVIS_DATA_DIR`) |
