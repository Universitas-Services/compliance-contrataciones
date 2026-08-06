"""Utilidades de seguridad de la API (sin BD aún).

Cuando se conecte una base de datos: usar ORM o consultas parametrizadas
siempre; nunca concatenar SQL con input del usuario (protección inyección SQL).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Extensiones alineadas con el extractor
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".xls",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".webp",
    ".bmp",
    ".txt",
}

_SAFE_FILENAME = re.compile(r"[^\w.\-()+ ]+", re.UNICODE)


def cors_origins() -> list[str]:
    """Orígenes CORS desde CORS_ORIGINS (coma-separados). Default: front local."""
    raw = (os.getenv("CORS_ORIGINS") or "").strip()
    if not raw:
        return [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def max_upload_bytes() -> int:
    raw = (os.getenv("MAX_UPLOAD_MB") or "25").strip()
    try:
        mb = float(raw)
    except ValueError:
        mb = 25.0
    return int(mb * 1024 * 1024)


def sanitizar_nombre_archivo(nombre: str | None) -> str:
    base = Path(nombre or "archivo").name
    base = _SAFE_FILENAME.sub("_", base).strip("._") or "archivo"
    return base[:180]


def validar_extension_upload(nombre: str) -> str:
    """Devuelve la extensión normalizada o lanza ValueError."""
    ext = Path(nombre).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        permitidas = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        raise ValueError(
            f"Tipo de archivo no permitido ({ext or 'sin extensión'}). "
            f"Permitidos: {permitidas}"
        )
    return ext


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras HTTP básicas de endurecimiento."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        # Evitar cachear respuestas de API con datos de sesión
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
