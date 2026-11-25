"""
analisis_lib.py – Análisis de ítems de exámenes tipo test (sin Streamlit).

Privacidad: el Excel del corrector se procesa SOLO en memoria. Lo único que se guarda
en la base de datos son datos agregados por pregunta y las decisiones del profesor
(hojas An_Examenes y An_Preguntas). Ningún dato de alumnos se escribe en ningún sitio.
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
import datetime

import numpy as np
import pandas as pd

LETRAS = "ABCD"
SHEET_EXAMENES = "An_Examenes"
SHEET_PREGUNTAS = "An_Preguntas"
EX_COLS = ["ID_Examen", "Curso", "Convocatoria", "Nombre", "Fecha", "N_Preguntas", "N_Modelos",
           "Origen", "Claves", "Posiciones", "Permutaciones",
           "N_Alumnos", "Media", "KR20", "Fecha_Analisis",
           "Estado", "Contenido", "Usuario", "Actualizado",   # Estado: Borrador | Exportado | Importado
           "Creado", "Comprobacion"]   # Creado: cuándo se guardó/importó (Fecha = cuándo se hizo el examen)
PR_COLS = ["ID_Examen", "Pos", "ID_Pregunta", "N", "Pct_Acierto", "Pct_Blanco", "Discriminacion",
           "Pct_A", "Pct_B", "Pct_C", "Pct_D", "Decision", "Letra_Extra", "Revisar_Distractores", "Fecha"]

DECISIONES = {
    "": "Dejarla como está",
    "anular": "Anular",
    "buena": "Buena para todos",
    "aceptar": "Aceptar también otra letra",
    "cambiar": "Cambiar la clave",
}


# ── Utilidades ────────────────────────────────────────────────────────────────
def _norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn" and c != "�")
    return " ".join(s.split())


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return float("nan")


def curso_academico(fecha: datetime.date | None = None) -> str:
    """'24-25' para fechas entre septiembre de 2024 y agosto de 2025."""
    d = fecha or datetime.date.today()
    y = d.year if d.month >= 9 else d.year - 1
    return f"{y % 100:02d}-{(y + 1) % 100:02d}"


def dificultad_real(pct_acierto: float) -> str:
    """Dificultad observada: ≥ 70 % Fácil · 40–70 % Media · < 40 % Difícil."""
    if pct_acierto != pct_acierto:
        return ""
    return "Facil" if pct_acierto >= 70 else ("Media" if pct_acierto >= 40 else "Dificil")


# ── Lectura del Excel del corrector (solo en memoria) ─────────────────────────
def parse_corrector(data: bytes) -> dict:
    """Devuelve {"meta": {...}, "alumnos": DataFrame[Alumno, DNI, Ver, Resp, Total]}.

    El formato es el informe del lector óptico: unas filas de cabecera (nombre del test,
    grupo, asignatura, estadísticos) y una fila de títulos que contiene «Respuestas».
    En «Respuestas» cada carácter es una pregunta; un espacio es una respuesta en blanco
    y los blancos finales pueden faltar."""
    # .xls antiguo (OLE2) → xlrd; .xlsx (zip) → openpyxl. Explícito: las versiones nuevas de
    # pandas eligen otro motor por defecto que no está instalado.
    engine = "xlrd" if data[:4] == b"\xd0\xcf\x11\xe0" else "openpyxl"
    raw = pd.read_excel(io.BytesIO(data), header=None, dtype=str, engine=engine)
    hdr = None
    for i in range(min(len(raw), 60)):
        if any(_norm(v) == "respuestas" for v in raw.iloc[i].tolist()):
            hdr = i
            break
    if hdr is None:
        raise ValueError("No se encuentra la fila de títulos con la columna «Respuestas».")

    cols = {}
    for j, v in enumerate(raw.iloc[hdr].tolist()):
        if str(v) != "nan":
            cols.setdefault(_norm(v), j)

    def _col(*names):
        for n in names:
            for k, j in cols.items():
                if k == n or k.startswith(n):
                    return j
        return None

    meta = {}
    for i in range(hdr):
        vals = [v for v in raw.iloc[i].tolist() if str(v) != "nan"]
        if len(vals) >= 2:
            k = _norm(vals[0]).rstrip(":").strip()
            meta[k] = str(vals[1]).strip()

    j_resp, j_ver, j_tot = _col("respuestas"), _col("ver"), _col("total")
    j_alu, j_dni = _col("alumno"), _col("dni")
    rows = []
    for i in range(hdr + 1, len(raw)):
        r = raw.iloc[i]
        resp = r.iloc[j_resp]
        tot = r.iloc[j_tot] if j_tot is not None else None
        alu = r.iloc[j_alu] if j_alu is not None else None
        if str(resp) == "nan" and str(tot) == "nan":
            continue
        if str(alu) == "nan" and str(tot) == "nan":
            continue
        ver = r.iloc[j_ver] if j_ver is not None else ""
        rows.append({
            "Alumno": "" if str(alu) == "nan" else str(alu).strip(),
            "DNI": "" if j_dni is None or str(r.iloc[j_dni]) == "nan" else str(r.iloc[j_dni]).strip(),
            "Ver": "" if str(ver) == "nan" else str(ver).strip(),
            "Resp": "" if str(resp) == "nan" else str(resp).rstrip("\r\n"),
            "Total": _num(tot),
        })
    alumnos = pd.DataFrame(rows, columns=["Alumno", "DNI", "Ver", "Resp", "Total"])
    return {"meta": meta, "alumnos": alumnos}


def respuestas_matriz(resps: list[str], n: int) -> np.ndarray:
    """Lista de cadenas → matriz N×n de letras ('' = en blanco)."""
    M = np.full((len(resps), n), "", dtype=object)
    for i, s in enumerate(resps):
        for j, ch in enumerate(str(s)[:n]):
            ch = ch.upper()
            M[i, j] = ch if ch in LETRAS else ""
    return M


def estimar_clave(M: np.ndarray, top_frac: float = 0.27) -> str:
    """Clave probable: la letra más marcada por el 27 % con más coincidencias con la moda global."""
    n = M.shape[1]
    moda = []
    for j in range(n):
        vals = [v for v in M[:, j] if v]
        moda.append(max(set(vals), key=vals.count) if vals else "A")
    score = (M == np.array(moda)).sum(axis=1)
    top = M[np.argsort(-score)[:max(1, int(len(M) * top_frac))]]
    out = []
    for j in range(n):
        vals = [v for v in top[:, j] if v]
        out.append(max(set(vals), key=vals.count) if vals else moda[j])
    return "".join(out)


# ── Puntuación ────────────────────────────────────────────────────────────────
def aceptadas(clave: str, decisiones: dict | None = None) -> list:
    """Para cada pregunta, el conjunto de letras que puntúan (None = anulada)."""
    dec = decisiones or {}
    out = []
    for j, c in enumerate(clave):
        d = dec.get(j, {})
        t = d.get("tipo", "")
        if t == "anular":
            out.append(None)
        elif t == "buena":
            out.append(set(LETRAS))
        elif t == "aceptar":
            out.append({c, d.get("letra", c)})
        elif t == "cambiar":
            out.append({d.get("letra", c)})
        else:
            out.append({c})
    return out


def puntuar(M: np.ndarray, acc: list, pen: float = 0.33) -> pd.DataFrame:
    """Aciertos, fallos, blancos, puntuación (R − pen·W; el corrector usa 0,33) y nota sobre 10.
    «Buena para todos» cuenta como acierto aunque esté en blanco."""
    N, n = M.shape
    R = np.zeros(N); W = np.zeros(N); B = np.zeros(N)
    valid = [j for j in range(n) if acc[j] is not None]
    for j in valid:
        col = M[:, j]
        if acc[j] == set(LETRAS):
            R += 1
            continue
        blank = col == ""
        ok = np.array([v in acc[j] for v in col])
        R += ok; B += blank; W += (~ok & ~blank)
    total = R - pen * W
    nota = total / max(1, len(valid)) * 10
    return pd.DataFrame({"Aciertos": R, "Fallos": W, "Blancos": B, "Total": total, "Nota": nota})


def kr20(C: np.ndarray) -> float:
    n = C.shape[1]
    if n < 2 or len(C) < 2:
        return float("nan")
    p = C.mean(axis=0)
    var = C.sum(axis=1).var()
    if var == 0:
        return float("nan")
    return n / (n - 1) * (1 - (p * (1 - p)).sum() / var)


def kr20_margen(C: np.ndarray, B: int = 300, seed: int = 0) -> tuple:
    """Intervalo del 90 % de KR-20 por remuestreo de alumnos (bootstrap)."""
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        v = kr20(C[rng.integers(0, len(C), len(C))])
        if v == v:
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return float(np.percentile(vals, 5)), float(np.percentile(vals, 95))


def _corr(a, b) -> float:
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def analizar(M: np.ndarray, clave: str, k: int = 4) -> dict:
    """Estadísticos por pregunta y del examen (con la clave original, sin decisiones)."""
    N, n = M.shape
    K = np.array(list(clave))
    C = (M == K).astype(float)
    Bl = (M == "")
    X = C.sum(axis=1)
    orden = np.argsort(X, kind="stable")
    g = max(1, int(round(N * 0.27)))
    inf, sup = orden[:g], orden[-g:]
    quint = np.array_split(orden, 5)
    notas = puntuar(M, aceptadas(clave))["Nota"].to_numpy()
    rel = kr20(C)
    items = []
    for j in range(n):
        rest = X - C[:, j]
        opts = {}
        for L in LETRAS:
            m = M[:, j] == L
            opts[L] = {
                "pct": 100 * m.mean(),
                "sup": 100 * m[sup].mean(),
                "inf": 100 * m[inf].mean(),
                "nota": float(notas[m].mean()) if m.any() else float("nan"),
                "n": int(m.sum()),
            }
        keep = [i for i in range(n) if i != j]
        items.append({
            "pos": j + 1,
            "clave": clave[j],
            "acierto": 100 * C[:, j].mean(),
            "blanco": 100 * Bl[:, j].mean(),
            "corregido": 100 * (C[:, j].sum() - ((~Bl[:, j]) & (C[:, j] == 0)).sum() / (k - 1)) / N,
            "disc": _corr(C[:, j], rest),
            "sup": 100 * C[sup, j].mean(),
            "inf": 100 * C[inf, j].mean(),
            "quintiles": [100 * C[q, j].mean() if len(q) else float("nan") for q in quint],
            "kr20_sin": kr20(C[:, keep]),
            "opciones": opts,
        })
    for it in items:
        it["etiquetas"] = etiquetas_item(it, rel)
    return {"items": items, "kr20": rel, "C": C, "X": X, "notas": notas, "N": N, "n": n}


def etiquetas_item(it: dict, rel: float) -> list:
    """Motivos para revisar una pregunta (vacío = sin problemas)."""
    t = []
    d = it["disc"]
    if d == d and d < 0:
        t.append("Discrimina al revés")
    elif d == d and d < 0.15:
        t.append("Discrimina poco")
    for L, o in it["opciones"].items():
        if L != it["clave"] and o["sup"] > it["sup"] and o["pct"] >= 15:
            t.append(f"Distractor {L} atrae a los mejores")
            break
    if it["blanco"] >= 30:
        t.append("Muchos blancos")
    if it["acierto"] >= 90:
        t.append("Muy fácil")
    elif it["acierto"] < 20:
        t.append("Muy difícil")
    if rel == rel and it["kr20_sin"] == it["kr20_sin"] and it["kr20_sin"] - rel > 0.01:
        t.append("Sin ella el examen es más fiable")
    return t


def distractores_inutiles(it: dict, umbral: float = 5.0) -> list:
    return [L for L, o in it["opciones"].items() if L != it["clave"] and o["pct"] < umbral]


def diagnostico(it: dict) -> str:
    """Frase corta con la interpretación de la pregunta."""
    et = it["etiquetas"]
    if not et:
        return "Funciona bien: los que más saben la aciertan más y los distractores cumplen su papel."
    if "Discrimina al revés" in et:
        mejor = max((L for L in LETRAS if L != it["clave"]), key=lambda L: it["opciones"][L]["sup"])
        return (f"La aciertan más los que peor van que los que mejor van. Revisa la clave: "
                f"los mejores marcan sobre todo la {mejor}.")
    if any(e.startswith("Distractor") for e in et):
        L = next(e for e in et if e.startswith("Distractor")).split()[1]
        return (f"La opción {L} atrae a los mejores alumnos más que la correcta: puede ser ambigua "
                f"o también defendible.")
    if "Muchos blancos" in et:
        return "Mucha gente la deja en blanco: puede ser confusa o tratar algo poco trabajado."
    if "Muy fácil" in et:
        return "Casi todos la aciertan: aporta poco para distinguir niveles."
    if "Muy difícil" in et:
        return "Casi nadie la acierta: revisa si el enunciado y la clave son correctos."
    return "Distingue poco entre los que saben más y los que saben menos."


# ── Registro de exámenes (solo datos del examen, nunca de alumnos) ────────────
def get_examenes(dfs: dict) -> pd.DataFrame:
    df = dfs.get(SHEET_EXAMENES)
    if df is None or df.empty:
        return pd.DataFrame(columns=EX_COLS)
    df = df.copy()
    for c in EX_COLS:
        if c not in df.columns:
            df[c] = ""
    return df.fillna("").astype(str)


def get_resultados(dfs: dict) -> pd.DataFrame:
    df = dfs.get(SHEET_PREGUNTAS)
    if df is None or df.empty:
        return pd.DataFrame(columns=PR_COLS)
    df = df.copy()
    for c in PR_COLS:
        if c not in df.columns:
            df[c] = ""
    return df.fillna("").astype(str)


def _j(v, default):
    try:
        x = json.loads(v) if v else default
        return x if isinstance(x, type(default)) else default
    except Exception:
        return default


def examen_info(row) -> dict:
    """Fila de An_Examenes → dict con claves/posiciones/permutaciones ya decodificadas."""
    d = dict(row)
    d["claves"] = _j(d.get("Claves", ""), {})
    d["posiciones"] = _j(d.get("Posiciones", ""), {})
    d["perms"] = _j(d.get("Permutaciones", ""), {})
    return d


def registro_desde_master(master: list, nombre: str, convocatoria: str = "", fecha: str = "",
                          curso: str = "") -> dict:
    """Fila de An_Examenes a partir del «master» de generar_master_examen."""
    claves, pos, perms = {}, {}, {}
    for m in master:
        v = m["letra_version"]
        claves[v] = "".join(p.get("letra_final", "A") for p in m["preguntas"])
        pos[v] = [str(p.get("ID_Pregunta", "")) for p in m["preguntas"]]
        pv = []
        for p in m["preguntas"]:
            orig = [str(o) for o in (p.get("opciones_list") or [])]
            fin = [str(o) for o in (p.get("opciones_finales") or orig)]
            s = ""
            for o in fin[:4]:
                s += LETRAS[orig.index(o)] if o in orig and orig.index(o) < 4 else "?"
            pv.append(s.ljust(4, "?"))
        perms[v] = pv
    n = len(master[0]["preguntas"]) if master else 0
    return {
        "ID_Examen": nombre, "Curso": curso or curso_academico(), "Convocatoria": convocatoria,
        "Nombre": nombre, "Fecha": fecha or datetime.date.today().isoformat(),
        "N_Preguntas": str(n), "N_Modelos": str(len(master)), "Origen": "Generador",
        "Claves": json.dumps(claves), "Posiciones": json.dumps(pos), "Permutaciones": json.dumps(perms),
        "N_Alumnos": "", "Media": "", "KR20": "", "Fecha_Analisis": "",
        "Estado": "Exportado", "Actualizado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def upsert_examen(dfs: dict, fila: dict) -> dict:
    df = get_examenes(dfs)
    df = df[df["ID_Examen"] != fila["ID_Examen"]]
    old = get_examenes(dfs)
    prev = old[old["ID_Examen"] == fila["ID_Examen"]]
    if not prev.empty:   # conservar los datos del análisis si se re-exporta con el mismo nombre
        for c in ("N_Alumnos", "Media", "KR20", "Fecha_Analisis", "Contenido", "Usuario"):
            if not fila.get(c):
                fila[c] = prev.iloc[0][c]
    if not fila.get("Creado"):
        fila["Creado"] = (prev.iloc[0]["Creado"] if not prev.empty and prev.iloc[0]["Creado"]
                          else datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    dfs[SHEET_EXAMENES] = pd.concat([df, pd.DataFrame([{c: fila.get(c, "") for c in EX_COLS}])],
                                    ignore_index=True)
    return dfs


def borrar_examen(dfs: dict, id_examen: str) -> dict:
    dfs[SHEET_EXAMENES] = get_examenes(dfs).query("ID_Examen != @id_examen")
    dfs[SHEET_PREGUNTAS] = get_resultados(dfs).query("ID_Examen != @id_examen")
    return dfs


def guardar_resultados(dfs: dict, id_examen: str, filas: list, resumen: dict) -> dict:
    """Sustituye las filas agregadas de ese examen y actualiza su resumen."""
    df = get_resultados(dfs)
    df = df[df["ID_Examen"] != id_examen]
    nuevas = pd.DataFrame([{c: str(f.get(c, "")) for c in PR_COLS} for f in filas])
    dfs[SHEET_PREGUNTAS] = pd.concat([df, nuevas], ignore_index=True)
    ex = get_examenes(dfs)
    m = ex["ID_Examen"] == id_examen
    for k, v in resumen.items():
        ex.loc[m, k] = str(v)
    dfs[SHEET_EXAMENES] = ex
    return dfs


# ── Unificación de modelos (todo se expresa en el orden y letras del primer modelo) ──
def mapa_ver(vers: list, modelos: list) -> dict:
    """Valor de la columna «Ver» del corrector → letra de modelo."""
    out = {}
    for v in vers:
        s = str(v).strip().upper()
        if s in modelos:
            out[v] = s
        elif s.isdigit() and 1 <= int(s) <= len(modelos):
            out[v] = modelos[int(s) - 1]
        elif len(s) == 1 and s in "ABCDEF":
            out[v] = None          # modelo que no está en el registro (p. ej. se importó solo el A): no se analiza
        else:
            out[v] = modelos[0] if modelos else ""
    return out


def unificar(alumnos: pd.DataFrame, info: dict) -> tuple:
    """Respuestas de todos los modelos en el orden y las letras del primer modelo.
    Requiere posiciones y permutaciones de todos los modelos (exámenes del Generador)."""
    modelos = sorted(info["claves"])
    base = modelos[0]
    n = len(info["claves"][base])
    pos_base = {pid: j for j, pid in enumerate(info["posiciones"][base])}
    inv_base = []
    for s in info["perms"][base]:
        inv_base.append({o: LETRAS[i] for i, o in enumerate(s) if o in LETRAS})
    vmap = mapa_ver(alumnos["Ver"].unique().tolist(), modelos)
    rows = []
    for _, a in alumnos.iterrows():
        v = vmap.get(a["Ver"], base)
        fila = [""] * n
        r = respuestas_matriz([a["Resp"]], n)[0]
        for p, L in enumerate(r):
            if not L:
                continue
            pid = info["posiciones"][v][p]
            j = pos_base.get(pid)
            if j is None:
                continue
            perm = info["perms"][v][p]
            orig = perm[LETRAS.index(L)] if LETRAS.index(L) < len(perm) else "?"
            fila[j] = inv_base[j].get(orig, "")
        rows.append(fila)
    return np.array(rows, dtype=object).reshape(len(rows), n), info["claves"][base]


def cuadran(M: np.ndarray, acc: list, totales, pen: float = 0.33, tol: float = 0.02) -> tuple:
    """(alumnos cuyas puntuaciones coinciden con las del corrector, alumnos con puntuación del corrector)."""
    t = np.asarray(totales, dtype=float)
    ok = np.isfinite(t)
    if not ok.any():
        return 0, 0
    d = np.abs(puntuar(M, acc, pen)["Total"].to_numpy() - t)
    return int((d[ok] <= tol).sum()), int(ok.sum())


def buscar_clave(M: np.ndarray, clave: str, totales, pen: float = 0.33, max_cambios: int = 20) -> list:
    """Busca la clave que reproduce las puntuaciones del corrector cambiando el mínimo de preguntas.
    Devuelve [(pos, tipo, letra)] con tipo en cambiar | aceptar | buena | anular (como las decisiones)."""
    t = np.asarray(totales, dtype=float)
    fin = np.isfinite(t)
    N, n = M.shape
    blank = M == ""

    def contrib(j, S):
        if S == "buena":
            return np.ones(N)
        if S == "anular":
            return np.zeros(N)
        hit = np.isin(M[:, j], list(S))
        return hit * 1.0 - (~hit & ~blank[:, j]) * pen

    cur = {j: {clave[j]} for j in range(min(n, len(clave)))}
    C = {j: contrib(j, cur[j]) for j in cur}
    T = sum(C.values())
    err = lambda x: float(np.abs(x[fin] - t[fin]).sum())
    e0 = err(T)
    cambios = {}
    for _ in range(max_cambios):
        if e0 < 1e-6:
            break
        best = None
        for j in cur:
            c = clave[j]
            cands = [{L} for L in LETRAS] + [{c, L} for L in LETRAS if L != c] + ["buena", "anular"]
            for S in cands:
                if S == cur[j]:
                    continue
                cj = contrib(j, S)
                e = err(T - C[j] + cj)
                if best is None or e < best[0] - 1e-9:
                    best = (e, j, S, cj)
        if best is None or best[0] >= e0 - 1e-6:
            break
        e0, j, S, cj = best
        T = T - C[j] + cj
        C[j], cur[j] = cj, S
        c = clave[j]
        if S in ("buena", "anular"):
            cambios[j] = (j, S, "")
        elif S == {c}:
            cambios.pop(j, None)
        elif len(S) == 1:
            cambios[j] = (j, "cambiar", next(iter(S)))
        else:
            cambios[j] = (j, "aceptar", next(iter(S - {c})))
    return sorted(cambios.values())


def puede_unificar(info: dict) -> bool:
    cl, ps, pr = info.get("claves", {}), info.get("posiciones", {}), info.get("perms", {})
    if len(cl) < 2:
        return False
    return all(v in ps and v in pr and len(ps[v]) == len(cl[v]) and all(ps[v]) for v in cl)


# Fecha del archivo al cargarse (ver _recarga.py)
import os as _os_mt
_MTIME = _os_mt.path.getmtime(__file__)
