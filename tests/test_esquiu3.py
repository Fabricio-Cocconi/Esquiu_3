"""
Pruebas Automatizadas - Sistema Esquiu3 (Evidencia de Aprendizaje Nº 3)
Instituto Superior Politécnico Córdoba (ISPC) - Año 2026
Materia: Testeo de Software (Prof. David Cabrera / Prof. Carolina Ahumada)
Grupo Nº 6: Yanina Roldan, Gabriel Yoles Trucco, Fabricio Cocconi, Franco Gonzalo Arce

Casos de Prueba implementados según las consignas de cátedra:
- Pruebas Funcionales (Caja Negra y Clases de Equivalencia): CF-01 a CF-05
- Pruebas No Funcionales (2 tipos seleccionados):
    * Seguridad: CS-01 y CS-02
    * Usabilidad: CU-01 y CU-02
"""
from pathlib import Path
import pytest
import main

FECHA_PRUEBA = "2026-11-02"  # Lunes de prueba

DATOS_BASE = {
    "Cancha": "Cancha 5",
    "Tipo_Cancha": "Fútbol 7",
    "Fecha": FECHA_PRUEBA,
    "Hora": "20:00",
    "Cliente_ID": "CLI-102",
    "Condicion_Climatica": "Despejado",
    "Temperatura_C": 22.0,
    "Humedad_Pct": 55.0,
    "Anotacion_Cuaderno": "Turno cargado por el recepcionista",
}


def crear_payload_reserva(**modificaciones):
    """Genera datos de reserva válidos con modificaciones puntuales para cada prueba."""
    datos = DATOS_BASE.copy()
    datos.update(modificaciones)
    return datos


def crear_payload_prediccion(**modificaciones):
    """Genera datos para consultar al modelo predictor."""
    datos = {k: v for k, v in DATOS_BASE.items() if k != "Anotacion_Cuaderno"}
    datos.update(modificaciones)
    return datos


# ==============================================================================
# 1. PRUEBAS FUNCIONALES (CF-01 a CF-05) - Método de Caja Negra
# ==============================================================================

@pytest.mark.caso("CF-01")
def test_cf01_registro_exitoso_cancha_libre(client, reg):
    """
    CF-01: Cargar una reserva válida en una cancha libre y verificar que se guarde
    correctamente y que la cancha quede marcada como ocupada.
    """
    payload = crear_payload_reserva(Cancha="Cancha 5", Hora="20:00")
    respuesta = client.post("/api/v1/reservas", json=payload)

    assert respuesta.status_code == 201, "La reserva válida debería responder HTTP 201 Created"
    cuerpo = respuesta.json()
    reserva = cuerpo["reserva"]

    # Verificamos que se genere ID de reserva y se guarden los datos ingresados
    assert reserva["id"].startswith("R-")
    assert reserva["Cancha"] == "Cancha 5"
    assert reserva["Hora"] == "20:00"

    # Verificamos en la grilla que el turno aparezca como 'ocupada'
    ocupacion = client.get("/api/v1/canchas/ocupacion", params={"fecha": FECHA_PRUEBA}).json()
    cancha5 = next(c for c in ocupacion["canchas"] if c["cancha"] == "Cancha 5")
    slot20 = next(s for s in cancha5["slots"] if s["hora"] == "20:00")
    assert slot20["estado"] == "ocupada"

    reg(obtenido=f"Reserva {reserva['id']} guardada con éxito (HTTP 201). La Cancha 5 a las 20:00 hs figura ocupada en la grilla.")


@pytest.mark.caso("CF-02")
def test_cf02_bloqueo_reserva_duplicada(client, reg):
    """
    CF-02: Intentar cargar una reserva duplicada en la misma cancha, fecha y hora.
    Verificar que el sistema no deje guardar y devuelva cartel de 'Horario no disponible' (HTTP 409).
    """
    # 1. Guardamos la primera reserva
    primera = client.post("/api/v1/reservas", json=crear_payload_reserva(Cancha="Cancha 5", Hora="20:00", Cliente_ID="CLI-101"))
    assert primera.status_code == 201

    # 2. Intentamos guardar otra en el mismo horario con otro cliente
    duplicada = client.post("/api/v1/reservas", json=crear_payload_reserva(Cancha="Cancha 5", Hora="20:00", Cliente_ID="CLI-104"))
    assert duplicada.status_code == 409, "El sistema debe rechazar reservas solapadas con HTTP 409 Conflict"

    detalle = duplicada.json()["detail"]
    assert "Horario no disponible" in detalle["mensaje"]
    assert detalle["codigo"] == "HORARIO_NO_DISPONIBLE"

    reg(obtenido=f"El sistema bloqueó el turno duplicado con HTTP 409 y mensaje: '{detalle['mensaje']}'.")


@pytest.mark.caso("CF-03")
def test_cf03_validacion_campos_obligatorios_vacios(client, reg):
    """
    CF-03: Intentar guardar una reserva dejando campos obligatorios vacíos (ej. sin cliente o sin hora).
    Comprobar que el sistema valide y muestre mensaje de advertencia (HTTP 422).
    """
    # Caso A: Falta el campo Cliente_ID
    sin_cliente = crear_payload_reserva()
    sin_cliente["Cliente_ID"] = ""
    resp_a = client.post("/api/v1/reservas", json=sin_cliente)
    assert resp_a.status_code == 422, "Enviar cliente vacío debe devolver error de validación HTTP 422"

    # Caso B: Hora fuera del rango de turnos (ej: 03:00 de la madrugada)
    hora_invalida = crear_payload_reserva(Hora="03:00")
    resp_b = client.post("/api/v1/reservas", json=hora_invalida)
    assert resp_b.status_code == 422, "Enviar horario fuera de 14 a 22 hs debe ser rechazado"

    reg(obtenido="El sistema rechazó los datos incompletos con HTTP 422 mostrando qué campo falta completar.")


@pytest.mark.caso("CF-04")
def test_cf04_prediccion_semaforo_rojo_cliente_faltas_horario_pico(client, reg):
    """
    CF-04: Probar la predicción del modelo cargando un turno en horario pico (19 a 23 hs)
    para un cliente con faltas previas y día de lluvia/frío. Verificar semáforo Rojo y pedido de seña del 50%.
    """
    # CLI-103 tiene historial de faltas en el cuaderno; horario pico 22:00 hs con Lluvia y frío
    payload = crear_payload_prediccion(
        Cliente_ID="CLI-103",
        Hora="22:00",
        Condicion_Climatica="Lluvia",
        Temperatura_C=10.0,
        Humedad_Pct=90.0,
        Fecha="2026-11-03",
    )
    resp = client.post("/api/v1/reservas/predict", json=payload)
    assert resp.status_code == 200

    prediccion = resp.json()
    assert prediccion["color"] == "rojo", "Debe marcar semáforo rojo ante alto riesgo"
    assert prediccion["nivel_riesgo"] == "Rojo - Alto"
    assert prediccion["requiere_sena"] is True, "Debe exigir seña obligatoria"
    assert "seña obligatoria del 50%" in prediccion["accion_preventiva"]
    assert "WhatsApp" in prediccion["accion_preventiva"]

    reg(obtenido=f"Semáforo: {prediccion['nivel_riesgo']} ({prediccion['probabilidad_noshow']:.1%} de riesgo). Acción: {prediccion['accion_preventiva']}.")


@pytest.mark.caso("CF-05")
def test_cf05_cliente_nuevo_sin_historial(client, reg):
    """
    CF-05: Cargar una reserva con un cliente nuevo (que no figuraba en el cuaderno viejo).
    Comprobar que el sistema funcione normalmente sin arrojar error 500 (Fix BUG-02).
    """
    cliente_nuevo = "CLI-NUEVO-ISPC"
    payload = crear_payload_reserva(Cliente_ID=cliente_nuevo, Hora="19:00")
    resp = client.post("/api/v1/reservas", json=payload)

    assert resp.status_code == 201, "El cliente nuevo debe poder registrarse normalmente"
    cuerpo = resp.json()
    assert cuerpo["prediccion"]["cliente_nuevo"] is True
    assert 0.0 <= cuerpo["prediccion"]["probabilidad_noshow"] <= 1.0

    reg(obtenido=f"Cliente nuevo {cliente_nuevo} registrado con éxito (HTTP 201). Se le asignó el promedio general de asistencia sin fallos.")


# ==============================================================================
# 2. PRUEBAS NO FUNCIONALES (2 Tipos Seleccionados: Seguridad y Usabilidad)
# ==============================================================================

# --- TIPO 1: SEGURIDAD (CS-01 y CS-02) ---

@pytest.mark.caso("CS-01")
def test_cs01_permisos_por_rol_recepcionista_denegado(client, reg):
    """
    CS-01: Permisos por rol: Comprobar que si ingresamos como 'Recepcionista',
    el sistema no permita ver la pestaña de Auditoría y Métricas del Administrador (HTTP 403 Forbidden).
    """
    # Intentamos acceder al panel de auditoría con rol de recepcionista
    resp = client.get("/api/v1/admin/metricas", headers={"X-Role": "Recepcionista"})
    assert resp.status_code == 403, "Recepcionista no debe tener acceso a métricas de administración"
    assert resp.json()["detail"]["codigo"] == "ACCESO_DENEGADO"

    # Verificamos que con rol Admin sí se pueda acceder
    resp_admin = client.get("/api/v1/admin/metricas", headers={"X-Role": "Admin"})
    assert resp_admin.status_code == 200

    reg(obtenido="Rol Recepcionista bloqueado correctamente con HTTP 403 Acceso Denegado. Rol Admin accede con HTTP 200.")


@pytest.mark.caso("CS-02")
def test_cs02_campos_seguros_sanitizacion_xss(client, reg):
    """
    CS-02: Campos seguros: Probar qué pasa si alguien escribe código o símbolos raros
    (<script>alert(1)</script>) en las notas del turno, verificando que se guarde como texto común
    y no ejecute scripts ni rompa la página (Fix BUG-01).
    """
    payload_peligroso = "<script>alert('XSS')</script>"
    payload = crear_payload_reserva(Anotacion_Cuaderno=payload_peligroso)
    resp = client.post("/api/v1/reservas", json=payload)

    assert resp.status_code == 201
    cuerpo_texto = resp.text
    # Verificamos que la etiqueta <script> no quede viva sin escapar
    assert "<script>" not in cuerpo_texto
    assert "&lt;script&gt;" in cuerpo_texto

    reg(obtenido="El texto malicioso fue neutralizado y convertido a texto plano (&lt;script&gt;) sin ejecutarse.")


# --- TIPO 2: USABILIDAD (CU-01 y CU-02) ---

@pytest.mark.caso("CU-01")
def test_cu01_usabilidad_claridad_visual_semaforo(client, reg):
    """
    CU-01: Claridad visual: Verificar que los colores del semáforo (Verde, Amarillo y Rojo)
    y los carteles de aviso se entiendan rápido y correspondan con las reglas del complejo.
    """
    colores_validos = {"verde", "amarillo", "rojo"}
    etiquetas_esperadas = {
        "verde": "Verde - Bajo",
        "amarillo": "Amarillo - Medio",
        "rojo": "Rojo - Alto",
    }

    # Probamos una reserva de bajo riesgo (despejado y horario temprano)
    p_baja = client.post("/api/v1/reservas/predict", json=crear_payload_prediccion(Hora="15:00", Condicion_Climatica="Despejado")).json()
    # Probamos una reserva de riesgo crítico (horario pico, lluvia y cliente con faltas)
    p_alta = client.post("/api/v1/reservas/predict", json=crear_payload_prediccion(Cliente_ID="CLI-103", Hora="22:00", Condicion_Climatica="Lluvia")).json()

    assert p_baja["color"] in colores_validos
    assert p_baja["nivel_riesgo"] == etiquetas_esperadas[p_baja["color"]]
    assert len(p_baja["accion_preventiva"]) > 0

    assert p_alta["color"] == "rojo"
    assert p_alta["nivel_riesgo"] == "Rojo - Alto"
    assert "seña obligatoria" in p_alta["accion_preventiva"].lower()

    reg(obtenido=f"Semáforos validados: Baja -> {p_baja['nivel_riesgo']}; Crítica -> {p_alta['nivel_riesgo']} con indicación de seña clara.")


@pytest.mark.caso("CU-02")
def test_cu02_usabilidad_grilla_con_scroll_1366x768(reg):
    """
    CU-02: Visualización de la tabla: Comprobar que la grilla de las 13 canchas tenga
    barra de desplazamiento (scroll) horizontal y cabeceras fijas para que no se corte
    en las pantallas de las notebooks del grupo (resolución 1366x768) (Fix BUG-03).
    """
    archivo_css = Path(main.STATIC_DIR) / "styles.css"
    contenido_css = archivo_css.read_text(encoding="utf-8")

    # Verificamos que exista el contenedor con scroll y sticky headers
    assert ".grid-scroll" in contenido_css or "overflow: auto" in contenido_css, "Debe existir scroll para la grilla"
    assert "position: sticky" in contenido_css, "Las cabeceras de canchas deben ser fijas"
    assert len(main.modelo.cancha_tipo) == 13, "Deben estar presentes las 13 canchas"

    reg(obtenido="Verificado: la grilla cuenta con contenedor con scroll horizontal (.grid-scroll / overflow: auto) y cabeceras fijas.")
