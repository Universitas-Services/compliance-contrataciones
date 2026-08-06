"""Factory de agentes: dupla Analista + Jurídico por modalidad."""

from __future__ import annotations

from app.agents.modalities.base import BaseModalidadAgent
from app.agents.modalities.ca_acto_separado import (
    CAActoSeparadoAnalistaAgent,
    CAActoSeparadoJuridicoAgent,
)
from app.agents.modalities.ca_apertura_diferida import (
    CAAperturaDiferidaAnalistaAgent,
    CAAperturaDiferidaJuridicoAgent,
)
from app.agents.modalities.ca_apertura_unica import (
    CAAperturaUnicaAnalistaAgent,
    CAAperturaUnicaJuridicoAgent,
)
from app.agents.modalities.concurso_cerrado import (
    ConcursoCerradoAnalistaAgent,
    ConcursoCerradoJuridicoAgent,
)
from app.agents.modalities.consulta_precio import (
    ConsultaPrecioAnalistaAgent,
    ConsultaPrecioJuridicoAgent,
)
from app.agents.modalities.contratacion_directa import (
    ContratacionDirectaAnalistaAgent,
    ContratacionDirectaJuridicoAgent,
)
from app.agents.modalities.modalidades_excluidas import (
    ModalidadesExcluidasAnalistaAgent,
    ModalidadesExcluidasJuridicoAgent,
)
from app.models.schemas import Modalidad, RolAgente, TipoContratacion

_REGISTRY: dict[tuple[Modalidad, RolAgente], type[BaseModalidadAgent]] = {
    (Modalidad.CA_ACTO_UNICO_APERTURA_UNICA, RolAgente.ANALISTA): CAAperturaUnicaAnalistaAgent,
    (Modalidad.CA_ACTO_UNICO_APERTURA_UNICA, RolAgente.JURIDICO): CAAperturaUnicaJuridicoAgent,
    (Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA, RolAgente.ANALISTA): CAAperturaDiferidaAnalistaAgent,
    (Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA, RolAgente.JURIDICO): CAAperturaDiferidaJuridicoAgent,
    (Modalidad.CA_ACTO_SEPARADO, RolAgente.ANALISTA): CAActoSeparadoAnalistaAgent,
    (Modalidad.CA_ACTO_SEPARADO, RolAgente.JURIDICO): CAActoSeparadoJuridicoAgent,
    (Modalidad.CONCURSO_CERRADO, RolAgente.ANALISTA): ConcursoCerradoAnalistaAgent,
    (Modalidad.CONCURSO_CERRADO, RolAgente.JURIDICO): ConcursoCerradoJuridicoAgent,
    (Modalidad.CONSULTA_PRECIO, RolAgente.ANALISTA): ConsultaPrecioAnalistaAgent,
    (Modalidad.CONSULTA_PRECIO, RolAgente.JURIDICO): ConsultaPrecioJuridicoAgent,
    (Modalidad.CONTRATACION_DIRECTA, RolAgente.ANALISTA): ContratacionDirectaAnalistaAgent,
    (Modalidad.CONTRATACION_DIRECTA, RolAgente.JURIDICO): ContratacionDirectaJuridicoAgent,
    (Modalidad.MODALIDADES_EXCLUIDAS, RolAgente.ANALISTA): ModalidadesExcluidasAnalistaAgent,
    (Modalidad.MODALIDADES_EXCLUIDAS, RolAgente.JURIDICO): ModalidadesExcluidasJuridicoAgent,
}


def get_agente(
    modalidad: Modalidad,
    tipo_contratacion: TipoContratacion,
    rol: RolAgente = RolAgente.ANALISTA,
) -> BaseModalidadAgent:
    cls = _REGISTRY[(modalidad, rol)]
    return cls(tipo_contratacion)


def get_modalidad_agent(
    modalidad: Modalidad,
    tipo_contratacion: TipoContratacion,
) -> BaseModalidadAgent:
    """Compat: historicamente devolvía el experto único; ahora = Analista."""
    return get_agente(modalidad, tipo_contratacion, RolAgente.ANALISTA)


def listar_agentes_registrados() -> list[tuple[str, str]]:
    return [(m.value, r.value) for (m, r) in _REGISTRY]
