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
import _recarga; _recarga.comprobar()   # recarga módulos compartidos si cambiaron (despliegues en Streamlit Cloud)

import os as _o, sys as _s
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import examen_lib_latex as lib
import analisis_lib as A
from app_theme import initial_sidebar, notify, get_estilo
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback, apply_theme, page_header,
    mathjax_html, render_question_card_html, nombre_bloque, nombre_tema,
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
res_db = A.get_resultados(dfs)
_ex_opts = ["__none__"] + exs["ID_Examen"].tolist()
_ex_lbl = {r["ID_Examen"]: f'{r["Curso"]} · {r["Convocatoria"] or "—"} · {r["Nombre"]}' for _, r in exs.iterrows()}
_ex_lbl["__none__"] = "Examen sin registrar (clave a mano)"

with st.container(border=True, key="card_an_src"):
    c1, c2 = st.columns([1.2, 1], gap="medium")
    with c1:
        if _ss.get("an_exam") not in _ex_opts:
            _ss["an_exam"] = _ex_opts[-1] if len(_ex_opts) > 1 else "__none__"
        ex_id = st.selectbox("Examen", _ex_opts, key="an_exam", format_func=lambda x: _ex_lbl.get(x, x),
                             help="Los exámenes exportados desde el Generador se registran solos. "
                                  "Los anteriores se pueden registrar en la pestaña «Exámenes».")
    with c2:
        up = st.file_uploader("Excel del corrector (.xls / .xlsx)", type=["xls", "xlsx"], key="an_upload",
                              help="Solo se lee en memoria: no se guarda en la app ni en la base de datos.")
    st.caption("🔒 Los datos de los alumnos solo se usan en esta sesión. En la base de datos compartida "
               "solo se guardan porcentajes por pregunta y las decisiones que tomes.")

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
    st.markdown("<div class='sec-title'>Exámenes registrados</div>", unsafe_allow_html=True)
    if exs.empty:
        st.info("Todavía no hay exámenes registrados. Se registran solos al exportar desde el Generador; "
                "los anteriores puedes registrarlos aquí abajo.")
    else:
        show = exs[["Curso", "Convocatoria", "Nombre", "Fecha", "N_Preguntas", "N_Modelos", "Origen",
                    "N_Alumnos", "Media", "KR20", "Fecha_Analisis"]].rename(columns={
            "N_Preguntas": "Preguntas", "N_Modelos": "Modelos", "N_Alumnos": "Alumnos",
            "Media": "Media /10", "KR20": "KR-20", "Fecha_Analisis": "Analizado"})
        st.dataframe(show.sort_values(["Curso", "Fecha"], ascending=False), hide_index=True,
                     use_container_width=True)
        with st.expander("Editar o borrar un examen"):
            e_id = st.selectbox("Examen", exs["ID_Examen"].tolist(), key="an_ed_id",
                                format_func=lambda x: _ex_lbl.get(x, x))
            row = exs[exs["ID_Examen"] == e_id].iloc[0]
            k1, k2, k3 = st.columns(3)
            n_cur = k1.text_input("Curso", row["Curso"], key=f"an_ed_cur_{e_id}")
            n_con = k2.text_input("Convocatoria", row["Convocatoria"], key=f"an_ed_con_{e_id}")
            n_nom = k3.text_input("Nombre", row["Nombre"], key=f"an_ed_nom_{e_id}")
            b1, b2, b3 = st.columns([1, 1, 2])
            if b1.button("Guardar cambios", type="primary", key="an_ed_save"):
                f = dict(row); f.update({"Curso": n_cur.strip(), "Convocatoria": n_con.strip(), "Nombre": n_nom.strip()})
                A.upsert_examen(dfs, f)
                guardar_hojas([A.SHEET_EXAMENES])
                notify("✅ Examen actualizado.")
                st.rerun()
            conf = b3.checkbox("Confirmo que quiero borrarlo (y su análisis guardado)", key="an_ed_conf")
            if b2.button("Borrar", key="an_ed_del", disabled=not conf):
                A.borrar_examen(dfs, e_id)
                guardar_hojas([A.SHEET_EXAMENES, A.SHEET_PREGUNTAS])
                _ss.get("an_dec", {}).pop(e_id, None)
                notify("🗑️ Examen borrado del registro.")
                st.rerun()

    st.markdown("<div class='sec-title' style='margin-top:18px'>Registrar un examen anterior</div>",
                unsafe_allow_html=True)
    st.caption("Para exámenes que no se hicieron con el Generador. Basta con la clave de cada modelo; "
               "vincular las preguntas con la base de datos es opcional.")
    with st.form("an_form_reg", clear_on_submit=False):
        r1, r2, r3, r4 = st.columns(4)
        g_cur = r1.text_input("Curso", A.curso_academico())
        g_con = r2.text_input("Convocatoria", placeholder="Ordinaria, Extraordinaria…")
        g_nom = r3.text_input("Nombre", placeholder="Examen Ordinario 24-25")
        g_fec = r4.date_input("Fecha", datetime.date.today())
        _sug = ""
        if data is not None:
            _vers = sorted(v for v in data["alumnos"]["Ver"].unique())
            lines = []
            for v in _vers:
                sub = data["alumnos"][data["alumnos"]["Ver"] == v]
                n = int(sub["Resp"].str.len().max() or 0)
                lines.append(f"{v or 'A'}={A.estimar_clave(A.respuestas_matriz(sub['Resp'].tolist(), n))}")
            _sug = "\n".join(lines)
        g_cl = st.text_area("Claves (una línea por modelo: A=DCAC…)", value=_sug, height=90,
                            help="Si has subido el Excel del corrector, se propone la clave más probable "
                                 "(la que marcan los mejores alumnos). Revísala.")
        if st.form_submit_button("Registrar examen", type="primary"):
            claves = {}
            for ln in g_cl.splitlines():
                if "=" in ln:
                    k, v = ln.split("=", 1)
                    v = "".join(c for c in v.upper() if c in A.LETRAS)
                    if v:
                        claves[(k.strip().upper() or "A")[:3]] = v
            if not g_nom.strip() or not claves:
                st.error("Falta el nombre o la clave.")
            else:
                eid = g_nom.strip()
                if eid in exs["ID_Examen"].tolist():
                    eid = f"{eid} ({g_cur.strip()})"
                n = len(next(iter(claves.values())))
                A.upsert_examen(dfs, {
                    "ID_Examen": eid, "Curso": g_cur.strip(), "Convocatoria": g_con.strip(), "Nombre": g_nom.strip(),
                    "Fecha": g_fec.isoformat(), "N_Preguntas": str(n), "N_Modelos": str(len(claves)),
                    "Origen": "Manual", "Claves": json.dumps(claves), "Posiciones": "{}", "Permutaciones": "{}"})
                guardar_hojas([A.SHEET_EXAMENES])
                _ss["an_exam"] = eid
                notify(f"✅ Examen «{g_nom.strip()}» registrado.")
                st.rerun()

    man = exs[exs["Origen"] == "Manual"]
    if not man.empty:
        st.markdown("<div class='sec-title' style='margin-top:18px'>Vincular preguntas (opcional)</div>",
                    unsafe_allow_html=True)
        st.caption("Indica qué pregunta de la base de datos ocupa cada posición del primer modelo. Así el "
                   "análisis muestra el enunciado y queda en el historial de la pregunta. Se proponen primero "
                   "las preguntas cuya respuesta correcta coincide con la clave (★).")
        l_id = st.selectbox("Examen", man["ID_Examen"].tolist(), key="an_ln_id",
                            format_func=lambda x: _ex_lbl.get(x, x))
        li = A.examen_info(man[man["ID_Examen"] == l_id].iloc[0])
        base = sorted(li["claves"])[0]
        clave = li["claves"][base]
        cur = li["posiciones"].get(base, [""] * len(clave))
        cur = (cur + [""] * len(clave))[:len(clave)]
        blqs = ["(todos)"] + list(st.session_state.bloques or [])
        f_b = st.selectbox("Buscar en el bloque", blqs, key="an_ln_blq",
                           format_func=lambda b: b if b == "(todos)" else nombre_bloque(b))
        pool = df_preg if f_b == "(todos)" else df_preg[df_preg["bloque"] == f_b]
        nuevos = []
        cols = st.columns(3)
        for j, L in enumerate(clave):
            cand = pool[pool["letra_correcta"].astype(str).str.upper() == L]["ID_Pregunta"].tolist()
            otros = [p for p in pool["ID_Pregunta"].tolist() if p not in cand]
            opts = [""] + cand + otros
            if cur[j] and cur[j] not in opts:
                opts.append(cur[j])
            star = set(cand)
            v = cols[j % 3].selectbox(
                f"Posición {j + 1} · clave {L}", opts, index=opts.index(cur[j]) if cur[j] in opts else 0,
                key=f"an_ln_{l_id}_{j}",
                format_func=lambda p: "— sin vincular —" if not p else
                (("★ " if p in star else "") + f"{p} · {str(_bank.get(p, {}).get('enunciado', ''))[:60]}"))
            nuevos.append(v)
        if st.button("Guardar vínculos", type="primary", key="an_ln_save"):
            f = dict(man[man["ID_Examen"] == l_id].iloc[0])
            pos = li["posiciones"]; pos[base] = nuevos
            f["Posiciones"] = json.dumps(pos)
            A.upsert_examen(dfs, f)
            guardar_hojas([A.SHEET_EXAMENES])
            notify(f"✅ {sum(1 for x in nuevos if x)} posiciones vinculadas.")
            st.rerun()


# ── Sin Excel: solo la gestión del registro ──────────────────────────────────
if data is None:
    st.markdown("<div class='an-note'>Sube el Excel que devuelve el corrector para ver el análisis. "
                "Mientras tanto, aquí tienes el registro de exámenes.</div>", unsafe_allow_html=True)
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
alumnos = alumnos.assign(Modelo=alumnos["Ver"].map(vmap).fillna(modelos[0]))

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
    if st.button("Guardar análisis", type="primary", key=key,
                 help="Guarda en la base de datos los porcentajes por pregunta y tus decisiones. "
                      "No guarda nada de los alumnos."):
        _guardar_analisis()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Modo revisión (página completa, pregunta a pregunta)
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


def _modo_revision():
    lista = _orden_filtrado() or list(range(len(items)))
    j = _ss.get("an_rev_j", lista[0])
    if j not in range(len(items)):
        j = lista[0]
    it = items[j]
    pos_l = lista.index(j) if j in lista else 0

    t1, t2, t3, t4 = st.columns([1.3, 3, 1, 1], vertical_alignment="center")
    if t1.button("← Volver al análisis", key="an_rev_back"):
        _ss["an_rev_mode"] = False
        st.rerun()
    t2.markdown(f"**Modo revisión** · pregunta {j + 1} de {len(items)} · "
                f"{pos_l + 1}/{len(lista)} en la lista «{_ss.get('an_filtro', 'Todas')}»")
    if t3.button("‹ Anterior", key="an_rev_prev", disabled=pos_l == 0, use_container_width=True):
        _ss["an_rev_j"] = lista[pos_l - 1]; st.rerun()
    if t4.button("Siguiente ›", key="an_rev_next", disabled=pos_l >= len(lista) - 1, use_container_width=True):
        _ss["an_rev_j"] = lista[pos_l + 1]; st.rerun()

    cl, cm, cr = st.columns([0.9, 2.6, 1.7], gap="medium")
    with cl.container(height=640, border=True):
        for jj in lista:
            iv = items[jj]
            mark = {"e": " ●", "w": " ◐"}.get(_sev(iv), "")
            d = " ✎" if jj in dec else ""
            if st.button(f"{jj + 1} · {_f(iv['acierto'])} %{mark}{d}", key=f"an_rev_go_{jj}",
                         type="primary" if jj == j else "secondary", use_container_width=True):
                _ss["an_rev_j"] = jj; st.rerun()

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


if _ss.get("an_rev_mode"):
    _modo_revision()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# Pestañas
# ══════════════════════════════════════════════════════════════════════════════
t_res, t_pre, t_alu, t_exa = st.tabs(["📊 Resumen", "❓ Preguntas", "🎓 Alumnos", "🗂️ Exámenes"])

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
    # ¿Coincide con el corrector? (con la clave original y sin decisiones)
    tot = sub_al["Total"].to_numpy(dtype=float)
    if np.isfinite(tot).any():
        dif_c = np.abs(punt_orig["Total"].to_numpy() - tot)
        n_mal = int((dif_c[np.isfinite(dif_c)] > 0.02).sum())
        if n_mal == 0:
            st.markdown('<span class="an-chip ok">✓ Las puntuaciones coinciden con las del corrector</span>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="an-chip warn">No coinciden con el corrector en {n_mal} alumno(s): '
                        f'revisa la clave o el modelo</span>', unsafe_allow_html=True)

    g1, g2 = st.columns([1.4, 1], gap="large")
    with g1:
        st.markdown("<div class='sec-title' style='margin-top:12px'>Distribución de notas</div>", unsafe_allow_html=True)
        import plotly.graph_objects as go
        _cls = np.clip(np.floor(notas.to_numpy()), 0, 9).astype(int)
        cnt = [int((_cls == b).sum()) for b in range(10)]
        fig = go.Figure(go.Bar(x=[f"{b}–{b + 1}" for b in range(10)], y=cnt,
                               marker_color=["#c0392b" if b < 5 else "#1d4a94" for b in range(10)]))
        fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="alumnos",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with g2:
        st.markdown("<div class='sec-title' style='margin-top:12px'>Perfil de las preguntas</div>", unsafe_allow_html=True)
        reales = [A.dificultad_real(it["acierto"]) for it in items]
        dd = [it["disc"] for it in items if it["disc"] == it["disc"]]
        prof = [("Fáciles (≥ 70 % aciertos)", reales.count("Facil")), ("Medias", reales.count("Media")),
                ("Difíciles (< 40 %)", reales.count("Dificil")),
                ("Discriminan bien (≥ 0,30)", sum(1 for d in dd if d >= 0.3)),
                ("Discriminan poco (< 0,15)", sum(1 for d in dd if d < 0.15))]
        h = ""
        for lbl, n in prof:
            h += (f"<div class='an-row' style='display:flex;gap:10px;align-items:center;margin:5px 0'>"
                  f"<span style='flex:1.4'>{lbl}</span><span style='flex:1'>{_bar(100 * n / len(items))}</span>"
                  f"<b style='width:28px;text-align:right'>{n}</b></div>")
        st.markdown(h, unsafe_allow_html=True)
        if ids and any(ids) and not df_preg.empty:
            comp = sum(1 for j, it in enumerate(items) if ids[j] in _bank and
                       str(_bank[ids[j]].get("dificultad", "")).lower() == reales[j].lower())
            n_l = sum(1 for p in ids if p in _bank)
            st.caption(f"La dificultad del banco acierta en {comp} de {n_l} preguntas vinculadas.")

    if ids and any(p in _bank for p in ids):
        st.markdown("<div class='sec-title' style='margin-top:6px'>Por temas</div>", unsafe_allow_html=True)
        tm = {}
        for j, it in enumerate(items):
            b = _bank.get(ids[j])
            if not b:
                continue
            k = (str(b.get("bloque", "")), str(b.get("Tema", "")))
            tm.setdefault(k, []).append(it["acierto"])
        h = ""
        for (b, t), v in sorted(tm.items(), key=lambda kv: np.mean(kv[1])):
            h += (f"<div class='an-row' style='display:flex;gap:10px;align-items:center;margin:5px 0'>"
                  f"<span style='flex:2'>{nombre_bloque(b)} · {nombre_tema(t)} <small>({len(v)} preg.)</small></span>"
                  f"<span style='flex:1.4'>{_bar(np.mean(v))}</span><b style='width:52px;text-align:right'>"
                  f"{_f(np.mean(v))} %</b></div>")
        st.markdown(h, unsafe_allow_html=True)

    if len(modelos) > 1:
        st.markdown("<div class='sec-title' style='margin-top:10px'>Por modelos</div>", unsafe_allow_html=True)
        h = ""
        for v in modelos:
            s = alumnos[alumnos["Modelo"] == v]
            ck = claves.get(v, "")
            if s.empty or not ck:
                continue
            Mv = A.respuestas_matriz(s["Resp"].tolist(), len(ck))
            pv = A.puntuar(Mv, A.aceptadas(ck))
            kv = A.kr20((Mv == np.array(list(ck))).astype(float))
            h += (f"<span class='an-chip'>Modelo {v}: {len(s)} alumnos · media {_f(pv['Nota'].mean(), 2)} · "
                  f"KR-20 {_f(kv, 2)}</span> ")
        st.markdown(h, unsafe_allow_html=True)
    st.write("")
    _boton_guardar("an_res_save")

with t_pre:
    f1, f2 = st.columns([3, 1.2], vertical_alignment="bottom")
    with f1.container(key="pill_an_filtro"):
        st.radio("Mostrar", ["Todas", "A revisar", "Muchos blancos", "Muy fáciles", "Muy difíciles"],
                 horizontal=True, key="an_filtro")
    f2.selectbox("Ordenar por", ["Posición", "Acierto (menor primero)", "Discriminación (menor primero)",
                                 "Blancos (mayor primero)"], key="an_orden")
    lista = _orden_filtrado()

    st.markdown("<div class='sec-title' style='margin-top:6px'>Mapa del examen"
                "<span class='sec-meta'> verde: bien · ámbar: a revisar · rojo: problema serio · "
                "borde azul: con decisión</span></div>", unsafe_allow_html=True)
    cells = ""
    for j, it in enumerate(items):
        cls = (_sev(it) + (" d" if j in dec else "")).strip()
        cells += (f"<div class='{cls}' title='{'; '.join(it['etiquetas']) or 'Bien'}'>{j + 1}"
                  f"<small>{_f(it['acierto'])}%</small></div>")
    st.markdown(f"<div class='an-map'>{cells}</div>", unsafe_allow_html=True)

    b1, b2 = st.columns([1, 3])
    if b1.button("Modo revisión", type="primary", key="an_go_rev", disabled=not lista,
                 help="Revisa las preguntas de la lista una a una, con todos los datos y las decisiones."):
        _ss["an_rev_mode"] = True
        _ss["an_rev_j"] = lista[0]
        st.rerun()
    b2.caption(f"{len(lista)} pregunta(s) en la lista.")

    hdr = st.columns([0.45, 3.2, 1.4, 0.8, 0.8, 2.6, 0.8])
    for c, t in zip(hdr, ["Nº", "Pregunta", "Aciertos", "Blancos", "Discr.", "Motivos", ""]):
        c.markdown(f"<small style='color:var(--muted,#888);font-weight:600'>{t}</small>", unsafe_allow_html=True)
    for j in lista:
        it = items[j]
        c = st.columns([0.45, 3.2, 1.4, 0.8, 0.8, 2.6, 0.8], vertical_alignment="center")
        c[0].markdown(f"**{j + 1}**")
        enun = str(_bank.get(ids[j], {}).get("enunciado", "")) if ids[j] else ""
        c[1].markdown(f"<div class='an-row'>{(enun[:90] + '…') if len(enun) > 90 else enun or '<small>sin vincular</small>'}"
                      f"<br><small>clave {clave[j]}{' · ' + ids[j] if ids[j] else ''}"
                      f"{' · ' + A.DECISIONES[dec[j]['tipo']] if j in dec else ''}</small></div>",
                      unsafe_allow_html=True)
        c[2].markdown(f"{_bar(it['acierto'], True)}<small>{_f(it['acierto'])} %</small>", unsafe_allow_html=True)
        c[3].markdown(f"<small>{_f(it['blanco'])} %</small>", unsafe_allow_html=True)
        c[4].markdown(f"<small>{_f(it['disc'], 2)}</small>", unsafe_allow_html=True)
        c[5].markdown(_chips(it["etiquetas"]), unsafe_allow_html=True)
        if c[6].button("Revisar", key=f"an_open_{j}"):
            _ss["an_rev_mode"] = True
            _ss["an_rev_j"] = j
            st.rerun()

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

with t_exa:
    _tab_examenes()
