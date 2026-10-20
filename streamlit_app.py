"""
streamlit_app.py  –  Punto de entrada de la aplicación Generador de Exámenes.

Ejecutar con:
    streamlit run streamlit_app.py
"""
import streamlit as st
import datetime

# ── Configuración de página (DEBE ser el primer comando Streamlit) ────────────
st.set_page_config(
    page_title="Generador Exámenes · UCM",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app_utils import (init_session_state, render_sidebar, handle_oauth_callback, apply_theme,
                       nombre_bloque, _nsort)
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


def _home_bitacora():
    ss    = st.session_state
    hoy   = datetime.date.today()
    fecha = f"{_DIAS[hoy.weekday()]} {hoy.day} de {_MESES[hoy.month - 1]}"
    n_sel = len(ss.get("sel_ids", []))

    if ss.db_connected:
        sub = (f"{n_sel} preguntas seleccionadas en el Generador" if n_sel
               else "Ninguna pregunta seleccionada todavía")
    else:
        sub = "Base de datos no conectada"
    st.markdown(f'<div class="pg-head"><div class="pg-title">{fecha}</div>'
                f'<div class="pg-sub">{sub}</div></div>', unsafe_allow_html=True)

    if ss.db_connected:
        df     = ss.df_preguntas
        nunca  = int((df["usada"] == "").sum())
        usadas = len(df) - nunca
        pct    = int(usadas / len(df) * 100) if len(df) else 0
        n_bloq = df["bloque"].nunique() if "bloque" in df.columns else 0
        st.markdown(kpi_html([
            ("Total preguntas",     len(df), f"en {n_bloq} bloques", False),
            ("Usadas en exámenes",  usadas,  bar_html(pct), False),
            ("Sin usar",            nunca,   "nunca han salido en un examen", False),
            ("Cobertura",           f"{pct} %", "preguntas usadas alguna vez", False),
            ("Seleccionadas ahora", n_sel,   "en el Generador", True),
        ]), unsafe_allow_html=True)
    else:
        st.warning("**Base de datos no conectada.** Sube tu archivo Excel desde la barra lateral para empezar.")

    col_l, col_r = st.columns([3, 2], gap="medium")
    with col_l:
        if ss.db_connected and "bloque" in ss.df_preguntas.columns:
            df = ss.df_preguntas
            rows = ""
            for blq in sorted(df["bloque"].dropna().unique().tolist(), key=_nsort):
                d_b   = df[df["bloque"] == blq]
                tot   = len(d_b)
                usa   = int((d_b["usada"] != "").sum())
                rows += (f'<div class="cov-row"><span class="cov-name" title="{nombre_bloque(str(blq))}">'
                         f'{nombre_bloque(str(blq))}</span>{bar_html(usa / tot * 100 if tot else 0)}'
                         f'<span class="cov-num">{usa}/{tot}</span></div>')
            st.markdown('<div class="card"><div class="sec-title">Cobertura por bloque'
                        '<span class="sec-meta">usadas / total</span></div>'
                        f'{rows}</div>', unsafe_allow_html=True)

        # Módulos (mismos botones que en el estilo Clásico)
        st.markdown('<div class="sec-title" style="margin-top:4px">Módulos</div>', unsafe_allow_html=True)
        _mods = [
            ("Gestor DB", "Añadir, importar, editar y analizar el banco de preguntas.",
             "Abrir Gestor DB →", "btn_home_gestor", "pages/1_Gestor_DB.py", "primary"),
            ("Generador", "Seleccionar preguntas o auto-rellenar y exportar a Word / LaTeX.",
             "Abrir Generador →", "btn_home_gen", "pages/2_Generador.py", "primary"),
            ("Configuración", "Bloques, temas, objetivos, datos de la asignatura y apariencia.",
             "Abrir Configuración →", "btn_home_cfg", "pages/3_Configuracion.py", "secondary"),
            ("Manual de uso", "Guía paso a paso, formatos de exportación y preguntas frecuentes.",
             "Ver Manual →", "btn_home_help", "pages/4_Ayuda.py", "secondary"),
        ]
        m_cols = st.columns(2, gap="small")
        for i, (tit, desc, lbl, key, page, kind) in enumerate(_mods):
            with m_cols[i % 2]:
                with st.container(border=True, key=f"home_mod_{i}"):
                    st.markdown(f"**{tit}**")
                    st.caption(desc)
                    if st.button(lbl, use_container_width=True, type=kind, key=key):
                        st.switch_page(page)

    with col_r:
        historial = ss.historial
        if historial:
            rows = ""
            for entry in reversed(historial[-6:]):
                rows += (f'<div class="list-row"><span class="list-date">{entry.get("fecha", "")}</span>'
                         f'<span class="list-title">{entry.get("titulo", "Sin título")}</span>'
                         f'<span class="list-meta">{entry.get("n_preguntas", "?")} preg · '
                         f'{entry.get("n_modelos", "?")} mod.</span></div>')
            st.markdown(f'<div class="card"><div class="sec-title">Últimos exámenes generados</div>{rows}</div>',
                        unsafe_allow_html=True)
        pasos = [
            ("Conecta tu base de datos Excel", "Barra lateral"),
            ("Configura bloques, temas y objetivos", "Configuración"),
            ("Añade o importa preguntas", "Gestor DB"),
            ("Selecciona preguntas o usa Auto-relleno", "Generador"),
            ("Exporta a Word / LaTeX", "Generador"),
        ]
        rows = "".join(f'<div class="list-row"><span class="step-n">{i}</span>'
                       f'<span class="list-title" style="white-space:normal">{t}</span><span class="pill">{d}</span></div>'
                       for i, (t, d) in enumerate(pasos, 1))
        st.markdown(f'<div class="card"><div class="sec-title">Inicio rápido</div>{rows}</div>',
                    unsafe_allow_html=True)

    st.caption(
        f"Generador Exámenes · Unidad de Física Médica · Facultad de Medicina · UCM · {hoy.year}"
        "  —  Desarrollado por Diego García Pinto"
    )


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
