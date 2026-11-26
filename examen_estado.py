"""Estado del examen en el Generador: deshacer/rehacer de Preview, borrador automático en la base de datos,
abrir exámenes guardados (bloqueados, con sus modelos exactos) y nombre automático con fecha.

Todo lo que se guarda va a la hoja An_Examenes (sin ningún dato de alumnos)."""
import datetime
import hashlib
import json
import os as _os_mt
import re
import time

import streamlit as st

import analisis_lib as A

MAX_UNDO = 20
AUTOSAVE_SEG = 15


# ── utilidades ────────────────────────────────────────────────────────────────
def _ss():
    return st.session_state


def _fijas() -> list:
    return list(_ss().get("manual_order") or [])


def _set_fijas(ids: list):
    _ss().manual_order = list(ids)
    _ss().sel_ids = list(ids)


def fecha_iso(fecha: str) -> str:
    """'20/01/2026' o '20-01-2026' → '2026-01-20' (si no se entiende, hoy)."""
    s = str(fecha or "").strip()
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", s)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    return datetime.date.today().isoformat()


def fecha_es(iso: str) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}-{s[5:7]}-{s[:4]}" if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else s


def siglas(asig: str) -> str:
    """'Física Médica' → 'FM' (palabras de más de 3 letras)."""
    w = [x for x in re.split(r"\s+", str(asig or "").strip()) if len(x) > 3]
    return "".join(x[0].upper() for x in w)[:6]


def nombre_auto(tipo: str, asig: str, fecha: str) -> str:
    partes = [str(tipo or "Examen").strip().title(), siglas(asig), fecha_es(fecha_iso(fecha))]
    return re.sub(r"\s+", " ", " ".join(p for p in partes if p)).strip()


def usuario() -> str:
    return str(_ss().get("google_user_email", "") or "")


# ── deshacer / rehacer ────────────────────────────────────────────────────────
def _snap(desc: str = "") -> dict:
    ss = _ss()
    return {"cache": list(ss.get("cache_examen") or []), "fijas": _fijas(), "desc": desc,
            "cambios": dict(ss.get("pv_cambios") or {}), "ultimo": ss.get("pv_ultimo", "")}


def _restaurar(s: dict):
    ss = _ss()
    ss.cache_examen = list(s["cache"]) or None
    _set_fijas(s["fijas"])
    ss["pv_cambios"] = dict(s["cambios"])
    ss["pv_ultimo"] = s.get("ultimo", "")


def registrar(desc: str, tipo: str | None, antes: dict | None = None):
    """Apunta un cambio hecho a mano. `antes` = estado previo (si no, el actual)."""
    ss = _ss()
    pila = ss.setdefault("pv_undo", [])
    s_ = antes or _snap()
    s_["cambio"] = desc
    pila.append(s_)
    del pila[:-MAX_UNDO]
    ss["pv_redo"] = []
    if tipo:
        c = ss.setdefault("pv_cambios", {})
        c[tipo] = c.get(tipo, 0) + 1
    ss["pv_ultimo"] = desc


def snap() -> dict:
    return _snap()


def deshacer():
    ss = _ss()
    if ss.get("pv_undo"):
        previo = ss["pv_undo"].pop()
        ahora = _snap()
        ahora["cambio"] = previo.get("cambio", "")
        ss.setdefault("pv_redo", []).append(ahora)
        _restaurar(previo)


def rehacer():
    ss = _ss()
    if ss.get("pv_redo"):
        sig = ss["pv_redo"].pop()
        ahora = _snap()
        ahora["cambio"] = sig.get("cambio", "")
        ss.setdefault("pv_undo", []).append(ahora)
        _restaurar(sig)


def volver_generado():
    ss = _ss()
    if ss.get("pv_base"):
        registrar("Volver al examen generado", None)
        ss.cache_examen = list(ss["pv_base"])
        ss["pv_cambios"] = {}


def al_generar(pool: list):
    """Antes de sustituir el examen por uno recién generado (se puede deshacer)."""
    ss = _ss()
    if ss.get("cache_examen"):
        registrar("Generar de nuevo", None)
    ss["pv_base"] = list(pool)
    ss["pv_cambios"] = {}
    ss["pv_ultimo"] = ""


def n_cambios() -> int:
    return sum((_ss().get("pv_cambios") or {}).values())


def bloqueado() -> bool:
    return bool(_ss().get("recovery_mode"))


# ── contenido y borrador ─────────────────────────────────────────────────────
def _jsonable(o):
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, (bytes, bytearray)):
        return None
    return str(o)


def _dev_sin_imagenes(dev: list) -> list:
    out = []
    for q in dev or []:
        q2 = {k: v for k, v in q.items() if k != "imagen_bytes"}
        q2["subapartados"] = [{k: v for k, v in a.items() if k != "imagen_bytes"} for a in (q.get("subapartados") or [])]
        out.append(q2)
    return out


def contenido() -> dict:
    ss = _ss()
    cfg = {k: v for k, v in (ss.get("exam_cfg") or {}).items() if not isinstance(v, (bytes, bytearray))}
    return {"v": 1, "test": [p.get("ID_Pregunta", "") for p in (ss.get("cache_examen") or [])],
            "fijas": _fijas(), "receta": ss.get("auto_recipe") or {}, "opts": ss.get("auto_opts") or {},
            "dev": _dev_sin_imagenes(ss.get("dev_questions") or []), "cfg": cfg,
            "cambios": ss.get("pv_cambios") or {}}


def _json(c: dict) -> str:
    return json.dumps(c, ensure_ascii=False, default=_jsonable)


def _firma(c: dict) -> str:
    return hashlib.md5(_json(c).encode("utf-8")).hexdigest()


def hay_algo(c: dict) -> bool:
    return bool(c["test"] or c["dev"] or c["fijas"])


def guardar_borrador(forzar: bool = False) -> bool:
    """Guarda el examen en curso como borrador en An_Examenes. Devuelve True si ha escrito."""
    from app_utils import guardar_hojas
    ss = _ss()
    if not ss.get("excel_dfs") or bloqueado():
        return False
    c = contenido()
    if not hay_algo(c):
        return False
    f = _firma(c)
    if f == ss.get("_draft_sig") and not forzar:
        return False
    if not forzar and time.time() - ss.get("_draft_t", 0) < AUTOSAVE_SEG:
        return False
    did = ss.get("draft_id") or f"BORRADOR-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    cfg = c["cfg"]
    fila = {"ID_Examen": did, "Curso": A.curso_academico(), "Convocatoria": cfg.get("tipo", ""),
            "Nombre": cfg.get("file") or "Examen sin nombre", "Fecha": fecha_iso(cfg.get("fecha", "")),
            "N_Preguntas": str(len(c["test"])), "N_Modelos": str(cfg.get("vers", "")), "Origen": "Generador",
            "Estado": "Borrador", "Contenido": _json(c), "Usuario": usuario(),
            "Actualizado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    A.upsert_examen(ss.excel_dfs, fila)
    guardar_hojas([A.SHEET_EXAMENES])
    ss["draft_id"], ss["_draft_sig"], ss["_draft_t"] = did, f, time.time()
    return True


def borrar_borrador():
    """Tras exportar: el borrador se sustituye por el examen exportado."""
    ss = _ss()
    did = ss.pop("draft_id", None)
    if did and did in set(A.get_examenes(ss.excel_dfs)["ID_Examen"]):
        A.borrar_examen(ss.excel_dfs, did)
    ss["_draft_sig"] = _firma(contenido())


@st.fragment(run_every=AUTOSAVE_SEG + 5)
def indicador_borrador():
    """Línea de estado bajo el título del Generador; guarda el borrador sola cada ~20 s si hubo cambios."""
    ss = _ss()
    if not ss.get("excel_dfs"):
        return
    if bloqueado():
        lk = ss.get("exam_lock") or {}
        st.markdown(f"<div class='bor-st'><span class='dot lk'></span>Examen guardado · "
                    f"{lk.get('Nombre', '')} · bloqueado</div>", unsafe_allow_html=True)
        return
    c = contenido()
    if not hay_algo(c):
        return
    try:
        guardar_borrador()
    except Exception as e:   # sin conexión, etc.: no interrumpe el trabajo
        st.caption(f"No se ha podido guardar el borrador: {e}")
    pend = _firma(c) != ss.get("_draft_sig")
    t = ss.get("_draft_t")
    if pend:
        txt, cls = "Cambios sin guardar · se guardan solos en unos segundos", "pd"
    else:
        mins = int((time.time() - t) // 60) if t else 0
        txt, cls = f"Borrador guardado · {'hace ' + str(mins) + ' min' if mins else 'ahora mismo'}", "ok"
    c1, c2 = st.columns([5, 1], vertical_alignment="center")
    c1.markdown(f"<div class='bor-st'><span class='dot {cls}'></span>{txt}</div>", unsafe_allow_html=True)
    if pend and c2.button("Guardar ahora", key="bor_now", type="tertiary"):
        guardar_borrador(forzar=True)
        st.rerun(scope="fragment")


# ── abrir exámenes guardados ─────────────────────────────────────────────────
def examenes(incluir_borradores=True):
    ss = _ss()
    df = A.get_examenes(ss.get("excel_dfs") or {})
    if not incluir_borradores:
        df = df[df["Estado"] != "Borrador"]
    return df


def estado_de(row) -> str:
    return row.get("Estado") or ("Importado" if row.get("Origen") == "Importado" else "Exportado")


def master_desde_registro(info: dict, por_id: dict) -> list:
    """Reconstruye los modelos tal como se exportaron (orden, opciones barajadas y claves)."""
    master = []
    for m, v in enumerate(sorted(info.get("posiciones") or {}), 1):
        ids = info["posiciones"][v]
        perms = (info.get("perms") or {}).get(v) or []
        clave = (info.get("claves") or {}).get(v, "")
        pregs = []
        for k, pid in enumerate(ids):
            base = por_id.get(pid)
            if base is None:
                continue
            p = dict(base)
            p["ID_Pregunta"] = pid
            orig = list(p.get("opciones_list") or [])
            s = perms[k] if k < len(perms) else "ABCD"
            fin = [orig[A.LETRAS.index(ch)] if ch in A.LETRAS and A.LETRAS.index(ch) < len(orig) else (orig[i] if i < len(orig) else "")
                   for i, ch in enumerate(s[:len(orig)])]
            p["opciones_finales"] = fin
            p["letra_final"] = (clave[k] if k < len(clave) else "A")
            p["num"] = len(pregs) + 1
            pregs.append(p)
        master.append({"modelo": m, "letra_version": v, "preguntas": pregs})
    return master


def abrir(row) -> str:
    """Carga un examen guardado en el Generador. Devuelve un texto para el aviso."""
    from desarrollo_ui import normalizar
    ss = _ss()
    try:
        guardar_borrador(forzar=True)   # lo que hubiera en curso no se pierde
    except Exception:
        pass
    info = A.examen_info(row)
    c = A._j(row.get("Contenido", ""), {})
    df = ss.df_preguntas
    por_id = {r["ID_Pregunta"]: r for r in df.to_dict("records")}
    ids = c.get("test") or (info.get("posiciones") or {}).get("A") or next(iter((info.get("posiciones") or {}).values()), [])
    cache = [dict(por_id[i]) for i in ids if i in por_id]
    faltan = len(ids) - len(cache)
    ss.cache_examen = cache or None
    _set_fijas([i for i in (c.get("fijas") or []) if i in por_id])
    ss.auto_recipe = c.get("receta") or {}
    ss.auto_opts = c.get("opts") or {}
    ss.dev_questions = [normalizar(q) for q in (c.get("dev") or [])]
    if c.get("cfg"):
        ss.exam_cfg = dict(c["cfg"])
        for k in [k for k in list(ss.keys()) if str(k).startswith("exp_")]:
            ss.pop(k, None)          # el formulario de Exportar vuelve a leer la configuración
    for k in ("pv_undo", "pv_redo", "export_files", "_lock_master", "dev_edit_uid", "_gen_conf"):
        ss.pop(k, None)
    ss["pv_base"], ss["pv_cambios"], ss["pv_ultimo"] = list(cache), dict(c.get("cambios") or {}), ""
    est = estado_de(row)
    if est == "Borrador":
        ss["recovery_mode"] = False
        ss.pop("exam_lock", None)
        ss["draft_id"] = row["ID_Examen"]
        ss["_draft_sig"] = _firma(contenido())
        ss["_draft_t"] = time.time()
    else:
        ss["recovery_mode"] = True
        ss["exam_lock"] = info
        ss["draft_id"] = None
        if info.get("posiciones"):
            ss["_lock_master"] = master_desde_registro(info, por_id)
    return (f"Abierto «{row.get('Nombre') or row['ID_Examen']}»"
            + (f" · {faltan} pregunta(s) ya no están en la base de datos" if faltan else ""))


def desbloquear():
    ss = _ss()
    ss["recovery_mode"] = False
    for k in ("exam_lock", "_lock_master"):
        ss.pop(k, None)
    ss["pv_base"] = list(ss.get("cache_examen") or [])
    ss["pv_cambios"] = {}
    ss["_draft_sig"] = None     # a partir de aquí es un examen nuevo: se guardará como borrador


def master_bloqueado(pool: list) -> list | None:
    """Si el examen abierto está bloqueado, sus modelos exactos (con los datos actuales de las preguntas)."""
    ss = _ss()
    info = ss.get("exam_lock")
    if not bloqueado() or not info or not info.get("posiciones") or not pool:
        return None
    return master_desde_registro(info, {p["ID_Pregunta"]: p for p in pool})


# ── modelos fijados al exportar ──────────────────────────────────────────────
# Al exportar (o al ver la vista previa del PDF) se guardan el orden y el barajado de cada modelo. Volver a
# exportar con las mismas preguntas y el mismo barajado reutiliza exactamente esos modelos (mismas claves);
# solo «Generar modelos nuevos» o un cambio de preguntas/barajado los rehace, y siempre con confirmación.
def firma_modelos(ids: list, cfg: dict) -> str:
    """Lo que determina los modelos: preguntas y su orden, nº de modelos, orden, barajado y anclaje."""
    base = {"ids": list(ids), "vers": cfg.get("vers", 1), "ord": cfg.get("ord", "bloques"), "bar": cfg.get("bar", True),
            "anc": [cfg.get("anc_chk", True), cfg.get("anc_txt", "")], "partes": cfg.get("partes_modo", "completo")}
    return hashlib.md5(json.dumps(base, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def ids_examen() -> list:
    ss = _ss()
    cache = ss.get("cache_examen") or []
    return [p.get("ID_Pregunta") for p in cache] if cache else _fijas()


def fijar(master: list, firma: str, previa: bool = False):
    if not master or not master[0].get("preguntas"):
        return
    f = A.registro_desde_master(master, "x")
    ant = _ss().get("exp_fix") or {}
    _ss()["exp_fix"] = {"info": {"claves": json.loads(f["Claves"]), "posiciones": json.loads(f["Posiciones"]),
                                 "perms": json.loads(f["Permutaciones"])},
                        "firma": firma,
                        "fecha": ant.get("fecha") if ant.get("firma") == firma else datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
                        "exportado": (previa is False) or (ant.get("exportado") and ant.get("firma") == firma)}


def estado_modelos(cfg: dict | None = None) -> tuple:
    """('ninguno' | 'vigente' | 'cambiado', datos de la fijación)."""
    ss = _ss()
    fx = ss.get("exp_fix")
    if not fx:
        return "ninguno", {}
    f = firma_modelos(ids_examen(), cfg if cfg is not None else (ss.get("exam_cfg") or {}))
    return ("vigente" if f == fx["firma"] else "cambiado"), fx


def master_fijado(pool: list, firma: str) -> list | None:
    fx = _ss().get("exp_fix")
    if not fx or fx.get("firma") != firma or not pool:
        return None
    return master_desde_registro(fx["info"], {p["ID_Pregunta"]: p for p in pool})


def descartar_fijado(nombre: str = ""):
    """«Generar modelos nuevos»: la exportación anterior queda en el registro como «sustituida»."""
    from app_utils import guardar_hojas
    ss = _ss()
    fx = ss.pop("exp_fix", None)
    ss.pop("export_files", None)
    if not (fx and fx.get("exportado") and nombre and ss.get("excel_dfs")):
        return
    exs = A.get_examenes(ss.excel_dfs)
    r = exs[exs["ID_Examen"] == nombre]
    if r.empty:
        return
    f = dict(r.iloc[0])
    f["ID_Examen"] = f"{nombre} · sustituido {fx.get('fecha', '')}"
    f["Nombre"] = f["ID_Examen"]
    f["Estado"] = "Sustituido"
    A.upsert_examen(ss.excel_dfs, f)
    guardar_hojas([A.SHEET_EXAMENES])


# ── cambios desde la última preparación ─────────────────────────────────────
_CLAVES_MODELO = {"vers": "Número de modelos", "ord": "Orden de las preguntas", "bar": "Barajar respuestas",
                  "anc_chk": "Anclaje de opciones", "anc_txt": "Frases de anclaje", "partes_modo": "Partes del examen"}
_ETIQ = {"inst": "Institución", "asig": "Asignatura", "tipo": "Tipo de examen", "fecha": "Fecha", "tiem": "Tiempo",
         "file": "Nombre del examen", "ins": "Instrucciones", "h1": "Cabecera de desarrollo", "h2": "Cabecera de test",
         "tit_fund": "Título de desarrollo", "tit_test": "Título de test", "campos_alumno": "Campos del alumno",
         "tipografia": "Tipografía", "color_scheme": "Esquema de color", "font_size": "Tamaño de letra",
         "espaciado": "Espaciado", "margenes": "Márgenes", "cabecera_compacta": "Cabecera compacta",
         "sin_recuadro": "Recuadro del alumno", "estilo_num": "Numeración", "opciones_cols": "Columnas de opciones",
         "fancyhdr_on": "Encabezado y pie", "footer_text": "Texto del pie", "dos_por_hoja": "Dos páginas por hoja",
         "pts_fund": "Puntos de desarrollo", "pts_test": "Puntos de test", "penalizacion": "Penalización",
         "sol_bold": "Solución en negrita", "sol_color": "Color de la solución", "sol_ast": "Asterisco en la solución",
         "estilo_sol": "Estilo del bloque de solución", "exp_word": "Formato Word", "exp_tex": "Formato LaTeX",
         "pautado": "Espacio de respuesta", "preambulo_extra": "Paquetes LaTeX extra", "sol_info_bloque": "Bloque en soluciones",
         "sol_info_tema": "Tema en soluciones", "sol_info_dif": "Dificultad en soluciones", "sol_info_id": "ID en soluciones",
         "adapt_enabled": "Versión adaptada"}


def _val(v) -> str:
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, (list, tuple)):
        return ", ".join(map(str, v)) or "—"
    t = str(v if v not in (None, "") else "—").replace("\n", " ")
    return t if len(t) <= 28 else t[:26] + "…"


def firma_dev() -> str:
    return hashlib.md5(_json(_dev_sin_imagenes(_ss().get("dev_questions") or [])).encode("utf-8")).hexdigest()


def instantanea(ids: list, cfg: dict) -> dict:
    return {"ids": list(ids), "cfg": {k: v for k, v in (cfg or {}).items() if not isinstance(v, (bytes, bytearray))},
            "dev": firma_dev()}


def diferencias(snap: dict | None, ids: list, cfg: dict) -> tuple:
    """(cambios de aspecto, cambios que afectan a las claves) desde la última preparación, en lenguaje claro."""
    if not snap:
        return [], []
    asp, cla = [], []
    a_ids, n_ids = list(snap.get("ids") or []), list(ids)
    quit_, pon = [x for x in a_ids if x not in n_ids], [x for x in n_ids if x not in a_ids]
    if quit_ or pon:
        cla.append("Preguntas: " + " · ".join(([f"quitadas {len(quit_)} ({', '.join(quit_[:3])}{'…' if len(quit_) > 3 else ''})"] if quit_ else [])
                                             + ([f"añadidas {len(pon)} ({', '.join(pon[:3])}{'…' if len(pon) > 3 else ''})"] if pon else [])))
    elif a_ids != n_ids:
        cla.append("Orden de las preguntas cambiado")
    old = snap.get("cfg") or {}
    for k in sorted(set(old) | set(cfg or {})):
        va, vn = old.get(k), (cfg or {}).get(k)
        if str(va) == str(vn):
            continue
        if k in _CLAVES_MODELO:
            cla.append(f"{_CLAVES_MODELO[k]}: {_val(va)} → {_val(vn)}")
        else:
            asp.append(f"{_ETIQ.get(k, k.replace('_', ' ').capitalize())}: {_val(va)} → {_val(vn)}")
    if snap.get("dev") and snap.get("dev") != firma_dev():
        asp.append("Preguntas de desarrollo modificadas")
    return asp, cla


_MTIME = _os_mt.path.getmtime(__file__)
