"""
pages/4_Ayuda.py  –  Manual de uso y referencia de la aplicación.
"""
import streamlit as st
from app_utils import init_session_state, render_sidebar, APP_CSS

st.set_page_config(page_title="Ayuda · ExamGen UCM", page_icon="📖", layout="wide")
init_session_state()

st.markdown(APP_CSS, unsafe_allow_html=True)
st.markdown("""
<style>
.help-hero {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 60%, #1d4ed8 100%);
  border-radius: 16px; padding: 32px 40px; margin-bottom: 24px; color: white;
  box-shadow: 0 8px 28px rgba(29,78,216,.2);
}
.help-hero h2 { font-size: 1.8em; font-weight: 800; margin: 0 0 6px 0; letter-spacing:-.02em; }
.help-hero p  { opacity: .7; margin: 0; font-size: .95em; }

.help-card {
  background: white; border-radius: 14px; padding: 22px 26px;
  box-shadow: 0 2px 10px rgba(0,0,0,.07); border: 1px solid #f1f5f9;
  margin-bottom: 16px;
}
.help-card h4 { font-size: 1em; font-weight: 700; color: #0f172a; margin: 0 0 10px 0; }
.help-card p, .help-card li {
  font-size: 0.875em; color: #475569; line-height: 1.65; margin: 4px 0;
}
.help-card ul { padding-left: 18px; margin: 6px 0; }
.help-step {
  display: flex; gap: 14px; align-items: flex-start;
  padding: 10px 0; border-bottom: 1px solid #f8fafc;
}
.help-step:last-child { border-bottom: none; }
.step-num {
  min-width: 28px; height: 28px; border-radius: 50%;
  background: #1d4ed8; color: white;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.8em; font-weight: 700; flex-shrink: 0; margin-top: 1px;
}
.step-body { flex: 1; }
.step-title { font-weight: 600; color: #0f172a; font-size: .88em; }
.step-desc  { color: #64748b; font-size: .82em; margin-top: 2px; line-height: 1.5; }

.tip-box {
  background: #eff6ff; border-left: 3px solid #3b82f6;
  border-radius: 0 8px 8px 0; padding: 10px 14px; margin: 10px 0;
  font-size: 0.855em; color: #1e40af; line-height: 1.55;
}
.warn-box {
  background: #fffbeb; border-left: 3px solid #f59e0b;
  border-radius: 0 8px 8px 0; padding: 10px 14px; margin: 10px 0;
  font-size: 0.855em; color: #92400e; line-height: 1.55;
}
.kbd {
  background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px;
  padding: 2px 7px; font-family: monospace; font-size: .85em; color: #334155;
}
.section-label {
  font-size: 0.72em; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: #94a3b8; margin: 20px 0 10px 0; display: block;
}
</style>
""", unsafe_allow_html=True)

render_sidebar()

st.markdown("""
<div class="help-hero">
  <h2>📖 Manual de Uso</h2>
  <p>Generador de Exámenes · Unidad de Física Médica · UCM</p>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
tab_inicio, tab_gestor, tab_gen, tab_export, tab_latex, tab_faq = st.tabs([
    "🚀 Inicio rápido",
    "🗄️ Gestor DB",
    "🎲 Generador",
    "💾 Exportación",
    "📑 LaTeX / Word",
    "❓ FAQ",
])

# ── TAB 1: INICIO RÁPIDO ──────────────────────────────────────────────────────
with tab_inicio:
    col1, col2 = st.columns([3, 2], gap="large")

    with col1:
        st.markdown("<span class='section-label'>Flujo de trabajo básico</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
        <div class='help-step'>
          <div class='step-num'>1</div>
          <div class='step-body'>
            <div class='step-title'>Conecta la base de datos</div>
            <div class='step-desc'>
              En la <b>barra lateral</b> sube tu fichero Excel (<code>.xlsx</code>) o conecta tu
              Google Sheet con OAuth. La app detecta automáticamente los bloques (hojas del Excel).
            </div>
          </div>
        </div>
        <div class='help-step'>
          <div class='step-num'>2</div>
          <div class='step-body'>
            <div class='step-title'>Añade o importa preguntas</div>
            <div class='step-desc'>
              Desde <b>Gestor DB → Añadir</b> puedes crear preguntas una a una.
              Desde <b>Importar</b> puedes subir documentos Word o archivos Aiken (<code>.txt</code>)
              con muchas preguntas a la vez.
            </div>
          </div>
        </div>
        <div class='help-step'>
          <div class='step-num'>3</div>
          <div class='step-body'>
            <div class='step-title'>Configura nombres de bloques y temas</div>
            <div class='step-desc'>
              En <b>Configuración</b> asigna nombres descriptivos a tus bloques
              ("Bloque I → Radiología general") y temas ("Tema 5 → TAC"). Aparecerán en
              todos los filtros, estadísticas y tarjetas de la app.
            </div>
          </div>
        </div>
        <div class='help-step'>
          <div class='step-num'>4</div>
          <div class='step-body'>
            <div class='step-title'>Selecciona preguntas para el examen</div>
            <div class='step-desc'>
              En <b>Generador → Selección</b>: elige preguntas manualmente con filtros,
              o usa el <b>Auto-relleno</b> (🤖) para configurar cuántas por bloque/tema/dificultad.
              Puedes combinar ambos métodos.
            </div>
          </div>
        </div>
        <div class='help-step'>
          <div class='step-num'>5</div>
          <div class='step-body'>
            <div class='step-title'>Previsualiza en la pestaña Preview</div>
            <div class='step-desc'>
              Pulsa <b>🎲 Generar</b> para fijar la selección aleatoria y ver el examen completo.
              Repite hasta estar satisfecho. Las fórmulas LaTeX se renderizan con <b>∑ MathJax</b>.
            </div>
          </div>
        </div>
        <div class='help-step'>
          <div class='step-num'>6</div>
          <div class='step-body'>
            <div class='step-title'>Configura y exporta</div>
            <div class='step-desc'>
              En <b>Exportar</b>: rellena los metadatos del examen (asignatura, fecha, tiempo…),
              elige Word y/o LaTeX, y pulsa <b>💾 EXPORTAR EXAMEN</b>.
              Descarga el ZIP con todos los ficheros generados.
            </div>
          </div>
        </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("<span class='section-label'>Formato del Excel / Google Sheet</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
          <h4>Estructura esperada</h4>
          <p>Cada <b>hoja</b> del Excel corresponde a un <b>bloque</b> (ej. "Bloque I", "Bloque II").</p>
          <p>Las columnas requeridas en cada hoja son:</p>
          <ul>
            <li><code>ID_Pregunta</code> — identificador único</li>
            <li><code>Tema</code> — número de tema (1–40)</li>
            <li><code>Enunciado</code> — texto de la pregunta</li>
            <li><code>OpcionA</code>, <code>OpcionB</code>, <code>OpcionC</code>, <code>OpcionD</code></li>
            <li><code>Correcta</code> — letra de la respuesta correcta (A/B/C/D)</li>
            <li><code>Dificultad</code> — Facil / Media / Dificil</li>
            <li><code>Usada</code> — fecha de último uso (o vacío)</li>
          </ul>
          <p>La columna <code>Notas</code> es opcional.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class='tip-box'>
          💡 <b>Si partes de cero</b>, conecta tu Google Sheet o sube un Excel vacío (con las hojas creadas).
          La app puede crear bloques desde el Gestor si las hojas están vacías.
        </div>
        <div class='warn-box'>
          ⚠️ <b>Formato Aiken</b>: cada pregunta empieza con el enunciado, seguido de las opciones
          en líneas separadas (A) … (D) … y una línea <code>ANSWER: X</code>.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<span class='section-label'>Modos de conexión</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
          <h4>📂 Excel local</h4>
          <p>Sube el fichero <code>.xlsx</code> con el uploader del sidebar. Los cambios se guardan
          en memoria y puedes descargar el Excel actualizado con el botón ⬇️ del sidebar.</p>
          <h4 style='margin-top:12px'>☁️ Google Sheets</h4>
          <p>Conecta vía OAuth Google con el botón del sidebar. Necesitas tener configuradas
          las credenciales OAuth en Streamlit Secrets. Los cambios se guardan en memoria
          (no se escriben de vuelta al GSheet automáticamente en esta versión).</p>
        </div>
        """, unsafe_allow_html=True)

# ── TAB 2: GESTOR DB ──────────────────────────────────────────────────────────
with tab_gestor:
    g1, g2 = st.columns(2, gap="large")

    with g1:
        st.markdown("<span class='section-label'>Pestañas del Gestor</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
          <h4>➕ Añadir</h4>
          <p>Crea preguntas individualmente. Selecciona bloque, tema y dificultad,
          escribe el enunciado y las 4 opciones, elige la correcta y guarda.</p>
          <p>La app <b>detecta duplicados</b> por similitud de texto antes de guardar.</p>
          <p>Si el bloque no existe aún, selecciona <em>"➕ Nuevo bloque..."</em> y escribe su nombre.</p>
        </div>
        <div class='help-card'>
          <h4>📥 Importar</h4>
          <p>Sube un documento <b>Word (.docx)</b>, <b>PDF</b> o archivo <b>Aiken (.txt)</b>
          con múltiples preguntas. La app las extrae y las muestra en una lista de revisión
          antes de confirmar la importación.</p>
          <p>Puedes editar cada pregunta extraída antes de importarla definitivamente.</p>
          <p>Indica el <b>bloque destino</b>, tema y dificultad por defecto (se puede cambiar por pregunta).</p>
        </div>
        <div class='help-card'>
          <h4>✏️ Gestionar</h4>
          <p>Lista todas las preguntas con filtros por bloque, tema, dificultad y uso.
          Haz clic en el icono de edición (✏️) para abrir el diálogo de edición completa.</p>
          <p><b>Operaciones masivas</b>: selecciona varias preguntas y cambia su tema,
          dificultad, márcalas como usadas o elimínalas de una vez.</p>
        </div>
        """, unsafe_allow_html=True)

    with g2:
        st.markdown("""
        <div class='help-card'>
          <h4>📊 Estadísticas</h4>
          <p>Vista global y por bloque de:</p>
          <ul>
            <li>Total de preguntas, por dificultad</li>
            <li>Preguntas usadas vs sin usar</li>
            <li>Porcentaje de cobertura</li>
            <li>Detalle por tema dentro de cada bloque</li>
          </ul>
          <p>Usa el selector de vista para explorar bloque por bloque.</p>
        </div>
        <div class='help-card'>
          <h4>🔄 JSON Export / Import</h4>
          <p>En la pestaña Gestionar encontrarás opciones para:</p>
          <ul>
            <li>Exportar preguntas filtradas a JSON (para compartir o backup)</li>
            <li>Importar preguntas desde un JSON generado por esta misma app</li>
          </ul>
          <p>Útil para mover preguntas entre bases de datos o hacer copias de seguridad.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class='tip-box'>
          💡 <b>IDs de pregunta</b>: se generan automáticamente con el formato
          <code>BloqueI_T05_01</code> (bloque + tema + número secuencial).
          No los edites manualmente.
        </div>
        """, unsafe_allow_html=True)

# ── TAB 3: GENERADOR ─────────────────────────────────────────────────────────
with tab_gen:
    gen1, gen2 = st.columns(2, gap="large")

    with gen1:
        st.markdown("<span class='section-label'>Pestaña Selección</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
          <h4>Selección manual</h4>
          <p>Usa los filtros (bloque, tema, dificultad, uso) para encontrar preguntas.
          Haz clic en cualquier pregunta para verla completa en el panel de preview izquierdo
          y añádela o quítala del examen con los botones.</p>
          <p>El panel derecho muestra las preguntas fijas seleccionadas.
          Puedes reordenarlas con ⬆️ ⬇️ o eliminarlas con 🗑️.</p>
        </div>
        <div class='help-card'>
          <h4>🤖 Auto-relleno</h4>
          <p>Pulsa el botón <b>🤖 Auto-relleno</b> para abrir el configurador.
          Por cada bloque puedes especificar cuántas preguntas quieres de cada dificultad
          (de cualquier tema o de un tema específico).</p>
          <p>La receta se guarda hasta que la limpies con ✖. Al generar en Preview,
          se seleccionan aleatoriamente.</p>
          <p>Puedes combinar preguntas fijas manuales + receta automática.</p>
        </div>
        """, unsafe_allow_html=True)

    with gen2:
        st.markdown("<span class='section-label'>Pestaña Preview</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
          <h4>🎲 Generar</h4>
          <p>Pulsa <b>🎲 Generar</b> para resolver la receta automática (selección aleatoria)
          y mostrar el examen completo. <b>Esto fija las preguntas para la exportación.</b></p>
          <p>Repite las veces que quieras hasta estar satisfecho con la selección.
          Solo se exportará el último Preview generado.</p>
        </div>
        <div class='help-card'>
          <h4>∑ MathJax</h4>
          <p>Pulsa <b>∑ MathJax</b> para renderizar las fórmulas LaTeX en el preview.
          Las fórmulas inline van entre <code>$...$</code> y las en bloque entre
          <code>$$...$$</code> o entornos <code>\\begin&#123;equation&#125;</code>.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class='tip-box'>
          💡 El flujo recomendado es: <b>Selección → Preview (Generar) → Exportar</b>.
          El botón Exportar usa exactamente las preguntas que se mostraron en el último Preview.
          Si no has generado Preview y solo tienes receta automática, el botón Exportar
          aparece deshabilitado hasta que lo hagas.
        </div>
        """, unsafe_allow_html=True)

# ── TAB 4: EXPORTACIÓN ───────────────────────────────────────────────────────
with tab_export:
    exp1, exp2 = st.columns(2, gap="large")

    with exp1:
        st.markdown("<span class='section-label'>Configuración del examen</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
          <h4>Metadatos</h4>
          <ul>
            <li><b>Institución</b>: aparece en la cabecera (ej. UCM)</li>
            <li><b>Asignatura</b>: nombre del examen (ej. FÍSICA MÉDICA)</li>
            <li><b>Tipo de examen</b>: ej. EXAMEN FINAL, PARCIAL...</li>
            <li><b>Fecha</b> y <b>Tiempo</b> permitido</li>
            <li><b>Campos del alumno</b>: nombre, DNI, grupo, firma</li>
          </ul>
        </div>
        <div class='help-card'>
          <h4>Opciones de generación</h4>
          <ul>
            <li><b>Nº Modelos</b>: genera A, B, C, D simultáneamente (distintos órdenes)</li>
            <li><b>Orden preguntas</b>: aleatorio por bloques, global, manual o por ID</li>
            <li><b>Barajar respuestas</b>: cambia el orden A/B/C/D entre modelos</li>
            <li><b>Disposición opciones</b>: 1 o 2 columnas</li>
          </ul>
        </div>
        """, unsafe_allow_html=True)

    with exp2:
        st.markdown("""
        <div class='help-card'>
          <h4>Marcado de soluciones</h4>
          <p>La app genera siempre <b>dos versiones</b>: el examen limpio y la versión con
          soluciones marcadas. Puedes marcar la correcta con negrita, color rojo y/o asterisco (*).</p>
        </div>
        <div class='help-card'>
          <h4>Hoja de respuestas</h4>
          <p>Activa la <b>hoja de respuestas OMR/tabla</b> en el expander correspondiente.
          Se genera como página adicional al final del examen, con burbujas para rellenar
          (estilo OMR) o como tabla.</p>
        </div>
        <div class='help-card'>
          <h4>Versión adaptada</h4>
          <p>Genera adicionalmente una versión con mayor tamaño de letra, más interlineado
          y más espacio en los huecos de desarrollo (para alumnos con necesidades especiales).</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class='tip-box'>
          💡 <b>Presets</b>: guarda tu configuración actual (asignatura, opciones, estilo…)
          con un nombre y recupérala en futuras sesiones con un clic.
        </div>
        """, unsafe_allow_html=True)

# ── TAB 5: LATEX / WORD ──────────────────────────────────────────────────────
with tab_latex:
    lat1, lat2 = st.columns(2, gap="large")

    with lat1:
        st.markdown("<span class='section-label'>LaTeX</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
          <h4>Archivo generado</h4>
          <p>Se genera un <code>.tex</code> por cada modelo (MOD_A.tex, MOD_A_SOL.tex, …)
          y el fichero de estilo <code>estilo_examen_moderno_v2.sty</code>, todo en un ZIP.</p>
          <p>Compilar con <b>pdfLaTeX</b> (dos pasadas) o <b>LuaLaTeX</b>.
          En <a href='https://www.overleaf.com' target='_blank'>Overleaf</a>:
          sube el ZIP, establece el compilador a <em>pdfLaTeX</em> y compila.</p>
        </div>
        <div class='help-card'>
          <h4>Fórmulas matemáticas</h4>
          <p>Usa sintaxis LaTeX estándar en los enunciados y opciones:</p>
          <ul>
            <li>Inline: <code>$E = mc^2$</code></li>
            <li>Bloque: <code>$$\\int_0^\\infty f(x)\\,dx$$</code></li>
            <li>Entornos: <code>\\begin&#123;equation&#125; ... \\end&#123;equation&#125;</code></li>
          </ul>
          <p>El Preview MathJax en la app las renderiza para que puedas revisar antes de exportar.</p>
        </div>
        """, unsafe_allow_html=True)

    with lat2:
        st.markdown("<span class='section-label'>Word</span>", unsafe_allow_html=True)
        st.markdown("""
        <div class='help-card'>
          <h4>Archivo generado</h4>
          <p>Se genera un <code>.docx</code> por modelo más su versión con soluciones.
          Usa la plantilla por defecto o sube tu propia plantilla Word personalizada
          en el expander <em>Plantillas</em>.</p>
        </div>
        <div class='help-card'>
          <h4>Estilos visuales (LaTeX)</h4>
          <p>En el expander <em>🎨 Estilo visual</em> del Generador puedes configurar:</p>
          <ul>
            <li><b>Esquema de color</b>: Azul, Verde, Granate, Gris</li>
            <li><b>Tipografía</b>: Computer Modern, Palatino, Helvetica, Times</li>
            <li><b>Estilo de numeración</b>: Cuadrado, Círculo, Número, Sin estilo</li>
            <li><b>Tamaño de letra y modo compacto</b></li>
          </ul>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class='warn-box'>
          ⚠️ Las fórmulas LaTeX <b>no se renderizan en Word</b>: aparecen como texto literal.
          Para exámenes con muchas fórmulas se recomienda usar la exportación LaTeX.
        </div>
        """, unsafe_allow_html=True)

# ── TAB 6: FAQ ────────────────────────────────────────────────────────────────
with tab_faq:
    faqs = [
        ("¿Por qué no se guardan los cambios en Google Sheets?",
         "La versión actual guarda los cambios en memoria durante la sesión. "
         "Usa el botón ⬇️ <b>Descargar</b> del sidebar para obtener el Excel actualizado "
         "y súbelo de nuevo o impórtalo a tu Google Sheet manualmente. "
         "La escritura directa a GSheets está planificada para una versión futura."),
        ("¿Qué pasa si cierro el navegador o expira la sesión?",
         "Streamlit Community Cloud mantiene la sesión activa mientras el navegador esté abierto. "
         "Si la sesión expira, vuelve a conectar la base de datos desde el sidebar. "
         "Las preguntas están en tu Excel/Google Sheet; solo se pierde la sesión de trabajo actual."),
        ("¿Puedo tener más de un Google Sheet conectado?",
         "Solo uno por sesión. Para cambiar de base de datos, desconecta la actual "
         "con el botón 🚪 Salir del sidebar y conecta la nueva."),
        ("El círculo/cuadrado del estilo de numeración no se ve bien en el PDF.",
         "Asegúrate de compilar el .tex con <b>pdfLaTeX</b> y de que el .sty esté en la misma "
         "carpeta que el .tex. En Overleaf, sube ambos ficheros del ZIP."),
        ("¿Cómo añado imágenes a las preguntas?",
         "Actualmente la app no gestiona imágenes en los enunciados. Para insertar imágenes "
         "deberás editar el .tex generado manualmente con <code>\\includegraphics</code>."),
        ("¿Puedo cambiar el orden de las preguntas después de generar?",
         "Sí: en la pestaña Selección usa los botones ⬆️ ⬇️ del panel derecho para reordenar "
         "las preguntas fijas. Después vuelve a Preview y regenera."),
        ("¿Qué significa 'cobertura' en las estadísticas?",
         "Porcentaje de preguntas del banco que han sido usadas al menos una vez en un examen. "
         "Una pregunta se marca como usada automáticamente al exportar."),
        ("¿Cómo configuro nombres descriptivos para bloques y temas?",
         "Ve a <b>Configuración</b> (página 3). Ahí puedes asignar nombres como "
         "'Bloque I → Radiología General' o 'Tema 5 → Tomografía Computarizada'. "
         "Estos nombres se guardan en la propia base de datos y aparecen en toda la app."),
    ]

    for q, a in faqs:
        with st.expander(f"❓ {q}"):
            st.markdown(f"<div style='font-size:.875em;color:#475569;line-height:1.65'>{a}</div>",
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div class='help-card'>
      <h4>¿Necesitas más ayuda?</h4>
      <p>Reporta problemas o sugiere mejoras en el repositorio del proyecto.</p>
    </div>
    """, unsafe_allow_html=True)
