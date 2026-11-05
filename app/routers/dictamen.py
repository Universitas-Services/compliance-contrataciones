"""Dictamen jurídico sin estado: el cliente envía los JSON del expediente."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.orchestrator import dictamen_desde_documentos
from app.core.capacidad import cupo_analisis
from app.models.schemas import DictamenExpedienteRequest, DictamenExpedienteResponse
from app.routers.sesiones import _LLM_ERRORS, _http_from_llm

router = APIRouter(prefix="/dictamen", tags=["dictamen"])


@router.post("", response_model=DictamenExpedienteResponse)
def emitir_dictamen(body: DictamenExpedienteRequest) -> DictamenExpedienteResponse:
    try:
        with cupo_analisis():
            dictamen = dictamen_desde_documentos(
                nomenclatura=body.nomenclatura,
                modalidad=body.modalidad,
                tipo_contratacion=body.tipo_contratacion,
                documentos=body.documentos,
                mensaje=body.mensaje,
                forzar_final=body.forzar_final,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except _LLM_ERRORS as exc:
        raise _http_from_llm(exc) from exc
    return DictamenExpedienteResponse(
        alcance=dictamen.alcance,
        markdown=dictamen.markdown,
        puntaje=dictamen.puntaje,
        pendientes=dictamen.slots_pendientes,
    )
