"""
pages/2_Generador.py  –  Generador de exámenes.

Pestañas:
  1. Selección    – Filtros + lista disponible/seleccionada + relleno automático
  2. Desarrollo   – Preguntas de desarrollo / abiertas
  3. Preview      – Vista previa HTML con MathJax
  4. Exportar     – Configuración del examen + exportar Word/LaTeX/CSV
  5. Historial    – Últimos exámenes generados
"""
import streamlit as st
import pandas as pd
import datetime
import random
import os
import sys
import re
import json
import tempfile
from itertools import groupby

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import streamlit.components.v1 as stcomponents
import examen_lib_latex as lib
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback, APP_CSS, page_header,
    reload_db, bloques_disponibles, temas_de_bloque,
    es_uso_antiguo, render_question_card_html, mathjax_html,
    append_historial, save_preset, delete_preset,
    OUTPUT_DIR, _nsort,
)

# ── Configuración ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Generador · Exámenes UCM", page_icon="🎲", layout="wide")
init_session_state()
handle_oauth_callback()
st.markdown(APP_CSS, unsafe_allow_html=True)
render_sidebar()

_n_sel = len(st.session_state.sel_ids)
st.title("🎲 Generador de Exámenes")
st.caption(f"{_n_sel} preguntas seleccionadas" if _n_sel else "Selecciona preguntas para el examen")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos desde la barra lateral antes de continuar.")
    st.stop()

df_total: pd.DataFrame = st.session_state.df_preguntas
bloques = bloques_disponibles()

def nsort(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]

# ── Helpers de estado ─────────────────────────────────────────────────────────
def get_sel_ids() -> list:
    return st.session_state.manual_order  # manual_order es la lista ordenada

def set_sel_ids(ids: list):
    st.session_state.manual_order = list(ids)
    st.session_state.sel_ids = list(ids)

# ═════════════════════════════════════════════════════════════════════════════
# DIALOG: CONFIGURACIÓN DE RELLENO AUTOMÁTICO
# ═════════════════════════════════════════════════════════════════════════════
@st.dialog("🤖 Configuración de relleno automático", width="large")
def _dialog_autofill(n_obj: int):
    """Modal para configurar la receta de generación aleatoria."""
    df_all  = st.session_state.df_preguntas
    blqs    = st.session_state.bloques or []
    manual  = st.session_state.manual_order or []
    recipe  = dict(st.session_state.get("auto_recipe", {}))

    if not blqs or df_all.empty:
        st.warning("Conecta la base de datos antes de usar el auto-relleno.")
        return

    n_manual  = len(manual)
    manual_set = set(manual)

    # Resumen superior
    st.markdown(
        f"<div style='background:#e8f4fd;border:1px solid #aed6f1;border-radius:8px;"
        f"padding:10px 16px;margin-bottom:10px;font-size:0.87em;color:#1a5276'>"
        f"📌 <b>Fijas (manual):</b> {n_manual} &nbsp;·&nbsp; "
        f"<b>Objetivo:</b> {n_obj} &nbsp;·&nbsp; "
        f"<b>Slots auto disponibles:</b> {max(0, n_obj - n_manual)}"
        f"</div>",
        unsafe_allow_html=True
    )
    st.caption(
        "Selecciona un bloque y configura cuántas preguntas por dificultad/tema añadir "
        "automáticamente al generar. La receta se guarda hasta que la limpies."
    )

    sel_blq = st.selectbox("📦 Bloque a configurar:", blqs, key="af_dlg_blq_sel")

    if sel_blq:
        df_blq  = df_all[df_all["bloque"] == sel_blq]
        df_avail = df_blq[~df_blq["ID_Pregunta"].isin(manual_set)]
        key_blq  = re.sub(r"[^a-zA-Z0-9]", "_", sel_blq)
        blq_saved = recipe.get(sel_blq, {})
        n_fix_blq = len(df_blq) - len(df_avail)

        st.markdown(
            f"<span style='color:#555;font-size:0.85em'>"
            f"{len(df_avail)} disponibles · {n_fix_blq} de este bloque ya son manuales fijas"
            f"</span>",
            unsafe_allow_html=True
        )

        # ── Sección: cualquier tema ───────────────────────────────────────────
        st.markdown("##### 📋 De cualquier tema en este bloque:")
        n_f_all = int((df_avail["dificultad"].str.lower() == "facil").sum())
        n_m_all = int((df_avail["dificultad"].str.lower() == "media").sum())
        n_d_all = int((df_avail["dificultad"].str.lower().isin(["dificil", "difícil"])).sum())
        all_saved = blq_saved.get("__ALL__", {})

        ac1, ac2, ac3 = st.columns(3)
        ac1.number_input(f"🟢 Fácil (disp: {n_f_all})", min_value=0,
                          value=int(all_saved.get("facil", 0)),
                          key=f"af_{key_blq}_ALL_f")
        ac2.number_input(f"🟡 Media (disp: {n_m_all})", min_value=0,
                          value=int(all_saved.get("media", 0)),
                          key=f"af_{key_blq}_ALL_m")
        ac3.number_input(f"🔴 Difícil (disp: {n_d_all})", min_value=0,
                          value=int(all_saved.get("dificil", 0)),
                          key=f"af_{key_blq}_ALL_d")

        # ── Sección: por tema ─────────────────────────────────────────────────
        temas_blq = sorted(df_blq["Tema"].unique().tolist(), key=_nsort)
        if temas_blq:
            st.markdown("##### 📌 Por tema específico (acumulativo al anterior):")
            th0, th1, th2, th3 = st.columns([3, 1, 1, 1])
            th0.markdown("<small><b>Tema</b></small>", unsafe_allow_html=True)
            th1.markdown("<small style='color:#27ae60'><b>🟢 Fácil</b></small>",
                         unsafe_allow_html=True)
            th2.markdown("<small style='color:#b7950b'><b>🟡 Media</b></small>",
                         unsafe_allow_html=True)
            th3.markdown("<small style='color:#c0392b'><b>🔴 Difícil</b></small>",
                         unsafe_allow_html=True)

            for tema in temas_blq:
                df_t  = df_avail[df_avail["Tema"].astype(str) == str(tema)]
                n_ft  = int((df_t["dificultad"].str.lower() == "facil").sum())
                n_mt  = int((df_t["dificultad"].str.lower() == "media").sum())
                n_dt  = int((df_t["dificultad"].str.lower().isin(["dificil", "difícil"])).sum())
                t_saved = blq_saved.get(str(tema), {})
                key_t = re.sub(r"[^a-zA-Z0-9]", "_", f"{sel_blq}_{tema}")

                tc0, tc1, tc2, tc3 = st.columns([3, 1, 1, 1])
                tc0.markdown(
                    f"<small><b>Tema {tema}</b> &nbsp;"
                    f"<span style='color:#888'>🟢{n_ft} 🟡{n_mt} 🔴{n_dt}</span></small>",
                    unsafe_allow_html=True
                )
                tc1.number_input("f", min_value=0, max_value=n_ft,
                                  value=int(t_saved.get("facil", 0)),
                                  key=f"af_{key_t}_f",
                                  label_visibility="collapsed")
                tc2.number_input("m", min_value=0, max_value=n_mt,
                                  value=int(t_saved.get("media", 0)),
                                  key=f"af_{key_t}_m",
                                  label_visibility="collapsed")
                tc3.number_input("d", min_value=0, max_value=n_dt,
                                  value=int(t_saved.get("dificil", 0)),
                                  key=f"af_{key_t}_d",
                                  label_visibility="collapsed")

    # ── Total configurado (leyendo session_state + receta guardada) ───────────
    total_cfg = 0
    for blq in blqs:
        k_blq   = re.sub(r"[^a-zA-Z0-9]", "_", blq)
        prev_b  = recipe.get(blq, {})
        all_p   = prev_b.get("__ALL__", {})
        total_cfg += (
            st.session_state.get(f"af_{k_blq}_ALL_f", all_p.get("facil",  0)) +
            st.session_state.get(f"af_{k_blq}_ALL_m", all_p.get("media",  0)) +
            st.session_state.get(f"af_{k_blq}_ALL_d", all_p.get("dificil", 0))
        )
        df_blq2 = df_all[df_all["bloque"] == blq]
        for tema in df_blq2["Tema"].unique().tolist():
            kt   = re.sub(r"[^a-zA-Z0-9]", "_", f"{blq}_{tema}")
            tp   = prev_b.get(str(tema), {})
            total_cfg += (
                st.session_state.get(f"af_{kt}_f", tp.get("facil",  0)) +
                st.session_state.get(f"af_{kt}_m", tp.get("media",  0)) +
                st.session_state.get(f"af_{kt}_d", tp.get("dificil", 0))
            )

    total_final = n_manual + total_cfg
    color_tot   = "#27ae60" if total_final <= n_obj else "#e74c3c"

    st.markdown("---")
    st.markdown(
        f"**Auto:** {total_cfg} &nbsp;·&nbsp; **Manuales fijas:** {n_manual} &nbsp;·&nbsp; "
        f"**Total estimado:** <span style='font-weight:800;color:{color_tot}'>"
        f"{total_final} / {n_obj}</span>",
        unsafe_allow_html=True
    )
    if total_final > n_obj:
        st.warning(f"⚠️ El total supera el objetivo por {total_final - n_obj} pregunta(s). "
                   "Ajusta las cantidades o aumenta el objetivo.")

    bc1, _, bc2 = st.columns([1, 2, 1])
    if bc1.button("🗑️ Limpiar receta", key="af_dlg_clear"):
        keys_af = [k for k in st.session_state if k.startswith("af_")]
        for k in keys_af:
            del st.session_state[k]
        st.session_state["auto_recipe"] = {}
        st.rerun()

    if bc2.button("✅ Guardar receta", type="primary", key="af_dlg_ok"):
        new_recipe = {}
        for blq in blqs:
            k_blq  = re.sub(r"[^a-zA-Z0-9]", "_", blq)
            prev_b = recipe.get(blq, {})
            all_p  = prev_b.get("__ALL__", {})
            blq_r  = {}

            af = st.session_state.get(f"af_{k_blq}_ALL_f", all_p.get("facil",  0))
            am = st.session_state.get(f"af_{k_blq}_ALL_m", all_p.get("media",  0))
            ad = st.session_state.get(f"af_{k_blq}_ALL_d", all_p.get("dificil", 0))
            if af + am + ad > 0:
                blq_r["__ALL__"] = {"facil": af, "media": am, "dificil": ad}

            df_blq2 = df_all[df_all["bloque"] == blq]
            for tema in df_blq2["Tema"].unique().tolist():
                kt = re.sub(r"[^a-zA-Z0-9]", "_", f"{blq}_{tema}")
                tp = prev_b.get(str(tema), {})
                tf = st.session_state.get(f"af_{kt}_f", tp.get("facil",  0))
                tm = st.session_state.get(f"af_{kt}_m", tp.get("media",  0))
                td = st.session_state.get(f"af_{kt}_d", tp.get("dificil", 0))
                if tf + tm + td > 0:
                    blq_r[str(tema)] = {"facil": tf, "media": tm, "dificil": td}

            if blq_r:
                new_recipe[blq] = blq_r

        st.session_state["auto_recipe"] = new_recipe
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# PESTAÑAS
# ═════════════════════════════════════════════════════════════════════════════
tab_sel, tab_dev, tab_prev, tab_exp, tab_hist = st.tabs(
    ["🔢 Selección", "✍️ Desarrollo", "👁️ Preview", "💾 Exportar", "📋 Historial"]
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 · SELECCIÓN
# ─────────────────────────────────────────────────────────────────────────────
with tab_sel:
    sel_ids_actual = get_sel_ids()
    n_sel = len(sel_ids_actual)

    # ── Objetivo + botón auto-relleno ─────────────────────────────────────────
    oc1, oc2 = st.columns([3, 2])
    with oc1:
        n_obj = st.number_input(
            "🎯 Objetivo (nº de preguntas)", min_value=1, max_value=200,
            value=st.session_state.get("tgt_pregs", 20), key="tgt_pregs"
        )
    with oc2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("🤖 Auto-relleno", use_container_width=True, key="btn_auto_dlg",
                     help="Configurar selección automática por bloque / tema / dificultad",
                     type="secondary"):
            _dialog_autofill(n_obj)

    # ── Resumen receta activa ─────────────────────────────────────────────────
    recipe = st.session_state.get("auto_recipe", {})
    if recipe:
        total_r, parts = 0, []
        for blq, temas_cfg in recipe.items():
            blq_t = sum(v for difs in temas_cfg.values() for v in difs.values())
            if blq_t > 0:
                parts.append(f"{blq}: {blq_t}")
                total_r += blq_t
        summary_str = " · ".join(parts[:4]) + (" ···" if len(parts) > 4 else "")
        rc1, rc2 = st.columns([9, 1])
        rc1.markdown(
            f"<div style='background:#e8f4fd;border:1px solid #aed6f1;border-radius:6px;"
            f"padding:5px 12px;font-size:0.83em;color:#1a5276'>"
            f"🤖 <b>Receta activa</b> — {total_r} preg. auto  ·  {summary_str}</div>",
            unsafe_allow_html=True
        )
        if rc2.button("✖", key="btn_clear_recipe_sel", help="Eliminar receta automática"):
            st.session_state["auto_recipe"] = {}
            st.rerun()

    # ── Filtros (colapsables para maximizar espacio) ──────────────────────────
    with st.expander("🔍 Filtros", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        f_bloque = fc1.selectbox("Bloque", ["Todos"] + bloques, key="sel_f_bloque")
        temas_disp = (temas_de_bloque(f_bloque) if f_bloque != "Todos"
                      else sorted(df_total["Tema"].unique().tolist(), key=_nsort))
        f_tema   = fc2.selectbox("Tema", ["Todos"] + [str(t) for t in temas_disp],
                                  key="sel_f_tema")
        f_dif    = fc3.selectbox("Dificultad", ["Todas", "Facil", "Media", "Dificil"],
                                  key="sel_f_dif")
        f_uso    = fc4.selectbox(
            "Uso", ["Todos", "Nunca usada", "Usada", "Usada >6 meses", "Usada >12 meses"],
            key="sel_f_uso"
        )
        f_search = fc5.text_input("Buscar", placeholder="Texto...", key="sel_search")

    # Aplicar filtros
    df_filt = df_total.copy()
    df_filt = df_filt[~df_filt["ID_Pregunta"].isin(sel_ids_actual)]
    if f_bloque != "Todos":
        df_filt = df_filt[df_filt["bloque"] == f_bloque]
    if f_tema != "Todos":
        df_filt = df_filt[df_filt["Tema"].astype(str) == f_tema]
    if f_dif != "Todas":
        df_filt = df_filt[df_filt["dificultad"].str.lower() == f_dif.lower()]
    if f_uso == "Nunca usada":
        df_filt = df_filt[df_filt["usada"] == ""]
    elif f_uso == "Usada":
        df_filt = df_filt[df_filt["usada"] != ""]
    elif f_uso == "Usada >6 meses":
        df_filt = df_filt[df_filt["usada"].apply(lambda v: es_uso_antiguo(v, 6))]
    elif f_uso == "Usada >12 meses":
        df_filt = df_filt[df_filt["usada"].apply(lambda v: es_uso_antiguo(v, 12))]
    if f_search:
        q = f_search.lower()
        mask = df_filt["enunciado"].str.lower().str.contains(q, na=False)
        ops_mask = df_filt["opciones_list"].apply(
            lambda ops: any(q in str(o).lower() for o in ops)
            if isinstance(ops, list) else False
        )
        df_filt = df_filt[mask | ops_mask]

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYOUT 3 COLUMNAS: disponibles | preview | fijas
    # ═══════════════════════════════════════════════════════════════════════════
    col_list, col_prev, col_sel = st.columns([2, 3, 2])

    # ── Columna izquierda: lista de disponibles ────────────────────────────────
    with col_list:
        lh1, lh2 = st.columns([3, 2])
        lh1.markdown(f"**Disponibles — {len(df_filt)}**")
        if lh2.button("➕ Todas", key="btn_add_all",
                      help="Añadir todas las preguntas filtradas como fijas",
                      disabled=(len(df_filt) == 0), use_container_width=True):
            cur = get_sel_ids()
            for pid in df_filt["ID_Pregunta"].tolist():
                if pid not in cur:
                    cur.append(pid)
            set_sel_ids(cur)
            st.rerun()

        display_avail = df_filt[["ID_Pregunta", "Tema", "dificultad", "enunciado"]].copy()
        display_avail["enunciado"] = display_avail["enunciado"].str[:60]
        display_avail.columns = ["ID", "T", "Dif", "Enunciado"]
        display_avail = display_avail.reset_index(drop=True)

        sel_avail = st.dataframe(
            display_avail,
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="df_avail",
            height=480,
            column_config={
                "ID":        st.column_config.TextColumn("ID", width=120),
                "T":         st.column_config.TextColumn("T", width=30),
                "Dif":       st.column_config.TextColumn("Dif", width=50),
                "Enunciado": st.column_config.TextColumn("Enunciado", width="large"),
            },
        )
        avail_sel_rows = sel_avail.selection.rows if sel_avail.selection else []
        if avail_sel_rows:
            new_avail_pid = df_filt.iloc[avail_sel_rows[0]]["ID_Pregunta"]
            if new_avail_pid != st.session_state.get("_last_avail_pid"):
                st.session_state["_last_avail_pid"] = new_avail_pid
                st.session_state["sel_preview_pid"] = new_avail_pid

    # ── Columna central: preview ───────────────────────────────────────────────
    with col_prev:
        preview_pid = st.session_state.get("sel_preview_pid")
        if preview_pid:
            row_insp = df_total[df_total["ID_Pregunta"] == preview_pid]
            if not row_insp.empty:
                row_d_prev = dict(row_insp.iloc[0])
                card_html_prev = render_question_card_html(row_d_prev, show_sol=True)
                st.markdown(card_html_prev, unsafe_allow_html=True)

                # Botones añadir / quitar
                is_sel = preview_pid in sel_ids_actual
                pa1, pa2 = st.columns(2)
                if is_sel:
                    if pa1.button("➖ Quitar del examen", key="btn_prev_rem",
                                   use_container_width=True):
                        cur = get_sel_ids()
                        if preview_pid in cur:
                            cur.remove(preview_pid)
                        set_sel_ids(cur)
                        st.rerun()
                else:
                    if pa1.button("➕ Añadir al examen", key="btn_prev_add",
                                   use_container_width=True, type="primary"):
                        cur = get_sel_ids()
                        if preview_pid not in cur:
                            cur.append(preview_pid)
                        set_sel_ids(cur)
                        st.rerun()

                # Botón MathJax
                _mjax_key_sel = f"mjax_sel_{preview_pid}"
                if pa2.button("∑ Renderizar LaTeX", key=f"mjax_btn_sel_{preview_pid}",
                               use_container_width=True):
                    st.session_state[_mjax_key_sel] = True
                if st.session_state.get(_mjax_key_sel, False):
                    mj1, mj2 = st.columns([1, 3])
                    if mj1.button("✖ Cerrar LaTeX", key=f"mjax_close_sel_{preview_pid}",
                                   use_container_width=True):
                        st.session_state[_mjax_key_sel] = False
                        st.rerun()
                    stcomponents.html(mathjax_html(card_html_prev), height=480, scrolling=True)
            else:
                st.info("Selecciona una pregunta de la lista para previsualizarla.")
        else:
            st.markdown(
                "<div style='background:#f8f9fa;border:2px dashed #dee2e6;"
                "border-radius:12px;padding:60px 20px;text-align:center;"
                "color:#bbb;margin-top:30px'>"
                "<div style='font-size:2.5em;margin-bottom:12px'>👈</div>"
                "<div style='font-weight:600;font-size:1em;color:#aaa'>"
                "Haz clic en una pregunta</div>"
                "<div style='font-size:0.85em;margin-top:6px;color:#ccc'>"
                "para previsualizarla aquí</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    # ── Columna derecha: preguntas fijas ──────────────────────────────────────
    with col_sel:
        pct_obj   = min(100, int(n_sel / n_obj * 100)) if n_obj else 0
        bar_color = "#27ae60" if n_sel >= n_obj else "#3498db"
        st.markdown(
            f"<div style='margin-bottom:4px'>"
            f"<b>📌 Fijas</b>"
            f"<span style='float:right;font-size:0.9em;font-weight:700;color:{bar_color}'>"
            f"{n_sel} / {n_obj}</span></div>"
            f"<div style='background:#e9ecef;border-radius:4px;height:6px;margin-bottom:8px'>"
            f"<div style='width:{pct_obj}%;height:6px;border-radius:4px;"
            f"background:{bar_color}'></div></div>",
            unsafe_allow_html=True,
        )

        if sel_ids_actual:
            df_sel = df_total[df_total["ID_Pregunta"].isin(sel_ids_actual)].copy()
            id_order = {pid: i for i, pid in enumerate(sel_ids_actual)}
            df_sel["_ord"] = df_sel["ID_Pregunta"].map(id_order)
            df_sel = df_sel.sort_values("_ord").drop(columns=["_ord"]).reset_index(drop=True)

            display_sel = df_sel[["ID_Pregunta", "Tema", "dificultad"]].copy()
            display_sel.columns = ["ID", "T", "Dif"]
            display_sel = display_sel.reset_index(drop=True)

            sel_right = st.dataframe(
                display_sel,
                use_container_width=True,
                hide_index=False,
                selection_mode="single-row",
                on_select="rerun",
                key="df_sel",
                height=380,
                column_config={
                    "ID":  st.column_config.TextColumn("ID", width=120),
                    "T":   st.column_config.TextColumn("T", width=30),
                    "Dif": st.column_config.TextColumn("Dif", width=50),
                },
            )
            right_sel_rows = sel_right.selection.rows if sel_right.selection else []
            right_sel_pid = (df_sel.iloc[right_sel_rows[0]]["ID_Pregunta"]
                             if right_sel_rows else None)
            # Clic en fijas → actualizar preview (sólo si cambió)
            if right_sel_pid:
                if right_sel_pid != st.session_state.get("_last_sel_pid"):
                    st.session_state["_last_sel_pid"] = right_sel_pid
                    st.session_state["sel_preview_pid"] = right_sel_pid

            # Botones de reordenar / quitar
            sb1, sb2, sb3 = st.columns(3)
            if sb1.button("⬆️", key="btn_up", disabled=(right_sel_pid is None),
                          use_container_width=True, help="Subir"):
                cur = get_sel_ids()
                idx = cur.index(right_sel_pid) if right_sel_pid in cur else -1
                if idx > 0:
                    cur[idx], cur[idx - 1] = cur[idx - 1], cur[idx]
                    set_sel_ids(cur)
                st.rerun()
            if sb2.button("⬇️", key="btn_dn", disabled=(right_sel_pid is None),
                          use_container_width=True, help="Bajar"):
                cur = get_sel_ids()
                idx = cur.index(right_sel_pid) if right_sel_pid in cur else -1
                if idx >= 0 and idx < len(cur) - 1:
                    cur[idx], cur[idx + 1] = cur[idx + 1], cur[idx]
                    set_sel_ids(cur)
                st.rerun()
            if sb3.button("🗑️", key="btn_rem2", disabled=(right_sel_pid is None),
                          use_container_width=True, help="Quitar del examen"):
                cur = get_sel_ids()
                if right_sel_pid in cur:
                    cur.remove(right_sel_pid)
                set_sel_ids(cur)
                st.rerun()

            if st.button("🗑️ Limpiar todo", key="btn_clear_all",
                         use_container_width=True):
                set_sel_ids([])
                st.rerun()
        else:
            st.markdown(
                "<div style='background:#f8f9fa;border:2px dashed #dee2e6;"
                "border-radius:10px;padding:30px 12px;text-align:center;"
                "color:#aaa;font-size:0.85em;margin-top:4px'>"
                "📭 Sin preguntas fijas<br>"
                "<span style='font-size:0.85em'>"
                "Añade desde el preview o usa 🤖</span>"
                "</div>",
                unsafe_allow_html=True,
            )

# TAB 2 · DESARROLLO
# ─────────────────────────────────────────────────────────────────────────────
with tab_dev:
    st.subheader("Preguntas de desarrollo / abiertas")
    st.caption("Estas preguntas se incluirán como PARTE I del examen (cuestiones abiertas).")

    # Obtener / inicializar lista de preguntas de desarrollo
    dev_qs: list = st.session_state.dev_questions

    if st.button("➕ Añadir pregunta de desarrollo", key="btn_add_dev"):
        dev_qs.append({"txt": "", "pts": 1.0, "espacio": "Automático"})
        st.session_state.dev_questions = dev_qs
        st.rerun()

    to_delete = []
    for i, q in enumerate(dev_qs):
        with st.container():
            col_txt, col_pts, col_esp, col_del = st.columns([5, 1, 2, 1])
            new_txt = col_txt.text_area(f"Pregunta {i+1}", value=q["txt"],
                                         height=70, key=f"dev_txt_{i}",
                                         label_visibility="collapsed",
                                         placeholder="Enunciado de la pregunta de desarrollo...")
            new_pts = col_pts.number_input("Pts", value=float(q["pts"]),
                                            min_value=0.0, step=0.5, key=f"dev_pts_{i}",
                                            label_visibility="collapsed")
            new_esp = col_esp.selectbox("Espacio",
                                         ["Automático", "5 líneas", "10 líneas", "Media Cara", "Cara Completa"],
                                         index=["Automático", "5 líneas", "10 líneas", "Media Cara", "Cara Completa"].index(q.get("espacio","Automático")),
                                         key=f"dev_esp_{i}",
                                         label_visibility="collapsed")
            if col_del.button("🗑️", key=f"dev_del_{i}"):
                to_delete.append(i)
            # Actualizar en session_state
            dev_qs[i] = {"txt": new_txt, "pts": new_pts, "espacio": new_esp}

    if to_delete:
        for i in sorted(to_delete, reverse=True):
            dev_qs.pop(i)
        st.session_state.dev_questions = dev_qs
        st.rerun()

    if dev_qs:
        st.session_state.dev_questions = dev_qs

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 · PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
with tab_prev:

    # ── Banner de modo recuperación ───────────────────────────────────────────
    if st.session_state.get("recovery_mode"):
        rb1, rb2 = st.columns([5, 1])
        rb1.warning(
            "🔒 **MODO RECUPERACIÓN** — Examen cargado desde CSV. "
            "El botón **Generar** está deshabilitado para evitar sobreescribir el preview."
        )
        if rb2.button("🔓 Desbloquear", key="btn_unlock_prev", use_container_width=True):
            st.session_state["recovery_mode"] = False
            st.rerun()

    # ── Controles ─────────────────────────────────────────────────────────────
    ctrl1, ctrl2, ctrl3, ctrl4, ctrl5 = st.columns([2, 2, 2, 1, 1])
    show_sol  = ctrl1.checkbox("Mostrar soluciones ✓", value=True, key="prev_show_sol")
    ord_prev  = ctrl2.selectbox("Orden",
                    ["Por bloques", "Global aleatorio", "Manual (selección)", "Sin barajar (ID)"],
                    key="prev_ord")
    seed_prev = ctrl3.number_input("Semilla (0=aleatoria)", min_value=0, value=0, key="prev_seed")
    _locked   = st.session_state.get("recovery_mode", False)
    gen_btn   = ctrl4.button("🎲 Generar", type="primary", key="btn_gen_prev",
                              use_container_width=True, disabled=_locked)
    mj_btn    = ctrl5.button("∑ MathJax", key="btn_mathjax", use_container_width=True,
                              help="Vista con fórmulas matemáticas renderizadas")

    sel_prev  = get_sel_ids()          # manuales fijas
    auto_rec  = st.session_state.get("auto_recipe", {})

    if gen_btn:
        if not sel_prev and not auto_rec:
            st.warning("⚠️ Sin preguntas seleccionadas ni receta automática — ve a la pestaña Selección.")
        else:
            rng          = random.Random(seed_prev if seed_prev else None)
            df_lookup    = df_total.set_index("ID_Pregunta").to_dict("index")
            exam_ids     = list(sel_prev)     # empezar con las manuales fijas
            already_used = set(exam_ids)
            warns_gen    = []

            # ── Aplicar receta automática ─────────────────────────────────────
            for bloque, temas_cfg in auto_rec.items():
                for tema_key, dif_cfg in temas_cfg.items():
                    for dif_name, n_req in dif_cfg.items():
                        if n_req <= 0:
                            continue
                        if tema_key == "__ALL__":
                            already_fixed = [
                                p for p in sel_prev
                                if df_lookup.get(p, {}).get("bloque", "") == bloque
                                and df_lookup.get(p, {}).get("dificultad", "").lower() == dif_name.lower()
                            ]
                            pool_ids = df_total[
                                (df_total["bloque"] == bloque) &
                                (df_total["dificultad"].str.lower() == dif_name.lower()) &
                                (~df_total["ID_Pregunta"].isin(already_used))
                            ]["ID_Pregunta"].tolist()
                            label_str = "(cualquier tema)"
                        else:
                            already_fixed = [
                                p for p in sel_prev
                                if df_lookup.get(p, {}).get("bloque", "") == bloque
                                and str(df_lookup.get(p, {}).get("Tema", "")) == str(tema_key)
                                and df_lookup.get(p, {}).get("dificultad", "").lower() == dif_name.lower()
                            ]
                            pool_ids = df_total[
                                (df_total["bloque"] == bloque) &
                                (df_total["Tema"].astype(str) == str(tema_key)) &
                                (df_total["dificultad"].str.lower() == dif_name.lower()) &
                                (~df_total["ID_Pregunta"].isin(already_used))
                            ]["ID_Pregunta"].tolist()
                            label_str = f"Tema {tema_key}"

                        needed = max(0, n_req - len(already_fixed))
                        actual = min(needed, len(pool_ids))
                        picked = rng.sample(pool_ids, actual) if actual > 0 else []
                        if actual < needed:
                            warns_gen.append(
                                f"**{bloque}** {label_str} {dif_name}: "
                                f"receta={n_req}, fijas={len(already_fixed)}, añadidas={actual}"
                            )
                        exam_ids.extend(picked)
                        already_used.update(picked)

            st.session_state["gen_warnings"] = warns_gen

            # ── Construir pool y ordenar ──────────────────────────────────────
            pool = df_total[df_total["ID_Pregunta"].isin(exam_ids)].to_dict("records")
            ord_key = ord_prev
            if ord_key == "Global aleatorio":
                rng.shuffle(pool)
            elif ord_key == "Sin barajar (ID)":
                pool.sort(key=lambda x: nsort(x.get("ID_Pregunta", "")))
            elif ord_key == "Manual (selección)":
                pos = {pid: i for i, pid in enumerate(exam_ids)}
                pool.sort(key=lambda x: pos.get(x["ID_Pregunta"], 9999))
            else:  # Por bloques
                pool.sort(key=lambda x: nsort(x.get("bloque", "")))
                new_pool = []
                for _, grp in groupby(pool, key=lambda x: x.get("bloque", "")):
                    g = list(grp); rng.shuffle(g); new_pool.extend(g)
                pool = new_pool

            st.session_state.cache_examen = pool
            st.session_state.pop("prev_mathjax", None)
            st.rerun()

    # ── Mostrar avisos de la última generación ────────────────────────────────
    for w in st.session_state.get("gen_warnings", []):
        st.warning(f"⚠️ {w}")

    cache = st.session_state.cache_examen

    if not cache:
        n_auto_est = sum(v for tc in auto_rec.values() for d in tc.values() for v in d.values()) if auto_rec else 0
        if sel_prev or auto_rec:
            st.info(
                f"🔢 **{len(sel_prev)}** preguntas fijas"
                + (f" + receta auto (~{n_auto_est} adicionales)" if n_auto_est else "")
                + ". Pulsa **🎲 Generar** para crear el examen."
            )
        else:
            st.info("Selecciona preguntas en la pestaña **Selección** y pulsa **🎲 Generar**.")
    else:
        cfg  = st.session_state.get("exam_cfg", {})
        inst = cfg.get("inst", "UCM")
        asig = cfg.get("asig", "FÍSICA MÉDICA")

        # ── Cabecera del examen ───────────────────────────────────────────────
        st.markdown(
            f"<div style='background:linear-gradient(90deg,#2c3e50,#1a252f);color:white;"
            f"padding:14px 18px;border-radius:8px;margin-bottom:16px'>"
            f"<h3 style='margin:0;font-size:1.1em'>{inst} · {asig}</h3>"
            f"<p style='margin:4px 0 0 0;opacity:0.75;font-size:0.85em'>"
            f"{len(cache)} preguntas test"
            f"{'  +  ' + str(len(st.session_state.dev_questions)) + ' desarrollo' if st.session_state.dev_questions else ''}"
            f"</p></div>",
            unsafe_allow_html=True,
        )

        # ── Vista MathJax (iframe) ────────────────────────────────────────────
        if mj_btn:
            st.session_state["prev_mathjax"] = not st.session_state.get("prev_mathjax", False)
            st.rerun()

        if st.session_state.get("prev_mathjax"):
            # Construir HTML completo con MathJax
            dev_qs = st.session_state.dev_questions
            html_body = ""
            if dev_qs:
                html_body += "<h4 style='color:#2c3e50'>PARTE I — DESARROLLO</h4>"
                for i, q in enumerate(dev_qs):
                    html_body += f"<p><b>{i+1}. {q['txt']}</b> ({q['pts']} pts)</p>"
                html_body += "<hr style='margin:12px 0'>"
            html_body += f"<h4 style='color:#2c3e50'>PARTE II — TEST ({len(cache)} preguntas)</h4>"
            q_num = 0
            prev_blq = None
            for p in cache:
                blq = p.get("bloque", "")
                if blq != prev_blq:
                    n_f = sum(1 for x in cache if x.get("bloque") == blq and x.get("dificultad","").lower() in ("facil","fácil"))
                    n_m = sum(1 for x in cache if x.get("bloque") == blq and x.get("dificultad","").lower() == "media")
                    n_d = sum(1 for x in cache if x.get("bloque") == blq and x.get("dificultad","").lower() in ("dificil","difícil"))
                    html_body += (f'<div class="bloque-hdr">{blq}'
                                  f'<span>🟢{n_f} 🟡{n_m} 🔴{n_d}</span></div>')
                    prev_blq = blq
                q_num += 1
                html_body += render_question_card_html(p, show_sol=show_sol, num=q_num)
            full_html = mathjax_html(html_body)
            height_px = max(800, len(cache) * 200)
            st.caption("Vista MathJax — las fórmulas $...$ se renderizan correctamente.")
            stcomponents.html(full_html, height=min(height_px, 2200), scrolling=True)
        else:
            # ── Vista nativa Streamlit (cards con colores, sin iframe) ─────────
            dev_qs = st.session_state.dev_questions
            if dev_qs:
                st.markdown(
                    "<div style='background:#eaf4fb;border-left:4px solid #3498db;"
                    "border-radius:5px;padding:10px 14px;margin-bottom:12px'>"
                    "<b style='color:#2c3e50'>PARTE I — DESARROLLO</b></div>",
                    unsafe_allow_html=True
                )
                for i, q in enumerate(dev_qs):
                    st.markdown(
                        f"<div style='padding:6px 14px;margin-bottom:4px;border-left:3px solid #3498db'>"
                        f"<b>{i+1}.</b> {q['txt']} <span style='color:#888;font-size:0.85em'>({q['pts']} pts · {q['espacio']})</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

            st.markdown(
                f"<div style='background:#eaf4fb;border-left:4px solid #3498db;"
                f"border-radius:5px;padding:10px 14px;margin-bottom:12px'>"
                f"<b style='color:#2c3e50'>PARTE II — TEST</b>"
                f"<span style='margin-left:10px;color:#666;font-size:0.85em'>{len(cache)} preguntas</span></div>",
                unsafe_allow_html=True
            )

            # Agrupar por bloque
            bloques_en_cache = []
            bloque_groups: dict = {}
            for p in cache:
                b = p.get("bloque", "—")
                if b not in bloque_groups:
                    bloque_groups[b] = []
                    bloques_en_cache.append(b)
                bloque_groups[b].append(p)

            q_num = 0
            for blq in bloques_en_cache:
                preg_list = bloque_groups[blq]
                n_f = sum(1 for p in preg_list if p.get("dificultad","").lower() in ("facil","fácil"))
                n_m = sum(1 for p in preg_list if p.get("dificultad","").lower() == "media")
                n_d = sum(1 for p in preg_list if p.get("dificultad","").lower() in ("dificil","difícil"))

                # Bloque como acordeón colapsable
                label = (
                    f"📦 {blq}  —  {len(preg_list)} preguntas"
                    f"  🟢 {n_f} Fácil  🟡 {n_m} Media  🔴 {n_d} Difícil"
                )
                with st.expander(label, expanded=True):
                    cards_html = ""
                    for p in preg_list:
                        q_num += 1
                        cards_html += render_question_card_html(p, show_sol=show_sol, num=q_num)
                    st.markdown(cards_html, unsafe_allow_html=True)

        st.caption("ℹ️ Para fórmulas matemáticas usa el botón **∑ MathJax** arriba. Los bloques se pueden colapsar haciendo clic en su cabecera.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 · EXPORTAR  (rediseñado)
# ─────────────────────────────────────────────────────────────────────────────

# ── Helper: ejecutar exportación completa en memoria ─────────────────────────
def _ejecutar_export():
    """Genera todos los archivos en memoria y los guarda en session_state['export_files']."""
    cfg          = st.session_state.get("exam_cfg", {})
    sel_actual   = get_sel_ids()
    nombre_arch  = cfg.get("file", f"Examen_{datetime.date.today()}")
    n_mod        = cfg.get("vers", 1)
    exp_word     = cfg.get("exp_word", True)
    exp_tex      = cfg.get("exp_tex",  True)

    df_dict = st.session_state.df_preguntas.set_index("ID_Pregunta").to_dict("index")
    pool = []
    for pid in sel_actual:
        if pid in df_dict:
            item = dict(df_dict[pid]); item["ID_Pregunta"] = pid
            pool.append(item)

    cfg_export = {
        "titulo_asignatura": cfg.get("asig", ""),
        "tipo_examen":       cfg.get("tipo", ""),
        "entidad":           cfg.get("inst", ""),
        "fecha":             cfg.get("fecha", ""),
        "tiempo":            cfg.get("tiem", ""),
        "instr_gen":         cfg.get("ins",  ""),
        "info_fund":         cfg.get("h1",   ""),
        "info_test":         cfg.get("h2",   ""),
        "barajar_preguntas":  cfg.get("ord", "bloques") != "manual",
        "barajar_respuestas": cfg.get("bar", True),
        "frases_anclaje_extra": cfg.get("anc_txt","") if cfg.get("anc_chk", True) else "",
        "sol_negrita": cfg.get("sol_bold", False),
        "sol_rojo":    cfg.get("sol_red",  False),
        "sol_ast":     cfg.get("sol_ast",  True),
        "fundamentales_data": [
            {"txt": q["txt"], "pts": q["pts"], "espacio": q["espacio"]}
            for q in st.session_state.get("dev_questions", [])
        ],
    }
    tpl_word_bytes = st.session_state.get("_tpl_word_bytes")
    tpl_tex_bytes  = st.session_state.get("_tpl_tex_bytes")
    if tpl_tex_bytes:
        cfg_export["plantilla_tex_bytes"] = tpl_tex_bytes

    master = lib.generar_master_examen(pool, n_mod, cfg_export)

    ef = {"nombre": nombre_arch, "_zip_all": {}}

    # CSV (siempre)
    csv_data = lib.exportar_csv_bytes(master, nombre_arch)
    ef["csv_claves"] = csv_data["claves"]
    ef["csv_meta"]   = csv_data["metadata"]
    ef["_zip_all"][f"{nombre_arch}_CLAVES.csv"]   = csv_data["claves"]
    ef["_zip_all"][f"{nombre_arch}_METADATA.csv"] = csv_data["metadata"]

    # Word
    if exp_word:
        ef["word_exam"] = lib.rellenar_plantilla_word_bytes(master, nombre_arch, cfg_export, tpl_bytes=tpl_word_bytes, modo_solucion=False)
        ef["word_sol"]  = lib.rellenar_plantilla_word_bytes(master, nombre_arch, cfg_export, tpl_bytes=tpl_word_bytes, modo_solucion=True)
        for letra, data in ef["word_exam"].items():
            ef["_zip_all"][f"{nombre_arch}_MOD{letra}.docx"] = data
        for letra, data in ef["word_sol"].items():
            ef["_zip_all"][f"{nombre_arch}_MOD{letra}_SOL.docx"] = data

    # LaTeX
    if exp_tex:
        ef["latex_exam"] = lib.generar_latex_strings(master, nombre_arch, cfg_export, modo_solucion=False)
        ef["latex_sol"]  = lib.generar_latex_strings(master, nombre_arch, cfg_export, modo_solucion=True)
        for letra, data in ef["latex_exam"].items():
            ef["_zip_all"][f"{nombre_arch}_MOD{letra}.tex"] = data
        for letra, data in ef["latex_sol"].items():
            ef["_zip_all"][f"{nombre_arch}_MOD{letra}_SOL.tex"] = data

    ef["zip_bytes"] = lib.generar_zip_bytes(ef["_zip_all"])

    # Marcar preguntas como usadas en la DB
    hoy = datetime.date.today().strftime("%Y-%m-%d")
    dfs = st.session_state.excel_dfs
    for bloque_name, df_sheet in dfs.items():
        head    = [str(h).lower().strip() for h in df_sheet.columns]
        idx_id  = next((i for i, h in enumerate(head) if "id_preg" in h or h == "id"), -1)
        idx_usa = next((i for i, h in enumerate(head) if "usada" in h or "fecha" in h), -1)
        if idx_id == -1 or idx_usa == -1: continue
        id_col  = df_sheet.columns[idx_id]
        usa_col = df_sheet.columns[idx_usa]
        mask = df_sheet[id_col].astype(str).isin([str(pid) for pid in sel_actual])
        df_sheet.loc[mask, usa_col] = hoy
    reload_db()

    # Historial
    append_historial({
        "fecha":        datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "nombre":       nombre_arch,
        "titulo":       cfg.get("asig", ""),
        "asig":         cfg.get("asig", ""),
        "tipo":         cfg.get("tipo", ""),
        "n_preguntas":  len(sel_actual),
        "n_modelos":    n_mod,
        "ids":          sel_actual[:],
        "usuario":      st.session_state.get("google_user_email", ""),
    })
    st.session_state.cache_examen   = pool
    st.session_state["export_files"] = ef


@st.dialog("✅ Confirmar exportación", width="small")
def _dialog_confirmar_export():
    cfg    = st.session_state.get("exam_cfg", {})
    sel    = get_sel_ids()
    n_mod  = cfg.get("vers", 1)
    st.markdown(f"**{len(sel)} preguntas · {n_mod} modelo(s)**")
    formatos = ["📊 CSV Claves + Metadatos (siempre)"]
    if cfg.get("exp_word", True): formatos.append(f"📄 Word: {n_mod} examen(es) + {n_mod} con soluciones")
    if cfg.get("exp_tex",  True): formatos.append(f"📑 LaTeX: {n_mod} examen(es) + {n_mod} con soluciones")
    for f_item in formatos:
        st.markdown(f"• {f_item}")
    sol_lb = []
    if cfg.get("sol_bold"): sol_lb.append("negrita")
    if cfg.get("sol_red"):  sol_lb.append("rojo")
    if cfg.get("sol_ast"):  sol_lb.append("asterisco (*)")
    if sol_lb: st.caption(f"Soluciones marcadas con: {', '.join(sol_lb)}")
    st.markdown("---")
    c1, c2 = st.columns(2)
    if c1.button("✅ Exportar", type="primary", use_container_width=True, key="dlg_ok"):
        with st.spinner("Generando archivos…"):
            try:
                _ejecutar_export()
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback; st.code(traceback.format_exc())
                return
        st.rerun()
    if c2.button("Cancelar", use_container_width=True, key="dlg_cancel"):
        st.rerun()


@st.dialog("👁 Vista previa · Modelo A", width="large")
def _dialog_preview_examen():
    sel = get_sel_ids()
    if not sel:
        st.warning("No hay preguntas seleccionadas.")
        return
    df_q    = st.session_state.df_preguntas
    df_dict = df_q.set_index("ID_Pregunta").to_dict("index")
    pool_p  = []
    for pid in sel:
        if pid in df_dict:
            item = dict(df_dict[pid]); item["ID_Pregunta"] = pid
            pool_p.append(item)
    pc1, pc2 = st.columns(2)
    show_sol_p = pc1.checkbox("Mostrar soluciones", value=True, key="prev_show_sol")
    if pc2.button("∑ Renderizar LaTeX", key="prev_mjax_btn"):
        st.session_state["_prev_mjax"] = True
    cards_html = "".join(render_question_card_html(p, show_sol=show_sol_p, num=i+1) for i, p in enumerate(pool_p))
    if st.session_state.get("_prev_mjax"):
        stcomponents.html(mathjax_html(cards_html), height=650, scrolling=True)
    else:
        st.markdown(cards_html, unsafe_allow_html=True)


with tab_exp:
    sel_actual = get_sel_ids()
    n_pregs    = len(sel_actual)
    cfg        = st.session_state.get("exam_cfg", {})

    col_cfg, col_res = st.columns([3, 2], gap="large")

    with col_cfg:

        # ── 1. Identificación ──────────────────────────────────────────────────
        with st.expander("📋 Identificación del examen", expanded=True):
            e1, e2, e3 = st.columns(3)
            inst  = e1.text_input("Institución",    value=cfg.get("inst", "UCM"),                  key="exp_inst")
            asig  = e2.text_input("Asignatura",     value=cfg.get("asig", "FÍSICA MÉDICA"),         key="exp_asig")
            tipo  = e3.text_input("Tipo de examen", value=cfg.get("tipo", "EXAMEN FINAL"),          key="exp_tipo")
            e4, e5, e6 = st.columns(3)
            fecha         = e4.text_input("Fecha",          value=cfg.get("fecha", datetime.date.today().strftime("%d/%m/%Y")), key="exp_fecha")
            tiem          = e5.text_input("Tiempo",         value=cfg.get("tiem",  "90 min"),       key="exp_tiem")
            nombre_archivo = e6.text_input("Nombre archivo", value=cfg.get("file", f"Examen_{datetime.date.today()}"), key="exp_file")

        # ── 2. Generación ─────────────────────────────────────────────────────
        with st.expander("⚙️ Opciones de generación", expanded=True):
            oc1, oc2, oc3 = st.columns(3)
            num_modelos = oc1.selectbox("Nº Modelos", [1, 2, 3, 4],
                                        index=max(0, cfg.get("vers", 1) - 1), key="exp_vers")
            _orden_opts = [("Aleatorio por Bloques","bloques"),("Aleatorio Global","global"),
                           ("Manual (selección)","manual"),("Sin barajar (ID)","secuencial")]
            _orden_idx  = next((i for i, (_, v) in enumerate(_orden_opts) if v == cfg.get("ord","bloques")), 0)
            orden_val   = oc2.selectbox("Orden preguntas", _orden_opts, index=_orden_idx,
                                        format_func=lambda x: x[0], key="exp_ord")
            orden       = orden_val[1]
            barajar     = oc3.checkbox("Barajar respuestas", value=cfg.get("bar", True), key="exp_bar")

        # ── 3. Formatos + Marcado de soluciones ───────────────────────────────
        with st.expander("📄 Formatos y marcado de soluciones", expanded=True):
            st.markdown("**Formatos de exportación:**")
            fc1, fc2, fc3 = st.columns(3)
            fc1.markdown("📊 **CSV** (siempre)", help="Clave de respuestas y metadatos — siempre se generan")
            exp_word = fc2.checkbox("📄 Word (.docx)", value=cfg.get("exp_word", True), key="exp_word")
            exp_tex  = fc3.checkbox("📑 LaTeX (.tex)", value=cfg.get("exp_tex",  True), key="exp_tex")
            if exp_tex:
                st.caption("ℹ️ LaTeX compatible con Overleaf/Prism. Requiere la clase `exam`.")
            st.markdown("**Marcado de la versión soluciones:**")
            sc1, sc2, sc3 = st.columns(3)
            sol_bold = sc1.checkbox("Negrita",        value=cfg.get("sol_bold", False), key="exp_sol_bold")
            sol_red  = sc2.checkbox("Color rojo",     value=cfg.get("sol_red",  False), key="exp_sol_red")
            sol_ast  = sc3.checkbox("Asterisco (*)",  value=cfg.get("sol_ast",  True),  key="exp_sol_ast")

        # ── 4. Instrucciones y Cabeceras ──────────────────────────────────────
        with st.expander("📝 Instrucciones y cabeceras", expanded=True):
            instr     = st.text_area("Instrucciones generales",
                                     value=cfg.get("ins", "Conteste en la hoja de respuestas."),
                                     height=70, key="exp_ins")
            hc1, hc2  = st.columns(2)
            info_fund = hc1.text_area("Cabecera sección desarrollo", value=cfg.get("h1", ""), height=70, key="exp_h1")
            info_test = hc2.text_area("Cabecera sección test",       value=cfg.get("h2", ""), height=70, key="exp_h2")

        # ── 5. Anclaje ────────────────────────────────────────────────────────
        with st.expander("⚓ Anclaje de opciones", expanded=True):
            ac1, ac2      = st.columns([1, 2])
            anclaje_auto  = ac1.checkbox("Activar anclaje", value=cfg.get("anc_chk", True), key="exp_anc")
            anclaje_extra = ac2.text_input("Frases extra (coma separadas)",
                                           value=cfg.get("anc_txt", ""), key="exp_anc_txt",
                                           disabled=not anclaje_auto)
            if anclaje_auto:
                _base = ["todas las anteriores","ninguna de las anteriores","ambas son correctas","son correctas","son falsas"]
                _extra = [f.strip() for f in anclaje_extra.split(",") if f.strip()] if anclaje_extra else []
                _todas = _base + _extra
                st.caption("Anclan (no se barajan): " + " · ".join(f'"{f}"' for f in _todas[:5]) + ("…" if len(_todas)>5 else ""))

        # ── 6. Plantillas ─────────────────────────────────────────────────────
        with st.expander("📎 Plantillas (Word / LaTeX / Logo)", expanded=False):
            st.caption("Se suben por sesión. Los presets guardan la configuración pero no la plantilla.")
            tc1, tc2, tc3    = st.columns(3)
            tpl_word_file    = tc1.file_uploader("Plantilla Word (.docx)", type=["docx"], key="exp_tpl_word")
            tpl_tex_file     = tc2.file_uploader("Plantilla LaTeX (.tex)", type=["tex"],  key="exp_tpl_tex")
            logo_file        = tc3.file_uploader("Logo (PNG/JPG)",         type=["png","jpg","jpeg"], key="exp_logo")
            if tpl_word_file:
                st.session_state["_tpl_word_bytes"] = tpl_word_file.getvalue()
                st.session_state["_tpl_word_name"]  = tpl_word_file.name
                tc1.success(f"✅ {tpl_word_file.name}")
            elif st.session_state.get("_tpl_word_bytes"):
                tc1.info(f"En memoria: {st.session_state.get('_tpl_word_name','plantilla.docx')}")
            if tpl_tex_file:
                st.session_state["_tpl_tex_bytes"] = tpl_tex_file.getvalue()
                st.session_state["_tpl_tex_name"]  = tpl_tex_file.name
                tc2.success(f"✅ {tpl_tex_file.name}")
            elif st.session_state.get("_tpl_tex_bytes"):
                tc2.info(f"En memoria: {st.session_state.get('_tpl_tex_name','plantilla.tex')}")
            if logo_file:
                import tempfile as _tmp
                _logo_p = os.path.join(_tmp.gettempdir(), logo_file.name)
                with open(_logo_p, "wb") as _f: _f.write(logo_file.read())
                st.session_state["_logo_path"] = _logo_p
                tc3.success(f"✅ {logo_file.name}")

        # ── 7. Presets ────────────────────────────────────────────────────────
        with st.expander("💾 Presets de configuración", expanded=False):
            st.caption("Guarda y reutiliza configuraciones completas (instrucciones, datos, opciones).")
            _presets = st.session_state.presets
            pr1, pr2  = st.columns([3, 1])
            _sel_pr   = pr1.selectbox("Preset", ["— Seleccionar —"] + list(_presets.keys()), key="preset_sel")
            if pr2.button("📂 Cargar", key="btn_load_preset", use_container_width=True) and _sel_pr != "— Seleccionar —":
                st.session_state.exam_cfg = _presets.get(_sel_pr, {})
                st.success(f"Preset '{_sel_pr}' cargado.")
                st.rerun()
            pr3, pr4  = st.columns([3, 1])
            _pr_name  = pr3.text_input("Nombre del preset", placeholder="Ej: FM I Ordinario 2026",
                                       key="preset_name_input", label_visibility="collapsed")
            if pr4.button("💾 Guardar", key="btn_save_preset", use_container_width=True):
                if _pr_name.strip():
                    save_preset(_pr_name.strip(), st.session_state.get("exam_cfg", {}))
                    st.success(f"Preset '{_pr_name}' guardado.")
                    st.rerun()
            if _sel_pr != "— Seleccionar —":
                if st.button(f"🗑️ Eliminar '{_sel_pr}'", key="btn_del_preset"):
                    delete_preset(_sel_pr); st.rerun()

        # ── Persistir cfg en session_state ────────────────────────────────────
        st.session_state.exam_cfg = {
            "inst": inst, "asig": asig, "tipo": tipo, "fecha": fecha, "tiem": tiem,
            "file": nombre_archivo, "ins": instr, "h1": info_fund, "h2": info_test,
            "vers": num_modelos, "ord": orden, "bar": barajar,
            "exp_word": exp_word, "exp_tex": exp_tex,
            "sol_bold": sol_bold, "sol_red": sol_red, "sol_ast": sol_ast,
            "anc_chk": anclaje_auto, "anc_txt": anclaje_extra,
        }

    # ── Panel derecho: Resumen + Botones + Descargas ───────────────────────────
    with col_res:

        # Construir textos del resumen
        _sol_marks = []
        if sol_bold: _sol_marks.append("negrita")
        if sol_red:  _sol_marks.append("rojo")
        if sol_ast:  _sol_marks.append("asterisco *")
        _sol_str = ", ".join(_sol_marks) if _sol_marks else "sin marcar"

        _fmt_parts = ["📊 CSV"]
        if exp_word: _fmt_parts.append("📄 Word")
        if exp_tex:  _fmt_parts.append("📑 LaTeX")
        _fmt_str = " · ".join(_fmt_parts)

        _tpl_w = st.session_state.get("_tpl_word_name", "plantilla por defecto")
        _tpl_t = st.session_state.get("_tpl_tex_name",  "plantilla por defecto")

        _anc_status = "activado" if anclaje_auto else "desactivado"
        _anc_frases = ["todas las anteriores", "ninguna de las anteriores", "ambas son correctas"]
        if anclaje_auto and anclaje_extra:
            _anc_frases += [f.strip() for f in anclaje_extra.split(",") if f.strip()]
        _anc_prev = " · ".join(f'"{f}"' for f in _anc_frases[:3]) + ("…" if len(_anc_frases) > 3 else "")

        _tpl_rows = ""
        if exp_word: _tpl_rows += f'<div style="opacity:0.8">📎 Word: {_tpl_w}</div>'
        if exp_tex:  _tpl_rows += f'<div style="opacity:0.8">📎 LaTeX: {_tpl_t}</div>'

        st.markdown(
            f"""<div style="background:linear-gradient(135deg,#1a252f,#2c3e50);color:white;
            border-radius:12px;padding:18px 20px;margin-bottom:12px;font-size:0.87em;line-height:1.75">
            <div style="font-size:1.05em;font-weight:800;margin-bottom:2px">{asig or '—'} · {tipo or '—'}</div>
            <div style="opacity:0.65;font-size:0.82em;margin-bottom:10px">
              {inst or '—'} &nbsp;·&nbsp; {fecha or '—'} &nbsp;·&nbsp; {tiem or '—'}</div>
            <hr style="border-color:rgba(255,255,255,0.15);margin:8px 0">
            <div>📋 <b>{n_pregs}</b> preguntas &nbsp;&nbsp; 🔢 <b>{num_modelos}</b> modelo(s)</div>
            <div>📦 {_fmt_str}</div>
            <div>✍️ Soluciones: {_sol_str}</div>
            <hr style="border-color:rgba(255,255,255,0.15);margin:8px 0">
            <div style="opacity:0.85">⚓ Anclaje: {_anc_status}</div>
            {'<div style="opacity:0.6;font-size:0.82em">' + _anc_prev + '</div>' if anclaje_auto else ''}
            <hr style="border-color:rgba(255,255,255,0.15);margin:8px 0">
            {_tpl_rows}
            </div>""",
            unsafe_allow_html=True,
        )

        if st.button("👁 Vista previa del examen", use_container_width=True, key="btn_preview_exam"):
            _dialog_preview_examen()

        st.markdown("<div style='margin:6px 0'></div>", unsafe_allow_html=True)

        if st.button("💾 EXPORTAR EXAMEN", type="primary", use_container_width=True,
                     key="btn_export_main", disabled=(n_pregs == 0)):
            _dialog_confirmar_export()
        if n_pregs == 0:
            st.caption("⚠️ Ve a la pestaña **Selección** para elegir preguntas.")

        # ── Botones de descarga (tras exportar) ───────────────────────────────
        ef = st.session_state.get("export_files")
        if ef:
            _nef = ef.get("nombre", "examen")
            st.markdown("---")
            st.markdown("**⬇️ Descargas**")

            st.download_button(
                "⬇️ Descargar TODO (.zip)",
                data=ef["zip_bytes"],
                file_name=f"{_nef}_completo.zip",
                mime="application/zip",
                use_container_width=True,
                key="dl_zip_all",
                type="primary",
            )

            if ef.get("word_exam"):
                st.markdown("**Word:**")
                _wc1, _wc2 = st.columns(2)
                _wc1.download_button("📄 Exámenes",
                    data=lib.generar_zip_bytes({f"{_nef}_MOD{l}.docx": d for l, d in ef["word_exam"].items()}),
                    file_name=f"{_nef}_word_examenes.zip", mime="application/zip",
                    use_container_width=True, key="dl_word_exam")
                _wc2.download_button("📄 Soluciones",
                    data=lib.generar_zip_bytes({f"{_nef}_MOD{l}_SOL.docx": d for l, d in ef["word_sol"].items()}),
                    file_name=f"{_nef}_word_soluciones.zip", mime="application/zip",
                    use_container_width=True, key="dl_word_sol")

            if ef.get("latex_exam"):
                st.markdown("**LaTeX:**")
                _lc1, _lc2 = st.columns(2)
                _lc1.download_button("📑 Exámenes",
                    data=lib.generar_zip_bytes({f"{_nef}_MOD{l}.tex": d for l, d in ef["latex_exam"].items()}),
                    file_name=f"{_nef}_latex_examenes.zip", mime="application/zip",
                    use_container_width=True, key="dl_latex_exam")
                _lc2.download_button("📑 Soluciones",
                    data=lib.generar_zip_bytes({f"{_nef}_MOD{l}_SOL.tex": d for l, d in ef["latex_sol"].items()}),
                    file_name=f"{_nef}_latex_soluciones.zip", mime="application/zip",
                    use_container_width=True, key="dl_latex_sol")

            st.markdown("**CSV:**")
            _cc1, _cc2 = st.columns(2)
            _cc1.download_button("📊 Clave",     data=ef["csv_claves"], file_name=f"{_nef}_CLAVES.csv",
                                 mime="text/csv", use_container_width=True, key="dl_csv_claves")
            _cc2.download_button("📊 Metadatos", data=ef["csv_meta"],   file_name=f"{_nef}_METADATA.csv",
                                 mime="text/csv", use_container_width=True, key="dl_csv_meta")

            if st.button("🔄 Nueva exportación", use_container_width=True, key="btn_clear_export"):
                st.session_state.pop("export_files", None)
                st.session_state.pop("_prev_mjax", None)
                st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 · HISTORIAL
# ─────────────────────────────────────────────────────────────────────────────
with tab_hist:
    st.subheader("Historial de exámenes generados")

    hist = st.session_state.historial
    if not hist:
        st.info("No hay exámenes en el historial aún. Exporta tu primer examen.")
    else:
        hist_rev = list(reversed(hist))  # más reciente primero
        for i, entry in enumerate(hist_rev):
            with st.expander(
                f"📄 {entry.get('nombre','?')} · {entry.get('fecha','?')} · {entry.get('n_pregs','?')} pregs",
                expanded=(i == 0)
            ):
                hc1, hc2 = st.columns(2)
                with hc1:
                    st.markdown(f"**Asig:** {entry.get('asig','')}")
                    st.markdown(f"**Tipo:** {entry.get('tipo','')}")
                    st.markdown(f"**Modelos:** {entry.get('modelos','')}")
                    st.markdown(f"**Ruta:** `{entry.get('ruta','')}`")
                with hc2:
                    ids = entry.get("ids", [])
                    st.markdown(f"**Preguntas ({len(ids)}):**")
                    st.caption(", ".join(ids[:10]) + ("..." if len(ids) > 10 else ""))

                if st.button("↩️ Recargar preguntas de este examen",
                             key=f"hist_reload_{i}"):
                    # Recargar en selección
                    valid = [pid for pid in ids if pid in df_total["ID_Pregunta"].values]
                    set_sel_ids(valid)
                    st.success(f"Recargadas {len(valid)} preguntas. Ve a la pestaña Selección.")
                    st.rerun()

    # ── Recuperar desde CSV ────────────────────────────────────────────────
    st.divider()
    st.markdown("**Recuperar examen desde CSV de metadatos:**")
    csv_file = st.file_uploader("Archivo _METADATA.csv", type=["csv"], key="hist_csv_up")
    if csv_file and st.button("📥 Cargar desde CSV", key="btn_load_csv"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tf:
            tf.write(csv_file.read())
            tmp_csv = tf.name
        try:
            ids_csv = lib.cargar_examen_csv(tmp_csv)
            os.unlink(tmp_csv)
            valid = [pid for pid in ids_csv if pid in df_total["ID_Pregunta"].values]
            if valid:
                set_sel_ids(valid)
                pool = df_total[df_total["ID_Pregunta"].isin(valid)].to_dict("records")
                st.session_state.cache_examen = pool
                st.session_state["recovery_mode"] = True  # activa modo recuperación
                st.success(
                    f"✅ Recuperadas {len(valid)} de {len(ids_csv)} preguntas del CSV. "
                    "Ve a **Preview** — el botón Generar está bloqueado "
                    "(pulsa 🔓 Desbloquear si quieres modificarlo)."
                )
                st.rerun()
            else:
                st.warning(f"Se encontraron {len(ids_csv)} IDs en el CSV pero ninguno coincide con la DB actual.")
        except Exception as e:
            st.error(f"Error al leer el CSV: {e}")
