"""Preguntas de seguimiento por modalidad × tipo de contratación × documento.

Placeholders razonables de auditoría (PoC). Se especializarán con basamento legal.
"""

from __future__ import annotations

from app.models.schemas import Modalidad, TipoContratacion, TipoDocumento

# Preguntas transversales por tipo de documento (todas las modalidades).
_BASE: dict[TipoDocumento, list[str]] = {
    TipoDocumento.SOLICITUD_UNIDAD_USUARIA: [
        "¿La solicitud identifica de forma clara la necesidad y el objeto a contratar?",
        "¿Consta la unidad usuaria solicitante y la fecha de la solicitud?",
        "¿El alcance descrito es coherente con la modalidad de selección elegida?",
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
    TipoDocumento.ACTOS_MOTIVADOS: [
        "¿El acto motivado expresa de forma suficiente los fundamentos de hecho y de derecho?",
        "¿La decisión adoptada es coherente con los antecedentes del expediente?",
        "¿Identifica el órgano emisor, fecha y nomenclatura del procedimiento?",
    ],
    TipoDocumento.LLAMADO_INVITACION: [
        "¿El llamado/invitación publica el objeto, plazos y lugar de entrega de ofertas?",
        "¿Coincide la nomenclatura con la del resto del expediente?",
        "¿Se indica la modalidad de selección de forma expresa?",
    ],
    TipoDocumento.MODIFICACIONES_PLIEGO: [
        "¿La modificación está motivada y notificada a los interesados en tiempo hábil?",
        "¿Afecta requisitos esenciales o plazos de forma que deba reabrirse el proceso?",
        "¿Queda trazabilidad de la versión vigente del pliego?",
    ],
    TipoDocumento.ACTA_RECEPCION_OFERTAS: [
        "¿El acta registra fecha, hora, lugar y oferentes presentes/recibidos?",
        "¿Consta la integridad de los sobres o medios de presentación?",
        "¿Hay observaciones de los oferentes y cómo se trataron?",
    ],
    TipoDocumento.OFERTAS_RECIBIDAS: [
        "¿La oferta responde a los requisitos del pliego o invitación?",
        "¿Se identifica al oferente y la nomenclatura del procedimiento?",
        "¿Hay inconsistencias técnicas o económicas evidentes frente a lo solicitado?",
    ],
    TipoDocumento.INFORME_ANALISIS_RECOMENDACION: [
        "¿El informe aplica los criterios de evaluación previstos?",
        "¿La recomendación está sustentada en el análisis y es trazable?",
        "¿Se documentan descalificaciones o exclusiones con fundamento?",
    ],
    TipoDocumento.DOCUMENTO_ADJUDICACION: [
        "¿La adjudicación identifica al adjudicatario, el objeto y el monto?",
        "¿Es coherente con el informe de recomendación?",
        "¿Consta la autoridad competente y la fecha del acto?",
    ],
    TipoDocumento.NOTIFICACION_ADJUDICACION: [
        "¿Se notificó a adjudicatario y demás oferentes según corresponda?",
        "¿La notificación indica plazos para eventuales reclamos o formalización?",
        "¿Coincide con los datos del acto de adjudicación?",
    ],
    TipoDocumento.CONTRATO: [
        "¿El contrato identifica correctamente las partes, objeto, monto y plazo?",
        "¿Las obligaciones y condiciones son coherentes con la adjudicación y el pliego?",
        "¿Constan firmas / formalización válida de ambas partes?",
        "¿Hay cláusulas de garantías, penalidades y resolución acordes al expediente?",
    ],
    TipoDocumento.JUSTIFICACION_CONTRATACION_DIRECTA: [
        "¿La justificación encuadra el supuesto legal de contratación directa?",
        "¿Se acreditan los hechos que hacen procedente la excepción?",
        "¿Se evaluó la razonabilidad del proveedor y del precio?",
    ],
    TipoDocumento.INVITACION_CERRADA: [
        "¿La invitación se dirige a oferentes preseleccionados con fundamento?",
        "¿Se informa objeto, plazos y condiciones de participación?",
        "¿Hay evidencia de envío/recibo a todos los invitados?",
    ],
    TipoDocumento.SOLICITUD_COTIZACIONES: [
        "¿Se solicitó cotización a un número suficiente de proveedores?",
        "¿La solicitud describe el bien/servicio de forma comparable?",
        "¿Quedan constancias de envío y respuesta?",
    ],
    TipoDocumento.COMPARATIVO_PRECIOS: [
        "¿El comparativo enfrenta ofertas homogéneas (mismas especificaciones)?",
        "¿La selección del menor precio u oferta más conveniente está motivada?",
        "¿Se identifican exclusiones o cotizaciones incompletas?",
    ],
    TipoDocumento.ACTA_APERTURA_TECNICA: [
        "¿El acta de apertura técnica registra oferentes y cumplimiento formal?",
        "¿Se separa claramente la evaluación técnica de la económica?",
        "¿Hay firmas de la comisión y observaciones relevantes?",
    ],
    TipoDocumento.ACTA_APERTURA_ECONOMICA: [
        "¿Solo se abren ofertas económicas de quienes pasaron la fase técnica?",
        "¿Se registran montos ofertados de forma transparente?",
        "¿Coincide con el cronograma de apertura diferida?",
    ],
    TipoDocumento.DOCUMENTO_EXCLUSION: [
        "¿El documento identifica el supuesto de exclusión de la modalidad ordinaria?",
        "¿Fundamenta de hecho y de derecho por qué no aplica el régimen ordinario?",
        "¿Es coherente con el objeto y la urgencia/necesidad planteada?",
    ],
    TipoDocumento.OTROS: [
        "¿Qué aporte concreto tiene este documento en el expediente?",
        "¿Está referenciado o es coherente con la nomenclatura del procedimiento?",
        "¿Genera alguna observación de compliance que deba escalarse?",
    ],
}

# Matiz por tipo de contratación (se añaden a las base).
_EXTRA_TIPO: dict[TipoContratacion, dict[TipoDocumento, list[str]]] = {
    TipoContratacion.BIENES: {
        TipoDocumento.SOLICITUD_UNIDAD_USUARIA: [
            "¿Se especifican cantidades, unidad de medida y especificaciones técnicas mínimas del bien?",
        ],
        TipoDocumento.PLIEGO_CONDICIONES: [
            "¿El pliego detalla especificaciones técnicas, marca/referencia equivalentes y condiciones de entrega?",
        ],
        TipoDocumento.CONTRATO: [
            "¿El contrato fija cantidad, especificaciones, lugar y plazo de entrega de los bienes?",
        ],
        TipoDocumento.COMPARATIVO_PRECIOS: [
            "¿Las cotizaciones comparan el mismo bien (o equivalente técnico) y condiciones de entrega?",
        ],
    },
    TipoContratacion.OBRAS: {
        TipoDocumento.SOLICITUD_UNIDAD_USUARIA: [
            "¿La solicitud describe el alcance de la obra, ubicación y necesidad de intervención?",
        ],
        TipoDocumento.PLIEGO_CONDICIONES: [
            "¿Existen planos, memoria descriptiva o especificaciones de obra referenciadas en el pliego?",
        ],
        TipoDocumento.ACTA_INICIO: [
            "¿El acta contempla cronograma de obra y/o hitos de ejecución relevantes?",
        ],
        TipoDocumento.CONTRATO: [
            "¿El contrato fija plazo de ejecución, anticipos, retenciones y régimen de variaciones de obra?",
        ],
        TipoDocumento.INFORME_ANALISIS_RECOMENDACION: [
            "¿El análisis considera capacidad técnica/experiencia en obras similares de los oferentes?",
        ],
    },
    TipoContratacion.SERVICIOS: {
        TipoDocumento.SOLICITUD_UNIDAD_USUARIA: [
            "¿Se describen el alcance del servicio, frecuencia y resultados esperados?",
        ],
        TipoDocumento.PLIEGO_CONDICIONES: [
            "¿El pliego define niveles de servicio (SLA), personal mínimo o entregables medibles?",
        ],
        TipoDocumento.CONTRATO: [
            "¿El contrato establece forma de pago, indicadores de cumplimiento y penalidades por incumplimiento?",
        ],
        TipoDocumento.JUSTIFICACION_CONTRATACION_DIRECTA: [
            "¿Se justifica por qué el servicio no puede obtenerse mediante modalidad competitiva?",
        ],
    },
}

# Matiz por modalidad (se añaden a las base + tipo).
_EXTRA_MODALIDAD: dict[Modalidad, dict[TipoDocumento, list[str]]] = {
    Modalidad.CA_ACTO_UNICO_APERTURA_UNICA: {
        TipoDocumento.ACTA_RECEPCION_OFERTAS: [
            "¿La apertura única registra en el mismo acto los aspectos formales y económicos requeridos?",
        ],
        TipoDocumento.PLIEGO_CONDICIONES: [
            "¿El pliego es consistente con un concurso abierto de acto único / apertura única?",
        ],
    },
    Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA: {
        TipoDocumento.ACTA_APERTURA_TECNICA: [
            "¿Queda claro que la oferta económica permanece cerrada hasta la apertura diferida?",
        ],
        TipoDocumento.ACTA_APERTURA_ECONOMICA: [
            "¿Solo participan en la apertura económica quienes cumplieron la evaluación técnica?",
        ],
    },
    Modalidad.CA_ACTO_SEPARADO: {
        TipoDocumento.ACTA_APERTURA_TECNICA: [
            "¿El expediente refleja la separación de actos prevista para esta modalidad?",
        ],
    },
    Modalidad.CONCURSO_CERRADO: {
        TipoDocumento.ACTA_INICIO: [
            "¿Se documenta el criterio de preselección de los invitados al concurso cerrado?",
        ],
        TipoDocumento.INVITACION_CERRADA: [
            "¿Todos los preseleccionados recibieron la misma información y plazos?",
        ],
    },
    Modalidad.CONSULTA_PRECIO: {
        TipoDocumento.SOLICITUD_COTIZACIONES: [
            "¿El proceso de consulta de precios garantiza comparabilidad y trazabilidad de las cotizaciones?",
        ],
        TipoDocumento.COMPARATIVO_PRECIOS: [
            "¿La decisión se basa en el comparativo y no en criterios no documentados?",
        ],
    },
    Modalidad.CONTRATACION_DIRECTA: {
        TipoDocumento.JUSTIFICACION_CONTRATACION_DIRECTA: [
            "¿La justificación evita generalidades y acredita el supuesto concreto de contratación directa?",
        ],
        TipoDocumento.ACTOS_MOTIVADOS: [
            "¿El acto motivado remite expresamente a la justificación de la contratación directa?",
        ],
    },
    Modalidad.MODALIDADES_EXCLUIDAS: {
        TipoDocumento.DOCUMENTO_EXCLUSION: [
            "¿El documento de exclusión es previo o concurrente a la decisión de no usar modalidad ordinaria?",
        ],
        TipoDocumento.ACTOS_MOTIVADOS: [
            "¿El acto motivado enlaza de forma expresa con el fundamento de la exclusión?",
        ],
        TipoDocumento.CONTRATO: [
            "¿El instrumento contractual es coherente con el régimen de exclusión aplicado?",
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

    _add(_BASE.get(tipo_documento, [
        f"¿El documento {tipo_documento.value} es coherente con el expediente?",
        f"¿Identifica la nomenclatura del procedimiento en {tipo_documento.value}?",
        f"¿Hay observaciones de compliance relevantes en {tipo_documento.value}?",
    ]))
    _add(_EXTRA_TIPO.get(tipo_contratacion, {}).get(tipo_documento, []))
    _add(_EXTRA_MODALIDAD.get(modalidad, {}).get(tipo_documento, []))
    return out
