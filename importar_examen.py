"""Importar exámenes hechos con versiones anteriores de la app (o retocados a mano).

Archivos que entiende (cada uno aporta lo que tiene):
  · METADATA.csv (formato antiguo con Enunciado_Inicio, o nuevo con enunciado y opciones)
  · CLAVES (.csv o .xlsx del lector: Pregunta · Versión · Respuesta; admite «A | D»)
  · _SOL.tex de la app (enunciado, opciones y correcta en rojo)
  · Word final (.docx) de un modelo: manda en el orden de preguntas y de opciones
Nada de esto contiene datos de alumnos."""
import difflib
import io
import os as _os_mt
import re
import unicodedata

import pandas as pd

LETRAS = "ABCD"


# ── texto ─────────────────────────────────────────────────────────────────────
def limpiar_tex(s: str) -> str:
    s = str(s or "")
    s = re.sub(r"\\textcolor\{[^}]*\}\{", "", s)
    s = re.sub(r"\\(textbf|textit|emph|underline)\{", "", s)
    s = s.replace("\\%", "%").replace("\\&", "&").replace("~", " ")
    return re.sub(r"\s+", " ", s).strip().rstrip("}").strip()


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", limpiar_tex(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def sim(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _letras(x) -> str:
    """'A | D' → 'AD'; 'b' → 'B'."""
    return "".join(c for c in str(x or "").upper() if c in LETRAS)


# ── lectura de archivos ───────────────────────────────────────────────────────
def _csv(data: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = txt.splitlines()[0] if txt else ""
    sep = ";" if first.count(";") >= first.count(",") else ","
    return pd.read_csv(io.StringIO(txt), sep=sep, dtype=str).fillna("")


def _claves_df(df: pd.DataFrame) -> dict:
    """DataFrame del lector (Pregunta, Versión, Respuesta) → {versión: [letras aceptadas por posición]}."""
    cols = list(df.columns)
    c_p = next((c for c in cols if str(c).lower().startswith("pregunta")), cols[0])
    c_v = next((c for c in cols if str(c).lower().startswith("versi")), cols[1])
    c_r = next((c for c in cols if str(c).lower().startswith("respuesta")), cols[2])
    out = {}
    for _, r in df.iterrows():
        v = str(r[c_v]).strip().upper()
        try:
            p = int(float(r[c_p]))
        except (TypeError, ValueError):
            continue
        out.setdefault(v, {})[p] = _letras(r[c_r])
    return {v: [d[k] for k in sorted(d)] for v, d in out.items()}


def _meta_df(df: pd.DataFrame) -> dict:
    """METADATA → {versión: [{id, bloque, tema, dificultad, enun, ops, ok}] en orden}."""
    out = {}
    nuevo = "Enunciado" in df.columns
    for _, r in df.iterrows():
        if not str(r.get("ID_BaseDatos", "")).strip() or not str(r.get("Version", "")).strip():
            continue      # filas vacías o de notas
        v = str(r.get("Version", "A")).strip().upper()
        ops = [r.get(f"Opcion_{L}", "") for L in LETRAS] if nuevo else []
        out.setdefault(v, []).append({
            "n": int(float(r.get("Num_Examen") or 0) or 0), "id": str(r.get("ID_BaseDatos", "")).strip(),
            "bloque": r.get("Bloque", ""), "tema": str(r.get("Tema", "")).removesuffix(".0"),
            "dificultad": r.get("Dificultad", ""), "enun": r.get("Enunciado") if nuevo else r.get("Enunciado_Inicio", ""),
            "ops": ops, "ok": _letras(r.get("Respuesta_Correcta", ""))[:1] if nuevo else "", "completo": nuevo})
    for v in out:
        out[v].sort(key=lambda x: x["n"])
    return out


def _tex(txt: str) -> list:
    """_SOL.tex de la app antigua: \\item enunciado + enumerate de 4 opciones; la correcta en rojo/negrita."""
    txt = txt.replace("\\begin{document}", "\n")
    qs, cur, depth = [], None, 0
    for l in txt.splitlines():
        l = l.strip()
        while l.startswith("\\begin{enumerate}"):
            depth += 1
            l = l[len("\\begin{enumerate}"):].strip()
        if l.startswith("\\end{enumerate}"):
            depth -= 1
            continue
        if not l.startswith("\\item"):
            if cur is not None and depth == 1 and l and not l.startswith("\\"):
                cur["enun"] += " " + l
            continue
        t = l[5:].strip()
        if depth == 1:
            cur = {"enun": t, "ops": [], "ok": ""}
            qs.append(cur)
        elif depth == 2 and cur is not None:
            if "textcolor" in t or "\\textbf" in t:
                cur["ok"] = LETRAS[len(cur["ops"])] if len(cur["ops"]) < 4 else ""
            cur["ops"].append(limpiar_tex(t))
    for q in qs:
        q["enun"] = limpiar_tex(q["enun"])
    return [q for q in qs if len(q["ops"]) >= 2]


def _docx(data: bytes) -> tuple:
    """Word del examen: (versión o '', [{label, enun, ops, bis}])."""
    import docx
    d = docx.Document(io.BytesIO(data))
    ps = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    ver = ""
    for p in ps[:15]:
        m = re.search(r"modelo\s+(?:de\s+)?(?:examen\s+)?([A-F])\b", p, re.I)
        if m:
            ver = m.group(1).upper()
            break
    out = []
    for p in ps:
        m = re.match(r"^(\d{1,3})\s*(\(bis\)|bis)?\s*[.\-)]+\s*-?\s*(.+)$", p, re.I)
        if m and (not out or len(out[-1]["ops"]) >= 2):
            out.append({"label": m.group(1) + (" bis" if m.group(2) else ""), "enun": m.group(3).strip(),
                        "ops": [], "bis": bool(m.group(2))})
        elif out and len(out[-1]["ops"]) < 4:
            out[-1]["ops"].append(p)
    return ver, [q for q in out if len(q["ops"]) >= 2]


def leer(nombre: str, data: bytes) -> dict:
    """Reconoce un archivo. Devuelve {tipo, desc, datos}."""
    ext = nombre.lower().rsplit(".", 1)[-1]
    try:
        if ext == "csv":
            df = _csv(data)
            if "ID_BaseDatos" in df.columns:
                m = _meta_df(df)
                n = max(len(x) for x in m.values())
                return {"tipo": "meta", "datos": m, "desc": (
                    f"Metadatos ({'formato nuevo' if any(x['completo'] for v in m.values() for x in v) else 'formato antiguo'})"
                    f" · modelos {', '.join(sorted(m))} · {n} preguntas")}
            if any(str(c).lower().startswith("respuesta") for c in df.columns):
                c = _claves_df(df)
                return {"tipo": "claves", "datos": c, "desc": _desc_claves(c)}
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(data), dtype=str, engine="xlrd" if data[:4] == b"\xd0\xcf\x11\xe0" else None).fillna("")
            if any(str(c).lower().startswith("respuesta") for c in df.columns) or len(df.columns) >= 3:
                c = _claves_df(df)
                if c:
                    return {"tipo": "claves", "datos": c, "desc": _desc_claves(c)}
        elif ext == "tex":
            qs = _tex(data.decode("utf-8", errors="replace"))
            if qs:
                return {"tipo": "tex", "datos": qs, "desc": f"Texto completo y correcta · {len(qs)} preguntas"
                        + ("" if all(q["ok"] for q in qs) else " (sin la correcta marcada en algunas)")}
        elif ext == "docx":
            ver, qs = _docx(data)
            if qs:
                nb = sum(q["bis"] for q in qs)
                return {"tipo": "docx", "datos": {"ver": ver or "A", "qs": qs},
                        "desc": f"Examen final · modelo {ver or 'A (supuesto)'} · {len(qs) - nb} preguntas"
                                + (f" + {nb} «bis»" if nb else "")}
    except Exception as e:
        return {"tipo": "error", "datos": None, "desc": f"No se ha podido leer: {e}"}
    return {"tipo": "otro", "datos": None, "desc": "No reconocido (se ignora)"}


def _desc_claves(c: dict) -> str:
    n = max(len(v) for v in c.values())
    dobles = sum(1 for v in c.values() for x in v if len(x) > 1)
    return (f"Claves · modelos {', '.join(sorted(c))} · {n} preguntas"
            + (f" · {dobles // max(1, len(c))} con dos respuestas válidas" if dobles else ""))


# ── base de datos ─────────────────────────────────────────────────────────────
class IndiceBD:
    def __init__(self, df: pd.DataFrame):
        self.rows = {r["ID_Pregunta"]: r for r in df.to_dict("records")}
        self.norms = {pid: norm(r.get("enunciado", "")) for pid, r in self.rows.items()}
        self.exact = {n: pid for pid, n in self.norms.items() if n}
        self.tok = {pid: set(re.findall(r"\w{4,}", str(r.get("enunciado", "")).lower())) for pid, r in self.rows.items()}

    def buscar(self, enun: str) -> tuple:
        """(id, parecido 0-1) de la pregunta de la BD más parecida."""
        n = norm(enun)
        if n in self.exact:
            return self.exact[n], 1.0
        t = set(re.findall(r"\w{4,}", str(enun).lower()))
        cand = sorted(self.tok, key=lambda p: -len(t & self.tok[p]) / (len(t | self.tok[p]) or 1))[:6]
        best = max(cand, key=lambda p: difflib.SequenceMatcher(None, n, self.norms[p]).ratio(), default=None)
        return (best, difflib.SequenceMatcher(None, n, self.norms[best]).ratio()) if best else (None, 0.0)


def _perm(ops_examen: list, ops_bd: list) -> str:
    """Letras de la BD en el orden en que salen en el examen ('CABD'); '?' si no se reconoce."""
    s = ""
    for o in ops_examen[:4]:
        sc = [sim(o, b) for b in ops_bd[:4]]
        j = max(range(len(sc)), key=lambda i: sc[i]) if sc else -1
        s += LETRAS[j] if j >= 0 and sc[j] >= 0.8 else "?"
    return s.ljust(4, "?")


# ── montar el examen ──────────────────────────────────────────────────────────
def montar(archivos: list, df_bd: pd.DataFrame) -> dict:
    """Combina los archivos reconocidos. Devuelve {ref, items, modelos{v: {...}}, avisos}."""
    meta = next((a["datos"] for a in archivos if a["tipo"] == "meta"), {})
    claves = next((a["datos"] for a in archivos if a["tipo"] == "claves"), {})
    tex = next((a["datos"] for a in archivos if a["tipo"] == "tex"), [])
    docs = [a["datos"] for a in archivos if a["tipo"] == "docx"]
    idx = IndiceBD(df_bd)
    avisos = []

    # 1) modelo de referencia: el del Word; si no, el .tex; si no, el METADATA
    if docs:
        ref, base = docs[0]["ver"], [dict(q) for q in docs[0]["qs"]]
    elif tex:
        ref = "A" if "A" in (meta or claves or {"A": 0}) else sorted(meta or claves)[0]
        base = [{"label": str(i + 1), "enun": q["enun"], "ops": q["ops"], "bis": False} for i, q in enumerate(tex)]
    elif meta:
        ref = "A" if "A" in meta else sorted(meta)[0]
        base = [{"label": str(i + 1), "enun": m["enun"], "ops": m["ops"], "bis": False} for i, m in enumerate(meta[ref])]
    else:
        return {"error": "Falta el METADATA, el _SOL.tex o el Word del examen."}

    meta_all = [m for v in meta.values() for m in v]
    pos = 0
    for q in base:
        q["pos"] = None if q["bis"] else pos
        pos += 0 if q["bis"] else 1
        # correcta según el .tex o el METADATA nuevo (por texto)
        ok_txt = ""
        if tex:
            t = max(tex, key=lambda x: sim(x["enun"], q["enun"]))
            if sim(t["enun"], q["enun"]) >= 0.85 and t["ok"]:
                ok_txt = t["ops"][LETRAS.index(t["ok"])]
        m_hit = None
        if meta_all:
            m_hit = max(meta_all, key=lambda m: (norm(q["enun"]).startswith(norm(m["enun"])[:40]) and len(norm(m["enun"])) > 10,
                                                 sim(m["enun"], q["enun"][:len(m["enun"]) + 5])))
            if not (norm(q["enun"]).startswith(norm(m_hit["enun"])[:40]) and len(norm(m_hit["enun"])) > 10) \
                    and sim(m_hit["enun"], q["enun"][:len(m_hit["enun"]) + 5]) < 0.85:
                m_hit = None
            if m_hit and m_hit["completo"] and m_hit["ok"] and not ok_txt:
                ok_txt = m_hit["ops"][LETRAS.index(m_hit["ok"])]
        q["ok_txt"] = ok_txt
        q["meta"] = m_hit
        # pregunta de la BD
        pid, s = (None, 0.0)
        if m_hit and m_hit["id"] in idx.rows:
            pid, s = m_hit["id"], sim(idx.rows[m_hit["id"]].get("enunciado", ""), q["enun"])
            if s < 0.6:
                pid2, s2 = idx.buscar(q["enun"])
                if s2 > s:
                    pid, s = pid2, s2
        else:
            pid, s = idx.buscar(q["enun"])
        if pid and s >= 0.97:
            q["estado"], q["id"] = "bd", pid
        elif pid and s >= 0.8:
            q["estado"], q["id"] = "cambiada", pid
        else:
            q["estado"], q["id"] = "nueva", None
        q["sim"] = round(s, 2)
        q["perm"] = (_perm(q["ops"], list(idx.rows[q["id"]].get("opciones_list") or []))
                     if q["id"] and q["ops"] else "ABCD")
        q["anadir"] = q["estado"] == "nueva"
        q["vincular"] = q["estado"] != "nueva"     # para «cambiada»: vincular (True) o añadir como nueva (False)
        q["bloque"] = (m_hit or {}).get("bloque") or (idx.rows[pid]["bloque"] if pid else "")
        q["tema"] = (m_hit or {}).get("tema") or (str(idx.rows[pid].get("Tema", "")) if pid else "")
        q["dificultad"] = (m_hit or {}).get("dificultad") or (idx.rows[pid].get("dificultad", "") if pid else "Media")
        q["etiqueta"] = "plan anterior" if q["bis"] else ""
        # letra correcta en este examen
        if ok_txt and q["ops"]:
            sc = [sim(ok_txt, o) for o in q["ops"]]
            j = max(range(len(sc)), key=lambda i: sc[i])
            q["ok"] = LETRAS[j] if sc[j] >= 0.8 else ""
        else:
            q["ok"] = ""
    items = [q for q in base if not q["bis"]]
    n = len(items)

    # 2) clave del modelo de referencia
    modelos = {}
    kc = claves.get(ref) or []
    if kc and len(kc) != n:
        avisos.append(f"La clave del modelo {ref} tiene {len(kc)} preguntas y el examen {n}.")
    # La correcta sacada del texto (Word + .tex/metadatos) manda: es lo que se imprimió. Del archivo de claves
    # se conservan las respuestas dobles («A | D») si incluyen esa letra.
    k_ref, difs = [], []
    for j, q in enumerate(items):
        kf = kc[j] if j < len(kc) else ""
        if q["ok"]:
            k_ref.append(kf if q["ok"] in kf and len(kf) > 1 else q["ok"])
            if kf and q["ok"] not in kf:
                difs.append(f"{j + 1} ({kf}→{q['ok']})")
        else:
            k_ref.append(kf)
    if difs:
        avisos.append(f"El archivo de claves del modelo {ref} no coincide con el examen en {len(difs)} pregunta(s): "
                      + ", ".join(difs) + ". Se usa la respuesta del examen (Word/.tex).")
    coinc = sum(1 for q, k in zip(items, k_ref) if q["ok"] and q["ok"] in k)
    con_ok = sum(1 for q in items if q["ok"])
    modelos[ref] = {"orden": list(range(n)), "clave": list(k_ref[:n]) + [""] * (n - len(k_ref)), "opciones": "exactas",
                    "fuente": "Word final" if docs else ("_SOL.tex" if tex else "metadatos"),
                    "coincide": (coinc, con_ok)}

    # 3) otros modelos (de las claves): orden deducido de los metadatos o por desplazamiento
    for v in sorted(set(claves) - {ref}):
        kv = claves[v]
        best = None
        m_v = meta.get(v) or []
        ids_ref = [q["id"] or "" for q in items]
        if m_v and len(m_v) == n and all(m["id"] in ids_ref for m in m_v):
            orden = [ids_ref.index(m["id"]) for m in m_v]
            best = (orden, "metadatos")
        else:
            for s_ in range(n):
                orden = [(j + s_) % n for j in range(n)]
                sc = sum(1 for j in range(min(n, len(kv))) if set(kv[j]) & set(k_ref[orden[j]]))
                if best is None or sc > best[2]:
                    best = (orden, f"desplazamiento de {s_}" if s_ else "mismo orden", sc)
            # comprobación con el orden relativo de los metadatos (si los hay)
            best = (best[0], best[1])
        orden = best[0]
        sc = sum(1 for j in range(min(n, len(kv))) if set(kv[j]) & set(k_ref[orden[j]]))
        mismo = sc >= 0.9 * n
        clave_v = ([k_ref[i] for i in orden] if mismo else list(kv[:n]) + [""] * (n - len(kv)))
        modelos[v] = {"orden": orden, "clave": clave_v, "fuente": best[1],
                      "opciones": "como el modelo " + ref if mismo else "desconocidas",
                      "coincide": (sc, n), "propuesto": True}
    return {"ref": ref, "base": base, "items": items, "modelos": modelos, "avisos": avisos, "n": n}


def registro(res: dict, elegidos: list, nombre: str, curso: str, convocatoria: str, fecha: str) -> tuple:
    """Fila de An_Examenes + decisiones «aceptar otra letra» (respuestas dobles de la clave)."""
    import json
    import datetime
    items, ref = res["items"], res["ref"]
    ids = [q.get("id") or f"?{nombre}#{j + 1}" for j, q in enumerate(items)]
    claves, posiciones, perms, extra = {}, {}, {}, []
    for v in elegidos:
        m = res["modelos"][v]
        cl, pos, pr = "", [], []
        for j, i in enumerate(m["orden"]):
            q = items[i]
            letras = m["clave"][j] or q["ok"] or "A"
            cl += letras[0]
            pos.append(ids[i])
            if m["opciones"] == "desconocidas" or not q.get("ops"):
                pr.append("????")
            else:
                pr.append(q.get("perm") or "ABCD")
            if v == sorted(elegidos)[0] and len(letras) > 1:
                extra.append((j + 1, ids[i], letras[1:]))
        claves[v], posiciones[v], perms[v] = cl, pos, pr
    test = posiciones[sorted(elegidos)[0]] if elegidos else []
    fila = {"ID_Examen": nombre, "Curso": curso, "Convocatoria": convocatoria, "Nombre": nombre, "Fecha": fecha,
            "N_Preguntas": str(res["n"]), "N_Modelos": str(len(elegidos)), "Origen": "Importado",
            "Claves": json.dumps(claves), "Posiciones": json.dumps(posiciones), "Permutaciones": json.dumps(perms),
            "Estado": "Importado", "Actualizado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Contenido": json.dumps({"v": 1, "test": [i for i in test if not i.startswith("?")]}, ensure_ascii=False)}
    return fila, extra


_MTIME = _os_mt.path.getmtime(__file__)
