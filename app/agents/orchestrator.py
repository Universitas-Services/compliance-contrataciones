"""Orquestador conversacional de compliance multi-modalidad (dupla Analista/Jurídico)."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.agents.cuestionario import (
    documento_cuestionario_activo,
    mensaje_pregunta_actual,
    pregunta_pendiente,
    progreso_cuestionario,
    registrar_respuesta,
    sincronizar_informe_documento,
)
from app.agents.knowledge import etiqueta_modalidad
from app.agents.modalities import get_agente, get_modalidad_agent
from app.core import session_store
from app.core.llm_client import (
    chat_compliance,
    consultar_juridico,
    interpretar_cambio_nomenclatura,
    interpretar_turno_config,
)
from app.models.schemas import (
    AlcanceDictamen,
    DictamenJuridico,
    EstadoSesion,
    MensajeChat,
    Modalidad,
    RolAgente,
    RolMensaje,
    SesionCompliance,
    TipoContratacion,
    TipoDocumento,
)


def _config_completa(sesion: SesionCompliance) -> bool:
    return bool(sesion.nomenclatura and sesion.modalidad and sesion.tipo_contratacion)


def _slots_pendientes_vals(sesion: SesionCompliance) -> list[TipoDocumento]:
    auditados = {
        d.tipo for d in sesion.documentos_analizados if getattr(d, "tipo_coincide", True)
    }
    return [s.tipo_documento for s in sesion.checklist_slots if s.tipo_documento not in auditados]


def _activar_sesion(sesion: SesionCompliance) -> str:
    assert sesion.modalidad and sesion.tipo_contratacion
    agent = get_modalidad_agent(sesion.modalidad, sesion.tipo_contratacion)
    sesion.checklist_slots = agent.obtener_checklist()
    sesion.estado = EstadoSesion.ACTIVA
    slots_txt = "\n".join(
        f"- {s.tipo_documento.value}: {s.descripcion}" for s in sesion.checklist_slots
    )
    return (
        f"Sesión activada para «{sesion.nomenclatura}».\n"
        f"Modalidad: {etiqueta_modalidad(sesion.modalidad)}\n"
        f"Tipo de contratación: {sesion.tipo_contratacion.value}\n\n"
        f"{agent.descripcion}\n\n"
        "Operan dos agentes: **Analista** (forma, por documento) y **Jurídico** "
        "(fondo; puedes pedirlo en cualquier momento con documentos parciales).\n\n"
        "Checklist sugerido (cualquier orden; no obligatorio completar todos):\n"
        f"{slots_txt}\n\n"
        "Sube documentos o escribe «revisión jurídica» / usa el botón correspondiente."
    )


def _aplicar_nomenclatura(sesion: SesionCompliance, valor: str | None) -> str | None:
    """Asigna o reemplaza nomenclatura. Devuelve el valor nuevo si hubo cambio."""
    if not isinstance(valor, str):
        return None
    nueva = valor.strip()
    if not nueva or nueva.lower() in {"null", "none"}:
        return None
    if sesion.nomenclatura == nueva:
        return None
    sesion.nomenclatura = nueva
    sesion.pendiente_cambio_nomenclatura = False
    return nueva


def _aplicar_extraccion_llm(sesion: SesionCompliance, data: dict) -> list[str]:
    cambios: list[str] = []
    # Nomenclatura: se puede fijar o corregir por chat (modalidad/tipo no).
    nueva_nom = _aplicar_nomenclatura(sesion, data.get("nomenclatura"))
    if nueva_nom is not None:
        cambios.append(f"nomenclatura={nueva_nom}")
    if not sesion.modalidad:
        raw = data.get("modalidad")
        if isinstance(raw, str) and raw.strip():
            key = raw.strip().upper().replace(" ", "_").replace("-", "_")
            for m in Modalidad:
                if m.value == key or m.name == key:
                    sesion.modalidad = m
                    cambios.append(f"modalidad={m.value}")
                    break
    if not sesion.tipo_contratacion:
        raw = data.get("tipo_contratacion")
        if isinstance(raw, str) and raw.strip():
            key = raw.strip().upper()
            for t in TipoContratacion:
                if t.value == key or t.name == key:
                    sesion.tipo_contratacion = t
                    cambios.append(f"tipo_contratacion={t.value}")
                    break
    return cambios


def _parece_salir_del_cuestionario(mensaje: str) -> bool:
    t = mensaje.strip().lower()
    triggers = (
        "saltar pregunta",
        "saltar cuestionario",
        "omitir pregunta",
        "omitir cuestionario",
        "cancelar cuestionario",
        "pausar cuestionario",
        "más tarde",
        "luego el cuestionario",
        "subir otro",
        "otro documento",
    )
    return any(t.startswith(x) or t == x for x in triggers)


def _parece_pedido_juridico(mensaje: str) -> bool:
    t = mensaje.strip().lower()
    keys = (
        "revisión jurídica",
        "revision juridica",
        "dictamen jurídico",
        "dictamen juridico",
        "parecer jurídico",
        "parecer juridico",
        "agente jurídico",
        "agente juridico",
        "revisión legal",
        "revision legal",
    )
    return any(k in t for k in keys)


def _parece_cambio_nomenclatura(mensaje: str) -> bool:
    t = mensaje.strip().lower()
    if "nomenclatura" in t:
        return True
    claves = (
        "código del procedimiento",
        "codigo del procedimiento",
        "código del expediente",
        "codigo del expediente",
        "renombrar el expediente",
        "cambiar el código",
        "cambiar el codigo",
        "nuevo código del procedimiento",
        "nuevo codigo del procedimiento",
    )
    return any(k in t for k in claves)


def _intentar_cambio_nomenclatura(sesion: SesionCompliance, mensaje: str) -> str | None:
    """Si el mensaje trata de nomenclatura, aplica el cambio o responde. None = seguir flujo."""
    pendiente = bool(sesion.pendiente_cambio_nomenclatura)
    if not pendiente and not _parece_cambio_nomenclatura(mensaje):
        return None

    # Segundo paso: el usuario solo envía el código nuevo tras haber pedido el cambio.
    if pendiente and not _parece_cambio_nomenclatura(mensaje):
        candidata = mensaje.strip().strip("«»\"'")
        if candidata and len(candidata) <= 120 and "\n" not in candidata:
            anterior = sesion.nomenclatura
            nueva = _aplicar_nomenclatura(sesion, candidata)
            sesion.pendiente_cambio_nomenclatura = False
            if nueva is not None:
                return (
                    f"Listo. Nomenclatura actualizada de «{anterior}» a «{nueva}»."
                )
            return f"La nomenclatura ya era «{sesion.nomenclatura}». No hubo cambios."
        sesion.pendiente_cambio_nomenclatura = False
        # No parece un código: cancelar pendiente y seguir flujo normal.
        return None

    try:
        data = interpretar_cambio_nomenclatura(sesion, mensaje_usuario=mensaje)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None

    if data.get("intencion"):
        anterior = sesion.nomenclatura
        nueva = _aplicar_nomenclatura(sesion, data.get("nomenclatura"))
        resp = str(data.get("respuesta") or "").strip()
        if nueva is not None:
            sesion.pendiente_cambio_nomenclatura = False
            return resp or (
                f"Listo. Nomenclatura actualizada de «{anterior}» a «{nueva}»."
            )
        sesion.pendiente_cambio_nomenclatura = True
        return resp or "¿Cuál es la nueva nomenclatura del procedimiento?"

    sesion.pendiente_cambio_nomenclatura = False
    resp = str(data.get("respuesta") or "").strip()
    return resp or None


def ejecutar_dictamen_juridico(
    sesion: SesionCompliance,
    *,
    mensaje: str,
    documento_ids: list[str] | None = None,
    forzar_final: bool = False,
) -> DictamenJuridico:
    """Invoca al Jurídico de la modalidad y persiste el dictamen."""
    if not sesion.modalidad or not sesion.tipo_contratacion:
        raise ValueError("La sesión debe tener modalidad y tipo de contratación.")
    if sesion.estado != EstadoSesion.ACTIVA:
        raise ValueError("La sesión debe estar ACTIVA.")

    pendientes = _slots_pendientes_vals(sesion)
    docs = sesion.documentos_analizados
    if documento_ids:
        idset = set(documento_ids)
        docs = [d for d in docs if d.id in idset]
        missing = idset - {d.id for d in docs}
        if missing:
            raise ValueError(f"Documentos no encontrados: {sorted(missing)}")

    if forzar_final or not pendientes:
        alcance = AlcanceDictamen.FINAL
    else:
        alcance = AlcanceDictamen.PARCIAL

    juridico = get_agente(sesion.modalidad, sesion.tipo_contratacion, RolAgente.JURIDICO)
    markdown = consultar_juridico(
        sesion,
        system_experto=juridico.system_prompt_experto(),
        mensaje_usuario=mensaje,
        documento_ids=[d.id for d in docs] if documento_ids else None,
        slots_pendientes=[p.value for p in pendientes],
        alcance=alcance.value,
    )

    dictamen = DictamenJuridico(
        id=str(uuid.uuid4()),
        fecha=datetime.utcnow(),
        alcance=alcance,
        documento_ids=[d.id for d in docs],
        mensaje_usuario=mensaje,
        markdown=markdown,
        slots_pendientes=list(pendientes),
    )
    sesion.dictamenes_juridicos.append(dictamen)
    etiqueta = "final" if alcance == AlcanceDictamen.FINAL else "parcial"
    sesion.historial.append(
        MensajeChat(
            rol=RolMensaje.USER,
            contenido=f"[Revisión jurídica {etiqueta}] {mensaje}",
            timestamp=datetime.utcnow(),
        )
    )
    sesion.historial.append(
        MensajeChat(
            rol=RolMensaje.ASSISTANT,
            contenido=f"**Dictamen jurídico ({etiqueta})**\n\n{markdown}",
            timestamp=datetime.utcnow(),
        )
    )
    return dictamen


def _procesar_respuesta_cuestionario(
    sesion: SesionCompliance,
    mensaje: str,
) -> str | None:
    doc = documento_cuestionario_activo(sesion)
    if doc is None:
        sesion.documento_en_cuestionario = None
        return None

    if _parece_salir_del_cuestionario(mensaje):
        sesion.documento_en_cuestionario = None
        return (
            "Dejamos el cuestionario en pausa. Puedes retomarlo escribiendo "
            "«continuar cuestionario» o subiendo otro documento. "
            "Las preguntas pendientes seguirán reflejadas en el informe."
        )

    if mensaje.strip().lower() in {"continuar cuestionario", "retomar cuestionario"}:
        sesion.documento_en_cuestionario = doc.id
        return mensaje_pregunta_actual(doc)

    pend = pregunta_pendiente(doc)
    if pend is None:
        sesion.documento_en_cuestionario = None
        return None

    registrar_respuesta(doc, mensaje)
    sincronizar_informe_documento(doc)

    if pregunta_pendiente(doc) is None:
        sesion.documento_en_cuestionario = None
        hechas, total = progreso_cuestionario(doc)
        return (
            f"Respuesta registrada. Cuestionario de «{doc.tipo.value}» completado "
            f"({hechas}/{total}).\n\n"
            "Las respuestas ya están en el informe del documento y se incluirán "
            "en el informe global y en futuras revisiones jurídicas."
        )

    sesion.documento_en_cuestionario = doc.id
    hechas, total = progreso_cuestionario(doc)
    return (
        f"Respuesta registrada ({hechas}/{total}).\n\n"
        + mensaje_pregunta_actual(doc)
    )


def crear_sesion(
    *,
    nomenclatura: str | None = None,
    modalidad: Modalidad | None = None,
    tipo_contratacion: TipoContratacion | None = None,
) -> tuple[SesionCompliance, str]:
    sesion = SesionCompliance(
        id=str(uuid.uuid4()),
        nomenclatura=nomenclatura,
        modalidad=modalidad,
        tipo_contratacion=tipo_contratacion,
        estado=EstadoSesion.CONFIGURANDO,
    )
    if _config_completa(sesion):
        mensaje = _activar_sesion(sesion)
        sesion.historial.append(
            MensajeChat(
                rol=RolMensaje.ASSISTANT,
                contenido=mensaje,
                timestamp=datetime.utcnow(),
            )
        )
    else:
        mensaje = ""
    session_store.guardar_sesion(sesion.id, sesion)
    return sesion, mensaje


def procesar_mensaje(sesion_id: str, mensaje: str) -> tuple[SesionCompliance, str]:
    sesion = session_store.get_sesion(sesion_id)
    if sesion is None:
        raise LookupError(f"Sesión no encontrada: {sesion_id}")

    sesion.historial.append(
        MensajeChat(rol=RolMensaje.USER, contenido=mensaje, timestamp=datetime.utcnow())
    )

    if sesion.estado == EstadoSesion.CONFIGURANDO:
        data = interpretar_turno_config(sesion, mensaje_usuario=mensaje)
        _aplicar_extraccion_llm(sesion, data if isinstance(data, dict) else {})
        if _config_completa(sesion):
            respuesta = _activar_sesion(sesion)
        else:
            respuesta = str((data or {}).get("respuesta") or "").strip()
            if not respuesta:
                respuesta = (
                    "Sigamos con la configuración del expediente. "
                    "Indica nomenclatura, modalidad y tipo de contratación "
                    "(BIENES, OBRAS o SERVICIOS)."
                )
    else:
        # Jurídico tiene prioridad sobre Q&A si el mensaje es un pedido explícito
        if _parece_pedido_juridico(mensaje):
            try:
                dictamen = ejecutar_dictamen_juridico(sesion, mensaje=mensaje)
                # historial ya actualizado dentro; evitar duplicar user msg
                # (ya añadimos user al inicio: removemos el doble user del dictamen)
                # ejecutar_dictamen añade otro user+assistant → limpiar el user extra
                # Simplificación: quitar los dos últimos user duplicados no; 
                # mejor no añadir user al inicio cuando es jurídico... 
                # Ajuste: historial tiene user (línea inicial) + user/assistant de dictamen.
                # Eliminamos el penúltimo user duplicado del dictamen.
                if len(sesion.historial) >= 3:
                    # [..., user_orig, user_dict, asst_dict]
                    # dejar user_orig y asst, quitar user_dict
                    sesion.historial.pop(-2)
                respuesta = sesion.historial[-1].contenido
                # no append another assistant below
                session_store.guardar_sesion(sesion.id, sesion)
                return sesion, respuesta
            except ValueError as exc:
                respuesta = str(exc)
        else:
            nom_resp = _intentar_cambio_nomenclatura(sesion, mensaje)
            if nom_resp is not None:
                respuesta = nom_resp
            else:
                qa = _procesar_respuesta_cuestionario(sesion, mensaje)
                if qa is not None:
                    respuesta = qa
                else:
                    agent = None
                    if sesion.modalidad and sesion.tipo_contratacion:
                        agent = get_modalidad_agent(sesion.modalidad, sesion.tipo_contratacion)
                    system_extra = agent.system_prompt_experto() if agent else ""
                    docs_ctx = ""
                    if sesion.documentos_analizados:
                        docs_ctx = "Documentos ya auditados:\n" + "\n".join(
                            f"- {d.tipo.value} ({d.nombre_archivo}): cumple={d.cumple}; "
                            f"preguntas_pendientes="
                            f"{sum(1 for p in d.preguntas_seguimiento if not p.respondida)}"
                            for d in sesion.documentos_analizados
                        )
                    system_extra = (
                        f"{system_extra}\n{docs_ctx}\n"
                        "Si el usuario quiere revisión jurídica, indícale «revisión jurídica» "
                        "o el botón correspondiente. Para cuestionario: «continuar cuestionario». "
                        "Puede cambiar la nomenclatura del expediente por chat; "
                        "modalidad y tipo de contratación no se cambian en esta sesión."
                    ).strip()
                    respuesta = chat_compliance(
                        sesion,
                        mensaje_usuario=mensaje,
                        system_extra=system_extra,
                    )

    sesion.historial.append(
        MensajeChat(rol=RolMensaje.ASSISTANT, contenido=respuesta, timestamp=datetime.utcnow())
    )
    session_store.guardar_sesion(sesion.id, sesion)
    return sesion, respuesta
