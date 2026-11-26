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


def _es_rojo(c) -> bool:
    c = tuple(c) if isinstance(c, (list, tuple)) else ()
    return len(c) >= 3 and c[0] > 0.55 and c[1] < 0.35 and c[2] < 0.35


def _pdf(data: bytes) -> tuple:
    """PDF de texto de un examen: (versión o '', [{label, enun, ops, bis, ok, bloque, tema}]).
    Admite una o dos columnas (también «dos páginas por hoja»); la correcta se reconoce si está
    en rojo, en negrita o con asterisco (versión con soluciones)."""
    import pdfplumber
    ver, out = "", []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pg in pdf.pages:
            W = pg.width
            ws = pg.extract_words(extra_attrs=["non_stroking_color", "fontname"], x_tolerance=1.5, keep_blank_chars=False)
            if not ver:
                cab = unicodedata.normalize("NFC", " ".join(w["text"] for w in ws[:60]))
                m = re.search(r"(?:Versi[oó]n|Modelo)\s*([A-F])\b", cab)
                ver = m.group(1) if m else ""
            cruzan = sum(1 for w in ws if w["x0"] < W / 2 - 5 and w["x1"] > W / 2 + 5)
            izq = sum(1 for w in ws if w["x1"] <= W / 2)
            cols = [(0, W / 2), (W / 2, W)] if ws and cruzan <= 0.02 * len(ws) and 0.15 < izq / len(ws) < 0.85 else [(0, W)]
            for x0, x1 in cols:
                col = sorted([w for w in ws if x0 <= (w["x0"] + w["x1"]) / 2 < x1], key=lambda w: (round(w["top"]), w["x0"]))
                lineas = []
                for w in col:
                    if lineas and abs(lineas[-1][0] - w["top"]) <= 3:
                        lineas[-1][1].append(w)
                    else:
                        lineas.append([w["top"], [w]])
                for _, wl in lineas:
                    wl.sort(key=lambda w: w["x0"])
                    t = unicodedata.normalize("NFC", " ".join(w["text"] for w in wl).strip())
                    rojo = any(_es_rojo(w.get("non_stroking_color")) for w in wl)
                    negr = sum(1 for w in wl if "bold" in str(w.get("fontname", "")).lower()) > len(wl) / 2
                    mb = re.match(r"^Bloque:\s*(.+?)\s*·\s*Tema:\s*([\w.]+)", t)
                    if mb:
                        if out:
                            out[-1]["bloque"], out[-1]["tema"] = mb.group(1).strip(), mb.group(2)
                        continue
                    if re.match(r"^(P[aá]gina|P[aá]g\.)\s*\d", t) or (t.isupper() and len(t) > 3) or re.match(r"^(Versi[oó]n|Modelo)\s*[A-F]$", t):
                        continue
                    m = re.match(r"^(\d{1,3})\s*(\(bis\)|bis)?\s*[.)]-?\s*(.+)$", t)
                    if m and (m.group(2) or int(m.group(1)) == sum(1 for q in out if not q["bis"]) + 1):
                        out.append({"label": m.group(1) + (" bis" if m.group(2) else ""), "enun": m.group(3), "ops": [],
                                    "bis": bool(m.group(2)), "ok": "", "bloque": "", "tema": ""})
                        continue
                    if not out:
                        continue
                    q = out[-1]
                    mo = re.match(r"^([a-dA-D])\s*[).]\s*(.*)$", t)
                    if mo and len(q["ops"]) < 4 and mo.group(1).lower() == "abcd"[len(q["ops"])]:
                        txt = mo.group(2)
                        if rojo or negr or txt.startswith("*") or txt.endswith("*"):
                            q["ok"] = LETRAS[len(q["ops"])]
                        q["ops"].append(txt.strip("* ").strip())
                    elif q["ops"]:
                        q["ops"][-1] = (q["ops"][-1][:-1] + t) if q["ops"][-1].endswith("-") else q["ops"][-1] + " " + t
                    else:
                        q["enun"] = (q["enun"][:-1] + t) if q["enun"].endswith("-") else q["enun"] + " " + t
    qs = [q for q in out if len(q["ops"]) >= 2]
    if sum(1 for q in qs if q["ok"]) == len(qs):        # todas «marcadas» = no hay marca real (p. ej. todo en negrita)
        pass
    return ver, qs


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
        elif ext in ("docx", "pdf"):
            ver, qs = _docx(data) if ext == "docx" else _pdf(data)
            if qs:
                nb = sum(q["bis"] for q in qs)
                n_ok = sum(1 for q in qs if q.get("ok"))
                return {"tipo": "docx", "datos": {"ver": ver or "", "qs": qs, "ext": ext, "con_ok": n_ok >= 0.8 * len(qs)},
                        "desc": f"Examen ({ext.upper()}) · modelo {ver or '? (se supone por orden)'} · {len(qs) - nb} preguntas"
                                + (f" + {nb} «bis»" if nb else "") + (" · con la correcta marcada" if n_ok >= 0.8 * len(qs) else "")}
    except Exception as e:
        return {"tipo": "error", "datos": None, "desc": f"No se ha podido leer: {e}"}
    return {"tipo": "otro", "datos": None, "desc": "No reconocido (se ignora)"}


def _desc_claves(c: dict) -> str:
    n = max(len(v) for v in c.values())
    dobles = sum(1 for v in c.values() for x in v if len(x) > 1)
    return (f"Claves · modelos {', '.join(sorted(c))} · {n} preguntas"
            + (f" · {dobles // max(1, len(c))} con dos respuestas válidas" if dobles else ""))


def elegir(archivos: list) -> dict:
    """Si hay varios archivos del mismo tipo, elige el mejor y dice para qué se usa cada uno.
    Devuelve {"meta", "claves", "tex", "docs", "papel": [(texto, tipo_tag)] en el orden de `archivos`}."""
    idx = {t: [i for i, a in enumerate(archivos) if a["tipo"] == t] for t in ("meta", "claves", "tex", "docx")}
    def mejor(t, key):
        return max(idx[t], key=key) if idx[t] else None
    i_meta = mejor("meta", lambda i: (len(archivos[i]["datos"]), max(len(x) for x in archivos[i]["datos"].values())))
    i_cla = mejor("claves", lambda i: (len(archivos[i]["datos"]), max(len(x) for x in archivos[i]["datos"].values())))
    i_tex = mejor("tex", lambda i: (sum(1 for q in archivos[i]["datos"] if q["ok"]), len(archivos[i]["datos"])))
    # documentos (Word o PDF): uno por modelo; sin versión reconocida → A, B… por orden
    usadas = {archivos[i]["datos"]["ver"] for i in idx["docx"] if archivos[i]["datos"]["ver"]}
    libres = [L for L in "ABCDEF" if L not in usadas]
    for i in idx["docx"]:
        if not archivos[i]["datos"]["ver"]:
            archivos[i]["datos"]["ver"] = libres.pop(0) if libres else "A"
    doc_de = {}
    for i in idx["docx"]:
        v = archivos[i]["datos"]["ver"]
        j = doc_de.get(v)
        if j is None or (archivos[i]["datos"].get("con_ok") and not archivos[j]["datos"].get("con_ok")):
            doc_de[v] = i
    hay_doc = bool(idx["docx"])
    papel = []
    for i, a in enumerate(archivos):
        t = a["tipo"]
        if t == "docx":
            v = a["datos"]["ver"]
            papel.append((f"orden, opciones{' y correcta' if a['datos'].get('con_ok') else ''} del modelo {v}", "m")
                         if doc_de.get(v) == i else (f"no se usa: hay otro documento del modelo {v}", "n"))
        elif t == "meta":
            papel.append(("qué pregunta es cada una" + (" · orden de los otros modelos" if len(a["datos"]) > 1 else ""), "f")
                         if i == i_meta else ("no se usa: hay otro METADATA más completo", "n"))
        elif t == "claves":
            papel.append(("clave (se comprueba con el corrector)", "f") if i == i_cla
                         else ("no se usa: hay otra clave más completa", "n"))
        elif t == "tex":
            papel.append((("texto y correcta" + ("" if hay_doc else " · orden y opciones (no hay Word)")), "f" if hay_doc else "w")
                         if i == i_tex else ("no se usa: ya hay otro .tex con la correcta marcada", "n"))
        elif t == "error":
            papel.append(("no se ha podido leer", "d"))
        else:
            papel.append(("se ignora", "n"))
    return {"meta": archivos[i_meta]["datos"] if i_meta is not None else {},
            "claves": archivos[i_cla]["datos"] if i_cla is not None else {},
            "tex": archivos[i_tex]["datos"] if i_tex is not None else [],
            "docs": [archivos[doc_de[v]]["datos"] for v in sorted(doc_de)], "papel": papel}


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
def _nom_doc(d) -> str:
    return "PDF" if d.get("ext") == "pdf" else "Word"


def montar(archivos: list, df_bd: pd.DataFrame) -> dict:
    """Combina los archivos reconocidos. Devuelve {ref, items, modelos{v: {...}}, avisos}."""
    el = elegir(archivos)
    meta, claves, tex, docs = el["meta"], el["claves"], el["tex"], el["docs"]
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
        q["ok_doc"], q["bloque_doc"], q["tema_doc"] = q.get("ok", ""), q.get("bloque", ""), q.get("tema", "")
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
        q["bloque"] = (m_hit or {}).get("bloque") or q["bloque_doc"] or (idx.rows[pid]["bloque"] if pid else "")
        q["tema"] = (m_hit or {}).get("tema") or q["tema_doc"] or (str(idx.rows[pid].get("Tema", "")) if pid else "")
        q["dificultad"] = (m_hit or {}).get("dificultad") or (idx.rows[pid].get("dificultad", "") if pid else "Media")
        q["etiqueta"] = "plan anterior" if q["bis"] else ""
        # letra correcta en este examen
        if ok_txt and q["ops"]:
            sc = [sim(ok_txt, o) for o in q["ops"]]
            j = max(range(len(sc)), key=lambda i: sc[i])
            q["ok"] = LETRAS[j] if sc[j] >= 0.8 else ""
        else:
            q["ok"] = ""
        if q["ok_doc"]:          # la correcta marcada en el propio examen (PDF de soluciones) manda
            q["ok"] = q["ok_doc"]
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
                    "fuente": (_nom_doc(docs[0]) + f" del modelo {ref}" if docs else ("_SOL.tex" if tex else "metadatos")),
                    "coincide": (coinc, con_ok)}

    # 3a) otros modelos con su propio documento (Word o PDF): orden y opciones exactos
    for d in docs[1:]:
        v = d["ver"]
        qv = [q for q in d["qs"] if not q["bis"]]
        libres_i, orden, perms_ref, clave_v = set(range(n)), [], [], []
        for j, q in enumerate(qv):
            i = max(libres_i, key=lambda i: sim(items[i]["enun"], q["enun"])) if libres_i else 0
            libres_i.discard(i)
            orden.append(i)
            pr_ = _perm(q["ops"], items[i]["ops"]) if items[i]["ops"] else "ABCD"
            perms_ref.append(pr_)
            if q.get("ok"):
                clave_v.append(q["ok"])
            elif claves.get(v) and j < len(claves[v]):
                clave_v.append(claves[v][j])
            else:      # la correcta del modelo de referencia, en la posición que ocupa en este modelo
                Lr = (k_ref[i] or "?")[0]
                clave_v.append(LETRAS[pr_.index(Lr)] if Lr in pr_ else "")
        kc_v = claves.get(v) or []
        co = sum(1 for j, k in enumerate(clave_v) if j < len(kc_v) and k and k[0] in kc_v[j])
        modelos[v] = {"orden": orden, "clave": clave_v + [""] * (n - len(clave_v)), "opciones": "exactas",
                      "perms_ref": perms_ref, "fuente": _nom_doc(d) + f" del modelo {v}",
                      "coincide": (co, len(kc_v)) if kc_v else (len(clave_v), len(clave_v))}
        if len(qv) != n:
            avisos.append(f"El documento del modelo {v} tiene {len(qv)} preguntas y el del {ref} {n}.")

    # 3b) otros modelos solo con clave: orden deducido de los metadatos o por desplazamiento
    for v in sorted(set(claves) - set(modelos)):
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
            d_ = (m.get("decisiones") or {}).get(j)
            cl += letras[0]
            pos.append(ids[i])
            if m["opciones"] == "desconocidas" or not q.get("ops"):
                pr.append("????")
            elif m.get("perms_ref"):      # opciones de este modelo → letras del modelo de referencia → letras de la BD
                qp = q.get("perm") or "ABCD"
                pr.append("".join(qp[LETRAS.index(c)] if c in LETRAS and LETRAS.index(c) < len(qp) else "?"
                                  for c in m["perms_ref"][j]).ljust(4, "?"))
            else:
                pr.append(q.get("perm") or "ABCD")
            if v == sorted(elegidos)[0]:
                if d_:
                    extra.append((j + 1, ids[i], d_[0], d_[1]))
                elif len(letras) > 1:
                    extra.append((j + 1, ids[i], "aceptar", letras[1]))
        claves[v], posiciones[v], perms[v] = cl, pos, pr
    test = posiciones[sorted(elegidos)[0]] if elegidos else []
    fila = {"ID_Examen": nombre, "Curso": curso, "Convocatoria": convocatoria, "Nombre": nombre, "Fecha": fecha,
            "N_Preguntas": str(res["n"]), "N_Modelos": str(len(elegidos)), "Origen": "Importado",
            "Claves": json.dumps(claves), "Posiciones": json.dumps(posiciones), "Permutaciones": json.dumps(perms),
            "Estado": "Importado", "Actualizado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Contenido": json.dumps({"v": 1, "test": [i for i in test if not i.startswith("?")],
                                     "dec_corrector": {str(p - 1): [tp, L or ""] for p, _pid, tp, L in extra}},
                                    ensure_ascii=False),
            "Comprobacion": json.dumps({v: res["modelos"][v].get("comprobado") for v in elegidos
                                        if res["modelos"][v].get("comprobado")})}
    return fila, extra


_MTIME = _os_mt.path.getmtime(__file__)
