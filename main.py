import time
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from db import pos_engine
from pos_routes import router as pos_router
from pos_routes_catalog import router as pos_catalog_router
from pos_routes_maintenance import router as pos_maintenance_router
from pos_routes_sales import router as pos_sales_router
from pos_routes_print import router as pos_print_router

APP_BASE_PATH = (os.getenv("APP_BASE_PATH", "/ext/pos").strip() or "/ext/pos").rstrip("/")
if not APP_BASE_PATH.startswith("/"):
    APP_BASE_PATH = f"/{APP_BASE_PATH}"

app = FastAPI(title="RodelSoft - POS")

# Static bajo contrato de app externa
app.mount(f"{APP_BASE_PATH}/static", StaticFiles(directory="static"), name="static")

# Rutas base POS bajo prefijo estándar
app.include_router(pos_router, prefix=APP_BASE_PATH)

# Estos routers YA traen sus propios subpaths internos (/api, etc.),
# solo necesitan vivir bajo /ext/pos
app.include_router(pos_catalog_router, prefix=APP_BASE_PATH)
app.include_router(pos_maintenance_router, prefix=APP_BASE_PATH)
app.include_router(pos_sales_router, prefix=APP_BASE_PATH)

# Print actualmente estaba bajo /pos; se conserva esa semántica
# pero ahora bajo el contrato externo: /ext/pos/pos/...
app.include_router(pos_print_router, prefix=f"{APP_BASE_PATH}/pos")


def wait_engine(engine_to_check, label: str, retries: int = 20):
    for i in range(retries):
        try:
            with engine_to_check.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[startup] DB {label} OK")
            return
        except Exception as e:
            if i == retries - 1:
                print(f"[startup] DB {label} no disponible: {e}")
            else:
                print(f"[startup] Esperando DB {label}... intento {i+1}/{retries}")
                time.sleep(2)


@app.on_event("startup")
def _startup():
    wait_engine(pos_engine, "POS")
