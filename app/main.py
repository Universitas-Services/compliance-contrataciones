"""
API FastAPI — compliance-contrataciones

Auditoría conversacional de contrataciones públicas (Venezuela):
orquestador + dupla Analista/Jurídico por modalidad.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.security import SecurityHeadersMiddleware, cors_origins
from app.routers import sesiones

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="compliance-contrataciones",
    description=(
        "API de compliance de contrataciones públicas multi-modalidad "
        "(orquestador + dupla Analista/Jurídico × 7 modalidades)."
    ),
    version="0.4.0",
)

_origins = cors_origins()
# credentials + "*" no es válido en navegadores; si piden "*", desactivar credentials
_allow_cred = "*" not in _origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_cred,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(sesiones.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.4.0", "service": "compliance-contrataciones"}


@app.get("/")
def ui_root():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        return {
            "status": "ok",
            "service": "compliance-contrataciones",
            "docs": "/docs",
        }
    return FileResponse(index)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
