// Jarvis.exe — el shell de escritorio FINO (ventana WebView2 sobre el workspace).
//
// Una app de VERDAD con ventana propia (WebView2, el mismo runtime que usaba
// la app vieja) que muestra el workspace que vive en Linux. Al abrir te recibe
// el MISMO splash de siempre —scripts/jarvis-shell-ui.html, rescatado verbatim
// de f6ffabd8— con su constelación, su "Entrar al workspace" y su zambullida.
//
// NADA nativo adentro: sin motor, sin terminales propias, sin Rust. La lección
// del 2026-08-06 es que el quilombo empezó cuando la app quiso ser más que una
// ventana; esto son 700 KB que solo abren una ventana.
//
// Contrato con el splash (lo que la UI espera del shell, igual que en Tauri):
//   window.__build(n)          número de build en el margen
//   window.__estado(msg, err)  progreso mientras se prepara el motor
//   window.__listo(url)        motor arriba → aparece el botón; navega sola
//
// Se compila con el csc.exe de fábrica de Windows + las DLLs del SDK de
// WebView2 EMBEBIDAS en el exe (un solo archivo, sin instalador):
//   bash scripts/compilar-lanzador-windows.sh
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Pipes;
using System.Net;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

static class Programa
{
    [DllImport("user32.dll")]
    static extern bool SetProcessDpiAwarenessContext(IntPtr valor);

    // Perfil del WebView (cookies, caché): propio de la app, no del browser.
    internal static string CarpetaApp()
    {
        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Jarvis");
    }

    // La 2ª instancia le avisa a la 1ª por esta señal con nombre y se va.
    internal const string SenalMostrar = "JarvisShellMostrar";
    static Mutex unica;

    [STAThread]
    static void Main()
    {
        // INSTANCIA ÚNICA: con la ✕ mandando la app a la bandeja, el doble clic
        // siguiente abría un SEGUNDO Jarvis.exe — dos vigías pisándose las
        // recuperaciones del motor (medido 2026-08-08: health checks de a pares
        // en el log del server). La 2ª instancia despierta a la 1ª y muere.
        bool nueva;
        unica = new Mutex(true, "JarvisShellUnica", out nueva);
        if (!nueva)
        {
            try
            {
                EventWaitHandle ev;
                if (EventWaitHandle.TryOpenExisting(SenalMostrar, out ev)) { ev.Set(); ev.Dispose(); }
            }
            catch { }
            return;
        }

        // Las DLLs del SDK viven AL LADO del exe, como en cualquier app
        // instalada (y como estaba la app vieja). NO se embeben ni se extraen
        // en runtime: un exe sin firma que escupe DLLs a disco es la firma de
        // comportamiento de un dropper y Defender lo mata por heurística
        // (Trojan:Win32/Sabsik.FL.A!ml, visto 2026-08-06).
        try { SetProcessDpiAwarenessContext((IntPtr)(-4)); } catch { }  // PerMonitorV2

        Application.EnableVisualStyles();
        Correr();
    }

    // Separado y sin inline para que el JIT no toque tipos de WebView2 antes de
    // que el AssemblyResolve esté registrado.
    [MethodImpl(MethodImplOptions.NoInlining)]
    static void Correr() { Application.Run(new VentanaJarvis()); }
}

// Paths and wsl.exe flags for any machine: no hardcoded distro/user/repo.
//   JARVIS_WSL_DIR    Linux path to the clone (default: $HOME/jarvis-workspace)
//   JARVIS_WSL_DISTRO WSL distro name (default: whatever `wsl.exe` uses)
static class JarvisWsl
{
    static string repoLinux;
    static string repoUnc;
    static readonly object candado = new object();

    internal static string DistroFlag()
    {
        string d = Environment.GetEnvironmentVariable("JARVIS_WSL_DISTRO");
        if (string.IsNullOrEmpty(d)) return "";
        return "-d " + d.Trim() + " ";
    }

    // Linux path to the repo. Resolves $HOME via wsl when JARVIS_WSL_DIR is unset.
    internal static string RepoLinux()
    {
        lock (candado)
        {
            if (repoLinux != null) return repoLinux;
            string env = Environment.GetEnvironmentVariable("JARVIS_WSL_DIR");
            if (!string.IsNullOrEmpty(env))
            {
                repoLinux = env.Trim().TrimEnd('/');
                return repoLinux;
            }
            string home = Capturar("printf %s \"$HOME\"").Trim()
                .Replace("\r", "").Replace("\n", "");
            if (string.IsNullOrEmpty(home))
                throw new InvalidOperationException("no pude resolver $HOME en WSL");
            repoLinux = home + "/jarvis-workspace";
            return repoLinux;
        }
    }

    // UNC via wslpath so we never hardcode \\wsl.localhost\Distro\home\...
    internal static string ArchivoUnc(string relativo)
    {
        lock (candado)
        {
            if (repoUnc == null)
            {
                string linux = RepoLinux();
                string unc = Capturar("wslpath -w " + ShQuote(linux)).Trim()
                    .Replace("\r", "").Replace("\n", "");
                if (string.IsNullOrEmpty(unc))
                    throw new InvalidOperationException("wslpath -w fallo para " + linux);
                repoUnc = unc.TrimEnd('\\');
            }
            return repoUnc + "\\" + relativo.Replace('/', '\\');
        }
    }

    internal static string ShQuote(string s)
    {
        return "'" + s.Replace("'", "'\\''") + "'";
    }

    internal static void Ejecutar(string comando, int esperaMs)
    {
        var psi = new ProcessStartInfo();
        psi.FileName = "wsl.exe";
        psi.Arguments = DistroFlag() + "-- bash -lc \"" + comando.Replace("\"", "\\\"") + "\"";
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        using (var p = Process.Start(psi)) p.WaitForExit(esperaMs);
    }

    internal static string Capturar(string comando)
    {
        var psi = new ProcessStartInfo();
        psi.FileName = "wsl.exe";
        psi.Arguments = DistroFlag() + "-- bash -lc \"" + comando.Replace("\"", "\\\"") + "\"";
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        using (var p = Process.Start(psi))
        {
            string salida = p.StandardOutput.ReadToEnd();
            if (!p.WaitForExit(60000)) { try { p.Kill(); } catch { } }
            return salida ?? "";
        }
    }
}

class VentanaJarvis : Form
{
    // El health va por 127.0.0.1: el NOMBRE localhost resuelve ::1 primero y
    // WSL no escucha ahí. El workspace SÍ abre por localhost — la Radio
    // necesita ese origen para los embeds de YouTube.
    const string Salud = "http://127.0.0.1:3000/api/health";
    const string Url = "http://localhost:3000";

    // ── Ventana SIN marco nativo ─────────────────────────────────────────
    // Los controles (minimizar/maximizar/cerrar), el arrastre y el resize
    // viven ADENTRO de la app: los dibuja frontend/shell/window-chrome.js en
    // la propia #jw-bar del workspace, como en la app vieja. Acá está el
    // lado nativo de ese puente.
    const int WM_NCLBUTTONDOWN = 0x00A1, WM_GETMINMAXINFO = 0x0024;
    const int WM_NCCALCSIZE = 0x0083, WM_ERASEBKGND = 0x0014, WM_EXITSIZEMOVE = 0x0232;
    const int HTCAPTION = 2;
    // Estilos que FormBorderStyle.None borra y el gesto nativo necesita de vuelta.
    const int WS_MINIMIZEBOX = 0x00020000, WS_MAXIMIZEBOX = 0x00010000;
    const int WS_THICKFRAME = 0x00040000, WS_SYSMENU = 0x00080000;
    const int WS_CAPTION = 0x00C00000, WS_CLIPCHILDREN = 0x02000000;

    [DllImport("user32.dll")] static extern bool ReleaseCapture();
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr wp, IntPtr lp);
    [DllImport("user32.dll")] static extern IntPtr MonitorFromWindow(IntPtr h, int flags);
    [DllImport("user32.dll")] static extern bool GetMonitorInfo(IntPtr mon, ref MONITORINFO mi);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr h, int attr, ref int val, int size);
    // El estado REAL de la ventana según Windows. En WM_NCCALCSIZE no sirve
    // `WindowState`: ese mensaje llega ANTES de que WinForms actualice su
    // propiedad, así que preguntarle a la clase da "Normal" en plena maximización.
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);

    [StructLayout(LayoutKind.Sequential)] struct RECT { public int left, top, right, bottom; }
    [StructLayout(LayoutKind.Sequential)] struct MONITORINFO
    { public int cbSize; public RECT rcMonitor; public RECT rcWork; public int dwFlags; }
    [StructLayout(LayoutKind.Sequential)] struct POINT { public int x, y; }
    // Lo que Windows manda en WM_NCCALCSIZE: rgrc0 es el rect que, al volver,
    // pasa a ser el ÁREA CLIENTE.
    [StructLayout(LayoutKind.Sequential)] struct NCCALCSIZE_PARAMS
    { public RECT rgrc0, rgrc1, rgrc2; public IntPtr lppos; }
    [StructLayout(LayoutKind.Sequential)] struct MINMAXINFO
    { public POINT ptReserved, ptMaxSize, ptMaxPosition, ptMinTrackSize, ptMaxTrackSize; }

    // Nombre de zona → borde nativo que arranca el resize (HTLEFT=10 … HTBOTTOMRIGHT=17)
    static int BordeDeZona(string z)
    {
        switch (z)
        {
            case "w": return 10; case "e": return 11; case "n": return 12;
            case "nw": return 13; case "ne": return 14; case "s": return 15;
            case "sw": return 16; case "se": return 17;
        }
        return 0;
    }

    Microsoft.Web.WebView2.WinForms.WebView2 web;
    readonly PresenciaDiscord presencia = new PresenciaDiscord();

    public VentanaJarvis()
    {
        Text = "Jarvis";
        BackColor = Color.FromArgb(8, 7, 13);       // --obs-0 del splash
        FormBorderStyle = FormBorderStyle.None;     // el chrome lo dibuja la app
        // Abre EN VENTANA (1440×900 centrada), como la app vieja. Nace sin
        // maximizar a propósito: el splash de bienvenida se ve mejor contenido
        // que ocupando la pantalla entera, y maximizar queda a un clic en el
        // botón que dibuja la propia app. Pedido del usuario, 2026-08-07.
        StartPosition = FormStartPosition.CenterScreen;
        // El tamaño se clampea al área de trabajo real: en una pantalla chica
        // —o con la escala de Windows en 125/150%— 1440×900 desborda y la
        // ventana se vería otra vez a pantalla completa, que es justo lo que
        // se quiso evitar. El 90% deja ver el escritorio alrededor.
        Rectangle area = Screen.PrimaryScreen.WorkingArea;
        Size = new Size(Math.Min(1440, (int)(area.Width * 0.9)),
                        Math.Min(900, (int)(area.Height * 0.9)));
        MinimumSize = new Size(900, 600);

        Stream ico = Assembly.GetExecutingAssembly().GetManifestResourceStream("jarvis.ico");
        if (ico != null) Icon = new Icon(ico);
        MontarBandeja();   // necesita el Icon ya cargado
        MontarDespertador();

        web = new Microsoft.Web.WebView2.WinForms.WebView2();
        web.Dock = DockStyle.Fill;
        web.DefaultBackgroundColor = Color.FromArgb(8, 7, 13);
        Controls.Add(web);

        AplicarEsquinas();   // redondeadas en ventana, cuadradas si ocupa todo

        Resize += delegate { AvisarEstado(); };
        // El límite del maximizado se recalcula al cambiar de monitor (cada uno
        // tiene su área de trabajo, y la barra de tareas puede estar en otro lado).
        LocationChanged += delegate { AjustarLimiteMaximizado(); };
        Load += delegate { AjustarLimiteMaximizado(); };
        Load += AlCargar;
    }

    // ── Ventana sin marco A LA VISTA, pero NORMAL para el sistema ─────────
    // `FormBorderStyle.None` no solo saca el marco: le borra al HWND los estilos
    // con los que Windows decide si una ventana puede moverse, restaurarse y
    // snapear. Sin WS_THICKFRAME|WS_MAXIMIZEBOX, el move loop del sistema NO
    // des-maximiza al arrastrar — que es exactamente el gesto que este archivo
    // reimplementaba a mano, con dos movimientos de ventana y sin umbral.
    //
    // Se los devolvemos y el marco se borra VISUALMENTE en WM_NCCALCSIZE (área
    // cliente = ventana entera). Para el usuario sigue sin marco; para el SO es
    // una ventana común, así que aporta gratis: drag-to-restore con su propio
    // umbral y su propio cálculo de posición, Aero Snap, sombra y animaciones.
    // Referencia: melak47/BorderlessWindow y widget_hwnd_utils.cc de Chromium.
    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.Style |= WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX
                      | WS_SYSMENU | WS_CAPTION | WS_CLIPCHILDREN;
            return cp;
        }
    }

    // Sin marco, "maximizar" tapa la barra de tareas: hay que clavar el tamaño
    // al ÁREA DE TRABAJO del monitor donde está la ventana.
    protected override void WndProc(ref Message m)
    {
        // Área cliente = ventana entera: el marco existe para el SO pero no se
        // dibuja. Es lo que mantiene la ventana "sin marco" con los estilos
        // nativos puestos.
        if (m.Msg == WM_NCCALCSIZE && m.WParam != IntPtr.Zero)
        {
            // MAXIMIZADA hay que clampear: con WS_THICKFRAME, Windows agranda la
            // ventana el grosor del marco (medido acá: 1936×1048 en (-8,-8) para
            // un área de trabajo de 1920×1032). Si el cliente copiara ese rect,
            // los íconos anclados a la derecha quedarían 8px FUERA de la pantalla
            // y el borde de abajo taparía la barra de tareas. El cliente se clava
            // al área de trabajo; el marco sobrante queda afuera, invisible.
            if (IsZoomed(Handle) && !enFullscreen)
            {
                var ncp = (NCCALCSIZE_PARAMS)Marshal.PtrToStructure(
                    m.LParam, typeof(NCCALCSIZE_PARAMS));
                IntPtr mon2 = MonitorFromWindow(Handle, 2 /* NEAREST */);
                var mi2 = new MONITORINFO();
                mi2.cbSize = Marshal.SizeOf(typeof(MONITORINFO));
                if (GetMonitorInfo(mon2, ref mi2))
                {
                    ncp.rgrc0 = mi2.rcWork;
                    Marshal.StructureToPtr(ncp, m.LParam, false);
                }
            }
            m.Result = IntPtr.Zero;
            return;
        }

        // El fondo lo pinta WebView2. Que Windows lo borre antes es una pasada
        // de más que se ve como flash al redimensionar. Devolver 1 = "ya está
        // borrado, no hagas nada" (lo mismo hace Chromium en OnEraseBkgnd,
        // con el comentario "Needed to prevent resize flicker").
        if (m.Msg == WM_ERASEBKGND)
        {
            m.Result = (IntPtr)1;
            return;
        }

        // Terminó de moverse/redimensionarse: el navegador pudo quedar con el
        // :hover pegado en lo que estaba bajo el cursor cuando la ventana saltó
        // (durante el gesto nativo NO le llegan eventos de mouse a la página).
        if (m.Msg == WM_EXITSIZEMOVE) LimpiarHover();

        base.WndProc(ref m);
    }

    // Maximizada = EXACTAMENTE el área de trabajo del monitor donde está la
    // ventana. Se hace con `MaximizedBounds` (la API de WinForms, que sí se
    // respeta) y no escribiendo WM_GETMINMAXINFO a mano: con WS_THICKFRAME,
    // Windows llena esa estructura agrandada el grosor del marco y pisaba lo
    // nuestro, escribiéramos antes o después de base.WndProc.
    void AjustarLimiteMaximizado()
    {
        try { MaximizedBounds = Screen.FromHandle(Handle).WorkingArea; }
        catch { }
    }

    // ── Pantalla completa ────────────────────────────────────────────────
    // Distinta de "maximizada": maximizada respeta el área de trabajo (deja ver
    // la barra de tareas, ver WM_GETMINMAXINFO); pantalla completa tapa el
    // monitor ENTERO. Como la ventana ya es sin marco, alcanza con estirar los
    // bounds — no hay que tocar estilos nativos.
    bool enFullscreen;
    FormWindowState estadoPreFS = FormWindowState.Normal;
    Rectangle boundsPreFS;

    void AlternarFullscreen()
    {
        if (!enFullscreen)
        {
            // Des-maximizar ANTES de estirar: entrar a pantalla completa encima
            // de una ventana maximizada dejaba la barra de tareas en NEGRO
            // (glitch de repintado de Windows). Se guarda el estado para volver.
            estadoPreFS = WindowState;
            if (WindowState == FormWindowState.Maximized) WindowState = FormWindowState.Normal;
            boundsPreFS = Bounds;
            Bounds = Screen.FromHandle(Handle).Bounds;      // el monitor completo
            enFullscreen = true;
        }
        else
        {
            // Al salir: primero los bounds chicos y RECIÉN maximizar si venía
            // así. Al revés, Windows restaura el placement guardado y se come
            // el maximize.
            enFullscreen = false;
            Bounds = boundsPreFS;
            WindowState = estadoPreFS;
        }
        AvisarEstado();
    }

    // ── Bandeja del sistema ──────────────────────────────────────────────
    // La ✕ NO mata la app: la manda a la bandeja, viva. De ahí se retoma con un
    // click, y el «Cerrar» del menú es el único punto que apaga de verdad.
    // Pedido del usuario (2026-08-07).
    NotifyIcon bandeja;
    bool cerrandoDeVerdad;

    void MontarBandeja()
    {
        var menu = new ContextMenuStrip();
        menu.Items.Add("Abrir Jarvis", null, delegate { VolverDeBandeja(); });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Cerrar", null, delegate { ApagarTodo(); });

        bandeja = new NotifyIcon();
        bandeja.Icon = Icon;
        bandeja.Text = "Jarvis";
        bandeja.ContextMenuStrip = menu;
        // Un click (o doble) sobre el ícono retoma; el derecho abre el menú.
        bandeja.MouseUp += delegate (object s, MouseEventArgs ev)
        {
            if (ev.Button == MouseButtons.Left) VolverDeBandeja();
        };
        bandeja.Visible = false;
    }

    void IrABandeja()
    {
        // Primero avisarle a la página, MIENTRAS todavía se la puede ejecutar:
        // apaga la radio y lo que gaste de gusto con la ventana escondida.
        // Las terminales siguen: viven en tmux, del lado del server.
        try
        {
            if (web != null && web.CoreWebView2 != null)
                web.CoreWebView2.ExecuteScriptAsync("window.__shellOculto && window.__shellOculto(true)");
        }
        catch { }
        if (bandeja != null) bandeja.Visible = true;
        // Solo Hide(): una ventana oculta ya no figura en la barra de tareas, y
        // tocar ShowInTaskbar en caliente hace que WinForms RECREE el handle —
        // con un WebView2 hospedado adentro eso lo re-parenta y es pedir
        // problemas (medido: el handle viejo quedaba muerto).
        Hide();
    }

    void VolverDeBandeja()
    {
        Show();
        if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
        Activate();
        try
        {
            if (web != null && web.CoreWebView2 != null)
                web.CoreWebView2.ExecuteScriptAsync("window.__shellOculto && window.__shellOculto(false)");
        }
        catch { }
    }

    // La 2ª instancia (doble clic con la app ya viva, quizás en bandeja) no
    // abre otra ventana: manda la señal con nombre y muere — acá se la escucha
    // para retomar la que ya existe.
    EventWaitHandle despertador;
    void MontarDespertador()
    {
        try { despertador = new EventWaitHandle(false, EventResetMode.AutoReset, Programa.SenalMostrar); }
        catch { return; }
        var t = new Thread(delegate ()
        {
            while (true)
            {
                try { despertador.WaitOne(); } catch { return; }
                try { BeginInvoke((Action)VolverDeBandeja); } catch { return; }
            }
        });
        t.IsBackground = true;
        t.Start();
    }

    // Apagar de verdad: la app, el server y la distro. El usuario eligió este
    // alcance sabiendo que se lleva puestas las sesiones tmux de los agentes
    // (2026-08-07). El pkill primero para que uvicorn cierre ordenado; el
    // `wsl --shutdown` después barre todo lo que quede.
    void ApagarTodo()
    {
        cerrandoDeVerdad = true;
        if (bandeja != null) bandeja.Visible = false;
        presencia.Parar();   // que la tarjeta de Discord no sobreviva a la app
        SoltarAncla();   // que el ancla no quede peleándole al --shutdown
        try { Wsl("pkill -f 'uvicorn plotspace' || true", 10000); } catch { }
        try { WslApagar(); } catch { }
        Close();
    }

    static void WslApagar()
    {
        var psi = new ProcessStartInfo();
        psi.FileName = "wsl.exe";
        psi.Arguments = "--shutdown";
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        using (var p = Process.Start(psi)) p.WaitForExit(20000);
    }

    // Alt+F4 y cualquier otro cierre del sistema también van a la bandeja: el
    // único camino que termina el proceso es el «Cerrar» del menú.
    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (!cerrandoDeVerdad && e.CloseReason == CloseReason.UserClosing)
        {
            e.Cancel = true;
            IrABandeja();
            return;
        }
        if (bandeja != null) { bandeja.Visible = false; bandeja.Dispose(); }
        base.OnFormClosing(e);
    }

    // Al soltar el gesto nativo, el :hover del navegador puede haber quedado
    // pegado en el botón que estaba bajo el cursor cuando la ventana cambió de
    // tamaño: durante el move loop de Windows la página NO recibe eventos de
    // mouse, así que nunca se entera de que el cursor ya no está ahí.
    void LimpiarHover()
    {
        if (web == null || web.CoreWebView2 == null) return;
        try { web.CoreWebView2.ExecuteScriptAsync("window.__shellFinArrastre && window.__shellFinArrastre()"); }
        catch { }
    }

    // Esquinas redondeadas de Windows 11: SOLO en ventana. Ocupando toda la
    // pantalla hay que cuadrarlas — el redondeo deja cuatro huecos por los que
    // se ve el ESCRITORIO, y con eso deja de sentirse pantalla completa
    // (reportado por el usuario, 2026-08-07). 1 = DONOTROUND · 2 = ROUND.
    void AplicarEsquinas()
    {
        int pref = (enFullscreen || WindowState == FormWindowState.Maximized) ? 1 : 2;
        try { DwmSetWindowAttribute(Handle, 33, ref pref, 4); } catch { }
    }

    // Último estado avisado al frontend, para no spamear ExecuteScriptAsync en
    // cada tick de un resize con el mouse: solo hablamos cuando algo CAMBIA.
    string ultimoEstado = "";

    void AvisarEstado()
    {
        string maxi = (WindowState == FormWindowState.Maximized) ? "true" : "false";
        string fs = enFullscreen ? "true" : "false";
        string estado = maxi + "|" + fs;
        if (estado == ultimoEstado) return;
        ultimoEstado = estado;
        AplicarEsquinas();
        if (web == null || web.CoreWebView2 == null) return;
        try
        {
            web.CoreWebView2.ExecuteScriptAsync(
                "window.__shellEstado && window.__shellEstado(" + maxi + "," + fs + ")");
            // compat con el contrato viejo del chrome
            web.CoreWebView2.ExecuteScriptAsync(
                "window.__shellMaximizado && window.__shellMaximizado(" + maxi + ")");
        }
        catch { }
    }


    // Los pedidos de la UI: mover, redimensionar y los tres botones.
    void AlMensaje(object o, Microsoft.Web.WebView2.Core.CoreWebView2WebMessageReceivedEventArgs e)
    {
        string m;
        try { m = e.TryGetWebMessageAsString(); } catch { return; }
        if (m == null) return;

        // Mover: solo se prohíbe a PANTALLA COMPLETA (moverla la descoloca).
        // Maximizada NO se toca acá: con los estilos nativos puestos, el move
        // loop de Windows la des-maximiza SOLO —con su umbral de arrastre, así
        // que un click simple ya no la achica— y calcula él la posición. Hacerlo
        // a mano era la causa del parpadeo y del cursor cayendo sobre un ícono.
        //
        // Las coordenadas REALES del cursor van en el lParam: es lo que la doc
        // de WM_NCLBUTTONDOWN espera, y evita el salto por los milisegundos que
        // tarda el mensaje en viajar del JS hasta acá.
        if (m == "drag")
        {
            if (enFullscreen) return;
            Point pc = Cursor.Position;
            IntPtr lp = (IntPtr)((pc.Y << 16) | (pc.X & 0xFFFF));
            ReleaseCapture();
            SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)HTCAPTION, lp);
        }
        else if (m.StartsWith("resize:"))
        {
            if (WindowState == FormWindowState.Maximized || enFullscreen) return;
            int borde = BordeDeZona(m.Substring(7));
            if (borde == 0) return;
            ReleaseCapture();
            SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)borde, IntPtr.Zero);
        }
        else if (m == "min") { WindowState = FormWindowState.Minimized; }
        else if (m == "max")
        {
            // Maximizar "inteligente", como la app vieja: estando en pantalla
            // completa el botón SALE de ahí y deja la ventana chica (restaurada),
            // no maximizada. Fuera de pantalla completa, toggle normal.
            if (enFullscreen)
            {
                estadoPreFS = FormWindowState.Normal;
                AlternarFullscreen();
            }
            else
            {
                WindowState = WindowState == FormWindowState.Maximized
                    ? FormWindowState.Normal : FormWindowState.Maximized;
                AvisarEstado();
            }
        }
        else if (m == "fullscreen") { AlternarFullscreen(); }
        else if (m == "close") { IrABandeja(); }
    }

    // Puente que ve TODA página cargada en la app (splash y workspace): el
    // frontend habla con el shell por acá y en un browser normal no existe,
    // así que window-chrome.js se apaga solo.
    const string Puente =
        "(function(){var wv=window.chrome&&window.chrome.webview;if(!wv)return;" +
        "window.__shell={min:function(){wv.postMessage('min')}," +
        "max:function(){wv.postMessage('max')},close:function(){wv.postMessage('close')}," +
        "drag:function(){wv.postMessage('drag')}," +
        "fullscreen:function(){wv.postMessage('fullscreen')}," +
        "resize:function(d){wv.postMessage('resize:'+d)}};" +
        // el splash trae su propia barra invisible de arrastre (.titlebar)
        "document.addEventListener('mousedown',function(e){if(e.button)return;" +
        "var t=e.target;if(t&&t.closest&&t.closest('.titlebar'))window.__shell.drag()});" +
        "document.addEventListener('dblclick',function(e){var t=e.target;" +
        "if(t&&t.closest&&t.closest('.titlebar'))window.__shell.max()});})()";

    async void AlCargar(object o, EventArgs e)
    {
        string datos = Path.Combine(Programa.CarpetaApp(), "WebView2");
        var entorno = await Microsoft.Web.WebView2.Core.CoreWebView2Environment
            .CreateAsync(null, datos, null);
        await web.EnsureCoreWebView2Async(entorno);

        var s = web.CoreWebView2.Settings;
        s.AreDefaultContextMenusEnabled = false;   // menú de browser: no, es una app
        s.IsStatusBarEnabled = false;
        // Los aceleradores DE BROWSER se apagan: esto es una app, no una pestaña.
        // El que molestaba de verdad era F11 — WebView2 lo tomaba para SU propio
        // fullscreen del contenido (que, con la ventana ya sin marco, no cambia
        // nada a la vista) y competía con el nuestro: hacía falta apretarlo dos
        // veces para que la VENTANA se fuera a pantalla completa. Apagarlos no
        // toca los eventos del DOM, así que los atajos del workspace (Ctrl+P,
        // Ctrl+K, F11) siguen llegando al JS como siempre.
        s.AreBrowserAcceleratorKeysEnabled = false;

        web.CoreWebView2.WebMessageReceived += AlMensaje;
        await web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(Puente);

        // Anclar ANTES de leer el repo / mirar el motor: si la distro está fría,
        // el ancla ya la bootea (y desbloquea wslpath / $HOME); si está tibia,
        // evita que se apague en el medio del chequeo.
        AnclarDistro();
        SembrarToken();   // nunca ver la pantalla de token: la app ya entra logueada

        web.CoreWebView2.NavigateToString(Splash());
        await Task.Delay(150);                     // que el <script> del splash exista

        string build = Build();
        if (build != null) await Js("window.__build && window.__build(" + build + ")");

        if (!await Task.Run((Func<bool>)Responde) && !await LevantarYEsperar()) return;

        // Motor arriba: el splash completa la constelación y muestra el botón.
        // De ahí en adelante manda la UI — el usuario entra cuando quiere.
        await Js("window.__listo && window.__listo('" + Url + "')");
        IniciarVigilancia();
        presencia.Iniciar();   // "Jugando Jarvis" en Discord (si Discord corre)
    }

    // ── Ancla de vida de la distro ───────────────────────────────────────
    // WSL apaga la distro ENTERA ~60s después de que se desconecta su último
    // cliente wsl.exe. El motor que levanta esta app queda setsid'd (NO es
    // cliente) y los wsl.exe que lo lanzan terminan al toque: sin ancla, WSL
    // enterraba al server SANO cada ~85s (journal 2026-08-08: "The system
    // will power off now!" en serie, calzado con cada relanzo del vigía) y el
    // vigía lo revivía en la misma trampa — el loop eterno de "El servidor se
    // está reiniciando". Un cliente wsl.exe dormido, vivo mientras la app
    // viva, sostiene la distro (y las sesiones tmux de los agentes). Mismo
    // truco que wsl-vpnkit. Muere solo con la app (hijo) o con SoltarAncla().
    Process ancla;

    void AnclarDistro()
    {
        try { if (ancla != null && !ancla.HasExited) return; } catch { }
        var psi = new ProcessStartInfo();
        psi.FileName = "wsl.exe";
        psi.Arguments = JarvisWsl.DistroFlag() + "--exec sleep infinity";
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        try { ancla = Process.Start(psi); } catch { ancla = null; }
    }

    void SoltarAncla()
    {
        try { if (ancla != null && !ancla.HasExited) ancla.Kill(); } catch { }
        ancla = null;
    }

    // Levanta el motor y espera a que responda, con DOS intentos de verdad.
    // El de antes lanzaba una sola vez y después solo miraba el reloj 90s: si
    // ese único intento se perdía (distro fría que tardó más que el warm-up),
    // no había segunda oportunidad, solo el cartel de error.
    async Task<bool> LevantarYEsperar()
    {
        for (int intento = 1; intento <= 2; intento++)
        {
            string rotulo = intento == 1 ? "Levantando el motor en WSL… "
                                         : "El motor tarda — reintentando… ";
            await Estado(rotulo.TrimEnd(' ', '…') + "…", false);
            await Task.Run((Action)LevantarServer);
            for (int i = 0; i < 60; i++)
            {
                if (await Task.Run((Func<bool>)Responde)) return true;
                await Estado(rotulo + (i + 1) + "s", false);
                await Task.Delay(1000);
            }
        }
        await Estado("No pude levantar el motor tras dos intentos.\n\n" +
            "Cloná el repo en WSL a ~/jarvis-workspace (o setea JARVIS_WSL_DIR).\n" +
            "Probá a mano:\n  bash ~/jarvis-workspace/scripts/reiniciar-server.sh\n\n" +
            "(log: ~/jarvis-workspace/data/lanzador.log)", true);
        return false;
    }

    // ── Vigilancia del motor ─────────────────────────────────────────────
    // El chequeo de arranque era ÚNICO. Si el motor se caía con la app YA
    // abierta (se cayó WSL, se apagó la distro, se reinició Windows), la
    // ventana se quedaba para siempre en la pantalla "El servidor se está
    // reiniciando" que dibuja el frontend, esperando un boot_id que no iba a
    // llegar porque del otro lado no había nadie. Este timer es el camino de
    // vuelta: detecta la caída y vuelve a levantar el motor solo.
    System.Windows.Forms.Timer vigia;
    bool recuperando;
    int fallos;

    void IniciarVigilancia()
    {
        if (vigia != null) return;
        vigia = new System.Windows.Forms.Timer();
        vigia.Interval = 5000;
        vigia.Tick += Vigilar;
        vigia.Start();
    }

    async void Vigilar(object o, EventArgs e)
    {
        if (recuperando || web == null || web.CoreWebView2 == null) return;
        AnclarDistro();   // si alguien apagó la distro a mano, volver a sostenerla
        if (await Task.Run((Func<bool>)Responde)) { fallos = 0; return; }

        // 6 fallos seguidos (~30s) antes de mover un dedo. El umbral NO es
        // paranoia: "Actualizar ahora" reinicia el server in-place (os.execv) y
        // lo deja caído varios segundos. Con un umbral corto el vigía se metía
        // en el medio de una actualización normal, tiraba el splash encima y
        // llamaba a reiniciar-server.sh, que al encontrar el server YA de vuelta
        // pedía OTRO reinicio. Una caída de verdad (se fue WSL) igual se
        // recupera sola en medio minuto, que es lo que importa.
        if (++fallos < 6) return;

        // recuperando se prende ACÁ, antes de los chequeos lentos: el de WSL
        // tarda hasta ~8s y con el flag apagado otro tick del timer se metía en
        // paralelo y podía disparar una SEGUNDA recuperación encima.
        recuperando = true;
        try
        {
            // Última chance antes de intervenir: si volvió recién, no hacemos nada.
            if (await Task.Run((Func<bool>)Responde)) { fallos = 0; return; }
            // Segunda opinión desde ADENTRO de la distro: si el server está sano
            // y el roto es el puente Windows↔WSL (proxy, firewall de Hyper-V,
            // localhost IPv6), relanzar no arregla nada — y molestar a un motor
            // vivo es exactamente el bug que este vigía no debe causar.
            if (await Task.Run((Func<bool>)RespondeDesdeWsl)) { fallos = 0; return; }

            bool estaba = EnWorkspace();      // ¿ya había entrado, o sigue en el splash?
            web.CoreWebView2.NavigateToString(Splash());
            await Task.Delay(150);
            string build = Build();
            if (build != null) await Js("window.__build && window.__build(" + build + ")");
            await Estado("El motor se cayó — levantándolo…", false);

            if (await LevantarYEsperar())
            {
                fallos = 0;
                if (estaba) web.CoreWebView2.Navigate(Url);   // devolverlo donde estaba
                else await Js("window.__listo && window.__listo('" + Url + "')");
            }
        }
        catch { }
        finally { recuperando = false; }
    }

    // Con NavigateToString el Source queda en about:blank; el workspace es http.
    bool EnWorkspace()
    {
        try { var u = web.Source; return u != null && u.Scheme.StartsWith("http"); }
        catch { return false; }
    }

    Task<string> Js(string codigo) { return web.CoreWebView2.ExecuteScriptAsync(codigo); }

    Task<string> Estado(string texto, bool esError)
    {
        return Js("window.__estado && window.__estado(decodeURIComponent('" +
                  Uri.EscapeDataString(texto) + "')," + (esError ? "true" : "false") + ")");
    }

    bool Responde()
    {
        try
        {
            var req = (HttpWebRequest)WebRequest.Create(Salud);
            req.Proxy = null;       // sin auto-detect de proxy de .NET: es 127.0.0.1
            // 3s y no 1.5: el box sufre CPU starvation medida — bajo carga un
            // health sano puede tardar más que 1.5s y contaba como caída.
            req.Timeout = 3000;
            req.ReadWriteTimeout = 3000;
            using (var resp = (HttpWebResponse)req.GetResponse())
                return (int)resp.StatusCode == 200;
        }
        catch { return false; }
    }

    // Segunda opinión desde ADENTRO de la distro: curl al mismo endpoint. Si
    // esto da 200, el motor está vivo y el roto es el puente Windows↔WSL —
    // relanzar no arregla nada. stdout capturado (el Wsl() común lo tira).
    bool RespondeDesdeWsl()
    {
        try
        {
            var psi = new ProcessStartInfo();
            psi.FileName = "wsl.exe";
            psi.Arguments = JarvisWsl.DistroFlag() + "-- bash -lc \"curl -s -o /dev/null " +
                "-w '%{http_code}' --max-time 3 http://127.0.0.1:3000/api/health\"";
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            using (var p = Process.Start(psi))
            {
                string salida = p.StandardOutput.ReadToEnd();
                if (!p.WaitForExit(8000)) { try { p.Kill(); } catch { } return false; }
                return salida.Trim() == "200";
            }
        }
        catch { return false; }
    }

    // Levanta el motor adentro de WSL. Dos cuidados que no son de adorno:
    //
    // 1) La distro puede estar FRÍA (apagada del todo: se reinició Windows, se
    //    corrió `wsl --shutdown`). Ahí el primer `wsl.exe` no arranca nada: se
    //    le va todo el tiempo booteando la distro. Por eso el warm-up aparte,
    //    con su propia espera larga, ANTES del comando que importa.
    // 2) Todo va en try/catch. Si `wsl.exe` no está en el PATH o la distro no
    //    responde, `Process.Start` TIRA — y antes esa excepción subía sin dueño
    //    desde el Task.Run, dejando la ventana clavada en "Levantando el motor…"
    //    sin decir nunca por qué.
    //
    // El log NO va a /tmp: en WSL /tmp es tmpfs y se borra en CADA arranque de
    // la distro — justo el caso que uno necesita depurar. Va a data/ del repo
    // (gitignored), y en append para conservar los intentos anteriores.
    void LevantarServer()
    {
        try { Wsl("true", 90000); } catch { }          // despierta la distro fría
        try
        {
            // JARVIS_WSL_DIR from Windows is visible inside WSL; otherwise $HOME/jarvis-workspace.
            Wsl("REPO=${JARVIS_WSL_DIR:-$HOME/jarvis-workspace}; " +
                "cd $REPO && mkdir -p data && { date '+== %F %T lanzado por Jarvis.exe'; } " +
                ">>data/lanzador.log 2>&1; cd $REPO && setsid nohup bash " +
                "scripts/reiniciar-server.sh >>data/lanzador.log 2>&1 </dev/null & exit 0", 20000);
        }
        catch { }
    }

    static void Wsl(string comando, int esperaMs)
    {
        JarvisWsl.Ejecutar(comando, esperaMs);
    }

    // ── Sesión: la app entra sola ────────────────────────────────────────
    // La API y los WS exigen la cookie `jarvis_token`. En el browser eso se
    // resuelve una vez por /login#token=…; en la APP no se le pide nada al
    // usuario: el token se lee del repo por el share de WSL y se siembra como
    // cookie del perfil (que es propio del shell, en %LocalAppData%\Jarvis),
    // así el workspace abre logueado desde el primer frame.
    //
    // Sin token legible (distro dormida, ruta movida) no se rompe nada: cae al
    // login normal del workspace.
    void SembrarToken()
    {
        try
        {
            string token = File.ReadAllText(
                JarvisWsl.ArchivoUnc("data/jarvis_token.txt")).Trim();
            if (token.Length == 0) return;
            var cm = web.CoreWebView2.CookieManager;
            foreach (string host in new[] { "localhost", "127.0.0.1" })
            {
                var c = cm.CreateCookie("jarvis_token", token, host, "/");
                c.IsHttpOnly = false;
                c.Expires = DateTime.Now.AddYears(1);
                cm.AddOrUpdateCookie(c);
            }
        }
        catch { }
    }

    // El número de build sale del VERSION del repo, leído por el share de WSL.
    // Si no se puede (distro dormida, ruta movida) el margen queda sin badge:
    // el splash nace con ese bloque hidden.
    static string Build()
    {
        try
        {
            string v = File.ReadAllText(JarvisWsl.ArchivoUnc("VERSION")).Trim();
            int corte = v.LastIndexOf('.');
            string n = corte > 0 ? v.Substring(corte + 1) : v;
            int _;
            return int.TryParse(n, out _) ? n : null;
        }
        catch { return null; }
    }

    static string Splash()
    {
        using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream("ui.html"))
        using (var r = new StreamReader(s, Encoding.UTF8))
            return r.ReadToEnd();
    }
}

// ── Discord Rich Presence ("Jugando Jarvis") ─────────────────────────────────
// Port del presence.rs de la app vieja (5a0bccaf, borrado en dc707f4f): el pipe
// de Discord (discord-ipc-N) vive en Windows y WSL no lo alcanza, así que el
// cliente IPC corre acá, en el lanzador. Se poletea el backend
// (GET /api/system/presence, que arma details/state bilingües + conteo de
// agentes) cada ~15s y se empuja la Activity. El timer "hace cuánto" lo fija el
// arranque de la app (inicioEpoch), estable entre updates. Si Discord no está
// corriendo, se reintenta en silencio: NUNCA rompe el shell.
class PresenciaDiscord
{
    // La App "Jarvis" del Discord Developer Portal: de ahí salen el nombre
    // visible ("Jarvis") y los art assets (el icono). Sin esa App, Discord no
    // muestra nada. Las keys de los assets las decide el backend (large_image /
    // small_image en el JSON) → no se hardcodean acá.
    const string AppId = "1524623263798525982";

    // Discord throttlea las actualizaciones (~1 cada 15s). Con 15s vamos justos
    // y sin spamear; además solo se manda set_activity si algo CAMBIÓ.
    const int PollMs = 15000;
    const string UrlPresence = "http://127.0.0.1:3000/api/system/presence";

    Thread hilo;
    volatile bool parar;
    NamedPipeClientStream pipe;
    string ultimaFirma;   // firma del último envío: no quemar el rate-limit
    string token;
    string rutaToken;     // UNC resuelto a data/jarvis_token.txt (misma fuente que SembrarToken)
    long inicioEpoch;
    readonly JavaScriptSerializer json = new JavaScriptSerializer();

    public void Iniciar()
    {
        if (hilo != null) return;
        inicioEpoch = (long)(DateTime.UtcNow -
            new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
        hilo = new Thread(Bucle);
        hilo.IsBackground = true;
        hilo.Start();
    }

    public void Parar()
    {
        parar = true;
        CerrarPipe();
    }

    void Bucle()
    {
        while (!parar)
        {
            try { Tick(); }
            catch { CerrarPipe(); }   // cualquier hipo → reconectar en la próxima
            Thread.Sleep(PollMs);
        }
    }

    void Tick()
    {
        Dictionary<string, object> datos = TraerPresence();
        if (datos == null) return;                 // motor caído: nada que mostrar
        if (pipe == null && !Conectar()) return;   // Discord cerrado: silencio

        string firma = Campo(datos, "details") + "|" + Campo(datos, "state") + "|" +
                       Campo(datos, "large_image") + "|" + Campo(datos, "small_image") + "|" +
                       Campo(datos, "small_text");
        if (firma == ultimaFirma) return;
        if (MandarActividad(datos)) { ultimaFirma = firma; }
        else { CerrarPipe(); ultimaFirma = null; } // Discord se reinició: reconectar
    }

    // GET al backend con la cookie del token. 401/403 = token regenerado →
    // olvidarlo para releerlo del share en la próxima vuelta.
    Dictionary<string, object> TraerPresence()
    {
        try
        {
            if (token == null)
            {
                try
                {
                    if (rutaToken == null) rutaToken = JarvisWsl.ArchivoUnc("data/jarvis_token.txt");
                    token = File.ReadAllText(rutaToken).Trim();
                }
                catch { token = ""; }
            }
            var req = (HttpWebRequest)WebRequest.Create(UrlPresence);
            req.Proxy = null;
            req.Timeout = 3000;
            req.ReadWriteTimeout = 3000;
            if (token.Length > 0) req.Headers.Add("Cookie", "jarvis_token=" + token);
            using (var resp = (HttpWebResponse)req.GetResponse())
            using (var r = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
            {
                return json.Deserialize<Dictionary<string, object>>(r.ReadToEnd());
            }
        }
        catch (WebException e)
        {
            var r = e.Response as HttpWebResponse;
            if (r != null && ((int)r.StatusCode == 401 || (int)r.StatusCode == 403)) token = null;
            return null;
        }
        catch { return null; }
    }

    // Discord escucha en discord-ipc-0…9 (varios clientes = varios slots).
    bool Conectar()
    {
        for (int i = 0; i < 10; i++)
        {
            var p = new NamedPipeClientStream(".", "discord-ipc-" + i, PipeDirection.InOut);
            try { p.Connect(200); }
            catch { p.Dispose(); continue; }
            pipe = p;
            try
            {
                Mandar(0, "{\"v\":1,\"client_id\":\"" + AppId + "\"}");  // handshake
                if (LeerFrame(2000) != null) return true;                // READY
            }
            catch { }
            CerrarPipe();
        }
        return false;
    }

    bool MandarActividad(Dictionary<string, object> datos)
    {
        var actividad = new Dictionary<string, object>();
        actividad["details"] = Campo(datos, "details");
        actividad["state"] = Campo(datos, "state");
        var tiempos = new Dictionary<string, object>();
        tiempos["start"] = inicioEpoch;
        actividad["timestamps"] = tiempos;
        var assets = new Dictionary<string, object>();
        assets["large_image"] = Campo(datos, "large_image");
        string hover = Campo(datos, "large_text");
        assets["large_text"] = hover.Length > 0 ? hover : "Jarvis";
        // El punto de estado (small_*) es opcional: el backend manda "" cuando
        // no se subieron los assets del punto — ahí no se agrega.
        string punto = Campo(datos, "small_image");
        if (punto.Length > 0)
        {
            assets["small_image"] = punto;
            assets["small_text"] = Campo(datos, "small_text");
        }
        actividad["assets"] = assets;

        var args = new Dictionary<string, object>();
        args["pid"] = Process.GetCurrentProcess().Id;
        args["activity"] = actividad;
        var msg = new Dictionary<string, object>();
        msg["cmd"] = "SET_ACTIVITY";
        msg["args"] = args;
        msg["nonce"] = Guid.NewGuid().ToString();

        try
        {
            Mandar(1, json.Serialize(msg));
            LeerFrame(2000);   // la respuesta se drena y descarta (no llenar el pipe)
            return true;
        }
        catch { return false; }
    }

    // Frame del IPC: int32 LE opcode + int32 LE largo + JSON UTF-8.
    void Mandar(int op, string cuerpo)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(cuerpo);
        byte[] frame = new byte[8 + bytes.Length];
        BitConverter.GetBytes(op).CopyTo(frame, 0);
        BitConverter.GetBytes(bytes.Length).CopyTo(frame, 4);
        bytes.CopyTo(frame, 8);
        pipe.Write(frame, 0, frame.Length);
        pipe.Flush();
    }

    string LeerFrame(int esperaMs)
    {
        byte[] cab = LeerExacto(8, esperaMs);
        if (cab == null) return null;
        int largo = BitConverter.ToInt32(cab, 4);
        if (largo < 0 || largo > 65536) return null;
        byte[] cuerpo = LeerExacto(largo, esperaMs);
        return cuerpo == null ? null : Encoding.UTF8.GetString(cuerpo);
    }

    // Read con timeout de verdad: PipeStream no soporta ReadTimeout, así que se
    // espera el ReadAsync — un Discord mudo no puede colgar el hilo para siempre.
    byte[] LeerExacto(int n, int esperaMs)
    {
        byte[] buf = new byte[n];
        int leidos = 0;
        while (leidos < n)
        {
            Task<int> t;
            try { t = pipe.ReadAsync(buf, leidos, n - leidos); }
            catch { return null; }
            if (!t.Wait(esperaMs)) return null;
            if (t.Result <= 0) return null;
            leidos += t.Result;
        }
        return buf;
    }

    void CerrarPipe()
    {
        try { if (pipe != null) pipe.Dispose(); } catch { }
        pipe = null;
    }

    static string Campo(Dictionary<string, object> d, string k)
    {
        object v;
        return (d != null && d.TryGetValue(k, out v) && v != null) ? v.ToString() : "";
    }
}
