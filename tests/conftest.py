"""Fixtures y registro de evidencia de las pruebas (genera tests/resultados_pruebas.json)."""
import json
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

import main

RESULTADOS: dict = {}
SALIDA = Path(__file__).parent / "resultados_pruebas.json"


def _cid(item) -> str:
    m = item.get_closest_marker("caso")
    return m.args[0] if m else item.name


@pytest.fixture(scope="session")
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def estado_limpio():
    """Cada prueba parte del cuaderno historico sin reservas nuevas (aislamiento)."""
    main.store.reset()
    yield


@pytest.fixture
def reg(request):
    """Registra datos reales observados durante la prueba (se vuelcan al informe)."""
    cid = _cid(request.node)

    def _registrar(**datos):
        RESULTADOS.setdefault(cid, {}).update(datos)
    return _registrar


@pytest.fixture(scope="session")
def servidor_http():
    """Levanta uvicorn real en un hilo para medir latencia sobre HTTP (no solo en proceso)."""
    config = uvicorn.Config(main.app, host="127.0.0.1", port=8765, log_level="error")
    server = uvicorn.Server(config)
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield "http://127.0.0.1:8765"
    server.should_exit = True
    hilo.join(timeout=5)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    salida = yield
    rep = salida.get_result()
    if rep.when == "call":
        d = RESULTADOS.setdefault(_cid(item), {})
        d["estado"] = "PASSED" if rep.passed else "FAILED"
        d["nodeid"] = item.nodeid
        d["duracion_s"] = round(rep.duration, 3)


def pytest_sessionfinish(session, exitstatus):
    SALIDA.write_text(json.dumps(RESULTADOS, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
