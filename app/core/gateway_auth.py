"""Auth servicio-a-servicio: gateways de confianza (Laravel / Nest).

El navegador no debe llamar a FastAPI directo. Cada gateway manda
`X-Agent-Key`; aquí solo validamos que la llamada viene de un cliente
conocido. Permisos de usuario humano viven en Laravel/Nest.
"""

from __future__ import annotations

import logging
import os

from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)

_CLIENT_ENVS: tuple[tuple[str, str], ...] = (
    ("AGENT_CLIENT_LARAVEL_KEY", "laravel-testing"),
    ("AGENT_CLIENT_NEST_KEY", "nest-production"),
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def agent_auth_enabled() -> bool:
    """Si false, se omite la validación (demos locales sin gateway).

    Default false si la variable no está (no romper entornos locales viejos).
    En staging/prod poner AGENT_AUTH_ENABLED=true.
    """
    return _env_bool("AGENT_AUTH_ENABLED", False)


def docs_enabled() -> bool:
    """Swagger/ReDoc. Default true (local); apagar en staging/prod."""
    return _env_bool("DOCS_ENABLED", True)


def _allowed_clients() -> dict[str, str]:
    """Mapa key → client_name; ignora keys vacías."""
    out: dict[str, str] = {}
    for env_name, client_name in _CLIENT_ENVS:
        key = (os.getenv(env_name) or "").strip().strip("\"'")
        if key:
            out[key] = client_name
    return out


async def verify_gateway(
    request: Request,
    x_agent_key: str | None = Header(default=None, alias="X-Agent-Key"),
) -> str | None:
    """Valida X-Agent-Key y deja client_name en request.state."""
    if not agent_auth_enabled():
        request.state.client_name = "auth-disabled"
        logger.debug(
            "gateway_auth bypass path=%s client=auth-disabled",
            request.url.path,
        )
        return "auth-disabled"

    clients = _allowed_clients()
    if not clients:
        logger.error(
            "AGENT_AUTH_ENABLED=true pero no hay AGENT_CLIENT_*_KEY configuradas"
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Auth de gateway habilitada sin claves de cliente. "
                "Configura AGENT_CLIENT_LARAVEL_KEY y/o AGENT_CLIENT_NEST_KEY, "
                "o pon AGENT_AUTH_ENABLED=false en desarrollo local."
            ),
        )

    key = (x_agent_key or "").strip().strip("\"'")
    client_name = clients.get(key)
    if not client_name:
        logger.warning(
            "gateway_auth 401 path=%s key_present=%s",
            request.url.path,
            bool(key),
        )
        raise HTTPException(status_code=401, detail="No autorizado")

    request.state.client_name = client_name
    logger.info(
        "gateway_auth ok client=%s path=%s method=%s",
        client_name,
        request.url.path,
        request.method,
    )
    return client_name
