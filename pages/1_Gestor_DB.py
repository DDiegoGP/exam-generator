"""
pages/1_Gestor_DB.py  –  Gestor de la Base de Datos de preguntas.

Pestañas:
  1. Añadir        – Formulario para nueva pregunta
  2. Importar      – Carga desde Word / Aiken con vista previa
  3. Gestionar     – Lista filtrable, editor individual, operaciones masivas
  4. Estadísticas  – Dashboard de cobertura y dificultad
"""
import streamlit as st
import streamlit.components.v1 as stcomponents
import pandas as pd
import datetime
import os
import re
import sys
import io
import json

# Asegurar que project_dir esté en path
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import examen_lib_latex as lib
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback, APP_CSS, page_header,
    connect_db, reload_db,
    bloques_disponibles, temas_de_bloque, temas_en_db,
    nombre_bloque, nombre_tema,
    es_uso_antiguo, render_question_card_html, mathjax_html, _nsort,
    sync_hoja_gsheets, sync_bloques_gsheets,
)

# ── Configuración ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gestor DB · Exámenes UCM", page_icon="🗄️", layout="wide")
init_session_state()
handle_oauth_callback()
st.markdown(APP_CSS, unsafe_allow_html=True)
render_sidebar()

# ── Dialog: editor de pregunta individual ─────────────────────────────────────
@st.dialog("✏️ Editar pregunta", width="large")
def _dialog_editar_pregunta(pid: str, row: dict):
    """Modal de edición de una pregunta. Llama a st.rerun() para cerrar."""
    bloques_list = st.session_state.bloques or []

    st.markdown(f"**ID:** `{pid}`")
    st.markdown("---")

    dc1, dc2 = st.columns([1, 2])

    with dc1:
        blq_idx = bloques_list.index(row["bloque"]) if row["bloque"] in bloques_list else 0
        ed_blq  = st.selectbox("Bloque", bloques_list, index=blq_idx, key="dlg_bloque")
        temas_d = temas_de_bloque(ed_blq) or [str(i) for i in range(1, 51)]
        # Intentar encontrar el tema actual
        tem_cur = str(row.get("Tema", "1"))
        tem_idx = temas_d.index(tem_cur) if tem_cur in temas_d else 0
        ed_tema = st.selectbox("Tema", temas_d, index=tem_idx, key="dlg_tema",
                               format_func=nombre_tema)

        dif_opts = ["Facil", "Media", "Dificil"]
        dif_cur  = str(row.get("dificultad", "Media")).capitalize()
        dif_idx  = dif_opts.index(dif_cur) if dif_cur in dif_opts else 1
        ed_dif   = st.selectbox("Dificultad", dif_opts, index=dif_idx, key="dlg_dif")

        corr_opts = ["A", "B", "C", "D"]
        corr_cur  = str(row.get("letra_correcta", "A")).upper()
        corr_idx  = corr_opts.index(corr_cur) if corr_cur in corr_opts else 0
        ed_corr   = st.selectbox("Respuesta correcta", corr_opts, index=corr_idx, key="dlg_corr")

        # Fecha de uso — checkbox + date_input
        import datetime as _dt
        _usada_raw = str(row.get("usada", "") or "").strip()
        _usada_val = None
        if _usada_raw and _usada_raw not in ('nan', 'NaT', 'None'):
            try: _usada_val = _dt.datetime.strptime(_usada_raw[:10], "%Y-%m-%d").date()
            except Exception: pass
        ed_tiene_fecha = st.checkbox("Pregunta ya usada", value=(_usada_val is not None), key="dlg_tiene_usada")
        if ed_tiene_fecha:
            ed_usada_date = st.date_input("Fecha de uso", value=_usada_val or _dt.date.today(), key="dlg_usada")
            ed_usada = ed_usada_date.strftime("%Y-%m-%d")
        else:
            ed_usada = ""
        ed_notas = st.text_area("Notas", value=str(row.get("notas", "") or ""),
                                 height=70, key="dlg_notas")

    with dc2:
        ed_enun = st.text_area("Enunciado", value=str(row.get("enunciado", "")),
                                height=120, key="dlg_enun")
        ops_orig = row.get("opciones_list", []) or ["", "", "", ""]
        ed_ops = []
        for li, ll in enumerate(["A", "B", "C", "D"]):
            v = ops_orig[li] if li < len(ops_orig) else ""
            ed_ops.append(st.text_input(f"Opción {ll}", value=v, key=f"dlg_op{ll}"))

    st.markdown("---")
    sc1, sc2, sc3 = st.columns([2, 2, 1])

    if sc1.button("💾 Guardar cambios", type="primary", use_container_width=True, key="dlg_save"):
        datos = {
            "bloque":     ed_blq,
            "tema":       ed_tema,
            "enunciado":  ed_enun.strip(),
            "opciones":   ed_ops,
            "correcta":   ed_corr,
            "dificultad": ed_dif,
            "usada":      ed_usada,
            "notas":      ed_notas.strip(),
        }
        ok, msg = lib.actualizar_pregunta_excel_local(
            st.session_state.excel_path,
            st.session_state.excel_dfs,
            pid, datos
        )
        if ok:
            _bloques_sync = list({datos["bloque"], row.get("bloque", datos["bloque"])})
            sync_bloques_gsheets(_bloques_sync)
            reload_db()
            st.rerun()
        else:
            st.error(f"❌ {msg}")

    if sc3.button("✖ Cancelar", use_container_width=True, key="dlg_cancel"):
        st.rerun()


@st.dialog("✏️ Editar pregunta importada", width="large")
def _dialog_editar_staging():
    """Modal completo para revisar/editar una pregunta del staging de importación."""
    idx      = st.session_state.get("_staging_edit_idx", 0)
    staging  = st.session_state.import_staging
    if not staging or idx >= len(staging):
        st.error("Pregunta no encontrada."); st.rerun(); return

    q = staging[idx]
    bloques_list = bloques_disponibles()

    st.markdown(f"**Pregunta {idx + 1} de {len(staging)}**")
    st.markdown("---")

    dc1, dc2 = st.columns([1, 2])
    with dc1:
        blq_idx = bloques_list.index(q.get("bloque", "")) if q.get("bloque", "") in bloques_list else 0
        ed_blq  = st.selectbox("Bloque", bloques_list, index=blq_idx, key="stg_dlg_bloque")
        temas_d = temas_de_bloque(ed_blq) or [str(i) for i in range(1, 51)]
        tem_cur = str(q.get("tema", "1"))
        tem_idx = temas_d.index(tem_cur) if tem_cur in temas_d else 0
        ed_tema = st.selectbox("Tema", temas_d, index=tem_idx, key="stg_dlg_tema",
                               format_func=nombre_tema)
        dif_opts = ["Facil", "Media", "Dificil"]
        dif_cur  = str(q.get("dificultad", "Media")).capitalize()
        dif_idx  = dif_opts.index(dif_cur) if dif_cur in dif_opts else 1
        ed_dif   = st.selectbox("Dificultad", dif_opts, index=dif_idx, key="stg_dlg_dif")
        corr_opts = ["A", "B", "C", "D"]
        corr_cur  = str(q.get("letra_correcta", "A")).upper()
        corr_idx  = corr_opts.index(corr_cur) if corr_cur in corr_opts else 0
        ed_corr   = st.radio("Respuesta correcta", corr_opts, index=corr_idx,
                             horizontal=True, key="stg_dlg_corr")

        import datetime as _dt
        _usada_raw = str(q.get("usada", "") or "").strip()
        _usada_val = None
        if _usada_raw and _usada_raw not in ('nan', 'NaT', 'None'):
            try: _usada_val = _dt.datetime.strptime(_usada_raw[:10], "%Y-%m-%d").date()
            except Exception: pass
        ed_tiene_fecha = st.checkbox("Pregunta ya usada", value=(_usada_val is not None), key="stg_dlg_tiene_usada")
        if ed_tiene_fecha:
            ed_usada_date = st.date_input("Fecha de uso", value=_usada_val or _dt.date.today(), key="stg_dlg_usada")
            ed_usada = ed_usada_date.strftime("%Y-%m-%d")
        else:
            ed_usada = ""

    with dc2:
        ed_enun  = st.text_area("Enunciado", value=str(q.get("enunciado", "")),
                                height=130, key="stg_dlg_enun")
        st.markdown("**Opciones** (la correcta marcada con ✓):")
        ops_orig = q.get("opciones_list", ["", "", "", ""])
        ed_ops   = []
        for li, ll in enumerate(["A", "B", "C", "D"]):
            v     = ops_orig[li] if li < len(ops_orig) else ""
            label = f"Opción {ll} ✓" if ll == ed_corr else f"Opción {ll}"
            ed_ops.append(st.text_input(label, value=v, key=f"stg_dlg_op{ll}"))

    warns = q.get("_warnings", [])
    if warns:
        st.warning("Avisos: " + " | ".join(warns))

    st.markdown("---")
    sc1, sc2 = st.columns(2)
    if sc1.button("💾 Guardar", type="primary", use_container_width=True, key="stg_dlg_save"):
        staging[idx] = {**q,
            "enunciado": ed_enun.strip(), "opciones_list": ed_ops,
            "letra_correcta": ed_corr, "bloque": ed_blq,
            "tema": ed_tema, "dificultad": ed_dif,
            "usada": ed_usada, "_warnings": [],
        }
        st.session_state.import_staging = staging
        st.session_state["_staging_edit_idx"] = None
        st.rerun()
    if sc2.button("✖ Cancelar", use_container_width=True, key="stg_dlg_cancel"):
        st.session_state["_staging_edit_idx"] = None
        st.rerun()


@st.dialog("📖 Solución desarrollada", width="large")
def _dialog_solucion(pid: str, row: dict):
    """Modal para ver y editar la solución desarrollada de una pregunta."""
    # ── Encabezado: enunciado prominente + metadatos ──────────────────────────
    dif     = str(row.get("dificultad", "Media"))
    dif_l   = dif.lower().replace("á","a").replace("í","i")
    dif_col = {"facil": "#27ae60", "media": "#f39c12", "dificil": "#c0392b"}.get(dif_l, "#888")
    corr    = str(row.get("letra_correcta", "A")).upper()
    corr_col= {"A": "#27ae60", "B": "#2980b9", "C": "#8e44ad", "D": "#c0392b"}.get(corr, "#555")
    ops     = row.get("opciones_list", []) or []

    st.markdown(
        f"<div style='background:#f0f4ff;border-left:4px solid #3498db;"
        f"border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:10px'>"
        f"<div style='font-size:0.75em;color:#666;margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<b style='color:#2c3e50'>{pid}</b>"
        f"<span style='background:{dif_col};color:#fff;border-radius:8px;"
        f"padding:1px 8px;font-size:0.9em'>{dif}</span>"
        f"<span style='background:{corr_col};color:#fff;border-radius:8px;"
        f"padding:1px 8px;font-size:0.9em'>Resp. correcta: {corr}</span></div>"
        f"<div style='font-size:1.0em;color:#1a252f;line-height:1.6;font-weight:500'>"
        f"{row.get('enunciado','')}</div></div>",
        unsafe_allow_html=True,
    )

    # Opciones en lectura compacta
    if any(ops):
        op_html = "<div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px'>"
        for i, ll in enumerate(["A", "B", "C", "D"]):
            txt  = ops[i] if i < len(ops) else ""
            is_c = ll == corr
            bg   = corr_col if is_c else "#f1f3f5"
            fg   = "#fff"    if is_c else "#495057"
            fw   = "600"     if is_c else "400"
            op_html += (
                f"<div style='background:{bg};color:{fg};border-radius:6px;"
                f"padding:4px 10px;font-size:0.82em;font-weight:{fw}'>"
                f"<b>{ll})</b> {txt}{' ✓' if is_c else ''}</div>"
            )
        op_html += "</div>"
        st.markdown(op_html, unsafe_allow_html=True)

    st.divider()

    # ── Plantillas de inicio ──────────────────────────────────────────────────
    _sol_key = f"dlg_sol_txt_{pid}"
    st.markdown("<span style='font-size:0.82em;color:#888;font-weight:600'>PLANTILLA RÁPIDA</span>",
                unsafe_allow_html=True)
    tp1, tp2, tp3 = st.columns(3)
    if tp1.button("📝 Razonamiento", key=f"tpl_razon_{pid}", use_container_width=True):
        st.session_state[_sol_key] = (
            f"La respuesta correcta es la **{corr})** porque...\n\n"
            f"Las otras opciones son incorrectas porque..."
        )
    if tp2.button("🔢 Cálculo", key=f"tpl_calc_{pid}", use_container_width=True):
        st.session_state[_sol_key] = (
            "**Datos:**\n\n\n\n"
            "**Desarrollo:**\n\n\n\n"
            "**Resultado:**"
        )
    if tp3.button("💡 Concepto", key=f"tpl_concept_{pid}", use_container_width=True):
        st.session_state[_sol_key] = (
            f"**Concepto clave:** ...\n\n"
            f"**Opción {corr})** es correcta porque...\n\n"
            f"**Las demás son incorrectas** porque..."
        )

    # ── Editor de solución ────────────────────────────────────────────────────
    sol_actual = str(row.get("solucion", "") or "").strip()
    nueva_sol  = st.text_area(
        "Solución — LaTeX: `$...$` inline · `$$...$$` o `\\[...\\]` bloque · TikZ renderiza al exportar PDF",
        value=sol_actual, height=180, key=_sol_key,
    )

    # Auto-habilitar render si ya hay solución guardada
    _mjax_sol_key = f"dlg_sol_mjax_{pid}"
    if sol_actual and _mjax_sol_key not in st.session_state:
        st.session_state[_mjax_sol_key] = True

    rc1, rc2 = st.columns(2)
    if rc1.button("∑ Renderizar LaTeX", use_container_width=True, key="dlg_sol_render"):
        st.session_state[_mjax_sol_key] = True
    if st.session_state.get(_mjax_sol_key) and rc2.button("✖ Cerrar render",
                                                            use_container_width=True,
                                                            key="dlg_sol_close_render"):
        st.session_state[_mjax_sol_key] = False

    if st.session_state.get(_mjax_sol_key, False):
        if nueva_sol.strip():
            sol_html = (
                "<div style='font-family:-apple-system,sans-serif;font-size:14px;"
                "color:#2c3e50;padding:14px;background:#f0f9ff;"
                "border-left:3px solid #3498db;border-radius:0 8px 8px 0;line-height:1.65'>"
                f"{nueva_sol}</div>"
            )
            stcomponents.html(mathjax_html(sol_html), height=280, scrolling=True)
        else:
            st.info("Escribe la solución para renderizarla.")

    st.divider()
    sg1, sg2 = st.columns([3, 1])
    if sg1.button("💾 Guardar solución", type="primary", use_container_width=True, key="dlg_sol_save"):
        datos = {
            "bloque":     row.get("bloque", ""),
            "enunciado":  row.get("enunciado", ""),
            "tema":       str(row.get("Tema", "1")),
            "correcta":   row.get("letra_correcta", "A"),
            "dificultad": row.get("dificultad", "Media"),
            "usada":      row.get("usada", ""),
            "notas":      row.get("notas", ""),
            "opciones":   row.get("opciones_list", []) or [],
            "solucion":   nueva_sol.strip(),
        }
        ok, msg = lib.actualizar_pregunta_excel_local(
            st.session_state.excel_path,
            st.session_state.excel_dfs,
            pid, datos,
        )
        if ok:
            sync_bloques_gsheets([datos["bloque"]])
            reload_db()
            st.success("✅ Solución guardada.")
            st.rerun()
        else:
            st.error(f"❌ {msg}")
    if sg2.button("✖ Cerrar", use_container_width=True, key="dlg_sol_cancel"):
        st.rerun()


st.title("🗄️ Gestor de Base de Datos")
st.caption(f"{len(st.session_state.df_preguntas)} preguntas · {len(st.session_state.bloques)} bloques"
           if st.session_state.db_connected else "Sin conexión a la base de datos")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos desde la barra lateral antes de continuar.")
    st.stop()

df_total: pd.DataFrame = st.session_state.df_preguntas
bloques = bloques_disponibles()

# Columnas estándar para crear un bloque nuevo desde cero
_STD_COLS = ["ID_Pregunta", "Tema", "Enunciado", "OpcionA", "OpcionB",
             "OpcionC", "OpcionD", "Correcta", "Usada en Examen", "Dificultad", "Notas", "Solución"]
_NUEVO_BLQ = "__nuevo__"


def _bloque_selectbox(label: str, key: str, col_widget=None) -> str:
    """Selectbox de bloque con opción 'Nuevo bloque...'. Devuelve el nombre final del bloque."""
    opts = bloques + [_NUEVO_BLQ]
    widget = col_widget or st
    sel = widget.selectbox(label, opts, key=key,
                           format_func=lambda b: "➕ Nuevo bloque..." if b == _NUEVO_BLQ else nombre_bloque(b))
    if sel == _NUEVO_BLQ:
        return (col_widget or st).text_input("Nombre del nuevo bloque", key=f"{key}_nuevo",
                                             placeholder="ej: Bloque I")
    return sel


def _asegurar_bloque(excel_dfs: dict, bloque: str) -> pd.DataFrame:
    """Si el bloque no existe o está vacío sin columnas, lo inicializa con columnas estándar."""
    existing = excel_dfs.get(bloque)
    if existing is None or len(existing.columns) == 0:
        excel_dfs[bloque] = pd.DataFrame(columns=_STD_COLS)
        st.session_state.bloques = [k for k in excel_dfs if k not in lib.CFG_SHEETS]
    return excel_dfs[bloque]


def _fill_row(blk_df: pd.DataFrame, p_data: dict, nid: str) -> dict:
    """Construye una fila nueva usando coincidencia por palabras clave + posicional seguro para opciones.

    p_data puede tener: enunciado, opciones_list, letra_correcta, tema (o Tema),
                        dificultad, usada, notas.
    El relleno posicional solo toca columnas NO reclamadas por la coincidencia de palabras clave,
    evitando así sobreescribir 'Usada en Examen' o 'Dificultad' si el GSheet tiene un orden distinto.
    """
    new_row = {col: "" for col in blk_df.columns}
    tema_val = p_data.get("tema") or p_data.get("Tema") or ""

    claimed: set[int] = set()
    for idx, col in enumerate(blk_df.columns):
        cl = str(col).strip().lower()
        if "id_preg" in cl or cl == "id":
            new_row[col] = nid
            claimed.add(idx)
        elif "tema" in cl and "id" not in cl:
            new_row[col] = str(tema_val)
            claimed.add(idx)
        elif "dificultad" in cl:
            new_row[col] = p_data.get("dificultad", "")
            claimed.add(idx)
        elif "correcta" in cl:
            new_row[col] = p_data.get("letra_correcta", "")
            claimed.add(idx)
        elif "enunciado" in cl:
            new_row[col] = p_data.get("enunciado", "")
            claimed.add(idx)
        elif "usada" in cl or "fecha" in cl:
            new_row[col] = p_data.get("usada", "")
            claimed.add(idx)
        elif "soluci" in cl:
            new_row[col] = p_data.get("solucion", "")
            claimed.add(idx)
        elif "nota" in cl:
            new_row[col] = p_data.get("notas", "")
            claimed.add(idx)

    # Opciones: relleno posicional SOLO en columnas no reclamadas, justo después de Enunciado
    enun_idx = next((i for i, c in enumerate(blk_df.columns)
                     if "enunciado" in str(c).lower()), None)
    if enun_idx is not None:
        opts = list(p_data.get("opciones_list", []))
        op_n = 0
        for j in range(1, len(blk_df.columns)):
            if op_n >= 4:
                break
            ci = enun_idx + j
            if ci >= len(blk_df.columns):
                break
            if ci not in claimed:
                new_row[blk_df.columns[ci]] = opts[op_n] if op_n < len(opts) else ""
                op_n += 1
    return new_row


# ═════════════════════════════════════════════════════════════════════════════
# PESTAÑA PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════
tab_add, tab_imp, tab_man, tab_stat, tab_sol = st.tabs(
    ["➕ Añadir", "📥 Importar", "✏️ Gestionar", "📊 Estadísticas", "📖 Soluciones"]
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 · AÑADIR
# ─────────────────────────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Añadir nueva pregunta")

    col_cfg, col_form = st.columns([1, 2])

    with col_cfg:
        bloque_add = _bloque_selectbox("Bloque", "add_bloque")
        tema_add   = st.selectbox("Tema", temas_de_bloque(bloque_add) or [str(i) for i in range(1, 51)], key="add_tema",
                                   format_func=nombre_tema)
        dif_add    = st.selectbox("Dificultad", ["Facil", "Media", "Dificil"], index=1, key="add_dif")
        corr_add   = st.selectbox("Respuesta correcta", ["A", "B", "C", "D"], key="add_corr")

    with col_form:
        enun_add = st.text_area("Enunciado", height=100, key="add_enun",
                                placeholder="Escribe el enunciado de la pregunta...")
        st.markdown("**Opciones:**")
        ops_add = []
        for l in ["A", "B", "C", "D"]:
            ops_add.append(
                st.text_input(f"Opción {l}", key=f"add_op{l}",
                              placeholder=f"Texto de la opción {l}")
            )

    if st.button("💾 Guardar pregunta", type="primary", key="btn_guardar_add"):
        p = {
            "enunciado": enun_add.strip(),
            "opciones_list": ops_add,
            "letra_correcta": corr_add,
        }
        ok_v, warns = lib.validar_pregunta(p)
        if warns:
            for w in warns:
                st.warning(f"⚠️ {w}")

        if enun_add.strip():
            # Comprobar duplicados
            is_dup, sim = lib.check_for_similar_enunciado(enun_add.strip(), df_total)
            if is_dup:
                st.error(f"❌ Pregunta muy similar ya existe en la base de datos (similitud {sim:.0%}). Descartada.")
            else:
                nid, _ = lib.generar_siguiente_id(df_total, bloque_add, tema_add)
                excel_path = st.session_state.excel_path
                excel_dfs  = st.session_state.excel_dfs
                blk_df     = _asegurar_bloque(excel_dfs, bloque_add)

                new_row = _fill_row(blk_df, {
                    "tema": tema_add, "dificultad": dif_add,
                    "letra_correcta": corr_add, "enunciado": enun_add.strip(),
                    "opciones_list": ops_add, "usada": "", "notas": "",
                }, nid)
                excel_dfs[bloque_add] = pd.concat(
                    [blk_df, pd.DataFrame([new_row])], ignore_index=True
                )
                lib.guardar_excel_local(excel_path, excel_dfs)
                st.success(f"✅ Pregunta guardada con ID: **{nid}**")
                sync_bloques_gsheets([bloque_add])
                reload_db()
                st.rerun()
        else:
            st.error("❌ El enunciado no puede estar vacío.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 · IMPORTAR
# ─────────────────────────────────────────────────────────────────────────────
with tab_imp:
    st.subheader("Importar preguntas")

    # ── Configuración ─────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    bloque_imp = _bloque_selectbox("Bloque destino", "imp_bloque", c1)
    tema_imp   = c2.selectbox("Tema", temas_de_bloque(bloque_imp) or [str(i) for i in range(1, 51)], key="imp_tema",
                               format_func=nombre_tema)
    dif_imp    = c3.selectbox("Dificultad", ["Facil", "Media", "Dificil"], index=1, key="imp_dif")
    fmt_imp    = c4.selectbox("Formato", ["Word (.docx)", "PDF (.pdf)", "Aiken (.txt)"], key="imp_fmt")

    es_word = "Word" in fmt_imp
    es_pdf  = "PDF"  in fmt_imp
    if es_word or es_pdf:
        marca_imp = st.selectbox(
            "¿Cómo está marcada la respuesta correcta?",
            lib.MARCAS_CORRECTA_WORD, index=0, key="imp_marca",
            help="Negrita · Resaltado · Color · Subrayado · Asterisco · MAYÚSCULAS · Siempre la primera"
        )
    else:
        marca_imp = "Negrita"  # Aiken usa ANSWER:

    ext_map = {"Word (.docx)": "docx", "PDF (.pdf)": "pdf", "Aiken (.txt)": "txt"}
    accept  = ext_map.get(fmt_imp, "txt")
    up_file = st.file_uploader("Subir archivo", type=[accept], key="imp_uploader")

    if st.button("👁️ Previsualizar", key="btn_preview_imp") and up_file is not None:
        try:
            if es_word:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tf:
                    tf.write(up_file.read()); tmp_path = tf.name
                preguntas = lib.procesar_archivo_docx(tmp_path, bloque_imp, tema_imp, dif_imp, marca_imp)
                os.unlink(tmp_path)
            elif es_pdf:
                preguntas = lib.parse_pdf_bytes(up_file.read(), bloque_imp, tema_imp, dif_imp, marca_imp)
            else:
                text = up_file.read().decode("utf-8", errors="replace")
                preguntas = lib.parse_aiken(text, bloque_imp, tema_imp, dif_imp)
            st.session_state.import_staging = preguntas
            st.session_state["_staging_edit_idx"] = None
            # Inicializar todas las selecciones a True
            for i in range(len(preguntas)):
                st.session_state[f"stg_sel_{i}"] = True
            st.success(f"Detectadas **{len(preguntas)}** preguntas. Revisa, edita si es necesario e importa.")
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")

    # ── Lista de staging ──────────────────────────────────────────────────────
    staging = st.session_state.get("import_staging", [])
    if staging:
        # Botones de selección masiva
        ba, bd = st.columns(2)
        if ba.button("☑ Seleccionar todas", key="stg_sel_all", use_container_width=True):
            for i in range(len(staging)):
                st.session_state[f"stg_sel_{i}"] = True
            st.rerun()
        if bd.button("☐ Deseleccionar todas", key="stg_desel_all", use_container_width=True):
            for i in range(len(staging)):
                st.session_state[f"stg_sel_{i}"] = False
            st.rerun()

        # Inyectar CSS para apretar el espacio entre filas de la lista
        st.markdown("""<style>
div[data-testid="stHorizontalBlock"] > div { padding-top:2px!important; padding-bottom:2px!important; }
div[data-testid="stCheckbox"] { margin-top:4px!important; }
</style>""", unsafe_allow_html=True)

        # Cabecera
        h0, h2, h3, h4 = st.columns([0.5, 8, 0.8, 0.7])
        h0.markdown("<span style='font-size:0.8em;color:#888'>✓</span>", unsafe_allow_html=True)
        h2.markdown("<span style='font-size:0.8em;color:#888'>Enunciado</span>", unsafe_allow_html=True)
        h3.markdown("<span style='font-size:0.8em;color:#888'>Resp.</span>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

        _BADGE = {"A": "#27ae60", "B": "#2980b9", "C": "#8e44ad", "D": "#c0392b"}
        for i, q in enumerate(staging):
            c_sel, c_enun, c_resp, c_edit = st.columns([0.5, 8, 0.8, 0.7])

            c_sel.checkbox("", value=st.session_state.get(f"stg_sel_{i}", True),
                           key=f"stg_sel_{i}", label_visibility="collapsed")

            warns      = q.get("_warnings", [])
            warn_icon  = " <span style='color:#e67e22'>⚠</span>" if warns else ""
            enun_short = q["enunciado"][:85] + ("…" if len(q["enunciado"]) > 85 else "")
            c_enun.markdown(
                f"<span style='font-size:0.85em;line-height:1.3'>"
                f"<b style='color:#999;font-size:0.8em'>{i+1}.</b> {enun_short}{warn_icon}</span>",
                unsafe_allow_html=True
            )

            col = _BADGE.get(q["letra_correcta"], "#555")
            c_resp.markdown(
                f"<span style='background:{col};color:#fff;padding:1px 7px;"
                f"border-radius:10px;font-size:0.82em;font-weight:bold'>{q['letra_correcta']}</span>",
                unsafe_allow_html=True
            )

            if c_edit.button("✏️", key=f"stg_edit_{i}", help="Ver / editar pregunta completa"):
                st.session_state["_staging_edit_idx"] = i
                _dialog_editar_staging()

        st.divider()

        # Abre el dialog si hubo rerun con _staging_edit_idx pendiente
        if st.session_state.get("_staging_edit_idx") is not None:
            _dialog_editar_staging()

        sel_ids   = [i for i in range(len(staging)) if st.session_state.get(f"stg_sel_{i}", True)]
        sel_count = len(sel_ids)
        st.caption(f"Seleccionadas: **{sel_count}** de {len(staging)}")

        c_imp, c_clr = st.columns([3, 1])
        if c_imp.button(f"📥 Importar seleccionadas ({sel_count})", type="primary",
                        key="btn_imp_sel", disabled=(sel_count == 0)):
            imported = 0; skipped = 0
            excel_path = st.session_state.excel_path
            excel_dfs  = st.session_state.excel_dfs

            for i in sel_ids:
                p_data = {
                    "enunciado":      staging[i]["enunciado"],
                    "opciones_list":  staging[i]["opciones_list"],
                    "letra_correcta": staging[i]["letra_correcta"],
                    "bloque":         staging[i].get("bloque", bloque_imp),
                    "tema":           str(staging[i].get("tema", tema_imp)),
                    "dificultad":     staging[i].get("dificultad", dif_imp),
                    "usada":          staging[i].get("usada", ""),
                }
                is_dup, _ = lib.check_for_similar_enunciado(p_data["enunciado"], df_total)
                if is_dup: skipped += 1; continue
                blk    = p_data["bloque"]
                blk_df = _asegurar_bloque(excel_dfs, blk)
                nid, _ = lib.generar_siguiente_id(df_total, blk, p_data["tema"])
                new_row = _fill_row(blk_df, p_data, nid)
                excel_dfs[blk] = pd.concat([blk_df, pd.DataFrame([new_row])], ignore_index=True)
                df_total = pd.concat([df_total, pd.DataFrame([{
                    "ID_Pregunta": nid, "bloque": blk, "Tema": p_data["tema"],
                    "enunciado": p_data["enunciado"], "opciones_list": p_data["opciones_list"],
                    "letra_correcta": p_data["letra_correcta"], "dificultad": p_data["dificultad"],
                    "usada": "", "notas": "",
                }])], ignore_index=True)
                imported += 1

            if imported:
                lib.guardar_excel_local(excel_path, excel_dfs)
                st.success(f"✅ {imported} pregunta(s) importada(s). {skipped} duplicada(s) omitida(s).")
                st.session_state.import_staging = []
                _bloques_imp = list({staging[i].get("bloque", bloque_imp) for i in sel_ids})
                sync_bloques_gsheets(_bloques_imp)
                reload_db()
                st.rerun()
            else:
                st.warning(f"No se importó ninguna pregunta. {skipped} duplicada(s) omitida(s).")

        if c_clr.button("🗑️ Limpiar", key="btn_clear_staging"):
            st.session_state.import_staging = []
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 · GESTIONAR
# ─────────────────────────────────────────────────────────────────────────────
with tab_man:
    st.subheader("Gestionar preguntas")

    # ── Filtros ──────────────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4, fc5 = st.columns([2, 2, 1.5, 2, 0.7])

    f_bloque = fc1.selectbox(
        "Bloque", ["Todos"] + bloques, key="man_f_bloque",
        format_func=lambda b: "Todos" if b == "Todos" else nombre_bloque(b),
    )

    # Reset tema si cambia el bloque
    _prev_blq = st.session_state.get("_man_prev_bloque", f_bloque)
    if _prev_blq != f_bloque:
        st.session_state["man_f_tema"] = "Todos"
    st.session_state["_man_prev_bloque"] = f_bloque

    # Temas que REALMENTE existen en la DB (sin añadir 1-50)
    temas_disponibles = temas_en_db(f_bloque)
    # Asegurar que el valor guardado en session_state sea válido
    _t_cur = st.session_state.get("man_f_tema", "Todos")
    if _t_cur != "Todos" and _t_cur not in temas_disponibles:
        st.session_state["man_f_tema"] = "Todos"

    f_tema = fc2.selectbox(
        "Tema", ["Todos"] + temas_disponibles, key="man_f_tema",
        format_func=lambda t: "Todos" if t == "Todos" else nombre_tema(t),
    )
    f_dif  = fc3.selectbox("Dificultad", ["Todas", "Facil", "Media", "Dificil"], key="man_f_dif")
    f_uso  = fc4.selectbox(
        "Uso", ["Todos", "Nunca usada", "Usada", "Usada >6m", "Usada >12m"], key="man_f_uso",
    )
    # Botón limpiar filtros
    fc5.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    if fc5.button("🔄", key="btn_clear_filters", help="Limpiar todos los filtros"):
        for k in ("man_f_bloque", "man_f_tema", "man_f_dif", "man_f_uso",
                  "man_search", "man_search_global", "man_filter_sin_sol"):
            st.session_state.pop(k, None)
        st.rerun()

    srch1, srch2, srch3 = st.columns([4, 1.2, 1])
    f_search  = srch1.text_input("🔍 Buscar", placeholder="Enunciado, opciones, notas…", key="man_search")
    f_global  = srch2.checkbox("🌐 Todos los bloques", key="man_search_global", value=False,
                                help="Buscar ignorando el filtro de bloque")
    f_sin_sol = srch3.checkbox("Sin solución", key="man_filter_sin_sol", value=False)

    # ── Aplicar filtros ───────────────────────────────────────────────────────
    df_filt = df_total.copy()
    if f_bloque != "Todos" and not f_global:
        df_filt = df_filt[df_filt["bloque"] == f_bloque]
    if f_tema != "Todos":
        df_filt = df_filt[df_filt["Tema"].astype(str) == f_tema]
    if f_dif != "Todas":
        df_filt = df_filt[df_filt["dificultad"].str.lower() == f_dif.lower()]
    if f_uso == "Nunca usada":
        df_filt = df_filt[df_filt["usada"] == ""]
    elif f_uso == "Usada":
        df_filt = df_filt[df_filt["usada"] != ""]
    elif f_uso == "Usada >6m":
        df_filt = df_filt[df_filt["usada"].apply(lambda v: es_uso_antiguo(v, 6))]
    elif f_uso == "Usada >12m":
        df_filt = df_filt[df_filt["usada"].apply(lambda v: es_uso_antiguo(v, 12))]
    if f_sin_sol:
        df_filt = df_filt[~df_filt["solucion"].apply(
            lambda v: bool(str(v).strip() and str(v) not in ('nan', 'None', '')))]
    if f_search:
        sq = f_search.lower()
        mask = df_filt["enunciado"].str.lower().str.contains(sq, na=False)
        mask = mask | df_filt["notas"].astype(str).str.lower().str.contains(sq, na=False)
        mask = mask | df_filt["opciones_list"].apply(
            lambda ops: any(sq in str(o).lower() for o in (ops or [])))
        df_filt = df_filt[mask]

    # Contador + badge global search
    n_filt   = len(df_filt)
    pct_filt = int(n_filt / len(df_total) * 100) if len(df_total) else 0
    _gbadge  = (
        "  ·  <span style='background:#dbeafe;color:#1e40af;border-radius:8px;"
        "padding:1px 8px;font-size:0.9em;font-weight:600'>🌐 búsqueda global</span>"
        if f_global and f_search else ""
    )
    st.markdown(
        f"<div style='font-size:0.82em;color:#666;margin-bottom:6px'>"
        f"Mostrando <b style='color:#2c3e50'>{n_filt}</b> de {len(df_total)} preguntas"
        f"{'  ·  <b style=\"color:#3498db\">' + str(pct_filt) + '%</b>' if pct_filt < 100 else ''}"
        f"{_gbadge}</div>",
        unsafe_allow_html=True,
    )

    # ── Layout 2 columnas: tabla + panel derecho ──────────────────────────────
    if df_filt.empty:
        st.info("No hay preguntas que coincidan con los filtros.")
    else:
        col_table, col_preview = st.columns([3, 2], gap="medium")

        with col_table:
            display_df = df_filt[["ID_Pregunta", "bloque", "Tema", "dificultad",
                                   "usada", "solucion", "enunciado"]].copy()
            display_df["enunciado"] = display_df["enunciado"].str[:120]
            display_df["usada"]     = display_df["usada"].apply(lambda v: v or "—")
            display_df["bloque"]    = display_df["bloque"].apply(nombre_bloque)
            display_df["solucion"]  = display_df["solucion"].apply(
                lambda v: "✓" if str(v).strip() and str(v) not in ('nan','None','') else "—")
            display_df.columns = ["ID", "Bloque", "T", "Dif.", "Usado", "Sol.", "Enunciado"]
            display_df = display_df.reset_index(drop=True)

            sel = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                selection_mode="multi-row",
                on_select="rerun",
                key="man_df_sel",
                height=420,
                column_config={
                    "ID":        st.column_config.TextColumn("ID", width=115),
                    "Bloque":    st.column_config.TextColumn("Bloque", width=115),
                    "T":         st.column_config.TextColumn("T", width=32),
                    "Dif.":      st.column_config.TextColumn("Dif.", width=55),
                    "Usado":     st.column_config.TextColumn("Usado", width=80),
                    "Sol.":      st.column_config.TextColumn("Sol.", width=40),
                    "Enunciado": st.column_config.TextColumn("Enunciado", width="large"),
                },
            )

            sel_rows = sel.selection.rows if sel.selection else []
            n_sel    = len(sel_rows)
            sel_pid  = (df_filt.iloc[sel_rows[0]]["ID_Pregunta"]
                        if n_sel == 1 else None)
            sel_pids_multi = ([df_filt.iloc[r]["ID_Pregunta"] for r in sel_rows]
                              if n_sel > 1 else [])

            # ── Operaciones masivas (solo texto/dificultad, no borrado) ────────
            with st.expander(f"⚙️ Operaciones sobre las {n_filt} preguntas filtradas",
                             expanded=False):
                bulk_ids = df_filt["ID_Pregunta"].tolist()
                st.caption(
                    f"Afectan a **todas las preguntas visibles** según los filtros "
                    f"({n_filt}). Usa los filtros para acotar antes de aplicar."
                )
                bt1, bt2 = st.tabs(["Cambiar Tema / Dificultad", "Buscar y reemplazar"])
                with bt1:
                    bc1, bc2 = st.columns(2)
                    bulk_tema = bc1.text_input("Nuevo tema (vacío = no cambiar)", key="bulk_tema")
                    bulk_dif  = bc2.selectbox("Nueva dificultad",
                                              ["(no cambiar)", "Facil", "Media", "Dificil"],
                                              key="bulk_dif")
                    if st.button(f"✅ Aplicar a {n_filt} preguntas", key="btn_bulk_apply"):
                        msgs = []
                        if bulk_tema.strip():
                            ok, m = lib.actualizar_campo_masivo(
                                st.session_state.excel_path, st.session_state.excel_dfs,
                                bulk_ids, "tema", bulk_tema.strip())
                            msgs.append(m)
                        if bulk_dif != "(no cambiar)":
                            ok, m = lib.actualizar_campo_masivo(
                                st.session_state.excel_path, st.session_state.excel_dfs,
                                bulk_ids, "dificultad", bulk_dif)
                            msgs.append(m)
                        if msgs:
                            sync_bloques_gsheets(list(
                                df_total[df_total["ID_Pregunta"].isin(bulk_ids)]["bloque"].unique()))
                            st.success(" | ".join(msgs)); reload_db(); st.rerun()
                        else:
                            st.warning("No hay cambios que aplicar.")
                with bt2:
                    fr1, fr2 = st.columns(2)
                    bulk_find = fr1.text_input("Buscar en enunciado", key="bulk_find")
                    bulk_repl = fr2.text_input("Reemplazar por", key="bulk_repl")
                    if st.button(f"🔄 Reemplazar en {n_filt} preguntas", key="btn_bulk_repl"):
                        if not bulk_find.strip():
                            st.warning("Escribe el texto a buscar.")
                        else:
                            ok, msg = lib.reemplazar_texto_masivo(
                                st.session_state.excel_path, st.session_state.excel_dfs,
                                bulk_ids, bulk_find, bulk_repl)
                            if ok:
                                sync_bloques_gsheets(list(
                                    df_total[df_total["ID_Pregunta"].isin(bulk_ids)]["bloque"].unique()))
                                st.success(msg); reload_db(); st.rerun()
                            else:
                                st.error(msg)

        # ── Panel derecho: preview (1 fila) o acción multi (N filas) ─────────
        with col_preview:

            # ══ MULTI-SELECT: N > 1 ══════════════════════════════════════════
            if n_sel > 1:
                st.markdown(
                    f"<div style='background:#fff3cd;border-left:4px solid #f39c12;"
                    f"border-radius:0 8px 8px 0;padding:14px 18px;margin-bottom:12px'>"
                    f"<div style='font-size:1.05em;font-weight:700;color:#856404'>"
                    f"📋 {n_sel} preguntas seleccionadas</div>"
                    f"<div style='font-size:0.82em;color:#78350f;margin-top:4px'>"
                    f"IDs: {', '.join(sel_pids_multi[:6])}"
                    f"{'…' if len(sel_pids_multi) > 6 else ''}</div></div>",
                    unsafe_allow_html=True,
                )
                _del_confirm = st.checkbox(
                    f"Confirmo que quiero eliminar estas {n_sel} preguntas",
                    key="multi_del_confirm",
                )
                if st.button(
                    f"🗑️ Eliminar {n_sel} seleccionadas",
                    type="primary",
                    disabled=not _del_confirm,
                    use_container_width=True,
                    key="btn_multi_del",
                ):
                    ok, msg = lib.eliminar_preguntas_excel_local(
                        st.session_state.excel_path,
                        st.session_state.excel_dfs,
                        sel_pids_multi,
                    )
                    if ok:
                        sync_bloques_gsheets(list(
                            df_total[df_total["ID_Pregunta"].isin(sel_pids_multi)]["bloque"].unique()))
                        st.success(msg); reload_db(); st.rerun()
                    else:
                        st.error(msg)

            # ══ SINGLE-SELECT: preview completo ══════════════════════════════
            elif sel_pid:
                row_d     = dict(df_total[df_total["ID_Pregunta"] == sel_pid].iloc[0])
                card_html = render_question_card_html(row_d, show_sol=True, include_notas=False)
                sol_txt   = str(row_d.get("solucion", "") or "").strip()
                notas_txt = str(row_d.get("notas",    "") or "").strip()
                notas_html = ""

                # Tarjeta principal
                st.markdown(card_html, unsafe_allow_html=True)

                # Notas
                if notas_txt:
                    notas_html = (
                        "<div style='background:#fefce8;border-left:3px solid #f59e0b;"
                        "border-radius:0 8px 8px 0;padding:8px 14px;margin-top:4px;"
                        "font-size:0.875em;color:#78350f;line-height:1.5'>"
                        "<b style='color:#92400e'>📝 Notas:</b> "
                        f"{notas_txt}</div>"
                    )
                    st.markdown(notas_html, unsafe_allow_html=True)

                # Solución expandible
                if sol_txt:
                    with st.expander("📖 Ver solución", expanded=False):
                        _sol_prev_html = (
                            "<div style='font-size:13px;color:#2c3e50;padding:10px;"
                            "background:#f0f9ff;border-left:3px solid #3498db;"
                            "border-radius:0 6px 6px 0;line-height:1.6'>"
                            f"{sol_txt}</div>"
                        )
                        _mjax_exp = f"mjax_exp_{sel_pid}"
                        if st.session_state.get(_mjax_exp, False):
                            stcomponents.html(mathjax_html(_sol_prev_html), height=200, scrolling=True)
                        else:
                            st.markdown(_sol_prev_html, unsafe_allow_html=True)
                        if st.button("∑ Renderizar LaTeX", key=f"mjax_exp_btn_{sel_pid}",
                                     use_container_width=True):
                            st.session_state[_mjax_exp] = not st.session_state.get(_mjax_exp, False)
                            st.rerun()

                # ── Render LaTeX global (tarjeta + notas) ─────────────────
                _mjax_key = f"mjax_gest_{sel_pid}"
                _rend_on  = st.session_state.get(_mjax_key, False)
                if st.button(
                    "✖ Cerrar LaTeX" if _rend_on else "∑ Renderizar LaTeX",
                    key=f"mjax_btn_{sel_pid}",
                    use_container_width=True,
                ):
                    st.session_state[_mjax_key] = not _rend_on
                    st.rerun()
                if _rend_on:
                    stcomponents.html(
                        mathjax_html(card_html + notas_html),
                        height=480, scrolling=True,
                    )

                st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)

                # ── Botones de acción: 4 en una fila ──────────────────────
                ba1, ba2, ba3, ba4 = st.columns(4)
                if ba1.button("✏️ Editar", type="primary", use_container_width=True,
                              key="btn_edit_q"):
                    _dialog_editar_pregunta(sel_pid, row_d)
                if ba2.button("📖 Solución", use_container_width=True, key="btn_sol_q",
                              help="Sin solución aún" if not sol_txt else "Ver / editar solución"):
                    _dialog_solucion(sel_pid, row_d)
                if ba3.button("📋 Duplicar", use_container_width=True, key="btn_dup_q"):
                    blk    = row_d["bloque"]
                    tema_d = str(row_d.get("Tema", "1"))
                    nid, _ = lib.generar_siguiente_id(df_total, blk, tema_d)
                    blk_df = st.session_state.excel_dfs.get(blk)
                    if blk_df is not None:
                        new_row_dup = _fill_row(blk_df, {
                            "tema": tema_d,
                            "dificultad": row_d.get("dificultad", "Media"),
                            "letra_correcta": row_d.get("letra_correcta", "A"),
                            "enunciado": str(row_d.get("enunciado", "")) + " (COPIA)",
                            "opciones_list": row_d.get("opciones_list", []) or [],
                            "usada": "",
                            "notas": row_d.get("notas", "") or "",
                            "solucion": "",
                        }, nid)
                        st.session_state.excel_dfs[blk] = pd.concat(
                            [blk_df, pd.DataFrame([new_row_dup])], ignore_index=True)
                        lib.guardar_excel_local(st.session_state.excel_path,
                                                st.session_state.excel_dfs)
                        st.success(f"✅ Duplicada como **{nid}**")
                        sync_bloques_gsheets([blk]); reload_db(); st.rerun()

                # Borrar con confirmación inline
                _del_key = f"del_confirm_{sel_pid}"
                if ba4.button("🗑️ Borrar", use_container_width=True, key="btn_del_q"):
                    st.session_state[_del_key] = not st.session_state.get(_del_key, False)
                if st.session_state.get(_del_key, False):
                    st.warning(f"¿Eliminar **{sel_pid}** de forma permanente?")
                    cd1, cd2 = st.columns(2)
                    if cd1.button("✅ Sí, eliminar", type="primary",
                                  use_container_width=True, key="btn_del_confirm"):
                        ok, msg = lib.eliminar_preguntas_excel_local(
                            st.session_state.excel_path,
                            st.session_state.excel_dfs,
                            [sel_pid],
                        )
                        if ok:
                            sync_bloques_gsheets([row_d["bloque"]])
                            st.session_state.pop(_del_key, None)
                            reload_db(); st.rerun()
                        else:
                            st.error(msg)
                    if cd2.button("✖ Cancelar", use_container_width=True, key="btn_del_cancel"):
                        st.session_state.pop(_del_key, None)
                        st.rerun()

            # ══ NADA SELECCIONADO ═════════════════════════════════════════════
            else:
                st.markdown(
                    "<div style='text-align:center;padding:40px 20px;color:#888;"
                    "border:2px dashed #dee2e6;border-radius:10px;margin-top:10px'>"
                    "<div style='font-size:2em;margin-bottom:8px'>👆</div>"
                    "<div style='font-weight:600'>Haz clic en una fila para previsualizarla</div>"
                    "<div style='font-size:0.85em;margin-top:4px'>"
                    "Selecciona varias filas para borrarlas en grupo</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

    # ── Export/Import JSON ───────────────────────────────────────────────────
    sel_ids_for_json = [sel_pid] if sel_pid else []
    with st.expander("📤 Exportar / Importar JSON (entre bases de datos)"):
        jc1, jc2 = st.columns(2)

        with jc1:
            st.markdown("**Exportar preguntas filtradas a JSON**")
            ids_to_export = df_filt["ID_Pregunta"].tolist() if not df_filt.empty else []
            if ids_to_export:
                n_exp = st.number_input(f"Se exportarán {len(ids_to_export)} preguntas filtradas", value=len(ids_to_export), disabled=True)
                if st.button("📤 Exportar a JSON", key="btn_exp_json"):
                    import tempfile
                    out_path = os.path.join(PROJECT_DIR, f"export_{datetime.date.today()}.json")
                    n = lib.exportar_preguntas_json(ids_to_export, df_total, out_path)
                    with open(out_path, "rb") as f:
                        st.download_button("⬇️ Descargar JSON", f.read(), file_name=os.path.basename(out_path),
                                           mime="application/json", key="dl_json")
                    st.success(f"{n} preguntas exportadas.")
            else:
                st.caption("Aplica filtros para seleccionar preguntas a exportar.")

        with jc2:
            st.markdown("**Importar desde JSON**")
            bloque_json = _bloque_selectbox("Bloque destino", "json_bloque")
            json_file   = st.file_uploader("Archivo JSON", type=["json"], key="json_uploader")
            if json_file and st.button("📥 Importar JSON", key="btn_imp_json"):
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tf:
                    tf.write(json_file.read())
                    tmp_json = tf.name
                nuevas, dupes = lib.importar_preguntas_json(tmp_json, bloque_json, df_total)
                os.unlink(tmp_json)
                if nuevas:
                    blk_df = _asegurar_bloque(st.session_state.excel_dfs, bloque_json)
                    for p in nuevas:
                        new_row = _fill_row(blk_df, {
                            "tema": p.get("Tema") or p.get("tema", "1"),
                            "dificultad": p.get("dificultad", "Media"),
                            "letra_correcta": p.get("letra_correcta", "A"),
                            "enunciado": p.get("enunciado", ""),
                            "opciones_list": p.get("opciones_list", []),
                            "usada": p.get("usada", ""),
                            "notas": p.get("notas", "") or "",
                        }, p["ID_Pregunta"])
                        blk_df = pd.concat([blk_df, pd.DataFrame([new_row])], ignore_index=True)
                    st.session_state.excel_dfs[bloque_json] = blk_df
                    lib.guardar_excel_local(st.session_state.excel_path, st.session_state.excel_dfs)
                    st.success(f"✅ {len(nuevas)} importadas, {dupes} duplicadas omitidas.")
                    sync_bloques_gsheets([bloque_json])
                    reload_db()
                    st.rerun()
                else:
                    st.warning(f"No se importó ninguna pregunta nueva. {dupes} duplicadas omitidas.")

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 · ESTADÍSTICAS
# ─────────────────────────────────────────────────────────────────────────────
with tab_stat:
    df = df_total
    if df.empty:
        st.info("Sin datos para mostrar.")
    else:
        total   = len(df)
        nunca   = int((df["usada"] == "").sum())
        usadas  = total - nunca
        pct_uso = int(usadas / total * 100) if total else 0

        # ── Tarjetas de métricas globales ─────────────────────────────────────
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.markdown(
            f"<div class='stat-card'><div class='stat-num'>{total}</div>"
            f"<div class='stat-label'>📚 Total preguntas</div></div>",
            unsafe_allow_html=True)
        mc2.markdown(
            f"<div class='stat-card ok'><div class='stat-num' style='color:#27ae60'>{usadas}</div>"
            f"<div class='stat-label'>✅ Usadas alguna vez</div></div>",
            unsafe_allow_html=True)
        mc3.markdown(
            f"<div class='stat-card warn'><div class='stat-num' style='color:#f39c12'>{nunca}</div>"
            f"<div class='stat-label'>🆕 Sin usar</div></div>",
            unsafe_allow_html=True)
        mc4.markdown(
            f"<div class='stat-card'><div class='stat-num'>{len(bloques)}</div>"
            f"<div class='stat-label'>📦 Bloques</div></div>",
            unsafe_allow_html=True)
        mc5.markdown(
            f"<div class='stat-card used'><div class='stat-num' style='color:#8e44ad'>{pct_uso}%</div>"
            f"<div class='stat-label'>🎯 % Cobertura</div></div>",
            unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Selector de vista ─────────────────────────────────────────────────
        vista_opts = ["📊 Resumen global"] + bloques
        sv1, sv2 = st.columns([3, 6])
        vista = sv1.selectbox("🔍 Ver detalle:", vista_opts, key="stat_vista",
                               label_visibility="collapsed",
                               format_func=lambda b: b if b == "📊 Resumen global" else f"📦 {nombre_bloque(b)}")

        st.markdown("---")

        # ══════════════════════════════════════════════════════════════════════
        if vista == "📊 Resumen global":
        # ══════════════════════════════════════════════════════════════════════
            st.markdown("#### 📊 Distribución por bloque y dificultad")

            blq_stats = []
            for blq in bloques:
                dfb    = df[df["bloque"] == blq]
                n_tot  = len(dfb)
                n_f    = int((dfb["dificultad"].str.lower() == "facil").sum())
                n_m    = int((dfb["dificultad"].str.lower() == "media").sum())
                n_d    = int((dfb["dificultad"].str.lower().isin(["dificil","difícil"])).sum())
                n_us   = int((dfb["usada"] != "").sum())
                pct_us = int(n_us / n_tot * 100) if n_tot else 0
                blq_stats.append({"bloque": blq, "total": n_tot,
                                   "facil": n_f, "media": n_m, "dificil": n_d,
                                   "usadas": n_us, "pct": pct_us})

            hdr_html = "".join(
                f"<th style='background:#2c3e50;color:white;padding:8px 12px;"
                f"text-align:{{'left' if i==0 else 'center'}};font-size:0.82em'>{h}</th>"
                for i, h in enumerate(["Bloque", "Total", "🟢 Fácil", "🟡 Media",
                                        "🔴 Difícil", "Usadas", "Dif. mix", "Cobertura"])
            )
            rows_html = ""
            for idx_s, s in enumerate(blq_stats):
                col_uso = ("#27ae60" if s["pct"] >= 60
                           else ("#f39c12" if s["pct"] >= 30 else "#c0392b"))
                dif_bar = (
                    f"<div style='display:flex;gap:1px;height:14px;border-radius:4px;overflow:hidden'>"
                    f"<div style='background:#27ae60;width:{int(s['facil']/max(s['total'],1)*100)}%'></div>"
                    f"<div style='background:#f39c12;width:{int(s['media']/max(s['total'],1)*100)}%'></div>"
                    f"<div style='background:#c0392b;width:{int(s['dificil']/max(s['total'],1)*100)}%'></div>"
                    f"</div>"
                )
                pct_bar = (
                    f"<div style='display:flex;align-items:center;gap:5px'>"
                    f"<div style='flex:1;background:#e9ecef;border-radius:3px;height:8px'>"
                    f"<div style='background:{col_uso};width:{s['pct']}%;height:8px;border-radius:3px'></div></div>"
                    f"<span style='font-size:0.8em;font-weight:700;color:{col_uso}'>{s['pct']}%</span>"
                    f"</div>"
                )
                bg = "#fafbfc" if idx_s % 2 == 0 else "#fff"
                rows_html += (
                    f"<tr style='background:{bg}'>"
                    f"<td style='padding:8px 12px;font-weight:700;color:#2c3e50'>{nombre_bloque(s['bloque'])}</td>"
                    f"<td style='padding:8px;text-align:center;font-weight:600'>{s['total']}</td>"
                    f"<td style='padding:8px;text-align:center;color:#27ae60;font-weight:600'>{s['facil']}</td>"
                    f"<td style='padding:8px;text-align:center;color:#b7950b;font-weight:600'>{s['media']}</td>"
                    f"<td style='padding:8px;text-align:center;color:#c0392b;font-weight:600'>{s['dificil']}</td>"
                    f"<td style='padding:8px;text-align:center'>{s['usadas']}</td>"
                    f"<td style='padding:8px;min-width:100px'>{dif_bar}</td>"
                    f"<td style='padding:8px 12px;min-width:140px'>{pct_bar}</td>"
                    f"</tr>"
                )

            st.markdown(
                f"<table style='width:100%;border-collapse:collapse;border-radius:8px;"
                f"overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)'>"
                f"<thead><tr>{hdr_html}</tr></thead>"
                f"<tbody>{rows_html}</tbody></table>",
                unsafe_allow_html=True
            )
            st.markdown("<br>", unsafe_allow_html=True)

            col_dif, col_uso_det = st.columns(2)
            with col_dif:
                st.markdown("#### 🎯 Distribución global de dificultad")
                dif_counts = df["dificultad"].value_counts()
                total_dif  = sum(int(dif_counts.get(k, 0)) for k in ["Facil","Media","Dificil"])
                for dif_key, col_d, label in [
                    ("Facil","#27ae60","🟢 Fácil"),
                    ("Media","#f39c12","🟡 Media"),
                    ("Dificil","#c0392b","🔴 Difícil"),
                ]:
                    n_d  = int(dif_counts.get(dif_key, 0))
                    pct  = int(n_d / total_dif * 100) if total_dif else 0
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:10px;margin:7px 0'>"
                        f"<div style='width:90px;font-size:0.85em;font-weight:600;color:{col_d}'>{label}</div>"
                        f"<div style='flex:1;background:#e9ecef;border-radius:5px;height:18px'>"
                        f"<div style='background:{col_d};width:{pct}%;height:18px;border-radius:5px;"
                        f"display:flex;align-items:center;padding-left:6px;"
                        f"color:white;font-size:0.75em;font-weight:700'>{n_d} ({pct}%)</div></div></div>",
                        unsafe_allow_html=True
                    )

            with col_uso_det:
                st.markdown("#### 📅 Uso por bloque")
                for s in blq_stats:
                    n_sin = s["total"] - s["usadas"]
                    w_us  = int(s["usadas"] / s["total"] * 100) if s["total"] else 0
                    st.markdown(
                        f"<div style='margin:5px 0'>"
                        f"<div style='display:flex;justify-content:space-between;font-size:0.8em;margin-bottom:2px'>"
                        f"<span style='font-weight:600;color:#2c3e50'>{s['bloque']}</span>"
                        f"<span style='color:#888'>{s['usadas']} usadas · {n_sin} sin usar</span></div>"
                        f"<div style='display:flex;height:12px;border-radius:4px;overflow:hidden'>"
                        f"<div style='background:#27ae60;width:{w_us}%'></div>"
                        f"<div style='background:#e9ecef;width:{100-w_us}%'></div>"
                        f"</div></div>",
                        unsafe_allow_html=True
                    )

        # ══════════════════════════════════════════════════════════════════════
        else:  # Bloque específico
        # ══════════════════════════════════════════════════════════════════════
            sel_blq = vista  # vista is now the raw block name
            dfb     = df[df["bloque"] == sel_blq]

            n_tot_b  = len(dfb)
            n_us_b   = int((dfb["usada"] != "").sum())
            n_nu_b   = n_tot_b - n_us_b
            pct_b    = int(n_us_b / n_tot_b * 100) if n_tot_b else 0
            temas_b  = sorted(dfb["Tema"].unique().tolist(), key=_nsort)
            n_temas_b = len(temas_b)

            # 4 metric cards para el bloque
            bc1, bc2, bc3, bc4 = st.columns(4)
            bc1.markdown(
                f"<div class='stat-card'><div class='stat-num'>{n_tot_b}</div>"
                f"<div class='stat-label'>📚 Total en bloque</div></div>",
                unsafe_allow_html=True)
            bc2.markdown(
                f"<div class='stat-card ok'><div class='stat-num' style='color:#27ae60'>{n_us_b}</div>"
                f"<div class='stat-label'>✅ Usadas</div></div>",
                unsafe_allow_html=True)
            bc3.markdown(
                f"<div class='stat-card warn'><div class='stat-num' style='color:#f39c12'>{n_nu_b}</div>"
                f"<div class='stat-label'>🆕 Sin usar</div></div>",
                unsafe_allow_html=True)
            bc4.markdown(
                f"<div class='stat-card'><div class='stat-num'>{n_temas_b}</div>"
                f"<div class='stat-label'>📌 Temas</div></div>",
                unsafe_allow_html=True)

            st.markdown(f"<br>", unsafe_allow_html=True)
            st.markdown(f"#### 📌 Detalle por tema — {nombre_bloque(sel_blq)}")

            # Filtro de dificultad
            tf1, _ = st.columns([2, 6])
            filt_dif_b = tf1.selectbox(
                "Filtrar dificultad:", ["Todas", "Facil", "Media", "Dificil"],
                key="stat_blq_dif"
            )
            dfb_f = (dfb if filt_dif_b == "Todas"
                     else dfb[dfb["dificultad"].str.lower() == filt_dif_b.lower()])

            # Tabla de temas
            hdr_t = "".join(
                f"<th style='background:#2c3e50;color:white;padding:8px 12px;"
                f"text-align:{{'left' if i==0 else 'center'}};font-size:0.82em'>{h}</th>"
                for i, h in enumerate(["Tema", "Total", "🟢 Fácil", "🟡 Media",
                                        "🔴 Difícil", "Usadas", "Cobertura"])
            )
            rows_t = ""
            for idx_t, tema in enumerate(temas_b):
                dft = dfb_f[dfb_f["Tema"].astype(str) == str(tema)]
                if dft.empty:
                    continue
                n_t   = len(dft)
                n_ft  = int((dft["dificultad"].str.lower() == "facil").sum())
                n_mt  = int((dft["dificultad"].str.lower() == "media").sum())
                n_dt  = int((dft["dificultad"].str.lower().isin(["dificil","difícil"])).sum())
                n_ut  = int((dft["usada"] != "").sum())
                pct_t = int(n_ut / n_t * 100) if n_t else 0
                col_t = ("#27ae60" if pct_t >= 60
                         else ("#f39c12" if pct_t >= 30 else "#c0392b"))
                cob_bar = (
                    f"<div style='display:flex;align-items:center;gap:5px'>"
                    f"<div style='flex:1;background:#e9ecef;border-radius:3px;height:8px'>"
                    f"<div style='background:{col_t};width:{pct_t}%;height:8px;border-radius:3px'></div></div>"
                    f"<span style='font-size:0.8em;font-weight:700;color:{col_t}'>{pct_t}%</span></div>"
                )
                bg_t = "#fafbfc" if idx_t % 2 == 0 else "#fff"
                rows_t += (
                    f"<tr style='background:{bg_t}'>"
                    f"<td style='padding:7px 12px;font-weight:700;color:#2c3e50'>{nombre_tema(str(tema))}</td>"
                    f"<td style='padding:7px;text-align:center;font-weight:600'>{n_t}</td>"
                    f"<td style='padding:7px;text-align:center;color:#27ae60'>{n_ft}</td>"
                    f"<td style='padding:7px;text-align:center;color:#b7950b'>{n_mt}</td>"
                    f"<td style='padding:7px;text-align:center;color:#c0392b'>{n_dt}</td>"
                    f"<td style='padding:7px;text-align:center'>{n_ut}</td>"
                    f"<td style='padding:7px 12px;min-width:130px'>{cob_bar}</td>"
                    f"</tr>"
                )

            if rows_t:
                st.markdown(
                    f"<table style='width:100%;border-collapse:collapse;border-radius:8px;"
                    f"overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)'>"
                    f"<thead><tr>{hdr_t}</tr></thead>"
                    f"<tbody>{rows_t}</tbody></table>",
                    unsafe_allow_html=True
                )
            else:
                st.info(f"No hay datos para dificultad: {filt_dif_b}")

            st.markdown("<br>", unsafe_allow_html=True)

            col_db1, col_db2 = st.columns(2)

            with col_db1:
                st.markdown(f"#### 🎯 Dificultad en {sel_blq}")
                dif_counts_b = dfb["dificultad"].value_counts()
                for dif_key, col_d, label in [
                    ("Facil","#27ae60","🟢 Fácil"),
                    ("Media","#f39c12","🟡 Media"),
                    ("Dificil","#c0392b","🔴 Difícil"),
                ]:
                    n_db  = int(dif_counts_b.get(dif_key, 0))
                    pct_db = int(n_db / n_tot_b * 100) if n_tot_b else 0
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:10px;margin:7px 0'>"
                        f"<div style='width:90px;font-size:0.85em;font-weight:600;color:{col_d}'>{label}</div>"
                        f"<div style='flex:1;background:#e9ecef;border-radius:5px;height:18px'>"
                        f"<div style='background:{col_d};width:{pct_db}%;height:18px;border-radius:5px;"
                        f"display:flex;align-items:center;padding-left:6px;"
                        f"color:white;font-size:0.75em;font-weight:700'>{n_db} ({pct_db}%)</div></div></div>",
                        unsafe_allow_html=True
                    )

            with col_db2:
                st.markdown(f"#### 📅 Uso por tema en {sel_blq}")
                for tema in temas_b:
                    dft2  = dfb[dfb["Tema"].astype(str) == str(tema)]
                    n_t2  = len(dft2)
                    n_ut2 = int((dft2["usada"] != "").sum())
                    n_nu2 = n_t2 - n_ut2
                    w_us2 = int(n_ut2 / n_t2 * 100) if n_t2 else 0
                    st.markdown(
                        f"<div style='margin:5px 0'>"
                        f"<div style='display:flex;justify-content:space-between;font-size:0.8em;margin-bottom:2px'>"
                        f"<span style='font-weight:600'>Tema {tema}</span>"
                        f"<span style='color:#888'>{n_ut2} usadas · {n_nu2} sin usar</span></div>"
                        f"<div style='display:flex;height:12px;border-radius:4px;overflow:hidden'>"
                        f"<div style='background:#27ae60;width:{w_us2}%'></div>"
                        f"<div style='background:#e9ecef;width:{100-w_us2}%'></div>"
                        f"</div></div>",
                        unsafe_allow_html=True
                    )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 · SOLUCIONES (editor batch interactivo)
# ─────────────────────────────────────────────────────────────────────────────
with tab_sol:
    st.subheader("Editor de Soluciones")
    st.caption("Repasa pregunta a pregunta y añade o edita la solución desarrollada.")

    # ── Métricas globales ─────────────────────────────────────────────────────
    def _tiene_sol(v) -> bool:
        return bool(str(v).strip() and str(v) not in ('nan', 'None', ''))

    n_sol_total  = len(df_total)
    n_sol_con    = int(df_total["solucion"].apply(_tiene_sol).sum())
    n_sol_sin    = n_sol_total - n_sol_con
    pct_sol      = int(n_sol_con / n_sol_total * 100) if n_sol_total else 0

    sm1, sm2, sm3 = st.columns(3)
    sm1.markdown(
        f"<div class='stat-card ok'><div class='stat-num' style='color:#27ae60'>{n_sol_con}</div>"
        f"<div class='stat-label'>📖 Con solución</div></div>",
        unsafe_allow_html=True)
    sm2.markdown(
        f"<div class='stat-card warn'><div class='stat-num' style='color:#f39c12'>{n_sol_sin}</div>"
        f"<div class='stat-label'>⬜ Sin solución</div></div>",
        unsafe_allow_html=True)
    sm3.markdown(
        f"<div class='stat-card'><div class='stat-num' style='color:#3498db'>{pct_sol}%</div>"
        f"<div class='stat-label'>✅ Completado</div></div>",
        unsafe_allow_html=True)

    # Barra de progreso global
    bar_w = pct_sol
    bar_r = 100 - bar_w
    st.markdown(
        f"<div style='margin:12px 0 4px 0'>"
        f"<div style='display:flex;justify-content:space-between;font-size:0.78em;color:#666;margin-bottom:3px'>"
        f"<span>Progreso global de soluciones</span><span style='font-weight:700'>{n_sol_con}/{n_sol_total}</span></div>"
        f"<div style='background:#e9ecef;border-radius:6px;height:12px;overflow:hidden'>"
        f"<div style='background:#27ae60;width:{bar_w}%;height:12px;border-radius:6px;"
        f"transition:width 0.4s'></div></div></div>",
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Filtros ───────────────────────────────────────────────────────────────
    sf1, sf2 = st.columns([2, 2])
    sol_blq = sf1.selectbox("Filtrar por bloque:", ["Todos"] + bloques,
                            key="sol_blq_filter",
                            format_func=lambda b: "Todos" if b == "Todos" else nombre_bloque(b))
    sol_modo = sf2.radio("Mostrar:", ["Sin solución", "Con solución", "Todas"],
                         horizontal=True, key="sol_modo")

    # Construir df de trabajo
    df_work = df_total.copy()
    if sol_blq != "Todos":
        df_work = df_work[df_work["bloque"] == sol_blq]
    _mask_sol = df_work["solucion"].apply(_tiene_sol)
    if sol_modo == "Sin solución":
        df_work = df_work[~_mask_sol]
    elif sol_modo == "Con solución":
        df_work = df_work[_mask_sol]
    df_work = df_work.reset_index(drop=True)

    if df_work.empty:
        if sol_modo == "Sin solución":
            st.success("✅ ¡Todas las preguntas de este filtro tienen solución!")
        else:
            st.info("No hay preguntas para los filtros activos.")
    else:
        # ── Navegación ────────────────────────────────────────────────────────
        if "sol_edit_idx" not in st.session_state:
            st.session_state.sol_edit_idx = 0
        sol_idx = min(st.session_state.sol_edit_idx, len(df_work) - 1)

        row_s  = dict(df_work.iloc[sol_idx])
        pid_s  = row_s["ID_Pregunta"]
        corr_s = str(row_s.get("letra_correcta", "A")).upper()

        # Caption de progreso local
        n_en_filtro = len(df_work)
        st.markdown(
            f"<div style='font-size:0.82em;color:#555;margin-bottom:6px'>"
            f"Pregunta <b>{sol_idx + 1}</b> de <b>{n_en_filtro}</b> · "
            f"(Progreso global: {n_sol_con}/{n_sol_total} con solución)</div>",
            unsafe_allow_html=True
        )

        # ── Tarjeta de pregunta ───────────────────────────────────────────────
        card_html_s = render_question_card_html(row_s, show_sol=False, include_notas=False)
        st.markdown(card_html_s, unsafe_allow_html=True)

        notas_s = str(row_s.get("notas", "") or "").strip()
        if notas_s:
            st.markdown(
                "<div style='background:#fefce8;border-left:3px solid #f59e0b;"
                "border-radius:0 8px 8px 0;padding:8px 12px;margin-top:4px;"
                "font-size:0.85em;color:#78350f'>"
                f"<b style='color:#92400e'>📝 Notas:</b> {notas_s}</div>",
                unsafe_allow_html=True
            )

        # ── Plantillas de inicio ──────────────────────────────────────────────
        sol_key_b = f"sol_batch_txt_{pid_s}"
        st.markdown(
            "<span style='font-size:0.82em;color:#888;font-weight:600'>PLANTILLA RÁPIDA</span>",
            unsafe_allow_html=True
        )
        btp1, btp2, btp3 = st.columns(3)
        if btp1.button("📝 Razonamiento", key=f"bsol_razon_{pid_s}", use_container_width=True):
            st.session_state[sol_key_b] = (
                f"La respuesta correcta es la **{corr_s})** porque...\n\n"
                f"Las otras opciones son incorrectas porque..."
            )
        if btp2.button("🔢 Cálculo", key=f"bsol_calc_{pid_s}", use_container_width=True):
            st.session_state[sol_key_b] = (
                "**Datos:**\n\n\n\n"
                "**Desarrollo:**\n\n\n\n"
                "**Resultado:**"
            )
        if btp3.button("💡 Concepto", key=f"bsol_concept_{pid_s}", use_container_width=True):
            st.session_state[sol_key_b] = (
                f"**Concepto clave:** ...\n\n"
                f"**Opción {corr_s})** es correcta porque...\n\n"
                f"**Las demás son incorrectas** porque..."
            )

        # ── Editor inline ──────────────────────────────────────────────────────
        sol_actual_b = str(row_s.get("solucion", "") or "").strip()
        nueva_sol_b  = st.text_area(
            "Solución — LaTeX: `$...$` inline · `$$...$$` o `\\[...\\]` bloque",
            value=sol_actual_b,
            height=160,
            key=sol_key_b,
        )

        # Render LaTeX
        _mjax_b_key = f"sol_batch_mjax_{pid_s}"
        if sol_actual_b and _mjax_b_key not in st.session_state:
            st.session_state[_mjax_b_key] = True
        rb1, rb2 = st.columns(2)
        _rend_on = st.session_state.get(_mjax_b_key, False)
        if rb1.button(
            "✖ Cerrar render" if _rend_on else "∑ Renderizar LaTeX",
            key=f"sol_batch_render_{pid_s}",
            use_container_width=True
        ):
            st.session_state[_mjax_b_key] = not _rend_on
            st.rerun()
        if _rend_on and nueva_sol_b.strip():
            _sol_rhtml = (
                "<div style='font-family:-apple-system,sans-serif;font-size:13px;"
                "color:#2c3e50;padding:12px;background:#f0f9ff;"
                "border-left:3px solid #3498db;border-radius:0 8px 8px 0;line-height:1.65'>"
                f"{nueva_sol_b}</div>"
            )
            stcomponents.html(mathjax_html(_sol_rhtml), height=240, scrolling=True)

        # ── Botones de navegación ─────────────────────────────────────────────
        st.markdown("---")
        nav1, nav2, nav3 = st.columns(3)

        if nav1.button("← Anterior", key="sol_batch_prev",
                       use_container_width=True, disabled=(sol_idx == 0)):
            st.session_state.sol_edit_idx = sol_idx - 1
            st.rerun()

        if nav2.button("⏭️ Saltar", key="sol_batch_skip", use_container_width=True):
            st.session_state.sol_edit_idx = min(n_en_filtro - 1, sol_idx + 1)
            st.rerun()

        if nav3.button("💾 Guardar y siguiente →", type="primary",
                       key="sol_batch_save", use_container_width=True):
            datos_s = {
                "bloque":     row_s.get("bloque", ""),
                "enunciado":  row_s.get("enunciado", ""),
                "tema":       str(row_s.get("Tema", "1")),
                "correcta":   row_s.get("letra_correcta", "A"),
                "dificultad": row_s.get("dificultad", "Media"),
                "usada":      row_s.get("usada", ""),
                "notas":      row_s.get("notas", ""),
                "opciones":   row_s.get("opciones_list", []) or [],
                "solucion":   nueva_sol_b.strip(),
            }
            ok_s, msg_s = lib.actualizar_pregunta_excel_local(
                st.session_state.excel_path,
                st.session_state.excel_dfs,
                pid_s, datos_s,
            )
            if ok_s:
                sync_bloques_gsheets([datos_s["bloque"]])
                reload_db()
                # En modo "Sin solución", la pregunta desaparece del filtro.
                # Mantener el mismo índice (apuntará a la siguiente).
                st.session_state.sol_edit_idx = sol_idx
                st.success("✅ Solución guardada.")
                st.rerun()
            else:
                st.error(f"❌ {msg_s}")

