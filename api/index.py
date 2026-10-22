import sys
from pathlib import Path

# Agregar la raíz del proyecto al sys.path para importar main, train_model, etc.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app as fastapi_app

async def app(scope, receive, send):
    """
    Wrapper ASGI para normalizar rutas en el entorno serverless de Vercel.
    Garantiza que FastAPI reciba siempre la ruta limpia original (/api/v1/..., /docs, etc.).
    """
    if scope["type"] == "http":
        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        matched = headers.get(b"x-matched-path", b"").decode("utf-8")

        # Si Vercel rewrote la URL interna a /api/index.py pero el cliente pidió una ruta original
        if path in ("/api/index.py", "/api/index", "/api/index.py/", "/api/index/"):
            if matched:
                scope = dict(scope)
                scope["path"] = matched

        # Si la petición llega como /v1/..., anteponer /api para coincidir con FastAPI
        cur_path = scope.get("path", "")
        if cur_path.startswith("/v1/"):
            scope = dict(scope)
            scope["path"] = "/api" + cur_path

    await fastapi_app(scope, receive, send)
