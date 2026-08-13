"""Preguntas de rúbrica por modalidad × tipo de contratación × documento.

Placeholders de auditoría; se especializarán con basamento legal.
"""

from __future__ import annotations

from app.models.schemas import Modalidad, TipoContratacion, TipoDocumento

_BASE: dict[TipoDocumento, list[str]] = {
    TipoDocumento.ACTIVIDADES_PREVIAS: [
        "¿Constan las actividades previas que fundamentan el inicio del procedimiento?",
        "¿Se identifica la necesidad u objeto a contratar de forma clara?",
        "¿Hay trazabilidad de la unidad / área responsable de la solicitud?",
    ],
    TipoDocumento.ACTA_INICIO: [
        "¿El acta de inicio identifica la nomenclatura del procedimiento?",
        "¿Constan el monto estimado y el objeto de la contratación?",
        "¿Figuran las firmas de la Comisión de Contrataciones (o órgano competente)?",
        "¿Se documenta la verificación RNC / situación legal de los participantes, si aplica?",
    ],
    TipoDocumento.PLIEGO_CONDICIONES: [
        "¿El pliego fija requisitos de participación y criterios de evaluación de forma clara?",
        "¿Incluye cronograma, garantías y condiciones de entrega o ejecución?",
        "¿Hay cláusulas discriminatorias o ambiguas que puedan afectar la competencia?",
    ],
    TipoDocumento.CONDICIONES_CONTRATACION: [
        "¿Las condiciones de contratación definen el objeto, plazos y obligaciones esenciales?",
        "¿Son coherentes con el acto motivado que autoriza el procedimiento?",
        "¿Identifican la nomenclatura del expediente?",
    ],
    TipoDocumento.LLAMADO: [
        "¿El llamado publica el objeto, plazos y lugar de entrega de ofertas?",
        "¿Coincide la nomenclatura con la del resto del expediente?",
        "¿Se indica la modalidad de selección de forma expresa?",
    ],
    TipoDocumento.INVITACIONES: [
        "¿La invitación identifica a los destinatarios y el objeto del procedimiento?",
        "¿Constan plazos y condiciones de presentación?",
        "¿Coincide la nomenclatura con el expediente?",
    ],
    TipoDocumento.PUNTO_DE_CUENTA: [
        "¿El punto de cuenta autoriza expresamente el inicio del procedimiento?",
        "¿Identifica objeto, modalidad y fundamento de la autorización?",
        "¿Consta la aprobación del órgano competente?",
    ],
    TipoDocumento.ACTO_MOTIVADO_INICIO: [
        "¿El acto motivado autoriza el inicio del procedimiento de forma expresa?",
        "¿Expone fundamentos de hecho y de derecho suficientes?",
        "¿Identifica nomenclatura, objeto y órgano emisor?",
    ],
    TipoDocumento.ACTA_RECEPCION_SOBRES: [
        "¿El acta registra fecha, hora, lugar y oferentes/sobres recibidos?",
        "¿Consta la integridad de los sobres o medios de presentación?",
        "¿Hay observaciones de los oferentes y cómo se trataron?",
    ],
    TipoDocumento.ACTA_APERTURA_SOBRES: [
        "¿El acta documenta la apertura en el momento correspondiente a la modalidad?",
        "¿Identifica las ofertas/sobres abiertos y asistentes?",
        "¿Registra observaciones relevantes de la apertura?",
    ],
    TipoDocumento.ACTA_RECEPCION_MV_CALIF_OFERTAS: [
        "¿Registra la recepción de manifestaciones de voluntad, calificación y/o ofertas?",
        "¿Constan fecha, hora, lugar e interesados presentados?",
        "¿Hay control de integridad de la documentación recibida?",
    ],
    TipoDocumento.ACTA_APERTURA_MV_CALIFICACION: [
        "¿Documenta la apertura de manifestaciones de voluntad y documentos de calificación?",
        "¿Identifica participantes y resultado formal del acto?",
        "¿Es coherente con la modalidad (diferida / cerrado / separado)?",
    ],
    TipoDocumento.INFORME_CALIFICACION: [
        "¿El informe evalúa los requisitos de calificación de forma motivada?",
        "¿Concluye con recomendación clara de habilitación o no?",
        "¿Se apoya en el pliego y en la documentación presentada?",
    ],
    TipoDocumento.NOTIFICACION_CALIFICACION: [
        "¿Notifica el resultado de la calificación a los interesados?",
        "¿Identifica el procedimiento y el sentido de la decisión?",
        "¿Consta medio y fecha de notificación?",
    ],
    TipoDocumento.ACTA_APERTURA_OFERTAS_DEVOLUCION: [
        "¿Documenta la apertura de ofertas y, si aplica, la devolución de sobres?",
        "¿Identifica oferentes y documentos abiertos?",
        "¿Registra observaciones del acto?",
    ],
    TipoDocumento.ACTA_RECEPCION_MV_CALIFICACION: [
        "¿Registra la recepción de manifestaciones de voluntad y documentos de calificación?",
        "¿Constan fecha, hora, lugar e interesados?",
        "¿Hay control de integridad de la documentación?",
    ],
    TipoDocumento.ACTA_RECEPCION_OFERTAS: [
        "¿El acta registra fecha, hora, lugar y ofertas recibidas?",
        "¿Consta la integridad de los sobres o medios de presentación?",
        "¿Hay observaciones de los oferentes?",
    ],
    TipoDocumento.ACTA_APERTURA_OFERTAS: [
        "¿Documenta la apertura de ofertas en el momento correspondiente?",
        "¿Identifica oferentes y contenido abierto?",
        "¿Registra observaciones del acto?",
    ],
    TipoDocumento.ACTA_RECEPCION_CALIF_OFERTAS: [
        "¿Registra la recepción de documentos de calificación y/o ofertas?",
        "¿Constan fecha, hora, lugar e interesados?",
        "¿Hay control de integridad de la documentación?",
    ],
    TipoDocumento.ACTA_APERTURA_CALIF_OFERTAS: [
        "¿Documenta la apertura de calificación y/o ofertas?",
        "¿Identifica participantes y resultado del acto?",
        "¿Es coherente con la consulta de precio?",
    ],
    TipoDocumento.OFERTAS: [
        "¿La oferta responde a los requisitos del pliego o invitación?",
        "¿Se identifica al oferente y la nomenclatura del procedimiento?",
        "¿La oferta económica/técnica es legible y completa en lo esencial?",
    ],
    TipoDocumento.GARANTIA_SOSTENIMIENTO_OFERTA: [
        "¿Consta la garantía de sostenimiento de la oferta cuando el pliego la exige?",
        "¿Identifica monto, vigencia y oferente?",
        "¿Es coherente con los requisitos del pliego?",
    ],
    TipoDocumento.INFORME_EVALUACION_RECOMENDACION: [
        "¿El informe motiva la evaluación conforme a los criterios del pliego?",
        "¿Formula una recomendación de adjudicación clara?",
        "¿Trata de forma homogénea a los oferentes evaluados?",
    ],
    TipoDocumento.INFORME_RECOMENDACION: [
        "¿El informe formula una recomendación motivada de adjudicación?",
        "¿Se apoya en la evaluación de las ofertas recibidas?",
        "¿Identifica el procedimiento y el oferente recomendado?",
    ],
    TipoDocumento.INFORME_VERIFICACION_RAZONABILIDAD: [
        "¿Verifica la razonabilidad de precios de forma documentada?",
        "¿Incluye recomendación asociada a la verificación?",
        "¿Es coherente con las ofertas e invitaciones del expediente?",
    ],
    TipoDocumento.INFORME_VERIFICACION_ADJUDICACION: [
        "¿El informe verifica y recomienda la adjudicación de forma motivada?",
        "¿Se apoya en la documentación del expediente?",
        "¿Identifica el procedimiento y la conclusión?",
    ],
    TipoDocumento.INFORME_OPINION_COMISION: [
        "¿Consta la opinión de la Comisión de Contrataciones?",
        "¿La opinión es congruente con el informe de evaluación/recomendación?",
        "¿Identifica el procedimiento y el sentido de la opinión?",
    ],
    TipoDocumento.ADJUDICACION_O_EQUIVALENTE: [
        "¿El acto de adjudicación (o equivalente) identifica al adjudicatario y el objeto?",
        "¿Es coherente con la recomendación previa?",
        "¿Consta fundamento y nomenclatura del procedimiento?",
    ],
    TipoDocumento.ADJUDICACION_ACTO_MOTIVADO: [
        "¿La adjudicación se formaliza mediante acto motivado?",
        "¿Expone fundamentos suficientes de hecho y de derecho?",
        "¿Identifica adjudicatario, objeto y nomenclatura?",
    ],
    TipoDocumento.NOTIFICACION_ADJUDICADOS: [
        "¿Se notifica la adjudicación al/los adjudicatario(s)?",
        "¿Identifica el procedimiento y el sentido de la decisión?",
        "¿Consta medio y fecha de notificación?",
    ],
    TipoDocumento.NOTIFICACION_NO_ADJUDICADOS: [
        "¿Se notifica el resultado a los no adjudicados?",
        "¿Identifica el procedimiento y el sentido de la decisión?",
        "¿Consta medio y fecha de notificación?",
    ],
    TipoDocumento.NOTIFICACION_INTERESADOS: [
        "¿Se notifica a los interesados el resultado relevante del procedimiento?",
        "¿Identifica nomenclatura y sentido de la comunicación?",
        "¿Consta medio y fecha de notificación?",
    ],
    TipoDocumento.CONTRATO: [
        "¿El contrato/orden identifica partes, objeto, monto y plazos?",
        "¿Es coherente con la adjudicación y el pliego/condiciones?",
        "¿Constan firmas o formalidades esenciales de perfeccionamiento?",
    ],
    TipoDocumento.RESPONSABILIDAD_SOCIAL: [
        "¿Consta la documentación de responsabilidad social exigida?",
        "¿Identifica el procedimiento y el alcance de la obligación?",
        "¿Es coherente con lo previsto en el pliego o normativa aplicable?",
    ],
    TipoDocumento.OTROS: [
        "¿El documento es pertinente al expediente y a la modalidad?",
        "¿Identifica la nomenclatura del procedimiento?",
        "¿Aporta hechos relevantes para la auditoría de compliance?",
    ],
}

_EXTRA_TIPO: dict[TipoContratacion, dict[TipoDocumento, list[str]]] = {
    TipoContratacion.BIENES: {
        TipoDocumento.PLIEGO_CONDICIONES: [
            "¿Las especificaciones técnicas de los bienes son verificables y no direccionadas?",
        ],
        TipoDocumento.CONTRATO: [
            "¿El contrato/orden precisa cantidades, unidad de medida y condiciones de entrega?",
        ],
    },
    TipoContratacion.OBRAS: {
        TipoDocumento.PLIEGO_CONDICIONES: [
            "¿El alcance de obra y el cronograma son suficientemente definidos?",
        ],
        TipoDocumento.ACTA_INICIO: [
            "¿El monto estimado es coherente con el alcance de obra descrito?",
        ],
        TipoDocumento.CONTRATO: [
            "¿El contrato de obra fija plazo de ejecución y forma de pago?",
        ],
    },
    TipoContratacion.SERVICIOS: {
        TipoDocumento.PLIEGO_CONDICIONES: [
            "¿El servicio contratado tiene entregables o niveles de servicio medibles?",
        ],
        TipoDocumento.CONTRATO: [
            "¿El contrato de servicio define alcance, plazo y contraprestación?",
        ],
    },
}

_EXTRA_MODALIDAD: dict[Modalidad, dict[TipoDocumento, list[str]]] = {
    Modalidad.CA_ACTO_UNICO_APERTURA_UNICA: {
        TipoDocumento.ACTA_APERTURA_SOBRES: [
            "¿La apertura es coherente con un acto único de apertura (técnica y económica cuando aplique)?",
        ],
    },
    Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA: {
        TipoDocumento.ACTA_APERTURA_MV_CALIFICACION: [
            "¿La apertura de calificación está separada de la apertura de ofertas conforme a la modalidad diferida?",
        ],
    },
    Modalidad.CA_ACTO_SEPARADO: {
        TipoDocumento.ACTA_RECEPCION_OFERTAS: [
            "¿La recepción de ofertas es posterior y separable de la fase de calificación?",
        ],
    },
    Modalidad.CONCURSO_CERRADO: {
        TipoDocumento.INVITACIONES: [
            "¿Las invitaciones se dirigen solo a oferentes preseleccionados?",
        ],
    },
    Modalidad.CONSULTA_PRECIO: {
        TipoDocumento.PUNTO_DE_CUENTA: [
            "¿El punto de cuenta es previo al inicio formal del procedimiento de consulta de precio?",
        ],
    },
    Modalidad.CONTRATACION_DIRECTA: {
        TipoDocumento.ACTO_MOTIVADO_INICIO: [
            "¿La autorización motiva el supuesto concreto de contratación directa?",
        ],
    },
    Modalidad.MODALIDADES_EXCLUIDAS: {
        TipoDocumento.ACTO_MOTIVADO_INICIO: [
            "¿El acto motiva de forma suficiente la aplicación del régimen de exclusión?",
        ],
        TipoDocumento.ADJUDICACION_ACTO_MOTIVADO: [
            "¿La adjudicación por acto motivado es coherente con el régimen de exclusión?",
        ],
    },
}


def preguntas_para(
    modalidad: Modalidad,
    tipo_contratacion: TipoContratacion,
    tipo_documento: TipoDocumento,
) -> list[str]:
    """Arma la lista de preguntas de seguimiento para un documento concreto."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(items: list[str]) -> None:
        for q in items:
            qn = q.strip()
            if qn and qn not in seen:
                seen.add(qn)
                out.append(qn)

    _add(
        _BASE.get(
            tipo_documento,
            [
                f"¿El documento {tipo_documento.value} es coherente con el expediente?",
                f"¿Identifica la nomenclatura del procedimiento?",
                "¿Hay observaciones de compliance relevantes?",
            ],
        )
    )
    _add(_EXTRA_TIPO.get(tipo_contratacion, {}).get(tipo_documento, []))
    _add(_EXTRA_MODALIDAD.get(modalidad, {}).get(tipo_documento, []))
    return out
