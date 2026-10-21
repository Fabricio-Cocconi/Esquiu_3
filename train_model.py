"""
ESQUIU3 - MODELO PREDICTIVO DE AUSENTISMO (NO-SHOW)
================================================================================
Materia:      Práctica Profesionalizante I
Carrera:      Tecnicatura Superior en Ciencia de Datos e Inteligencia Artificial
Institución:  Instituto Superior Politécnico Córdoba (ISPC)
Docentes:     Prof. Daniela Accietto - Prof. Florencia García
Equipo:       Grupo Nº 6 - Evidencia de Aprendizaje Nº 3 (Ciclo Lectivo 2026)
Metodología:  CRISP-DM (Cross-Industry Standard Process for Data Mining)
================================================================================
Fases de la Metodología CRISP-DM aplicadas en este script:
  1. Comprensión del Negocio y Exploración de Datos
  2. Preparación de los Datos y Calidad (Limpieza, Imputación, Anti-Leakage)
  3. Modelado (Pipeline con ColumnTransformer y RandomForestClassifier)
  4. Evaluación del Modelo (Matriz de Confusión, Accuracy, Precision, Recall, F1)
  5. Despliegue y Exportación de Artefactos (joblib y reporte JSON)
================================================================================
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "reservas_esquiu3.csv"
MODEL_PATH = BASE_DIR / "modelo_esquiu3.joblib"
REPORT_PATH = BASE_DIR / "reporte_entrenamiento.json"

RANDOM_STATE = 42
HORA_PICO_INICIO, HORA_PICO_FIN = 19, 23          # Franja nocturna de mayor demanda (19 a 23 hs)
ESTADOS_NO_SHOW = {"Ausente", "Cancelada"}

# Línea base declarada formalmente a los profesores en la Evidencia 2
BASELINE_EVIDENCIA_2 = {"accuracy": 0.78, "recall_no_show": 0.72}

# Definición de variables predictoras (Features)
FEATURES_CAT = ["Tipo_Cancha", "Condicion_Climatica"]
FEATURES_NUM = [
    "Dia_Semana",
    "Hora_Num",
    "Historial_Cumplimiento_Cliente",
    "Temperatura_C",
    "Humedad_Pct",
]
FEATURES = [
    "Tipo_Cancha",
    "Dia_Semana",
    "Hora_Num",
    "Historial_Cumplimiento_Cliente",
    "Temperatura_C",
    "Humedad_Pct",
    "Condicion_Climatica",
]
FEATURES_SIN_CLIMA = [
    "Tipo_Cancha",
    "Dia_Semana",
    "Hora_Num",
    "Historial_Cumplimiento_Cliente",
]

# Umbrales del Semáforo Predictivo para la recepción
# Verde: < 0.35 | Amarillo: 0.35 a 0.65 | Rojo: >= 0.65 (exige seña del 50%)
UMBRALES_RIESGO = {"amarillo": 0.35, "rojo": 0.65}


# ==============================================================================
# FUNCIONES AUXILIARES REUTILIZADAS POR LA API Y EL FLUJO OPERATIVO
# ==============================================================================
def categoria_cumplimiento(tasa: float) -> str:
    """Clasificación cualitativa de la conducta del cliente según el apunte."""
    if tasa >= 0.85:
        return "Excelente"
    if tasa >= 0.50:
        return "Regular"
    return "Malo"


def limpiar_dataset(csv_path: Path = CSV_PATH) -> tuple[pd.DataFrame, dict]:
    """
    CRISP-DM FASE 2: Preparación de Datos.
    Tratamiento de inconsistencias y valores nulos según lo visto en clase.
    """
    df = pd.read_csv(csv_path, encoding="utf-8")
    total_original = len(df)

    # 1) Detección y descarte de fechas inconsistentes (año 1900)
    fecha_parseada = pd.to_datetime(df["Fecha"], errors="coerce")
    mask_1900 = fecha_parseada.dt.year == 1900
    mask_invalida = fecha_parseada.isna() | (fecha_parseada.dt.year < 2000)
    filas_descartadas = df[mask_invalida]
    df = df[~mask_invalida].copy()
    df["Fecha"] = fecha_parseada[~mask_invalida]

    # 2) Tratamiento de valores faltantes (Unidad 2):
    #    Paso a: Creación de la columna indicadora (Missing Flag)
    nulos_antes = int(df["Monto_Abonado"].isna().sum())
    df["monto_faltante_flag"] = df["Monto_Abonado"].isna().astype(int)

    #    Paso b: Imputación por grupo con la mediana de cada Tipo_Cancha
    precios = (df[df["Monto_Abonado"] > 0]
               .groupby("Tipo_Cancha")["Monto_Abonado"]
               .median()
               .to_dict())
    df["Monto_Imputado"] = df["Monto_Abonado"].isna()
    df["Monto_Abonado"] = df["Monto_Abonado"].fillna(df["Tipo_Cancha"].map(precios))

    resumen = {
        "filas_originales": int(total_original),
        "filas_descartadas_fecha_invalida": int(mask_invalida.sum()),
        "filas_descartadas_anio_1900": int(mask_1900.sum()),
        "fechas_descartadas": filas_descartadas["Fecha"].astype(str).tolist(),
        "filas_resultantes": int(len(df)),
        "nulos_monto_abonado": nulos_antes,
        "pct_nulos_monto_abonado": round(100 * nulos_antes / total_original, 2),
        "nulos_monto_restantes": int(df["Monto_Abonado"].isna().sum()),
        "mediana_precio_por_tipo": {k: float(v) for k, v in precios.items()},
    }
    return df.reset_index(drop=True), resumen


def ingenieria_caracteristicas(df: pd.DataFrame) -> pd.DataFrame:
    """Extrae componentes temporales y define la variable objetivo binaria No_Show."""
    df = df.copy()
    df["Dia_Semana"] = df["Fecha"].dt.dayofweek                       # 0 = Lunes ... 6 = Domingo
    df["Hora_Num"] = df["Hora"].str.split(":").str[0].astype(int)
    df["Es_Fin_De_Semana"] = (df["Dia_Semana"] >= 5).astype(int)
    df["Es_Horario_Pico"] = df["Hora_Num"].between(HORA_PICO_INICIO, HORA_PICO_FIN - 1).astype(int)
    df["No_Show"] = df["Estado_Reserva"].isin(ESTADOS_NO_SHOW).astype(int)
    return df


def calcular_historial_cumplimiento(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, float]:
    """
    Calcula el historial de cumplimiento por cliente evitando fuga de información (Data Leakage).
    Para el cliente nuevo que no posee registros previos se asigna la mediana general del complejo.
    """
    df = df.sort_values(["Fecha", "Hora_Num", "Cancha"], kind="stable").reset_index(drop=True)
    asistio = 1 - df["No_Show"]
    previas = asistio.groupby(df["Cliente_ID"]).cumsum() - asistio
    n_previas = df.groupby("Cliente_ID").cumcount()
    tasa_previa = (previas / n_previas.replace(0, np.nan))

    # Mediana global histórica como tasa por defecto para clientes nuevos
    resumen_cli = df.groupby("Cliente_ID").agg(
        n=("No_Show", "size"),
        asistidas=("No_Show", lambda s: int((1 - s).sum()))
    )
    resumen_cli["tasa"] = resumen_cli["asistidas"] / resumen_cli["n"]
    default = float(resumen_cli["tasa"].median())

    df["Historial_Cumplimiento_Cliente"] = tasa_previa.fillna(default)
    df["Historial_Categoria"] = df["Historial_Cumplimiento_Cliente"].map(categoria_cumplimiento)

    diccionario = {
        cid: {
            "tasa": round(float(r.tasa), 4),
            "n_reservas": int(r.n),
            "categoria": categoria_cumplimiento(float(r.tasa))
        }
        for cid, r in resumen_cli.iterrows()
    }
    return df, diccionario, default


# ==============================================================================
# PIPELINE Y ENTRENAMIENTO PRINCIPAL (CRISP-DM)
# ==============================================================================
def main() -> dict:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore")

    print("=" * 80)
    print("ESQUIU3 — PIPELINE DE MACHINE LEARNING (CRISP-DM)")
    print("Materia: Práctica Profesionalizante I — ISPC")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # FASE 1: COMPRENSIÓN DE LOS DATOS Y ANÁLISIS EXPLORATORIO (EDA)
    # --------------------------------------------------------------------------
    print("\n[FASE 1] Comprensión de los Datos — Análisis Exploratorio Inicial:")
    df_crudo = pd.read_csv(CSV_PATH, encoding="utf-8")
    print(f"• Dimensiones del archivo original (df.shape): {df_crudo.shape}")
    print("\n• Estructura de tipos de datos (df.info()):")
    df_crudo.info()
    print("\n• Estadísticas descriptivas de variables numéricas (df.describe()):")
    print(df_crudo.describe().round(2))
    print("\n• Conteo de valores nulos o faltantes (df.isnull().sum()):")
    print(df_crudo.isnull().sum())

    # --------------------------------------------------------------------------
    # FASE 2: PREPARACIÓN DE LOS DATOS Y CALIDAD (Unidad 2)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[FASE 2] Preparación de los Datos y Tratamiento de Calidad:")
    df_limpio, limpieza = limpiar_dataset(CSV_PATH)
    print(f"• Inconsistencias de año 1900 descartadas : {limpieza['filas_descartadas_anio_1900']} filas -> {limpieza['fechas_descartadas']}")
    print(f"• Tratamiento de nulos en Monto_Abonado  : Creación de Missing Flag + Imputación por mediana ({limpieza['pct_nulos_monto_abonado']}%)")
    print(f"• Medianas calculadas por Tipo de Cancha : {limpieza['mediana_precio_por_tipo']}")
    print(f"• Registros válidos resultantes          : {limpieza['filas_resultantes']} filas")

    # Ingeniería de Características
    df_proc = ingenieria_caracteristicas(df_limpio)
    df_proc, hist_clientes, hist_default = calcular_historial_cumplimiento(df_proc)
    print(f"• Variable objetivo No_Show definida     : {int(df_proc['No_Show'].sum())} ausencias / cancelaciones ({100 * df_proc['No_Show'].mean():.1f}%)")
    print(f"• Historial por cliente calculado        : {len(hist_clientes)} clientes mapeados | Tasa por defecto (nuevos): {hist_default:.3f}")

    # Separación de variables predictoras X y variable objetivo y
    X = df_proc[FEATURES]
    y = df_proc["No_Show"]

    # PREVENCIÓN DE DATA LEAKAGE (Unidad 2):
    # Separamos en train y test ANTES de codificar para que el conjunto de prueba no contamine el entrenamiento.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.20,
        stratify=y,
        random_state=RANDOM_STATE
    )
    print(f"• Partición de datos (80% Train / 20% Test): Train={len(X_train)} filas, Test={len(X_test)} filas (estratificado)")

    # --------------------------------------------------------------------------
    # FASE 3: MODELADO (Unidades 1 y 2)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[FASE 3] Modelado con Pipeline de Scikit-Learn:")
    
    # Preprocesador de variables categóricas nominales:
    # Codificación One-Hot Encoding eliminando la primera categoría (drop="first") para evitar colinealidad.
    preprocesador = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(drop="first", handle_unknown="ignore"), FEATURES_CAT),
            ("num", "passthrough", FEATURES_NUM),
        ]
    )

    # NOTA DIDÁCTICA (Unidad 2):
    # Al utilizar RandomForestClassifier (algoritmo basado en ensambles de árboles de decisión),
    # NO es necesario aplicar escalado de características numéricas (como StandardScaler o MinMaxScaler).
    # Los árboles toman decisiones dividiendo los datos mediante umbrales independientes en cada variable,
    # por lo que no se ven afectados por las distintas escalas ni calculan distancias euclidianas como KNN.
    clasificador = RandomForestClassifier(
        n_estimators=100,
        max_depth=5,
        class_weight="balanced",
        random_state=RANDOM_STATE
    )

    pipeline = Pipeline(steps=[
        ("preprocesador", preprocesador),
        ("clasificador", clasificador)
    ])

    print("• Entrenando Pipeline (ColumnTransformer + RandomForestClassifier)...")
    pipeline.fit(X_train, y_train)

    # --------------------------------------------------------------------------
    # FASE 4: EVALUACIÓN (Métricas de la lámina de Clasificación - Unidad 2)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[FASE 4] Evaluación del Modelo:")

    # Evaluación en conjunto de prueba (Test Set)
    y_pred_test = pipeline.predict(X_test)
    y_prob_test = pipeline.predict_proba(X_test)[:, 1]

    acc_test = float(accuracy_score(y_test, y_pred_test))
    rec_test = float(recall_score(y_test, y_pred_test, zero_division=0))
    prec_test = float(precision_score(y_test, y_pred_test, zero_division=0))
    f1_test = float(f1_score(y_test, y_pred_test, zero_division=0))
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_test, labels=[0, 1]).ravel()

    print(f"• Métricas en Conjunto de Prueba (Test Set 20%, n={len(y_test)}):")
    print(f"    - Exactitud (Accuracy) : {acc_test:.4f} ({acc_test*100:.1f}%)")
    print(f"    - Precisión (Precision): {prec_test:.4f} ({prec_test*100:.1f}%)")
    print(f"    - Exhaustividad (Recall): {rec_test:.4f} ({rec_test*100:.1f}%)")
    print(f"    - Puntuación F1 (F1)   : {f1_test:.4f}")
    print(f"    - Matriz de Confusión  : TN={tn}, FP={fp}, FN={fn}, TP={tp}")

    # Validación Cruzada Estratificada de 5 Folds para medir estabilidad global sobre el dataset
    cv_5fold = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    scores_recall_cv = cross_val_score(pipeline, X, y, cv=cv_5fold, scoring="recall")
    scores_acc_cv = cross_val_score(pipeline, X, y, cv=cv_5fold, scoring="accuracy")

    # Validación comparativa SIN clima (para demostrar el aporte de las variables climáticas)
    pipe_sin_clima = Pipeline(steps=[
        ("preprocesador", ColumnTransformer([
            ("cat", OneHotEncoder(drop="first", handle_unknown="ignore"), ["Tipo_Cancha"]),
            ("num", "passthrough", ["Dia_Semana", "Hora_Num", "Historial_Cumplimiento_Cliente"]),
        ])),
        ("clasificador", RandomForestClassifier(max_depth=5, class_weight="balanced", random_state=RANDOM_STATE))
    ])
    scores_recall_sin_clima = cross_val_score(pipe_sin_clima, df_proc[FEATURES_SIN_CLIMA], y, cv=cv_5fold, scoring="recall")

    recall_medio_cv = float(scores_recall_cv.mean())
    recall_medio_sin_clima = float(scores_recall_sin_clima.mean())
    mejora_pp = round(100 * (recall_medio_cv - recall_medio_sin_clima), 2)

    print(f"\n• Validación Cruzada Estratificada (5 Folds):")
    print(f"    - Recall CON Variables Climáticas : {recall_medio_cv:.4f} ({recall_medio_cv*100:.2f}%)")
    print(f"    - Recall SIN Variables Climáticas : {recall_medio_sin_clima:.4f} ({recall_medio_sin_clima*100:.2f}%)")
    print(f"    - Aporte Neto del Clima           : +{mejora_pp:.2f} puntos porcentuales de detección")
    print(f"    - Línea base de la Evidencia 2     : {BASELINE_EVIDENCIA_2['recall_no_show']*100:.1f}%")
    print(f"    - Estado del objetivo pedagógico   : {'SUPERADO' if recall_medio_cv > BASELINE_EVIDENCIA_2['recall_no_show'] else 'NO ALCANZADO'}")

    # --------------------------------------------------------------------------
    # FASE 5: DESPLIEGUE Y EXPORTACIÓN DE ARTEFACTOS
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[FASE 5] Despliegue y Exportación de Artefactos:")

    # Reentrenamos el pipeline con la totalidad de los datos limpios para maximizar aprendizaje en producción
    pipeline_final = Pipeline(steps=[
        ("preprocesador", preprocesador),
        ("clasificador", RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            class_weight="balanced",
            random_state=RANDOM_STATE
        ))
    ])
    pipeline_final.fit(X, y)

    # Importancia de variables según el Random Forest
    try:
        feature_names = pipeline_final.named_steps["preprocesador"].get_feature_names_out()
        importancias = dict(zip(
            feature_names,
            [round(float(v), 4) for v in pipeline_final.named_steps["clasificador"].feature_importances_]
        ))
        importancias = dict(sorted(importancias.items(), key=lambda kv: -kv[1]))
    except Exception:
        importancias = {}

    # Diccionario de asignación Cancha -> Tipo_Cancha para la grilla
    cancha_tipo = df_proc.groupby("Cancha")["Tipo_Cancha"].first().to_dict()
    cancha_tipo = dict(sorted(cancha_tipo.items(), key=lambda kv: int(kv[0].split()[-1])))

    datos_holdout = {
        "accuracy": round(acc_test, 4),
        "precision_no_show": round(prec_test, 4),
        "recall_no_show": round(rec_test, 4),
        "f1_no_show": round(f1_test, 4),
        "matriz_confusion": {"TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp)},
        "n_test": len(y_test),
        "n_no_show_test": int(y_test.sum()),
    }
    cv_con = {
        "recall_no_show_media": round(recall_medio_cv, 4),
        "recall_no_show_desvio": round(float(scores_recall_cv.std()), 4),
        "accuracy_media": round(float(scores_acc_cv.mean()), 4),
    }
    cv_sin = {
        "recall_no_show_media": round(recall_medio_sin_clima, 4),
    }

    metricas_resumen = {
        "holdout_20pct": datos_holdout,
        "holdout_25pct": datos_holdout,
        "validacion_cruzada_5fold_con_clima": cv_con,
        "validacion_cruzada_repetida_5x5_con_clima": cv_con,
        "validacion_cruzada_5fold_sin_clima": cv_sin,
        "validacion_cruzada_repetida_5x5_sin_clima": cv_sin,
        "mejora_recall_por_clima_pp": mejora_pp,
        "baseline_evidencia_2": BASELINE_EVIDENCIA_2,
        "objetivo_recall_mayor_72_cumplido": bool(recall_medio_cv > BASELINE_EVIDENCIA_2["recall_no_show"]),
        "importancia_variables": importancias,
    }

    reporte = {
        "version_modelo": "esquiu3-rf-ispc-v2",
        "materia": "Práctica Profesionalizante I - ISPC",
        "docentes": "Prof. Daniela Accietto - Prof. Florencia García",
        "entrenado_en": datetime.now().isoformat(timespec="seconds"),
        "metodologia": "CRISP-DM",
        "limpieza": limpieza,
        "dataset": {
            "filas_originales": int(len(df_crudo)),
            "filas_validas": int(len(df_proc)),
            "no_show_total": int(y.sum()),
            "pct_no_show": round(100 * float(y.mean()), 2),
            "clientes_registrados": len(hist_clientes),
            "tasa_default_nuevos": round(hist_default, 4),
        },
        "variables_predictoras": FEATURES,
        "metricas": metricas_resumen,
        "umbrales_riesgo": UMBRALES_RIESGO,
    }

    # Guardar reporte JSON y modelo serializado en joblib
    REPORT_PATH.write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
    joblib.dump({
        "pipeline": pipeline_final,
        "features": FEATURES,
        "historial_clientes": hist_clientes,
        "historial_default": hist_default,
        "precios_por_tipo": limpieza["mediana_precio_por_tipo"],
        "cancha_tipo": cancha_tipo,
        "umbrales_riesgo": UMBRALES_RIESGO,
        "metricas": metricas_resumen,
        "version_modelo": reporte["version_modelo"],
        "entrenado_en": reporte["entrenado_en"],
    }, MODEL_PATH)

    print(f"• Modelo persistido exitosamente en: {MODEL_PATH.name}")
    print(f"• Reporte académico guardado en     : {REPORT_PATH.name}")
    print("=" * 80)
    print("PROCESO CRISP-DM FINALIZADO EXITOSAMENTE")
    print("=" * 80)
    return reporte


if __name__ == "__main__":
    main()
