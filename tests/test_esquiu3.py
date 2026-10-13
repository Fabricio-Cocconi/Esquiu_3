"""
Suite de pruebas automatizadas - Esquiu3 MVP Beta (Evidencia 3)
Testeo de Software - ISPC 2026 - Grupo Nº 6

CF-01..CF-04  Funcionales
CS-01..CS-02  No funcionales: Seguridad (RBAC y XSS)
CU-01..CU-02  No funcionales: Usabilidad (semaforo) y Rendimiento (latencia < 300 ms)
Mas pruebas complementarias (EX-xx) sobre validaciones y regresion de BUG-03.
"""
import statistics
import time
from pathlib import Path

import httpx
import pytest

import main

FECHA = "2026-11-02"  # lunes
BASE = {
    "Cancha": "Cancha 5", "Tipo_Cancha": "Fútbol 7", "Fecha": FECHA, "Hora": "20:00",
    "Cliente_ID": "CLI-102", "Condicion_Climatica": "Despejado", "Temperatura_C": 22.0, "Humedad_Pct": 55,
    "Anotacion_Cuaderno": "Turno de prueba",
}
PREDICT_KEYS = {k: v for k, v in BASE.items() if k != "Anotacion_Cuaderno"}


def reserva(**kw):
    return {**BASE, **kw}


def pred(**kw):
    return {**PREDICT_KEYS, **kw}


# ------------------------------------------------------------------ FUNCIONALES
@pytest.mark.caso("CF-01")
def test_cf01_registro_exitoso_en_cancha_disponible(client, reg):
    r = client.post("/api/v1/reservas", json=reserva())
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    res = cuerpo["reserva"]
    assert res["id"].startswith("R-") and res["Cancha"] == "Cancha 5" and res["Hora"] == "20:00"
    assert "probabilidad_noshow" in cuerpo["prediccion"]              # adjunta el resultado del modelo ML
    assert main.store.buscar(res["id"]) is not None                    # persistida en el almacen
    ocup = client.get("/api/v1/canchas/ocupacion", params={"fecha": FECHA}).json()
    celda = next(s for c in ocup["canchas"] if c["cancha"] == "Cancha 5" for s in c["slots"] if s["hora"] == "20:00")
    assert celda["estado"] == "ocupada"
    reg(obtenido=f"HTTP 201, reserva {res['id']} creada; prediccion adjunta: {cuerpo['prediccion']['nivel_riesgo']} "
                 f"({cuerpo['prediccion']['probabilidad_noshow']:.2%}); la grilla marca Cancha 5 20:00 como 'ocupada'")


@pytest.mark.caso("CF-02")
def test_cf02_bloqueo_de_reserva_duplicada(client, reg):
    assert client.post("/api/v1/reservas", json=reserva()).status_code == 201
    dup = client.post("/api/v1/reservas", json=reserva(Cliente_ID="CLI-104"))      # otro cliente, mismo turno
    assert dup.status_code == 409
    detalle = dup.json()["detail"]
    assert "Horario no disponible" in detalle["mensaje"] and detalle["codigo"] == "HORARIO_NO_DISPONIBLE"
    # otra cancha en la misma hora y la misma cancha en otra hora siguen disponibles
    assert client.post("/api/v1/reservas", json=reserva(Cancha="Cancha 4")).status_code == 201
    assert client.post("/api/v1/reservas", json=reserva(Hora="21:00")).status_code == 201
    # el turno bloqueado no genero una segunda reserva
    n = [r for r in main.store.reservas if r["origen"] == "mvp" and r["Cancha"] == "Cancha 5" and r["Hora"] == "20:00"]
    assert len(n) == 1
    # turno historico del cuaderno (Cancha 4, 2024-03-04 19:00, Completada) tambien bloquea
    h = client.post("/api/v1/reservas", json=reserva(Cancha="Cancha 4", Fecha="2024-03-04", Hora="19:00"))
    assert h.status_code == 409
    reg(obtenido=f"Segundo intento -> HTTP 409 codigo {detalle['codigo']}: \"{detalle['mensaje']}\". "
                 "Solo 1 reserva persistida; otra cancha / otra hora -> 201; turno historico del cuaderno -> 409")


@pytest.mark.caso("CF-03")
@pytest.mark.parametrize("clima,temp,hum", [("Lluvia", 10.0, 90), ("Frío Extremo", 4.0, 70)])
def test_cf03_riesgo_alto_cliente_con_faltas_horario_pico(client, reg, clima, temp, hum):
    body = pred(Cliente_ID="CLI-103", Hora="22:00", Condicion_Climatica=clima, Temperatura_C=temp, Humedad_Pct=hum,
                Fecha="2026-11-03")
    r = client.post("/api/v1/reservas/predict", json=body)
    assert r.status_code == 200
    p = r.json()
    assert p["color"] == "rojo" and p["nivel_riesgo"] == "Rojo - Alto"
    assert "seña obligatoria del 50%" in p["accion_preventiva"] and "WhatsApp" in p["accion_preventiva"]
    assert p["requiere_sena"] is True and p["monto_sena"] == main.modelo.precios["Fútbol 7"] * 0.5
    assert p["categoria_historial"] == "Malo" and p["cliente_nuevo"] is False
    reg(**{f"obtenido_{clima}": f"CLI-103 (historial Malo) 22:00 {clima}: {p['nivel_riesgo']} {p['probabilidad_noshow']:.2%}; "
                                f"seña ${p['monto_sena']:,.0f}; acción: \"{p['accion_preventiva']}\""})


@pytest.mark.caso("CF-04")
def test_cf04_prediccion_cliente_nuevo_sin_historial(client, reg):
    """Valida el fix de BUG-02: cliente inexistente en el cuaderno NO debe producir HTTP 500."""
    nuevo = "CLI-NUEVO-9999"
    assert nuevo.upper() not in main.modelo.hist
    r = client.post("/api/v1/reservas/predict", json=pred(Cliente_ID=nuevo, Hora="19:00"))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["cliente_nuevo"] is True
    assert p["historial_cumplimiento"] == pytest.approx(round(main.modelo.hist_default, 4))   # imputacion por defecto (mediana)
    assert 0.0 <= p["probabilidad_noshow"] <= 1.0
    assert p["color"] == "verde"                                     # turno temprano y despejado -> riesgo bajo
    # tambien funciona al registrar y en escenarios adversos (sin excepciones)
    assert client.post("/api/v1/reservas", json=reserva(Cliente_ID=nuevo, Hora="19:00")).status_code == 201
    adverso = client.post("/api/v1/reservas/predict", json=pred(Cliente_ID="Otro Cliente Nuevo", Hora="22:00", Condicion_Climatica="Lluvia", Humedad_Pct=92))
    assert adverso.status_code == 200 and adverso.json()["cliente_nuevo"] is True
    reg(obtenido=f"HTTP 200 (sin Error 500). cliente_nuevo=true, historial por defecto={p['historial_cumplimiento']}, "
                 f"{p['nivel_riesgo']} ({p['probabilidad_noshow']:.2%}). Escenario adverso (22:00, lluvia): {adverso.json()['nivel_riesgo']}")


# ------------------------------------------------------------------ SEGURIDAD
@pytest.mark.caso("CS-01")
def test_cs01_rbac_recepcionista_denegado_en_metricas(client, reg):
    denegado = client.get("/api/v1/admin/metricas", headers={"X-Role": "Recepcionista"})
    assert denegado.status_code == 403
    assert denegado.json()["detail"]["codigo"] == "ACCESO_DENEGADO"
    assert "metricas" not in denegado.text.lower().replace("métricas", "")      # no filtra datos del modelo
    assert client.get("/api/v1/admin/cuaderno", headers={"X-Role": "Recepcionista"}).status_code == 403
    assert client.get("/api/v1/admin/metricas").status_code == 401                # sin credencial
    assert client.get("/api/v1/admin/metricas", headers={"X-Role": "Hacker"}).status_code == 403   # rol desconocido
    ok = client.get("/api/v1/admin/metricas", headers={"X-Role": "Admin"})
    assert ok.status_code == 200 and "modelo" in ok.json() and "limpieza" in ok.json()
    reg(obtenido="Recepcionista -> 403 ACCESO_DENEGADO; sin header -> 401; rol 'Hacker' -> 403; Admin -> 200 con métricas")


@pytest.mark.caso("CS-02")
def test_cs02_sanitizacion_xss(client, reg):
    """Valida el fix de BUG-01: las etiquetas HTML/JS se escapan antes de persistir y de responder."""
    xss = "<script>alert('XSS')</script>"
    r = client.post("/api/v1/reservas", json=reserva(Cliente_ID=xss, Anotacion_Cuaderno=xss + "<img src=x onerror=alert(1)>"))
    assert r.status_code == 201, r.text
    cuerpo = r.text
    assert "<script>" not in cuerpo and "<img" not in cuerpo
    res = r.json()["reserva"]
    assert res["Cliente_ID"] == "&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;"
    assert "&lt;img" in res["Anotacion_Cuaderno"]
    # no reaparece sin escapar en las lecturas posteriores (grilla)
    grilla = client.get("/api/v1/canchas/ocupacion", params={"fecha": FECHA}).text
    assert "<script>" not in grilla and "&lt;script&gt;" in grilla
    # el almacen interno tampoco guarda la etiqueta viva
    guardada = main.store.buscar(res["id"])
    assert "<" not in guardada["Cliente_ID"] and "<" not in guardada["Anotacion_Cuaderno"]
    # cabeceras defensivas
    assert "script-src 'self'" in r.headers["Content-Security-Policy"] and r.headers["X-Content-Type-Options"] == "nosniff"
    reg(obtenido=f"HTTP 201; Cliente_ID almacenado como \"{res['Cliente_ID']}\"; nota escapada; la grilla no contiene <script>; "
                 "cabeceras CSP (script-src 'self') y X-Content-Type-Options presentes")


# ------------------------------------------------------------------ USABILIDAD / RENDIMIENTO
@pytest.mark.caso("CU-01")
def test_cu01_consistencia_del_semaforo(client, reg):
    etiquetas = {"verde": "Verde - Bajo", "amarillo": "Amarillo - Medio", "rojo": "Rojo - Alto"}
    escenarios = [
        pred(Cliente_ID="CLI-101", Hora="19:00"),
        pred(Cliente_ID="CLI-103", Hora="22:00", Condicion_Climatica="Lluvia", Temperatura_C=10, Humedad_Pct=90),
        pred(Cliente_ID="CLI-NUEVO-1", Hora="21:00", Condicion_Climatica="Nublado", Temperatura_C=14, Humedad_Pct=70),
    ]
    vistos = []
    for esc in escenarios:
        p = client.post("/api/v1/reservas/predict", json=esc).json()
        assert {"probabilidad_noshow", "nivel_riesgo", "color", "accion_preventiva"} <= p.keys()
        assert p["nivel_riesgo"] == etiquetas[p["color"]]                       # color <-> etiqueta textual coherentes
        assert p["accion_preventiva"] == main.ACCIONES[p["color"]] and len(p["accion_preventiva"]) > 20
        assert p["color"] == main.modelo.nivel(p["probabilidad_noshow"])         # color <-> probabilidad coherentes
        assert (p["requiere_sena"] is True) == (p["color"] == "rojo")
        vistos.append(f"{p['color']}/{p['nivel_riesgo']}/{p['probabilidad_noshow']:.0%}")
    # fronteras de los umbrales
    u = main.modelo.umbrales
    assert main.modelo.nivel(u["amarillo"] - 0.001) == "verde" and main.modelo.nivel(u["amarillo"]) == "amarillo"
    assert main.modelo.nivel(u["rojo"] - 0.001) == "amarillo" and main.modelo.nivel(u["rojo"]) == "rojo"
    # el texto de la accion en rojo es el exigido por el negocio
    assert main.ACCIONES["rojo"] == "Exigir seña obligatoria del 50% y enviar recordatorio automático por WhatsApp"
    reg(obtenido="Escenarios evaluados (color/etiqueta/prob): " + "; ".join(vistos) +
                 f". Umbrales: amarillo>={u['amarillo']}, rojo>={u['rojo']}")


@pytest.mark.caso("CU-02")
def test_cu02_latencia_inferencia_menor_a_300ms(servidor_http, reg):
    url = servidor_http + "/api/v1/reservas/predict"
    with httpx.Client() as c:
        for _ in range(3):                                   # calentamiento (carga perezosa, conexiones)
            assert c.post(url, json=PREDICT_KEYS).status_code == 200
        t = []
        for i in range(30):
            body = pred(Cliente_ID=f"CLI-{101 + i % 24}", Hora=f"{19 + i % 4}:00")
            t0 = time.perf_counter()
            r = c.post(url, json=body)
            t.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200
    t_sorted = sorted(t)
    media, p95, maximo = statistics.mean(t), t_sorted[int(len(t) * 0.95) - 1], max(t)
    assert maximo < 300, f"Latencia máxima {maximo:.1f} ms supera 300 ms"
    reg(obtenido=f"30 llamadas HTTP reales (uvicorn local): media={media:.1f} ms, p95={p95:.1f} ms, máx={maximo:.1f} ms (< 300 ms)",
        latencia_ms={"media": round(media, 1), "p95": round(p95, 1), "max": round(maximo, 1), "n": len(t)})


# ------------------------------------------------------------------ COMPLEMENTARIAS
@pytest.mark.caso("EX-01")
def test_ex01_validaciones_y_solapamiento(client, reg):
    assert client.post("/api/v1/reservas", json=reserva(Cancha="Cancha 99")).status_code == 422
    assert client.post("/api/v1/reservas", json=reserva(Tipo_Cancha="Pádel")).status_code == 422       # Cancha 5 es Fútbol 7
    assert client.post("/api/v1/reservas", json=reserva(Hora="03:00")).status_code == 422
    assert client.post("/api/v1/reservas", json=reserva(Condicion_Climatica="Tornado")).status_code == 422
    assert client.post("/api/v1/reservas", json=reserva(Temperatura_C=900)).status_code == 422
    assert main.store.conflicto("Cancha 5", FECHA, "20:00", 60) is None
    main.store.crear({"Cancha": "Cancha 5", "Fecha": FECHA, "Hora": "20:00"})                          # ocupa 20:00-21:00
    assert main.store.conflicto("Cancha 5", FECHA, "20:30") is not None                                # solapado
    assert main.store.conflicto("Cancha 5", FECHA, "21:00") is None                                    # contiguo permitido
    reg(obtenido="Cancha/Tipo/Hora/Clima/Temperatura inválidos -> 422; solape 20:30 -> bloqueado; contiguo 21:00 -> libre")


@pytest.mark.caso("EX-02")
def test_ex02_ocupacion_13_canchas_y_clima_con_fallback(client, reg):
    o = client.get("/api/v1/canchas/ocupacion", params={"fecha": "2024-03-04"}).json()
    assert len(o["canchas"]) == 13 and o["resumen"]["total_canchas"] == 13
    assert [c["cancha"] for c in o["canchas"]][-1] == "Cancha 13"
    assert len(o["horas"]) == 9 and o["horas"][0] == "14:00" and o["horas"][-1] == "22:00"
    assert o["resumen"]["turnos_ocupados"] == 3
    normal = client.get("/api/v1/clima/pronostico", params={"fecha": FECHA}).json()
    caido = client.get("/api/v1/clima/pronostico", params={"fecha": FECHA, "simular_caida": True}).json()
    assert normal["fallback"] is False and caido["fallback"] is True and "Condicion_Climatica" in caido
    reg(obtenido="13 canchas x 9 turnos; 2024-03-04 con 3 turnos ocupados; clima con caída simulada -> fallback histórico")


@pytest.mark.caso("EX-04")
@pytest.mark.parametrize("clima,temp,hum", [("Despejado", 31.0, 40), ("Lluvia", 9.0, 95), ("Frío Extremo", -3.0, 80), ("Nublado", 18.5, 60)])
def test_ex04_analisis_de_clima_libre(client, reg, clima, temp, hum):
    """El usuario puede ingresar cualquier clima y recibe un analisis explicado + comparacion por condicion."""
    r = client.post("/api/v1/reservas/predict", json=pred(Cliente_ID="CLI-105", Hora="21:00", Condicion_Climatica=clima,
                                                           Temperatura_C=temp, Humedad_Pct=hum))
    assert r.status_code == 200, r.text
    p = r.json()
    a = p["analisis_clima"]
    assert a["ingresado"]["condicion"] == clima and len(a["escenarios"]) == 4
    elegido = [s for s in a["escenarios"] if s["es_el_elegido"]]
    assert len(elegido) == 1 and elegido[0]["probabilidad"] == p["probabilidad_noshow"]
    assert len(a["explicacion"]) >= 4 and a["advertencia"]
    assert all(0.0 <= s["probabilidad"] <= 1.0 for s in a["escenarios"])
    assert a["historico_cuaderno"] is not None and a["historico_cuaderno"]["n"] > 0
    reg(**{f"obtenido_{clima}": f"{clima} {temp} °C {hum}%: {p['nivel_riesgo']} {p['probabilidad_noshow']:.0%}; "
                                f"diferencia vs día despejado {a['diferencia_pp']:+g} pp"})


@pytest.mark.caso("EX-03")
def test_ex03_regresion_bug03_css_grilla_con_scroll(reg):
    """BUG-03: la grilla debe vivir en un contenedor con scroll y cabecera/columna fijas (no desbordar el layout)."""
    css = (Path(main.STATIC_DIR) / "styles.css").read_text(encoding="utf-8")
    bloque = css.split(".grid-scroll {")[1].split("}")[0]
    assert "overflow: auto" in bloque and "max-height" in bloque
    assert "position: sticky" in css.split(".grilla thead th {")[1].split("}")[0]
    assert len(main.modelo.cancha_tipo) == 13
    reg(obtenido="CSS: .grid-scroll {overflow:auto; max-height} + thead/primera columna sticky. Verificación visual 1366x768 en navegador")
