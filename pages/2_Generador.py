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
    nombre_bloque, nombre_tema,
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
                                  key="sel_f_tema",
                                  format_func=lambda t: "Todos" if t == "Todos" else nombre_tema(t))
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
                card_html_prev = render_question_card_html(row_d_prev, show_sol=True, include_notas=False)
                st.markdown(card_html_prev, unsafe_allow_html=True)

                # Notas debajo de la tarjeta
                notas_txt_prev  = str(row_d_prev.get("notas", "") or "").strip()
                notas_html_prev = ""
                if notas_txt_prev:
                    notas_html_prev = (
                        "<div style='background:#fefce8;border-left:3px solid #f59e0b;"
                        "border-radius:0 8px 8px 0;padding:10px 14px;margin-top:4px;"
                        "font-size:0.875em;color:#78350f;line-height:1.55'>"
                        "<b style='color:#92400e;display:block;margin-bottom:4px'>📝 Notas</b>"
                        f"{notas_txt_prev}</div>"
                    )
                    st.markdown(notas_html_prev, unsafe_allow_html=True)

                # Badge solución
                sol_txt_badge = str(row_d_prev.get("solucion", "") or "").strip()
                if sol_txt_badge:
                    st.markdown(
                        "<div style='margin-top:4px;display:flex;align-items:center;gap:6px'>"
                        "<span style='background:#dbeafe;color:#1e40af;border:1px solid #93c5fd;"
                        "border-radius:12px;padding:2px 10px;font-size:0.78em;font-weight:600;"
                        "letter-spacing:0.02em'>📖 Solución disponible</span></div>",
                        unsafe_allow_html=True,
                    )

                # Botones añadir / quitar + Solución
                is_sel = preview_pid in sel_ids_actual
                pa1, pa2, pa3 = st.columns(3)
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

                # Botón Solución
                sol_txt_prev = str(row_d_prev.get("solucion", "") or "").strip()
                if pa2.button("📖 Solución", key="btn_prev_sol",
                               use_container_width=True, disabled=not sol_txt_prev):
                    st.session_state["_gen_sol_pid"] = preview_pid
                    st.session_state["_gen_sol_row"] = row_d_prev

                # Botón MathJax
                _mjax_key_sel = f"mjax_sel_{preview_pid}"
                if pa3.button("∑ Renderizar LaTeX", key=f"mjax_btn_sel_{preview_pid}",
                               use_container_width=True):
                    st.session_state[_mjax_key_sel] = True
                if st.session_state.get(_mjax_key_sel, False):
                    mj1, mj2 = st.columns([1, 3])
                    if mj1.button("✖ Cerrar LaTeX", key=f"mjax_close_sel_{preview_pid}",
                                   use_container_width=True):
                        st.session_state[_mjax_key_sel] = False
                        st.rerun()
                    stcomponents.html(mathjax_html(card_html_prev + notas_html_prev), height=480, scrolling=True)

                # Mostrar solución inline si se ha pulsado el botón
                if (st.session_state.get("_gen_sol_pid") == preview_pid
                        and st.session_state.get("_gen_sol_row")):
                    sol_txt = str(st.session_state["_gen_sol_row"].get("solucion", "") or "").strip()
                    if sol_txt:
                        sol_html = (
                            "<div style='font-family:-apple-system,sans-serif;font-size:14px;"
                            "color:#2c3e50;padding:12px;background:#f0f9ff;"
                            "border-left:3px solid #3498db;border-radius:0 8px 8px 0;margin-top:6px'>"
                            "<b style='color:#1a5276;display:block;margin-bottom:6px'>📖 Solución</b>"
                            f"{sol_txt}</div>"
                        )
                        st.markdown("---")
                        stcomponents.html(mathjax_html(sol_html), height=250, scrolling=True)
                        if st.button("✖ Cerrar solución", key="btn_close_sol_gen"):
                            st.session_state.pop("_gen_sol_pid", None)
                            st.session_state.pop("_gen_sol_row", None)
                            st.rerun()
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

    # ── Panel de estadísticas de selección (tiempo real) ─────────────────────
    if sel_ids_actual:
        import plotly.graph_objects as go
        df_sel_stat = df_total[df_total["ID_Pregunta"].isin(sel_ids_actual)].copy()
        n_total_db = len(df_total)

        # Conteos por dificultad
        dif_counts = df_sel_stat["dificultad"].str.lower().value_counts()
        n_facil  = int(dif_counts.get("facil",  0))
        n_media  = int(dif_counts.get("media",  0))
        n_dificil= int(dif_counts.get("dificil",0))

        # Alertas
        _alerts = []
        if n_sel < n_obj:
            _alerts.append(f"⚠️ Faltan {n_obj - n_sel} preguntas para el objetivo")
        if n_sel > n_obj:
            _alerts.append(f"ℹ️ {n_sel - n_obj} preguntas extra sobre el objetivo")
        _pct_dif = round(n_dificil / n_sel * 100) if n_sel else 0
        if _pct_dif > 50:
            _alerts.append(f"⚠️ Mucha dificultad alta: {_pct_dif}% de difíciles")

        st.markdown("---")
        _sc1, _sc2, _sc3 = st.columns([2, 3, 3])

        # Donut dificultad
        with _sc1:
            st.markdown("**📊 Dificultad**")
            _dif_fig = go.Figure(go.Pie(
                labels=["Fácil", "Media", "Difícil"],
                values=[n_facil, n_media, n_dificil],
                hole=0.55,
                marker_colors=["#27ae60", "#f39c12", "#c0392b"],
                textinfo="value",
                hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
            ))
            _dif_fig.update_layout(
                margin=dict(t=0, b=0, l=0, r=0), height=150,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                showlegend=True,
                legend=dict(orientation="v", x=1.0, y=0.5, font=dict(size=10)),
            )
            st.plotly_chart(_dif_fig, use_container_width=True, config={"displayModeBar": False})

        # Cobertura por bloque
        with _sc2:
            st.markdown("**📦 Bloques cubiertos**")
            _blq_sel = df_sel_stat["bloque"].value_counts()
            _blq_tot = df_total["bloque"].value_counts()
            _blq_all = sorted(_blq_tot.index.tolist(), key=_nsort)
            _blq_labels = [nombre_bloque(str(b))[:20] for b in _blq_all]
            _blq_n_sel  = [int(_blq_sel.get(b, 0)) for b in _blq_all]
            _blq_n_rest = [max(0, int(_blq_tot.get(b, 0)) - int(_blq_sel.get(b, 0))) for b in _blq_all]
            _blq_fig = go.Figure()
            _blq_fig.add_trace(go.Bar(
                y=_blq_labels, x=_blq_n_sel, orientation="h",
                name="Seleccionadas", marker_color="#3498db",
                hovertemplate="%{y}: %{x} seleccionadas<extra></extra>",
            ))
            _blq_fig.add_trace(go.Bar(
                y=_blq_labels, x=_blq_n_rest, orientation="h",
                name="Disponibles", marker_color="#ecf0f1",
                hovertemplate="%{y}: %{x} disponibles<extra></extra>",
            ))
            _blq_fig.update_layout(
                barmode="stack", margin=dict(t=0, b=0, l=0, r=5),
                height=max(120, 28 * len(_blq_all)),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False, xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=False, tickfont=dict(size=10)),
            )
            st.plotly_chart(_blq_fig, use_container_width=True, config={"displayModeBar": False})

        # Alertas y métricas clave
        with _sc3:
            st.markdown("**📋 Resumen**")
            _m1, _m2 = st.columns(2)
            _m1.metric("Seleccionadas", n_sel, delta=f"{n_sel - n_obj:+d} vs objetivo")
            _m2.metric("% del banco", f"{round(n_sel / n_total_db * 100)}%")
            _m3, _m4, _m5 = st.columns(3)
            _m3.metric("Fácil",    n_facil)
            _m4.metric("Media",    n_media)
            _m5.metric("Difícil",  n_dificil)
            for _alert in _alerts:
                st.warning(_alert)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 · DESARROLLO
# ─────────────────────────────────────────────────────────────────────────────

def _dev_md_to_html(text):
    """Markdown (**bold**, *italic*) + LaTeX ($...$, $$...$$) → HTML para preview."""
    # Proteger secciones math antes de parsear markdown
    math_parts = []
    def save(m):
        math_parts.append(m.group(0))
        return f'\x00M{len(math_parts)-1}\x00'
    text = re.sub(r'\$\$.+?\$\$', save, text, flags=re.DOTALL)
    text = re.sub(r'\$.+?\$', save, text)
    # Markdown → HTML
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    # Restaurar math
    for idx, mp in enumerate(math_parts):
        text = text.replace(f'\x00M{idx}\x00', mp)
    return text.replace('\n', '<br>')


_ESP_LABELS = ["Automático", "5 líneas", "10 líneas", "Media Cara", "Cara Completa"]

with tab_dev:
    st.title("✍️ Preguntas de Desarrollo")
    st.caption(
        "Se incluirán como **PARTE I** del examen. "
        "Formato: `**negrita**` · `*cursiva*` · `$LaTeX inline$` · `$$bloque$$`"
    )

    dev_qs: list = st.session_state.dev_questions

    if st.button("➕ Añadir pregunta de desarrollo", key="btn_add_dev"):
        dev_qs.append({"txt": "", "pts": 1.0, "espacio": "Automático",
                       "criterios": [], "solucion_modelo": "",
                       "imagen_bytes": None, "imagen_name": "", "imagen_pos": "debajo"})
        st.session_state.dev_questions = dev_qs
        st.rerun()

    to_delete = []
    for i, q in enumerate(dev_qs):
        with st.container(border=True):
            # ── Cabecera: título + controles ──────────────────────────────────
            ch, cp, ce, cd = st.columns([3, 1, 2, 1])
            ch.markdown(f"**Pregunta {i+1}**")
            new_pts = cp.number_input(
                "pts", value=float(q["pts"]), min_value=0.0, step=0.5,
                key=f"dev_pts_{i}", help="Puntuación"
            )
            new_esp = ce.selectbox(
                "Espacio respuesta", _ESP_LABELS,
                index=_ESP_LABELS.index(q.get("espacio", "Automático")),
                key=f"dev_esp_{i}", label_visibility="collapsed",
            )
            if cd.button("🗑️", key=f"dev_del_{i}", help="Eliminar pregunta"):
                to_delete.append(i)

            # ── Split: editor | preview ───────────────────────────────────────
            col_edit, col_prev = st.columns(2, gap="medium")

            with col_edit:
                new_txt = st.text_area(
                    "Enunciado",
                    value=q["txt"],
                    height=160,
                    key=f"dev_txt_{i}",
                    label_visibility="collapsed",
                    placeholder=(
                        "Escribe el enunciado...\n\n"
                        "Negrita: **texto**\n"
                        "Cursiva: *texto*\n"
                        "Fórmula inline: $E = mc^2$\n"
                        "Fórmula bloque: $$\\frac{d}{dx}f(x)$$"
                    ),
                )

            with col_prev:
                if new_txt.strip():
                    body = _dev_md_to_html(new_txt)
                else:
                    body = '<span style="color:#bbb;font-style:italic">El preview aparece aquí al escribir…</span>'
                prev_html = f"""
<div style="font-family:Calibri,sans-serif;font-size:11pt;line-height:1.6;
            padding:12px 16px;background:#fff;border:1px solid #ddd;
            border-radius:6px;min-height:160px;color:#111;box-sizing:border-box">
  <div style="color:#aaa;font-size:8pt;text-transform:uppercase;letter-spacing:.06em;
              border-bottom:1px solid #eee;padding-bottom:5px;margin-bottom:10px">
    Vista previa · Word / LaTeX
  </div>
  {body}
</div>"""
                stcomponents.html(mathjax_html(prev_html), height=200, scrolling=False)

            # Inicializar con valores actuales (se sobreescriben dentro del expander)
            criterios      = list(q.get("criterios", []))
            new_sol_modelo = q.get("solucion_modelo", "")
            new_img_bytes  = q.get("imagen_bytes")
            new_img_name   = q.get("imagen_name", "")
            new_img_pos    = q.get("imagen_pos", "debajo")

            # ── Rúbrica + Imagen + Solución modelo ───────────────────────────
            with st.expander("📋 Rúbrica / Imagen / Solución modelo", expanded=False):
                _rub_tab, _img_tab, _sol_tab = st.tabs(["📋 Rúbrica", "🖼️ Imagen", "📖 Solución modelo"])

                with _rub_tab:
                    st.caption("Define los criterios de evaluación con su puntuación parcial.")
                    to_del_crit = []
                    for ci, crit in enumerate(criterios):
                        rc1, rc2, rc3 = st.columns([5, 1, 1])
                        new_desc = rc1.text_input("Criterio", value=crit.get("desc", ""),
                                                   key=f"crit_desc_{i}_{ci}",
                                                   label_visibility="collapsed",
                                                   placeholder="Descripción del criterio…")
                        new_cpts = rc2.number_input("pts", value=float(crit.get("pts", 0.5)),
                                                     min_value=0.0, step=0.25,
                                                     key=f"crit_pts_{i}_{ci}",
                                                     label_visibility="collapsed")
                        if rc3.button("🗑️", key=f"crit_del_{i}_{ci}", help="Eliminar criterio"):
                            to_del_crit.append(ci)
                        else:
                            criterios[ci] = {"desc": new_desc, "pts": new_cpts}
                    for ci in sorted(to_del_crit, reverse=True):
                        criterios.pop(ci)
                    if st.button("➕ Añadir criterio", key=f"crit_add_{i}"):
                        criterios.append({"desc": "", "pts": 0.5})
                    _total_crit = sum(c.get("pts", 0) for c in criterios)
                    if criterios:
                        st.caption(f"Total criterios: **{_total_crit:.2f} pts** (pregunta: {new_pts} pts)")

                with _img_tab:
                    _img_pos_opts = {"debajo": "Entre texto y caja de respuesta",
                                     "encima": "Encima del texto",
                                     "lado":   "Al lado del texto (flotante)"}
                    _img_cur_pos  = q.get("imagen_pos", "debajo")
                    _img_pos_idx  = list(_img_pos_opts.keys()).index(_img_cur_pos) if _img_cur_pos in _img_pos_opts else 0
                    new_img_pos = st.selectbox("Posición de la imagen", list(_img_pos_opts.keys()),
                                               index=_img_pos_idx,
                                               format_func=lambda x: _img_pos_opts[x],
                                               key=f"dev_img_pos_{i}")
                    img_up = st.file_uploader("Subir imagen (PNG/JPG/PDF recortado)",
                                              type=["png", "jpg", "jpeg"],
                                              key=f"dev_img_{i}")
                    if img_up:
                        new_img_bytes = img_up.getvalue()
                        new_img_name  = img_up.name
                        st.image(img_up, width=300)
                    elif q.get("imagen_bytes"):
                        import io as _io_tmp
                        new_img_bytes = q["imagen_bytes"]
                        new_img_name  = q.get("imagen_name", f"dev_img_{i+1}.png")
                        st.image(_io_tmp.BytesIO(new_img_bytes), width=300, caption=new_img_name)
                        if st.button("🗑️ Quitar imagen", key=f"dev_img_del_{i}"):
                            new_img_bytes = None
                            new_img_name  = ""
                    else:
                        new_img_bytes = None
                        new_img_name  = ""

                with _sol_tab:
                    st.caption("Solución modelo (puede contener LaTeX). Aparecerá en el Solucionario del preview y en el archivo de rúbrica.")
                    new_sol_modelo = st.text_area(
                        "Solución modelo", value=q.get("solucion_modelo", ""),
                        height=140, key=f"dev_sol_{i}",
                        label_visibility="collapsed",
                        placeholder="Escribe la solución modelo…\n$E = mc^2$\n$$\\int_0^\\infty e^{-x}\\,dx = 1$$"
                    )
                    if new_sol_modelo.strip():
                        stcomponents.html(mathjax_html(
                            f'<div style="padding:8px;font-family:serif;font-size:11pt">{new_sol_modelo}</div>'
                        ), height=120, scrolling=False)

            dev_qs[i] = {
                "txt": new_txt, "pts": new_pts, "espacio": new_esp,
                "criterios": criterios,
                "solucion_modelo": new_sol_modelo,
                "imagen_bytes": new_img_bytes,
                "imagen_name":  new_img_name,
                "imagen_pos":   new_img_pos,
            }

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

    # Usar lo que se generó en Preview (cache_examen).
    # Si no hay cache (solo preguntas manuales, sin Preview previo), construir desde sel_actual.
    cache = st.session_state.get("cache_examen") or []
    if cache:
        pool = list(cache)
    else:
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
        "sol_negrita": cfg.get("sol_bold",  False),
        "sol_color":   cfg.get("sol_color", "red"),
        "sol_ast":     cfg.get("sol_ast",  True),
        "fundamentales_data": [
            {
                "txt":          q["txt"],
                "pts":          q["pts"],
                "espacio":      q["espacio"],
                "imagen_bytes": q.get("imagen_bytes"),
                "imagen_name":  q.get("imagen_name", f"dev_img_{di+1}.png"),
                "imagen_pos":   q.get("imagen_pos", "debajo"),
            }
            for di, q in enumerate(st.session_state.get("dev_questions", []))
        ],
        # Estilo visual
        "color_scheme":  cfg.get("color_scheme", "azul"),
        "tipografia":    cfg.get("tipografia",   "cm"),
        "font_size":     cfg.get("font_size",    12),
        "linespread":    1.0,
        "modo_compacto": cfg.get("modo_compacto", False),
        # Puntos y penalización
        "pts_fund":      cfg.get("pts_fund", ""),
        "pts_test":      cfg.get("pts_test", ""),
        "penalizacion":  cfg.get("penalizacion", ""),
        # Diseño
        "campos_alumno":  cfg.get("campos_alumno", ["nombre", "dni", "grupo", "firma"]),
        "opciones_cols":  cfg.get("opciones_cols", 1),
        "logo_path":      st.session_state.get("_logo_path", ""),
        "estilo_num":     cfg.get("estilo_num", "cuadrado"),
        # Títulos de secciones
        "titulo_fund":    cfg.get("titulo_fund", "PREGUNTAS DE DESARROLLO"),
        "titulo_test":    cfg.get("titulo_test", "PREGUNTAS TEST"),
        # Hoja de respuestas
        "hoja_respuestas": cfg.get("hoja_respuestas", False),
        "estilo_hoja":     cfg.get("estilo_hoja", "omr"),
        # Marca de agua
        "watermark_sol":  cfg.get("watermark_sol", False),
        "watermark_text": cfg.get("watermark_text", "SOLUCIONES"),
        # Encabezado/pie
        "fancyhdr_on":   cfg.get("fancyhdr_on", True),
        "footer_text":   cfg.get("footer_text", ""),
        "dos_por_hoja":  cfg.get("dos_por_hoja", False),
        # Info en soluciones
        "sol_info_bloque": cfg.get("sol_info_bloque", False),
        "sol_info_tema":   cfg.get("sol_info_tema",   False),
        "sol_info_dif":    cfg.get("sol_info_dif",    False),
        # Solucionario
        "incluir_solucionario": cfg.get("incluir_solucionario", False),
        "titulo_solucionario":  cfg.get("titulo_solucionario", "Solucionario"),
        # Caja de calificación
        "notacal_dev":   cfg.get("notacal_dev",   False),
        "notacal_test":  cfg.get("notacal_test",  False),
        "notacal_final": cfg.get("notacal_final", False),
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

    # LaTeX (+ bundle .sty)
    if exp_tex:
        ef["latex_exam"] = lib.generar_latex_strings(master, nombre_arch, cfg_export, modo_solucion=False)
        ef["latex_sol"]  = lib.generar_latex_strings(master, nombre_arch, cfg_export, modo_solucion=True)
        for letra, data in ef["latex_exam"].items():
            ef["_zip_all"][f"{nombre_arch}_MOD{letra}.tex"] = data
        for letra, data in ef["latex_sol"].items():
            ef["_zip_all"][f"{nombre_arch}_MOD{letra}_SOL.tex"] = data
        # Bundlear .sty personalizado
        sty_bytes = lib._generar_sty(cfg_export)
        if sty_bytes:
            ef["_zip_all"]["estilo_examen_moderno_v2.sty"] = sty_bytes
        # Logo si existe
        _logo_p = st.session_state.get("_logo_path", "")
        if _logo_p and os.path.isfile(_logo_p):
            import os as _os
            with open(_logo_p, "rb") as _lf:
                ef["_zip_all"][_os.path.basename(_logo_p)] = _lf.read()

    # Imágenes de preguntas de desarrollo → bundlear en ZIP
    dev_qs_export = st.session_state.get("dev_questions", [])
    for di, dq in enumerate(dev_qs_export):
        if dq.get("imagen_bytes"):
            _ext   = os.path.splitext(dq.get("imagen_name", "img.png"))[1] or ".png"
            _fname = f"dev_img_{di+1}{_ext}"
            ef["_zip_all"][_fname] = dq["imagen_bytes"]

    # Guía de corrección (rúbrica)
    if cfg.get("incl_rubrica", False) and dev_qs_export:
        _rub_cfg = {
            "titulo": cfg.get("tit_rubrica", "Guía de Corrección"),
            "asig":   cfg.get("asig", ""),
            "inst":   cfg.get("inst", ""),
            "fecha":  cfg.get("fecha", ""),
        }
        if cfg.get("fmt_rubrica_tex", True) and exp_tex:
            _rub_tex = lib.generar_rubrica_latex(dev_qs_export, _rub_cfg)
            ef["_zip_all"][f"{nombre_arch}_RUBRICA.tex"] = _rub_tex
        if cfg.get("fmt_rubrica_word", True) and exp_word:
            _rub_word = lib.generar_rubrica_word_bytes(dev_qs_export, _rub_cfg)
            ef["_zip_all"][f"{nombre_arch}_RUBRICA.docx"] = _rub_word

    # Versión adaptada
    if cfg.get("adapt_enabled", False) and (exp_word or exp_tex):
        cfg_adapt = dict(cfg_export)
        cfg_adapt["font_size"]         = int(cfg.get("adapt_font_size", 14))
        cfg_adapt["linespread"]        = float(cfg.get("adapt_spacing", "1.5"))
        cfg_adapt["adapt_espacio_pct"] = int(cfg.get("adapt_espacio_pct", 50))
        cfg_adapt["adaptada_id"]       = cfg.get("adapt_id", "VERSIÓN ADAPTADA")
        cfg_adapt["modo_compacto"]     = False  # nunca compacto en adaptada
        if exp_word:
            adapt_word = lib.rellenar_plantilla_word_bytes(master, nombre_arch, cfg_adapt, modo_solucion=False)
            ef["word_adapt"] = adapt_word
            for letra, data in adapt_word.items():
                ef["_zip_all"][f"{nombre_arch}_MOD{letra}_ADAPT.docx"] = data
        if exp_tex:
            adapt_latex = lib.generar_latex_strings(master, nombre_arch, cfg_adapt, modo_solucion=False)
            ef["latex_adapt"] = adapt_latex
            for letra, data in adapt_latex.items():
                ef["_zip_all"][f"{nombre_arch}_MOD{letra}_ADAPT.tex"] = data

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

    # Historial — estadísticas de dificultad y bloques
    _df_exp = st.session_state.df_preguntas
    _df_used = _df_exp[_df_exp["ID_Pregunta"].isin(sel_actual)]
    _dif_ctr = _df_used["dificultad"].str.lower().value_counts()
    _bloques_usados = sorted(_df_used["bloque"].dropna().unique().tolist(), key=_nsort)
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
        "n_facil":      int(_dif_ctr.get("facil",  0)),
        "n_media":      int(_dif_ctr.get("media",  0)),
        "n_dificil":    int(_dif_ctr.get("dificil",0)),
        "bloques":      _bloques_usados,
        "exam_cfg":     dict(cfg),
    })
    st.session_state.cache_examen   = pool
    st.session_state["export_files"] = ef


@st.dialog("✅ Confirmar exportación", width="small")
def _dialog_confirmar_export():
    cfg      = st.session_state.get("exam_cfg", {})
    sel      = get_sel_ids()
    auto_rec = st.session_state.get("auto_recipe", {})
    n_rec    = sum(int(v) for bd in auto_rec.values() for sd in bd.values()
                   if isinstance(sd, dict) for v in sd.values() if isinstance(v, (int, float)))
    n_mod    = cfg.get("vers", 1)
    _lbl     = (f"{len(sel)} fijas + ~{n_rec} auto" if sel and n_rec
                else f"~{n_rec} auto" if n_rec else str(len(sel)))
    st.markdown(f"**{_lbl} preguntas · {n_mod} modelo(s)**")
    formatos = ["📊 CSV Claves + Metadatos (siempre)"]
    if cfg.get("exp_word", True): formatos.append(f"📄 Word: {n_mod} examen(es) + {n_mod} con soluciones")
    if cfg.get("exp_tex",  True): formatos.append(f"📑 LaTeX: {n_mod} examen(es) + {n_mod} con soluciones")
    for f_item in formatos:
        st.markdown(f"• {f_item}")
    sol_lb = []
    if cfg.get("sol_bold"): sol_lb.append("negrita")
    _clbl = {"red": "rojo", "green": "verde", "blue": "azul", "orange": "naranja", "purple": "morado"}
    if cfg.get("sol_color"): sol_lb.append(_clbl.get(cfg["sol_color"], cfg["sol_color"]))
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


_SOL_COLOR_CSS = {
    "red": "#c0392b", "green": "#1e8a1e", "blue": "#0a4e8a",
    "orange": "#cc6600", "purple": "#6a0dad",
}


def _build_exam_preview_html(cfg, pool_p, dev_qs, show_sol=False, modelo="A"):
    """Genera HTML que imita el aspecto del examen impreso."""
    _sol_css_color = _SOL_COLOR_CSS.get(cfg.get("sol_color", ""), "#1a7a2e")
    html = []
    html.append(f"""<style>
.ep-wrap {{ max-width:760px; margin:0 auto; font-family:'Times New Roman',serif; font-size:11pt; color:#111; background:#fff; padding:24px 32px; border:1px solid #ccc; border-radius:6px; }}
.ep-header {{ text-align:center; border-bottom:2px solid #333; padding-bottom:10px; margin-bottom:14px; }}
.ep-inst {{ font-size:12pt; font-weight:bold; }}
.ep-title {{ font-size:15pt; font-weight:bold; margin:4px 0; }}
.ep-subtitle {{ font-size:12pt; }}
.ep-meta {{ font-size:9.5pt; color:#444; margin-top:4px; }}
.ep-scoring {{ font-size:9.5pt; color:#1a5276; background:#eaf4fb; border:1px solid #aed6f1; border-radius:4px; padding:3px 10px; margin-top:6px; display:inline-block; }}
.ep-campos {{ border-top:1px solid #aaa; padding-top:10px; margin:12px 0 6px 0; display:flex; flex-wrap:wrap; gap:12px 24px; align-items:flex-end; font-size:11pt; }}
.ep-campo {{ display:flex; align-items:baseline; gap:4px; }}
.ep-campo b {{ white-space:nowrap; }}
.ep-campo .ep-underline {{ min-width:80px; flex:1; border-bottom:1px solid #555; min-height:18px; display:inline-block; }}
.ep-campo .ep-underline-xs {{ width:100px; border-bottom:1px solid #555; min-height:18px; display:inline-block; }}
.ep-instr {{ background:#f7f7f7; border:1px solid #bbb; border-radius:4px; padding:8px 12px; font-size:10pt; font-style:italic; margin:10px 0 14px 0; }}
.ep-part {{ font-size:12pt; font-weight:bold; text-align:center; background:#2c3e50; color:#fff; padding:5px 12px; margin:16px 0 8px 0; border-radius:4px; }}
.ep-part-info {{ font-size:10pt; font-style:italic; color:#444; margin-bottom:8px; }}
.ep-bloque-sep {{ font-size:10pt; font-weight:bold; color:#2c3e50; border-bottom:1px solid #adb5bd; margin:10px 0 4px 0; padding-bottom:2px; }}
.ep-q {{ margin-bottom:10px; page-break-inside:avoid; }}
.ep-q-stem {{ margin:0 0 5px 0; }}
.ep-q-num {{ font-weight:bold; }}
.ep-options {{ margin:3px 0 3px 22px; font-size:10.5pt; }}
.ep-opt {{ display:block; padding:1px 4px; }}
.ep-opt.correct {{ font-weight:bold; color:{_sol_css_color}; }}
.ep-space-box {{ border:1px solid #999; margin:5px 0 12px 22px; border-radius:3px; background:#fafafa; }}
</style>""")

    html.append('<div class="ep-wrap">')

    # ── Cabecera ──────────────────────────────────────────────────────────────
    inst  = cfg.get("inst", "")
    asig  = cfg.get("asig", "")
    tipo  = cfg.get("tipo", "Examen")
    fecha = cfg.get("fecha", "")
    tiem  = cfg.get("tiem", "")
    pts_fund    = str(cfg.get("pts_fund", "")).strip()
    pts_test    = str(cfg.get("pts_test", "")).strip()
    penalizacion = str(cfg.get("penalizacion", "")).strip()

    html.append('<div class="ep-header">')
    if inst:
        html.append(f'<div class="ep-inst">{inst}</div>')
    html.append(f'<div class="ep-title">{asig}</div>')
    html.append(f'<div class="ep-subtitle">{tipo} &mdash; Modelo {modelo}</div>')
    meta_parts = []
    if fecha: meta_parts.append(fecha)
    if tiem:  meta_parts.append(f"Tiempo: {tiem}")
    if meta_parts:
        html.append(f'<div class="ep-meta">{" &nbsp;|&nbsp; ".join(meta_parts)}</div>')

    # Puntuación en cabecera
    _score_parts = []
    if pts_fund:  _score_parts.append(f"Desarrollo: {pts_fund} pts")
    if pts_test:  _score_parts.append(f"Test: {pts_test} pts")
    if penalizacion and penalizacion not in ("Sin penalización", ""):
        _score_parts.append(f"Penalización: {penalizacion}")
    if _score_parts:
        html.append(f'<div class="ep-scoring">{"&nbsp;&nbsp;|&nbsp;&nbsp;".join(_score_parts)}</div>')

    html.append('</div>')  # ep-header

    # ── Campos del alumno ─────────────────────────────────────────────────────
    campos_alumno = cfg.get("campos_alumno", ["nombre", "dni", "grupo", "firma"])
    _campo_labels = {
        "nombre": "Nombre", "dni": "DNI/NIE", "grupo": "Grupo/Aula",
        "firma": "Firma", "email": "Email", "matricula": "Nº Matrícula",
        "titulacion": "Titulación", "telefono": "Teléfono", "notas": "Observaciones",
    }
    _short_campos = {"dni", "grupo", "firma", "matricula", "telefono"}
    if campos_alumno:
        html.append('<div class="ep-campos">')
        for campo in campos_alumno:
            lbl = _campo_labels.get(campo, campo.capitalize())
            ul_cls = "ep-underline-xs" if campo in _short_campos else "ep-underline"
            html.append(
                f'<div class="ep-campo">'
                f'<b>{lbl}:&nbsp;</b>'
                f'<span class="{ul_cls}"></span>'
                f'</div>'
            )
        html.append('</div>')

    # ── Instrucciones generales ───────────────────────────────────────────────
    instr = cfg.get("ins", "")
    if instr:
        html.append(f'<div class="ep-instr">{instr}</div>')

    # ── PARTE I: Desarrollo ───────────────────────────────────────────────────
    both_sections = bool(dev_qs) and bool(pool_p)
    tit_fund = cfg.get("titulo_fund", "PREGUNTAS DE DESARROLLO")
    tit_test = cfg.get("titulo_test", "PREGUNTAS TEST")
    if dev_qs:
        info_fund = cfg.get("h1", "")
        _fund_hdr = f"PARTE I &mdash; {tit_fund}" if both_sections else tit_fund
        _fund_info = f" &nbsp;<span style='font-weight:normal;font-size:10pt'>[{pts_fund} pts]</span>" if pts_fund else ""
        html.append(f'<div class="ep-part">{_fund_hdr}{_fund_info}</div>')
        if info_fund:
            html.append(f'<div class="ep-part-info">{info_fund}</div>')
        for i, q in enumerate(dev_qs):
            import base64 as _b64
            pts       = q.get("pts", 1)
            esp       = q.get("espacio", "Automático")
            txt       = q.get("txt", "")
            img_bytes = q.get("imagen_bytes")
            img_pos   = q.get("imagen_pos", "debajo")
            img_name  = q.get("imagen_name", "")
            heights   = {"5 líneas": 70, "10 líneas": 130, "media cara": 200, "cara completa": 360}
            box_h     = next((v for k, v in heights.items() if k.lower() in esp.lower()), 100)
            _img_ext  = (os.path.splitext(img_name)[1].lstrip(".") or "png") if img_name else "png"
            _img_html = (
                f'<div style="text-align:center;margin:6px 0">'
                f'<img src="data:image/{_img_ext};base64,{_b64.b64encode(img_bytes).decode()}" '
                f'style="max-width:85%;border:1px solid #ccc;border-radius:3px"></div>'
            ) if img_bytes else ""

            html.append('<div class="ep-q">')
            if img_bytes and img_pos == 'encima':
                html.append(_img_html)
            html.append(
                f'<div class="ep-q-stem">'
                f'<span class="ep-q-num">{i+1}.</span>'
                f' <em style="font-size:9.5pt;color:#555">({pts} pt{"s" if float(pts) != 1 else ""})</em>'
                f'<span style="margin-left:6px">{txt}</span>'
                f'</div>'
            )
            if img_bytes and img_pos in ('debajo', 'lado'):
                html.append(_img_html)
            html.append(f'<div class="ep-space-box" style="min-height:{box_h}px"></div>')
            html.append('</div>')

    # ── PARTE II: Test ────────────────────────────────────────────────────────
    if pool_p:
        info_test = cfg.get("h2", "")
        _pen_info = ""
        if penalizacion and penalizacion not in ("Sin penalización", ""):
            _pen_info = f" &nbsp;<span style='font-weight:normal;font-size:10pt'>pen. {penalizacion}</span>"
        _test_hdr = f"PARTE II &mdash; {tit_test}" if both_sections else tit_test
        _test_info = (
            f" &nbsp;<span style='font-weight:normal;font-size:10pt'>[{pts_test} pts{_pen_info}]</span>"
            if pts_test else _pen_info
        )
        html.append(f'<div class="ep-part">{_test_hdr}{_test_info}</div>')
        if info_test:
            html.append(f'<div class="ep-part-info">{info_test}</div>')

        # Separadores de bloque
        _cur_bloque = None
        for i, p in enumerate(pool_p):
            _p_bloque = str(p.get("bloque", ""))
            if _p_bloque and _p_bloque != _cur_bloque:
                _cur_bloque = _p_bloque
                _blq_name = nombre_bloque(_p_bloque)
                html.append(f'<div class="ep-bloque-sep">&#9658; {_blq_name}</div>')

            enun      = p.get("enunciado", "")
            ops_list  = p.get("opciones_list", ["", "", "", ""])
            letra_c   = p.get("letra_correcta", "A")
            idx_c     = {"A": 0, "B": 1, "C": 2, "D": 3}.get(letra_c, 0)
            labels    = ["a", "b", "c", "d"]
            html.append(f'<div class="ep-q">')
            html.append(
                f'<div class="ep-q-stem">'
                f'<span class="ep-q-num">{i+1}.</span>'
                f'<span style="margin-left:6px">{enun}</span>'
                f'</div>'
            )
            html.append('<div class="ep-options">')
            for j, lbl in enumerate(labels):
                if j < len(ops_list):
                    txt = ops_list[j]
                    is_c = show_sol and j == idx_c
                    css  = 'ep-opt correct' if is_c else 'ep-opt'
                    mark = " ✓" if is_c else ""
                    html.append(f'<span class="{css}">{lbl})&nbsp;{txt}{mark}</span>')
            html.append('</div>')  # ep-options
            html.append('</div>')  # ep-q

    html.append('</div>')  # ep-wrap
    return "\n".join(html)


def _build_solucionario_html(cfg, pool_p, dev_qs):
    """Genera HTML del solucionario: enunciado + respuesta correcta + texto de solución."""
    _sol_css_color = _SOL_COLOR_CSS.get(cfg.get("sol_color", ""), "#1a7a2e")
    html = [f"""<style>
.sol-wrap {{ max-width:760px; margin:0 auto; font-family:'Times New Roman',serif; font-size:11pt; color:#111; background:#fff; padding:24px 32px; border:1px solid #ccc; border-radius:6px; }}
.sol-title {{ font-size:14pt; font-weight:bold; text-align:center; background:#2c3e50; color:#fff; padding:8px 16px; border-radius:6px; margin-bottom:18px; }}
.sol-q {{ border:1px solid #dee2e6; border-radius:6px; padding:12px 16px; margin-bottom:14px; page-break-inside:avoid; }}
.sol-q-num {{ font-weight:bold; color:#2c3e50; font-size:10.5pt; }}
.sol-stem {{ margin:4px 0 8px 0; font-size:10.5pt; color:#333; }}
.sol-resp {{ font-size:10pt; font-weight:bold; color:{_sol_css_color}; margin-bottom:6px; }}
.sol-text {{ background:#f8f9fa; border-left:3px solid {_sol_css_color}; padding:8px 12px; font-size:10.5pt; line-height:1.6; border-radius:0 4px 4px 0; }}
.sol-no-sol {{ font-size:9.5pt; color:#aaa; font-style:italic; }}
.sol-dev {{ background:#fff8e1; border:1px solid #f0c040; border-radius:6px; padding:12px 16px; margin-bottom:14px; }}
.sol-dev-title {{ font-size:10.5pt; font-weight:bold; color:#7a5500; margin-bottom:6px; }}
</style>"""]
    html.append('<div class="sol-wrap">')
    tit_sol = cfg.get("titulo_solucionario", "Solucionario")
    html.append(f'<div class="sol-title">📖 {tit_sol}</div>')

    # ── Preguntas de desarrollo ──────────────────────────────────────────────
    if dev_qs:
        html.append('<div class="sol-q" style="border-color:#f0c040">')
        html.append('<div class="sol-q-num">PREGUNTAS DE DESARROLLO</div>')
        for i, q in enumerate(dev_qs):
            sol_mod = q.get("solucion_modelo", "").strip()
            html.append(f'<div style="margin:8px 0 4px 0"><b>{i+1}.</b> {q.get("txt","")}</div>')
            if sol_mod:
                html.append(f'<div class="sol-text" style="margin-bottom:8px">{sol_mod}</div>')
            else:
                html.append('<div class="sol-no-sol">Sin solución modelo</div>')
        html.append('</div>')

    # ── Preguntas test ───────────────────────────────────────────────────────
    labels_map = {0: "a", 1: "b", 2: "c", 3: "d"}
    for i, p in enumerate(pool_p):
        enun     = p.get("enunciado", "")
        ops_list = p.get("opciones_list", ["", "", "", ""])
        letra_c  = p.get("letra_correcta", "A")
        idx_c    = {"A": 0, "B": 1, "C": 2, "D": 3}.get(letra_c, 0)
        sol_txt  = str(p.get("solucion", "")).strip()
        sol_txt  = "" if sol_txt in ("nan", "None", "NaN") else sol_txt
        resp_lbl = labels_map.get(idx_c, "?")
        resp_txt = ops_list[idx_c] if idx_c < len(ops_list) else ""

        html.append('<div class="sol-q">')
        html.append(f'<div class="sol-q-num">Pregunta {i+1}</div>')
        html.append(f'<div class="sol-stem">{enun}</div>')
        html.append(
            f'<div class="sol-resp">&#10003; Respuesta: {resp_lbl}) {resp_txt}</div>'
        )
        if sol_txt:
            html.append(f'<div class="sol-text">{sol_txt}</div>')
        else:
            html.append('<div class="sol-no-sol">Sin texto de solución en la base de datos</div>')
        html.append('</div>')

    html.append('</div>')
    return "\n".join(html)


@st.dialog("👁 Vista previa · Modelo A", width="large")
def _dialog_preview_examen():
    cache  = st.session_state.get("cache_examen") or []
    sel    = get_sel_ids()
    dev_qs = st.session_state.get("dev_questions", [])

    if cache:
        pool_p = list(cache)
    elif sel:
        df_q    = st.session_state.df_preguntas
        df_dict = df_q.set_index("ID_Pregunta").to_dict("index")
        pool_p  = []
        for pid in sel:
            if pid in df_dict:
                item = dict(df_dict[pid]); item["ID_Pregunta"] = pid
                pool_p.append(item)
    else:
        pool_p = []

    if not pool_p and not dev_qs:
        st.warning("No hay preguntas seleccionadas. Ve a **👁️ Preview** y pulsa **🎲 Generar** primero.")
        return

    cfg = st.session_state.get("exam_cfg", {})

    dlg_tab_exam, dlg_tab_sol = st.tabs(["📄 Examen", "📖 Solucionario"])

    with dlg_tab_exam:
        dc1, dc2 = st.columns([3, 1])
        show_sol_p = dc1.checkbox("Mostrar respuesta correcta inline", value=True, key="_dlg_show_sol")
        render_mjax = dc2.button("∑ MathJax", key="_dlg_mjax_btn")
        if render_mjax:
            st.session_state["_dlg_mjax"] = True
        exam_html = _build_exam_preview_html(cfg, pool_p, dev_qs, show_sol=show_sol_p, modelo="A")
        if st.session_state.get("_dlg_mjax"):
            stcomponents.html(mathjax_html(exam_html), height=660, scrolling=True)
        else:
            st.caption("Pulsa **∑ MathJax** para renderizar fórmulas.")
            stcomponents.html(exam_html, height=660, scrolling=True)

    with dlg_tab_sol:
        ds1, ds2 = st.columns([3, 1])
        ds1.caption("Muestra el texto completo del campo **solución** de cada pregunta.")
        render_mjax_sol = ds2.button("∑ MathJax", key="_dlg_mjax_sol_btn")
        if render_mjax_sol:
            st.session_state["_dlg_mjax_sol"] = True
        sol_html = _build_solucionario_html(cfg, pool_p, dev_qs)
        if st.session_state.get("_dlg_mjax_sol"):
            stcomponents.html(mathjax_html(sol_html), height=660, scrolling=True)
        else:
            st.caption("Pulsa **∑ MathJax** para renderizar fórmulas LaTeX.")
            stcomponents.html(sol_html, height=660, scrolling=True)


def _render_pdf_viewer(pdf_bytes: bytes, height: int = 700):
    """Muestra un PDF en un iframe usando blob URL (funciona en Chrome/Firefox).
    Chrome bloquea data: URIs en iframes, pero permite createObjectURL."""
    import base64 as _b64
    _b64_str = _b64.b64encode(pdf_bytes).decode()
    _uid = abs(hash(pdf_bytes[:64]))  # ID único para el elemento
    stcomponents.html(f"""
<script>
(function() {{
  var b64 = "{_b64_str}";
  var bin = atob(b64);
  var arr = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  var blob = new Blob([arr], {{type: "application/pdf"}});
  var url  = URL.createObjectURL(blob);
  var el   = document.getElementById("pdfviewer_{_uid}");
  if (el) el.src = url;
}})();
</script>
<iframe id="pdfviewer_{_uid}" src="" width="100%" height="{height}px"
  style="border:1px solid #ccc;border-radius:6px;display:block">
</iframe>
""", height=height + 20, scrolling=False)


@st.dialog("🔨 Compilando PDF…", width="large")
def _dialog_compilar_pdf():
    """Diálogo que compila el PDF y muestra progreso + resultado."""
    req = st.session_state.get("_compile_request", {})
    if not req:
        st.error("Sin datos de compilación.")
        return

    st.caption(
        "Enviando a [latexonline.cc](https://latexonline.cc) · "
        "⚠️ Servidor externo — no incluyas datos personales en los enunciados."
    )
    _prog = st.progress(0, text="Preparando archivos…")
    _status = st.empty()

    _sty = req["sty"]
    if isinstance(_sty, str):
        _sty = _sty.encode("utf-8")

    _prog.progress(20, text="Empaquetando .tex + .sty…")
    _status.info("Enviando a latexonline.cc…")

    try:
        _prog.progress(40, text="Compilando con pdflatex…")
        _pdf_bytes = lib.compilar_latex_online(
            tex_str=req["tex"],
            sty_bytes=_sty,
            extra_files=req.get("imgs", {}),
            nombre=req["nombre"],
        )
        _prog.progress(100, text="✅ Compilación correcta")
        _status.success(f"PDF generado correctamente — {len(_pdf_bytes)//1024} KB")
        st.session_state["_compiled_pdf"] = {
            "bytes": _pdf_bytes,
            "pdf_name": req["pdf_name"],
        }
        st.session_state.pop("_compile_request", None)

        # Previsualización inline dentro del diálogo
        st.download_button(
            "⬇️ Descargar PDF",
            data=_pdf_bytes,
            file_name=req["pdf_name"],
            mime="application/pdf",
            use_container_width=True,
            key="dl_pdf_dialog",
        )
        _render_pdf_viewer(_pdf_bytes, height=700)

    except Exception as _ex:
        _prog.progress(100, text="❌ Error")
        _status.error("Error de compilación")
        _log = str(_ex)
        _err_lines = [l for l in _log.splitlines() if "error" in l.lower()]
        if _err_lines:
            st.warning("**Errores detectados:**\n\n" + "\n".join(f"- `{l.strip()}`" for l in _err_lines[:10]))
        with st.expander("📋 Log completo"):
            st.code(_log[:4000], language="")


@st.dialog("📄 Vista PDF compilado", width="large")
def _dialog_ver_pdf(cpdf: dict):
    st.download_button(
        "⬇️ Descargar",
        data=cpdf["bytes"],
        file_name=cpdf["pdf_name"],
        mime="application/pdf",
        use_container_width=True,
        key="dl_pdf_viewer_dlg",
    )
    _render_pdf_viewer(cpdf["bytes"], height=750)


with tab_exp:
    sel_actual = get_sel_ids()
    n_pregs    = len(sel_actual)
    _auto_rec  = st.session_state.get("auto_recipe", {})
    n_recipe   = sum(
        int(v)
        for blq_data in _auto_rec.values()
        for slot_data in blq_data.values()
        if isinstance(slot_data, dict)
        for v in slot_data.values()
        if isinstance(v, (int, float))
    )
    n_total    = n_pregs + n_recipe
    cfg        = st.session_state.get("exam_cfg", {})

    col_cfg, col_res = st.columns([3, 2], gap="large")

    with col_cfg:

        # ── 1. Configuración del examen ────────────────────────────────────────
        with st.expander("📋 Configuración del examen", expanded=True):
            _cg = st.session_state.get("cfg_general", {})

            # Sincronizar desde cfg_general (flag pattern)
            if st.session_state.pop("_sync_from_cfg_general", False):
                st.session_state["exp_inst"]  = _cg.get("universidad") or _cg.get("departamento") or ""
                st.session_state["exp_asig"]  = _cg.get("asignatura") or ""

            # Inicializar desde cfg_general si el widget aún no existe en session_state
            if "exp_inst" not in st.session_state:
                st.session_state["exp_inst"] = cfg.get("inst") or _cg.get("universidad") or _cg.get("departamento") or ""
            if "exp_asig" not in st.session_state:
                st.session_state["exp_asig"] = cfg.get("asig") or _cg.get("asignatura") or ""

            _sync_col, _ = st.columns([2, 4])
            if _sync_col.button("↺ Rellenar desde Configuración", key="btn_sync_cfg",
                                help="Sobreescribe Institución y Asignatura con los datos de ⚙️ Configuración"):
                st.session_state["_sync_from_cfg_general"] = True
                st.rerun()

            e1, e2, e3 = st.columns(3)
            inst  = e1.text_input("Institución",    key="exp_inst")
            asig  = e2.text_input("Asignatura",     key="exp_asig")
            tipo  = e3.text_input("Tipo de examen", value=cfg.get("tipo", "EXAMEN FINAL"),          key="exp_tipo")
            e4, e5, e6 = st.columns(3)
            fecha         = e4.text_input("Fecha",          value=cfg.get("fecha", datetime.date.today().strftime("%d/%m/%Y")), key="exp_fecha")
            tiem          = e5.text_input("Tiempo",         value=cfg.get("tiem",  "90 min"),       key="exp_tiem")
            nombre_archivo = e6.text_input("Nombre archivo", value=cfg.get("file", f"Examen_{datetime.date.today()}"), key="exp_file")
            _campos_def   = cfg.get("campos_alumno", ["nombre", "dni", "grupo", "firma"])
            _campos_map   = {"nombre": "Nombre", "dni": "DNI/NIU", "grupo": "Grupo", "firma": "Firma"}
            _campos_sel   = st.multiselect("Campos del alumno en el examen", list(_campos_map.keys()),
                                           default=_campos_def,
                                           format_func=lambda x: _campos_map[x], key="exp_campos")

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
            oc4         = st.columns(1)[0]
            _cols_idx   = 0 if cfg.get("opciones_cols", 1) == 1 else 1
            _cols_opt   = oc4.radio("Disposición opciones test", ["1 columna", "2 columnas"],
                                    index=_cols_idx, horizontal=True, key="exp_opcols")
            opciones_cols = 1 if _cols_opt == "1 columna" else 2
        campos_alumno = _campos_sel

        # ── 3. Formatos + Marcado de soluciones ───────────────────────────────
        with st.expander("📄 Formatos y marcado de soluciones", expanded=True):
            st.markdown("**Formatos de exportación:**")
            fc1, fc2, fc3 = st.columns(3)
            fc1.markdown("📊 **CSV** (siempre)", help="Clave de respuestas y metadatos — siempre se generan")
            exp_word = fc2.checkbox("📄 Word (.docx)", value=cfg.get("exp_word", True), key="exp_word")
            exp_tex  = fc3.checkbox("📑 LaTeX (.tex)", value=cfg.get("exp_tex",  True), key="exp_tex")
            if exp_tex:
                st.caption("ℹ️ LaTeX usa `article` + `estilo_examen_moderno_v2.sty` (incluido en el ZIP).")
            st.markdown("**Marcado de la versión soluciones:**")
            sc1, sc2, sc3 = st.columns(3)
            sol_bold = sc1.checkbox("Negrita", value=cfg.get("sol_bold", False), key="exp_sol_bold")
            _color_opts = {"": "Sin color", "red": "Rojo", "green": "Verde",
                           "blue": "Azul", "orange": "Naranja", "purple": "Morado"}
            _color_cur  = cfg.get("sol_color", "red")
            _color_idx  = list(_color_opts.keys()).index(_color_cur) if _color_cur in _color_opts else 1
            sol_color = sc2.selectbox("Color respuesta correcta", list(_color_opts.keys()),
                                      index=_color_idx, format_func=lambda x: _color_opts[x],
                                      key="exp_sol_color")
            sol_ast  = sc3.checkbox("Asterisco (*)", value=cfg.get("sol_ast", True), key="exp_sol_ast")
            st.markdown("**Marca de agua en versión soluciones:**")
            wc1, wc2 = st.columns([1, 2])
            watermark_sol  = wc1.checkbox("Añadir marca de agua", value=cfg.get("watermark_sol", False), key="exp_wm_on")
            watermark_text = wc2.text_input("Texto de la marca", value=cfg.get("watermark_text", "SOLUCIONES"),
                                            key="exp_wm_text", disabled=not watermark_sol)
            st.markdown("**Info extra por pregunta en versión soluciones (LaTeX):**")
            ic1, ic2, ic3 = st.columns(3)
            sol_info_bloque = ic1.checkbox("Bloque",      value=cfg.get("sol_info_bloque", False), key="exp_sol_bloque")
            sol_info_tema   = ic2.checkbox("Tema",        value=cfg.get("sol_info_tema",   False), key="exp_sol_tema")
            sol_info_dif    = ic3.checkbox("Dificultad",  value=cfg.get("sol_info_dif",    False), key="exp_sol_dif")

        # ── 4. Instrucciones y Cabeceras ──────────────────────────────────────
        with st.expander("📝 Instrucciones y cabeceras", expanded=True):
            instr     = st.text_area("Instrucciones generales",
                                     value=cfg.get("ins", "Conteste en la hoja de respuestas."),
                                     height=70, key="exp_ins")
            tc1, tc2  = st.columns(2)
            titulo_fund = tc1.text_input("Título sección desarrollo",
                                         value=cfg.get("titulo_fund", "PREGUNTAS DE DESARROLLO"),
                                         key="exp_tit_fund")
            titulo_test = tc2.text_input("Título sección test",
                                         value=cfg.get("titulo_test", "PREGUNTAS TEST"),
                                         key="exp_tit_test")
            hc1, hc2  = st.columns(2)
            info_fund = hc1.text_area("Cabecera sección desarrollo", value=cfg.get("h1", ""), height=70, key="exp_h1")
            info_test = hc2.text_area("Cabecera sección test",       value=cfg.get("h2", ""), height=70, key="exp_h2")

        # ── 4b. Estilo visual ─────────────────────────────────────────────────
        with st.expander("🎨 Estilo visual", expanded=False):
            _scheme_opts  = {"azul": "Azul profesional", "ucm": "Colores UCM (granate)", "byn": "Blanco y Negro"}
            _scheme_cur   = cfg.get("color_scheme", "azul")
            _scheme_idx   = list(_scheme_opts.keys()).index(_scheme_cur) if _scheme_cur in _scheme_opts else 0
            sv1, sv2      = st.columns(2)
            color_scheme  = sv1.selectbox("Esquema de color", list(_scheme_opts.keys()),
                                          index=_scheme_idx, format_func=lambda x: _scheme_opts[x],
                                          key="exp_color_scheme")
            _font_opts    = {"cm": "Computer Modern (LaTeX)", "palatino": "Palatino / Georgia",
                             "times": "Times New Roman", "libertine": "Linux Libertine",
                             "helvet": "Helvetica / Arial", "garamond": "Garamond"}
            _font_cur     = cfg.get("tipografia", "cm")
            _font_idx     = list(_font_opts.keys()).index(_font_cur) if _font_cur in _font_opts else 0
            tipografia    = sv2.selectbox("Tipografía", list(_font_opts.keys()),
                                          index=_font_idx, format_func=lambda x: _font_opts[x],
                                          key="exp_tipografia")
            sv3, sv4      = st.columns(2)
            _size_opts    = [10, 11, 12]
            _size_cur     = int(cfg.get("font_size", 12))
            _size_idx     = _size_opts.index(_size_cur) if _size_cur in _size_opts else 2
            font_size_val = sv3.selectbox("Tamaño de letra", _size_opts,
                                          index=_size_idx, format_func=lambda x: f"{x} pt",
                                          key="exp_font_size")
            modo_compacto = sv4.checkbox("Modo compacto LaTeX",
                                         value=cfg.get("modo_compacto", False), key="exp_compacto",
                                         help="Encabezado pequeño, más preguntas en página 1")
            _enum_opts  = {"cuadrado": "Cuadrado ▪", "circulo": "Círculo ●", "vacio": "Círculo ○", "numero": "Número 1.", "nada": "Sin estilo"}
            _enum_cur   = cfg.get("estilo_num", "cuadrado")
            _enum_idx   = list(_enum_opts.keys()).index(_enum_cur) if _enum_cur in _enum_opts else 0
            estilo_num  = st.selectbox("Numeración de preguntas (LaTeX)", list(_enum_opts.keys()),
                                       index=_enum_idx, format_func=lambda x: _enum_opts[x],
                                       key="exp_estilo_num",
                                       help="Estilo del número de cada pregunta en el PDF LaTeX")
            fh1, fh2  = st.columns([1, 2])
            fancyhdr_on  = fh1.checkbox("Encabezado/pie de página", value=cfg.get("fancyhdr_on", True),
                                        key="exp_fancyhdr",
                                        help="Muestra asignatura + versión en cabecera y nº de página en pie")
            footer_text  = fh2.text_input("Texto extra en pie de página",
                                          value=cfg.get("footer_text", ""), key="exp_footer",
                                          placeholder="ej: Prohibido el uso de móvil",
                                          disabled=not fancyhdr_on)
            dos_por_hoja = st.checkbox(
                "2 páginas por hoja (A5 → A4 apaisado)",
                value=cfg.get("dos_por_hoja", False), key="exp_dos_por_hoja",
                help="LaTeX: imprime 2 páginas A5 en una hoja A4 apaisada (pgfpages). Word: genera en tamaño A5."
            )

        # ── 4b-bis. Hoja de respuestas ────────────────────────────────────────
        with st.expander("📋 Hoja de respuestas", expanded=False):
            st.caption("Se añade como página final del examen (solo en versión alumno, no en soluciones).")
            hr1, hr2 = st.columns([1, 2])
            hoja_respuestas = hr1.checkbox("Generar hoja de respuestas",
                                           value=cfg.get("hoja_respuestas", False), key="exp_hoja_resp")

        # ── 4b-ter. Solucionario ──────────────────────────────────────────────
        with st.expander("📖 Solucionario (apéndice)", expanded=False):
            st.caption("Añade un apéndice al LaTeX de soluciones con las soluciones desarrolladas de cada pregunta.")
            sl1, sl2 = st.columns([1, 2])
            incluir_solucionario = sl1.checkbox("Incluir solucionario",
                                                value=cfg.get("incluir_solucionario", False),
                                                key="exp_incl_sol")
            titulo_solucionario = sl2.text_input("Título del apéndice",
                                                 value=cfg.get("titulo_solucionario", "Solucionario"),
                                                 key="exp_tit_sol", disabled=not incluir_solucionario)
            _estilo_hoja_opts = {"omr": "OMR — Burbujas (○ A ○ B ○ C ○ D)", "tabla": "Tabla — Celdas para marcar"}
            _estilo_hoja_cur  = cfg.get("estilo_hoja", "omr")
            _estilo_hoja_idx  = list(_estilo_hoja_opts.keys()).index(_estilo_hoja_cur) if _estilo_hoja_cur in _estilo_hoja_opts else 0
            estilo_hoja = hr2.selectbox("Estilo de la hoja", list(_estilo_hoja_opts.keys()),
                                        index=_estilo_hoja_idx,
                                        format_func=lambda x: _estilo_hoja_opts[x],
                                        key="exp_estilo_hoja", disabled=not hoja_respuestas)

        # ── 4b-cuarto. Guía de corrección (rúbrica) ──────────────────────────
        _dev_qs_now  = st.session_state.get("dev_questions", [])
        _has_rubrica = any(q.get("criterios") or q.get("solucion_modelo","").strip()
                           for q in _dev_qs_now)
        with st.expander("📐 Guía de corrección (rúbrica)", expanded=_has_rubrica):
            st.caption(
                "Genera un documento separado con la rúbrica y soluciones modelo "
                "de las preguntas de desarrollo. Se incluye en el ZIP."
            )
            rb1, rb2, rb3 = st.columns(3)
            incl_rubrica = rb1.checkbox("Incluir guía de corrección",
                                        value=cfg.get("incl_rubrica", _has_rubrica),
                                        key="exp_incl_rubrica",
                                        disabled=not _has_rubrica)
            if not _has_rubrica:
                rb1.caption("⚠️ Define rúbrica/solución en Tab ✍️ Desarrollo")
            fmt_rubrica_word = rb2.checkbox("Formato Word (.docx)", value=cfg.get("fmt_rubrica_word", True),
                                             key="exp_rubrica_word", disabled=not incl_rubrica)
            fmt_rubrica_tex  = rb3.checkbox("Formato LaTeX (.tex)",  value=cfg.get("fmt_rubrica_tex",  True),
                                             key="exp_rubrica_tex",  disabled=not incl_rubrica)
            tit_rubrica = st.text_input("Título del documento",
                                        value=cfg.get("tit_rubrica", "Guía de Corrección"),
                                        key="exp_tit_rubrica", disabled=not incl_rubrica)

        # ── 4c-bis. Caja de calificación ──────────────────────────────────────
        _has_test_q = bool(sel_actual) or bool(st.session_state.get("auto_recipe"))
        _has_dev_q  = bool(st.session_state.get("dev_questions", []))
        with st.expander("🎓 Caja de calificación", expanded=False):
            st.caption(
                "Añade una caja para anotar la nota al final de cada sección. "
                "Solo aparece en la versión alumno, no en la de soluciones."
            )
            nc1, nc2, nc3 = st.columns(3)
            notacal_dev  = nc1.checkbox(
                "Caja desarrollo",
                value=cfg.get("notacal_dev", False), key="exp_notacal_dev",
                disabled=not _has_dev_q,
                help="Se añade al final de la sección de desarrollo"
            )
            notacal_test = nc2.checkbox(
                "Caja test",
                value=cfg.get("notacal_test", False), key="exp_notacal_test",
                disabled=not _has_test_q,
                help="Se añade al final de la sección test"
            )
            notacal_final = nc3.checkbox(
                "Nota final",
                value=cfg.get("notacal_final", False), key="exp_notacal_final",
                disabled=not (_has_dev_q or _has_test_q),
                help="Caja de nota final con suma de las partes"
            )
            if not _has_dev_q:
                nc1.caption("⚠️ Sin preguntas de desarrollo")
            if not _has_test_q:
                nc2.caption("⚠️ Sin preguntas test")
        # ── 4c. Puntos y penalización ─────────────────────────────────────────
        with st.expander("📊 Puntos y penalización", expanded=False):
            st.caption("Si dejas un campo vacío, ese dato no aparece en el examen.")
            pp1, pp2, pp3 = st.columns(3)
            pts_fund_val  = pp1.text_input("Puntos desarrollo", value=cfg.get("pts_fund", ""),
                                           key="exp_pts_fund", placeholder="ej: 4")
            pts_test_val  = pp2.text_input("Puntos test",       value=cfg.get("pts_test", ""),
                                           key="exp_pts_test", placeholder="ej: 6")
            _pen_opts     = ["Sin penalización", "−1/3", "−1/4", "−1/5", "−0,25", "Personalizado"]
            _pen_cur      = cfg.get("penalizacion", "Sin penalización")
            _pen_idx      = _pen_opts.index(_pen_cur) if _pen_cur in _pen_opts else 0
            penalizacion_sel = pp3.selectbox("Penalización", _pen_opts, index=_pen_idx, key="exp_pen")
            if penalizacion_sel == "Personalizado":
                penalizacion_val = st.text_input("Valor personalizado", value=cfg.get("pen_custom", ""),
                                                 key="exp_pen_custom", placeholder="ej: −0.2")
            else:
                penalizacion_val = "" if penalizacion_sel == "Sin penalización" else penalizacion_sel

        # ── 4d. Versión adaptada ──────────────────────────────────────────────
        with st.expander("♿ Versión adaptada", expanded=False):
            adapt_enabled = st.checkbox("Generar versión adaptada adicional",
                                        value=cfg.get("adapt_enabled", False), key="exp_adapt_on")
            if adapt_enabled:
                ad1, ad2, ad3 = st.columns(3)
                _asize_opts  = [12, 14, 16, 18]
                _asize_cur   = int(cfg.get("adapt_font_size", 14))
                _asize_idx   = _asize_opts.index(_asize_cur) if _asize_cur in _asize_opts else 1
                adapt_fsize  = ad1.selectbox("Tamaño letra", _asize_opts, index=_asize_idx,
                                             format_func=lambda x: f"{x} pt", key="exp_adapt_size")
                _aspac_opts  = {"1.0": "Normal", "1.5": "1,5×", "2.0": "Doble"}
                _aspac_cur   = str(cfg.get("adapt_spacing", "1.5"))
                _aspac_idx   = list(_aspac_opts.keys()).index(_aspac_cur) if _aspac_cur in _aspac_opts else 1
                adapt_spac   = ad2.selectbox("Interlineado", list(_aspac_opts.keys()),
                                             index=_aspac_idx, format_func=lambda x: _aspac_opts[x],
                                             key="exp_adapt_spac")
                _aextra_opts = {"0": "Normal", "25": "+25%", "50": "+50%", "100": "+100%"}
                _aextra_cur  = str(cfg.get("adapt_espacio_pct", "50"))
                _aextra_idx  = list(_aextra_opts.keys()).index(_aextra_cur) if _aextra_cur in _aextra_opts else 2
                adapt_extra  = ad3.selectbox("Cajas desarrollo", list(_aextra_opts.keys()),
                                             index=_aextra_idx, format_func=lambda x: _aextra_opts[x],
                                             key="exp_adapt_extra")
                adapt_id_val = st.text_input("Identificador en cabecera",
                                             value=cfg.get("adapt_id", "VERSIÓN ADAPTADA"),
                                             key="exp_adapt_id",
                                             placeholder="ej: VERSIÓN ADAPTADA — García López")
            else:
                adapt_fsize = int(cfg.get("adapt_font_size", 14))
                adapt_spac  = str(cfg.get("adapt_spacing", "1.5"))
                adapt_extra = str(cfg.get("adapt_espacio_pct", "50"))
                adapt_id_val = cfg.get("adapt_id", "VERSIÓN ADAPTADA")

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
                if tc1.button("🗑️ Quitar plantilla Word", key="btn_clear_tpl_word", use_container_width=True):
                    st.session_state.pop("_tpl_word_bytes", None)
                    st.session_state.pop("_tpl_word_name", None)
                    st.rerun()
            if tpl_tex_file:
                st.session_state["_tpl_tex_bytes"] = tpl_tex_file.getvalue()
                st.session_state["_tpl_tex_name"]  = tpl_tex_file.name
                tc2.success(f"✅ {tpl_tex_file.name}")
            elif st.session_state.get("_tpl_tex_bytes"):
                tc2.info(f"En memoria: {st.session_state.get('_tpl_tex_name','plantilla.tex')}")
                if tc2.button("🗑️ Quitar plantilla LaTeX", key="btn_clear_tpl_tex", use_container_width=True):
                    st.session_state.pop("_tpl_tex_bytes", None)
                    st.session_state.pop("_tpl_tex_name", None)
                    st.rerun()
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
            "opciones_cols": opciones_cols, "campos_alumno": campos_alumno,
            "exp_word": exp_word, "exp_tex": exp_tex,
            "sol_bold": sol_bold, "sol_color": sol_color, "sol_ast": sol_ast,
            "anc_chk": anclaje_auto, "anc_txt": anclaje_extra,
            # Estilo visual
            "color_scheme": color_scheme, "tipografia": tipografia,
            "font_size": font_size_val, "modo_compacto": modo_compacto,
            "estilo_num": estilo_num,
            "fancyhdr_on": fancyhdr_on, "footer_text": footer_text,
            "dos_por_hoja": dos_por_hoja,
            # Puntos y penalización
            "pts_fund": pts_fund_val, "pts_test": pts_test_val,
            "penalizacion": penalizacion_val,
            "pen_custom": cfg.get("pen_custom", ""),
            # Versión adaptada
            "adapt_enabled":    adapt_enabled,
            "adapt_font_size":  adapt_fsize,
            "adapt_spacing":    adapt_spac,
            "adapt_espacio_pct": int(adapt_extra),
            "adapt_id":         adapt_id_val,
            # Títulos de secciones
            "titulo_fund": titulo_fund, "titulo_test": titulo_test,
            # Hoja de respuestas
            "hoja_respuestas": hoja_respuestas, "estilo_hoja": estilo_hoja,
            # Marca de agua
            "watermark_sol": watermark_sol, "watermark_text": watermark_text,
            # Info en soluciones
            "sol_info_bloque": sol_info_bloque,
            "sol_info_tema":   sol_info_tema,
            "sol_info_dif":    sol_info_dif,
            # Solucionario
            "incluir_solucionario": incluir_solucionario,
            "titulo_solucionario":  titulo_solucionario,
            # Guía de corrección (rúbrica)
            "incl_rubrica":     incl_rubrica,
            "fmt_rubrica_word": fmt_rubrica_word,
            "fmt_rubrica_tex":  fmt_rubrica_tex,
            "tit_rubrica":      tit_rubrica,
            # Caja de calificación
            "notacal_dev":   notacal_dev,
            "notacal_test":  notacal_test,
            "notacal_final": notacal_final,
        }

    # ── Panel derecho: Resumen + Botones + Descargas ───────────────────────────
    with col_res:

        # Construir textos del resumen
        _sol_marks = []
        if sol_bold: _sol_marks.append("negrita")
        _color_label = {"red": "rojo", "green": "verde", "blue": "azul", "orange": "naranja", "purple": "morado"}
        if sol_color: _sol_marks.append(_color_label.get(sol_color, sol_color))
        if sol_ast:  _sol_marks.append("asterisco *")
        _sol_str = ", ".join(_sol_marks) if _sol_marks else "sin marcar"

        _fmt_parts = ["📊 CSV"]
        if exp_word: _fmt_parts.append("📄 Word")
        if exp_tex:  _fmt_parts.append("📑 LaTeX")
        _fmt_str = " · ".join(_fmt_parts)

        _tpl_w = st.session_state.get("_tpl_word_name", "por defecto")
        _tpl_t = st.session_state.get("_tpl_tex_name",  "por defecto")

        _orden_labels = {"bloques": "Aleatorio por bloques", "global": "Aleatorio global",
                         "manual": "Manual (selección)", "secuencial": "Sin barajar (ID)"}
        _orden_label = _orden_labels.get(orden, orden)
        _barajar_str = "Sí" if barajar else "No"

        _n_dev = len(st.session_state.get("dev_questions", []))
        _dev_str = f" + {_n_dev} desarrollo" if _n_dev else ""

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
            <div>📋 <b>{n_pregs if not n_recipe else (f"{n_pregs} fijas + ~{n_recipe} auto" if n_pregs else f"~{n_recipe} auto")}</b> test{_dev_str} &nbsp;&nbsp; 🔢 <b>{num_modelos}</b> modelo(s)</div>
            <div>🔀 {_orden_label}</div>
            <div>🃏 Barajar respuestas: {_barajar_str}</div>
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

        _need_preview = n_recipe > 0 and not st.session_state.get("cache_examen")
        if st.button("💾 EXPORTAR EXAMEN", type="primary", use_container_width=True,
                     key="btn_export_main", disabled=(n_total == 0 or _need_preview)):
            _dialog_confirmar_export()
        if n_total == 0:
            st.caption("⚠️ Ve a la pestaña **Selección** para elegir preguntas o configura un relleno automático.")
        elif _need_preview:
            st.caption("⚠️ Tienes una receta automática. Ve a **👁️ Preview** y pulsa **🎲 Generar** para fijar las preguntas antes de exportar.")

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
                if ef.get("word_adapt"):
                    st.download_button("♿ Adaptada (Word)",
                        data=lib.generar_zip_bytes({f"{_nef}_MOD{l}_ADAPT.docx": d for l, d in ef["word_adapt"].items()}),
                        file_name=f"{_nef}_word_adaptada.zip", mime="application/zip",
                        use_container_width=True, key="dl_word_adapt")

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
                if ef.get("latex_adapt"):
                    st.download_button("♿ Adaptada (LaTeX)",
                        data=lib.generar_zip_bytes({f"{_nef}_MOD{l}_ADAPT.tex": d for l, d in ef["latex_adapt"].items()}),
                        file_name=f"{_nef}_latex_adaptada.zip", mime="application/zip",
                        use_container_width=True, key="dl_latex_adapt")

            st.markdown("**CSV:**")
            _cc1, _cc2 = st.columns(2)
            _cc1.download_button("📊 Clave",     data=ef["csv_claves"], file_name=f"{_nef}_CLAVES.csv",
                                 mime="text/csv", use_container_width=True, key="dl_csv_claves")
            _cc2.download_button("📊 Metadatos", data=ef["csv_meta"],   file_name=f"{_nef}_METADATA.csv",
                                 mime="text/csv", use_container_width=True, key="dl_csv_meta")

            if st.button("🔄 Nueva exportación", use_container_width=True, key="btn_clear_export"):
                st.session_state.pop("export_files", None)
                st.session_state.pop("_prev_mjax", None)
                st.session_state.pop("_compiled_pdf", None)
                st.rerun()

        # ── Compilación PDF online ────────────────────────────────────────────
        st.markdown("---")

        _ef_now    = st.session_state.get("export_files")
        _tex_avail = _ef_now and _ef_now.get("latex_exam")

        if not _tex_avail:
            st.info("Activa **📑 LaTeX** y exporta primero para poder compilar el PDF.")
        else:
            _latex_exam   = _ef_now["latex_exam"]
            _sty_b        = _ef_now["_zip_all"].get("estilo_examen_moderno_v2.sty", b"")
            _img_files    = {k: v for k, v in _ef_now["_zip_all"].items()
                             if k.startswith("dev_img_")}
            _modelos_disp = list(_latex_exam.keys())
            nombre_compile = _ef_now.get("nombre", "examen")

            _cx1, _cx2, _cx3 = st.columns([1, 1, 2])
            _modelo_sel = _cx1.selectbox("Modelo", _modelos_disp,
                                          key="compile_modelo",
                                          format_func=lambda x: f"Modelo {x}")
            _sol_sel    = _cx2.radio("Versión", ["Alumno", "Soluciones"],
                                      horizontal=True, key="compile_ver")

            if _cx3.button("🔨 Compilar PDF", type="primary",
                            use_container_width=True, key="btn_compile_pdf"):
                _tex_src = (
                    _ef_now["latex_exam"][_modelo_sel]
                    if _sol_sel == "Alumno"
                    else _ef_now.get("latex_sol", _ef_now["latex_exam"])[_modelo_sel]
                )
                _pdf_name = f"{nombre_compile}_MOD{_modelo_sel}{'_SOL' if _sol_sel == 'Soluciones' else ''}.pdf"
                st.session_state["_compile_request"] = {
                    "tex": _tex_src, "sty": _sty_b, "imgs": _img_files,
                    "nombre": nombre_compile, "pdf_name": _pdf_name,
                }
                st.session_state.pop("_compiled_pdf", None)
                st.session_state["_show_compile_dialog"] = True
                st.rerun()

            # Abrir el diálogo si hay petición pendiente
            if st.session_state.pop("_show_compile_dialog", False):
                _dialog_compilar_pdf()

            # Resultado previo (persiste entre reruns)
            _cpdf = st.session_state.get("_compiled_pdf")
            if _cpdf:
                import base64 as _b64
                _da, _db = st.columns([1, 1])
                _da.download_button(
                    "⬇️ Descargar PDF compilado",
                    data=_cpdf["bytes"],
                    file_name=_cpdf["pdf_name"],
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_compiled_pdf",
                )
                if _db.button("🔍 Ver PDF", use_container_width=True, key="btn_ver_pdf"):
                    st.session_state["_show_pdf_viewer"] = True
                    st.rerun()
                if st.session_state.pop("_show_pdf_viewer", False):
                    _dialog_ver_pdf(_cpdf)

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
            ids         = entry.get("ids", [])
            n_f         = entry.get("n_facil",   0)
            n_m         = entry.get("n_media",   0)
            n_d         = entry.get("n_dificil", 0)
            n_total_e   = len(ids)
            bloques_e   = entry.get("bloques", [])
            exam_cfg_e  = entry.get("exam_cfg", {})
            _blq_str    = ", ".join(nombre_bloque(str(b)) for b in bloques_e[:4])
            if len(bloques_e) > 4: _blq_str += "…"

            with st.expander(
                f"📄 {entry.get('nombre','?')} · {entry.get('fecha','?')} · {n_total_e} pregs",
                expanded=(i == 0)
            ):
                hc1, hc2, hc3 = st.columns([2, 2, 2])
                with hc1:
                    st.markdown(f"**Asig:** {entry.get('asig','—')}")
                    st.markdown(f"**Tipo:** {entry.get('tipo','—')}")
                    st.markdown(f"**Modelos:** {entry.get('n_modelos','—')}")
                    if entry.get("usuario"):
                        st.caption(f"👤 {entry['usuario']}")
                with hc2:
                    st.markdown("**Dificultad:**")
                    _dif_total = n_f + n_m + n_d or 1
                    _pct_f = round(n_f / _dif_total * 100)
                    _pct_m = round(n_m / _dif_total * 100)
                    _pct_d = round(n_d / _dif_total * 100)
                    st.markdown(
                        f"<div style='font-size:0.85em'>"
                        f"<span style='color:#27ae60'>⬤ Fácil: {n_f} ({_pct_f}%)</span> &nbsp; "
                        f"<span style='color:#f39c12'>⬤ Media: {n_m} ({_pct_m}%)</span> &nbsp; "
                        f"<span style='color:#c0392b'>⬤ Difícil: {n_d} ({_pct_d}%)</span>"
                        f"</div>"
                        f"<div style='display:flex;height:8px;border-radius:4px;overflow:hidden;margin-top:4px'>"
                        f"<div style='width:{_pct_f}%;background:#27ae60'></div>"
                        f"<div style='width:{_pct_m}%;background:#f39c12'></div>"
                        f"<div style='width:{_pct_d}%;background:#c0392b'></div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if _blq_str:
                        st.markdown(f"**Bloques:** {_blq_str}")
                with hc3:
                    st.markdown(f"**IDs ({n_total_e}):**")
                    st.caption(", ".join(ids[:8]) + ("…" if len(ids) > 8 else ""))

                _ha1, _ha2, _ha3 = st.columns(3)
                if _ha1.button("↩️ Recargar preguntas", key=f"hist_reload_{i}",
                               use_container_width=True, help="Restaura las preguntas en la pestaña Selección"):
                    valid = [pid for pid in ids if pid in df_total["ID_Pregunta"].values]
                    set_sel_ids(valid)
                    st.success(f"Recargadas {len(valid)} preguntas. Ve a la pestaña Selección.")
                    st.rerun()
                if exam_cfg_e and _ha2.button("↺ Restaurar configuración", key=f"hist_cfg_{i}",
                                               use_container_width=True,
                                               help="Recupera toda la configuración de exportación (institución, tipo, fecha, estilo…)"):
                    st.session_state.exam_cfg = dict(exam_cfg_e)
                    st.success("Configuración restaurada. Ve a la pestaña Exportar.")
                    st.rerun()
                if _ha3.button("↩️+↺ Ambos", key=f"hist_both_{i}",
                               use_container_width=True,
                               help="Restaura tanto las preguntas como la configuración"):
                    valid = [pid for pid in ids if pid in df_total["ID_Pregunta"].values]
                    set_sel_ids(valid)
                    if exam_cfg_e:
                        st.session_state.exam_cfg = dict(exam_cfg_e)
                    st.success(f"Restauradas {len(valid)} preguntas y configuración. Ve a Selección o Exportar.")
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
