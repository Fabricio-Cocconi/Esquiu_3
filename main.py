"""
Esquiu3 - API REST de integracion (FastAPI) - Evidencia 3 / MVP Beta

Conecta: cuaderno digitalizado (CSV limpio) + modelo Random Forest (joblib) + reglas de negocio + UI web.

Ejecutar:  uvicorn main:app --reload      ->  http://127.0.0.1:8000
Docs API:  http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import html
import re
import threading
import time
import unicodedata
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import train_model as tm

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

HORAS_GRILLA = [f"{h:02d}:00" for h in range(14, 23)]      # turnos de 60 min: 14:00 ... 22:00 (cierre 23:00)
CONDICIONES = ["Despejado", "Nublado", "Lluvia", "Frío Extremo"]
TIPOS = ["Fútbol 5", "Fútbol 7", "Fútbol 11", "Pádel"]
ROLES_VALIDOS = {"Admin", "Recepcionista"}
PORCENTAJE_SENA = 0.50

ACCIONES = {
    "rojo": "Exigir seña obligatoria del 50% y enviar recordatorio automático por WhatsApp",
    "amarillo": "Enviar recordatorio automático por WhatsApp 24 hs antes y sugerir seña voluntaria",
    "verde": "Sin acción adicional: confirmar el turno de forma estándar",
}
NIVELES = {"rojo": "Rojo - Alto", "amarillo": "Amarillo - Medio", "verde": "Verde - Bajo"}


# ======================================================================================
# Seguridad: sanitizacion y normalizacion
# ======================================================================================
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitizar_texto(valor: str | None, max_len: int = 300) -> str:
    """Defensa XSS: elimina caracteres de control y ESCAPA &, <, >, ", ' (html.escape)."""
    if valor is None:
        return ""
    limpio = _CTRL.sub("", str(valor)).strip()[:max_len]
    return html.escape(limpio, quote=True)


def _sin_acentos(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn").lower().strip()


def _normalizar_opcion(valor: str, opciones: list[str], nombre: str) -> str:
    mapa = {_sin_acentos(o): o for o in opciones}
    clave = _sin_acentos(valor)
    if clave not in mapa:
        raise ValueError(f"{nombre} invalido. Valores permitidos: {', '.join(opciones)}")
    return mapa[clave]


def _pct(p: float) -> str:
    """Porcentaje legible: nunca muestra 0% ni 100% absolutos (el modelo no es infalible)."""
    if p >= 0.995:
        return "más del 99%"
    if p < 0.005:
        return "menos del 1%"
    return f"{p:.0%}"


# ======================================================================================
# Servicio de modelo (carga el joblib; entrena si no existe)
# ======================================================================================
class ServicioModelo:
    def __init__(self) -> None:
        if not tm.MODEL_PATH.exists():
            tm.main()
        self.bundle = joblib.load(tm.MODEL_PATH)
        self.pipeline = self.bundle["pipeline"]
        self.hist = {k.upper(): v for k, v in self.bundle["historial_clientes"].items()}
        self.hist_default: float = self.bundle["historial_default"]
        self.precios: dict = self.bundle["precios_por_tipo"]
        self.umbrales: dict = self.bundle["umbrales_riesgo"]
        self.cancha_tipo: dict = self.bundle["cancha_tipo"]
        self.clima_hist: dict = {}          # lo completa ReservaStore: {condicion: {n, no_show, pct}}

    def historial(self, cliente_id: str) -> tuple[float, bool, str]:
        """(tasa, es_nuevo, categoria). Cliente desconocido -> valor por defecto (mediana), sin error."""
        info = self.hist.get(str(cliente_id).strip().upper())
        if info is None:
            return self.hist_default, True, tm.categoria_cumplimiento(self.hist_default)
        return float(info["tasa"]), False, info["categoria"]

    def nivel(self, p: float) -> str:
        if p >= self.umbrales["rojo"]:
            return "rojo"
        if p >= self.umbrales["amarillo"]:
            return "amarillo"
        return "verde"

    def predecir_lote(self, filas: list[dict]) -> list[float]:
        df = pd.DataFrame(filas)[tm.FEATURES]
        return [float(p) for p in self.pipeline.predict_proba(df)[:, 1]]

    def predecir(self, *, tipo: str, fecha: date, hora: str, cliente_id: str, condicion: str,
                 temperatura: float, humedad: float) -> dict:
        tasa, nuevo, categoria = self.historial(cliente_id)
        hora_num = int(hora.split(":")[0])
        base = {
            "Tipo_Cancha": tipo, "Dia_Semana": fecha.weekday(), "Hora_Num": hora_num,
            "Historial_Cumplimiento_Cliente": tasa, "Temperatura_C": temperatura,
            "Humedad_Pct": humedad, "Condicion_Climatica": condicion,
        }
        p = self.predecir_lote([base])[0]
        color = self.nivel(p)
        factores = []
        if condicion == "Lluvia":
            factores.append("Pronóstico de lluvia")
        if condicion == "Frío Extremo" or temperatura <= 8:
            factores.append("Frío extremo")
        if tm.HORA_PICO_INICIO <= hora_num < tm.HORA_PICO_FIN:
            factores.append("Horario pico (19-23 hs)")
        if nuevo:
            factores.append("Cliente nuevo: sin historial (valor por defecto)")
        elif categoria == "Malo":
            factores.append("Historial de faltas del cliente")
        elif categoria == "Excelente":
            factores.append("Cliente con historial excelente")
        precio = float(self.precios.get(tipo, 0))
        analisis = self._analisis_clima(base, p, condicion, temperatura, humedad)
        return {
            "probabilidad_noshow": round(p, 4),
            "nivel_riesgo": NIVELES[color],
            "color": color,
            "accion_preventiva": ACCIONES[color],
            "requiere_sena": color == "rojo",
            "monto_sena": round(precio * PORCENTAJE_SENA) if color == "rojo" else 0,
            "precio_turno": precio,
            "cliente_nuevo": nuevo,
            "historial_cumplimiento": round(tasa, 4),
            "categoria_historial": categoria,
            "factores": factores,
            "analisis_clima": analisis,
            "version_modelo": self.bundle["version_modelo"],
        }

    # -- analisis del clima elegido por el usuario ------------------------------------
    REFERENCIA_CLIMA = {"Condicion_Climatica": "Despejado", "Temperatura_C": 22.0, "Humedad_Pct": 55.0}

    def _analisis_clima(self, base: dict, p: float, condicion: str, temp: float, hum: float) -> dict:
        """Compara el turno con otros climas (todo lo demas igual) y lo explica en lenguaje llano."""
        filas = [{**base, "Condicion_Climatica": c} for c in CONDICIONES] + [{**base, **self.REFERENCIA_CLIMA}]
        probs = self.predecir_lote(filas)
        escenarios = [{"condicion": c, "probabilidad": round(pc, 4), "color": self.nivel(pc), "es_el_elegido": c == condicion}
                      for c, pc in zip(CONDICIONES, probs[:-1])]
        p_ref = probs[-1]
        dif_pp = round((p - p_ref) * 100, 1)
        hist = self.clima_hist.get(condicion)

        e = [f"Clima ingresado: {condicion}, {temp:g} °C y {hum:g}% de humedad. Con ese clima el modelo estima una "
             f"probabilidad de {_pct(p)} de que el turno no se use (ausencia o cancelación).",
             f"Como punto de comparación, el mismo turno en un día despejado típico (22 °C, 55% de humedad) tendría {_pct(p_ref)}."]
        if abs(dif_pp) < 5:
            e.append(f"Conclusión: el clima ingresado casi no cambia el riesgo de este turno (diferencia de {dif_pp:+g} puntos). "
                     "Pesan más otros datos, como la hora o el historial del cliente.")
        elif dif_pp > 0:
            e.append(f"Conclusión: el clima ingresado AUMENTA el riesgo en {dif_pp:g} puntos porcentuales respecto de un día despejado.")
        else:
            e.append(f"Conclusión: el clima ingresado REDUCE el riesgo en {abs(dif_pp):g} puntos porcentuales respecto de un día despejado.")
        if hist and hist["n"]:
            e.append(f"Qué pasó en el cuaderno: de {hist['n']} reservas con clima '{condicion}', {hist['no_show']} ({hist['pct']:.0f}%) "
                     "terminaron en ausencia o cancelación.")
        else:
            e.append(f"En el cuaderno no hay reservas con clima '{condicion}', por lo que el modelo no tiene ejemplos para ese caso.")
        cautela = ("Ojo: el modelo aprendió de pocas reservas (menos de 100). Sirve como guía para decidir si pedir seña, "
                   "no como una predicción exacta.")
        if hist and 0 < hist["n"] < 15:
            cautela += f" Además, hay solo {hist['n']} casos con '{condicion}' en el historial."
        return {"ingresado": {"condicion": condicion, "temperatura_c": temp, "humedad_pct": hum},
                "probabilidad_ingresado": round(p, 4), "probabilidad_referencia": round(p_ref, 4), "diferencia_pp": dif_pp,
                "escenarios": escenarios, "historico_cuaderno": hist, "explicacion": e, "advertencia": cautela}


# ======================================================================================
# Almacen de reservas (en memoria, sembrado con el cuaderno digitalizado limpio)
# ======================================================================================
class ReservaStore:
    def __init__(self, modelo: ServicioModelo) -> None:
        self.modelo = modelo
        self.lock = threading.RLock()
        self.df_limpio, self.limpieza = tm.limpiar_dataset()
        self.df_crudo = pd.read_csv(tm.CSV_PATH, encoding="utf-8")
        self.reservas: list[dict] = []
        self.contador = Counter()
        _h = tm.ingenieria_caracteristicas(self.df_limpio).groupby("Condicion_Climatica")["No_Show"].agg(["size", "sum"])
        self.modelo.clima_hist = {c: {"n": int(r["size"]), "no_show": int(r["sum"]),
                                      "pct": round(100 * float(r["sum"]) / int(r["size"]), 1)} for c, r in _h.iterrows()}
        self.reset()

    # -- sembrado historico ------------------------------------------------------------
    def _sembrar_historico(self) -> list[dict]:
        df = self.df_limpio
        filas = [{
            "Tipo_Cancha": r.Tipo_Cancha, "Dia_Semana": r.Fecha.weekday(), "Hora_Num": int(r.Hora[:2]),
            "Historial_Cumplimiento_Cliente": self.modelo.historial(r.Cliente_ID)[0],
            "Temperatura_C": r.Temperatura_C, "Humedad_Pct": r.Humedad_Pct, "Condicion_Climatica": r.Condicion_Climatica,
        } for r in df.itertuples()]
        probs = self.modelo.predecir_lote(filas)
        out = []
        for i, (r, p) in enumerate(zip(df.itertuples(), probs), start=1):
            color = self.modelo.nivel(p)
            out.append({
                "id": f"H-{i:04d}", "origen": "cuaderno", "Cancha": r.Cancha, "Tipo_Cancha": r.Tipo_Cancha,
                "Fecha": r.Fecha.date().isoformat(), "Hora": r.Hora, "Cliente_ID": sanitizar_texto(r.Cliente_ID),
                "Condicion_Climatica": r.Condicion_Climatica, "Temperatura_C": float(r.Temperatura_C),
                "Humedad_Pct": float(r.Humedad_Pct), "Anotacion_Cuaderno": sanitizar_texto(r.Anotacion_Cuaderno),
                "Estado_Reserva": r.Estado_Reserva, "Monto_Abonado": float(r.Monto_Abonado),
                "prediccion": {"probabilidad_noshow": round(p, 4), "color": color, "nivel_riesgo": NIVELES[color]},
            })
        return out

    def reset(self) -> None:
        """Restaura el estado inicial (cuaderno historico) y los contadores. Util para pruebas."""
        with self.lock:
            self.reservas = self._sembrar_historico()
            self.contador = Counter()
            self._seq = 0

    # -- disponibilidad --------------------------------------------------------------
    @staticmethod
    def _minutos(hora: str) -> int:
        h, m = hora.split(":")
        return int(h) * 60 + int(m)

    def conflicto(self, cancha: str, fecha: str, hora: str, duracion_min: int = 60) -> dict | None:
        """Devuelve la reserva que bloquea el horario (duplicada o solapada) o None. Las canceladas liberan el turno."""
        ini = self._minutos(hora)
        for r in self.reservas:
            if r["Cancha"] != cancha or r["Fecha"] != fecha or r["Estado_Reserva"] == "Cancelada":
                continue
            otro = self._minutos(r["Hora"])
            if ini < otro + duracion_min and otro < ini + duracion_min:      # interseccion de intervalos
                return r
        return None

    def verificar_disponibilidad(self, cancha: str, fecha: str, hora: str) -> None:
        """Lanza HTTP 409 'Horario no disponible' si el turno esta duplicado o solapado."""
        choque = self.conflicto(cancha, fecha, hora)
        if choque:
            self.contador["bloqueos_409"] += 1
            raise HTTPException(409, detail={
                "codigo": "HORARIO_NO_DISPONIBLE",
                "mensaje": f"Horario no disponible: {cancha} ya está reservada el {fecha} a las "
                           f"{choque['Hora']} (reserva {choque['id']}).",
                "reserva_existente": choque["id"],
            })

    def crear(self, data: dict) -> dict:
        with self.lock:                      # check + insert atomico (evita doble reserva concurrente)
            self.verificar_disponibilidad(data["Cancha"], data["Fecha"], data["Hora"])
            self._seq += 1
            data.update({"id": f"R-{self._seq:04d}", "origen": "mvp", "Estado_Reserva": "Confirmada",
                         "sena_pagada": False, "whatsapp_enviado": False,
                         "creada_en": datetime.now().isoformat(timespec="seconds")})
            self.reservas.append(data)
            self.contador["reservas_creadas"] += 1
            return data

    def buscar(self, rid: str) -> dict | None:
        return next((r for r in self.reservas if r["id"] == rid), None)


modelo = ServicioModelo()
store = ReservaStore(modelo)


# ======================================================================================
# Servicio climatico SIMULADO (con fallback ante caida)
# ======================================================================================
class ClimaNoDisponible(Exception):
    pass


def _clima_simulado(fecha: date, simular_caida: bool) -> dict:
    if simular_caida:
        raise ClimaNoDisponible("Servicio climático simulado fuera de línea")
    rng = np.random.default_rng(fecha.toordinal())
    base = 18 + 8 * np.cos((fecha.timetuple().tm_yday - 15) / 365 * 2 * np.pi)       # Cordoba: verano calido, invierno frio
    temp = float(round(base + rng.normal(0, 3), 1))
    cond = str(rng.choice(["Despejado", "Nublado", "Lluvia"], p=[0.6, 0.25, 0.15]))
    if temp <= 8:
        cond = "Frío Extremo"
    hum = int(np.clip(rng.normal(88 if cond == "Lluvia" else 58, 8), 35, 98))
    return {"Condicion_Climatica": cond, "Temperatura_C": temp, "Humedad_Pct": hum}


def _clima_fallback(fecha: date) -> dict:
    """Fallback: promedios historicos del cuaderno para el mes consultado (o globales si no hay datos)."""
    df = store.df_limpio
    mes = df[df["Fecha"].dt.month == fecha.month]
    base = mes if len(mes) >= 3 else df
    return {"Condicion_Climatica": str(base["Condicion_Climatica"].mode().iloc[0]),
            "Temperatura_C": float(round(base["Temperatura_C"].mean(), 1)),
            "Humedad_Pct": int(round(base["Humedad_Pct"].mean()))}


# ======================================================================================
# Esquemas
# ======================================================================================
class PrediccionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    Cancha: str = Field(..., min_length=1, max_length=20, examples=["Cancha 5"])
    Tipo_Cancha: str = Field(..., examples=["Fútbol 7"])
    Fecha: date = Field(..., examples=["2026-11-02"])
    Hora: str = Field(..., examples=["21:00"])
    Cliente_ID: str = Field(..., min_length=1, max_length=64, examples=["CLI-103"])
    Condicion_Climatica: str = Field(..., examples=["Lluvia"])
    Temperatura_C: float = Field(..., ge=-15, le=50)
    Humedad_Pct: float = Field(..., ge=0, le=100)

    @field_validator("Cancha")
    @classmethod
    def _cancha(cls, v: str) -> str:
        m = re.fullmatch(r"(?i)(?:cancha\s*)?(\d{1,2})", v)
        nombre = f"Cancha {int(m.group(1))}" if m else None
        if nombre not in modelo.cancha_tipo:
            raise ValueError("Cancha invalida. Valores permitidos: Cancha 1 ... Cancha 13")
        return nombre

    @field_validator("Tipo_Cancha")
    @classmethod
    def _tipo(cls, v: str) -> str:
        return _normalizar_opcion(v, TIPOS, "Tipo_Cancha")

    @field_validator("Condicion_Climatica")
    @classmethod
    def _clima(cls, v: str) -> str:
        return _normalizar_opcion(v, CONDICIONES, "Condicion_Climatica")

    @field_validator("Hora")
    @classmethod
    def _hora(cls, v: str) -> str:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
        if not m:
            raise ValueError("Hora invalida. Formato esperado HH:MM")
        h, mi = int(m.group(1)), int(m.group(2))
        if mi != 0 or not (14 <= h <= 22):
            raise ValueError("Los turnos son de 60 min en punto entre 14:00 y 22:00 (cierre 23:00)")
        return f"{h:02d}:{mi:02d}"

    @model_validator(mode="after")
    def _coherencia(self):
        esperado = modelo.cancha_tipo.get(self.Cancha)
        if esperado and esperado != self.Tipo_Cancha:
            raise ValueError(f"{self.Cancha} es de tipo '{esperado}', no '{self.Tipo_Cancha}'")
        return self


class ReservaIn(PrediccionIn):
    Anotacion_Cuaderno: str = Field("", max_length=300)


# ======================================================================================
# Aplicacion
# ======================================================================================
app = FastAPI(
    title="Esquiu3 - API de Reservas y Predicción de No-Show",
    description="MVP Beta (Evidencia 3 - ISPC 2026 - Grupo Nº 6). Integra cuaderno digitalizado, Random Forest y reglas de negocio.",
    version="1.0.0-beta",
)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none'")
    return resp


@app.exception_handler(RequestValidationError)
async def validacion_handler(request: Request, exc: RequestValidationError):
    errores = [{"campo": ".".join(str(x) for x in e["loc"][1:]) or "body",
                "mensaje": str(e["msg"]).replace("Value error, ", "")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": {"codigo": "DATOS_INVALIDOS",
                        "mensaje": "; ".join(f"{e['campo']}: {e['mensaje']}" for e in errores), "errores": errores}})


def requiere_admin(x_role: str | None = Header(default=None, alias="X-Role")) -> str:
    """RBAC simulado por header: Admin -> ok | Recepcionista -> 403 | ausente -> 401."""
    if x_role is None:
        store.contador["accesos_401"] += 1
        raise HTTPException(401, detail={"codigo": "NO_AUTENTICADO", "mensaje": "Falta el header X-Role"})
    if x_role not in ROLES_VALIDOS or x_role != "Admin":
        store.contador["accesos_denegados_403"] += 1
        raise HTTPException(403, detail={"codigo": "ACCESO_DENEGADO",
                                         "mensaje": f"El rol '{sanitizar_texto(x_role, 30)}' no tiene permiso para este recurso (se requiere Admin)"})
    return x_role


def _prediccion_de(d: PrediccionIn) -> dict:
    return modelo.predecir(tipo=d.Tipo_Cancha, fecha=d.Fecha, hora=d.Hora, cliente_id=d.Cliente_ID,
                           condicion=d.Condicion_Climatica, temperatura=d.Temperatura_C, humedad=d.Humedad_Pct)


@app.get("/api/v1/health", tags=["Sistema"])
@app.get("/v1/health", tags=["Sistema"], include_in_schema=False)
@app.get("/api/health", tags=["Sistema"], include_in_schema=False)
@app.get("/health", tags=["Sistema"], include_in_schema=False)
def health():
    return {"estado": "ok", "modelo": modelo.bundle["version_modelo"], "entrenado_en": modelo.bundle["entrenado_en"]}


@app.get("/api/v1/catalogo", tags=["Sistema"])
@app.get("/v1/catalogo", tags=["Sistema"], include_in_schema=False)
def catalogo():
    clientes = sorted(({"id": k, "tasa": v["tasa"], "n_reservas": v["n_reservas"], "categoria": v["categoria"]}
                       for k, v in modelo.bundle["historial_clientes"].items()), key=lambda c: c["id"])
    return {"canchas": [{"nombre": c, "tipo": t} for c, t in modelo.cancha_tipo.items()], "tipos": TIPOS,
            "condiciones": CONDICIONES, "horas": HORAS_GRILLA, "precios": modelo.precios, "clientes": clientes,
            "umbrales_riesgo": modelo.umbrales, "porcentaje_sena": PORCENTAJE_SENA}


@app.post("/api/v1/reservas/predict", tags=["Predicción"])
@app.post("/v1/reservas/predict", tags=["Predicción"], include_in_schema=False)
def predecir(d: PrediccionIn):
    t0 = time.perf_counter()
    res = _prediccion_de(d)
    store.contador["predicciones"] += 1
    store.contador["latencia_ms_acum"] += (time.perf_counter() - t0) * 1000
    return res


@app.post("/api/v1/reservas", status_code=201, tags=["Reservas"])
@app.post("/v1/reservas", status_code=201, tags=["Reservas"], include_in_schema=False)
def crear_reserva(d: ReservaIn):
    cliente = sanitizar_texto(d.Cliente_ID, 64)                       # XSS: escape ANTES de persistir
    nota = sanitizar_texto(d.Anotacion_Cuaderno, 300)
    store.verificar_disponibilidad(d.Cancha, d.Fecha.isoformat(), d.Hora)   # falla rapido (se repite atomico al insertar)
    pred = _prediccion_de(d)
    reserva = store.crear({
        "Cancha": d.Cancha, "Tipo_Cancha": d.Tipo_Cancha, "Fecha": d.Fecha.isoformat(), "Hora": d.Hora,
        "Cliente_ID": cliente, "Anotacion_Cuaderno": nota, "Condicion_Climatica": d.Condicion_Climatica,
        "Temperatura_C": d.Temperatura_C, "Humedad_Pct": d.Humedad_Pct, "prediccion": pred,
    })
    return {"mensaje": "Reserva registrada correctamente", "reserva": reserva, "prediccion": pred}


@app.post("/api/v1/reservas/{reserva_id}/sena", tags=["Reservas"])
@app.post("/v1/reservas/{reserva_id}/sena", tags=["Reservas"], include_in_schema=False)
def registrar_sena(reserva_id: str):
    r = store.buscar(sanitizar_texto(reserva_id, 20))
    if not r or r["origen"] != "mvp":
        raise HTTPException(404, detail={"codigo": "NO_ENCONTRADA", "mensaje": "Reserva no encontrada"})
    r["sena_pagada"] = True
    return {"mensaje": "Seña registrada", "id": r["id"], "monto_sena": r["prediccion"]["monto_sena"]}


@app.post("/api/v1/reservas/{reserva_id}/recordatorio-whatsapp", tags=["Reservas"])
@app.post("/v1/reservas/{reserva_id}/recordatorio-whatsapp", tags=["Reservas"], include_in_schema=False)
def recordatorio_whatsapp(reserva_id: str):
    """Pasarela de WhatsApp SIMULADA: no envia mensajes reales (limitacion conocida de la Beta)."""
    r = store.buscar(sanitizar_texto(reserva_id, 20))
    if not r or r["origen"] != "mvp":
        raise HTTPException(404, detail={"codigo": "NO_ENCONTRADA", "mensaje": "Reserva no encontrada"})
    r["whatsapp_enviado"] = True
    texto = (f"Hola {r['Cliente_ID']}! Te recordamos tu turno en Esquiu3: {r['Cancha']} el {r['Fecha']} a las {r['Hora']} hs. "
             f"Por favor confirmá tu asistencia respondiendo SI. Si no vas a poder venir, avisanos con anticipación.")
    return {"estado": "SIMULADO", "mensaje_enviado": texto, "detalle": "Mensaje no enviado a ningún número real (pasarela simulada)"}


@app.get("/api/v1/clima/pronostico", tags=["Clima"])
@app.get("/v1/clima/pronostico", tags=["Clima"], include_in_schema=False)
def pronostico(fecha: date, simular_caida: bool = False):

    try:
        return {**_clima_simulado(fecha, simular_caida), "fuente": "servicio_climatico_simulado", "fallback": False}
    except ClimaNoDisponible:
        return {**_clima_fallback(fecha), "fuente": "fallback_promedios_historicos_del_cuaderno", "fallback": True}


def _estadisticas_cuaderno() -> dict:
    df = tm.ingenieria_caracteristicas(store.df_limpio)
    lj_pico = df[(df["Dia_Semana"] <= 3) & (df["Es_Horario_Pico"] == 1)]
    fin = df[df["Es_Fin_De_Semana"] == 1]
    return {
        "total_reservas_validas": int(len(df)),
        "por_estado": df["Estado_Reserva"].value_counts().to_dict(),
        "pct_no_show": round(100 * float(df["No_Show"].mean()), 1),
        "pct_reservas_lunes_a_jueves_19_a_23": round(100 * len(lj_pico) / len(df), 1),
        "pct_reservas_futbol11_en_fin_de_semana": round(100 * float((fin["Tipo_Cancha"] == "Fútbol 11").sum() / max((df["Tipo_Cancha"] == "Fútbol 11").sum(), 1)), 1),
        "reservas_por_tipo": df["Tipo_Cancha"].value_counts().to_dict(),
        "no_show_por_clima": {k: round(100 * float(v), 1) for k, v in df.groupby("Condicion_Climatica")["No_Show"].mean().items()},
        "dias_con_mayor_actividad": [str(k.date()) for k in df["Fecha"].value_counts().head(5).index],
    }


@app.get("/api/v1/canchas/ocupacion", tags=["Canchas"])
@app.get("/v1/canchas/ocupacion", tags=["Canchas"], include_in_schema=False)
def ocupacion(fecha: date):

    f = fecha.isoformat()
    delDia = [r for r in store.reservas if r["Fecha"] == f]
    canchas, ocupados, riesgo = [], 0, Counter()
    for nombre, tipo in modelo.cancha_tipo.items():
        slots = []
        for hora in HORAS_GRILLA:
            r = next((x for x in delDia if x["Cancha"] == nombre and x["Hora"] == hora and x["Estado_Reserva"] != "Cancelada"), None)
            canc = next((x for x in delDia if x["Cancha"] == nombre and x["Hora"] == hora and x["Estado_Reserva"] == "Cancelada"), None)
            if r:
                ocupados += 1
                riesgo[r["prediccion"]["color"]] += 1
                slots.append({"hora": hora, "estado": "ocupada", "reserva": {
                    "id": r["id"], "cliente": r["Cliente_ID"], "estado": r["Estado_Reserva"], "origen": r["origen"],
                    "color": r["prediccion"]["color"], "nivel_riesgo": r["prediccion"]["nivel_riesgo"],
                    "probabilidad_noshow": r["prediccion"]["probabilidad_noshow"], "nota": r.get("Anotacion_Cuaderno", ""),
                    "clima": r["Condicion_Climatica"]}})
            else:
                slot = {"hora": hora, "estado": "libre"}
                if canc:
                    slot["cancelada_previa"] = {"id": canc["id"], "cliente": canc["Cliente_ID"], "nota": canc.get("Anotacion_Cuaderno", "")}
                slots.append(slot)
        canchas.append({"cancha": nombre, "tipo": tipo, "slots": slots})
    total = len(modelo.cancha_tipo) * len(HORAS_GRILLA)
    return {"fecha": f, "horas": HORAS_GRILLA, "canchas": canchas,
            "resumen": {"total_canchas": len(canchas), "turnos_totales": total, "turnos_ocupados": ocupados,
                        "turnos_libres": total - ocupados, "ocupacion_pct": round(100 * ocupados / total, 1),
                        "riesgo": {"rojo": riesgo["rojo"], "amarillo": riesgo["amarillo"], "verde": riesgo["verde"]}},
            "estadisticas_cuaderno": _estadisticas_cuaderno()}


@app.get("/api/v1/admin/metricas", tags=["Administración"])
@app.get("/v1/admin/metricas", tags=["Administración"], include_in_schema=False)
def admin_metricas(_: str = Depends(requiere_admin)):
    pred = store.contador["predicciones"]
    return {
        "modelo": {"version": modelo.bundle["version_modelo"], "entrenado_en": modelo.bundle["entrenado_en"],
                   "variables": tm.FEATURES, "metricas": modelo.bundle["metricas"]},
        "limpieza": store.limpieza,
        "uso_api": {"predicciones": pred, "reservas_creadas": store.contador["reservas_creadas"],
                    "bloqueos_horario_409": store.contador["bloqueos_409"],
                    "accesos_denegados_403": store.contador["accesos_denegados_403"],
                    "latencia_media_prediccion_ms": round(store.contador["latencia_ms_acum"] / pred, 2) if pred else None},
        "estadisticas_cuaderno": _estadisticas_cuaderno(),
    }


@app.get("/api/v1/admin/cuaderno", tags=["Administración"])
@app.get("/v1/admin/cuaderno", tags=["Administración"], include_in_schema=False)
def admin_cuaderno(_: str = Depends(requiere_admin)):

    """Filas ORIGINALES del CSV (tal cual se digitalizaron), marcando artefactos y sanitizadas contra XSS."""
    raw = store.df_crudo
    filas = []
    for i, r in raw.iterrows():
        fecha = pd.to_datetime(r["Fecha"], errors="coerce")
        filas.append({
            "fila": int(i) + 2, "Fecha": sanitizar_texto(r["Fecha"]), "Hora": sanitizar_texto(r["Hora"]),
            "Cancha": sanitizar_texto(r["Cancha"]), "Tipo_Cancha": sanitizar_texto(r["Tipo_Cancha"]),
            "Cliente_ID": sanitizar_texto(r["Cliente_ID"]), "Estado_Reserva": sanitizar_texto(r["Estado_Reserva"]),
            "Monto_Abonado": None if pd.isna(r["Monto_Abonado"]) else float(r["Monto_Abonado"]),
            "Temperatura_C": float(r["Temperatura_C"]), "Humedad_Pct": float(r["Humedad_Pct"]),
            "Condicion_Climatica": sanitizar_texto(r["Condicion_Climatica"]),
            "Anotacion_Cuaderno": sanitizar_texto(r["Anotacion_Cuaderno"]),
            "artefacto": "fecha_1900" if (pd.isna(fecha) or fecha.year < 2000) else ("monto_nulo" if pd.isna(r["Monto_Abonado"]) else None),
        })
    return {"total": len(filas), "limpieza": store.limpieza, "filas": filas,
            "reporte_entrenamiento": {"mejores_hiperparametros": _reporte().get("mejores_hiperparametros"),
                                      "metricas": modelo.bundle["metricas"], "dataset": _reporte().get("dataset")}}


def _reporte() -> dict:
    import json
    try:
        return json.loads(tm.REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------- Frontend estatico ---------------------------------
def _buscar_index_html() -> Path | None:
    candidatos = [
        STATIC_DIR / "index.html",
        BASE_DIR / "index.html",
        Path.cwd() / "static" / "index.html",
        Path.cwd() / "index.html",
        Path("/var/task/static/index.html"),
    ]
    for c in candidatos:
        if c.exists():
            return c
    return None


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
@app.get("/api/index", include_in_schema=False)
@app.get("/api/index.py", include_in_schema=False)
def index():
    ruta = _buscar_index_html()
    if ruta and ruta.exists():
        return FileResponse(ruta)
    return JSONResponse(status_code=200, content={"estado": "ok", "mensaje": "Esquiu3 API operativa"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    logo = STATIC_DIR / "logo.png"
    if logo.exists():
        return FileResponse(logo, media_type="image/png")
    return JSONResponse(status_code=204, content=None)


@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def catch_all_debug(request: Request, path_name: str):
    return {
        "debug": True,
        "path_param": path_name,
        "url_path": request.url.path,
        "scope_path": request.scope.get("path"),
        "root_path": request.scope.get("root_path"),
        "headers": dict(request.headers),
    }


