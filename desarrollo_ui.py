"""
desarrollo_ui.py – Preguntas de desarrollo: banco en la base de datos (hoja «Desarrollo») y editor.

El editor es el mismo en Generador › Desarrollo (preguntas de un examen) y en Gestor › Desarrollo
(banco). Pestañas: Enunciado (+ Datos) · Apartados · Solución · Rúbrica · Clasificación · Vista previa.

Estructura de una pregunta (la que ya usaba la exportación):
  txt, modo (markdown|latex), pts, espacio, imagen_bytes, imagen_name, imagen_pos, datos_ids,
  subapartados[{enunciado, puntos, espacio, solucion, imagen_bytes, imagen_name, imagen_pos}],
  numeracion_apt, solucion_modelo, criterios[{desc, pts, incremento, apartado}]
  + banco_id, bloque, tema, objetivo, dificultad, etiqueta, usada  (para el banco)
Las imágenes no se guardan en el banco (Google Sheets no admite archivos): viajan con el examen.
"""
from __future__ import annotations

import datetime
import json
import re
import uuid

import pandas as pd
import streamlit as st

SHEET = "Desarrollo"
COLS = ["ID", "Bloque", "Tema", "Objetivo", "Dificultad", "Etiqueta", "Usada", "Modo", "Enunciado", "Puntos",
        "Espacio", "Numeracion", "Apartados", "Solucion", "Criterios", "Datos", "ImagenPos", "Modificada"]
ESP_LABELS = ["Automático", "5 líneas", "10 líneas", "Media Cara", "Cara Completa"]
ESP_APT = ["3cm", "4cm", "5cm", "6cm", "7cm", "8cm", "10cm", "12cm", "15cm", "18cm"]
NUM_LABELS = {"abc": "a) b) c)", "roman": "i) ii) iii)", "num": "1) 2) 3)"}
IMG_POS = {"debajo": "Debajo del texto", "lado": "A la derecha", "centrada": "Centrada"}
PLANTILLAS = {
    "Razonamiento": "**Planteamiento:** …\n\n**Desarrollo:** …\n\n**Conclusión:** …",
    "Cálculo": "**Datos:**\n\n\n**Desarrollo:**\n\n$$\n\n$$\n\n**Resultado:**",
    "Concepto": "**Concepto clave:** …\n\n**Explicación:** …",
}
SN_TEXT_MD = [("B", "**TEXTO**"), ("I", "*TEXTO*"), ("• Lista", "\n- Elemento 1\n- Elemento 2\n"),
              ("1\\. Num", "\n1. Primero\n2. Segundo\n"), ("— Sep", "\n---\n")]
SN_TEXT_TEX = [("B", "\\textbf{TEXTO}"), ("I", "\\textit{TEXTO}"), ("• Lista", "\\begin{itemize}\n  \\item \n\\end{itemize}"),
               ("1\\. Num", "\\begin{enumerate}\n  \\item \n\\end{enumerate}"), ("— Sep", "\\medskip")]
SN_MATH = [("$ …", "$valor$"), ("$$ …", "$$\n\\frac{a}{b}\n$$"), ("½", "$\\frac{num}{den}$"), ("√", "$\\sqrt{x}$"),
           ("xⁿ", "$x^{n}$"), ("xₙ", "$x_{n}$"), ("∑", "$\\sum_{i=1}^{n} x_i$"), ("∫", "$\\int_a^b f(x)\\,dx$"),
           ("αβγ", "$\\alpha$")]
SN_PHYS = [("Dosis", "$D = \\frac{E}{m}$"), ("Actividad", "$A = A_0\\,e^{-\\lambda t}$"),
           ("T½", "$T_{1/2} = \\frac{\\ln 2}{\\lambda}$"), ("Atenuación", "$I = I_0\\,e^{-\\mu x}$"),
           ("μ/ρ", "$\\frac{\\mu}{\\rho}$"), ("HVL", "$HVL = \\frac{\\ln 2}{\\mu}$"), ("E=mc²", "$E = mc^2$"),
           ("SNR", "$SNR = \\frac{\\bar{S}}{\\sigma_S}$")]


# ── Utilidades ────────────────────────────────────────────────────────────────
def _txt(v) -> str:
    s = "" if v is None else str(v)
    return "" if s in ("nan", "None", "NaT") else s


def _f(v, d=0.0) -> float:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return d


def _jl(v, d):
    try:
        x = json.loads(v) if _txt(v) else d
        return x if isinstance(x, type(d)) else d
    except ValueError:
        return d


def etiqueta_apt(i: int, num: str) -> str:
    if num == "roman":
        return ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"][i % 10]
    if num == "num":
        return str(i + 1)
    return "abcdefghij"[i % 10]


def g(x) -> str:
    """Número con coma decimal (0,5)."""
    return f"{x:g}".replace(".", ",")


def puntos(q: dict) -> float:
    apts = q.get("subapartados") or []
    return sum(_f(a.get("puntos"), 0) for a in apts) if apts else _f(q.get("pts"), 1.0)


def nueva() -> dict:
    return {"_uid": uuid.uuid4().hex[:8], "txt": "", "modo": "markdown", "pts": 1.0, "espacio": "Automático",
            "imagen_bytes": None, "imagen_name": "", "imagen_pos": "debajo", "datos_ids": "", "subapartados": [],
            "numeracion_apt": "abc", "solucion_modelo": "", "criterios": [], "banco_id": "", "bloque": "",
            "tema": "", "objetivo": "", "dificultad": "Media", "etiqueta": "", "usada": ""}


def normalizar(q: dict) -> dict:
    base = nueva()
    base.update({k: v for k, v in (q or {}).items() if v is not None or k in ("imagen_bytes",)})
    base["_uid"] = (q or {}).get("_uid") or base["_uid"]
    base["subapartados"] = list(base.get("subapartados") or [])
    for a in base["subapartados"]:
        a.setdefault("enunciado", ""); a.setdefault("puntos", 1.0); a.setdefault("espacio", "5cm")
        a.setdefault("solucion", ""); a.setdefault("imagen_bytes", None); a.setdefault("imagen_name", "")
        a.setdefault("imagen_pos", "debajo")
    base["criterios"] = [dict({"desc": "", "pts": 0.5, "incremento": 0.25, "apartado": None}, **c)
                         for c in (base.get("criterios") or [])]
    return base


def criterios_export(q: dict) -> list:
    """Criterios ordenados por apartado y con su letra delante (la guía de corrección sale agrupada)."""
    apts = q.get("subapartados") or []
    num = q.get("numeracion_apt", "abc")
    out = []
    for c in sorted(q.get("criterios") or [], key=lambda c: (c.get("apartado") is None, c.get("apartado") or 0)):
        a = c.get("apartado")
        desc = c.get("desc", "")
        if apts and a is not None and 0 <= int(a) < len(apts):
            desc = f"{etiqueta_apt(int(a), num)}) {desc}"
        out.append({"desc": desc, "pts": c.get("pts", 0), "incremento": c.get("incremento", 0.25)})
    return out


# ── Banco (hoja «Desarrollo») ────────────────────────────────────────────────
def get_banco(dfs: dict) -> pd.DataFrame:
    df = dfs.get(SHEET)
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    df = df.copy()
    for c in COLS:
        if c not in df.columns:
            df[c] = ""
    return df[COLS].fillna("").astype(str)


def fila_a_pregunta(r) -> dict:
    q = nueva()
    q.update({"banco_id": _txt(r["ID"]), "bloque": _txt(r["Bloque"]), "tema": _txt(r["Tema"]).removesuffix(".0"),
              "objetivo": _txt(r["Objetivo"]), "dificultad": _txt(r["Dificultad"]) or "Media",
              "etiqueta": _txt(r["Etiqueta"]), "usada": _txt(r["Usada"]), "modo": _txt(r["Modo"]) or "markdown",
              "txt": _txt(r["Enunciado"]), "pts": _f(r["Puntos"], 1.0), "espacio": _txt(r["Espacio"]) or "Automático",
              "numeracion_apt": _txt(r["Numeracion"]) or "abc", "subapartados": _jl(r["Apartados"], []),
              "solucion_modelo": _txt(r["Solucion"]), "criterios": _jl(r["Criterios"], []),
              "datos_ids": _txt(r["Datos"]), "imagen_pos": _txt(r["ImagenPos"]) or "debajo"})
    return normalizar(q)


def pregunta_a_fila(q: dict) -> dict:
    apts = [{k: a.get(k) for k in ("enunciado", "puntos", "espacio", "solucion", "imagen_pos")}
            for a in q.get("subapartados") or []]
    return {"ID": q.get("banco_id", ""), "Bloque": q.get("bloque", ""), "Tema": str(q.get("tema", "") or ""),
            "Objetivo": q.get("objetivo", ""), "Dificultad": q.get("dificultad", ""), "Etiqueta": q.get("etiqueta", ""),
            "Usada": q.get("usada", ""), "Modo": q.get("modo", "markdown"), "Enunciado": q.get("txt", ""),
            "Puntos": f"{puntos(q):g}", "Espacio": q.get("espacio", "Automático"),
            "Numeracion": q.get("numeracion_apt", "abc"), "Apartados": json.dumps(apts, ensure_ascii=False),
            "Solucion": q.get("solucion_modelo", ""),
            "Criterios": json.dumps([{k: c.get(k) for k in ("desc", "pts", "incremento", "apartado")}
                                     for c in q.get("criterios") or []], ensure_ascii=False),
            "Datos": q.get("datos_ids", ""), "ImagenPos": q.get("imagen_pos", "debajo"),
            "Modificada": datetime.date.today().isoformat()}


def nuevo_id(banco: pd.DataFrame, bloque: str, tema: str) -> str:
    b = (str(bloque).split()[-1] if str(bloque).strip() else "GEN").upper()
    t = str(tema or "0").removesuffix(".0")
    t = f"{int(t):02d}" if t.isdigit() else (t or "00")
    pre = f"DES_{b}_{t}_"
    nums = [int(x[len(pre):]) for x in banco["ID"] if x.startswith(pre) and x[len(pre):].isdigit()]
    return f"{pre}{(max(nums) + 1) if nums else 1:02d}"


def guardar_en_banco(q: dict, nueva_copia: bool = False) -> str:
    """Crea o actualiza la pregunta en el banco y lo persiste. Devuelve su ID."""
    from app_utils import guardar_hojas
    dfs = st.session_state.excel_dfs
    banco = get_banco(dfs)
    if nueva_copia or not q.get("banco_id") or q["banco_id"] not in set(banco["ID"]):
        q["banco_id"] = nuevo_id(banco, q.get("bloque", ""), q.get("tema", ""))
    fila = pregunta_a_fila(q)
    banco = banco[banco["ID"] != q["banco_id"]]
    dfs[SHEET] = pd.concat([banco, pd.DataFrame([fila])], ignore_index=True)
    guardar_hojas([SHEET])
    return q["banco_id"]


def eliminar_de_banco(ids: list):
    from app_utils import guardar_hojas
    dfs = st.session_state.excel_dfs
    dfs[SHEET] = get_banco(dfs)[lambda d: ~d["ID"].isin(set(ids))]
    guardar_hojas([SHEET])


def marcar_usadas(ids: list, fecha: str):
    from app_utils import guardar_hojas
    if not ids:
        return
    dfs = st.session_state.excel_dfs
    b = get_banco(dfs)
    if b.empty:
        return
    b.loc[b["ID"].isin(set(ids)), "Usada"] = fecha
    dfs[SHEET] = b
    guardar_hojas([SHEET])


def banco_como_tabla(banco: pd.DataFrame) -> pd.DataFrame:
    """El banco con las columnas que esperan los filtros comunes y la tabla (ID_Pregunta, enunciado…)."""
    rows = []
    for _, r in banco.iterrows():
        q = fila_a_pregunta(r)
        apts = q["subapartados"]
        sol = bool(_txt(q["solucion_modelo"]).strip() or any(_txt(a.get("solucion")).strip() for a in apts))
        rows.append({"ID_Pregunta": q["banco_id"], "bloque": q["bloque"], "Tema": q["tema"], "objetivo": q["objetivo"],
                     "dificultad": q["dificultad"], "comentario": q["etiqueta"], "usada": q["usada"],
                     "enunciado": re.sub(r"\s+", " ", q["txt"]), "opciones_list": [a.get("enunciado", "") for a in apts],
                     "notas": "", "solucion": "sí" if sol else "", "_pts": puntos(q), "_napt": len(apts),
                     "_rub": bool(q["criterios"])})
    return pd.DataFrame(rows, columns=["ID_Pregunta", "bloque", "Tema", "objetivo", "dificultad", "comentario", "usada",
                                       "enunciado", "opciones_list", "notas", "solucion", "_pts", "_napt", "_rub"])


# ── Vista HTML (para la vista en directo y la vista previa LaTeX) ────────────
def md_html(text: str) -> str:
    """Markdown + LaTeX → HTML para la vista previa; las figuras TikZ se muestran como imagen."""
    import figuras
    if figuras.tiene(text):
        extra = (st.session_state.get("exam_cfg") or {}).get("preambulo_extra", "")
        return figuras.html(text, _md_html_base, extra)
    return _md_html_base(text)


def _md_html_base(text: str) -> str:
    math = []

    def keep(m):
        math.append(m.group(0))
        return f"\x00M{len(math) - 1}\x00"
    t = re.sub(r"\$\$.+?\$\$", keep, text or "", flags=re.DOTALL)
    t = re.sub(r"\$.+?\$", keep, t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", t)
    t = re.sub(r"\\textbf\{([^}]*)\}", r"<strong>\1</strong>", t)
    t = re.sub(r"\\textit\{([^}]*)\}", r"<em>\1</em>", t)
    for i, m in enumerate(math):
        t = t.replace(f"\x00M{i}\x00", m)
    return t.replace("\n", "<br>")


def _mathjax(html: str, height: int):
    import streamlit.components.v1 as stc
    from app_utils import mathjax_html
    stc.html(mathjax_html(html), height=height, scrolling=True)


def vista_html(q: dict, con_sol: bool, n: int = 1, datos_txt: str = "") -> str:
    apts = q.get("subapartados") or []
    num = q.get("numeracion_apt", "abc")
    h = (f"<div style='line-height:1.65'><b>{n}.</b> {md_html(q.get('txt', ''))} "
         f"<span style='color:var(--muted)'>({puntos(q):g} pt)</span>")
    if datos_txt:
        h += f"<div style='margin-top:6px;font-size:.92em'><b>Datos:</b> {datos_txt}</div>"
    for i, a in enumerate(apts):
        h += (f"<div style='margin:8px 0 0 16px'><b>{etiqueta_apt(i, num)})</b> {md_html(a.get('enunciado', ''))} "
              f"<span style='color:var(--muted)'>({_f(a.get('puntos'), 0):g} pt)</span>")
        if con_sol and _txt(a.get("solucion")).strip():
            h += (f"<div style='margin-top:4px;padding:6px 10px;border-left:3px solid var(--ok);background:var(--ok-bg);"
                  f"border-radius:0 6px 6px 0'>{md_html(a['solucion'])}</div>")
        elif not con_sol:
            h += "<div style='height:46px;border:1px dashed var(--border2);border-radius:6px;margin-top:4px'></div>"
        h += "</div>"
    if con_sol and not apts and _txt(q.get("solucion_modelo")).strip():
        h += (f"<div style='margin-top:10px;padding:8px 12px;border-left:3px solid var(--ok);background:var(--ok-bg);"
              f"border-radius:0 6px 6px 0'><b style='color:var(--ok)'>Solución:</b> {md_html(q['solucion_modelo'])}</div>")
    if not con_sol and not apts:
        h += "<div style='height:70px;border:1px dashed var(--border2);border-radius:6px;margin-top:8px'></div>"
    return h + "</div>"


# ── Importar desde texto ─────────────────────────────────────────────────────
FORMATO_TEXTO = r"""## Un haz de ultrasonidos de 5 MHz incide sobre la interfase músculo–hueso.
\begin{tikzpicture}
  \draw[->] (0,0) -- (2,0) node[right] {$x$};
\end{tikzpicture}
a) [1 pt] Calcula el coeficiente de reflexión $R$.
Solución: $$R = \left(\frac{Z_h - Z_m}{Z_h + Z_m}\right)^2 \approx 0{,}41$$
Criterio: Planteamiento de R | 0,5
Criterio: Cálculo con unidades | 0,5
b) [1 pt] ¿Qué fracción llega al hueso?
Solución: $T = 1 - R$
Bloque: III · Tema: 9 · Dificultad: Media

## Siguiente pregunta…"""

_CLAVES_TXT = ("solución", "solucion", "criterio", "bloque", "tema", "dificultad", "puntos", "espacio", "etiqueta", "objetivo")


def parse_texto(texto: str, bloques: list | None = None) -> tuple:
    """Texto plano con LaTeX (y figuras TikZ) → (preguntas, avisos). Formato: FORMATO_TEXTO."""
    import figuras
    qs, avisos = [], []
    q = apt = None
    campo = None            # dónde va la línea siguiente: ("txt",) | ("apt",) | ("sol_apt",) | ("sol",)
    en_fig = False

    def _num(x):
        try:
            return float(str(x).replace(",", ".").strip())
        except ValueError:
            return None

    def _bloque(v):
        v = v.strip()
        for b in bloques or []:
            if v.lower() == str(b).lower() or str(b).lower().endswith(" " + v.lower()):
                return b
        return ("BLOQUE " + v) if re.fullmatch(r"[IVXLC]+", v.upper()) else v

    def _add(texto_):
        nonlocal q, apt
        if campo == "txt":
            q["txt"] += texto_
        elif campo == "apt":
            apt["enunciado"] += texto_
        elif campo == "sol_apt":
            apt["solucion"] += texto_
        elif campo == "sol":
            q["solucion_modelo"] += texto_

    for linea in (texto or "").splitlines():
        l = linea.rstrip()
        empieza = re.search(r"\\begin\{(tikzpicture|circuitikz)\}", l)
        if en_fig or empieza:          # dentro de una figura: todo es código, nada de marcadores
            if q is not None and campo:
                _add("\n" + l)
            if empieza:
                en_fig = True
            if re.search(r"\\end\{(tikzpicture|circuitikz)\}", l):
                en_fig = False
            continue
        m = re.match(r"^#{2,3}\s*(.*)$", l)
        if m:
            q = nueva()
            q["txt"] = m.group(1).strip()
            qs.append(q)
            apt, campo = None, "txt"
            continue
        if q is None:
            continue
        m = re.match(r"^\s*([a-z]|[ivx]{1,4}|\d{1,2})\)\s*(?:\[\s*([\d.,]+)\s*pts?\.?\s*\])?\s*(.*)$", l, re.I)
        if m and not l.lower().startswith(_CLAVES_TXT):
            apt = {"enunciado": m.group(3).strip(), "puntos": _num(m.group(2)) if m.group(2) else 1.0, "espacio": "5cm",
                   "solucion": "", "imagen_bytes": None, "imagen_name": "", "imagen_pos": "debajo"}
            q["subapartados"].append(apt)
            if m.group(1).lower() in ("i", "ii", "iii", "iv", "v") and len(q["subapartados"]) == 1 and m.group(1).lower() == "i":
                q["numeracion_apt"] = "roman"
            elif m.group(1).isdigit():
                q["numeracion_apt"] = "num"
            campo = "apt"
            continue
        m = re.match(r"^\s*soluci[oó]n\s*:\s*(.*)$", l, re.I)
        if m:
            campo = "sol_apt" if apt is not None else "sol"
            _add(m.group(1).strip())
            continue
        m = re.match(r"^\s*criterio\s*:\s*(.*?)\s*(?:\|\s*([\d.,]+))?\s*$", l, re.I)
        if m:
            q["criterios"].append({"desc": m.group(1).strip(), "pts": _num(m.group(2)) or 0.5, "incremento": 0.25,
                                   "apartado": (len(q["subapartados"]) - 1) if apt is not None else None})
            continue
        if re.match(r"^\s*(bloque|tema|dificultad|puntos|espacio|etiqueta|objetivo)\s*:", l, re.I):
            for k, v in re.findall(r"(bloque|tema|dificultad|puntos|espacio|etiqueta|objetivo)\s*:\s*([^·|;]+)", l, re.I):
                k, v = k.lower(), v.strip()
                if k == "bloque":
                    q["bloque"] = _bloque(v)
                elif k == "tema":
                    q["tema"] = v.removesuffix(".0")
                elif k == "dificultad":
                    q["dificultad"] = {"facil": "Facil", "fácil": "Facil", "media": "Media", "dificil": "Dificil",
                                       "difícil": "Dificil"}.get(v.lower(), v.title())
                elif k == "puntos":
                    q["pts"] = _num(v) or q["pts"]
                elif k == "espacio":
                    q["espacio"] = v
                elif k in ("etiqueta", "objetivo"):
                    q[k] = v
            campo = None
            continue
        if campo:
            _add("\n" + l)
    for i, qq in enumerate(qs):
        for k in ("txt", "solucion_modelo"):
            qq[k] = qq[k].strip()
        for a in qq["subapartados"]:
            a["enunciado"], a["solucion"] = a["enunciado"].strip(), a["solucion"].strip()
        if not qq["txt"]:
            avisos.append(f"La pregunta {i + 1} no tiene enunciado.")
    return [normalizar(x) for x in qs if x["txt"] or x["subapartados"]], avisos


def ui_importar_texto(k: str, destino: str):
    """Pegar preguntas de desarrollo en texto plano (con LaTeX y TikZ). Devuelve la lista para añadir o None."""
    import figuras
    with st.popover("Desde texto", use_container_width=True):
        st.markdown("Pega una o varias preguntas. Cada pregunta empieza por `##`; los apartados por `a)` (con `[1 pt]` "
                    "opcional); `Solución:` y `Criterio: texto | puntos` van detrás de lo que corresponda; al final, "
                    "`Bloque: … · Tema: … · Dificultad: …`. Las fórmulas, tal cual (`$…$`, `$$…$$`) y las figuras como "
                    "`\\begin{tikzpicture}…\\end{tikzpicture}`.")
        with st.expander("Ver un ejemplo"):
            st.code(FORMATO_TEXTO, language="latex")
        txt = st.text_area("Texto", height=260, key=f"{k}_txt", label_visibility="collapsed",
                           placeholder="## Enunciado de la pregunta…")
        if not txt.strip():
            return None
        qs, avisos = parse_texto(txt, list(st.session_state.get("bloques") or []))
        for a in avisos:
            st.warning(a)
        if not qs:
            st.caption("No se ha reconocido ninguna pregunta (¿falta el `##` del principio?).")
            return None
        st.markdown(f"**{len(qs)} pregunta(s) reconocidas:**")
        for i, q in enumerate(qs, 1):
            nf = sum(len(figuras.bloques(x)) for x in [q["txt"], q["solucion_modelo"]]
                     + [a["enunciado"] + a["solucion"] for a in q["subapartados"]])
            st.markdown(f"<div class='devq-s'>{i}. {re.sub(chr(92) + 'begin.*', '…', q['txt'])[:90]} · "
                        f"{len(q['subapartados'])} apartados · {len(q['criterios'])} criterios"
                        f"{f' · {nf} figura(s)' if nf else ''} · {q['bloque'] or 'sin bloque'}</div>", unsafe_allow_html=True)
        if st.button(f"Añadir {len(qs)} {destino}", type="primary", key=f"{k}_ok", use_container_width=True):
            st.session_state.pop(f"{k}_txt", None)
            return qs
    return None


# ── Editor ────────────────────────────────────────────────────────────────────
def _toolbar(k: str, campo: str, q_get, q_set, grupos):
    """Barras de inserción en una fila compacta; cada botón añade el fragmento al final del texto."""
    with st.container(horizontal=True, gap="small", key=f"devtb_{k}"):
        for nombre, items in grupos:
            st.markdown(f"<span class='devtb-l'>{nombre}</span>", unsafe_allow_html=True)
            for j, (lbl, snip) in enumerate(items):
                if st.button(lbl, key=f"{k}_{nombre[:3]}_{j}"):
                    nuevo = q_get() + snip
                    q_set(nuevo)
                    st.session_state[campo] = nuevo   # el cuadro de texto aún no se ha dibujado en esta ejecución


def _ta(col, key: str, inicial: str, **kw) -> str:
    """Cuadro de texto cuyo valor vive en session_state (así las barras de símbolos pueden escribir en él)."""
    if key not in st.session_state:
        st.session_state[key] = inicial or ""
    return col.text_area(kw.pop("label", "Texto"), key=key, label_visibility="collapsed", **kw)


def _live(k: str, texto: str, modo: str, alto: int, sol: bool = False):
    """Vista en directo de un texto con fórmulas."""
    if modo == "markdown" and "\\begin" not in texto:
        with st.container(border=True, height=alto, key=f"devlv{'s' if sol else ''}_{k}"):
            st.markdown(texto if texto.strip() else "*La vista previa aparecerá aquí.*")
    else:
        _mathjax(f"<div style='font-size:14px;line-height:1.6'>{md_html(texto) or '<i>Vista previa</i>'}</div>", alto)


def editor(q: dict, k: str, bloques: list, en_examen: bool = True, pts_en_editor: bool = True):
    """Dibuja el editor completo de la pregunta `q` (la modifica en sitio). `k`: prefijo único de claves."""
    from app_utils import (nombre_bloque, nombre_tema, objetivos_de_tema, nombre_objetivo, temas_de_bloque)
    import examen_lib_latex as lib
    ss = st.session_state
    q.update(normalizar(q))
    apts = q["subapartados"]
    md = q.get("modo", "markdown") == "markdown"

    import figuras
    figuras.boton([q.get("txt", ""), q.get("solucion_modelo", "")]
                  + [x.get("enunciado", "") + "\n" + x.get("solucion", "") for x in apts], k,
                  (ss.get("exam_cfg") or {}).get("preambulo_extra", ""))
    t_en, t_ap, t_so, t_ru, t_cl, t_pv = st.tabs(["Enunciado", "Apartados", "Solución", "Rúbrica", "Clasificación",
                                                  "Vista previa (LaTeX)"])
    grupos = [("TEXTO", SN_TEXT_MD if md else SN_TEXT_TEX), ("MATEMÁTICAS", SN_MATH), ("FÍSICA MÉDICA", SN_PHYS)]

    # ── Enunciado (+ Datos) ───────────────────────────────────────────────────
    with t_en:
        ck = f"{k}_txt"
        _toolbar(f"{k}_tbe", ck, lambda: ss.get(ck, q["txt"]), lambda v: q.__setitem__("txt", v), grupos)
        with st.expander("Guía rápida de escritura"):
            st.markdown("Texto normal y fórmulas entre `$…$` (en línea) o `$$…$$` (en bloque). "
                        "`**negrita**`, `*cursiva*`, listas con `- ` o `1. `. Ejemplos: `$D = \\frac{E}{m}$`, "
                        "`$I = I_0 e^{-\\mu x}$`, `$\\alpha$`, `$\\mu$`." if md else
                        "LaTeX puro: `\\textbf{…}`, `\\textit{…}`, `$…$`, `\\[…\\]`, `itemize`/`enumerate`.")
        c1, c2 = st.columns(2)
        q["txt"] = _ta(c1, ck, q["txt"], height=200, placeholder="Escribe el enunciado… Fórmulas entre $…$")
        with c2:
            _live(ck, q["txt"], q["modo"], 200)
        i1, i2 = st.columns([1, 2.2], vertical_alignment="bottom")
        q["imagen_pos"] = i1.selectbox("Posición de la imagen", list(IMG_POS), format_func=IMG_POS.get,
                                       index=list(IMG_POS).index(q.get("imagen_pos", "debajo")) if q.get("imagen_pos") in IMG_POS else 0,
                                       key=f"{k}_imgpos")
        up = i2.file_uploader("Imagen del enunciado (PNG/JPG) · se guarda con el examen", type=["png", "jpg", "jpeg"],
                              key=f"{k}_img")
        if up is not None:
            q["imagen_bytes"], q["imagen_name"] = up.getvalue(), up.name
        if q.get("imagen_bytes"):
            m1, m2 = st.columns([4, 1], vertical_alignment="center")
            m1.image(q["imagen_bytes"], width=220, caption=q.get("imagen_name", ""))
            if m2.button("Quitar imagen", key=f"{k}_imgdel"):
                q["imagen_bytes"], q["imagen_name"] = None, ""
        if not apts:
            p1, p2, _ = st.columns([1, 1.4, 2])
            if pts_en_editor:
                q["pts"] = p1.number_input("Puntos", min_value=0.0, step=0.5, value=_f(q.get("pts"), 1.0), key=f"{k}_pts")
            else:
                p1.markdown(f"<div style='padding-top:30px'>Puntos: <b>{_f(q.get('pts'), 1.0):g}</b> "
                            "<small style='color:var(--muted)'>(arriba, en la lista)</small></div>", unsafe_allow_html=True)
            q["espacio"] = p2.selectbox("Espacio para responder", ESP_LABELS,
                                        index=ESP_LABELS.index(q["espacio"]) if q.get("espacio") in ESP_LABELS else 0,
                                        key=f"{k}_esp")
        # Datos (constantes)
        ddf = lib.get_datos_df(ss.get("excel_dfs", {}))
        with st.container(border=True, key=f"card_{k}_datos"):
            st.markdown("**Datos** <span style='color:var(--muted);font-size:.85rem'>· constantes que se imprimen "
                        "bajo el enunciado (Configuración › Constantes)</span>", unsafe_allow_html=True)
            if ddf.empty or not ddf["ID"].astype(str).str.strip().any():
                st.caption("No hay constantes en la base de datos. Añádelas en Configuración › Constantes.")
            else:
                opts = [str(x).strip() for x in ddf["ID"] if str(x).strip()]
                lab = {str(r["ID"]).strip(): f"{_txt(r.get('Nombre'))} · {_txt(r.get('Símbolo'))} = {_txt(r.get('Valor'))} {_txt(r.get('Unidades'))}".strip()
                       for _, r in ddf.iterrows()}
                cur = [x for x in (q.get("datos_ids") or "").split(",") if x.strip() in opts]
                sel = st.multiselect("Constantes", opts, default=cur, key=f"{k}_datos", format_func=lambda x: lab.get(x, x),
                                     label_visibility="collapsed", placeholder="Añadir constante…")
                q["datos_ids"] = ",".join(sel)
                if sel:
                    st.caption(f"Así sale en el examen → Datos: {lib.format_datos_word(q['datos_ids'], ddf)}")

    # ── Apartados ─────────────────────────────────────────────────────────────
    with t_ap:
        h1, h2 = st.columns([2, 1.2], vertical_alignment="center")
        with h1.container(key=f"seg_{k}_num"):
            q["numeracion_apt"] = st.radio("Numeración", list(NUM_LABELS), format_func=NUM_LABELS.get, horizontal=True,
                                           index=list(NUM_LABELS).index(q.get("numeracion_apt", "abc")), key=f"{k}_num")
        h2.markdown(f"<div style='text-align:right;color:var(--muted)'>{len(apts)} apartado{'s' if len(apts) != 1 else ''}"
                    f"{' · total <b>' + format(puntos(q), 'g') + ' pt</b>' if apts else ''}</div>", unsafe_allow_html=True)
        abiertos = ss.setdefault(f"_{k}_apt_open", set(range(len(apts))) if len(apts) <= 2 else {0})
        accion = None
        for i, a in enumerate(apts):
            lt = etiqueta_apt(i, q["numeracion_apt"])
            with st.container(border=True, key=f"card_{k}_apt_{i}"):
                r = st.columns([0.35, 3.2, 1.1, 1.4, 0.4, 0.4, 0.4, 0.4], vertical_alignment="center")
                r[0].markdown(f"**{lt})**")
                if i in abiertos:
                    r[1].caption("Enunciado del apartado · la solución está en la pestaña Solución")
                    a["puntos"] = r[2].number_input("Puntos", min_value=0.0, step=0.5, value=_f(a.get("puntos"), 1.0),
                                                    key=f"{k}_apts_{i}")
                    a["espacio"] = r[3].selectbox("Espacio", ESP_APT, key=f"{k}_apte_{i}",
                                                  index=ESP_APT.index(a["espacio"]) if a.get("espacio") in ESP_APT else 2)
                else:
                    r[1].markdown(f"<div style='white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                                  f"{_txt(a.get('enunciado')) or '<i>(vacío)</i>'}</div>", unsafe_allow_html=True)
                    r[2].markdown(f"**{_f(a.get('puntos'), 0):g} pt**")
                    r[3].caption(a.get("espacio", ""))
                if r[4].button("▾" if i in abiertos else "▸", key=f"{k}_apto_{i}", help="Plegar / desplegar"):
                    abiertos.symmetric_difference_update({i})
                if r[5].button("↑", key=f"{k}_aptu_{i}", disabled=i == 0):
                    accion = ("up", i)
                if r[6].button("↓", key=f"{k}_aptd_{i}", disabled=i == len(apts) - 1):
                    accion = ("down", i)
                if r[7].button("×", key=f"{k}_aptx_{i}", help="Eliminar apartado"):
                    accion = ("del", i)
                if i in abiertos:
                    ak = f"{k}_apt_{i}_txt"
                    _toolbar(f"{k}_tba_{i}", ak, lambda a=a, ak=ak: ss.get(ak, a["enunciado"]),
                             lambda v, a=a: a.__setitem__("enunciado", v), [("MATEMÁTICAS", SN_MATH)])
                    e1, e2 = st.columns(2)
                    a["enunciado"] = _ta(e1, ak, a.get("enunciado", ""), height=90,
                                         placeholder=f"Enunciado del apartado {lt})…")
                    with e2:
                        _live(ak, a["enunciado"], q["modo"], 90)
                    g1, g2 = st.columns([1, 2.2], vertical_alignment="bottom")
                    a["imagen_pos"] = g1.selectbox("Posición imagen", list(IMG_POS), format_func=IMG_POS.get, key=f"{k}_apip_{i}",
                                                   index=list(IMG_POS).index(a.get("imagen_pos", "debajo")) if a.get("imagen_pos") in IMG_POS else 0)
                    aup = g2.file_uploader("Imagen del apartado (opcional)", type=["png", "jpg", "jpeg"], key=f"{k}_apimg_{i}")
                    if aup is not None:
                        a["imagen_bytes"], a["imagen_name"] = aup.getvalue(), aup.name
                    if a.get("imagen_bytes"):
                        st.caption(f"Imagen: {a.get('imagen_name', '')}")
        if accion:
            tipo, i = accion
            if tipo == "del":
                apts.pop(i)
                q["criterios"] = [dict(c, apartado=(None if c.get("apartado") == i else
                                                    (c["apartado"] - 1 if c.get("apartado") is not None and c["apartado"] > i else c.get("apartado"))))
                                  for c in q["criterios"]]
            else:
                j = i - 1 if tipo == "up" else i + 1
                apts[i], apts[j] = apts[j], apts[i]
                for c in q["criterios"]:
                    if c.get("apartado") == i:
                        c["apartado"] = j
                    elif c.get("apartado") == j:
                        c["apartado"] = i
            for kk in [x for x in ss.keys() if str(x).startswith(f"{k}_apt") or str(x).startswith(f"{k}_ap") or str(x).startswith(f"{k}_sol_")]:
                del ss[kk]
            ss[f"_{k}_apt_open"] = set()
            st.rerun()
        if st.button("➕ Añadir apartado", key=f"{k}_aptadd", type="primary"):
            apts.append({"enunciado": "", "puntos": 1.0, "espacio": "5cm", "solucion": "", "imagen_bytes": None,
                         "imagen_name": "", "imagen_pos": "debajo"})
            abiertos.add(len(apts) - 1)
            st.rerun()

    # ── Solución ──────────────────────────────────────────────────────────────
    with t_so:
        pl = st.columns([1.2, 1, 1, 1, 3], vertical_alignment="center")
        pl[0].caption("Plantillas:")
        destino = f"{k}_sol_g" if not apts else f"{k}_sol_0"
        for j, (nom, tpl) in enumerate(PLANTILLAS.items()):
            if pl[1 + j].button(nom, key=f"{k}_tpl_{j}", use_container_width=True):
                if not apts:
                    q["solucion_modelo"] = (q.get("solucion_modelo", "") + ("\n\n" if q.get("solucion_modelo") else "") + tpl)
                    ss[destino] = q["solucion_modelo"]
                else:
                    apts[0]["solucion"] = apts[0].get("solucion", "") + tpl
                    ss[destino] = apts[0]["solucion"]
        if not apts:
            sk = f"{k}_sol_g"
            _toolbar(f"{k}_tbs", sk, lambda: ss.get(sk, q["solucion_modelo"]), lambda v: q.__setitem__("solucion_modelo", v), grupos)
            s1, s2 = st.columns(2)
            q["solucion_modelo"] = _ta(s1, sk, q["solucion_modelo"], height=200, placeholder="Solución modelo…")
            with s2:
                _live(sk, q["solucion_modelo"], q["modo"], 200, sol=True)
        else:
            st.caption("La solución de cada apartado (sale en el solucionario y en la guía de corrección).")
            for i, a in enumerate(apts):
                lt = etiqueta_apt(i, q["numeracion_apt"])
                st.markdown(f"<div class='dev-apref'><b>{lt})</b> {md_html(_txt(a.get('enunciado')))[:220] or '<i>(sin enunciado)</i>'} "
                            f"<small>· {_f(a.get('puntos'), 0):g} pt</small></div>", unsafe_allow_html=True)
                sk = f"{k}_sol_{i}"
                s1, s2 = st.columns(2)
                a["solucion"] = _ta(s1, sk, a.get("solucion", ""), height=90, placeholder=f"Solución del apartado {lt})…")
                with s2:
                    _live(sk, a["solucion"], q["modo"], 90, sol=True)

    # ── Rúbrica (por apartado) ────────────────────────────────────────────────
    with t_ru:
        crit = q["criterios"]
        grupos_r = ([(i, f"{etiqueta_apt(i, q['numeracion_apt'])}) {(_txt(a.get('enunciado')) or '').replace('$', '')[:70]}", _f(a.get("puntos"), 0))
                     for i, a in enumerate(apts)] if apts else [(None, "Toda la pregunta", puntos(q))])
        if apts and any(c.get("apartado") is None for c in crit):
            grupos_r.append((None, "Criterios generales de la pregunta (asígnalos a un apartado)", 0))
        tot = sum(_f(c.get("pts"), 0) for c in crit)
        st.markdown(f"<div style='display:flex;justify-content:space-between;margin-bottom:8px'>"
                    f"<span style='color:var(--muted)'>Criterios de corrección: salen en la guía de corrección.</span>"
                    f"<span>Total rúbrica <b>{g(tot)}</b> / pregunta <b>{g(puntos(q))} pt</b> "
                    f"{'✓' if abs(tot - puntos(q)) < 0.01 or not crit else '<span class=dev-warn>no cuadra</span>'}</span></div>",
                    unsafe_allow_html=True)
        borrar = None
        for gi, (ap_i, titulo, pts_g) in enumerate(grupos_r):
            idx = [n for n, c in enumerate(crit) if c.get("apartado") == ap_i]
            sub = sum(_f(crit[n].get("pts"), 0) for n in idx)
            with st.container(border=True, key=f"card_{k}_rub_{gi}"):
                ok = abs(sub - pts_g) < 0.01 or (ap_i is None and apts)
                st.markdown(f"<div style='display:flex;justify-content:space-between'><b>{titulo}</b>"
                            + (f"<span>criterios <b>{g(sub)}</b> / apartado <b>{g(pts_g)} pt</b> "
                               f"{'✓' if ok else '<span class=dev-warn>no cuadra</span>'}</span>" if not (ap_i is None and apts) else "")
                            + "</div>", unsafe_allow_html=True)
                if idx:
                    hh = st.columns([4, 1, 1, 1.6, 0.4])
                    for c_, t_ in zip(hh, ["Criterio", "Pts máx", "Incremento", "Valores posibles", ""]):
                        c_.markdown(f"<span class='dev-hd'>{t_}</span>", unsafe_allow_html=True)
                for n in idx:
                    c = crit[n]
                    rr = st.columns([4, 1, 1, 1.6, 0.4], vertical_alignment="center")
                    c["desc"] = rr[0].text_input("Criterio", c.get("desc", ""), key=f"{k}_cd_{n}", label_visibility="collapsed",
                                                 placeholder="Descripción del criterio…")
                    c["pts"] = rr[1].number_input("pts", min_value=0.0, step=0.25, value=_f(c.get("pts"), 0.5), key=f"{k}_cp_{n}",
                                                  label_visibility="collapsed")
                    c["incremento"] = rr[2].number_input("inc", min_value=0.0, step=0.05, value=_f(c.get("incremento"), 0.25),
                                                         key=f"{k}_ci_{n}", label_visibility="collapsed")
                    niv = ""
                    if c["incremento"] > 0 and c["pts"] > 0:
                        niv = " · ".join(g(c['incremento'] * j) for j in range(int(round(c["pts"] / c["incremento"])) + 1))[:60]
                    rr[3].markdown(f"<span class='dev-niv'>{niv}</span>", unsafe_allow_html=True)
                    if apts and ap_i is None:
                        pass
                    if rr[4].button("×", key=f"{k}_cx_{n}"):
                        borrar = n
                    if apts and ap_i is None:
                        sel = st.selectbox("Asignar a apartado", [None] + list(range(len(apts))), key=f"{k}_ca_{n}",
                                           format_func=lambda x: "— general —" if x is None else f"{etiqueta_apt(x, q['numeracion_apt'])})")
                        c["apartado"] = sel
                lbl_add = f"➕ Criterio para {etiqueta_apt(ap_i, q['numeracion_apt'])})" if ap_i is not None else "➕ Añadir criterio"
                if not (ap_i is None and apts) and st.button(lbl_add, key=f"{k}_cadd_{gi}"):
                    crit.append({"desc": "", "pts": 0.5, "incremento": 0.25, "apartado": ap_i})
                    st.rerun()
        if borrar is not None:
            crit.pop(borrar)
            for kk in [x for x in ss.keys() if re.match(rf"^{re.escape(k)}_c[dpia]_\d+$", str(x))]:
                del ss[kk]
            st.rerun()

    # ── Clasificación ─────────────────────────────────────────────────────────
    with t_cl:
        st.caption("Para buscarla y filtrarla en el banco, la receta y las estadísticas.")
        a1, a2 = st.columns(2)
        blq_opts = [""] + list(bloques)
        q["bloque"] = a1.selectbox("Bloque", blq_opts, index=blq_opts.index(q["bloque"]) if q.get("bloque") in blq_opts else 0,
                                   key=f"{k}_blq", format_func=lambda b: nombre_bloque(b) if b else "— Sin bloque —")
        tms = [""] + [str(t) for t in (temas_de_bloque(q["bloque"]) if q["bloque"] else [])]
        if q.get("tema") and q["tema"] not in tms:
            tms.append(q["tema"])
        q["tema"] = a2.selectbox("Tema", tms, index=tms.index(q["tema"]) if q.get("tema") in tms else 0, key=f"{k}_tema",
                                 format_func=lambda t: nombre_tema(t) if t else "— Sin tema —")
        b1, b2 = st.columns(2)
        objs = [""] + objetivos_de_tema(q["bloque"], q["tema"])
        if q.get("objetivo") and q["objetivo"] not in objs:
            objs.append(q["objetivo"])
        q["objetivo"] = b1.selectbox("Objetivo docente", objs, index=objs.index(q["objetivo"]) if q.get("objetivo") in objs else 0,
                                     key=f"{k}_obj", format_func=lambda x: nombre_objetivo(x) if x else "— Sin objetivo —")
        q["etiqueta"] = b2.text_input("Etiqueta", q.get("etiqueta", ""), key=f"{k}_etq", placeholder="ej: EXAMEN_FINAL")
        difs = ["Facil", "Media", "Dificil"]
        with st.container(key=f"seg_{k}_dif"):
            q["dificultad"] = st.radio("Dificultad", difs, horizontal=True, key=f"{k}_dif",
                                       index=difs.index(q["dificultad"]) if q.get("dificultad") in difs else 1,
                                       format_func=lambda o: {"Facil": "Fácil", "Dificil": "Difícil"}.get(o, o))
        st.markdown(f"<div class='dev-meta'><span>ID en el banco <b>{q.get('banco_id') or '— (aún no está en el banco)'}</b></span>"
                    f"<span>Último uso <b>{q.get('usada') or 'nunca'}</b> <small>(se marca al exportar)</small></span></div>",
                    unsafe_allow_html=True)

    # ── Vista previa ──────────────────────────────────────────────────────────
    with t_pv:
        with st.container(key=f"seg_{k}_pv"):
            ver = st.radio("Versión", ["Alumno", "Con soluciones"], horizontal=True, key=f"{k}_pvver")
        dtxt = lib.format_datos_word(q["datos_ids"], lib.get_datos_df(ss.get("excel_dfs", {}))) if q.get("datos_ids") else ""
        _mathjax(vista_html(q, ver != "Alumno", 1, dtxt), 420)
        st.caption("El PDF definitivo, en Exportar › Compilar PDF.")


# Fecha del archivo al cargarse (ver _recarga.py)
import os as _os_mt
_MTIME = _os_mt.path.getmtime(__file__)
