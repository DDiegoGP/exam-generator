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
        # Configuración de bloques/temas
        "cfg_bloques":   {},   # {bloque_name: descripcion}
        "cfg_temas":     {},   # {tema_str: {nombre, bloque}}
        "cfg_general":   {},   # {clave: valor}
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
    st.session_state.cfg_bloques = lib.get_cfg_bloques(dfs)
    st.session_state.cfg_temas   = lib.get_cfg_temas(dfs)
    st.session_state.cfg_general = lib.get_cfg_general(dfs)
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
            })

    if not rows:
        return pd.DataFrame(columns=["ID_Pregunta","bloque","Tema","enunciado",
                                      "opciones_list","letra_correcta","dificultad","usada","notas","solucion"])
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
        cfg = st.secrets.get("GOOGLE_OAUTH", {})
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
def _render_gsheets_oauth():
    """
    Sección Google Sheets en el sidebar.
    Solo se renderiza si 'GOOGLE_OAUTH' está configurado en st.secrets.
    """
    cfg = st.secrets.get("GOOGLE_OAUTH", {})
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
            key="sidebar_gsheets_url",
            label_visibility="collapsed",
            placeholder="https://docs.google.com/spreadsheets/d/...",
        )

        gc1, gc2 = st.columns(2)
        if gc1.button("📥 Cargar", key="btn_load_gsheets", use_container_width=True):
            with st.spinner("Conectando…"):
                ok, msg = connect_db_from_gsheets(
                    st.session_state["google_token"], gs_url
                )
            if ok:
                st.rerun()
            else:
                st.error(msg)

        if gc2.button("🚪 Salir", key="btn_logout_google", use_container_width=True):
            for k in ("google_token", "google_user_email", "_gsheets_url", "_gsheets_title"):
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()


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
        st.markdown(
            "<div style='background:linear-gradient(135deg,#1a252f,#2c3e50);"
            "border-radius:10px;padding:12px 16px;margin-bottom:14px;color:white'>"
            "<div style='font-size:1.15em;font-weight:800;letter-spacing:-.01em'>📝 ExamGen UCM</div>"
            f"<div style='font-size:0.78em;opacity:0.85;margin-top:3px;font-weight:600'>{_sub}</div>"
            f"{_inst_line}"
            "</div>",
            unsafe_allow_html=True,
        )

        # ── Google Sheets OAuth (si está configurado) ─────────────────────────
        _render_gsheets_oauth()

        st.markdown("**📚 Base de Datos Excel**")

        # ── Upload de Excel (funciona local Y en Cloud) ───────────────────────
        uploaded = st.file_uploader(
            "Cargar Excel (.xlsx)",
            type=["xlsx"],
            key="sidebar_upload",
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
                key="sidebar_path_manual",
                label_visibility="collapsed",
                placeholder="C:/ruta/archivo.xlsx",
            )
            if st.button("🔌 Conectar", key="btn_conectar_manual",
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
            if _asig_sb:  _lines.append(f"<b style='color:#2c3e50'>{_asig_sb}</b>")
            if _grado_sb: _lines.append(f"<span style='color:#555'>{_grado_sb}</span>")
            if _anio_sb:  _lines.append(f"<span style='color:#777;font-size:0.85em'>{_anio_sb}</span>")
            if _dept_sb:  _lines.append(f"<span style='color:#888;font-size:0.82em'>{_dept_sb}</span>")
            if _univ_sb:  _lines.append(f"<span style='color:#888;font-size:0.82em'>{_univ_sb}</span>")
            st.markdown(
                "<div style='background:#f0f7ff;border:1px solid #c8dff8;border-radius:8px;"
                "padding:9px 13px;margin-bottom:10px;line-height:1.6'>"
                + "<br>".join(_lines) +
                "<div style='font-size:0.7em;color:#aaa;margin-top:4px'>📋 Configuración → General</div>"
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
                f'<small style="color:#555">{fname}</small>',
                unsafe_allow_html=True,
            )
            st.caption(f"{len(df)} preguntas · {len(st.session_state.bloques)} bloques")
            if not df.empty:
                nunca = (df["usada"] == "").sum()
                st.caption(f"🆕 Sin usar: {nunca} · 📝 Usadas: {len(df) - nunca}")

            col_r, col_d = st.columns(2)
            if col_r.button("🔄 Recargar", use_container_width=True, key="btn_reload"):
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
                    key="btn_download_excel",
                )
        else:
            st.markdown('<span class="conn-wait">⏳ Sin conexión</span>',
                        unsafe_allow_html=True)
            st.caption("Sube un archivo Excel arriba para empezar.")

        st.divider()
        st.caption("ExamGen UCM · Unidad de Física Médica")

# ── Page header helper ────────────────────────────────────────────────────────
def page_header(icon: str, title: str, subtitle: str = ""):
    """Renderiza una cabecera de página consistente con componentes nativos."""
    st.title(f"{icon} {title}")
    if subtitle:
        st.caption(subtitle)

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

def es_uso_antiguo(v: str, months: int) -> bool:
    try:
        return (datetime.datetime.strptime(str(v).split(" ")[0], "%Y-%m-%d")
                < datetime.datetime.now() - datetime.timedelta(days=months * 30))
    except (ValueError, TypeError):
        return False

def mathjax_html(contenido: str) -> str:
    """Envuelve contenido HTML en una página con MathJax y los estilos de la app."""
    return f"""<!DOCTYPE html><html><head>
<script>MathJax={{tex:{{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$'],['\\\\[','\\\\]']]}},svg:{{fontCache:'global'}}}};</script>
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
        nota_html = (f'<div style="margin-top:5px;padding:3px 8px;background:#fef3cd;'
                     f'border-radius:3px;font-size:0.8em">📝 {notas}</div>')

    def _trunc(s: str, n: int = 32) -> str:
        return s if len(s) <= n else s[:n] + "…"

    _blq_label = _trunc(nombre_bloque(str(row.get("bloque", ""))), 30)
    _tem_label = _trunc(nombre_tema(str(row.get("Tema", ""))), 35)

    return (
        f'<div class="q-card {cls_card}">'
        f'<div class="q-head">'
        f'<span class="q-num">{num_s} &nbsp;<small style="font-weight:400;color:#888">{row.get("ID_Pregunta","")}</small></span>'
        f'<span title="{nombre_bloque(str(row.get("bloque","")))} · {nombre_tema(str(row.get("Tema","")))}">'
        f'{_blq_label} · {_tem_label} '
        f'<span class="tag {cls_tag}">{dif}</span>'
        f'<span class="tag {cls_u}">{u_t}</span></span></div>'
        f'<div class="q-enun">{row.get("enunciado","")}</div>'
        f'{opts_html}{nota_html}</div>'
    )
