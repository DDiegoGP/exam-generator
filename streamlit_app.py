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

from app_utils import init_session_state, render_sidebar, handle_oauth_callback, APP_CSS
import os

# ── Inicializar estado ────────────────────────────────────────────────────────
init_session_state()

# ── Completar flujo OAuth si venimos de Google ────────────────────────────────
handle_oauth_callback()

# ── CSS global + estilos home ─────────────────────────────────────────────────
st.markdown(APP_CSS, unsafe_allow_html=True)
st.markdown("""
<style>

/* ── Hero ─────────────────────────────────────────────────── */
.home-hero {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 55%, #1d4ed8 100%);
  border-radius: 18px;
  padding: 40px 48px;
  margin-bottom: 28px;
  color: white;
  position: relative;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(29,78,216,.25);
}
.home-hero::before {
  content: '';
  position: absolute;
  right: -60px; top: -60px;
  width: 280px; height: 280px;
  border-radius: 50%;
  background: rgba(255,255,255,.04);
}
.home-hero::after {
  content: '';
  position: absolute;
  right: 60px; bottom: -80px;
  width: 200px; height: 200px;
  border-radius: 50%;
  background: rgba(96,165,250,.08);
}
.home-hero h1 {
  font-size: 2.2em;
  font-weight: 800;
  margin: 0 0 6px 0;
  letter-spacing: -0.03em;
  line-height: 1.15;
}
.home-hero .subtitle {
  font-size: 1em;
  opacity: 0.70;
  margin: 0 0 20px 0;
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

/* ── Tarjetas de métricas ──────────────────────────────────── */
.stat-hero {
  background: white;
  border-radius: 14px;
  padding: 18px 22px;
  box-shadow: 0 2px 12px rgba(0,0,0,.07);
  border: 1px solid #f1f5f9;
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
.stat-hero-num { font-size: 2em; font-weight: 800; color: #0f172a; line-height: 1; }
.stat-hero-lbl { font-size: 0.75em; color: #94a3b8; margin-top: 4px; font-weight: 500; letter-spacing:.02em; }

/* ── Módulos ────────────────────────────────────────────────── */
.mod-card {
  background: white;
  border-radius: 16px;
  padding: 26px 28px;
  box-shadow: 0 2px 12px rgba(0,0,0,.07);
  border: 1px solid #f1f5f9;
  height: 100%;
  transition: box-shadow .25s, transform .2s;
}
.mod-card:hover {
  box-shadow: 0 12px 32px rgba(0,0,0,.13);
  transform: translateY(-3px);
}
.mod-icon-wrap {
  width: 52px; height: 52px;
  border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.6em;
  margin-bottom: 14px;
}
.mod-icon-wrap.blue { background: #eff6ff; }
.mod-icon-wrap.indigo { background: #eef2ff; }
.mod-icon-wrap.green { background: #f0fdf4; }
.mod-icon-wrap.amber { background: #fffbeb; }
.mod-title { font-size: 1.1em; font-weight: 700; color: #0f172a; margin: 0 0 8px 0; }
.mod-desc  { font-size: 0.855em; color: #64748b; line-height: 1.6; margin-bottom: 14px; }
.mod-feat  { margin: 0; padding: 0; list-style: none; }
.mod-feat li {
  font-size: 0.8em; color: #475569;
  padding: 3px 0; display: flex; align-items: flex-start; gap: 7px;
}
.mod-feat li::before {
  content: "✓"; color: #3b82f6; font-weight: 700; font-size: 0.95em; margin-top:1px;
}

/* ── Actividad reciente ─────────────────────────────────────── */
.activity-wrap {
  background: white;
  border-radius: 14px;
  padding: 18px 22px;
  box-shadow: 0 2px 10px rgba(0,0,0,.06);
  border: 1px solid #f1f5f9;
}
.activity-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 9px 0;
  border-bottom: 1px solid #f8fafc;
  font-size: 0.84em;
}
.activity-row:last-child { border-bottom: none; }
.act-title { font-weight: 600; color: #1e293b; flex: 1; }
.act-meta  { color: #94a3b8; font-size: 0.9em; white-space: nowrap; margin-left: 12px; }
.act-badge {
  background: #eff6ff; color: #1d4ed8;
  border-radius: 6px;
  padding: 2px 8px; font-size: 0.82em; font-weight: 600; margin-left: 8px;
}

/* ── Section label ──────────────────────────────────────────── */
.section-label {
  font-size: 0.72em; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: #94a3b8; margin-bottom: 12px; display: block;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar()

# ═══════════════════════════════════════════════════════════════════════════════
# HERO BANNER
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="home-hero">
  <h1>📝 Generador de Exámenes</h1>
  <div class="subtitle">Unidad de Física Médica · Universidad Complutense de Madrid</div>
  <div class="badges">
    <span class="badge">v43</span>
    <span class="badge">Curso 2025–2026</span>
    <span class="badge">☁️ Cloud + Local</span>
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

    sm1, sm2, sm3, sm4, sm5 = st.columns(5)
    sm1.markdown(
        f"<div class='stat-hero'><div class='stat-hero-num'>{len(df)}</div>"
        f"<div class='stat-hero-lbl'>📚 TOTAL PREGUNTAS</div></div>",
        unsafe_allow_html=True)
    sm2.markdown(
        f"<div class='stat-hero ok'><div class='stat-hero-num' style='color:#16a34a'>{usadas}</div>"
        f"<div class='stat-hero-lbl'>✅ USADAS</div></div>",
        unsafe_allow_html=True)
    sm3.markdown(
        f"<div class='stat-hero warn'><div class='stat-hero-num' style='color:#d97706'>{nunca}</div>"
        f"<div class='stat-hero-lbl'>🆕 SIN USAR</div></div>",
        unsafe_allow_html=True)
    sm4.markdown(
        f"<div class='stat-hero pur'><div class='stat-hero-num' style='color:#7c3aed'>{pct}%</div>"
        f"<div class='stat-hero-lbl'>🎯 COBERTURA</div></div>",
        unsafe_allow_html=True)
    sm5.markdown(
        f"<div class='stat-hero red'><div class='stat-hero-num' style='color:#dc2626'>{n_sel}</div>"
        f"<div class='stat-hero-lbl'>🔢 SELECCIONADAS</div></div>",
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
else:
    st.info("⚠️ Conecta la base de datos desde la barra lateral para ver las estadísticas.")
    st.markdown("<br>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULOS (tarjetas)
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<span class='section-label'>Módulos</span>", unsafe_allow_html=True)
mc1, mc2, mc3 = st.columns(3)

with mc1:
    st.markdown("""
    <div class="mod-card">
      <div class="mod-icon-wrap blue">🗄️</div>
      <div class="mod-title">Gestor de Base de Datos</div>
      <div class="mod-desc">
        Gestiona el banco de preguntas: añade, edita, importa y analiza la cobertura por bloques y temas.
      </div>
      <ul class="mod-feat">
        <li>Añadir preguntas con validación de duplicados</li>
        <li>Importar desde Word, PDF o formato Aiken</li>
        <li>Editor con diálogo modal de edición</li>
        <li>Operaciones masivas (tema, dificultad, eliminar)</li>
        <li>Dashboard de cobertura y dificultad</li>
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
      <div class="mod-icon-wrap indigo">🎲</div>
      <div class="mod-title">Generador de Exámenes</div>
      <div class="mod-desc">
        Crea exámenes equilibrados: selección manual o relleno automático por bloques, temas y dificultad.
      </div>
      <ul class="mod-feat">
        <li>Selección manual con filtros avanzados</li>
        <li>Relleno automático por bloque y dificultad</li>
        <li>Preguntas de desarrollo/abiertas adicionales</li>
        <li>Vista previa con renderizado MathJax</li>
        <li>Exportar a Word y LaTeX (múltiples modelos)</li>
        <li>Presets de configuración e historial</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Abrir Generador →", use_container_width=True, type="primary", key="btn_home_gen"):
        st.switch_page("pages/2_Generador.py")

with mc3:
    st.markdown("""
    <div class="mod-card">
      <div class="mod-icon-wrap green">⚙️</div>
      <div class="mod-title">Configuración</div>
      <div class="mod-desc">
        Personaliza los nombres de bloques y temas para que aparezcan en toda la aplicación.
      </div>
      <ul class="mod-feat">
        <li>Asignar nombres descriptivos a bloques</li>
        <li>Asignar nombres a temas individuales</li>
        <li>Los nombres se muestran en filtros y estadísticas</li>
        <li>Se guardan en la propia base de datos</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Abrir Configuración →", use_container_width=True, key="btn_home_cfg"):
        st.switch_page("pages/3_Configuracion.py")

# ── Fila inferior: Actividad reciente + Ayuda rápida ──────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
col_act, col_help = st.columns([3, 2], gap="large")

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

with col_help:
    st.markdown("<span class='section-label'>Inicio rápido</span>", unsafe_allow_html=True)
    st.markdown("""
    <div class='activity-wrap'>
      <div class='activity-row'><span class='act-title'>1. Conecta tu base de datos</span>
        <span class='act-badge'>Sidebar</span></div>
      <div class='activity-row'><span class='act-title'>2. Añade o importa preguntas</span>
        <span class='act-badge'>Gestor DB</span></div>
      <div class='activity-row'><span class='act-title'>3. Configura nombres de bloques</span>
        <span class='act-badge'>Config.</span></div>
      <div class='activity-row'><span class='act-title'>4. Genera y previsualiza el examen</span>
        <span class='act-badge'>Generador</span></div>
      <div class='activity-row'><span class='act-title'>5. Exporta a Word / LaTeX</span>
        <span class='act-badge'>Generador</span></div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("📖 Manual de uso completo →", use_container_width=True, key="btn_home_help"):
        st.switch_page("pages/4_Ayuda.py")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Generador Exámenes v43 · Unidad de Física Médica · UCM · {datetime.date.today().year}")
