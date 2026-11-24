"""
clasificador.py – Propone bloque, tema y objetivo para preguntas nuevas (sin IA externa).

Compara el texto de la pregunta (enunciado + opciones) con:
  · las preguntas que ya hay en cada tema del banco,
  · los nombres de temas y bloques y la descripción de los objetivos (Configuración).
Usa TF-IDF con similitud del coseno. Cuantas más preguntas y nombres haya, mejor propone.
La propuesta siempre se revisa antes de importar.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

_STOP = set("""
a al algo algun alguna algunas alguno algunos ante antes aquel aquella aquellas aquello aquellos aqui asi aun
bajo bien cada como con contra cual cuales cualquier cuando cuanto de del desde donde dos el ella ellas ello ellos
en entre era eran es esa esas ese eso esos esta estaba estado estan estar este esto estos fue fueron ha han hasta
hay la las le les lo los mas me mediante menos mi mientras muy ni no nos o otra otras otro otros para pero poco
por porque puede pueden que quien se segun ser si sido siempre sin sobre su sus tal tambien tanto te tiene tienen
todo todos tras tu un una unas uno unos y ya cual correcta correcto siguiente siguientes afirmacion afirmaciones
verdadera falsa respecto valor caso forma tipo cierto cierta ninguna anteriores todas
""".split())


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\$[^$]*\$", " ", t)   # fuera fórmulas LaTeX en línea


def tokens(t: str) -> list:
    out = []
    for w in re.findall(r"[a-z][a-z0-9]{2,}", _norm(t)):
        if w in _STOP:
            continue
        if len(w) > 5 and w.endswith("es"):
            w = w[:-2]
        elif len(w) > 4 and w.endswith("s"):
            w = w[:-1]
        out.append(w)
    return out


def _cos(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    num = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return num / (na * nb) if na and nb else 0.0


class Clasificador:
    def __init__(self, df, cfg_bloques: dict | None = None, cfg_temas: dict | None = None,
                 cfg_objetivos: dict | None = None):
        cfg_bloques = cfg_bloques or {}
        cfg_temas = cfg_temas or {}
        self.objetivos = cfg_objetivos or {}
        docs = {}      # (bloque, tema) -> Counter
        nq = Counter()
        corpus = []
        for _, r in df.iterrows():
            b, t = str(r.get("bloque", "")), str(r.get("Tema", "")).removesuffix(".0")
            tk = tokens(str(r.get("enunciado", "")) + " " + " ".join(map(str, r.get("opciones_list") or [])))
            docs.setdefault((b, t), Counter()).update(tk)
            nq[(b, t)] += 1
            corpus.append(set(tk))
        # nombres de tema (pesan como 3 preguntas) y descripción del bloque
        for t, d in cfg_temas.items():
            if not isinstance(d, dict):
                continue
            b = d.get("bloque", "")
            nombre = str(d.get("nombre", "") or "")
            key = next((k for k in docs if k[1] == str(t) and (not b or k[0] == b)), (b, str(t)))
            if not key[0]:
                continue
            tk = tokens(nombre) * 3
            if tk:
                docs.setdefault(key, Counter()).update(tk)
                corpus.append(set(tk))
        for key in list(docs):
            desc = str(cfg_bloques.get(key[0], "") or "")
            if desc and desc not in ("nan", "None"):
                docs[key].update(tokens(desc))
        self.obj_docs = {}
        for c, d in self.objetivos.items():
            tk = tokens(f"{d.get('nombre_corto', '')} {d.get('descripcion', '')}")
            if tk:
                self.obj_docs[c] = Counter(tk)
                corpus.append(set(tk))
        n = max(1, len(corpus))
        df_cnt = Counter(w for s in corpus for w in s)
        self.idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df_cnt.items()}
        self.temas = {k: self._tfidf(v) for k, v in docs.items()}
        self.objs = {c: self._tfidf(v) for c, v in self.obj_docs.items()}
        self.n_preg = nq

    def _tfidf(self, cnt: Counter) -> dict:
        tot = sum(cnt.values()) or 1
        return {w: (c / tot) * self.idf.get(w, math.log(2) + 1) for w, c in cnt.items()}

    def clasificar(self, enunciado: str, opciones=None) -> dict:
        """{'bloque', 'tema', 'objetivo', 'conf': 'alta'|'media'|'baja', 'score'}"""
        q = self._tfidf(Counter(tokens(f"{enunciado} {' '.join(map(str, opciones or []))}")))
        sc = sorted(((_cos(q, v), k) for k, v in self.temas.items()), reverse=True)
        if not sc or sc[0][0] <= 0:
            return {"bloque": "", "tema": "", "objetivo": "", "conf": "baja", "score": 0.0}
        s1, (b, t) = sc[0]
        s2 = sc[1][0] if len(sc) > 1 else 0.0
        # Si los dos primeros son del mismo bloque, al menos el bloque es fiable
        mismo_blq = len(sc) > 1 and sc[1][1][0] == b
        conf = ("alta" if s1 >= 0.28 and (s1 - s2 >= 0.06 or mismo_blq)
                else "media" if s1 >= 0.14 else "baja")
        obj, so = "", 0.0
        for c, v in self.objs.items():
            d = self.objetivos.get(c, {})
            if d.get("bloque") and d["bloque"] != b:
                continue
            if d.get("tema") and str(d["tema"]) != t:
                continue
            s = _cos(q, v)
            if s > so:
                obj, so = c, s
        return {"bloque": b, "tema": t, "objetivo": obj if so >= 0.12 else "", "conf": conf,
                "score": round(s1, 3)}


# Fecha del archivo al cargarse (ver _recarga.py)
import os as _os_mt
_MTIME = _os_mt.path.getmtime(__file__)
