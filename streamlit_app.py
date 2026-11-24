"""
streamlit_app.py  –  Punto de entrada de la aplicación Generador de Exámenes.

Ejecutar con:
    streamlit run streamlit_app.py
"""
import streamlit as st
import datetime
from app_theme import initial_sidebar

# ── Configuración de página (DEBE ser el primer comando Streamlit) ────────────
st.set_page_config(
    page_title="Generador Exámenes · UCM",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state=initial_sidebar("expanded"),
)

from app_utils import (init_session_state, render_sidebar, handle_oauth_callback, apply_theme,
                       nombre_bloque, nombre_tema, es_uso_antiguo, _nsort)
from app_theme import get_estilo, kpi_html, bar_html
import os

# ── Inicializar estado ────────────────────────────────────────────────────────
init_session_state()

# ── Completar flujo OAuth si venimos de Google ────────────────────────────────
handle_oauth_callback()

# ── CSS global + estilos home ─────────────────────────────────────────────────
apply_theme("inicio")
st.markdown("""
<style>

/* ── Hero ─────────────────────────────────────────────────── */
.home-hero {
  background: linear-gradient(135deg, var(--chip, #0f172a) 0%, var(--chip, #1e3a5f) 45%, #1d4ed8 100%);
  border-radius: 18px;
  padding: 36px 48px;
  margin-bottom: 24px;
  color: var(--chip-ink, white);
  position: relative;
  overflow: hidden;
  box-shadow: 0 10px 40px rgba(29,78,216,.30);
}
.home-hero::before {
  content: '';
  position: absolute;
  right: -40px; top: -80px;
  width: 320px; height: 320px;
  border-radius: 50%;
  background: rgba(255,255,255,.035);
}
.home-hero::after {
  content: '';
  position: absolute;
  right: 90px; bottom: -100px;
  width: 240px; height: 240px;
  border-radius: 50%;
  background: rgba(96,165,250,.07);
}
.home-hero-inner {
  position: relative; z-index: 1;
  display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 16px;
}
.home-hero h1 {
  font-size: 2.1em;
  font-weight: 800;
  margin: 0 0 4px 0;
  letter-spacing: -0.03em;
  line-height: 1.15;
}
.home-hero .subtitle {
  font-size: .95em;
  opacity: 0.70;
  margin: 0 0 18px 0;
  letter-spacing: .01em;
}
.home-hero .badges { display: flex; gap: 8px; flex-wrap: wrap; }
.home-hero .badge {
  display: inline-flex; align-items: center;
  background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.2);
  border-radius: 20px;
  padding: 4px 14px;
  font-size: 0.78em;
  font-weight: 600;
  letter-spacing: .03em;
  backdrop-filter: blur(4px);
}
.hero-deco {
  font-size: 5.5em;
  opacity: .12;
  line-height: 1;
  user-select: none;
  position: absolute;
  right: 48px; top: 18px;
}

/* ── Tarjetas de métricas ──────────────────────────────────── */
.stat-hero {
  background: var(--card, white);
  border-radius: 14px;
  padding: 16px 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,.07);
  border: 1px solid var(--ui-border, #f1f5f9);
  text-align: center;
  position: relative;
  overflow: hidden;
}
.stat-hero::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--accent, #3b82f6);
  border-radius: 14px 14px 0 0;
}
.stat-hero.ok  { --accent: #22c55e; }
.stat-hero.warn{ --accent: #f59e0b; }
.stat-hero.pur { --accent: #8b5cf6; }
.stat-hero.red { --accent: #ef4444; }
.stat-hero-num { font-size: 2em; font-weight: 800; color: var(--text, #0f172a); line-height: 1; }
.stat-hero-lbl { font-size: 0.72em; color: var(--muted, #94a3b8); margin-top: 5px; font-weight: 600; letter-spacing:.06em; text-transform:uppercase; }

/* ── Módulos ────────────────────────────────────────────────── */
.mod-card {
  background: var(--card, white);
  border-radius: 16px;
  padding: 24px 26px;
  box-shadow: 0 2px 14px rgba(0,0,0,.07);
  border: 1px solid var(--ui-border, #f1f5f9);
  height: 100%;
  transition: box-shadow .25s, transform .2s, border-color .2s;
}
.mod-card:hover {
  box-shadow: 0 14px 36px rgba(0,0,0,.13);
  transform: translateY(-3px);
  border-color: var(--ui-border, #e2e8f0);
}
.mod-icon-wrap {
  width: 50px; height: 50px;
  border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.5em;
  margin-bottom: 14px;
}
.mod-icon-wrap.blue   { background: var(--primary-soft, #eff6ff); }
.mod-icon-wrap.indigo { background: var(--primary-soft, #eef2ff); }
.mod-icon-wrap.green  { background: var(--ok-bg, #f0fdf4); }
.mod-icon-wrap.amber  { background: var(--note-bg, #fffbeb); }
.mod-icon-wrap.rose   { background: var(--err-bg, #fff1f2); }
.mod-icon-wrap.teal   { background: var(--ok-bg, #f0fdfa); }
.mod-title { font-size: 1.05em; font-weight: 700; color: var(--text, #0f172a); margin: 0 0 8px 0; }
.mod-desc  { font-size: 0.84em; color: var(--muted, #64748b); line-height: 1.6; margin-bottom: 14px; }
.mod-feat  { margin: 0; padding: 0; list-style: none; }
.mod-feat li {
  font-size: 0.79em; color: var(--text2, #475569);
  padding: 2px 0; display: flex; align-items: flex-start; gap: 7px;
}
.mod-feat li::before {
  content: "✓"; color: var(--primary, #3b82f6); font-weight: 700; font-size: 0.95em; margin-top:1px; flex-shrink:0;
}

/* ── Actividad reciente ─────────────────────────────────────── */
.activity-wrap {
  background: var(--card, white);
  border-radius: 14px;
  padding: 18px 22px;
  box-shadow: 0 2px 10px rgba(0,0,0,.06);
  border: 1px solid var(--ui-border, #f1f5f9);
}
.activity-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 9px 0;
  border-bottom: 1px solid var(--ui-border, #f8fafc);
  font-size: 0.84em;
}
.activity-row:last-child { border-bottom: none; }
.act-title { font-weight: 600; color: var(--text, #1e293b); flex: 1; }
.act-meta  { color: var(--muted, #94a3b8); font-size: 0.9em; white-space: nowrap; margin-left: 12px; }
.act-badge {
  background: var(--primary-soft, #eff6ff); color: var(--primary, #1d4ed8);
  border-radius: 6px;
  padding: 2px 8px; font-size: 0.82em; font-weight: 600; margin-left: 8px;
}

/* ── Section label ──────────────────────────────────────────── */
.section-label {
  font-size: 0.72em; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted, #94a3b8); margin-bottom: 12px; display: block;
}

/* ── No-DB banner ───────────────────────────────────────────── */
.no-db-banner {
  background: linear-gradient(90deg, var(--note-bg, #fff7ed), var(--note-bg, #fffbeb));
  border: 1px solid var(--note-border, #fed7aa);
  border-radius: 12px;
  padding: 14px 20px;
  font-size: .9em;
  color: var(--note-text, #92400e);
  margin-bottom: 20px;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar()

# ═══════════════════════════════════════════════════════════════════════════════
# INICIO · ESTILO BITÁCORA  (el estilo Clásico sigue más abajo, sin cambios)
# ═══════════════════════════════════════════════════════════════════════════════
_DIAS  = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


_HOME_CSS = """<style>
.hm-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; margin:2px 0 14px 0; }
.hm-stat { background:var(--card2); border-radius:10px; padding:10px 14px; }
.hm-stat .n { font-size:1.45rem; font-weight:700; color:var(--text); line-height:1.2; font-variant-numeric:tabular-nums; }
.hm-stat .l { font-size:.78rem; color:var(--muted); }
.hm-empty { color:var(--muted); font-size:.92rem; padding:6px 0 12px 0; }
.hm-line { font-size:.86rem; color:var(--text2); margin:-4px 0 12px 0; }
.hm-line b { color:var(--text); }
.hm-ex { display:grid; grid-template-columns:86px minmax(0,1fr) auto; gap:12px; align-items:center; padding:9px 0;
  border-bottom:1px solid var(--border); }
.hm-ex:last-child { border-bottom:none; }
.hm-ex .d { font-family:var(--mono); font-size:.8rem; color:var(--muted); }
.hm-ex .t { color:var(--text); font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.hm-ex .t small { display:block; font-weight:400; color:var(--muted); font-size:.78rem; }
.hm-chip { font-size:.74rem; font-weight:600; border-radius:999px; padding:2px 9px; white-space:nowrap; }
.hm-chip.ok { background:var(--ok-bg); color:var(--ok); } .hm-chip.warn { background:var(--warn-bg); color:var(--warn); }
.hm-chip.mut { background:var(--card2); color:var(--muted); }
.hm-tile .kpi-val { font-size:1.75rem; }
.hm-tema { display:grid; grid-template-columns:minmax(0,1fr) 90px 34px; gap:12px; align-items:center; padding:7px 0; }
.hm-tema .t { color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.hm-tema .t small { color:var(--muted); margin-left:6px; }
.hm-tema .n { font-family:var(--mono); font-size:.82rem; color:var(--muted); text-align:right; }
[class*="st-key-card_home_k"] [data-testid="stButton"] button { padding:0; min-height:0; }
.hm-blqs { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; }
.hm-blq { background:var(--card2); border-radius:10px; padding:10px 13px 11px 13px; display:flex; flex-direction:column; gap:5px; }
.hm-blq .k { font-family:var(--mono); font-size:.72rem; font-weight:600; color:var(--muted); letter-spacing:.04em; }
.hm-blq .n { font-weight:600; color:var(--text); font-size:.9rem; line-height:1.3; min-height:2.6em;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.hm-blq .s { font-size:.76rem; color:var(--muted); } .hm-blq .s b { color:var(--text); }
</style>"""


def _ir_gestor(preset: dict):
    """Abre el Gestor con los filtros indicados (se aplican antes de dibujar sus controles)."""
    st.session_state["_gestor_preset"] = preset
    st.switch_page("pages/1_Gestor_DB.py")


def _home_bitacora():
    import analisis_lib as _A
    ss    = st.session_state
    hoy   = datetime.date.today()
    fecha = f"{_DIAS[hoy.weekday()]} {hoy.day} de {_MESES[hoy.month - 1]}"
    st.markdown(_HOME_CSS, unsafe_allow_html=True)

    # ── Sin base de datos: solo cómo empezar ─────────────────────────────────
    if not ss.db_connected:
        st.markdown(f'<div class="pg-head"><div class="pg-title">{fecha}</div>'
                    f'<div class="pg-sub">Base de datos no conectada</div></div>', unsafe_allow_html=True)
        with st.container(border=True, key="card_home_conn"):
            st.markdown(
                "<div class='sec-title'>Conecta tu base de datos para empezar</div>"
                "<div class='steps-inline' style='flex-direction:column;gap:8px'>"
                "<span><b>1</b>Pulsa <b style='font-family:inherit;color:var(--text)'>Base de datos</b>, "
                "arriba a la derecha.</span>"
                "<span><b>2</b>Entra con tu cuenta de Google y elige la hoja, o sube el archivo Excel.</span>"
                "<span><b>3</b>Ya puedes gestionar preguntas, generar exámenes y analizarlos.</span></div>",
                unsafe_allow_html=True)
        st.caption(f"Generador de Exámenes · Unidad de Física Médica · UCM · {hoy.year} — Diego García Pinto")
        return

    df     = ss.df_preguntas
    n_bloq = df["bloque"].nunique() if "bloque" in df.columns else 0
    origen = ss.get("_upload_name") or os.path.basename(ss.get("excel_path", "") or "")
    h1, h2 = st.columns([5, 1.4], vertical_alignment="bottom")
    h1.markdown(f'<div class="pg-head" style="margin:0"><div class="pg-title">{fecha}</div>'
                f'<div class="pg-sub">{len(df)} preguntas · {n_bloq} bloques'
                f'{" · " + origen if origen else ""}</div></div>', unsafe_allow_html=True)
    if h2.button("Ir al Generador", use_container_width=True, type="primary", key="btn_home_gen"):
        st.switch_page("pages/2_Generador.py")
    st.write("")

    # ── Fila 1: seguir trabajando · últimos exámenes ─────────────────────────
    c1, c2 = st.columns([1.2, 1], gap="medium")
    with c1.container(border=True, key="card_home_curso"):
        st.markdown("<div class='sec-title'>Seguir trabajando</div>", unsafe_allow_html=True)
        n_fij = len(ss.get("sel_ids", []) or [])
        rec   = ss.get("auto_recipe", {}) or {}
        n_aut = sum(int(v) for bd in rec.values() if isinstance(bd, dict) for sd in bd.values()
                    if isinstance(sd, dict) for v in sd.values() if isinstance(v, (int, float)))
        n_dev = len(ss.get("dev_questions", []) or [])
        n_gen = len(ss.get("cache_examen", []) or [])
        ef    = ss.get("export_files") or {}
        if n_fij or n_aut or n_dev or n_gen:
            stats = [(n_fij, "fijas"), (n_aut, "por auto-relleno"), (n_dev, "de desarrollo"),
                     (n_gen, "en la vista previa")]
            st.markdown("<div class='hm-stats'>" + "".join(
                f"<div class='hm-stat'><div class='n'>{n}</div><div class='l'>{l}</div></div>" for n, l in stats)
                + "</div>", unsafe_allow_html=True)
            if ef.get("nombre"):
                st.markdown(f"<div class='hm-line'>Última exportación: <b>{ef['nombre']}</b></div>",
                            unsafe_allow_html=True)
            if st.button("Continuar con el examen", type="primary", key="btn_home_cont"):
                st.switch_page("pages/2_Generador.py")
        else:
            st.markdown("<div class='hm-empty'>No hay ningún examen en preparación. En el Generador eliges "
                        "las preguntas (a mano o con auto-relleno), las revisas en la vista previa y exportas "
                        "a Word o LaTeX.</div>", unsafe_allow_html=True)
            if st.button("Empezar un examen", type="primary", key="btn_home_new"):
                st.switch_page("pages/2_Generador.py")

    with c2.container(border=True, key="card_home_exams"):
        st.markdown("<div class='sec-title'>Últimos exámenes<span class='sec-meta'>registrados</span></div>",
                    unsafe_allow_html=True)
        exs = _A.get_examenes(ss.get("excel_dfs", {}))
        if exs.empty:
            st.markdown("<div class='hm-empty'>Aún no hay exámenes registrados. Se registran solos al exportar, "
                        "y los anteriores se pueden añadir en Análisis.</div>", unsafe_allow_html=True)
        else:
            rows = ""
            for _, r in exs.sort_values("Fecha", ascending=False).head(4).iterrows():
                if str(r["KR20"]).strip():
                    try:
                        chip = (f"<span class='hm-chip ok'>media {float(r['Media']):.2f} · "
                                f"KR-20 {float(r['KR20']):.2f}</span>").replace(".", ",")
                    except ValueError:
                        chip = "<span class='hm-chip ok'>analizado</span>"
                else:
                    chip = "<span class='hm-chip mut'>sin analizar</span>"
                sub = " · ".join(x for x in (r["Curso"], r["Convocatoria"], f"{r['N_Preguntas']} preguntas") if x)
                rows += (f"<div class='hm-ex'><span class='d'>{r['Fecha'][:10]}</span>"
                         f"<span class='t'>{r['Nombre']}<small>{sub}</small></span>{chip}</div>")
            st.markdown(rows, unsafe_allow_html=True)
        if st.button("Analizar un examen", key="btn_home_an"):
            st.switch_page("pages/5_Analisis.py")

    # ── Fila 2: estado del banco (cada dato lleva al Gestor ya filtrado) ──────
    st.markdown("<div class='sec-title' style='margin-top:6px'>Estado del banco</div>", unsafe_allow_html=True)
    _u = df["usada"].astype(str)
    nunca = int((_u.str.strip() == "").sum())
    viejas = int(_u.apply(lambda v: es_uso_antiguo(v, 12)).sum())
    if "solucion" in df.columns:
        sin_sol = int(df["solucion"].astype(str).str.strip().isin(["", "nan", "None"]).sum())
    else:
        sin_sol = len(df)
    n_tem = df["Tema"].astype(str).nunique() if "Tema" in df.columns else 0
    pct = lambda n: f"{round(100 * n / len(df))} % del banco" if len(df) else ""
    tiles = [
        ("Preguntas", len(df), f"{n_bloq} bloques · {n_tem} temas", {}),
        ("Sin solución", sin_sol, pct(sin_sol), {"man_filter_sin_sol": True, "man_f_sol": "Sin"}),
        ("Nunca usadas", nunca, pct(nunca), {"man_f_uso": "Nunca usada"}),
        ("Sin usar hace +12 meses", viejas, "usadas por última vez hace más de un año", {"man_f_uso": "Usada >12m"}),
    ]
    tcols = st.columns(len(tiles), gap="small")
    for i, (lbl, val, sub, pre) in enumerate(tiles):
        with tcols[i].container(border=True, key=f"card_home_k{i}"):
            st.markdown(f"<div class='hm-tile'><div class='kpi-lbl'>{lbl}</div><div class='kpi-val'>{val}</div>"
                        f"<div class='kpi-sub'>{sub}</div></div>", unsafe_allow_html=True)
            if st.button("Ver en el Gestor →", key=f"btn_home_k{i}", type="tertiary", disabled=not val):
                _ir_gestor(pre)

    # ── Fila 3: cobertura por bloque · temas con pocas preguntas ─────────────
    c3, c4 = st.columns([1.2, 1], gap="medium")
    with c3.container(border=True, key="card_home_cov"):
        cfg_b = ss.get("cfg_bloques", {}) or {}
        cfg_t = ss.get("cfg_temas", {}) or {}
        tiles = ""
        for blq in sorted(df["bloque"].dropna().unique().tolist(), key=_nsort):
            d_b = df[df["bloque"] == blq]
            tot = len(d_b)
            frescas = int(d_b["usada"].astype(str).apply(
                lambda v: not v.strip() or v in ("nan", "None") or es_uso_antiguo(v, 12)).sum())
            temas_b = sorted({str(t).removesuffix(".0") for t in d_b["Tema"].astype(str)}, key=_nsort)
            desc = str(cfg_b.get(blq, "") or "").strip()
            if desc in ("nan", "None"):
                desc = ""
            if not desc:   # sin descripción del bloque: los nombres de sus temas, si los hay
                noms = [cfg_t.get(t, {}).get("nombre", "") for t in temas_b if isinstance(cfg_t.get(t), dict)]
                noms = [n for n in noms if n and n not in ("nan", "None")]
                desc = " · ".join(noms[:2]) if noms else "Temas " + ", ".join(temas_b[:6])
            tiles += (f"<div class='hm-blq'><div class='k'>{blq}</div><div class='n' title='{desc}'>{desc}</div>"
                      f"<div class='s'><b>{tot}</b> preguntas · {len(temas_b)} tema{'s' if len(temas_b) != 1 else ''}</div>"
                      f"{bar_html(100 * frescas / tot if tot else 0)}"
                      f"<div class='s'>{frescas} sin usar en el último año</div></div>")
        st.markdown("<div class='sec-title'>Bloques<span class='sec-meta'>la barra indica las preguntas "
                    "disponibles (sin usar en 12 meses)</span></div>"
                    f"<div class='hm-blqs'>{tiles}</div>", unsafe_allow_html=True)
        if not any(str(v).strip() not in ("", "nan", "None") for v in cfg_b.values()):
            st.caption("Pon un nombre a cada bloque en Configuración › Bloques y aparecerá aquí.")

    with c4.container(border=True, key="card_home_temas"):
        cnt = df["Tema"].astype(str).str.replace(r"\.0$", "", regex=True).value_counts().to_dict() \
            if "Tema" in df.columns else {}
        temas = {str(t): d for t, d in (ss.get("cfg_temas", {}) or {}).items()}
        for t in cnt:
            temas.setdefault(t, {})
        pocos = sorted(((t, cnt.get(t, 0)) for t in temas if cnt.get(t, 0) < 4), key=lambda x: (x[1], _nsort(x[0])))
        st.markdown("<div class='sec-title'>Temas con pocas preguntas<span class='sec-meta'>menos de 4</span></div>",
                    unsafe_allow_html=True)
        if not pocos:
            st.markdown("<div class='hm-empty'>Todos los temas tienen al menos 4 preguntas.</div>",
                        unsafe_allow_html=True)
        else:
            mx = max(4, max(n for _, n in pocos))
            rows = ""
            for t, n in pocos[:7]:
                d = temas.get(t) if isinstance(temas.get(t), dict) else {}
                blq = nombre_bloque(str(d.get("bloque", ""))) if d.get("bloque") else ""
                rows += (f"<div class='hm-tema'><span class='t'>{nombre_tema(t)}<small>{blq}</small></span>"
                         f"{bar_html(100 * n / mx)}<span class='n'>{n}</span></div>")
            st.markdown(rows, unsafe_allow_html=True)
            if len(pocos) > 7:
                st.caption(f"y {len(pocos) - 7} más")

    st.caption(f"Generador de Exámenes · Unidad de Física Médica · Facultad de Medicina · UCM · {hoy.year}"
               "  —  Desarrollado por Diego García Pinto")

if get_estilo() == "bitacora":
    _home_bitacora()
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# HERO BANNER
# ═══════════════════════════════════════════════════════════════════════════════
_year = datetime.date.today().year
st.markdown(f"""
<div class="home-hero">
  <div class="hero-deco">📝</div>
  <div class="home-hero-inner">
    <div>
      <h1>Generador de Exámenes</h1>
      <div class="subtitle">Unidad de Física Médica &nbsp;·&nbsp; Facultad de Medicina · UCM</div>
      <div class="badges">
        <span class="badge">🎓 Grado + Máster</span>
        <span class="badge">Curso {_year - 1}–{_year}</span>
        <span class="badge">☁️ Cloud + Local</span>
        <span class="badge">LaTeX &amp; Word</span>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MÉTRICAS RÁPIDAS
# ═══════════════════════════════════════════════════════════════════════════════
db = st.session_state
if db.db_connected:
    df    = db.df_preguntas
    nunca  = int((df["usada"] == "").sum())
    usadas = len(df) - nunca
    n_sel  = len(db.sel_ids)
    pct    = int(usadas / len(df) * 100) if len(df) else 0
    n_bloq = df["bloque"].nunique() if "bloque" in df.columns else 0

    sm1, sm2, sm3, sm4, sm5 = st.columns(5)
    sm1.markdown(
        f"<div class='stat-hero'><div class='stat-hero-num'>{len(df)}</div>"
        f"<div class='stat-hero-lbl'>Total preguntas</div></div>",
        unsafe_allow_html=True)
    sm2.markdown(
        f"<div class='stat-hero ok'><div class='stat-hero-num' style='color:var(--ui-ok, #16a34a)'>{usadas}</div>"
        f"<div class='stat-hero-lbl'>Usadas en exámenes</div></div>",
        unsafe_allow_html=True)
    sm3.markdown(
        f"<div class='stat-hero warn'><div class='stat-hero-num' style='color:var(--ui-warn, #d97706)'>{nunca}</div>"
        f"<div class='stat-hero-lbl'>Sin usar</div></div>",
        unsafe_allow_html=True)
    sm4.markdown(
        f"<div class='stat-hero pur'><div class='stat-hero-num' style='color:var(--ui-used, #7c3aed)'>{pct}%</div>"
        f"<div class='stat-hero-lbl'>Cobertura</div></div>",
        unsafe_allow_html=True)
    sm5.markdown(
        f"<div class='stat-hero red'><div class='stat-hero-num' style='color:var(--ui-err, #dc2626)'>{n_sel}</div>"
        f"<div class='stat-hero-lbl'>Seleccionadas ahora</div></div>",
        unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
else:
    st.markdown("""
    <div class='no-db-banner'>
      ⚠️ <strong>Base de datos no conectada.</strong>
      Sube tu archivo Excel desde la barra lateral para empezar.
    </div>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULOS (tarjetas 2×2)
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<span class='section-label'>Módulos de la aplicación</span>", unsafe_allow_html=True)

row1c1, row1c2 = st.columns(2, gap="medium")
row2c1, row2c2 = st.columns(2, gap="medium")

with row1c1:
    st.markdown("""
    <div class="mod-card">
      <div class="mod-icon-wrap blue">🗄️</div>
      <div class="mod-title">Gestor de Base de Datos</div>
      <div class="mod-desc">
        Gestiona el banco de preguntas: añade, edita, importa y analiza la cobertura por bloques, temas y objetivos docentes.
      </div>
      <ul class="mod-feat">
        <li>Añadir preguntas con validación de duplicados</li>
        <li>Importar desde Excel con etiquetas y comentarios</li>
        <li>Editor modal con LaTeX en tiempo real</li>
        <li>Operaciones masivas (tema, dificultad, eliminar)</li>
        <li>Dashboard de cobertura por bloque y tema</li>
        <li>Gestión de objetivos / competencias</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Abrir Gestor DB →", use_container_width=True, type="primary", key="btn_home_gestor"):
        st.switch_page("pages/1_Gestor_DB.py")

with row1c2:
    st.markdown("""
    <div class="mod-card">
      <div class="mod-icon-wrap indigo">🎲</div>
      <div class="mod-title">Generador de Exámenes</div>
      <div class="mod-desc">
        Crea exámenes equilibrados: selección manual o auto-relleno por bloques, temas, objetivos y dificultad.
      </div>
      <ul class="mod-feat">
        <li>Selección manual con filtros avanzados</li>
        <li>Auto-relleno por bloque, tema y dificultad</li>
        <li>Filtro y receta por objetivo docente</li>
        <li>Preguntas de desarrollo con editor LaTeX/Markdown</li>
        <li>Vista previa con renderizado MathJax</li>
        <li>Exportar a Word y LaTeX (Test / Desarrollo / Ambos)</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Abrir Generador →", use_container_width=True, type="primary", key="btn_home_gen"):
        st.switch_page("pages/2_Generador.py")

with row2c1:
    st.markdown("""
    <div class="mod-card">
      <div class="mod-icon-wrap green">⚙️</div>
      <div class="mod-title">Configuración</div>
      <div class="mod-desc">
        Personaliza la asignatura: nombres de bloques, temas y objetivos docentes que aparecen en toda la aplicación.
      </div>
      <ul class="mod-feat">
        <li>Asignar nombres descriptivos a bloques</li>
        <li>Asignar nombres a temas individuales</li>
        <li>Definir objetivos / competencias docentes</li>
        <li>Datos generales de la asignatura</li>
        <li>Exportar / importar toda la configuración (JSON)</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Abrir Configuración →", use_container_width=True, key="btn_home_cfg"):
        st.switch_page("pages/3_Configuracion.py")

with row2c2:
    st.markdown("""
    <div class="mod-card">
      <div class="mod-icon-wrap amber">📖</div>
      <div class="mod-title">Manual de uso</div>
      <div class="mod-desc">
        Guía completa de la aplicación: cómo gestionar la base de datos, generar exámenes y configurar la asignatura.
      </div>
      <ul class="mod-feat">
        <li>Inicio rápido paso a paso</li>
        <li>Guía del Gestor de Base de Datos</li>
        <li>Guía del Generador de Exámenes</li>
        <li>Referencia de formatos de exportación</li>
        <li>Preguntas frecuentes</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Ver Manual →", use_container_width=True, key="btn_home_help"):
        st.switch_page("pages/4_Ayuda.py")

# ── Fila inferior: Actividad reciente + Inicio rápido ────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
col_act, col_quick = st.columns([3, 2], gap="large")

with col_act:
    historial = st.session_state.historial
    if historial:
        st.markdown("<span class='section-label'>Últimos exámenes generados</span>", unsafe_allow_html=True)
        rows_html = ""
        for entry in reversed(historial[-6:]):
            titulo  = entry.get("titulo", "Sin título")
            fecha   = entry.get("fecha", "")
            n_preg  = entry.get("n_preguntas", "?")
            modelos = entry.get("n_modelos", "?")
            rows_html += (
                f"<div class='activity-row'>"
                f"  <span class='act-title'>{titulo}</span>"
                f"  <span class='act-meta'>{fecha}</span>"
                f"  <span class='act-badge'>{n_preg} preg · {modelos} mod.</span>"
                f"</div>"
            )
        st.markdown(f"<div class='activity-wrap'>{rows_html}</div>", unsafe_allow_html=True)

with col_quick:
    st.markdown("<span class='section-label'>Inicio rápido</span>", unsafe_allow_html=True)
    st.markdown("""
    <div class='activity-wrap'>
      <div class='activity-row'><span class='act-title'>1. Conecta tu base de datos Excel</span>
        <span class='act-badge'>Sidebar</span></div>
      <div class='activity-row'><span class='act-title'>2. Configura bloques, temas y objetivos</span>
        <span class='act-badge'>Config.</span></div>
      <div class='activity-row'><span class='act-title'>3. Añade o importa preguntas</span>
        <span class='act-badge'>Gestor DB</span></div>
      <div class='activity-row'><span class='act-title'>4. Selecciona preguntas o usa Auto-relleno</span>
        <span class='act-badge'>Generador</span></div>
      <div class='activity-row'><span class='act-title'>5. Exporta a Word / LaTeX</span>
        <span class='act-badge'>Generador</span></div>
    </div>
    """, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("---")
st.caption(
    f"Generador Exámenes · Unidad de Física Médica · Facultad de Medicina · UCM · {_year}"
    "  —  Desarrollado por Diego García Pinto"
)
