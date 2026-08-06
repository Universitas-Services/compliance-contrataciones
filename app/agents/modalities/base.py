"""Bases de la dupla Analista + Jurídico por modalidad."""

from __future__ import annotations

from abc import ABC

from app.agents.knowledge import (
    etiqueta_modalidad,
    get_descripcion_modalidad,
    get_rama,
)
from app.agents.knowledge.preguntas import preguntas_para
from app.agents.modalities.prompts import prompt_analista, prompt_juridico
from app.models.schemas import (
    Modalidad,
    RolAgente,
    SlotChecklist,
    TipoContratacion,
    TipoDocumento,
)


class BaseModalidadAgent(ABC):
    """Base compartida: checklist/knowledge por modalidad × tipo."""

    modalidad: Modalidad
    rol: RolAgente

    def __init__(self, tipo_contratacion: TipoContratacion) -> None:
        self.tipo_contratacion = tipo_contratacion
        self._rama = get_rama(self.modalidad, tipo_contratacion)

    @property
    def descripcion(self) -> str:
        return get_descripcion_modalidad(self.modalidad)

    @property
    def etiqueta(self) -> str:
        return etiqueta_modalidad(self.modalidad)

    def obtener_checklist(self) -> list[SlotChecklist]:
        slots: list[SlotChecklist] = []
        for slot in self._rama["slots"]:
            slots.append(
                SlotChecklist(
                    tipo_documento=slot["tipo_documento"],
                    descripcion=slot["descripcion"],
                    elementos_requeridos=list(slot["elementos_requeridos"]),
                    auditado=False,
                )
            )
        return slots

    def requisitos(self, tipo: TipoDocumento) -> dict:
        for slot in self._rama["slots"]:
            if slot["tipo_documento"] == tipo:
                return {
                    "descripcion": slot["descripcion"],
                    "elementos_requeridos": list(slot["elementos_requeridos"]),
                }
        return {
            "descripcion": f"Documento {tipo.value} (fuera del checklist sugerido).",
            "elementos_requeridos": [
                "(pendiente de definir con basamento legal específico)"
            ],
        }

    def preguntas(self, tipo: TipoDocumento) -> list[str]:
        return preguntas_para(self.modalidad, self.tipo_contratacion, tipo)

    def system_prompt_experto(self) -> str:
        raise NotImplementedError


class BaseAnalistaAgent(BaseModalidadAgent):
    """Revisión de forma: identidad, checklist, JSON, criticidad."""

    rol = RolAgente.ANALISTA

    def system_prompt_experto(self) -> str:
        return prompt_analista(
            self.modalidad,
            self.tipo_contratacion.value,
            self.descripcion,
        )


class BaseJuridicoAgent(BaseModalidadAgent):
    """Revisión de fondo: riesgo, conclusiones, informe narrativo."""

    rol = RolAgente.JURIDICO

    def system_prompt_experto(self) -> str:
        return prompt_juridico(
            self.modalidad,
            self.tipo_contratacion.value,
            self.descripcion,
        )
