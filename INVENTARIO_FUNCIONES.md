# Inventario de funciones — Generador de Exámenes

Lista de comprobación para el rediseño visual (rama `rediseno-visual`).
Tras cada fase se recorre entera: cada punto debe seguir funcionando igual.

Leyenda: **[V]** = el rediseño cambia su aspecto · **[C]** = cambia su comportamiento (acordado) · sin marca = no debería notarse ningún cambio salvo el estilo general.

---

## 0. Global (todas las páginas)

### Barra lateral · conexión a la base de datos (`app_utils.py`)
- [ ] Subir Excel (`file_uploader`) y conectar automáticamente; no reconecta en cada recarga
- [ ] «Ruta local directa» (expander) + botón **Conectar**
- [ ] Botón **Recargar** (cloud: re-procesa en memoria · local: relee del disco)
- [ ] Botón **Descargar Excel** siempre disponible cuando hay conexión
- [ ] Google Sheets (solo si hay `GOOGLE_OAUTH` en secrets):
  - [ ] **Iniciar sesión con Google** → redirección y vuelta automática (callback `?code=`)
  - [ ] Email del usuario conectado
  - [ ] URL de la hoja + **Cargar**
  - [ ] **Salir** (borra token y datos de sesión)
  - [ ] Sincronización automática de cada bloque modificado con Google Sheets
- [ ] Guardado en Excel local (no-op en cloud)
- [ ] **Nuevo:** botones de estilo Bitácora / Clásico al pie de la barra lateral

### Navegación **[C]**
- [ ] Las 5 páginas accesibles: Inicio · Gestor DB · Generador · Configuración · Ayuda (pasan a la barra superior)
- [ ] Cabecera de página (título + subtítulo) **[V]**

### Ventana compartida «Editar pregunta» (`app_utils.py`, usada desde Gestor y Generador)
- [ ] Bloque, Tema, Dificultad, Respuesta correcta
- [ ] Pregunta ya usada + Fecha de uso
- [ ] Notas, Etiqueta, Objetivo docente
- [ ] Constantes / Datos (expander)
- [ ] Enunciado + Opciones A–D
- [ ] **Guardar cambios** / **Cancelar**

---

## 1. Inicio (`streamlit_app.py`)
- [ ] 5 indicadores: Total preguntas · Usadas · Sin usar · Cobertura · Seleccionadas ahora **[V]**
- [ ] Aviso «Base de datos no conectada» cuando no hay Excel **[V]**
- [ ] 4 tarjetas de módulos con botones: Abrir Gestor DB · Abrir Generador · Abrir Configuración · Ver Manual **[V]**
- [ ] Últimos exámenes generados (desde historial) **[V]**
- [ ] Inicio rápido **[V]**
- [ ] Pie de página

---

## 2. Gestor DB (`pages/1_Gestor_DB.py`) — 7 pestañas

### 2.1 Gestionar
- [ ] Filtros: bloque, tema, dificultad, **Buscar**, «Todos los bloques», «Sin solución», botón reiniciar filtros
- [ ] Tabla de preguntas filtradas + selección de fila **[V]**
- [ ] Panel derecho con la pregunta seleccionada (tarjeta) **[V]**
  - [ ] Botones Editar · Solución · Duplicar · Eliminar (con confirmación «Sí, eliminar» / Cancelar)
  - [ ] Ver solución (expander) + **Renderizar LaTeX**
- [ ] Operaciones masivas sobre las filtradas (expander):
  - [ ] Cambiar Tema / Dificultad → «Aplicar a N preguntas»
  - [ ] Buscar y reemplazar → «Reemplazar en N preguntas»
- [ ] Exportar / Importar JSON entre bases de datos (Exportar a JSON, Descargar JSON, subir JSON, Importar JSON)

### 2.2 Soluciones (editor por lotes)
- [ ] Métricas globales de soluciones **[V]**
- [ ] Filtro por bloque + «Mostrar» (radio)
- [ ] Plantillas de inicio: Razonamiento · Cálculo · Concepto
- [ ] Navegación: ← Anterior · Saltar · Guardar y siguiente →

### 2.3 Añadir
- [ ] Tema, Dificultad, Respuesta correcta, Enunciado, Opciones A–D
- [ ] Crear bloque nuevo (nombre)
- [ ] **Guardar pregunta**

### 2.4 Importar
- [ ] Tema, Dificultad, Formato: Word (.docx) · PDF (.pdf) · Aiken (.txt)
- [ ] Subir archivo + **Previsualizar**
- [ ] Lista de staging: casillas, Seleccionar / Deseleccionar todas, editar cada una (ventana «Editar pregunta importada»)
- [ ] **Importar seleccionadas (N)** · **Limpiar**

### 2.5 Estadísticas
- [ ] Selector de vista: global / por bloque
- [ ] 8 gráficos Plotly (distribución, cobertura, dificultad, soluciones, por tema, uso…) **[V]** (colores según el estilo)
- [ ] Desglose por tema con barras **[V]**

### 2.6 Constantes físicas
- [ ] Nueva constante (expander): nombre, ID auto, categoría (o nueva), símbolo, valor, unidades LaTeX → **Añadir constante**
- [ ] Lista agrupada por categoría (expanders) con editar (formulario Guardar/Cancelar) y eliminar
- [ ] Ventana «Seleccionar constantes / datos» (Aplicar selección / Cancelar)

### 2.7 Objetivos docentes
- [ ] Nuevo objetivo (expander): nombre corto, código auto, descripción, bloque y tema opcionales → **Añadir objetivo**
- [ ] Lista con editar (formulario) y eliminar

### Ventana «Solución desarrollada»
- [ ] Encabezado con enunciado y metadatos
- [ ] Plantillas Razonamiento · Cálculo · Concepto
- [ ] Editor + **Renderizar LaTeX** / Cerrar render
- [ ] **Guardar solución** / Cerrar

---

## 3. Generador (`pages/2_Generador.py`) — 5 pestañas

### 3.1 Selección **[C]**
- [ ] Objetivo (nº de preguntas)
- [ ] **Auto-relleno** → ventana de receta por bloque / tema / objetivo con Fácil · Media · Difícil (disponibles), total configurado, **Limpiar receta** / **Guardar receta**
- [ ] Resumen de receta activa + quitar receta (✖) **[V]**
- [ ] Filtros: Bloque, Tema, Dificultad, Uso (nunca / usada / >6 meses / >12 meses), Buscar (enunciado y opciones), Etiqueta, Objetivo **[V]** (pasan a píldoras + «Más filtros»)
- [ ] Tabla de disponibles + **Añadir todas** **[V]**
- [ ] Vista previa de la pregunta **[C]**: por defecto en ventana; opción en Configuración para el layout de 3 columnas actual
  - [ ] Tarjeta con solución marcada, Notas, distintivo «Solución disponible»
  - [ ] Añadir / Quitar · Sol. · ∑ LaTeX · Editar · Cerrar LaTeX / Cerrar solución
  - [ ] El render LaTeX persiste tras editar
- [ ] Fijas: lista ordenada con ⬆️ ⬇️ 🗑️ y **Limpiar todo** **[V]** (en modo ventana, botón 👁 para ver la fija seleccionada)
- [ ] Desde la ventana: Añadir/Quitar cierra la ventana; Editar abre el editor; Sol. y ∑ LaTeX se muestran dentro
- [ ] Estadísticas de la selección en tiempo real: gráfico de dificultad, bloques cubiertos, métricas (seleccionadas vs objetivo, % del banco, F/M/D) **[V]**

### 3.2 Desarrollo
- [ ] **Añadir pregunta de desarrollo**
- [ ] Exportar / Importar JSON de preguntas de desarrollo
- [ ] Cada pregunta (expander) con 4 subpestañas:
  - [ ] Enunciado: texto, guía rápida de escritura, snippets, imagen (subir / Quitar imagen)
  - [ ] Apartados: añadir / quitar, previsualizar apartado; ventana «Editar subapartados» (numeración, añadir / eliminar, Guardar / Cancelar)
  - [ ] Rúbrica y datos: criterios (añadir / quitar), constantes, Renderizar
  - [ ] Vista previa
- [ ] Solución modelo: Editar / Vista previa
- [ ] Eliminar pregunta

### 3.3 Preview
- [ ] Banner de modo recuperación + **Desbloquear**
- [ ] Mostrar soluciones · Orden · Semilla (0 = aleatoria)
- [ ] **Generar** (fijas en orden + receta aleatoria en cada generación)
- [ ] **MathJax**
- [ ] Avisos de la última generación (expanders) **[V]**

### 3.4 Exportar
- [ ] Configuración del examen: institución, asignatura, tipo, fecha, tiempo, nombre de archivo, campos del alumno; **Rellenar desde Configuración**
- [ ] Opciones de generación: nº de modelos, orden, barajar respuestas
- [ ] Formatos y marcado: Word / LaTeX, negrita, color, asterisco, estilo de solución, marca de agua, mostrar bloque / tema / dificultad
- [ ] Instrucciones y cabeceras (generales, títulos y cabeceras de las secciones)
- [ ] Estilo visual LaTeX: esquema de color, tipografía, tamaño, espaciado, márgenes, cabecera, recuadro del alumno, disposición de opciones, numeración, encabezado / pie
- [ ] Hoja de respuestas
- [ ] Solucionario (apéndice): título, estilo
- [ ] Guía de corrección (rúbrica): Word / LaTeX, título
- [ ] Formulario / hoja de fórmulas: subir PDF, Quitar formulario
- [ ] Caja de calificación
- [ ] Puntos y penalización (incl. valor personalizado)
- [ ] Versión adaptada: tamaño de letra, interlineado, cajas, identificador
- [ ] Anclaje de opciones + frases extra
- [ ] Plantillas Word / LaTeX / Logo (subir / quitar)
- [ ] Presets: Cargar · Guardar · Eliminar
- [ ] Panel derecho: resumen **[V]**, **Vista previa del examen** (ventana Modelo A: Examen / Solucionario, MathJax, respuesta inline), **EXPORTAR EXAMEN** → ventana de confirmación (Exportar / Cancelar)
- [ ] Descargas: Exámenes y Soluciones (Word y LaTeX), Adaptada (Word y LaTeX), Clave, Metadatos (CSV `;`)
- [ ] Marcar como utilizadas · Deshacer marcado · Nueva exportación
- [ ] Compilar PDF: modelo + versión → ventana «Compilando PDF…» (descarga, log completo) → **Ver PDF** (ventana con descarga)
- [ ] Ver fuente .tex (depuración)

### 3.5 Historial
- [ ] Lista de exámenes (expanders) **[V]**
- [ ] Recargar preguntas · Restaurar configuración · Ambos
- [ ] Recuperar desde `_METADATA.csv` → **Cargar desde CSV**

---

## 4. Configuración (`pages/3_Configuracion.py`) — 5 pestañas (+1 nueva)
- [ ] General: datos del examen + vista previa del encabezado → **Guardar datos generales**
- [ ] Bloques: nombres → **Guardar nombres de bloques** (sincroniza Google Sheets)
- [ ] Temas: filtro por bloque, «solo sin nombre», recuento por tema → **Guardar nombres de temas**
- [ ] Objetivos → **Guardar objetivos**
- [ ] Copia de configuración: exportar JSON (descarga) / importar JSON
- [ ] **Nueva:** Apariencia — estilo (Bitácora · Clásico; claro/oscuro desde ⋮ → Settings) y vista previa en ventana / 3 columnas, con «Guardar como predeterminado»

---

## 5. Ayuda (`pages/4_Ayuda.py`)
- [ ] 6 pestañas: Inicio rápido · Gestor DB · Generador · Exportación · LaTeX/Word · FAQ (expanders) **[V]**

---

## Fuera del alcance (no se toca)
- `examen_lib_latex.py`: parseo, exportación LaTeX/Word/CSV, compilación PDF
- Formato del Excel y de los CSV (separador `;`)
- Presets e historial (`presets_examen.json`, `historial_examenes.json`)
- Los documentos exportados: el estilo de la app no cambia el aspecto de los exámenes
