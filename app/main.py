"""
API FastAPI — compliance-contrataciones

Auditoría conversacional de contrataciones públicas (Venezuela):
orquestador + dupla Analista/Jurídico por modalidad.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.security import SecurityHeadersMiddleware, cors_origins
from app.routers import sesiones

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
