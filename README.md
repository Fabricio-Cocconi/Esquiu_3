# ⚽ Esquiu3 · Sistema Inteligente de Gestión de Canchas y Analítica Predictiva de No-Show

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688.svg)](https://fastapi.tiangolo.com/)
[![Scikit-Learn](https://img.shields.io/badge/scikit--learn-Random%20Forest-F7931E.svg)](https://scikit-learn.org/)
[![Pytest](https://img.shields.io/badge/Tests-16%2F16%20Passing-brightgreen.svg)](https://docs.pytest.org/)
[![ISPC](https://img.shields.io/badge/ISPC%202026-Evidencia%20N%C2%BA3-orange.svg)](https://www.ispc.edu.ar/)

> **MVP Beta Integrado** desarrollado para la **Evidencia de Aprendizaje Nº 3** (Año 2026) del **Instituto Superior Politécnico Córdoba (ISPC)**, articulando las materias **Testeo de Software** y **Práctica Profesionalizante I**.

---

## 📌 Contexto del Proyecto

El complejo deportivo **"Esquiu3"** cuenta con **13 canchas** deportivas (Fútbol 5 sintético, Fútbol 7 césped, Pádel panorámico de blindex, Tenis polvo de ladrillo y Básquet parquet techado).

Históricamente, la administración operaba mediante un **cuaderno físico manuscrito**, lo que generaba:
1. **Solapamiento involuntario de turnos** y conflictos en recepción.
2. **Alta tasa de ausentismo imprevisto (*No-Show*)**, dejando canchas ociosas en horarios pico sin posibilidad de reasignación.
3. **Pérdida de ingresos** no mitigada, acentuada por la falta de anticipación a factores meteorológicos adversos (frío extremo, lluvia).
4. **Anomalías en el registro manual**, tales como fechas con año 1900 y montos nulos por señas omitidas.

### 💡 Solución Desarrollada
Un sistema web integral que combina:
- **Landing Page moderna e interactiva** con bloques de contenido explicativo y animaciones fluidas al hacer scroll.
- **Motor Predictivo de Machine Learning** (*Random Forest Classifier*) optimizado para maximizar el **Recall de Ausentismo (91.07% en Validación Cruzada 5x5 / 100% en conjunto de prueba)**.
- **Semáforo de Riesgo en Tiempo Real** (Verde = Bajo, Amarillo = Medio, Rojo = Alto riesgo de inasistencia) con política activa de cobro de seña del 50% y generación de mensajes instantáneos para WhatsApp.
- **Grilla Interactiva de 13 canchas** con navegación temporal y prevención de duplicados (código HTTP 409).
- **Módulo de Clima Libre y Explicación Neutra**, permitiendo simular cualquier escenario meteorológico y comprender el impacto directo en la probabilidad de asistencia.
- **Auditoría con Control de Acceso Basado en Roles (RBAC)** y trazabilidad de los datos digitalizados.

---

## 🚀 Características Principales

| Módulo | Descripción |
| :--- | :--- |
| **🏠 Landing Page Interactiva** | Presentación visual con estética beige cálido y naranja (#E65C00), animaciones de entrada, métricas clave en tiempo real, stepper de flujo operativo y presentación del equipo. |
| **⚡ Dashboard MVP Beta** | Entorno operativo intuitivo para recepción con carga de reservas, sugerencia automática de tipo de cancha e historial de clientes. |
| **🚦 Semáforo Predictivo ML** | Inferencia instantánea (< 20 ms) con probabilidades calibradas. Si el riesgo es Amarillo o Rojo, exige seña del 50% y redacta el mensaje de confirmación para WhatsApp. |
| **🌦️ Simulador de Clima Libre** | Presets rápidos (Despejado, Lluvia, Frío extremo) o carga libre de temperatura/humedad con re-análisis en tiempo real explicado en lenguaje claro y accesible. |
| **🏟️ Grilla de 13 Canchas** | Matriz de disponibilidad horaria (14:00 a 23:00 hs) con codificación cromática por nivel de riesgo y prevención estricta de solapamientos. |
| **🛡️ Seguridad & RBAC** | Sanitización contra XSS en notas de clientes y restricción de endpoints administrativos (`X-Role: Admin`). |
| **📋 Panel de Auditoría** | Inspección del dataset histórico digitalizado (`reservas_esquiu3.csv`), matriz de confusión, importancia de variables y detección de anomalías. |

---

## 📊 Métricas del Modelo de Machine Learning

El modelo fue entrenado con `train_model.py` utilizando `RandomForestClassifier` con regularización contra sobreajuste (`max_depth=5`, `class_weight='balanced'`) y validación cruzada estratificada repetida (5 folds × 5 repeticiones):

| Métrica | Validación Cruzada (5x5) | Conjunto de Prueba (Hold-out) | Objetivo ISPC | Estado |
| :--- | :---: | :---: | :---: | :---: |
| **Recall (No-Show)** | **91.07%** | **100.0%** | > 72.0% | ✅ Superado (+19.07 pp) |
| **Accuracy Global** | **94.68%** | **96.0%** | > 80.0% | ✅ Superado |
| **Precisión (Ausentes)**| **88.67%** | **83.3%** | - | ✅ Alta confianza |
| **Aporte del Clima (Δ Recall)** | **+14.27 pp** | **+16.67 pp** | Relevante | ✅ Valida hipótesis |
| **Latencia de Inferencia** | **~ 12 ms** | **~ 12 ms** | < 300 ms | ✅ Rendimiento óptimo |

---

## 🛠️ Estructura del Repositorio

```text
├── EVIDENCIA_3_ISPC_GRUPO6.md    # Documento formal completo para la entrega académica ISPC
├── main.py                       # API REST FastAPI con validaciones, RBAC y fallback climático
├── train_model.py                # Pipeline de ML: limpieza, feature engineering, validación y exportación
├── regenerar_csv.py              # Script reproducible de generación y balanceo del dataset sintético
├── modelo_esquiu3.joblib         # Artefacto binario serializado del modelo entrenado
├── reporte_entrenamiento.json    # Métricas oficiales y matriz de confusión del entrenamiento
├── reservas_esquiu3.csv          # Dataset activo digitalizado del cuaderno con cancelaciones distribuidas
├── reservas_esquiu3_original.csv # Respaldo del dataset original
├── requirements.txt              # Dependencias del proyecto para pip
├── pytest.ini                    # Configuración del entorno de pruebas
├── .gitignore                    # Archivos y carpetas excluidos del control de versiones
├── static/
│   ├── index.html                # Interfaz web unificada: Landing Page animada + Dashboard MVP
│   ├── styles.css                # Sistema de diseño SharedSpaceManager (beige/naranja) y animaciones CSS
│   └── app.js                    # Lógica frontend vanilla (defensa XSS, conmutador de modos, observer)
└── tests/
    ├── conftest.py               # Fixtures compartidas para cliente HTTP y mock de modelo
    ├── test_esquiu3.py           # Suite completa de 16 pruebas automatizadas
    └── resultados_pruebas.json   # Registro persistido de ejecución de pruebas
```

---

## 💻 Instalación y Puesta en Marcha

### Prerrequisitos
- **Python 3.10 o superior** instalado en el sistema.
- Navegador web moderno (Chrome, Firefox, Edge).

### 1. Clonar el Repositorio
```bash
git clone https://github.com/TU_USUARIO/TU_REPOSITORIO.git
cd TU_REPOSITORIO
```

### 2. Crear y Activar un Entorno Virtual (Recomendado)
- **En Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
- **En Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Instalar Dependencias
```bash
pip install -r requirements.txt
```

### 4. (Opcional) Reentrenar el Modelo Predictivo
```bash
python train_model.py
```
*Genera `modelo_esquiu3.joblib` y actualiza `reporte_entrenamiento.json`.*

### 5. Iniciar la Aplicación Web
```bash
python -m uvicorn main:app --reload --port 8000
```

### 6. Acceder al Sistema
Abre tu navegador e ingresa a:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

- Podrás navegar por la **Landing Page animada** y conmutar en cualquier momento al **Dashboard MVP**.
- La documentación interactiva de la API está disponible en **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)** (Swagger UI).

---

## 🧪 Pruebas Automatizadas (QA & Testing)

El proyecto cuenta con **16 casos de prueba unitarios, de integración, seguridad y regresión**, ejecutados bajo `pytest`:

```bash
python -m pytest
```

### Resumen de la Matriz de Pruebas:
- **CF-01**: Registro exitoso de reserva en cancha y turno disponible.
- **CF-02**: Bloqueo con HTTP 409 Conflict ante intento de reserva duplicada/solapada.
- **CF-03**: Detección de riesgo ALTO (Rojo) para clientes con historial de inasistencia en horario pico y lluvia/frío.
- **CF-04**: Manejo correcto de cliente nuevo sin historial (imputación por mediana).
- **CS-01**: Control de Acceso RBAC: Recepcionista denegado (HTTP 403) en endpoints de auditoría administrativa.
- **CS-02**: Sanitización contra inyección XSS (`<script>alert(1)</script>`) en notas del cuaderno.
- **CU-01**: Consistencia probabilística del semáforo (Verde < 35%, Amarillo 35-65%, Rojo > 65%).
- **CU-02**: Garantía de latencia de inferencia menor a 300 ms (medición real ~ 12 ms).
- **EX-01 / EX-02**: Validaciones de dominio, grilla de 13 canchas y servicio climático resiliente con fallback.
- **EX-03**: Regresión de layout CSS y scroll horizontal en grilla horaria.
- **EX-04**: Análisis multiescenario de clima libre con explicación en lenguaje natural.

---

## 👥 Equipo de Proyecto (Grupo Nº 6 - ISPC 2026)

- **Yanina Roldan**
- **Gabriel Yoles Trucco**
- **Fabricio Cocconi**
- **Franco Gonzalo Arce**

### Cuerpo Docente Evaluador
- **Prof. David Cabrera & Prof. Carolina Ahumada** — *Testeo de Software*
- **Prof. Daniela Accietto & Prof. Florencia García** — *Práctica Profesionalizante I*

**Instituto Superior Politécnico Córdoba (ISPC)** · Tecnicaturas Superiores en Ciencia de Datos e Inteligencia Artificial & Desarrollo de Software.
