"""
pages/3_Configuracion.py  –  Configuración de la base de datos.

Pestañas:
  1. General   – Datos de la asignatura (asignatura, grado, año, dpto, notas)
  2. Bloques   – Nombres descriptivos de bloques
  3. Temas     – Nombres de temas con contador de preguntas
  4. Backup    – Exportar / importar configuración como JSON
"""
import json
import io
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
    sync_bloques_gsheets, sync_hoja_gsheets, reload_db,
)

st.set_page_config(page_title="Configuración · Exámenes UCM", page_icon="⚙️", layout="wide")
init_session_state()
handle_oauth_callback()
st.markdown(APP_CSS, unsafe_allow_html=True)
render_sidebar()

page_header("⚙️", "Configuración", "Nombres de bloques, temas y datos de la asignatura")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos desde la barra lateral antes de continuar.")
    st.stop()

# ── Asegurar que las hojas de config existen y están sincronizadas ────────────
dfs = st.session_state.excel_dfs
dfs = lib.init_cfg_from_data(dfs)
st.session_state.excel_dfs = dfs

bloques_list  = st.session_state.bloques
df_preguntas  = st.session_state.df_preguntas

tab_gen, tab_bloques, tab_temas, tab_backup = st.tabs(
    ["📋 General", "📦 Bloques", "📌 Temas", "💾 Backup config"]
)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · GENERAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_gen:
    st.markdown("#### Datos de la asignatura")
    st.caption(
        "Esta información aparecerá en los encabezados de los exámenes exportados "
        "y es visible en toda la app."
    )

    cfg_g = st.session_state.get("cfg_general", {})

    _CAMPOS_GEN = [
        ("asignatura",    "Asignatura",           "Física Médica, Radiología…"),
        ("grado",         "Grado / Máster",        "Grado en Medicina, Máster en Física Médica…"),
        ("anio_academico","Año académico",          "2025-2026"),
        ("departamento",  "Departamento",           "Dpto. de Física Atómica, Molecular y Nuclear…"),
        ("universidad",   "Universidad / Facultad", "UCM – Facultad de Medicina"),
    ]

    ga1, ga2 = st.columns(2)
    new_vals = {}
    for i, (key, label, placeholder) in enumerate(_CAMPOS_GEN):
        col = ga1 if i % 2 == 0 else ga2
        val = cfg_g.get(key, "")
        if str(val) in ("nan", "None"):
            val = ""
        new_vals[key] = col.text_input(label, value=val, placeholder=placeholder,
                                        key=f"cfg_gen_{key}")

    notas_v = cfg_g.get("notas", "")
    if str(notas_v) in ("nan", "None"):
        notas_v = ""
    new_vals["notas"] = st.text_area(
        "Notas generales",
        value=notas_v,
        height=140,
        placeholder="Descripción del curso, año académico, observaciones generales…",
        key="cfg_notas_area",
    )

    if st.button("💾 Guardar datos generales", type="primary", key="btn_save_gen"):
        cfg_g_new = {**cfg_g, **new_vals}
        dfs = lib.save_cfg_general(st.session_state.excel_dfs, cfg_g_new)
        dfs = _load_cfg(dfs)
        st.session_state.excel_dfs   = dfs
        st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
        path = st.session_state.get("excel_path", "")
        if path:
            lib.guardar_excel_local(path, dfs)
        sync_hoja_gsheets(lib.CFG_GENERAL_SHEET)
        st.success("✅ Datos generales guardados.")
        st.rerun()

    # Vista previa del encabezado de examen
    saved_g = st.session_state.get("cfg_general", {})
    asig = saved_g.get("asignatura", "") or ""
    grad = saved_g.get("grado", "") or ""
    anio = saved_g.get("anio_academico", "") or ""
    dept = saved_g.get("departamento", "") or ""
    univ = saved_g.get("universidad", "") or ""
    if any([asig, grad, anio, dept, univ]):
        st.divider()
        st.markdown("**Vista previa del encabezado de examen:**")
        header_lines = []
        if asig:  header_lines.append(f"**{asig}**")
        if grad:  header_lines.append(grad)
        if dept:  header_lines.append(dept)
        if univ:  header_lines.append(univ)
        if anio:  header_lines.append(f"Año académico: {anio}")
        st.markdown(
            "<div style='background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;"
            "padding:14px 20px;font-size:0.9em;line-height:1.8'>"
            + "<br>".join(header_lines) +
            "</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · BLOQUES
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

    # Añadir columna Nº preguntas (solo lectura)
    if not df_preguntas.empty and "bloque" in df_preguntas.columns:
        counts_b = df_preguntas.groupby("bloque").size().to_dict()
        cfg_b["N preguntas"] = cfg_b["Bloque"].apply(lambda b: counts_b.get(b, 0))
    else:
        cfg_b["N preguntas"] = 0

    edited_b = st.data_editor(
        cfg_b,
        column_config={
            "Bloque":       st.column_config.TextColumn("Bloque (ID interno)", disabled=True, width="medium"),
            "Descripcion":  st.column_config.TextColumn("Descripción", width="large",
                                                         help="Ej: Óptica, Electromagnetismo, Radiación Ionizante…"),
            "N preguntas":  st.column_config.NumberColumn("Preguntas", disabled=True, width="small"),
        },
        hide_index=True,
        use_container_width=True,
        key="editor_bloques",
        num_rows="fixed",
    )

    if st.button("💾 Guardar nombres de bloques", type="primary", key="btn_save_bloques"):
        # Guardar sin la columna de conteo
        save_b = edited_b[["Bloque", "Descripcion"]].copy()
        dfs = lib.save_cfg_bloques(st.session_state.excel_dfs, save_b)
        dfs = _load_cfg(dfs)
        st.session_state.excel_dfs  = dfs
        st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
        path = st.session_state.get("excel_path", "")
        if path:
            lib.guardar_excel_local(path, dfs)
        sync_hoja_gsheets(lib.CFG_BLOQUES_SHEET)
        st.success("✅ Nombres de bloques guardados.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · TEMAS
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

    # Añadir columna Nº preguntas (solo lectura)
    if not df_preguntas.empty and "Tema" in df_preguntas.columns:
        counts_t = df_preguntas.groupby(df_preguntas["Tema"].astype(str).str.replace(r"\.0$", "", regex=True)).size().to_dict()
        cfg_t["N preg."] = cfg_t["Tema"].apply(lambda t: counts_t.get(str(t), 0))
    else:
        cfg_t["N preg."] = 0

    # Filtro por bloque
    tf1, tf2 = st.columns([2, 4])
    f_blq     = tf1.selectbox("Filtrar por bloque:", ["Todos"] + bloques_list, key="cfg_t_blq")
    sin_nombre = tf2.checkbox("Mostrar solo temas sin nombre", key="cfg_t_sin_nombre", value=False)

    cfg_t_show = cfg_t.copy()
    if f_blq != "Todos":
        cfg_t_show = cfg_t_show[cfg_t_show["Bloque"] == f_blq]
    if sin_nombre:
        cfg_t_show = cfg_t_show[cfg_t_show["Nombre"].apply(
            lambda v: not str(v).strip() or str(v) in ("nan", "None", "")
        )]
    cfg_t_show = cfg_t_show.reset_index(drop=True)

    # Métricas rápidas
    n_con_nombre = int((cfg_t["Nombre"].apply(
        lambda v: bool(str(v).strip() and str(v) not in ("nan", "None", ""))
    )).sum())
    n_total_t = len(cfg_t)
    pct_t = int(n_con_nombre / n_total_t * 100) if n_total_t else 0

    tm1, tm2, tm3 = st.columns(3)
    tm1.metric("Total temas", n_total_t)
    tm2.metric("Con nombre", n_con_nombre)
    tm3.metric("Completado", f"{pct_t}%")

    edited_t = st.data_editor(
        cfg_t_show,
        column_config={
            "Tema":    st.column_config.TextColumn("Nº Tema", disabled=True, width="small"),
            "Nombre":  st.column_config.TextColumn("Nombre descriptivo", width="large",
                                                    help="Ej: Óptica geométrica, Ley de Faraday…"),
            "Bloque":  st.column_config.SelectboxColumn(
                "Bloque", options=bloques_list, width="medium",
                help="Bloque al que pertenece este tema"
            ),
            "N preg.": st.column_config.NumberColumn("Preguntas", disabled=True, width="small"),
        },
        hide_index=True,
        use_container_width=True,
        key="editor_temas",
        num_rows="fixed",
    )

    if st.button("💾 Guardar nombres de temas", type="primary", key="btn_save_temas"):
        # Reconstruir df completo combinando la vista editada con el resto
        edited_no_count = edited_t[["Tema", "Nombre", "Bloque"]].copy()
        if f_blq != "Todos" or sin_nombre:
            # identificar filas editadas por Tema
            edited_temas_set = set(edited_no_count["Tema"].astype(str))
            other = cfg_t[~cfg_t["Tema"].astype(str).isin(edited_temas_set)][["Tema", "Nombre", "Bloque"]]
            merged = pd.concat([other, edited_no_count], ignore_index=True)
        else:
            merged = edited_no_count

        # Reordenar por tema numérico
        try:
            import re as _re
            merged["_sort"] = merged["Tema"].apply(
                lambda t: [int(x) if x.isdigit() else x.lower()
                           for x in _re.split(r"(\d+)", str(t))]
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
        sync_hoja_gsheets(lib.CFG_TEMAS_SHEET)
        st.success("✅ Nombres de temas guardados.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 · BACKUP CONFIG
# ══════════════════════════════════════════════════════════════════════════════
with tab_backup:
    st.markdown("#### Exportar / importar configuración")
    st.caption(
        "Descarga la configuración (bloques, temas, datos generales) como un archivo JSON "
        "para hacer backup o reutilizarla en otra base de datos de la misma asignatura."
    )

    bc1, bc2 = st.columns(2)

    # ── Exportar ──────────────────────────────────────────────────────────────
    with bc1:
        st.markdown("**📤 Exportar configuración**")

        cfg_export = {
            "general": st.session_state.get("cfg_general", {}),
            "bloques": [
                {"bloque": r["Bloque"], "descripcion": r.get("Descripcion", "")}
                for _, r in st.session_state.excel_dfs.get(
                    lib.CFG_BLOQUES_SHEET, pd.DataFrame()
                ).iterrows()
            ],
            "temas": [
                {"tema": r["Tema"], "nombre": r.get("Nombre", ""), "bloque": r.get("Bloque", "")}
                for _, r in st.session_state.excel_dfs.get(
                    lib.CFG_TEMAS_SHEET, pd.DataFrame()
                ).iterrows()
            ],
        }
        json_bytes = json.dumps(cfg_export, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "⬇️ Descargar configuración JSON",
            data=json_bytes,
            file_name="config_examenes.json",
            mime="application/json",
            key="btn_export_cfg",
            use_container_width=True,
        )
        st.caption(f"Se exportarán: {len(cfg_export['bloques'])} bloques · {len(cfg_export['temas'])} temas")

    # ── Importar ──────────────────────────────────────────────────────────────
    with bc2:
        st.markdown("**📥 Importar configuración**")
        st.warning(
            "⚠️ La importación **reemplaza** los nombres de bloques, temas y datos generales. "
            "Las preguntas no se modifican.",
        )
        cfg_file = st.file_uploader("Archivo JSON de configuración", type=["json"], key="cfg_uploader")

        _imp_mode = st.radio(
            "Modo de importación:",
            ["Merge (conservar nombres existentes, solo añadir vacíos)", "Reemplazar todo"],
            key="cfg_imp_mode",
        )

        if cfg_file and st.button("📥 Importar", type="primary", key="btn_import_cfg",
                                   use_container_width=True):
            try:
                data = json.loads(cfg_file.read().decode("utf-8"))
                merge_mode = "Merge" in _imp_mode

                # General
                new_gen = data.get("general", {})
                if merge_mode:
                    cur_gen = dict(st.session_state.get("cfg_general", {}))
                    for k, v in new_gen.items():
                        if not cur_gen.get(k, ""):
                            cur_gen[k] = v
                    new_gen = cur_gen

                # Bloques
                cur_b_df = st.session_state.excel_dfs.get(lib.CFG_BLOQUES_SHEET, pd.DataFrame())
                cur_b_map = {str(r["Bloque"]): str(r.get("Descripcion", "") or "")
                             for _, r in cur_b_df.iterrows()} if not cur_b_df.empty else {}
                for item in data.get("bloques", []):
                    blq = str(item.get("bloque", ""))
                    desc = str(item.get("descripcion", "") or "")
                    if blq in cur_b_map:
                        if merge_mode and cur_b_map[blq]:
                            continue  # preserve existing
                        cur_b_map[blq] = desc
                new_b_df = pd.DataFrame([
                    {"Bloque": b, "Descripcion": cur_b_map.get(b, "")}
                    for b in bloques_list
                ])

                # Temas
                cur_t_df = st.session_state.excel_dfs.get(lib.CFG_TEMAS_SHEET, pd.DataFrame())
                cur_t_map = {}
                if not cur_t_df.empty:
                    for _, r in cur_t_df.iterrows():
                        t = str(r.get("Tema", "")).strip().replace(".0", "")
                        if t:
                            cur_t_map[t] = {"nombre": str(r.get("Nombre", "") or ""),
                                             "bloque": str(r.get("Bloque", "") or "")}
                for item in data.get("temas", []):
                    t = str(item.get("tema", "")).strip().replace(".0", "")
                    if not t:
                        continue
                    if t in cur_t_map and merge_mode and cur_t_map[t]["nombre"]:
                        continue  # preserve existing
                    cur_t_map[t] = {
                        "nombre": str(item.get("nombre", "") or ""),
                        "bloque": str(item.get("bloque", "") or ""),
                    }
                import re as _re
                _k2 = lambda t: [int(x) if x.isdigit() else x.lower()
                                  for x in _re.split(r"(\d+)", str(t))]
                new_t_df = pd.DataFrame([
                    {"Tema": t, "Nombre": cur_t_map[t]["nombre"], "Bloque": cur_t_map[t]["bloque"]}
                    for t in sorted(cur_t_map, key=_k2)
                ])

                # Guardar todo
                dfs = st.session_state.excel_dfs
                dfs = lib.save_cfg_general(dfs, new_gen)
                dfs = lib.save_cfg_bloques(dfs, new_b_df)
                dfs = lib.save_cfg_temas(dfs, new_t_df)
                dfs = _load_cfg(dfs)
                st.session_state.excel_dfs   = dfs
                st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
                path = st.session_state.get("excel_path", "")
                if path:
                    lib.guardar_excel_local(path, dfs)
                sync_hoja_gsheets(lib.CFG_BLOQUES_SHEET)
                sync_hoja_gsheets(lib.CFG_TEMAS_SHEET)
                sync_hoja_gsheets(lib.CFG_GENERAL_SHEET)
                st.success("✅ Configuración importada correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al importar: {e}")
