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
import os as _o, sys as _s
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import _recarga, importlib as _il_r, os as _os_r   # _recarga también se recarga a sí mismo si cambió
_recarga = (_il_r.reload(_recarga) if getattr(_recarga, "_MTIME", None) != _os_r.path.getmtime(_recarga.__file__) else _recarga)
_recarga.comprobar()
from app_theme import initial_sidebar, notify
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
import examen_estado as E
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback, apply_theme, page_header,
    reload_db, bloques_disponibles, temas_de_bloque, objetivos_de_tema,
    es_uso_antiguo, render_question_card_html, mathjax_html,
    append_historial, save_preset, delete_preset,
    nombre_bloque, nombre_tema, nombre_objetivo,
    OUTPUT_DIR, _nsort,
    _dialog_editar_pregunta, marcar_preguntas_usadas, guardar_hojas, filtros_bitacora,
    grupo_pregunta, selector_agrupar, n_preg, orden_bloque,
)
orden_bloque_g = orden_bloque
from app_theme import get_preview_mode, get_estilo, qtable, qtable_row

# ── Configuración ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Generador · Exámenes UCM", page_icon="🎲", layout="wide",
                   initial_sidebar_state=initial_sidebar())
init_session_state()
handle_oauth_callback()
apply_theme("generador")
render_sidebar()

_n_sel = len(st.session_state.sel_ids)
_sub_gen = (f"{_n_sel} preguntas seleccionadas" if _n_sel else "Selecciona preguntas para el examen")
page_header("🎲", "Generador de Exámenes", _sub_gen, color="#1a6b3a")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos desde la barra lateral antes de continuar.")
    st.stop()
E.indicador_borrador()

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
# DIALOG: SUBAPARTADOS DE PREGUNTA DE DESARROLLO
# ═════════════════════════════════════════════════════════════════════════════
@st.dialog("📑 Editar subapartados", width="large")
def _dialog_subapartados(q_idx: int):
    """Modal para editar los subapartados de una pregunta de desarrollo."""
    import json as _j
    dev_qs = st.session_state.dev_questions
    if q_idx >= len(dev_qs):
        st.error("Índice de pregunta no válido."); return
    q = dev_qs[q_idx]
    subapts = list(q.get("subapartados") or [])

    _NUM_LABELS = {"abc": "a), b), c)…", "roman": "i), ii), iii)…", "num": "1), 2), 3)…"}
    num_apt = st.radio("Numeración", list(_NUM_LABELS.keys()),
                       index=list(_NUM_LABELS.keys()).index(q.get("numeracion_apt", "abc")),
                       format_func=lambda x: _NUM_LABELS[x], horizontal=True,
                       key=f"apt_num_{q_idx}")

    st.divider()

    to_del_apt = []
    for ai, apt in enumerate(subapts):
        st.markdown(f"**Apartado {ai+1}**")
        c1, c2, c3 = st.columns([5, 1, 1])
        subapts[ai]["enunciado"] = c1.text_area(
            "Enunciado", value=apt.get("enunciado", ""), height=80,
            key=f"apt_enun_{q_idx}_{ai}", label_visibility="collapsed")
        subapts[ai]["puntos"] = c2.number_input(
            "Pts", value=float(apt.get("puntos") or 1.0), min_value=0.0, step=0.5,
            key=f"apt_pts_{q_idx}_{ai}")
        _esp_opts = ["3cm", "4cm", "5cm", "6cm", "7cm", "8cm", "10cm", "12cm", "15cm", "18cm"]
        _esp_cur  = str(apt.get("espacio") or "5cm")
        subapts[ai]["espacio"] = c3.selectbox(
            "Espacio", _esp_opts,
            index=_esp_opts.index(_esp_cur) if _esp_cur in _esp_opts else 2,
            key=f"apt_esp_{q_idx}_{ai}")
        subapts[ai]["solucion"] = st.text_area(
            "Solución modelo (opcional)", value=apt.get("solucion", ""), height=70,
            key=f"apt_sol_{q_idx}_{ai}",
            placeholder="Escribe la solución para este apartado…")
        if st.button("🗑 Eliminar este apartado", key=f"apt_del_{q_idx}_{ai}"):
            to_del_apt.append(ai)
        st.divider()

    if to_del_apt:
        for ai in sorted(to_del_apt, reverse=True):
            subapts.pop(ai)

    if st.button("➕ Añadir apartado", key=f"apt_add_{q_idx}"):
        subapts.append({"enunciado": "", "puntos": 1.0, "espacio": "5cm", "solucion": ""})

    _pts_total = sum(float(a.get("puntos") or 0) for a in subapts)
    if subapts:
        st.info(f"Total puntos: **{_pts_total:g} pt**")

    _sa1, _sa2 = st.columns(2)
    if _sa1.button("💾 Guardar", type="primary", use_container_width=True, key=f"apt_save_{q_idx}"):
        dev_qs[q_idx]["subapartados"] = subapts
        dev_qs[q_idx]["numeracion_apt"] = num_apt
        st.session_state.dev_questions = dev_qs
        st.rerun()
    if _sa2.button("✕ Cancelar", use_container_width=True, key=f"apt_cancel_{q_idx}"):
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# DIALOG: CONFIGURACIÓN DE RELLENO AUTOMÁTICO

# ═════════════════════════════════════════════════════════════════════════════
# RECETA DE AUTO-RELLENO (Bitácora): Resumen · Reparto rápido · Cantidades · Opciones
# Estructura (igual que la antigua): {bloque: {"__ALL__"|tema|"__OBJ_cod": {facil, media, dificil}}}
# Los objetivos sin bloque van en el pseudo-bloque "__GEN__".
# ═════════════════════════════════════════════════════════════════════════════
_DIFS = ("facil", "media", "dificil")
_DIFL = ("Fácil", "Media", "Difícil")
_MEZCLAS = {"Como el banco": None, "30 · 50 · 20": (30, 50, 20), "50 · 40 · 10": (50, 40, 10),
            "20 · 50 · 30": (20, 50, 30), "Personalizada": "pers"}
_GEN = "__GEN__"
_RECETAS_SHEET = "Cfg_Recetas"
_OPT_DEF = {"evitar_meses": 0, "excl_examenes": [], "excl_etiquetas": [], "solo_etiquetas": [],
            "solo_sol": False, "excl_revisar": False, "criterio": "menos usadas", "max_tema": 0, "max_obj": 0}


def _cuotas(total: int, pesos: dict, topes: dict) -> dict:
    """Reparte `total` según `pesos` (resto mayor) sin pasar de `topes`; lo que sobra va a los demás."""
    out = {k: 0 for k in pesos}
    resto = total
    activos = {k for k in pesos if topes.get(k, 0) > 0 and pesos[k] > 0}
    while resto > 0 and activos:
        w = sum(pesos[k] for k in activos)
        ideal = {k: resto * pesos[k] / w for k in activos}
        base = {k: min(int(ideal[k]), topes[k] - out[k]) for k in activos}
        dado = sum(base.values())
        for k in sorted(activos, key=lambda k: -(ideal[k] - int(ideal[k]))):
            if dado >= resto:
                break
            if out[k] + base[k] < topes[k]:
                base[k] += 1
                dado += 1
        if dado == 0:
            break
        for k in activos:
            out[k] += base[k]
        resto -= dado
        activos = {k for k in activos if out[k] < topes[k]}
    return out


def _dif_norm(v) -> str:
    return str(v).lower().replace("á", "a").replace("í", "i")


def _datos_analisis():
    """IDs excluidos por exámenes elegidos, IDs «a revisar» y discriminación más reciente (de Análisis)."""
    import analisis_lib as _A
    dfs = st.session_state.get("excel_dfs", {})
    exs, res = _A.get_examenes(dfs), _A.get_resultados(dfs)
    pos = {r["ID_Examen"]: {p for v in _A.examen_info(r)["posiciones"].values() for p in v if p}
           for _, r in exs.iterrows()}
    revisar, disc = set(), {}
    if not res.empty:
        for _, r in res.sort_values("Fecha").groupby("ID_Pregunta").tail(1).iterrows():
            try:
                d = float(r["Discriminacion"])
            except ValueError:
                d = None
            if d is not None:
                disc[r["ID_Pregunta"]] = d
            if r["Decision"] == "anular" or str(r["Revisar_Distractores"]) in ("1", "True") or (d is not None and d < 0):
                revisar.add(r["ID_Pregunta"])
    nombres = {r["ID_Examen"]: f'{r["Curso"]} · {r["Convocatoria"] or ""} · {r["Nombre"]}'.replace(" ·  ·", " ·")
               for _, r in exs.iterrows()}
    return pos, revisar, disc, nombres


def _filtrar_opciones(d, opts, an=None):
    """Aplica las opciones «qué preguntas pueden entrar» a un DataFrame de preguntas."""
    pos, revisar, _, _ = an or _datos_analisis()
    m = int(opts.get("evitar_meses", 0) or 0)
    if m:
        u = d["usada"].astype(str).replace({"nan": "", "None": ""}).str.strip()
        d = d[(u == "") | u.apply(lambda v: es_uso_antiguo(v, m))]
    ex = set()
    for e in opts.get("excl_examenes", []) or []:
        ex |= pos.get(e, set())
    if ex:
        d = d[~d["ID_Pregunta"].isin(ex)]
    com = d.get("comentario", pd.Series("", index=d.index)).astype(str).str.strip()
    if opts.get("excl_etiquetas"):
        d = d[~com.isin(opts["excl_etiquetas"])]
        com = com[d.index]
    if opts.get("solo_etiquetas"):
        d = d[com.isin(opts["solo_etiquetas"])]
    if opts.get("solo_sol"):
        d = d[~d.get("solucion", pd.Series("", index=d.index)).astype(str).str.strip().isin(["", "nan", "None"])]
    if opts.get("excl_revisar") and revisar:
        d = d[~d["ID_Pregunta"].isin(revisar)]
    return d


def _pool_receta(df_all, manual, opts, an=None):
    return _filtrar_opciones(df_all[~df_all["ID_Pregunta"].isin(set(manual))], opts, an)


def _disp(d) -> list:
    dd = d["dificultad"].map(_dif_norm)
    return [int((dd == x).sum()) for x in _DIFS]


def _filas_receta(pool, blqs):
    """Filas editables: [(bloque, clave, nivel, nombre, disponibles[3])]."""
    cfg_o = st.session_state.get("cfg_objetivos", {}) or {}
    obj = pool.get("objetivo", pd.Series("", index=pool.index)).astype(str)
    filas = {}
    for b in blqs:
        db = pool[pool["bloque"] == b]
        hijos = []
        for t in sorted({str(x).removesuffix(".0") for x in db["Tema"].astype(str)}, key=_nsort):
            hijos.append((t, nombre_tema(t), _disp(db[db["Tema"].astype(str).str.removesuffix(".0") == t])))
        for c, d in cfg_o.items():
            if d.get("bloque") == b:
                hijos.append((f"__OBJ_{c}", f"Objetivo {c} · {d.get('nombre_corto', '')}", _disp(db[obj[db.index] == c])))
        filas[b] = {"disp": _disp(db), "hijos": hijos}
    gen = [(f"__OBJ_{c}", f"Objetivo {c} · {d.get('nombre_corto', '')}", _disp(pool[obj == c]))
           for c, d in cfg_o.items() if not d.get("bloque")]
    return filas, gen


def _rq_key(b, k, i):
    import re as _re
    return "rq_" + _re.sub(r"[^A-Za-z0-9_]", "_", f"{b}__{k}") + f"_{i}"


def _es_rq_cantidad(k) -> bool:
    """Claves de las casillas de cantidades (no las de reparto rápido ni los botones)."""
    k = str(k)
    return k.startswith("rq_") and k[-2:] in ("_0", "_1", "_2") and not k.startswith(("rq_tog", "rq_load", "rq_del"))


def _cantidades(blqs, filas, gen) -> dict:
    """Lee las cantidades (de los widgets) → {(bloque, clave): [f, m, d]}.
    Guarda una copia en _rq_vals: si una casilla no se dibujó en una ejecución, Streamlit borra su
    valor; al volver se restaura desde la copia."""
    ss = st.session_state
    copia = ss.setdefault("_rq_vals", {})
    for k, v in copia.items():
        if k not in ss:
            ss[k] = v
    out = {}
    for b in blqs:
        for k in ["__ALL__"] + [h[0] for h in filas.get(b, {}).get("hijos", [])]:
            out[(b, k)] = [int(ss.get(_rq_key(b, k, i), 0) or 0) for i in range(3)]
    for k, _, _ in gen:
        out[(_GEN, k)] = [int(ss.get(_rq_key(_GEN, k, i), 0) or 0) for i in range(3)]
    for k in [k for k in ss.keys() if _es_rq_cantidad(k)]:
        copia[k] = int(ss[k] or 0)
    return out


def _cargar_en_widgets(recipe: dict, opts: dict):
    """Pasa una receta guardada a los controles (antes de dibujarlos)."""
    ss = st.session_state
    for k in [k for k in ss.keys() if _es_rq_cantidad(k)]:
        del ss[k]
    ss["_rq_vals"] = {}
    for b, temas in (recipe or {}).items():
        for k, dct in temas.items():
            for i, d in enumerate(_DIFS):
                ss[_rq_key(b, k, i)] = int(dct.get(d, 0) or 0)
    o = {**_OPT_DEF, **(opts or {})}
    ss["rec_evitar"] = {0: "No", 6: "6 meses", 12: "12 meses", 24: "24 meses"}.get(int(o["evitar_meses"] or 0), "No")
    ss["rec_excl_ex"], ss["rec_excl_et"], ss["rec_solo_et"] = list(o["excl_examenes"]), list(o["excl_etiquetas"]), list(o["solo_etiquetas"])
    ss["rec_sol"], ss["rec_revisar"] = bool(o["solo_sol"]), bool(o["excl_revisar"])
    ss["rec_criterio"] = {"menos usadas": "Primero las menos usadas", "azar": "Al azar",
                          "discrimina": "Primero las que mejor discriminan"}.get(o["criterio"], "Primero las menos usadas")
    ss["rec_max_tema"], ss["rec_max_obj"] = int(o["max_tema"] or 0), int(o["max_obj"] or 0)


def _opts_de_widgets() -> dict:
    ss = st.session_state
    return {"evitar_meses": {"No": 0, "6 meses": 6, "12 meses": 12, "24 meses": 24}.get(ss.get("rec_evitar", "No"), 0),
            "excl_examenes": list(ss.get("rec_excl_ex", [])), "excl_etiquetas": list(ss.get("rec_excl_et", [])),
            "solo_etiquetas": list(ss.get("rec_solo_et", [])), "solo_sol": bool(ss.get("rec_sol", False)),
            "excl_revisar": bool(ss.get("rec_revisar", False)),
            "criterio": {"Al azar": "azar", "Primero las que mejor discriminan": "discrimina"}.get(
                ss.get("rec_criterio", ""), "menos usadas"),
            "max_tema": int(ss.get("rec_max_tema", 0) or 0), "max_obj": int(ss.get("rec_max_obj", 0) or 0)}


def _recetas_guardadas() -> pd.DataFrame:
    df = st.session_state.get("excel_dfs", {}).get(_RECETAS_SHEET)
    if df is None or df.empty:
        return pd.DataFrame(columns=["Nombre", "Receta", "Opciones", "Descripcion", "Fecha"])
    return df.fillna("").astype(str)


@st.dialog("Receta de auto-relleno", width="large")
def _dialog_receta(n_obj: int):
    import json as _json
    ss = st.session_state
    df_all = ss.df_preguntas
    blqs = list(ss.bloques or [])
    manual = list(ss.manual_order or [])
    if not blqs or df_all.empty:
        st.warning("Conecta la base de datos antes de usar el auto-relleno.")
        return
    # cargas pendientes (receta guardada, reparto rápido, vaciar): antes de dibujar los controles
    if "_rec_pend" in ss:
        _r, _o = ss.pop("_rec_pend")
        _cargar_en_widgets(_r, _o if _o is not None else _opts_de_widgets())
    an = _datos_analisis()
    opts = _opts_de_widgets()
    pool = _pool_receta(df_all, manual, opts, an)
    filas, gen = _filas_receta(pool, blqs)
    q = _cantidades(blqs, filas, gen)
    guard = _recetas_guardadas()

    h1, h2 = st.columns([2.3, 1.3], vertical_alignment="bottom")
    h1.markdown(f"<div class='rec-top'><span><b>{len(manual)}</b> fijas</span><span><b>{n_obj}</b> objetivo</span>"
                f"<span><b>{max(0, n_obj - len(manual))}</b> huecos para la receta</span>"
                f"<span><b>{len(pool)}</b> preguntas pueden entrar</span></div>", unsafe_allow_html=True)
    _nom = ["—"] + guard["Nombre"].tolist()
    sel_g = h2.selectbox("Recetas guardadas", _nom, key="rec_guardada",
                         format_func=lambda n: "— Elegir receta guardada —" if n == "—" else n)
    if sel_g != "—" and ss.get("_rec_cargada") != sel_g:
        r = guard[guard["Nombre"] == sel_g].iloc[0]
        try:
            ss["_rec_pend"] = (_json.loads(r["Receta"] or "{}"), _json.loads(r["Opciones"] or "{}"))
        except ValueError:
            ss["_rec_pend"] = ({}, None)
        ss["_rec_cargada"] = sel_g
        st.rerun(scope="fragment")

    t1, t2, t3, t4 = st.tabs(["Resumen", "Reparto rápido", "Cantidades por bloque, tema y objetivo", "Opciones"])

    # ── Totales y avisos (se usan en Resumen y en el pie) ───────────────────
    tot = [sum(v[i] for v in q.values()) for i in range(3)]
    n_rec = sum(tot)
    total = len(manual) + n_rec
    man_dif = df_all[df_all["ID_Pregunta"].isin(manual)]["dificultad"].map(_dif_norm)
    mix = [tot[i] + int((man_dif == d).sum()) for i, d in enumerate(_DIFS)]
    avisos = []

    def disp_de(b, k):
        if b == _GEN:
            return next((h[2] for h in gen if h[0] == k), [0, 0, 0])
        if k == "__ALL__":
            return filas[b]["disp"]
        return next((h[2] for h in filas[b]["hijos"] if h[0] == k), [0, 0, 0])

    def nombre_de(b, k):
        if k == "__ALL__":
            return f"{b} (cualquier tema)"
        hit = next((h[1] for h in (gen if b == _GEN else filas[b]["hijos"]) if h[0] == k), k)
        return hit if b == _GEN else f"{b}, {hit}"

    for (b, k), v in q.items():
        av = disp_de(b, k)
        for i in range(3):
            if v[i] > av[i]:
                avisos.append(f"{nombre_de(b, k)}: pides {v[i]} de dificultad {_DIFL[i].lower()} y solo hay {av[i]}")
    for b in blqs:   # lo pedido en total por bloque y dificultad no puede superar lo disponible del bloque
        for i in range(3):
            pedido = sum(v[i] for (bb, k), v in q.items() if bb == b)
            if pedido > filas[b]["disp"][i] and not any(f"{b} (" in a or a.startswith(f"{b},") for a in avisos):
                avisos.append(f"{b}: en total pides {pedido} de dificultad {_DIFL[i].lower()} y solo hay {filas[b]['disp'][i]}")

    # ── 1) Resumen ────────────────────────────────────────────────────────────
    with t1:
        col = "var(--ok)" if total == n_obj else ("var(--err)" if total > n_obj else "var(--warn)")
        sub_t = ("coincide con el objetivo" if total == n_obj else
                 f"faltan {n_obj - total}" if total < n_obj else f"te pasas en {total - n_obj}")
        st.markdown(
            "<div class='rec-k'>"
            f"<div><span>Fijas</span><b>{len(manual)}</b><small>elegidas a mano</small></div>"
            f"<div><span>De la receta</span><b style='color:var(--primary)'>{n_rec}</b><small>se eligen al pulsar Generar</small></div>"
            f"<div><span>Total</span><b style='color:{col}'>{total} / {n_obj}</b><small>{sub_t}</small></div>"
            f"<div><span>Dificultad</span><b>{mix[0]} · {mix[1]} · {mix[2]}</b><small>fácil · media · difícil</small></div></div>",
            unsafe_allow_html=True)
        if sum(mix):
            pc = [round(100 * x / sum(mix)) for x in mix]
            st.markdown(f"<div class='rec-mixl'><span>Mezcla de dificultad del examen (fijas + receta)</span>"
                        f"<span>{pc[0]} % · {pc[1]} % · {pc[2]} %</span></div><div class='rec-mix'>"
                        + "".join(f"<span style='flex:{x or 0.0001};background:{c}'></span>" for x, c in
                                  zip(mix, ("var(--ok)", "var(--primary)", "var(--err)"))) + "</div>",
                        unsafe_allow_html=True)
        lineas = ""
        for b in blqs + ([_GEN] if gen else []):
            partes = [(k, v) for (bb, k), v in q.items() if bb == b and sum(v)]
            if not partes:
                continue
            n_b = sum(sum(v) for _, v in partes)
            fmd = [sum(v[i] for _, v in partes) for i in range(3)]
            org = " · ".join(("cualquier tema" if k == "__ALL__" else
                              (f"objetivo {k[6:]}" if k.startswith("__OBJ_") else f"tema {k}")) + f" ({sum(v)})"
                             for k, v in partes)
            nom = "Objetivos generales" if b == _GEN else nombre_bloque(b)
            lineas += (f"<div class='rec-l'><span><small>{'' if b == _GEN else b}</small>{nom.split(' — ', 1)[-1]}</span>"
                       f"<span class='o'>{org}</span><span class='mx'>"
                       + "".join(f"<span style='flex:{x or 0.0001};background:{c}'></span>" for x, c in
                                 zip(fmd, ("var(--ok)", "var(--primary)", "var(--err)")))
                       + f"</span><b>{n_b}</b></div>")
        if lineas:
            st.markdown(f"<div class='rec-sec'>Por bloque</div>{lineas}", unsafe_allow_html=True)
        else:
            st.info("La receta está vacía. Usa «Reparto rápido» o pon cantidades en «Cantidades por bloque, tema y objetivo».")
        chips = []
        if opts["evitar_meses"]:
            chips.append(f"evita usadas en {opts['evitar_meses']} meses")
        chips += [f"sin preguntas de {an[3].get(e, e)}" for e in opts["excl_examenes"]]
        chips += [f"excluye «{e}»" for e in opts["excl_etiquetas"]]
        if opts["solo_etiquetas"]:
            chips.append("solo " + ", ".join(f"«{e}»" for e in opts["solo_etiquetas"]))
        if opts["solo_sol"]:
            chips.append("solo con solución")
        if opts["excl_revisar"]:
            chips.append("sin anuladas ni «a revisar»")
        chips.append({"menos usadas": "primero las menos usadas", "azar": "al azar",
                      "discrimina": "primero las que mejor discriminan"}[opts["criterio"]])
        if opts["max_tema"]:
            chips.append(f"máx. {opts['max_tema']} por tema")
        if opts["max_obj"]:
            chips.append(f"máx. {opts['max_obj']} por objetivo")
        st.markdown("<div class='rec-ch'><span>Opciones:</span>" + "".join(f"<em>{c}</em>" for c in chips) + "</div>",
                    unsafe_allow_html=True)
        if avisos:
            st.markdown(f"<div class='rec-av'><b>{len(avisos)} aviso{'s' if len(avisos) != 1 else ''}</b> · "
                        + " · ".join(avisos[:4]) + (" …" if len(avisos) > 4 else "") + "</div>", unsafe_allow_html=True)

    # ── 2) Reparto rápido ────────────────────────────────────────────────────
    with t2:
        st.caption("Reparte un número de preguntas entre los bloques. Rellena «cualquier tema» de cada bloque; "
                   "lo que hayas pedido por tema u objetivo se mantiene y se suma.")
        r1, r2 = st.columns([1, 2.6])
        libres = max(0, n_obj - len(manual) - sum(sum(v) for (b, k), v in q.items() if k != "__ALL__"))
        n_auto = r1.number_input("Preguntas a repartir", min_value=0, max_value=500, value=libres, key="rq_n")
        bsel = r2.multiselect("Bloques", blqs, default=blqs, key="rq_blqs")
        with st.container(key="seg_rq_modo"):
            modo = st.radio("Entre bloques", ["Proporcional a las disponibles", "A partes iguales",
                                              "Según el temario (nº de temas)"], horizontal=True, key="rq_modo")
        with st.container(key="seg_rq_mix"):
            mezcla = st.radio("Dificultad", list(_MEZCLAS), horizontal=True, key="rq_mix")
        pct = _MEZCLAS[mezcla]
        if pct == "pers":
            pc1, pc2, pc3, _ = st.columns([1, 1, 1, 2])
            pct = (pc1.number_input("% fácil", 0, 100, 30, key="rq_pf"), pc2.number_input("% media", 0, 100, 50, key="rq_pm"),
                   pc3.number_input("% difícil", 0, 100, 20, key="rq_pd"))
        temas_b = {b: len(filas[b]["hijos"]) or 1 for b in bsel}
        peso = {b: (sum(filas[b]["disp"]) if modo.startswith("Proporcional") else
                    1 if modo.startswith("A partes") else temas_b[b]) for b in bsel}
        qb = _cuotas(int(n_auto), peso, {b: sum(filas[b]["disp"]) for b in bsel})
        rep = {}
        for b in bsel:
            w = dict(zip(_DIFS, pct if pct else filas[b]["disp"]))
            qd = _cuotas(qb[b], w, dict(zip(_DIFS, filas[b]["disp"])))
            rep[b] = [qd[d] for d in _DIFS]
        mxr = max([sum(v) for v in rep.values()] + [1])
        st.markdown("<div class='rec-sec'>Así quedaría «cualquier tema» en cada bloque</div>"
                    + "".join(f"<div class='rec-pr'><span>{nombre_bloque(b)}</span><span class='bar'><span style='width:"
                              f"{100 * sum(v) / mxr:.0f}%'></span></span><span class='m'>{v[0]}·{v[1]}·{v[2]}</span><b>{sum(v)}</b></div>"
                              for b, v in rep.items()), unsafe_allow_html=True)
        falta = int(n_auto) - sum(sum(v) for v in rep.values())
        if falta > 0:
            st.caption(f"⚠️ Con las opciones actuales solo hay preguntas para {int(n_auto) - falta}: faltan {falta}.")
        if st.button("Aplicar a la receta", type="primary", key="rq_aplicar", disabled=not bsel or not n_auto):
            nueva = {}
            for (b, k), v in q.items():
                if k != "__ALL__" and sum(v):
                    nueva.setdefault(b, {})[k] = dict(zip(_DIFS, v))
            for b, v in rep.items():
                if sum(v):
                    nueva.setdefault(b, {})["__ALL__"] = dict(zip(_DIFS, v))
            ss["_rec_pend"] = (nueva, None)
            st.rerun(scope="fragment")

    # ── 3) Cantidades ────────────────────────────────────────────────────────
    with t3:
        abiertos = ss.setdefault("_rq_open", set())
        c1, c2, c3 = st.columns([4, 1.2, 1.2], vertical_alignment="center")
        c1.caption("En la fila de cada bloque pones las de «cualquier tema»; despliégalo (▸) para pedir además "
                   "preguntas de un tema u objetivo concretos. «Total» lo suma todo.")
        if c2.button("▾ Desplegar todo" if len(abiertos) < len(blqs) else "▸ Plegar todo", key="rq_fold",
                     use_container_width=True):
            abiertos.clear() if len(abiertos) >= len(blqs) else abiertos.update(blqs)
        if c3.button("Poner todo a 0", key="rq_cero", use_container_width=True):
            ss["_rec_pend"] = ({}, None)
            st.rerun(scope="fragment")

        def fila(b, k, nombre, av, nivel, total_fila=None, sub=""):
            cols = st.columns([3.6, 0.95, 0.95, 0.95, 1.1, 0.5], vertical_alignment="center")
            if nivel == 0:
                ab = b in abiertos
                if cols[0].button(f"{'▾' if ab else '▸'}  {nombre}", key=f"rq_tog_{_rq_key(b, '', 0)}",
                                  type="tertiary"):
                    abiertos.symmetric_difference_update({b})   # sus filas se dibujan justo debajo
                if sub:
                    cols[0].caption(sub)
            else:
                cols[0].markdown(f"<div class='rq-h'>{nombre}</div>", unsafe_allow_html=True)
            for i in range(3):
                kk = _rq_key(b, k, i)
                warn = int(ss.get(kk, 0) or 0) > av[i]
                with cols[1 + i].container(key=f"rqc{'w' if warn else ''}_{kk}"):
                    st.number_input(_DIFL[i], min_value=0, max_value=200, step=1, key=kk, label_visibility="collapsed")
            cols[4].markdown(f"<span class='rq-d'>{av[0]} · {av[1]} · {av[2]}</span>", unsafe_allow_html=True)
            tt = sum(q[(b, k)]) if total_fila is None else total_fila
            cols[5].markdown(f"<b class='rq-t{' z' if not tt else ''}'>{tt}</b>", unsafe_allow_html=True)

        hd = st.columns([3.6, 0.95, 0.95, 0.95, 1.1, 0.5])
        for c, t in zip(hd, ["Bloque · tema · objetivo", "Fácil", "Media", "Difícil", "Disponibles", "Total"]):
            c.markdown(f"<span class='rq-hd'>{t}</span>", unsafe_allow_html=True)
        for b in blqs:
            n_b = sum(sum(v) for (bb, k), v in q.items() if bb == b)
            extra = [(k, v) for (bb, k), v in q.items() if bb == b and k != "__ALL__" and sum(v)]
            sub = (f"{sum(q[(b, '__ALL__')])} de cualquier tema + " + " + ".join(
                f"{sum(v)} del {'objetivo ' + k[6:] if k.startswith('__OBJ_') else 'tema ' + k}" for k, v in extra)) if extra else ""
            with st.container(key=f"rqb_{_rq_key(b, '', 0)}"):
                fila(b, "__ALL__", nombre_bloque(b), filas[b]["disp"], 0, n_b, sub)
                if b in abiertos:
                    for k, nm, av in filas[b]["hijos"]:
                        fila(b, k, nm, av, 1)
        if gen:
            st.markdown("<div class='rec-sec' style='margin-top:12px'>Objetivos generales (de cualquier bloque)</div>",
                        unsafe_allow_html=True)
            for k, nm, av in gen:
                fila(_GEN, k, nm, av, 1)

    # ── 4) Opciones ──────────────────────────────────────────────────────────
    with t4:
        o1, o2 = st.columns([1.2, 1], gap="medium")
        with o1.container(border=True, key="card_rec_o1"):
            st.markdown("**Qué preguntas pueden entrar**")
            with st.container(key="seg_rec_evitar"):
                st.radio("Evitar las usadas en…", ["No", "6 meses", "12 meses", "24 meses"], horizontal=True, key="rec_evitar")
            st.multiselect("No repetir preguntas de estos exámenes", list(an[3]), key="rec_excl_ex",
                           format_func=lambda e: an[3].get(e, e), placeholder="Ninguno",
                           help="Exámenes registrados (Análisis › Exámenes)")
            coms = sorted({str(x).strip() for x in df_all.get("comentario", pd.Series(dtype=str)).astype(str)
                           if str(x).strip() not in ("", "nan", "None")})
            e1, e2 = st.columns(2)
            e1.multiselect("Excluir etiquetas", coms, key="rec_excl_et", placeholder="Ninguna")
            e2.multiselect("Solo con estas etiquetas", coms, key="rec_solo_et", placeholder="Cualquiera")
            st.toggle("Solo preguntas con solución desarrollada", key="rec_sol")
            st.toggle("Excluir las anuladas o marcadas «a revisar» en Análisis", key="rec_revisar")
        with o2:
            with st.container(border=True, key="card_rec_o2"):
                st.markdown("**Cómo elegir entre las posibles**")
                with st.container(key="seg_rec_crit"):
                    st.radio("Criterio", ["Primero las menos usadas", "Al azar", "Primero las que mejor discriminan"],
                             horizontal=True, key="rec_criterio", label_visibility="collapsed")
                st.caption("«Mejor discriminan» usa los análisis guardados; las preguntas sin análisis van detrás.")
            with st.container(border=True, key="card_rec_o3"):
                st.markdown("**Límites**")
                l1, l2 = st.columns(2)
                l1.number_input("Máximo por tema (0 = sin límite)", 0, 50, key="rec_max_tema")
                l2.number_input("Máximo por objetivo (0 = sin límite)", 0, 50, key="rec_max_obj")
            with st.container(border=True, key="card_rec_o4"):
                st.markdown("**Recetas guardadas**")
                st.caption("Se guardan en la base de datos (hoja «Cfg_Recetas»): las tienes cada curso y las ven tus compañeros.")
                if guard.empty:
                    st.caption("Todavía no hay ninguna. Usa «Guardar como…» abajo.")
                for i, r in guard.iterrows():
                    g1, g2, g3 = st.columns([3, 0.8, 0.8], vertical_alignment="center")
                    g1.markdown(f"<span class='rq-g'><b>{r['Nombre']}</b> <small>{r['Descripcion']}</small></span>",
                                unsafe_allow_html=True)
                    if g2.button("Cargar", key=f"rq_load_{i}", type="tertiary"):
                        ss["_rec_pend"] = (_json.loads(r["Receta"] or "{}"), _json.loads(r["Opciones"] or "{}"))
                        ss["_rec_cargada"] = r["Nombre"]
                        st.rerun(scope="fragment")
                    if g3.button("Borrar", key=f"rq_del_{i}", type="tertiary"):
                        ss.excel_dfs[_RECETAS_SHEET] = guard[guard["Nombre"] != r["Nombre"]]
                        guardar_hojas([_RECETAS_SHEET])
                        st.rerun(scope="fragment")

    # ── Pie: resumen y botones ───────────────────────────────────────────────
    st.markdown(f"<div class='rec-sum'><span><b>{len(manual)}</b> fijas + <b>{n_rec}</b> de la receta = "
                f"<b style='color:{'var(--ok)' if total == n_obj else ('var(--err)' if total > n_obj else 'var(--warn)')}'>"
                f"{total}</b> / {n_obj}</span><span>Fácil <b>{tot[0]}</b> · Media <b>{tot[1]}</b> · Difícil <b>{tot[2]}</b></span></div>",
                unsafe_allow_html=True)

    def _receta_dict():
        out = {}
        for (b, k), v in q.items():
            if sum(v):
                out.setdefault(b, {})[k] = dict(zip(_DIFS, v))
        return out

    f1, _, f2, f3 = st.columns([1.1, 1.6, 1.2, 1.5])
    if f1.button("Quitar receta", key="rec_clear"):
        ss["auto_recipe"], ss["auto_opts"] = {}, {}
        for k in [k for k in ss.keys() if _es_rq_cantidad(k)]:
            del ss[k]
        ss["_rq_vals"] = {}
        st.rerun()
    if f2.button("Guardar como…", key="rec_saveas", use_container_width=True):
        ss["_rec_saving"] = not ss.get("_rec_saving", False)
    if f3.button("Usar esta receta", type="primary", key="rec_save", use_container_width=True):
        ss["auto_recipe"], ss["auto_opts"] = _receta_dict(), opts
        notify(f"✅ Receta lista: {n_rec} preguntas automáticas. Se eligen al pulsar «Generar» en Generar.")
        st.rerun()
    if ss.get("_rec_saving"):
        s1, s2 = st.columns([3, 1], vertical_alignment="bottom")
        nombre = s1.text_input("Nombre de la receta", value=ss.get("_rec_cargada", ""), key="rec_nombre",
                               placeholder="Parcial 1, Final ordinaria…")
        if s2.button("Guardar", type="primary", key="rec_save_ok", use_container_width=True) and not nombre.strip():
            st.error("Escribe un nombre para la receta.")
        elif ss.get("rec_save_ok") and nombre.strip():
            nb = len({b for (b, k), v in q.items() if sum(v) and b != _GEN})
            desc = f"{n_rec} preguntas · {nb} bloque{'s' if nb != 1 else ''}" + (
                f" · evita usadas {opts['evitar_meses']} meses" if opts["evitar_meses"] else "")
            fila_g = {"Nombre": nombre.strip(), "Receta": _json.dumps(_receta_dict(), ensure_ascii=False),
                      "Opciones": _json.dumps(opts, ensure_ascii=False), "Descripcion": desc,
                      "Fecha": datetime.date.today().isoformat()}
            ss.excel_dfs[_RECETAS_SHEET] = pd.concat([guard[guard["Nombre"] != nombre.strip()], pd.DataFrame([fila_g])],
                                                     ignore_index=True)
            guardar_hojas([_RECETAS_SHEET])
            ss["_rec_saving"], ss["_rec_cargada"] = False, nombre.strip()
            st.toast(f"Receta «{nombre.strip()}» guardada", icon="✅")
            st.rerun(scope="fragment")


def _elegir_receta(pool_ids, n, rng, df_lookup, exam_ids, opts, sin_tope=False, an=None):
    """Elige `n` preguntas de `pool_ids` según las opciones de la receta."""
    if not n or not pool_ids:
        return []
    an = an or _datos_analisis()
    sub = pd.DataFrame([{"ID_Pregunta": p, **df_lookup.get(p, {})} for p in pool_ids])
    ids = _filtrar_opciones(sub, opts, an)["ID_Pregunta"].tolist()
    rng.shuffle(ids)
    crit = opts.get("criterio", "menos usadas" if opts.get("prioridad", True) else "azar")
    if crit == "menos usadas":   # nunca usadas primero; después, las usadas hace más tiempo
        ids.sort(key=lambda p: str(df_lookup.get(p, {}).get("usada", "") or "").strip() or "0000")
    elif crit == "discrimina":
        ids.sort(key=lambda p: -an[2].get(p, -9))
    t_max = int(opts.get("max_tema", 0) or 0)
    o_max = int(opts.get("max_obj", 0) or 0)
    if sin_tope or (not t_max and not o_max):
        return ids[:n]
    ct, co = {}, {}
    for p in exam_ids:
        r = df_lookup.get(p, {})
        ct[(r.get("bloque"), str(r.get("Tema")))] = ct.get((r.get("bloque"), str(r.get("Tema"))), 0) + 1
        co[str(r.get("objetivo", ""))] = co.get(str(r.get("objetivo", "")), 0) + 1
    out = []
    for p in ids:
        if len(out) >= n:
            break
        r = df_lookup.get(p, {})
        t, o = (r.get("bloque"), str(r.get("Tema"))), str(r.get("objetivo", "") or "")
        if t_max and ct.get(t, 0) >= t_max:
            continue
        if o_max and o not in ("", "nan", "None") and co.get(o, 0) >= o_max:
            continue
        out.append(p)
        ct[t] = ct.get(t, 0) + 1
        co[o] = co.get(o, 0) + 1
    return out


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
        f"<div style='background:var(--primary-soft, #e8f4fd);border:1px solid var(--border2, #aed6f1);border-radius:8px;"
        f"padding:10px 16px;margin-bottom:10px;font-size:0.87em;color:var(--primary, #1a5276)'>"
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
            f"<span style='color:var(--text2, #555);font-size:0.85em'>"
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
            th1.markdown("<small style='color:var(--ui-ok, #27ae60)'><b>🟢 Fácil</b></small>",
                         unsafe_allow_html=True)
            th2.markdown("<small style='color:var(--ui-warn, #b7950b)'><b>🟡 Media</b></small>",
                         unsafe_allow_html=True)
            th3.markdown("<small style='color:var(--ui-err, #c0392b)'><b>🔴 Difícil</b></small>",
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
                    f"<span style='color:var(--muted, #888)'>🟢{n_ft} 🟡{n_mt} 🔴{n_dt}</span></small>",
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

        # ── Sección: por objetivo docente ────────────────────────────────────
        cfg_objs = st.session_state.get("cfg_objetivos", {})
        objs_blq = [cod for cod, data in cfg_objs.items()
                    if not data.get("bloque") or data["bloque"] == sel_blq]
        if objs_blq:
            st.markdown("##### 🎯 Por objetivo docente (acumulativo):")
            oh0, oh1, oh2, oh3 = st.columns([3, 1, 1, 1])
            oh0.markdown("<small><b>Objetivo</b></small>", unsafe_allow_html=True)
            oh1.markdown("<small style='color:var(--ui-ok, #27ae60)'><b>🟢 Fácil</b></small>", unsafe_allow_html=True)
            oh2.markdown("<small style='color:var(--ui-warn, #b7950b)'><b>🟡 Media</b></small>", unsafe_allow_html=True)
            oh3.markdown("<small style='color:var(--ui-err, #c0392b)'><b>🔴 Difícil</b></small>", unsafe_allow_html=True)
            for ocod in objs_blq:
                df_o = df_avail[df_avail["objetivo"].astype(str) == ocod] if "objetivo" in df_avail.columns else df_avail.iloc[0:0]
                n_fo = int((df_o["dificultad"].str.lower() == "facil").sum())
                n_mo = int((df_o["dificultad"].str.lower() == "media").sum())
                n_do = int((df_o["dificultad"].str.lower().isin(["dificil", "difícil"])).sum())
                o_saved = blq_saved.get(f"__OBJ_{ocod}", {})
                key_o = re.sub(r"[^a-zA-Z0-9]", "_", f"{sel_blq}_OBJ_{ocod}")
                oc0, oc1, oc2, oc3 = st.columns([3, 1, 1, 1])
                oc0.markdown(
                    f"<small><b>{ocod}</b> &nbsp;"
                    f"<span style='color:var(--muted, #888)'>🟢{n_fo} 🟡{n_mo} 🔴{n_do}</span></small>",
                    unsafe_allow_html=True
                )
                oc1.number_input("f", min_value=0, max_value=n_fo,
                                  value=int(o_saved.get("facil", 0)),
                                  key=f"af_{key_o}_f", label_visibility="collapsed")
                oc2.number_input("m", min_value=0, max_value=n_mo,
                                  value=int(o_saved.get("media", 0)),
                                  key=f"af_{key_o}_m", label_visibility="collapsed")
                oc3.number_input("d", min_value=0, max_value=n_do,
                                  value=int(o_saved.get("dificil", 0)),
                                  key=f"af_{key_o}_d", label_visibility="collapsed")

    # ── Total configurado (leyendo session_state + receta guardada) ───────────
    cfg_objs_total = st.session_state.get("cfg_objetivos", {})
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
        objs_blq_t = [cod for cod, data in cfg_objs_total.items()
                      if not data.get("bloque") or data["bloque"] == blq]
        for ocod in objs_blq_t:
            key_o = re.sub(r"[^a-zA-Z0-9]", "_", f"{blq}_OBJ_{ocod}")
            op = prev_b.get(f"__OBJ_{ocod}", {})
            total_cfg += (
                st.session_state.get(f"af_{key_o}_f", op.get("facil",  0)) +
                st.session_state.get(f"af_{key_o}_m", op.get("media",  0)) +
                st.session_state.get(f"af_{key_o}_d", op.get("dificil", 0))
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
        _cfg_objs_save = st.session_state.get("cfg_objetivos", {})
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

            objs_blq_s = [cod for cod, data in _cfg_objs_save.items()
                          if not data.get("bloque") or data["bloque"] == blq]
            for ocod in objs_blq_s:
                key_o = re.sub(r"[^a-zA-Z0-9]", "_", f"{blq}_OBJ_{ocod}")
                op = prev_b.get(f"__OBJ_{ocod}", {})
                of = st.session_state.get(f"af_{key_o}_f", op.get("facil",  0))
                om = st.session_state.get(f"af_{key_o}_m", op.get("media",  0))
                od = st.session_state.get(f"af_{key_o}_d", op.get("dificil", 0))
                if of + om + od > 0:
                    blq_r[f"__OBJ_{ocod}"] = {"facil": of, "media": om, "dificil": od}

            if blq_r:
                new_recipe[blq] = blq_r

        st.session_state["auto_recipe"] = new_recipe
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# PESTAÑAS
# ═════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────
# DESARROLLO (Bitácora): examen + banco + el editor en la página
# ─────────────────────────────────────────────────────────────────────────────
def _desarrollo_bitacora():
    import desarrollo_ui as DU
    from app_theme import kpi_html
    ss = st.session_state
    dev_qs = ss.dev_questions
    for q in dev_qs:
        q.update(DU.normalizar(q))
    q_ed = next((x for x in dev_qs if x["_uid"] == ss.get("dev_edit_uid")), None)
    if q_ed is not None:            # vista editor (la lista no se dibuja)
        _desarrollo_editor_gen(q_ed)
        return
    banco = DU.get_banco(ss.get("excel_dfs", {}))
    cfg = ss.get("exam_cfg", {}) or {}
    pts_dev = sum(DU.puntos(q) for q in dev_qs)
    n_test = len(ss.get("cache_examen") or []) or len(get_sel_ids())
    pts_test = DU._f(cfg.get("pts_test"), 0)
    pts_fund_cfg = DU._f(cfg.get("pts_fund"), 0)
    n_rub = sum(1 for q in dev_qs if q.get("criterios"))
    if pts_fund_cfg:
        ok = abs(pts_dev - pts_fund_cfg) < 0.01
        sub_tot = "cuadra con lo configurado en Exportar" if ok else f"en Exportar figuran {pts_fund_cfg:g} pts de desarrollo"
    else:
        ok, sub_tot = True, "puntos de desarrollo y test (Ver y exportar › Examen)"
    st.markdown(kpi_html([
        ("Desarrollo", len(dev_qs), f"pregunta{'s' if len(dev_qs) != 1 else ''} · {pts_dev:g} puntos", False),
        ("Test", n_test, f"preguntas · {pts_test:g} puntos" if pts_test else "preguntas", False),
        ("Total", f"{pts_dev + pts_test:g}", sub_tot, not ok),
        ("Rúbricas", f"{n_rub} de {len(dev_qs)}", "con criterios de corrección", False),
    ], compact=True), unsafe_allow_html=True)

    # ── Lista: preguntas de este examen ──
    h1, h2, h3, h4, h5, h6 = st.columns([1.9, 1, 1.45, 1.1, 1.15, 1.05], vertical_alignment="center")
    with h6:
        _nuevas_txt = DU.ui_importar_texto("dev_txt", "al examen")
    if _nuevas_txt:
        dev_qs.extend(_nuevas_txt)
        notify(f"✅ {len(_nuevas_txt)} pregunta(s) añadidas al examen desde texto.")
        st.rerun()
    h1.markdown("<div class='sec-title' style='margin:0'>Preguntas de este examen</div>", unsafe_allow_html=True)
    if h2.button("➕ Nueva", key="dev_nueva", type="primary", use_container_width=True):
        q = DU.nueva()
        dev_qs.append(q)
        ss["dev_edit_uid"] = q["_uid"]
        st.rerun()
    if h3.button(f"Añadir del banco · {len(banco)}", key="dev_banco_btn", use_container_width=True,
                 help="Elige preguntas del banco de desarrollo"):
        _dlg_banco_desarrollo()
    if dev_qs:
        h4.download_button("Descargar JSON", _dev_qs_to_json(dev_qs), file_name="preguntas_desarrollo.json",
                           mime="application/json", key="dev_json_dl", use_container_width=True,
                           help="Descarga las preguntas de este examen (con imágenes)")
    with h5.popover("Subir JSON", use_container_width=True):
        up = st.file_uploader("Preguntas de desarrollo (JSON)", type=["json"], key="dev_json_up")
        if up is not None and ss.get("_dev_json_upload_name") != up.name:
            try:
                nuevas = [DU.normalizar(q) for q in _dev_qs_from_json(up.getvalue())]
                dev_qs.extend(nuevas)
                ss["_dev_json_upload_name"] = up.name
                notify(f"✅ {len(nuevas)} pregunta(s) añadidas al examen")
                st.rerun()
            except Exception as e:
                st.error(f"No se ha podido leer el JSON: {e}")
    if not dev_qs:
        st.info("Este examen no tiene preguntas de desarrollo. Añádelas desde el banco o crea una nueva.")
        return
    accion = None
    for i, q in enumerate(dev_qs):
        apts = q["subapartados"]
        sol = bool(q["solucion_modelo"].strip() or any(str(a.get("solucion", "")).strip() for a in apts))
        sub = (f"{q.get('banco_id') or 'nueva · no está en el banco'} · "
               + (f"{len(apts)} apartados" if apts else "sin apartados") + " · "
               + ("solución" if sol else "sin solución") + (" + rúbrica" if q["criterios"] else ""))
        with st.container(border=True, key=f"card_devq_{q['_uid']}"):
            r = st.columns([0.3, 3.9, 1.0, 0.95, 0.38, 0.38, 0.38], vertical_alignment="center")
            r[0].markdown(f"**{i + 1}.**")
            enun = re.sub(r"\s+", " ", q["txt"]).strip() or "(sin enunciado)"
            r[1].markdown(f"<div class='devq-t'>{enun[:140]}</div><div class='devq-s'>{sub}</div>", unsafe_allow_html=True)
            if apts:
                r[2].markdown(f"<b>{DU.puntos(q):g} pts</b><div class='devq-s'>suma de apartados</div>", unsafe_allow_html=True)
            else:
                q["pts"] = r[2].number_input("Puntos", min_value=0.0, step=0.5, value=DU._f(q.get("pts"), 1.0),
                                             key=f"devpts_{q['_uid']}", label_visibility="collapsed",
                                             help="Puntos en este examen (no cambia el banco)")
            if r[3].button("✎ Editar", key=f"dev_ed_{q['_uid']}", use_container_width=True):
                ss["dev_edit_uid"] = q["_uid"]
                st.rerun()
            if r[4].button("↑", key=f"dev_up_{q['_uid']}", disabled=i == 0):
                accion = ("up", i)
            if r[5].button("↓", key=f"dev_dn_{q['_uid']}", disabled=i == len(dev_qs) - 1):
                accion = ("dn", i)
            if r[6].button("×", key=f"dev_rm_{q['_uid']}", help="Quitar del examen"):
                accion = ("rm", i)
    if accion:
        t, i = accion
        if t == "rm":
            dev_qs.pop(i)
        else:
            j = i - 1 if t == "up" else i + 1
            dev_qs[i], dev_qs[j] = dev_qs[j], dev_qs[i]
        st.rerun()
    st.caption("Los puntos son de este examen y no cambian los del banco.")


def _desarrollo_editor_gen(q):
    """Generador › Desarrollo, vista editor: barra fija arriba y el editor a todo el ancho."""
    import desarrollo_ui as DU
    ss = st.session_state
    dev_qs = ss.dev_questions
    i = dev_qs.index(q)
    with st.container(border=True, key="dev_bar"):
        c = st.columns([1.5, 2.2, 0.42, 0.7, 0.42, 1.75, 1.4, 1.6], vertical_alignment="center")
        if c[0].button("← Volver al examen", key="dev_back", use_container_width=True):
            ss.pop("dev_edit_uid", None)
            st.rerun()
        c[1].markdown(f"<div class='devq-t' style='font-size:1.05rem'>Pregunta {i + 1} · editando</div>"
                      f"<div class='devq-s'>{q.get('banco_id') or 'nueva (no está en el banco)'}"
                      f"{' · ' + q['bloque'] if q.get('bloque') else ''}{' · Tema ' + q['tema'] if q.get('tema') else ''}</div>",
                      unsafe_allow_html=True)
        if c[2].button("‹", key="dev_prev", use_container_width=True, disabled=i == 0, help="Pregunta anterior"):
            ss["dev_edit_uid"] = dev_qs[i - 1]["_uid"]
            st.rerun()
        c[3].markdown(f"<div class='devbar-pos'>{i + 1} de {len(dev_qs)}</div>", unsafe_allow_html=True)
        if c[4].button("›", key="dev_next", use_container_width=True, disabled=i >= len(dev_qs) - 1,
                       help="Pregunta siguiente"):
            ss["dev_edit_uid"] = dev_qs[i + 1]["_uid"]
            st.rerun()
        guardar = c[5].button("Guardar en el banco", type="primary", key=f"dev_save_{q['_uid']}", use_container_width=True,
                              help="Guarda la pregunta (sin las imágenes) para reutilizarla en otros exámenes")
        copia = c[6].button("Guardar copia", key=f"dev_copy_{q['_uid']}", use_container_width=True,
                            help="Crea una pregunta nueva en el banco con este contenido")
        if c[7].button("Quitar del examen", key=f"dev_rm2_{q['_uid']}", use_container_width=True):
            dev_qs.remove(q)
            ss.pop("dev_edit_uid", None)
            st.rerun()
        aviso = st.container()
    with st.container(key=f"seg_devmode_{q['_uid']}"):
        m = st.radio("Escritura", ["Markdown (recomendado)", "LaTeX puro"], horizontal=True,
                     index=0 if q.get("modo") != "latex" else 1, key=f"devmodo_{q['_uid']}")
    q["modo"] = "latex" if m.startswith("LaTeX") else "markdown"
    DU.editor(q, f"dq_{q['_uid']}", list(ss.bloques or []), pts_en_editor=False)
    st.caption("Los cambios valen ya para este examen; «Guardar en el banco» los guarda también para otros.")
    # después del editor: así se guarda también el último cambio escrito
    if guardar or copia:
        if not q["txt"].strip():
            aviso.error("Escribe el enunciado antes de guardarla.")
        else:
            pid = DU.guardar_en_banco(q, nueva_copia=bool(copia))
            notify(f"✅ {'Copia guardada' if copia else 'Guardada'} en el banco como {pid}.")
            st.rerun()


def _dev_anadir_del_banco(pid: str):
    import desarrollo_ui as DU
    ss = st.session_state
    banco = DU.get_banco(ss.get("excel_dfs", {}))
    r = banco[banco["ID"] == pid]
    if not r.empty and pid not in {q.get("banco_id") for q in ss.dev_questions}:
        ss.dev_questions.append(DU.fila_a_pregunta(r.iloc[0]))


@st.dialog("Añadir preguntas del banco de desarrollo", width="large", on_dismiss="rerun")
def _dlg_banco_desarrollo():
    import desarrollo_ui as DU
    ss = st.session_state
    banco = DU.get_banco(ss.get("excel_dfs", {}))
    if banco.empty:
        st.info("El banco está vacío. Guarda preguntas con «Guardar en el banco» o créalas en Gestor › Desarrollo "
                "(también puedes importar allí vuestros JSON antiguos).")
        return
    f1, f2, f3 = st.columns([2, 1.2, 1])
    qtxt = f1.text_input("Buscar", key="dev_bq", placeholder="🔍 Enunciado o ID", label_visibility="collapsed")
    fb = f2.selectbox("Bloque", ["Todos"] + list(ss.bloques or []), key="dev_bb", label_visibility="collapsed",
                      format_func=lambda b: "Bloque: todos" if b == "Todos" else nombre_bloque(b))
    temas_b = sorted({t for t in (banco["Tema"] if fb == "Todos" else banco[banco["Bloque"] == fb]["Tema"]) if t},
                     key=lambda t: (len(t), t))
    ft = f3.selectbox("Tema", ["Todos"] + temas_b, key="dev_bt", label_visibility="collapsed",
                      format_func=lambda t: "Tema: todos" if t == "Todos" else f"Tema {t}")
    b = banco
    if fb != "Todos":
        b = b[b["Bloque"] == fb]
    if ft != "Todos":
        b = b[b["Tema"] == ft]
    if qtxt.strip():
        m = qtxt.strip().lower()
        b = b[(b["Enunciado"].str.lower().str.contains(m, regex=False)) | (b["ID"].str.lower().str.contains(m, regex=False))]
    en_ex = {q.get("banco_id") for q in ss.dev_questions}
    st.caption(f"{len(b)} de {len(banco)} preguntas · ya en el examen: {len(en_ex - {''})}")
    with st.container(height=440, key="card_dev_banco"):
        if b.empty:
            st.caption("No hay preguntas con estos filtros.")
        for _, r_ in b.iterrows():
            dentro = r_["ID"] in en_ex
            rr = st.columns([3.6, 0.9, 0.7, 0.9], vertical_alignment="center")
            _en = re.sub(r"\s+", " ", r_["Enunciado"])[:130]
            napt = len(DU._jl(r_["Apartados"], []))
            rr[0].markdown(f"<div class='devq-s'>{r_['ID']} · {nombre_bloque(r_['Bloque']) if r_['Bloque'] else 'sin bloque'}"
                           f"{' · T' + r_['Tema'] if r_['Tema'] else ''}{f' · {napt} apartados' if napt else ''}</div>"
                           f"<div class='devq-t'>{_en}</div>", unsafe_allow_html=True)
            rr[1].markdown(f"<span class='devq-s'>{('usada ' + r_['Usada'][:7]) if r_['Usada'] else 'nunca usada'}</span>",
                           unsafe_allow_html=True)
            rr[2].markdown(f"<b>{r_['Puntos']} pt</b>", unsafe_allow_html=True)
            rr[3].button("Añadida" if dentro else "Añadir", key=f"dev_add_{r_['ID']}", disabled=dentro,
                         type="secondary" if dentro else "primary", use_container_width=True,
                         on_click=_dev_anadir_del_banco, args=(r_["ID"],))
    if st.button("Listo", type="primary", key="dev_banco_ok"):
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# PREVIEW (Bitácora): el examen como lista + panel lateral + avisos + acciones
# ─────────────────────────────────────────────────────────────────────────────
def _historial_cambios():
    """Preview (Bitácora): historial de cambios a mano con deshacer, rehacer y volver al examen generado."""
    ss = st.session_state
    hechos = [x.get("cambio", "") for x in ss.get("pv_undo") or [] if x.get("cambio")]
    por_rehacer = [x.get("cambio", "") for x in ss.get("pv_redo") or [] if x.get("cambio")]
    n = E.n_cambios()
    with st.container(key="pvc_hist").expander(f"Historial de cambios{f' · {len(hechos)}' if hechos else ''}", expanded=True):
        if not hechos and not por_rehacer:
            st.markdown("<div class='pv-n'>Aún no has cambiado nada a mano. Lo que hagas aquí (cambiar, quitar, mover o "
                        "fijar preguntas) aparecerá en esta lista y se podrá deshacer.</div>", unsafe_allow_html=True)
        else:
            filas = "".join(f"<div class='pvh-r{' u' if i == 0 else ''}'><span>{len(hechos) - i}</span>{c}</div>"
                            for i, c in enumerate(reversed(hechos[-8:])))
            if len(hechos) > 8:
                filas += f"<div class='pv-n'>… y {len(hechos) - 8} cambios anteriores</div>"
            if por_rehacer:
                filas += "".join(f"<div class='pvh-r d'><span>↷</span>{c}</div>" for c in reversed(por_rehacer[-3:]))
            st.markdown(filas, unsafe_allow_html=True)
        if st.button("↶ Deshacer", key="pv_undo_b", disabled=not hechos, use_container_width=True,
                     help=f"Vuelve a como estaba antes de «{hechos[-1]}»" if hechos else None):
            E.deshacer(); st.rerun()
        if hechos:
            st.caption(f"Deshace «{hechos[-1]}».")
        if st.button("↷ Rehacer", key="pv_redo_b", disabled=not por_rehacer, use_container_width=True):
            E.rehacer(); st.rerun()
        if por_rehacer:
            st.caption(f"Vuelve a aplicar «{por_rehacer[-1]}».")
        if st.button("Volver al examen generado", key="pv_base_b", use_container_width=True,
                     disabled=not (n and ss.get("pv_base"))):
            E.volver_generado(); st.rerun()
        if n and ss.get("pv_base"):
            st.caption(f"Descarta {'el cambio' if n == 1 else f'los {n} cambios'} a mano y deja el examen como salió al pulsar Generar "
                       "(también se puede deshacer).")


def _avisos_preguntas(cache):
    """{ID: [(texto, clase)]} con: usada hace poco, sin solución y lo que digan los análisis guardados."""
    import analisis_lib as _A
    res = _A.get_resultados(st.session_state.get("excel_dfs", {}))
    ult = {}
    if not res.empty:
        for _, r in res.sort_values("Fecha").groupby("ID_Pregunta").tail(1).iterrows():
            ult[r["ID_Pregunta"]] = r
    hoy = datetime.date.today()
    out = {}
    for p in cache:
        pid = p.get("ID_Pregunta")
        av = []
        u = str(p.get("usada", "") or "").strip()[:10]
        if u and u not in ("nan", "None"):
            try:
                d = datetime.date.fromisoformat(u)
                meses = (hoy.year - d.year) * 12 + hoy.month - d.month
                if meses < 12:
                    av.append((f"usada hace {meses} mes{'es' if meses != 1 else ''}" if meses else "usada este mes", "u"))
            except ValueError:
                pass
        if not str(p.get("solucion", "") or "").strip() or str(p.get("solucion")) in ("nan", "None"):
            av.append(("sin solución", "w"))
        r = ult.get(pid)
        if r is not None:
            ex = r["ID_Examen"]
            try:
                dsc = float(r["Discriminacion"])
            except ValueError:
                dsc = None
            if r["Decision"] == "anular":
                av.append((f"anulada · {ex}", "d"))
            elif dsc is not None and dsc < 0:
                av.append((f"discrimina al revés · {ex}", "d"))
            elif dsc is not None and dsc < 0.15:
                av.append((f"discrimina poco · {ex}", "d"))
            if str(r["Revisar_Distractores"]) in ("1", "True"):
                av.append(("reescribir distractores", "w"))
        out[pid] = av
    return out


def _sustituir(i: int, nueva: dict):
    ss = st.session_state
    _antes = E.snap()
    cache = ss.cache_examen = list(ss.cache_examen)
    _old = cache[i].get("ID_Pregunta")
    cache[i] = nueva
    E.registrar(f"Cambiada la {i + 1} ({_old} → {nueva.get('ID_Pregunta')})", "cambiadas", _antes)
    notify(f"Pregunta {i + 1} cambiada por {nueva.get('ID_Pregunta')}.")


@st.dialog("Cambiar pregunta", width="large")
def _dlg_cambiar(i: int):
    """Elige la pregunta que sustituye a la i: mismo tema o bloque, misma dificultad o cualquiera, fuera del examen."""
    import analisis_lib as _A
    ss = st.session_state
    cache = ss.cache_examen
    p = cache[i]
    df = ss.df_preguntas
    dentro = {x.get("ID_Pregunta") for x in cache}
    st.markdown(f"<div class='cb-act'><span>Pregunta {i + 1} · {p.get('ID_Pregunta')} · {nombre_bloque(str(p.get('bloque', '')))} · "
                f"T{str(p.get('Tema', '')).removesuffix('.0')} · {p.get('dificultad', '')}</span>"
                f"<b>{str(p.get('enunciado', ''))[:220]}</b></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.1, 1.1, 1.6], vertical_alignment="bottom")
    amb = c1.radio("De dónde", ["Mismo tema", "Todo el bloque"], horizontal=True, key=f"cb_amb_{i}")
    dif = c2.radio("Dificultad", [f"{p.get('dificultad', '')}", "Cualquiera"], horizontal=True, key=f"cb_dif_{i}")
    q = c3.text_input("Buscar", key=f"cb_q_{i}", placeholder="Buscar en el enunciado o el ID", label_visibility="collapsed")
    cand = df[(df["bloque"] == p.get("bloque")) & (~df["ID_Pregunta"].isin(dentro))]
    if amb == "Mismo tema":
        cand = cand[cand["Tema"].astype(str).str.removesuffix(".0") == str(p.get("Tema", "")).removesuffix(".0")]
    if dif != "Cualquiera":
        cand = cand[cand["dificultad"].map(_dif_norm) == _dif_norm(p.get("dificultad", ""))]
    if q.strip():
        ql = q.strip().lower()
        cand = cand[cand["enunciado"].astype(str).str.lower().str.contains(ql, regex=False)
                    | cand["ID_Pregunta"].astype(str).str.lower().str.contains(ql, regex=False)]
    cand = cand.assign(_u=cand["usada"].astype(str).str.strip().replace({"nan": "", "None": ""}).replace("", "0000")).sort_values("_u")
    res = _A.get_resultados(ss.get("excel_dfs", {}))
    ult = {}
    if not res.empty:
        for _, r in res.sort_values("Fecha").groupby("ID_Pregunta").tail(1).iterrows():
            ult[r["ID_Pregunta"]] = r
    st.caption(f"{len(cand)} pregunta(s) que no están en el examen · primero las nunca usadas y las usadas hace más tiempo")
    with st.container(height=430, key="cb_lista"):
        if cand.empty:
            st.info("No hay preguntas con estos criterios. Prueba con «Todo el bloque» o «Cualquiera».")
        for r in cand.head(40).to_dict("records"):
            u = str(r.get("usada", "") or "").strip()[:10]
            u = "" if u in ("nan", "None") else u
            an = ult.get(r["ID_Pregunta"])
            an_txt = ""
            if an is not None and str(an["Pct_Acierto"]).strip():
                an_txt = f"<span class='pv-chip m'>{float(an['Pct_Acierto']):.0f}% aciertos en {an['ID_Examen']}</span>"
            ops = r.get("opciones_list") or []
            corr = {"A": 0, "B": 1, "C": 2, "D": 3}.get(str(r.get("letra_correcta", "")).upper(), -1)
            with st.container(border=True, key=f"cb_c_{r['ID_Pregunta']}"):
                h1, h2 = st.columns([5, 1], vertical_alignment="center")
                dk = _dif_norm(r.get("dificultad", ""))
                h1.markdown(f"<div class='pv-meta'><span class='id'>{r['ID_Pregunta']}</span>"
                            f"<span>T{str(r.get('Tema', '')).removesuffix('.0')}</span>"
                            f"<span class='pv-chip {'f' if dk == 'facil' else ('d' if dk == 'dificil' else 'm')}'>{r.get('dificultad', '')}</span>"
                            f"<span class='pv-chip {'u' if u else 'n'}'>{'usada ' + u if u else 'nunca usada'}</span>{an_txt}</div>",
                            unsafe_allow_html=True)
                if h2.button("Elegir", type="primary", key=f"cb_ok_{r['ID_Pregunta']}", use_container_width=True):
                    _sustituir(i, {k: v for k, v in r.items() if k != "_u"})
                    st.rerun()
                st.markdown(f"<div class='cb-en'>{r.get('enunciado', '')}</div>"
                            + "".join(f"<div class='cb-op{' ok' if j == corr else ''}'>{'abcd'[j]}) {o}{' ✓' if j == corr else ''}</div>"
                                      for j, o in enumerate(ops[:4])), unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    if b1.button("Elegir al azar (la menos usada)", key=f"cb_azar_{i}", use_container_width=True, disabled=cand.empty):
        _sustituir(i, cand.iloc[0].drop(labels=["_u"]).to_dict())
        st.rerun()
    if b2.button("Cancelar", key=f"cb_no_{i}", use_container_width=True):
        st.rerun()


def _cambiar_pregunta(i: int) -> bool:
    """Sustituye la pregunta i de la vista previa por otra del mismo tema y dificultad (la menos usada)."""
    ss = st.session_state
    cache = ss.cache_examen
    p = cache[i]
    dentro = {x.get("ID_Pregunta") for x in cache}
    df = ss.df_preguntas
    base = df[(df["bloque"] == p.get("bloque")) & (df["dificultad"].map(_dif_norm) == _dif_norm(p.get("dificultad", "")))
              & (~df["ID_Pregunta"].isin(dentro))]
    opts = ss.get("auto_opts") or {}
    for cand in (base[base["Tema"].astype(str) == str(p.get("Tema"))], base):
        if opts:
            cand = _filtrar_opciones(cand, opts)
        if not cand.empty:
            cand = cand.assign(_u=cand["usada"].astype(str).str.strip().replace({"nan": "", "None": ""}).replace("", "0000"))
            nueva = cand.sort_values("_u").iloc[0].drop(labels=["_u"]).to_dict()
            cache[i] = nueva
            return True
    return False


def _preview_bitacora(cache, show_sol, vista):
    import desarrollo_ui as DU
    ss = st.session_state
    cfg = ss.get("exam_cfg", {}) or {}
    dev_qs = ss.get("dev_questions", []) or []
    editable = vista == "Vista previa" and not E.bloqueado()
    avisos = _avisos_preguntas(cache)
    pts_dev = sum(DU.puntos(q) for q in dev_qs)
    pts_test = DU._f(cfg.get("pts_test"), 0)
    filtro = ss.get("pv_filtro")
    fijas = set(get_sel_ids())

    col_m, col_p = st.columns([1, 0.36], gap="medium")
    with col_m:
        asig = cfg.get("asig") or (ss.get("cfg_general", {}) or {}).get("asignatura", "") or ""
        tipo = cfg.get("tipo", "") or "Examen"
        st.markdown(f"<div class='pv-cab'><small>{asig}</small><div class='t'>{tipo}"
                    f"{' · ' + str(cfg.get('fecha')) if cfg.get('fecha') else ''}</div>"
                    f"<div class='s'>{len(dev_qs)} de desarrollo ({pts_dev:g} pts) · {len(cache)} de test"
                    f"{' (' + format(pts_test, 'g') + ' pts)' if pts_test else ''}"
                    f"{' · ' + vista if not editable else ''}</div></div>", unsafe_allow_html=True)
        _render_checks_prev(cache, vista)
        if filtro:
            fx1, fx2 = st.columns([4, 1], vertical_alignment="center")
            fx1.markdown(f"Mostrando solo las preguntas con aviso: **{filtro}**")
            if fx2.button("Ver todas", key="pv_fclear", use_container_width=True):
                ss.pop("pv_filtro", None)
                st.rerun()
        if dev_qs and not filtro:
            st.markdown(f"<div class='pv-parte'><b>Parte I · Desarrollo</b><span>{len(dev_qs)} preguntas · {pts_dev:g} puntos</span></div>",
                        unsafe_allow_html=True)
            for n, q in enumerate(dev_qs, 1):
                apts = q.get("subapartados") or []
                sol = bool(str(q.get("solucion_modelo", "")).strip() or any(str(a.get("solucion", "")).strip() for a in apts))
                with st.container(border=True, key=f"pvd_{n}"):
                    chips = (f"<span class='pv-chip m'>{DU.puntos(q):g} pts</span>"
                             + (f"<span class='pv-chip n'>{len(apts)} apartados</span>" if apts else "")
                             + ("" if sol else "<span class='pv-chip w'>sin solución modelo</span>")
                             + ("" if q.get("criterios") else "<span class='pv-chip n'>sin rúbrica</span>"))
                    st.markdown(f"<div class='pv-meta'><b>{n}.</b>{chips}</div>", unsafe_allow_html=True)
                    st.markdown(q.get("txt", "") or "*(sin enunciado)*")
                    for j, a in enumerate(apts):
                        st.markdown(f"**{DU.etiqueta_apt(j, q.get('numeracion_apt', 'abc'))})** {a.get('enunciado', '')}  "
                                    f"*({DU._f(a.get('puntos'), 0):g} pt)*")
        st.markdown(f"<div class='pv-parte'><b>Parte II · Test</b><span>{len(cache)} preguntas"
                    f"{' · ' + format(pts_test, 'g') + ' puntos' if pts_test else ''}</span></div>", unsafe_allow_html=True)
        # Grupos consecutivos por bloque (respeta el orden del examen)
        grupos = []
        for i, p in enumerate(cache):
            av = avisos.get(p.get("ID_Pregunta", ""), [])
            if filtro and not any(filtro in t for t, _ in av):
                continue
            if not grupos or grupos[-1][0] != p.get("bloque"):
                grupos.append((p.get("bloque"), []))
            grupos[-1][1].append(i)
        g1, g2, _ = st.columns([1.1, 1.1, 4])
        if g1.button("▾ Desplegar todo", key="pv_open_all", use_container_width=True):
            ss["pv_abiertos"], ss["pv_ver"] = True, ss.get("pv_ver", 0) + 1
        if g2.button("▸ Plegar todo", key="pv_close_all", use_container_width=True):
            ss["pv_abiertos"], ss["pv_ver"] = False, ss.get("pv_ver", 0) + 1
        # el sufijo invisible cambia al pulsar «todo»: así los desplegables vuelven a abrirse o cerrarse
        _zw = "​" * (ss.get("pv_ver", 0) % 7)
        accion = None
        for blq, idxs in grupos:
            difs_b = [_dif_norm(cache[i].get("dificultad", "")) for i in idxs]
            n_av = sum(1 for i in idxs if avisos.get(cache[i].get("ID_Pregunta", "")))
            label = (f"**{nombre_bloque(str(blq))}** — {len(idxs)} pregunta{'s' if len(idxs) != 1 else ''} · "
                     f"{difs_b.count('facil')} F · {difs_b.count('media')} M · {difs_b.count('dificil')} D"
                     + (f" · {n_av} con aviso" if n_av else "") + _zw)
            with st.expander(label, expanded=ss.get("pv_abiertos", True)):
                for i in idxs:
                    p = cache[i]
                    pid = p.get("ID_Pregunta", "")
                    av = avisos.get(pid, [])
                    dl = _dif_norm(p.get("dificultad", ""))
                    with st.container(border=True, key=f"pvq_{i}"):
                        hm, ha = st.columns([3, 2.1], vertical_alignment="center")
                        chips = (f"<span class='pv-chip {'f' if dl == 'facil' else ('d' if dl == 'dificil' else 'm')}'>{p.get('dificultad', '')}</span>"
                                 + ("<span class='pv-chip ok'>fija</span>" if pid in fijas else "")
                                 + "".join(f"<span class='pv-chip {c}'>{t}</span>" for t, c in av))
                        hm.markdown(f"<div class='pv-meta'><b>{i + 1}.</b><span class='id'>{pid}</span>"
                                    f"<span>T{str(p.get('Tema', '')).removesuffix('.0')}</span>{chips}</div>",
                                    unsafe_allow_html=True)
                        if editable:
                            with ha.container(horizontal=True, gap="small", key=f"pvact_{i}"):
                                if st.button("↻ Cambiar", key=f"pv_cb_{i}", help="Cambiar por otra del mismo tema y dificultad"):
                                    accion = ("cambiar", i)
                                if st.button("✎", key=f"pv_ed_{i}", help="Editar la pregunta"):
                                    accion = ("editar", i)
                                if st.button("📌", key=f"pv_fx_{i}", help="Fijar (que se mantenga al generar de nuevo)",
                                             disabled=pid in fijas):
                                    accion = ("fijar", i)
                                if st.button("↑", key=f"pv_up_{i}", disabled=i == 0):
                                    accion = ("up", i)
                                if st.button("↓", key=f"pv_dn_{i}", disabled=i == len(cache) - 1):
                                    accion = ("dn", i)
                                if st.button("×", key=f"pv_rm_{i}", help="Quitar del examen"):
                                    accion = ("rm", i)
                        with st.container(key=f"pven_{i}"):   # enunciado en negrita (CSS)
                            st.markdown(str(p.get("enunciado", "")))
                        ops = p.get("opciones_list") or []
                        corr = {"A": 0, "B": 1, "C": 2, "D": 3}.get(str(p.get("letra_correcta", "")).upper(), -1)
                        with st.container(key=f"pvops_{i}"):
                            for j, o in enumerate(ops[:4]):
                                t = f"{'abcd'[j]}) {o}"
                                if show_sol and j == corr:
                                    with st.container(key=f"pvok_{i}"):   # correcta con fondo verde (CSS)
                                        st.markdown(f"{t} ✓")
                                else:
                                    st.markdown(t)
        if accion:
            t, i = accion
            if t == "cambiar":
                _dlg_cambiar(i)          # ventana para elegir la sustituta (no recarga la página)
            elif t == "editar":
                ss["_open_q"] = cache[i].get("ID_Pregunta")
            elif t == "fijar":
                E.registrar(f"Fijada la {i + 1} ({cache[i].get('ID_Pregunta')})", "fijadas")
                set_sel_ids(get_sel_ids() + [cache[i].get("ID_Pregunta")])
            elif t in ("up", "dn"):
                j = i - 1 if t == "up" else i + 1
                E.registrar(f"Movida la {i + 1} {'arriba' if t == 'up' else 'abajo'}", "movidas")
                cache = ss.cache_examen = list(cache)
                cache[i], cache[j] = cache[j], cache[i]
            elif t == "rm":
                E.registrar(f"Quitada la {i + 1} ({cache[i].get('ID_Pregunta')})", "quitadas")
                cache = ss.cache_examen = list(cache)
                cache.pop(i)
            if t != "cambiar":
                st.rerun()

    # ── Panel lateral ──
    with col_p.container(key="pv_panel"):
        n_test = len(cache)
        if editable:
            _historial_cambios()
        minutos = round(1.5 * n_test + 15 * pts_dev)
        with st.container(key="pvc_res").expander("Resumen", expanded=True):
            st.markdown("<div class='pv-ph'>Resumen</div>"
                        f"<div class='pv-kv'><span>Preguntas</span><b>{len(dev_qs)} + {n_test}</b></div>"
                        f"<div class='pv-kv'><span>Puntos</span><b>{pts_dev:g} + {pts_test:g} = {pts_dev + pts_test:g}</b></div>"
                        f"<div class='pv-kv'><span>Tiempo estimado</span><b>≈ {minutos} min</b></div>"
                        "<div class='pv-n'>1,5 min por pregunta de test y 15 min por punto de desarrollo</div>",
                        unsafe_allow_html=True)
        difs = [_dif_norm(p.get("dificultad", "")) for p in cache]
        cnt = [difs.count("facil"), difs.count("media"), difs.count("dificil")]
        with st.container(key="pvc_dif").expander("Dificultad del test", expanded=True):
            pc = [round(100 * c / n_test) if n_test else 0 for c in cnt]
            st.markdown("<div class='pv-ph'>Dificultad del test</div><div class='pv-mix'>"
                        + "".join(f"<span style='flex:{c or 0.0001};background:{col}'></span>" for c, col in
                                  zip(cnt, ("var(--ok)", "var(--primary)", "var(--err)")))
                        + f"</div><div class='pv-kv3'><span>{cnt[0]} ({pc[0]} %)</span><span>{cnt[1]} ({pc[1]} %)</span>"
                          f"<span>{cnt[2]} ({pc[2]} %)</span></div>", unsafe_allow_html=True)
        blqs = {}
        for p in cache:
            blqs[p.get("bloque", "")] = blqs.get(p.get("bloque", ""), 0) + 1
        mx = max(blqs.values() or [1])
        with st.container(key="pvc_blq").expander("Por bloque", expanded=False):
            st.markdown("<div class='pv-ph'>Por bloque</div>" + "".join(
                f"<div class='pv-b'><span>{b}</span><span class='bar'><span style='width:{100 * n / mx:.0f}%'></span></span><b>{n}</b></div>"
                for b, n in sorted(blqs.items(), key=lambda kv: orden_bloque_g(kv[0]))), unsafe_allow_html=True)
        letras = [str(p.get("letra_correcta", "")).upper() for p in cache]
        with st.container(key="pvc_letras").expander("Respuestas correctas", expanded=False):
            st.markdown("<div class='pv-ph'>Respuestas correctas</div><div class='pv-l'>"
                        + "".join(f"<div><small>{l}</small><b>{letras.count(l)}</b></div>" for l in "ABCD")
                        + "</div><div class='pv-n'>" + ("Se barajan al exportar." if vista == "Vista previa" else vista) + "</div>",
                        unsafe_allow_html=True)
        # Uso, cobertura, análisis anteriores y origen
        hoy = datetime.date.today()
        usos = [str(p.get("usada", "") or "").strip()[:10] for p in cache]
        nunca = sum(1 for u in usos if not u or u in ("nan", "None"))
        viejas = sum(1 for u in usos if u and u not in ("nan", "None") and es_uso_antiguo(u, 12))
        with st.container(key="pvc_uso").expander("Uso de las preguntas", expanded=False):
            st.markdown("<div class='pv-ph'>Uso de las preguntas</div><div class='pv-l3'>"
                        f"<div><b>{nunca}</b><small>nunca usadas</small></div>"
                        f"<div><b>{viejas}</b><small>hace más de un año</small></div>"
                        f"<div><b>{n_test - nunca - viejas}</b><small>en el último año</small></div></div>",
                        unsafe_allow_html=True)
        temas = {}
        for p in cache:
            k_ = (p.get("bloque"), str(p.get("Tema", "")).removesuffix(".0"))
            temas[k_] = temas.get(k_, 0) + 1
        con_obj = sum(1 for p in cache if str(p.get("objetivo", "") or "").strip() not in ("", "nan", "None"))
        con_sol = sum(1 for p in cache if str(p.get("solucion", "") or "").strip() not in ("", "nan", "None"))
        top_t = max(temas.items(), key=lambda kv: kv[1]) if temas else None
        with st.container(key="pvc_cob").expander("Cobertura", expanded=False):
            st.markdown("<div class='pv-ph'>Cobertura</div>"
                        f"<div class='pv-kv'><span>Temas distintos</span><b>{len(temas)}</b></div>"
                        + (f"<div class='pv-kv'><span>Tema con más preguntas</span><b>T{top_t[0][1]} · {top_t[1]}</b></div>" if top_t else "")
                        + f"<div class='pv-kv'><span>Con objetivo docente</span><b>{con_obj} / {n_test}</b></div>"
                        f"<div class='pv-kv'><span>Con solución desarrollada</span><b>{con_sol} / {n_test}</b></div>",
                        unsafe_allow_html=True)
        try:
            import analisis_lib as _A
            _res = _A.get_resultados(ss.get("excel_dfs", {}))
            _ult = (_res.sort_values("Fecha").groupby("ID_Pregunta").tail(1).set_index("ID_Pregunta")["Pct_Acierto"]
                    if not _res.empty else pd.Series(dtype=str))
            _vals = [float(_ult[p.get("ID_Pregunta")]) for p in cache if p.get("ID_Pregunta") in _ult.index
                     and str(_ult[p.get("ID_Pregunta")]).strip()]
        except Exception:
            _vals = []
        with st.container(key="pvc_an").expander("Según exámenes anteriores", expanded=False):
            if _vals:
                media = sum(_vals) / len(_vals)
                reales = [_A.dificultad_real(v) for v in _vals]
                st.markdown("<div class='pv-ph'>Según exámenes anteriores</div>"
                            f"<div class='pv-kv'><span>Preguntas con datos</span><b>{len(_vals)} / {n_test}</b></div>"
                            f"<div class='pv-kv'><span>Acierto medio esperado</span><b>{media:.0f} %</b></div>"
                            f"<div class='pv-kv'><span>Nota esperada del test</span><b>≈ {media / 10:.1f} / 10</b></div>"
                            f"<div class='pv-kv'><span>Dificultad real F · M · D</span><b>{reales.count('Facil')} · "
                            f"{reales.count('Media')} · {reales.count('Dificil')}</b></div>"
                            "<div class='pv-n'>Con el acierto de cada pregunta en su último análisis guardado (sin penalización).</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown("<div class='pv-ph'>Según exámenes anteriores</div><div class='pv-n'>Ninguna de estas preguntas "
                            "tiene todavía un análisis guardado (página Análisis).</div>", unsafe_allow_html=True)
        n_fij = sum(1 for p in cache if p.get("ID_Pregunta") in fijas)
        with st.container(key="pvc_ori").expander("Origen", expanded=False):
            st.markdown("<div class='pv-ph'>Origen</div>"
                        f"<div class='pv-kv'><span>Fijas (elegidas a mano)</span><b>{n_fij}</b></div>"
                        f"<div class='pv-kv'><span>De la receta / al azar</span><b>{n_test - n_fij}</b></div>",
                        unsafe_allow_html=True)
        tipos = {}
        for av in avisos.values():
            for t, c in av:
                k = re.sub(r" \d+ mes(es)?| este mes| · .*$", "", t)
                k = "usada hace poco" if k.startswith("usada") else k
                tipos[k] = tipos.get(k, 0) + 1
        n_dev_sin = sum(1 for q in dev_qs if not (str(q.get("solucion_modelo", "")).strip()
                                                  or any(str(a.get("solucion", "")).strip() for a in q.get("subapartados") or [])))
        with st.container(key="pvc_av").expander("Avisos", expanded=True):
            st.markdown(f"<div class='pv-ph'>Avisos <small>{sum(tipos.values()) + n_dev_sin}</small></div>", unsafe_allow_html=True)
            if not tipos and not n_dev_sin:
                st.caption("Ninguno.")
            for t, n in sorted(tipos.items(), key=lambda kv: -kv[1]):
                clave = "usada" if t.startswith("usada") else t
                if st.button(f"{n} · {t}", key=f"pv_f_{t}", use_container_width=True, type="tertiary",
                             help="Ver solo esas preguntas"):
                    ss["pv_filtro"] = clave
                    st.rerun()
            if n_dev_sin:
                st.caption(f"{n_dev_sin} pregunta(s) de desarrollo sin solución modelo")
        st.caption("Para ver el PDF definitivo: pestaña **Exportar › Compilar PDF**.")



def _historial_bd():
    """Historial › exámenes guardados en la base de datos (borradores, exportados e importados), compartidos."""
    import analisis_lib as _A
    ss = st.session_state
    exs = E.examenes()
    st.markdown("<div class='sec-title'>Exámenes<span class='sec-meta'>guardados en la base de datos: los ve cualquier "
                "profesor que la use</span></div>", unsafe_allow_html=True)
    if exs.empty:
        st.info("Todavía no hay exámenes guardados. Los borradores se guardan solos mientras trabajas y los exámenes "
                "al exportarlos; los anteriores se importan en Análisis › Exámenes.")
        return
    exs = exs.assign(_est=[E.estado_de(r) for r in exs.to_dict("records")])
    with st.container(key="pill_hist_f"):
        filtro = st.radio("Mostrar", ["Todos", "Borradores", "Exportados", "Importados"], horizontal=True,
                          key="hist_f", label_visibility="collapsed")
    m = {"Borradores": "Borrador", "Exportados": "Exportado", "Importados": "Importado"}.get(filtro)
    if m:
        exs = exs[exs["_est"] == m]
    exs = exs.assign(_ord=exs["Actualizado"].where(exs["Actualizado"] != "", exs["Fecha"])).sort_values("_ord", ascending=False)
    k_est = {"Borrador": "w", "Exportado": "f", "Importado": "u"}
    with st.container(border=True, key="card_hist_bd"):
        if exs.empty:
            st.caption("No hay exámenes de este tipo.")
        for r in exs.to_dict("records"):
            c = _A._j(r.get("Contenido", ""), {})
            n_dev = len(c.get("dev") or [])
            meta = (f"{r['N_Preguntas'] or len(c.get('test') or [])} test"
                    + (f" + {n_dev} desarrollo" if n_dev else "")
                    + (f" · {r['N_Modelos']} modelo(s)" if r["_est"] != "Borrador" and r["N_Modelos"] else "")
                    + (f" · {sum((c.get('cambios') or {}).values())} cambios a mano" if r["_est"] == "Borrador" and (c.get("cambios") or {}) else "")
                    + (f" · analizado: media {r['Media']}" if r["Media"] else (" · sin analizar" if r["_est"] != "Borrador" else ""))
                    + (" · guardado automático" if r["_est"] == "Borrador" else ""))
            actual = r["ID_Examen"] in (ss.get("draft_id"), (ss.get("exam_lock") or {}).get("ID_Examen"))
            h = st.columns([3.2, 1.0, 1.1, 1.3, 0.9, 0.9], vertical_alignment="center")
            h[0].markdown(f"<div class='devq-t'>{r['Nombre'] or r['ID_Examen']}{' · abierto ahora' if actual else ''}</div>"
                          f"<div class='devq-s'>{meta}</div>", unsafe_allow_html=True)
            h[1].markdown(f"<span class='tag tag-{k_est[r['_est']]}'>{r['_est']}</span>", unsafe_allow_html=True)
            h[2].markdown(f"<span class='devq-s'>{E.fecha_es(r['Actualizado'] or r['Fecha'])[:16]}</span>", unsafe_allow_html=True)
            h[3].markdown(f"<span class='devq-s'>{(r['Usuario'] or '').split('@')[0]}</span>", unsafe_allow_html=True)
            if h[4].button("Abrir", key=f"hb_open_{r['ID_Examen']}", type="primary", use_container_width=True,
                           disabled=not (c.get("test") or r["Posiciones"])):
                notify(E.abrir(r))
                st.rerun()
            if r["_est"] == "Borrador":
                if h[5].button("Borrar", key=f"hb_del_{r['ID_Examen']}", use_container_width=True):
                    _A.borrar_examen(ss.excel_dfs, r["ID_Examen"])
                    if ss.get("draft_id") == r["ID_Examen"]:
                        ss["draft_id"] = None
                    guardar_hojas([_A.SHEET_EXAMENES])
                    notify("Borrador borrado.")
                    st.rerun()
            elif h[5].button("Análisis", key=f"hb_an_{r['ID_Examen']}", use_container_width=True):
                ss["_an_exam_next"] = r["ID_Examen"]
                st.switch_page("pages/5_Analisis.py")
    st.caption("«Abrir» carga el examen en Selección, Desarrollo y Generar. Los exportados e importados se abren "
               "bloqueados y con sus modelos exactos; los borradores, para seguir trabajando.")
    st.page_link("pages/6_Examenes.py", label="Todos los exámenes, con su ficha, importar exámenes anteriores, editar y borrar ›")

def _receta_por(recipe: dict) -> tuple:
    """(total, {bloque: n}, {facil, media, dificil: n}) de la receta."""
    tot, por_b, por_d = 0, {}, {"facil": 0, "media": 0, "dificil": 0}
    for blq, temas_cfg in (recipe or {}).items():
        for difs in (temas_cfg or {}).values():
            for dk, v in (difs or {}).items():
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    continue
                tot += v
                por_b[blq] = por_b.get(blq, 0) + v
                d = _dif_norm(dk)
                if d in por_d:
                    por_d[d] += v
    return tot, por_b, por_d


def _resumen_seleccion(sel_ids, cache):
    """Selección (Bitácora): «Tu examen» — cuántas, de dónde salen, dificultad prevista y acciones."""
    ss = st.session_state
    df = ss.df_preguntas
    n_fx = len(sel_ids)
    n_rec, _, d_rec = _receta_por(ss.get("auto_recipe", {}))
    n_ex = len(cache) if cache else n_fx + n_rec
    d_fx = {"facil": 0, "media": 0, "dificil": 0}
    for d in df[df["ID_Pregunta"].isin(sel_ids)]["dificultad"].map(_dif_norm):
        if d in d_fx:
            d_fx[d] += 1
    if cache:
        d_tot = {"facil": 0, "media": 0, "dificil": 0}
        for p in cache:
            d = _dif_norm(p.get("dificultad", ""))
            if d in d_tot:
                d_tot[d] += 1
    else:
        d_tot = {k: d_fx[k] + d_rec[k] for k in d_fx}
    tt = max(1, sum(d_tot.values()))
    n_dev = len(ss.get("dev_questions") or [])
    with st.container(border=True, key="card_sel_res"):
        c1, c2, c3, c4 = st.columns([1.25, 1.35, 1.6, 1.25], vertical_alignment="center")
        with c1:
            st.markdown("<div class='dev-hd'>Tu examen</div>", unsafe_allow_html=True)
            obj = st.number_input("Objetivo (nº de preguntas de test)", min_value=1, max_value=200,
                                  value=ss.get("tgt_pregs", 20), key="tgt_pregs")
            pct = min(100, int(n_ex / obj * 100)) if obj else 0
            st.markdown(f"<div class='selr-n'><b>{n_ex}</b> / {obj} preguntas{f' · {n_dev} de desarrollo' if n_dev else ''}</div>"
                        f"<div class='selr-bar'><div style='width:{pct}%;background:{'var(--ok)' if n_ex >= obj else 'var(--primary)'}'></div></div>",
                        unsafe_allow_html=True)
        c2.markdown("<div class='dev-hd'>De dónde salen</div>"
                    f"<div class='selr-l'><b>{n_fx}</b> fijas (elegidas a mano)<br><b>{n_rec}</b> de la receta"
                    + (f"<br><b>{E.n_cambios()}</b> cambios a mano en Generar" if E.n_cambios() else "")
                    + ("<br>generado en Generar" if cache else "<br><span class='devq-s'>aún sin generar</span>")
                    + (" · bloqueado" if E.bloqueado() else "") + "</div>", unsafe_allow_html=True)
        c3.markdown("<div class='dev-hd'>Dificultad prevista</div>"
                    f"<div class='selr-dif'><div style='width:{d_tot['facil'] / tt * 100:.0f}%;background:var(--ok)'></div>"
                    f"<div style='width:{d_tot['media'] / tt * 100:.0f}%;background:var(--primary)'></div>"
                    f"<div style='width:{d_tot['dificil'] / tt * 100:.0f}%;background:var(--err)'></div></div>"
                    f"<div class='devq-s'>Fácil {d_tot['facil']} · Media {d_tot['media']} · Difícil {d_tot['dificil']}</div>",
                    unsafe_allow_html=True)
        with c4:
            if st.button("Receta: editar" if ss.get("auto_recipe") else "Receta automática", type="primary",
                         use_container_width=True, key="btn_auto_dlg",
                         help="Elige cuántas preguntas al azar por bloque, tema y dificultad"):
                ss["_rec_pend"] = (ss.get("auto_recipe", {}), ss.get("auto_opts", {}))
                _dialog_receta(obj)
            n_fijas_cache = sum(1 for p in (cache or []) if p.get("ID_Pregunta") in set(sel_ids))
            if cache and st.button("Fijar todo el examen", key="btn_fijar_todo", use_container_width=True,
                                   disabled=n_fijas_cache == len(cache),
                                   help="Convierte todas las preguntas del examen en fijas y quita la receta: "
                                        "así puedes seguir trabajando a partir de este examen sin que la receta lo cambie."):
                E.registrar("Fijar todo el examen", None)
                set_sel_ids([p.get("ID_Pregunta") for p in cache])
                ss.auto_recipe = {}
                notify("Las preguntas del examen son ahora fijas (la receta se ha quitado; puedes volver a ponerla).")
                st.rerun()
            if not cache:
                st.caption("Pulsa «Generar» en Generar para ver el examen.")


def _cobertura_seleccion(sel_ids, df):
    """Selección (Bitácora): preguntas por bloque — fijas + receta — y bloques sin ninguna."""
    _, por_b, _ = _receta_por(st.session_state.get("auto_recipe", {}))
    fx = df[df["ID_Pregunta"].isin(sel_ids)]["bloque"].value_counts().to_dict()
    blqs = sorted(set(st.session_state.bloques or []) | set(fx) | {b for b in por_b if b != "__GEN__"}, key=orden_bloque)
    mx = max([fx.get(b, 0) + por_b.get(b, 0) for b in blqs] + [1])
    filas = ""
    for b in blqs:
        f_, r_ = fx.get(b, 0), por_b.get(b, 0)
        vacio = f_ + r_ == 0
        filas += (f"<div class='selc-r{' v' if vacio else ''}'><span title='{nombre_bloque(b)}'>{nombre_bloque(b)}</span>"
                  f"<div class='selc-bar'><div class='f' style='width:{f_ / mx * 100:.0f}%'></div>"
                  f"<div class='r' style='width:{r_ / mx * 100:.0f}%'></div></div><b>{f_ + r_}</b></div>")
    if por_b.get("__GEN__"):
        filas += f"<div class='selc-r'><span>Objetivos generales</span><div></div><b>{por_b['__GEN__']}</b></div>"
    st.markdown("<div class='sec-title' style='margin:0 0 6px'>Cobertura del examen<span class='sec-meta'>fijas + receta, "
                "por bloque</span></div>" + filas
                + "<div class='devq-s' style='margin-top:6px'>■ fijas · ▭ receta · en rojo, bloques sin ninguna pregunta</div>",
                unsafe_allow_html=True)


tab_sel, tab_dev, tab_prev, tab_exp, tab_hist = st.tabs(
    ["🔢 Selección", "✍️ Desarrollo", "👁️ Generar", "💾 Ver y exportar", "📋 Historial"]
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 · SELECCIÓN
# ─────────────────────────────────────────────────────────────────────────────
with tab_sel:
    sel_ids_actual = get_sel_ids()
    n_sel = len(sel_ids_actual)
    _cache_sel = st.session_state.get("cache_examen") or []
    if get_estilo() == "bitacora":
        _resumen_seleccion(sel_ids_actual, _cache_sel)
        n_obj = st.session_state.get("tgt_pregs", 20)
    else:
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
                if get_estilo() == "bitacora":
                    st.session_state["_rec_pend"] = (st.session_state.get("auto_recipe", {}),
                                                     st.session_state.get("auto_opts", {}))
                    _dialog_receta(n_obj)
                else:
                    _dialog_autofill(n_obj)

    # ── Resumen receta activa ─────────────────────────────────────────────────
    recipe = st.session_state.get("auto_recipe", {})
    if recipe:
        total_r, parts = 0, []
        for blq, temas_cfg in recipe.items():
            blq_t = sum(v for difs in temas_cfg.values() for v in difs.values())
            if blq_t > 0:
                parts.append(f"{'Objetivos generales' if blq == '__GEN__' else blq}: {blq_t}")
                total_r += blq_t
        summary_str = " · ".join(parts[:4]) + (" ···" if len(parts) > 4 else "")
        if get_estilo() == "bitacora" and total_r:
            _o = st.session_state.get("auto_opts", {}) or {}
            _ops = [x for x in (f"evita usadas en {_o['evitar_meses']} meses" if _o.get("evitar_meses") else "",
                                f"sin {len(_o['excl_examenes'])} examen(es) anterior(es)" if _o.get("excl_examenes") else "",
                                "excluye " + ", ".join(_o["excl_etiquetas"]) if _o.get("excl_etiquetas") else "",
                                {"azar": "al azar", "discrimina": "primero las que mejor discriminan"}.get(
                                    _o.get("criterio"), "primero las menos usadas"),
                                "solo con solución" if _o.get("solo_sol") else "",
                                "sin anuladas ni «a revisar»" if _o.get("excl_revisar") else "",
                                f"máx. {_o['max_tema']} por tema" if _o.get("max_tema") else "",
                                f"máx. {_o['max_obj']} por objetivo" if _o.get("max_obj") else "") if x]
            _chips = "".join(f"<span class='rec-chip'>{p}</span>" for p in parts)
            rc1, rc0, rc2 = st.columns([9, 1.1, 1.3], vertical_alignment="center")
            rc1.markdown(f"<div class='rec-act'><b>Receta</b> <span class='rec-n'>{total_r} automáticas</span>"
                         f"{_chips}<small>{' · '.join(_ops)} · se eligen al pulsar «Generar» en Generar</small></div>",
                         unsafe_allow_html=True)
            if rc0.button("Editar", key="btn_edit_recipe_sel", use_container_width=True):
                st.session_state["_rec_pend"] = (st.session_state.get("auto_recipe", {}),
                                                 st.session_state.get("auto_opts", {}))
                _dialog_receta(st.session_state.get("tgt_pregs", 20))
            if rc2.button("Quitar receta", key="btn_clear_recipe_sel", use_container_width=True):
                st.session_state["auto_recipe"] = {}
                st.rerun()
            recipe = {}   # ya mostrada
        rc1, rc2 = (st.columns([9, 1]) if recipe else (st.empty(), st.empty()))
        if recipe: rc1.markdown(
            f"<div style='background:var(--primary-soft, #e8f4fd);border:1px solid var(--border2, #aed6f1);border-radius:6px;"
            f"padding:5px 12px;font-size:0.83em;color:var(--primary, #1a5276)'>"
            f"🤖 <b>Receta activa</b> — {total_r} preg. auto  ·  {summary_str}</div>",
            unsafe_allow_html=True
        )
        if recipe and rc2.button("✖", key="btn_clear_recipe_sel", help="Eliminar receta automática"):
            st.session_state["auto_recipe"] = {}
            st.rerun()

    # ── Filtros (colapsables para maximizar espacio) ──────────────────────────
    _bit_f = get_estilo() == "bitacora"
    if _bit_f:
        # Los mismos filtros que Gestor › Gestionar (sobre las preguntas aún no fijadas)
        df_filt = filtros_bitacora("sel_", df_total[~df_total["ID_Pregunta"].isin(sel_ids_actual)], bloques)
    elif st.session_state.get("sel_f_uso") in ("Usada >6m", "Usada >12m"):   # valores del estilo Bitácora
        st.session_state["sel_f_uso"] = st.session_state["sel_f_uso"].replace("m", " meses")
    if not _bit_f:
        with st.expander("🔍 Filtros", expanded=False):
            fc1, fc2, fc3, fc4, fc5 = st.columns(5)
            f_bloque = fc1.selectbox("Bloque", ["Todos"] + bloques, key="sel_f_bloque")
            temas_disp = (temas_de_bloque(f_bloque) if f_bloque != "Todos"
                          else sorted(df_total["Tema"].unique().tolist(), key=_nsort))
            f_tema   = fc2.selectbox("Tema", ["Todos"] + [str(t) for t in temas_disp],
                                      key="sel_f_tema",
                                      format_func=lambda t: "Todos" if t == "Todos" else nombre_tema(t))
            if not _bit_f:
                f_dif    = fc3.selectbox("Dificultad", ["Todas", "Facil", "Media", "Dificil"],
                                          key="sel_f_dif")
                f_uso    = fc4.selectbox(
                    "Uso", ["Todos", "Nunca usada", "Usada", "Usada >6 meses", "Usada >12 meses"],
                    key="sel_f_uso"
                )
            f_search = fc5.text_input("Buscar", placeholder="Texto...", key="sel_search")
            _coms_disp = sorted({c for c in df_total.get("comentario", pd.Series(dtype=str)).dropna() if c})
            _objs_disp = sorted({str(o) for o in df_total.get("objetivo", pd.Series(dtype=str)).dropna() if str(o).strip()})
            _has_extra = bool(_coms_disp) or bool(_objs_disp)
            if _has_extra:
                fc6, fc7, _ = st.columns([2, 2, 1])
                f_com = fc6.selectbox("Etiqueta", ["Todas"] + _coms_disp, key="sel_f_com") if _coms_disp else "Todas"
                f_obj = fc7.selectbox("Objetivo", ["Todos"] + _objs_disp, key="sel_f_obj",
                                      format_func=lambda x: "Todos" if x == "Todos" else nombre_objetivo(x)) if _objs_disp else "Todos"
            else:
                f_com = "Todas"
                f_obj = "Todos"

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
        if f_com != "Todas" and "comentario" in df_filt.columns:
            df_filt = df_filt[df_filt["comentario"] == f_com]
        if f_obj != "Todos" and "objetivo" in df_filt.columns:
            df_filt = df_filt[df_filt["objetivo"].astype(str) == f_obj]

    # ── Vista previa de una pregunta (panel central o ventana) ─────────────────
    def _render_sel_preview(preview_pid, row_d_prev, in_dialog=False):
        """Tarjeta + notas + botones de la pregunta. En ventana, los cambios que
        afectan a la página (añadir/quitar/editar) cierran la ventana con un rerun completo."""
        _rerun_local = (lambda: st.rerun(scope="fragment")) if in_dialog else st.rerun
        card_html_prev = render_question_card_html(row_d_prev, show_sol=True, include_notas=False)
        st.markdown(card_html_prev, unsafe_allow_html=True)

        # Notas debajo de la tarjeta
        notas_txt_prev  = str(row_d_prev.get("notas", "") or "").strip()
        notas_html_prev = ""
        if notas_txt_prev:
            notas_html_prev = (
                "<div style='background:var(--note-bg, #fefce8);border-left:3px solid var(--ui-warn, #f59e0b);"
                "border-radius:0 8px 8px 0;padding:10px 14px;margin-top:4px;"
                "font-size:0.875em;color:var(--note-text, #78350f);line-height:1.55'>"
                "<b style='color:var(--note-text, #92400e);display:block;margin-bottom:4px'>📝 Notas</b>"
                f"{notas_txt_prev}</div>"
            )
            st.markdown(notas_html_prev, unsafe_allow_html=True)

        # Badge solución
        sol_txt_badge = str(row_d_prev.get("solucion", "") or "").strip()
        if sol_txt_badge:
            st.markdown(
                "<div style='margin-top:4px;display:flex;align-items:center;gap:6px'>"
                "<span style='background:var(--primary-soft, #dbeafe);color:var(--primary, #1e40af);border:1px solid var(--border2, #93c5fd);"
                "border-radius:12px;padding:2px 10px;font-size:0.78em;font-weight:600;"
                "letter-spacing:0.02em'>📖 Solución disponible</span></div>",
                unsafe_allow_html=True,
            )

        # Botones añadir / quitar + Solución + Editar
        is_sel = preview_pid in get_sel_ids()
        pa1, pa2, pa3, pa4 = st.columns(4)
        if is_sel:
            if pa1.button("➖ Quitar", key="btn_prev_rem",
                           use_container_width=True):
                cur = get_sel_ids()
                if preview_pid in cur:
                    cur.remove(preview_pid)
                set_sel_ids(cur)
                if in_dialog:
                    st.session_state["_sel_dlg_nonce"] = st.session_state.get("_sel_dlg_nonce", 0) + 1
                st.rerun()
        else:
            if pa1.button("➕ Añadir", key="btn_prev_add",
                           use_container_width=True, type="primary"):
                cur = get_sel_ids()
                if preview_pid not in cur:
                    cur.append(preview_pid)
                set_sel_ids(cur)
                if in_dialog:
                    st.session_state["_sel_dlg_nonce"] = st.session_state.get("_sel_dlg_nonce", 0) + 1
                st.rerun()

        # Botón Solución
        sol_txt_prev = str(row_d_prev.get("solucion", "") or "").strip()
        if pa2.button("📖 Sol.", key="btn_prev_sol",
                       use_container_width=True, disabled=not sol_txt_prev):
            st.session_state["_gen_sol_pid"] = preview_pid
            st.session_state["_gen_sol_row"] = row_d_prev

        # Botón MathJax
        _mjax_key_sel = f"mjax_sel_{preview_pid}"
        if pa3.button("∑ LaTeX", key=f"mjax_btn_sel_{preview_pid}",
                       use_container_width=True):
            st.session_state[_mjax_key_sel] = True

        # Botón Editar (en ventana no se puede abrir otra ventana: se abre al recargar)
        if pa4.button("✏️ Editar", key=f"btn_edit_prev_{preview_pid}",
                       use_container_width=True):
            if in_dialog:
                st.session_state["_sel_edit_pid"] = preview_pid
                st.rerun()
            _dialog_editar_pregunta(preview_pid, row_d_prev)
        if st.session_state.get(_mjax_key_sel, False):
            mj1, mj2 = st.columns([1, 4])
            if mj1.button("✖ Cerrar LaTeX", key=f"mjax_close_sel_{preview_pid}",
                           use_container_width=True):
                st.session_state[_mjax_key_sel] = False
                _rerun_local()
            stcomponents.html(mathjax_html(card_html_prev + notas_html_prev), height=480, scrolling=True)

        # Mostrar solución inline si se ha pulsado el botón
        if (st.session_state.get("_gen_sol_pid") == preview_pid
                and st.session_state.get("_gen_sol_row")):
            sol_txt = str(st.session_state["_gen_sol_row"].get("solucion", "") or "").strip()
            if sol_txt:
                sol_html = (
                    "<div style='font-family:-apple-system,sans-serif;font-size:14px;"
                    "color:var(--text, #2c3e50);padding:12px;background:var(--primary-soft, #f0f9ff);"
                    "border-left:3px solid var(--primary, #3498db);border-radius:0 8px 8px 0;margin-top:6px'>"
                    "<b style='color:var(--primary, #1a5276);display:block;margin-bottom:6px'>📖 Solución</b>"
                    f"{sol_txt}</div>"
                )
                st.markdown("---")
                stcomponents.html(mathjax_html(sol_html), height=250, scrolling=True)
                if st.button("✖ Cerrar solución", key="btn_close_sol_gen"):
                    st.session_state.pop("_gen_sol_pid", None)
                    st.session_state.pop("_gen_sol_row", None)
                    _rerun_local()

    @st.dialog("👁 Vista previa de la pregunta", width="large")
    def _dialog_sel_preview(preview_pid):
        row_insp = df_total[df_total["ID_Pregunta"] == preview_pid]
        if row_insp.empty:
            st.info("La pregunta ya no está en la base de datos.")
            return
        _render_sel_preview(preview_pid, dict(row_insp.iloc[0]), in_dialog=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYOUT: disponibles | preview | fijas   (o disponibles | fijas + ventana)
    # ═══════════════════════════════════════════════════════════════════════════
    _prev_ventana = get_preview_mode() == "ventana"
    _bit_sel      = get_estilo() == "bitacora"   # Bitácora: tablas a medida
    _dlg_nonce    = st.session_state.get("_sel_dlg_nonce", 0)
    _open_preview = None   # pregunta a abrir en ventana en esta ejecución
    col_side = None
    if _prev_ventana and _bit_sel:
        col_list, col_side = st.columns([1.65, 1], gap="medium")
        col_prev = None
        col_sel = col_side.container(border=True, key="card_sel_fijas")
    elif _prev_ventana:
        col_list, col_sel = st.columns([3, 2])
        col_prev = None
    elif _bit_sel:
        col_list, col_side = st.columns([1.65, 1], gap="medium")
        col_prev = col_side.container(border=True, key="card_sel_prev")
        col_sel = col_side.container(border=True, key="card_sel_fijas")
    else:
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

        if _bit_sel:
            # Tabla a medida: agrupada por bloque y tema, «+» añade como fija, la fila abre la pregunta
            _recs = df_filt.to_dict("records")
            _recs.sort(key=lambda r: (orden_bloque(str(r.get("bloque", ""))), _nsort(str(r.get("Tema", ""))),
                                      str(r.get("ID_Pregunta", ""))))
            _gmodo = selector_agrupar("sel_grp")
            _grp_of = lambda r: grupo_pregunta(r, _gmodo)
            _cnt = {}
            for r in _recs:
                _cnt[_grp_of(r)] = _cnt.get(_grp_of(r), 0) + 1
            _act = qtable([qtable_row(r, grp=_grp_of(r), grp_meta=n_preg(_cnt[_grp_of(r)])) for r in _recs],
                          "seleccion", key="qt_avail", height=560, collapse_default=True, toolbar=True,
                          foot="Pulsa una fila para ver la pregunta · + la añade como fija",
                          empty="No hay preguntas disponibles con estos filtros")
            if _act and _act.get("action") == "add":
                cur = get_sel_ids()
                if _act["id"] not in cur:
                    cur.append(_act["id"])
                set_sel_ids(cur)
                st.rerun()
            elif _act and _act.get("action") == "open":
                st.session_state["sel_preview_pid"] = _act["id"]
                if _prev_ventana:
                    _open_preview = _act["id"]
        else:
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
                # en modo ventana, tras añadir/quitar se renueva la tabla para no
                # abrir sola la pregunta que ocupa ahora la fila seleccionada
                key="df_avail" if not _dlg_nonce else f"df_avail_{_dlg_nonce}",
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
                    _open_preview = new_avail_pid
            elif _prev_ventana:
                # sin fila seleccionada: volver a pulsar la misma pregunta la reabre
                st.session_state["_last_avail_pid"] = None
            if _prev_ventana:
                st.caption("Pulsa una fila para ver la pregunta completa.")

    # ── Columna central: preview (solo en modo panel) ─────────────────────────
    if col_prev is not None:
        with col_prev:
            preview_pid = st.session_state.get("sel_preview_pid")
            if preview_pid:
                row_insp = df_total[df_total["ID_Pregunta"] == preview_pid]
                if not row_insp.empty:
                    _render_sel_preview(preview_pid, dict(row_insp.iloc[0]))
                else:
                    st.info("Selecciona una pregunta de la lista para previsualizarla.")
            else:
                st.markdown(
                    "<div style='background:var(--card2, #f8f9fa);border:2px dashed var(--ui-border, #dee2e6);"
                    "border-radius:12px;padding:60px 20px;text-align:center;"
                    "color:var(--faint, #bbb);margin-top:30px'>"
                    "<div style='font-size:2.5em;margin-bottom:12px'>👈</div>"
                    "<div style='font-weight:600;font-size:1em;color:var(--faint, #aaa)'>"
                    "Haz clic en una pregunta</div>"
                    "<div style='font-size:0.85em;margin-top:6px;color:var(--faint, #ccc)'>"
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
            f"<div style='background:var(--track, #e9ecef);border-radius:4px;height:6px;margin-bottom:8px'>"
            f"<div style='width:{pct_obj}%;height:6px;border-radius:4px;"
            f"background:{bar_color}'></div></div>",
            unsafe_allow_html=True,
        )

        if sel_ids_actual:
            df_sel = df_total[df_total["ID_Pregunta"].isin(sel_ids_actual)].copy()
            id_order = {pid: i for i, pid in enumerate(sel_ids_actual)}
            df_sel["_ord"] = df_sel["ID_Pregunta"].map(id_order)
            df_sel = df_sel.sort_values("_ord").drop(columns=["_ord"]).reset_index(drop=True)

            if _bit_sel:
                # Tabla a medida: ↑ ↓ × en cada fila; la fila abre la pregunta
                _actf = qtable([qtable_row(r) for r in df_sel.to_dict("records")], "fijas", key="qt_fijas",
                               height=min(440, 40 + 52 * len(df_sel)))
                if _actf:
                    _pid, _a = _actf.get("id"), _actf.get("action")
                    cur = get_sel_ids()
                    idx = cur.index(_pid) if _pid in cur else -1
                    if _a == "open":
                        st.session_state["sel_preview_pid"] = _pid
                        if _prev_ventana:
                            _open_preview = _pid
                    elif idx >= 0:
                        if _a == "up" and idx > 0:
                            cur[idx], cur[idx - 1] = cur[idx - 1], cur[idx]
                        elif _a == "down" and idx < len(cur) - 1:
                            cur[idx], cur[idx + 1] = cur[idx + 1], cur[idx]
                        elif _a == "remove":
                            cur.remove(_pid)
                        set_sel_ids(cur)
                        st.rerun()
            else:
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
                # Clic en fijas → actualizar preview (sólo si cambió). En modo ventana
                # no se abre sola (se selecciona para reordenar): botón «Ver».
                if right_sel_pid:
                    if right_sel_pid != st.session_state.get("_last_sel_pid"):
                        st.session_state["_last_sel_pid"] = right_sel_pid
                        st.session_state["sel_preview_pid"] = right_sel_pid

                # Botones de reordenar / quitar
                if _prev_ventana:
                    sb1, sb2, sb3, sb4 = st.columns(4)
                    if sb4.button("👁", key="btn_view_sel", disabled=(right_sel_pid is None),
                                  use_container_width=True, help="Ver la pregunta"):
                        _open_preview = right_sel_pid
                else:
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
                "<div style='background:var(--card2, #f8f9fa);border:2px dashed var(--ui-border, #dee2e6);"
                "border-radius:10px;padding:30px 12px;text-align:center;"
                "color:var(--faint, #aaa);font-size:0.85em;margin-top:4px'>"
                "📭 Sin preguntas fijas<br>"
                "<span style='font-size:0.85em'>"
                "Añade desde el preview o usa 🤖</span>"
                "</div>",
                unsafe_allow_html=True,
            )

    if col_side is not None:
        with col_side.container(border=True, key="card_sel_cob"):
            _cobertura_seleccion(sel_ids_actual, df_total)

    # ── Ventanas (solo una por ejecución) ─────────────────────────────────────
    if _prev_ventana:
        _edit_pid = st.session_state.pop("_sel_edit_pid", None)
        if _edit_pid:
            _row_edit = df_total[df_total["ID_Pregunta"] == _edit_pid]
            if not _row_edit.empty:
                _dialog_editar_pregunta(_edit_pid, dict(_row_edit.iloc[0]))
        elif _open_preview:
            _dialog_sel_preview(_open_preview)

    # ── Panel de estadísticas de selección (tiempo real) ─────────────────────
    _stats_box = (st.expander("Estadísticas de las fijas") if get_estilo() == "bitacora" else st.container())
    _stats_box.__enter__()
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
    _stats_box.__exit__(None, None, None)


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


def _dev_qs_to_json(dev_qs: list) -> bytes:
    import json as _j, base64 as _b
    out = []
    for q in dev_qs:
        q2 = {k: v for k, v in q.items() if k != "imagen_bytes"}
        if q.get("imagen_bytes"):
            q2["imagen_b64"] = _b.b64encode(q["imagen_bytes"]).decode()
        q2["subapartados"] = []
        for apt in (q.get("subapartados") or []):
            apt2 = {k: v for k, v in apt.items() if k != "imagen_bytes"}
            if apt.get("imagen_bytes"):
                apt2["imagen_b64"] = _b.b64encode(apt["imagen_bytes"]).decode()
            q2["subapartados"].append(apt2)
        out.append(q2)
    return _j.dumps(out, indent=2, ensure_ascii=False).encode("utf-8")


def _dev_qs_from_json(raw: bytes) -> list:
    import json as _j, base64 as _b
    qs = _j.loads(raw.decode("utf-8"))
    for q in qs:
        if "imagen_b64" in q:
            q["imagen_bytes"] = _b.b64decode(q.pop("imagen_b64"))
        else:
            q["imagen_bytes"] = None
        q.setdefault("txt", ""); q.setdefault("pts", 1.0)
        q.setdefault("espacio", "Automático"); q.setdefault("modo", "markdown")
        q.setdefault("criterios", []); q.setdefault("solucion_modelo", "")
        q.setdefault("imagen_name", ""); q.setdefault("imagen_pos", "debajo")
        q.setdefault("datos_ids", "")
        apts = q.get("subapartados") or []
        for apt in apts:
            if "imagen_b64" in apt:
                apt["imagen_bytes"] = _b.b64decode(apt.pop("imagen_b64"))
            else:
                apt["imagen_bytes"] = None
            apt.setdefault("imagen_name", "")
            apt.setdefault("imagen_pos", "debajo")
        q["subapartados"] = apts
        q.setdefault("numeracion_apt", "abc")
    return qs


with tab_dev:
  if get_estilo() == "bitacora":
    _desarrollo_bitacora()
  else:
    _bit_dev = get_estilo() == "bitacora"
    page_header("✍️", "Preguntas de Desarrollo",
                "Se incluirán como PARTE I del examen · Markdown y LaTeX soportados",
                color="#7d3c98")

    dev_qs: list = st.session_state.dev_questions

    if st.button("➕ Añadir pregunta de desarrollo", key="btn_add_dev", type="primary"):
        dev_qs.append({"txt": "", "pts": 1.0, "espacio": "Automático",
                       "modo": "markdown",
                       "criterios": [], "solucion_modelo": "",
                       "imagen_bytes": None, "imagen_name": "", "imagen_pos": "debajo",
                       "datos_ids": "",
                       "subapartados": [], "numeracion_apt": "abc"})
        st.session_state.dev_questions = dev_qs
        st.rerun()

    # ── Export / Import JSON ──────────────────────────────────────────────────
    _io1, _io2 = st.columns(2)
    if dev_qs:
        _io1.download_button(
            "⬇️ Exportar preguntas (JSON)",
            data=_dev_qs_to_json(dev_qs),
            file_name="dev_questions.json",
            mime="application/json",
            use_container_width=True,
            key="dl_dev_qs",
            help="Descarga las preguntas de desarrollo como JSON para guardar, recuperar o compartir con compañeros",
        )
    _imp_up = _io2.file_uploader(
        "⬆️ Importar preguntas (JSON)", type=["json"], key="dev_qs_import",
        help="Carga un JSON exportado previamente — las preguntas se añaden a las existentes",
    )
    if _imp_up and st.session_state.get("_dev_json_upload_name") != _imp_up.name:
        try:
            _imported = _dev_qs_from_json(_imp_up.getvalue())
            dev_qs.extend(_imported)
            st.session_state.dev_questions = dev_qs
            st.session_state["_dev_json_upload_name"] = _imp_up.name
            notify(f"✅ {len(_imported)} pregunta(s) importada(s)")
            st.rerun()
        except Exception as _ie:
            st.error(f"Error al importar: {_ie}")

    if not dev_qs:
        st.info("No hay preguntas de desarrollo. Haz clic en **➕ Añadir pregunta** para empezar.")

    # ── Snippets (definidos una sola vez fuera del bucle) ────────────────────
    _SNIPS_TEXT_MD = [
        ("B",       "**TEXTO**",                           "**Negrita**: rodea el texto con **texto**"),
        ("I",       "*TEXTO*",                             "*Cursiva*: rodea el texto con *texto*"),
        ("• Lista", "\n- Elemento 1\n- Elemento 2\n",      "Lista con viñetas (cada línea empieza con -)"),
        ("1. Num",  "\n1. Primer punto\n2. Segundo\n",     "Lista numerada"),
        ("— Sep",   "\n---\n",                             "Separador horizontal"),
    ]
    _SNIPS_MATH_MD = [
        ("$ …",     "$valor$",                             "Fórmula inline: $E=mc^2$  ← entre signos $"),
        ("$$ …",    "$$\n\\frac{a}{b}\n$$",               "Fórmula en bloque centrada (línea propia)"),
        ("½",       "$\\frac{num}{den}$",                  "Fracción: $\\frac{numerador}{denominador}$"),
        ("√",       "$\\sqrt{x}$",                         "Raíz cuadrada: $\\sqrt{x}$"),
        ("xⁿ",      "$x^{n}$",                             "Potencia / superíndice: $x^{2}$"),
        ("xₙ",      "$x_{n}$",                             "Subíndice: $x_{n}$"),
        ("∑",       "$\\sum_{i=1}^{n} x_i$",              "Sumatorio"),
        ("∫",       "$\\int_a^b f(x)\\,dx$",              "Integral definida"),
        ("αβγ…",    "$\\alpha$",                           "Letras griegas: α→\\alpha  β→\\beta  γ→\\gamma  μ→\\mu  λ→\\lambda  ω→\\omega…"),
    ]
    _SNIPS_PHYS_MD = [
        ("Dosis",      "$D = \\frac{E}{m}$",                         "Dosis absorbida D [Gy = J/kg]"),
        ("Actividad",  "$A = A_0\\,e^{-\\lambda t}$",                "Actividad radiactiva A [Bq]"),
        ("T½",         "$T_{1/2} = \\frac{\\ln 2}{\\lambda}$",       "Período de semidesintegración"),
        ("Atenuación", "$I = I_0\\,e^{-\\mu x}$",                   "Ley de atenuación exponencial"),
        ("μ/ρ",        "$\\frac{\\mu}{\\rho}$",                      "Coeficiente de atenuación másico"),
        ("HVL",        "$HVL = \\frac{\\ln 2}{\\mu}$",              "Capa hemirreductora"),
        ("E=mc²",      "$E = mc^2$",                                 "Equivalencia masa-energía"),
        ("SNR",        "$SNR = \\frac{\\bar{S}}{\\sigma_S}$",        "Relación señal-ruido"),
    ]
    _SNIPS_TEXT_LATEX = [
        ("B",       "\\textbf{TEXTO}",                              "Negrita LaTeX: \\textbf{texto}"),
        ("I",       "\\textit{TEXTO}",                              "Cursiva LaTeX: \\textit{texto}"),
        ("• Lista", "\\begin{itemize}\n  \\item \n\\end{itemize}",  "Lista con viñetas"),
        ("1. Num",  "\\begin{enumerate}\n  \\item \n\\end{enumerate}", "Lista numerada"),
        ("— Sep",   "\\medskip",                                    "Espacio vertical"),
    ]
    _SNIPS_MATH_LATEX = [
        ("$ …",     "$valor$",                    "Fórmula inline"),
        ("\\[…\\]", "\\[\n\\frac{a}{b}\n\\]",    "Fórmula en bloque centrada"),
        ("½",       "\\frac{num}{den}",           "Fracción"),
        ("√",       "\\sqrt{x}",                 "Raíz cuadrada"),
        ("xⁿ",      "^{n}",                      "Superíndice"),
        ("xₙ",      "_{n}",                      "Subíndice"),
        ("∑",       "\\sum_{i=1}^{n}",           "Sumatorio"),
        ("∫",       "\\int_a^b",                 "Integral"),
        ("αβγ…",    "\\alpha",                   "Letras griegas: \\alpha \\beta \\gamma \\mu \\lambda…"),
    ]
    _SNIPS_PHYS_LATEX = [
        ("Dosis",      "$D = \\frac{E}{m}$",                        "Dosis absorbida [Gy]"),
        ("Actividad",  "$A = A_0\\,e^{-\\lambda t}$",               "Actividad radiactiva [Bq]"),
        ("T½",         "$T_{1/2} = \\frac{\\ln 2}{\\lambda}$",      "Período de semidesintegración"),
        ("Atenuación", "$I = I_0\\,e^{-\\mu x}$",                  "Ley de atenuación"),
        ("μ/ρ",        "$\\frac{\\mu}{\\rho}$",                     "Coef. atenuación másico"),
        ("HVL",        "$HVL = \\frac{\\ln 2}{\\mu}$",             "Capa hemirreductora"),
        ("E=mc²",      "$E = mc^2$",                                "Equivalencia masa-energía"),
    ]

    _IMG_POS_OPTS = {
        "debajo":   "Debajo del texto",
        "lado":     "Derecha (minipage flotante)",
        "centrada": "Centrada en bloque",
    }
    _SNIPS_APT = [
        ("$ …",  "$valor$",                "Fórmula inline"),
        ("$$ …", "$$\n\\frac{a}{b}\n$$",  "Bloque centrado"),
        ("½",    "$\\frac{n}{d}$",         "Fracción"),
        ("√",    "$\\sqrt{x}$",            "Raíz"),
        ("xⁿ",  "$x^{n}$",               "Potencia"),
        ("xₙ",  "$x_{n}$",                "Subíndice"),
        ("∑",   "$\\sum_{i=1}^{n}$",      "Sumatorio"),
        ("∫",   "$\\int_a^b$",            "Integral"),
        ("αβ…", "$\\alpha$",              "Griegas"),
    ]
    _ESP_APT_OPTS = ["3cm","4cm","5cm","6cm","7cm","8cm","10cm","12cm","15cm","18cm"]
    _NUM_LABELS   = {"abc": "a), b), c)…", "roman": "i), ii), iii)…", "num": "1), 2), 3)…"}

    to_delete = []
    for i, q in enumerate(dev_qs):
        # ── Acordeón ─────────────────────────────────────────────────────────
        # La lista real de la pregunta (no una copia): así añadir/eliminar apartados
        # sobrevive al st.rerun() que hacen esos botones
        q["subapartados"] = list(q.get("subapartados") or [])
        subapts   = q["subapartados"]
        _pts_disp = (sum(float(a.get("puntos") or 0) for a in subapts)
                     if subapts else float(q.get("pts", 1.0)))
        _prev_txt    = q.get("txt", "")
        _acc_preview = _prev_txt[:55].replace("\n", " ").strip() if _prev_txt.strip() else "— vacía"
        _n_apts_lbl  = f"  ·  {len(subapts)} apt." if subapts else ""
        _acc_label   = (f"**Pregunta {i+1}**  ·  {_pts_disp:g} pts{_n_apts_lbl}"
                        f"  —  {_acc_preview}{'…' if len(_prev_txt) > 55 else ''}")
        _auto_expand = (len(dev_qs) == 1) or not _prev_txt.strip()

        with st.expander(_acc_label, expanded=_auto_expand):
            # ── Cabecera compacta: modo + eliminar ────────────────────────────
            _hc1, _hc2 = st.columns([4, 1.2] if _bit_dev else [5, 1], vertical_alignment="bottom" if _bit_dev else "top")
            _modo_actual = q.get("modo", "markdown")
            with _hc1.container(key=f"seg_devmode_{i}"):   # botones unidos en Bitácora
                _modo_sel = st.radio(
                    "Modo de escritura",
                    ["✍ Markdown (recomendado)", "⚙ LaTeX puro"],
                    horizontal=True,
                    index=0 if _modo_actual != "latex" else 1,
                    key=f"dev_mode_{i}",
                    help="**Markdown**: texto normal + fórmulas con $…$. | **LaTeX puro**: usuarios avanzados.",
                )
            q["modo"] = "latex" if "LaTeX" in _modo_sel else "markdown"
            _is_md = q["modo"] == "markdown"
            _snips_text = _SNIPS_TEXT_MD   if _is_md else _SNIPS_TEXT_LATEX
            _snips_math = _SNIPS_MATH_MD   if _is_md else _SNIPS_MATH_LATEX
            _snips_phys = _SNIPS_PHYS_MD   if _is_md else _SNIPS_PHYS_LATEX

            if _hc2.button("🗑️ Eliminar pregunta" if _bit_dev else "🗑️ Eliminar", key=f"dev_del_{i}",
                           use_container_width=True):
                to_delete.append(i)

            # ── 4 pestañas ────────────────────────────────────────────────────
            if _bit_dev:
                _tab_enun, _tab_apts, _tab_sol, _tab_rub, _tab_prev_q = st.tabs(
                    ["📝 Enunciado", "📑 Apartados", "📖 Solución", "⚙️ Rúbrica y datos", "👁 Vista previa (LaTeX)"]
                )
            else:
                _tab_enun, _tab_apts, _tab_rub, _tab_prev_q = st.tabs(
                    ["📝 Enunciado", "📑 Apartados", "⚙️ Rúbrica & Datos", "👁 Vista previa"]
                )
                _tab_sol = _tab_enun   # Clásico: la solución sigue al final de Enunciado

            # ══════════════ Tab 1: Enunciado ══════════════════════════════════
            with _tab_enun:
                # Barra texto
                st.markdown(
                    "<div style='font-size:.72em;color:var(--ui-used, #7d3c98);font-weight:700;"
                    "letter-spacing:.06em;margin:6px 0 3px'>✏️ TEXTO</div>",
                    unsafe_allow_html=True,
                )
                _tb1 = st.columns(len(_snips_text))
                for _j, (_col, (_lbl, _snip, _tip)) in enumerate(zip(_tb1, _snips_text)):
                    if _col.button(_lbl, key=f"sT_{i}_{_j}", help=_tip, use_container_width=True):
                        _cur = st.session_state.get(f"dev_txt_{i}", q.get("txt", ""))
                        st.session_state[f"dev_txt_{i}"] = _cur + _snip
                        st.rerun()
                _tc_math, _tc_phys = (st.container(), st.container()) if _bit_dev else st.columns([9, 8])
                with _tc_math:
                    st.markdown(
                        "<div style='font-size:.72em;color:var(--ui-ok, #1a6b3a);font-weight:700;"
                        "letter-spacing:.06em;margin:4px 0 3px'>📐 MATEMÁTICAS</div>",
                        unsafe_allow_html=True,
                    )
                    _tb2 = st.columns(len(_snips_math))
                    for _j, (_col, (_lbl, _snip, _tip)) in enumerate(zip(_tb2, _snips_math)):
                        if _col.button(_lbl, key=f"sM_{i}_{_j}", help=_tip, use_container_width=True):
                            _cur = st.session_state.get(f"dev_txt_{i}", q.get("txt", ""))
                            st.session_state[f"dev_txt_{i}"] = _cur + _snip
                            st.rerun()
                with _tc_phys:
                    st.markdown(
                        "<div style='font-size:.72em;color:var(--primary, #1a3a5c);font-weight:700;"
                        "letter-spacing:.06em;margin:4px 0 3px'>🔬 FÍSICA MÉDICA</div>",
                        unsafe_allow_html=True,
                    )
                    _tb3 = st.columns(len(_snips_phys))
                    for _j, (_col, (_lbl, _snip, _tip)) in enumerate(zip(_tb3, _snips_phys)):
                        if _col.button(_lbl, key=f"sP_{i}_{_j}", help=_tip, use_container_width=True):
                            _cur = st.session_state.get(f"dev_txt_{i}", q.get("txt", ""))
                            st.session_state[f"dev_txt_{i}"] = _cur + _snip
                            st.rerun()

                with st.expander("📚 Guía rápida de escritura", expanded=False):
                    if _is_md:
                        st.markdown("""
**Markdown con fórmulas LaTeX** — escribe texto normal y envuelve las fórmulas con `$`

| Escribes… | Resultado |
|---|---|
| `**texto**` | **negrita** |
| `*texto*` | *cursiva* |
| `- elemento` | • lista con viñetas |
| `1. elemento` | 1. lista numerada |
| `$E = mc^2$` | fórmula inline: E = mc² |
| `$$\\frac{a}{b}$$` | fracción en bloque centrada |
| `$\\alpha$`, `$\\beta$`, `$\\mu$` | α, β, μ |
| `$D = \\frac{E}{m}$` | D = E/m (dosis) |
| `$I = I_0 e^{-\\mu x}$` | ley de atenuación |

💡 Para fórmulas largas usa `$$...$$` en su propia línea.
                        """)
                    else:
                        st.markdown("""
**LaTeX puro** — para usuarios avanzados

| Escribes… | Resultado |
|---|---|
| `\\textbf{texto}` | **negrita** |
| `\\textit{texto}` | *cursiva* |
| `$E = mc^2$` | fórmula inline |
| `\\frac{a}{b}` | fracción (dentro de `$`) |
| `\\sqrt{x}` | √x |
| `\\alpha`, `\\beta`, `\\mu` | α, β, μ |

💡 Para texto mixto con pocas fórmulas considera usar **Markdown**.
                        """)

                _ph_edit = (
                    "Escribe el enunciado en Markdown…\n\nEjemplo:\n"
                    "Calcula la dosis absorbida si la energía depositada es\n"
                    "$E = 5\\,\\mathrm{mJ}$ en una masa de $m = 2\\,\\mathrm{g}$.\n\n"
                    "Usando $D = \\frac{E}{m}$, obtenemos…"
                    if _is_md else "Escribe en LaTeX…\nCalcula $D = \\frac{E}{m}$ si…"
                )
                _ed_col, _pv_col = st.columns(2) if (_bit_dev and _is_md) else (st, None)
                new_txt = _ed_col.text_area(
                    "Enunciado", value=q.get("txt", ""), height=220,
                    key=f"dev_txt_{i}", label_visibility="collapsed",
                    placeholder=_ph_edit,
                )
                q["txt"] = new_txt
                if _pv_col is not None:   # vista en directo: Streamlit dibuja las fórmulas $…$
                    with _pv_col.container(border=True, height=220):
                        st.markdown(new_txt if new_txt.strip() else "*La vista previa aparecerá aquí.*")

                # Imagen del enunciado
                _img_cur_pos = q.get("imagen_pos", "debajo")
                if _img_cur_pos not in _IMG_POS_OPTS:
                    _img_cur_pos = "debajo"
                _ie1, _ie2 = st.columns([2, 3])
                new_img_pos = _ie1.selectbox(
                    "Posición de la imagen",
                    list(_IMG_POS_OPTS.keys()),
                    index=list(_IMG_POS_OPTS.keys()).index(_img_cur_pos),
                    format_func=lambda x: _IMG_POS_OPTS[x],
                    key=f"dev_img_pos_{i}",
                )
                img_up = _ie2.file_uploader(
                    "Añadir imagen al enunciado (PNG/JPG)",
                    type=["png", "jpg", "jpeg"],
                    key=f"dev_img_{i}",
                )
                if img_up:
                    new_img_bytes = img_up.getvalue()
                    new_img_name  = img_up.name
                    st.image(img_up, width=280)
                elif q.get("imagen_bytes"):
                    import io as _io_tmp
                    new_img_bytes = q["imagen_bytes"]
                    new_img_name  = q.get("imagen_name", f"dev_img_{i+1}.png")
                    _ic1, _ic2 = st.columns([3, 1])
                    _ic1.image(_io_tmp.BytesIO(new_img_bytes), width=260, caption=new_img_name)
                    if _ic2.button("🗑️ Quitar imagen", key=f"dev_img_del_{i}"):
                        new_img_bytes = None
                        new_img_name  = ""
                else:
                    new_img_bytes = None
                    new_img_name  = ""

            # ══════════════ Solución (pestaña propia en Bitácora) ═════════════
            with _tab_sol:
                # Solución modelo — solo cuando NO hay apartados
                if not subapts:
                    st.divider()
                    st.markdown(
                        "<div style='font-size:.8em;color:var(--ui-ok, #27ae60);font-weight:700;"
                        "margin:6px 0 4px'>📖 Solución modelo</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        "<div style='font-size:.72em;color:var(--ui-used, #7d3c98);font-weight:700;"
                        "letter-spacing:.06em;margin:4px 0 3px'>✏️ TEXTO</div>",
                        unsafe_allow_html=True,
                    )
                    _stb1 = st.columns(len(_snips_text))
                    for _j, (_col, (_lbl, _snip, _tip)) in enumerate(zip(_stb1, _snips_text)):
                        if _col.button(_lbl, key=f"ssT_{i}_{_j}", help=_tip, use_container_width=True):
                            _cur = st.session_state.get(f"dev_sol_{i}", q.get("solucion_modelo", ""))
                            st.session_state[f"dev_sol_{i}"] = _cur + _snip
                            st.rerun()
                    _stc_m, _stc_p = (st.container(), st.container()) if _bit_dev else st.columns([9, 8])
                    with _stc_m:
                        st.markdown(
                            "<div style='font-size:.72em;color:var(--ui-ok, #1a6b3a);font-weight:700;"
                            "letter-spacing:.06em;margin:4px 0 3px'>📐 MATEMÁTICAS</div>",
                            unsafe_allow_html=True,
                        )
                        _stb2 = st.columns(len(_snips_math))
                        for _j, (_col, (_lbl, _snip, _tip)) in enumerate(zip(_stb2, _snips_math)):
                            if _col.button(_lbl, key=f"ssM_{i}_{_j}", help=_tip, use_container_width=True):
                                _cur = st.session_state.get(f"dev_sol_{i}", q.get("solucion_modelo", ""))
                                st.session_state[f"dev_sol_{i}"] = _cur + _snip
                                st.rerun()
                    with _stc_p:
                        st.markdown(
                            "<div style='font-size:.72em;color:var(--primary, #1a3a5c);font-weight:700;"
                            "letter-spacing:.06em;margin:4px 0 3px'>🔬 FÍSICA MÉDICA</div>",
                            unsafe_allow_html=True,
                        )
                        _stb3 = st.columns(len(_snips_phys))
                        for _j, (_col, (_lbl, _snip, _tip)) in enumerate(zip(_stb3, _snips_phys)):
                            if _col.button(_lbl, key=f"ssP_{i}_{_j}", help=_tip, use_container_width=True):
                                _cur = st.session_state.get(f"dev_sol_{i}", q.get("solucion_modelo", ""))
                                st.session_state[f"dev_sol_{i}"] = _cur + _snip
                                st.rerun()
                    _sol_et, _sol_pt = st.tabs(["✏️ Editar solución", "👁 Vista previa"])
                    with _sol_et:
                        new_sol_modelo = st.text_area(
                            "Solución modelo", value=q.get("solucion_modelo", ""),
                            height=200, key=f"dev_sol_{i}",
                            label_visibility="collapsed",
                            placeholder="Escribe la solución en Markdown…\n\n"
                                        "**a)** Aplicando $A = \\lambda N$:\n\n"
                                        "$$\\lambda = \\frac{M \\cdot A}{m \\cdot N_A}$$",
                        )
                    with _sol_pt:
                        _sol_cur = st.session_state.get(f"dev_sol_{i}", q.get("solucion_modelo", ""))
                        if _sol_cur.strip():
                            _sbody = _dev_md_to_html(_sol_cur)
                            stcomponents.html(mathjax_html(
                                f"""<div style="font-family:Calibri,sans-serif;font-size:10.5pt;
                                    line-height:1.7;padding:16px 22px;background:var(--ok-bg, #f6fff6);
                                    border:1px solid var(--ui-border, #c8e6c9);border-radius:8px;color:var(--text, #1a1a2e)">
                                  <div style="color:var(--ui-ok, #27ae60);font-size:8pt;text-transform:uppercase;
                                      letter-spacing:.1em;font-weight:700;border-bottom:2px solid var(--ui-border, #c8e6c9);
                                      padding-bottom:6px;margin-bottom:14px">Solución modelo</div>
                                  {_sbody}</div>"""
                            ), height=280, scrolling=True)
                        else:
                            st.info("Escribe la solución para ver la vista previa.")
                else:
                    new_sol_modelo = q.get("solucion_modelo", "")
                    if _bit_dev:
                        st.caption("Esta pregunta tiene apartados: la solución se escribe en cada apartado "
                                   "(pestaña Apartados).")

            # ══════════════ Tab 2: Apartados ══════════════════════════════════
            with _tab_apts:
                _num_apt = st.radio(
                    "Numeración de apartados",
                    list(_NUM_LABELS.keys()),
                    index=list(_NUM_LABELS.keys()).index(q.get("numeracion_apt", "abc")),
                    format_func=lambda x: _NUM_LABELS[x],
                    horizontal=True,
                    key=f"apt_num_{i}",
                )
                _to_del_apt = []
                for ai, apt in enumerate(subapts):
                    _apt_head = apt.get("enunciado","")[:45] or "(vacío)"
                    _apt_pts_v = float(apt.get("puntos") or 1.0)
                    with st.expander(
                        f"**{ai+1}.** {_apt_head}  ·  {_apt_pts_v:g} pt",
                        expanded=not apt.get("enunciado","").strip(),
                    ):
                        _ac1, _ac2, _ac3 = st.columns([1.5, 2, 0.6])
                        apt["puntos"] = _ac1.number_input(
                            "Puntos", value=_apt_pts_v, min_value=0.0, step=0.5,
                            key=f"apt_pts_{i}_{ai}")
                        _ec = str(apt.get("espacio") or "5cm")
                        apt["espacio"] = _ac2.selectbox(
                            "Espacio respuesta", _ESP_APT_OPTS,
                            index=_ESP_APT_OPTS.index(_ec) if _ec in _ESP_APT_OPTS else 2,
                            key=f"apt_esp_{i}_{ai}")
                        if _ac3.button("🗑", key=f"apt_del_{i}_{ai}",
                                        help="Eliminar", use_container_width=True):
                            _to_del_apt.append(ai)

                        # Toolbar math apartado
                        _asb = st.columns(len(_SNIPS_APT))
                        for _sj, (_asc, (_asl, _ass, _ast)) in enumerate(zip(_asb, _SNIPS_APT)):
                            if _asc.button(_asl, key=f"aM_{i}_{ai}_{_sj}", help=_ast,
                                           use_container_width=True):
                                _ck = f"apt_enun_{i}_{ai}"
                                st.session_state[_ck] = (
                                    st.session_state.get(_ck, apt.get("enunciado","")) + _ass)
                                st.rerun()

                        apt["enunciado"] = st.text_area(
                            "Enunciado del apartado",
                            value=apt.get("enunciado",""), height=110,
                            key=f"apt_enun_{i}_{ai}",
                            placeholder=f"Enunciado del apartado {ai+1}…",
                        )

                        # Imagen del apartado
                        _ai1, _ai2 = st.columns([2, 3])
                        _apt_img_cur = apt.get("imagen_pos","debajo")
                        if _apt_img_cur not in _IMG_POS_OPTS:
                            _apt_img_cur = "debajo"
                        apt["imagen_pos"] = _ai1.selectbox(
                            "Posición imagen apartado",
                            list(_IMG_POS_OPTS.keys()),
                            index=list(_IMG_POS_OPTS.keys()).index(_apt_img_cur),
                            format_func=lambda x: _IMG_POS_OPTS[x],
                            key=f"apt_img_pos_{i}_{ai}",
                        )
                        _apt_img_up = _ai2.file_uploader(
                            "Imagen del apartado (opcional)",
                            type=["png","jpg","jpeg"],
                            key=f"apt_img_{i}_{ai}",
                        )
                        if _apt_img_up:
                            apt["imagen_bytes"] = _apt_img_up.getvalue()
                            apt["imagen_name"]  = _apt_img_up.name
                            st.image(_apt_img_up, width=240)
                        elif apt.get("imagen_bytes"):
                            import io as _io_tmp2
                            _aic1, _aic2 = st.columns([3, 1])
                            _aic1.image(_io_tmp2.BytesIO(apt["imagen_bytes"]), width=220,
                                        caption=apt.get("imagen_name",""))
                            if _aic2.button("🗑️ Quitar", key=f"apt_img_del_{i}_{ai}"):
                                apt["imagen_bytes"] = None
                                apt["imagen_name"]  = ""
                        else:
                            apt["imagen_bytes"] = None
                            apt["imagen_name"]  = ""

                        # Solución del apartado
                        st.markdown(
                            "<div style='font-size:.72em;color:var(--ui-ok, #27ae60);font-weight:700;"
                            "letter-spacing:.06em;margin:6px 0 3px'>📖 SOLUCIÓN (snippets)</div>",
                            unsafe_allow_html=True,
                        )
                        _ssb = st.columns(len(_SNIPS_APT))
                        for _sj, (_ssc, (_ssl, _sss, _sst)) in enumerate(zip(_ssb, _SNIPS_APT)):
                            if _ssc.button(_ssl, key=f"aS_{i}_{ai}_{_sj}", help=_sst,
                                           use_container_width=True):
                                _sk = f"apt_sol_{i}_{ai}"
                                st.session_state[_sk] = (
                                    st.session_state.get(_sk, apt.get("solucion","")) + _sss)
                                st.rerun()
                        apt["solucion"] = st.text_area(
                            "Solución modelo del apartado (opcional)",
                            value=apt.get("solucion",""), height=90,
                            key=f"apt_sol_{i}_{ai}",
                            placeholder="Solución de este apartado…",
                        )

                        # Preview individual
                        _apt_pv_key = f"_apt_pv_{i}_{ai}"
                        if st.button("🔍 Previsualizar apartado", key=f"apt_pv_btn_{i}_{ai}",
                                      use_container_width=True):
                            st.session_state[_apt_pv_key] = not st.session_state.get(_apt_pv_key, False)
                            st.rerun()
                        if st.session_state.get(_apt_pv_key):
                            _apt_enun_html = _dev_md_to_html(apt.get("enunciado",""))
                            _apt_sol_html  = _dev_md_to_html(apt.get("solucion",""))
                            _apt_html = (
                                f"<div style='font-family:Calibri,sans-serif;font-size:10.5pt;"
                                f"line-height:1.7;padding:14px 18px;background:var(--card2, #f8f9fa);"
                                f"border:1px solid var(--ui-border, #dee2e6);border-radius:6px;color:var(--text, #1a1a2e)'>"
                                f"<div style='font-weight:700;color:var(--ui-used, #7d3c98);margin-bottom:8px'>"
                                f"Apartado {ai+1}</div>{_apt_enun_html}"
                            )
                            if apt.get("solucion","").strip():
                                _apt_html += (
                                    f"<div style='margin-top:10px;padding:8px 12px;"
                                    f"background:var(--ok-bg, #f0fff0);border-left:3px solid var(--ui-ok, #27ae60);"
                                    f"border-radius:4px'><small style='color:var(--ui-ok, #27ae60);"
                                    f"font-weight:700'>Solución:</small><br>{_apt_sol_html}</div>"
                                )
                            _apt_html += "</div>"
                            stcomponents.html(mathjax_html(_apt_html), height=260, scrolling=True)

                        subapts[ai] = apt

                for ai in sorted(_to_del_apt, reverse=True):
                    subapts.pop(ai)

                if st.button("➕ Añadir apartado", key=f"apt_add_{i}", type="primary"):
                    subapts.append({
                        "enunciado": "", "puntos": 1.0, "espacio": "5cm",
                        "solucion": "", "imagen_bytes": None,
                        "imagen_name": "", "imagen_pos": "debajo",
                    })
                    st.rerun()
                if subapts:
                    _pts_apts = sum(float(a.get("puntos") or 0) for a in subapts)
                    st.caption(f"{len(subapts)} apartados · total **{_pts_apts:g} pt**")

            # ══════════════ Tab 3: Rúbrica & Datos ════════════════════════════
            with _tab_rub:
                _rr1, _rr2 = st.columns(2)
                if subapts:
                    _pts_calc = sum(float(a.get("puntos") or 0) for a in subapts)
                    _rr1.metric("Puntos totales (suma de apartados)", f"{_pts_calc:g} pt")
                    new_pts = _pts_calc
                else:
                    new_pts = _rr1.number_input(
                        "Puntuación (pts)", value=float(q.get("pts", 1.0)),
                        min_value=0.0, step=0.5, key=f"dev_pts_{i}")
                new_esp = _rr2.selectbox(
                    "Espacio para respuesta", _ESP_LABELS,
                    index=_ESP_LABELS.index(q.get("espacio", "Automático"))
                          if q.get("espacio", "Automático") in _ESP_LABELS else 0,
                    key=f"dev_esp_{i}",
                )

                st.markdown("---")
                st.caption("Criterios de evaluación: descripción, puntos máximos e incremento.")
                criterios = list(q.get("criterios", []))
                _rh1, _rh2, _rh3, _rh4 = st.columns([5, 1.2, 1.2, 0.8])
                _rh1.markdown("<small style='color:var(--muted, #888)'>Criterio</small>", unsafe_allow_html=True)
                _rh2.markdown("<small style='color:var(--muted, #888)'>Pts máx</small>", unsafe_allow_html=True)
                _rh3.markdown("<small style='color:var(--muted, #888)'>Incremento</small>", unsafe_allow_html=True)
                to_del_crit = []
                for ci, crit in enumerate(criterios):
                    rc1, rc2, rc3, rc4 = st.columns([5, 1.2, 1.2, 0.8])
                    new_desc = rc1.text_input(
                        "Criterio", value=crit.get("desc", ""),
                        key=f"crit_desc_{i}_{ci}",
                        label_visibility="collapsed",
                        placeholder="Descripción del criterio…")
                    new_cpts = rc2.number_input(
                        "pts", value=float(crit.get("pts", 0.5)),
                        min_value=0.0, step=0.25,
                        key=f"crit_pts_{i}_{ci}",
                        label_visibility="collapsed")
                    new_cinc = rc3.number_input(
                        "inc", value=float(crit.get("incremento", 0.25)),
                        min_value=0.0, step=0.05,
                        key=f"crit_inc_{i}_{ci}",
                        label_visibility="collapsed")
                    if rc4.button("🗑️", key=f"crit_del_{i}_{ci}", help="Eliminar criterio"):
                        to_del_crit.append(ci)
                    else:
                        _levels = []
                        if new_cinc > 0 and new_cpts > 0:
                            import math as _m
                            _n = round(new_cpts / new_cinc)
                            _levels = [f"{new_cinc*k:.2g}" for k in range(_n + 1)]
                        criterios[ci] = {"desc": new_desc, "pts": new_cpts,
                                         "incremento": new_cinc}
                        if _levels:
                            rc1.caption(f"Valores posibles: {' / '.join(_levels)}")
                for ci in sorted(to_del_crit, reverse=True):
                    criterios.pop(ci)
                if st.button("➕ Añadir criterio", key=f"crit_add_{i}"):
                    criterios.append({"desc": "", "pts": 0.5, "incremento": 0.25})
                _total_crit = sum(c.get("pts", 0) for c in criterios)
                if criterios:
                    _crit_caption = f"Total criterios: **{_total_crit:.2f} pts** (pregunta: {new_pts} pts)"
                    if abs(_total_crit - new_pts) > 0.01:
                        st.warning(f"⚠️ {_crit_caption} — **No coinciden**")
                    else:
                        st.caption(_crit_caption)

                st.markdown("---")
                st.caption(
                    "Constantes que aparecerán como *Datos:* debajo del enunciado. "
                    "Añade nuevas en **Configuración → 🔢 Constantes**."
                )
                new_datos_ids = q.get("datos_ids", "")
                _datos_df_gen = lib.get_datos_df(st.session_state.get("excel_dfs", {}))
                if _datos_df_gen.empty or not _datos_df_gen['ID'].astype(str).str.strip().any():
                    st.info("No hay constantes en la BD. Añádelas en Configuración → 🔢 Constantes.")
                else:
                    _cur_ids = [x.strip() for x in new_datos_ids.split(',') if x.strip()]
                    _cats_gen = sorted(
                        _datos_df_gen['Categoría'].fillna('Sin categoría').unique().tolist())
                    _sel_ids = list(_cur_ids)
                    for _cat in _cats_gen:
                        _cdf = _datos_df_gen[
                            _datos_df_gen['Categoría'].fillna('Sin categoría') == _cat]
                        if _cdf.empty:
                            continue
                        st.markdown(f"**{_cat}**")
                        for _, _dr in _cdf.iterrows():
                            _did = str(_dr['ID']).strip()
                            _nom = str(_dr.get('Nombre','') or '').strip()
                            _sym = str(_dr.get('Símbolo','') or '').strip()
                            _val = str(_dr.get('Valor','') or '').strip()
                            _uni = str(_dr.get('Unidades','') or '').strip()
                            _lbl = f"{_nom} — {_sym} = {_val} {_uni}".strip(" —")
                            _chk = st.checkbox(_lbl, value=(_did in _sel_ids),
                                               key=f"gen_dat_{i}_{_did}")
                            if _chk and _did not in _sel_ids:
                                _sel_ids.append(_did)
                            elif not _chk and _did in _sel_ids:
                                _sel_ids.remove(_did)
                    new_datos_ids = ','.join(_sel_ids)
                    if new_datos_ids:
                        _prev_dat = lib.format_datos_word(new_datos_ids, _datos_df_gen)
                        st.caption(f"→ *{_prev_dat}*")

            # ══════════════ Tab 4: Vista previa completa ═══════════════════════
            with _tab_prev_q:
                _pv1, _pv2 = st.columns([3, 1])
                _sol_mode_prev = _pv1.radio(
                    "Versión a previsualizar", ["Alumno", "Soluciones"],
                    horizontal=True, key=f"qprev_ver_{i}",
                )
                _prev_state_key = f"_qprev_{i}"
                if _pv2.button("🔍 Renderizar", key=f"qprev_btn_{i}",
                                use_container_width=True, type="primary"):
                    st.session_state[_prev_state_key] = True
                    st.rerun()
                if st.session_state.get(_prev_state_key):
                    _show_sol  = (_sol_mode_prev == "Soluciones")
                    _qh_main   = _dev_md_to_html(q.get("txt",""))
                    _qhtml = (
                        f"<div style='font-family:Calibri,sans-serif;font-size:11pt;"
                        f"line-height:1.75;padding:20px 26px;background:var(--used-bg, #fdfaff);"
                        f"border:1px solid var(--ui-border, #ede7f6);border-radius:8px;color:var(--text, #1a1a2e)'>"
                        f"<div style='color:var(--ui-used, #7d3c98);font-size:8pt;text-transform:uppercase;"
                        f"letter-spacing:.1em;font-weight:700;border-bottom:2px solid var(--ui-border, #ede7f6);"
                        f"padding-bottom:6px;margin-bottom:16px'>"
                        f"Pregunta {i+1} · {'Soluciones' if _show_sol else 'Alumno'}</div>"
                        f"<p style='font-weight:700;margin-bottom:10px'>({_pts_disp:g} pts)</p>"
                        f"{_qh_main}"
                    )
                    if subapts:
                        _enum_labs = {
                            "abc":   [chr(ord('a')+k) for k in range(26)],
                            "roman": ["i","ii","iii","iv","v","vi","vii","viii","ix","x"],
                            "num":   [str(k+1) for k in range(20)],
                        }
                        _labs = _enum_labs.get(q.get("numeracion_apt","abc"), _enum_labs["abc"])
                        _qhtml += "<ol style='padding-left:20px;margin-top:12px'>"
                        for ai2, apt2 in enumerate(subapts):
                            _lab2      = _labs[ai2] if ai2 < len(_labs) else str(ai2+1)
                            _apt_e2    = _dev_md_to_html(apt2.get("enunciado",""))
                            _apt_pts2  = float(apt2.get("puntos") or 0)
                            _qhtml += (
                                f"<li style='margin-bottom:10px'>"
                                f"<span style='font-weight:600'>({_lab2})</span> "
                                f"<em style='color:var(--muted, #888)'>({_apt_pts2:g} pt)</em> {_apt_e2}"
                            )
                            if _show_sol and apt2.get("solucion","").strip():
                                _qhtml += (
                                    f"<div style='margin:6px 0 0 16px;padding:6px 10px;"
                                    f"background:var(--ok-bg, #f0fff0);border-left:3px solid var(--ui-ok, #27ae60);"
                                    f"border-radius:3px'><small style='color:var(--ui-ok, #27ae60);"
                                    f"font-weight:700'>Sol:</small> "
                                    f"{_dev_md_to_html(apt2.get('solucion',''))}</div>"
                                )
                            elif not _show_sol:
                                _qhtml += (
                                    f"<div style='margin:6px 0 0 16px;height:40px;"
                                    f"border:1px dashed var(--ui-border, #ccc);border-radius:3px;"
                                    f"background:var(--card2, #fafafa)'></div>"
                                )
                            _qhtml += "</li>"
                        _qhtml += "</ol>"
                    else:
                        _sol_txt = q.get("solucion_modelo","").strip()
                        if _show_sol and _sol_txt:
                            _qhtml += (
                                f"<div style='margin-top:14px;padding:10px 14px;"
                                f"background:var(--ok-bg, #f0fff0);border-left:4px solid var(--ui-ok, #27ae60);"
                                f"border-radius:4px'>"
                                f"<small style='color:var(--ui-ok, #27ae60);font-weight:700'>"
                                f"Solución modelo</small><br>"
                                f"{_dev_md_to_html(_sol_txt)}</div>"
                            )
                        else:
                            _qhtml += (
                                "<div style='margin-top:14px;height:80px;"
                                "border:1px dashed var(--border2, #bdc3c7);border-radius:4px;"
                                "background:var(--card2, #fafafa);display:flex;align-items:center;"
                                "justify-content:center;color:var(--faint, #aaa)'>"
                                "[ Espacio de respuesta ]</div>"
                            )
                    _qhtml += "</div>"
                    stcomponents.html(mathjax_html(_qhtml), height=520, scrolling=True)
                else:
                    st.info("Pulsa **🔍 Renderizar** para ver la vista previa completa.")

            # ── Guardar estado ────────────────────────────────────────────────
            dev_qs[i] = {
                "txt":            new_txt,
                "pts":            new_pts,
                "espacio":        new_esp,
                "modo":           q["modo"],
                "criterios":      criterios,
                "solucion_modelo": new_sol_modelo,
                "imagen_bytes":   new_img_bytes,
                "imagen_name":    new_img_name,
                "imagen_pos":     new_img_pos,
                "datos_ids":      new_datos_ids,
                "subapartados":   subapts,
                "numeracion_apt": _num_apt,
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
def _alto_texto(t: str, cpl: int = 120) -> int:
    """Altura aproximada (px) de un texto en la vista con fórmulas."""
    return 22 * max(1, -(-len(str(t or "")) // cpl))


def _alto_tarjeta(p: dict) -> int:
    ops = (p.get("opciones_list") or [])[:4]
    return 70 + _alto_texto(p.get("enunciado", "")) + sum(_alto_texto(o, 130) + 6 for o in ops)


def _render_checks_prev(cache: list, vista: str):
    """Avisos rápidos sobre el examen: reparto de respuestas, repeticiones, preguntas incompletas."""
    from difflib import SequenceMatcher
    n = len(cache)
    letras = [str(p.get("letra_correcta", "")).upper() for p in cache]
    cnt = {L: letras.count(L) for L in "ABCD"}
    chips, warns = [], 0
    reparto = " · ".join(f"{L} {cnt[L]}" for L in "ABCD")
    if vista == "Vista previa" and st.session_state.get("exam_cfg", {}).get("bar", True):
        chips.append(("", f"Respuestas correctas: {reparto} (se barajan al exportar; mira un modelo)"))
    else:
        mal = n >= 8 and any(c > 0.4 * n or c < 0.1 * n for c in cnt.values())
        warns += mal
        chips.append(("warn" if mal else "ok", f"Respuestas correctas: {reparto}"))
        run, best, prev = 0, 0, None
        for L in letras:
            run = run + 1 if L == prev else 1
            prev = L
            best = max(best, run)
        if best >= 4:
            warns += 1
            chips.append(("warn", f"{best} respuestas seguidas con la misma letra"))
    ids = [p.get("ID_Pregunta") for p in cache]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        warns += 1
        chips.append(("err", "Repetidas: " + ", ".join(dups)))
    norm = [lib._normalizar_texto(p.get("enunciado", "")) for p in cache]
    pares = []
    for i in range(n):
        for j in range(i + 1, n):
            if ids[i] != ids[j] and norm[i] and SequenceMatcher(None, norm[i], norm[j]).quick_ratio() > 0.85 \
                    and SequenceMatcher(None, norm[i], norm[j]).ratio() > 0.85:
                pares.append(f"{i + 1}–{j + 1}")
    if pares:
        warns += 1
        chips.append(("warn", "Enunciados muy parecidos: " + ", ".join(pares[:6])))
    inc = [str(k + 1) for k, p in enumerate(cache)
           if str(p.get("letra_correcta", "")).upper() not in ("A", "B", "C", "D")
           or sum(1 for o in (p.get("opciones_list") or [])[:4] if str(o).strip()) < 4]
    if inc:
        warns += 1
        chips.append(("err", "Sin respuesta correcta u opciones vacías: " + ", ".join(inc)))
    recientes = sum(1 for p in cache if str(p.get("usada", "") or "").strip()
                    and not es_uso_antiguo(str(p.get("usada", "")), 12))
    if recientes:
        chips.append(("warn", f"{recientes} usada(s) en los últimos 12 meses"))
    sin_sol = sum(1 for p in cache if not str(p.get("solucion", "") or "").strip())
    if sin_sol:
        chips.append(("", f"{sin_sol} sin solución desarrollada"))
    if not warns:
        chips.insert(0, ("ok", "✓ Sin problemas detectados"))
    _col = {"ok": "var(--ok-bg);color:var(--ok)", "warn": "var(--warn-bg);color:var(--warn)",
            "err": "var(--err-bg);color:var(--err)", "": "var(--card2);color:var(--text2)"}
    html = "".join(f"<span style='display:inline-block;padding:3px 10px;margin:2px 4px 2px 0;border-radius:999px;"
                   f"font-size:.8rem;font-weight:600;background:{_col[c]}'>{t}</span>" for c, t in chips)
    st.markdown(f"<div style='margin:2px 0 12px 0'><b style='font-size:.85rem;margin-right:6px'>"
                f"Comprobaciones</b>{html}</div>", unsafe_allow_html=True)



with tab_prev:

    # ── Banner de modo recuperación ───────────────────────────────────────────
    if st.session_state.get("recovery_mode"):
        _lk = st.session_state.get("exam_lock") or {}
        with st.container(key="pv_lock"):
            rb1, rb2 = st.columns([5, 1], vertical_alignment="center")
            rb1.markdown(
                (f"**Examen {E.estado_de(_lk).lower()} · {_lk.get('Nombre', '')}** — abierto tal como se guardó: orden"
                 + (f", modelos {', '.join(sorted(_lk.get('posiciones') or {}))} y sus claves" if _lk.get("posiciones") else "")
                 + ". Bloqueado para no cambiarlo por accidente; si lo exportas de nuevo saldrá idéntico.")
                if _lk else "**Examen recuperado desde CSV** — bloqueado para no cambiarlo por accidente.")
            if rb2.button("Desbloquear", key="btn_unlock_prev", use_container_width=True):
                E.desbloquear()
                notify("Examen desbloqueado: los cambios se guardarán como un examen nuevo.")
                st.rerun()

    # ── Controles (Bitácora: en una tarjeta, interruptor y «Renderizar LaTeX») ─
    _bit_prev = get_estilo() == "bitacora"
    with (st.container(border=True, key="card_prev_ctrl") if _bit_prev else st.container()):
        ctrl1, ctrl2, ctrl3, ctrl4, ctrl5 = (st.columns([1.8, 1.8, 1.5, 1, 1.7], vertical_alignment="bottom")
                                             if _bit_prev else st.columns([2, 2, 2, 1, 1]))
        show_sol  = (ctrl1.toggle("Mostrar soluciones", value=True, key="prev_show_sol") if _bit_prev
                     else ctrl1.checkbox("Mostrar soluciones ✓", value=True, key="prev_show_sol"))
        ord_prev  = ctrl2.selectbox("Orden",
                        ["Por bloques", "Por temas", "Global aleatorio", "Manual (selección)", "Sin barajar (ID)"],
                        key="prev_ord")
        seed_prev = ctrl3.number_input("Semilla (0=aleatoria)", min_value=0, value=0, key="prev_seed")
        _locked   = st.session_state.get("recovery_mode", False)
        gen_btn   = ctrl4.button("🎲 Generar", type="primary", key="btn_gen_prev",
                                  use_container_width=True, disabled=_locked)
        _ef_master = ((st.session_state.get("export_files") or {}).get("_master")
                      or st.session_state.get("_lock_master") or [])
        if _bit_prev:
            _mods_prev = ["Vista previa"] + [f"Modelo {m['letra_version']}" for m in _ef_master]
            if st.session_state.get("prev_modelo") not in _mods_prev:
                st.session_state["prev_modelo"] = "Vista previa"
            vista_mod = ctrl5.selectbox(
                "Ver", _mods_prev, key="prev_modelo",
                help="Los modelos A, B… son los de la última exportación, con su orden y sus letras definitivas.")
            mj_btn = False
        else:
            vista_mod = "Vista previa"
            mj_btn    = ctrl5.button("∑ MathJax", key="btn_mathjax",
                                      use_container_width=True,
                                      help="Vista con fórmulas matemáticas renderizadas")

    sel_prev  = get_sel_ids()          # manuales fijas
    auto_rec  = st.session_state.get("auto_recipe", {})

    if gen_btn and E.n_cambios() and st.session_state.get("cache_examen"):
        st.session_state["_gen_conf"] = True
        gen_btn = False
    if st.session_state.get("_gen_conf"):
        with st.container(key="pv_genconf"):
            gc1, gc2, gc3 = st.columns([5, 1.3, 1], vertical_alignment="center")
            gc1.markdown(f"**Este examen tiene {E.n_cambios()} cambio(s) hechos a mano.** Si generas de nuevo se rehace "
                         "con la receta y se pierden (podrás recuperarlos con Deshacer).")
            if gc2.button("Generar igualmente", type="primary", key="pv_genconf_ok", use_container_width=True):
                st.session_state.pop("_gen_conf", None)
                gen_btn = True
            if gc3.button("Cancelar", key="pv_genconf_no", use_container_width=True):
                st.session_state.pop("_gen_conf", None)
                st.rerun()

    if gen_btn:
        if not sel_prev and not auto_rec:
            st.warning("⚠️ Sin preguntas seleccionadas ni receta automática — ve a la pestaña Selección.")
        else:
            rng          = random.Random(seed_prev if seed_prev else None)
            _an_gen      = _datos_analisis() if auto_rec else None
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
                                and _dif_norm(df_lookup.get(p, {}).get("dificultad", "")) == _dif_norm(dif_name)
                            ]
                            pool_ids = df_total[
                                (df_total["bloque"] == bloque) &
                                (df_total["dificultad"].map(_dif_norm) == _dif_norm(dif_name)) &
                                (~df_total["ID_Pregunta"].isin(already_used))
                            ]["ID_Pregunta"].tolist()
                            label_str = "(cualquier tema)"
                        elif tema_key.startswith("__OBJ_"):
                            obj_cod = tema_key[len("__OBJ_"):]
                            already_fixed = [
                                p for p in sel_prev
                                if (bloque == "__GEN__" or df_lookup.get(p, {}).get("bloque", "") == bloque)
                                and str(df_lookup.get(p, {}).get("objetivo", "")) == obj_cod
                                and _dif_norm(df_lookup.get(p, {}).get("dificultad", "")) == _dif_norm(dif_name)
                            ]
                            _obj_mask = (
                                ((df_total["bloque"] == bloque) | (bloque == "__GEN__")) &
                                (df_total["dificultad"].map(_dif_norm) == _dif_norm(dif_name)) &
                                (~df_total["ID_Pregunta"].isin(already_used))
                            )
                            if "objetivo" in df_total.columns:
                                _obj_mask &= (df_total["objetivo"].astype(str) == obj_cod)
                            pool_ids = df_total[_obj_mask]["ID_Pregunta"].tolist()
                            label_str = f"Obj {obj_cod}"
                        else:
                            already_fixed = [
                                p for p in sel_prev
                                if df_lookup.get(p, {}).get("bloque", "") == bloque
                                and str(df_lookup.get(p, {}).get("Tema", "")) == str(tema_key)
                                and _dif_norm(df_lookup.get(p, {}).get("dificultad", "")) == _dif_norm(dif_name)
                            ]
                            pool_ids = df_total[
                                (df_total["bloque"] == bloque) &
                                (df_total["Tema"].astype(str) == str(tema_key)) &
                                (df_total["dificultad"].map(_dif_norm) == _dif_norm(dif_name)) &
                                (~df_total["ID_Pregunta"].isin(already_used))
                            ]["ID_Pregunta"].tolist()
                            label_str = f"Tema {tema_key}"

                        needed = max(0, n_req - len(already_fixed))
                        if get_estilo() == "bitacora" or st.session_state.get("auto_opts"):
                            picked = _elegir_receta(pool_ids, needed, rng, df_lookup, exam_ids,
                                                    st.session_state.get("auto_opts", {}) or {},
                                                    sin_tope=tema_key not in ("__ALL__",) and not tema_key.startswith("__OBJ_"),
                                                    an=_an_gen)
                            actual = len(picked)
                        else:
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
            elif ord_key == "Por temas":
                pool.sort(key=lambda x: (orden_bloque(x.get("bloque", "")), nsort(str(x.get("Tema", "")))))
                new_pool = []
                for _, grp in groupby(pool, key=lambda x: (x.get("bloque", ""), str(x.get("Tema", "")))):
                    g = list(grp); rng.shuffle(g); new_pool.extend(g)
                pool = new_pool
            else:  # Por bloques
                pool.sort(key=lambda x: orden_bloque(x.get("bloque", "")))
                new_pool = []
                for _, grp in groupby(pool, key=lambda x: x.get("bloque", "")):
                    g = list(grp); rng.shuffle(g); new_pool.extend(g)
                pool = new_pool

            E.al_generar(pool)
            st.session_state.cache_examen = pool
            st.session_state.pop("prev_mathjax", None)
            st.rerun()

    # ── Mostrar avisos de la última generación ────────────────────────────────
    for w in st.session_state.get("gen_warnings", []):
        st.warning(f"⚠️ {w}")

    cache = st.session_state.cache_examen
    if cache and vista_mod != "Vista previa":
        # Modelo de la última exportación: orden y letras definitivos
        _mm = next((m for m in _ef_master if f"Modelo {m['letra_version']}" == vista_mod), None)
        if _mm:
            cache = [dict(p, opciones_list=p.get("opciones_finales", p.get("opciones_list")),
                          letra_correcta=p.get("letra_final", p.get("letra_correcta")))
                     for p in _mm["preguntas"]]

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
    elif _bit_prev:
        _preview_bitacora(cache, show_sol, vista_mod)
    else:
        cfg  = st.session_state.get("exam_cfg", {})
        inst = cfg.get("inst", "UCM")
        asig = cfg.get("asig", "FÍSICA MÉDICA")

        # ── Cabecera del examen (Clásico; en Bitácora el recuento va debajo) ───
        if not _bit_prev: st.markdown(
            f"<div style='background:linear-gradient(90deg,var(--chip, #2c3e50),var(--chip, #1a252f));color:var(--chip-ink, white);"
            f"padding:14px 18px;border-radius:8px;margin-bottom:16px'>"
            f"<h3 style='margin:0;font-size:1.1em'>{inst} · {asig}</h3>"
            f"<p style='margin:4px 0 0 0;opacity:0.75;font-size:0.85em'>"
            f"{len(cache)} preguntas test"
            f"{'  +  ' + str(len(st.session_state.dev_questions)) + ' desarrollo' if st.session_state.dev_questions else ''}"
            f"</p></div>",
            unsafe_allow_html=True,
        )

        # ── Comprobaciones rápidas (Bitácora) ──────────────────────────────────
        if _bit_prev:
            _render_checks_prev(cache, vista_mod)

        # ── Vista MathJax (iframe) ────────────────────────────────────────────
        if mj_btn:
            st.session_state["prev_mathjax"] = not st.session_state.get("prev_mathjax", False)
            st.rerun()

        if st.session_state.get("prev_mathjax") and not _bit_prev:
            # Construir HTML completo con MathJax (Clásico, botón ∑ MathJax)
            dev_qs = st.session_state.dev_questions
            html_body = ""
            if dev_qs:
                html_body += "<h4 style='color:var(--text, #2c3e50)'>PARTE I — DESARROLLO</h4>"
                for i, q in enumerate(dev_qs):
                    html_body += f"<p><b>{i+1}. {q['txt']}</b> ({q['pts']} pts)</p>"
                html_body += "<hr style='margin:12px 0'>"
            html_body += f"<h4 style='color:var(--text, #2c3e50)'>PARTE II — TEST ({len(cache)} preguntas)</h4>"
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
            if _bit_prev:
                st.caption("Para ver el PDF definitivo: pestaña **Exportar › Compilar PDF**.")
            else:
                st.caption("Vista MathJax — las fórmulas $...$ se renderizan correctamente.")
            stcomponents.html(full_html, height=min(height_px, 2200), scrolling=True)
        else:
            # ── Vista nativa Streamlit (cards con colores, sin iframe) ─────────
            dev_qs = st.session_state.dev_questions
            if _bit_prev:
                st.caption(f"**{len(cache)}** preguntas test"
                           + (f" + **{len(dev_qs)}** de desarrollo" if dev_qs else ""))
            if dev_qs:
                if _bit_prev:
                    _pts_dev = sum(float(q.get("pts") or 0) for q in dev_qs)
                    st.markdown(f"<div class='bloque-header'>PARTE I — DESARROLLO"
                                f"<span class='bloque-stats'>{len(dev_qs)} preguntas · {_pts_dev:g} pts</span></div>",
                                unsafe_allow_html=True)
                else:
                    st.markdown(
                        "<div style='background:var(--primary-soft, #eaf4fb);border-left:4px solid var(--primary, #3498db);"
                        "border-radius:5px;padding:10px 14px;margin-bottom:12px'>"
                        "<b style='color:var(--text, #2c3e50)'>PARTE I — DESARROLLO</b></div>",
                        unsafe_allow_html=True
                    )
                if _bit_prev:   # con fórmulas renderizadas
                    _dev_html = "".join(
                        f"<div class='q-card'><div class='q-enun'>{i+1}. {q['txt']}</div>"
                        f"<div style='font-size:.85em;color:var(--muted)'>{q['pts']} pts · {q['espacio']}</div></div>"
                        for i, q in enumerate(dev_qs))
                    stcomponents.html(mathjax_html(_dev_html), height=min(900, 40 + sum(
                        _alto_texto(q.get("txt", "")) + 40 for q in dev_qs)), scrolling=True)
                for i, q in enumerate(dev_qs if not _bit_prev else []):
                    st.markdown(
                        f"<div style='padding:6px 14px;margin-bottom:4px;border-left:3px solid var(--primary, #3498db)'>"
                        f"<b>{i+1}.</b> {q['txt']} <span style='color:var(--muted, #888);font-size:0.85em'>({q['pts']} pts · {q['espacio']})</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

            if _bit_prev:
                st.markdown(f"<div class='bloque-header'>PARTE II — TEST"
                            f"<span class='bloque-stats'>{len(cache)} preguntas</span></div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(
                    f"<div style='background:var(--primary-soft, #eaf4fb);border-left:4px solid var(--primary, #3498db);"
                    f"border-radius:5px;padding:10px 14px;margin-bottom:12px'>"
                    f"<b style='color:var(--text, #2c3e50)'>PARTE II — TEST</b>"
                    f"<span style='margin-left:10px;color:var(--muted, #666);font-size:0.85em'>{len(cache)} preguntas</span></div>",
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
                    f"{blq} — {len(preg_list)} preguntas · {n_f} fácil · {n_m} media · {n_d} difícil"
                    if _bit_prev else
                    f"📦 {blq}  —  {len(preg_list)} preguntas"
                    f"  🟢 {n_f} Fácil  🟡 {n_m} Media  🔴 {n_d} Difícil"
                )
                with st.expander(label, expanded=True):
                    cards_html = ""
                    for p in preg_list:
                        q_num += 1
                        cards_html += render_question_card_html(p, show_sol=show_sol, num=q_num)
                    if _bit_prev:   # fórmulas renderizadas dentro de cada bloque plegable
                        stcomponents.html(mathjax_html(cards_html), scrolling=True,
                                          height=min(1600, 24 + sum(_alto_tarjeta(p) for p in preg_list)))
                    else:
                        st.markdown(cards_html, unsafe_allow_html=True)

        if _bit_prev:
            st.caption("Pulsa la cabecera de un bloque para plegarlo. Para ver el PDF definitivo: "
                       "pestaña **Exportar › Compilar PDF**.")
        else:
            st.caption("ℹ️ Para fórmulas matemáticas usa el botón **∑ MathJax** arriba. Los bloques se pueden colapsar haciendo clic en su cabecera.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 · EXPORTAR  (rediseñado)
# ─────────────────────────────────────────────────────────────────────────────

# ── Helper: inyectar formulario en fichero LaTeX ─────────────────────────────
def _inject_formulario_tex(tex_str: str, formulario_name: str) -> str:
    pkg = "\\usepackage{pdfpages}"
    if pkg not in tex_str:
        tex_str = tex_str.replace("\\begin{document}", pkg + "\n\\begin{document}")
    inc = f"\n\\clearpage\n\\includepdf[pages=-]{{{formulario_name}}}\n"
    return tex_str.replace("\\end{document}", inc + "\\end{document}")


# ── Helper: ejecutar exportación completa en memoria ─────────────────────────
def _ejecutar_export(previa: bool = False):
    """Genera todos los archivos en memoria y los guarda en session_state['export_files'].
    previa=True: vista previa del PDF (mismos modelos que la exportación, pero sin marcar preguntas usadas,
    sin registrar el examen y sin historial)."""
    cfg          = st.session_state.get("exam_cfg", {})
    sel_actual   = get_sel_ids()
    nombre_arch  = cfg.get("file", f"Examen_{datetime.date.today()}")
    n_mod        = cfg.get("vers", 1)
    exp_word     = cfg.get("exp_word", True)
    exp_tex      = cfg.get("exp_tex",  True)

    # Construir el pool con datos FRESCOS de df_preguntas (para que datos/notas editados
    # después del Preview aparezcan), preservando el ORDEN de la cache si existe.
    df_dict = st.session_state.df_preguntas.set_index("ID_Pregunta").to_dict("index")
    cache   = st.session_state.get("cache_examen") or []
    if cache:
        # Preservar orden de la cache pero releer campos de df_preguntas
        pool = []
        for cached_item in cache:
            pid = cached_item.get("ID_Pregunta", "")
            if pid in df_dict:
                item = dict(df_dict[pid]); item["ID_Pregunta"] = pid
                # Mantener campos calculados por generar_master_examen (opciones_visibles, etc.)
                for _k in ("opciones_visibles",):
                    if _k in cached_item:
                        item[_k] = cached_item[_k]
                pool.append(item)
    else:
        pool = []
        for pid in sel_actual:
            if pid in df_dict:
                item = dict(df_dict[pid]); item["ID_Pregunta"] = pid
                pool.append(item)

    for _p in pool:      # línea de información de la versión con soluciones (nombres legibles)
        _partes_i = []
        if cfg.get("sol_info_bloque"):
            _partes_i.append(nombre_bloque(str(_p.get("bloque", ""))))
        if cfg.get("sol_info_tema"):
            _partes_i.append(nombre_tema(str(_p.get("Tema", "")).removesuffix(".0")))
        if cfg.get("sol_info_dif"):
            _partes_i.append(str(_p.get("dificultad", "")))
        if cfg.get("sol_info_id"):
            _partes_i.append(str(_p.get("ID_Pregunta", "")))
        _p["_info_sol"] = " · ".join(x for x in _partes_i if x)
    cfg_export = {
        "preambulo_extra":   cfg.get("preambulo_extra", ""),
        "titulo_asignatura": cfg.get("asig", ""),
        "tipo_examen":       cfg.get("tipo", ""),
        "entidad":           cfg.get("inst", ""),
        "fecha":             cfg.get("fecha", ""),
        "tiempo":            cfg.get("tiem", ""),
        "instr_gen":         cfg.get("ins",  ""),
        "info_fund":         cfg.get("h1",   ""),
        "info_test":         cfg.get("h2",   ""),
        "barajar_preguntas":   cfg.get("ord", "bloques") == "global",
        "barajar_por_bloques": cfg.get("ord", "bloques") == "bloques",
        "barajar_por_temas":   cfg.get("ord", "bloques") == "temas",
        "barajar_respuestas":  cfg.get("bar", True),
        "frases_anclaje_extra": cfg.get("anc_txt","") if cfg.get("anc_chk", True) else "",
        "sol_negrita": cfg.get("sol_bold",  False),
        "sol_color":   cfg.get("sol_color", "red"),
        "sol_ast":     cfg.get("sol_ast",  True),
        "fundamentales_data": [
            {
                "txt":            q["txt"],
                "modo":           q.get("modo", "markdown"),
                "pts":            q["pts"],
                "espacio":        q["espacio"],
                "criterios":      __import__("desarrollo_ui").criterios_export(q),
                "solucion_modelo": q.get("solucion_modelo", ""),
                "solucion_modo":  q.get("modo", "markdown"),
                "imagen_bytes":   q.get("imagen_bytes"),
                "imagen_name":    q.get("imagen_name", f"dev_img_{di+1}.png"),
                "imagen_pos":     q.get("imagen_pos", "debajo"),
                "datos_ids":      q.get("datos_ids", ""),
                "subapartados":   q.get("subapartados", []),
                "numeracion_apt": q.get("numeracion_apt", "abc"),
                "_tikz_png":      ([__import__("figuras").png(b_, cfg.get("preambulo_extra", ""))
                                    for b_ in __import__("figuras").bloques(q["txt"])] if exp_word else []),
            }
            for di, q in enumerate(st.session_state.get("dev_questions", []))
        ],
        # Constantes / Datos físicos
        "datos_df": lib.get_datos_df(st.session_state.get("excel_dfs", {})),
        # Estilo visual
        "color_scheme":     cfg.get("color_scheme", "azul"),
        "tipografia":       cfg.get("tipografia",   "cm"),
        "font_size":        cfg.get("font_size",    12),
        "linespread":       1.0,
        "espaciado":        cfg.get("espaciado", "normal"),
        "modo_compacto":    cfg.get("espaciado", "normal") == "compacto",  # compat
        "margenes":         cfg.get("margenes", "normal"),
        "cabecera_compacta": cfg.get("cabecera_compacta", False),
        "sin_recuadro":     cfg.get("sin_recuadro", False),
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
        "sol_info_id":     cfg.get("sol_info_id",     False),
        "pautado":         cfg.get("pautado", "libre"),
        # Solucionario
        "incluir_solucionario": cfg.get("incluir_solucionario", False),
        "titulo_solucionario":  cfg.get("titulo_solucionario", "Solucionario"),
        # Caja de calificación
        "notacal_dev":   cfg.get("notacal_dev",   False),
        "notacal_test":  cfg.get("notacal_test",  False),
        "notacal_final": cfg.get("notacal_final", False),
        # Estilo bloque solución desarrollo
        "estilo_sol":    cfg.get("estilo_sol", "caja"),
    }
    tpl_word_bytes = st.session_state.get("_tpl_word_bytes")
    tpl_tex_bytes  = st.session_state.get("_tpl_tex_bytes")
    if tpl_tex_bytes:
        cfg_export["plantilla_tex_bytes"] = tpl_tex_bytes

    # ── Modo partes ────────────────────────────────────────────────────────────
    partes_modo = cfg.get("partes_modo", "completo")
    _fund_data  = cfg_export.get("fundamentales_data", [])

    if partes_modo == "solo_test":
        cfg_export["fundamentales_data"] = []
        _runs = [("", pool, cfg_export)]
    elif partes_modo == "solo_dev":
        _runs = [("", [], cfg_export)]
    elif partes_modo == "separados":
        _cfg_test = dict(cfg_export); _cfg_test["fundamentales_data"] = []
        _cfg_dev  = dict(cfg_export); _cfg_dev["dos_por_hoja"] = False  # 2-por-hoja solo para test
        _runs = [("_TEST", pool, _cfg_test), ("_DEV", [], _cfg_dev)]
    else:
        _runs = [("", pool, cfg_export)]

    ef = {"nombre": nombre_arch, "_zip_all": {}, "_fecha": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")}
    _firma_mod = E.firma_modelos([p.get("ID_Pregunta") for p in pool], cfg)
    _ef_ant = st.session_state.get("export_files") or {}
    ef["_snap"] = E.instantanea([p.get("ID_Pregunta") for p in pool], cfg)

    for _sfx, _pool, _cfg in _runs:
        _arch = nombre_arch + _sfx
        _master = (E.master_bloqueado(_pool) or E.master_fijado(_pool, _firma_mod)
                   or lib.generar_master_examen(_pool, n_mod, _cfg))

        if not _sfx or (partes_modo == "separados" and _sfx == "_TEST"):
            ef["_master"] = _master   # el mismo que da las claves del CSV
        if not _sfx:  # solo primer run para CSV (no aplica en separados o aplica al test)
            csv_data = lib.exportar_csv_bytes(_master, _arch)
            ef["csv_claves"] = csv_data["claves"]
            ef["csv_meta"]   = csv_data["metadata"]
            ef["_zip_all"][f"{_arch}_CLAVES.csv"]   = csv_data["claves"]
            ef["_zip_all"][f"{_arch}_METADATA.csv"] = csv_data["metadata"]
        elif partes_modo == "separados" and _sfx == "_TEST":
            csv_data = lib.exportar_csv_bytes(_master, _arch)
            ef["csv_claves"] = csv_data["claves"]
            ef["csv_meta"]   = csv_data["metadata"]
            ef["_zip_all"][f"{_arch}_CLAVES.csv"]   = csv_data["claves"]
            ef["_zip_all"][f"{_arch}_METADATA.csv"] = csv_data["metadata"]

        if exp_word:
            _wex = lib.rellenar_plantilla_word_bytes(_master, _arch, _cfg, tpl_bytes=tpl_word_bytes, modo_solucion=False)
            _wsol = lib.rellenar_plantilla_word_bytes(_master, _arch, _cfg, tpl_bytes=tpl_word_bytes, modo_solucion=True)
            for letra, data in _wex.items():
                ef["_zip_all"][f"{_arch}_MOD{letra}.docx"] = data
            for letra, data in _wsol.items():
                ef["_zip_all"][f"{_arch}_MOD{letra}_SOL.docx"] = data
            ef[f"word_exam{_sfx}"] = _wex   # "" | "_TEST" | "_DEV"
            ef[f"word_sol{_sfx}"]  = _wsol

        if exp_tex:
            _tex_ex  = lib.generar_latex_strings(_master, _arch, _cfg, modo_solucion=False)
            _tex_sol = lib.generar_latex_strings(_master, _arch, _cfg, modo_solucion=True)
            for letra, data in _tex_ex.items():
                ef["_zip_all"][f"{_arch}_MOD{letra}.tex"] = data
            for letra, data in _tex_sol.items():
                ef["_zip_all"][f"{_arch}_MOD{letra}_SOL.tex"] = data
            sty_bytes = lib._generar_sty(_cfg)
            if sty_bytes:
                ef["_zip_all"]["estilo_examen_moderno_v2.sty"] = sty_bytes
            _logo_p = st.session_state.get("_logo_path", "")
            if _logo_p and os.path.isfile(_logo_p):
                import os as _os
                with open(_logo_p, "rb") as _lf:
                    ef["_zip_all"][_os.path.basename(_logo_p)] = _lf.read()
            _form_bytes_e = st.session_state.get("_formulario_bytes")
            _form_name_e  = st.session_state.get("_formulario_name", "formulario.pdf")
            if _form_bytes_e and cfg.get("incl_formulario", False):
                _tex_ex  = {k: _inject_formulario_tex(v, _form_name_e) for k, v in _tex_ex.items()}
                _tex_sol = {k: _inject_formulario_tex(v, _form_name_e) for k, v in _tex_sol.items()}
                # Actualizar _zip_all con las versiones inyectadas
                for _l, _d in _tex_ex.items():
                    ef["_zip_all"][f"{_arch}_MOD{_l}.tex"] = _d
                for _l, _d in _tex_sol.items():
                    ef["_zip_all"][f"{_arch}_MOD{_l}_SOL.tex"] = _d
            ef[f"latex_exam{_sfx}"] = _tex_ex   # "" | "_TEST" | "_DEV"
            ef[f"latex_sol{_sfx}"]  = _tex_sol

    # Incluir PDF del formulario en el ZIP si procede
    _form_bytes_final = st.session_state.get("_formulario_bytes")
    _form_name_final  = st.session_state.get("_formulario_name", "formulario.pdf")
    if _form_bytes_final and cfg.get("incl_formulario", False):
        ef["_zip_all"][_form_name_final] = _form_bytes_final
        ef["formulario_bytes"] = _form_bytes_final
        ef["formulario_name"]  = _form_name_final

    # usar primer master para referencias internas
    master = ef.get("_master") or lib.generar_master_examen(   # el mismo que dio las claves (también para la versión adaptada)
        pool if partes_modo not in ("solo_dev",) else [],
        n_mod, cfg_export
    )

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
            "titulo":        cfg.get("tit_rubrica", "Guía de Corrección"),
            "asig":          cfg.get("asig", ""),
            "inst":          cfg.get("inst", ""),
            "fecha":         cfg.get("fecha", ""),
            "rubrica_cajas": cfg.get("rubrica_cajas", False),
        }
        if cfg.get("fmt_rubrica_tex", True) and exp_tex:
            _rub_tex = lib.generar_rubrica_latex(
                [dict(q, criterios=__import__("desarrollo_ui").criterios_export(q)) for q in dev_qs_export], _rub_cfg)
            ef["_zip_all"][f"{nombre_arch}_RUBRICA.tex"] = _rub_tex
        if cfg.get("fmt_rubrica_word", True) and exp_word:
            _rub_word = lib.generar_rubrica_word_bytes(
                [dict(q, criterios=__import__("desarrollo_ui").criterios_export(q)) for q in dev_qs_export], _rub_cfg)
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

    if _ef_ant.get("_snap") == ef["_snap"]:      # mismos ajustes: se conservan los PDF ya compilados
        for _k, _v in (_ef_ant.get("_zip_all") or {}).items():
            if _k.endswith(".pdf") and _k not in ef["_zip_all"]:
                ef["_zip_all"][_k] = _v
    ef["zip_bytes"] = lib.generar_zip_bytes(ef["_zip_all"])
    _misma_clave = (st.session_state.get("exp_fix") or {}).get("firma") == _firma_mod
    if not E.bloqueado():
        E.fijar(ef.get("_master") or [], _firma_mod, previa=previa)
    if previa:
        ef["_previa"] = True
        if _ef_ant.get("_definitivo") and _misma_clave:     # solo cambió el aspecto: sigue siendo el definitivo
            ef["_definitivo"], ef["_n_usadas"] = _ef_ant["_definitivo"], _ef_ant.get("_n_usadas", 0)
        st.session_state["export_files"] = ef
        return
    ef["_definitivo"] = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    ef["_n_usadas"] = len(pool)

    # Marcar preguntas como usadas en la DB (con la fecha del examen; todas las del examen, no solo las fijas)
    hoy = E.fecha_iso(cfg.get("fecha", ""))
    sel_actual = [p.get("ID_Pregunta") for p in pool] or sel_actual
    dfs = st.session_state.excel_dfs
    for bloque_name, df_sheet in dfs.items():
        if bloque_name in lib.CFG_SHEETS:   # solo hojas de preguntas (no análisis, recetas ni banco de desarrollo)
            continue
        head    = [str(h).lower().strip() for h in df_sheet.columns]
        idx_id  = next((i for i, h in enumerate(head) if "id_preg" in h or h == "id"), -1)
        idx_usa = next((i for i, h in enumerate(head) if "usada" in h or "fecha" in h), -1)
        if idx_id == -1 or idx_usa == -1: continue
        id_col  = df_sheet.columns[idx_id]
        usa_col = df_sheet.columns[idx_usa]
        mask = df_sheet[id_col].astype(str).isin([str(pid) for pid in sel_actual])
        df_sheet.loc[mask, usa_col] = hoy
    reload_db()
    try:   # las preguntas de desarrollo del banco también quedan marcadas como usadas
        __import__("desarrollo_ui").marcar_usadas(
            [q.get("banco_id") for q in st.session_state.get("dev_questions", []) if q.get("banco_id")], hoy)
    except Exception:
        pass

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

    # Registro del examen para el análisis de ítems (claves, posiciones y orden de opciones por
    # modelo; ningún dato de alumnos). Mismo nombre de archivo → se actualiza el registro.
    _mreg = ef.get("_master") or []
    if _mreg and _mreg[0]["preguntas"]:
        try:
            import analisis_lib as _A
            _fila = _A.registro_desde_master(_mreg, nombre_arch, convocatoria=cfg.get("tipo", ""),
                                             fecha=E.fecha_iso(cfg.get("fecha", "")))
            _fila.update({"Contenido": E._json(E.contenido()), "Usuario": E.usuario()})
            _A.upsert_examen(st.session_state.excel_dfs, _fila)
            E.borrar_borrador()
            guardar_hojas([_A.SHEET_EXAMENES])
            ef["_registrado"] = nombre_arch
        except Exception as _e:
            st.session_state.setdefault("_sync_errors", []).append(
                f"⚠️ No se pudo registrar el examen para el análisis: {_e}")


@st.dialog("Exportar examen", width="small")
def _dialog_confirmar_export(previa: bool = False):
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
    _exs = E.examenes(incluir_borradores=False)
    _nom = cfg.get("file", "")
    _lk = st.session_state.get("exam_lock") or {}
    _dup = _nom in set(_exs["ID_Examen"]) and not (E.bloqueado() and _lk.get("ID_Examen") == _nom)
    _ok_dup = True
    if _dup:
        st.warning(f"Ya existe un examen llamado «{_nom}». Si exportas, se reemplaza su registro "
                   "(el análisis guardado se conserva). Para no reemplazarlo, cambia el nombre en Exportar.")
        _ok_dup = st.checkbox("Reemplazarlo", key="dlg_dup_ok")
    _est_m, _fx = E.estado_modelos(cfg)
    _ok_mod = True
    if E.bloqueado():
        st.caption("Examen bloqueado: se exportan exactamente los mismos modelos y claves.")
    elif _est_m == "vigente":
        st.success(f"Se usan los mismos modelos y claves fijados el {_fx.get('fecha', '')}: "
                   "lo que ya hayas impreso sigue valiendo.")
    elif _est_m == "cambiado":
        st.warning(f"Has cambiado las preguntas o el barajado desde el {_fx.get('fecha', '')}. Se generarán "
                   "**modelos nuevos**: las claves y los archivos anteriores dejarán de valer"
                   + (" (la exportación anterior queda en Exámenes como «sustituida»)." if _fx.get("exportado") else "."))
        _ok_mod = st.checkbox("Entiendo: tendré que descargar de nuevo todos los archivos", key="dlg_mod_ok")
    else:
        st.caption("Al " + ("ver la vista previa" if previa else "exportar") + " se fijan los modelos y las claves: "
                   "si vuelves a exportar saldrán exactamente iguales.")
    if previa:
        st.caption("Preparar no registra el examen ni marca preguntas como usadas: eso se hace al darlo por definitivo.")
    else:
        st.caption("Al darlo por definitivo, el examen queda registrado en Exámenes (con sus claves, para analizarlo) "
                   f"y sus preguntas se marcan como usadas con la fecha del examen ({cfg.get('fecha', '')}).")
    st.markdown("---")
    c1, c2 = st.columns(2)
    if c1.button("Preparar" if previa else "Dar por definitivo", type="primary", use_container_width=True, key="dlg_ok",
                 disabled=not (_ok_dup and _ok_mod)):
        with st.spinner("Generando archivos…"):
            try:
                if _est_m == "cambiado" and not E.bloqueado():
                    E.descartar_fijado(cfg.get("file", "") if _fx.get("exportado") else "")
                _ejecutar_export(previa=previa)
                st.session_state["_exp_ir_dl"] = True
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback; st.code(traceback.format_exc())
                return
        st.rerun()
    if c2.button("Cancelar", use_container_width=True, key="dlg_cancel"):
        st.rerun()


@st.dialog("Generar modelos nuevos", width="small")
def _dialog_modelos_nuevos():
    _est_m, _fx = E.estado_modelos()
    st.markdown("Se volverá a barajar el orden de las preguntas y de las opciones. "
                f"**Las claves y los archivos de la exportación del {_fx.get('fecha', '')} dejarán de valer**: si ya "
                "imprimiste o repartiste ese examen, corrígelo con aquella clave, no con la nueva.")
    if _fx.get("exportado"):
        st.info("La exportación anterior se conserva en Exámenes como «sustituida», con sus claves, por si la necesitas.")
    ok = st.checkbox("Entiendo que tendré que descargar de nuevo todos los archivos", key="dlg_nuevos_ok")
    c1, c2 = st.columns(2)
    if c1.button("Generar modelos nuevos", type="primary", key="dlg_nuevos_go", disabled=not ok, use_container_width=True):
        E.descartar_fijado(st.session_state.get("exam_cfg", {}).get("file", "") if _fx.get("exportado") else "")
        notify("Modelos anteriores descartados: pulsa «Exportar examen» para generar los nuevos.")
        st.rerun()
    if c2.button("Cancelar", key="dlg_nuevos_no", use_container_width=True):
        st.rerun()


def _preparar():
    _est, _ = E.estado_modelos()
    if _est == "cambiado" and not E.bloqueado():
        _dialog_confirmar_export(previa=True)        # cambian las claves: pide confirmación
        return
    with st.spinner("Preparando los archivos…"):
        _ejecutar_export(previa=True)
    notify("✅ Archivos preparados. Puedes ver el PDF debajo.")
    st.rerun()


def _paso_preparar(n_total, n_recipe):
    """Exportar (Bitácora) · ① Preparar archivos, con los cambios desde la última preparación."""
    ss = st.session_state
    ef = ss.get("export_files")
    with st.container(border=True, key="exp_paso1"):
        st.markdown("<div class='exp-paso'>① Preparar archivos</div>", unsafe_allow_html=True)
        if n_total == 0:
            st.caption("Elige preguntas en Selección (o pon una receta) para poder prepararlo.")
            return
        if n_recipe > 0 and not ss.get("cache_examen"):
            st.caption("Tienes una receta: pulsa «Generar» en Generar para fijar las preguntas antes de prepararlo.")
            return
        if E.bloqueado():
            st.caption("Examen abierto bloqueado: se preparan sus modelos y claves exactos.")
        if not ef:
            st.caption("Baraja una vez y fija los modelos y las claves, y genera todos los archivos. No registra nada "
                       "todavía: puedes verlo y cambiarlo cuantas veces quieras.")
            if st.button("Preparar archivos", type="primary", key="btn_preparar", use_container_width=True):
                _preparar()
            return
        st.markdown(f"<div class='exp-st'>Preparado el <b>{ef.get('_fecha', '')}</b>"
                    + (f" · <b style='color:var(--ok)'>definitivo</b> el {ef['_definitivo']}" if ef.get("_definitivo") else "")
                    + "</div>", unsafe_allow_html=True)
        asp, cla = E.diferencias(ef.get("_snap"), E.ids_examen(), ss.get("exam_cfg") or {})
        if asp or cla:
            with st.container(key="exp_cambios_" + ("cla" if cla else "asp")):
                st.markdown(f"**Has cambiado cosas desde la preparación del {ef.get('_fecha', '')}**"
                            + "".join(f"<div class='exp-ch'>· {x}</div>" for x in cla + asp)
                            + ("<div class='exp-cla'>✗ <b>Cambian las claves</b>: los archivos anteriores dejan de valer"
                               + (" (el examen ya era definitivo: el anterior quedará como «sustituido»)" if ef.get("_definitivo") else "")
                               + ".</div>" if cla else
                               "<div class='exp-asp'>✓ Las claves no cambian (mismas preguntas y mismo barajado).</div>"),
                            unsafe_allow_html=True)
                if st.button("Actualizar archivos", type="primary", key="btn_actualizar", use_container_width=True):
                    _preparar()
        else:
            st.caption("✓ Los archivos están al día con tus ajustes.")
        if not E.bloqueado() and st.button("Generar modelos nuevos", key="btn_modelos_nuevos", type="tertiary",
                                           help="Otro barajado con las mismas preguntas (cambian las claves)."):
            _dialog_modelos_nuevos()


def _paso_definitivo(ef):
    """Exportar (Bitácora) · ③ Dar por definitivo: registra el examen y marca las preguntas como usadas."""
    ss = st.session_state
    st.divider()
    if ef.get("_definitivo"):
        st.success(f"Definitivo desde el {ef['_definitivo']}: registrado en Exámenes y {ef.get('_n_usadas', 0)} preguntas "
                   f"marcadas como usadas con la fecha del examen.")
        return
    if ss.get("_dl_hecho"):
        st.warning("Has descargado los archivos. Si los vas a imprimir, dalos por definitivos para que el examen "
                   "quede registrado (y se pueda analizar después).")
    if st.button("Dar por definitivo", type="primary", key="btn_definitivo", use_container_width=True):
        _dialog_confirmar_export(previa=False)
    st.caption("Hazlo cuando lo vayas a imprimir: registra el examen en Exámenes con sus claves y marca sus preguntas "
               "como usadas. Antes de eso nada se guarda en la base de datos.")


_SEC_ABIERTAS = {"Datos del examen", "Aspecto general", "Hoja de respuestas", "Presets de configuración"}


def _seg(donde, etiqueta: str, opciones: dict, key: str, actual):
    """Selector segmentado (pocas opciones); si se deselecciona, mantiene el valor actual."""
    if key in st.session_state and st.session_state[key] not in opciones:
        st.session_state.pop(key)
    v = donde.segmented_control(etiqueta, list(opciones), format_func=lambda x: opciones[x], key=key,
                                default=actual if actual in opciones else next(iter(opciones)))
    return actual if v is None else v


def _sec_exp(titulo: str, abierto: bool = True):
    """Bitácora: desplegable con aspecto de tarjeta (abierto solo el primero de cada sección); Clásico: como antes."""
    if get_estilo() == "bitacora":
        k = re.sub(r"\W+", "_", titulo.lower()).strip("_")[:30]
        return st.container(key=f"expsec_{k}").expander(titulo, expanded=titulo in _SEC_ABIERTAS)
    return st.expander(titulo, expanded=abierto)


_SOL_COLOR_CSS = {
    "red": "#c0392b", "green": "#1e8a1e", "blue": "#0a4e8a",
    "orange": "#cc6600", "purple": "#6a0dad",
}


def _build_exam_preview_html(cfg, pool_p, dev_qs, show_sol=False, modelo="A"):
    """Genera HTML que imita el aspecto del examen impreso."""
    _sol_css_color = _SOL_COLOR_CSS.get(cfg.get("sol_color", ""), "#1a7a2e")
    html = []
    html.append(f"""<style>
.ep-wrap {{ max-width:760px; margin:0 auto; font-family:'Times New Roman',serif; font-size:11pt; color:var(--text, #111); background:var(--card, #fff); padding:24px 32px; border:1px solid var(--ui-border, #ccc); border-radius:6px; }}
.ep-header {{ text-align:center; border-bottom:2px solid var(--border2, #333); padding-bottom:10px; margin-bottom:14px; }}
.ep-inst {{ font-size:12pt; font-weight:bold; }}
.ep-title {{ font-size:15pt; font-weight:bold; margin:4px 0; }}
.ep-subtitle {{ font-size:12pt; }}
.ep-meta {{ font-size:9.5pt; color:var(--text2, #444); margin-top:4px; }}
.ep-scoring {{ font-size:9.5pt; color:var(--primary, #1a5276); background:var(--primary-soft, #eaf4fb); border:1px solid var(--border2, #aed6f1); border-radius:4px; padding:3px 10px; margin-top:6px; display:inline-block; }}
.ep-campos {{ border-top:1px solid var(--ui-border, #aaa); padding-top:10px; margin:12px 0 6px 0; display:flex; flex-wrap:wrap; gap:12px 24px; align-items:flex-end; font-size:11pt; }}
.ep-campo {{ display:flex; align-items:baseline; gap:4px; }}
.ep-campo b {{ white-space:nowrap; }}
.ep-campo .ep-underline {{ min-width:80px; flex:1; border-bottom:1px solid var(--border2, #555); min-height:18px; display:inline-block; }}
.ep-campo .ep-underline-xs {{ width:100px; border-bottom:1px solid var(--border2, #555); min-height:18px; display:inline-block; }}
.ep-instr {{ background:var(--card2, #f7f7f7); border:1px solid var(--ui-border, #bbb); border-radius:4px; padding:8px 12px; font-size:10pt; font-style:italic; margin:10px 0 14px 0; }}
.ep-part {{ font-size:12pt; font-weight:bold; text-align:center; background:var(--chip, #2c3e50); color:var(--chip-ink, #fff); padding:5px 12px; margin:16px 0 8px 0; border-radius:4px; }}
.ep-part-info {{ font-size:10pt; font-style:italic; color:var(--text2, #444); margin-bottom:8px; }}
.ep-bloque-sep {{ font-size:10pt; font-weight:bold; color:var(--text, #2c3e50); border-bottom:1px solid var(--ui-border, #adb5bd); margin:10px 0 4px 0; padding-bottom:2px; }}
.ep-q {{ margin-bottom:10px; page-break-inside:avoid; }}
.ep-q-stem {{ margin:0 0 5px 0; }}
.ep-q-num {{ font-weight:bold; }}
.ep-options {{ margin:3px 0 3px 22px; font-size:10.5pt; }}
.ep-opt {{ display:block; padding:1px 4px; }}
.ep-opt.correct {{ font-weight:bold; color:{_sol_css_color}; }}
.ep-space-box {{ border:1px solid var(--ui-border, #999); margin:5px 0 12px 22px; border-radius:3px; background:var(--card2, #fafafa); }}
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
                f'style="max-width:85%;border:1px solid var(--ui-border, #ccc);border-radius:3px"></div>'
            ) if img_bytes else ""

            html.append('<div class="ep-q">')
            if img_bytes and img_pos == 'encima':
                html.append(_img_html)
            html.append(
                f'<div class="ep-q-stem">'
                f'<span class="ep-q-num">{i+1}.</span>'
                f' <em style="font-size:9.5pt;color:var(--text2, #555)">({pts} pt{"s" if float(pts) != 1 else ""})</em>'
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
.sol-wrap {{ max-width:760px; margin:0 auto; font-family:'Times New Roman',serif; font-size:11pt; color:var(--text, #111); background:var(--card, #fff); padding:24px 32px; border:1px solid var(--ui-border, #ccc); border-radius:6px; }}
.sol-title {{ font-size:14pt; font-weight:bold; text-align:center; background:var(--chip, #2c3e50); color:var(--chip-ink, #fff); padding:8px 16px; border-radius:6px; margin-bottom:18px; }}
.sol-q {{ border:1px solid var(--ui-border, #dee2e6); border-radius:6px; padding:12px 16px; margin-bottom:14px; page-break-inside:avoid; }}
.sol-q-num {{ font-weight:bold; color:var(--text, #2c3e50); font-size:10.5pt; }}
.sol-stem {{ margin:4px 0 8px 0; font-size:10.5pt; color:var(--text, #333); }}
.sol-resp {{ font-size:10pt; font-weight:bold; color:{_sol_css_color}; margin-bottom:6px; }}
.sol-text {{ background:var(--card2, #f8f9fa); border-left:3px solid {_sol_css_color}; padding:8px 12px; font-size:10.5pt; line-height:1.6; border-radius:0 4px 4px 0; }}
.sol-no-sol {{ font-size:9.5pt; color:var(--faint, #aaa); font-style:italic; }}
.sol-dev {{ background:var(--note-bg, #fff8e1); border:1px solid var(--ui-warn, #f0c040); border-radius:6px; padding:12px 16px; margin-bottom:14px; }}
.sol-dev-title {{ font-size:10.5pt; font-weight:bold; color:var(--note-text, #7a5500); margin-bottom:6px; }}
</style>"""]
    html.append('<div class="sol-wrap">')
    tit_sol = cfg.get("titulo_solucionario", "Solucionario")
    html.append(f'<div class="sol-title">📖 {tit_sol}</div>')

    # ── Preguntas de desarrollo ──────────────────────────────────────────────
    if dev_qs:
        html.append('<div class="sol-q" style="border-color:var(--ui-warn, #f0c040)">')
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
        st.warning("No hay preguntas seleccionadas. Ve a **Generar** y pulsa **🎲 Generar** primero.")
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
    """Renderiza PDF con PDF.js (canvas). Funciona en iframes sandboxed de Streamlit;
    no depende del visor nativo del navegador ni de blob: URLs en iframes anidados."""
    import base64 as _b64
    _b64_str = _b64.b64encode(pdf_bytes).decode()
    stcomponents.html(f"""
<div id="pdf-container"
     style="background:#666;padding:8px;overflow-y:auto;height:{height}px;box-sizing:border-box">
  <p id="pdf-loading" style="color:#fff;text-align:center;margin-top:40px;font-family:sans-serif">
    Cargando PDF…
  </p>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<script>
(function() {{
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

  var b64 = "{_b64_str}";
  var bin = atob(b64);
  var arr = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);

  var container = document.getElementById('pdf-container');
  var loading   = document.getElementById('pdf-loading');

  pdfjsLib.getDocument({{data: arr}}).promise.then(function(pdf) {{
    loading.remove();
    var total = pdf.numPages;
    function renderPage(num) {{
      pdf.getPage(num).then(function(page) {{
        var contW = container.clientWidth - 16;   // 8px padding cada lado
        var vp0   = page.getViewport({{scale: 1}});
        var scale  = contW / vp0.width;
        var vp     = page.getViewport({{scale: scale}});
        var canvas = document.createElement('canvas');
        canvas.width  = vp.width;
        canvas.height = vp.height;
        canvas.style.display    = 'block';
        canvas.style.margin     = '0 auto 8px';
        canvas.style.background = '#fff';
        canvas.style.boxShadow  = '0 1px 4px rgba(0,0,0,.5)';
        container.appendChild(canvas);
        page.render({{canvasContext: canvas.getContext('2d'), viewport: vp}}).promise.then(function() {{
          if (num < total) renderPage(num + 1);
        }});
      }});
    }}
    renderPage(1);
  }}).catch(function(err) {{
    loading.textContent = 'Error cargando PDF: ' + err.message;
    loading.style.color = '#f88';
  }});
}})();
</script>
""", height=height + 20, scrolling=False)


@st.dialog("🔨 Compilando PDF…", width="large")
def _clave_modelo(ef, letra) -> str:
    m = next((x for x in (ef or {}).get("_master") or [] if x["letra_version"] == letra), None)
    return "".join(p.get("letra_final", "?") for p in m["preguntas"]) if m else ""


def _comprobar_pdf(pdf_bytes: bytes, clave: str) -> tuple:
    """Lee la correcta marcada en el PDF de soluciones y la compara con la clave. (ok, mensaje)."""
    try:
        import importar_examen as _IMP
        _v, qs = _IMP._pdf(pdf_bytes)
    except Exception as e:
        return False, f"No se ha podido comprobar el PDF automáticamente: {e}"
    marc = "".join(q.get("ok") or "?" for q in qs if not q.get("bis"))
    if len(marc) != len(clave) or marc.count("?") > len(clave) // 2:
        return True, "Comprobación automática no disponible para este PDF (no se reconocen bien las preguntas)."
    mal = [f"{j + 1} (PDF {a} · clave {b})" for j, (a, b) in enumerate(zip(marc, clave)) if a != b]
    if not mal:
        return True, f"✓ La correcta marcada en el PDF coincide con la clave en las {len(clave)} preguntas."
    return False, f"✗ La correcta marcada en el PDF NO coincide con la clave en: {', '.join(mal)}. No lo uses sin revisarlo."


def _compilar_todos(ef):
    """Compila todos los modelos (alumno y soluciones) de test/examen completo, comprueba y los añade al ZIP."""
    sty = ef["_zip_all"].get("estilo_examen_moderno_v2.sty", b"")
    imgs = {k: v for k, v in ef["_zip_all"].items() if k.startswith("dev_img_")}
    if ef.get("formulario_name") and ef.get("formulario_bytes"):
        imgs[ef["formulario_name"]] = ef["formulario_bytes"]
    trabajos = []
    for sfx in ("", "_TEST", "_DEV"):
        for letra in (ef.get(f"latex_exam{sfx}") or {}):
            trabajos.append((sfx, letra, False))
            if ef.get(f"latex_sol{sfx}"):
                trabajos.append((sfx, letra, True))
    prog = st.progress(0, text="Compilando…")
    errores, avisos = [], []
    for k, (sfx, letra, sol) in enumerate(trabajos):
        nombre = f"{ef.get('nombre', 'examen')}{sfx}"
        pdf_name = f"{nombre}_MOD{letra}{'_SOL' if sol else ''}.pdf"
        prog.progress(k / max(1, len(trabajos)), text=f"Compilando {pdf_name}…")
        try:
            tex = (ef[f"latex_sol{sfx}"] if sol else ef[f"latex_exam{sfx}"])[letra]
            pdf = lib.compilar_latex_online(tex_str=tex, sty_bytes=sty, extra_files=imgs, nombre=nombre)
            ef["_zip_all"][pdf_name] = pdf
            if sol and sfx in ("", "_TEST"):
                ok, msg = _comprobar_pdf(pdf, _clave_modelo(ef, letra))
                if not ok:
                    avisos.append(f"{pdf_name}: {msg}")
        except Exception as e:
            errores.append(f"{pdf_name}: {e}")
    prog.progress(1.0, text="Hecho")
    ef["zip_bytes"] = lib.generar_zip_bytes(ef["_zip_all"])
    for a in avisos:
        st.error(a)
    for e in errores:
        st.warning(f"No se ha podido compilar {e}")
    if not errores and not avisos:
        notify(f"✅ {len(trabajos)} PDF compilados, comprobados y añadidos al ZIP.")
        st.rerun()


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
        if req.get("clave"):
            _chk = _comprobar_pdf(_pdf_bytes, req["clave"])
            (st.success if _chk[0] else st.error)(_chk[1])
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

    _bit_exp = get_estilo() == "bitacora"
    col_cfg, col_res = (st.columns([2.2, 1.15], gap="medium") if _bit_exp else st.columns([3, 2], gap="large"))
    _ef_top = st.session_state.get("export_files")
    _g_dl = None

    with (col_cfg.container(key="exp_secs") if _bit_exp else col_cfg):
        # Bitácora: secciones en pestañas verticales (tras exportar, «Descargas y PDF» primero); Clásico: una debajo de otra
        if _bit_exp:
            st.session_state.pop("_exp_ir_dl", None)
            _g_exam, _g_fmt, _g_extra, _g_tpl = st.tabs(["Examen", "Formato", "Documentos extra", "Plantillas y presets"])
        else:
            _g_exam = _g_fmt = _g_extra = _g_tpl = st.container()


        with _g_exam:
            # ── 1. Configuración del examen ────────────────────────────────────────
            with _sec_exp("Datos del examen", True):
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

                _sync_col, _ = st.columns([3, 3])
                if _sync_col.button("Rellenar desde Configuración", key="btn_sync_cfg",
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
                _auto_nom = E.nombre_auto(tipo, asig, fecha)
                if ("exp_file" not in st.session_state
                        or st.session_state["exp_file"] in ("", st.session_state.get("_exp_file_auto"))
                        or str(st.session_state["exp_file"]).startswith("Examen_")):
                    st.session_state["exp_file"] = cfg.get("file") if ("exp_file" not in st.session_state and cfg.get("file")
                                                                         and not str(cfg.get("file")).startswith("Examen_")) else _auto_nom
                st.session_state["_exp_file_auto"] = _auto_nom
                nombre_archivo = e6.text_input("Nombre del examen y de los archivos", key="exp_file",
                                               help="Se forma solo con el tipo, la asignatura y la fecha (DD-MM-AAAA); puedes cambiarlo.")
                _campos_def   = cfg.get("campos_alumno", ["nombre", "dni", "grupo", "firma"])
                _campos_map   = {"nombre": "Nombre", "dni": "DNI/NIU", "grupo": "Grupo", "firma": "Firma"}
                _campos_sel   = st.multiselect("Campos del alumno en el examen", list(_campos_map.keys()),
                                               default=_campos_def,
                                               format_func=lambda x: _campos_map[x], key="exp_campos")

        with _g_exam:
            # ── 2. Generación ─────────────────────────────────────────────────────
            with _sec_exp("Modelos y barajado", True):
                oc1, oc2, oc3 = st.columns(3)
                num_modelos = oc1.selectbox("Nº Modelos", [1, 2, 3, 4],
                                            index=max(0, cfg.get("vers", 1) - 1), key="exp_vers")
                _orden_opts = [("Aleatorio por Bloques","bloques"),("Aleatorio por Temas","temas"),
                               ("Aleatorio Global","global"),
                               ("Manual (selección)","manual"),("Sin barajar (ID)","secuencial")]
                _orden_idx  = next((i for i, (_, v) in enumerate(_orden_opts) if v == cfg.get("ord","bloques")), 0)
                orden_val   = oc2.selectbox("Orden preguntas", _orden_opts, index=_orden_idx,
                                            format_func=lambda x: x[0], key="exp_ord")
                orden       = orden_val[1]
                barajar     = oc3.checkbox("Barajar respuestas", value=cfg.get("bar", True), key="exp_bar")

                st.markdown("<div class='exp-sub'>Modo de partes</div>", unsafe_allow_html=True)
                _partes_opts = [
                    ("completo",    "Completo: desarrollo y test en un documento"),
                    ("solo_test",   "📋 Solo Test (MCQ)"),
                    ("solo_dev",    "Solo desarrollo"),
                    ("separados",   "Separados: desarrollo y test en dos documentos"),
                ]
                _partes_idx = next((i for i, (v, _) in enumerate(_partes_opts)
                                    if v == cfg.get("partes_modo", "separados")), 3)
                partes_modo = st.selectbox(
                    "Modo de partes", _partes_opts, index=_partes_idx,
                    format_func=lambda x: x[1], key="exp_partes_modo",
                    label_visibility="collapsed",
                )[0]
                if partes_modo == "separados":
                    st.caption("Dos documentos independientes: **_DEV** (desarrollo, A4) y **_TEST** (test, con opción 2-por-hoja).")
            campos_alumno = _campos_sel

        with _g_exam:
            # ── 4. Instrucciones y Cabeceras ──────────────────────────────────────
            with _sec_exp("Instrucciones y cabeceras de sección", True):
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

        with _g_extra:
            # ── 4b-bis. Hoja de respuestas ────────────────────────────────────────
            with _sec_exp("Hoja de respuestas", False):
                st.caption("Se añade como página final del examen (solo en versión alumno, no en soluciones).")
                hr1, hr2 = st.columns([1, 2])
                hoja_respuestas = hr1.checkbox("Generar hoja de respuestas",
                                               value=cfg.get("hoja_respuestas", False), key="exp_hoja_resp")

        with _g_extra:
            # ── 4b-ter. Solucionario ──────────────────────────────────────────────
            with _sec_exp("Solucionario (apéndice)", False):
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

        with _g_extra:
            # ── 4b-cuarto. Guía de corrección (rúbrica) ──────────────────────────
            _dev_qs_now  = st.session_state.get("dev_questions", [])
            _has_rubrica = any(q.get("criterios") or q.get("solucion_modelo","").strip()
                               for q in _dev_qs_now)
            with _sec_exp("Guía de corrección (rúbrica)", _has_rubrica):
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
                    rb1.caption("Define la rúbrica o la solución en la pestaña Desarrollo.")
                fmt_rubrica_word = rb2.checkbox("Formato Word (.docx)", value=cfg.get("fmt_rubrica_word", True),
                                                 key="exp_rubrica_word", disabled=not incl_rubrica)
                fmt_rubrica_tex  = rb3.checkbox("Formato LaTeX (.tex)",  value=cfg.get("fmt_rubrica_tex",  True),
                                                 key="exp_rubrica_tex",  disabled=not incl_rubrica)
                tit_rubrica = st.text_input("Título del documento",
                                            value=cfg.get("tit_rubrica", "Guía de Corrección"),
                                            key="exp_tit_rubrica", disabled=not incl_rubrica)
                rubrica_cajas = st.checkbox(
                    "☑ Cajas de puntuación para corrector (columna derecha en criterios)",
                    value=cfg.get("rubrica_cajas", False),
                    key="exp_rubrica_cajas",
                    disabled=not incl_rubrica,
                    help="Añade una caja [ ___ ] a la derecha de cada criterio para que el corrector anote la nota directamente en el PDF impreso.",
                )

        with _g_extra:
            # ── 4b-quinto. Formulario / Hoja de fórmulas ─────────────────────────
            _form_stored = bool(st.session_state.get("_formulario_bytes"))
            with _sec_exp("Formulario (hoja de fórmulas)", _form_stored):
                st.caption(
                    "Adjunta un PDF con el formulario de la asignatura. "
                    "Se incluirá como última página en los archivos LaTeX (requiere compilación local con pdfpages)."
                )
                _f1, _f2 = st.columns([2, 1])
                incl_formulario = _f1.checkbox(
                    "Incluir formulario al final del examen",
                    value=cfg.get("incl_formulario", _form_stored),
                    key="exp_incl_formulario",
                    disabled=not _form_stored,
                )
                _form_up = st.file_uploader(
                    "Subir PDF del formulario", type=["pdf"], key="formulario_upload",
                    help="El PDF se incluirá como página(s) extra al final del LaTeX con \\includepdf",
                )
                if _form_up:
                    if st.session_state.get("_formulario_upload_name") != _form_up.name:
                        st.session_state["_formulario_bytes"]      = _form_up.getvalue()
                        st.session_state["_formulario_name"]       = _form_up.name
                        st.session_state["_formulario_upload_name"] = _form_up.name
                        st.rerun()
                if _form_stored:
                    _f2.success(f"{st.session_state.get('_formulario_name','formulario.pdf')}")
                    if _f2.button("Quitar formulario", key="btn_del_formulario", use_container_width=True):
                        for _k in ("_formulario_bytes", "_formulario_name", "_formulario_upload_name"):
                            st.session_state.pop(_k, None)
                        st.rerun()
                else:
                    incl_formulario = False

        with _g_extra:
            # ── 4c-bis. Caja de calificación ──────────────────────────────────────
            _has_test_q = bool(sel_actual) or bool(st.session_state.get("auto_recipe"))
            _has_dev_q  = bool(st.session_state.get("dev_questions", []))
            with _sec_exp("Caja de calificación", False):
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
        with _g_exam:
            # ── 4c. Puntos y penalización ─────────────────────────────────────────
            with _sec_exp("Puntos y penalización", False):
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

        with _g_extra:
            # ── 4d. Versión adaptada ──────────────────────────────────────────────
            with _sec_exp("Versión adaptada", False):
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

        with _g_fmt:
            # ── Formato: aspecto general · cabecera y pie · preguntas · versión con soluciones · archivos ──
            with _sec_exp("Aspecto general", True):
                fa1, fa2 = st.columns([1.4, 1])
                color_scheme = _seg(fa1, "Esquema de color", {"azul": "Azul", "ucm": "Granate UCM", "byn": "Blanco y negro"},
                                    "exp_color_scheme", cfg.get("color_scheme", "azul"))
                _font_opts = {"cm": "Computer Modern (clásica de LaTeX)", "libertine": "Linux Libertine",
                              "palatino": "Palatino", "times": "Times", "helvet": "Helvetica",
                              "fira": "Fira Sans (sin remates, moderna)", "sourcesans": "Source Sans (sin remates, clara)"}
                _font_cur = cfg.get("tipografia", "cm") if cfg.get("tipografia", "cm") in _font_opts else "cm"
                tipografia = fa2.selectbox("Tipografía", list(_font_opts), index=list(_font_opts).index(_font_cur),
                                           format_func=_font_opts.get, key="exp_tipografia")
                fb1, fb3 = st.columns(2)
                fb2 = st
                font_size_val = _seg(fb1, "Tamaño de letra", {10: "10", 11: "11", 12: "12"}, "exp_font_size",
                                     int(cfg.get("font_size", 12)) if int(cfg.get("font_size", 12)) in (10, 11, 12) else 12)
                _esp_raw = cfg.get("espaciado", "compacto" if cfg.get("modo_compacto", False) else "normal")
                espaciado = _seg(fb2, "Espacio entre preguntas", {"normal": "Normal", "compacto": "Compacto",
                                                                   "muy_compacto": "Muy compacto"},
                                 "exp_espaciado", _esp_raw if _esp_raw in ("normal", "compacto", "muy_compacto") else "normal")
                margenes = _seg(fb3, "Márgenes", {"normal": "20 mm", "reducido": "15 mm", "minimo": "12 mm"},
                                "exp_margenes", cfg.get("margenes", "normal") if cfg.get("margenes") in ("normal", "reducido", "minimo") else "normal")

            with _sec_exp("Cabecera y pie de página", False):
                fc1, fc2 = st.columns([1.2, 1])
                cabecera_compacta = _seg(fc1, "Cabecera", {False: "Completa", True: "Compacta (una línea)"},
                                         "exp_cab_compacta", bool(cfg.get("cabecera_compacta", False)))
                sin_recuadro = not fc2.toggle("Recuadro para nombre, DNI y firma", value=not cfg.get("sin_recuadro", False),
                                              key="exp_recuadro")
                fd1, fd2 = st.columns([1, 1.6], vertical_alignment="bottom")
                fancyhdr_on = fd1.toggle("Encabezado y pie", value=cfg.get("fancyhdr_on", True), key="exp_fancyhdr",
                                         help="Asignatura y modelo arriba; número de página abajo.")
                footer_text = fd2.text_input("Texto en el pie", value=cfg.get("footer_text", ""), key="exp_footer",
                                             placeholder="ej.: Prohibido el uso del móvil", disabled=not fancyhdr_on)

            with _sec_exp("Preguntas", False):
                fe1, fe2 = st.columns([1.3, 1])
                _enum_opts = {"cuadrado": "Cuadrado", "circulo": "Círculo relleno", "vacio": "Círculo vacío",
                              "numero": "Número con punto", "nada": "Sin adorno"}
                estilo_num = fe1.selectbox("Numeración de las preguntas", list(_enum_opts),
                                           index=list(_enum_opts).index(cfg.get("estilo_num", "cuadrado"))
                                           if cfg.get("estilo_num", "cuadrado") in _enum_opts else 0,
                                           format_func=_enum_opts.get, key="exp_estilo_num")
                opciones_cols = _seg(fe2, "Opciones del test", {1: "En 1 columna", 2: "En 2 columnas"}, "exp_opcols_v2",
                                     2 if cfg.get("opciones_cols", 1) == 2 else 1)
                pautado = _seg(st, "Espacio de respuesta en desarrollo", {"libre": "En blanco", "lineas": "Con líneas",
                                                                           "cuadricula": "Con cuadrícula"},
                               "exp_pautado", cfg.get("pautado", "libre") if cfg.get("pautado") in ("libre", "lineas", "cuadricula") else "libre")
                st.markdown("<div class='exp-sub'>Anclaje de opciones</div>", unsafe_allow_html=True)
                ff1, ff2 = st.columns([1, 2], vertical_alignment="bottom")
                anclaje_auto = ff1.toggle("No barajar «todas/ninguna…»", value=cfg.get("anc_chk", True), key="exp_anc",
                                          help="Las opciones como «Todas las anteriores» se quedan en su sitio al barajar.")
                anclaje_extra = ff2.text_input("Otras frases que no se barajan (separadas por comas)",
                                               value=cfg.get("anc_txt", ""), key="exp_anc_txt", disabled=not anclaje_auto)
                if anclaje_auto:
                    _todas = (["todas las anteriores", "ninguna de las anteriores", "ambas son correctas", "son correctas", "son falsas"]
                              + [f.strip() for f in (anclaje_extra or "").split(",") if f.strip()])
                    st.caption("Se quedan en su sitio: " + " · ".join(f"«{f}»" for f in _todas[:5]) + ("…" if len(_todas) > 5 else ""))

            with _sec_exp("Versión con soluciones", False):
                st.markdown("<div class='exp-sub'>Cómo se marca la correcta</div>", unsafe_allow_html=True)
                fg1, fg2, fg3 = st.columns([1.3, 1, 1], vertical_alignment="bottom")
                _color_opts = {"": "Sin color", "red": "Rojo", "green": "Verde", "blue": "Azul", "orange": "Naranja", "purple": "Morado"}
                sol_color = fg1.selectbox("Color", list(_color_opts), index=list(_color_opts).index(cfg.get("sol_color", "red"))
                                          if cfg.get("sol_color", "red") in _color_opts else 1,
                                          format_func=_color_opts.get, key="exp_sol_color")
                sol_bold = fg2.toggle("Negrita", value=cfg.get("sol_bold", False), key="exp_sol_bold")
                sol_ast = fg3.toggle("Asterisco (*)", value=cfg.get("sol_ast", True), key="exp_sol_ast")
                estilo_sol = _seg(st, "Solución de las preguntas de desarrollo", {"caja": "En un recuadro", "linea": "Con línea lateral",
                                                                                  "texto": "Texto sin adorno"},
                                  "exp_estilo_sol", cfg.get("estilo_sol", "caja") if cfg.get("estilo_sol") in ("caja", "linea", "texto") else "caja")
                fh1, fh2 = st.columns([1, 1.6], vertical_alignment="bottom")
                watermark_sol = fh1.toggle("Marca de agua", value=cfg.get("watermark_sol", False), key="exp_wm_on")
                watermark_text = fh2.text_input("Texto de la marca", value=cfg.get("watermark_text", "SOLUCIONES"),
                                                key="exp_wm_text", disabled=not watermark_sol)
                st.markdown("<div class='exp-sub'>Debajo de cada pregunta (LaTeX)</div>", unsafe_allow_html=True)
                fi1, fi2, fi3, fi4 = st.columns(4)
                sol_info_bloque = fi1.checkbox("Bloque", value=cfg.get("sol_info_bloque", False), key="exp_sol_bloque")
                sol_info_tema = fi2.checkbox("Tema", value=cfg.get("sol_info_tema", False), key="exp_sol_tema")
                sol_info_dif = fi3.checkbox("Dificultad", value=cfg.get("sol_info_dif", False), key="exp_sol_dif")
                sol_info_id = fi4.checkbox("ID", value=cfg.get("sol_info_id", False), key="exp_sol_id")

            with _sec_exp("Archivos", False):
                fj1, fj2 = st.columns(2)
                exp_word = fj1.toggle("Word (.docx)", value=cfg.get("exp_word", True), key="exp_word")
                exp_tex = fj2.toggle("LaTeX (.tex) y PDF", value=cfg.get("exp_tex", True), key="exp_tex",
                                     help="Necesario para ver y compilar el PDF.")
                st.caption("La clave y los metadatos (CSV) se generan siempre.")
                dos_por_hoja = st.toggle(
                    "Dos páginas por hoja en el test (A5 en A4 apaisado)" if partes_modo == "separados"
                    else "Dos páginas por hoja (A5 en A4 apaisado)",
                    value=cfg.get("dos_por_hoja", False), key="exp_dos_por_hoja",
                    help="LaTeX: dos páginas A5 en una hoja A4 apaisada. Word: tamaño A5.")

        with _g_tpl:
            # ── 6. Plantillas ─────────────────────────────────────────────────────
            with _sec_exp("Paquetes LaTeX extra", False):
                preambulo_extra = st.text_area(
                    "Se añaden al preámbulo del LaTeX (por ejemplo, librerías de TikZ que no estén ya)",
                    value=cfg.get("preambulo_extra", ""), height=80, key="exp_preambulo",
                    placeholder="\\usetikzlibrary{3d}\n\\usepackage{siunitx}",
                    help="Ya se cargan solas las librerías habituales de TikZ (flechas, cálculo, posiciones, ángulos, "
                         "tramas…); pgfplots y circuitikz se añaden si alguna figura los usa.")
            with _sec_exp("Plantillas y logo", False):
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
                    if tc1.button("Quitar plantilla Word", key="btn_clear_tpl_word", use_container_width=True):
                        st.session_state.pop("_tpl_word_bytes", None)
                        st.session_state.pop("_tpl_word_name", None)
                        st.rerun()
                if tpl_tex_file:
                    st.session_state["_tpl_tex_bytes"] = tpl_tex_file.getvalue()
                    st.session_state["_tpl_tex_name"]  = tpl_tex_file.name
                    tc2.success(f"✅ {tpl_tex_file.name}")
                elif st.session_state.get("_tpl_tex_bytes"):
                    tc2.info(f"En memoria: {st.session_state.get('_tpl_tex_name','plantilla.tex')}")
                    if tc2.button("Quitar plantilla LaTeX", key="btn_clear_tpl_tex", use_container_width=True):
                        st.session_state.pop("_tpl_tex_bytes", None)
                        st.session_state.pop("_tpl_tex_name", None)
                        st.rerun()
                if logo_file:
                    import tempfile as _tmp
                    _logo_p = os.path.join(_tmp.gettempdir(), logo_file.name)
                    with open(_logo_p, "wb") as _f: _f.write(logo_file.read())
                    st.session_state["_logo_path"] = _logo_p
                    tc3.success(f"✅ {logo_file.name}")

        with _g_tpl:
            # ── 7. Presets ────────────────────────────────────────────────────────
            with _sec_exp("Presets de configuración", False):
                st.caption("Guarda y reutiliza configuraciones completas (instrucciones, datos, opciones).")
                from app_utils import cargar_presets as _cargar_presets
                _presets = _cargar_presets()
                pr1, pr2  = st.columns([3, 1])
                _sel_pr   = pr1.selectbox("Preset", ["— Seleccionar —"] + list(_presets.keys()), key="preset_sel")
                if pr2.button("Cargar", key="btn_load_preset", use_container_width=True) and _sel_pr != "— Seleccionar —":
                    st.session_state.exam_cfg = _presets.get(_sel_pr, {})
                    notify(f"Preset '{_sel_pr}' cargado.")
                    st.rerun()
                pr3, pr4  = st.columns([3, 1])
                _pr_name  = pr3.text_input("Nombre del preset", placeholder="Ej: FM I Ordinario 2026",
                                           key="preset_name_input", label_visibility="collapsed")
                if pr4.button("Guardar", key="btn_save_preset", use_container_width=True):
                    if _pr_name.strip():
                        save_preset(_pr_name.strip(), st.session_state.get("exam_cfg", {}))
                        notify(f"Preset '{_pr_name}' guardado.")
                        st.rerun()
                if _sel_pr != "— Seleccionar —":
                    if st.button(f"Eliminar «{_sel_pr}»", key="btn_del_preset"):
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
            "preambulo_extra": preambulo_extra,
            # Estilo visual
            "color_scheme": color_scheme, "tipografia": tipografia,
            "font_size": font_size_val,
            "espaciado": espaciado, "margenes": margenes,
            "cabecera_compacta": cabecera_compacta, "sin_recuadro": sin_recuadro,
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
            "sol_info_id":     sol_info_id,
            "pautado":         pautado,
            # Solucionario
            "incluir_solucionario": incluir_solucionario,
            "titulo_solucionario":  titulo_solucionario,
            # Guía de corrección (rúbrica)
            "incl_rubrica":     incl_rubrica,
            "fmt_rubrica_word": fmt_rubrica_word,
            "fmt_rubrica_tex":  fmt_rubrica_tex,
            "tit_rubrica":      tit_rubrica,
            "rubrica_cajas":    rubrica_cajas,
            # Formulario
            "incl_formulario":  incl_formulario,
            # Caja de calificación
            "notacal_dev":   notacal_dev,
            "notacal_test":  notacal_test,
            "notacal_final": notacal_final,
            # Estilo bloque solución desarrollo
            "estilo_sol": estilo_sol,
            # Modo partes
            "partes_modo": partes_modo,
        }

    # ── Panel derecho: Resumen + Botones + Descargas ───────────────────────────
    with (col_res.container(key="exp_res") if _bit_exp else col_res):
        if _bit_exp:
            _paso_preparar(n_total, n_recipe)

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

        _orden_labels = {"bloques": "Aleatorio por bloques", "temas": "Aleatorio por temas",
                         "global": "Aleatorio global",
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

        if _bit_exp:
            _partes_lbl = {"completo": "Completo", "solo_test": "Solo test",
                           "solo_dev": "Solo desarrollo", "separados": "Separados"}
            _n_test_lbl = (f"{n_pregs} + ~{n_recipe} auto" if (n_pregs and n_recipe)
                           else (f"~{n_recipe} auto" if n_recipe else str(n_pregs)))
            _items = [("Preguntas test", _n_test_lbl),
                      ("Desarrollo", f"{_n_dev} preguntas" if _n_dev else "—"),
                      ("Modelos", str(num_modelos)),
                      ("Partes", _partes_lbl.get(partes_modo, partes_modo)),
                      ("Formatos", " · ".join(["CSV"] + (["Word"] if exp_word else []) + (["LaTeX"] if exp_tex else []))),
                      ("Soluciones", _sol_str)]
            _sum_box = st.expander("Resumen de la configuración")
            _sum_box.markdown(
                f'<div class="card" style="margin-bottom:10px"><div class="sum-title">{asig or "—"} · {tipo or "—"}</div>'
                f'<div class="sum-meta">{inst or "—"} · {fecha or "—"} · {tiem or "—"}</div><div class="sum-grid">'
                + "".join(f'<div><div class="sum-l">{l}</div><div class="sum-v">{v}</div></div>' for l, v in _items)
                + "</div></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""<div style="background:linear-gradient(135deg,var(--chip, #1a252f),var(--chip, #2c3e50));color:var(--chip-ink, white);
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

        if _bit_exp:
            if st.button("Vista rápida (sin compilar)", key="btn_preview_exam", type="tertiary"):
                _dialog_preview_examen()
        else:
            _bx1, _bx2 = st.columns(2) if _bit_exp else (st, st)
            if _bx1.button("👁 Vista previa" if _bit_exp else "👁 Vista previa del examen", use_container_width=True,
                           key="btn_preview_exam", help="Vista rápida del examen (sin compilar)"):
                _dialog_preview_examen()
            if _bit_exp and _bx2.button("Vista previa del PDF", use_container_width=True, key="btn_preview_pdf",
                                        disabled=(n_total == 0 or (n_recipe > 0 and not st.session_state.get("cache_examen"))),
                                        help="Compila el PDF que quieras (parte, modelo, alumno o soluciones) con los modelos "
                                             "definitivos, sin exportar todavía."):
                _dialog_confirmar_export(previa=True)

            if not _bit_exp:
                st.markdown("<div style='margin:6px 0'></div>", unsafe_allow_html=True)

            _need_preview = n_recipe > 0 and not st.session_state.get("cache_examen")
            if (st if _bit_exp else _bx2).button("💾 Exportar examen" if _bit_exp else "💾 EXPORTAR EXAMEN", type="primary",
                           use_container_width=True,
                           key="btn_export_main", disabled=(n_total == 0 or _need_preview)):
                _dialog_confirmar_export()
            if n_total == 0:
                st.caption("⚠️ Ve a la pestaña **Selección** para elegir preguntas o configura un relleno automático.")
            elif _need_preview:
                st.caption("⚠️ Tienes una receta automática. Ve a **Generar** y pulsa **🎲 Generar** para fijar las preguntas antes de exportar.")


        # Bitácora: descargas y compilación en dos pestañas; Clásico: una debajo de otra
        if _bit_exp:   # ② Ver el PDF · ③ Descargar y dar por definitivo (en este orden)
            _ef_prep = st.session_state.get("export_files")
            _t_pdf = st.container(border=True, key="exp_paso2") if _ef_prep else st.container()
            _t_dl = st.container(border=True, key="exp_paso3") if _ef_prep else st.container()
            if _ef_prep:
                _t_pdf.markdown("<div class='exp-paso'>② Ver el PDF</div>", unsafe_allow_html=True)
                _t_dl.markdown("<div class='exp-paso'>③ Descargar y dar por definitivo</div>", unsafe_allow_html=True)
        else:
            _t_dl = _t_pdf = st.container()
        with _t_dl:
            pass
            # ── Botones de descarga (tras exportar) ───────────────────────────────
            ef = st.session_state.get("export_files")
            if ef and (_bit_exp or not ef.get("_previa")):
                _nef = ef.get("nombre", "examen")
                _fw, _fl, _fc = ("Word · ", "LaTeX · ", "CSV · ") if _bit_exp else ("", "", "")
                if not _bit_exp:
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
                    on_click=lambda: st.session_state.__setitem__("_dl_hecho", True),
                )
                if _bit_exp and any(ef.get(f"latex_exam{_s}") for _s in ("", "_TEST")):
                    _np = sum(1 for k in ef["_zip_all"] if k.endswith(".pdf"))
                    if st.button(f"Compilar todos los PDF y añadirlos al ZIP{f' · {_np} ya incluidos' if _np else ''}",
                                 key="btn_compile_all", use_container_width=True,
                                 help="Compila todos los modelos (alumno y soluciones) y comprueba que la correcta marcada "
                                      "coincide con la clave. Tarda unos segundos por PDF."):
                        _compilar_todos(ef)

                _sueltos = st.expander("Archivos sueltos (Word, LaTeX, CSV)") if _bit_exp else st.container()
                _sueltos.__enter__()
                _word_sfxs = [s for s in ("", "_TEST", "_DEV") if ef.get(f"word_exam{s}")]
                if _word_sfxs:
                    if not _bit_exp:
                        st.markdown("**Word:**")
                    _wlbl_map = {"": "", "_TEST": " · TEST", "_DEV": " · DEV"}
                    for _ws in _word_sfxs:
                        _wlbl = _wlbl_map[_ws]
                        _warch = _nef + _ws
                        _wc1, _wc2 = st.columns(2)
                        _wc1.download_button(f"📄 {_fw}Exámenes{_wlbl}",
                            data=lib.generar_zip_bytes({f"{_warch}_MOD{l}.docx": d for l, d in ef[f"word_exam{_ws}"].items()}),
                            file_name=f"{_warch}_word_examenes.zip", mime="application/zip",
                            use_container_width=True, key=f"dl_word_exam{_ws}")
                        _wc2.download_button(f"📄 {_fw}Soluciones{_wlbl}",
                            data=lib.generar_zip_bytes({f"{_warch}_MOD{l}_SOL.docx": d for l, d in ef[f"word_sol{_ws}"].items()}),
                            file_name=f"{_warch}_word_soluciones.zip", mime="application/zip",
                            use_container_width=True, key=f"dl_word_sol{_ws}")
                    if ef.get("word_adapt"):
                        st.download_button("♿ Adaptada (Word)",
                            data=lib.generar_zip_bytes({f"{_nef}_MOD{l}_ADAPT.docx": d for l, d in ef["word_adapt"].items()}),
                            file_name=f"{_nef}_word_adaptada.zip", mime="application/zip",
                            use_container_width=True, key="dl_word_adapt")

                _latex_sfxs = [s for s in ("", "_TEST", "_DEV") if ef.get(f"latex_exam{s}")]
                if _latex_sfxs:
                    if not _bit_exp:
                        st.markdown("**LaTeX:**")
                    _llbl_map = {"": "", "_TEST": " · TEST", "_DEV": " · DEV"}
                    for _ls in _latex_sfxs:
                        _llbl = _llbl_map[_ls]
                        _larch = _nef + _ls
                        _lc1, _lc2 = st.columns(2)
                        _lc1.download_button(f"📑 {_fl}Exámenes{_llbl}",
                            data=lib.generar_zip_bytes({f"{_larch}_MOD{l}.tex": d for l, d in ef[f"latex_exam{_ls}"].items()}),
                            file_name=f"{_larch}_latex_examenes.zip", mime="application/zip",
                            use_container_width=True, key=f"dl_latex_exam{_ls}")
                        _lc2.download_button(f"📑 {_fl}Soluciones{_llbl}",
                            data=lib.generar_zip_bytes({f"{_larch}_MOD{l}_SOL.tex": d for l, d in ef[f"latex_sol{_ls}"].items()}),
                            file_name=f"{_larch}_latex_soluciones.zip", mime="application/zip",
                            use_container_width=True, key=f"dl_latex_sol{_ls}")
                    if ef.get("latex_adapt"):
                        st.download_button("♿ Adaptada (LaTeX)",
                            data=lib.generar_zip_bytes({f"{_nef}_MOD{l}_ADAPT.tex": d for l, d in ef["latex_adapt"].items()}),
                            file_name=f"{_nef}_latex_adaptada.zip", mime="application/zip",
                            use_container_width=True, key="dl_latex_adapt")

                if not _bit_exp:
                    st.markdown("**CSV:**")
                _cc1, _cc2 = st.columns(2)
                _cc1.download_button(f"📊 {_fc}Clave",     data=ef["csv_claves"], file_name=f"{_nef}_CLAVES.csv",
                                     mime="text/csv", use_container_width=True, key="dl_csv_claves")
                _cc2.download_button(f"📊 {_fc}Metadatos", data=ef["csv_meta"],   file_name=f"{_nef}_METADATA.csv",
                                     mime="text/csv", use_container_width=True, key="dl_csv_meta")
                _sueltos.__exit__(None, None, None)
                if _bit_exp:
                    _paso_definitivo(ef)

                if not _bit_exp:
                    # ── Marcar preguntas como utilizadas ─────────────────────────────
                    st.markdown("---")
                    _cache_pids = [p.get("ID_Pregunta", "") for p in (st.session_state.get("cache_examen") or []) if p.get("ID_Pregunta")]
                    _ya_marcado = st.session_state.get("_exam_marcado", False)
                    if _ya_marcado:
                        st.success(f"✅ {st.session_state.get('_exam_marcado_n', 0)} preguntas marcadas como utilizadas el {datetime.date.today()}")
                        if st.button("↩ Deshacer marcado", key="btn_unmark", use_container_width=True):
                            st.session_state.pop("_exam_marcado", None)
                            st.session_state.pop("_exam_marcado_n", None)
                            st.rerun()
                    else:
                        _mu1, _mu2 = st.columns([3, 2])
                        _mu1.caption(f"📋 {len(_cache_pids)} preguntas en el examen actual")
                        if _mu2.button("✅ Marcar como utilizadas", key="btn_marcar_usadas",
                                       use_container_width=True, disabled=not _cache_pids,
                                       help="Guarda la fecha de hoy como 'Fecha de uso' en la BD para todas las preguntas del examen"):
                            _n = marcar_preguntas_usadas(_cache_pids, datetime.date.today().strftime("%Y-%m-%d"))
                            st.session_state["_exam_marcado"] = True
                            st.session_state["_exam_marcado_n"] = _n
                            st.rerun()

                    if st.button("🔄 Nueva exportación", use_container_width=True, key="btn_clear_export"):
                        st.session_state.pop("export_files", None)
                        st.session_state.pop("_prev_mjax", None)
                        st.session_state.pop("_compiled_pdf", None)
                        st.session_state.pop("_exam_marcado", None)
                        st.session_state.pop("_exam_marcado_n", None)
                        st.rerun()

        with _t_pdf:
            # ── Compilación PDF online ────────────────────────────────────────────
            if not _bit_exp:
                st.markdown("---")

            _ef_now    = st.session_state.get("export_files")
            _tex_avail_sfxs = [s for s in ("", "_TEST", "_DEV") if _ef_now and _ef_now.get(f"latex_exam{s}")]
            _nombre_base    = _ef_now.get("nombre", "examen") if _ef_now else "examen"
            _rub_tex_key    = f"{_nombre_base}_RUBRICA.tex"
            _rub_tex_raw    = (_ef_now["_zip_all"].get(_rub_tex_key) or "") if _ef_now else ""
            _rub_tex_bytes  = _rub_tex_raw.decode("utf-8", errors="replace") if isinstance(_rub_tex_raw, (bytes, bytearray)) else str(_rub_tex_raw)

            if not _tex_avail_sfxs and not _rub_tex_bytes:
                if not _bit_exp:
                    st.info("Activa **📑 LaTeX** y exporta primero para poder compilar el PDF.")
                elif _ef_now:
                    st.caption("Para ver el PDF, activa el formato LaTeX en Formato › Formatos y versión con soluciones "
                               "y actualiza los archivos.")
            else:
                _sty_b     = _ef_now["_zip_all"].get("estilo_examen_moderno_v2.sty", b"") if _ef_now else b""
                _img_files = {k: v for k, v in _ef_now["_zip_all"].items() if k.startswith("dev_img_")} if _ef_now else {}
                if _ef_now and _ef_now.get("formulario_name") and _ef_now.get("formulario_bytes"):
                    _img_files[_ef_now["formulario_name"]] = _ef_now["formulario_bytes"]

                # Construir lista de documentos compilables (examen + rúbrica si existe)
                _doc_lbl_map = {"": "Examen completo", "_TEST": "Test (MCQ)", "_DEV": "Desarrollo"}
                _compile_opts = [("exam", s, _doc_lbl_map[s]) for s in _tex_avail_sfxs]
                if _rub_tex_bytes:
                    _compile_opts.append(("rub", "", "Rúbrica / Guía de corrección"))

                if len(_compile_opts) > 1:
                    _doc_sel = st.selectbox(
                        "Documento a compilar",
                        _compile_opts,
                        format_func=lambda x: x[2],
                        key="compile_doc",
                    )
                elif _compile_opts:
                    _doc_sel = _compile_opts[0]
                else:
                    _doc_sel = None

                if _doc_sel:
                    _doc_type, _compile_sfx, _doc_label = _doc_sel

                    # Layout unificado [info1 | info2 | botón] para rubrica y examen
                    if _bit_exp:     # columna estrecha: modelo y versión en una fila; el botón debajo
                        _cx1, _cx2 = st.columns([1, 1.4])
                        _cx3 = st.container()
                    else:
                        _cx1, _cx2, _cx3 = st.columns([1, 1, 2])

                    if _doc_type == "rub":
                        _cx1.caption(f"📐 **{_doc_label}**")
                        _cx2.caption(_rub_tex_key)
                        _tex_preview_src = _rub_tex_bytes
                    else:
                        _latex_exam_sel = _ef_now[f"latex_exam{_compile_sfx}"]
                        _modelos_disp   = list(_latex_exam_sel.keys())
                        nombre_compile  = _nombre_base + _compile_sfx
                        _modelo_sel = _cx1.selectbox("Modelo", _modelos_disp,
                                                      key="compile_modelo",
                                                      format_func=lambda x: f"Modelo {x}")
                        _sol_sel    = _cx2.radio("Versión", ["Alumno", "Soluciones"],
                                                  horizontal=True, key="compile_ver")
                        _tex_preview_src = (
                            _latex_exam_sel.get(_modelos_disp[0], "") if _modelos_disp else ""
                        )

                    if _cx3.button("🔨 Compilar PDF", type="primary",
                                    use_container_width=True, key="btn_compile_pdf"):
                        if _doc_type == "rub":
                            st.session_state["_compile_request"] = {
                                "tex":    _rub_tex_bytes,
                                "sty":    _sty_b, "imgs": _img_files,
                                "nombre": _rub_tex_key.replace(".tex", ""),
                                "pdf_name": _rub_tex_key.replace(".tex", ".pdf"),
                            }
                        else:
                            _tex_src = (
                                _latex_exam_sel[_modelo_sel]
                                if _sol_sel == "Alumno"
                                else _ef_now.get(f"latex_sol{_compile_sfx}", _latex_exam_sel)[_modelo_sel]
                            )
                            _pdf_name = f"{nombre_compile}_MOD{_modelo_sel}{'_SOL' if _sol_sel == 'Soluciones' else ''}.pdf"
                            st.session_state["_compile_request"] = {
                                "tex": _tex_src, "sty": _sty_b, "imgs": _img_files,
                                "nombre": nombre_compile, "pdf_name": _pdf_name,
                                "clave": (_clave_modelo(_ef_now, _modelo_sel)
                                          if _sol_sel == "Soluciones" and _compile_sfx in ("", "_TEST") else ""),
                            }
                        st.session_state.pop("_compiled_pdf", None)
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
                            _dialog_ver_pdf(_cpdf)

                    # Fuente .tex (para depuración)
                    with st.expander("📋 Ver fuente .tex (depuración)", expanded=False):
                        _src_lines = _tex_preview_src.split("\n")
                        _numbered  = "\n".join(f"{i+1:>3}: {l}" for i, l in enumerate(_src_lines[:100]))
                        st.code(_numbered, language="latex")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 · HISTORIAL
# ─────────────────────────────────────────────────────────────────────────────
with tab_hist:
    if get_estilo() == "clasico":
        st.subheader("Historial de exámenes generados")
    else:
        pass

    _historial_bd()
    hist = st.session_state.historial
    if get_estilo() == "bitacora":
        _hist_box = st.expander(f"Historial antiguo de este ordenador · {len(hist)}")
    else:
        _hist_box = st.container()
    _hist_box.__enter__()
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
                (f"{entry.get('fecha','?')} · {entry.get('nombre','?')} · {n_total_e} preguntas · "
                 f"{entry.get('n_modelos','—')} modelo(s) · {n_f} F / {n_m} M / {n_d} D")
                if get_estilo() == "bitacora" else
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
                        f"<span style='color:var(--ui-ok, #27ae60)'>⬤ Fácil: {n_f} ({_pct_f}%)</span> &nbsp; "
                        f"<span style='color:var(--ui-warn, #f39c12)'>⬤ Media: {n_m} ({_pct_m}%)</span> &nbsp; "
                        f"<span style='color:var(--ui-err, #c0392b)'>⬤ Difícil: {n_d} ({_pct_d}%)</span>"
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
                    notify(f"Recargadas {len(valid)} preguntas. Ve a la pestaña Selección.")
                    st.rerun()
                if exam_cfg_e and _ha2.button("↺ Restaurar configuración", key=f"hist_cfg_{i}",
                                               use_container_width=True,
                                               help="Recupera toda la configuración de exportación (institución, tipo, fecha, estilo…)"):
                    st.session_state.exam_cfg = dict(exam_cfg_e)
                    notify("Configuración restaurada. Ve a la pestaña Ver y exportar.")
                    st.rerun()
                if _ha3.button("↩️+↺ Ambos", key=f"hist_both_{i}",
                               use_container_width=True,
                               help="Restaura tanto las preguntas como la configuración"):
                    valid = [pid for pid in ids if pid in df_total["ID_Pregunta"].values]
                    set_sel_ids(valid)
                    if exam_cfg_e:
                        st.session_state.exam_cfg = dict(exam_cfg_e)
                    notify(f"Restauradas {len(valid)} preguntas y configuración. Ve a Selección o Exportar.")
                    st.rerun()

    _hist_box.__exit__(None, None, None)
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
                _by = {r["ID_Pregunta"]: r for r in df_total[df_total["ID_Pregunta"].isin(valid)].to_dict("records")}
                pool = [_by[i] for i in valid]          # en el orden del examen
                E.al_generar(pool)
                st.session_state.cache_examen = pool
                st.session_state.pop("exam_lock", None)
                st.session_state["recovery_mode"] = True  # activa modo recuperación
                st.success(
                    f"✅ Recuperadas {len(valid)} de {len(ids_csv)} preguntas del CSV. "
                    "Ve a **Generar** — el botón Generar está bloqueado "
                    "(pulsa 🔓 Desbloquear si quieres modificarlo)."
                )
                st.rerun()
            else:
                st.warning(f"Se encontraron {len(ids_csv)} IDs en el CSV pero ninguno coincide con la DB actual.")
        except Exception as e:
            st.error(f"Error al leer el CSV: {e}")
