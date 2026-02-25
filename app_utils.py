"""
app_utils.py  –  Estado compartido, conexión DB y utilidades Streamlit.
"""
import os
import sys
import json
import datetime
import re

import pandas as pd
import streamlit as st

# ── Ruta del proyecto ────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import examen_lib_latex as lib

# ── Archivos persistentes ────────────────────────────────────────────────────
PRESETS_FILE = os.path.join(PROJECT_DIR, "presets_examen.json")
HIST_FILE    = os.path.join(PROJECT_DIR, "historial_examenes.json")
DEFAULT_XLSX = os.path.join(PROJECT_DIR, "Base de Datos FM 29-01-26.xlsx")
OUTPUT_DIR   = os.path.join(PROJECT_DIR, "Output")

# ── CSS global ────────────────────────────────────────────────────────────────
APP_CSS = """
<style>
:root {
  --p:#2c3e50; --p-light:#34495e; --acc:#3498db;
  --ok:#27ae60; --warn:#f39c12; --err:#c0392b;
  --used:#8e44ad; --unused:#95a5a6;
  --border:#bdc3c7; --border-light:#dee2e6; --bg-light:#f8f9fa;
}
.block-container { padding-top:0.8rem !important; padding-bottom:2rem !important; }

/* ── Tarjetas de pregunta ── */
.q-card {
  border-left: 5px solid #bdc3c7;
  border-radius: 7px;
  padding: 11px 15px;
  margin-bottom: 9px;
  background: #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,.08);
  font-size: 0.9em;
  line-height: 1.55;
  transition: box-shadow .15s;
}
.q-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,.13); }
.q-card.dif-facil  { border-left-color: #27ae60; background: #f0faf4; }
.q-card.dif-media  { border-left-color: #f39c12; background: #fffdf0; }
.q-card.dif-dificil{ border-left-color: #c0392b; background: #fdf5f5; }
.q-card.dif-nueva  { border-left-color: #3498db; background: #f0f7ff; }
.q-head {
  display:flex; justify-content:space-between; align-items:center;
  margin-bottom:6px; font-size:0.78em; color:#666;
}
.q-num  { font-weight:700; color:#2c3e50; font-size:0.95em; }
.q-enun { font-weight:600; margin-bottom:8px; color:#1a1a2e; }
.q-opts { padding-left:10px; }
.q-opt  { margin:3px 0; color:#444; }
.q-opt.correct { color:#1e8449; font-weight:700; }

/* ── Tags de dificultad y uso ── */
.tag { display:inline-block; border-radius:4px; padding:2px 7px; font-size:0.74em; font-weight:700; margin-left:4px; letter-spacing:.02em; }
.tag-f { background:#d5f5e3; color:#1a7a3d; border:1px solid #abeacc; }
.tag-m { background:#fef9e7; color:#9a7a00; border:1px solid #f5dfa0; }
.tag-d { background:#fadbd8; color:#922b21; border:1px solid #f0b0aa; }
.tag-u { background:#e8daef; color:#6c3483; border:1px solid #c9a8e0; }
.tag-n { background:#eaecee; color:#555; border:1px solid #ccc; }

/* ── Cabecera de bloque en preview ── */
.bloque-header {
  background: linear-gradient(90deg, #1a252f, #2c3e50);
  color: white;
  padding: 9px 16px;
  border-radius: 7px;
  margin: 18px 0 10px 0;
  font-weight: 700;
  font-size: 0.95em;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 5px rgba(0,0,0,.2);
}
.bloque-stats { font-size:0.82em; font-weight:400; opacity:0.85; }

/* ── Stat cards (estadísticas) ── */
.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,.09);
  border-top: 4px solid var(--acc);
  text-align: center;
}
.stat-card.ok   { border-top-color: var(--ok); }
.stat-card.warn { border-top-color: var(--warn); }
.stat-card.err  { border-top-color: var(--err); }
.stat-card.used { border-top-color: var(--used); }
.stat-num  { font-size: 2em; font-weight: 800; color: #2c3e50; line-height: 1.1; }
.stat-label{ font-size: 0.82em; color: #666; margin-top: 3px; font-weight: 500; }

/* ── Bloque row en stats ── */
.blq-row {
  display:grid; grid-template-columns:minmax(100px,1fr) 60px 60px 60px 70px 130px;
  align-items:center; gap:8px; padding:8px 12px; border-radius:6px;
  margin-bottom:5px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.06);
  font-size:0.85em;
}
.blq-row:hover { background:#f0f7ff; }
.blq-name { font-weight:700; color:#2c3e50; }
.blq-bar-track { background:#e9ecef; border-radius:4px; height:10px; }
.blq-bar-fill  { height:10px; border-radius:4px; }

/* ── Sidebar ── */
.conn-ok   { color:var(--ok);  font-weight:700; }
.conn-err  { color:var(--err); font-weight:700; }
.conn-wait { color:var(--warn);font-weight:700; }

/* ── Tabla de preguntas ── */
.q-table { width:100%; border-collapse:collapse; font-size:0.85em; }
.q-table th { background:#2c3e50; color:white; padding:7px 10px; text-align:left; position:sticky; top:0; letter-spacing:.02em; }
.q-table td { padding:6px 10px; border-bottom:1px solid #eee; vertical-align:middle; }
.q-table tr:hover td { background:#f0f7ff; cursor:pointer; }
.q-table tr.selected td { background:#dbeeff; }
.q-enun-cell { max-width:420px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

/* ── Sección de filtros con borde ── */
.filter-section {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}

/* ── Info boxes más compactos ── */
[data-testid="stInfo"] { border-radius: 8px !important; }
[data-testid="stWarning"] { border-radius: 8px !important; }
[data-testid="stSuccess"] { border-radius: 8px !important; }
</style>
"""

# ── Session state ────────────────────────────────────────────────────────────
def init_session_state():
    """Inicializa claves en session_state si no existen."""
    defaults: dict = {
        "db_connected":  False,
        "excel_path":    DEFAULT_XLSX if os.path.isfile(DEFAULT_XLSX) else "",
        "excel_dfs":     {},
        "df_preguntas":  pd.DataFrame(),
        "bloques":       [],
        # Generador
        "sel_ids":       [],
        "manual_order":  [],
        "cache_examen":  None,
        "dev_questions": [],   # preguntas de desarrollo
        "exam_cfg":      {},   # configuración exportación (guardada entre pestañas)
        "recovery_mode": False,  # True cuando se carga desde CSV
        # Presets / historial
        "presets":       _load_json(PRESETS_FILE, {}),
        "historial":     _load_json(HIST_FILE, []),
        # Import staging
        "import_staging": [],
        # Mensajes de log (export)
        "export_log":    [],
        # Guardado temporal para undo en Gestor
        "undo_state":    None,
        # Receta de auto-relleno del Generador
        "auto_recipe":   {},
        # Avisos de la última generación
        "gen_warnings":  [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ── JSON helpers ─────────────────────────────────────────────────────────────
def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return True
    except Exception:
        return False

# ── Presets ──────────────────────────────────────────────────────────────────
def save_preset(name: str, cfg: dict):
    st.session_state.presets[name] = cfg
    _save_json(PRESETS_FILE, st.session_state.presets)

def delete_preset(name: str):
    st.session_state.presets.pop(name, None)
    _save_json(PRESETS_FILE, st.session_state.presets)

# ── Historial ────────────────────────────────────────────────────────────────
def append_historial(entry: dict):
    hist = st.session_state.historial
    hist.append(entry)
    st.session_state.historial = hist[-20:]  # máximo 20 entradas
    _save_json(HIST_FILE, st.session_state.historial)

# ── Parseo Excel ─────────────────────────────────────────────────────────────
def _normalizar_fecha(val) -> str:
    s = str(val).strip()
    if s in ("nan", "NaT", "None", "", "nat"):
        return ""
    try:
        ts = pd.Timestamp(val)
        if pd.isnull(ts):
            return ""
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return s

def _nsort(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]

def procesar_excel_dfs(dfs: dict) -> pd.DataFrame:
    """
    Dado el dict {nombre_hoja: DataFrame} que devuelve cargar_excel_local,
    construye un DataFrame unificado con las columnas estándar:
      ID_Pregunta, bloque, Tema, enunciado, opciones_list, letra_correcta,
      dificultad, usada, notas
    """
    rows = []
    for b_name, df_sheet in dfs.items():
        if df_sheet.empty:
            continue
        head = [str(h).lower().strip() for h in df_sheet.columns]

        # Detectar índices de columnas clave
        idx_id   = next((i for i, h in enumerate(head) if "id_preg" in h or h == "id"), -1)
        idx_enun = next((i for i, h in enumerate(head) if "enunciado" in h), -1)
        idx_tem  = next((i for i, h in enumerate(head) if "tema" in h and "id" not in h), -1)
        idx_dif  = next((i for i, h in enumerate(head) if "dificultad" in h), -1)
        idx_nota = next((i for i, h in enumerate(head) if "nota" in h), -1)

        # Opciones: 4 columnas justo después del enunciado
        idx_opA  = idx_enun + 1 if idx_enun != -1 else -1

        # Columna correcta: típicamente enunciado + 5
        idx_corr_offset = 5  # enun, A, B, C, D, Correcta

        # Columna "usada"
        idx_usada = next((i for i, h in enumerate(head) if "usada" in h or "fecha" in h), -1)

        for _, row_s in df_sheet.iterrows():
            r = row_s.tolist()

            if idx_id == -1 or idx_enun == -1 or idx_opA == -1:
                continue

            # Ignorar filas sin ID
            id_val = str(r[idx_id]).strip()
            if not id_val or id_val.lower() in ("nan", "none", "id_pregunta"):
                continue

            # Tema
            tem_raw = str(r[idx_tem]).strip() if idx_tem != -1 else "1"
            if tem_raw.endswith(".0"):
                tem_raw = tem_raw[:-2]
            if tem_raw in ("nan", "None", ""):
                tem_raw = "1"

            # Opciones (4 columnas)
            ops = []
            for j in range(4):
                oi = idx_opA + j
                ops.append(str(r[oi]) if oi < len(r) and str(r[oi]) not in ("nan", "None") else "")

            # Respuesta correcta
            corr_idx = idx_enun + idx_corr_offset
            if corr_idx < len(r):
                corr_raw = str(r[corr_idx]).strip().upper()
            else:
                corr_raw = "A"
            if corr_raw not in ("A", "B", "C", "D"):
                corr_raw = "A"

            # Dificultad
            dif_raw = str(r[idx_dif]).strip() if idx_dif != -1 and idx_dif < len(r) else "Media"
            if dif_raw in ("nan", "None", ""):
                dif_raw = "Media"

            # Usada / fecha
            u_val = ""
            if idx_usada != -1 and idx_usada < len(r):
                u_val = _normalizar_fecha(r[idx_usada])

            # Notas
            nota_val = ""
            if idx_nota != -1 and idx_nota < len(r):
                n = str(r[idx_nota]).strip()
                nota_val = "" if n in ("nan", "NaT", "None") else n

            rows.append({
                "ID_Pregunta":   id_val,
                "bloque":        b_name,
                "Tema":          tem_raw,
                "enunciado":     str(r[idx_enun]),
                "opciones_list": ops,
                "letra_correcta": corr_raw,
                "dificultad":    dif_raw,
                "usada":         u_val,
                "notas":         nota_val,
            })

    if not rows:
        return pd.DataFrame(columns=["ID_Pregunta","bloque","Tema","enunciado",
                                      "opciones_list","letra_correcta","dificultad","usada","notas"])
    return pd.DataFrame(rows)

# ── Conexión ─────────────────────────────────────────────────────────────────
def connect_db(path: str):
    """Carga el Excel y actualiza session_state. Retorna (ok, mensaje)."""
    try:
        dfs = lib.cargar_excel_local(path)
        df  = procesar_excel_dfs(dfs)
        st.session_state.excel_path    = path
        st.session_state.excel_dfs     = dfs
        st.session_state.df_preguntas  = df
        st.session_state.bloques       = list(dfs.keys())
        st.session_state.db_connected  = True
        return True, f"{len(df)} preguntas en {len(dfs)} bloque(s)"
    except FileNotFoundError:
        st.session_state.db_connected = False
        return False, f"Archivo no encontrado: {path}"
    except PermissionError:
        st.session_state.db_connected = False
        return False, "Sin permiso para leer el archivo (¿está abierto en Excel?)"
    except Exception as e:
        st.session_state.db_connected = False
        return False, f"Error al cargar: {e}"

def reload_db():
    """Recarga el Excel desde la ruta guardada (tras guardar cambios)."""
    if st.session_state.excel_path:
        connect_db(st.session_state.excel_path)

# ── Sidebar (componente compartido) ─────────────────────────────────────────
def render_sidebar():
    """Renderiza la barra lateral de conexión, compartida entre todas las páginas."""
    with st.sidebar:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a252f,#2c3e50);
                    border-radius:10px;padding:12px 16px;margin-bottom:14px;color:white;">
          <div style="font-size:1.15em;font-weight:800;letter-spacing:-.01em">📝 ExamGen UCM</div>
          <div style="font-size:0.72em;opacity:0.65;margin-top:2px">Generador de Exámenes v42</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("**📚 Base de Datos**")

        # ── Botón principal: explorador de archivos ──
        if st.button("📂 Seleccionar archivo...", use_container_width=True, key="btn_file_pick"):
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.wm_attributes('-topmost', True)
                initial = st.session_state.excel_path or DEFAULT_XLSX
                init_dir = os.path.dirname(initial) if os.path.isfile(initial) else PROJECT_DIR
                chosen = filedialog.askopenfilename(
                    title="Seleccionar base de datos Excel",
                    filetypes=[("Excel", "*.xlsx *.xls"), ("Todos los archivos", "*.*")],
                    initialdir=init_dir,
                )
                root.destroy()
                if chosen:
                    st.session_state.excel_path = chosen
                    ok, msg = connect_db(chosen)
                    if not ok:
                        st.session_state["_sidebar_err"] = msg
                    st.rerun()
            except Exception as e:
                st.session_state["_sidebar_err"] = f"Error explorador: {e}"
                st.rerun()

        # Mostrar errores pendientes
        if st.session_state.get("_sidebar_err"):
            st.error(st.session_state.pop("_sidebar_err"))

        # ── Estado de conexión ──
        if st.session_state.db_connected:
            fname = os.path.basename(st.session_state.excel_path)
            df    = st.session_state.df_preguntas
            st.markdown(
                f'<span class="conn-ok">✅ Conectado</span><br>'
                f'<small style="color:#555;word-break:break-all">{fname}</small>',
                unsafe_allow_html=True,
            )
            st.caption(f"{len(df)} preguntas · {len(st.session_state.bloques)} bloques")
            if not df.empty:
                nunca = (df["usada"] == "").sum()
                st.caption(f"🆕 Sin usar: {nunca} · 📝 Usadas: {len(df) - nunca}")
            if st.button("🔄 Recargar", use_container_width=True, key="btn_reload"):
                reload_db()
                st.rerun()
        else:
            st.markdown('<span class="conn-wait">⏳ Sin conexión</span>', unsafe_allow_html=True)

        # ── Ruta manual (respaldo / Colab) ──
        with st.expander("✏️ Ruta manual", expanded=False):
            path_m = st.text_input(
                "Ruta al .xlsx",
                value=st.session_state.excel_path,
                key="sidebar_path_manual",
                label_visibility="collapsed",
                placeholder="C:/ruta/archivo.xlsx",
            )
            if st.button("🔌 Conectar con esta ruta", key="btn_conectar_manual",
                         use_container_width=True):
                ok, msg = connect_db(path_m)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        st.divider()
        st.caption("Generador Examenes v42 · UCM")

# ── Page header helper ────────────────────────────────────────────────────────
def page_header(icon: str, title: str, subtitle: str = ""):
    """Renderiza una cabecera de página consistente con gradiente."""
    sub_html = f'<div style="font-size:0.85em;opacity:0.75;margin-top:2px">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""<div style="background:linear-gradient(90deg,#1a252f,#2c3e50);
                color:white;border-radius:10px;padding:14px 22px;
                margin-bottom:18px;display:flex;align-items:center;gap:14px;
                box-shadow:0 3px 10px rgba(0,0,0,.2);">
          <span style="font-size:1.9em">{icon}</span>
          <div>
            <div style="font-size:1.15em;font-weight:800;letter-spacing:-.01em">{title}</div>
            {sub_html}
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

# ── Helpers varios ────────────────────────────────────────────────────────────
def temas_de_bloque(bloque: str) -> list[str]:
    df = st.session_state.df_preguntas
    if df.empty:
        return [str(i) for i in range(1, 51)]
    t = df[df["bloque"] == bloque]["Tema"].unique() if bloque and bloque != "Todos" else df["Tema"].unique()
    return sorted([str(x) for x in t if str(x) not in ("nan", "None", "")], key=_nsort)

def bloques_disponibles() -> list[str]:
    return st.session_state.bloques or []

def es_uso_antiguo(v: str, months: int) -> bool:
    try:
        return (datetime.datetime.strptime(str(v).split(" ")[0], "%Y-%m-%d")
                < datetime.datetime.now() - datetime.timedelta(days=months * 30))
    except (ValueError, TypeError):
        return False

def mathjax_html(contenido: str) -> str:
    """Envuelve contenido HTML en una página con MathJax y los estilos de la app."""
    return f"""<!DOCTYPE html><html><head>
<script>MathJax={{tex:{{inlineMath:[['$','$'],['\\\\(','\\\\)']]}},svg:{{fontCache:'global'}}}};</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
<style>
*{{box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#2c3e50;padding:10px 12px;margin:0;background:#f8f9fa}}
.q-card{{border-left:4px solid #bdc3c7;border-radius:6px;padding:10px 14px;margin-bottom:8px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.06);font-size:0.9em;line-height:1.5}}
.q-card.dif-facil{{border-left-color:#27ae60;background:#f0faf4}}
.q-card.dif-media{{border-left-color:#f39c12;background:#fffdf0}}
.q-card.dif-dificil{{border-left-color:#c0392b;background:#fdf5f5}}
.q-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;font-size:0.78em;color:#666}}
.q-num{{font-weight:700;color:#2c3e50;font-size:1em}}
.q-enun{{font-weight:600;margin-bottom:7px}}
.q-opts{{padding-left:8px}}
.q-opt{{margin:2px 0;color:#444}}
.q-opt.correct{{color:#1e8449;font-weight:700}}
.tag{{display:inline-block;border-radius:3px;padding:1px 5px;font-size:0.75em;font-weight:600;margin-left:4px}}
.tag-f{{background:#d5f5e3;color:#1e8449}}.tag-m{{background:#fef9e7;color:#b7950b}}
.tag-d{{background:#fadbd8;color:#922b21}}.tag-u{{background:#e8daef;color:#6c3483}}.tag-n{{background:#eaecee;color:#626567}}
.bloque-hdr{{background:linear-gradient(90deg,#2c3e50,#34495e);color:#fff;padding:7px 12px;border-radius:5px;margin:14px 0 6px 0;font-weight:700;font-size:0.92em;display:flex;justify-content:space-between}}
</style>
</head><body>{contenido}</body></html>"""

def render_question_card_html(row, show_sol: bool = True, num: int = None) -> str:
    """Genera HTML de una tarjeta de pregunta con colores por dificultad."""
    dif    = str(row.get("dificultad", "Media"))
    dif_l  = dif.lower().replace("á","a").replace("í","i")
    cls_card = {"facil": "dif-facil", "media": "dif-media", "dificil": "dif-dificil"}.get(dif_l, "")
    cls_tag  = {"facil": "tag-f", "media": "tag-m", "dificil": "tag-d"}.get(dif_l, "tag-m")

    u     = str(row.get("usada", "") or "")
    cls_u = "tag-u" if u else "tag-n"
    u_t   = u if u else "Nueva"
    num_s = f"Preg. {num}" if num else str(row.get("ID_Pregunta", ""))

    ops = row.get("opciones_list", []) or []
    if isinstance(ops, str):
        try: ops = json.loads(ops)
        except Exception: ops = []

    corr_l = str(row.get("letra_correcta", "A")).upper()
    idx_c  = {"A": 0, "B": 1, "C": 2, "D": 3}.get(corr_l, 0)

    opts_html = '<div class="q-opts">'
    for i, l in enumerate(["a", "b", "c", "d"]):
        txt = ops[i] if i < len(ops) else ""
        is_c = show_sol and i == idx_c
        cls  = ' class="q-opt correct"' if is_c else ' class="q-opt"'
        mark = " ✓" if is_c else ""
        opts_html += f'<div{cls}>{l}) {txt}{mark}</div>'
    opts_html += "</div>"

    notas = str(row.get("notas", "") or "").strip()
    nota_html = (f'<div style="margin-top:5px;padding:3px 8px;background:#fef3cd;'
                 f'border-radius:3px;font-size:0.8em">📝 {notas}</div>') if notas else ""

    return (
        f'<div class="q-card {cls_card}">'
        f'<div class="q-head">'
        f'<span class="q-num">{num_s} &nbsp;<small style="font-weight:400;color:#888">{row.get("ID_Pregunta","")}</small></span>'
        f'<span>B:{row.get("bloque","")} · T:{row.get("Tema","")} '
        f'<span class="tag {cls_tag}">{dif}</span>'
        f'<span class="tag {cls_u}">{u_t}</span></span></div>'
        f'<div class="q-enun">{row.get("enunciado","")}</div>'
        f'{opts_html}{nota_html}</div>'
    )
