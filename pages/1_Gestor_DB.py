"""
pages/1_Gestor_DB.py  –  Gestor de la Base de Datos de preguntas.

Pestañas:
  1. Añadir        – Formulario para nueva pregunta
  2. Importar      – Carga desde Word / Aiken con vista previa
  3. Gestionar     – Lista filtrable, editor individual, operaciones masivas
  4. Estadísticas  – Dashboard de cobertura y dificultad
"""
import streamlit as st
import os as _o, sys as _s
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import _recarga; _recarga.comprobar()   # recarga módulos compartidos si cambiaron (despliegues en Streamlit Cloud)
from app_theme import initial_sidebar, notify
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
from app_theme import get_preview_mode, get_estilo, question_detail_html, qtable, qtable_row
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback, apply_theme, page_header,
    connect_db, reload_db,
    bloques_disponibles, temas_de_bloque, temas_en_db, objetivos_de_tema,
    nombre_bloque, nombre_tema, nombre_objetivo,
    es_uso_antiguo, render_question_card_html, mathjax_html, _nsort,
    sync_hoja_gsheets, sync_bloques_gsheets,
    _dialog_editar_pregunta, filtros_bitacora, limpiar_filtros, marcar_preguntas_usadas,
    grupo_pregunta, selector_agrupar, n_preg, orden_bloque,
)

# ── Configuración ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gestor DB · Exámenes UCM", page_icon="🗄️", layout="wide",
                   initial_sidebar_state=initial_sidebar())
init_session_state()
handle_oauth_callback()
apply_theme("gestor")
render_sidebar()

# ── Dialog: selector de constantes físicas ────────────────────────────────────
@st.dialog("📊 Seleccionar constantes / datos", width="large")
def _dialog_seleccionar_datos(current_ids: str, result_key: str):
    """Permite elegir constantes de la BD para asociarlas a una pregunta.
    El resultado se guarda en st.session_state[result_key] como string CSV de IDs."""
    dfs = st.session_state.get("excel_dfs", {})
    datos_df = lib.get_datos_df(dfs)

    if datos_df.empty or datos_df.dropna(subset=['ID']).empty:
        st.warning("No hay constantes en la base de datos. Añádelas en **Configuración → 🔢 Constantes**.")
        if st.button("Cerrar"):
            st.rerun()
        return

    current_list = [i.strip() for i in str(current_ids).split(',') if i.strip()]
    selected_ids = list(current_list)

    st.caption("Marca las constantes que aparecerán como *Datos:* debajo del enunciado.")

    datos_df = datos_df[datos_df['ID'].astype(str).str.strip() != ''].copy()
    categorias = sorted(datos_df['Categoría'].fillna('Sin categoría').unique().tolist())

    for cat in categorias:
        cat_df = datos_df[datos_df['Categoría'].fillna('Sin categoría') == cat]
        if cat_df.empty:
            continue
        st.markdown(f"**{cat}**")
        for _, r in cat_df.iterrows():
            did   = str(r['ID']).strip()
            nom   = str(r.get('Nombre',  '') or '').strip()
            sym   = str(r.get('Símbolo', '') or '').strip()
            val   = str(r.get('Valor',   '') or '').strip()
            uni   = str(r.get('Unidades','') or '').strip()
            label = f"**{nom}** — {sym} = {val} {uni}".strip(" —")
            checked = st.checkbox(label, value=(did in selected_ids),
                                  key=f"_dsel_{result_key}_{did}")
            if checked and did not in selected_ids:
                selected_ids.append(did)
            elif not checked and did in selected_ids:
                selected_ids.remove(did)

    st.markdown("---")
    col_ok, col_cl = st.columns([3, 1])
    if col_ok.button("✅ Aplicar selección", type="primary", use_container_width=True):
        st.session_state[result_key] = ','.join(selected_ids)
        st.rerun()
    if col_cl.button("✖ Cancelar", use_container_width=True):
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
        ed_com = st.text_input("Etiqueta", value=str(q.get("comentario", "") or ""),
                               key="stg_dlg_com", placeholder="ej: CLASE, EXAMEN_2023...")
        _obj_stg_opts = [""] + objetivos_de_tema(q.get("bloque", ed_blq), str(ed_tema))
        _obj_stg_cur  = str(q.get("objetivo", "") or "")
        _obj_stg_idx  = _obj_stg_opts.index(_obj_stg_cur) if _obj_stg_cur in _obj_stg_opts else 0
        ed_obj_stg = st.selectbox("Objetivo", _obj_stg_opts, index=_obj_stg_idx,
                                  key="stg_dlg_obj",
                                  format_func=lambda x: "— Sin objetivo —" if x == "" else nombre_objetivo(x))

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
            "usada": ed_usada, "comentario": ed_com.strip(), "objetivo": ed_obj_stg, "_warnings": [],
            "_auto": ({**q["_auto"], "conf": "revisada"} if q.get("_auto") else None),
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
        f"<div style='background:var(--primary-soft, #f0f4ff);border-left:4px solid var(--primary, #3498db);"
        f"border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:10px'>"
        f"<div style='font-size:0.75em;color:var(--muted, #666);margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<b style='color:var(--text, #2c3e50)'>{pid}</b>"
        f"<span style='background:{dif_col};color:#fff;border-radius:8px;"
        f"padding:1px 8px;font-size:0.9em'>{dif}</span>"
        f"<span style='background:{corr_col};color:#fff;border-radius:8px;"
        f"padding:1px 8px;font-size:0.9em'>Resp. correcta: {corr}</span></div>"
        f"<div style='font-size:1.0em;color:var(--text, #1a252f);line-height:1.6;font-weight:500'>"
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
    st.markdown("<span style='font-size:0.82em;color:var(--muted, #888);font-weight:600'>PLANTILLA RÁPIDA</span>",
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
                "color:var(--text, #2c3e50);padding:14px;background:var(--primary-soft, #f0f9ff);"
                "border-left:3px solid var(--primary, #3498db);border-radius:0 8px 8px 0;line-height:1.65'>"
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
            notify("✅ Solución guardada.")
            st.rerun()
        else:
            st.error(f"❌ {msg}")
    if sg2.button("✖ Cerrar", use_container_width=True, key="dlg_sol_cancel"):
        st.rerun()


_sub_db = (f"{len(st.session_state.df_preguntas)} preguntas · {len(st.session_state.bloques)} bloques"
           if st.session_state.db_connected else "Sin conexión a la base de datos")
page_header("🗄️", "Gestor de Base de Datos", _sub_db, color="#1a3a5c")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos desde la barra lateral antes de continuar.")
    st.stop()

df_total: pd.DataFrame = st.session_state.df_preguntas
bloques = bloques_disponibles()

# Columnas estándar para crear un bloque nuevo desde cero
_STD_COLS = ["ID_Pregunta", "Tema", "Enunciado", "OpcionA", "OpcionB",
             "OpcionC", "OpcionD", "Correcta", "Usada en Examen", "Dificultad", "Notas", "Comentario", "Objetivo", "Solución"]
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
        elif "comentar" in cl:
            new_row[col] = p_data.get("comentario", "")
            claimed.add(idx)
        elif cl == "objetivo":
            new_row[col] = p_data.get("objetivo", "")
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
# Constantes y Objetivos están en Configuración (definen la asignatura, no son preguntas)
tab_man, tab_sol, tab_add, tab_imp, tab_stat = st.tabs(
    ["✏️ Gestionar", "📖 Soluciones", "➕ Añadir", "📥 Importar", "📊 Estadísticas"]
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
                notify(f"✅ Pregunta guardada con ID: **{nid}**")
                sync_bloques_gsheets([bloque_add])
                reload_db()
                st.rerun()
        else:
            st.error("❌ El enunciado no puede estar vacío.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 · IMPORTAR
# ─────────────────────────────────────────────────────────────────────────────
def _ui_importar_json():
    """Importar preguntas desde un JSON exportado de otra base de datos."""
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
            notify(f"✅ {len(nuevas)} importadas, {dupes} duplicadas omitidas.")
            sync_bloques_gsheets([bloque_json])
            reload_db()
            st.rerun()
        else:
            st.warning(f"No se importó ninguna pregunta nueva. {dupes} duplicadas omitidas.")


def _guardar_masivo(ids, msgs):
    sync_bloques_gsheets(list(df_total[df_total["ID_Pregunta"].isin(ids)]["bloque"].unique()))
    reload_db()
    notify(" · ".join(m for m in msgs if m))
    st.rerun()


@st.dialog("Cambiar tema", width="small")
def _dlg_tema(ids):
    st.caption(f"{len(ids)} pregunta(s) seleccionada(s)")
    temas = sorted({str(t) for t in (st.session_state.get("cfg_temas", {}) or {})}
                   | {str(t) for t in df_total["Tema"].astype(str)}, key=_nsort)
    t = st.selectbox("Nuevo tema", temas, format_func=nombre_tema, key="bulk_dlg_tema")
    if st.button("Aplicar", type="primary", key="bulk_dlg_tema_ok"):
        ok, m = lib.actualizar_campo_masivo(st.session_state.excel_path, st.session_state.excel_dfs, ids, "tema", t)
        _guardar_masivo(ids, [m]) if ok else st.error(m)


@st.dialog("Cambiar dificultad", width="small")
def _dlg_dif(ids):
    st.caption(f"{len(ids)} pregunta(s) seleccionada(s)")
    with st.container(key="seg_bulk_dif"):
        d = st.radio("Nueva dificultad", ["Facil", "Media", "Dificil"], index=1, horizontal=True, key="bulk_dlg_dif",
                     format_func=lambda o: {"Facil": "Fácil", "Dificil": "Difícil"}.get(o, o))
    if st.button("Aplicar", type="primary", key="bulk_dlg_dif_ok"):
        ok, m = lib.actualizar_campo_masivo(st.session_state.excel_path, st.session_state.excel_dfs, ids, "dificultad", d)
        _guardar_masivo(ids, [m]) if ok else st.error(m)


@st.dialog("Asignar objetivo", width="small")
def _dlg_obj(ids):
    st.caption(f"{len(ids)} pregunta(s) seleccionada(s)")
    objs = [""] + list((st.session_state.get("cfg_objetivos", {}) or {}).keys())
    o = st.selectbox("Objetivo", objs, key="bulk_dlg_obj",
                     format_func=lambda x: "— Quitar el objetivo —" if not x else nombre_objetivo(x))
    if len(objs) == 1:
        st.caption("No hay objetivos: créalos en Configuración › Objetivos.")
    if st.button("Aplicar", type="primary", key="bulk_dlg_obj_ok"):
        ok, m = lib.actualizar_campo_masivo(st.session_state.excel_path, st.session_state.excel_dfs, ids, "objetivo", o)
        _guardar_masivo(ids, [m]) if ok else st.error(m)


@st.dialog("Poner etiqueta", width="small")
def _dlg_com(ids):
    st.caption(f"{len(ids)} pregunta(s) seleccionada(s)")
    v = st.text_input("Etiqueta", key="bulk_dlg_com", placeholder="ej: CLASE, EXAMEN_2023… (vacío = quitarla)")
    if st.button("Aplicar", type="primary", key="bulk_dlg_com_ok"):
        ok, m = lib.actualizar_campo_masivo(st.session_state.excel_path, st.session_state.excel_dfs, ids,
                                            "comentario", v.strip())
        _guardar_masivo(ids, [m]) if ok else st.error(m)


@st.dialog("Marcar como usadas", width="small")
def _dlg_usada(ids):
    st.caption(f"{len(ids)} pregunta(s) seleccionada(s)")
    f = st.date_input("Fecha de uso", value=datetime.date.today(), key="bulk_dlg_usada")
    if st.button("Aplicar", type="primary", key="bulk_dlg_usada_ok"):
        n = marcar_preguntas_usadas(ids, f.strftime("%Y-%m-%d"))
        notify(f"✅ {n} pregunta(s) marcadas como usadas el {f.strftime('%d/%m/%Y')}.")
        st.rerun()


@st.dialog("Buscar y reemplazar", width="small")
def _dlg_repl(ids):
    st.caption(f"En el enunciado de {len(ids)} pregunta(s) seleccionada(s)")
    a = st.text_input("Buscar", key="bulk_dlg_find")
    b = st.text_input("Reemplazar por", key="bulk_dlg_repl")
    if st.button("Reemplazar", type="primary", key="bulk_dlg_repl_ok", disabled=not a):
        ok, m = lib.reemplazar_texto_masivo(st.session_state.excel_path, st.session_state.excel_dfs, ids, a, b)
        _guardar_masivo(ids, [m]) if ok else st.error(m)


@st.dialog("Eliminar preguntas", width="small")
def _dlg_del(ids):
    st.warning(f"Se eliminarán **{len(ids)}** pregunta(s) de forma permanente: {', '.join(ids[:5])}"
               + ("…" if len(ids) > 5 else ""))
    if st.checkbox("Confirmo que quiero eliminarlas", key="bulk_dlg_del_conf") and \
            st.button(f"Eliminar {len(ids)}", type="primary", key="bulk_dlg_del_ok"):
        ok, m = lib.eliminar_preguntas_excel_local(st.session_state.excel_path, st.session_state.excel_dfs, ids)
        if ok:
            st.session_state["man_checked"] = []
            st.session_state["_man_chk_reset"] = st.session_state.get("_man_chk_reset", 0) + 1
            _guardar_masivo(ids, [m])
        else:
            st.error(m)


def _barra_acciones(ids):
    """Barra oscura sobre las preguntas MARCADAS (no sobre todas las filtradas)."""
    import json as _json
    with st.container(horizontal=True, gap="small", key="man_actbar"):
        st.markdown(f"<span class='ab-count'>{len(ids)} seleccionada{'s' if len(ids) != 1 else ''}</span>",
                    unsafe_allow_html=True)
        acciones = [("Cambiar tema", _dlg_tema), ("Dificultad", _dlg_dif), ("Objetivo", _dlg_obj),
                    ("Etiqueta", _dlg_com), ("Marcar como usada", _dlg_usada), ("Buscar y reemplazar", _dlg_repl)]
        for i, (lbl, fn) in enumerate(acciones):
            if st.button(lbl, key=f"man_act_{i}"):
                fn(ids)
        _pregs = df_total[df_total["ID_Pregunta"].isin(ids)].to_dict("records")
        st.download_button("Exportar JSON", _json.dumps({"version": 1, "preguntas": _pregs}, ensure_ascii=False,
                                                        indent=2, default=str).encode("utf-8"),
                           file_name=f"preguntas_{datetime.date.today()}.json", mime="application/json",
                           key="man_act_json")
        if st.button("Eliminar", key="man_act_del"):
            _dlg_del(ids)
        if st.button("Quitar selección ×", key="man_act_clear"):
            st.session_state["man_checked"] = []
            st.session_state["_man_chk_reset"] = st.session_state.get("_man_chk_reset", 0) + 1
            st.rerun()



def _estadisticas_bitacora(df_all):
    """Gestor › Estadísticas como panel (Bitácora)."""
    import analisis_lib as _A
    from app_theme import kpi_html
    ss = st.session_state
    _vacio = lambda v: str(v).strip() in ("", "nan", "None", "NaT")

    c1, c2, _ = st.columns([1.3, 1.6, 4], vertical_alignment="bottom")
    with c1.container(key="seg_est_ver"):
        ver = st.radio("Ver", ["Toda la base", "Un bloque"], horizontal=True, key="est_ver")
    blq = c2.selectbox("Bloque", bloques, key="est_blq", format_func=nombre_bloque) if ver == "Un bloque" and bloques else None
    df = df_all if not blq else df_all[df_all["bloque"] == blq]
    n = len(df)
    if not n:
        st.info("Este bloque todavía no tiene preguntas.")
        return
    tema_s = df["Tema"].astype(str).str.removesuffix(".0")
    dif = df["dificultad"].astype(str).str.lower().str.replace("á", "a").str.replace("í", "i")
    uso = df["usada"].astype(str).apply(lambda v: "" if _vacio(v) else v.strip()[:10])
    sol = ~df.get("solucion", pd.Series("", index=df.index)).apply(_vacio)
    obj = df.get("objetivo", pd.Series("", index=df.index)).astype(str)
    con_obj = ~obj.apply(_vacio)
    disp = uso.apply(lambda v: not v or es_uso_antiguo(v, 12))
    cfg_t = ss.get("cfg_temas", {}) or {}
    temas_cfg = {str(t) for t, d in cfg_t.items() if not blq or (isinstance(d, dict) and d.get("bloque") in ("", blq))}
    todos_temas = sorted(temas_cfg | set(tema_s), key=_nsort)
    vacios = [t for t in todos_temas if t not in set(tema_s)]
    pct = lambda k: f"{round(100 * k / n)} % del banco"

    st.markdown(kpi_html([
        ("Preguntas", n, f"{df['bloque'].nunique()} bloques · {len(set(tema_s))} temas", False),
        ("Con solución", int(sol.sum()), pct(int(sol.sum())), False),
        ("Disponibles", int(disp.sum()), "sin usar en 12 meses", False),
        ("Temas sin preguntas", len(vacios), ", ".join(f"Tema {t}" for t in vacios[:3]) or "ninguno", False),
        ("Con objetivo", int(con_obj.sum()), pct(int(con_obj.sum())), False),
    ], compact=True), unsafe_allow_html=True)

    # ── Mapa de calor · uso por mes ─────────────────────────────────────────
    g1, g2 = st.columns([1.15, 1], gap="medium")
    filas = ([(t, nombre_tema(t).split(": ", 1)[-1] if ":" in nombre_tema(t) else "", tema_s == t) for t in todos_temas]
             if blq else
             [(b, (ss.get("cfg_bloques", {}) or {}).get(b, "") or "", df["bloque"] == b)
              for b in sorted(df["bloque"].unique(), key=orden_bloque)])
    mx = 1
    datos = []
    for k, nom, m in filas:
        v = [int((dif[m] == "facil").sum()), int((dif[m] == "media").sum()), int((dif[m] == "dificil").sum())]
        mx = max(mx, *v)
        datos.append((k, nom, v))

    def celda(v):
        if v == 0:
            return "<span class='hm0'>0</span>"
        a = 12 + 70 * v / mx
        return (f"<span style='background:color-mix(in srgb, var(--primary) {a:.0f}%, transparent);"
                f"color:{'#fff' if a > 50 else 'var(--text)'}'>{v}</span>")

    rows = "".join(f"<div class='hmr'><span class='hn'><small>{'Tema ' + k if blq else k}</small>"
                   f"{nom if nom and str(nom) not in ('nan', 'None') else ''}</span>"
                   + "".join(celda(x) for x in v) + f"<b>{sum(v)}</b></div>" for k, nom, v in datos)
    g1.markdown("<div class='card est'><div class='est-h'><b>Preguntas por "
                + ("tema" if blq else "bloque") + " y dificultad</b><small>más oscuro = más preguntas · rojo = ninguna</small></div>"
                "<div class='hmr hdr'><span></span><span>Fácil</span><span>Media</span><span>Difícil</span><span>Total</span></div>"
                f"{rows}</div>", unsafe_allow_html=True)

    hoy = datetime.date.today()
    meses = []
    for i in range(11, -1, -1):
        y, mth = hoy.year, hoy.month - i
        while mth <= 0:
            mth += 12
            y -= 1
        meses.append(f"{y}-{mth:02d}")
    cnt = uso.str[:7].value_counts().to_dict()
    vm = [cnt.get(m, 0) for m in meses]
    top = max(vm) or 1
    MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    bars = "".join(f"<div class='ub'><small>{v or ''}</small><span style='height:{max(3, 120 * v / top):.0f}px'"
                   f"{' class=z' if not v else ''}></span><em>{MES[int(m[5:]) - 1]}</em></div>" for m, v in zip(meses, vm))
    nunca = int((uso == "").sum())
    ult6 = int(uso.apply(lambda v: bool(v) and not es_uso_antiguo(v, 6)).sum())
    g2.markdown("<div class='card est'><div class='est-h'><b>Uso en exámenes</b><small>preguntas usadas por mes · "
                f"último año</small></div><div class='ubars'>{bars}</div><div class='mini3'>"
                f"<div><b>{nunca}</b><small>nunca usadas</small></div>"
                f"<div><b>{int(disp.sum())}</b><small>disponibles (sin usar en 12 meses)</small></div>"
                f"<div><b>{ult6}</b><small>usadas en los últimos 6 meses</small></div></div>"
                "<div class='est-n'>Se cuenta la última fecha de uso de cada pregunta.</div></div>", unsafe_allow_html=True)

    # ── Temas ───────────────────────────────────────────────────────────────
    st.write("")
    h1, h2 = st.columns([3, 2.2], vertical_alignment="bottom")
    h1.markdown("<div class='sec-title' style='margin:0'>Temas</div>", unsafe_allow_html=True)
    with h2.container(key="seg_est_orden"):
        orden = st.radio("Ordenar por", ["Menos preguntas", "Más sin solución", "Número de tema"],
                         horizontal=True, key="est_orden")
    tdat = []
    for t in todos_temas:
        m = tema_s == t
        k = int(m.sum())
        b = df.loc[m, "bloque"].iloc[0] if k else (cfg_t.get(t, {}) or {}).get("bloque", "") if isinstance(cfg_t.get(t), dict) else ""
        tdat.append(dict(t=t, b=b, n=k, f=int((dif[m] == "facil").sum()), m=int((dif[m] == "media").sum()),
                         d=int((dif[m] == "dificil").sum()), ss=int((~sol[m]).sum()), u=max(uso[m]) if k and any(uso[m]) else ""))
    if orden == "Menos preguntas":
        tdat.sort(key=lambda r: (r["n"], _nsort(r["t"])))
    elif orden == "Más sin solución":
        tdat.sort(key=lambda r: (-r["ss"], _nsort(r["t"])))
    mxn = max([r["n"] for r in tdat] + [1])
    trs = ""
    for r in tdat:
        nom = nombre_tema(r["t"])
        nom = nom.split(": ", 1)[1] if ": " in nom else ""
        mini = "".join(f"<span style='flex:{v or 0.001};background:{c}'></span>"
                       for v, c in ((r["f"], "var(--ok)"), (r["m"], "var(--primary)"), (r["d"], "var(--err)")))
        chip = (f"<span class='tg w'>{r['ss']} sin sol.</span>" if r["ss"] else
                ("<span class='tg f'>completas</span>" if r["n"] else "<span class='tg n'>—</span>"))
        trs += (f"<div class='tr'><span><b>Tema {r['t']}</b> {nom}</span><span class='mono'>{r['b']}</span>"
                f"<span class='bw'><span class='bar'><span style='width:{100 * r['n'] / mxn:.0f}%'></span></span>"
                f"<b class='{'z' if not r['n'] else ''}'>{r['n']}</b></span>"
                f"<span class='mini'>{mini}</span>{chip}<span class='mono'>{r['u'][:7] or '—'}</span></div>")
    with st.container(height=min(520, 70 + 42 * len(tdat)), key="card_est_temas"):
        st.markdown("<div class='tr hdr'><span>Tema</span><span>Bloque</span><span>Preguntas</span>"
                    f"<span>F · M · D</span><span>Solución</span><span>Último uso</span></div>{trs}",
                    unsafe_allow_html=True)

    # ── Dificultad banco vs observada · objetivos ───────────────────────────
    d1, d2 = st.columns(2, gap="medium")
    res = _A.get_resultados(ss.get("excel_dfs", {}))
    res = res[res["ID_Pregunta"].isin(set(df["ID_Pregunta"]))] if not res.empty else res
    if res.empty:
        d1.markdown("<div class='card est'><div class='est-h'><b>Dificultad: banco frente a lo observado</b></div>"
                    "<div class='est-n'>Aún no hay análisis guardados de preguntas de este banco. Se rellena al guardar "
                    "el análisis de un examen en la página Análisis.</div></div>", unsafe_allow_html=True)
    else:
        last = res.sort_values("Fecha").groupby("ID_Pregunta").tail(1)
        bank = df.set_index("ID_Pregunta")["dificultad"].astype(str).str.lower().str.replace("á", "a").str.replace("í", "i")
        M = {(a, b): 0 for a in ("facil", "media", "dificil") for b in ("facil", "media", "dificil")}
        for _, r in last.iterrows():
            real = _A.dificultad_real(float(r["Pct_Acierto"] or "nan")).lower()
            bk = bank.get(r["ID_Pregunta"], "")
            if real and bk in ("facil", "media", "dificil"):
                M[(bk, real)] += 1
        tot = sum(M.values())
        dis = sum(v for (a, b), v in M.items() if a != b)
        cells = ""
        for a in ("facil", "media", "dificil"):
            cells += f"<span class='ml'>banco {a.replace('facil', 'fácil').replace('dificil', 'difícil')}</span>"
            for b in ("facil", "media", "dificil"):
                v = M[(a, b)]
                cls = "ok" if a == b else ("w" if v else "n")
                cells += f"<span class='mc {cls}'>{v}</span>"
        d1.markdown("<div class='card est'><div class='est-h'><b>Dificultad: banco frente a lo observado</b>"
                    f"<small>{tot} preguntas con análisis guardado</small></div><div class='mat'><span></span>"
                    "<span class='ml c'>real fácil</span><span class='ml c'>real media</span><span class='ml c'>real difícil</span>"
                    f"{cells}</div><div class='est-n'><b>{dis} de {tot}</b> no coinciden con la dificultad del banco. "
                    "Puedes cambiarla desde Análisis › modo revisión.</div></div>", unsafe_allow_html=True)
    cfg_o = ss.get("cfg_objetivos", {}) or {}
    objs = [(c, d) for c, d in cfg_o.items() if not blq or d.get("bloque") in ("", blq)]
    cnt_o = obj.value_counts().to_dict()
    mxo = max([cnt_o.get(c, 0) for c, _ in objs] + [1])
    orow = "".join(f"<div class='or'><span class='mono'>{c}</span><span class='on'>{d.get('nombre_corto') or '—'}</span>"
                   f"<span class='bar'><span style='width:{100 * cnt_o.get(c, 0) / mxo:.0f}%'></span></span>"
                   f"<b class='{'z' if not cnt_o.get(c, 0) else ''}'>{cnt_o.get(c, 0)}</b></div>" for c, d in objs)
    d2.markdown("<div class='card est'><div class='est-h'><b>Objetivos docentes</b><small>preguntas asignadas a cada "
                "objetivo</small></div>"
                + (orow or "<div class='est-n'>No hay objetivos. Créalos en Configuración › Objetivos.</div>")
                + f"<div class='est-n'><b>{int((~con_obj).sum())} preguntas</b> sin objetivo asignado.</div></div>",
                unsafe_allow_html=True)


def _stg_sin_correcta(q: dict) -> bool:
    if str(q.get("letra_correcta", "")).upper() not in ("A", "B", "C", "D"):
        return True
    return any(("Sin respuesta" in w or "por defecto" in w) for w in q.get("_warnings", []))


def _stg_problemas(q: dict) -> bool:
    return bool(q.get("_dup") or q.get("_dup_file") or _stg_sin_correcta(q))


def _stg_tags(q: dict) -> str:
    def chip(t, c):
        return (f"<span style='display:inline-block;padding:0 7px;border-radius:999px;font-size:.78em;"
                f"font-weight:600;margin-left:4px;background:var(--{c}-bg, #fdf0d5);color:var(--{c}, #7a4f00)'>{t}</span>")
    out = ""
    a = q.get("_auto")
    if a:
        _c = {"alta": "ok", "media": "primary", "baja": "warn", "revisada": "used"}.get(a["conf"], "primary")
        _bg = {"primary": "var(--primary-soft, #e6edf8)", "used": "var(--used-bg, #eee8f8)"}.get(_c, f"var(--{_c}-bg)")
        _txt = f"{q.get('bloque', '')} · Tema {q.get('tema', '')}" + (f" · {q['objetivo']}" if q.get("objetivo") else "")
        out += (f"<span style='display:inline-block;padding:0 7px;border-radius:999px;font-size:.78em;font-weight:600;"
                f"margin-left:4px;background:{_bg};color:var(--{_c})' title='Propuesta automática · confianza {a['conf']}'>"
                f"{_txt} · {a['conf']}</span>")
    if q.get("_dup"):
        out += chip(f"posible duplicado ({q['_dup']} %)", "err")
    if q.get("_dup_file"):
        out += chip("repetida en el archivo", "err")
    if _stg_sin_correcta(q):
        out += chip("sin respuesta correcta", "warn")
    otras = [w for w in q.get("_warnings", []) if "Sin respuesta" not in w and "por defecto" not in w]
    if otras:
        out += chip(otras[0].lower(), "warn")
    return out


with tab_imp:
    st.subheader("Importar preguntas")
    if get_estilo() == "bitacora":
        with st.expander("Importar desde un JSON exportado de otra base de datos"):
            _ui_importar_json()

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
    com_imp = st.text_input(
        "Etiqueta de importación",
        placeholder="ej: CLASE, EXAMEN_2023, RECUPERACION...",
        key="imp_comentario",
        help="Se añade a todas las preguntas importadas (aunque la escribas después de previsualizar), "
             "salvo a las que les pongas otra con ✏️. Después podrás filtrar por ella en Gestionar."
    )
    auto_cls = st.toggle(
        "Proponer bloque, tema y objetivo de cada pregunta", value=True, key="imp_auto",
        help="Compara cada pregunta con las del banco y con los nombres de bloques, temas y objetivos "
             "(Configuración). Es una propuesta: la revisas en la tabla antes de importar. "
             "Sin propuesta, todas van al bloque y tema elegidos arriba.")

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
            for p in preguntas:
                p["comentario"] = com_imp.strip()
            # Revisión: posibles duplicados (con la base de datos y dentro del archivo)
            _seen = []
            for p in preguntas:
                _d, _sim = lib.check_for_similar_enunciado(p.get("enunciado", ""), df_total)
                p["_dup"] = round(float(_sim) * 100) if _d else 0
                _n = lib._normalizar_texto(p.get("enunciado", ""))
                p["_dup_file"] = bool(_n) and _n in _seen
                _seen.append(_n)
            if auto_cls and not df_total.empty:
                from clasificador import Clasificador
                _cls = Clasificador(df_total, st.session_state.get("cfg_bloques", {}),
                                    st.session_state.get("cfg_temas", {}), st.session_state.get("cfg_objetivos", {}))
                for p in preguntas:
                    c = _cls.clasificar(p.get("enunciado", ""), p.get("opciones_list", []))
                    if c["bloque"]:
                        p["bloque"], p["tema"] = c["bloque"], c["tema"]
                        if c["objetivo"]:
                            p["objetivo"] = c["objetivo"]
                        p["_auto"] = c
            st.session_state.import_staging = preguntas
            st.session_state["_staging_edit_idx"] = None
            # Selección inicial: se desmarcan las que tienen problemas
            for i, p in enumerate(preguntas):
                st.session_state[f"stg_sel_{i}"] = not _stg_problemas(p)
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

        _n_dup = sum(1 for q in staging if q.get("_dup") or q.get("_dup_file"))
        _n_sc  = sum(1 for q in staging if _stg_sin_correcta(q))
        st.markdown(f"**{len(staging)}** detectadas · **{_n_dup}** posibles duplicados · **{_n_sc}** sin respuesta "
                    f"correcta clara" + (" — se han desmarcado; revísalas con ✏️" if (_n_dup or _n_sc) else ""))
        _autos = [q["_auto"]["conf"] for q in staging if q.get("_auto")]
        if _autos:
            ca1, ca2 = st.columns([3, 1.3], vertical_alignment="center")
            ca1.markdown(
                f"Bloque y tema propuestos: **{_autos.count('alta')}** con confianza alta · "
                f"**{_autos.count('media')}** media · **{_autos.count('baja')}** baja"
                + (f" · **{_autos.count('revisada')}** revisadas" if "revisada" in _autos else "")
                + ". Revisa sobre todo las de confianza baja (✏️ para cambiarlas).")
            if ca2.button("Usar el bloque y tema de arriba", key="btn_stg_no_auto", use_container_width=True,
                          help="Descarta las propuestas: todas irán al bloque y tema elegidos arriba"):
                for q in staging:
                    q["bloque"], q["tema"] = bloque_imp, str(tema_imp)
                    q.pop("objetivo", None)
                    q.pop("_auto", None)
                st.rerun()

        # Cabecera
        h0, h2, h3, h4 = st.columns([0.5, 8, 0.8, 0.7])
        h0.markdown("<span style='font-size:0.8em;color:var(--muted, #888)'>✓</span>", unsafe_allow_html=True)
        h2.markdown("<span style='font-size:0.8em;color:var(--muted, #888)'>Enunciado</span>", unsafe_allow_html=True)
        h3.markdown("<span style='font-size:0.8em;color:var(--muted, #888)'>Resp.</span>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

        _BADGE = {"A": "#27ae60", "B": "#2980b9", "C": "#8e44ad", "D": "#c0392b"}
        for i, q in enumerate(staging):
            c_sel, c_enun, c_resp, c_edit = st.columns([0.5, 8, 0.8, 0.7])

            c_sel.checkbox("", value=st.session_state.get(f"stg_sel_{i}", True),
                           key=f"stg_sel_{i}", label_visibility="collapsed")

            warns      = q.get("_warnings", [])
            warn_icon  = " <span style='color:var(--ui-warn, #e67e22)'>⚠</span>" if warns else ""
            _tags = _stg_tags(q)
            if _tags:
                warn_icon = " " + _tags
            enun_short = q["enunciado"][:85] + ("…" if len(q["enunciado"]) > 85 else "")
            c_enun.markdown(
                f"<span style='font-size:0.85em;line-height:1.3'>"
                f"<b style='color:var(--muted, #999);font-size:0.8em'>{i+1}.</b> {enun_short}{warn_icon}</span>",
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
                st.rerun()

        st.divider()

        # Abre el dialog si hubo rerun con _staging_edit_idx pendiente
        if st.session_state.get("_staging_edit_idx") is not None:
            _dialog_editar_staging()

        sel_ids   = [i for i in range(len(staging)) if st.session_state.get(f"stg_sel_{i}", True)]
        sel_count = len(sel_ids)
        st.caption(f"Seleccionadas: **{sel_count}** de {len(staging)}")

        c_imp, c_clr = st.columns([3, 1])
        if c_imp.button(f"📥 Importar {sel_count}" if get_estilo() == "bitacora"
                        else f"📥 Importar seleccionadas ({sel_count})", type="primary",
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
                    # la etiqueta de importación vale para todas, salvo las que tengan una propia (✏️)
                    "comentario":     staging[i].get("comentario", "") or com_imp.strip(),
                    "objetivo":       staging[i].get("objetivo", ""),
                }
                is_dup, _ = lib.check_for_similar_enunciado(p_data["enunciado"], df_total)
                if is_dup: skipped += 1; continue
                blk    = p_data["bloque"]
                blk_df = _asegurar_bloque(excel_dfs, blk)
                if "Comentario" not in blk_df.columns:
                    ins = blk_df.columns.get_loc("Notas") + 1 if "Notas" in blk_df.columns else len(blk_df.columns)
                    blk_df.insert(ins, "Comentario", "")
                    excel_dfs[blk] = blk_df
                if "Objetivo" not in blk_df.columns:
                    ins2 = (blk_df.columns.get_loc("Comentario") + 1
                            if "Comentario" in blk_df.columns
                            else len(blk_df.columns))
                    blk_df.insert(ins2, "Objetivo", "")
                    excel_dfs[blk] = blk_df
                nid, _ = lib.generar_siguiente_id(df_total, blk, p_data["tema"])
                new_row = _fill_row(blk_df, p_data, nid)
                excel_dfs[blk] = pd.concat([blk_df, pd.DataFrame([new_row])], ignore_index=True)
                df_total = pd.concat([df_total, pd.DataFrame([{
                    "ID_Pregunta": nid, "bloque": blk, "Tema": p_data["tema"],
                    "enunciado": p_data["enunciado"], "opciones_list": p_data["opciones_list"],
                    "letra_correcta": p_data["letra_correcta"], "dificultad": p_data["dificultad"],
                    "usada": "", "notas": "", "comentario": p_data.get("comentario", ""),
                    "objetivo": p_data.get("objetivo", ""),
                }])], ignore_index=True)
                imported += 1

            if imported:
                lib.guardar_excel_local(excel_path, excel_dfs)
                notify(f"✅ {imported} pregunta(s) importada(s). {skipped} duplicada(s) omitida(s).")
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
    _bit = get_estilo() == "bitacora"   # Bitácora: disposición nueva; Clásico: la de siempre
    if not _bit:
        st.subheader("Gestionar preguntas")

    # ── Filtros ──────────────────────────────────────────────────────────────
    # Flag pattern: aplicar resets ANTES de renderizar widgets
    if st.session_state.pop("_do_clear_filters", False):
        st.session_state["man_f_bloque"]       = "Todos"
        st.session_state["man_f_tema"]         = "Todos"
        st.session_state["man_f_dif"]          = "Todas"
        st.session_state["man_f_uso"]          = "Todos"
        st.session_state["man_search"]         = ""
        st.session_state["man_search_global"]  = False
        st.session_state["man_filter_sin_sol"] = False
        st.session_state["_man_prev_bloque"]   = "Todos"
        limpiar_filtros("man_")
    _preset = st.session_state.pop("_gestor_preset", None)   # filtros pedidos desde Inicio
    if _preset:
        for _k, _v in {"man_f_bloque": "Todos", "man_f_tema": "Todos", "man_f_dif": "Todas",
                       "man_f_uso": "Todos", "man_search": "", "man_filter_sin_sol": False,
                       "man_f_sol": "Todas", "man_f_obj": "Todos", "man_f_com": "Todas",
                       "man_search_global": False, "_man_prev_bloque": "Todos", **_preset}.items():
            st.session_state[_k] = _v

    if _bit:
        # Filtros comunes con Generador › Selección (buscador, bloque, tema, objetivo, uso,
        # dificultad, solución, etiqueta) con etiquetas de filtros activos y recuento
        df_filt = filtros_bitacora("man_", df_total, bloques)
        _multi_mode = False
    else:
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
        fc5.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
        if fc5.button("🔄", key="btn_clear_filters", help="Limpiar todos los filtros"):
            st.session_state["_do_clear_filters"] = True
            st.rerun()

        srch1, srch2, srch3 = st.columns([4, 1.2, 1])
        f_search  = srch1.text_input("🔍 Buscar", placeholder="Enunciado, opciones, notas…", key="man_search")
        f_global  = srch2.checkbox("🌐 Todos los bloques", key="man_search_global", value=False,
                                    help="Buscar ignorando el filtro de bloque")
        f_sin_sol = srch3.checkbox("Sin solución", key="man_filter_sin_sol", value=False)

        _count_slot = st

    if not _bit:
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
            "  ·  <span style='background:var(--primary-soft, #dbeafe);color:var(--primary, #1e40af);border-radius:8px;"
            "padding:1px 8px;font-size:0.9em;font-weight:600'>🌐 búsqueda global</span>"
            if f_global and f_search else ""
        )
        _count_slot.markdown(
            f"<div style='font-size:0.82em;color:var(--muted, #666);margin-bottom:6px'>"
            f"Mostrando <b style='color:var(--text, #2c3e50)'>{n_filt}</b> de {len(df_total)} preguntas"
            f"{'  ·  <b style=\"color:var(--primary, #3498db)\">' + str(pct_filt) + '%</b>' if pct_filt < 100 else ''}"
            f"{_gbadge}</div>",
            unsafe_allow_html=True,
        )

    n_filt = len(df_filt)

    # ── Vista previa de una pregunta (panel derecho o ventana) ────────────────
    def _duplicar_pregunta(sel_pid, row_d):
        """Crea una copia de la pregunta (sin solución ni fecha de uso) en su mismo bloque y tema."""
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
            notify(f"✅ Duplicada como **{nid}**")
            sync_bloques_gsheets([blk]); reload_db(); st.rerun()

    def _acciones_editor(sel_pid, row_d):
        """Duplicar / Eliminar dentro del editor (Bitácora)."""
        e1, e2 = st.columns(2)
        if e1.button("Duplicar", key="dlg_dup", use_container_width=True):
            _duplicar_pregunta(sel_pid, row_d)
        _dk = f"dlg_del_conf_{sel_pid}"
        if e2.button("Eliminar", key="dlg_del", use_container_width=True):
            st.session_state[_dk] = not st.session_state.get(_dk, False)
        if st.session_state.get(_dk):
            st.warning(f"¿Eliminar {sel_pid} de forma permanente?")
            if st.button("Sí, eliminar", type="primary", key="dlg_del_ok", use_container_width=True):
                ok, msg = lib.eliminar_preguntas_excel_local(
                    st.session_state.excel_path, st.session_state.excel_dfs, [sel_pid])
                if ok:
                    sync_bloques_gsheets([row_d["bloque"]])
                    st.session_state.pop(_dk, None)
                    st.session_state.pop("man_open_pid", None)
                    notify(f"🗑️ {sel_pid} eliminada.")
                    reload_db(); st.rerun()
                else:
                    st.error(msg)

    def _render_gest_preview(sel_pid, row_d, in_dialog=False):
        """Tarjeta + acciones. En ventana, editar/solución se abren al recargar la página
        y borrar/duplicar renuevan la tabla para no abrir sola otra pregunta."""
        _rerun_local = (lambda: st.rerun(scope="fragment")) if in_dialog else st.rerun

        def _renovar_tabla():
            if in_dialog:
                st.session_state["_man_dlg_nonce"] = st.session_state.get("_man_dlg_nonce", 0) + 1

        card_html = render_question_card_html(row_d, show_sol=True, include_notas=False)
        sol_txt   = str(row_d.get("solucion", "") or "").strip()
        notas_txt = str(row_d.get("notas",    "") or "").strip()
        notas_html = ""

        # 1. Tarjeta principal (Bitácora: cabecera con etiquetas y recuadros)
        _bt = get_estilo() == "bitacora"
        st.markdown(question_detail_html(row_d) if _bt else card_html, unsafe_allow_html=True)

        # 2. Notas
        if notas_txt:
            notas_html = (
                "<div style='background:var(--note-bg, #fefce8);border-left:3px solid var(--ui-warn, #f59e0b);"
                "border-radius:0 8px 8px 0;padding:8px 14px;margin-top:4px;"
                "font-size:0.875em;color:var(--note-text, #78350f);line-height:1.5'>"
                "<b style='color:var(--note-text, #92400e)'>📝 Notas:</b> "
                f"{notas_txt}</div>"
            )
            st.markdown(notas_html, unsafe_allow_html=True)

        # 3. Render LaTeX toggle (tarjeta + notas)
        _mjax_key = f"mjax_gest_{sel_pid}"
        _rend_on  = st.session_state.get(_mjax_key, False)
        if st.button(
            "✖ Cerrar LaTeX" if _rend_on else "∑ Renderizar LaTeX",
            key=f"mjax_btn_{sel_pid}",
            use_container_width=True,
        ):
            st.session_state[_mjax_key] = not _rend_on
            _rerun_local()
        if _rend_on:
            stcomponents.html(
                mathjax_html(card_html + notas_html),
                height=480, scrolling=True,
            )

        # 4. Botones de acción — solo icono, misma anchura, tooltip descriptivo
        st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
        ba1, ba2, ba3, ba4 = st.columns(4)
        if ba1.button("✏️ Editar pregunta" if _bt else "✏️", use_container_width=True, type="primary",
                      key="btn_edit_q", help="Editar pregunta"):
            if in_dialog:   # no se puede abrir una ventana dentro de otra
                st.session_state["_man_open"] = ("edit", sel_pid); st.rerun()
            _dialog_editar_pregunta(sel_pid, row_d)
        if ba2.button(("📖 Ver solución" if sol_txt else "📖 Escribir solución") if _bt else "📖",
                      use_container_width=True, key="btn_sol_q",
                      help="Sin solución aún" if not sol_txt else "Ver / editar solución"):
            if in_dialog:
                st.session_state["_man_open"] = ("sol", sel_pid); st.rerun()
            _dialog_solucion(sel_pid, row_d)
        if ba3.button("📋 Duplicar" if _bt else "📋", use_container_width=True, key="btn_dup_q",
                      help="Duplicar pregunta"):
            _duplicar_pregunta(sel_pid, row_d)

        # Borrar con confirmación inline
        _del_key = f"del_confirm_{sel_pid}"
        if ba4.button("🗑️ Eliminar" if _bt else "🗑️", use_container_width=True, key="btn_del_q",
                      help="Eliminar esta pregunta"):
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
                    _renovar_tabla(); reload_db(); st.rerun()
                else:
                    st.error(msg)
            if cd2.button("✖ Cancelar", use_container_width=True, key="btn_del_cancel"):
                st.session_state.pop(_del_key, None)
                _rerun_local()

        # 5. Solución expandible — debajo de los botones
        if sol_txt:
            with st.expander("📖 Ver solución", expanded=False):
                _sol_prev_html = (
                    "<div style='font-size:13px;color:var(--text, #2c3e50);padding:10px;"
                    "background:var(--primary-soft, #f0f9ff);border-left:3px solid var(--primary, #3498db);"
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
                    _rerun_local()


    @st.dialog("👁 Pregunta", width="large")
    def _dialog_gest_preview(pid):
        _r = df_total[df_total["ID_Pregunta"] == pid]
        if _r.empty:
            st.info("La pregunta ya no está en la base de datos.")
            return
        _render_gest_preview(pid, dict(_r.iloc[0]), in_dialog=True)

    # ── Layout 2 columnas: tabla + panel derecho ──────────────────────────────
    if df_filt.empty:
        st.info("No hay preguntas que coincidan con los filtros.")
    else:
        _gest_ventana = get_preview_mode() == "ventana"
        _man_nonce    = st.session_state.get("_man_dlg_nonce", 0)
        _man_open_pid = None   # pregunta a abrir en ventana en esta ejecución
        if _gest_ventana:      # tabla a todo el ancho; acciones debajo
            col_table, col_preview = st.container(), st.container()
        else:
            col_table, col_preview = st.columns([3, 2], gap="medium")

        with col_table:
            # Toggle modo selección múltiple (en Bitácora está en la fila de estado)
            if not _bit:
                _multi_mode = st.toggle(
                    "☑️ Modo selección múltiple",
                    value=st.session_state.get("man_multi_mode", False),
                    key="man_multi_mode",
                    help="Activa para seleccionar varias filas y borrarlas. Desactiva para navegar pregunta a pregunta.",
                )

            if _bit:
                # Tabla a medida: agrupada por bloque, casillas para acciones en grupo, la fila abre la pregunta
                _recs = df_filt.to_dict("records")
                _recs.sort(key=lambda r: (orden_bloque(str(r.get("bloque", ""))), _nsort(str(r.get("Tema", ""))),
                                          str(r.get("ID_Pregunta", ""))))
                _gmodo = selector_agrupar("man_grp")
                _meta = {}
                for r in _recs:
                    g = grupo_pregunta(r, _gmodo)
                    m = _meta.setdefault(g, [0, 0, 0])
                    m[0] += 1
                    m[1] += bool(str(r.get("usada", "") or "").strip())
                    m[2] += bool(str(r.get("solucion", "") or "").strip() not in ("", "nan", "None"))
                _ids_ok = set(df_filt["ID_Pregunta"])
                _checked = [i for i in st.session_state.get("man_checked", []) if i in _ids_ok]
                _rows = []
                for r in _recs:
                    g = grupo_pregunta(r, _gmodo)
                    _rows.append(qtable_row(r, grp=g, grp_meta=(f"{n_preg(_meta[g][0])} · {_meta[g][1]} usadas"
                                                                f" · {_meta[g][2]} con solución")))
                _bar_slot = st.container()   # barra de acciones: se rellena tras leer la tabla
                _act = qtable(_rows, "gestor", key="qt_gestor", height=540, checked=_checked,
                              reset=st.session_state.get("_man_chk_reset", 0),
                              collapse_default=True, toolbar=True,
                              foot="Pulsa una fila para abrir el editor · marca casillas para actuar sobre varias",
                              empty="No hay preguntas que coincidan con los filtros")
                if _act and _act.get("action") == "check":
                    _checked = [i for i in _act.get("ids", []) if i in _ids_ok]
                    st.session_state["man_checked"] = _checked
                elif _act and _act.get("action") == "open":
                    st.session_state["man_open_pid"] = _act["id"]
                    if _gest_ventana:
                        _man_open_pid = _act["id"]
                n_sel          = len(_checked)
                sel_pids_multi = list(_checked)
                _op = st.session_state.get("man_open_pid")
                sel_pid        = _op if _op in _ids_ok and not _checked else None
                if _checked:
                    with _bar_slot:
                        _barra_acciones(list(_checked))
            else:
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
                    selection_mode="multi-row" if _multi_mode else "single-row",
                    on_select="rerun",
                    key="man_df_sel" if not _man_nonce else f"man_df_sel_{_man_nonce}",
                    height=400,
                    column_config={
                        "ID":        st.column_config.TextColumn("ID", width=150 if _bit else 115),
                        "Bloque":    st.column_config.TextColumn("Bloque", width=100 if _bit else 115),
                        "T":         st.column_config.TextColumn("Tema" if _bit else "T", width=56 if _bit else 32),
                        "Dif.":      st.column_config.TextColumn("Dificultad" if _bit else "Dif.", width=88 if _bit else 55),
                        "Usado":     st.column_config.TextColumn("Último uso" if _bit else "Usado", width=104 if _bit else 80),
                        "Sol.":      st.column_config.TextColumn("Solución" if _bit else "Sol.", width=76 if _bit else 40),
                        "Enunciado": st.column_config.TextColumn("Enunciado", width="large"),
                    },
                )

                sel_rows = sel.selection.rows if sel.selection else []
                n_sel    = len(sel_rows)
                sel_pid  = (df_filt.iloc[sel_rows[0]]["ID_Pregunta"]
                            if n_sel == 1 else None)
                sel_pids_multi = ([df_filt.iloc[r]["ID_Pregunta"] for r in sel_rows]
                                  if n_sel > 1 else [])
                if _gest_ventana:   # abrir solo cuando cambia la fila elegida
                    if sel_pid and sel_pid != st.session_state.get("_man_last_pid"):
                        _man_open_pid = sel_pid
                    st.session_state["_man_last_pid"] = sel_pid
                    if not sel_pid and n_sel <= 1:
                        st.caption("Marca la casilla de una fila para abrir la pregunta en una ventana. "
                                   "Con «Selección múltiple» puedes borrar varias a la vez.")

            if not _bit:
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
                                notify(" | ".join(msgs)); reload_db(); st.rerun()
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
                                    notify(msg); reload_db(); st.rerun()
                                else:
                                    st.error(msg)

        # ── Panel derecho: preview (1 fila) o acción multi (N filas) ─────────
        with col_preview:

            # ══ MULTI-SELECT: N > 1 (en Bitácora, desde 1 casilla) ══════════
            if n_sel > 1 and not _bit:
                st.markdown(
                    f"<div style='background:var(--note-bg, #fff3cd);border-left:4px solid var(--ui-warn, #f39c12);"
                    f"border-radius:0 8px 8px 0;padding:14px 18px;margin-bottom:12px'>"
                    f"<div style='font-size:1.05em;font-weight:700;color:var(--note-text, #856404)'>"
                    f"📋 {n_sel} preguntas seleccionadas</div>"
                    f"<div style='font-size:0.82em;color:var(--note-text, #78350f);margin-top:4px'>"
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
                        st.session_state["man_checked"] = []
                        st.session_state["_man_chk_reset"] = st.session_state.get("_man_chk_reset", 0) + 1
                        notify(msg); reload_db(); st.rerun()
                    else:
                        st.error(msg)

            # ══ SINGLE-SELECT: preview completo (panel) o botón para reabrir la ventana ══
            elif sel_pid:
                if _gest_ventana:
                    if st.button(f"👁 Ver {sel_pid}", key="btn_man_view"):
                        _man_open_pid = sel_pid
                else:
                    _render_gest_preview(sel_pid, dict(df_total[df_total["ID_Pregunta"] == sel_pid].iloc[0]))

            # ══ NADA SELECCIONADO ═════════════════════════════════════════════
            elif _gest_ventana:
                pass   # el aviso está justo debajo de la tabla
            else:
                st.markdown(
                    "<div style='text-align:center;padding:40px 20px;color:var(--muted, #888);"
                    "border:2px dashed var(--ui-border, #dee2e6);border-radius:10px;margin-top:10px'>"
                    "<div style='font-size:2em;margin-bottom:8px'>👆</div>"
                    "<div style='font-weight:600'>Haz clic en una fila para previsualizarla</div>"
                    "<div style='font-size:0.85em;margin-top:4px'>"
                    "Selecciona varias filas para borrarlas en grupo</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        # ── Ventanas (solo una por ejecución) ──────────────────────────────
        if _gest_ventana:
            _pend = st.session_state.pop("_man_open", None)
            if _pend:
                _kind, _pid = _pend
                _r = df_total[df_total["ID_Pregunta"] == _pid]
                if not _r.empty:
                    if _kind == "edit":
                        _dialog_editar_pregunta(_pid, dict(_r.iloc[0]), _acciones_editor)
                    else:
                        _dialog_solucion(_pid, dict(_r.iloc[0]))
            elif _man_open_pid:
                if _bit:   # Bitácora: la fila abre directamente el editor (con Duplicar / Eliminar)
                    _r = df_total[df_total["ID_Pregunta"] == _man_open_pid]
                    if not _r.empty:
                        _dialog_editar_pregunta(_man_open_pid, dict(_r.iloc[0]), _acciones_editor)
                else:
                    _dialog_gest_preview(_man_open_pid)

    if not _bit:
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
                _ui_importar_json()

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 · ESTADÍSTICAS
# ─────────────────────────────────────────────────────────────────────────────
with tab_stat:
  if get_estilo() == "bitacora" and not df_total.empty:
    _estadisticas_bitacora(df_total)
  else:
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.error("Instala plotly: `pip install plotly`")
        go = None

    df = df_total
    if df.empty:
        st.info("Sin datos para mostrar.")
    elif go is None:
        pass
    else:
        def _sol_count(series) -> int:
            """Cuenta filas con solución real en una columna solucion."""
            s = series.fillna("").astype(str)
            return int((s.str.strip().ne("") & ~s.isin(["nan", "None"])).sum())

        total   = len(df)
        nunca   = int((df["usada"] == "").sum())
        usadas  = total - nunca
        n_sol_g = _sol_count(df["solucion"]) if "solucion" in df.columns else 0
        pct_uso = int(usadas / total * 100) if total else 0
        pct_sol = int(n_sol_g / total * 100) if total else 0

        _PLT_CFG = dict(
            plot_bgcolor="rgba(248,249,250,0.6)",
            paper_bgcolor="white",
            font=dict(family="Inter, sans-serif", size=12, color="#2c3e50"),
            margin=dict(l=10, r=10, t=36, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                        font=dict(size=11)),
        )

        # ── KPI cards ─────────────────────────────────────────────────────────
        mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
        mc1.markdown(
            f"<div class='stat-card'><div class='stat-num'>{total}</div>"
            f"<div class='stat-label'>📚 Total</div></div>",
            unsafe_allow_html=True)
        mc2.markdown(
            f"<div class='stat-card ok'><div class='stat-num' style='color:var(--ui-ok, #27ae60)'>{usadas}</div>"
            f"<div class='stat-label'>✅ Usadas</div></div>",
            unsafe_allow_html=True)
        mc3.markdown(
            f"<div class='stat-card warn'><div class='stat-num' style='color:var(--ui-warn, #f39c12)'>{nunca}</div>"
            f"<div class='stat-label'>🆕 Sin usar</div></div>",
            unsafe_allow_html=True)
        mc4.markdown(
            f"<div class='stat-card'><div class='stat-num'>{len(bloques)}</div>"
            f"<div class='stat-label'>📦 Bloques</div></div>",
            unsafe_allow_html=True)
        mc5.markdown(
            f"<div class='stat-card used'><div class='stat-num' style='color:var(--ui-used, #8e44ad)'>{pct_uso}%</div>"
            f"<div class='stat-label'>🎯 Cobertura</div></div>",
            unsafe_allow_html=True)
        _sol_cls = "ok" if pct_sol >= 60 else "warn"
        _sol_clr = "#27ae60" if pct_sol >= 60 else "#f39c12"
        mc6.markdown(
            f"<div class='stat-card {_sol_cls}'>"
            f"<div class='stat-num' style='color:{_sol_clr}'>{pct_sol}%</div>"
            f"<div class='stat-label'>📖 Con solución</div></div>",
            unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Selector de vista ──────────────────────────────────────────────────
        vista_opts = ["📊 Resumen global"] + bloques
        sv1, _ = st.columns([3, 6])
        vista = sv1.selectbox(
            "Vista:", vista_opts, key="stat_vista", label_visibility="collapsed",
            format_func=lambda b: b if b == "📊 Resumen global" else f"📦 {nombre_bloque(b)}"
        )
        st.markdown("---")

        # ── Calcular stats por bloque (siempre necesario) ─────────────────────
        blq_stats = []
        for blq in bloques:
            dfb   = df[df["bloque"] == blq]
            n_tot = len(dfb)
            n_f   = int((dfb["dificultad"].str.lower() == "facil").sum())
            n_m   = int((dfb["dificultad"].str.lower() == "media").sum())
            n_d   = int((dfb["dificultad"].str.lower().isin(["dificil", "difícil"])).sum())
            n_us  = int((dfb["usada"] != "").sum())
            n_sol_b = _sol_count(dfb["solucion"]) if "solucion" in dfb.columns else 0
            blq_stats.append({
                "bloque": blq, "total": n_tot,
                "facil": n_f, "media": n_m, "dificil": n_d,
                "usadas": n_us, "sol": n_sol_b,
                "pct": int(n_us / n_tot * 100) if n_tot else 0,
            })

        # ══════════════════════════════════════════════════════════════════════
        if vista == "📊 Resumen global":
        # ══════════════════════════════════════════════════════════════════════

            col_a, col_b = st.columns([3, 2], gap="large")

            with col_a:
                st.markdown("#### Distribución por bloque y dificultad")
                blq_labels = [nombre_bloque(s["bloque"])[:42] for s in blq_stats]
                fig1 = go.Figure()
                for vals, name, color in [
                    ([s["facil"]   for s in blq_stats], "Fácil",   "#27ae60"),
                    ([s["media"]   for s in blq_stats], "Media",   "#f39c12"),
                    ([s["dificil"] for s in blq_stats], "Difícil", "#c0392b"),
                ]:
                    fig1.add_trace(go.Bar(
                        y=blq_labels, x=vals, name=name, orientation="h",
                        marker_color=color,
                        text=vals, textposition="inside", insidetextanchor="middle",
                        textfont=dict(color="white", size=11),
                        hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x}}<extra></extra>",
                    ))
                fig1.update_layout(
                    **_PLT_CFG,
                    barmode="stack",
                    height=max(260, 48 * len(blq_stats) + 70),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                    xaxis=dict(title="Nº preguntas", gridcolor="#e9ecef"),
                    title=dict(text="", x=0.5),
                )
                st.plotly_chart(fig1, use_container_width=True)

                st.markdown("#### Cobertura de uso por bloque")
                fig_cob = go.Figure()
                for vals, name, color in [
                    ([s["usadas"]           for s in blq_stats], "Usadas",   "#8e44ad"),
                    ([s["total"]-s["usadas"] for s in blq_stats], "Sin usar", "#bdc3c7"),
                ]:
                    fig_cob.add_trace(go.Bar(
                        y=blq_labels, x=vals, name=name, orientation="h",
                        marker_color=color,
                        text=vals, textposition="inside", insidetextanchor="middle",
                        textfont=dict(color="white", size=11),
                        hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x}}<extra></extra>",
                    ))
                fig_cob.update_layout(
                    **_PLT_CFG,
                    barmode="stack",
                    height=max(220, 40 * len(blq_stats) + 70),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                    xaxis=dict(title="Nº preguntas", gridcolor="#e9ecef"),
                )
                st.plotly_chart(fig_cob, use_container_width=True)

            with col_b:
                st.markdown("#### Dificultad global")
                n_f_g = sum(s["facil"]   for s in blq_stats)
                n_m_g = sum(s["media"]   for s in blq_stats)
                n_d_g = sum(s["dificil"] for s in blq_stats)
                fig_d = go.Figure(data=[go.Pie(
                    labels=["Fácil", "Media", "Difícil"],
                    values=[n_f_g, n_m_g, n_d_g],
                    hole=0.55,
                    marker=dict(colors=["#27ae60", "#f39c12", "#c0392b"],
                                line=dict(color="white", width=2)),
                    textinfo="percent+label",
                    hoverinfo="label+percent+value",
                    pull=[0.03, 0.03, 0.03],
                )])
                fig_d.update_layout(
                    paper_bgcolor="white",
                    height=300,
                    margin=dict(l=10, r=10, t=10, b=10),
                    legend=dict(orientation="h", yanchor="top", y=-0.05, x=0.1),
                    annotations=[dict(
                        text=f"<b>{total}</b><br>pregs.",
                        x=0.5, y=0.5, font_size=14, showarrow=False,
                        font=dict(color="#2c3e50"),
                    )],
                )
                st.plotly_chart(fig_d, use_container_width=True)

                st.markdown("#### Soluciones completadas")
                n_sol_list  = [s["sol"]           for s in blq_stats]
                n_sin_sol   = [s["total"]-s["sol"] for s in blq_stats]
                fig_sol = go.Figure()
                fig_sol.add_trace(go.Bar(
                    y=blq_labels, x=n_sol_list, name="Con solución",
                    orientation="h", marker_color="#3498db",
                    hovertemplate="<b>%{y}</b><br>Con solución: %{x}<extra></extra>",
                ))
                fig_sol.add_trace(go.Bar(
                    y=blq_labels, x=n_sin_sol, name="Sin solución",
                    orientation="h", marker_color="#e0e7ef",
                    hovertemplate="<b>%{y}</b><br>Sin solución: %{x}<extra></extra>",
                ))
                fig_sol.update_layout(
                    **_PLT_CFG,
                    barmode="stack",
                    height=max(220, 40 * len(blq_stats) + 70),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                    xaxis=dict(title="Nº preguntas", gridcolor="#e9ecef"),
                )
                st.plotly_chart(fig_sol, use_container_width=True)

        # ══════════════════════════════════════════════════════════════════════
        else:  # Bloque específico
        # ══════════════════════════════════════════════════════════════════════
            sel_blq   = vista
            dfb       = df[df["bloque"] == sel_blq]
            n_tot_b   = len(dfb)
            n_us_b    = int((dfb["usada"] != "").sum())
            n_nu_b    = n_tot_b - n_us_b
            temas_b   = sorted(dfb["Tema"].unique().tolist(), key=_nsort)
            n_temas_b = len(temas_b)
            n_sol_b   = _sol_count(dfb["solucion"]) if "solucion" in dfb.columns else 0
            pct_sol_b = int(n_sol_b / n_tot_b * 100) if n_tot_b else 0
            pct_us_b  = int(n_us_b / n_tot_b * 100) if n_tot_b else 0

            # KPI cards del bloque
            bc1, bc2, bc3, bc4, bc5 = st.columns(5)
            bc1.markdown(
                f"<div class='stat-card'><div class='stat-num'>{n_tot_b}</div>"
                f"<div class='stat-label'>📚 Total</div></div>",
                unsafe_allow_html=True)
            bc2.markdown(
                f"<div class='stat-card ok'><div class='stat-num' style='color:var(--ui-ok, #27ae60)'>{n_us_b}</div>"
                f"<div class='stat-label'>✅ Usadas</div></div>",
                unsafe_allow_html=True)
            bc3.markdown(
                f"<div class='stat-card warn'><div class='stat-num' style='color:var(--ui-warn, #f39c12)'>{n_nu_b}</div>"
                f"<div class='stat-label'>🆕 Sin usar</div></div>",
                unsafe_allow_html=True)
            bc4.markdown(
                f"<div class='stat-card'><div class='stat-num'>{n_temas_b}</div>"
                f"<div class='stat-label'>📌 Temas</div></div>",
                unsafe_allow_html=True)
            _sb_cls = "ok" if pct_sol_b >= 60 else "warn"
            _sb_clr = "#27ae60" if pct_sol_b >= 60 else "#f39c12"
            bc5.markdown(
                f"<div class='stat-card {_sb_cls}'>"
                f"<div class='stat-num' style='color:{_sb_clr}'>"
                f"{pct_sol_b}%</div>"
                f"<div class='stat-label'>📖 Con solución</div></div>",
                unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Calcular datos por tema
            tema_data = []
            for tema in temas_b:
                dft   = dfb[dfb["Tema"].astype(str) == str(tema)]
                n_t   = len(dft)
                n_ft  = int((dft["dificultad"].str.lower() == "facil").sum())
                n_mt  = int((dft["dificultad"].str.lower() == "media").sum())
                n_dt  = int((dft["dificultad"].str.lower().isin(["dificil", "difícil"])).sum())
                n_ut  = int((dft["usada"] != "").sum())
                n_st  = _sol_count(dft["solucion"]) if "solucion" in dft.columns else 0
                tema_data.append({
                    "tema": tema, "n": n_t,
                    "facil": n_ft, "media": n_mt, "dificil": n_dt,
                    "usadas": n_ut, "sol": n_st,
                })
            tema_labels = [nombre_tema(str(t["tema"]))[:45] for t in tema_data]

            col_c, col_d = st.columns([3, 2], gap="large")

            with col_c:
                st.markdown(f"#### Distribución por tema — {nombre_bloque(sel_blq)}")
                fig_t = go.Figure()
                for vals, name, color in [
                    ([t["facil"]   for t in tema_data], "Fácil",   "#27ae60"),
                    ([t["media"]   for t in tema_data], "Media",   "#f39c12"),
                    ([t["dificil"] for t in tema_data], "Difícil", "#c0392b"),
                ]:
                    fig_t.add_trace(go.Bar(
                        y=tema_labels, x=vals, name=name, orientation="h",
                        marker_color=color,
                        text=vals, textposition="inside", insidetextanchor="middle",
                        textfont=dict(color="white", size=10),
                        hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x}}<extra></extra>",
                    ))
                fig_t.update_layout(
                    **_PLT_CFG,
                    barmode="stack",
                    height=max(280, 40 * len(tema_data) + 90),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
                    xaxis=dict(title="Nº preguntas", gridcolor="#e9ecef"),
                )
                st.plotly_chart(fig_t, use_container_width=True)

                st.markdown("#### Uso por tema")
                fig_uso = go.Figure()
                for vals, name, color in [
                    ([t["usadas"]       for t in tema_data], "Usadas",   "#8e44ad"),
                    ([t["n"]-t["usadas"] for t in tema_data], "Sin usar", "#bdc3c7"),
                ]:
                    fig_uso.add_trace(go.Bar(
                        y=tema_labels, x=vals, name=name, orientation="h",
                        marker_color=color,
                        text=vals, textposition="inside", insidetextanchor="middle",
                        textfont=dict(color="white", size=10),
                        hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x}}<extra></extra>",
                    ))
                fig_uso.update_layout(
                    **_PLT_CFG,
                    barmode="stack",
                    height=max(280, 40 * len(tema_data) + 90),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
                    xaxis=dict(title="Nº preguntas", gridcolor="#e9ecef"),
                )
                st.plotly_chart(fig_uso, use_container_width=True)

            with col_d:
                st.markdown("#### Dificultad en el bloque")
                n_f_b = int((dfb["dificultad"].str.lower() == "facil").sum())
                n_m_b = int((dfb["dificultad"].str.lower() == "media").sum())
                n_d_b = int((dfb["dificultad"].str.lower().isin(["dificil", "difícil"])).sum())
                fig_d2 = go.Figure(data=[go.Pie(
                    labels=["Fácil", "Media", "Difícil"],
                    values=[n_f_b, n_m_b, n_d_b],
                    hole=0.55,
                    marker=dict(colors=["#27ae60", "#f39c12", "#c0392b"],
                                line=dict(color="white", width=2)),
                    textinfo="percent+label",
                    hoverinfo="label+percent+value",
                    pull=[0.03, 0.03, 0.03],
                )])
                fig_d2.update_layout(
                    paper_bgcolor="white",
                    height=290,
                    margin=dict(l=10, r=10, t=10, b=10),
                    legend=dict(orientation="h", yanchor="top", y=-0.05, x=0.1),
                    annotations=[dict(
                        text=f"<b>{n_tot_b}</b><br>pregs.",
                        x=0.5, y=0.5, font_size=14, showarrow=False,
                        font=dict(color="#2c3e50"),
                    )],
                )
                st.plotly_chart(fig_d2, use_container_width=True)

                st.markdown("#### Soluciones por tema")
                fig_sol_t = go.Figure()
                fig_sol_t.add_trace(go.Bar(
                    y=tema_labels, x=[t["sol"] for t in tema_data],
                    name="Con solución", orientation="h",
                    marker_color="#3498db",
                    hovertemplate="<b>%{y}</b><br>Con solución: %{x}<extra></extra>",
                ))
                fig_sol_t.add_trace(go.Bar(
                    y=tema_labels, x=[t["n"] - t["sol"] for t in tema_data],
                    name="Sin solución", orientation="h",
                    marker_color="#e0e7ef",
                    hovertemplate="<b>%{y}</b><br>Sin solución: %{x}<extra></extra>",
                ))
                fig_sol_t.update_layout(
                    **_PLT_CFG,
                    barmode="stack",
                    height=max(280, 40 * len(tema_data) + 90),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
                    xaxis=dict(title="Nº preguntas", gridcolor="#e9ecef"),
                )
                st.plotly_chart(fig_sol_t, use_container_width=True)


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
        f"<div class='stat-card ok'><div class='stat-num' style='color:var(--ui-ok, #27ae60)'>{n_sol_con}</div>"
        f"<div class='stat-label'>📖 Con solución</div></div>",
        unsafe_allow_html=True)
    sm2.markdown(
        f"<div class='stat-card warn'><div class='stat-num' style='color:var(--ui-warn, #f39c12)'>{n_sol_sin}</div>"
        f"<div class='stat-label'>⬜ Sin solución</div></div>",
        unsafe_allow_html=True)
    sm3.markdown(
        f"<div class='stat-card'><div class='stat-num' style='color:var(--primary, #3498db)'>{pct_sol}%</div>"
        f"<div class='stat-label'>✅ Completado</div></div>",
        unsafe_allow_html=True)

    # Barra de progreso global
    bar_w = pct_sol
    bar_r = 100 - bar_w
    st.markdown(
        f"<div style='margin:12px 0 4px 0'>"
        f"<div style='display:flex;justify-content:space-between;font-size:0.78em;color:var(--muted, #666);margin-bottom:3px'>"
        f"<span>Progreso global de soluciones</span><span style='font-weight:700'>{n_sol_con}/{n_sol_total}</span></div>"
        f"<div style='background:var(--track, #e9ecef);border-radius:6px;height:12px;overflow:hidden'>"
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
            f"<div style='font-size:0.82em;color:var(--text2, #555);margin-bottom:6px'>"
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
                "<div style='background:var(--note-bg, #fefce8);border-left:3px solid var(--ui-warn, #f59e0b);"
                "border-radius:0 8px 8px 0;padding:8px 12px;margin-top:4px;"
                "font-size:0.85em;color:var(--note-text, #78350f)'>"
                f"<b style='color:var(--note-text, #92400e)'>📝 Notas:</b> {notas_s}</div>",
                unsafe_allow_html=True
            )

        # ── Plantillas de inicio ──────────────────────────────────────────────
        sol_key_b = f"sol_batch_txt_{pid_s}"
        st.markdown(
            "<span style='font-size:0.82em;color:var(--muted, #888);font-weight:600'>PLANTILLA RÁPIDA</span>",
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
                "color:var(--text, #2c3e50);padding:12px;background:var(--primary-soft, #f0f9ff);"
                "border-left:3px solid var(--primary, #3498db);border-radius:0 8px 8px 0;line-height:1.65'>"
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
                notify("✅ Solución guardada.")
                st.rerun()
            else:
                st.error(f"❌ {msg_s}")
