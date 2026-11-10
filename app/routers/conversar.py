"""Chat sin estado con el Coordinador de Compliance."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.llm_client import conversar
from app.models.schemas import ConversarRequest, ConversarResponse
from app.routers.sesiones import _LLM_ERRORS, _http_from_llm

router = APIRouter(prefix="/conversar", tags=["conversar"])


@router.post("", response_model=ConversarResponse)
def conversar_ruta(body: ConversarRequest) -> ConversarResponse:
    try:
        resultado = conversar(
            usuario_nombre=body.usuario_nombre,
            ente=body.ente,
            expediente=body.expediente.model_dump(mode="json"),
            historial=[m.model_dump() for m in body.historial],
            mensaje=body.mensaje,
        )
    except _LLM_ERRORS as exc:
        raise _http_from_llm(exc) from exc
    return ConversarResponse(**resultado)
