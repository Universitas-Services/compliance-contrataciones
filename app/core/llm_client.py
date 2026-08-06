"""Cliente LLM abstraído (Gemini vía API OpenAI-compatible + fallback por env)."""

from __future__ import annotations

import json
import logging
import os
import re

from dotenv import load_dotenv
from openai import APIError, APIStatusError, OpenAI, RateLimitError

from app.models.schemas import Modalidad, SesionCompliance, TipoDocumento

load_dotenv(override=True)

logger = logging.getLogger(__name__)

JSON_SHAPE_HINT = (
    '{"resumen": str, "cumple": bool, '
    '"tipo_coincide": bool, '
    '"tipo_detectado": str|null, '
    '"observaciones": [{"severidad": str, "descripcion": str, "subsanacion": str|null, "ref": str|null}], '
    '"preguntas_sugeridas": [str], '
    '"informe_markdown": str}'
)

JSON_SHAPE_CHUNK = (
    '{"resumen_parcial": str, '
    '"tipo_detectado_parcial": str|null, '
    '"observaciones": [{"severidad": str, "descripcion": str, "subsanacion": str|null, "ref": str|null}], '
    '"elementos_vistos": [str], '
    '"notas": str}'
)

_TIPOS_DOC_GUIA = (
    "SOLICITUD_UNIDAD_USUARIA=solicitud/necesidad de la unidad; "
    "ACTA_INICIO=acta de inicio del procedimiento; "
    "PLIEGO_CONDICIONES=pliego/bases/condiciones de la contratación; "
    "ACTOS_MOTIVADOS=acto motivado/resolución motivada; "
    "LLAMADO_INVITACION=llamado o invitación pública; "
    "MODIFICACIONES_PLIEGO=modificaciones al pliego; "
    "ACTA_RECEPCION_OFERTAS=acta de recepción de ofertas; "
    "OFERTAS_RECIBIDAS=oferta de un participante; "
    "INFORME_ANALISIS_RECOMENDACION=informe de análisis/recomendación; "
    "DOCUMENTO_ADJUDICACION=adjudicación; "
    "NOTIFICACION_ADJUDICACION=notificación de adjudicación; "
    "CONTRATO=contrato, convenio u orden contractual firmada; "
    "JUSTIFICACION_CONTRATACION_DIRECTA=justificación de contratación directa; "
    "INVITACION_CERRADA=invitación a oferentes preseleccionados; "
    "SOLICITUD_COTIZACIONES=solicitud de cotizaciones; "
    "COMPARATIVO_PRECIOS=cuadro comparativo de precios; "
    "ACTA_APERTURA_TECNICA=acta de apertura técnica; "
    "ACTA_APERTURA_ECONOMICA=acta de apertura económica; "
    "DOCUMENTO_EXCLUSION=documento que fundamenta exclusión de modalidad ordinaria; "
    "OTROS=otro documento del expediente."
)

_FALLBACK_STATUS_CODES = {429, 404, 503}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _model() -> str:
    model = (os.getenv("GEMINI_MODEL") or os.getenv("OPENAI_MODEL") or "").strip()
    if not model:
        raise RuntimeError("GEMINI_MODEL no está definida en el entorno.")
    return model


def _timeout() -> float:
    raw = os.getenv("GEMINI_TIMEOUT") or os.getenv("OPENAI_TIMEOUT") or "90"
    return float(raw)


def _client() -> OpenAI:
    """Cliente primario; URL/clave/modelo solo desde GEMINI_* (o OPENAI_*)."""
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY no está definida. Copia .env.example a .env y configura la clave."
        )
    base_url = (
        os.getenv("GEMINI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    ).strip()
    if not base_url:
        raise RuntimeError("GEMINI_BASE_URL no está definida en el entorno.")
    return OpenAI(api_key=api_key, base_url=base_url, timeout=_timeout())


def _fallback_configured() -> bool:
    if not _env_bool("FALLBACK_ENABLED", False):
        return False
    base = (os.getenv("FALLBACK_BASE_URL") or "").strip()
    model = (os.getenv("FALLBACK_MODEL") or "").strip()
    return bool(base and model)


def _fallback_model() -> str:
    model = (os.getenv("FALLBACK_MODEL") or "").strip()
    if not model:
        raise RuntimeError("FALLBACK_MODEL no está definida en el entorno.")
    return model


def _fallback_timeout() -> float:
    raw = (os.getenv("FALLBACK_TIMEOUT") or "").strip() or "180"
    return float(raw)


def _client_fallback() -> OpenAI:
    """Cliente secundario; todo desde FALLBACK_* (sin hosts fijos en código)."""
    base_url = (os.getenv("FALLBACK_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("FALLBACK_BASE_URL no está definida en el entorno.")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    api_key = (os.getenv("FALLBACK_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "FALLBACK_API_KEY no está definida. Pon un valor en .env "
            "(aunque el servidor no la valide)."
        )
    return OpenAI(api_key=api_key, base_url=base_url, timeout=_fallback_timeout())


def _es_error_fallback(exc: BaseException) -> bool:
    """True si conviene reintentar en el proveedor FALLBACK_*."""
    if isinstance(exc, RateLimitError):
        return True
    status = getattr(exc, "status_code", None)
    if status in _FALLBACK_STATUS_CODES:
        return True
    if isinstance(exc, APIStatusError) and exc.status_code in _FALLBACK_STATUS_CODES:
        return True
    msg = str(exc).lower()
    markers = (
        "quota",
        "resource_exhausted",
        "rate limit",
        "rate_limit",
        "high demand",
        "no longer available",
        "unavailable",
        "exceeded your current quota",
    )
    return any(m in msg for m in markers)


def _respuesta_texto(response) -> str:
    choice = response.choices[0].message
    text = choice.content or ""
    if isinstance(text, list):
        partes = []
        for part in text:
            if isinstance(part, dict) and part.get("type") == "text":
                partes.append(part.get("text", ""))
            elif isinstance(part, str):
                partes.append(part)
        return "\n".join(partes).strip()
    return str(text).strip()


def _limpiar_y_parsear_json(texto: str) -> dict:
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = re.sub(r"^```(?:json)?\s*", "", limpio, count=1, flags=re.IGNORECASE)
        limpio = re.sub(r"\s*```$", "", limpio, count=1)
    return json.loads(limpio.strip())


def _anthropic_image_a_openai(bloque: dict) -> dict:
    source = bloque.get("source") or {}
    media_type = source.get("media_type", "image/png")
    data = source.get("data", "")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{data}"},
    }


def _armar_content_usuario(contenido: dict, instrucciones: str) -> list[dict]:
    bloques: list[dict] = [{"type": "text", "text": instrucciones}]
    modo = contenido.get("modo")
    payload = contenido.get("contenido")
    imgs = contenido.get("imagenes_selectivas") or []

    if modo in {"texto", "mixto"}:
        texto = payload if isinstance(payload, str) else str(payload or "")
        bloques.append(
            {
                "type": "text",
                "text": f"Contenido del documento (texto estructurado):\n\n{texto}",
            }
        )
        for img in imgs[:3]:
            if isinstance(img, dict) and img.get("type") == "image" and "source" in img:
                pag = img.get("pagina")
                if pag:
                    bloques.append({"type": "text", "text": f"[Imagen selectiva p.{pag}]"})
                bloques.append(_anthropic_image_a_openai(img))
    elif modo == "imagen":
        if not isinstance(payload, dict):
            raise ValueError("contenido.modo='imagen' requiere un dict de visión")
        if payload.get("type") == "image" and "source" in payload:
            bloques.append(_anthropic_image_a_openai(payload))
        elif payload.get("type") == "image_url":
            bloques.append(payload)
        else:
            raise ValueError("Formato de imagen no reconocido")
    else:
        raise ValueError(f"modo de contenido no soportado: {modo!r}")
    return bloques


def _llamar_modelo(
    *,
    system: str,
    user_content: str | list[dict],
    max_tokens: int = 4096,
) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    try:
        response = _client().chat.completions.create(
            model=_model(),
            max_tokens=max_tokens,
            messages=messages,
        )
        return _respuesta_texto(response)
    except (RateLimitError, APIStatusError, APIError) as primary_exc:
        if not (_es_error_fallback(primary_exc) and _fallback_configured()):
            raise
        logger.warning(
            "Proveedor primario falló (%s); reintentando con FALLBACK_MODEL",
            getattr(primary_exc, "status_code", type(primary_exc).__name__),
        )
        try:
            response = _client_fallback().chat.completions.create(
                model=_fallback_model(),
                max_tokens=max_tokens,
                messages=messages,
            )
            return _respuesta_texto(response)
        except Exception as fallback_exc:  # noqa: BLE001
            raise RuntimeError(
                f"Primario falló ({primary_exc!s}) y fallback también ({fallback_exc!s})"
            ) from fallback_exc


_DOMINIO_COMPLIANCE = (
    "Tu ÚNICO dominio es: compliance de contrataciones públicas en Venezuela "
    "(LCP/RLCP), modalidades de selección, requisitos documentales del expediente, "
    "auditoría de documentos de la sesión y trámites relacionados con esa auditoría.\n"
    "MEMORIA DE SESIÓN (obligatoria): SÍ recuerdas y usas el historial de esta "
    "conversación y los datos ya configurados del expediente (nomenclatura, modalidad, "
    "tipo de contratación, documentos ya auditados y sus hallazgos). Eso NO es "
    "información ajena: es el contexto del expediente en curso.\n"
    "Si el usuario pregunta algo del historial de esta misma sesión (p. ej. cómo se "
    "llamó, qué nomenclatura dio, qué documento subió), puedes responderlo con lo "
    "que aparece en el historial y volver al trámite.\n"
    "Si pregunta algo fuera de dominio y fuera del historial de la sesión "
    "(ciencia general, ocio, otros países, temas ajenos), di claramente que no "
    "estás entrenado/habilitado para eso y redirígelo al compliance. "
    "No inventes respuestas de otros temas."
)


def interpretar_cambio_nomenclatura(
    sesion: SesionCompliance,
    *,
    mensaje_usuario: str,
) -> dict:
    """Detecta si el usuario quiere cambiar la nomenclatura del expediente activo.

    Shape: {intencion: bool, nomenclatura: str|null, respuesta: str}
    """
    system = (
        "Eres el orquestador de compliance de contrataciones públicas. "
        "Debes decidir si el usuario quiere CAMBIAR o CORREGIR la nomenclatura "
        "(código del procedimiento) del expediente ya configurado.\n"
        f"{_DOMINIO_COMPLIANCE}\n"
        f"Nomenclatura actual: {sesion.nomenclatura!r}. "
        f"Modalidad y tipo de contratación NO se pueden cambiar por chat.\n\n"
        "Reglas:\n"
        "- intencion=true solo si pide explícitamente cambiar/corregir/actualizar "
        "la nomenclatura, o aporta un nuevo código claramente como reemplazo "
        "(p. ej. «cámbiala a CA-2026-099», «la nomenclatura correcta es …»).\n"
        "- Si intencion=true y da el nuevo código, ponlo en 'nomenclatura' y "
        "confirma en 'respuesta' (menciona la anterior y la nueva).\n"
        "- Si intencion=true pero no da el código nuevo, nomenclatura=null y "
        "pide el nuevo código en 'respuesta'.\n"
        "- Si solo pregunta cuál es la nomenclatura actual (sin querer cambiarla), "
        "intencion=false y responde con el valor actual.\n"
        "- Si pide cambiar modalidad o tipo de contratación, intencion=false y "
        "explica que eso no se puede cambiar en esta sesión; la nomenclatura sí.\n"
        "- Si el mensaje no trata de nomenclatura, intencion=false y respuesta=\"\".\n"
        "- Español, breve. SOLO JSON válido:\n"
        '{"intencion": bool, "nomenclatura": str|null, "respuesta": str}'
    )
    historial_txt = []
    for m in sesion.historial[-6:]:
        historial_txt.append(f"{m.rol.value}: {m.contenido}")
    user = (
        "Historial reciente:\n"
        + ("\n".join(historial_txt) if historial_txt else "(vacío)")
        + f"\n\nUsuario: {mensaje_usuario}"
    )
    raw = _llamar_modelo(system=system, user_content=user, max_tokens=512)
    try:
        return _limpiar_y_parsear_json(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        correccion = (
            "Corrige y responde SOLO JSON válido con el shape indicado.\n"
            f"Respuesta anterior:\n{raw}"
        )
        raw2 = _llamar_modelo(system=system, user_content=correccion, max_tokens=512)
        return _limpiar_y_parsear_json(raw2)


def chat_compliance(
    sesion: SesionCompliance,
    *,
    mensaje_usuario: str,
    system_extra: str = "",
) -> str:
    system = (
        "Eres el orquestador conversacional de compliance de contrataciones públicas "
        "en Venezuela. Interpretas cada mensaje del usuario con juicio (no eres un "
        "flujo rígido de reglas).\n"
        f"{_DOMINIO_COMPLIANCE}\n"
        f"Sesión id={sesion.id}, estado={sesion.estado.value}, "
        f"nomenclatura={sesion.nomenclatura}, modalidad={sesion.modalidad}, "
        f"tipo={sesion.tipo_contratacion}.\n"
        "El usuario PUEDE cambiar la nomenclatura del expediente por chat "
        "(el sistema lo aplicará si lo pide con claridad). NO puede cambiar "
        "modalidad ni tipo de contratación en esta sesión.\n"
        f"{system_extra}"
    )
    historial_txt = []
    for m in sesion.historial[-8:]:
        historial_txt.append(f"{m.rol.value}: {m.contenido}")
    user = (
        "Historial reciente:\n"
        + ("\n".join(historial_txt) if historial_txt else "(vacío)")
        + f"\n\nUsuario: {mensaje_usuario}"
    )
    return _llamar_modelo(system=system, user_content=user, max_tokens=2048)


def interpretar_turno_config(
    sesion: SesionCompliance,
    *,
    mensaje_usuario: str,
) -> dict:
    modalidades = [m.value for m in Modalidad]
    system = (
        "Eres el orquestador conversacional de compliance de contrataciones públicas "
        "en Venezuela (LCP/RLCP). Interpretas el mensaje del usuario con el LLM "
        "(cerebro), no con reglas ciegas.\n"
        f"{_DOMINIO_COMPLIANCE}\n"
        "Estás en fase de configuración de la sesión. Debes obtener: "
        "nomenclatura del procedimiento, modalidad de selección y "
        "tipo de contratación (BIENES|OBRAS|SERVICIOS).\n"
        f"Modalidades válidas (códigos internos para el campo JSON 'modalidad', "
        f"NO los escribas en 'respuesta'): {modalidades}.\n"
        "Nombres legibles de modalidades (puedes mencionarlos en 'respuesta' si hace "
        "falta, pero preferible pedir que elija en la interfaz): "
        "CA — Apertura única; CA — Apertura diferida; CA — Acto separado; "
        "Concurso cerrado; Consulta de precio; Contratación directa; "
        "Modalidades excluidas.\n"
        f"Estado actual: nomenclatura={sesion.nomenclatura!r}, "
        f"modalidad={sesion.modalidad.value if sesion.modalidad else None}, "
        f"tipo={sesion.tipo_contratacion.value if sesion.tipo_contratacion else None}.\n\n"
        "Reglas:\n"
        "- Si el usuario saluda (con o sin nombre), saluda y pide lo que falte "
        "(empieza por nomenclatura). Puedes usar el nombre si lo dijo en el historial.\n"
        "- Si pregunta por algo YA dicho en esta conversación (nombre, nomenclatura, "
        "etc.), respóndelo con el historial y retoma el dato pendiente. "
        "NO digas que no recuerdas datos de esta misma sesión.\n"
        "- Si el mensaje está fuera de dominio (dinosaurios, clima, etc. y no es "
        "dato del expediente), marca fuera_de_dominio=true, deja "
        "nomenclatura/modalidad/tipo_contratacion en null, y en 'respuesta' di "
        "que no estás entrenado para ese tema; luego retoma el dato pendiente.\n"
        "- Solo extrae un campo si el usuario lo aporta de forma clara y plausible "
        "(nomenclatura tipo código de procedimiento, no una pregunta ni texto ajeno).\n"
        "- Si ya hay nomenclatura y el usuario la corrige o pide cambiarla "
        "(p. ej. «cámbiala a CA-2026-099»), extrae la NUEVA en 'nomenclatura' y "
        "confirma el cambio en 'respuesta'. NO permitas cambiar modalidad ni tipo "
        "de contratación una vez fijados: déjalos en null y explica que no se "
        "pueden cambiar en esta sesión (habría que abrir otra).\n"
        "- IMPORTANTE para 'respuesta': NUNCA listes códigos en MAYÚSCULAS_CON_GUIONES "
        "(ej. CA_ACTO_UNICO_APERTURA_UNICA). Cuando pidas modalidad o tipo, di algo "
        "breve como: confirma la nomenclatura y pide que elija la modalidad / tipo "
        "en las opciones de la pantalla. No digas 'las opciones válidas son: ...'.\n"
        "- Responde en español, conversacional y breve.\n\n"
        "Responde SOLO JSON válido:\n"
        '{"respuesta": str, "nomenclatura": str|null, "modalidad": str|null, '
        '"tipo_contratacion": str|null, "fuera_de_dominio": bool}'
    )
    historial_txt = []
    for m in sesion.historial[-10:]:
        historial_txt.append(f"{m.rol.value}: {m.contenido}")
    user = (
        "Historial:\n"
        + ("\n".join(historial_txt) if historial_txt else "(vacío)")
        + f"\n\nÚltimo mensaje del usuario: {mensaje_usuario}"
    )
    raw = _llamar_modelo(system=system, user_content=user, max_tokens=1024)
    try:
        return _limpiar_y_parsear_json(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        correccion = (
            "Corrige y responde SOLO JSON válido con el shape indicado.\n"
            f"Respuesta anterior:\n{raw}"
        )
        raw2 = _llamar_modelo(system=system, user_content=correccion, max_tokens=1024)
        return _limpiar_y_parsear_json(raw2)


def analizar_documento(
    tipo_documento: TipoDocumento,
    contenido: dict,
    requisitos: dict,
    *,
    system_experto: str = "",
    preguntas_preestablecidas: list[str] | None = None,
    modalidad: Modalidad | None = None,
    nomenclatura: str | None = None,
    docs_previos_resumen: str = "",
) -> dict:
    """Analiza un documento (map-reduce por chunks si aplica) → JSON de hallazgo."""
    elementos = requisitos.get("elementos_requeridos") or []
    descripcion = requisitos.get("descripcion") or ""
    lista = "\n".join(f"- {item}" for item in elementos)
    preguntas = preguntas_preestablecidas or []
    preguntas_txt = "\n".join(f"- {p}" for p in preguntas) or "(ninguna)"
    nom = (nomenclatura or "").strip() or "N/D"
    meta = contenido.get("canonico") or {}
    meta_txt = (
        f"Extracción: metodo={meta.get('metodo')}, paginas={meta.get('paginas')}, "
        f"bloques={meta.get('bloques')}, cobertura_ocr={meta.get('cobertura_ocr')}. "
        f"Advertencias: {meta.get('advertencias') or []}"
    )

    coherencia = (
        f"NOMENCLATURA DE LA SESIÓN: «{nom}».\n"
        "Busca nomenclatura/código del procedimiento en el documento.\n"
        "Reporta inconsistencias; incluye 'ref' (pág/bloque) en observaciones.\n"
    )
    if docs_previos_resumen.strip():
        coherencia += (
            "Documentos ya auditados:\n" f"{docs_previos_resumen}\n"
        )

    identidad = (
        "PASO 1 — IDENTIDAD:\n"
        f"Declarado: {tipo_documento.value} ({descripcion or 'N/D'}).\n"
        f"Catálogo: {_TIPOS_DOC_GUIA}\n"
        "Si no corresponde: tipo_coincide=false, cumple=false, observación critica.\n"
        f"Si corresponde: tipo_coincide=true, tipo_detectado={tipo_documento.value}.\n"
    )

    system = (
        (system_experto + "\n\n" if system_experto else "")
        + "Eres el AGENTE ANALISTA de compliance (Venezuela).\n"
        f"Nomenclatura: {nom}. Modalidad: {modalidad.value if modalidad else 'N/D'}.\n"
        f"Tipo declarado: {tipo_documento.value}. {meta_txt}\n\n"
        f"{identidad}\n{coherencia}\n"
        "PASO 2 — Solo si tipo_coincide=true, verifica:\n"
        f"{lista}\n\nPreguntas sugeridas:\n{preguntas_txt}\n\n"
        f"SOLO JSON: {JSON_SHAPE_HINT}\n"
        'severidad ∈ {"info","advertencia","critica"}.'
    )

    chunks = list(contenido.get("chunks") or [])
    if not chunks and isinstance(contenido.get("contenido"), str) and contenido.get("contenido"):
        chunks = [contenido["contenido"]]

    if len(chunks) > 1:
        parciales: list[dict] = []
        for i, chunk in enumerate(chunks, start=1):
            system_map = (
                (system_experto + "\n\n" if system_experto else "")
                + "ANALISTA: bloque parcial. No omitas hallazgos. SOLO JSON:\n"
                f"{JSON_SHAPE_CHUNK}\n"
                f"Tipo declarado: {tipo_documento.value}. Bloque {i}/{len(chunks)}."
            )
            user_content = [
                {
                    "type": "text",
                    "text": f"Analiza SOLO bloque {i}/{len(chunks)}. SOLO JSON.",
                },
                {"type": "text", "text": chunk},
            ]
            raw = _llamar_modelo(system=system_map, user_content=user_content, max_tokens=4096)
            try:
                parciales.append(_limpiar_y_parsear_json(raw))
            except (json.JSONDecodeError, TypeError, ValueError):
                parciales.append(
                    {
                        "resumen_parcial": raw[:500],
                        "observaciones": [],
                        "notas": "json_invalido",
                    }
                )

        system_reduce = (
            system
            + "\nConsolida TODOS los bloques parciales en el JSON final (no omitas)."
        )
        user_reduce = (
            "Consolida en JSON final. SOLO JSON.\n\n"
            f"{json.dumps(parciales, ensure_ascii=False)}"
        )
        raw = _llamar_modelo(system=system_reduce, user_content=user_reduce, max_tokens=6144)
        try:
            return _limpiar_y_parsear_json(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            correccion = (
                f"Corrige SOLO JSON:\n{JSON_SHAPE_HINT}\n\nAnterior:\n{raw}"
            )
            return _limpiar_y_parsear_json(
                _llamar_modelo(
                    system=system_reduce, user_content=correccion, max_tokens=6144
                )
            )

    if chunks:
        contenido_envio = {
            **contenido,
            "modo": "mixto" if contenido.get("imagenes_selectivas") else "texto",
            "contenido": chunks[0],
        }
    else:
        contenido_envio = contenido

    user_content = _armar_content_usuario(
        contenido_envio,
        "Analiza el documento. Responde únicamente con el JSON solicitado.",
    )
    raw = _llamar_modelo(system=system, user_content=user_content, max_tokens=6144)
    try:
        return _limpiar_y_parsear_json(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        correccion = (
            f"Corrige SOLO JSON:\n{JSON_SHAPE_HINT}\n\nAnterior:\n{raw}"
        )
        return _limpiar_y_parsear_json(
            _llamar_modelo(system=system, user_content=correccion, max_tokens=6144)
        )


def consultar_juridico(
    sesion: SesionCompliance,
    *,
    system_experto: str,
    mensaje_usuario: str,
    documento_ids: list[str] | None = None,
    slots_pendientes: list[str] | None = None,
    alcance: str = "PARCIAL",
) -> str:
    """Dictamen jurídico narrativo (markdown)."""
    docs = sesion.documentos_analizados
    if documento_ids:
        idset = set(documento_ids)
        docs = [d for d in docs if d.id in idset]

    docs_payload = []
    for d in docs:
        docs_payload.append(
            {
                "id": d.id,
                "tipo": d.tipo.value,
                "archivo": d.nombre_archivo,
                "cumple": d.cumple,
                "tipo_coincide": d.tipo_coincide,
                "tipo_detectado": d.tipo_detectado,
                "resumen": d.resumen,
                "observaciones": [o.model_dump() for o in d.observaciones],
                "cuestionario": [
                    {
                        "pregunta": p.texto,
                        "respondida": p.respondida,
                        "respuesta": p.respuesta,
                    }
                    for p in d.preguntas_seguimiento
                ],
                "informe_extracto": (d.informe_markdown or "")[:2500],
            }
        )

    previos = [
        {
            "fecha": dj.fecha.isoformat(),
            "alcance": dj.alcance.value,
            "markdown_extracto": (dj.markdown or "")[:2000],
        }
        for dj in (sesion.dictamenes_juridicos or [])[-3:]
    ]

    system = (
        f"{system_experto}\n\n"
        f"Alcance: {alcance}. Si es PARCIAL, no lo presentes como definitivo.\n"
        "Responde SOLO markdown:\n"
        "## Alcance y limitaciones\n## Hallazgos jurídicos\n## Riesgos\n"
        "## Conclusiones\n## Recomendaciones\n"
    )
    user = (
        f"Solicitud:\n{mensaje_usuario}\n\n"
        f"Expediente: nomenclatura={sesion.nomenclatura}, "
        f"modalidad={sesion.modalidad}, tipo={sesion.tipo_contratacion}.\n"
        f"Slots pendientes: {slots_pendientes or []}\n\n"
        f"Documentos ({len(docs_payload)}):\n"
        f"{json.dumps(docs_payload, ensure_ascii=False)}\n\n"
        f"Dictámenes previos:\n{json.dumps(previos, ensure_ascii=False)}"
    )
    return _llamar_modelo(system=system, user_content=user, max_tokens=8192)


def generar_informe_global(sesion: SesionCompliance) -> str:
    payload = sesion.model_dump(mode="json")
    for d in payload.get("documentos_analizados") or []:
        if isinstance(d, dict):
            d.pop("texto_extraido", None)
    system = (
        "Eres un auditor senior de compliance de contrataciones públicas en Venezuela. "
        "Redactas INFORME GLOBAL en markdown. Integra Analista, cuestionarios y "
        "dictámenes Jurídicos (parcial vs final). No inventes hechos. "
        "Cierra con recomendaciones priorizadas."
    )
    user = (
        "Estructura exacta:\n"
        f"# Informe global de auditoría — {sesion.nomenclatura or 'Expediente'}\n\n"
        "## 1. Resumen ejecutivo\n## 2. Documentos revisados\n"
        "## 3. Hallazgos del expediente\n## 4. Cuestionario de seguimiento\n"
        "## 5. Dictámenes jurídicos\n## 6. Análisis de cumplimiento\n"
        "## 7. Conclusiones\n## 8. Recomendaciones\n\n"
        f"Datos:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    return _llamar_modelo(system=system, user_content=user, max_tokens=8192)
