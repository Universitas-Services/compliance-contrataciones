"""API de sesiones conversacionales de compliance."""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from openai import APIError, APITimeoutError, RateLimitError

from app.agents.cuestionario import (
    mensaje_pregunta_actual,
    sincronizar_informe_documento,
)
from app.agents.extractor import procesar_archivo
from app.agents.modalities import get_modalidad_agent
from app.agents.orchestrator import crear_sesion, ejecutar_dictamen_juridico, procesar_mensaje
from app.agents.report_agent import (
    DocumentoNoEncontradoError,
    InformeNoDisponibleError,
    SesionNoEncontradaError,
    export_dictamen_juridico,
    export_documento,
    export_global,
    informe_documento_markdown,
    informe_global_markdown,
)
from app.core import session_store
from app.core.llm_client import analizar_documento
from app.core.security import (
    max_upload_bytes,
    sanitizar_nombre_archivo,
    validar_extension_upload,
)
from app.models.schemas import (
    AnalisisDocumentoResponse,
    CrearSesionRequest,
    CrearSesionResponse,
    DocumentoAnalizado,
    EstadoSesion,
    ExtraccionMeta,
    InformeMarkdownResponse,
    JuridicoRequest,
    JuridicoResponse,
    MensajeRequest,
    MensajeResponse,
    Observacion,
    PreguntaSeguimiento,
    RespuestasDocumentoRequest,
    SesionCompliance,
    SesionResumen,
    TipoDocumento,
)

router = APIRouter(prefix="/sesiones", tags=["sesiones"])

_SEVERIDADES = {"info", "advertencia", "critica"}


def _require_sesion(sesion_id: str) -> SesionCompliance:
    sesion = session_store.get_sesion(sesion_id)
    if sesion is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return sesion


def _parse_observaciones(raw: object) -> list[Observacion]:
    if not isinstance(raw, list):
        return []
    out: list[Observacion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        severidad = str(item.get("severidad", "advertencia")).lower()
        if severidad not in _SEVERIDADES:
            severidad = "advertencia"
        descripcion = str(item.get("descripcion", "")).strip()
        if not descripcion:
            continue
        subs = item.get("subsanacion")
        ref = item.get("ref")
        out.append(
            Observacion(
                severidad=severidad,  # type: ignore[arg-type]
                descripcion=descripcion,
                subsanacion=str(subs).strip() if subs else None,
                ref=str(ref).strip() if ref else None,
            )
        )
    return out


def _slots_pendientes(sesion: SesionCompliance) -> list[TipoDocumento]:
    """Slots sin un documento de identidad correcta (tipo_coincide)."""
    auditados = {
        d.tipo for d in sesion.documentos_analizados if getattr(d, "tipo_coincide", True)
    }
    return [s.tipo_documento for s in sesion.checklist_slots if s.tipo_documento not in auditados]


def _asegurar_obs_tipo_incorrecto(
    observaciones: list[Observacion],
    *,
    tipo_declarado: TipoDocumento,
    tipo_detectado: str | None,
) -> list[Observacion]:
    """Garantiza observación crítica si el archivo no es el tipo declarado."""
    texto_clave = "tipo declarado"
    if any(texto_clave in o.descripcion.lower() or "no corresponde" in o.descripcion.lower() for o in observaciones):
        return observaciones
    detectado = tipo_detectado or "otro tipo de documento"
    observaciones = list(observaciones)
    observaciones.insert(
        0,
        Observacion(
            severidad="critica",
            descripcion=(
                f"El archivo no corresponde al tipo declarado ({tipo_declarado.value}). "
                f"Se detectó: {detectado}."
            ),
            subsanacion=(
                f"Sube el documento correcto para «{tipo_declarado.value}» "
                "o vuelve a cargar este archivo eligiendo el tipo que realmente es."
            ),
        ),
    )
    return observaciones


def _sesion_resumen(sesion: SesionCompliance) -> SesionResumen:
    hint = None
    if sesion.historial:
        hint = sesion.historial[-1].timestamp.isoformat()
    elif sesion.documentos_analizados:
        hint = sesion.documentos_analizados[-1].fecha_analisis.isoformat()
    return SesionResumen(
        id=sesion.id,
        nomenclatura=sesion.nomenclatura,
        modalidad=sesion.modalidad,
        tipo_contratacion=sesion.tipo_contratacion,
        estado=sesion.estado,
        docs_count=len(sesion.documentos_analizados),
        updated_hint=hint,
    )


@router.get("/", response_model=list[SesionResumen])
def listar_sesiones() -> list[SesionResumen]:
    """Lista todas las sesiones en memoria (panel izquierdo del frontend)."""
    sesiones = session_store.listar_sesiones()
    # Más recientes primero según updated_hint / historial
    resumenes = [_sesion_resumen(s) for s in sesiones]
    resumenes.sort(key=lambda s: s.updated_hint or "", reverse=True)
    return resumenes


@router.post("/", response_model=CrearSesionResponse)
def abrir_sesion(body: CrearSesionRequest | None = None) -> CrearSesionResponse:
    body = body or CrearSesionRequest()
    sesion, mensaje = crear_sesion(
        nomenclatura=body.nomenclatura,
        modalidad=body.modalidad,
        tipo_contratacion=body.tipo_contratacion,
    )
    return CrearSesionResponse(sesion=sesion, mensaje=mensaje)


@router.post("/{sesion_id}/mensaje", response_model=MensajeResponse)
def enviar_mensaje(sesion_id: str, body: MensajeRequest) -> MensajeResponse:
    try:
        sesion, respuesta = procesar_mensaje(sesion_id, body.mensaje)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (APITimeoutError, RateLimitError, APIError) as exc:
        raise HTTPException(status_code=502, detail=f"Error LLM: {exc}") from exc
    return MensajeResponse(sesion=sesion, respuesta=respuesta)


@router.get("/{sesion_id}", response_model=SesionCompliance)
def obtener_sesion(sesion_id: str) -> SesionCompliance:
    return _require_sesion(sesion_id)


@router.get("/{sesion_id}/checklist")
def obtener_checklist(sesion_id: str):
    sesion = _require_sesion(sesion_id)
    if sesion.estado == EstadoSesion.CONFIGURANDO or not sesion.checklist_slots:
        raise HTTPException(
            status_code=409,
            detail="La sesión aún no está configurada (falta nomenclatura/modalidad/tipo).",
        )
    return {
        "modalidad": sesion.modalidad,
        "tipo_contratacion": sesion.tipo_contratacion,
        "slots": sesion.checklist_slots,
        "pendientes": _slots_pendientes(sesion),
    }


@router.post("/{sesion_id}/documentos", response_model=AnalisisDocumentoResponse)
async def cargar_documento(
    sesion_id: str,
    archivo: UploadFile = File(...),
    tipo_documento: TipoDocumento | None = Query(default=None),
    tipo_documento_form: TipoDocumento | None = Form(default=None, alias="tipo_documento"),
) -> AnalisisDocumentoResponse:
    tipo = tipo_documento if tipo_documento is not None else tipo_documento_form
    if tipo is None:
        raise HTTPException(
            status_code=422,
            detail="Se requiere tipo_documento (query o form).",
        )

    sesion = _require_sesion(sesion_id)
    if sesion.estado != EstadoSesion.ACTIVA or not sesion.modalidad or not sesion.tipo_contratacion:
        raise HTTPException(
            status_code=409,
            detail="Configura nomenclatura, modalidad y tipo antes de cargar documentos.",
        )

    agent = get_modalidad_agent(sesion.modalidad, sesion.tipo_contratacion)
    requisitos = agent.requisitos(tipo)
    preguntas = agent.preguntas(tipo)

    nombre_seguro = sanitizar_nombre_archivo(archivo.filename)
    try:
        suffix = validar_extension_upload(nombre_seguro)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    limite = max_upload_bytes()
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            total = 0
            while True:
                chunk = await archivo.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limite:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Archivo demasiado grande. Máximo "
                            f"{limite // (1024 * 1024)} MB."
                        ),
                    )
                tmp.write(chunk)

        procesado = procesar_archivo(tmp_path, nombre_seguro)
        docs_previos = "\n".join(
            f"- {d.tipo.value} | {d.nombre_archivo} | cumple={d.cumple} | {d.resumen[:160]}"
            for d in sesion.documentos_analizados
        )
        analisis = analizar_documento(
            tipo,
            procesado,
            requisitos,
            system_experto=agent.system_prompt_experto(),
            preguntas_preestablecidas=preguntas,
            modalidad=sesion.modalidad,
            nomenclatura=sesion.nomenclatura,
            docs_previos_resumen=docs_previos,
        )

        preg_objs: list[PreguntaSeguimiento] = []
        tipo_coincide = analisis.get("tipo_coincide")
        if tipo_coincide is None:
            tipo_coincide = True
        tipo_coincide = bool(tipo_coincide)
        tipo_detectado_raw = analisis.get("tipo_detectado")
        tipo_detectado = (
            str(tipo_detectado_raw).strip() if tipo_detectado_raw not in (None, "") else None
        )

        # Cuestionario solo si el archivo es del tipo declarado
        if tipo_coincide:
            seen_q: set[str] = set()
            for texto in preguntas:
                t = str(texto).strip()
                if not t or t in seen_q:
                    continue
                seen_q.add(t)
                preg_objs.append(
                    PreguntaSeguimiento(id=f"q{len(preg_objs)+1}", texto=t)
                )
            # Añade sugerencias del modelo que no dupliquen el catálogo
            extra = analisis.get("preguntas_sugeridas") or []
            if isinstance(extra, list):
                for texto in extra:
                    t = str(texto).strip()
                    if not t or t in seen_q:
                        continue
                    seen_q.add(t)
                    preg_objs.append(
                        PreguntaSeguimiento(id=f"q{len(preg_objs)+1}", texto=t)
                    )

        observaciones = _parse_observaciones(analisis.get("observaciones"))
        cumple = bool(analisis.get("cumple", False))
        if not tipo_coincide:
            cumple = False
            observaciones = _asegurar_obs_tipo_incorrecto(
                observaciones,
                tipo_declarado=tipo,
                tipo_detectado=tipo_detectado,
            )

        canon = procesado.get("canonico") or {}
        extraccion = ExtraccionMeta(
            metodo=str(canon.get("metodo") or procesado.get("modo") or "texto"),
            paginas=int(canon.get("paginas") or 0),
            bloques=int(canon.get("bloques") or 0),
            advertencias=list(canon.get("advertencias") or []),
            cobertura_ocr=canon.get("cobertura_ocr"),
        )
        # Truncar texto persistido para no inflar el store (máx ~80k chars)
        texto_ext = str(procesado.get("texto_extraido") or "")
        if len(texto_ext) > 80000:
            texto_ext = texto_ext[:80000] + "\n…[truncado en persistencia]"

        documento = DocumentoAnalizado(
            id=str(uuid.uuid4()),
            tipo=tipo,
            nombre_archivo=nombre_seguro,
            resumen=str(analisis.get("resumen", "")),
            observaciones=observaciones,
            cumple=cumple,
            fecha_analisis=datetime.now(timezone.utc),
            informe_markdown=str(analisis.get("informe_markdown", "")),
            preguntas_seguimiento=preg_objs,
            tipo_coincide=tipo_coincide,
            tipo_detectado=tipo_detectado,
            texto_extraido=texto_ext,
            extraccion=extraccion,
        )
        if preg_objs:
            sincronizar_informe_documento(documento)

        sesion.documentos_analizados.append(documento)
        # Solo marcar el slot como auditado si el archivo es del tipo declarado
        if tipo_coincide:
            for slot in sesion.checklist_slots:
                if slot.tipo_documento == tipo:
                    slot.auditado = True

        pendientes = _slots_pendientes(sesion)
        if not tipo_coincide:
            sesion.documento_en_cuestionario = None
            msg = (
                f"Documento incorrecto: declaraste {tipo.value}, pero el archivo "
                f"parece ser {tipo_detectado or 'de otro tipo'}. "
                "No se marca el slot como auditado y no se inicia cuestionario. "
                "Vuelve a subir el archivo correcto o elige el tipo adecuado. "
                f"Informe en /documentos/{documento.id}/informe."
            )
        else:
            msg = (
                f"Documento {tipo.value} analizado (cumple={documento.cumple}). "
                f"Informe disponible en /documentos/{documento.id}/informe "
                f"(también .pdf / .docx)."
            )
            if pendientes:
                msg += f" Slots sugeridos aún sin auditar: {len(pendientes)}."
            if preg_objs:
                sesion.documento_en_cuestionario = documento.id
                msg += (
                    "\n\nInicio el cuestionario de seguimiento de este documento. "
                    "Responde en el chat (o en el panel de preguntas).\n\n"
                    + mensaje_pregunta_actual(documento)
                )

        session_store.guardar_sesion(sesion.id, sesion)
        return AnalisisDocumentoResponse(
            documento=documento,
            mensaje=msg,
            slots_pendientes=pendientes,
        )
    except APITimeoutError as exc:
        raise HTTPException(status_code=504, detail="Timeout del modelo LLM.") from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail="Rate limit del proveedor LLM.") from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"Error LLM: {exc.message or exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@router.post("/{sesion_id}/juridico", response_model=JuridicoResponse)
def revision_juridica(sesion_id: str, body: JuridicoRequest) -> JuridicoResponse:
    sesion = _require_sesion(sesion_id)
    try:
        dictamen = ejecutar_dictamen_juridico(
            sesion,
            mensaje=body.mensaje,
            documento_ids=body.documento_ids,
            forzar_final=body.forzar_final,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except APITimeoutError as exc:
        raise HTTPException(status_code=504, detail="Timeout del modelo LLM.") from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail="Rate limit del proveedor LLM.") from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"Error LLM: {exc.message or exc}") from exc

    session_store.guardar_sesion(sesion.id, sesion)
    return JuridicoResponse(
        sesion=sesion,
        dictamen=dictamen,
        respuesta=dictamen.markdown,
    )


@router.get("/{sesion_id}/juridico/{dictamen_id}/informe.pdf")
def get_dictamen_juridico_pdf(sesion_id: str, dictamen_id: str):
    try:
        data, media, filename = export_dictamen_juridico(
            sesion_id, dictamen_id, "pdf"
        )
    except SesionNoEncontradaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentoNoEncontradoError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{sesion_id}/juridico/{dictamen_id}/informe.docx")
def get_dictamen_juridico_docx(sesion_id: str, dictamen_id: str):
    try:
        data, media, filename = export_dictamen_juridico(
            sesion_id, dictamen_id, "docx"
        )
    except SesionNoEncontradaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentoNoEncontradoError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{sesion_id}/documentos/{doc_id}/respuestas", response_model=DocumentoAnalizado)
def responder_preguntas(
    sesion_id: str,
    doc_id: str,
    body: RespuestasDocumentoRequest,
) -> DocumentoAnalizado:
    from app.agents.cuestionario import pregunta_pendiente, registrar_respuesta

    sesion = _require_sesion(sesion_id)
    doc = next((d for d in sesion.documentos_analizados if d.id == doc_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    for pregunta in doc.preguntas_seguimiento:
        if pregunta.id in body.respuestas:
            registrar_respuesta(
                doc,
                body.respuestas[pregunta.id],
                pregunta_id=pregunta.id,
            )

    sincronizar_informe_documento(doc)
    if pregunta_pendiente(doc) is None:
        if sesion.documento_en_cuestionario == doc.id:
            sesion.documento_en_cuestionario = None
    else:
        sesion.documento_en_cuestionario = doc.id

    session_store.guardar_sesion(sesion.id, sesion)
    return doc


@router.get("/{sesion_id}/documentos/{doc_id}/informe", response_model=InformeMarkdownResponse)
def get_informe_documento(sesion_id: str, doc_id: str) -> InformeMarkdownResponse:
    try:
        md = informe_documento_markdown(sesion_id, doc_id)
    except SesionNoEncontradaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentoNoEncontradoError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return InformeMarkdownResponse(informe_markdown=md)


@router.get("/{sesion_id}/documentos/{doc_id}/informe.pdf")
def get_informe_documento_pdf(sesion_id: str, doc_id: str):
    try:
        data, media, filename = export_documento(sesion_id, doc_id, "pdf")
    except (SesionNoEncontradaError, DocumentoNoEncontradoError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{sesion_id}/documentos/{doc_id}/informe.docx")
def get_informe_documento_docx(sesion_id: str, doc_id: str):
    try:
        data, media, filename = export_documento(sesion_id, doc_id, "docx")
    except (SesionNoEncontradaError, DocumentoNoEncontradoError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{sesion_id}/informe", response_model=InformeMarkdownResponse)
def get_informe_global(
    sesion_id: str,
    usar_llm: bool = Query(default=True),
) -> InformeMarkdownResponse:
    try:
        md = informe_global_markdown(sesion_id, usar_llm=usar_llm)
    except SesionNoEncontradaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InformeNoDisponibleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (APITimeoutError, RateLimitError, APIError) as exc:
        raise HTTPException(status_code=502, detail=f"Error LLM: {exc}") from exc
    return InformeMarkdownResponse(informe_markdown=md)


@router.get("/{sesion_id}/informe.pdf")
def get_informe_global_pdf(
    sesion_id: str,
    usar_llm: bool = Query(default=True),
):
    try:
        data, media, filename = export_global(sesion_id, "pdf", usar_llm=usar_llm)
    except SesionNoEncontradaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InformeNoDisponibleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (APITimeoutError, RateLimitError, APIError) as exc:
        raise HTTPException(status_code=502, detail=f"Error LLM: {exc}") from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{sesion_id}/informe.docx")
def get_informe_global_docx(
    sesion_id: str,
    usar_llm: bool = Query(default=True),
):
    try:
        data, media, filename = export_global(sesion_id, "docx", usar_llm=usar_llm)
    except SesionNoEncontradaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InformeNoDisponibleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (APITimeoutError, RateLimitError, APIError) as exc:
        raise HTTPException(status_code=502, detail=f"Error LLM: {exc}") from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
