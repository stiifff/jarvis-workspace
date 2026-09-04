"""BATERÍA E2E de terminales — motor de UN emulador + política B2 (fuente fija / vendor local).

NO la corre pytest (sin prefijo test_): necesita un server VIVO y un browser real.
Uso (contra un server EFÍMERO aislado, jamás contra el :3000 del usuario):
  1. Worktree limpio + data/ fresca:  rm -rf <WT>/data && mkdir <WT>/data
  2. cd <WT> && venv/bin/python -m uvicorn plotspace.main:app --port 5731 --loop asyncio
  3. JARVIS_QA_DIR=<WT> venv/bin/python plotspace/tests/e2e/bateria_terminales.py
  4. Limpiar: matar el server, tmux kill-session de las jarvis_<n> de QA, restaurar <WT>.
Requiere Playwright + chromium (receta WSL: LD_LIBRARY_PATH a las libs NSS extraídas,
ver la memoria playwright-chromium-mismatch). Regla: TODO cambio a terminal*.js /
terminals.py / control_mode.py corre esta batería ANTES de commitear.
"""
# Server de ensayo :5731 (worktree aislado, DB fresca). Basada en bateria_motor.py
# (10/10 del merge del motor) + 3 escenarios nuevos de la tanda B2.
import asyncio, json, os, subprocess, sys

import requests
from playwright.async_api import async_playwright

BASE = os.environ.get('JARVIS_QA_BASE', 'http://127.0.0.1:5731')
WT = os.environ.get('JARVIS_QA_DIR', '/home/user/jarvis/.claude/worktrees/terminales-un-emulador')
TOKEN = open(f'{WT}/data/jarvis_token.txt').read().strip()
CHROMIUM = os.path.expanduser('~/.cache/ms-playwright/chromium-1148/chrome-linux/chrome')

R = {}
MARK = f'RUN{os.getpid()}'   # marker único por corrida: re-runs contra un pane sucio no false-fallan

def tmuxq(ses, fmt):
    return subprocess.run(['tmux', 'display', '-p', '-t', ses, fmt],
                          capture_output=True, text=True).stdout.strip()

def sk(ses, *args):
    subprocess.run(['tmux', 'send-keys', '-t', ses, *args], capture_output=True)

async def xeval(page, tid, expr):
    return await page.evaluate(f'''() => {{
      const i = window.terminalesXterm.get({tid});
      if (!i) return null;
      const term = i.term, buf = term.buffer.active;
      return {expr};
    }}''')

async def texto_buffer(page, tid):
    return await page.evaluate(f'''() => {{
      const i = window.terminalesXterm.get({tid});
      if (!i) return '';
      const b = i.term.buffer.active, out = [];
      for (let n = 0; n < b.length; n++) {{
        const l = b.getLine(n);
        out.push(l ? l.translateToString(true) : '');
      }}
      return out.join('\\n');
    }}''')

async def convergencia(page, tids):
    """[(tid, cols, rows, font, tmux_wxh, converge)] para cada terminal."""
    out = []
    for t in tids:
        d = await xeval(page, t, '({c: term.cols, r: term.rows, f: term.options.fontSize})')
        win = tmuxq(f'jarvis_{t}', '#{window_width}x#{window_height}')
        out.append((t, d['c'], d['r'], d['f'], win, win == f"{d['c']}x{d['r']}"))
    return out

async def main():
    errores = []
    ck = {'jarvis_token': TOKEN}
    r = requests.post(f'{BASE}/api/projects', cookies=ck,
                      json={'nombre': 'bateria-b2', 'ruta': f'{WT}/data/qa-proj'})
    pid = r.json()['id']
    tids = []
    for n in ('QA1', 'QA2', 'QA3', 'QA4'):
        r = requests.post(f'{BASE}/api/projects/{pid}/terminals', cookies=ck,
                          json={'nombre': n, 'tipo_ia': 'manual'})
        tids.append(r.json()['id'])
    assert not (set(tids) & {821, 831, 883}), 'colisión con sesiones vivas'
    tid = tids[0]
    ses = f'jarvis_{tid}'
    print(f'proyecto={pid} terminales={tids}')

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROMIUM, headless=True)
        ctx = await browser.new_context(viewport={'width': 1400, 'height': 800})
        await ctx.add_cookies([{'name': 'jarvis_token', 'value': TOKEN,
                                'domain': '127.0.0.1', 'path': '/'}])
        page = await ctx.new_page()
        page.on('console', lambda m: errores.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: errores.append(str(e)))
        await page.goto(f'{BASE}/workspace?id={pid}', wait_until='domcontentloaded')
        await page.wait_for_timeout(4500)

        # ── B2-1. xterm 100% LOCAL: ni un recurso de CDN para las terminales ──
        recursos = await page.evaluate('''() =>
          performance.getEntriesByType('resource').map(r => r.name)
            .filter(n => n.includes('xterm'))''')
        cdn = [u for u in recursos if 'jsdelivr' in u or 'unpkg' in u or 'cdnjs' in u]
        vendor = [u for u in recursos if '/static/vendor/xterm/' in u]
        tiene_api = await page.evaluate('typeof Terminal !== "undefined" && typeof FitAddon !== "undefined"')
        R['B2_1_xterm_vendoreado'] = not cdn and len(vendor) >= 4 and tiene_api
        print(f'  vendor: {len(vendor)} recursos locales, {len(cdn)} de CDN')

        # ── B2-2. FUENTE FIJA con 4 terminales en columnas angostas + convergencia ──
        conv = await convergencia(page, tids)
        for c in conv: print(f'   t{c[0]}: xterm={c[1]}x{c[2]} font={c[3]} tmux={c[4]} converge={c[5]}')
        R['B2_2_fuente_fija_multi'] = all(c[3] == 13 for c in conv) and all(c[5] for c in conv) \
            and all(c[1] >= 20 for c in conv)

        # ── 1. attach + eco de tipeo ──
        body = page.locator('.terminal-body').first
        await body.click()
        await page.keyboard.type('echo eco-vivo-$((3*4))')
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(900)
        txt = await texto_buffer(page, tid)
        R['1_attach_y_eco'] = 'eco-vivo-12' in txt

        # ── 2. scrollback LOCAL + rueda local sin copy-mode ──
        await page.keyboard.type('seq 1 300')
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(1200)
        antes = await xeval(page, tid, '({len: buf.length, vy: buf.viewportY, rows: term.rows})')
        bb = await body.bounding_box()
        await page.mouse.move(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2)
        for _ in range(12):
            await page.mouse.wheel(0, -120)
            await page.wait_for_timeout(30)
        despues = await xeval(page, tid, '({vy: buf.viewportY})')
        inmode = tmuxq(ses, '#{pane_in_mode}')
        R['2_scroll_local'] = (antes['len'] > antes['rows']
                              and despues['vy'] < antes['vy'] and inmode == '0')
        print(f"  scroll: buffer={antes['len']} filas, viewport {antes['vy']}→{despues['vy']}, copy-mode={inmode}")
        for _ in range(20):
            await page.mouse.wheel(0, 120)
            await page.wait_for_timeout(20)

        # ── 3. rueda DURANTE flood ──
        sk(ses, 'for i in $(seq 1 1500); do echo linea-$i; done', 'Enter')
        await page.wait_for_timeout(400)
        for _ in range(10):
            await page.mouse.wheel(0, -120)
            await page.wait_for_timeout(40)
        await page.wait_for_timeout(2500)
        inmode = tmuxq(ses, '#{pane_in_mode}')
        txt = await texto_buffer(page, tid)
        R['3_rueda_en_flood'] = inmode == '0' and 'linea-1500' in txt
        for _ in range(30):
            await page.mouse.wheel(0, 120)
            await page.wait_for_timeout(15)

        # ── 4. resize en vivo → convergencia exacta en TODAS (sin throttle) ──
        await page.set_viewport_size({'width': 1000, 'height': 650})
        await page.wait_for_timeout(900)
        conv = await convergencia(page, tids)
        R['4_resize_convergente'] = all(c[5] for c in conv) and all(c[3] == 13 for c in conv)
        for c in conv: print(f'   resize t{c[0]}: xterm={c[1]}x{c[2]} font={c[3]} tmux={c[4]} converge={c[5]}')
        await page.set_viewport_size({'width': 1400, 'height': 800})
        await page.wait_for_timeout(900)

        # ── 5. F5 → el scrollback SOBREVIVE (el seed) ──
        await page.reload(wait_until='domcontentloaded')
        await page.wait_for_timeout(4000)
        txt = await texto_buffer(page, tid)
        R['5_f5_restaura_scrollback'] = 'linea-1234' in txt and 'linea-1500' in txt

        # ── 6. TUI estilo Ink + resize A MITAD de redraw ──
        script = (r'frame(){ printf "FRAME<%s> uno\nFRAME<%s> dos\nFRAME<%s> tres\n" $1 $1 $1; };'
                  r'frame A; sleep 2; printf "\033[3A\r\033[0J"; frame B;'
                  r'sleep 2; printf "\033[3A\r\033[0J"; frame C')
        body = page.locator('.terminal-body').first
        await body.click()
        sk(ses, script, 'Enter')
        await page.wait_for_timeout(800)
        await page.set_viewport_size({'width': 900, 'height': 600})
        await page.wait_for_timeout(2500)
        await page.set_viewport_size({'width': 1400, 'height': 800})
        await page.wait_for_timeout(2000)
        txt = await texto_buffer(page, tid)
        frames_a = txt.count('FRAME<A> uno')
        frames_c = txt.count('FRAME<C> uno')
        R['6_tui_resize_mid_render'] = frames_c == 1 and frames_a <= 2
        print(f'  frames: A={frames_a} C={frames_c}')

        # ── 7. alt-screen (less) ──
        sk(ses, 'less /etc/services', 'Enter')
        await page.wait_for_timeout(1200)
        tipo = await xeval(page, tid, '({t: buf.type})')
        en_alt = tipo and tipo['t'] == 'alternate'
        sk(ses, 'q')
        await page.wait_for_timeout(900)
        tipo2 = await xeval(page, tid, '({t: buf.type})')
        txt = await texto_buffer(page, tid)
        R['7_alt_screen'] = en_alt and tipo2['t'] == 'normal' and 'linea-1234' in txt
        print(f"  alt: entró={en_alt} salió={tipo2['t']}")

        # ── 7b. UTF-8 crudo ──
        sk(ses, 'echo "utf8: está ─── ✅ ñandú 🚀"', 'Enter')
        await page.wait_for_timeout(800)
        txt = await texto_buffer(page, tid)
        R['7b_utf8_intacto'] = 'está ─── ✅ ñandú 🚀' in txt and 'est?' not in txt

        # ── 8. monitores intactos (capture == pantalla) ──
        sk(ses, f'echo MONITOR-VE-{MARK}', 'Enter')
        await page.wait_for_timeout(700)
        cap = subprocess.run(['tmux', 'capture-pane', '-p', '-t', ses],
                             capture_output=True, text=True).stdout
        R['8_monitores_intactos'] = f'MONITOR-VE-{MARK}' in cap

        # ── B3-1. rueda RÁPIDA: un notch (120px) = FACTOR_RUEDA×(120/18) = 20 líneas ──
        body = page.locator('.terminal-body').first
        bb = await body.bounding_box()
        await page.mouse.move(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2)
        v0 = await xeval(page, tid, '({vy: buf.viewportY, len: buf.length})')
        await page.mouse.wheel(0, -120)
        await page.wait_for_timeout(150)
        v1 = await xeval(page, tid, '({vy: buf.viewportY})')
        R['B3_1_rueda_rapida'] = v0['len'] > 60 and (v0['vy'] - v1['vy']) == 20
        print(f"  rueda: 1 notch movió {v0['vy'] - v1['vy']} líneas (esperado 20)")
        for _ in range(10):
            await page.mouse.wheel(0, 240)
            await page.wait_for_timeout(20)

        # ── B3-2. HOLD durante selección: el output NO mueve el contenido bajo el drag ──
        await page.mouse.move(bb['x'] + 40, bb['y'] + 60)
        await page.mouse.down()
        await page.mouse.move(bb['x'] + 200, bb['y'] + 90, steps=4)   # drag de selección armado
        await page.wait_for_timeout(120)
        sk(ses, f'echo HOLD-{MARK}-LLEGO', 'Enter')
        await page.wait_for_timeout(700)
        txt_drag = await texto_buffer(page, tid)
        retiene = f'HOLD-{MARK}-LLEGO' not in txt_drag           # retenido mientras se arrastra
        await page.mouse.up()
        await page.wait_for_timeout(600)
        txt_post = await texto_buffer(page, tid)
        R['B3_2_hold_seleccion'] = retiene and f'HOLD-{MARK}-LLEGO' in txt_post
        print(f"  hold: retenido durante drag={retiene}, volcado al soltar={f'HOLD-{MARK}-LLEGO' in txt_post}")

        # ── B2-3. layout persistido con BASURA → se sanea solo, sin romper nada ──
        await page.evaluate(f'''() => localStorage.setItem('jarvis.terminals.layout.{pid}',
          JSON.stringify({{ v: 3, mode: 'libre', free: {{
            '{tids[0]}': {{ x: 'hola', y: 0, w: NaN, h: 1 }},
            '{tids[1]}': {{ x: 4.5, y: -3, w: 9, h: 0.5 }},
            '{tids[2]}': null,
            '{tids[3]}': {{ x: 0, y: 0, w: 0, h: 0 }}
          }} }}))''')
        n_err_antes = len(errores)
        await page.reload(wait_until='domcontentloaded')
        await page.wait_for_timeout(4000)
        conv = await convergencia(page, tids)
        cards_ok = all(c[1] >= 20 and c[2] >= 5 and c[5] for c in conv)
        R['B2_3_layout_basura_saneado'] = cards_ok and len(errores) == n_err_antes
        for c in conv: print(f'   saneado t{c[0]}: xterm={c[1]}x{c[2]} font={c[3]} tmux={c[4]} converge={c[5]}')

        # ── 9. observador (?qa=1) ──
        ctx2 = await browser.new_context(viewport={'width': 1100, 'height': 700})
        await ctx2.add_cookies([{'name': 'jarvis_token', 'value': TOKEN,
                                 'domain': '127.0.0.1', 'path': '/'}])
        page2 = await ctx2.new_page()
        await page2.goto(f'{BASE}/workspace?id={pid}&qa=1', wait_until='domcontentloaded')
        # POLL hasta que el seed pinte (8 attaches simultáneos pueden tardar), y
        # comparar sobre texto APLANADO: en la card angosta del observador el string
        # puede quedar wrapeado en dos filas — eso es render correcto, no un fallo.
        ve = False
        for _ in range(20):
            await page2.wait_for_timeout(500)
            txt2 = (await texto_buffer(page2, tid)).replace('\n', '')
            if f'MONITOR-VE-{MARK}' in txt2: ve = True; break
        await page2.locator('.terminal-body').first.click()
        await page2.keyboard.type('INTRUSO')
        await page2.keyboard.press('Enter')
        await page2.wait_for_timeout(800)
        cap = subprocess.run(['tmux', 'capture-pane', '-p', '-t', ses],
                             capture_output=True, text=True).stdout
        R['9_observador'] = ve and 'INTRUSO' not in cap
        print(f"  observador: ve={ve}, tipeo bloqueado={'INTRUSO' not in cap}")
        await ctx2.close()

        await browser.close()

    R['10_cero_errores_consola'] = not errores
    print('\n=== BATERÍA E2E (motor + B2) ===')
    ok = True
    for k, v in R.items():
        print(f"  {k}: {'OK' if v else 'FALLO'}")
        ok = ok and bool(v)
    if errores:
        print('errores consola:', json.dumps(errores[:6]))
    print('RESULTADO:', 'TODO VERDE' if ok else 'HAY FALLAS')
    sys.exit(0 if ok else 1)

asyncio.run(main())
