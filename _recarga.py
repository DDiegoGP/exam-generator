"""
_recarga.py – Evita usar versiones antiguas de los módulos compartidos.

Streamlit vuelve a ejecutar cada página en cada interacción, pero los módulos importados
(app_utils, app_theme…) se quedan en memoria. Tras subir cambios a Streamlit Cloud, una
página nueva podía encontrarse un app_utils viejo (ImportError). Cada módulo compartido
guarda la fecha de su archivo al cargarse (_MTIME); si el archivo es más nuevo, se recarga.
Mantener este archivo mínimo: si cambiara, él mismo no se recargaría.
"""
import importlib
import os
import sys

_ORDEN = ["examen_lib_latex", "analisis_lib", "clasificador", "app_theme", "app_utils", "desarrollo_ui", "examen_estado", "importar_examen"]   # dependencias primero


def comprobar():
    recargar = False
    for nombre in _ORDEN:
        m = sys.modules.get(nombre)
        if m is None or not getattr(m, "__file__", None):
            continue
        try:
            actual = os.path.getmtime(m.__file__)
        except OSError:
            continue
        if recargar or getattr(m, "_MTIME", None) != actual:
            importlib.reload(m)
            recargar = True   # lo que depende de un módulo recargado también se recarga

