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
    bloques_disponibles, temas_de_bloque,
    es_uso_antiguo, render_question_card_html, mathjax_html, _nsort,
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
        ed_tema = st.selectbox("Tema", temas_d, index=tem_idx, key="dlg_tema")

        dif_opts = ["Facil", "Media", "Dificil"]
        dif_cur  = str(row.get("dificultad", "Media")).capitalize()
        dif_idx  = dif_opts.index(dif_cur) if dif_cur in dif_opts else 1
        ed_dif   = st.selectbox("Dificultad", dif_opts, index=dif_idx, key="dlg_dif")

        corr_opts = ["A", "B", "C", "D"]
        corr_cur  = str(row.get("letra_correcta", "A")).upper()
        corr_idx  = corr_opts.index(corr_cur) if corr_cur in corr_opts else 0
        ed_corr   = st.selectbox("Respuesta correcta", corr_opts, index=corr_idx, key="dlg_corr")

        # Fecha de uso — date_input con soporte a vacío
        import datetime as _dt
        _usada_raw = str(row.get("usada", "") or "").strip()
        _usada_val = None
        if _usada_raw and _usada_raw not in ('nan', 'NaT', 'None'):
            try: _usada_val = _dt.datetime.strptime(_usada_raw[:10], "%Y-%m-%d").date()
            except Exception: pass
        ed_usada_date = st.date_input("Usada (fecha)", value=_usada_val, key="dlg_usada",
                                       help="Deja en blanco si la pregunta no ha sido usada")
        ed_usada = ed_usada_date.strftime("%Y-%m-%d") if ed_usada_date else ""
        if ed_usada and st.button("🗑 Borrar fecha", key="dlg_usada_clear"):
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
        ed_tema = st.selectbox("Tema", temas_d, index=tem_idx, key="stg_dlg_tema")
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
        ed_usada_date = st.date_input("Usada (fecha)", value=_usada_val, key="stg_dlg_usada",
                                      help="Opcional — si ya fue usada en un examen anterior")
        ed_usada = ed_usada_date.strftime("%Y-%m-%d") if ed_usada_date else ""
        if ed_usada and st.button("🗑 Borrar fecha", key="stg_dlg_usada_clear"):
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


st.title("🗄️ Gestor de Base de Datos")
st.caption(f"{len(st.session_state.df_preguntas)} preguntas · {len(st.session_state.bloques)} bloques"
           if st.session_state.db_connected else "Sin conexión a la base de datos")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos desde la barra lateral antes de continuar.")
    st.stop()

df_total: pd.DataFrame = st.session_state.df_preguntas
bloques = bloques_disponibles()

# ═════════════════════════════════════════════════════════════════════════════
# PESTAÑA PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════
tab_add, tab_imp, tab_man, tab_stat = st.tabs(
    ["➕ Añadir", "📥 Importar", "✏️ Gestionar", "📊 Estadísticas"]
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 · AÑADIR
# ─────────────────────────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Añadir nueva pregunta")

    col_cfg, col_form = st.columns([1, 2])

    with col_cfg:
        bloque_add = st.selectbox("Bloque", bloques, key="add_bloque")
        tema_add   = st.selectbox("Tema",   temas_de_bloque(bloque_add) or [str(i) for i in range(1,51)], key="add_tema")
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
                blk_df     = excel_dfs.get(bloque_add)

                if blk_df is None:
                    st.error(f"El bloque '{bloque_add}' no existe en el Excel.")
                else:
                    new_row = {col: "" for col in blk_df.columns}
                    new_row["ID_Pregunta"] = nid
                    for col in blk_df.columns:
                        cl = str(col).lower()
                        if "tema" in cl and "id" not in cl:
                            new_row[col] = tema_add
                        elif "dificultad" in cl:
                            new_row[col] = dif_add
                        elif "correcta" in cl or "resp" in cl:
                            new_row[col] = corr_add
                        elif "enunciado" in cl:
                            new_row[col] = enun_add.strip()
                    # Opciones
                    enun_idx = next((i for i, c in enumerate(blk_df.columns) if "enunciado" in str(c).lower()), None)
                    if enun_idx is not None:
                        for j, op in enumerate(ops_add[:4]):
                            oi = enun_idx + 1 + j
                            if oi < len(blk_df.columns):
                                new_row[blk_df.columns[oi]] = op
                    excel_dfs[bloque_add] = pd.concat(
                        [blk_df, pd.DataFrame([new_row])], ignore_index=True
                    )
                    lib.guardar_excel_local(excel_path, excel_dfs)
                    st.success(f"✅ Pregunta guardada con ID: **{nid}**")
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
    bloque_imp = c1.selectbox("Bloque destino", bloques, key="imp_bloque")
    tema_imp   = c2.selectbox("Tema", temas_de_bloque(bloque_imp) or [str(i) for i in range(1, 51)], key="imp_tema")
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
                blk_df = excel_dfs.get(blk)
                if blk_df is None: skipped += 1; continue
                nid, _ = lib.generar_siguiente_id(df_total, blk, p_data["tema"])
                new_row = {col: "" for col in blk_df.columns}
                new_row["ID_Pregunta"] = nid
                for col in blk_df.columns:
                    cl = str(col).lower()
                    if "tema" in cl and "id" not in cl: new_row[col] = p_data["tema"]
                    elif "dificultad" in cl:             new_row[col] = p_data["dificultad"]
                    elif "correcta" in cl or "resp" in cl: new_row[col] = p_data["letra_correcta"]
                    elif "enunciado" in cl:              new_row[col] = p_data["enunciado"]
                    elif "usada" in cl or "fecha" in cl: new_row[col] = p_data["usada"]
                enun_idx = next((ci for ci, c in enumerate(blk_df.columns) if "enunciado" in str(c).lower()), None)
                if enun_idx is not None:
                    for j, op in enumerate(p_data["opciones_list"][:4]):
                        oi = enun_idx + 1 + j
                        if oi < len(blk_df.columns): new_row[blk_df.columns[oi]] = op
                    ci = enun_idx + 5
                    if ci < len(blk_df.columns): new_row[blk_df.columns[ci]] = p_data["letra_correcta"]
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
                reload_db(); st.rerun()
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
    fc1, fc2, fc3, fc4 = st.columns(4)
    f_bloque = fc1.selectbox("Bloque", ["Todos"] + bloques, key="man_f_bloque")
    temas_disponibles = (
        temas_de_bloque(f_bloque) if f_bloque != "Todos"
        else sorted(df_total["Tema"].unique().tolist(), key=_nsort)
    )
    f_tema   = fc2.selectbox("Tema", ["Todos"] + [str(t) for t in temas_disponibles], key="man_f_tema")
    f_dif    = fc3.selectbox("Dificultad", ["Todas", "Facil", "Media", "Dificil"], key="man_f_dif")
    f_uso    = fc4.selectbox("Uso", ["Todos", "Nunca usada", "Usada", "Usada >6 meses", "Usada >12 meses"], key="man_f_uso")
    f_search = st.text_input("🔍 Buscar en enunciado", placeholder="Texto a buscar...", key="man_search")

    # Aplicar filtros
    df_filt = df_total.copy()
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
        df_filt = df_filt[mask]

    # Contador compacto
    n_filt = len(df_filt)
    pct_filt = int(n_filt / len(df_total) * 100) if len(df_total) else 0
    st.markdown(
        f"<div style='font-size:0.82em;color:#666;margin-bottom:8px'>"
        f"Mostrando <b style='color:#2c3e50'>{n_filt}</b> de {len(df_total)} preguntas"
        f"{'  ·  <b style=\"color:#3498db\">' + str(pct_filt) + '% del total</b>' if pct_filt < 100 else ''}"
        f"</div>",
        unsafe_allow_html=True
    )

    # ── Layout 2 columnas: tabla (izq.) + preview (der.) ─────────────────────
    sel_pid: str | None = None   # ID de la pregunta seleccionada (single-row)

    if df_filt.empty:
        st.info("No hay preguntas que coincidan con los filtros.")
    else:
        col_table, col_preview = st.columns([3, 2], gap="medium")

        # ── Columna izquierda: tabla (navegación single-click) ───────────────
        with col_table:
            display_df = df_filt[["ID_Pregunta", "bloque", "Tema", "dificultad", "usada", "enunciado"]].copy()
            display_df["enunciado"] = display_df["enunciado"].str[:130]
            display_df["usada"]     = display_df["usada"].apply(lambda v: v if v else "—")
            display_df.columns      = ["ID", "Bloque", "T", "Dif.", "Usado", "Enunciado"]
            display_df              = display_df.reset_index(drop=True)

            sel = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",   # ← single-row para navegar
                on_select="rerun",
                key="man_df_sel",
                height=420,
                column_config={
                    "ID":       st.column_config.TextColumn("ID", width=130),
                    "Bloque":   st.column_config.TextColumn("Bloque", width=85),
                    "T":        st.column_config.TextColumn("T", width=35),
                    "Dif.":     st.column_config.TextColumn("Dif.", width=58),
                    "Usado":    st.column_config.TextColumn("Usado", width=80),
                    "Enunciado":st.column_config.TextColumn("Enunciado", width="large"),
                },
            )

            sel_rows = sel.selection.rows if sel.selection else []
            sel_pid  = df_filt.iloc[sel_rows[0]]["ID_Pregunta"] if sel_rows else None

            # ── Operaciones masivas (trabajan sobre df_filt, no sobre selección) ──
            with st.expander(
                f"⚙️ Operaciones masivas — aplicar a las {n_filt} preguntas filtradas",
                expanded=False
            ):
                bulk_ids = df_filt["ID_Pregunta"].tolist()
                st.caption(
                    "Estas operaciones afectan a **todas las preguntas visibles** "
                    f"según los filtros activos ({n_filt} preguntas). "
                    "Usa los filtros de arriba para acotar el conjunto antes de aplicar."
                )
                bulk_tab1, bulk_tab2, bulk_tab3 = st.tabs(
                    ["Cambiar Tema/Dificultad", "Buscar y Reemplazar", "Eliminar"]
                )

                with bulk_tab1:
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
                            st.success(" | ".join(msgs)); reload_db(); st.rerun()
                        else:
                            st.warning("No hay cambios que aplicar.")

                with bulk_tab2:
                    fr1, fr2 = st.columns(2)
                    bulk_find = fr1.text_input("Buscar texto en enunciado", key="bulk_find")
                    bulk_repl = fr2.text_input("Reemplazar por", key="bulk_repl")
                    if st.button(f"🔄 Reemplazar en {n_filt} preguntas", key="btn_bulk_repl"):
                        if not bulk_find.strip():
                            st.warning("Escribe el texto a buscar.")
                        else:
                            ok, msg = lib.reemplazar_texto_masivo(
                                st.session_state.excel_path, st.session_state.excel_dfs,
                                bulk_ids, bulk_find, bulk_repl)
                            if ok: st.success(msg); reload_db(); st.rerun()
                            else:  st.error(msg)

                with bulk_tab3:
                    st.warning(
                        f"⚠️ Se eliminarán **{n_filt} preguntas** de forma permanente "
                        "(se creará un backup antes)."
                    )
                    confirm_del = st.checkbox(
                        f"Confirmo que quiero eliminar estas {n_filt} preguntas",
                        key="bulk_del_confirm"
                    )
                    if st.button("🗑️ Eliminar preguntas filtradas", type="primary",
                                 disabled=not confirm_del, key="btn_bulk_del"):
                        ok, msg = lib.eliminar_preguntas_excel_local(
                            st.session_state.excel_path, st.session_state.excel_dfs, bulk_ids)
                        if ok: st.success(msg); reload_db(); st.rerun()
                        else:  st.error(msg)

        # ── Columna derecha: preview + botones de acción ─────────────────────
        with col_preview:
            if sel_pid:
                row_d     = dict(df_total[df_total["ID_Pregunta"] == sel_pid].iloc[0])
                card_html = render_question_card_html(row_d, show_sol=True)
                st.markdown(card_html, unsafe_allow_html=True)

                # ── Botón MathJax ──────────────────────────────────────────
                _mjax_key = f"mjax_gest_{sel_pid}"
                _mj1, _mj2 = st.columns([2, 3])
                if _mj1.button("∑ Renderizar LaTeX", key=f"mjax_btn_{sel_pid}",
                                use_container_width=True):
                    st.session_state[_mjax_key] = True
                if st.session_state.get(_mjax_key, False):
                    if _mj2.button("✖ Cerrar LaTeX", key=f"mjax_close_{sel_pid}",
                                   use_container_width=True):
                        st.session_state[_mjax_key] = False
                        st.rerun()
                    stcomponents.html(mathjax_html(card_html), height=500, scrolling=True)

                bc1, bc2 = st.columns(2)
                if bc1.button("✏️ Editar", type="primary", use_container_width=True,
                              key="btn_edit_q"):
                    _dialog_editar_pregunta(sel_pid, row_d)

                if bc2.button("📋 Duplicar", use_container_width=True, key="btn_dup_q"):
                    blk    = row_d["bloque"]
                    tema_d = str(row_d.get("Tema", "1"))
                    nid, _ = lib.generar_siguiente_id(df_total, blk, tema_d)
                    blk_df = st.session_state.excel_dfs.get(blk)
                    if blk_df is not None:
                        new_row_dup = {col: "" for col in blk_df.columns}
                        new_row_dup["ID_Pregunta"] = nid
                        for col in blk_df.columns:
                            cl = str(col).lower()
                            if "enunciado" in cl:
                                new_row_dup[col] = str(row_d.get("enunciado", "")) + " (COPIA)"
                            elif "tema" in cl and "id" not in cl:
                                new_row_dup[col] = tema_d
                            elif "dificultad" in cl:
                                new_row_dup[col] = row_d.get("dificultad", "Media")
                            elif "correcta" in cl or "resp" in cl:
                                new_row_dup[col] = row_d.get("letra_correcta", "A")
                        enun_idx = next((ci for ci, c in enumerate(blk_df.columns)
                                         if "enunciado" in str(c).lower()), None)
                        if enun_idx is not None:
                            ops_dup = row_d.get("opciones_list", []) or []
                            for j, op in enumerate(ops_dup[:4]):
                                oi = enun_idx + 1 + j
                                if oi < len(blk_df.columns):
                                    new_row_dup[blk_df.columns[oi]] = op
                        st.session_state.excel_dfs[blk] = pd.concat(
                            [blk_df, pd.DataFrame([new_row_dup])], ignore_index=True)
                        lib.guardar_excel_local(st.session_state.excel_path,
                                                st.session_state.excel_dfs)
                        st.success(f"✅ Duplicada como **{nid}**")
                        reload_db()
                        st.rerun()
            else:
                st.markdown(
                    "<div style='text-align:center;padding:40px 20px;"
                    "color:#888;border:2px dashed #dee2e6;border-radius:10px;margin-top:10px'>"
                    "<div style='font-size:2em;margin-bottom:8px'>👆</div>"
                    "<div style='font-weight:600'>Haz clic en una fila</div>"
                    "<div style='font-size:0.85em;margin-top:4px'>para ver la pregunta aquí</div>"
                    "</div>",
                    unsafe_allow_html=True
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
            bloque_json = st.selectbox("Bloque destino", bloques, key="json_bloque")
            json_file   = st.file_uploader("Archivo JSON", type=["json"], key="json_uploader")
            if json_file and st.button("📥 Importar JSON", key="btn_imp_json"):
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tf:
                    tf.write(json_file.read())
                    tmp_json = tf.name
                nuevas, dupes = lib.importar_preguntas_json(tmp_json, bloque_json, df_total)
                os.unlink(tmp_json)
                if nuevas:
                    blk_df = st.session_state.excel_dfs.get(bloque_json)
                    if blk_df is not None:
                        for p in nuevas:
                            new_row = {col: "" for col in blk_df.columns}
                            new_row["ID_Pregunta"] = p["ID_Pregunta"]
                            for col in blk_df.columns:
                                cl = str(col).lower()
                                if "enunciado" in cl: new_row[col] = p.get("enunciado","")
                                elif "tema" in cl and "id" not in cl: new_row[col] = p.get("Tema","1")
                                elif "dificultad" in cl: new_row[col] = p.get("dificultad","Media")
                                elif "correcta" in cl or "resp" in cl: new_row[col] = p.get("letra_correcta","A")
                            blk_df = pd.concat([blk_df, pd.DataFrame([new_row])], ignore_index=True)
                        st.session_state.excel_dfs[bloque_json] = blk_df
                        lib.guardar_excel_local(st.session_state.excel_path, st.session_state.excel_dfs)
                        st.success(f"✅ {len(nuevas)} importadas, {dupes} duplicadas omitidas.")
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
        vista_opts = ["📊 Resumen global"] + [f"📦 {b}" for b in bloques]
        sv1, sv2 = st.columns([3, 6])
        vista = sv1.selectbox("🔍 Ver detalle:", vista_opts, key="stat_vista",
                               label_visibility="collapsed")

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
                    f"<td style='padding:8px 12px;font-weight:700;color:#2c3e50'>{s['bloque']}</td>"
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
            sel_blq = vista.replace("📦 ", "")
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
            st.markdown(f"#### 📌 Detalle por tema — {sel_blq}")

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
                    f"<td style='padding:7px 12px;font-weight:700;color:#2c3e50'>Tema {tema}</td>"
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

