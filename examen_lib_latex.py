import pandas as pd
import random, re, os
from docx import Document
from docx.shared import Inches, RGBColor, Pt
import openpyxl

try:
    import gspread
    from google.auth import default
    _HAS_GSPREAD = True
except ImportError:
    _HAS_GSPREAD = False

# --- DETECCIÓN DE ENTORNO ---
def detectar_entorno():
    """Retorna 'colab' si se ejecuta en Google Colab, 'local' en caso contrario."""
    try:
        import google.colab
        return 'colab'
    except ImportError:
        return 'local'

# --- CONEXIÓN GOOGLE SHEETS ---
def conectar_sheet_seguro(url):
    if not _HAS_GSPREAD:
        raise ImportError("gspread no disponible. Instale gspread y google-auth para usar Google Sheets.")
    creds, _ = default()
    gc = gspread.authorize(creds)
    return gc.open_by_url(url)

# --- CONEXIÓN EXCEL LOCAL ---
def cargar_excel_local(filepath):
    """Lee todas las hojas de un .xlsx y devuelve dict {nombre_hoja: DataFrame}."""
    xls = pd.ExcelFile(filepath, engine='openpyxl')
    return {name: pd.read_excel(xls, sheet_name=name) for name in xls.sheet_names}

def backup_excel(filepath, max_backups=10):
    """Crea backup del Excel antes de guardar. Mantiene ultimas max_backups copias."""
    import shutil, datetime as _dt
    if not os.path.exists(filepath): return
    backup_dir = os.path.join(os.path.dirname(filepath), '_backups')
    os.makedirs(backup_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(filepath))[0]
    ts = _dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    shutil.copy2(filepath, os.path.join(backup_dir, f"{base}_{ts}.xlsx"))
    # Limpiar backups antiguos
    bks = sorted([f for f in os.listdir(backup_dir) if f.startswith(base) and f.endswith('.xlsx')])
    for old in bks[:-max_backups]:
        os.remove(os.path.join(backup_dir, old))

def guardar_excel_local(filepath, dict_of_dfs):
    """Escribe a disco. Si filepath está vacío (modo cloud/upload), no hace nada."""
    if not filepath:
        return
    backup_excel(filepath)
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        for sheet_name, df in dict_of_dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

def generar_excel_bytes(dict_of_dfs) -> bytes:
    """Genera el Excel en memoria (para descarga en cloud mode o backup)."""
    import io as _io
    buf = _io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        for sheet_name, df in dict_of_dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buf.getvalue()

def actualizar_pregunta_excel_local(filepath, dict_of_dfs, pid, datos):
    """Equivalente local de actualizar_pregunta_db para archivos Excel."""
    try:
        bloque = datos['bloque']
        if bloque not in dict_of_dfs:
            return False, f"Bloque '{bloque}' no encontrado"
        df = dict_of_dfs[bloque]
        # Asegurar columna notas existe
        if not any('nota' in str(c).lower() for c in df.columns):
            df['notas'] = ''; dict_of_dfs[bloque] = df
        mask = df['ID_Pregunta'].astype(str) == str(pid)
        if not mask.any():
            return False, "ID no encontrado"
        idx = df[mask].index[0]

        for col in df.columns:
            cl = str(col).lower().strip()
            if 'enunciado' in cl:
                df.at[idx, col] = datos['enunciado']
            elif 'tema' in cl and 'id' not in cl:
                df.at[idx, col] = datos['tema']
            elif 'correcta' in cl or 'resp' in cl:
                df.at[idx, col] = datos['correcta']
            elif 'dificultad' in cl:
                df.at[idx, col] = datos['dificultad']
            elif 'usada' in cl or 'used' in cl:
                if datos.get('usada'):
                    df.at[idx, col] = datos['usada']
            elif 'nota' in cl:
                df.at[idx, col] = datos.get('notas', '')

        # Actualizar opciones (columnas después de Enunciado)
        enun_col_idx = None
        for i, col in enumerate(df.columns):
            if 'enunciado' in str(col).lower():
                enun_col_idx = i
                break
        if enun_col_idx is not None:
            for j, op in enumerate(datos['opciones']):
                op_col_idx = enun_col_idx + 1 + j
                if op_col_idx < len(df.columns):
                    df.iat[idx, op_col_idx] = op

        guardar_excel_local(filepath, dict_of_dfs)
        return True, "Actualizado correctamente"
    except Exception as e:
        return False, str(e)

def eliminar_preguntas_excel_local(filepath, dict_of_dfs, ids):
    """Elimina varias preguntas por ID de todas las hojas del Excel."""
    try:
        backup_excel(filepath)
        ids_set = set(str(i) for i in ids)
        count = 0
        for sheet in list(dict_of_dfs.keys()):
            df = dict_of_dfs[sheet]
            if 'ID_Pregunta' not in df.columns:
                continue
            mask = df['ID_Pregunta'].astype(str).isin(ids_set)
            count += int(mask.sum())
            dict_of_dfs[sheet] = df[~mask].reset_index(drop=True)
        guardar_excel_local(filepath, dict_of_dfs)
        return True, f"{count} pregunta(s) eliminada(s)"
    except Exception as e:
        return False, str(e)

def actualizar_campo_masivo(filepath, dict_of_dfs, ids, campo, valor):
    """Actualiza tema o dificultad para múltiples preguntas a la vez."""
    try:
        backup_excel(filepath)
        ids_set = set(str(i) for i in ids)
        count = 0
        for sheet, df in dict_of_dfs.items():
            if 'ID_Pregunta' not in df.columns:
                continue
            mask = df['ID_Pregunta'].astype(str).isin(ids_set)
            if not mask.any():
                continue
            for col in df.columns:
                cl = str(col).lower().strip()
                if campo == 'tema' and 'tema' in cl and 'id' not in cl:
                    dict_of_dfs[sheet].loc[mask, col] = valor
                    count += int(mask.sum())
                elif campo == 'dificultad' and 'dificultad' in cl:
                    dict_of_dfs[sheet].loc[mask, col] = valor
                    count += int(mask.sum())
        guardar_excel_local(filepath, dict_of_dfs)
        return True, f"{count} pregunta(s) actualizadas → {campo}='{valor}'"
    except Exception as e:
        return False, str(e)

def reemplazar_texto_masivo(filepath, dict_of_dfs, ids, buscar, reemplazar_con):
    """Find & replace en el enunciado de las preguntas indicadas."""
    try:
        backup_excel(filepath)
        ids_set = set(str(i) for i in ids)
        count = 0
        for sheet, df in dict_of_dfs.items():
            if 'ID_Pregunta' not in df.columns:
                continue
            mask = df['ID_Pregunta'].astype(str).isin(ids_set)
            if not mask.any():
                continue
            for col in df.columns:
                if 'enunciado' in str(col).lower():
                    dict_of_dfs[sheet].loc[mask, col] = (
                        df.loc[mask, col].astype(str)
                        .str.replace(buscar, reemplazar_con, regex=False)
                    )
                    count += int(mask.sum())
                    break
        guardar_excel_local(filepath, dict_of_dfs)
        return True, f"Texto reemplazado en {count} pregunta(s)"
    except Exception as e:
        return False, str(e)

def validar_pregunta(pregunta):
    """Valida una pregunta dict. Retorna (ok, warnings_list)."""
    warnings = []
    enun = pregunta.get('enunciado', '').strip()
    if not enun: warnings.append("Enunciado vacio")
    ops = pregunta.get('opciones_list', [])
    if len(ops) < 4: warnings.append(f"Solo {len(ops)} opciones (se necesitan 4)")
    for i, op in enumerate(ops):
        if not str(op).strip(): warnings.append(f"Opcion {chr(65+i)} vacia")
    correcta = pregunta.get('letra_correcta', '').upper()
    if correcta not in ('A','B','C','D'): warnings.append(f"Respuesta correcta invalida: '{correcta}'")
    ops_clean = [str(o).strip().lower() for o in ops if str(o).strip()]
    if len(ops_clean) != len(set(ops_clean)): warnings.append("Opciones duplicadas detectadas")
    return len(warnings) == 0, warnings

# --- UTILIDADES ---
def check_for_similar_enunciado(text, df):
    if df.empty: return False, 0.0
    from difflib import SequenceMatcher
    text = str(text).lower().strip()
    if 'enunciado' not in df.columns: return False, 0.0
    sims = df['enunciado'].astype(str).apply(lambda x: SequenceMatcher(None, text, x.lower().strip()).ratio())
    max_sim = sims.max()
    return (max_sim > 0.9, max_sim)

def generar_siguiente_id(df, bloque, tema):
    prefix = f"FM_{str(bloque).zfill(2)}_{str(tema).zfill(2)}"
    if df is None or df.empty or 'ID_Pregunta' not in df.columns: return f"{prefix}_01", 1
    existing = df[df['ID_Pregunta'].astype(str).str.startswith(prefix)]
    if existing.empty: return f"{prefix}_01", 1
    nums = []
    for x in existing['ID_Pregunta']:
        try: nums.append(int(x.split('_')[-1]))
        except: pass
    next_n = max(nums) + 1 if nums else 1
    return f"{prefix}_{str(next_n).zfill(2)}", next_n

def get_first_empty_row(worksheet, col_check=1):
    cols = worksheet.col_values(col_check) 
    return len(cols) + 1

# --- PARSERS DE IMPORTACIÓN (formato normalizado) ---
# Cada parser devuelve lista de dicts:
# {'enunciado': str, 'opciones_list': [A,B,C,D], 'letra_correcta': str,
#  'bloque': str, 'tema': str, 'dificultad': str, '_warnings': [str]}

def parse_aiken(text, bloque_destino='', tema_destino='1', dificultad_destino='Media'):
    """Parsea texto en formato Aiken. Devuelve lista normalizada de preguntas."""
    preguntas = []
    lines = [l.rstrip() for l in text.splitlines()]
    current = None
    re_opt = re.compile(r'^([A-D])[.)]\s+(.+)', re.IGNORECASE)
    re_ans = re.compile(r'^ANSWER[:\s]+([A-D])', re.IGNORECASE)

    for line in lines:
        if not line.strip():
            continue
        m_ans = re_ans.match(line)
        m_opt = re_opt.match(line)
        if m_ans:
            if current:
                current['letra_correcta'] = m_ans.group(1).upper()
                while len(current['opciones_list']) < 4:
                    current['opciones_list'].append("")
                current['opciones_list'] = current['opciones_list'][:4]
                preguntas.append(current)
                current = None
        elif m_opt:
            if current:
                current['opciones_list'].append(m_opt.group(2).strip())
        else:
            # Nueva pregunta: línea que no es opción ni ANSWER
            if current:  # pregunta sin ANSWER: guardar incompleta
                current['_warnings'].append("Sin respuesta ANSWER")
                while len(current['opciones_list']) < 4: current['opciones_list'].append("")
                current['opciones_list'] = current['opciones_list'][:4]
                preguntas.append(current)
            current = {
                'enunciado': line.strip(), 'opciones_list': [],
                'letra_correcta': 'A', 'bloque': bloque_destino,
                'tema': tema_destino, 'dificultad': dificultad_destino,
                '_warnings': []
            }
    if current:
        current['_warnings'].append("Sin respuesta ANSWER al final")
        while len(current['opciones_list']) < 4: current['opciones_list'].append("")
        current['opciones_list'] = current['opciones_list'][:4]
        preguntas.append(current)

    # Validación básica
    for p in preguntas:
        if len([o for o in p['opciones_list'] if o.strip()]) < 4:
            p['_warnings'].append("Menos de 4 opciones detectadas")
    return preguntas

# --- IMPORTACIÓN WORD ---
def procesar_archivo_docx(filepath, bloque_destino, tema_destino='1', dificultad_destino='Media'):
    """Parsea un .docx con preguntas numeradas. Devuelve lista normalizada."""
    doc = Document(filepath)
    preguntas = []
    current_preg = None
    re_preg = re.compile(r'^\s*(\d+)[\.\-\)]+\s*(.+)', re.DOTALL)
    re_opt_explicit = re.compile(r'^\s*([a-dA-D])[\.\-\)]+\s*(.+)', re.IGNORECASE)

    for para in doc.paragraphs:
        txt = para.text.strip()
        if not txt: continue
        is_bold = any(run.bold for run in para.runs)

        m_p = re_preg.match(txt)
        if m_p:
            if current_preg:
                while len(current_preg['opciones_list']) < 4: current_preg['opciones_list'].append("")
                current_preg['opciones_list'] = current_preg['opciones_list'][:4]
                preguntas.append(current_preg)
            current_preg = {
                'enunciado': m_p.group(2).strip(), 'opciones_list': [],
                'letra_correcta': 'A', 'bloque': bloque_destino,
                'tema': tema_destino, 'dificultad': dificultad_destino,
                '_warnings': []
            }
            continue

        if current_preg:
            m_o = re_opt_explicit.match(txt)
            texto_opcion = m_o.group(2).strip() if m_o else (txt if len(current_preg['opciones_list']) < 4 else "")
            if texto_opcion:
                current_preg['opciones_list'].append(texto_opcion)
                if is_bold:
                    idx = len(current_preg['opciones_list']) - 1
                    current_preg['letra_correcta'] = ['A','B','C','D'][idx] if idx < 4 else 'A'

    if current_preg:
        while len(current_preg['opciones_list']) < 4: current_preg['opciones_list'].append("")
        current_preg['opciones_list'] = current_preg['opciones_list'][:4]
        preguntas.append(current_preg)

    for p in preguntas:
        if len([o for o in p['opciones_list'] if o.strip()]) < 4:
            p['_warnings'].append("Menos de 4 opciones detectadas")
    return preguntas

# --- DB UPDATE ---
def actualizar_pregunta_db(sheet, pid, datos, idx_usada_ignorado):
    try:
        ws = sheet.worksheet(datos['bloque'])
        cell = ws.find(pid)
        if not cell: return False, "ID no encontrado"
        r = cell.row
        headers = [str(h).lower().strip() for h in ws.row_values(1)]
        col_enun = -1; col_tem = -1; col_corr = -1; col_dif = -1; col_usada = -1; col_nota = -1
        for i, h in enumerate(headers):
            idx = i + 1
            if 'enunciado' in h: col_enun = idx
            elif 'tema' in h: col_tem = idx
            elif 'correcta' in h or 'resp' in h: col_corr = idx
            elif 'dificultad' in h: col_dif = idx
            elif 'usada' in h or 'used' in h: col_usada = idx
            elif 'nota' in h: col_nota = idx

        if col_enun != -1: ws.update_cell(r, col_enun, datos['enunciado'])
        if col_tem != -1: ws.update_cell(r, col_tem, datos['tema'])
        if col_corr != -1: ws.update_cell(r, col_corr, datos['correcta'])
        if col_dif != -1: ws.update_cell(r, col_dif, datos['dificultad'])
        if col_nota != -1: ws.update_cell(r, col_nota, datos.get('notas', ''))
        if col_enun != -1:
            cells = [gspread.Cell(r, col_enun+1+i, op) for i, op in enumerate(datos['opciones'])]
            ws.update_cells(cells)
        if datos['usada'] and col_usada != -1:
            ws.update_cell(r, col_usada, datos['usada'])
        return True, "Actualizado correctamente"
    except Exception as e: return False, str(e)

# --- UTILIDADES LATEX ---
def _escape_latex(text):
    """Escapa caracteres especiales de LaTeX, preservando secciones math ($...$, $$...$$)."""
    text = str(text)
    # Extraer secciones math para protegerlas del escape
    import re as _re
    _math_parts = []
    def _save_math(m):
        _math_parts.append(m.group(0))
        return f'\x00MATH{len(_math_parts)-1}\x00'
    # Proteger $$...$$ primero, luego $...$
    text = _re.sub(r'\$\$.+?\$\$', _save_math, text, flags=_re.DOTALL)
    text = _re.sub(r'\$.+?\$', _save_math, text)
    # Escapar texto plano
    text = text.replace('\\', r'\textbackslash{}')
    for char in ['&', '%', '#', '_', '{', '}']:
        text = text.replace(char, '\\' + char)
    text = text.replace('~', r'\textasciitilde{}')
    text = text.replace('^', r'\textasciicircum{}')
    # Restaurar secciones math
    for i, mp in enumerate(_math_parts):
        text = text.replace(f'\x00MATH{i}\x00', mp)
    return text

# --- EXPORTAR ---
def generar_master_examen(pool, num_modelos, cfg):
    master = []
    letras_version = ['A','B','C','D','E','F']
    for m in range(1, num_modelos+1):
        ex = [p.copy() for p in pool]
        if cfg.get('barajar_preguntas', True): random.shuffle(ex)
        for idx, p in enumerate(ex):
            ops = p.get('opciones_visibles', p.get('opciones_list'))[:]
            correcta_orig_letra = p.get('letra_correcta', 'A')
            idx_orig = {'A':0, 'B':1, 'C':2, 'D':3}.get(correcta_orig_letra, 0)
            txt_correcta = p.get('opciones_list')[idx_orig]
            anclado = False
            frases_anclaje = ["todas las anteriores", "ninguna de las anteriores", "ambas son", "son correctas", "son falsas"]
            if cfg.get('frases_anclaje_extra'):
                frases_anclaje.extend([x.lower().strip() for x in cfg['frases_anclaje_extra'].split(',')])
            for op in ops:
                if any(f in str(op).lower() for f in frases_anclaje): anclado = True
            if cfg.get('barajar_respuestas', True) and not anclado:
                random.shuffle(ops)
            try:
                new_idx = ops.index(txt_correcta)
                new_letra = ['A','B','C','D'][new_idx]
            except: new_letra = 'A'
            p['opciones_finales'] = ops; p['letra_final'] = new_letra; p['num'] = idx + 1
        letra_v = letras_version[m-1] if m <= len(letras_version) else str(m)
        master.append({'modelo': m, 'letra_version': letra_v, 'preguntas': ex})
    return master

def exportar_archivos_csv(master, ruta, nombre):
    # 1. CLAVES (Formato Vertical Lector)
    rows_claves = []
    for m in master:
        version = m['letra_version']
        for p in m['preguntas']:
            rows_claves.append({
                'Pregunta': p['num'], 'Versión': version, 'Respuesta': p['letra_final'],
                'Puntos': '1,00', 'Vínculo': '0', 'Penalización': '0,33',
                'Ponderación': '0,00', 'Máx.P.Abiertas': '0,00'
            })
    pd.DataFrame(rows_claves).to_csv(os.path.join(ruta, f"{nombre}_CLAVES.csv"), index=False, encoding='utf-8-sig', sep=';')

    # 2. METADATA (Información para el profesor)
    rows_meta = []
    for m in master:
        for p in m['preguntas']:
            rows_meta.append({
                'Modelo': m['modelo'], 'Version': m['letra_version'], 'Num_Examen': p['num'],
                'ID_BaseDatos': p['ID_Pregunta'], 'Bloque': p.get('bloque',''), 'Tema': p.get('Tema',''),
                'Dificultad': p.get('dificultad',''), 'Enunciado_Inicio': str(p['enunciado'])[:50]
            })
    pd.DataFrame(rows_meta).to_csv(os.path.join(ruta, f"{nombre}_METADATA.csv"), index=False, encoding='utf-8-sig', sep=';')

def generar_latex(master, ruta, nombre, cfg, modo_solucion=False):
    sufijo = "_SOL" if modo_solucion else ""
    plantilla_tex = ""
    if cfg.get('plantilla_tex_path'):
        try:
            with open(cfg['plantilla_tex_path'], 'r', encoding='utf-8') as f: plantilla_tex = f.read()
        except (FileNotFoundError, PermissionError, UnicodeDecodeError): pass
    _DEFAULT_TEX = r"""\documentclass[a4paper,12pt]{exam}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[spanish]{babel}
\usepackage{amsmath,amssymb}
\usepackage{geometry}
\geometry{margin=2cm}
\usepackage{xcolor}
\usepackage{graphicx}

% Header / Footer
\pagestyle{headandfoot}
\firstpageheader{[[LOGO]][[INSTITUCION]]}{[[TIPO_EXAMEN]] -- Modelo [[VERSION]]}{[[FECHA]]}
\runningheader{[[TITULO]]}{Modelo [[VERSION]]}{Pág. \thepage/\numpages}
\firstpagefooter{}{}{}
\runningfooter{}{}{}

\begin{document}

\begin{center}
{\Large \textbf{[[TITULO]]}} \\[6pt]
{\large [[TIPO_EXAMEN]] -- Modelo [[VERSION]]} \\[4pt]
[[INSTITUCION]] \hfill [[FECHA]] \hfill Tiempo: [[TIEMPO]]
\end{center}

\vspace{2mm}
\noindent\textbf{Nombre:} \hrulefill \hspace{1cm} \textbf{Grupo:} \hrulefill

\vspace{3mm}
\noindent\textit{[[INSTRUCCIONES]]}

[[INFO_FUNDAMENTALES]]

[[FUNDAMENTALES]]

[[INFO_TEST]]

\begin{questions}
[[PREGUNTAS]]
\end{questions}

\end{document}"""

    if not plantilla_tex:
        plantilla_tex = _DEFAULT_TEX

    for m in master:
        tex = plantilla_tex
        tex = tex.replace('[[TIPO_EXAMEN]]', _escape_latex(cfg.get('tipo_examen','')))
        tex = tex.replace('[[INSTITUCION]]', _escape_latex(cfg.get('entidad','')))
        tex = tex.replace('[[TITULO]]', _escape_latex(cfg.get('titulo_asignatura','')))
        tex = tex.replace('[[FECHA]]', _escape_latex(cfg.get('fecha','')))
        tex = tex.replace('[[TIEMPO]]', _escape_latex(cfg.get('tiempo','')))
        tex = tex.replace('[[VERSION]]', m['letra_version'])
        tex = tex.replace('[[INSTRUCCIONES]]', _escape_latex(cfg.get('instr_gen','')))
        tex = tex.replace('[[INFO_FUNDAMENTALES]]', _escape_latex(cfg.get('info_fund','')))
        tex = tex.replace('[[INFO_TEST]]', _escape_latex(cfg.get('info_test','')))
        logo_path = cfg.get('logo_path', '')
        if logo_path and os.path.isfile(logo_path):
            logo_tex = r"\includegraphics[height=1.2cm]{" + logo_path.replace('\\', '/') + r"} "
        else:
            logo_tex = ""
        tex = tex.replace('[[LOGO]]', logo_tex)

        bloque_fund = ""
        if cfg.get('fundamentales_data'):
            bloque_fund = r"\begin{enumerate}" + "\n"
            for c in cfg['fundamentales_data']:
                bloque_fund += r"\item \textbf{" + _escape_latex(c['txt']) + r"} (" + str(c['pts']) + " pts)\n"
                esp = c.get('espacio','Automático'); h = "5cm"
                if "10" in esp: h="8cm"
                elif "Media" in esp: h="12cm"
                elif "Cara" in esp: h="18cm"
                if modo_solucion: bloque_fund += r"\par \textit{[Espacio (" + esp + r")]} \vspace{1cm}" + "\n"
                else: bloque_fund += r"\par \framebox{\begin{minipage}[t]["+h+r"]{\linewidth} \end{minipage}} \vspace{0.5cm}" + "\n"
            bloque_fund += r"\end{enumerate}" + "\n"
        tex = tex.replace('[[FUNDAMENTALES]]', bloque_fund)

        bloque_test = ""
        for p in m['preguntas']:
            bloque_test += r"\question " + _escape_latex(p['enunciado']) + "\n"
            ops = p['opciones_finales']; letra_corr = p['letra_final']; idx_corr = {'A':0,'B':1,'C':2,'D':3}.get(letra_corr, 0)
            bloque_test += r"\begin{choices}" + "\n"
            for i, l in enumerate(['a','b','c','d']):
                txt_op = _escape_latex(ops[i])
                if modo_solucion and i == idx_corr:
                    if cfg.get('sol_negrita'): txt_op = r"\textbf{" + txt_op + "}"
                    if cfg.get('sol_rojo'): txt_op = r"\textcolor{red}{" + txt_op + "}"
                    if cfg.get('sol_ast'): txt_op = txt_op + " *"
                    bloque_test += r"\CorrectChoice " + txt_op + "\n"
                else:
                    bloque_test += r"\choice " + txt_op + "\n"
            bloque_test += r"\end{choices}" + "\n"
        tex = tex.replace('[[PREGUNTAS]]', bloque_test)
        
        with open(os.path.join(ruta, f"{nombre}_MOD{m['letra_version']}{sufijo}.tex"), "w", encoding='utf-8') as f: f.write(tex)

def _insert_paragraph_after(paragraph, text=""):
    """Inserta un párrafo nuevo inmediatamente después del párrafo dado. Devuelve el nuevo Paragraph."""
    from docx.oxml.ns import qn
    new_p = paragraph._element.makeelement(qn('w:p'), {})
    paragraph._element.addnext(new_p)
    new_para = paragraph.__class__(new_p, paragraph._parent)
    if text:
        new_para.text = text
    return new_para

def _insert_table_after(paragraph, rows, cols, doc):
    """Inserta una tabla después del párrafo dado. Devuelve la tabla."""
    tbl = doc.add_table(rows=rows, cols=cols)
    # Mover la tabla XML justo después del párrafo
    paragraph._element.addnext(tbl._tbl)
    return tbl

def _replace_in_paragraph(paragraph, key, val):
    """Reemplaza placeholder en un párrafo respetando los runs y su formato."""
    full = paragraph.text
    if key not in full:
        return
    # Caso simple: placeholder en un solo run
    for run in paragraph.runs:
        if key in run.text:
            run.text = run.text.replace(key, val)
            return
    # Caso complejo: placeholder dividido entre runs - reconstruir
    combined = ''.join(r.text for r in paragraph.runs)
    idx = combined.find(key)
    if idx < 0:
        return
    # Localizar qué runs abarca el placeholder
    pos = 0
    start_run = end_run = 0
    start_offset = end_offset = 0
    for ri, run in enumerate(paragraph.runs):
        rlen = len(run.text)
        if pos + rlen > idx and start_run == 0 and pos <= idx:
            start_run = ri
            start_offset = idx - pos
        if pos + rlen >= idx + len(key):
            end_run = ri
            end_offset = idx + len(key) - pos
            break
        pos += rlen
    # Insertar valor en el primer run, limpiar los intermedios
    runs = paragraph.runs
    runs[start_run].text = runs[start_run].text[:start_offset] + val + runs[end_run].text[end_offset:]
    for ri in range(start_run + 1, end_run + 1):
        runs[ri].text = ''

def _setup_word_styles(doc, cfg, version):
    """Configura estilos profesionales para documento Word sin plantilla."""
    from docx.shared import Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_ORIENT

    # Margenes 2cm
    for section in doc.sections:
        section.top_margin = Cm(2); section.bottom_margin = Cm(2)
        section.left_margin = Cm(2); section.right_margin = Cm(2)

    # Fuente por defecto
    style = doc.styles['Normal']
    style.font.name = 'Calibri'; style.font.size = Pt(11)

    # Header
    header = doc.sections[0].header
    hp = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    hp.text = f"{cfg.get('entidad','')}  |  {cfg.get('titulo_asignatura','')}  |  Modelo {version}"
    hp.style.font.size = Pt(8); hp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Footer
    footer = doc.sections[0].footer
    fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fp.style.font.size = Pt(8)

    # Titulo centrado
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run(cfg.get('titulo_asignatura','')); r.bold = True; r.font.size = Pt(16); r.font.name = 'Calibri'
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = sub.add_run(f"{cfg.get('tipo_examen','')} - Modelo {version}"); r2.font.size = Pt(13); r2.font.name = 'Calibri'
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r3 = info.add_run(f"{cfg.get('entidad','')}    {cfg.get('fecha','')}    Tiempo: {cfg.get('tiempo','')}"); r3.font.size = Pt(10)

    # Nombre y grupo
    doc.add_paragraph("")
    ng = doc.add_paragraph()
    ng.add_run("Nombre: ").bold = True; ng.add_run("_" * 50 + "   ")
    ng.add_run("Grupo: ").bold = True; ng.add_run("_" * 15)

    # Instrucciones
    if cfg.get('instr_gen'):
        pi = doc.add_paragraph()
        ri = pi.add_run(cfg.get('instr_gen','')); ri.italic = True; ri.font.size = Pt(10)

    doc.add_paragraph("")  # Separador
    doc.add_paragraph("[[FUNDAMENTALES]]")
    doc.add_paragraph("[[PREGUNTAS]]")

def rellenar_plantilla_word(master, ruta, nombre, cfg, tpl_path=None, modo_solucion=False):
    for m in master:
        doc = Document(tpl_path) if tpl_path else Document()
        sufijo = "_SOL" if modo_solucion else ""
        if not tpl_path:
            _setup_word_styles(doc, cfg, m['letra_version'])

        replacements = {'[[TIPO_EXAMEN]]': cfg.get('tipo_examen',''), '[[INSTITUCION]]': cfg.get('entidad',''),
            '[[TITULO]]': cfg.get('titulo_asignatura',''), '[[FECHA]]': cfg.get('fecha',''),
            '[[TIEMPO]]': cfg.get('tiempo',''), '[[VERSION]]': m['letra_version'],
            '[[INSTRUCCIONES]]': cfg.get('instr_gen',''), '[[INFO_FUNDAMENTALES]]': cfg.get('info_fund',''),
            '[[INFO_TEST]]': cfg.get('info_test','')}

        for p in doc.paragraphs:
            for key, val in replacements.items():
                _replace_in_paragraph(p, key, val)

        for p in list(doc.paragraphs):
            if '[[FUNDAMENTALES]]' in p.text:
                p.text = ""
                insert_after = p
                if cfg.get('fundamentales_data'):
                    for c in cfg['fundamentales_data']:
                        p_fund = _insert_paragraph_after(insert_after, f"{c['txt']} ({c['pts']} pts)")
                        p_fund.runs[0].bold = True
                        insert_after = p_fund
                        if not modo_solucion:
                            esp = c.get('espacio','Automático')
                            tbl = _insert_table_after(insert_after, rows=1, cols=1, doc=doc)
                            tbl.style = 'Table Grid'
                            lines = 3 if "5" in esp else 6 if "10" in esp else 10
                            for _ in range(lines): tbl.rows[0].cells[0].add_paragraph()
                            # Avanzar insert_after al párrafo siguiente a la tabla
                            # Creamos un párrafo separador tras la tabla
                            sep_p_el = tbl._tbl.makeelement('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p', {})
                            tbl._tbl.addnext(sep_p_el)
                            from docx.text.paragraph import Paragraph
                            insert_after = Paragraph(sep_p_el, doc.element.body)

            if '[[PREGUNTAS]]' in p.text:
                p.text = ""
                insert_after = p
                for preg in m['preguntas']:
                    p_enun = _insert_paragraph_after(insert_after)
                    r_num = p_enun.add_run(f"{preg['num']}. {preg['enunciado']}")
                    r_num.bold = True; r_num.font.name = 'Calibri'; r_num.font.size = Pt(11)
                    insert_after = p_enun
                    ops = preg['opciones_finales']; letra_corr = preg['letra_final']; idx_corr = {'A':0,'B':1,'C':2,'D':3}.get(letra_corr, 0)
                    for i, l in enumerate(['a','b','c','d']):
                        p_op = _insert_paragraph_after(insert_after, f"    {l}) {ops[i]}")
                        if modo_solucion and i == idx_corr:
                            if cfg.get('sol_negrita'): p_op.runs[0].bold = True
                            if cfg.get('sol_rojo'): p_op.runs[0].font.color.rgb = RGBColor(255, 0, 0)
                            if cfg.get('sol_ast'): p_op.add_run(" *")
                        insert_after = p_op

        doc.save(os.path.join(ruta, f"{nombre}_MOD{m['letra_version']}{sufijo}.docx"))

def cargar_examen_csv(path):
    # Detectar separador leyendo la primera línea
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        first_line = f.readline()
    sep = ';' if first_line.count(';') >= first_line.count(',') else ','
    df = pd.read_csv(path, sep=sep, encoding='utf-8-sig')
    if 'ID_BaseDatos' in df.columns:
        return df['ID_BaseDatos'].unique().tolist()
    elif 'ID' in df.columns:
        return df['ID'].unique().tolist()
    return []

def exportar_preguntas_json(ids, df, filepath):
    """Exporta una seleccion de preguntas a JSON portable."""
    import json
    pregs = df[df['ID_Pregunta'].isin(ids)].to_dict('records')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'preguntas': pregs}, f, ensure_ascii=False, indent=2, default=str)
    return len(pregs)

def importar_preguntas_json(filepath, bloque_destino, df_existing):
    """Importa preguntas desde JSON. Retorna (nuevas_list, duplicados_count)."""
    import json
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    pregs = data.get('preguntas', [])
    nuevas = []; dupes = 0
    for p in pregs:
        enun = p.get('enunciado','')
        is_dup, _ = check_for_similar_enunciado(enun, df_existing)
        if is_dup: dupes += 1; continue
        tema = p.get('Tema', '1')
        nid, _ = generar_siguiente_id(df_existing, bloque_destino, tema)
        p_new = dict(p)
        p_new['ID_Pregunta'] = nid; p_new['bloque'] = bloque_destino; p_new['usada'] = ''
        nuevas.append(p_new)
        # Update df_existing for next ID generation
        df_existing.loc[len(df_existing)] = p_new
    return nuevas, dupes
