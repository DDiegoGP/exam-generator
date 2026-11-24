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
from app_theme import apply_theme, get_estilo, render_estilo_quick  # noqa: F401  (apply_theme se reexporta a las páginas)

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
        # Configuración de bloques/temas
        "cfg_bloques":   {},   # {bloque_name: descripcion}
        "cfg_temas":     {},   # {tema_str: {nombre, bloque}}
        "cfg_general":   {},   # {clave: valor}
        "cfg_objetivos": {},   # {codigo: {nombre_corto, descripcion, bloque, tema}}
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

def _load_cfg(dfs: dict):
    """Lee las hojas de configuración del dfs y actualiza session_state."""
    dfs = lib.init_cfg_from_data(dfs)
    st.session_state.cfg_bloques   = lib.get_cfg_bloques(dfs)
    st.session_state.cfg_temas     = lib.get_cfg_temas(dfs)
    st.session_state.cfg_general   = lib.get_cfg_general(dfs)
    st.session_state.cfg_objetivos = lib.get_cfg_objetivos(dfs)
    return dfs


def nombre_bloque(bloque: str) -> str:
    """Retorna nombre para mostrar: 'Bloque IX — Óptica' o 'Bloque IX' si sin desc."""
    desc = st.session_state.get("cfg_bloques", {}).get(bloque, "")
    return f"{bloque} — {desc}" if desc else bloque


def nombre_tema(tema: str) -> str:
    """Retorna nombre para mostrar: 'Tema 39: Óptica geométrica' o 'Tema 39'."""
    t = str(tema)
    if t.endswith(".0"):
        t = t[:-2]
    entry  = st.session_state.get("cfg_temas", {}).get(t, {})
    nombre = entry.get("nombre", "") if isinstance(entry, dict) else ""
    return f"Tema {t}: {nombre}" if nombre else f"Tema {t}"


def procesar_excel_dfs(dfs: dict) -> pd.DataFrame:
    """
    Dado el dict {nombre_hoja: DataFrame} que devuelve cargar_excel_local,
    construye un DataFrame unificado con las columnas estándar:
      ID_Pregunta, bloque, Tema, enunciado, opciones_list, letra_correcta,
      dificultad, usada, notas
    """
    rows = []
    for b_name, df_sheet in dfs.items():
        if b_name in lib.CFG_SHEETS:
            continue
        if df_sheet.empty:
            continue
        head = [str(h).lower().strip() for h in df_sheet.columns]

        # Detectar índices de columnas clave
        idx_id   = next((i for i, h in enumerate(head) if "id_preg" in h or h == "id"), -1)
        idx_enun = next((i for i, h in enumerate(head) if "enunciado" in h), -1)
        idx_tem  = next((i for i, h in enumerate(head) if "tema" in h and "id" not in h), -1)
        idx_dif  = next((i for i, h in enumerate(head) if "dificultad" in h), -1)
        idx_nota = next((i for i, h in enumerate(head) if "nota" in h and "soluci" not in h), -1)
        idx_sol  = next((i for i, h in enumerate(head) if "soluci" in h), -1)
        idx_datos = next((i for i, h in enumerate(head) if h == "datos" or h == "datos_ids"), -1)
        idx_com   = next((i for i, h in enumerate(head) if "comentar" in h), -1)
        idx_obj   = next((i for i, h in enumerate(head) if h == "objetivo"), -1)

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

            # Solución
            sol_val = ""
            if idx_sol != -1 and idx_sol < len(r):
                s = str(r[idx_sol]).strip()
                sol_val = "" if s in ("nan", "NaT", "None") else s

            # Datos (IDs de constantes físicas, separados por coma)
            datos_val = ""
            if idx_datos != -1 and idx_datos < len(r):
                d = str(r[idx_datos]).strip()
                datos_val = "" if d in ("nan", "NaT", "None") else d

            # Comentario / etiqueta de importación
            com_val = ""
            if idx_com != -1 and idx_com < len(r):
                c = str(r[idx_com]).strip()
                com_val = "" if c in ("nan", "NaT", "None") else c

            # Objetivo docente
            obj_val = ""
            if idx_obj != -1 and idx_obj < len(r):
                o = str(r[idx_obj]).strip()
                obj_val = "" if o in ("nan", "NaT", "None") else o

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
                "solucion":      sol_val,
                "datos":         datos_val,
                "comentario":    com_val,
                "objetivo":      obj_val,
            })

    if not rows:
        return pd.DataFrame(columns=["ID_Pregunta","bloque","Tema","enunciado",
                                      "opciones_list","letra_correcta","dificultad","usada","notas","solucion","datos","comentario","objetivo"])
    return pd.DataFrame(rows)

# ── Conexión ─────────────────────────────────────────────────────────────────
def connect_db(path: str):
    """Carga el Excel desde ruta local y actualiza session_state."""
    try:
        dfs = lib.cargar_excel_local(path)
        dfs = _load_cfg(dfs)
        df  = procesar_excel_dfs(dfs)
        st.session_state.excel_path    = path
        st.session_state.excel_dfs     = dfs
        st.session_state.df_preguntas  = df
        st.session_state.bloques       = [k for k in dfs if k not in lib.CFG_SHEETS]
        st.session_state["excel_bytes"] = lib.generar_excel_bytes(dfs)
        st.session_state.db_connected  = True
        n_blq = len(st.session_state.bloques)
        return True, f"{len(df)} preguntas en {n_blq} bloque(s)"
    except FileNotFoundError:
        st.session_state.db_connected = False
        return False, f"Archivo no encontrado: {path}"
    except PermissionError:
        st.session_state.db_connected = False
        return False, "Sin permiso para leer el archivo (¿está abierto en Excel?)"
    except Exception as e:
        st.session_state.db_connected = False
        return False, f"Error al cargar: {e}"

def connect_db_from_gsheets(token: dict, spreadsheet_url: str) -> tuple:
    """Carga la DB desde Google Sheets usando token OAuth 2.0. Retorna (ok, mensaje)."""
    try:
        import gspread
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=token.get("access_token"),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)

        # Extraer ID del spreadsheet desde la URL
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9\-_]+)", spreadsheet_url)
        if not m:
            return False, "URL de Google Sheets no válida. Debe ser del tipo: https://docs.google.com/spreadsheets/d/..."
        spreadsheet_id = m.group(1)

        sh = gc.open_by_key(spreadsheet_id)
        st.session_state["_gsheets_id"] = spreadsheet_id
        dfs = {}
        existing_sheet_names = set()
        for ws in sh.worksheets():
            try:
                records = ws.get_all_records(numericise_ignore=["all"])
            except Exception:
                records = []
            dfs[ws.title] = pd.DataFrame(records) if records else pd.DataFrame()
            existing_sheet_names.add(ws.title)

        dfs = _load_cfg(dfs)

        # Empujar a GSheets las hojas de config que no existían allí (creadas en memoria)
        for cfg_name in lib.CFG_SHEETS:
            if cfg_name not in existing_sheet_names and cfg_name in dfs:
                df_cfg = dfs[cfg_name]
                try:
                    ws_cfg = sh.add_worksheet(
                        title=cfg_name,
                        rows=max(100, len(df_cfg) + 5),
                        cols=max(10, len(df_cfg.columns) + 1),
                    )
                    if len(df_cfg.columns) > 0:
                        headers = list(df_cfg.columns)
                        rows_data = df_cfg.fillna("").astype(str).values.tolist()
                        ws_cfg.update([headers] + rows_data)
                except Exception:
                    pass  # no crítico, se intentará al guardar en Configuración

        df = procesar_excel_dfs(dfs)
        st.session_state.excel_path    = ""
        st.session_state.excel_dfs     = dfs
        st.session_state.df_preguntas  = df
        st.session_state.bloques       = [k for k in dfs if k not in lib.CFG_SHEETS]
        st.session_state.db_connected  = True
        st.session_state["excel_bytes"] = lib.generar_excel_bytes(dfs)
        st.session_state["_gsheets_url"]  = spreadsheet_url
        st.session_state["_gsheets_title"] = sh.title
        st.session_state["_upload_name"]   = f"GSheets: {sh.title}"
        n_blq = len(st.session_state.bloques)
        return True, f"Conectado: {sh.title} · {len(df)} preguntas en {n_blq} hoja(s)"
    except Exception as e:
        st.session_state.db_connected = False
        return False, f"Error al conectar Google Sheets: {e}"


def connect_db_from_upload(uploaded_file) -> tuple:
    """Carga el Excel desde un st.file_uploader (cloud mode). Retorna (ok, mensaje)."""
    try:
        import io
        bytes_data = uploaded_file.read()
        xls = pd.ExcelFile(io.BytesIO(bytes_data), engine='openpyxl')
        dfs = {name: pd.read_excel(xls, sheet_name=name) for name in xls.sheet_names}
        dfs = _load_cfg(dfs)
        df  = procesar_excel_dfs(dfs)
        st.session_state.excel_path    = ""   # sin ruta en cloud
        st.session_state.excel_dfs     = dfs
        st.session_state.df_preguntas  = df
        st.session_state.bloques       = [k for k in dfs if k not in lib.CFG_SHEETS]
        st.session_state.db_connected  = True
        st.session_state["excel_bytes"] = lib.generar_excel_bytes(dfs)
        st.session_state["_upload_name"] = uploaded_file.name
        return True, f"Conectado: {uploaded_file.name}"
    except Exception as e:
        st.session_state.db_connected = False
        return False, f"Error al cargar Excel: {e}"

def reload_db():
    """Re-procesa los dfs en memoria. En local: re-lee desde disco.
    NUNCA re-descarga desde GSheets — eso solo lo hace el botón Recargar."""
    path = st.session_state.get("excel_path", "")
    if path and os.path.isfile(path):
        connect_db(path)
        return
    # GSheets / upload: re-procesa desde dfs ya en memoria
    dfs = st.session_state.get("excel_dfs", {})
    if dfs:
        dfs = _load_cfg(dfs)
        df = procesar_excel_dfs(dfs)
        st.session_state.excel_dfs     = dfs
        st.session_state.df_preguntas  = df
        st.session_state.bloques       = [k for k in dfs if k not in lib.CFG_SHEETS]
        st.session_state.db_connected  = True
        st.session_state["excel_bytes"] = lib.generar_excel_bytes(dfs)

def sync_hoja_gsheets(bloque: str) -> bool:
    """Reescribe la hoja del bloque en Google Sheets con el contenido actual de excel_dfs.
    No-op si no hay conexión GSheets activa. Muestra warning si falla."""
    spreadsheet_id = st.session_state.get("_gsheets_id")
    token          = st.session_state.get("google_token")
    if not spreadsheet_id or not token:
        return False  # modo local/upload, sin GSheets activo

    df_sheet = st.session_state.get("excel_dfs", {}).get(bloque)
    if df_sheet is None:
        return False

    try:
        import gspread
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=token.get("access_token"),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(spreadsheet_id)

        try:
            ws = sh.worksheet(bloque)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=bloque, rows=max(200, len(df_sheet) + 20), cols=20)

        ws.clear()
        if len(df_sheet.columns) > 0:
            headers = list(df_sheet.columns)
            rows    = df_sheet.fillna("").astype(str).values.tolist()
            ws.update([headers] + rows)
        return True

    except Exception as e:
        # Guardar el error en session_state para mostrarlo DESPUÉS del rerun
        st.session_state.setdefault("_sync_errors", []).append(
            f"⚠️ No se pudo sincronizar '{bloque}' con Google Sheets: {e}. "
            "Descarga el Excel desde el sidebar para no perder los cambios."
        )
        return False


def sync_bloques_gsheets(bloques: list) -> None:
    """Sincroniza varios bloques a la vez. Muestra spinner mientras escribe."""
    if not st.session_state.get("_gsheets_id"):
        return
    with st.spinner("Guardando en Google Sheets…"):
        for blq in bloques:
            sync_hoja_gsheets(blq)


# ── Google OAuth helpers (flujo manual, sin popup) ────────────────────────────
import urllib.parse

_GSHEETS_SCOPES = (
    "openid profile email "
    "https://www.googleapis.com/auth/spreadsheets "
    "https://www.googleapis.com/auth/drive.readonly"
)


def _oauth_cfg() -> dict:
    """Bloque GOOGLE_OAUTH de st.secrets, o {} si no hay secrets (p. ej. en local)."""
    try:
        return st.secrets.get("GOOGLE_OAUTH", {})
    except Exception:
        return {}


def _google_oauth_url(cfg: dict) -> str:
    """Genera la URL de autorización de Google para redirigir al usuario."""
    params = {
        "client_id":     cfg["client_id"],
        "redirect_uri":  cfg["redirect_uri"],
        "response_type": "code",
        "scope":         _GSHEETS_SCOPES,
        "access_type":   "offline",
        "prompt":        "select_account",
    }
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)


def _exchange_code(code: str, cfg: dict) -> dict:
    """Intercambia el código de autorización por un token de acceso."""
    import requests as req
    r = req.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code":          code,
            "client_id":     cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri":  cfg["redirect_uri"],
            "grant_type":    "authorization_code",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _google_userinfo(access_token: str) -> dict:
    """Obtiene email y nombre del usuario autenticado."""
    import requests as req
    r = req.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    return r.json() if r.ok else {}


def handle_oauth_callback():
    """
    Detecta si la URL contiene ?code= (callback de Google) y completa el flujo.
    Llamar al inicio de CADA página, antes de render_sidebar().
    """
    try:
        cfg = _oauth_cfg()
        if not cfg.get("client_id"):
            return
        params = st.query_params
        if "code" not in params:
            return
        # Evitar doble intercambio si ya estamos autenticados
        if "google_token" in st.session_state:
            st.query_params.clear()
            return
        code = params["code"]
        with st.spinner("Completando autenticación con Google…"):
            token    = _exchange_code(code, cfg)
            userinfo = _google_userinfo(token.get("access_token", ""))
        st.session_state["google_token"]      = token
        st.session_state["google_user_email"] = userinfo.get("email", "")
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Error en autenticación Google: {e}")
        st.query_params.clear()


# ── Google Sheets OAuth section (sidebar) ────────────────────────────────────
def _render_gsheets_oauth(p: str = ""):
    """
    Sección Google Sheets en el sidebar.
    Solo se renderiza si 'GOOGLE_OAUTH' está configurado en st.secrets.
    """
    cfg = _oauth_cfg()
    if not cfg.get("client_id"):
        return  # No configurado: sección invisible

    st.markdown("**🔗 Google Sheets**")

    if "google_token" not in st.session_state:
        oauth_url = _google_oauth_url(cfg)
        st.link_button(
            "🔐 Iniciar sesión con Google",
            url=oauth_url,
            use_container_width=True,
        )
        st.caption("Redirige a Google y vuelve automáticamente.")
    else:
        email = st.session_state.get("google_user_email", "")
        st.caption(f"🟢 {email}" if email else "🟢 Sesión Google activa")

        gs_url = st.text_input(
            "URL hoja de cálculo",
            value=st.session_state.get("_gsheets_url", ""),
            key=p + "sidebar_gsheets_url",
            label_visibility="collapsed",
            placeholder="https://docs.google.com/spreadsheets/d/...",
        )

        gc1, gc2 = st.columns(2)
        if gc1.button("📥 Cargar", key=p + "btn_load_gsheets", use_container_width=True):
            with st.spinner("Conectando…"):
                ok, msg = connect_db_from_gsheets(
                    st.session_state["google_token"], gs_url
                )
            if ok:
                st.rerun()
            else:
                st.error(msg)

        if gc2.button("🚪 Salir", key=p + "btn_logout_google", use_container_width=True):
            for k in ("google_token", "google_user_email", "_gsheets_url", "_gsheets_title"):
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()


def _render_db_panel(p: str = ""):
    """Conexión a la base de datos: Google Sheets, Excel, ruta local, estado, recargar y descargar.
    Se usa en la barra lateral (p="") y en el desplegable de la barra superior (p="pop_");
    el prefijo `p` evita claves de widget repetidas."""
    # ── Google Sheets OAuth (si está configurado) ─────────────────────────
    _render_gsheets_oauth(p)

    if get_estilo() == "clasico":
        st.markdown("**📚 Base de Datos Excel**")

    # ── Upload de Excel (funciona local Y en Cloud) ───────────────────────
    uploaded = st.file_uploader(
        "Cargar Excel (.xlsx)",
        type=["xlsx"],
        key=p + "sidebar_upload",
        help="Sube tu base de datos Excel. Los cambios se guardan en memoria "
             "y puedes descargar el archivo actualizado abajo.",
        label_visibility="collapsed",
    )
    if uploaded is not None:
        # Solo reconectar si es un archivo nuevo (evita resetear cambios en cada rerun)
        if uploaded.name != st.session_state.get("_upload_name"):
            ok, msg = connect_db_from_upload(uploaded)
            if ok:
                st.rerun()
            else:
                st.error(msg)

    # ── Ruta local directa (solo útil en local, oculta en Cloud) ─────────
    with st.expander("📂 Ruta local directa", expanded=False):
        path_m = st.text_input(
            "Ruta al .xlsx",
            value=st.session_state.excel_path,
            key=p + "sidebar_path_manual",
            label_visibility="collapsed",
            placeholder="C:/ruta/archivo.xlsx",
        )
        if st.button("🔌 Conectar", key=p + "btn_conectar_manual",
                     use_container_width=True):
            ok, msg = connect_db(path_m)
            if ok:
                st.rerun()
            else:
                st.error(msg)

    # ── Datos de la asignatura (cfg_general) ─────────────────────────────
    _cg = st.session_state.get("cfg_general", {})
    _asig_sb = _cg.get("asignatura", "") or ""
    _grado_sb = _cg.get("grado", "") or ""
    _anio_sb  = _cg.get("anio_academico", "") or ""
    _dept_sb  = _cg.get("departamento", "") or ""
    _univ_sb  = _cg.get("universidad", "") or ""
    if any([_asig_sb, _grado_sb, _dept_sb, _univ_sb]):
        _lines = []
        if _asig_sb:  _lines.append(f"<b style='color:var(--text, #2c3e50)'>{_asig_sb}</b>")
        if _grado_sb: _lines.append(f"<span style='color:var(--text2, #555)'>{_grado_sb}</span>")
        if _anio_sb:  _lines.append(f"<span style='color:var(--muted, #777);font-size:0.85em'>{_anio_sb}</span>")
        if _dept_sb:  _lines.append(f"<span style='color:var(--muted, #888);font-size:0.82em'>{_dept_sb}</span>")
        if _univ_sb:  _lines.append(f"<span style='color:var(--muted, #888);font-size:0.82em'>{_univ_sb}</span>")
        st.markdown(
            "<div style='background:var(--primary-soft, #f0f7ff);border:1px solid var(--ui-border, #c8dff8);"
            "border-radius:8px;padding:9px 13px;margin-bottom:10px;line-height:1.6'>"
            + "<br>".join(_lines) +
            "<div style='font-size:0.7em;color:var(--faint, #aaa);margin-top:4px'>📋 Configuración → General</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Estado de conexión ────────────────────────────────────────────────
    if st.session_state.db_connected:
        fname = (st.session_state.get("_upload_name")
                 or os.path.basename(st.session_state.excel_path)
                 or "base_datos.xlsx")
        df = st.session_state.df_preguntas
        st.markdown(
            f'<span class="conn-ok">✅ Conectado</span> '
            f'<small style="color:var(--text2, #555)">{fname}</small>',
            unsafe_allow_html=True,
        )
        st.caption(f"{len(df)} preguntas · {len(st.session_state.bloques)} bloques")
        if not df.empty:
            nunca = (df["usada"] == "").sum()
            st.caption(f"🆕 Sin usar: {nunca} · 📝 Usadas: {len(df) - nunca}")

        col_r, col_d = st.columns(2)
        if col_r.button("🔄 Recargar", use_container_width=True, key=p + "btn_reload"):
            _gid   = st.session_state.get("_gsheets_id")
            _token = st.session_state.get("google_token")
            if _gid and _token:
                connect_db_from_gsheets(_token,
                    f"https://docs.google.com/spreadsheets/d/{_gid}")
            else:
                reload_db()
            st.session_state["_reload_toast"] = True
            st.rerun()
        if st.session_state.pop("_reload_toast", False):
            n = len(st.session_state.df_preguntas)
            st.toast(f"✅ Base de datos recargada · {n} preguntas", icon="✅")

        # ── Descarga del Excel actualizado ────────────────────────────────
        excel_bytes = st.session_state.get("excel_bytes", b"")
        if excel_bytes:
            col_d.download_button(
                "⬇️ Descargar",
                data=excel_bytes,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=p + "btn_download_excel",
            )
    else:
        st.markdown('<span class="conn-wait">⏳ Sin conexión</span>',
                    unsafe_allow_html=True)
        st.caption("Sube un archivo Excel arriba para empezar.")
    render_estilo_quick(p)


# ── Sidebar (componente compartido) ─────────────────────────────────────────
def render_sidebar():
    """Barra lateral compartida. Funciona tanto en local como en Streamlit Cloud."""
    # Mostrar errores de sync GSheets que sobrevivieron al rerun
    sync_errors = st.session_state.pop("_sync_errors", [])
    for err in sync_errors:
        st.warning(err)

    with st.sidebar:
        cfg_gen = st.session_state.get("cfg_general", {})
        asig    = cfg_gen.get("asignatura", "")
        inst    = cfg_gen.get("universidad", "") or cfg_gen.get("departamento", "")
        _sub    = asig or "Generador de Exámenes"
        _inst_line = (
            f"<div style='font-size:0.7em;opacity:0.55;margin-top:1px'>{inst}</div>"
            if inst else ""
        )
        if get_estilo() == "clasico":
            st.markdown(
                "<div style='background:linear-gradient(135deg,var(--chip, #1a252f),var(--chip, #2c3e50));"
                "border-radius:10px;padding:12px 16px;margin-bottom:14px;color:var(--chip-ink, white)'>"
                "<div style='font-size:1.15em;font-weight:800;letter-spacing:-.01em'>📝 ExamGen UCM</div>"
                f"<div style='font-size:0.78em;opacity:0.85;margin-top:3px;font-weight:600'>{_sub}</div>"
                f"{_inst_line}"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:0.75rem;font-weight:600;letter-spacing:.08em;"
                "text-transform:uppercase;color:var(--muted);margin:2px 0 10px 0'>"
                "Base de datos</div>",
                unsafe_allow_html=True,
            )

        _render_db_panel()

        st.divider()
        st.caption("ExamGen UCM · Unidad de Física Médica")
        st.markdown(
            "<div style='font-size:0.72em;color:var(--faint, #aaa);text-align:center;line-height:1.5'>"
            "Desarrollado por <b>Diego García Pinto</b><br>"
            "UCM · Física Médica"
            "</div>",
            unsafe_allow_html=True,
        )

# ── Page header helper ────────────────────────────────────────────────────────
def page_header(icon: str, title: str, subtitle: str = "", color: str = "#2c3e50"):
    if get_estilo() != "clasico":
        sub_html = f'<div class="pg-sub">{subtitle}</div>' if subtitle else ""
        st.markdown(f'<div class="pg-head"><div class="pg-title">{title}</div>{sub_html}</div>',
                    unsafe_allow_html=True)
        return
    sub_html = (f'<div style="font-size:.85em;opacity:.75;margin-top:5px;font-weight:400">{subtitle}</div>'
                if subtitle else "")
    # Spacer: evita que el primer elemento quede tapado por la barra fija de Streamlit
    st.markdown('<div style="margin-top:6px"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""<div style="background:linear-gradient(90deg,{color} 0%,{color}ee 100%);
            border-radius:12px;padding:18px 28px;margin-bottom:14px;color:white;
            box-shadow:0 4px 14px rgba(0,0,0,.22);line-height:1.3">
          <div style="font-size:1.55em;font-weight:800;letter-spacing:-.02em;line-height:1.2">{icon}&nbsp;{title}</div>
          {sub_html}
        </div>""",
        unsafe_allow_html=True,
    )

# ── Helpers varios ────────────────────────────────────────────────────────────
def temas_de_bloque(bloque: str) -> list[str]:
    """Devuelve temas para un bloque: unión de DB + cfg_temas, mínimo 1-50."""
    df    = st.session_state.df_preguntas
    cfg_t = st.session_state.get("cfg_temas", {})

    # Topics from DB
    if not df.empty:
        src = df[df["bloque"] == bloque]["Tema"].unique() if (bloque and bloque != "Todos") else df["Tema"].unique()
        db_set = {str(x) for x in src if str(x) not in ("nan", "None", "")}
    else:
        db_set = set()

    # Topics from config (topics assigned to this block, or unassigned)
    cfg_set = set()
    for t_str, t_data in cfg_t.items():
        if isinstance(t_data, dict):
            t_blq = t_data.get("bloque", "")
            if not t_blq or bloque == "Todos" or t_blq == bloque:
                cfg_set.add(t_str)
        else:
            cfg_set.add(t_str)

    union = db_set | cfg_set
    # Always guarantee at least topics 1-50 so empty DBs are usable
    union |= {str(i) for i in range(1, 51)}
    return sorted(list(union), key=_nsort)

def temas_en_db(bloque: str) -> list[str]:
    """Temas que REALMENTE existen en los datos para un bloque (sin añadir 1-50).
    Usar en filtros; para formularios de alta usar temas_de_bloque()."""
    df = st.session_state.df_preguntas
    if df.empty:
        return []
    if bloque and bloque != "Todos":
        src = df[df["bloque"] == bloque]["Tema"]
    else:
        src = df["Tema"]
    vals = {str(x) for x in src if str(x) not in ("nan", "None", "")}
    return sorted(list(vals), key=_nsort)


def bloques_disponibles() -> list[str]:
    return st.session_state.bloques or []


def objetivos_de_tema(bloque: str, tema: str) -> list[str]:
    """Códigos de objetivos asociados a un bloque+tema concreto."""
    cfg = st.session_state.get("cfg_objetivos", {})
    tema = str(tema).strip()
    return [
        cod for cod, data in cfg.items()
        if (not data["bloque"] or data["bloque"] == bloque)
        and (not data["tema"]  or str(data["tema"]).strip() == tema)
    ]


def nombre_objetivo(cod: str) -> str:
    """'OA1 — Ley de Beer' o 'OA1' si sin nombre_corto."""
    cfg = st.session_state.get("cfg_objetivos", {})
    if cod in cfg:
        nombre = cfg[cod].get("nombre_corto", "")
        return f"{cod} — {nombre}" if nombre else cod
    return cod

def es_uso_antiguo(v: str, months: int) -> bool:
    try:
        return (datetime.datetime.strptime(str(v).split(" ")[0], "%Y-%m-%d")
                < datetime.datetime.now() - datetime.timedelta(days=months * 30))
    except (ValueError, TypeError):
        return False

def _mathjax_bitacora(contenido: str) -> str:
    """Vista MathJax con el estilo Bitácora. Detecta si la app está en oscuro
    (atributo data-ui-mode del documento padre) y usa la paleta correspondiente."""
    from app_theme import _T_BITACORA_LIGHT, _T_BITACORA_DARK, _vars
    alias = ("--ui-ok:var(--ok);--ui-warn:var(--warn);--ui-err:var(--err);"
             "--ui-border:var(--border);--ui-used:var(--used);")
    return f"""<!DOCTYPE html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
<script>
try {{ if (window.parent.document.documentElement.getAttribute('data-ui-mode') === 'dark')
         document.documentElement.classList.add('dark'); }} catch (e) {{}}
MathJax={{tex:{{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$'],['\\\\[','\\\\]']]}},svg:{{fontCache:'global'}}}};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
<style>
:root{{{_vars(_T_BITACORA_LIGHT)}{alias}}}
html.dark{{{_vars(_T_BITACORA_DARK)}}}
*{{box-sizing:border-box}}
body{{font-family:'Figtree',system-ui,sans-serif;font-size:14px;color:var(--text);padding:10px 12px;margin:0;background:var(--card)}}
.q-card{{border:1px solid var(--border);border-radius:12px;padding:14px 18px;margin-bottom:10px;background:var(--card);line-height:1.55}}
.q-head{{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px;font-size:0.8em;color:var(--muted)}}
.q-num{{font-family:'JetBrains Mono',monospace;font-weight:600;color:var(--text)}}
.q-num small{{color:var(--muted)!important}}
.q-enun{{font-weight:600;margin-bottom:8px}}
.q-opts{{padding-left:4px}}
.q-opt{{margin:4px 0;color:var(--text2)}}
.q-opt.correct{{color:var(--ok);font-weight:600}}
.tag{{display:inline-block;border-radius:999px;padding:2px 9px;font-size:0.76em;font-weight:600;margin-left:4px}}
.tag-f{{background:var(--ok-bg);color:var(--ok)}}.tag-m{{background:var(--primary-soft);color:var(--primary)}}
.tag-d{{background:var(--err-bg);color:var(--err)}}.tag-u{{background:var(--used-bg);color:var(--used)}}
.tag-n{{background:var(--card2);color:var(--muted)}}
.bloque-hdr{{background:var(--card2);color:var(--text);border:1px solid var(--border);padding:8px 14px;border-radius:10px;margin:14px 0 8px 0;font-weight:700;font-size:0.92em;display:flex;justify-content:space-between}}
h1,h2,h3,h4{{color:var(--text)}}
</style>
</head><body>{contenido}</body></html>"""


def mathjax_html(contenido: str) -> str:
    """Envuelve contenido HTML en una página con MathJax y los estilos de la app."""
    if get_estilo() != "clasico":
        return _mathjax_bitacora(contenido)
    return f"""<!DOCTYPE html><html><head>
<script>MathJax={{tex:{{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$'],['\\\\[','\\\\]']]}},svg:{{fontCache:'global'}}}};</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
<style>
*{{box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:var(--text, #2c3e50);padding:10px 12px;margin:0;background:var(--card2, #f8f9fa)}}
.q-card{{border-left:4px solid var(--border2, #bdc3c7);border-radius:6px;padding:10px 14px;margin-bottom:8px;background:var(--card, #fff);box-shadow:0 1px 3px rgba(0,0,0,.06);font-size:0.9em;line-height:1.5}}
.q-card.dif-facil{{border-left-color:var(--ui-ok, #27ae60);background:var(--ok-bg, #f0faf4)}}
.q-card.dif-media{{border-left-color:var(--ui-warn, #f39c12);background:var(--note-bg, #fffdf0)}}
.q-card.dif-dificil{{border-left-color:var(--ui-err, #c0392b);background:var(--err-bg, #fdf5f5)}}
.q-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;font-size:0.78em;color:var(--muted, #666)}}
.q-num{{font-weight:700;color:var(--text, #2c3e50);font-size:1em}}
.q-enun{{font-weight:600;margin-bottom:7px}}
.q-opts{{padding-left:8px}}
.q-opt{{margin:2px 0;color:var(--text2, #444)}}
.q-opt.correct{{color:var(--ui-ok, #1e8449);font-weight:700}}
.tag{{display:inline-block;border-radius:3px;padding:1px 5px;font-size:0.75em;font-weight:600;margin-left:4px}}
.tag-f{{background:var(--ok-bg, #d5f5e3);color:var(--ui-ok, #1e8449)}}.tag-m{{background:var(--note-bg, #fef9e7);color:var(--ui-warn, #b7950b)}}
.tag-d{{background:var(--err-bg, #fadbd8);color:var(--ui-err, #922b21)}}.tag-u{{background:var(--used-bg, #e8daef);color:var(--ui-used, #6c3483)}}.tag-n{{background:var(--card2, #eaecee);color:var(--muted, #626567)}}
.bloque-hdr{{background:linear-gradient(90deg,var(--chip, #2c3e50),var(--chip, #34495e));color:var(--chip-ink, #fff);padding:7px 12px;border-radius:5px;margin:14px 0 6px 0;font-weight:700;font-size:0.92em;display:flex;justify-content:space-between}}
</style>
</head><body>{contenido}</body></html>"""

def render_question_card_html(row, show_sol: bool = True, num: int = None, include_notas: bool = True) -> str:
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
    nota_html = ""
    if include_notas and notas:
        nota_html = (f'<div style="margin-top:5px;padding:3px 8px;background:var(--note-bg, #fef3cd);'
                     f'border-radius:3px;font-size:0.8em">📝 {notas}</div>')

    def _trunc(s: str, n: int = 32) -> str:
        return s if len(s) <= n else s[:n] + "…"

    _blq_label = _trunc(nombre_bloque(str(row.get("bloque", ""))), 30)
    _tem_label = _trunc(nombre_tema(str(row.get("Tema", ""))), 35)

    return (
        f'<div class="q-card {cls_card}">'
        f'<div class="q-head">'
        f'<span class="q-num">{num_s} &nbsp;<small style="font-weight:400;color:var(--muted, #888)">{row.get("ID_Pregunta","")}</small></span>'
        f'<span title="{nombre_bloque(str(row.get("bloque","")))} · {nombre_tema(str(row.get("Tema","")))}">'
        f'{_blq_label} · {_tem_label} '
        f'<span class="tag {cls_tag}">{dif}</span>'
        f'<span class="tag {cls_u}">{u_t}</span></span></div>'
        f'<div class="q-enun">{row.get("enunciado","")}</div>'
        f'{opts_html}{nota_html}</div>'
    )


def _txt(v) -> str:
    s = "" if v is None else str(v)
    return "" if s in ("nan", "NaT", "None") else s


def datos_de_fila(row: dict, **cambios) -> dict:
    """Todos los campos que espera lib.actualizar_pregunta_excel_local, tomados de la fila
    actual de df_preguntas, con los cambios indicados (esa función sobrescribe todo)."""
    d = {
        "bloque": _txt(row.get("bloque")), "tema": _txt(row.get("Tema")) or "1",
        "enunciado": _txt(row.get("enunciado")), "opciones": list(row.get("opciones_list") or []),
        "correcta": _txt(row.get("letra_correcta")) or "A", "dificultad": _txt(row.get("dificultad")) or "Media",
        "usada": _txt(row.get("usada")), "notas": _txt(row.get("notas")),
        "comentario": _txt(row.get("comentario")), "objetivo": _txt(row.get("objetivo")),
        "datos_ids": _txt(row.get("datos")),
    }
    d.update(cambios)
    return d


def guardar_hojas(hojas: list):
    """Persiste excel_dfs tras cambiar hojas que no son de preguntas (local + Google Sheets)."""
    dfs = st.session_state.excel_dfs
    st.session_state["excel_bytes"] = lib.generar_excel_bytes(dfs)
    path = st.session_state.get("excel_path", "")
    if path:
        lib.guardar_excel_local(path, dfs)
    for h in hojas:
        sync_hoja_gsheets(h)


_PLANTILLAS_SOL = {
    "Razonamiento": "La respuesta correcta es la **{c})** porque...\n\nLas otras opciones son incorrectas porque...",
    "Cálculo": "**Datos:**\n\n\n\n**Desarrollo:**\n\n\n\n**Resultado:**",
    "Concepto": "**Concepto clave:** ...\n\n**Opción {c})** es correcta porque...\n\n**Las demás son incorrectas** porque...",
}


def _vista_formulas(html: str, height: int = 240):
    import streamlit.components.v1 as _stc
    _stc.html(mathjax_html(html), height=height, scrolling=True)


def _editor_bitacora(pid: str, row: dict, extra=None):
    """Editor en 4 pestañas (Pregunta · Solución · Clasificación · Notas y datos) con un solo «Guardar»."""
    bloques_list = st.session_state.bloques or []
    ss = st.session_state
    st.caption(f"{pid} · {nombre_bloque(str(row.get('bloque', '')))} · {nombre_tema(str(row.get('Tema', '')))}")
    col_ed, col_pv = st.columns([1.15, 1], gap="medium")
    with col_ed:
        t_p, t_s, t_c, t_n = st.tabs(["Pregunta", "Solución", "Clasificación", "Notas y datos"])

        with t_p:
            ed_enun = st.text_area("Enunciado", value=_txt(row.get("enunciado")), height=90, key="dlg_enun")
            ops_orig = list(row.get("opciones_list", []) or []) + ["", "", "", ""]
            corr_cur = _txt(row.get("letra_correcta")).upper() or "A"
            ed_corr = st.radio("Respuesta correcta", ["A", "B", "C", "D"], horizontal=True, key="dlg_corr",
                               index=["A", "B", "C", "D"].index(corr_cur) if corr_cur in "ABCD" else 0)
            ed_ops = []
            for li, ll in enumerate(["A", "B", "C", "D"]):
                ed_ops.append(st.text_input(f"Opción {ll}", value=_txt(ops_orig[li]), key=f"dlg_op{ll}"))

        with t_s:
            sk = f"dlg_sol_{pid}"
            if sk not in ss:
                ss[sk] = _txt(row.get("solucion")).strip()
            st.markdown("<span style='font-size:0.8em;color:var(--muted);font-weight:600'>PLANTILLA RÁPIDA</span>",
                        unsafe_allow_html=True)
            pc = st.columns(3)
            for i, (nom, tpl) in enumerate(_PLANTILLAS_SOL.items()):
                if pc[i].button(nom, key=f"dlg_tpl_{i}", use_container_width=True):
                    ss[sk] = tpl.replace("{c}", ed_corr)
            ed_sol = st.text_area("Solución — LaTeX: $...$ en línea · $$...$$ en bloque", key=sk, height=230)
            if not ed_sol.strip():
                st.caption("Sin solución. Elige una plantilla o escríbela; a la derecha verás las fórmulas.")

        with t_c:
            c1, c2 = st.columns(2)
            blq_idx = bloques_list.index(row["bloque"]) if row.get("bloque") in bloques_list else 0
            ed_blq = c1.selectbox("Bloque", bloques_list, index=blq_idx, key="dlg_bloque", format_func=nombre_bloque,
                                  disabled=True, help="La pregunta se guarda en la hoja de su bloque.")
            temas_d = temas_de_bloque(ed_blq) or [str(i) for i in range(1, 51)]
            tem_cur = str(row.get("Tema", "1"))
            ed_tema = c2.selectbox("Tema", temas_d, index=temas_d.index(tem_cur) if tem_cur in temas_d else 0,
                                   key="dlg_tema", format_func=nombre_tema)
            dif_opts = ["Facil", "Media", "Dificil"]
            dif_cur = _txt(row.get("dificultad")).capitalize() or "Media"
            with st.container(key="seg_dlg_dif"):
                ed_dif = st.radio("Dificultad", dif_opts, horizontal=True, key="dlg_dif",
                                  index=dif_opts.index(dif_cur) if dif_cur in dif_opts else 1,
                                  format_func=lambda o: {"Facil": "Fácil", "Dificil": "Difícil"}.get(o, o))
            _obj_opts = [""] + objetivos_de_tema(ed_blq, str(ed_tema))
            _obj_cur = _txt(row.get("objetivo"))
            if _obj_cur and _obj_cur not in _obj_opts:
                _obj_opts.append(_obj_cur)
            ed_obj = st.selectbox("Objetivo docente", _obj_opts,
                                  index=_obj_opts.index(_obj_cur) if _obj_cur in _obj_opts else 0, key="dlg_obj",
                                  format_func=lambda x: "— Sin objetivo —" if x == "" else nombre_objetivo(x))
            ed_com = st.text_input("Etiqueta", value=_txt(row.get("comentario")), key="dlg_com",
                                   placeholder="ej: CLASE, EXAMEN_2023...")

        with t_n:
            _usada_raw = _txt(row.get("usada")).strip()
            _usada_val = None
            if _usada_raw:
                try:
                    _usada_val = datetime.datetime.strptime(_usada_raw[:10], "%Y-%m-%d").date()
                except Exception:
                    pass
            if st.checkbox("Pregunta ya usada", value=(_usada_val is not None), key="dlg_tiene_usada"):
                ed_usada = st.date_input("Fecha de uso", value=_usada_val or datetime.date.today(),
                                         key="dlg_usada").strftime("%Y-%m-%d")
            else:
                ed_usada = ""
            ed_notas = st.text_area("Notas", value=_txt(row.get("notas")), height=80, key="dlg_notas")
            _datos_df = lib.get_datos_df(ss.get("excel_dfs", {}))
            _cur = [x.strip() for x in _txt(row.get("datos")).split(",") if x.strip()]
            sel_ids = []
            st.markdown("**Constantes / datos**")
            if _datos_df.empty or not _datos_df["ID"].astype(str).str.strip().any():
                st.caption("No hay constantes. Añádelas en Configuración → Constantes.")
            else:
                for _dc in sorted(_datos_df["Categoría"].fillna("Sin categoría").unique()):
                    _dcdf = _datos_df[_datos_df["Categoría"].fillna("Sin categoría") == _dc]
                    st.caption(_dc)
                    for _, _dr in _dcdf.iterrows():
                        _did = str(_dr["ID"]).strip()
                        _lbl = (f"{_txt(_dr.get('Nombre'))} ({_txt(_dr.get('Símbolo'))} = {_txt(_dr.get('Valor'))} "
                                f"{_txt(_dr.get('Unidades'))})").strip()
                        if st.checkbox(_lbl, value=(_did in _cur), key=f"dlgdat_{pid}_{_did}"):
                            sel_ids.append(_did)

    with col_pv:   # vista previa fija, siempre visible al lado
        st.markdown("<div style='font-size:.75rem;font-weight:600;color:var(--muted);letter-spacing:.06em;"
                    "margin:6px 0 4px 0'>VISTA PREVIA</div>", unsafe_allow_html=True)
        prev = dict(row)
        prev.update({"enunciado": ed_enun, "opciones_list": ed_ops, "letra_correcta": ed_corr,
                     "dificultad": ed_dif, "notas": ed_notas})
        _html = render_question_card_html(prev, show_sol=True, include_notas=True)
        _html += ("<div style='font-size:.72rem;font-weight:700;color:var(--muted);letter-spacing:.06em;"
                  "margin:12px 0 4px 2px'>SOLUCIÓN</div>")
        if ed_sol.strip():
            _html += ("<div style='line-height:1.6;padding:10px 14px;border-left:3px solid var(--primary);"
                      f"background:var(--primary-soft);border-radius:0 8px 8px 0'>{ed_sol}</div>")
        else:
            _html += ("<div style='padding:10px 14px;border:1px dashed var(--border2);border-radius:8px;"
                      "color:var(--muted);font-size:.9em'>Sin solución todavía. Escríbela en la pestaña "
                      "«Solución» y aparecerá aquí con las fórmulas renderizadas.</div>")
        _vista_formulas(_html, 470)

    sc1, sc2, sc3 = st.columns([1.6, 1, 2.4], vertical_alignment="center")
    if extra is not None:
        with sc3:
            extra(pid, row)
    if sc1.button("Guardar cambios", type="primary", use_container_width=True, key="dlg_save"):
        datos = {
            "bloque": ed_blq, "tema": ed_tema, "enunciado": ed_enun.strip(), "opciones": ed_ops,
            "correcta": ed_corr, "dificultad": ed_dif, "usada": ed_usada, "notas": ed_notas.strip(),
            "comentario": ed_com.strip(), "objetivo": ed_obj, "datos_ids": ",".join(sel_ids),
            "solucion": ed_sol.strip(),
        }
        ok, msg = lib.actualizar_pregunta_excel_local(ss.excel_path, ss.excel_dfs, pid, datos)
        if ok:
            sync_bloques_gsheets([datos["bloque"]])
            reload_db()
            ss.pop(sk, None)
            from app_theme import notify
            notify(f"✅ Pregunta {pid} guardada.")
            st.rerun()
        else:
            st.error(f"❌ {msg}")
    if sc2.button("Cancelar", use_container_width=True, key="dlg_cancel"):
        ss.pop(sk, None)
        st.rerun()


# ── Dialog compartido: editor de pregunta individual ─────────────────────────
@st.dialog("✏️ Editar pregunta", width="large")
def _dialog_editar_pregunta(pid: str, row: dict, extra=None):
    """Modal de edición de una pregunta. Llama a st.rerun() para cerrar.
    `extra(pid, row)`: botones adicionales junto a «Guardar» (p. ej. Duplicar / Eliminar en el Gestor)."""
    if get_estilo() == "bitacora":
        _editor_bitacora(pid, row, extra)
        return
    bloques_list = st.session_state.bloques or []

    st.markdown(f"**ID:** `{pid}`")
    st.markdown("---")

    dc1, dc2 = st.columns([1, 2])

    with dc1:
        blq_idx = bloques_list.index(row["bloque"]) if row["bloque"] in bloques_list else 0
        ed_blq  = st.selectbox("Bloque", bloques_list, index=blq_idx, key="dlg_bloque")
        temas_d = temas_de_bloque(ed_blq) or [str(i) for i in range(1, 51)]
        tem_cur = str(row.get("Tema", "1"))
        tem_idx = temas_d.index(tem_cur) if tem_cur in temas_d else 0
        ed_tema = st.selectbox("Tema", temas_d, index=tem_idx, key="dlg_tema",
                               format_func=nombre_tema)

        dif_opts = ["Facil", "Media", "Dificil"]
        dif_cur  = str(row.get("dificultad", "Media")).capitalize()
        dif_idx  = dif_opts.index(dif_cur) if dif_cur in dif_opts else 1
        ed_dif   = st.selectbox("Dificultad", dif_opts, index=dif_idx, key="dlg_dif")

        corr_opts = ["A", "B", "C", "D"]
        corr_cur  = str(row.get("letra_correcta", "A")).upper()
        corr_idx  = corr_opts.index(corr_cur) if corr_cur in corr_opts else 0
        ed_corr   = st.selectbox("Respuesta correcta", corr_opts, index=corr_idx, key="dlg_corr")

        _usada_raw = str(row.get("usada", "") or "").strip()
        _usada_val = None
        if _usada_raw and _usada_raw not in ('nan', 'NaT', 'None'):
            try: _usada_val = datetime.datetime.strptime(_usada_raw[:10], "%Y-%m-%d").date()
            except Exception: pass
        ed_tiene_fecha = st.checkbox("Pregunta ya usada", value=(_usada_val is not None), key="dlg_tiene_usada")
        if ed_tiene_fecha:
            ed_usada_date = st.date_input("Fecha de uso", value=_usada_val or datetime.date.today(), key="dlg_usada")
            ed_usada = ed_usada_date.strftime("%Y-%m-%d")
        else:
            ed_usada = ""
        ed_notas = st.text_area("Notas", value=str(row.get("notas", "") or ""),
                                 height=70, key="dlg_notas")
        ed_com = st.text_input("Etiqueta", value=str(row.get("comentario", "") or ""),
                               key="dlg_com", placeholder="ej: CLASE, EXAMEN_2023...")
        _obj_opts = [""] + objetivos_de_tema(row.get("bloque", ""), str(row.get("Tema", "")))
        _obj_cur  = str(row.get("objetivo", "") or "")
        _obj_idx  = _obj_opts.index(_obj_cur) if _obj_cur in _obj_opts else 0
        ed_obj = st.selectbox("Objetivo docente", _obj_opts, index=_obj_idx, key="dlg_obj",
                              format_func=lambda x: "— Sin objetivo —" if x == "" else nombre_objetivo(x))

        _datos_df_dlg = lib.get_datos_df(st.session_state.get("excel_dfs", {}))
        _datos_cur_init = str(row.get("datos", "") or "")
        with st.expander("📊 Constantes / Datos", expanded=bool(_datos_cur_init)):
            if _datos_df_dlg.empty or not _datos_df_dlg['ID'].astype(str).str.strip().any():
                st.caption("No hay constantes. Añádelas en Configuración → 🔢 Constantes.")
                _dlg_sel_ids = []
            else:
                _dlg_cur = [x.strip() for x in _datos_cur_init.split(',') if x.strip()]
                _dlg_sel_ids = []
                _dlg_cats = sorted(_datos_df_dlg['Categoría'].fillna('Sin categoría').unique())
                for _dc in _dlg_cats:
                    _dcdf = _datos_df_dlg[_datos_df_dlg['Categoría'].fillna('Sin categoría') == _dc]
                    st.markdown(f"**{_dc}**")
                    for _, _dr in _dcdf.iterrows():
                        _did = str(_dr['ID']).strip()
                        _nom = str(_dr.get('Nombre', '') or '').strip()
                        _sym = str(_dr.get('Símbolo', '') or '').strip()
                        _val = str(_dr.get('Valor', '') or '').strip()
                        _uni = str(_dr.get('Unidades', '') or '').strip()
                        _lbl = f"{_nom} ({_sym} = {_val} {_uni})".strip()
                        if st.checkbox(_lbl, value=(_did in _dlg_cur),
                                       key=f"dlgdat_{pid}_{_did}"):
                            _dlg_sel_ids.append(_did)
        ed_datos_ids = ','.join(_dlg_sel_ids)

    with dc2:
        ed_enun = st.text_area("Enunciado", value=str(row.get("enunciado", "")),
                                height=120, key="dlg_enun")
        ops_orig = row.get("opciones_list", []) or ["", "", "", ""]
        ed_ops = []
        for li, ll in enumerate(["A", "B", "C", "D"]):
            v = ops_orig[li] if li < len(ops_orig) else ""
            ed_ops.append(st.text_input(f"Opción {ll}", value=v, key=f"dlg_op{ll}"))

    st.markdown("---")
    sc1, sc2, sc3 = st.columns([2, 2, 1])

    if sc1.button("💾 Guardar cambios", type="primary", use_container_width=True, key="dlg_save"):
        datos = {
            "bloque":     ed_blq,
            "tema":       ed_tema,
            "enunciado":  ed_enun.strip(),
            "opciones":   ed_ops,
            "correcta":   ed_corr,
            "dificultad": ed_dif,
            "usada":      ed_usada,
            "notas":      ed_notas.strip(),
            "comentario": ed_com.strip(),
            "objetivo":   ed_obj,
            "datos_ids":  ed_datos_ids,
        }
        ok, msg = lib.actualizar_pregunta_excel_local(
            st.session_state.excel_path,
            st.session_state.excel_dfs,
            pid, datos
        )
        if ok:
            _bloques_sync = list({datos["bloque"], row.get("bloque", datos["bloque"])})
            sync_bloques_gsheets(_bloques_sync)
            reload_db()
            st.rerun()
        else:
            st.error(f"❌ {msg}")

    if sc3.button("✖ Cancelar", use_container_width=True, key="dlg_cancel"):
        st.rerun()


# ── Filtros comunes (Bitácora): Gestor › Gestionar y Generador › Selección ────
_USO_LBL = {"Todos": "Todas", "Nunca usada": "Nunca", "Usada": "Usadas",
            "Usada >6m": "> 6 meses", "Usada >12m": "> 12 meses"}
_USO_LEGACY = {"Usada >6 meses": "Usada >6m", "Usada >12 meses": "Usada >12m"}
_FDEF = dict(search="", bloque="Todos", tema="Todos", obj="Todos", uso="Todos", dif="Todas",
             sol="Todas", com="Todas", glob=False)


def _fkeys(p: str) -> dict:
    return dict(search=f"{p}search", bloque=f"{p}f_bloque", tema=f"{p}f_tema", obj=f"{p}f_obj",
                uso=f"{p}f_uso", dif=f"{p}f_dif", sol=f"{p}f_sol", com=f"{p}f_com", glob=f"{p}search_global")


def limpiar_filtros(p: str, nombres=None):
    """Pide limpiar filtros (se aplica en la siguiente ejecución, antes de dibujarlos)."""
    st.session_state[f"_{p}fclear"] = list(nombres or _FDEF)


def filtros_bitacora(p: str, df: pd.DataFrame, bloques: list, contar_en: pd.DataFrame = None) -> pd.DataFrame:
    """Dibuja los filtros (buscador, bloque, tema, objetivo, uso, dificultad, solución, etiqueta),
    las etiquetas de filtros activos y el recuento; devuelve `df` filtrado.
    `p` es el prefijo de las claves ('man_' en el Gestor, 'sel_' en el Generador)."""
    ss = st.session_state
    K = _fkeys(p)
    for n in ss.pop(f"_{p}fclear", []):
        ss[K[n]] = _FDEF[n]
    if ss.get(K["uso"]) in _USO_LEGACY:
        ss[K["uso"]] = _USO_LEGACY[ss[K["uso"]]]

    def _guard(name, opts):
        if K[name] in ss and ss[K[name]] not in opts:
            ss[K[name]] = _FDEF[name]

    blq_opts = ["Todos"] + [str(b) for b in bloques]
    _guard("bloque", blq_opts)
    _guard("uso", list(_USO_LBL))
    _guard("dif", ["Todas", "Facil", "Media", "Dificil"])
    _guard("sol", ["Todas", "Con", "Sin"])
    base = df if contar_en is None else contar_en

    with st.container(border=True, key=f"card_{p}filtros"):
        c = st.columns([2.2, 1.1, 1.1, 1.3, 1.1], vertical_alignment="bottom")
        f_search = c[0].text_input("Buscar", key=K["search"], placeholder="Enunciado, opciones, notas o ID…")
        f_bloque = c[1].selectbox("Bloque", blq_opts, key=K["bloque"],
                                  format_func=lambda b: "Todos" if b == "Todos" else nombre_bloque(b))
        if ss.get(f"_{p}prev_bloque", f_bloque) != f_bloque:
            ss[K["tema"]] = "Todos"
        ss[f"_{p}prev_bloque"] = f_bloque
        src = df if f_bloque == "Todos" else df[df["bloque"] == f_bloque]
        temas = sorted({str(t).removesuffix(".0") for t in src["Tema"].astype(str) if str(t) not in ("", "nan")},
                       key=_nsort)
        _guard("tema", ["Todos"] + temas)
        f_tema = c[2].selectbox("Tema", ["Todos"] + temas, key=K["tema"],
                                format_func=lambda t: "Todos" if t == "Todos" else nombre_tema(t))
        objs = sorted(set(ss.get("cfg_objetivos", {}) or {})
                      | {str(o) for o in df.get("objetivo", pd.Series(dtype=str)).astype(str)
                         if str(o).strip() not in ("", "nan", "None")}, key=_nsort)
        obj_opts = ["Todos"] + objs + ["__none__"]
        _guard("obj", obj_opts)
        f_obj = c[3].selectbox("Objetivo", obj_opts, key=K["obj"],
                               format_func=lambda o: {"Todos": "Todos", "__none__": "Sin objetivo"}.get(o) or nombre_objetivo(o))

        _u = base["usada"].astype(str).replace({"nan": "", "None": ""})
        _n = {"Todos": len(base), "Nunca usada": int((_u.str.strip() == "").sum()),
              "Usada": int((_u.str.strip() != "").sum()),
              "Usada >6m": int(_u.apply(lambda v: es_uso_antiguo(v, 6)).sum()),
              "Usada >12m": int(_u.apply(lambda v: es_uso_antiguo(v, 12)).sum())}
        c2 = st.columns([3.3, 1.9, 1.3, 0.6], vertical_alignment="bottom")
        with c2[0].container(key=f"pill_{p}uso"):
            f_uso = st.radio("Uso", list(_USO_LBL), key=K["uso"], horizontal=True,
                             format_func=lambda o: f"{_USO_LBL[o]} · {_n[o]}")
        with c2[1].container(key=f"seg_{p}dif"):
            f_dif = st.radio("Dificultad", ["Todas", "Facil", "Media", "Dificil"], key=K["dif"], horizontal=True,
                             format_func=lambda o: {"Facil": "Fácil", "Dificil": "Difícil"}.get(o, o))
        with c2[2].container(key=f"seg_{p}sol"):
            f_sol = st.radio("Solución", ["Todas", "Con", "Sin"], key=K["sol"], horizontal=True)
        coms = sorted({str(x).strip() for x in df.get("comentario", pd.Series(dtype=str)).astype(str)
                       if str(x).strip() not in ("", "nan", "None")})
        _guard("com", ["Todas"] + coms)
        f_com = c[4].selectbox("Etiqueta", ["Todas"] + coms, key=K["com"])

        # ── aplicar ──
        f_glob = bool(ss.get(K["glob"], False)) and bool(f_search.strip())
        d = df
        if f_bloque != "Todos" and not f_glob:
            d = d[d["bloque"] == f_bloque]
        if f_tema != "Todos" and not f_glob:
            d = d[d["Tema"].astype(str).str.removesuffix(".0") == f_tema]
        if f_obj == "__none__":
            d = d[d.get("objetivo", pd.Series("", index=d.index)).astype(str).str.strip().isin(["", "nan", "None"])]
        elif f_obj != "Todos":
            d = d[d.get("objetivo", pd.Series("", index=d.index)).astype(str) == f_obj]
        du = d["usada"].astype(str).replace({"nan": "", "None": ""}).str.strip()
        if f_uso == "Nunca usada":
            d = d[du == ""]
        elif f_uso == "Usada":
            d = d[du != ""]
        elif f_uso in ("Usada >6m", "Usada >12m"):
            d = d[du.apply(lambda v: es_uso_antiguo(v, 6 if f_uso == "Usada >6m" else 12))]
        if f_dif != "Todas":
            d = d[d["dificultad"].astype(str).str.lower() == f_dif.lower()]
        if f_sol != "Todas":
            _con = d.get("solucion", pd.Series("", index=d.index)).astype(str).str.strip().apply(
                lambda v: v not in ("", "nan", "None"))
            d = d[_con] if f_sol == "Con" else d[~_con]
        if f_com != "Todas":
            d = d[d.get("comentario", pd.Series("", index=d.index)).astype(str).str.strip() == f_com]
        if f_search.strip():
            q = f_search.strip().lower()
            m = (d["ID_Pregunta"].astype(str).str.lower().str.contains(q, regex=False)
                 | d["enunciado"].astype(str).str.lower().str.contains(q, regex=False)
                 | d.get("notas", pd.Series("", index=d.index)).astype(str).str.lower().str.contains(q, regex=False)
                 | d["opciones_list"].apply(lambda ops: any(q in str(o).lower() for o in (ops or []))))
            d = d[m]

        # ── filtros activos + recuento ──
        act = []
        if f_search.strip():
            act.append(("search", f"Buscar: «{f_search.strip()[:24]}»"))
        if f_bloque != "Todos":
            act.append(("bloque", f"Bloque: {f_bloque}"))
        if f_tema != "Todos":
            act.append(("tema", f"Tema {f_tema}"))
        if f_obj != "Todos":
            act.append(("obj", "Sin objetivo" if f_obj == "__none__" else f"Objetivo: {f_obj}"))
        if f_uso != "Todos":
            act.append(("uso", f"Uso: {_USO_LBL[f_uso]}"))
        if f_dif != "Todas":
            act.append(("dif", {"Facil": "Fácil", "Dificil": "Difícil"}.get(f_dif, f_dif)))
        if f_sol != "Todas":
            act.append(("sol", "Con solución" if f_sol == "Con" else "Sin solución"))
        if f_com != "Todas":
            act.append(("com", f"Etiqueta: {f_com}"))
        r = st.columns([6, 1.6], vertical_alignment="center")
        with r[0].container(horizontal=True, gap="small", key=f"chips_{p}"):
            if act:
                st.markdown("<span class='chips-lbl'>Filtros activos:</span>", unsafe_allow_html=True)
                for name, lbl in act:
                    if st.button(f"{lbl}  ×", key=f"{p}chip_{name}", help="Quitar este filtro"):
                        limpiar_filtros(p, [name] + (["glob"] if name == "search" else []))
                        st.rerun()
                if len(act) > 1 and st.button("Limpiar filtros", key=f"{p}chip_all", type="tertiary"):
                    limpiar_filtros(p)
                    st.rerun()
            else:
                st.markdown("<span class='chips-lbl'>Sin filtros</span>", unsafe_allow_html=True)
            if f_search.strip() and (f_bloque != "Todos" or f_tema != "Todos"):
                st.checkbox("Buscar en todos los bloques", key=K["glob"])
        r[1].markdown(f"<div class='chips-count'><b>{len(d)}</b> de {len(base)} preguntas</div>",
                      unsafe_allow_html=True)
    return d


def marcar_preguntas_usadas(pids: list, fecha_str: str) -> int:
    """Marca una lista de IDs de pregunta como usadas con la fecha dada.
    Devuelve el número de preguntas actualizadas correctamente."""
    count = 0
    df_p = st.session_state.get("df_preguntas")
    filas = df_p.set_index("ID_Pregunta").to_dict("index") if df_p is not None else {}
    for pid in pids:
        if pid not in filas:
            continue
        ok, _ = lib.actualizar_pregunta_excel_local(
            st.session_state.excel_path,
            st.session_state.excel_dfs,
            pid,
            datos_de_fila(filas[pid], usada=fecha_str)   # la función sobrescribe todos los campos
        )
        if ok:
            count += 1
    if count:
        # Sincronizar bloques afectados
        df_p = st.session_state.get("df_preguntas")
        if df_p is not None:
            bloques = df_p[df_p["ID_Pregunta"].isin(pids)]["bloque"].unique().tolist()
            sync_bloques_gsheets(bloques)
        reload_db()
    return count


# Fecha del archivo al cargarse (ver _recarga.py)
import os as _os_mt
_MTIME = _os_mt.path.getmtime(__file__)
