"""Orquestador conversacional de compliance multi-modalidad (dupla Analista/Jurídico)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from app.agents.knowledge import (
    etiqueta_documento,
    etiqueta_modalidad,
    etiqueta_tipo_contratacion,
)
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


def _texto_chat_plano(texto: str) -> str:
    """Quita énfasis markdown típico que el modelo mete en respuestas de chat."""
    t = texto or ""
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", t)
    t = t.replace("**", "")
    return t.strip()


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
        f"{i}. {s.descripcion or etiqueta_documento(s.tipo_documento)}"
        for i, s in enumerate(sesion.checklist_slots, start=1)
    )
    modalidad_txt = etiqueta_modalidad(sesion.modalidad)
    tipo_txt = etiqueta_tipo_contratacion(sesion.tipo_contratacion)
    return (
        f"Hemos registrado el Expediente N° {sesion.nomenclatura} de la modalidad "
        f"{modalidad_txt} para un contrato de {tipo_txt}.\n\n"
        "A continuación, verás el listado de documentos requeridos para esta "
        "modalidad. Por favor, selecciona el documento con el que deseas "
        "comenzar la revisión.\n\n"
        f"{slots_txt}\n\n"
        "Puedes adjuntar el archivo indicando el tipo correspondiente. "
        "Si en cualquier momento deseas una revisión jurídica del expediente "
        "(parcial o final), escribe «revisión jurídica» o usa el botón de Archivos."
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


def _match_modalidad(texto: str) -> Modalidad | None:
    t = texto.strip()
    if not t:
        return None
    key = t.upper().replace(" ", "_").replace("-", "_")
    for m in Modalidad:
        if t == m.value or key == m.value or key == m.name:
            return m
    # etiquetas legibles (por si el front envía label)
    for m in Modalidad:
        if etiqueta_modalidad(m).strip().lower() == t.lower():
            return m
    return None


def _match_tipo_contratacion(texto: str) -> TipoContratacion | None:
    t = texto.strip()
    if not t:
        return None
    key = t.upper().replace(" ", "_")
    for tipo in TipoContratacion:
        if key == tipo.value or key == tipo.name:
            return tipo
    labels = {
        "bienes": TipoContratacion.BIENES,
        "obra": TipoContratacion.OBRAS,
        "obras": TipoContratacion.OBRAS,
        "servicio": TipoContratacion.SERVICIOS,
        "servicios": TipoContratacion.SERVICIOS,
    }
    return labels.get(t.lower())


def _norm_txt(s: str) -> str:
    t = (s or "").lower()
    for a, b in (
        ("á", "a"),
        ("é", "e"),
        ("í", "i"),
        ("ó", "o"),
        ("ú", "u"),
        ("ü", "u"),
    ):
        t = t.replace(a, b)
    return t


def _detectar_tipo_en_texto(mensaje: str) -> TipoContratacion | None:
    """Detecta bienes/obras/servicios en texto libre (no solo mensaje exacto)."""
    low = _norm_txt(mensaje)
    # Más específico primero
    if re.search(r"\bservicios?\b", low):
        return TipoContratacion.SERVICIOS
    if re.search(r"\bobras?\b", low):
        return TipoContratacion.OBRAS
    if re.search(r"\bbienes?\b", low):
        return TipoContratacion.BIENES
    return None


def _detectar_modalidad_en_texto(mensaje: str) -> Modalidad | None:
    """Detecta modalidad por frases naturales en el mensaje."""
    # Primero intento match exacto (picker / código)
    exact = _match_modalidad(mensaje.strip())
    if exact is not None:
        return exact

    low = _norm_txt(mensaje)
    # Orden: más específico → más genérico
    reglas: list[tuple[tuple[str, ...], Modalidad]] = [
        (
            ("apertura unica", "acto unico apertura unica", "ca apertura unica"),
            Modalidad.CA_ACTO_UNICO_APERTURA_UNICA,
        ),
        (
            ("apertura diferida", "acto unico apertura diferida"),
            Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA,
        ),
        (("acto separado",), Modalidad.CA_ACTO_SEPARADO),
        (("concurso cerrado",), Modalidad.CONCURSO_CERRADO),
        (("consulta de precio", "consulta precio"), Modalidad.CONSULTA_PRECIO),
        (("contratacion directa",), Modalidad.CONTRATACION_DIRECTA),
        (("modalidades excluidas", "modalidad excluida"), Modalidad.MODALIDADES_EXCLUIDAS),
    ]
    for frases, mod in reglas:
        if any(f in low for f in frases):
            return mod
    # "concurso abierto" solo, sin apertura → asume apertura única (la más usada)
    if "concurso abierto" in low:
        return Modalidad.CA_ACTO_UNICO_APERTURA_UNICA
    return None


def _completar_extraccion_desde_mensaje(
    sesion: SesionCompliance,
    mensaje: str,
    data: dict,
) -> dict:
    """Rellena modalidad/tipo si el LLM los omitió pero el usuario ya los dijo."""
    out = dict(data)
    # Picker exacto (mensaje corto = código del OptionPicker)
    corto = mensaje.strip()
    if len(corto) <= 80 and "\n" not in corto:
        if not sesion.modalidad and not out.get("modalidad"):
            mod = _match_modalidad(corto)
            if mod is not None:
                out["modalidad"] = mod.value
        if not sesion.tipo_contratacion and not out.get("tipo_contratacion"):
            tipo = _match_tipo_contratacion(corto)
            if tipo is not None:
                out["tipo_contratacion"] = tipo.value

    # Texto libre / mensaje largo
    if not sesion.modalidad and not out.get("modalidad"):
        mod = _detectar_modalidad_en_texto(mensaje)
        if mod is not None:
            out["modalidad"] = mod.value
    if not sesion.tipo_contratacion and not out.get("tipo_contratacion"):
        tipo = _detectar_tipo_en_texto(mensaje)
        if tipo is not None:
            out["tipo_contratacion"] = tipo.value
    return out


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
    titulo = (
        "Informe Ejecutivo Final de Cierre"
        if alcance == AlcanceDictamen.FINAL
        else "Informe Ejecutivo Parcial de Avance"
    )
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
            contenido=f"**{titulo}**\n\n{markdown}",
            timestamp=datetime.utcnow(),
        )
    )
    return dictamen


def _procesar_respuesta_cuestionario(
    sesion: SesionCompliance,
    mensaje: str,
) -> str | None:
    """Legacy no-op: la rúbrica la responde el Analista al subir el documento."""
    sesion.documento_en_cuestionario = None
    return None


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
        fecha_inicio=datetime.utcnow(),
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
        # Siempre pasa por el LLM (respuesta conversacional + extracción).
        # Si el usuario ya dijo modalidad/tipo en el texto (o el picker),
        # se completan aunque el modelo los omita en el JSON.
        data = interpretar_turno_config(sesion, mensaje_usuario=mensaje)
        if not isinstance(data, dict):
            data = {}
        data = _completar_extraccion_desde_mensaje(sesion, mensaje, data)
        _aplicar_extraccion_llm(sesion, data)
        if _config_completa(sesion):
            respuesta = _activar_sesion(sesion)
        else:
            respuesta = str(data.get("respuesta") or "").strip()
            if not respuesta:
                ya_saludo = any(
                    m.rol == RolMensaje.ASSISTANT for m in sesion.historial[:-1]
                )
                if ya_saludo:
                    respuesta = (
                        "Continuemos con el registro del expediente. "
                        "Indícame o selecciona en pantalla el dato que falta "
                        "(nomenclatura, modalidad o tipo de contratación)."
                    )
                else:
                    respuesta = (
                        "Bienvenido al Módulo de Compliance de Contrataciones Públicas. "
                        "Soy el Coordinador de Compliance y estoy aquí para guiarte "
                        "en el proceso de auditoría. "
                        "Para comenzar, indícame la nomenclatura del expediente."
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
                respuesta = _texto_chat_plano(sesion.historial[-1].contenido)
                sesion.historial[-1].contenido = respuesta
                session_store.guardar_sesion(sesion.id, sesion)
                return sesion, respuesta
            except ValueError as exc:
                respuesta = str(exc)
        else:
            nom_resp = _intentar_cambio_nomenclatura(sesion, mensaje)
            if nom_resp is not None:
                respuesta = nom_resp
            else:
                _procesar_respuesta_cuestionario(sesion, mensaje)
                agent = None
                if sesion.modalidad and sesion.tipo_contratacion:
                    agent = get_modalidad_agent(sesion.modalidad, sesion.tipo_contratacion)
                docs_ctx = ""
                if sesion.documentos_analizados:
                    docs_ctx = "Documentos ya revisados:\n" + "\n".join(
                        f"- {etiqueta_documento(d.tipo)} ({d.nombre_archivo}): "
                        f"cumple={d.cumple}; "
                        f"tipo_coincide={getattr(d, 'tipo_coincide', True)}; "
                        f"rubrica="
                        f"{sum(1 for p in d.preguntas_seguimiento if p.respondida)}"
                        f"/{len(d.preguntas_seguimiento)}"
                        for d in sesion.documentos_analizados
                    )
                modalidad_ctx = ""
                if agent:
                    modalidad_ctx = (
                        f"Modalidad activa: {etiqueta_modalidad(sesion.modalidad)}. "
                        f"Tipo: {etiqueta_tipo_contratacion(sesion.tipo_contratacion)}.\n"
                        f"{agent.descripcion}\n"
                    )
                system_extra = (
                    f"{modalidad_ctx}{docs_ctx}\n"
                    "Eres siempre el Coordinador de Compliance (una sola cara). "
                    "No menciones agentes internos ni especialistas ocultos.\n"
                    "Expediente YA registrado: no reinicies el onboarding ni "
                    "pidas confirmar nomenclatura/modalidad/tipo otra vez.\n"
                    "Consultas de dominio (modalidades, bienes/obras/servicios, "
                    "legal/compliance) están permitidas en cualquier momento.\n"
                    "Si el usuario quiere una revisión jurídica del expediente, "
                    "indícale «revisión jurídica» o el botón de Archivos.\n"
                    "Al subir un documento, el sistema completa la rúbrica "
                    "automáticamente; no pidas respuestas al usuario.\n"
                    "Si un documento se marcó como tipo incorrecto, el slot NO "
                    "queda auditado: puede volver a subir el archivo correcto "
                    "o reclasificarlo eligiendo el tipo real.\n"
                    "Puede cambiar la nomenclatura por chat; modalidad y tipo "
                    "de contratación no se cambian en esta sesión."
                ).strip()
                respuesta = chat_compliance(
                    sesion,
                    mensaje_usuario=mensaje,
                    system_extra=system_extra,
                )

    respuesta = _texto_chat_plano(respuesta)
    sesion.historial.append(
        MensajeChat(rol=RolMensaje.ASSISTANT, contenido=respuesta, timestamp=datetime.utcnow())
    )
    session_store.guardar_sesion(sesion.id, sesion)
    return sesion, respuesta
