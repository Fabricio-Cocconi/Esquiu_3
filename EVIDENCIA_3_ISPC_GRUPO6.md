# INSTITUTO SUPERIOR POLITÉCNICO CÓRDOBA (ISPC)
## TECNICATURA SUPERIOR EN CIENCIA DE DATOS E INTELIGENCIA ARTIFICIAL
## TECNICATURA SUPERIOR EN DESARROLLO DE SOFTWARE

---

# INFORME TÉCNICO DE INTEGRACIÓN Y VALIDACIÓN (EVIDENCIA DE APRENDIZAJE Nº 3)
## PROYECTO: "ESQUIU3" - SISTEMA CENTRALIZADO DE GESTIÓN DE CANCHAS Y ANALÍTICA PREDICTIVA DE NO-SHOW (MVP BETA)

**CICLO LECTIVO:** 2026  
**MATERIAS INTEGRADAS:** 
- *Testeo de Software*
- *Práctica Profesionalizante I*

**DOCENTES TITULARES:**
- Prof. David Cabrera (Testeo de Software)
- Prof. Carolina Ahumada (Testeo de Software)
- Prof. Daniela Accietto (Práctica Profesionalizante I)
- Prof. Florencia García (Práctica Profesionalizante I)

**EQUIPO DE TRABAJO - GRUPO Nº 6:**
- Yanina Roldan
- Gabriel Yoles Trucco
- Fabricio Cocconi
- Franco Gonzalo Arce

---

> **PAUTAS FORMALES DE PRESENTACIÓN (ISPC):**  
> Formato base: Fuente Arial 12 pt, Títulos principales en Arial 16 pt negrita, Subtítulos en Arial 14 pt negrita, Interlineado de 1.5 líneas, Márgenes estándar de 2.5 cm (superior, inferior, izquierdo y derecho). Alineación justificada. Tablas con encabezados resaltados y bordes uniformes.

---

## RESUMEN EJECUTIVO Y CONTINUIDAD DEL PROYECTO

El presente documento constituye la entrega formal de la **Evidencia de Aprendizaje Nº 3** correspondiente al ciclo 2026. Este hito consolida el paso decisivo desde el análisis exploratorio preliminar (Evidencia 1) y el modelo baseline experimental (Evidencia 2) hacia una **solución tecnológica operativa de punta a punta (MVP Beta)** para el complejo deportivo **"Esquiu3"**, el cual opera 13 canchas deportivas (Fútbol 5, Fútbol 7, Fútbol 11 y Pádel) en la ciudad de Córdoba.

### Evolución técnica respecto a la Evidencia 2:
1. **Del Cuaderno Manuscrito al Dato Estructurado:** Se procesó y depuró la digitalización de las planillas históricas del período 2024-2025 (`reservas_esquiu3.csv`, 100 registros originales), remediando fallas de digitación humana (fechas anómalas con año `1900` y registros con monto ilegible).
2. **Superación del Modelo Baseline:** El modelo baseline de la Evidencia 2 (Random Forest con 78% de Accuracy y 72% de Recall en la clase minoritaria `No-Show`) presentaba una dependencia crítica de horarios nocturnos. Mediante la incorporación sistemática de variables meteorológicas (`Temperatura_C`, `Humedad_Pct`, `Condicion_Climatica`) y el cálculo dinámico del `Historial_Cumplimiento_Cliente`, el nuevo modelo entrenado y validado mediante validación cruzada repetida (5x5) alcanzó un **Recall medio de 91.07%** (100% en hold-out de prueba) y una **Accuracy de 94.68%**, superando ampliamente el piso exigido del 72%.
3. **Arquitectura Cliente-Servidor Desacoplada:** Se reemplazó el flujo manual de notebooks por un backend estructurado con **FastAPI**, persistencia en memoria transaccional concurrente con sembrado histórico, sanitización estricta de entradas y una interfaz web interactiva con semáforo predictivo de riesgo, grilla visual de 13 canchas con navegación temporal y panel de auditoría de datos.
4. **Validación Exhaustiva:** Se ejecutó una suite automatizada de pruebas con **PyTest** (16 casos cubiertos al 100%), abarcando pruebas funcionales, no funcionales de seguridad (RBAC y prevención XSS) y de usabilidad/rendimiento (latencia < 300 ms).

---

# PARTE A: TESTEO DE SOFTWARE

## 1. ALCANCE DE LAS PRUEBAS

El alcance del testing para la versión Beta del MVP de Esquiu3 delimita con precisión los componentes bajo prueba y los límites operativos de la iteración actual.

### 1.1 Elementos Dentro del Alcance (In-Scope)
- **Pipeline de Limpieza y Preprocesamiento ML (`train_model.py`):** Detección y exclusión de fechas incompatibles (año `1900`), imputación estadística por mediana de precios de turnos no cobrados/ilegibles, cálculo sin fuga de datos (*data leakage*) del historial de clientes y serialización del modelo en `modelo_esquiu3.joblib`.
- **Lógica Funcional del Backend (`main.py`):**
  - Endpoint de inferencia predictiva `POST /api/v1/reservas/predict`.
  - Endpoint de registro transaccional `POST /api/v1/reservas`, incluyendo detección y bloqueo atómico de solapamientos (HTTP 409).
  - Consulta de ocupación de las 13 canchas `GET /api/v1/canchas/ocupacion`.
  - Mecanismo de fallback ante indisponibilidad del servicio meteorológico simulado (`GET /api/v1/clima/pronostico`).
- **Pruebas No Funcionales Elegidas:**
  - **Seguridad (Control de Acceso y Sanitización):** Validación de control de acceso basado en roles (RBAC simulado mediante encabezado `X-Role`) y neutralización de ataques de Cross-Site Scripting (XSS) en cadenas de texto libre.
  - **Usabilidad y Rendimiento (Consistencia Visual y Latencia):** Coherencia semántica del semáforo tricolor de riesgo y latencia de inferencia menor a 300 milisegundos en peticiones HTTP.
- **Interfaz de Usuario Web (`index.html`, `app.js`, `styles.css`):** Formulario con actualización en tiempo real del clima, grilla con scroll bidireccional y panel de auditoría con control de privilegios.

### 1.2 Elementos Fuera del Alcance (Out-of-Scope)
- Integración real con pasarelas bancarias o procesadores de pago (Mercado Pago, transferencias bancarias directas). El cobro de seña se gestiona como registro de estado operativo interno.
- Conexión con la API oficial de WhatsApp Business (Meta Cloud API). La emisión de notificaciones de confirmación se implementa como pasarela simulada con trazabilidad en log.
- Autenticación federada mediante OAuth2/JWT con proveedores externos (Google/Auth0). Para el alcance de este MVP Beta se utiliza simulación de perfiles en cabecera HTTP.

### 1.3 Justificación de las Pruebas No Funcionales Seleccionadas
1. **Seguridad (RBAC y XSS):** En un negocio deportivo donde convergen múltiples roles (encargados de turno, recepcionistas, administradores), la información comercial (métricas de facturación y cuaderno de quejas) debe estar resguardada frente a accesos no autorizados. Asimismo, los campos abiertos para anotaciones del cliente representan un vector clásico de inyección; sanearlos garantiza la integridad tanto de la base de datos como de la consola de visualización.
2. **Usabilidad y Rendimiento:** La recepción de un complejo deportivo atiende llamadas telefónicas y clientes en mostrador simultáneamente. La respuesta del sistema predictivo debe ser inmediata (< 300 ms) para no demorar la atención, y el semáforo debe comunicar sin ambigüedades la conducta a seguir (solicitar seña y enviar WhatsApp) mediante código de color, texto explícito y porcentaje.

---

## 2. TAREAS Y SUBTAREAS DEL PLAN DE PRUEBAS

El ciclo de pruebas se estructuró siguiendo el estándar IEEE 829 y buenas prácticas de Aseguramiento de la Calidad (QA):

```
+-----------------------------------------------------------------------------------+
|                           PLAN DE PRUEBAS - ESQUIU3                               |
+-----------------------------------------------------------------------------------+
| 1. PLANIFICACIÓN       | - Definición de alcance funcional y no funcional         |
|                        | - Análisis de riesgos y estimación de tiempos            |
|                        | - Asignación de roles en el equipo de QA                 |
+------------------------+----------------------------------------------------------+
| 2. DISEÑO              | - Identificación de condiciones de prueba (Equivalencia) |
|                        | - Especificación de casos funcionales (CF-01 a CF-04)    |
|                        | - Especificación de casos de seguridad (CS-01, CS-02)    |
|                        | - Especificación de casos de usabilidad/rendimiento      |
|                        | - Redacción de fixtures y aislamiento de tests en PyTest |
+------------------------+----------------------------------------------------------+
| 3. EJECUCIÓN           | - Ejecución automatizada con pytest y TestClient FastAPI |
|                        | - Medición de latencia real con servidor HTTP uvicorn    |
|                        | - Verificación interactiva de la interfaz web            |
|                        | - Registro sistemático de evidencias en JSON             |
+------------------------+----------------------------------------------------------+
| 4. CIERRE              | - Consolidación del Reporte de Defectos (Bug Tracking)   |
|                        | - Evaluación de criterios de aceptación (100% tests OK)  |
|                        | - Emisión del Informe Final de Calidad (Evidencia 3)     |
+------------------------+----------------------------------------------------------+
```

---

## 3. SUPUESTOS DE EJECUCIÓN

1. **Aislamiento de Estado:** Cada prueba unitaria o de integración se ejecuta con el almacén de reservas reinicializado a partir del sembrado del cuaderno digitalizado limpio, evitando contaminación cruzada entre pruebas (*fixture* `estado_limpio`).
2. **Disponibilidad del Entorno de Ejecución:** El entorno cuenta con Python 3.11, dependencias científicas (`pandas`, `numpy`, `scikit-learn`, `joblib`), framework de API (`fastapi`, `uvicorn`, `httpx`, `pydantic`) y suite de testing (`pytest`).
3. **Representatividad del Dataset:** Se asume que los 98 turnos depurados reflejan la dinámica representativa del complejo y que el valor por defecto de cumplimiento para clientes sin historial previo (mediana histórica del 75-100%) no distorsiona el funcionamiento predictivo.

---

## 4. MATRIZ COMPLETA DE CASOS DE PRUEBA

La siguiente matriz documenta la ejecución completa de los casos de prueba diseñados para la entrega:

| ID | Caso de Prueba | Tipo | Precondición | Datos de Entrada | Pasos de Ejecución | Resultado Esperado | Resultado Obtenido | Estado / Evidencia |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CF-01** | Registro exitoso de reserva en cancha disponible | Funcional | Cancha 5 sin turnos ocupados el 2026-11-02 a las 20:00 hs | `Cancha: Cancha 5, Fecha: 2026-11-02, Hora: 20:00, Cliente: CLI-102, Clima: Despejado, Temp: 22°C, Hum: 55%` | 1. Enviar `POST /api/v1/reservas`.<br>2. Verificar código HTTP y cuerpo de respuesta.<br>3. Consultar ocupación en grilla. | HTTP 201 Created. Reserva creada con ID prefijado (`R-XXXX`). Predicción adjunta en tiempo real. Grilla muestra celda ocupada. | **HTTP 201 Created**. ID `R-0001` generado. Predicción Verde (0.00% No-Show). Grilla marca Cancha 5 20:00 como ocupada. | **PASSED** (0.033 s) |
| **CF-02** | Bloqueo de reserva duplicada en misma cancha, fecha y hora | Funcional | Existe reserva previa confirmada en Cancha 5, 2026-11-02 a las 20:00 hs | `Cancha: Cancha 5, Fecha: 2026-11-02, Hora: 20:00, Cliente: CLI-104` (segundo cliente) | 1. Confirmar reserva base.<br>2. Intentar registrar una segunda reserva con idéntico horario y cancha.<br>3. Verificar respuesta. | HTTP 409 Conflict. Código `HORARIO_NO_DISPONIBLE`. Mensaje claro indicando la reserva en conflicto. Base no duplica el turno. | **HTTP 409 Conflict**. Detalle: *"Horario no disponible: Cancha 5 ya está reservada el 2026-11-02 a las 20:00"*. No se registró duplicado. | **PASSED** (0.048 s) |
| **CF-03** | Detección de riesgo alto ante cliente moroso y clima adverso | Funcional | Cliente con historial de faltas frecuente (`CLI-103`) solicita turno en horario nocturno | `Cancha: Cancha 5, Cliente: CLI-103, Hora: 22:00, Clima: Lluvia / Frío Extremo, Temp: 10°C / 4°C` | 1. Enviar payload a `POST /api/v1/reservas/predict`.<br>2. Analizar nivel de riesgo, semáforo y sugerencias. | Nivel `Rojo - Alto`. Probabilidad de No-Show > 50%. Flag `requiere_sena: true`. Seña calculada al 50% del valor del turno. Acción preventiva de WhatsApp obligatoria. | **Nivel Rojo - Alto**. Probabilidad 100.00%. Seña exigida: $18.000 (50% de $36.000). Acción: *"Exigir seña obligatoria del 50% y enviar recordatorio automático por WhatsApp"*. | **PASSED** (0.014 s) |
| **CF-04** | Inferencia segura para cliente nuevo sin historial (Fix BUG-02) | Funcional | Cliente nuevo nunca registrado en el cuaderno físico (`CLI-NUEVO-9999`) | `Cliente_ID: CLI-NUEVO-9999, Cancha: Cancha 5, Fecha: 2026-11-02, Hora: 19:00, Clima: Despejado` | 1. Enviar payload de predicción.<br>2. Verificar ausencia de excepciones de servidor (HTTP 500).<br>3. Constatar valor imputado. | HTTP 200 OK. Campo `cliente_nuevo: true`. Tasa de cumplimiento imputada por defecto (mediana del sistema). Sin caídas de ejecución. | **HTTP 200 OK**. `cliente_nuevo: true`. Historial imputado: 1.0 (mediana). Nivel Verde (0.00% No-Show). En condiciones adversas evalúa a Rojo de forma segura sin Error 500. | **PASSED** (0.042 s) |
| **CS-01** | Control de acceso basado en roles (RBAC) en endpoint admin | No Funcional (Seguridad) | Endpoint `/api/v1/admin/metricas` configurado con dependencia de rol | Petición A: `X-Role: Recepcionista`<br>Petición B: Sin encabezado `X-Role`<br>Petición C: `X-Role: Admin` | 1. Petición A con rol recepcionista.<br>2. Petición B anónima.<br>3. Petición C con rol administrador. | Petición A: HTTP 403 Forbidden.<br>Petición B: HTTP 401 Unauthorized.<br>Petición C: HTTP 200 OK con métricas completas. | **Petición A: 403 Forbidden** (`ACCESO_DENEGADO`).<br>**Petición B: 401 Unauthorized** (`NO_AUTENTICADO`).<br>**Petición C: 200 OK** con reporte y métricas de limpieza. | **PASSED** (0.020 s) |
| **CS-02** | Neutralización de inyección de código XSS (Fix BUG-01) | No Funcional (Seguridad) | Entrada de texto libre en campos de cliente y anotación manuscrita | `Cliente_ID: <script>alert('XSS')</script>`, `Anotacion_Cuaderno: <img src=x onerror=alert(1)>` | 1. Enviar payload malicioso a `POST /api/v1/reservas`.<br>2. Inspeccionar respuesta, base de datos y grilla.<br>3. Verificar cabeceras CSP. | Caracteres de control y etiquetas escapadas en HTML entities (`&lt;script&gt;`). Sin ejecución de scripts. Cabecera CSP `script-src 'self'`. | **HTTP 201 Created**. Texto almacenado como `&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;`. Grilla no contiene `<script>`. Headers CSP y `X-Content-Type-Options: nosniff` activos. | **PASSED** (0.021 s) |
| **CU-01** | Consistencia visual y semántica del semáforo predictivo | No Funcional (Usabilidad) | Variedad de escenarios de prueba (bajo, medio y alto riesgo) | 3 payloads combinando clientes cumplidores/morosos y climas despejado/lluvioso | 1. Consultar predicción de cada escenario.<br>2. Contrastar coherencia entre color, etiqueta, umbral numérico y acción sugerida. | Correspondencia biunívoca: Verde < 25% (Acción estándar), Amarillo 25-50% (Recordatorio), Rojo ≥ 50% (Seña 50% + WhatsApp). | **Coherencia total**: Verde (0%, estándar), Rojo (84% y 73%, seña + WhatsApp). Etiquetas idénticas a los requerimientos de negocio. | **PASSED** (0.044 s) |
| **CU-02** | Rendimiento y latencia de inferencia en tiempo real | No Funcional (Rendimiento) | Servidor uvicorn ejecutándose en puerto local, modelo cargado en memoria | 30 peticiones HTTP secuenciales con variaciones de cliente y horario sobre `/api/v1/reservas/predict` | 1. Ejecutar fase de calentamiento (3 requests).<br>2. Disparar 30 requests cronometradas con `time.perf_counter`.<br>3. Calcular media, percentil 95 y máximo. | Latencia máxima menor a 300 ms. Promedio esperado < 50 ms en entorno local. | **Media: 14.4 ms**, **Percentil 95: 15.3 ms**, **Máximo: 68.3 ms**. Cumple holgadamente el criterio de aceptación (< 300 ms). | **PASSED** (0.746 s) |

---

## 5. RECURSOS DEL TESTING ACTUALIZADOS

| Categoría | Recurso / Herramienta | Versión / Especificación | Propósito en el Proyecto |
| :--- | :--- | :--- | :--- |
| **Entorno de Hardware** | CPU x86_64 / 16 GB RAM / SSD NVMe | Windows 11 Home / PowerShell | Plataforma base de desarrollo y ejecución de pruebas locales. |
| **Lenguaje y Runtime** | Python | 3.11.9 | Motor de ejecución del backend, pipelines ML y pruebas. |
| **Framework Backend** | FastAPI + Pydantic v2 | 0.135.3 / 2.12.5 | Exposición de endpoints REST, validación estricta de esquemas y middleware de seguridad. |
| **Servidor ASGI** | Uvicorn | 0.44.0 | Servidor web asíncrono para atención de peticiones en localhost:8000. |
| **Framework de Pruebas** | PyTest + pytest-cov | 9.1.1 | Automatización de la suite de pruebas unitarias y de integración. |
| **Cliente de Pruebas HTTP**| HTTPX / TestClient | 0.28.1 | Invocación asíncrona y síncrona de endpoints con medición de latencias. |
| **Librerías de ML** | Scikit-Learn / Joblib | 1.9.1 / 1.6.0 | Entrenamiento de Random Forest, GridSearchCV y serialización del pipeline. |
| **Análisis de Datos** | Pandas / NumPy | 2.3.3 / 2.3.3 | Depuración del dataset histórico, feature engineering y métricas. |
| **Auditoría de Frontend** | Lighthouse / DevTools | Chromium v124+ | Inspección de rendimiento web, accesibilidad y adaptación en 1366x768. |

---

## 6. REPORTE DE DEFECTOS (BUG TRACKING)

Durante la fase de integración entre la digitalización del cuaderno, el modelo y la API REST se identificaron y solucionaron los siguientes defectos críticos:

### BUG-01: Vulnerabilidad de Cross-Site Scripting (XSS) en Anotaciones y Nombre de Cliente
- **Severidad:** Alta (Seguridad).
- **Prioridad:** Urgente.
- **Componente Afectado:** `POST /api/v1/reservas` y vistas `index.html` / `app.js`.
- **Descripción del Defecto:** Al registrar reservas manuscritas digitalizadas o turnos nuevos, si el usuario ingresaba caracteres como `<script>alert('XSS')</script>` en el campo `Cliente_ID` o `Anotacion_Cuaderno`, el texto se renderizaba sin escapar en la grilla visual de turnos y en el panel de auditoría, permitiendo la inyección involuntaria de código JavaScript en el navegador del recepcionista.
- **Pasos para Reproducir:**
  1. Enviar petición `POST /api/v1/reservas` con `Cliente_ID: "<script>alert(1)</script>"`.
  2. Abrir la Grilla de Canchas en el navegador.
  3. Observar la ejecución del diálogo emergente en el navegador.
- **Solución Implementada:**
  1. Se incorporó una función estricta de sanitización en el backend (`sanitizar_texto()` en `main.py`) que aplica `html.escape(..., quote=True)` antes de cualquier persistencia o respuesta.
  2. En el frontend (`app.js`), se eliminó el uso de `innerHTML` para datos provenientes de usuarios, empleando exclusivamente creación de nodos DOM con `textContent`.
  3. Se activó la cabecera HTTP defensiva `Content-Security-Policy: script-src 'self'` y `X-Content-Type-Options: nosniff`.
- **Estado Actual:** **SOLUCIONADO** (Verificado mediante caso `CS-02`).

---

### BUG-02: Excepción no controlada (Error 500) ante Clientes Nuevos en Inferencia
- **Severidad:** Crítica (Disponibilidad).
- **Prioridad:** Alta.
- **Componente Afectado:** `ServicioModelo.predecir()` en `main.py`.
- **Descripción del Defecto:** El diccionario de historial de cumplimiento sólo contemplaba los 24 clientes digitalizados en el cuaderno de 2024-2025 (`CLI-101` a `CLI-124`). Cuando un recepcionista ingresaba un cliente por primera vez (ej. `CLI-NUEVO-01`), la búsqueda en el diccionario lanzaba un `KeyError` interno que escalaba a una respuesta HTTP 500 Internal Server Error, interrumpiendo la atención en mostrador.
- **Pasos para Reproducir:**
  1. Ingresar al formulario de recepción.
  2. Cargar un ID no existente en el historial: `CLI-2026-X`.
  3. Presionar "Evaluar riesgo".
  4. La API colapsaba con HTTP 500 y mensaje `KeyError: 'CLI-2026-X'`.
- **Solución Implementada:**
  1. Se refactorizó el método `ServicioModelo.historial()` para aplicar el patrón de valor por defecto (*fallback*): si el ID no existe, asigna automáticamente la mediana de cumplimiento del sistema (1.00), marca el flag booleano `cliente_nuevo: true` y clasifica su historial como "Excelente (por defecto)", retornando HTTP 200 sin excepciones.
- **Estado Actual:** **SOLUCIONADO** (Verificado mediante caso `CF-04`).

---

### BUG-03: Desbordamiento Visual de Canchas 10 a 13 en Resoluciones HD (1366x768)
- **Severidad:** Media (Usabilidad).
- **Prioridad:** Media.
- **Componente Afectado:** Grilla de 13 canchas (`static/styles.css`, contenedor `.grid-scroll`).
- **Descripción del Defecto:** En computadoras de escritorio comunes utilizadas en administraciones de clubes y canchas (resolución estándar HD de 1366x768 píxeles), las columnas de las canchas 10 a 13 quedaban cortadas horizontalmente y desbordaban la ventana gráfica del navegador, obligando a hacer scroll en toda la página y perdiendo de vista la cabecera horaria.
- **Pasos para Reproducir:**
  1. Configurar la resolución del navegador a 1366 x 768 píxeles.
  2. Abrir la pestaña "Grilla de las 13 Canchas".
  3. Observar que las canchas 11, 12 (Pádel) y 13 (Pádel) desaparecían del margen derecho.
- **Solución Implementada:**
  1. Se rediseñó el contenedor de la grilla (`.grid-scroll`) estableciendo `overflow: auto`, `min-width: 1180px` en la tabla y asignando `position: sticky` con `top: 0` y `z-index` diferenciado a los encabezados de horarios, y `left: 0` a la primera columna con los nombres de las canchas.
  2. De este modo, el usuario navega las 13 canchas fluidamente mediante scroll interno horizontal y vertical sin romper el layout general.
- **Estado Actual:** **SOLUCIONADO** (Verificado mediante caso `EX-03` y validación de estilos).

---

# PARTE B: PRÁCTICA PROFESIONALIZANTE I

## 1. INTEGRACIÓN DEL PROTOTIPO (ARQUITECTURA PUNTA A PUNTA)

La solución técnica desarrollada para Esquiu3 implementa una arquitectura modular de tres capas (Extracción/Entrenamiento, Lógica de Negocio/API y Presentación Reactiva), garantizando el desacoplamiento y la escalabilidad futura.

### Diagrama Arquitectónico del Flujo de Datos

```
+---------------------------------------------------------------------------------------+
|                              ARQUITECTURA DEL SISTEMA ESQUIU3                         |
+---------------------------------------------------------------------------------------+
|                                                                                       |
|   +------------------------------------+                                              |
|   |   Cuaderno Físico Manuscrito       |                                              |
|   |   (Digitalizado 2024-2025)         |                                              |
|   +-----------------+------------------+                                              |
|                     |                                                                 |
|                     v                                                                 |
|   +------------------------------------+                                              |
|   |   reservas_esquiu3.csv (100 filas) |                                              |
|   +-----------------+------------------+                                              |
|                     |                                                                 |
|                     v                                                                 |
|   +-------------------------------------------------------------------------------+   |
|   |                    PIPELINE DE MACHINE LEARNING (train_model.py)              |   |
|   |  - Limpieza: descarte de año 1900 (2 filas) e imputación mediana 3% nulos     |   |
|   |  - Feature Engineering: Horario pico, Día, Historial acumulado cliente        |   |
|   |  - Entrenamiento: RandomForestClassifier optimizado con GridSearchCV          |   |
|   |  - Validación: CV 5x5 estratificada (Recall: 91.07%, Accuracy: 94.68%)        |   |
|   +-----------------+-------------------------------------------------------------+   |
|                     |                                                                 |
|                     v                                                                 |
|   +------------------------------------+                                              |
|   |       modelo_esquiu3.joblib        | (Pipeline serializado + metadatos)           |
|   +-----------------+------------------+                                              |
|                     |                                                                 |
|                     v                                                                 |
|   +-------------------------------------------------------------------------------+   |
|   |                      BACKEND REST API (FastAPI - main.py)                     |   |
|   |  - Almacén en memoria concurrente (13 canchas, turnos 14:00 a 23:00 hs)       |   |
|   |  - POST /api/v1/reservas/predict (Inferencia en tiempo real, latencia ~14 ms) |   |
|   |  - POST /api/v1/reservas (Sanitización XSS, bloqueo solapamiento HTTP 409)    |   |
|   |  - GET  /api/v1/canchas/ocupacion (Matriz de ocupación coloreada por riesgo)  |   |
|   |  - GET  /api/v1/clima/pronostico (Servicio meteorológico + Fallback)          |   |
|   |  - GET  /api/v1/admin/metricas (Seguridad RBAC mediante header X-Role)        |   |
|   +-----------------+-------------------------------------------------------------+   |
|                     |                                                                 |
|                     v (JSON REST)                                                     |
|   +-------------------------------------------------------------------------------+   |
|   |                    FRONTEND WEB INTUITIVO (HTML5 / Vanilla CSS / JS)          |   |
|   |                                                                               |   |
|   |   [ Vista 1: Recepción ]       [ Vista 2: Grilla Canchas ]    [ Vista 3: Admin]   |   |
|   |   - Carga de turno             - Calendario 13 canchas        - Auditoría notas   |   |
|   |   - Presets de clima (☀️⛅🌧️❄️)   - Colores según riesgo         - Métricas limpieza |   |
|   |   - Semáforo predictivo        - Selección rápida de slot     - Desempeño ML      |   |
|   |   - Cobro seña / WhatsApp      - Scroll responsivo            - Control de rol    |   |
|   +-------------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------------+
```

### Explicación del Flujo Operativo:
1. **Entrenamiento y Persistencia:** Al iniciar el ciclo, `train_model.py` toma las 100 filas del archivo CSV, descarta las 2 filas con año 1900, imputa los 3 montos nulos por la mediana de su tipo de cancha, construye las variables numéricas y categóricas, y entrena el `RandomForestClassifier`. El pipeline completo, junto con los diccionarios de precios y comportamiento por cliente, se guarda en `modelo_esquiu3.joblib`.
2. **Servicio y Validación en Backend:** Al iniciar la API en FastAPI, se carga el bundle del modelo. El almacén en memoria se inicializa con los turnos válidos del cuaderno. Cuando la recepción envía una nueva reserva:
   - Se valida la coherencia entre cancha y tipo de cancha mediante esquemas de Pydantic.
   - Se verifica si el horario ya está ocupado en la misma cancha y fecha; de haber conflicto, se rechaza inmediatamente con `HTTP 409 Conflict`.
   - Se consulta el modelo de Machine Learning, el cual evalúa en menos de 15 ms la probabilidad de No-Show considerando el clima actual y el cliente.
   - Se etiqueta el riesgo: **Verde (< 25%)**, **Amarillo (25-50%)** o **Rojo (≥ 50%)**.
   - Si el riesgo es **Rojo**, el sistema activa automáticamente la regla de negocio: exige una seña obligatoria del 50% ($18.000 en F7) y genera el texto de recordatorio para WhatsApp.
3. **Experiencia de Usuario en Frontend:** La interfaz web permite al operador seleccionar climas rápidos mediante botones intuitivos (`☀️ Despejado`, `⛅ Nublado`, `🌧️ Lluvia`, `❄️ Frío extremo`) o ingresar valores específicos. Al interactuar con los campos, la interfaz recalcula en tiempo real el semáforo y ofrece un bloque de explicación en lenguaje llano, comparando el turno con un día despejado habitual.

---

## 2. ERRORES CONTROLADOS Y LIMITACIONES CONOCIDAS DEL MVP BETA

Como corresponde a una versión Beta de un Producto Mínimo Viable (MVP), el sistema cuenta con controles de excepción robustos y limitaciones de alcance documentadas:

1. **Simulación de la Pasarela de WhatsApp:**
   - *Control implementado:* El endpoint `POST /api/v1/reservas/{id}/recordatorio-whatsapp` genera la plantilla formal de mensaje con datos dinámicos (nombre del cliente, cancha, fecha, hora e instrucción de confirmación) y registra en el log que el mensaje fue "enviado".
   - *Limitación conocida:* No está conectado a un número real ni a la API de Meta; los mensajes no impactan en dispositivos móviles de clientes.
2. **Fallback ante Caída del Servicio Meteorológico:**
   - *Control implementado:* Si el servicio meteorológico externo falla o se activa la bandera `simular_caida=true`, el sistema no arroja error. En su lugar, activa la función `_clima_fallback()`, la cual calcula la moda de condición climática y promedios históricos de temperatura y humedad observados en el cuaderno para el mes en cuestión, notificando al recepcionista mediante una advertencia visual.
   - *Limitación conocida:* Los promedios mensuales son aproximados y no detectan tormentas imprevistas de última hora si la conexión meteorológica está caída.
3. **Ausencia de Pasarela de Pagos (Mercado Pago):**
   - *Control implementado:* El recepcionista cuenta con un botón interactivo "Registrar cobro de seña" que valida que el turno de riesgo alto haya sido señado antes de marcarlo como confirmado.
   - *Limitación conocida:* No genera links de pago (checkout) ni códigos QR automáticos; el cobro efectivo debe ser verificado por el encargado mediante efectivo o transferencia bancaria.
4. **Almacenamiento en Memoria de la Sesión:**
   - *Control implementado:* Thread-safe lock (`threading.RLock`) para evitar condiciones de carrera entre recepcionistas concurrentes.
   - *Limitación conocida:* Los turnos registrados en la sesión se pierden si se reinicia el proceso del servidor Uvicorn (para la versión final de producción se migrará a base de datos relacional PostgreSQL con SQLAlchemy/SQLModel).

---

## 3. DOCUMENTACIÓN TÉCNICA ACTUALIZADA Y JUSTIFICACIÓN DE CAMBIOS

### 3.1 Stack Tecnológico del MVP Beta

| Componente | Tecnología | Justificación Técnica de Selección |
| :--- | :--- | :--- |
| **Backend Core** | FastAPI 0.135+ | Asincronismo de alto rendimiento, validación automática mediante tipos de datos con Pydantic y documentación interactiva autogenerada en Swagger (`/docs`). |
| **Modelado Predictivo** | Scikit-Learn 1.9+ | Implementación de `RandomForestClassifier` con ponderación de clases (`class_weight='balanced'`), ensamblado de árboles y cálculo determinístico de probabilidades continuas con `predict_proba()`. |
| **Persistencia del Modelo** | Joblib 1.6+ | Serialización eficiente de pipelines de Scikit-Learn y diccionarios de metadatos en un único archivo binario transportable (`modelo_esquiu3.joblib`). |
| **Testing Automatizado** | PyTest 9.1+ | Ejecución parametrizada de pruebas unitarias, aserciones declarativas y captura programática de evidencias de ejecución. |
| **Frontend de Operación** | HTML5 Semántico + Vanilla CSS + JS Modular | Cero dependencias pesadas de empaquetado (Node/Webpack/React), carga instantánea en navegadores modestos, diseño responsivo adaptado a la identidad institucional de Esquiu3 (paleta cálida beige y acento naranja de SharedSpaceManager). |

### 3.2 Justificación de Cambios Respecto a las Evidencias 1 y 2

| Aspecto | Evidencia 1 y 2 (Previo) | Evidencia 3 (MVP Beta Actual) | Justificación del Cambio |
| :--- | :--- | :--- | :--- |
| **Entorno de Ejecución** | Notebooks interactivos de Jupyter (`.ipynb`) | Arquitectura cliente-servidor con backend FastAPI y frontend web | Los notebooks son herramientas analíticas exploratorias pero inviables para la operación diaria de un encargado de recepción en mostrador. |
| **Variables Predictoras** | Solo variables de calendario (`Hora`, `Tipo_Cancha`, `Dia_Semana`) | Se agregaron `Temperatura_C`, `Humedad_Pct`, `Condicion_Climatica` e `Historial_Cumplimiento_Cliente` | Las cancelaciones en complejos deportivos están fuertemente condicionadas por el clima (días de lluvia o frío polar) y la morosidad individual. Su inclusión aumentó el Recall de 72% a más de 91%. |
| **Calidad de Datos** | Registros brutos con fechas con año 1900 y montos nulos | Pipeline formal de depuración que documenta 2 descartes y 3 imputaciones medianas | Asegura que el modelo no aprenda de anomalías de digitación y provee trazabilidad para auditoría institucional. |
| **Validación de Software** | Pruebas manuales ad-hoc en celdas de notebook | Suite automatizada de 16 casos de prueba (funcionales, seguridad, usabilidad y latencia) | Garantiza repetibilidad, previene regresiones ante cambios de código y cumple los estándares formales de la materia *Testeo de Software*. |
| **Toma de Decisiones** | Inferencia aislada sin consecuencias operativas | Semáforo tricolor integrado con cálculo automático de seña del 50% y plantilla de WhatsApp | Convierte la analítica de datos en una herramienta de negocio preventiva que reduce directamente el impacto económico del No-Show. |

---

# CONCLUSIONES GENERALES DE LA ENTREGA

1. **Objetivo Académico y Técnico Alcanzado:** Se cumplieron en su totalidad las consignas de la Evidencia 3 para el ISPC, logrando una versión Beta completamente funcional, testeada y documentada que une la ciencia de datos con el desarrollo de software y el aseguramiento de la calidad.
2. **Impacto Directo en el Negocio:** Al identificar con un 91.07% de Recall los turnos de alto riesgo de inasistencia, el complejo deportivo Esquiu3 puede asegurar el cobro de señas por adelantado o liberar canchas con tiempo para otros clientes, mitigando las pérdidas económicas por turnos ociosos.
3. **Base Sólida para la Evidencia 4 / Versión Final:** La arquitectura modular y desacoplada permite incorporar con mínimo esfuerzo una base de datos relacional definitiva (PostgreSQL), pasarelas de pago reales y autenticación JWT para la entrega final del ciclo 2026.

---

*Documento elaborado y validado por el Grupo Nº 6 - Instituto Superior Politécnico Córdoba (ISPC), Octubre de 2026.*
