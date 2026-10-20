"""
app_theme.py  –  Estilos visuales de la app (Bitácora / Clásico) y barra superior.

- El modo claro/oscuro lo elige el usuario en el menú ⋮ → Settings de Streamlit
  (los dos temas nativos están definidos en .streamlit/config.toml).
- El estilo (Bitácora o Clásico) se guarda en Cfg_General → clave `ui_estilo`.
- Todo el CSS usa variables (--bg, --card, --text, --primary…); el modo oscuro
  solo redefine esas variables bajo :root[data-ui-mode="dark"].
"""
import os

import streamlit as st

ESTILOS = {
    "bitacora": "Bitácora",
    "clasico":  "Clásico",
}
ESTILO_DEFAULT = "bitacora"

# Páginas de la barra superior: (slug, ruta, etiqueta)
NAV_PAGES = [
    ("inicio",        "streamlit_app.py",         "Inicio"),
    ("gestor",        "pages/1_Gestor_DB.py",     "Gestor DB"),
    ("generador",     "pages/2_Generador.py",     "Generador"),
    ("configuracion", "pages/3_Configuracion.py", "Configuración"),
    ("ayuda",         "pages/4_Ayuda.py",         "Ayuda"),
]

MONO = "'JetBrains Mono', ui-monospace, Consolas, monospace"

# ── Paletas ───────────────────────────────────────────────────────────────────
_T_BITACORA_LIGHT = {
    "bg": "#eef1f6", "card": "#ffffff", "card2": "#f5f7fa",
    "border": "#dde2ea", "border2": "#d5dbe5", "track": "#e4e8ef",
    "text": "#1a2233", "text2": "#3d4556", "muted": "#5b6475",
    "primary": "#1d4a94", "primary-hover": "#163a75", "primary-soft": "#e6edf8", "primary-ink": "#ffffff",
    "chip": "#141a26", "chip-ink": "#ffffff",
    "ok": "#1e6b3c", "ok-bg": "#e3f1e8",
    "warn": "#7a4f00", "warn-bg": "#fdf0d5",
    "err": "#a3261a", "err-bg": "#fbe7e4",
    "used": "#5b3a9e", "used-bg": "#eee8f8",
    "note-bg": "#fbf6ea", "note-border": "#ecdcb4", "note-text": "#4a3a12",
}
_T_BITACORA_DARK = {
    "bg": "#10151f", "card": "#18202d", "card2": "#1d2635",
    "border": "#2a3443", "border2": "#344052", "track": "#2a3443",
    "text": "#e6eaf2", "text2": "#c3cad6", "muted": "#9aa4b5",
    "primary": "#8fb2f5", "primary-hover": "#b3cbf8", "primary-soft": "#1f2f4d", "primary-ink": "#ffffff",
    "chip": "#e6eaf2", "chip-ink": "#10151f",
    "ok": "#7fd19b", "ok-bg": "#16321f",
    "warn": "#f0c674", "warn-bg": "#3a2e12",
    "err": "#f19a8e", "err-bg": "#3d1b17",
    "used": "#c3a8f0", "used-bg": "#2c2240",
    "note-bg": "#2e2814", "note-border": "#5a4b20", "note-text": "#f0e2b8",
}
# Clásico: la paleta original de la app (#2c3e50 / #3498db). Solo modo claro.
_T_CLASICO = {
    "bg": "#ffffff", "card": "#ffffff", "card2": "#f8f9fa",
    "border": "#dee2e6", "border2": "#bdc3c7", "track": "#e9ecef",
    "text": "#2c3e50", "text2": "#444444", "muted": "#666666",
    "primary": "#3498db", "primary-hover": "#2e86c1", "primary-soft": "#e8f4fd", "primary-ink": "#ffffff",
    "chip": "#2c3e50", "chip-ink": "#ffffff",
    "ok": "#1e8449", "ok-bg": "#d5f5e3",
    "warn": "#9a7a00", "warn-bg": "#fef9e7",
    "err": "#922b21", "err-bg": "#fadbd8",
    "used": "#6c3483", "used-bg": "#e8daef",
    "note-bg": "#fef3cd", "note-border": "#f5dfa0", "note-text": "#78350f",
}


def _vars(tokens: dict) -> str:
    return "".join(f"--{k}:{v};" for k, v in tokens.items())


# ── Estilo activo ─────────────────────────────────────────────────────────────
def get_estilo() -> str:
    """Estilo activo: elección de esta sesión > Cfg_General.ui_estilo > Bitácora."""
    est = st.session_state.get("ui_estilo")
    if not est:
        est = st.session_state.get("cfg_general", {}).get("ui_estilo", "")
    return est if est in ESTILOS else ESTILO_DEFAULT


def set_estilo(estilo: str):
    if estilo in ESTILOS:
        st.session_state["ui_estilo"] = estilo


# ── CSS ───────────────────────────────────────────────────────────────────────
# Script que detecta si Streamlit está en claro u oscuro (por el color del texto
# del tema nativo) y marca <html data-ui-mode="dark|light">. Se instala una vez.
_MODE_SCRIPT = """
<span class="ui-mode-probe"></span>
<script>
(function () {
  if (window.__uiModeWatch) return;
  window.__uiModeWatch = true;
  function lum(c) {
    var m = (c || "").match(/[\\d.]+/g);
    if (!m || m.length < 3) return 0;
    return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255;
  }
  function check() {
    var el = document.querySelector('[data-testid="stAppViewContainer"]');
    if (!el) return;
    var mode = lum(getComputedStyle(el).color) > 0.5 ? "dark" : "light";
    var root = document.documentElement;
    if (root.getAttribute("data-ui-mode") !== mode) root.setAttribute("data-ui-mode", mode);
  }
  check();
  setInterval(check, 400);
})();
</script>
"""

_BASE_CSS = """
/* Ocultar el contenedor del script de modo */
.stElementContainer:has(.ui-mode-probe) { display: none !important; }
.mono { font-family: var(--mono) !important; font-variant-numeric: tabular-nums; }

/* Barra superior: navegación */
.st-key-topnav { gap: 2px !important; border-bottom: 1px solid var(--border2); margin: 2px 0 18px 0; flex-wrap: wrap; }
.st-key-topnav [data-testid="stPageLink-NavLink"] {
  background: transparent !important; border-radius: 0 !important;
  padding: 8px 16px !important; margin-bottom: -1px;
  border-bottom: 2px solid transparent;
}
.st-key-topnav [data-testid="stPageLink-NavLink"] * { color: var(--muted) !important; font-weight: 500 !important; }
.st-key-topnav [data-testid="stPageLink-NavLink"]:hover * { color: var(--text) !important; }
.st-key-nav_active [data-testid="stPageLink-NavLink"] { border-bottom-color: var(--primary); }
.st-key-nav_active [data-testid="stPageLink-NavLink"] * { color: var(--text) !important; font-weight: 600 !important; }
"""

_BITACORA_CSS = """
/* ── Lienzo ── */
.stApp, [data-testid="stAppViewContainer"] { background: var(--bg) !important; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stMainBlockContainer"] { padding-top: 2.4rem !important; padding-bottom: 3rem !important; }
[data-testid="stSidebar"] { background: var(--card) !important; }
h1, h2, h3, h4, h5 { letter-spacing: -0.01em; }

/* ── Cabecera de la app ── */
.tb-brand { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.tb-logo { width: 36px; height: 36px; border-radius: 9px; background: var(--chip);
  display: flex; align-items: center; justify-content: center; flex: none; }
.tb-logo svg { stroke: var(--chip-ink); }
.tb-title { font-size: 1.35rem; font-weight: 700; color: var(--text); line-height: 1.2; }
.tb-sub { font-family: var(--mono); font-size: 0.8rem; color: var(--muted); }

/* ── Cabecera de página ── */
.pg-head { margin: 4px 0 14px 0; }
.pg-title { font-size: 1.75rem; font-weight: 700; color: var(--text); line-height: 1.2; letter-spacing: -0.01em; }
.pg-sub { color: var(--muted); font-size: 1rem; margin-top: 4px; }

/* ── Pestañas: la de primer nivel es una tarjeta ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--border); }
[data-testid="stTabs"] [data-baseweb="tab"] { padding: 10px 14px; }
[data-testid="stTabs"] [data-baseweb="tab"] p { font-weight: 500; color: var(--muted); }
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] p { font-weight: 600; color: var(--text); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: var(--primary) !important; }
[data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }
[data-testid="stMainBlockContainer"] [data-testid="stTabs"] {
  background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 6px 22px 18px 22px;
}
[data-testid="stMainBlockContainer"] [data-testid="stTabs"] [data-testid="stTabs"],
[data-testid="stDialog"] [data-testid="stTabs"] {
  background: transparent; border: none; border-radius: 0; padding: 0;
}

/* ── Expanders, métricas, tablas, avisos, ventanas ── */
[data-testid="stExpander"] details { background: var(--card); border: 1px solid var(--border) !important; border-radius: 12px !important; }
[data-testid="stExpander"] summary p { font-weight: 600; }
[data-testid="stMetric"] { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
[data-testid="stMetricLabel"] p { font-size: 0.75rem !important; font-weight: 600 !important; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted) !important; }
[data-testid="stMetricValue"] { font-weight: 700; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border-radius: 10px; overflow: hidden; }
[data-testid="stAlert"] { border-radius: 10px; }
[data-testid="stDialog"] [role="dialog"] { border-radius: 16px; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-tertiary"] { font-weight: 500; }
[data-testid="stBaseButton-primary"] { font-weight: 600; }
[data-testid="stCaptionContainer"] { color: var(--muted); }
hr { border-color: var(--border) !important; }

/* ── Tarjetas de pregunta ── */
.q-card { border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px; margin-bottom: 10px;
  background: var(--card); font-size: 0.92em; line-height: 1.55; color: var(--text); }
.q-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-bottom: 8px; font-size: 0.8em; color: var(--muted); }
.q-num { font-family: var(--mono); font-weight: 600; color: var(--text); font-size: 0.95em; }
.q-num small { color: var(--muted) !important; }
.q-enun { font-weight: 600; margin-bottom: 8px; color: var(--text); }
.q-opts { padding-left: 4px; }
.q-opt { margin: 4px 0; color: var(--text2); }
.q-opt.correct { color: var(--ok); font-weight: 600; }

/* ── Etiquetas ── */
.tag { display: inline-block; border-radius: 999px; padding: 2px 9px; font-size: 0.76em; font-weight: 600; margin-left: 4px; border: none; }
.tag-f { background: var(--ok-bg); color: var(--ok); }
.tag-m { background: var(--primary-soft); color: var(--primary); }
.tag-d { background: var(--err-bg); color: var(--err); }
.tag-u { background: var(--used-bg); color: var(--used); }
.tag-n { background: var(--card2); color: var(--muted); border: 1px solid var(--border); }

/* ── Cabecera de bloque (preview) ── */
.bloque-header { background: var(--card2); color: var(--text); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 16px; margin: 18px 0 10px 0; font-weight: 700; font-size: 0.95em;
  display: flex; justify-content: space-between; align-items: center; }
.bloque-stats { font-size: 0.85em; font-weight: 400; color: var(--muted); }

/* ── Indicadores ── */
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; text-align: left; }
.stat-num { font-size: 2em; font-weight: 700; color: var(--text); line-height: 1.15; }
.stat-label { font-size: 0.72em; color: var(--muted); margin-top: 4px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }

/* ── Filas de bloque (estadísticas) ── */
.blq-row { display: grid; grid-template-columns: minmax(100px,1fr) 60px 60px 60px 70px 130px;
  align-items: center; gap: 8px; padding: 9px 12px; border-radius: 8px; margin-bottom: 5px;
  background: var(--card); border: 1px solid var(--border); font-size: 0.86em; color: var(--text); }
.blq-row:hover { background: var(--card2); }
.blq-name { font-weight: 700; color: var(--text); }
.blq-bar-track { background: var(--track); border-radius: 4px; height: 8px; }
.blq-bar-fill { height: 8px; border-radius: 4px; }

/* ── Conexión ── */
.conn-ok { color: var(--ok); font-weight: 700; }
.conn-err { color: var(--err); font-weight: 700; }
.conn-wait { color: var(--warn); font-weight: 700; }

/* ── Tabla HTML de preguntas ── */
.q-table { width: 100%; border-collapse: collapse; font-size: 0.86em; }
.q-table th { background: var(--card2); color: var(--muted); padding: 9px 10px; text-align: left; position: sticky; top: 0;
  font-size: 0.85em; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; border-bottom: 1px solid var(--border); }
.q-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; color: var(--text); }
.q-table tr:hover td { background: var(--primary-soft); cursor: pointer; }
.q-table tr.selected td { background: var(--primary-soft); }
.q-enun-cell { max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.filter-section { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; }
"""

# Retoques del estilo Clásico sobre el CSS original (APP_CSS)
_CLASICO_CSS = """
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5 {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
[data-testid="stBaseButton-primary"] { background: #3498db !important; border-color: #3498db !important; }
"""


def _tokens_css(estilo: str) -> str:
    if estilo == "clasico":
        return f":root{{{_vars(_T_CLASICO)}--mono:Consolas,'Courier New',monospace;}}"
    return (
        f":root{{{_vars(_T_BITACORA_LIGHT)}--mono:{MONO};"
        # alias de las variables antiguas, por si algún HTML en línea las usa
        "--p:var(--text);--p-light:var(--text2);--acc:var(--primary);"
        "--unused:var(--muted);--bg-light:var(--card2);}"
        f":root[data-ui-mode=\"dark\"]{{{_vars(_T_BITACORA_DARK)}}}"
    )


def apply_theme(page: str = ""):
    """Inyecta el CSS del estilo activo y dibuja la barra superior.

    Llamar en cada página justo después de init_session_state()/handle_oauth_callback().
    `page` es el slug de NAV_PAGES de la página actual (marca la pestaña activa).
    """
    estilo = get_estilo()
    if estilo == "clasico":
        from app_utils import APP_CSS  # import diferido: app_utils importa este módulo
        # Las variables nuevas van antes para que las de APP_CSS (--ok, --border…) prevalezcan
        css = (f"<style>{_tokens_css(estilo)}</style>" + APP_CSS
               + f"<style>{_BASE_CSS}{_CLASICO_CSS}</style>")
    else:
        css = f"<style>{_tokens_css(estilo)}{_BASE_CSS}{_BITACORA_CSS}</style>"
    st.html(css + _MODE_SCRIPT, unsafe_allow_javascript=True)
    render_topbar(page, estilo)


# ── Barra superior ────────────────────────────────────────────────────────────
_LOGO_SVG = (
    '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path>'
    '<path d="M14 3v5h5"></path><path d="M9 13h6"></path><path d="M9 17h4"></path></svg>'
)


def _estado_conexion() -> str:
    ss = st.session_state
    if not ss.get("db_connected"):
        return "sin base de datos · súbela desde la barra lateral"
    fname = (ss.get("_upload_name") or os.path.basename(ss.get("excel_path", "")) or "base_datos.xlsx")
    if ss.get("_gsheets_title"):
        fname = ss["_gsheets_title"]
    n = len(ss.get("df_preguntas", []))
    nb = len(ss.get("bloques", []))
    return f"{fname} · {n} preguntas · {nb} bloques"


def render_topbar(page: str = "", estilo: str = ""):
    """Marca + navegación entre páginas (sustituye a la navegación lateral)."""
    estilo = estilo or get_estilo()
    if estilo == "bitacora":
        asig = st.session_state.get("cfg_general", {}).get("asignatura", "") or ""
        if str(asig) in ("nan", "None"):
            asig = ""
        title = "Generador de Exámenes" + (f" · {asig}" if asig else "")
        st.markdown(
            f'<div class="tb-brand"><div class="tb-logo">{_LOGO_SVG}</div><div>'
            f'<div class="tb-title">{title}</div>'
            f'<div class="tb-sub">{_estado_conexion()}</div></div></div>',
            unsafe_allow_html=True,
        )
    with st.container(horizontal=True, gap=None, key="topnav"):
        for slug, path, label in NAV_PAGES:
            key = "nav_active" if slug == page else f"nav_{slug}"
            with st.container(key=key, width="content"):
                st.page_link(path, label=label)
