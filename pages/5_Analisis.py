"""
pages/5_Analisis.py  –  Análisis de ítems de exámenes ya corregidos.

Privacidad: el Excel del corrector (con nombres y DNI) se procesa SOLO en memoria durante
la sesión. En la base de datos (compartida entre profesores) únicamente se guardan datos
agregados por pregunta y las decisiones tomadas (hojas An_Examenes y An_Preguntas).

Pestañas: Resumen · Preguntas (con mapa del examen y modo revisión) · Alumnos · Exámenes
"""
import io
import json
import os
import sys
import datetime

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as stcomponents

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import _recarga, importlib as _il_r, os as _os_r   # _recarga también se recarga a sí mismo si cambió
_recarga = (_il_r.reload(_recarga) if getattr(_recarga, "_MTIME", None) != _os_r.path.getmtime(_recarga.__file__) else _recarga)
_recarga.comprobar()

import os as _o, sys as _s
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import examen_lib_latex as lib
import analisis_lib as A
from app_theme import initial_sidebar, notify, get_estilo
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback, apply_theme, page_header,
    mathjax_html, render_question_card_html, nombre_bloque, nombre_tema, temas_de_bloque,
    sync_bloques_gsheets, reload_db, guardar_hojas, datos_de_fila,
)

st.set_page_config(page_title="Análisis · Exámenes UCM", page_icon="📈", layout="wide",
                   initial_sidebar_state=initial_sidebar())
init_session_state()
handle_oauth_callback()
apply_theme("analisis")
render_sidebar()

st.markdown("""<style>
.an-kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:4px 0 16px 0; }
.an-kpi { background:var(--card,#fff); border:1px solid var(--border,#dee2e6); border-radius:12px; padding:13px 16px; }
.an-kpi .l { font-size:.78rem; color:var(--muted,#6c757d); font-weight:600; }
.an-kpi .v { font-size:1.55rem; font-weight:700; color:var(--text,#2c3e50); line-height:1.25; margin-top:2px; }
.an-kpi .s { font-size:.78rem; color:var(--muted,#6c757d); margin-top:2px; }
.an-kpi.ok .v { color:var(--ok,#27ae60); } .an-kpi.warn .v { color:var(--warn,#b9770e); } .an-kpi.err .v { color:var(--err,#c0392b); }
.an-chip { display:inline-block; padding:2px 9px; border-radius:999px; font-size:.75rem; font-weight:600; margin:1px 3px 1px 0;
  background:var(--card2,#f1f3f5); color:var(--text2,#495057); border:1px solid var(--border,#dee2e6); }
.an-chip.ok { background:var(--ok-bg,#e3f1e8); color:var(--ok,#1e6b3c); border-color:transparent; }
.an-chip.warn { background:var(--warn-bg,#fdf0d5); color:var(--warn,#7a4f00); border-color:transparent; }
.an-chip.err { background:var(--err-bg,#fbe7e4); color:var(--err,#a3261a); border-color:transparent; }
.an-note { background:var(--card2,#f8f9fa); border:1px solid var(--border,#dee2e6); border-radius:10px; padding:10px 14px;
  font-size:.86rem; color:var(--text2,#495057); margin:6px 0 12px 0; }
.an-map { display:grid; grid-template-columns:repeat(auto-fill,minmax(46px,1fr)); gap:6px; margin:6px 0 14px 0; }
.an-map div { border-radius:8px; padding:6px 0 5px 0; text-align:center; font-size:.8rem; font-weight:700; line-height:1.15;
  background:var(--ok-bg,#e3f1e8); color:var(--ok,#1e6b3c); border:2px solid transparent; }
.an-map div small { display:block; font-weight:500; font-size:.68rem; opacity:.85; }
.an-map div.w { background:var(--warn-bg,#fdf0d5); color:var(--warn,#7a4f00); }
.an-map div.e { background:var(--err-bg,#fbe7e4); color:var(--err,#a3261a); }
.an-map div.d { border-color:var(--primary,#3498db); }
.an-bar { height:7px; background:var(--track,#e9ecef); border-radius:4px; overflow:hidden; min-width:60px; }
.an-bar > div { height:100%; background:var(--primary,#3498db); border-radius:4px; }
.an-bar.ok > div { background:var(--ok,#27ae60); }
.an-opts { width:100%; border-collapse:collapse; font-size:.86rem; }
.an-opts th { text-align:left; font-size:.72rem; color:var(--muted,#6c757d); font-weight:600; padding:4px 6px;
  border-bottom:1px solid var(--border,#dee2e6); }
.an-opts td { padding:7px 6px; border-bottom:1px solid var(--border,#eee); vertical-align:middle; color:var(--text,#2c3e50); }
.an-opts tr.ok td { background:var(--ok-bg,#e3f1e8); }
.an-opts td.l { font-weight:700; width:28px; }
.an-diag { border-left:4px solid var(--primary,#3498db); background:var(--primary-soft,#eaf4fb); border-radius:0 10px 10px 0;
  padding:10px 14px; margin:10px 0; font-size:.9rem; color:var(--text,#2c3e50); }
.an-diag.e { border-color:var(--err,#c0392b); background:var(--err-bg,#fbe7e4); }
.an-diag.w { border-color:var(--warn,#b9770e); background:var(--warn-bg,#fdf0d5); }
.an-dl { display:grid; grid-template-columns:1fr auto; gap:4px 10px; font-size:.86rem; }
.an-dl span:nth-child(odd) { color:var(--muted,#6c757d); } .an-dl span:nth-child(even) { font-weight:600; text-align:right; color:var(--text,#2c3e50); }
.an-q5 { display:flex; align-items:flex-end; gap:6px; height:90px; margin:6px 0 2px 0; }
.an-q5 div { flex:1; background:var(--primary,#3498db); border-radius:5px 5px 0 0; position:relative; min-height:2px; }
.an-q5 div span { position:absolute; top:-17px; left:0; right:0; text-align:center; font-size:.7rem; color:var(--muted,#6c757d); }
.an-q5l { display:flex; gap:6px; font-size:.68rem; color:var(--muted,#6c757d); } .an-q5l span { flex:1; text-align:center; }
.an-row { font-size:.86rem; line-height:1.35; color:var(--text,#2c3e50); }
.an-row small { color:var(--muted,#6c757d); }
.an-est { border-radius:10px; padding:9px 12px; font-size:.85rem; }
.an-est.b { background:var(--ok-bg,#e3f1e8); color:var(--ok,#1e6b3c); } .an-est.w { background:var(--warn-bg,#fdf0d5); color:var(--warn,#7a4f00); } .an-est.m { background:var(--err-bg,#fbe7e4); color:var(--err,#a3261a); }
.st-key-an_nocuadra { background:var(--err-bg,#fbe7e4); border:1px solid var(--err,#a3261a); border-radius:12px; padding:14px 18px; margin:8px 0 14px; }
.st-key-an_nocuadra p { color:var(--text,#2c3e50); }
.an-frase { background:var(--card2,#f5f7fa); border-radius:10px; padding:11px 14px; margin:4px 0 12px; font-size:.95rem; line-height:1.55; }
.st-key-an_mapa { flex-wrap:wrap; }
[class*="st-key-anc_"] button { min-height:0 !important; height:34px; padding:0 9px; border:2px solid transparent; position:relative;
  font-weight:700; transition:opacity .15s; }
[class*="st-key-anc_f_"] button { background:var(--ok-bg,#e3f1e8); color:var(--ok,#1e6b3c); }
[class*="st-key-anc_m_"] button { background:var(--primary-soft,#e6edf8); color:var(--primary,#1d4a94); }
[class*="st-key-anc_h_"] button { background:var(--err-bg,#fbe7e4); color:var(--err,#a3261a); }
[class*="st-key-anc_"][class*="_e_"] button::after, [class*="st-key-anc_"][class*="_w_"] button::after {
  content:""; position:absolute; top:-4px; right:-4px; width:10px; height:10px; border-radius:50%; border:2px solid var(--card,#fff); }
[class*="st-key-anc_"][class*="_e_"] button::after { background:var(--err,#a3261a); }
[class*="st-key-anc_"][class*="_w_"] button::after { background:var(--warn,#b9770e); }
[class*="st-key-anc_"][class*="_k_"] button { border-color:var(--primary,#1d4a94); }
[class*="st-key-anc_"][class*="_s_"] button { outline:2px solid var(--text,#1a2233); }
[class*="st-key-anc_"][class*="_x_"] button { opacity:.25; }
.an-ley { display:flex; gap:14px; flex-wrap:wrap; font-size:.78rem; color:var(--muted,#6c757d); margin:2px 0 8px; }
.an-ley span { display:inline-flex; align-items:center; gap:5px; }
.an-ley i { width:12px; height:12px; border-radius:3px; display:inline-block; }
.an-ley i.f { background:var(--ok-bg); border:1px solid var(--ok); } .an-ley i.m { background:var(--primary-soft); border:1px solid var(--primary); }
.an-ley i.h { background:var(--err-bg); border:1px solid var(--err); }
.an-ley i.pe, .an-ley i.pw { border-radius:50%; width:9px; height:9px; } .an-ley i.pe { background:var(--err); } .an-ley i.pw { background:var(--warn); }
.an-ley i.dk { border:2px solid var(--primary); }
.an-pila { margin:6px 0 14px; } .an-pila .t { font-size:.82rem; font-weight:600; margin-bottom:5px; color:var(--text2); }
.an-pila .b { display:flex; height:14px; border-radius:99px; overflow:hidden; background:var(--track,#e9ecef); }
.an-pila .l { display:flex; flex-wrap:wrap; gap:10px; font-size:.76rem; color:var(--muted); margin-top:5px; }
.an-pila .l span { display:inline-flex; align-items:center; gap:4px; } .an-pila .l i { width:9px; height:9px; border-radius:2px; display:inline-block; }
.an-top { display:flex; justify-content:space-between; align-items:baseline; } .an-top b { font-size:1.3rem; }
.an-top span { font-size:.78rem; color:var(--muted); }
.an-top-e { font-size:.84rem; line-height:1.35; margin:4px 0 6px; min-height:3.4em; color:var(--text); }
[class*="st-key-an_topc_e_"] { border-top:3px solid var(--err) !important; } [class*="st-key-an_topc_w_"] { border-top:3px solid var(--warn) !important; }
table.an-mod { width:100%; border-collapse:collapse; font-size:.86rem; }
table.an-mod th { text-align:left; font-size:.72rem; color:var(--muted); font-weight:600; padding:4px 6px; border-bottom:1px solid var(--border); }
table.an-mod td { padding:6px; border-bottom:1px solid var(--border-light,#eee); }
[class*="st-key-an_fila_"] { border-bottom:1px solid var(--border-light,#e4e8ef); padding:2px 0; }
.an-t1 { display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.an-sm { color:var(--muted,#6c757d); font-size:.74rem; }
.an-disc { font-size:.8rem; font-weight:600; padding:2px 9px; border-radius:999px; }
.an-disc.o { background:var(--ok-bg); color:var(--ok); } .an-disc.w { background:var(--warn-bg); color:var(--warn); }
.an-disc.p { background:var(--card2); color:var(--muted); } .an-disc.e { background:var(--err-bg); color:var(--err); }
[class*="st-key-anc_"] button p { font-size:.8rem; }
</style>""", unsafe_allow_html=True)

page_header("📈", "Análisis de exámenes",
            "Cómo han funcionado las preguntas de un examen ya corregido")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos antes de continuar.")
    st.stop()

dfs = st.session_state.excel_dfs
df_preg = st.session_state.df_preguntas
_bank = df_preg.set_index("ID_Pregunta").to_dict("index") if not df_preg.empty else {}
_ss = st.session_state


# ── Utilidades de presentación ────────────────────────────────────────────────
def _f(v, d=0, pct=False):
    if v is None or v != v:
        return "—"
    s = f"{v:.{d}f}".replace(".", ",")
    return s + (" %" if pct else "")


def _kpis(items):
    h = "".join(f'<div class="an-kpi {c}"><div class="l">{l}</div><div class="v">{v}</div>'
                f'<div class="s">{s}</div></div>' for l, v, s, c in items)
    st.markdown(f'<div class="an-kpis">{h}</div>', unsafe_allow_html=True)


def _bar(p, ok=False):
    p = 0 if p != p else max(0, min(100, p))
    return f'<div class="an-bar{" ok" if ok else ""}"><div style="width:{p:.0f}%"></div></div>'


def _chips(et):
    if not et:
        return '<span class="an-chip ok">Bien</span>'
    out = ""
    for e in et:
        cls = "err" if ("revés" in e or "atrae" in e) else "warn"
        out += f'<span class="an-chip {cls}">{e}</span>'
    return out


def _disc_txt(d):
    """Discriminación en palabras: (texto, clase de color)."""
    if d != d:
        return "—", ""
    if d < 0:
        return "Al revés", "e"
    if d < 0.15:
        return "Poco", "p"
    if d < 0.3:
        return "Regular", "w"
    return "Bien", "o"


def _sev(it):
    et = it["etiquetas"]
    if any(("revés" in e or "atrae" in e) for e in et):
        return "e"
    return "w" if et else ""


def _zona_kr(lo, hi, v):
    def z(x):
        return "Buena" if x >= 0.8 else ("Aceptable" if x >= 0.7 else "Baja")
    if v != v:
        return "—", ""
    if lo == lo and z(lo) != z(hi):
        return f"{z(v)} · zona de duda", f"el margen va de {_f(lo, 2)} a {_f(hi, 2)}: puede ser {z(lo)} o {z(hi)}"
    return z(v), f"margen {_f(lo, 2)}–{_f(hi, 2)}" if lo == lo else ""


# ══════════════════════════════════════════════════════════════════════════════
# Origen de los datos: examen registrado + Excel del corrector (solo en memoria)
# ══════════════════════════════════════════════════════════════════════════════
exs = A.get_examenes(dfs)
exs = exs[exs["Estado"] != "Borrador"]   # los borradores del Generador no se analizan
res_db = A.get_resultados(dfs)
_ex_opts = ["__none__"] + exs["ID_Examen"].tolist()
_ex_lbl = {r["ID_Examen"]: f'{r["Curso"]} · {r["Convocatoria"] or "—"} · {r["Nombre"]}' for _, r in exs.iterrows()}
_ex_lbl["__none__"] = "Examen sin registrar (clave a mano)"

with st.container(border=True, key="card_an_src"):
    c1, c2, c3 = st.columns([1.25, 1.1, 0.9], gap="medium", vertical_alignment="center")
    with c1:
        if "_an_exam_next" in _ss:
            _ss["an_exam"] = _ss.pop("_an_exam_next")
        if _ss.get("an_exam") not in _ex_opts:
            _ss["_an_exam_next"] = _ex_opts[-1] if len(_ex_opts) > 1 else "__none__"
        ex_id = st.selectbox("Examen", _ex_opts, key="an_exam", format_func=lambda x: _ex_lbl.get(x, x),
                             help="Los exámenes exportados desde el Generador se registran solos. "
                                  "Los anteriores se pueden registrar en la pestaña «Exámenes».")
    with c2:
        up = st.file_uploader("Excel del corrector (.xls / .xlsx)", type=["xls", "xlsx"], key="an_upload",
                              help="Solo se lee en memoria: no se guarda en la app ni en la base de datos.")
    _estado_box = c3.empty()
    _guardar_box = c3.empty()
    st.caption("🔒 Los datos de los alumnos solo se usan en esta sesión. En la base de datos compartida "
               "solo se guardan porcentajes por pregunta y las decisiones que tomes. "
               "Para importar, editar o borrar exámenes: página Exámenes.")

if up is not None and _ss.get("_an_up_name") != (up.name, up.size):
    try:
        _ss["an_data"] = A.parse_corrector(up.getvalue())
        _ss["_an_up_name"] = (up.name, up.size)
        _ss.pop("an_rev_mode", None)
    except Exception as e:
        st.error(f"No se ha podido leer el Excel del corrector: {e}")
        _ss.pop("an_data", None)
if up is None and _ss.get("_an_up_name"):
    _ss.pop("an_data", None); _ss.pop("_an_up_name", None)

data = _ss.get("an_data")
info = A.examen_info(exs[exs["ID_Examen"] == ex_id].iloc[0]) if ex_id != "__none__" else None


# ── Decisiones (en sesión; se guardan en la BD con «Guardar análisis») ───────
def _dec_store(key: str, cargar: bool) -> dict:
    allp = _ss.setdefault("an_dec", {})
    if key not in allp:
        d, rv = {}, set()
        if cargar:
            for _, r in res_db[res_db["ID_Examen"] == ex_id].iterrows():
                try:
                    j = int(float(r["Pos"])) - 1
                except Exception:
                    continue
                if r["Decision"]:
                    d[j] = {"tipo": r["Decision"], "letra": r["Letra_Extra"]}
                if str(r["Revisar_Distractores"]) in ("1", "True", "Sí"):
                    rv.add(j)
        allp[key] = {"dec": d, "rev": rv}
    return allp[key]


def _tab_examenes():
    """La gestión de exámenes (importar, editar, borrar…) está en su propia página."""
    st.page_link("pages/6_Examenes.py", label="Ir a Exámenes: importar, editar datos, borrar o volver a importar ›")


# ── Sin Excel: solo la gestión del registro ──────────────────────────────────
if data is None:
    st.markdown("<div class='an-note'>Elige el examen y sube el Excel que devuelve el corrector para ver el análisis "
                "(solo se lee en memoria).</div>", unsafe_allow_html=True)
    _tab_examenes()
    st.stop()

alumnos = data["alumnos"]
if alumnos.empty:
    st.error("El Excel no contiene respuestas de alumnos.")
    st.stop()

# ── Modelos y clave ───────────────────────────────────────────────────────────
vers_raw = sorted(alumnos["Ver"].unique().tolist())
if info is not None and info["claves"]:
    modelos = sorted(info["claves"])
else:
    modelos = [str(v).upper() or "A" for v in vers_raw] if vers_raw != [""] else ["A"]
vmap = A.mapa_ver(vers_raw, modelos)
alumnos = alumnos.assign(Modelo=alumnos["Ver"].map(vmap))
_fuera = alumnos[alumnos["Modelo"].isna()]
if not _fuera.empty:
    st.caption(f"{len(_fuera)} alumno(s) del modelo {', '.join(sorted(_fuera['Ver'].astype(str).unique()))} no se analizan: "
               "ese modelo no está en el registro del examen.")
    alumnos = alumnos[alumnos["Modelo"].notna()]

claves = dict(info["claves"]) if info is not None else {}
if info is None:
    with st.container(border=True, key="card_an_keys"):
        st.markdown("**Clave del examen** — no está registrado, así que indícala para cada modelo "
                    "(se propone la más probable según los mejores alumnos).")
        kc = st.columns(len(modelos))
        for i, v in enumerate(modelos):
            sub = alumnos[alumnos["Modelo"] == v]
            n = int(sub["Resp"].str.len().max() or 0)
            k = f"an_key_{v}"
            if k not in _ss:
                _ss[k] = A.estimar_clave(A.respuestas_matriz(sub["Resp"].tolist(), n)) if n else ""
            claves[v] = "".join(c for c in kc[i].text_input(f"Modelo {v}", key=k).upper() if c in A.LETRAS)
        st.caption("Para guardar el análisis en la base de datos, registra el examen en la pestaña «Exámenes».")

unif_ok = info is not None and A.puede_unificar(info)
vistas = (["Unificado"] if unif_ok else []) + (modelos if len(modelos) > 1 else [])
if vistas:
    with st.container(key="pill_an_vista"):
        vista = st.radio("Ver", vistas, horizontal=True, key="an_vista",
                         format_func=lambda v: "Todos los modelos (unificado)" if v == "Unificado" else f"Modelo {v}",
                         help="Unificado: las preguntas de todos los modelos se juntan en el orden y las "
                              "letras del primer modelo.")
else:
    vista = modelos[0]
if vista not in (["Unificado"] + modelos):
    vista = modelos[0]

if vista == "Unificado":
    M, clave = A.unificar(alumnos, info)
    sub_al = alumnos
    base_m = sorted(info["claves"])[0]
else:
    sub_al = alumnos[alumnos["Modelo"] == vista] if len(modelos) > 1 else alumnos
    clave = claves.get(vista, "")
    base_m = vista
    M = A.respuestas_matriz(sub_al["Resp"].tolist(), len(clave)) if clave else None

if not clave or M is None or len(M) == 0:
    st.warning("Falta la clave de este modelo o no hay alumnos de ese modelo.")
    _tab_examenes()
    st.stop()

ids = (info["posiciones"].get(base_m, []) if info is not None else [])
ids = (list(ids) + [""] * len(clave))[:len(clave)]
perms = (info["perms"].get(base_m, []) if info is not None else [])
R = A.analizar(M, clave)
items = R["items"]
# Las decisiones se guardan por posición del primer modelo: solo en la vista unificada
# (o en el primer modelo / examen de un solo modelo) se pueden guardar en la base de datos.
guardable = info is not None and (vista == "Unificado" or base_m == sorted(info["claves"])[0])
if guardable:
    store = _dec_store(ex_id, True)
else:
    store = _dec_store(f"{ex_id}|{vista}|{clave}", False)
dec = store["dec"]
punt_orig = A.puntuar(M, A.aceptadas(clave))
punt_new = A.puntuar(M, A.aceptadas(clave, dec))


def _opt_texts(j):
    """Textos de las opciones tal como aparecían en el examen (primer modelo / modelo elegido)."""
    pid = ids[j]
    row = _bank.get(pid)
    if not row:
        return None, False
    ops = row.get("opciones_list") or []
    if j < len(perms) and perms[j] and "?" not in perms[j][:len(ops[:4])]:
        return [ops[A.LETRAS.index(c)] if A.LETRAS.index(c) < len(ops) else "" for c in perms[j][:4]], True
    return [ops[i] if i < len(ops) else "" for i in range(4)], False


def _guardar_analisis():
    hoy = datetime.date.today().isoformat()
    filas = []
    for j, it in enumerate(items):
        d = dec.get(j, {})
        filas.append({
            "ID_Examen": ex_id, "Pos": j + 1, "ID_Pregunta": ids[j], "N": R["N"],
            "Pct_Acierto": round(it["acierto"], 1), "Pct_Blanco": round(it["blanco"], 1),
            "Discriminacion": round(it["disc"], 3) if it["disc"] == it["disc"] else "",
            **{f"Pct_{L}": round(it["opciones"][L]["pct"], 1) for L in A.LETRAS},
            "Decision": d.get("tipo", ""), "Letra_Extra": d.get("letra", ""),
            "Revisar_Distractores": "1" if j in store["rev"] else "", "Fecha": hoy})
    A.guardar_resultados(dfs, ex_id, filas, {
        "N_Alumnos": R["N"], "Media": round(float(punt_new["Nota"].mean()), 2),
        "KR20": round(R["kr20"], 3) if R["kr20"] == R["kr20"] else "", "Fecha_Analisis": hoy})
    guardar_hojas([A.SHEET_EXAMENES, A.SHEET_PREGUNTAS])
    notify("✅ Análisis guardado (solo porcentajes por pregunta y decisiones; ningún dato de alumnos).")


def _boton_guardar(key):
    if info is None:
        st.caption("Registra el examen para poder guardar el análisis.")
        return
    if not guardable:
        st.caption("Para guardar el análisis usa la vista «Todos los modelos» o el primer modelo.")
        return
    if st.button("Guardar análisis", type="primary", key=key, use_container_width=True,
                 help="Guarda en la base de datos los porcentajes por pregunta y tus decisiones. "
                      "No guarda nada de los alumnos."):
        _guardar_analisis()
        st.rerun()


# ── ¿Reproduce la clave las notas del corrector? ─────────────────────────────
_cont = A._j((exs[exs["ID_Examen"] == ex_id].iloc[0]["Contenido"] if info is not None else ""), {})
_dec_corr = {int(k): {"tipo": v[0], "letra": v[1]} for k, v in (_cont.get("dec_corrector") or {}).items()} \
    if base_m == (sorted(info["claves"])[0] if info is not None else base_m) else {}
_tot = sub_al["Total"].to_numpy(dtype=float)
n_ok, n_tot = A.cuadran(M, A.aceptadas(clave, _dec_corr), _tot)
if n_tot:
    _bien = n_ok == n_tot
    _estado_box.markdown(f"<div class='an-est {'b' if _bien else 'm'}'><b>{'✓ Notas comprobadas' if _bien else '✗ Notas que no cuadran'}</b>"
                         f"<br>notas iguales a las del corrector en {n_ok} de {n_tot} alumnos"
                         + (f" · {len(_fuera)} del modelo {', '.join(sorted(_fuera['Ver'].astype(str).unique()))} fuera" if not _fuera.empty else "")
                         + "</div>", unsafe_allow_html=True)
_mantenida = base_m in (_cont.get("clave_del_examen") or [])
if n_tot and n_ok < n_tot and _mantenida:
    _estado_box.markdown(f"<div class='an-est w'><b>Clave del examen</b><br>notas iguales a las del corrector en {n_ok} de {n_tot} alumnos: "
                         "se mantuvo a propósito (mira Alumnos)</div>", unsafe_allow_html=True)
if n_tot and n_ok < 0.9 * n_tot and not _mantenida and not _ss.get(f"an_igual_{ex_id}_{vista}"):
    with st.container(key="an_nocuadra"):
        st.markdown(f"**Las notas solo coinciden con las del corrector en {n_ok} de {n_tot} alumnos.** Con la clave registrada los "
                    "alumnos sacan notas distintas de las del corrector: casi seguro la clave o el orden de las opciones no "
                    "son los del examen que se hizo (por ejemplo, se importó sin el Word final). El análisis **no es fiable**.")
        _prop = _ss.get(f"an_prop_{ex_id}_{vista}")
        k1, k2, k3 = st.columns([1.6, 1.4, 1])
        if info is not None and k1.button("Buscar la clave que usó el corrector", type="primary", key="an_busca"):
            with st.spinner("Buscando…"):
                _ss[f"an_prop_{ex_id}_{vista}"] = A.buscar_clave(M, clave, _tot)
            st.rerun()
        if k2.button("Volver a importar el examen", key="an_reimp"):
            _ss["ex_sel"] = ex_id
            st.switch_page("pages/6_Examenes.py")
        if k3.button("Ver igualmente", key="an_igual"):
            _ss[f"an_igual_{ex_id}_{vista}"] = True
            st.rerun()
        if _prop is not None:
            _d2 = dict(_dec_corr); _d2.update({j: {"tipo": tp, "letra": L} for j, tp, L in _prop})
            n2, _ = A.cuadran(M, A.aceptadas(clave, _d2), _tot)
            if _prop and n2 >= 0.9 * n_tot and len(_prop) <= 8:
                st.markdown(f"Con estos **{len(_prop)} cambios** cuadran **{n2}/{n_tot}**: "
                            + " · ".join(f"P{j + 1}: {clave[j]} → {L if tp == 'cambiar' else A.DECISIONES[tp].lower() + (' ' + L if L else '')}"
                                         for j, tp, L in _prop))
                if st.button("Corregir el registro con la clave del corrector", type="primary", key="an_aplica"):
                    _row = dict(exs[exs["ID_Examen"] == ex_id].iloc[0])
                    _cl = dict(info["claves"]); _k = list(_cl[base_m])
                    _dc = dict(_cont.get("dec_corrector") or {})
                    for j, tp, L in _prop:
                        if tp == "cambiar":
                            _k[j] = L
                        else:
                            _dc[str(j)] = [tp, L]
                    _cl[base_m] = "".join(_k)
                    _cont["dec_corrector"] = _dc
                    _row.update({"Claves": json.dumps(_cl), "Contenido": json.dumps(_cont, ensure_ascii=False),
                                 "Comprobacion": json.dumps({**A._j(_row.get("Comprobacion", ""), {}), base_m: f"{n2}/{n_tot}"})})
                    A.upsert_examen(dfs, _row)
                    # las decisiones del corrector (no los cambios de clave) pasan también a las decisiones del análisis
                    for j, tp, L in _prop:
                        if tp != "cambiar":
                            dec[j] = {"tipo": tp, "letra": L}
                    guardar_hojas([A.SHEET_EXAMENES])
                    _ss.pop(f"an_prop_{ex_id}_{vista}", None)
                    notify("✅ Clave del examen corregida: ahora reproduce las notas del corrector.")
                    st.rerun()
            else:
                st.markdown("Ninguna clave razonable reproduce las notas del corrector en este modelo: lo más probable es "
                            "que el orden de preguntas u opciones no sea el que se imprimió. Vuelve a importar el examen "
                            "con el Word final, o no analices este modelo.")
    _tab_examenes()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# Ficha de una pregunta (se abre desde el mapa, la lista o «Qué revisar primero»)
# ══════════════════════════════════════════════════════════════════════════════
def _orden_filtrado():
    f = _ss.get("an_filtro", "Todas")
    sel = []
    for j, it in enumerate(items):
        et = it["etiquetas"]
        if f == "A revisar" and not et:
            continue
        if f == "Muchos blancos" and "Muchos blancos" not in et:
            continue
        if f == "Muy fáciles" and "Muy fácil" not in et:
            continue
        if f == "Muy difíciles" and "Muy difícil" not in et:
            continue
        sel.append(j)
    o = _ss.get("an_orden", "Posición")
    if o == "Acierto (menor primero)":
        sel.sort(key=lambda j: items[j]["acierto"])
    elif o == "Discriminación (menor primero)":
        sel.sort(key=lambda j: (items[j]["disc"] if items[j]["disc"] == items[j]["disc"] else -9))
    elif o == "Blancos (mayor primero)":
        sel.sort(key=lambda j: -items[j]["blanco"])
    return sel


def _ficha_pregunta():
    lista = _orden_filtrado() or list(range(len(items)))
    j = _ss.get("an_rev_j", lista[0])
    if j not in range(len(items)):
        j = lista[0]
    it = items[j]
    pos_l = lista.index(j) if j in lista else 0

    t3, t2, t4, t5, t1 = st.columns([0.5, 3.6, 0.5, 1.5, 1], vertical_alignment="center")
    if t3.button("‹", key="an_rev_prev", disabled=pos_l == 0, use_container_width=True, help="Anterior de la lista"):
        _ss["an_rev_j"] = lista[pos_l - 1]; st.rerun()
    t2.markdown(f"<div style='font-size:1.1rem;font-weight:700'>Pregunta {j + 1} de {len(items)}</div>"
                f"<div class='devq-s'>{pos_l + 1}/{len(lista)} en la lista «{_ss.get('an_filtro', 'Todas')}»"
                f"{' · ' + ids[j] if ids[j] else ''}</div>", unsafe_allow_html=True)
    if t4.button("›", key="an_rev_next", disabled=pos_l >= len(lista) - 1, use_container_width=True, help="Siguiente de la lista"):
        _ss["an_rev_j"] = lista[pos_l + 1]; st.rerun()
    if ids[j] in _bank and t5.button("Editar en el Gestor", key="an_rev_edit", use_container_width=True):
        _ss["_open_q"] = ids[j]; st.rerun()
    if t1.button("Cerrar", key="an_rev_back", use_container_width=True):
        _ss["an_rev_mode"] = False
        st.rerun()

    cm, cr = st.columns([2.6, 1.7], gap="medium")

    with cm:
        pid = ids[j]
        bank = _bank.get(pid, {})
        head = (f"<b>Pregunta {j + 1}</b>"
                + (f" · <code>{pid}</code> · {nombre_bloque(str(bank.get('bloque', '')))} · "
                   f"{nombre_tema(str(bank.get('Tema', '')))}" if bank else " · <small>sin vincular a la base de datos</small>"))
        st.markdown(f"<div class='an-row'>{head}</div>", unsafe_allow_html=True)
        st.markdown(_chips(it["etiquetas"]), unsafe_allow_html=True)
        txts, exact = _opt_texts(j)
        rows = ""
        for L in A.LETRAS:
            o = it["opciones"][L]
            ok = L == clave[j]
            if ok:
                tag = '<span class="an-chip ok">correcta</span>'
            elif o["n"] == 0:
                tag = '<span class="an-chip">no la elige nadie</span>'
            elif o["sup"] > it["sup"]:
                tag = '<span class="an-chip err">atrae a los mejores</span>'
            elif o["pct"] >= 5:
                tag = '<span class="an-chip warn">distrae</span>'
            else:
                tag = '<span class="an-chip">apenas distrae</span>'
            txt = (txts[A.LETRAS.index(L)] if txts else "")
            txt = (txt[:110] + "…") if len(txt) > 110 else txt
            rows += (f"<tr class='{'ok' if ok else ''}'><td class='l'>{L}</td><td>{txt}</td>"
                     f"<td style='width:150px'>{_bar(o['pct'], ok)}<small>{_f(o['pct'])} % · {o['n']}</small></td>"
                     f"<td>{_f(o['sup'])} %</td><td>{_f(o['inf'])} %</td><td>{_f(o['nota'], 1)}</td><td>{tag}</td></tr>")
        bl = it["blanco"]
        rows += (f"<tr><td class='l'>—</td><td><i>En blanco</i></td><td>{_bar(bl)}<small>{_f(bl)} %</small></td>"
                 f"<td></td><td></td><td></td><td></td></tr>")
        st.markdown(
            "<table class='an-opts'><tr><th></th><th>Opción</th><th>La marcan</th><th>Mejores</th>"
            f"<th>Peores</th><th>Nota media</th><th></th></tr>{rows}</table>", unsafe_allow_html=True)
        if txts and not exact:
            st.caption("Opciones en el orden de la base de datos: puede no coincidir con el del examen.")
        st.caption("«Mejores» y «peores»: el 27 % con más y con menos aciertos. «Nota media»: de quienes marcan esa opción.")
        sev = _sev(it)
        st.markdown(f"<div class='an-diag {sev}'><b>Diagnóstico.</b> {A.diagnostico(it)}</div>",
                    unsafe_allow_html=True)
        inut = A.distractores_inutiles(it)
        rv = st.checkbox("Marcar: reescribir distractores" + (f" (no funcionan: {', '.join(inut)})" if inut else ""),
                         value=j in store["rev"], key=f"an_rev_mark_{ex_id}_{j}")
        if rv:
            store["rev"].add(j)
        else:
            store["rev"].discard(j)

        st.markdown("<div class='sec-title' style='margin-top:10px'>Decisión</div>", unsafe_allow_html=True)
        d_cur = dec.get(j, {})
        dk = st.radio("Decisión", list(A.DECISIONES), format_func=A.DECISIONES.get, horizontal=True,
                      index=list(A.DECISIONES).index(d_cur.get("tipo", "")), key=f"an_dec_t_{ex_id}_{j}",
                      label_visibility="collapsed")
        letra = ""
        if dk in ("aceptar", "cambiar"):
            otras = [L for L in A.LETRAS if L != clave[j]]
            sug = max(otras, key=lambda L: it["opciones"][L]["sup"])
            prev = d_cur.get("letra") if d_cur.get("letra") in otras else sug
            letra = st.selectbox("Letra", otras, index=otras.index(prev), key=f"an_dec_l_{ex_id}_{j}",
                                 help=f"Se propone la {sug}: la más marcada por los mejores tras la correcta.")
        tent = dict(dec)
        if dk:
            tent[j] = {"tipo": dk, "letra": letra}
        else:
            tent.pop(j, None)
        p_t = A.puntuar(M, A.aceptadas(clave, tent))
        diff = (p_t["Nota"] - punt_new["Nota"]).round(4)
        n_ch = int((diff != 0).sum())
        if dk != d_cur.get("tipo", "") or letra != d_cur.get("letra", ""):
            st.markdown(f"<div class='an-note'>Con este cambio, <b>{n_ch}</b> alumno(s) cambian de nota "
                        f"(media {'+' if diff.mean() >= 0 else ''}{_f(diff.mean(), 2)} puntos). "
                        f"Aprobados: {int((punt_new['Nota'] >= 5).sum())} → {int((p_t['Nota'] >= 5).sum())}.</div>",
                        unsafe_allow_html=True)
            if st.button("Aplicar decisión", type="primary", key=f"an_dec_ok_{ex_id}_{j}"):
                if dk:
                    dec[j] = {"tipo": dk, "letra": letra}
                else:
                    dec.pop(j, None)
                notify("✅ Decisión aplicada (recuerda «Guardar análisis»).")
                st.rerun()
        elif dk:
            st.caption(f"Decisión aplicada: {A.DECISIONES[dk]}{' ' + letra if letra else ''}.")
        _boton_guardar("an_rev_save")

    with cr:
        if bank:
            r = dict(bank); r["ID_Pregunta"] = pid
            if txts and exact:
                r["opciones_list"] = txts; r["letra_correcta"] = clave[j]
            stcomponents.html(mathjax_html(render_question_card_html(r, show_sol=True, num=j + 1)),
                              height=300, scrolling=True)
        else:
            st.markdown("<div class='an-note'>Pregunta sin vincular: vincúlala en «Exámenes» para ver aquí "
                        "su enunciado.</div>", unsafe_allow_html=True)
        real = A.dificultad_real(it["acierto"])
        banco = str(bank.get("dificultad", "")) if bank else ""
        kd = it["kr20_sin"] - R["kr20"] if R["kr20"] == R["kr20"] else float("nan")
        st.markdown(
            "<div class='an-dl'>"
            f"<span>Aciertos</span><span>{_f(it['acierto'])} %</span>"
            f"<span>Corregido por azar</span><span>{_f(it['corregido'])} %</span>"
            f"<span>Blancos</span><span>{_f(it['blanco'])} %</span>"
            f"<span>Discriminación</span><span>{_f(it['disc'], 2)}</span>"
            f"<span>Fiabilidad si se quita</span><span>{_f(it['kr20_sin'], 3)} "
            f"<small>({'+' if kd >= 0 else ''}{_f(kd, 3)})</small></span>"
            f"<span>Dificultad real</span><span>{real or '—'}</span>"
            f"<span>Dificultad en el banco</span><span>{banco or '—'}</span></div>", unsafe_allow_html=True)
        if bank and real and banco and real.lower() != banco.lower():
            if st.button(f"Cambiar en el banco a «{real}»", key=f"an_chg_dif_{pid}", use_container_width=True):
                ok, msg = lib.actualizar_pregunta_excel_local(_ss.excel_path, _ss.excel_dfs, pid,
                                                              datos_de_fila(bank, dificultad=real))
                if ok:
                    sync_bloques_gsheets([bank.get("bloque", "")])
                    reload_db()
                    notify(f"✅ {pid}: dificultad cambiada a {real}.")
                    st.rerun()
                else:
                    st.error(msg)
        q = it["quintiles"]
        bars = "".join(f"<div style='height:{max(2, v if v == v else 0):.0f}%'><span>{_f(v)}</span></div>" for v in q)
        st.markdown("<div class='sec-title' style='margin-top:14px'>Acierto por grupos de nota</div>"
                    f"<div class='an-q5'>{bars}</div><div class='an-q5l'><span>20 % peor</span><span></span>"
                    "<span>medio</span><span></span><span>20 % mejor</span></div>", unsafe_allow_html=True)
        if pid:
            h = res_db[(res_db["ID_Pregunta"] == pid) & (res_db["ID_Examen"] != ex_id)]
            st.markdown("<div class='sec-title' style='margin-top:14px'>Historial de la pregunta</div>",
                        unsafe_allow_html=True)
            if h.empty:
                st.caption("No aparece en otros exámenes analizados.")
            for _, hr in h.iterrows():
                st.markdown(f"<div class='an-row'>{_ex_lbl.get(hr['ID_Examen'], hr['ID_Examen'])}<br>"
                            f"<small>{hr['Pct_Acierto']} % aciertos · discriminación {hr['Discriminacion'] or '—'}"
                            f"{' · ' + A.DECISIONES.get(hr['Decision'], '') if hr['Decision'] else ''}</small></div>",
                            unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════
# Pestañas
# ══════════════════════════════════════════════════════════════════════════════
with _guardar_box.container():
    _boton_guardar("an_top_save")
if "_an_tab_next" in _ss:
    _ss["an_tab"] = _ss.pop("_an_tab_next")
with st.container(key="seg_an_tab"):
    _tab = st.radio("Sección", ["Resumen", "Preguntas", "Alumnos"], horizontal=True, key="an_tab",
                    label_visibility="collapsed")


def _abrir_ficha(j):
    _ss["_an_tab_next"] = "Preguntas"
    _ss["an_rev_mode"] = True
    _ss["an_rev_j"] = j
    st.rerun()


t_res, t_pre, t_alu = (st.container() if _tab == x else None for x in ("Resumen", "Preguntas", "Alumnos"))

if t_res is not None:
  with t_res:
    notas = punt_new["Nota"]
    lo, hi = A.kr20_margen(R["C"])
    zona, zsub = _zona_kr(lo, hi, R["kr20"])
    n_rev = sum(1 for it in items if it["etiquetas"])
    n_grave = sum(1 for it in items if _sev(it) == "e")
    _kpis([
        ("Alumnos", str(R["N"]), f"{len(clave)} preguntas" + (f" · {len(modelos)} modelos" if len(modelos) > 1 else ""), ""),
        ("Nota media", _f(notas.mean(), 2), f"{int((notas >= 5).sum())} aprobados ({_f(100 * (notas >= 5).mean())} %)"
         + (" · con decisiones" if dec else ""), ""),
        ("Fiabilidad (KR-20)", _f(R["kr20"], 2), f"{zona}" + (f" · {zsub}" if zsub else ""),
         "ok" if R["kr20"] >= 0.8 else ("warn" if R["kr20"] >= 0.7 else "err")),
        ("Preguntas a revisar", str(n_rev), f"{n_grave} con problemas serios", "err" if n_grave else ("warn" if n_rev else "ok")),
    ])
    # En resumen, en una frase
    _ac = float(np.mean([it["acierto"] for it in items]))
    _top = sorted([j for j in range(len(items)) if items[j]["etiquetas"]],
                  key=lambda j: ({"e": 0, "w": 1}.get(_sev(items[j]), 2),
                                 items[j]["disc"] if items[j]["disc"] == items[j]["disc"] else -9))[:4]
    _fiab = "fiable" if R["kr20"] >= 0.8 else ("aceptable" if R["kr20"] >= 0.7 else "poco fiable")
    _dif = "fácil" if _ac >= 70 else ("de dificultad media" if _ac >= 50 else ("algo difícil" if _ac >= 40 else "difícil"))
    st.markdown(f"<div class='an-frase'><b>En resumen:</b> examen {_fiab} y {_dif} (acierto medio {_f(_ac)} %)"
                + (f". Conviene mirar antes de cerrar las notas: " + ", ".join(
                    f"la <b>{j + 1}</b> ({(items[j]['etiquetas'] or [''])[0].lower()})" for j in _top[:3]) + "."
                   if _top else ". Ninguna pregunta da problemas.") + "</div>", unsafe_allow_html=True)

    g1, g2 = st.columns([1.35, 1], gap="large")
    with g1:
        st.markdown("<div class='sec-title' style='margin-top:12px'>Distribución de notas</div>", unsafe_allow_html=True)
        import plotly.graph_objects as go
        _cls = np.clip(np.floor(notas.to_numpy()), 0, 9).astype(int)
        cnt = [int((_cls == b).sum()) for b in range(10)]
        fig = go.Figure(go.Bar(x=[f"{b}–{b + 1}" for b in range(10)], y=cnt,
                               marker_color=["#c0392b" if b < 5 else "#1d4a94" for b in range(10)]))
        fig.add_vline(x=4.5, line_dash="dash", line_color="#5b6475",
                      annotation_text="aprobado", annotation_position="top")
        fig.update_layout(height=250, margin=dict(l=10, r=10, t=14, b=10), yaxis_title="alumnos",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with g2:
        st.markdown("<div class='sec-title' style='margin-top:12px'>Cómo han salido las preguntas</div>", unsafe_allow_html=True)
        reales = [A.dificultad_real(it["acierto"]) for it in items]
        dd = [it["disc"] for it in items if it["disc"] == it["disc"]]
        _n = max(1, len(items))

        def _pila(titulo, partes):
            tot = max(1, sum(n for _, n, _ in partes))
            barra = "".join(f"<div style='width:{n / tot * 100:.1f}%;background:var(--{c})' title='{l}: {n}'></div>"
                            for l, n, c in partes if n)
            ley = "".join(f"<span><i style='background:var(--{c})'></i>{l} <b>{n}</b></span>" for l, n, c in partes)
            return f"<div class='an-pila'><div class='t'>{titulo}</div><div class='b'>{barra}</div><div class='l'>{ley}</div></div>"
        st.markdown(_pila("Dificultad real (aciertos)", [("Fáciles ≥70 %", reales.count("Facil"), "ok"),
                                                         ("Medias", reales.count("Media"), "primary"),
                                                         ("Difíciles <40 %", reales.count("Dificil"), "err")])
                    + _pila("Discriminación (separa a los que saben)", [
                        ("Bien", sum(1 for d in dd if d >= 0.3), "ok"), ("Regular", sum(1 for d in dd if 0.15 <= d < 0.3), "warn"),
                        ("Poco", sum(1 for d in dd if 0 <= d < 0.15), "muted"), ("Al revés", sum(1 for d in dd if d < 0), "err")]),
                    unsafe_allow_html=True)
        if ids and any(ids) and not df_preg.empty:
            comp = sum(1 for j, it in enumerate(items) if ids[j] in _bank and
                       str(_bank[ids[j]].get("dificultad", "")).lower() == reales[j].lower())
            n_l = sum(1 for p in ids if p in _bank)
            st.caption(f"La dificultad que tenían en el banco acierta en {comp} de {n_l} preguntas.")

    st.markdown("<div class='sec-title' style='margin-top:8px'>Qué revisar primero</div>", unsafe_allow_html=True)
    if not _top:
        st.caption("Ninguna pregunta tiene avisos.")
    else:
        _cq = st.columns(4, gap="small")
        for c_, j in zip(_cq, _top):
            with c_.container(border=True, key=f"an_topc_{_sev(items[j]) or 'b'}_{j}"):
                _en = str(_bank.get(ids[j], {}).get("enunciado", "")) if ids[j] else ""
                st.markdown(f"<div class='an-top'><b>{j + 1}</b><span>{_f(items[j]['acierto'])} % aciertos</span></div>"
                            f"<div class='an-top-e'>{(_en[:85] + '…') if len(_en) > 85 else (_en or 'sin vincular')}</div>"
                            f"{_chips(items[j]['etiquetas'][:2])}", unsafe_allow_html=True)
                if st.button("Ver ficha", key=f"an_top_{j}", use_container_width=True):
                    _abrir_ficha(j)

    b1, b2 = st.columns([1.35, 1], gap="large")
    with b1:
        if ids and any(p in _bank for p in ids):
            _bq = {}
            for j, it in enumerate(items):
                bb = _bank.get(ids[j])
                if bb:
                    _bq.setdefault(str(bb.get("bloque", "")), []).append(it["acierto"])
            st.markdown("<div class='sec-title' style='margin-top:8px'>Por bloques<span class='sec-meta'>acierto medio, "
                        "de peor a mejor</span></div>", unsafe_allow_html=True)
            st.markdown("".join(f"<div class='an-row' style='display:flex;gap:10px;align-items:center;margin:5px 0'>"
                                f"<span style='flex:2'>{nombre_bloque(b)} <small>({len(v)} preg.)</small></span>"
                                f"<span style='flex:1.4'>{_bar(np.mean(v))}</span><b style='width:52px;text-align:right'>{_f(np.mean(v))} %</b></div>"
                                for b, v in sorted(_bq.items(), key=lambda kv: np.mean(kv[1]))), unsafe_allow_html=True)
            with st.expander("Por temas"):
                tm = {}
                for j, it in enumerate(items):
                    bb = _bank.get(ids[j])
                    if bb:
                        tm.setdefault((str(bb.get("bloque", "")), str(bb.get("Tema", ""))), []).append(it["acierto"])
                st.markdown("".join(f"<div class='an-row' style='display:flex;gap:10px;align-items:center;margin:5px 0'>"
                                    f"<span style='flex:2'>{nombre_bloque(b)} · {nombre_tema(t)} <small>({len(v)} preg.)</small></span>"
                                    f"<span style='flex:1.4'>{_bar(np.mean(v))}</span><b style='width:52px;text-align:right'>"
                                    f"{_f(np.mean(v))} %</b></div>" for (b, t), v in sorted(tm.items(), key=lambda kv: np.mean(kv[1]))),
                            unsafe_allow_html=True)
    with b2:
        st.markdown("<div class='sec-title' style='margin-top:8px'>Por modelos</div>", unsafe_allow_html=True)
        if len(modelos) > 1:
            filas = ""
            for v in modelos:
                s_ = alumnos[alumnos["Modelo"] == v]
                ck = claves.get(v, "")
                if s_.empty or not ck:
                    continue
                Mv = A.respuestas_matriz(s_["Resp"].tolist(), len(ck))
                pv = A.puntuar(Mv, A.aceptadas(ck))
                kv = A.kr20((Mv == np.array(list(ck))).astype(float))
                filas += (f"<tr><td><b>{v}</b></td><td>{len(s_)}</td><td>{_f(pv['Nota'].mean(), 2)}</td>"
                          f"<td>{_f(100 * (pv['Nota'] >= 5).mean())} %</td><td>{_f(kv, 2)}</td></tr>")
            st.markdown("<table class='an-mod'><tr><th>Modelo</th><th>Alumnos</th><th>Media</th><th>Aprueban</th>"
                        f"<th>KR-20</th></tr>{filas}</table>", unsafe_allow_html=True)
        else:
            st.caption("Un solo modelo analizado.")

if t_pre is not None:
  with t_pre:
    f1, f2 = st.columns([3, 1.2], vertical_alignment="bottom")
    with f1.container(key="pill_an_filtro"):
        st.radio("Mostrar", ["Todas", "A revisar", "Muchos blancos", "Muy fáciles", "Muy difíciles"],
                 horizontal=True, key="an_filtro")
    f2.selectbox("Ordenar por", ["Posición", "Acierto (menor primero)", "Discriminación (menor primero)",
                                 "Blancos (mayor primero)"], key="an_orden")
    lista = _orden_filtrado()

    st.markdown("<div class='sec-title' style='margin-top:6px'>Mapa del examen</div>"
                "<div class='an-ley'><span><i class='f'></i>Fácil (≥70 % aciertos)</span><span><i class='m'></i>Media</span>"
                "<span><i class='h'></i>Difícil (&lt;40 %)</span><span><i class='pe'></i>problema serio</span>"
                "<span><i class='pw'></i>a revisar</span><span><i class='dk'></i>con decisión</span></div>",
                unsafe_allow_html=True)
    _vis = set(lista)
    _filtrado = _ss.get("an_filtro", "Todas") != "Todas"
    with st.container(horizontal=True, gap="small", key="an_mapa"):
        for j, it in enumerate(items):
            sv = _sev(it) or "b"
            dk = {"Facil": "f", "Media": "m", "Dificil": "h"}.get(A.dificultad_real(it["acierto"]), "m")
            on = _ss.get("an_rev_mode") and _ss.get("an_rev_j") == j
            dim = _filtrado and j not in _vis
            ayuda = (f"Pregunta {j + 1}: {_f(it['acierto'])} % aciertos · discrimina {_disc_txt(it['disc'])[0].lower()}"
                     + (f" · {'; '.join(it['etiquetas'])}" if it["etiquetas"] else ""))
            if st.button(f"{j + 1} · {_f(it['acierto'])}%",
                         key=f"anc_{dk}_{sv}_{'k' if j in dec else 'n'}_{'s' if on else 'n'}_{'x' if dim else 'n'}_{j}",
                         help=ayuda):
                _abrir_ficha(j)
    st.caption(f"Pulsa una pregunta para ver su ficha · {len(lista)} pregunta(s) en la lista"
               + (" (las demás, atenuadas)" if _filtrado else "") + ".")
    if _ss.get("an_rev_mode"):
        with st.container(border=True, key="card_an_ficha"):
            _ficha_pregunta()
        st.stop()

    _W = [0.4, 3.5, 1.1, 1.35, 1.1, 2.1, 0.9]
    hdr = st.columns(_W)
    for c, t in zip(hdr, ["Nº", "Pregunta", "Dificultad", "Aciertos", "Discrimina", "Aviso principal", ""]):
        c.markdown(f"<span class='dev-hd'>{t}</span>", unsafe_allow_html=True)
    for j in lista:
        it = items[j]
        with st.container(key=f"an_fila_{j}"):
            c = st.columns(_W, vertical_alignment="center")
            c[0].markdown(f"**{j + 1}**")
            enun = str(_bank.get(ids[j], {}).get("enunciado", "")) if ids[j] else ""
            c[1].markdown(f"<div class='an-row'><span class='an-t1'>{enun or '<i>sin vincular</i>'}</span>"
                          f"<small>{ids[j] or ''}{' · clave ' + clave[j]}"
                          f"{' · ' + A.DECISIONES[dec[j]['tipo']] if j in dec else ''}</small></div>",
                          unsafe_allow_html=True)
            real = A.dificultad_real(it["acierto"]) or ""
            banco = str(_bank.get(ids[j], {}).get("dificultad", "")) if ids[j] else ""
            dk = {"Facil": "f", "Media": "m", "Dificil": "d"}.get(real, "m")
            c[2].markdown(f"<span class='tag tag-{dk}' style='margin:0'>{ {'Facil': 'Fácil', 'Dificil': 'Difícil'}.get(real, real)}</span>"
                          + (f"<br><small class='an-sm'>banco: {banco}</small>" if banco and banco.lower() != real.lower() else ""),
                          unsafe_allow_html=True)
            c[3].markdown(f"{_bar(it['acierto'], True)}<small>{_f(it['acierto'])} %"
                          + (f" · {_f(it['blanco'])} % en blanco" if it["blanco"] >= 15 else "") + "</small>",
                          unsafe_allow_html=True)
            dt, dc = _disc_txt(it["disc"])
            c[4].markdown(f"<span class='an-disc {dc}'>{dt}</span>", unsafe_allow_html=True)
            et = it["etiquetas"]
            c[5].markdown((_chips(et[:1]) + (f"<small class='an-sm'> +{len(et) - 1} más</small>" if len(et) > 1 else ""))
                          if et else "<small class='an-sm'>—</small>", unsafe_allow_html=True)
            if c[6].button("Ver ficha", key=f"an_open_{j}", use_container_width=True):
                _abrir_ficha(j)

if t_alu is not None:
  with t_alu:
    st.markdown("<div class='an-note'>🔒 Esta tabla solo existe en esta sesión: no se guarda en ningún sitio. "
                "Descárgala si la necesitas.</div>", unsafe_allow_html=True)
    tabla = pd.DataFrame({
        "Alumno": sub_al["Alumno"].to_numpy(), "DNI": sub_al["DNI"].to_numpy(), "Modelo": sub_al["Modelo"].to_numpy(),
        "Aciertos": punt_new["Aciertos"].astype(int), "Fallos": punt_new["Fallos"].astype(int),
        "Blancos": punt_new["Blancos"].astype(int),
        "Puntuación corrector": sub_al["Total"].to_numpy(), "Puntuación nueva": punt_new["Total"].round(2),
        "Nota /10 nueva": punt_new["Nota"].round(2),
        "Cambio (nota)": (punt_new["Nota"] - punt_orig["Nota"]).round(2),
    })
    if dec:
        st.caption(f"Notas recalculadas con {len(dec)} decisión(es): "
                   + ", ".join(f"P{j + 1} {A.DECISIONES[d['tipo']].lower()}{' ' + d['letra'] if d.get('letra') else ''}"
                               for j, d in sorted(dec.items())))
    else:
        st.caption("Sin decisiones: las notas son las del corrector (penalización 0,33 por fallo).")
    st.dataframe(tabla, hide_index=True, use_container_width=True, height=420)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        tabla.to_excel(w, index=False, sheet_name="Notas")
    st.download_button("Descargar notas (.xlsx)", buf.getvalue(), file_name="notas_recalculadas.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="an_dl_notas")

st.write("")
_tab_examenes()
