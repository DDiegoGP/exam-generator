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

from app_utils import init_session_state, render_sidebar, APP_CSS
import os

# ── Inicializar estado ────────────────────────────────────────────────────────
init_session_state()

# ── CSS global + estilos home ─────────────────────────────────────────────────
st.markdown(APP_CSS, unsafe_allow_html=True)
st.markdown("""
<style>
/* Hero banner */
.home-hero {
  background: linear-gradient(135deg, #1a252f 0%, #2c3e50 60%, #34495e 100%);
  border-radius: 14px;
  padding: 32px 40px;
  margin-bottom: 28px;
  color: white;
  position: relative;
  overflow: hidden;
}
.home-hero::after {
  content: '';
  position: absolute;
  right: -30px; top: -30px;
  width: 220px; height: 220px;
  border-radius: 50%;
  background: rgba(52,152,219,0.15);
}
.home-hero h1 {
  font-size: 2em;
  font-weight: 800;
  margin: 0 0 4px 0;
  letter-spacing: -0.02em;
}
.home-hero .subtitle {
  font-size: 1.05em;
  opacity: 0.75;
  margin: 0 0 16px 0;
}
.home-hero .badge {
  display: inline-block;
  background: rgba(52,152,219,0.3);
  border: 1px solid rgba(52,152,219,0.5);
  border-radius: 20px;
  padding: 3px 12px;
  font-size: 0.78em;
  font-weight: 600;
  letter-spacing: .04em;
  margin-right: 6px;
}

/* Módulos */
.mod-card {
  background: #fff;
  border-radius: 12px;
  padding: 22px 24px;
  box-shadow: 0 2px 10px rgba(0,0,0,.08);
  border: 1px solid #e9ecef;
  height: 100%;
  transition: box-shadow .2s, transform .15s;
}
.mod-card:hover {
  box-shadow: 0 6px 20px rgba(0,0,0,.13);
  transform: translateY(-2px);
}
.mod-icon { font-size: 2.2em; margin-bottom: 8px; }
.mod-title { font-size: 1.05em; font-weight: 700; color: #2c3e50; margin: 0 0 6px 0; }
.mod-desc  { font-size: 0.84em; color: #666; line-height: 1.55; }
.mod-feat  { margin: 10px 0 0 0; padding: 0; list-style: none; }
.mod-feat li {
  font-size: 0.8em; color: #555;
  padding: 2px 0; display: flex; align-items: center; gap: 5px;
}
.mod-feat li::before { content: "›"; color: #3498db; font-weight: 700; }

/* Stat mini */
.mini-stat {
  background: #fff;
  border-radius: 10px;
  padding: 14px 18px;
  box-shadow: 0 2px 8px rgba(0,0,0,.07);
  border-top: 3px solid #3498db;
  text-align: center;
}
.mini-stat.ok   { border-top-color: #27ae60; }
.mini-stat.warn { border-top-color: #f39c12; }
.mini-stat.used { border-top-color: #8e44ad; }
.mini-stat.sel  { border-top-color: #e74c3c; }
.mini-num   { font-size: 1.7em; font-weight: 800; color: #2c3e50; line-height: 1.1; }
.mini-lbl   { font-size: 0.75em; color: #888; margin-top: 3px; font-weight: 500; }

/* Actividad reciente */
.activity-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 0.84em;
}
.activity-row:last-child { border-bottom: none; }
.act-title { font-weight: 600; color: #2c3e50; flex: 1; }
.act-meta  { color: #888; font-size: 0.9em; white-space: nowrap; margin-left: 12px; }
.act-badge { background: #dbeeff; color: #1a5e9a; border-radius: 4px;
             padding: 1px 6px; font-size: 0.82em; font-weight: 600; margin-left: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar()

# ═══════════════════════════════════════════════════════════════════════════════
# HERO BANNER
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="home-hero">
  <h1>📝 Generador de Exámenes</h1>
  <div class="subtitle">Departamento de Física Médica · Universidad Complutense de Madrid</div>
  <span class="badge">v42</span>
  <span class="badge">2025–2026</span>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MÉTRICAS RÁPIDAS
# ═══════════════════════════════════════════════════════════════════════════════
db = st.session_state
if db.db_connected:
    df  = db.df_preguntas
    nunca  = int((df["usada"] == "").sum())
    usadas = len(df) - nunca
    n_sel  = len(db.sel_ids)
    pct    = int(usadas / len(df) * 100) if len(df) else 0

    sm1, sm2, sm3, sm4, sm5 = st.columns(5)
    sm1.markdown(
        f"<div class='mini-stat'><div class='mini-num'>{len(df)}</div><div class='mini-lbl'>📚 Total preguntas</div></div>",
        unsafe_allow_html=True)
    sm2.markdown(
        f"<div class='mini-stat ok'><div class='mini-num' style='color:#27ae60'>{usadas}</div><div class='mini-lbl'>✅ Usadas</div></div>",
        unsafe_allow_html=True)
    sm3.markdown(
        f"<div class='mini-stat warn'><div class='mini-num' style='color:#f39c12'>{nunca}</div><div class='mini-lbl'>🆕 Sin usar</div></div>",
        unsafe_allow_html=True)
    sm4.markdown(
        f"<div class='mini-stat used'><div class='mini-num' style='color:#8e44ad'>{pct}%</div><div class='mini-lbl'>🎯 Cobertura</div></div>",
        unsafe_allow_html=True)
    sm5.markdown(
        f"<div class='mini-stat sel'><div class='mini-num' style='color:#e74c3c'>{n_sel}</div><div class='mini-lbl'>🔢 Seleccionadas</div></div>",
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
else:
    st.info("⚠️ Conecta la base de datos desde la barra lateral para ver las estadísticas.")
    st.markdown("<br>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULOS (tarjetas)
# ═══════════════════════════════════════════════════════════════════════════════
mc1, mc2 = st.columns(2)

with mc1:
    st.markdown("""
    <div class="mod-card">
      <div class="mod-icon">🗄️</div>
      <div class="mod-title">Gestor de Base de Datos</div>
      <div class="mod-desc">
        Gestiona el banco de preguntas: añade, importa, edita y analiza la cobertura por bloques y temas.
      </div>
      <ul class="mod-feat">
        <li>Añadir preguntas individuales con validación</li>
        <li>Importar desde documentos Word o formato Aiken</li>
        <li>Editor individual con diálogo modal</li>
        <li>Operaciones masivas filtradas (cambio tema, dificultad, eliminar)</li>
        <li>Dashboard de estadísticas: cobertura, dificultad, uso</li>
        <li>Exportar / importar entre bases de datos (JSON)</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Abrir Gestor DB →", use_container_width=True, type="primary", key="btn_home_gestor"):
        st.switch_page("pages/1_Gestor_DB.py")

with mc2:
    st.markdown("""
    <div class="mod-card">
      <div class="mod-icon">🎲</div>
      <div class="mod-title">Generador de Exámenes</div>
      <div class="mod-desc">
        Crea exámenes equilibrados: selecciona preguntas manualmente o usa el relleno automático por bloques.
      </div>
      <ul class="mod-feat">
        <li>Selección manual con filtros (bloque, tema, dificultad, uso)</li>
        <li>Relleno automático por bloque con control de dificultad</li>
        <li>Preguntas de desarrollo/abiertas adicionales</li>
        <li>Vista previa con renderizado MathJax (fórmulas LaTeX)</li>
        <li>Exportar a Word y LaTeX (exam class)</li>
        <li>Presets de configuración y historial de exámenes</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Abrir Generador →", use_container_width=True, type="primary", key="btn_home_gen"):
        st.switch_page("pages/2_Generador.py")

# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVIDAD RECIENTE
# ═══════════════════════════════════════════════════════════════════════════════
historial = st.session_state.historial
if historial:
    st.markdown("---")
    st.markdown("#### 📋 Últimos exámenes generados")
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
            f"  <span class='act-badge'>{n_preg} preg · {modelos} modelos</span>"
            f"</div>"
        )
    st.markdown(f"<div style='background:#fff;border-radius:10px;padding:10px 18px;box-shadow:0 2px 8px rgba(0,0,0,.07);'>{rows_html}</div>",
                unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Generador Exámenes v42 · Departamento de Física Médica · UCM · {datetime.date.today().year}")
