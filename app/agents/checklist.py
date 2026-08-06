"""Compat: checklist legacy reexporta knowledge de CA apertura única / BIENES."""

from app.agents.knowledge import PLACEHOLDER as PLACEHOLDER_ELEMENTOS
from app.agents.knowledge import get_rama
from app.models.schemas import Modalidad, TipoContratacion, TipoDocumento

_rama = get_rama(Modalidad.CA_ACTO_UNICO_APERTURA_UNICA, TipoContratacion.BIENES)

CHECKLIST_ORDEN: list[TipoDocumento] = [s["tipo_documento"] for s in _rama["slots"]]

REQUISITOS_POR_DOCUMENTO: dict[TipoDocumento, dict] = {
    s["tipo_documento"]: {
        "descripcion": s["descripcion"],
        "elementos_requeridos": list(s["elementos_requeridos"]),
    }
    for s in _rama["slots"]
}


def siguiente_documento(documentos_ya_recibidos: list[TipoDocumento]) -> TipoDocumento | None:
    """Deprecated: el flujo nuevo no exige orden. Conservado por compat scripts."""
    recibidos = set(documentos_ya_recibidos)
    for tipo in CHECKLIST_ORDEN:
        if tipo not in recibidos:
            return tipo
    return None
