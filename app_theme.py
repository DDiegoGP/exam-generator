"""
app_theme.py  –  Estilos visuales de la app (Bitácora / Clásico) y barra superior.

- El modo claro/oscuro lo elige el usuario en el menú ⋮ → Settings de Streamlit
  (los dos temas nativos están definidos en .streamlit/config.toml).
- El estilo (Bitácora o Clásico) se guarda en Cfg_General → clave `ui_estilo`.
- Todo el CSS usa variables (--bg, --card, --text, --primary…); el modo oscuro
  solo redefine esas variables bajo :root[data-ui-mode="dark"].
- Los colores en línea de las páginas se escriben como var(--token, #original):
  en Clásico no se definen las variables, así que se usa el color original.
"""
import functools
import os
import re

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

ESTILOS = {
    "bitacora": "Bitácora",
    "clasico":  "Clásico",
}
ESTILO_DEFAULT = "bitacora"

PREVIEWS = {
    "ventana": "Ventana",
    "panel":   "Panel junto a la tabla",
}
PREVIEW_DEFAULT = "ventana"

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
    "text": "#1a2233", "text2": "#3d4556", "muted": "#5b6475", "faint": "#7d8596",
    "primary": "#1d4a94", "primary-hover": "#163a75", "primary-soft": "#e6edf8", "primary-ink": "#ffffff",
    "chip": "#141a26", "chip-ink": "#ffffff", "btn": "#1d4a94",
    "ok": "#1e6b3c", "ok-bg": "#e3f1e8",
    "warn": "#7a4f00", "warn-bg": "#fdf0d5",
    "err": "#a3261a", "err-bg": "#fbe7e4",
    "used": "#5b3a9e", "used-bg": "#eee8f8",
    "note-bg": "#fbf6ea", "note-border": "#ecdcb4", "note-text": "#4a3a12",
}
_T_BITACORA_DARK = {
    "bg": "#10151f", "card": "#18202d", "card2": "#1d2635",
    "border": "#2a3443", "border2": "#344052", "track": "#2a3443",
    "text": "#e6eaf2", "text2": "#c3cad6", "muted": "#9aa4b5", "faint": "#7d889b",
    "primary": "#8fb2f5", "primary-hover": "#b3cbf8", "primary-soft": "#1f2f4d", "primary-ink": "#ffffff",
    "chip": "#e6eaf2", "chip-ink": "#10151f", "btn": "#4f80dd",
    "ok": "#7fd19b", "ok-bg": "#16321f",
    "warn": "#f0c674", "warn-bg": "#3a2e12",
    "err": "#f19a8e", "err-bg": "#3d1b17",
    "used": "#c3a8f0", "used-bg": "#2c2240",
    "note-bg": "#2e2814", "note-border": "#5a4b20", "note-text": "#f0e2b8",
}


def _vars(tokens: dict) -> str:
    return "".join(f"--{k}:{v};" for k, v in tokens.items())


# ── Preferencias activas ──────────────────────────────────────────────────────
def _pref(key: str, valid: dict, default: str) -> str:
    """Elección de esta sesión > Cfg_General[key] > valor por defecto."""
    val = st.session_state.get(key)
    if not val:
        val = st.session_state.get("cfg_general", {}).get(key, "")
    return val if val in valid else default


def get_estilo() -> str:
    return _pref("ui_estilo", ESTILOS, ESTILO_DEFAULT)


def set_estilo(estilo: str):
    if estilo in ESTILOS:
        st.session_state["ui_estilo"] = estilo


def get_preview_mode() -> str:
    """Cómo se abre la vista previa de una pregunta en Generador → Selección."""
    return _pref("ui_preview", PREVIEWS, PREVIEW_DEFAULT)


def set_preview_mode(modo: str):
    if modo in PREVIEWS:
        st.session_state["ui_preview"] = modo


def render_estilo_quick():
    """Selector rápido de estilo (barra lateral). Sincronizado con Configuración → Apariencia."""
    # Botones en vez de un radio: un radio en la barra lateral puede verse con la
    # opción equivocada al cambiar de página; un botón no guarda estado en el navegador.
    estilo = get_estilo()
    st.caption("Estilo")
    cols = st.columns(len(ESTILOS))
    for col, (clave, nombre) in zip(cols, ESTILOS.items()):
        activo = clave == estilo
        if col.button(nombre, key=f"btn_sb_estilo_{clave}", type="primary" if activo else "secondary",
                      use_container_width=True) and not activo:
            set_estilo(clave)
            st.rerun()


# ── Etiquetas sin emojis (solo Bitácora) ──────────────────────────────────────
_EMOJI = ("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿"
          "←-⇿■-◿ℹ™️‍⃣]")
_LEAD = re.compile(rf"^\s*(?:{_EMOJI}+\s*\+?\s*)+")
_MD_LEAD = re.compile(rf"^(\s*(?:\*\*|#{{1,6}}\s+))\s*(?:{_EMOJI}+\s*)+")


def clean_label(s):
    """Quita los emojis iniciales de una etiqueta; si no queda texto, la deja igual."""
    if not isinstance(s, str):
        return s
    t = _LEAD.sub("", s)
    return t if t.strip() else s


def _clean_md(s):
    if not isinstance(s, str):
        return s
    return _MD_LEAD.sub(r"\1", s)


_LABEL_METHODS = [
    "button", "download_button", "form_submit_button", "expander", "popover",
    "selectbox", "multiselect", "radio", "checkbox", "toggle", "text_input",
    "text_area", "number_input", "date_input", "file_uploader", "slider",
    "segmented_control", "pills", "subheader", "header",
]


# Colores de los gráficos Plotly en Bitácora: tonos que se leen en claro y en oscuro
_CHART_COLORS = {
    "#27ae60": "#3f9d6b",                 # fácil
    "#f39c12": "#4f80dd",                 # media
    "#c0392b": "#c4505c",                 # difícil
    "#3498db": "#4f80dd",                 # seleccionadas / usadas
    "#e0e7ef": "rgba(127,140,160,0.30)",  # disponibles / resto
    "#ecf0f1": "rgba(127,140,160,0.30)",
    "#e9ecef": "rgba(127,140,160,0.20)",  # rejilla
}


def _recolor_fig(fig):
    """Cambia los colores fijos de una figura Plotly por los de Bitácora (en el sitio)."""
    def m(c):
        return _CHART_COLORS.get(c.lower(), c) if isinstance(c, str) else c
    # cada paso por separado: una figura rara nunca debe impedir que se dibuje
    for tr in getattr(fig, "data", []):
        try:
            if tr.type == "pie":
                if tr.marker.colors is not None:
                    tr.marker.colors = [m(c) for c in tr.marker.colors]
            elif isinstance(tr.marker.color, str):
                tr.marker.color = m(tr.marker.color)
        except Exception:
            pass
    for ax in ("xaxis", "yaxis"):
        try:
            a = fig.layout[ax]
            if isinstance(a.gridcolor, str):
                a.gridcolor = m(a.gridcolor)
        except Exception:
            pass
    return fig


def _install_label_filter():
    """Envuelve los widgets de Streamlit para limpiar la etiqueta en el estilo Bitácora.

    Solo cambia el texto mostrado (primer argumento); opciones, claves y valores no se tocan.
    """
    if getattr(DeltaGenerator, "_ui_label_filter", False):
        return

    def wrap(fn, cleaner, kw_names):
        @functools.wraps(fn)
        def inner(self, *args, **kwargs):
            if get_estilo() == "bitacora":
                if args:
                    args = (cleaner(args[0]),) + args[1:]
                else:
                    for k in kw_names:
                        if k in kwargs:
                            kwargs[k] = cleaner(kwargs[k])
                            break
            return fn(self, *args, **kwargs)
        return inner

    names = list(_LABEL_METHODS) + ["tabs", "markdown", "plotly_chart"]
    for n in _LABEL_METHODS:
        setattr(DeltaGenerator, n, wrap(getattr(DeltaGenerator, n), clean_label, ("label", "body")))
    setattr(DeltaGenerator, "tabs",
            wrap(DeltaGenerator.tabs, lambda xs: [clean_label(x) for x in xs], ("tabs",)))
    setattr(DeltaGenerator, "markdown", wrap(DeltaGenerator.markdown, _clean_md, ("body",)))
    setattr(DeltaGenerator, "plotly_chart",
            wrap(DeltaGenerator.plotly_chart, _recolor_fig, ("figure_or_data",)))
    # st.button, st.tabs… son métodos ya ligados al contenedor principal: re-ligarlos
    for n in names:
        setattr(st, n, getattr(st._main, n))

    _orig_dialog = st.dialog

    @functools.wraps(_orig_dialog)
    def dialog(title, *args, **kwargs):
        if get_estilo() == "bitacora":
            title = clean_label(title)
        return _orig_dialog(title, *args, **kwargs)

    st.dialog = dialog
    DeltaGenerator._ui_label_filter = True


# ── Componentes HTML ──────────────────────────────────────────────────────────
def kpi_html(items: list, compact: bool = False) -> str:
    """Fila de indicadores. items = [(etiqueta, valor, subtítulo, acento_bool), …]"""
    cards = []
    for label, value, sub, accent in items:
        val_cls = "kpi-val acc" if accent else "kpi-val"
        sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
        cards.append(f'<div class="kpi"><div class="kpi-lbl">{label}</div>'
                     f'<div class="{val_cls}">{value}</div>{sub_html}</div>')
    return f'<div class="kpi-grid{" compact" if compact else ""}">{"".join(cards)}</div>'


def _txt(v) -> str:
    v = str(v if v is not None else "").strip()
    return "" if v in ("nan", "None", "NaT") else v


def question_detail_html(row: dict) -> str:
    """Cabecera de una pregunta (ventana del Gestor, estilo Bitácora):
    ID + bloque·tema + etiquetas, enunciado, opciones y cuatro recuadros."""
    import json
    from app_utils import nombre_bloque, nombre_tema, nombre_objetivo  # import diferido (ciclo)

    pid  = _txt(row.get("ID_Pregunta"))
    dif  = _txt(row.get("dificultad")) or "Media"
    dl   = dif.lower().replace("á", "a").replace("í", "i")
    tag  = {"facil": "tag-f", "media": "tag-m", "dificil": "tag-d"}.get(dl, "tag-m")
    uso  = _txt(row.get("usada"))
    sol  = bool(_txt(row.get("solucion")))
    obj  = _txt(row.get("objetivo"))
    com  = _txt(row.get("comentario"))
    ops  = row.get("opciones_list", []) or []
    if isinstance(ops, str):
        try:
            ops = json.loads(ops)
        except Exception:
            ops = []
    corr = {"A": 0, "B": 1, "C": 2, "D": 3}.get(_txt(row.get("letra_correcta")).upper(), 0)

    tags = (f'<span class="tag {tag}">{dif}</span>'
            + (f'<span class="tag tag-u">Usada {uso}</span>' if uso else '<span class="tag tag-n">Nueva</span>')
            + ('<span class="tag tag-f">Con solución</span>' if sol else '<span class="tag qd-pend">Sin solución</span>'))
    opts = "".join(
        f'<div class="qd-opt{" ok" if i == corr else ""}">{l}) {ops[i] if i < len(ops) else ""}'
        f'{" ✓" if i == corr else ""}</div>'
        for i, l in enumerate("abcd")
    )

    def tile(lbl, val, cls=""):
        return f'<div class="qd-tile"><div class="qd-tl">{lbl}</div><div class="qd-tv {cls}">{val}</div></div>'

    tiles = (tile("Último uso", uso or "nunca", "mono" if uso else "muted")
             + tile("Objetivo", nombre_objetivo(obj) if obj else "sin asignar", "" if obj else "muted")
             + tile("Etiqueta", com or "sin etiqueta", "" if com else "muted")
             + tile("Solución", "disponible" if sol else "pendiente", "okc" if sol else "pend"))
    meta = f'{nombre_bloque(_txt(row.get("bloque")))} · {nombre_tema(_txt(row.get("Tema")))}'
    return (f'<div class="qd-card"><div class="qd-head"><div><span class="qd-id">{pid}</span>'
            f'<span class="qd-meta">{meta}</span></div><div>{tags}</div></div>'
            f'<div class="qd-enun">{_txt(row.get("enunciado"))}</div>{opts}</div>'
            f'<div class="qd-tiles">{tiles}</div>')


def bar_html(pct: float) -> str:
    pct = max(0, min(100, pct))
    return f'<div class="bar"><div style="width:{pct:.0f}%"></div></div>'


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

# Común a los dos estilos (con colores de reserva para Clásico, que no define variables)
_BASE_CSS = """
.stElementContainer:has(.ui-mode-probe) { display: none !important; }
.mono { font-family: var(--mono, Consolas, monospace) !important; font-variant-numeric: tabular-nums; }

.st-key-topnav { gap: 2px !important; border-bottom: 1px solid var(--border2, #dee2e6); margin: 2px 0 18px 0; flex-wrap: wrap; }
.st-key-topnav [data-testid="stPageLink-NavLink"] {
  background: transparent !important; border-radius: 0 !important;
  padding: 8px 16px !important; margin-bottom: -1px;
  border-bottom: 2px solid transparent;
}
.st-key-topnav [data-testid="stPageLink-NavLink"] * { color: var(--muted, #666) !important; font-weight: 500 !important; }
.st-key-topnav [data-testid="stPageLink-NavLink"]:hover * { color: var(--text, #2c3e50) !important; }
.st-key-nav_active [data-testid="stPageLink-NavLink"] { border-bottom-color: var(--primary, #3498db); }
.st-key-nav_active [data-testid="stPageLink-NavLink"] * { color: var(--text, #2c3e50) !important; font-weight: 600 !important; }
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
.sec-title { font-size: 1.05rem; font-weight: 700; color: var(--text); margin: 0 0 10px 0; }
.sec-meta { font-size: 0.85rem; color: var(--muted); font-weight: 400; margin-left: 6px; }

/* ── Indicadores y barras ── */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 4px 0 18px 0; }
.kpi { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }
.kpi-lbl { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.kpi-val { font-size: 2rem; font-weight: 700; color: var(--text); line-height: 1.15; margin-top: 4px; font-variant-numeric: tabular-nums; }
.kpi-val.acc { color: var(--primary); }
.kpi-sub { font-size: 0.82rem; color: var(--muted); margin-top: 2px; }
.bar { height: 7px; background: var(--track); border-radius: 4px; overflow: hidden; }
.bar > div { height: 100%; background: var(--primary); border-radius: 4px; }

/* ── Tarjeta genérica y listas (Inicio) ── */
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 18px 22px; margin-bottom: 16px; }
.cov-row { display: grid; grid-template-columns: minmax(90px, 1.2fr) minmax(0, 3fr) 70px; gap: 14px; align-items: center; padding: 7px 0; }
.cov-name { font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cov-num { font-family: var(--mono); font-size: 0.82rem; color: var(--muted); text-align: right; }
.list-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px; align-items: center;
  padding: 10px 0; border-bottom: 1px solid var(--border); }
.list-row:last-child { border-bottom: none; }
.list-date { font-family: var(--mono); font-size: 0.82rem; font-weight: 600; color: var(--text); }
.list-title { color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.list-meta { font-family: var(--mono); font-size: 0.8rem; color: var(--muted); }
.step-n { font-family: var(--mono); font-size: 0.8rem; font-weight: 600; color: var(--muted); }
.pill { display: inline-block; font-size: 0.76rem; font-weight: 600; border-radius: 999px; padding: 2px 10px;
  background: var(--primary-soft); color: var(--primary); }
[class*="st-key-home_mod_"] { background: var(--card); border-color: var(--border) !important; border-radius: 12px !important; }
.empty-box { background: var(--card); border: 1px dashed var(--border2); border-radius: 12px; padding: 34px 18px;
  text-align: center; color: var(--muted); }

/* ── Portada de Ayuda ── */
.help-hero { background: var(--card) !important; border: 1px solid var(--border); box-shadow: none !important;
  color: var(--text) !important; padding: 26px 30px !important; }
.help-hero h2 { color: var(--text) !important; }
.help-hero p { color: var(--muted) !important; opacity: 1 !important; }

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

/* ── Indicadores antiguos ── */
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

/* ── Detalle de pregunta (ventana del Gestor) ── */
.qd-card { border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; background: var(--card); color: var(--text); }
.qd-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; }
.qd-id { font-family: var(--mono); font-size: 1.05rem; font-weight: 600; margin-right: 10px; }
.qd-meta { color: var(--muted); }
.qd-enun { font-weight: 600; font-size: 1rem; line-height: 1.5; margin-bottom: 10px; }
.qd-opt { color: var(--text2); margin: 5px 0; }
.qd-opt.ok { color: var(--ok); font-weight: 600; }
.tag.qd-pend { background: var(--warn-bg); color: var(--warn); }
.qd-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 14px 0 6px; }
.qd-tile { border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; background: var(--card); }
.qd-tl { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.qd-tv { font-size: 1.05rem; font-weight: 600; margin-top: 6px; color: var(--text); }
.qd-tv.muted { color: var(--muted); }
.qd-tv.okc { color: var(--ok); }
.qd-tv.pend { color: var(--warn); }
.st-key-btn_del_q button { color: var(--err) !important; border-color: var(--err-bg) !important; }

/* ── Radios con forma de píldora (uso) y de botones unidos (dificultad) ── */
.st-key-man_uso_box [role="radiogroup"], .st-key-man_dif_box [role="radiogroup"] { flex-wrap: wrap; }
.st-key-man_uso_box [role="radiogroup"] { gap: 8px !important; }
.st-key-man_dif_box [role="radiogroup"] { gap: 0 !important; }
.st-key-man_uso_box label[data-baseweb="radio"], .st-key-man_dif_box label[data-baseweb="radio"] {
  margin: 0 !important; padding: 5px 13px !important; background: var(--card);
  border: 1px solid var(--border2); cursor: pointer; }
.st-key-man_uso_box label[data-baseweb="radio"] { border-radius: 999px; }
.st-key-man_dif_box label[data-baseweb="radio"] { border-radius: 0; margin-left: -1px !important; }
.st-key-man_dif_box label[data-baseweb="radio"]:first-child { border-radius: 9px 0 0 9px; margin-left: 0 !important; }
.st-key-man_dif_box label[data-baseweb="radio"]:last-child { border-radius: 0 9px 9px 0; }
.st-key-man_uso_box label[data-baseweb="radio"] > div:first-child,
.st-key-man_dif_box label[data-baseweb="radio"] > div:first-child { display: none; }
.st-key-man_uso_box label[data-baseweb="radio"] > div:last-child,
.st-key-man_dif_box label[data-baseweb="radio"] > div:last-child { padding-left: 0 !important; margin-left: 0 !important; }
.st-key-man_uso_box label[data-baseweb="radio"] p, .st-key-man_dif_box label[data-baseweb="radio"] p { margin: 0; font-size: 0.9rem; }
.st-key-man_uso_box label[data-baseweb="radio"]:has(input:checked) { background: var(--chip); border-color: var(--chip); }
.st-key-man_uso_box label[data-baseweb="radio"]:has(input:checked) p { color: var(--chip-ink) !important; font-weight: 600; }
.st-key-man_dif_box label[data-baseweb="radio"]:has(input:checked) { background: var(--btn); border-color: var(--btn); position: relative; }
.st-key-man_dif_box label[data-baseweb="radio"]:has(input:checked) p { color: #ffffff !important; font-weight: 600; }

/* ── Botones unidos para cualquier radio dentro de un contenedor con clave seg_* ── */
[class*="st-key-seg_"] [role="radiogroup"] { gap: 0 !important; flex-wrap: wrap; }
[class*="st-key-seg_"] label[data-baseweb="radio"] { margin: 0 0 0 -1px !important; padding: 6px 13px !important;
  background: var(--card); border: 1px solid var(--border2); border-radius: 0; cursor: pointer; }
[class*="st-key-seg_"] label[data-baseweb="radio"]:first-child { border-radius: 9px 0 0 9px; margin-left: 0 !important; }
[class*="st-key-seg_"] label[data-baseweb="radio"]:last-child { border-radius: 0 9px 9px 0; }
[class*="st-key-seg_"] label[data-baseweb="radio"] > div:first-child { display: none; }
[class*="st-key-seg_"] label[data-baseweb="radio"] > div:last-child { padding-left: 0 !important; margin-left: 0 !important; }
[class*="st-key-seg_"] label[data-baseweb="radio"] p { margin: 0; font-size: 0.9rem; }
[class*="st-key-seg_"] label[data-baseweb="radio"]:has(input:checked) { background: var(--btn); border-color: var(--btn); }
[class*="st-key-seg_"] label[data-baseweb="radio"]:has(input:checked) p { color: #ffffff !important; font-weight: 600; }

/* ── Tarjetas: contenedores con borde y clave card_* ── */
[class*="st-key-card_"] { background: var(--card); border-color: var(--border) !important; border-radius: 12px !important; }
[class*="st-key-dev_del_"] button { color: var(--err) !important; border-color: var(--err-bg) !important; }

/* ── Inicio compacto ── */
.kpi-grid.compact { grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 0 0 14px 0; }
.kpi-grid.compact .kpi { padding: 12px 16px; }
.kpi-grid.compact .kpi-val { font-size: 1.6rem; display: inline-block; margin-right: 8px; }
.kpi-grid.compact .kpi-sub { display: inline-block; }
.cov-2col { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 28px; }
.cov-2col .cov-row { grid-template-columns: 86px minmax(0, 1fr) 46px; padding: 6px 0; }
.steps-inline { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 0.86rem; color: var(--text2); }
.steps-inline b { font-family: var(--mono); color: var(--muted); margin-right: 4px; }

/* ── Resumen compacto de Exportar ── */
.sum-title { font-size: 1.05rem; font-weight: 700; color: var(--text); }
.sum-meta { font-family: var(--mono); font-size: 0.78rem; color: var(--muted); margin-top: 2px; }
.sum-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 18px; margin-top: 12px; }
.sum-l { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.sum-v { font-weight: 600; color: var(--text); margin-top: 2px; font-size: 0.92rem; }
"""

# Retoques del estilo Clásico sobre el CSS original (APP_CSS)
_CLASICO_CSS = """
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5 {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
/* deja sitio a la cabecera fija de Streamlit para que no tape la navegación */
[data-testid="stMainBlockContainer"] { padding-top: 3.6rem !important; }
[data-testid="stBaseButton-primary"] { background: #3498db !important; border-color: #3498db !important; }
"""


def _tokens_css() -> str:
    return (
        f":root{{{_vars(_T_BITACORA_LIGHT)}--mono:{MONO};"
        # alias de las variables antiguas, por si algún HTML en línea las usa
        "--p:var(--text);--p-light:var(--text2);--acc:var(--primary);"
        "--unused:var(--muted);--bg-light:var(--card2);"
        # nombres propios para el HTML de las páginas (APP_CSS de Clásico ya usa --ok, --border…)
        "--ui-ok:var(--ok);--ui-warn:var(--warn);--ui-err:var(--err);"
        "--ui-border:var(--border);--ui-used:var(--used);}"
        f":root[data-ui-mode=\"dark\"]{{{_vars(_T_BITACORA_DARK)}}}"
    )


def apply_theme(page: str = ""):
    """Inyecta el CSS del estilo activo y dibuja la barra superior.

    Llamar en cada página justo después de init_session_state()/handle_oauth_callback().
    `page` es el slug de NAV_PAGES de la página actual (marca la pestaña activa).
    """
    _install_label_filter()
    estilo = get_estilo()
    if estilo == "clasico":
        from app_utils import APP_CSS  # import diferido: app_utils importa este módulo
        # Sin variables: cada var(--x, #original) usa su color original
        css = APP_CSS + f"<style>{_BASE_CSS}{_CLASICO_CSS}</style>"
    else:
        css = f"<style>{_tokens_css()}{_BASE_CSS}{_BITACORA_CSS}</style>"
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
