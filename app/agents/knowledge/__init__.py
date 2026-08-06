"""Knowledge base placeholder por modalidad × tipo de contratación."""

from __future__ import annotations

from typing import TypedDict

from app.agents.knowledge.preguntas import preguntas_para
from app.models.schemas import Modalidad, TipoContratacion, TipoDocumento

PLACEHOLDER = "(pendiente de definir con basamento legal específico)"

ACTA_INICIO_ELEMENTOS = [
    "Descripción del objeto de la contratación y número del procedimiento",
    "Monto estimado de la contratación",
    "Verificación de la situación legal de las empresas (RNC)",
    "Empresas seleccionadas con Nivel Estimado de Contratación y Calificación Financiera",
    "Razones técnicas que fundamentaron la escogencia de las empresas participantes",
    "Cronograma de ejecución de la modalidad de selección",
    "Firma de los miembros de la Comisión de Contrataciones",
]


class SlotDef(TypedDict):
    tipo_documento: TipoDocumento
    descripcion: str
    elementos_requeridos: list[str]


class RamaKnowledge(TypedDict):
    slots: list[SlotDef]
    preguntas_por_documento: dict[TipoDocumento, list[str]]


class ModalidadKnowledge(TypedDict):
    descripcion: str
    ramas: dict[TipoContratacion, RamaKnowledge]


def _slot(
    tipo: TipoDocumento,
    descripcion: str,
    elementos: list[str] | None = None,
) -> SlotDef:
    return {
        "tipo_documento": tipo,
        "descripcion": descripcion,
        "elementos_requeridos": list(elementos or [PLACEHOLDER]),
    }


def _preguntas_rama(
    modalidad: Modalidad,
    tipo: TipoContratacion,
    slots: list[SlotDef],
) -> dict[TipoDocumento, list[str]]:
    return {
        s["tipo_documento"]: preguntas_para(modalidad, tipo, s["tipo_documento"])
        for s in slots
    }


def _preguntas_base(tipo: TipoDocumento) -> list[str]:
    # Compat: preferir catálogo genérico vía BIENES + CA apertura única como neutro.
    return preguntas_para(
        Modalidad.CA_ACTO_UNICO_APERTURA_UNICA,
        TipoContratacion.BIENES,
        tipo,
    )


def _rama_ca_comun(*, apertura_unica: bool = True) -> RamaKnowledge:
    slots: list[SlotDef] = [
        _slot(
            TipoDocumento.SOLICITUD_UNIDAD_USUARIA,
            "Solicitud formal de la unidad usuaria que inicia el procedimiento.",
        ),
        _slot(
            TipoDocumento.ACTA_INICIO,
            "Acta de inicio del procedimiento de selección.",
            ACTA_INICIO_ELEMENTOS if apertura_unica else [PLACEHOLDER],
        ),
        _slot(
            TipoDocumento.PLIEGO_CONDICIONES,
            "Pliego de condiciones que rige el concurso.",
        ),
        _slot(
            TipoDocumento.ACTOS_MOTIVADOS,
            "Actos motivados del procedimiento.",
        ),
        _slot(
            TipoDocumento.LLAMADO_INVITACION,
            "Llamado o invitación pública a presentar ofertas.",
        ),
        _slot(
            TipoDocumento.MODIFICACIONES_PLIEGO,
            "Modificaciones al pliego (si las hubiere).",
        ),
    ]
    if apertura_unica:
        slots.append(
            _slot(
                TipoDocumento.ACTA_RECEPCION_OFERTAS,
                "Acta de recepción/apertura única de ofertas.",
            )
        )
    else:
        slots.extend(
            [
                _slot(
                    TipoDocumento.ACTA_APERTURA_TECNICA,
                    "Acta de apertura de la oferta técnica (apertura diferida).",
                ),
                _slot(
                    TipoDocumento.ACTA_APERTURA_ECONOMICA,
                    "Acta de apertura de la oferta económica (apertura diferida).",
                ),
            ]
        )
    slots.extend(
        [
            _slot(
                TipoDocumento.OFERTAS_RECIBIDAS,
                "Ofertas presentadas por los oferentes.",
            ),
            _slot(
                TipoDocumento.INFORME_ANALISIS_RECOMENDACION,
                "Informe de análisis y recomendación.",
            ),
            _slot(
                TipoDocumento.DOCUMENTO_ADJUDICACION,
                "Documento de adjudicación.",
            ),
            _slot(
                TipoDocumento.NOTIFICACION_ADJUDICACION,
                "Notificación de adjudicación.",
            ),
            _slot(TipoDocumento.CONTRATO, "Contrato suscrito."),
            _slot(TipoDocumento.OTROS, "Documentos complementarios."),
        ]
    )
    preguntas = {s["tipo_documento"]: _preguntas_base(s["tipo_documento"]) for s in slots}
    return {"slots": slots, "preguntas_por_documento": preguntas}


def _rama_para_todos(
    builder,
    *,
    modalidad: Modalidad,
) -> dict[TipoContratacion, RamaKnowledge]:
    """Construye rama por BIENES/OBRAS/SERVICIOS con preguntas especializadas."""
    out: dict[TipoContratacion, RamaKnowledge] = {}
    for tipo in TipoContratacion:
        base = builder()
        slots = base["slots"]
        out[tipo] = {
            "slots": slots,
            "preguntas_por_documento": _preguntas_rama(modalidad, tipo, slots),
        }
    return out


def _rama_concurso_cerrado() -> RamaKnowledge:
    slots = [
        _slot(TipoDocumento.SOLICITUD_UNIDAD_USUARIA, "Solicitud de la unidad usuaria."),
        _slot(TipoDocumento.ACTA_INICIO, "Acta de inicio / selección de invitados."),
        _slot(TipoDocumento.INVITACION_CERRADA, "Invitación dirigida a oferentes preseleccionados."),
        _slot(TipoDocumento.PLIEGO_CONDICIONES, "Pliego de condiciones."),
        _slot(TipoDocumento.ACTA_RECEPCION_OFERTAS, "Acta de recepción de ofertas."),
        _slot(TipoDocumento.OFERTAS_RECIBIDAS, "Ofertas recibidas."),
        _slot(TipoDocumento.INFORME_ANALISIS_RECOMENDACION, "Informe de análisis."),
        _slot(TipoDocumento.DOCUMENTO_ADJUDICACION, "Adjudicación."),
        _slot(TipoDocumento.NOTIFICACION_ADJUDICACION, "Notificación."),
        _slot(TipoDocumento.CONTRATO, "Contrato."),
        _slot(TipoDocumento.OTROS, "Otros."),
    ]
    return {
        "slots": slots,
        "preguntas_por_documento": {
            s["tipo_documento"]: _preguntas_base(s["tipo_documento"]) for s in slots
        },
    }


def _rama_consulta_precio() -> RamaKnowledge:
    slots = [
        _slot(TipoDocumento.SOLICITUD_UNIDAD_USUARIA, "Solicitud de la unidad usuaria."),
        _slot(TipoDocumento.SOLICITUD_COTIZACIONES, "Solicitud de cotizaciones a proveedores."),
        _slot(TipoDocumento.COMPARATIVO_PRECIOS, "Cuadro comparativo de precios."),
        _slot(TipoDocumento.ACTOS_MOTIVADOS, "Acto motivado de selección."),
        _slot(TipoDocumento.DOCUMENTO_ADJUDICACION, "Adjudicación / orden de compra."),
        _slot(TipoDocumento.CONTRATO, "Contrato u orden formal (si aplica)."),
        _slot(TipoDocumento.OTROS, "Otros."),
    ]
    return {
        "slots": slots,
        "preguntas_por_documento": {
            s["tipo_documento"]: _preguntas_base(s["tipo_documento"]) for s in slots
        },
    }


def _rama_contratacion_directa() -> RamaKnowledge:
    slots = [
        _slot(
            TipoDocumento.JUSTIFICACION_CONTRATACION_DIRECTA,
            "Justificación de la contratación directa.",
        ),
        _slot(TipoDocumento.SOLICITUD_UNIDAD_USUARIA, "Solicitud de la unidad usuaria."),
        _slot(TipoDocumento.ACTOS_MOTIVADOS, "Actos motivados."),
        _slot(TipoDocumento.DOCUMENTO_ADJUDICACION, "Adjudicación directa."),
        _slot(TipoDocumento.CONTRATO, "Contrato."),
        _slot(TipoDocumento.OTROS, "Otros."),
    ]
    return {
        "slots": slots,
        "preguntas_por_documento": {
            s["tipo_documento"]: _preguntas_base(s["tipo_documento"]) for s in slots
        },
    }


def _rama_excluidas() -> RamaKnowledge:
    slots = [
        _slot(
            TipoDocumento.DOCUMENTO_EXCLUSION,
            "Documento que fundamenta la exclusión de modalidad ordinaria.",
        ),
        _slot(TipoDocumento.SOLICITUD_UNIDAD_USUARIA, "Solicitud / necesidad."),
        _slot(TipoDocumento.ACTOS_MOTIVADOS, "Acto motivado."),
        _slot(TipoDocumento.CONTRATO, "Instrumento contractual."),
        _slot(TipoDocumento.OTROS, "Otros."),
    ]
    return {
        "slots": slots,
        "preguntas_por_documento": {
            s["tipo_documento"]: _preguntas_base(s["tipo_documento"]) for s in slots
        },
    }


KNOWLEDGE: dict[Modalidad, ModalidadKnowledge] = {
    Modalidad.CA_ACTO_UNICO_APERTURA_UNICA: {
        "descripcion": (
            "Concurso Abierto — Acto único con apertura única. "
            "Checklist estructural típico del expediente de selección (placeholder salvo Acta de Inicio)."
        ),
        "ramas": _rama_para_todos(
            lambda: _rama_ca_comun(apertura_unica=True),
            modalidad=Modalidad.CA_ACTO_UNICO_APERTURA_UNICA,
        ),
    },
    Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA: {
        "descripcion": (
            "Concurso Abierto — Acto único con apertura diferida (técnica y económica por separado)."
        ),
        "ramas": _rama_para_todos(
            lambda: _rama_ca_comun(apertura_unica=False),
            modalidad=Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA,
        ),
    },
    Modalidad.CA_ACTO_SEPARADO: {
        "descripcion": "Concurso Abierto — Acto separado (placeholder de slots).",
        "ramas": _rama_para_todos(
            lambda: _rama_ca_comun(apertura_unica=False),
            modalidad=Modalidad.CA_ACTO_SEPARADO,
        ),
    },
    Modalidad.CONCURSO_CERRADO: {
        "descripcion": "Concurso cerrado con invitados preseleccionados.",
        "ramas": _rama_para_todos(
            _rama_concurso_cerrado,
            modalidad=Modalidad.CONCURSO_CERRADO,
        ),
    },
    Modalidad.CONSULTA_PRECIO: {
        "descripcion": "Consulta de precios / cotizaciones.",
        "ramas": _rama_para_todos(
            _rama_consulta_precio,
            modalidad=Modalidad.CONSULTA_PRECIO,
        ),
    },
    Modalidad.CONTRATACION_DIRECTA: {
        "descripcion": "Contratación directa debidamente justificada.",
        "ramas": _rama_para_todos(
            _rama_contratacion_directa,
            modalidad=Modalidad.CONTRATACION_DIRECTA,
        ),
    },
    Modalidad.MODALIDADES_EXCLUIDAS: {
        "descripcion": "Supuestos de modalidades excluidas del régimen ordinario.",
        "ramas": _rama_para_todos(
            _rama_excluidas,
            modalidad=Modalidad.MODALIDADES_EXCLUIDAS,
        ),
    },
}


def get_rama(modalidad: Modalidad, tipo: TipoContratacion) -> RamaKnowledge:
    return KNOWLEDGE[modalidad]["ramas"][tipo]


def get_descripcion_modalidad(modalidad: Modalidad) -> str:
    return KNOWLEDGE[modalidad]["descripcion"]


def etiqueta_modalidad(modalidad: Modalidad) -> str:
    labels = {
        Modalidad.CA_ACTO_UNICO_APERTURA_UNICA: "CA — Acto único / Apertura única",
        Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA: "CA — Acto único / Apertura diferida",
        Modalidad.CA_ACTO_SEPARADO: "CA — Acto separado",
        Modalidad.CONCURSO_CERRADO: "Concurso cerrado",
        Modalidad.CONSULTA_PRECIO: "Consulta de precio",
        Modalidad.CONTRATACION_DIRECTA: "Contratación directa",
        Modalidad.MODALIDADES_EXCLUIDAS: "Modalidades excluidas",
    }
    return labels[modalidad]
