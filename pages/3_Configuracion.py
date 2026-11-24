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
import os as _o, sys as _s
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import _recarga; _recarga.comprobar()   # recarga módulos compartidos si cambiaron (despliegues en Streamlit Cloud)
from app_theme import initial_sidebar, notify
import pandas as pd
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import examen_lib_latex as lib
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback,
    apply_theme, page_header, _load_cfg, _nsort,
    sync_bloques_gsheets, sync_hoja_gsheets, reload_db,
    temas_de_bloque, nombre_tema, nombre_bloque,
)
from app_theme import ESTILOS, PREVIEWS, get_estilo, set_estilo, get_preview_mode, set_preview_mode

st.set_page_config(page_title="Configuración · Exámenes UCM", page_icon="⚙️", layout="wide",
                   initial_sidebar_state=initial_sidebar())
init_session_state()
handle_oauth_callback()
apply_theme("configuracion")
render_sidebar()

page_header("⚙️", "Configuración", "Nombres de bloques, temas, objetivos y datos de la asignatura", color="#475569")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos desde la barra lateral antes de continuar.")
    st.stop()

# ── Asegurar que las hojas de config existen y están sincronizadas ────────────
dfs = st.session_state.excel_dfs
dfs = lib.init_cfg_from_data(dfs)
st.session_state.excel_dfs = dfs

bloques_list  = st.session_state.bloques
df_preguntas  = st.session_state.df_preguntas

tab_gen, tab_bloques, tab_temas, tab_obj, tab_const, tab_backup, tab_ui = st.tabs(
    ["📋 General", "📦 Bloques", "📌 Temas", "🎯 Objetivos", "🔢 Constantes",
     "💾 Copia de seguridad" if get_estilo() == "bitacora" else "💾 Backup config", "🎨 Apariencia"]
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
        notify("✅ Datos generales guardados.")
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
            "<div style='background:var(--card2, #f8f9fa);border:1px solid var(--ui-border, #dee2e6);border-radius:8px;"
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
        notify("✅ Nombres de bloques guardados.")
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

    if "Nombre" in cfg_t.columns:   # celdas vacías del Excel: «nan» → vacío
        cfg_t["Nombre"] = cfg_t["Nombre"].fillna("").astype(str).replace({"nan": "", "None": ""})

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

    def _guardar_temas_df(df_t):
        dfs = lib.save_cfg_temas(st.session_state.excel_dfs, df_t)
        dfs = _load_cfg(dfs)
        st.session_state.excel_dfs   = dfs
        st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
        path = st.session_state.get("excel_path", "")
        if path:
            lib.guardar_excel_local(path, dfs)
        sync_hoja_gsheets(lib.CFG_TEMAS_SHEET)

    with st.expander("➕ Añadir un tema (aunque todavía no tenga preguntas)",
                     expanded=bool(cfg_t.empty)):
        with st.form("form_nuevo_tema", clear_on_submit=True):
            nt1, nt2, nt3 = st.columns([1, 3, 2])
            _sig = 1
            try:
                _sig = max(int(float(t)) for t in cfg_t["Tema"] if str(t).replace(".", "", 1).isdigit()) + 1
            except ValueError:
                pass
            nt_num = nt1.text_input("Nº tema", value=str(_sig))
            nt_nom = nt2.text_input("Nombre", placeholder="Ej: Óptica geométrica")
            nt_blq = nt3.selectbox("Bloque", bloques_list) if bloques_list else ""
            if st.form_submit_button("Añadir tema", type="primary"):
                _n = nt_num.strip().removesuffix(".0")
                if not _n:
                    st.error("Indica el número del tema.")
                elif _n in set(cfg_t["Tema"].astype(str)):
                    st.error(f"El tema {_n} ya existe: cambia su nombre en la tabla de abajo.")
                else:
                    _new = pd.concat([cfg_t[["Tema", "Nombre", "Bloque"]],
                                      pd.DataFrame([{"Tema": _n, "Nombre": nt_nom.strip(), "Bloque": nt_blq}])],
                                     ignore_index=True)
                    _new["_s"] = _new["Tema"].apply(lambda t: [int(x) if x.isdigit() else x.lower()
                                                               for x in __import__("re").split(r"(\d+)", str(t))])
                    _guardar_temas_df(_new.sort_values("_s").drop(columns=["_s"]))
                    notify(f"✅ Tema {_n} añadido.")
                    st.rerun()
        _vacios = cfg_t[cfg_t["N preg."] == 0]["Tema"].astype(str).tolist()
        if _vacios:
            dq1, dq2 = st.columns([3, 1], vertical_alignment="bottom")
            _q = dq1.selectbox("Quitar un tema sin preguntas", _vacios, key="cfg_t_quitar",
                               format_func=lambda t: f"Tema {t}" + (
                                   f": {cfg_t.loc[cfg_t['Tema'].astype(str) == t, 'Nombre'].iloc[0]}"
                                   if str(cfg_t.loc[cfg_t['Tema'].astype(str) == t, 'Nombre'].iloc[0]).strip()
                                   not in ("", "nan", "None") else ""))
            if dq2.button("Quitar", key="btn_cfg_t_quitar", use_container_width=True):
                _guardar_temas_df(cfg_t[cfg_t["Tema"].astype(str) != _q][["Tema", "Nombre", "Bloque"]])
                notify(f"🗑️ Tema {_q} quitado.")
                st.rerun()

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
        notify("✅ Nombres de temas guardados.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 · OBJETIVOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_obj:
    st.markdown("#### Objetivos docentes / Competencias")
    st.caption(
        "Define los objetivos o competencias que se asignan a las preguntas (en el editor, pestaña "
        "«Clasificación»). Cada objetivo puede limitarse a un bloque o a un tema."
    )

    import re as _re_o
    _OCOLS = ["Codigo", "Nombre_corto", "Descripcion", "Bloque", "Tema"]
    cfg_o = st.session_state.excel_dfs.get(lib.CFG_OBJETIVOS_SHEET, pd.DataFrame(columns=_OCOLS)).copy()
    for _c in _OCOLS:   # columnas antiguas con tilde → nombres actuales
        _alt = {"Codigo": "Código", "Nombre_corto": "Nombre_Corto", "Descripcion": "Descripción"}.get(_c)
        if _c not in cfg_o.columns:
            cfg_o[_c] = cfg_o[_alt] if _alt and _alt in cfg_o.columns else ""
        cfg_o[_c] = cfg_o[_c].fillna("").astype(str).replace({"nan": "", "None": ""})
    cfg_o = cfg_o[_OCOLS]
    cfg_o = cfg_o[cfg_o["Codigo"].str.strip() != ""].reset_index(drop=True)
    _cnt_o = (df_preguntas["objetivo"].astype(str).value_counts().to_dict()
              if not df_preguntas.empty and "objetivo" in df_preguntas.columns else {})

    def _guardar_obj_df(df_o):
        dfs2 = lib.save_cfg_objetivos(st.session_state.excel_dfs, df_o[_OCOLS])
        dfs2 = _load_cfg(dfs2)
        st.session_state.excel_dfs   = dfs2
        st.session_state.excel_bytes = lib.generar_excel_bytes(dfs2)
        path = st.session_state.get("excel_path", "")
        if path:
            lib.guardar_excel_local(path, dfs2)
        sync_hoja_gsheets(lib.CFG_OBJETIVOS_SHEET)

    def _prefijo_bloque(b: str) -> str:
        """«BLOQUE III» → «B3»; sin bloque → «G» (general)."""
        b = str(b or "").strip().upper()
        if not b:
            return "G"
        m = _re_o.search(r"([IVXLC]+|\d+)$", b)
        if m:
            v = m.group(1)
            if v.isdigit():
                return f"B{int(v)}"
            val = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
            return "B" + str(sum(-val[ch] if i + 1 < len(v) and val[ch] < val[v[i + 1]] else val[ch]
                                 for i, ch in enumerate(v)))
        return _re_o.sub(r"[^A-Z0-9]", "", b)[:4] or "OBJ"

    def _siguiente_codigo(b: str) -> str:
        pre = _prefijo_bloque(b)
        nums = [int(x[len(pre) + 1:]) for x in cfg_o["Codigo"]
                if x.startswith(pre + "-") and x[len(pre) + 1:].isdigit()]
        return f"{pre}-{(max(nums) + 1) if nums else 1:02d}"

    _STOP = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y", "e", "o", "u", "a",
             "en", "al", "que", "se", "su", "sus", "para", "por", "con", "lo"}

    def _nombre_corto(desc: str) -> str:
        """Nombre corto a partir de la descripción: sin el verbo inicial ni artículos; hasta 6 palabras."""
        w = _re_o.findall(r"[\wÀ-ÿ\-·]+", desc or "")
        if w and _re_o.search(r"(ar|er|ir)$", w[0].lower()):
            w = w[1:]
        while w and w[0].lower() in _STOP:
            w = w[1:]
        out = w[:6]
        while len(out) > 1 and out[-1].lower() in _STOP:
            out = out[:-1]
        s = " ".join(out)
        return (s[:1].upper() + s[1:]) if s else ""

    def _temas_de(b: str) -> list:
        return [str(t) for t in temas_de_bloque(b)] if b else []

    # ── Añadir ────────────────────────────────────────────────────────────────
    with st.expander("➕ Añadir un objetivo", expanded=cfg_o.empty):
        na1, na2 = st.columns([2, 1])
        n_blq = na1.selectbox("Bloque", [""] + [str(b) for b in bloques_list], key="obj_new_blq",
                              format_func=lambda b: nombre_bloque(b) if b else "— Todos los bloques (general) —")
        n_tem = na2.selectbox("Tema (opcional)", [""] + _temas_de(n_blq), key="obj_new_tem",
                              format_func=lambda t: "— Todos —" if not t else nombre_tema(t))
        n_desc = st.text_area("Descripción", key="obj_new_desc", height=70,
                              placeholder="Ej: Calcular la dosis absorbida a partir de la fluencia de energía")
        n_nom = st.text_input("Nombre corto (opcional)", key="obj_new_nom",
                              placeholder=_nombre_corto(n_desc) or "Se genera a partir de la descripción")
        _cod = _siguiente_codigo(n_blq)
        st.caption(f"Se creará con el código **{_cod}** y el nombre corto "
                   f"**{n_nom.strip() or _nombre_corto(n_desc) or '—'}**.")
        if st.button("Añadir objetivo", type="primary", key="btn_obj_add", disabled=not n_desc.strip()):
            _new = pd.concat([cfg_o, pd.DataFrame([{
                "Codigo": _cod, "Nombre_corto": n_nom.strip() or _nombre_corto(n_desc),
                "Descripcion": n_desc.strip(), "Bloque": n_blq, "Tema": n_tem}])], ignore_index=True)
            _guardar_obj_df(_new)
            for _k in ("obj_new_desc", "obj_new_nom"):
                st.session_state.pop(_k, None)
            notify(f"✅ Objetivo {_cod} añadido.")
            st.rerun()

    # ── Lista: editar / quitar cada uno ──────────────────────────────────────
    if cfg_o.empty:
        st.info("Aún no hay objetivos. Añade el primero con el formulario de arriba.")
    else:
        _n_asig = sum(1 for x in cfg_o["Codigo"] if _cnt_o.get(x))
        st.caption(f"{len(cfg_o)} objetivo(s) · {_n_asig} con preguntas asignadas")
        _ed = st.session_state.get("_obj_edit_cod")
        _del = st.session_state.get("_obj_del_conf")
        for _, r in cfg_o.iterrows():
            cod = r["Codigo"]
            alc = " · ".join(x for x in (nombre_bloque(r["Bloque"]) if r["Bloque"] else "Todos los bloques",
                                         nombre_tema(r["Tema"]) if r["Tema"] else "") if x)
            with st.container(border=True, key=f"card_obj_{_re_o.sub(r'[^A-Za-z0-9_]', '_', cod)}"):
                if _ed == cod:
                    e1, e2 = st.columns(2)
                    e_nom = e1.text_input("Nombre corto", r["Nombre_corto"], key=f"oe_nom_{cod}")
                    _bo = [""] + [str(b) for b in bloques_list]
                    e_blq = e2.selectbox("Bloque", _bo, index=_bo.index(r["Bloque"]) if r["Bloque"] in _bo else 0,
                                         key=f"oe_blq_{cod}",
                                         format_func=lambda b: nombre_bloque(b) if b else "— Todos los bloques —")
                    e_desc = st.text_area("Descripción", r["Descripcion"], key=f"oe_desc_{cod}", height=70)
                    _to = [""] + _temas_de(e_blq)
                    e_tem = e1.selectbox("Tema", _to, index=_to.index(r["Tema"]) if r["Tema"] in _to else 0,
                                         key=f"oe_tem_{cod}", format_func=lambda t: "— Todos —" if not t else nombre_tema(t))
                    s1, s2, _ = st.columns([1, 1, 3])
                    if s1.button("Guardar", type="primary", key=f"oe_save_{cod}", use_container_width=True):
                        _m = cfg_o["Codigo"] == cod
                        cfg_o.loc[_m, ["Nombre_corto", "Descripcion", "Bloque", "Tema"]] = [
                            e_nom.strip(), e_desc.strip(), e_blq, e_tem]
                        _guardar_obj_df(cfg_o)
                        st.session_state.pop("_obj_edit_cod", None)
                        notify(f"✅ Objetivo {cod} guardado.")
                        st.rerun()
                    if s2.button("Cancelar", key=f"oe_cancel_{cod}", use_container_width=True):
                        st.session_state.pop("_obj_edit_cod", None)
                        st.rerun()
                else:
                    o1, o2, o3 = st.columns([6, 1, 1], vertical_alignment="center")
                    _n = _cnt_o.get(cod, 0)
                    o1.markdown(
                        f"<div style='display:flex;gap:10px;align-items:baseline;flex-wrap:wrap'>"
                        f"<code>{cod}</code><b>{r['Nombre_corto'] or '—'}</b>"
                        f"<span style='font-size:.8rem;color:var(--muted, #888)'>{alc} · "
                        f"{_n} pregunta{'s' if _n != 1 else ''}</span></div>"
                        + (f"<div style='font-size:.86rem;color:var(--text2, #555);margin-top:3px'>{r['Descripcion']}</div>"
                           if r["Descripcion"] else ""), unsafe_allow_html=True)
                    if o2.button("Editar", key=f"obj_edit_{cod}", use_container_width=True):
                        st.session_state["_obj_edit_cod"] = cod
                        st.session_state.pop("_obj_del_conf", None)
                        st.rerun()
                    if o3.button("Quitar", key=f"obj_del_{cod}", use_container_width=True):
                        st.session_state["_obj_del_conf"] = cod
                        st.rerun()
                    if _del == cod:
                        st.warning(f"¿Quitar el objetivo {cod}?"
                                   + (f" {_n} pregunta(s) lo tienen asignado: conservarán el código, pero ya "
                                      "no aparecerá en la lista." if _n else ""))
                        q1, q2, _ = st.columns([1, 1, 3])
                        if q1.button("Sí, quitar", type="primary", key=f"obj_del_ok_{cod}", use_container_width=True):
                            _guardar_obj_df(cfg_o[cfg_o["Codigo"] != cod])
                            st.session_state.pop("_obj_del_conf", None)
                            notify(f"🗑️ Objetivo {cod} quitado.")
                            st.rerun()
                        if q2.button("Cancelar", key=f"obj_del_no_{cod}", use_container_width=True):
                            st.session_state.pop("_obj_del_conf", None)
                            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB · CONSTANTES FÍSICAS (antes en el Gestor)
# ─────────────────────────────────────────────────────────────────────────────
with tab_const:
    st.subheader("Constantes físicas / Datos")
    st.caption(
        "Define los valores que aparecerán como *Datos:* debajo de los enunciados. "
        "Una vez añadidas, selecciónalas desde el editor de cada pregunta."
    )

    if not st.session_state.db_connected:
        st.info("Conecta una base de datos para gestionar las constantes.")
    else:
        import re as _re_const

        def _auto_id(nombre: str) -> str:
            s = nombre.lower().strip()
            for _src, _dst in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ñ','n')]:
                s = s.replace(_src, _dst)
            return _re_const.sub(r'[^a-z0-9]+', '_', s).strip('_')

        def _save_datos_state(df_new):
            _dfs2 = lib.save_datos_df(st.session_state.excel_dfs, df_new)
            st.session_state.excel_dfs    = _dfs2
            lib.guardar_excel_local(st.session_state.excel_path, _dfs2)
            st.session_state["excel_bytes"] = lib.generar_excel_bytes(_dfs2)
            sync_bloques_gsheets([lib.DATOS_SHEET])  # sincronizar con Google Sheets si está conectado

        _datos_df = lib.get_datos_df(st.session_state.excel_dfs)

        # ── Procesar acciones pendientes (delete / edit-save) antes de renderizar ──
        _del_id  = st.session_state.pop("_const_del_id", None)
        _upd_row = st.session_state.pop("_const_upd_row", None)

        if _del_id:
            _datos_df = _datos_df[_datos_df['ID'].astype(str) != _del_id].reset_index(drop=True)
            _save_datos_state(_datos_df)
            notify(f"🗑️ Constante '{_del_id}' eliminada.")
        if _upd_row:
            _did_upd = _upd_row['ID']
            _mask = _datos_df['ID'].astype(str) == _did_upd
            for _col, _val in _upd_row.items():
                _datos_df.loc[_mask, _col] = _val
            _save_datos_state(_datos_df)
            st.session_state.pop("_const_edit_id", None)

        # ── Formulario: añadir nueva constante ───────────────────────────────
        def _on_nc_nombre_change():
            st.session_state["nc_id"] = _auto_id(st.session_state.get("nc_nombre", ""))

        _cats_exist = (sorted(_datos_df['Categoría'].dropna().unique().tolist())
                       if not _datos_df.empty else [])

        with st.expander("➕ Nueva constante", expanded=False):
            _nca, _ncb = st.columns([3, 2])
            with _nca:
                st.text_input("Nombre", key="nc_nombre", on_change=_on_nc_nombre_change,
                              placeholder="Velocidad de la luz en el vacío")
                st.text_input("ID (auto-generado, editable)", key="nc_id",
                              placeholder="c_luz")
                _nc_cat_opts = _cats_exist + (["✏️ Escribir nueva…"] if _cats_exist else [])
                if _nc_cat_opts:
                    _nc_cat_sel = st.selectbox("Categoría", _nc_cat_opts, key="nc_cat_sel")
                    _nc_cat_final = (st.text_input("Nueva categoría", key="nc_cat_new",
                                                   placeholder="p.ej. Constantes fundamentales")
                                    if _nc_cat_sel == "✏️ Escribir nueva…"
                                    else _nc_cat_sel)
                else:
                    _nc_cat_final = st.text_input("Categoría", key="nc_cat_new",
                                                  placeholder="p.ej. Constantes fundamentales")
            with _ncb:
                st.text_input("Símbolo LaTeX", key="nc_sym",
                              placeholder="c", help="p.ej. `c`, `m_e`, `\\hbar`")
                st.text_input("Valor LaTeX", key="nc_val",
                              placeholder="3{,}00 \\times 10^8",
                              help="Se incluirá dentro de $…$, p.ej. `3{,}00 \\times 10^8`")
                st.text_input("Unidades LaTeX", key="nc_uni",
                              placeholder="\\text{m/s}")

            if st.button("💾 Añadir constante", type="primary", key="btn_add_const",
                         use_container_width=True):
                _nc_id  = st.session_state.get("nc_id",  "").strip()
                _nc_nom = st.session_state.get("nc_nombre","").strip()
                _nc_sym = st.session_state.get("nc_sym", "").strip()
                _nc_val = st.session_state.get("nc_val", "").strip()
                _nc_uni = st.session_state.get("nc_uni", "").strip()
                _nc_cat = _nc_cat_final.strip() if '_nc_cat_final' in dir() else ""
                if not _nc_id:
                    st.error("El ID no puede estar vacío.")
                elif not _nc_val:
                    st.error("El valor no puede estar vacío.")
                elif not _datos_df.empty and _nc_id in _datos_df['ID'].astype(str).tolist():
                    st.error(f"Ya existe una constante con ID `{_nc_id}`.")
                else:
                    _new_row = {'ID': _nc_id, 'Nombre': _nc_nom, 'Símbolo': _nc_sym,
                                'Valor': _nc_val, 'Unidades': _nc_uni, 'Categoría': _nc_cat}
                    import pandas as _pd_tmp
                    _datos_df = _pd_tmp.concat([_datos_df, _pd_tmp.DataFrame([_new_row])],
                                               ignore_index=True)
                    _save_datos_state(_datos_df)
                    for _k in ["nc_nombre","nc_id","nc_sym","nc_val","nc_uni","nc_cat_new"]:
                        st.session_state.pop(_k, None)
                    notify(f"✅ Constante `{_nc_id}` añadida.")
                    st.rerun()

        # ── Lista de constantes por categoría ─────────────────────────────────
        if _datos_df.empty or not _datos_df['ID'].astype(str).str.strip().any():
            st.info("Aún no hay constantes. Usa el formulario de arriba para añadir la primera.")
        else:
            _edit_id = st.session_state.get("_const_edit_id")
            _cats_all = sorted(_datos_df['Categoría'].fillna('Sin categoría').unique().tolist())

            for _cat in _cats_all:
                _cdf = _datos_df[_datos_df['Categoría'].fillna('Sin categoría') == _cat].copy()
                with st.expander(f"**{_cat}** — {len(_cdf)} constante(s)", expanded=True):
                    for _, _cr in _cdf.iterrows():
                        _did = str(_cr['ID']).strip()
                        if _edit_id == _did:
                            # ── Modo edición inline ───────────────────────────
                            with st.form(key=f"form_edit_{_did}", border=True):
                                _fe1, _fe2 = st.columns(2)
                                _en = _fe1.text_input("Nombre", value=str(_cr.get('Nombre','') or ''))
                                _es = _fe2.text_input("Símbolo", value=str(_cr.get('Símbolo','') or ''))
                                _ev = _fe1.text_input("Valor", value=str(_cr.get('Valor','') or ''))
                                _eu = _fe2.text_input("Unidades", value=str(_cr.get('Unidades','') or ''))
                                _cats_ed = sorted(_datos_df['Categoría'].dropna().unique().tolist())
                                _ec_idx  = _cats_ed.index(_cat) if _cat in _cats_ed else 0
                                _ec = st.selectbox("Categoría", _cats_ed, index=_ec_idx)
                                _fsb1, _fsb2 = st.columns(2)
                                if _fsb1.form_submit_button("💾 Guardar", type="primary",
                                                            use_container_width=True):
                                    st.session_state["_const_upd_row"] = {
                                        'ID': _did, 'Nombre': _en, 'Símbolo': _es,
                                        'Valor': _ev, 'Unidades': _eu, 'Categoría': _ec
                                    }
                                    st.rerun()
                                if _fsb2.form_submit_button("✖ Cancelar",
                                                            use_container_width=True):
                                    st.session_state.pop("_const_edit_id", None)
                                    st.rerun()
                        else:
                            # ── Modo visualización ────────────────────────────
                            _rc1, _rc2, _rc3 = st.columns([5, 1, 1])
                            _nom = str(_cr.get('Nombre','') or _did)
                            _sym = str(_cr.get('Símbolo','') or '')
                            _val = str(_cr.get('Valor','') or '')
                            _uni = str(_cr.get('Unidades','') or '')
                            _eq  = f" = {_val} {_uni}".rstrip() if _val else ""
                            _rc1.markdown(f"**{_nom}** — `{_did}`")
                            _rc1.caption(f"{_sym}{_eq}" if _sym or _val else "")
                            if _rc2.button("✏️", key=f"edbtn_{_did}", use_container_width=True,
                                           help="Editar"):
                                st.session_state["_const_edit_id"] = _did
                                st.rerun()
                            if _rc3.button("🗑️", key=f"delbtn_{_did}", use_container_width=True,
                                           help="Eliminar"):
                                st.session_state["_const_del_id"] = _did
                                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 · BACKUP CONFIG
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
            "objetivos": [
                {"codigo": r.get("Codigo", ""), "nombre_corto": r.get("Nombre_corto", ""),
                 "descripcion": r.get("Descripcion", ""), "bloque": r.get("Bloque", ""),
                 "tema": r.get("Tema", "")}
                for _, r in st.session_state.excel_dfs.get(
                    lib.CFG_OBJETIVOS_SHEET, pd.DataFrame()
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
        st.caption(f"Se exportarán: {len(cfg_export['bloques'])} bloques · "
                   f"{len(cfg_export['temas'])} temas · {len(cfg_export['objetivos'])} objetivos")

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

                # Objetivos
                cur_o_df = st.session_state.excel_dfs.get(lib.CFG_OBJETIVOS_SHEET, pd.DataFrame())
                cur_o_map = {}
                if not cur_o_df.empty and "Codigo" in cur_o_df.columns:
                    for _, r in cur_o_df.iterrows():
                        cod = str(r.get("Codigo", "")).strip()
                        if cod:
                            cur_o_map[cod] = {
                                "nombre_corto": str(r.get("Nombre_corto", "") or ""),
                                "descripcion":  str(r.get("Descripcion",  "") or ""),
                                "bloque":       str(r.get("Bloque",       "") or ""),
                                "tema":         str(r.get("Tema",         "") or ""),
                            }
                for item in data.get("objetivos", []):
                    cod = str(item.get("codigo", "")).strip()
                    if not cod:
                        continue
                    if cod in cur_o_map and merge_mode and cur_o_map[cod]["nombre_corto"]:
                        continue
                    cur_o_map[cod] = {
                        "nombre_corto": str(item.get("nombre_corto", "") or ""),
                        "descripcion":  str(item.get("descripcion",  "") or ""),
                        "bloque":       str(item.get("bloque",       "") or ""),
                        "tema":         str(item.get("tema",         "") or ""),
                    }
                new_o_df = pd.DataFrame([
                    {"Codigo": cod, "Nombre_corto": v["nombre_corto"],
                     "Descripcion": v["descripcion"], "Bloque": v["bloque"], "Tema": v["tema"]}
                    for cod, v in cur_o_map.items()
                ])

                # Guardar todo
                dfs = st.session_state.excel_dfs
                dfs = lib.save_cfg_general(dfs, new_gen)
                dfs = lib.save_cfg_bloques(dfs, new_b_df)
                dfs = lib.save_cfg_temas(dfs, new_t_df)
                dfs = lib.save_cfg_objetivos(dfs, new_o_df)
                dfs = _load_cfg(dfs)
                st.session_state.excel_dfs   = dfs
                st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
                path = st.session_state.get("excel_path", "")
                if path:
                    lib.guardar_excel_local(path, dfs)
                sync_hoja_gsheets(lib.CFG_BLOQUES_SHEET)
                sync_hoja_gsheets(lib.CFG_TEMAS_SHEET)
                sync_hoja_gsheets(lib.CFG_GENERAL_SHEET)
                sync_hoja_gsheets(lib.CFG_OBJETIVOS_SHEET)
                notify("✅ Configuración importada correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al importar: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 · APARIENCIA
# ══════════════════════════════════════════════════════════════════════════════
with tab_ui:
    st.markdown("#### Estilo de la aplicación")
    st.caption(
        "Se aplica a todas las páginas y se guarda en la hoja Cfg_General de tu base de datos. "
        "No cambia el aspecto de los exámenes exportados."
    )

    # Clave con el valor activo: el control se recrea con la opción correcta
    # (sincronizado con el selector de la barra lateral)
    _est_key = f"cfg_ui_estilo_{get_estilo()}"
    st.radio(
        "Estilo",
        list(ESTILOS),
        index=list(ESTILOS).index(get_estilo()),
        format_func=ESTILOS.get,
        captions=[
            "Tarjetas blancas sobre gris azulado, azul marino y cifras en monoespaciada. "
            "Disponible en claro y oscuro.",
            "El aspecto original de la aplicación (solo modo claro).",
        ],
        key=_est_key,
        on_change=lambda: set_estilo(st.session_state[_est_key]),
    )

    st.info(
        "**Claro / oscuro:** menú **⋮** (arriba a la derecha) → **Settings** → "
        "*Choose app theme* (Light, Dark o System, que sigue al sistema operativo). "
        "Se recuerda en este navegador."
    )

    st.markdown("#### Vista previa de preguntas")
    st.caption("Al marcar una pregunta en Gestor DB → Gestionar y en Generador → Selección.")

    _prv_key = f"cfg_ui_preview_{get_preview_mode()}"
    st.radio(
        "Vista previa",
        list(PREVIEWS),
        index=list(PREVIEWS).index(get_preview_mode()),
        format_func=PREVIEWS.get,
        captions=[
            "Se abre en una ventana sobre la página; la tabla de preguntas ocupa todo el ancho.",
            "La pregunta se muestra en un panel junto a la tabla (como antes).",
        ],
        key=_prv_key,
        on_change=lambda: set_preview_mode(st.session_state[_prv_key]),
        label_visibility="collapsed",
    )

    _cfg_g_ui     = st.session_state.get("cfg_general", {})
    _est_guardado = _cfg_g_ui.get("ui_estilo", "")
    _est_activo   = get_estilo()
    _prv_guardado = _cfg_g_ui.get("ui_preview", "")
    _prv_activo   = get_preview_mode()
    _ui_guardado  = (_est_guardado == _est_activo and _prv_guardado == _prv_activo)
    if st.button("💾 Guardar como predeterminado", type="primary", key="btn_save_ui",
                 disabled=_ui_guardado):
        cfg_g_new = {**_cfg_g_ui, "ui_estilo": _est_activo, "ui_preview": _prv_activo}
        dfs = lib.save_cfg_general(st.session_state.excel_dfs, cfg_g_new)
        dfs = _load_cfg(dfs)
        st.session_state.excel_dfs   = dfs
        st.session_state.excel_bytes = lib.generar_excel_bytes(dfs)
        path = st.session_state.get("excel_path", "")
        if path:
            lib.guardar_excel_local(path, dfs)
        sync_hoja_gsheets(lib.CFG_GENERAL_SHEET)
        st.rerun()
    if _ui_guardado:
        st.caption(f"Guardado en la base de datos: estilo {ESTILOS.get(_est_guardado)} · "
                   f"vista previa en {PREVIEWS.get(_prv_guardado, '').lower()}")
