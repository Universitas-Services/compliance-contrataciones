"""Esquemas Pydantic del dominio de compliance multi-modalidad."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TipoContratacion(str, Enum):
    """Objeto de la contratación: bienes, obras o servicios."""

    BIENES = "BIENES"
    OBRAS = "OBRAS"
    SERVICIOS = "SERVICIOS"


class Modalidad(str, Enum):
    """Modalidades de selección / contratación del RLCP."""

    CA_ACTO_UNICO_APERTURA_UNICA = "CA_ACTO_UNICO_APERTURA_UNICA"
    CA_ACTO_UNICO_APERTURA_DIFERIDA = "CA_ACTO_UNICO_APERTURA_DIFERIDA"
    CA_ACTO_SEPARADO = "CA_ACTO_SEPARADO"
    CONCURSO_CERRADO = "CONCURSO_CERRADO"
    CONSULTA_PRECIO = "CONSULTA_PRECIO"
    CONTRATACION_DIRECTA = "CONTRATACION_DIRECTA"
    MODALIDADES_EXCLUIDAS = "MODALIDADES_EXCLUIDAS"


class EstadoSesion(str, Enum):
    """Estado del ciclo de vida de una sesión de compliance."""

    CONFIGURANDO = "CONFIGURANDO"
    ACTIVA = "ACTIVA"
    CERRADA = "CERRADA"


class RolAgente(str, Enum):
    """Rol dentro de la dupla por modalidad."""

    ANALISTA = "ANALISTA"
    JURIDICO = "JURIDICO"


class AlcanceDictamen(str, Enum):
    """Si el dictamen cubre el expediente completo o solo lo auditado hasta ahora."""

    PARCIAL = "PARCIAL"
    FINAL = "FINAL"


class TipoDocumento(str, Enum):
    """Catálogo unificado de documentos del expediente de selección."""

    SOLICITUD_UNIDAD_USUARIA = "SOLICITUD_UNIDAD_USUARIA"
    ACTA_INICIO = "ACTA_INICIO"
    PLIEGO_CONDICIONES = "PLIEGO_CONDICIONES"
    ACTOS_MOTIVADOS = "ACTOS_MOTIVADOS"
    LLAMADO_INVITACION = "LLAMADO_INVITACION"
    MODIFICACIONES_PLIEGO = "MODIFICACIONES_PLIEGO"
    ACTA_RECEPCION_OFERTAS = "ACTA_RECEPCION_OFERTAS"
    OFERTAS_RECIBIDAS = "OFERTAS_RECIBIDAS"
    INFORME_ANALISIS_RECOMENDACION = "INFORME_ANALISIS_RECOMENDACION"
    DOCUMENTO_ADJUDICACION = "DOCUMENTO_ADJUDICACION"
    NOTIFICACION_ADJUDICACION = "NOTIFICACION_ADJUDICACION"
    CONTRATO = "CONTRATO"
    JUSTIFICACION_CONTRATACION_DIRECTA = "JUSTIFICACION_CONTRATACION_DIRECTA"
    INVITACION_CERRADA = "INVITACION_CERRADA"
    SOLICITUD_COTIZACIONES = "SOLICITUD_COTIZACIONES"
    COMPARATIVO_PRECIOS = "COMPARATIVO_PRECIOS"
    ACTA_APERTURA_TECNICA = "ACTA_APERTURA_TECNICA"
    ACTA_APERTURA_ECONOMICA = "ACTA_APERTURA_ECONOMICA"
    DOCUMENTO_EXCLUSION = "DOCUMENTO_EXCLUSION"
    OTROS = "OTROS"


class RolMensaje(str, Enum):
    """Rol en el historial conversacional."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Observacion(BaseModel):
    """Hallazgo de auditoría sobre un documento."""

    severidad: Literal["info", "advertencia", "critica"]
    descripcion: str
    subsanacion: str | None = None
    ref: str | None = None


class PreguntaSeguimiento(BaseModel):
    """Pregunta preestablecida asociada a un documento auditado."""

    id: str
    texto: str
    respondida: bool = False
    respuesta: str | None = None


class SlotChecklist(BaseModel):
    """Slot sugerido del checklist dinámico (no obligatorio ni ordenado)."""

    tipo_documento: TipoDocumento
    descripcion: str
    elementos_requeridos: list[str] = Field(default_factory=list)
    auditado: bool = False


class MensajeChat(BaseModel):
    """Turno del historial de chat de la sesión."""

    rol: RolMensaje
    contenido: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ExtraccionMeta(BaseModel):
    """Metadatos de extracción previa al análisis LLM."""

    metodo: str = "texto"
    paginas: int = 0
    bloques: int = 0
    advertencias: list[str] = Field(default_factory=list)
    cobertura_ocr: float | None = None


class DocumentoAnalizado(BaseModel):
    """Resultado del análisis de un documento cargado a la sesión."""

    id: str
    tipo: TipoDocumento
    nombre_archivo: str
    resumen: str
    observaciones: list[Observacion] = Field(default_factory=list)
    cumple: bool
    fecha_analisis: datetime
    informe_markdown: str = ""
    preguntas_seguimiento: list[PreguntaSeguimiento] = Field(default_factory=list)
    tipo_coincide: bool = True
    tipo_detectado: str | None = None
    texto_extraido: str = ""
    extraccion: ExtraccionMeta | None = None


class DictamenJuridico(BaseModel):
    """Dictamen del agente Jurídico persistido en la sesión."""

    id: str
    fecha: datetime = Field(default_factory=datetime.utcnow)
    alcance: AlcanceDictamen = AlcanceDictamen.PARCIAL
    documento_ids: list[str] = Field(default_factory=list)
    mensaje_usuario: str = ""
    markdown: str = ""
    slots_pendientes: list[TipoDocumento] = Field(default_factory=list)


class SesionCompliance(BaseModel):
    """Sesión conversacional de auditoría de compliance."""

    id: str
    nomenclatura: str | None = None
    modalidad: Modalidad | None = None
    tipo_contratacion: TipoContratacion | None = None
    estado: EstadoSesion = EstadoSesion.CONFIGURANDO
    historial: list[MensajeChat] = Field(default_factory=list)
    checklist_slots: list[SlotChecklist] = Field(default_factory=list)
    documentos_analizados: list[DocumentoAnalizado] = Field(default_factory=list)
    # Documento cuyo cuestionario de seguimiento está activo (uno a la vez).
    documento_en_cuestionario: str | None = None
    # True si el usuario pidió cambiar nomenclatura y aún no envió el código nuevo.
    pendiente_cambio_nomenclatura: bool = False
    dictamenes_juridicos: list[DictamenJuridico] = Field(default_factory=list)


class SesionResumen(BaseModel):
    """Resumen liviano para el panel de sesiones del frontend."""

    id: str
    nomenclatura: str | None = None
    modalidad: Modalidad | None = None
    tipo_contratacion: TipoContratacion | None = None
    estado: EstadoSesion
    docs_count: int = 0
    updated_hint: str | None = None


class CrearSesionRequest(BaseModel):
    """Alta de sesión; campos opcionales activan la sesión de inmediato."""

    nomenclatura: str | None = None
    modalidad: Modalidad | None = None
    tipo_contratacion: TipoContratacion | None = None


class CrearSesionResponse(BaseModel):
    sesion: SesionCompliance
    mensaje: str


class MensajeRequest(BaseModel):
    mensaje: str


class MensajeResponse(BaseModel):
    sesion: SesionCompliance
    respuesta: str


class AnalisisDocumentoResponse(BaseModel):
    documento: DocumentoAnalizado
    mensaje: str
    slots_pendientes: list[TipoDocumento] = Field(default_factory=list)


class RespuestasDocumentoRequest(BaseModel):
    respuestas: dict[str, str] = Field(
        ...,
        description="Mapa pregunta_id -> respuesta del usuario",
    )


class InformeMarkdownResponse(BaseModel):
    informe_markdown: str


class JuridicoRequest(BaseModel):
    mensaje: str = (
        "Emite una revisión jurídica del expediente con los documentos "
        "y respuestas disponibles hasta ahora."
    )
    documento_ids: list[str] | None = None
    forzar_final: bool = False


class JuridicoResponse(BaseModel):
    sesion: SesionCompliance
    dictamen: DictamenJuridico
    respuesta: str
