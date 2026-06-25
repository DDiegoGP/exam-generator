"""
dev_editor.py – Wrapper del componente ace editor para preguntas de desarrollo.

Se declara aquí (en un módulo propio) porque declare_component() requiere que
inspect.getmodule() devuelva un módulo válido, lo que falla cuando se llama
directamente desde un script de página de Streamlit (ejecutado vía exec()).
"""
import os
import streamlit.components.v1 as _components
from pathlib import Path

_COMPONENT_DIR = str(Path(__file__).parent / "editor_component")
_cmp = _components.declare_component("dev_ace_editor", path=_COMPONENT_DIR)


def ace_editor(value: str, mode: str = "latex", height: int = 200, key: str = None):
    default = {"content": value, "mode": mode}
    return _cmp(value=value, mode=mode, height=height, key=key, default=default)
