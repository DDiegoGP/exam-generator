"""
pages/6_Examenes.py  –  Todos los exámenes guardados en la base de datos (borradores, exportados e importados).

Lista con su ficha, acciones (analizar, abrir en el Generador, editar, volver a importar, borrar) e
«Importar examen anterior» (archivos de versiones anteriores de la app) con comprobación de la clave
contra las notas del corrector. Ningún dato de alumnos se guarda: el Excel del corrector solo se lee en memoria.
"""
import datetime
import json
import os
import sys

import numpy as np
import pandas as pd
import streamlit as st

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import _recarga, importlib as _il_r, os as _os_r   # _recarga también se recarga a sí mismo si cambió
_recarga = (_il_r.reload(_recarga) if getattr(_recarga, "_MTIME", None) != _os_r.path.getmtime(_recarga.__file__) else _recarga)
_recarga.comprobar()

import analisis_lib as A
import examen_estado as E
from app_theme import initial_sidebar, notify
from app_utils import (
    init_session_state, render_sidebar, handle_oauth_callback, apply_theme, page_header,
    nombre_bloque, nombre_tema, temas_de_bloque, guardar_hojas,
)

st.set_page_config(page_title="Exámenes · Exámenes UCM", page_icon="🗂️", layout="wide",
                   initial_sidebar_state=initial_sidebar())
init_session_state()
handle_oauth_callback()
apply_theme("examenes")
render_sidebar()

page_header("🗂️", "Exámenes", "Los guardados en la base de datos: los ve cualquier profesor que la use")

if not st.session_state.db_connected:
    st.warning("⚠️ Conecta la base de datos antes de continuar.")
    st.stop()

_ss = st.session_state
dfs = _ss.excel_dfs
df_preg = _ss.df_preguntas
_bank = df_preg.set_index("ID_Pregunta").to_dict("index") if not df_preg.empty else {}
exs = A.get_examenes(dfs)
_ex_lbl = {r["ID_Examen"]: f'{r["Curso"]} · {r["Convocatoria"] or "—"} · {r["Nombre"]}' for _, r in exs.iterrows()}
data = _ss.get("an_data")          # Excel del corrector subido en Análisis (para proponer claves)
_TAG_EST = {"Borrador": "w", "Exportado": "f", "Importado": "u", "Manual": "n"}


def _est(r) -> str:
    return "Manual" if r.get("Origen") == "Manual" and not r.get("Estado") else E.estado_de(r)


def _num(v, d=2) -> str:
    try:
        return f"{float(v):.{d}f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(v or "—")


def _fecha(s) -> str:
    return E.fecha_es(str(s or "")[:10]) if s else "—"


# ══════════════════════════════════════════════════════════════════════════════
# Importar examen anterior
# ══════════════════════════════════════════════════════════════════════════════
_TAG = {"bd": ("En la BD", "f"), "cambiada": ("En la BD · texto cambiado", "w"), "nueva": ("No está", "d")}


def _imp_reset():
    for k in [k for k in list(_ss.keys()) if str(k).startswith("imp_")]:
        _ss.pop(k, None)


def _steps(a: int) -> str:
    return "".join(f"<span class='imp-step{' on' if i == a else ''}'>{t}</span>"
                   for i, t in enumerate(("1 · Archivos", "2 · Revisar preguntas", "3 · Comprobar y registrar")))


@st.dialog("Editar antes de añadir", width="large")
def _imp_editar(i: int):
    res = _ss["imp_res"]
    q = res["base"][i]
    bls = list(_ss.bloques or [])
    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1.4])
    b = c1.selectbox("Bloque", bls, index=bls.index(q["bloque"]) if q["bloque"] in bls else 0, key=f"imp_e_b_{i}",
                     format_func=nombre_bloque)
    tms = temas_de_bloque(b) or [str(t) for t in range(1, 60)]
    t = c2.selectbox("Tema", tms, index=tms.index(str(q["tema"])) if str(q["tema"]) in tms else 0, key=f"imp_e_t_{i}",
                     format_func=nombre_tema)
    difs = ["Facil", "Media", "Dificil"]
    d = c3.selectbox("Dificultad", difs, index=difs.index(q["dificultad"]) if q["dificultad"] in difs else 1, key=f"imp_e_d_{i}")
    et = c4.text_input("Etiqueta", q.get("etiqueta", ""), key=f"imp_e_et_{i}")
    en = st.text_area("Enunciado", q["enun"], height=110, key=f"imp_e_en_{i}")
    ops = [st.text_input(f"Opción {L}", (q["ops"] + [""] * 4)[k], key=f"imp_e_o{L}_{i}") for k, L in enumerate("ABCD")]
    okL = st.radio("Respuesta correcta", list("ABCD"), index="ABCD".index(q["ok"]) if q.get("ok") in list("ABCD") else 0,
                   horizontal=True, key=f"imp_e_ok_{i}")
    if st.button("Guardar cambios", type="primary", key=f"imp_e_save_{i}"):
        q.update({"bloque": b, "tema": t, "dificultad": d, "etiqueta": et.strip(), "enun": en.strip(),
                  "ops": [o.strip() for o in ops], "ok": okL, "editada": True})
        st.rerun()


def _imp_paso1():
    import importar_examen as IMP
    with st.container(border=True, key="card_imp1"):
        h1, h2 = st.columns([5, 1], vertical_alignment="center")
        h1.markdown(f"**Importar examen anterior**" + (f" · vuelve a importar «{_ss['imp_reimp']}»" if _ss.get("imp_reimp") else "")
                    + f"<br>{_steps(0)}", unsafe_allow_html=True)
        if h2.button("Cancelar", key="imp_cancel1", use_container_width=True):
            _imp_reset(); st.rerun()
        c1, c2 = st.columns(2, gap="medium")
        ups = c1.file_uploader("Archivos del examen: lo que tengas (PDF o Word de cada modelo, METADATA, claves, _SOL.tex)",
                               type=["csv", "xlsx", "xls", "tex", "docx", "pdf"], accept_multiple_files=True, key="imp_files",
                               help="Puedes arrastrar todos los que tengas: la app elige cuál usar para cada cosa.")
        corr = c2.file_uploader("Excel del corrector (opcional, recomendado)", type=["xls", "xlsx"], key="imp_corr_up",
                                help="Sirve para comprobar que la clave reproduce sus notas. Solo se lee en memoria: "
                                     "no se guarda en la app ni en la base de datos.")
        if corr is not None and _ss.get("_imp_corr_name") != (corr.name, corr.size):
            try:
                _ss["imp_corr"] = A.parse_corrector(corr.getvalue())
                _ss["_imp_corr_name"] = (corr.name, corr.size)
            except Exception as e:
                c2.error(f"No se ha podido leer el Excel del corrector: {e}")
        if corr is None:
            _ss.pop("imp_corr", None); _ss.pop("_imp_corr_name", None)
        if _ss.get("imp_corr"):
            c2.caption(f"✓ {len(_ss['imp_corr']['alumnos'])} alumnos leídos (solo en memoria).")
        arch = [IMP.leer(u.name, u.getvalue()) for u in (ups or [])]
        if arch:
            el = IMP.elegir(arch)
            if not el["docs"]:
                st.markdown("<div class='imp-warn'><b>Falta el examen tal como se imprimió</b> (el PDF o el Word de cada "
                            "modelo). Sin él se usará el orden de preguntas y opciones del _SOL.tex o de los metadatos. Si el "
                            "examen se retocó o se volvió a exportar antes de imprimirlo, la clave no será la buena. Súbelo si lo "
                            "tienes; si no, el paso 3 comprobará la clave con el corrector.</div>", unsafe_allow_html=True)
            st.markdown("<div class='imp-f imp-h'><span>Archivo</span><span>Contiene</span><span>Se usa para</span></div>"
                        + "".join(f"<div class='imp-f'><code>{u.name}</code><span>{a['desc']}</span>"
                                  f"<span class='tag tag-{p[1]}'>{p[0]}</span></div>"
                                  for u, a, p in zip(ups, arch, el["papel"])), unsafe_allow_html=True)
        r1, r2, r3, r4 = st.columns([1, 1.2, 1, 2])
        prev = _ss.get("imp_prev") or {}
        cur = r1.text_input("Curso", prev.get("Curso") or A.curso_academico(), key="imp_cur")
        con = r2.text_input("Convocatoria", prev.get("Convocatoria") or "Ordinaria", key="imp_con")
        f0 = prev.get("Fecha")
        try:
            f0 = datetime.date.fromisoformat(f0[:10]) if f0 else datetime.date.today()
        except ValueError:
            f0 = datetime.date.today()
        fec = r3.date_input("Fecha en que se hizo", f0, format="DD/MM/YYYY", key="imp_fec")
        asig = (_ss.get("cfg_general", {}) or {}).get("asignatura", "") or "Física Médica"
        nom = r4.text_input("Nombre", prev.get("Nombre") or E.nombre_auto(con, asig, fec.strftime("%d/%m/%Y")), key="imp_nom")
        ok = any(a["tipo"] in ("meta", "tex", "docx") for a in arch)
        if st.button("Siguiente: revisar preguntas", type="primary", key="imp_next", disabled=not ok):
            with st.spinner("Comparando con la base de datos…"):
                r = IMP.montar(arch, df_preg)
            if r.get("error"):
                st.error(r["error"])
            else:
                r["datos"] = {"cur": cur.strip(), "con": con.strip(), "fec": fec.isoformat(), "nom": nom.strip()}
                _ss["imp_res"], _ss["imp_paso"] = r, 2
                st.rerun()


def _imp_paso2(res):
    d = res["datos"]
    with st.container(border=True, key="card_imp2"):
        h1, h2 = st.columns([5, 1], vertical_alignment="center")
        h1.markdown(f"**Importar examen anterior · {d['nom']}**<br>{_steps(1)}", unsafe_allow_html=True)
        if h2.button("Cancelar", key="imp_cancel", use_container_width=True):
            _imp_reset(); st.rerun()
        for w in res["avisos"]:
            st.warning(w)
        base = res["base"]
        cnt = {k: sum(1 for q in base if q["estado"] == k) for k in _TAG}
        with st.container(key="pill_imp_f"):
            f = st.radio("Mostrar", ["Todas", "En la BD", "Texto cambiado", "No están"], horizontal=True,
                         key="imp_filtro", label_visibility="collapsed",
                         format_func=lambda x: f"{x} · {len(base) if x == 'Todas' else cnt[{'En la BD': 'bd', 'Texto cambiado': 'cambiada', 'No están': 'nueva'}[x]]}")
        fk = {"En la BD": "bd", "Texto cambiado": "cambiada", "No están": "nueva"}.get(f)
        otros = {v: {i: j + 1 for j, i in enumerate(m["orden"])} for v, m in res["modelos"].items() if v != res["ref"]}
        W = [0.7, 0.6, 4.2, 1.6, 2.4]
        hd = st.columns(W)
        for c, t in zip(hd, [res["ref"], " · ".join(otros) or "", "Pregunta", "Estado", "Qué hacer"]):
            c.markdown(f"<span class='dev-hd'>{t}</span>", unsafe_allow_html=True)
        with st.container(height=520, key="card_imp_tabla"):
            for i, q in enumerate(base):
                if fk and q["estado"] != fk:
                    continue
                r = st.columns(W, vertical_alignment="center")
                r[0].markdown(f"**{q['label']}**")
                r[1].markdown(" · ".join(str(o.get(q["pos"], "—")) for o in otros.values()) if q["pos"] is not None else "—")
                r[2].markdown(f"<div class='devq-t' style='font-weight:500'>{q['enun'][:140]}</div>"
                              f"<div class='devq-s'>{q['id'] or 'nueva'}{' · editada' if q.get('editada') else ''}</div>",
                              unsafe_allow_html=True)
                lbl, k = _TAG[q["estado"]]
                r[3].markdown(f"<span class='tag tag-{k}'>{lbl}</span>", unsafe_allow_html=True)
                with r[4]:
                    if q["estado"] == "bd":
                        st.caption("Se vincula")
                    elif q["estado"] == "cambiada":
                        cc1, cc2 = st.columns([1, 1.4])
                        with cc1.popover("Comparar"):
                            st.markdown(f"**En el examen**\n\n{q['enun']}")
                            st.markdown(f"**En la base de datos ({q['id']})**\n\n{_bank.get(q['id'], {}).get('enunciado', '')}")
                        q["vincular"] = cc2.selectbox("acción", ["Vincular", "Añadir como nueva"], index=0 if q["vincular"] else 1,
                                                      key=f"imp_v_{i}", label_visibility="collapsed") == "Vincular"
                        if not q["vincular"] and st.button("Editar", key=f"imp_ed_{i}"):
                            _imp_editar(i)
                    else:
                        cc1, cc2 = st.columns([1.4, 1])
                        q["anadir"] = cc1.checkbox("Añadir a la BD", value=q["anadir"], key=f"imp_a_{i}")
                        if cc2.button("Editar", key=f"imp_ed_{i}", disabled=not q["anadir"]):
                            _imp_editar(i)
                        st.caption(f"{q['bloque'] or 'sin bloque'} · T{q['tema'] or '?'}"
                                   + (f" · correcta {q['ok']}" if q.get("ok") else " · correcta sin indicar")
                                   + (f" · «{q['etiqueta']}»" if q.get("etiqueta") else "")
                                   + (" · no se analiza" if q["bis"] else ""))
        nuevas = _nuevas(res)
        falta = [q["label"] for q in nuevas if not q["bloque"] or not q.get("ok")]
        if falta:
            st.warning(f"Revisa con «Editar» el bloque y la respuesta correcta de: {', '.join(falta)}")
        f1, f2 = st.columns([1, 3])
        if f1.button("‹ Archivos", key="imp_back"):
            _ss.pop("imp_res", None); _ss["imp_paso"] = 1; st.rerun()
        if f2.button("Siguiente: comprobar y registrar", type="primary", key="imp_go3", disabled=bool(falta)):
            _ss["imp_paso"] = 3; st.rerun()


def _nuevas(res):
    return [q for q in res["base"] if (q["estado"] == "nueva" and q["anadir"]) or (q["estado"] == "cambiada" and not q["vincular"])]


def _matriz_modelo(res, v):
    """(M, totales) de los alumnos del modelo v en el Excel del corrector, o (None, None)."""
    corr = _ss.get("imp_corr")
    if not corr:
        return None, None
    al = corr["alumnos"]
    vmap = A.mapa_ver(al["Ver"].unique().tolist(), sorted(res["modelos"]))
    sub = al[al["Ver"].map(vmap) == v]
    if sub.empty:
        return None, None
    return A.respuestas_matriz(sub["Resp"].tolist(), res["n"]), sub["Total"].to_numpy(dtype=float)


def _acc_modelo(m):
    out = []
    for j, k in enumerate(m["clave"]):
        d_ = (m.get("decisiones") or {}).get(j)
        k = k or "A"
        if d_ and d_[0] == "anular":
            out.append(None)
        elif d_ and d_[0] == "buena":
            out.append(set("ABCD"))
        elif d_ and d_[0] == "aceptar":
            out.append({k[0], d_[1]})
        else:
            out.append(set(k))
    return out


def _imp_paso3(res):
    d = res["datos"]
    with st.container(border=True, key="card_imp3"):
        h1, h2 = st.columns([5, 1], vertical_alignment="center")
        h1.markdown(f"**Importar examen anterior · {d['nom']}**<br>{_steps(2)}", unsafe_allow_html=True)
        if h2.button("Cancelar", key="imp_cancel3", use_container_width=True):
            _imp_reset(); st.rerun()
        if not _ss.get("imp_corr"):
            st.markdown("<div class='imp-warn'>No has subido el Excel del corrector (paso 1): no se puede comprobar que la "
                        "clave reproduce sus notas. Puedes registrar igualmente y comprobarlo después en Análisis.</div>",
                        unsafe_allow_html=True)
        else:
            st.caption("La app puntúa a cada alumno con la clave y lo compara con la nota que dio el corrector. "
                       "Si no cuadran, el análisis no sería fiable.")
        cols = st.columns(len(res["modelos"]), gap="medium")
        elegidos = []
        for c, (v, m) in zip(cols, sorted(res["modelos"].items())):
            with c.container(border=True, key=f"card_imp_m_{v}"):
                M, T = _matriz_modelo(res, v)
                ok_n = tot = 0
                if M is not None:
                    ok_n, tot = A.cuadran(M, _acc_modelo(m), T)
                    m["comprobado"] = f"{ok_n}/{tot}"
                bien = tot and ok_n == tot
                st.markdown(f"<div class='imp-mh'><b>Modelo {v}</b>"
                            + (f"<span class='tag tag-{'f' if bien else 'd'}'>{ok_n}/{tot} cuadran</span>" if tot
                               else "<span class='tag tag-n'>sin comprobar</span>") + "</div>", unsafe_allow_html=True)
                st.caption((f"Orden y opciones del {m['fuente']}" if not m.get("propuesto") else
                            f"Sin documento: orden deducido ({m['fuente']}); opciones {m['opciones']}"))
                if M is not None and not bien:
                    k_cl = "".join((x or "A")[0] for x in m["clave"])
                    prop = _ss.get(f"imp_prop_{v}")
                    if prop is None:      # se busca sola (tarda menos de un segundo)
                        prop = _ss[f"imp_prop_{v}"] = A.buscar_clave(M, k_cl, T)
                    elegida = _ss.get(f"imp_elec_{v}")
                    dec_ = {j: {"tipo": tp, "letra": L} for j, tp, L in prop}
                    n2, _ = A.cuadran(M, A.aceptadas(k_cl, dec_), T)
                    if prop and n2 >= 0.9 * tot and len(prop) <= 8:
                        def _desc(j, tp, L):
                            en = _bank.get(res["items"][m["orden"][j]].get("id") or "", {}).get(
                                "enunciado", res["items"][m["orden"][j]]["enun"])
                            hace = (f"usó la <b>{L}</b>" if tp == "cambiar" else
                                    f"dio por buena también la <b>{L}</b>" if tp == "aceptar" else
                                    "la dio por buena para todos" if tp == "buena" else "la anuló")
                            return (f"<div class='imp-cb'><b>{j + 1}</b><span>{en[:80]}</span>"
                                    f"<span>examen: <b>{(m['clave'][j] or '—')[0]}</b></span><span>corrector: {hace}</span></div>")
                        st.markdown(f"<div class='imp-expl'>Las notas del corrector no salen con la clave del examen impreso. "
                                    f"Salen exactas ({n2}/{tot}) si en {'esta pregunta' if len(prop) == 1 else f'estas {len(prop)} preguntas'} "
                                    f"se corrigió así:</div>" + "".join(_desc(*x) for x in prop), unsafe_allow_html=True)
                        st.markdown("**¿Con qué clave quieres analizarlo?**")
                        b1, b2 = st.columns(2)
                        if b1.button("La del examen impreso", key=f"imp_mant_{v}", use_container_width=True,
                                     type="primary" if elegida == "examen" else "secondary",
                                     help="Si el corrector se equivocó. En el Análisis verás qué alumnos cambian de nota."):
                            if elegida == "corrector":      # deshacer lo aplicado
                                for j, tp, L in prop:
                                    m["clave"][j] = m.get("_clave_orig", m["clave"])[j]
                                    (m.get("decisiones") or {}).pop(j, None)
                            _ss[f"imp_elec_{v}"] = "examen"
                            st.rerun()
                        if b2.button("La que usó el corrector", key=f"imp_usa_{v}", use_container_width=True,
                                     type="primary" if elegida == "corrector" else "secondary",
                                     help="Reproduce exactamente sus notas (también sus errores, si los hubo)."):
                            if elegida != "corrector":
                                m["_clave_orig"] = list(m["clave"])
                                for j, tp, L in prop:
                                    if tp == "cambiar":
                                        m["clave"][j] = L
                                    else:
                                        m.setdefault("decisiones", {})[j] = (tp, L)
                            _ss[f"imp_elec_{v}"] = "corrector"
                            st.rerun()
                    else:
                        st.markdown(f"<div class='imp-warn'>Ninguna clave razonable reproduce las notas del corrector en este "
                                    f"modelo: lo más probable es que el orden de preguntas u opciones no sea el que se "
                                    f"imprimió. <b>No conviene analizarlo</b> así ({tot} alumnos).</div>", unsafe_allow_html=True)
                elec = _ss.get(f"imp_elec_{v}")
                defecto = bool(bien) or bool(elec) or (not tot and not m.get("propuesto"))
                if st.checkbox(f"Analizar el modelo {v}", value=defecto, key=f"imp_m_{v}_{bool(bien)}_{elec}",
                               disabled=bool(tot) and not bien and not elec and bool(_ss.get(f"imp_prop_{v}")),
                               help="Elige antes con qué clave analizarlo." if tot and not bien and not elec else None):
                    elegidos.append(v)
        st.caption("Los alumnos de los modelos que no marques no se analizan.")
        nuevas = _nuevas(res)
        f1, f2 = st.columns([1, 3])
        if f1.button("‹ Revisar preguntas", key="imp_back3"):
            _ss["imp_paso"] = 2; st.rerun()
        lbl = (f"Registrar examen ({', '.join(elegidos) or 'ningún modelo'})"
               + (f" y añadir {len(nuevas)} pregunta(s)" if nuevas else ""))
        if f2.button(lbl, type="primary", key="imp_ok", disabled=not elegidos):
            _imp_registrar(res, elegidos, nuevas)


def _imp_registrar(res, elegidos, nuevas):
    import importar_examen as IMP
    from app_utils import insertar_preguntas, marcar_preguntas_usadas
    d = res["datos"]
    reimp = _ss.get("imp_reimp")
    if d["nom"] in set(A.get_examenes(dfs)["ID_Examen"]) and d["nom"] != reimp:
        st.error(f"Ya existe un examen llamado «{d['nom']}». Vuelve al paso 1 y cambia el nombre.")
        return
    with st.spinner("Añadiendo preguntas y registrando el examen…"):
        if nuevas:
            ids = insertar_preguntas([{
                "enunciado": q["enun"], "opciones_list": (q["ops"] + [""] * 4)[:4], "letra_correcta": q.get("ok") or "A",
                "bloque": q["bloque"], "tema": str(q["tema"]), "dificultad": q["dificultad"] or "Media",
                "usada": d["fec"], "comentario": q.get("etiqueta", ""), "objetivo": "", "solucion": "", "notas": ""}
                for q in nuevas])
            for q, nid in zip(nuevas, ids):
                q["id"], q["perm"] = nid, "ABCD"
        _dfp = _ss.df_preguntas.set_index("ID_Pregunta")
        vinc = [q["id"] for q in res["items"] if q.get("id") and q["id"] in _dfp.index
                and str(_dfp.loc[q["id"], "usada"] or "")[:10] < d["fec"]]
        if vinc:
            marcar_preguntas_usadas(vinc, d["fec"])
        dd = _ss.excel_dfs
        if reimp:      # volver a importar: se sustituye el registro y su análisis guardado
            A.borrar_examen(dd, reimp)
        fila, extra = IMP.registro(res, elegidos, d["nom"], d["cur"], d["con"], d["fec"])
        _mant = [v for v in elegidos if _ss.get(f"imp_elec_{v}") == "examen"]
        if _mant:          # clave del examen mantenida a propósito aunque no cuadre con el corrector
            _c = json.loads(fila["Contenido"]); _c["clave_del_examen"] = _mant
            fila["Contenido"] = json.dumps(_c, ensure_ascii=False)
        A.upsert_examen(dd, fila)
        if extra:      # respuestas dobles, buenas para todos y anuladas → decisiones del análisis
            pr = A.get_resultados(dd)
            filas = [{"ID_Examen": d["nom"], "Pos": str(p), "ID_Pregunta": pid, "Decision": tp,
                      "Letra_Extra": L or "", "Fecha": d["fec"]} for p, pid, tp, L in extra]
            dd[A.SHEET_PREGUNTAS] = pd.concat([pr, pd.DataFrame([{c: f.get(c, "") for c in A.PR_COLS} for f in filas])],
                                              ignore_index=True)
        guardar_hojas([A.SHEET_EXAMENES, A.SHEET_PREGUNTAS])
    _ss["ex_sel"] = d["nom"]
    _imp_reset()
    notify(f"✅ Examen «{d['nom']}» importado" + (f" y {len(nuevas)} pregunta(s) añadidas" if nuevas else "") + ".")
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Lista y ficha
# ══════════════════════════════════════════════════════════════════════════════
@st.dialog("Editar datos del examen")
def _dlg_editar(row):
    c1, c2 = st.columns(2)
    nom = c1.text_input("Nombre", row["Nombre"], key="exed_nom")
    cur = c2.text_input("Curso", row["Curso"], key="exed_cur")
    con = c1.text_input("Convocatoria", row["Convocatoria"], key="exed_con")
    try:
        f0 = datetime.date.fromisoformat(str(row["Fecha"])[:10])
    except ValueError:
        f0 = datetime.date.today()
    fec = c2.date_input("Fecha en que se hizo", f0, format="DD/MM/YYYY", key="exed_fec")
    if st.button("Guardar", type="primary", key="exed_ok"):
        f = dict(row)
        f.update({"Nombre": nom.strip() or row["Nombre"], "Curso": cur.strip(), "Convocatoria": con.strip(),
                  "Fecha": fec.isoformat()})
        A.upsert_examen(dfs, f)
        guardar_hojas([A.SHEET_EXAMENES])
        notify("✅ Datos del examen guardados.")
        st.rerun()


def _ficha(row):
    info = A.examen_info(row)
    est = _est(row)
    c = A._j(row.get("Contenido", ""), {})
    creado = row.get("Creado") or row.get("Actualizado") or row.get("Fecha_Analisis") or ""
    st.markdown(f"<div class='dev-hd'>Examen</div><div class='exf-t'>{row['Nombre'] or row['ID_Examen']}"
                f"<span class='tag tag-{_TAG_EST.get(est, 'n')}'>{est}</span></div>"
                f"<div class='devq-s'>{row['Curso'] or '—'} · {row['Convocatoria'] or '—'}</div>"
                f"<div class='exf-d'>Se hizo el <b>{_fecha(row['Fecha'])}</b> · "
                f"{'importado' if est == 'Importado' else 'guardado'} el {_fecha(creado)}"
                f"{' por ' + row['Usuario'].split('@')[0] if row.get('Usuario') else ''}</div>", unsafe_allow_html=True)
    mods = sorted(info["claves"]) or []
    comp = A._j(row.get("Comprobacion", ""), {})
    n_dev = len(c.get("dev") or [])
    kd = [("Preguntas", row["N_Preguntas"] or len(c.get("test") or []) or "—",
           f"de test{f' + {n_dev} de desarrollo' if n_dev else ''}"),
          ("Modelos", ", ".join(mods) or "—", "registrados con su clave" if mods else "aún sin clave"),
          ("Alumnos analizados", row["N_Alumnos"] or "—", f"media {_num(row['Media'])}" if row["Media"] else "sin analizar"),
          ("Fiabilidad", _num(row["KR20"]) if row["KR20"] else "—", "KR-20" + (f" · analizado el {_fecha(row['Fecha_Analisis'])}" if row["Fecha_Analisis"] else ""))]
    st.markdown("<div class='exf-k'>" + "".join(f"<div><small>{l}</small><b>{v}</b><span>{s}</span></div>" for l, v, s in kd)
                + "</div>", unsafe_allow_html=True)
    for v in mods:
        k = info["claves"][v]
        cmp_ = comp.get(v)
        st.markdown(f"<div class='dev-hd' style='margin-top:8px'>Clave del modelo {v}</div>"
                    f"<div class='exf-key'>{' '.join(k[i:i + 10] for i in range(0, len(k), 10))}</div>"
                    + (f"<div class='exf-ok {'b' if cmp_.split('/')[0] == cmp_.split('/')[1] else 'm'}'>"
                       f"{'✓' if cmp_.split('/')[0] == cmp_.split('/')[1] else '✗'} Notas comprobadas con el corrector: {cmp_} alumnos</div>"
                       if cmp_ else ""), unsafe_allow_html=True)
    ids = (info["posiciones"].get(mods[0]) if mods else None) or c.get("test") or []
    blq = {}
    for p in ids:
        b = _bank.get(p, {}).get("bloque")
        if b:
            blq[b] = blq.get(b, 0) + 1
    if blq:
        mx = max(blq.values())
        st.markdown("<div class='dev-hd' style='margin-top:10px'>Por bloque</div>"
                    + "".join(f"<div class='exf-b'><span>{b}</span><div class='exf-bar'><div style='width:{100 * n / mx:.0f}%'></div></div><b>{n}</b></div>"
                              for b, n in sorted(blq.items(), key=lambda kv: kv[0])), unsafe_allow_html=True)
    st.write("")
    b1, b2 = st.columns(2)
    if b1.button("Analizar", type="primary", key="exf_an", use_container_width=True, disabled=est == "Borrador" or not mods):
        _ss["_an_exam_next"] = row["ID_Examen"]
        st.switch_page("pages/5_Analisis.py")
    if b2.button("Abrir en el Generador", key="exf_gen", use_container_width=True,
                 disabled=not (c.get("test") or row["Posiciones"] not in ("", "{}"))):
        notify(E.abrir(row))
        st.switch_page("pages/2_Generador.py")
    b3, b4 = st.columns(2)
    if b3.button("Editar datos", key="exf_ed", use_container_width=True):
        _dlg_editar(row)
    if b4.button("Volver a importar", key="exf_re", use_container_width=True, disabled=est != "Importado",
                 help="Repite la importación con otros archivos; sustituye este registro y su análisis guardado."):
        _imp_reset()
        _ss.update({"imp_paso": 1, "imp_reimp": row["ID_Examen"], "imp_prev": dict(row)})
        st.rerun()
    if st.button("Borrar examen", key="exf_del", use_container_width=True):
        _ss["_exf_del"] = row["ID_Examen"]
    if _ss.get("_exf_del") == row["ID_Examen"]:
        st.warning("Se borra el examen y su análisis guardado (las preguntas de la base de datos no se tocan).")
        d1, d2 = st.columns(2)
        if d1.button("Sí, borrar", type="primary", key="exf_del_ok", use_container_width=True):
            A.borrar_examen(dfs, row["ID_Examen"])
            guardar_hojas([A.SHEET_EXAMENES, A.SHEET_PREGUNTAS])
            if _ss.get("draft_id") == row["ID_Examen"]:
                _ss["draft_id"] = None
            _ss.pop("_exf_del", None); _ss.pop("ex_sel", None)
            notify("🗑️ Examen borrado.")
            st.rerun()
        if d2.button("Cancelar", key="exf_del_no", use_container_width=True):
            _ss.pop("_exf_del", None); st.rerun()


def _lista():
    if exs.empty:
        st.info("Todavía no hay exámenes guardados. Se guardan al exportarlos desde el Generador (y los borradores "
                "mientras trabajas); los anteriores se importan con «Importar examen anterior».")
    t1, t2 = st.columns([4, 1.4], vertical_alignment="center")
    allx = exs.assign(_est=[_est(r) for r in exs.to_dict("records")])
    cnt = allx["_est"].value_counts().to_dict()
    with t1.container(key="pill_ex_f"):
        f = st.radio("Mostrar", ["Todos", "Borradores", "Exportados", "Importados"], horizontal=True, key="ex_f",
                     label_visibility="collapsed",
                     format_func=lambda x: f"{x} · {len(allx) if x == 'Todos' else cnt.get({'Borradores': 'Borrador', 'Exportados': 'Exportado', 'Importados': 'Importado'}[x], 0)}")
    if t2.button("Importar examen anterior", type="primary", key="ex_imp", use_container_width=True):
        _imp_reset(); _ss["imp_paso"] = 1; st.rerun()
    q = st.text_input("Buscar", key="ex_q", placeholder="Buscar por nombre, curso o convocatoria…", label_visibility="collapsed")
    m = {"Borradores": "Borrador", "Exportados": "Exportado", "Importados": "Importado"}.get(f)
    x = allx[allx["_est"] == m] if m else allx
    if q.strip():
        ql = q.strip().lower()
        x = x[x.apply(lambda r: ql in f"{r['Nombre']} {r['Curso']} {r['Convocatoria']} {r['ID_Examen']}".lower(), axis=1)]
    x = x.assign(_o=x["Fecha"].where(x["Fecha"] != "", x["Actualizado"])).sort_values("_o", ascending=False)
    if _ss.get("ex_sel") not in set(allx["ID_Examen"]) and not x.empty:
        _ss["ex_sel"] = x.iloc[0]["ID_Examen"]
    cl, cf = st.columns([1.55, 1], gap="medium")
    with cl.container(border=True, key="card_ex_lista"):
        if x.empty:
            st.caption("No hay exámenes con este filtro.")
        for r in x.to_dict("records"):
            on = r["ID_Examen"] == _ss.get("ex_sel")
            c = A._j(r.get("Contenido", ""), {})
            n_dev = len(c.get("dev") or [])
            meta = (f"{r['N_Preguntas'] or len(c.get('test') or [])} test" + (f" + {n_dev} desarrollo" if n_dev else "")
                    + (f" · modelos {', '.join(sorted(A._j(r['Claves'], {})))}" if r["Claves"] not in ("", "{}") else ""))
            an = (f"media {_num(r['Media'])} · KR-20 {_num(r['KR20'])}" if r["Media"] else ("—" if r["_est"] == "Borrador" else "sin analizar"))
            with st.container(key=f"exrow{'_on' if on else ''}_{abs(hash(r['ID_Examen'])) % 10**8}"):
                h = st.columns([3.1, 1.05, 1.05, 1.6, 0.55], vertical_alignment="center")
                h[0].markdown(f"<div class='devq-t'>{r['Nombre'] or r['ID_Examen']}</div><div class='devq-s'>{meta}</div>",
                              unsafe_allow_html=True)
                h[1].markdown(f"<span class='tag tag-{_TAG_EST.get(r['_est'], 'n')}'>{r['_est']}</span>", unsafe_allow_html=True)
                h[2].markdown(f"<span class='devq-s'>{_fecha(r['Fecha'])}</span>", unsafe_allow_html=True)
                h[3].markdown(f"<span class='devq-s'>{an}</span>", unsafe_allow_html=True)
                if h[4].button("›", key=f"exsel_{r['ID_Examen']}", type="primary" if on else "secondary", help="Ver ficha"):
                    _ss["ex_sel"] = r["ID_Examen"]; _ss.pop("_exf_del", None); st.rerun()
    with cf.container(border=True, key="card_ex_ficha"):
        sel = allx[allx["ID_Examen"] == _ss.get("ex_sel")]
        if sel.empty:
            st.caption("Elige un examen de la lista.")
        else:
            _ficha(sel.iloc[0].to_dict())
    with st.expander("Registrar un examen solo con la clave (sin archivos) · vincular preguntas"):
        _manual()


def _manual():
    st.markdown("<div class='sec-title' style='margin-top:18px'>Registrar solo con la clave</div>",
                unsafe_allow_html=True)
    st.caption("Si no tienes los archivos del examen: basta con la clave de cada modelo; "
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
                _ss["ex_sel"] = eid
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


# ══════════════════════════════════════════════════════════════════════════════
paso = _ss.get("imp_paso")
if paso == 2 and _ss.get("imp_res"):
    _imp_paso2(_ss["imp_res"])
elif paso == 3 and _ss.get("imp_res"):
    _imp_paso3(_ss["imp_res"])
elif paso:
    _imp_paso1()
else:
    _lista()
