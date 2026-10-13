"""
Esquiu3 - Pipeline de limpieza, feature engineering y entrenamiento (Evidencia 3 - MVP Beta)

Entradas : reservas_esquiu3.csv  (digitalizacion manual del cuaderno 2024-2025)
Salidas  : modelo_esquiu3.joblib        (pipeline sklearn + metadatos para la API)
           reporte_entrenamiento.json   (resumen de limpieza, metricas y comparativas)

Uso:  python train_model.py
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
from sklearn.model_selection import (GridSearchCV, RepeatedStratifiedKFold,
                                     StratifiedKFold, cross_val_predict,
                                     train_test_split)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "reservas_esquiu3.csv"
MODEL_PATH = BASE_DIR / "modelo_esquiu3.joblib"
REPORT_PATH = BASE_DIR / "reporte_entrenamiento.json"

RANDOM_STATE = 42
HORA_PICO_INICIO, HORA_PICO_FIN = 19, 23          # 19:00 a 23:00 hs
ESTADOS_NO_SHOW = {"Ausente", "Cancelada"}

# Referencia declarada en la Evidencia 2 (modelo baseline previo)
BASELINE_EVIDENCIA_2 = {"accuracy": 0.78, "recall_no_show": 0.72}

FEATURES_CAT = ["Tipo_Cancha", "Condicion_Climatica"]
FEATURES_NUM = ["Dia_Semana", "Hora_Num", "Historial_Cumplimiento_Cliente",
                "Temperatura_C", "Humedad_Pct"]
FEATURES = ["Tipo_Cancha", "Dia_Semana", "Hora_Num", "Historial_Cumplimiento_Cliente",
            "Temperatura_C", "Humedad_Pct", "Condicion_Climatica"]
FEATURES_SIN_CLIMA = ["Tipo_Cancha", "Dia_Semana", "Hora_Num", "Historial_Cumplimiento_Cliente"]

# Umbrales del semaforo predictivo (el rojo coincide con el umbral de decision 0.50 del clasificador)
UMBRALES_RIESGO = {"amarillo": 0.25, "rojo": 0.50}


# --------------------------------------------------------------------------------------
# Utilidades compartidas (tambien las usa la API)
# --------------------------------------------------------------------------------------
def categoria_cumplimiento(tasa: float) -> str:
    """Categoria legible del historial de asistencia de un cliente."""
    if tasa >= 0.85:
        return "Excelente"
    if tasa >= 0.50:
        return "Regular"
    return "Malo"


def limpiar_dataset(csv_path: Path = CSV_PATH) -> tuple[pd.DataFrame, dict]:
    """Limpia los artefactos de la digitalizacion manual. Devuelve (df_limpio, resumen_limpieza)."""
    df = pd.read_csv(csv_path, encoding="utf-8")
    total_original = len(df)

    # 1) Fechas inconsistentes (errores de tipeo al pasar el cuaderno a Excel, p.ej. ano 1900)
    fecha_parseada = pd.to_datetime(df["Fecha"], errors="coerce")
    mask_1900 = fecha_parseada.dt.year == 1900
    mask_invalida = fecha_parseada.isna() | (fecha_parseada.dt.year < 2000)
    filas_descartadas = df[mask_invalida]
    df = df[~mask_invalida].copy()
    df["Fecha"] = fecha_parseada[~mask_invalida]

    # 2) Imputacion de Monto_Abonado nulo por la mediana del precio de cada Tipo_Cancha.
    #    "Precio" = monto de turnos efectivamente cobrados (>0); un 0 significa "sin cobro", no es precio.
    nulos_antes = int(df["Monto_Abonado"].isna().sum())
    precios = (df[df["Monto_Abonado"] > 0].groupby("Tipo_Cancha")["Monto_Abonado"].median()
               .to_dict())
    df["Monto_Imputado"] = df["Monto_Abonado"].isna()
    df["Monto_Abonado"] = df["Monto_Abonado"].fillna(df["Tipo_Cancha"].map(precios))

    resumen = {
        "filas_originales": int(total_original),
        "filas_descartadas_fecha_invalida": int(mask_invalida.sum()),
        "filas_descartadas_anio_1900": int(mask_1900.sum()),
        "fechas_descartadas": filas_descartadas["Fecha"].tolist(),
        "filas_resultantes": int(len(df)),
        "nulos_monto_abonado": nulos_antes,
        "pct_nulos_monto_abonado": round(100 * nulos_antes / total_original, 2),
        "nulos_monto_restantes": int(df["Monto_Abonado"].isna().sum()),
        "mediana_precio_por_tipo": {k: float(v) for k, v in precios.items()},
    }
    return df.reset_index(drop=True), resumen


def ingenieria_caracteristicas(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega Dia_Semana, Hora_Num, Es_Fin_De_Semana, Es_Horario_Pico y la variable objetivo No_Show."""
    df = df.copy()
    df["Dia_Semana"] = df["Fecha"].dt.dayofweek                       # 0 = lunes ... 6 = domingo
    df["Hora_Num"] = df["Hora"].str.split(":").str[0].astype(int)
    df["Es_Fin_De_Semana"] = (df["Dia_Semana"] >= 5).astype(int)
    df["Es_Horario_Pico"] = df["Hora_Num"].between(HORA_PICO_INICIO, HORA_PICO_FIN - 1).astype(int)
    df["No_Show"] = df["Estado_Reserva"].isin(ESTADOS_NO_SHOW).astype(int)
    return df


def calcular_historial_cumplimiento(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, float]:
    """
    Historial_Cumplimiento_Cliente = tasa de asistencia previa del cliente.

    * Para ENTRENAR se calcula de forma dinamica y sin fuga de informacion (data leakage):
      cada reserva solo "ve" el comportamiento ANTERIOR de su cliente (ventana expansiva).
    * Para INFERIR se usa el diccionario con el historial completo; clientes nuevos reciben
      el valor por defecto (mediana de las tasas observadas).
    """
    df = df.sort_values(["Fecha", "Hora_Num", "Cancha"], kind="stable").reset_index(drop=True)
    asistio = 1 - df["No_Show"]
    previas = asistio.groupby(df["Cliente_ID"]).cumsum() - asistio
    n_previas = df.groupby("Cliente_ID").cumcount()
    tasa_previa = (previas / n_previas.replace(0, np.nan))

    # Valor por defecto = mediana de las tasas historicas finales por cliente
    resumen_cli = df.groupby("Cliente_ID").agg(n=("No_Show", "size"), asistidas=("No_Show", lambda s: int((1 - s).sum())))
    resumen_cli["tasa"] = resumen_cli["asistidas"] / resumen_cli["n"]
    default = float(resumen_cli["tasa"].median())

    df["Historial_Cumplimiento_Cliente"] = tasa_previa.fillna(default)
    df["Historial_Categoria"] = df["Historial_Cumplimiento_Cliente"].map(categoria_cumplimiento)

    diccionario = {
        cid: {"tasa": round(float(r.tasa), 4), "n_reservas": int(r.n),
              "categoria": categoria_cumplimiento(float(r.tasa))}
        for cid, r in resumen_cli.iterrows()
    }
    return df, diccionario, default


def construir_pipeline(features: list[str], **rf_params) -> Pipeline:
    cat = [c for c in features if c in FEATURES_CAT]
    num = [c for c in features if c in FEATURES_NUM]
    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), cat), ("num", "passthrough", num)]
    )
    rf = RandomForestClassifier(random_state=RANDOM_STATE, n_jobs=1, **rf_params)
    return Pipeline([("pre", pre), ("rf", rf)])


def _metricas(y_true, y_pred) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_no_show": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall_no_show": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1_no_show": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "matriz_confusion": {"TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp)},
    }


def _refit_recall_con_piso_accuracy(cv_results: dict) -> int:
    """Elige el candidato con mayor Recall (No_Show) cuya Accuracy no caiga bajo el baseline (78%)."""
    rec = np.array(cv_results["mean_test_recall"])
    acc = np.array(cv_results["mean_test_accuracy"])
    f1 = np.array(cv_results["mean_test_f1"])
    ok = acc >= BASELINE_EVIDENCIA_2["accuracy"]
    candidatos = np.where(ok)[0] if ok.any() else np.arange(len(rec))
    # orden: recall desc, f1 desc, menor complejidad (indice del grid) asc
    orden = sorted(candidatos, key=lambda i: (-round(rec[i], 6), -round(f1[i], 6), i))
    return int(orden[0])


def cv_repetida(features: list[str], params: dict, X: pd.DataFrame, y: pd.Series) -> dict:
    """Validacion cruzada estratificada repetida (5x5) -> estimacion mas estable que un unico hold-out."""
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=RANDOM_STATE)
    rec, acc, pre = [], [], []
    for tr, te in cv.split(X, y):
        pipe = construir_pipeline(features, **params).fit(X.iloc[tr][features], y.iloc[tr])
        pred = pipe.predict(X.iloc[te][features])
        rec.append(recall_score(y.iloc[te], pred, zero_division=0))
        acc.append(accuracy_score(y.iloc[te], pred))
        pre.append(precision_score(y.iloc[te], pred, zero_division=0))
    return {"recall_no_show_media": round(float(np.mean(rec)), 4), "recall_no_show_desvio": round(float(np.std(rec)), 4),
            "accuracy_media": round(float(np.mean(acc)), 4), "accuracy_desvio": round(float(np.std(acc)), 4),
            "precision_no_show_media": round(float(np.mean(pre)), 4), "n_evaluaciones": len(rec)}


# --------------------------------------------------------------------------------------
# Entrenamiento
# --------------------------------------------------------------------------------------
def main() -> dict:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore")

    print("=" * 78)
    print("ESQUIU3 - PIPELINE DE ENTRENAMIENTO (Evidencia 3 / MVP Beta)")
    print("=" * 78)

    # ---- 1. Limpieza ----
    df, limpieza = limpiar_dataset()
    print(f"[Limpieza] filas originales               : {limpieza['filas_originales']}")
    print(f"[Limpieza] descartadas por fecha invalida : {limpieza['filas_descartadas_fecha_invalida']} "
          f"(ano 1900: {limpieza['filas_descartadas_anio_1900']}) -> {limpieza['fechas_descartadas']}")
    print(f"[Limpieza] nulos en Monto_Abonado imputados: {limpieza['nulos_monto_abonado']} "
          f"({limpieza['pct_nulos_monto_abonado']}%) con medianas {limpieza['mediana_precio_por_tipo']}")
    print(f"[Limpieza] filas resultantes              : {limpieza['filas_resultantes']}")

    # ---- 2. Feature engineering ----
    df = ingenieria_caracteristicas(df)
    df, hist_clientes, hist_default = calcular_historial_cumplimiento(df)
    print(f"[Features] clientes conocidos: {len(hist_clientes)} | valor por defecto (mediana) para nuevos: {hist_default:.3f}")
    print(f"[Features] No_Show: {int(df['No_Show'].sum())} de {len(df)} ({100 * df['No_Show'].mean():.1f}%)")

    X, y = df[FEATURES + ["Es_Fin_De_Semana", "Es_Horario_Pico"]], df["No_Show"]

    # ---- 3. Hold-out estratificado + GridSearchCV (solo sobre train) ----
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE)
    grid = {
        "rf__n_estimators": [100, 300],
        "rf__max_depth": [None, 4, 6, 8],
        "rf__min_samples_leaf": [1, 2, 4],
        "rf__max_features": ["sqrt", None],
        "rf__class_weight": ["balanced", "balanced_subsample"],
    }
    scoring = {"recall": "recall", "accuracy": "accuracy", "f1": "f1", "precision": "precision"}
    gs = GridSearchCV(construir_pipeline(FEATURES), grid, scoring=scoring,
                      refit=_refit_recall_con_piso_accuracy,
                      cv=StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE), n_jobs=-1)
    gs.fit(X_tr[FEATURES], y_tr)
    mejores = {k.replace("rf__", ""): v for k, v in gs.best_params_.items()}
    print(f"[GridSearch] {len(gs.cv_results_['params'])} combinaciones x 5 folds | mejores parametros: {mejores}")
    print(f"[GridSearch] CV(train): recall={gs.cv_results_['mean_test_recall'][gs.best_index_]:.3f} "
          f"accuracy={gs.cv_results_['mean_test_accuracy'][gs.best_index_]:.3f}")

    met_holdout = _metricas(y_te, gs.best_estimator_.predict(X_te[FEATURES]))
    met_holdout["n_test"] = int(len(y_te))
    met_holdout["n_no_show_test"] = int(y_te.sum())

    # ---- 4. Estimacion mas estable: CV repetida (con y sin variables climaticas) ----
    cv_con_clima = cv_repetida(FEATURES, mejores, X, y)
    cv_sin_clima = cv_repetida(FEATURES_SIN_CLIMA, mejores, X, y)
    # Predicciones out-of-fold (para la matriz de confusion global)
    oof = cross_val_predict(construir_pipeline(FEATURES, **mejores), X[FEATURES], y,
                            cv=StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE))
    met_oof = _metricas(y, oof)

    # ---- 5. Modelo final: se reentrena con TODOS los datos limpios ----
    final = construir_pipeline(FEATURES, **mejores).fit(X[FEATURES], y)
    importancias = dict(zip(
        final.named_steps["pre"].get_feature_names_out(),
        [round(float(v), 4) for v in final.named_steps["rf"].feature_importances_]))
    importancias = dict(sorted(importancias.items(), key=lambda kv: -kv[1]))

    objetivo_cumplido = bool(met_holdout["recall_no_show"] > BASELINE_EVIDENCIA_2["recall_no_show"]
                             and cv_con_clima["recall_no_show_media"] > BASELINE_EVIDENCIA_2["recall_no_show"])

    # ---- 6. Catalogo operativo para la API (cancha -> tipo, precios) ----
    cancha_tipo = (df.groupby("Cancha")["Tipo_Cancha"].first().to_dict())
    cancha_tipo = dict(sorted(cancha_tipo.items(), key=lambda kv: int(kv[0].split()[-1])))

    metricas = {
        "holdout_25pct": met_holdout,
        "validacion_cruzada_repetida_5x5_con_clima": cv_con_clima,
        "validacion_cruzada_repetida_5x5_sin_clima": cv_sin_clima,
        "out_of_fold_5fold_dataset_completo": met_oof,
        "mejora_recall_por_clima_pp": round(100 * (cv_con_clima["recall_no_show_media"] - cv_sin_clima["recall_no_show_media"]), 2),
        "baseline_evidencia_2": BASELINE_EVIDENCIA_2,
        "objetivo_recall_mayor_72_cumplido": objetivo_cumplido,
        "importancia_variables": importancias,
    }
    reporte = {
        "version_modelo": "esquiu3-rf-beta-1.0",
        "entrenado_en": datetime.now().isoformat(timespec="seconds"),
        "limpieza": limpieza,
        "dataset": {"filas_entrenamiento": int(len(df)), "no_show": int(y.sum()),
                    "pct_no_show": round(100 * float(y.mean()), 2), "clientes_conocidos": len(hist_clientes),
                    "historial_default_nuevos": round(hist_default, 4),
                    "periodo": [str(df["Fecha"].min().date()), str(df["Fecha"].max().date())]},
        "variables_predictoras": FEATURES,
        "mejores_hiperparametros": mejores,
        "metricas": metricas,
        "umbrales_riesgo": UMBRALES_RIESGO,
        "advertencia": ("Dataset pequeno (<100 reservas validas): las metricas tienen alta varianza; "
                        "se reportan hold-out y validacion cruzada repetida."),
    }
    REPORT_PATH.write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")

    joblib.dump({
        "pipeline": final,
        "features": FEATURES,
        "historial_clientes": hist_clientes,
        "historial_default": hist_default,
        "precios_por_tipo": limpieza["mediana_precio_por_tipo"],
        "cancha_tipo": cancha_tipo,
        "umbrales_riesgo": UMBRALES_RIESGO,
        "metricas": metricas,
        "version_modelo": reporte["version_modelo"],
        "entrenado_en": reporte["entrenado_en"],
    }, MODEL_PATH)

    # ---- 7. Resumen por consola ----
    print("-" * 78)
    h = met_holdout
    print(f"[Hold-out 25% n={h['n_test']}, No_Show={h['n_no_show_test']}] accuracy={h['accuracy']:.3f} "
          f"precision={h['precision_no_show']:.3f} RECALL={h['recall_no_show']:.3f} f1={h['f1_no_show']:.3f} "
          f"conf={h['matriz_confusion']}")
    print(f"[CV repetida 5x5 CON clima] recall={cv_con_clima['recall_no_show_media']:.3f} "
          f"(+/-{cv_con_clima['recall_no_show_desvio']:.3f}) accuracy={cv_con_clima['accuracy_media']:.3f}")
    print(f"[CV repetida 5x5 SIN clima] recall={cv_sin_clima['recall_no_show_media']:.3f} "
          f"(+/-{cv_sin_clima['recall_no_show_desvio']:.3f}) accuracy={cv_sin_clima['accuracy_media']:.3f}")
    print(f"[Mejora por variables climaticas] {metricas['mejora_recall_por_clima_pp']:+.2f} pp de Recall")
    print(f"[Baseline Evidencia 2] accuracy={BASELINE_EVIDENCIA_2['accuracy']:.2f} recall={BASELINE_EVIDENCIA_2['recall_no_show']:.2f}")
    print(f"[OBJETIVO Recall > 72%] {'CUMPLIDO' if objetivo_cumplido else 'NO CUMPLIDO'}")
    print(f"[Top variables] {list(importancias.items())[:5]}")
    print(f"[Salida] {MODEL_PATH.name} | {REPORT_PATH.name}")
    return reporte


if __name__ == "__main__":
    main()
