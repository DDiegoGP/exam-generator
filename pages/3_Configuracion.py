"""
pages/3_Configuracion.py  –  Configuración de la base de datos.

Permite asignar nombres descriptivos a bloques y temas, y añadir notas
sobre la asignatura. Los cambios se guardan en hojas ocultas del Excel
(Cfg_Bloques, Cfg_Temas, Cfg_General) y son visibles en toda la app.
"""
import streamlit as st
import pandas as pd
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import examen_lib_latex as lib
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback,
    APP_CSS, page_header, _load_cfg, _nsort,
)

st.set_page_config(page_title="Configuración · Exámenes UCM", page_icon="⚙️", layout="wide")
init_session_state()
handle_oauth_callback()
st.markdown(APP_CSS, unsafe_allow_html=True)
render_sidebar()

page_header("⚙️", "Configuración", "Nombres de bloques, temas y notas de la asignatura")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos desde la barra lateral antes de continuar.")
    st.stop()

# ── Asegurar que las hojas de config existen ──────────────────────────────────
dfs = st.session_state.excel_dfs
dfs = lib.init_cfg_from_data(dfs)
st.session_state.excel_dfs = dfs

bloques_list = st.session_state.bloques  # ya filtrados de CFG_SHEETS

tab_bloques, tab_temas, tab_notas = st.tabs(["📦 Bloques", "📌 Temas", "📝 Notas"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · BLOQUES
# ══════════════════════════════════════════════════════════════════════════════
with tab_bloques:
    st.markdown("#### Nombres descriptivos de bloques")
    st.caption(
        "Escribe una descripción para cada bloque. En la app aparecerá como "
        "**'Bloque IX — Óptica'** en filtros, estadísticas y exportación."
    )

    cfg_b = st.session_state.excel_dfs.get(
        lib.CFG_BLOQUES_SHEET,
        pd.DataFrame({"Bloque": bloques_list, "Descripcion": [""] * len(bloques_list)})
    ).copy()

    edited_b = st.data_editor(
        cfg_b,
        column_config={
            "Bloque":      st.column_config.TextColumn("Bloque (ID interno)", disabled=True, width="medium"),
            "Descripcion": st.column_config.TextColumn("Descripción", width="large",
                                                        help="Ej: Óptica, Electromagnetismo, Radiación Ionizante…"),
        },
        hide_index=True,
        use_container_width=True,
        key="editor_bloques",
        num_rows="fixed",
    )

    if st.button("💾 Guardar nombres de bloques", type="primary", key="btn_save_bloques"):
        dfs = lib.save_cfg_bloques(st.session_state.excel_dfs, edited_b)
        dfs = _load_cfg(dfs)
        st.session_state.excel_dfs  = dfs
        st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
        path = st.session_state.get("excel_path", "")
        if path:
            lib.guardar_excel_local(path, dfs)
        st.success("✅ Nombres de bloques guardados.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · TEMAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_temas:
    st.markdown("#### Nombres descriptivos de temas")
    st.caption(
        "Asigna un nombre a cada tema. En la app aparecerá como "
        "**'Tema 39: Óptica geométrica'**. Filtra por bloque para editar más cómodamente."
    )

    cfg_t = st.session_state.excel_dfs.get(
        lib.CFG_TEMAS_SHEET,
        pd.DataFrame({"Tema": [], "Nombre": [], "Bloque": []})
    ).copy()

    # Normalizar Tema (quitar .0)
    if not cfg_t.empty and "Tema" in cfg_t.columns:
        cfg_t["Tema"] = cfg_t["Tema"].astype(str).str.replace(r"\.0$", "", regex=True)

    # Filtro por bloque
    f_blq = st.selectbox("Filtrar por bloque:", ["Todos"] + bloques_list, key="cfg_t_blq")
    cfg_t_show = cfg_t[cfg_t["Bloque"] == f_blq].copy() if f_blq != "Todos" else cfg_t.copy()

    edited_t = st.data_editor(
        cfg_t_show,
        column_config={
            "Tema":   st.column_config.TextColumn("Nº Tema", disabled=True, width="small"),
            "Nombre": st.column_config.TextColumn("Nombre descriptivo", width="large",
                                                   help="Ej: Óptica geométrica, Ley de Faraday…"),
            "Bloque": st.column_config.SelectboxColumn(
                "Bloque", options=bloques_list, width="medium",
                help="Bloque al que pertenece este tema"
            ),
        },
        hide_index=True,
        use_container_width=True,
        key="editor_temas",
        num_rows="fixed",
    )

    if st.button("💾 Guardar nombres de temas", type="primary", key="btn_save_temas"):
        if f_blq != "Todos":
            other  = cfg_t[cfg_t["Bloque"] != f_blq]
            merged = pd.concat([other, edited_t], ignore_index=True)
        else:
            merged = edited_t

        # Reordenar por tema numérico
        try:
            merged["_sort"] = merged["Tema"].apply(
                lambda t: [int(x) if x.isdigit() else x.lower()
                           for x in __import__("re").split(r"(\d+)", str(t))]
            )
            merged = merged.sort_values("_sort").drop(columns=["_sort"])
        except Exception:
            pass

        dfs = lib.save_cfg_temas(st.session_state.excel_dfs, merged)
        dfs = _load_cfg(dfs)
        st.session_state.excel_dfs   = dfs
        st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
        path = st.session_state.get("excel_path", "")
        if path:
            lib.guardar_excel_local(path, dfs)
        st.success("✅ Nombres de temas guardados.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · NOTAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_notas:
    st.markdown("#### Notas de la asignatura")
    st.caption("Texto libre. Solo visible en la app, no se exporta.")

    cfg_g    = st.session_state.get("cfg_general", {})
    notas_v  = cfg_g.get("notas", "")

    notas = st.text_area(
        "Notas",
        value=notas_v if str(notas_v) not in ("nan", "None") else "",
        height=220,
        placeholder="Descripción del curso, año académico, observaciones generales…",
        key="cfg_notas_area",
        label_visibility="collapsed",
    )

    if st.button("💾 Guardar notas", type="primary", key="btn_save_notas"):
        cfg_g_new = dict(cfg_g)
        cfg_g_new["notas"] = notas
        dfs = lib.save_cfg_general(st.session_state.excel_dfs, cfg_g_new)
        dfs = _load_cfg(dfs)
        st.session_state.excel_dfs   = dfs
        st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
        path = st.session_state.get("excel_path", "")
        if path:
            lib.guardar_excel_local(path, dfs)
        st.success("✅ Notas guardadas.")
        st.rerun()

    notas_saved = st.session_state.get("cfg_general", {}).get("notas", "")
    if notas_saved:
        st.divider()
        st.markdown("**Notas actuales:**")
        st.markdown(notas_saved)
