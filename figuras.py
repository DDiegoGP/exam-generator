"""Figuras TikZ en las preguntas de desarrollo.

· En el LaTeX exportado el código TikZ pasa tal cual (también en modo Markdown) y se añaden al preámbulo
  las librerías habituales; pgfplots y circuitikz solo si se usan.
· Para la vista previa dentro de la app (que no sabe dibujar TikZ) cada figura se compila aparte con el
  mismo servicio que los PDF (latexonline.cc) y se muestra como imagen; se guarda en caché.
· En Word, la figura va como imagen.
"""
import base64
import hashlib
import io
import os as _os_mt
import re

import streamlit as st

PATRON = re.compile(r"\\begin\{(tikzpicture|circuitikz)\}.*?\\end\{\1\}", re.DOTALL)
LIBRERIAS = r"\usetikzlibrary{arrows.meta,calc,positioning,patterns,angles,quotes,decorations.pathmorphing,shapes.geometric}"


def tiene(texto) -> bool:
    return bool(PATRON.search(str(texto or "")))


def bloques(texto) -> list:
    return [m.group(0) for m in PATRON.finditer(str(texto or ""))]


def preambulo(tex_o_codigo: str, extra: str = "") -> str:
    """Líneas de preámbulo que necesita el documento según lo que use."""
    t = str(tex_o_codigo or "")
    out = [LIBRERIAS]
    if "\\begin{axis}" in t or "\\addplot" in t:
        out += [r"\usepackage{pgfplots}", r"\pgfplotsset{compat=1.14}"]
    if "circuitikz" in t:
        out.append(r"\usepackage{circuitikz}")
    if extra.strip():
        out.append(extra.strip())
    return "\n".join(out)


def inyectar_preambulo(tex: str, extra: str = "") -> str:
    """Añade al .tex lo necesario para las figuras (solo si hay alguna)."""
    if not (tiene(tex) or extra.strip()) or "\\begin{document}" not in tex:
        return tex
    return tex.replace("\\begin{document}", preambulo(tex, extra) + "\n\\begin{document}", 1)


@st.cache_data(show_spinner=False, max_entries=200)
def png(codigo: str, extra: str = "") -> bytes | None:
    """Compila una figura suelta y la devuelve como PNG (None si no se puede)."""
    import examen_lib_latex as lib
    doc = ("\\documentclass[border=4pt]{standalone}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T1]{fontenc}\n"
           "\\usepackage{amsmath,amssymb}\n\\usepackage{tikz}\n" + preambulo(codigo, extra)
           + "\n\\begin{document}\n" + codigo + "\n\\end{document}\n")
    try:
        pdf = lib.compilar_latex_online(tex_str=doc, sty_bytes=b"", extra_files={},
                                        nombre="fig_" + hashlib.md5(doc.encode()).hexdigest()[:8])
        import pypdfium2 as pdfium
        page = pdfium.PdfDocument(pdf)[0]
        img = page.render(scale=2.2).to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _cache() -> dict:
    return st.session_state.setdefault("_fig_png", {})


def _clave(codigo: str, extra: str) -> str:
    return hashlib.md5((codigo + "\x00" + extra).encode("utf-8")).hexdigest()


def pendientes(textos: list, extra: str = "") -> list:
    """Figuras de estos textos que aún no se han dibujado en esta sesión."""
    c = _cache()
    return [b for t in textos for b in bloques(t) if _clave(b, extra) not in c]


def dibujar(textos: list, extra: str = "") -> int:
    """Dibuja (compila) las figuras pendientes; tarda unos segundos por figura. Devuelve cuántas."""
    c = _cache()
    n = 0
    for b in pendientes(textos, extra):
        c[_clave(b, extra)] = png(b, extra) or b""
        n += 1
    return n


def boton(textos: list, k: str, extra: str = ""):
    """Botón «Dibujar figuras» si hay figuras TikZ sin dibujar (la vista previa no las compila sola: es lento)."""
    pend = pendientes(textos, extra)
    if pend and st.button(f"Dibujar {len(pend)} figura(s) TikZ en la vista previa", key=f"{k}_fig",
                          help="Cada figura se compila en latexonline.cc; puede tardar 20-30 s la primera vez. "
                               "En el PDF exportado se dibujan siempre."):
        with st.spinner("Dibujando figuras…"):
            dibujar(textos, extra)
        st.rerun()


def html(texto: str, conversor, extra: str = "") -> str:
    """Convierte texto a HTML (con `conversor`) sustituyendo cada figura TikZ por su imagen (si ya se dibujó)."""
    figs = []

    def guardar(m):
        figs.append(m.group(0))
        return f"\x00F{len(figs) - 1}\x00"
    t = PATRON.sub(guardar, str(texto or ""))
    h = conversor(t)
    c = _cache()
    for i, f in enumerate(figs):
        k = _clave(f, extra)
        p = c.get(k)
        aviso = ("Figura TikZ · pulsa «Dibujar figuras» para verla aquí" if k not in c else
                 "Figura TikZ · no se ha podido dibujar (sin conexión o error en el código); revisa el código")
        rep = (f"<div style='text-align:center;margin:8px 0'><img src='data:image/png;base64,{base64.b64encode(p).decode()}' "
               f"style='max-width:100%;max-height:320px'></div>" if p else
               "<div style='font-size:12px;color:var(--muted);border:1px dashed var(--border2);border-radius:6px;padding:8px 10px;"
               f"margin:6px 0;text-align:center'>▦ {aviso}. En el PDF se dibuja igual.</div>")
        h = h.replace(f"\x00F{i}\x00", rep)
    return h


def sin_figuras(texto: str) -> str:
    """Texto sin los bloques TikZ (para Word, donde van como imagen aparte)."""
    return PATRON.sub("", str(texto or "")).strip()


_MTIME = _os_mt.path.getmtime(__file__)
