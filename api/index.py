import sys
from pathlib import Path

# Agregar la raíz del proyecto al sys.path para importar main, train_model, etc.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app
