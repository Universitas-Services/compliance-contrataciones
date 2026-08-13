"""Helpers de cuestionario de seguimiento e informes."""

from __future__ import annotations

import re

from app.models.schemas import DocumentoAnalizado, PreguntaSeguimiento, SesionCompliance

_QA_SECTION = "## Rúbrica del documento (Analista)"
_QA_SECTION_ALT = "## Respuestas de seguimiento / cuestionario"
_QA_SECTION_ALT2 = "## Respuestas de seguimiento"


def pregunta_pendiente(doc: DocumentoAnalizado) -> PreguntaSeguimiento | None:
    """Ya no hay Q&A de usuario: la rúbrica la responde el Analista al subir."""
    return None


def progreso_cuestionario(doc: DocumentoAnalizado) -> tuple[int, int]:
    total = len(doc.preguntas_seguimiento)
    hechas = sum(1 for p in doc.preguntas_seguimiento if p.respondida)
    return hechas, total


def documento_cuestionario_activo(
    sesion: SesionCompliance,
) -> DocumentoAnalizado | None:
    """Desactivado: el chat no atrapa respuestas de cuestionario de usuario."""
    return None


def _norm_estado(raw: str) -> str:
    t = raw.strip().lower().replace(" ", "_")
    if t in {"n/a", "n.a.", "na", "no_aplica", "noaplica"}:
        return "na"
    if t in {"si", "sí", "yes"}:
        return "si"
    if t in {"no"}:
        return "no"
    if t in {"parcial"}:
        return "parcial"
    if t in {"no_consta", "noconsta"}:
        return "no_consta"
    return "no_consta"


def aplicar_rubrica_agente(
    preguntas: list[PreguntaSeguimiento],
    rubrica_raw: object,
) -> None:
    """Rellena cada ítem de la rúbrica con la respuesta del Analista."""
    by_id: dict[str, dict] = {}
    items: list = []
    if isinstance(rubrica_raw, list):
        items = rubrica_raw
    elif isinstance(rubrica_raw, dict):
        items = rubrica_raw.get("items") or rubrica_raw.get("preguntas") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("id", "codigo_pregunta"):
            pid = str(item.get(key) or "").strip().lower()
            if pid:
                by_id[pid] = item

    for i, p in enumerate(preguntas, start=1):
        item = by_id.get(p.id.lower()) or by_id.get(f"q{i}")
        if item is None and p.codigo_pregunta:
            item = by_id.get(p.codigo_pregunta.lower())
        if item is None and i - 1 < len(items):
            cand = items[i - 1]
            item = cand if isinstance(cand, dict) else None
        if not item:
            p.respondida = True
            p.respondida_por = "agente"
            p.estado = "no_consta"
            p.respuesta = "Sin valoración explícita del modelo sobre este ítem."
            continue
        estado = _norm_estado(str(item.get("estado") or ""))
        resp = str(item.get("respuesta") or item.get("explicacion") or "").strip()
        ref = item.get("ref")
        p.estado = estado  # type: ignore[assignment]
        p.respuesta = resp or f"Estado: {estado}"
        p.ref = str(ref).strip() if ref not in (None, "") else None
        for campo in (
            "codigo_pregunta",
            "fundamento_legal",
            "rango_criticidad",
            "accion_legal",
            "advertencia_gerencia",
        ):
            val = item.get(campo)
            if val not in (None, ""):
                setattr(p, campo, str(val).strip())
            elif campo == "codigo_pregunta" and p.codigo_pregunta:
                continue  # conservar código del MD oficial
        p.respondida = True
        p.respondida_por = "agente"


def resumen_rubrica_chat(doc: DocumentoAnalizado) -> str:
    """Texto breve de la rúbrica para el mensaje post-upload."""
    if not doc.preguntas_seguimiento:
        return ""
    hechas, total = progreso_cuestionario(doc)
    estatus = doc.estatus_global or ("Verde" if doc.cumple else "Amarillo")
    lineas = [
        f"Estatus global: {estatus}",
        f"Rúbrica ({hechas}/{total} ítems):",
        "",
    ]
    for i, p in enumerate(doc.preguntas_seguimiento, start=1):
        est = (p.estado or "?").upper()
        ref = f" [{p.ref}]" if p.ref else ""
        cod = f"{p.codigo_pregunta} · " if p.codigo_pregunta else ""
        lineas.append(f"{i}. [{est}] {cod}{p.texto}")
        if p.respuesta:
            lineas.append(f"   → {p.respuesta}{ref}")
        lineas.append("")
    return "\n".join(lineas).rstrip()


def sincronizar_informe_documento(doc: DocumentoAnalizado) -> None:
    """Reescribe la sección de rúbrica del informe desde el estado actual."""
    base = doc.informe_markdown or ""
    for marker in (_QA_SECTION, _QA_SECTION_ALT, _QA_SECTION_ALT2):
        if marker in base:
            base = base.split(marker)[0].rstrip()
            break
    base = re.sub(r"\n{3,}", "\n\n", base).rstrip()

    if not doc.preguntas_seguimiento:
        doc.informe_markdown = base
        return

    hechas, total = progreso_cuestionario(doc)
    lineas = [
        "",
        _QA_SECTION,
        "",
        f"Progreso: {hechas}/{total} valorados por el Analista.",
        "",
    ]
    for i, p in enumerate(doc.preguntas_seguimiento, start=1):
        est = p.estado or ("ok" if p.respondida else "pendiente")
        lineas.append(f"### Ítem {i} ({est})")
        lineas.append("")
        lineas.append(p.texto)
        lineas.append("")
        if p.respondida and p.respuesta:
            lineas.append(f"**Respuesta del Analista:** {p.respuesta}")
            if p.ref:
                lineas.append(f"**Evidencia / ref:** {p.ref}")
        else:
            lineas.append("**Respuesta del Analista:** _(pendiente)_")
        lineas.append("")

    doc.informe_markdown = (base + "\n" + "\n".join(lineas)).strip() + "\n"


def registrar_respuesta(
    doc: DocumentoAnalizado,
    texto_respuesta: str,
    *,
    pregunta_id: str | None = None,
) -> PreguntaSeguimiento | None:
    """Compat: permite sobreescribir un ítem (p. ej. corrección manual)."""
    target: PreguntaSeguimiento | None = None
    if pregunta_id:
        target = next((p for p in doc.preguntas_seguimiento if p.id == pregunta_id), None)
    if target is None:
        for p in doc.preguntas_seguimiento:
            if not p.respondida:
                target = p
                break
    if target is None:
        return None
    target.respuesta = texto_respuesta.strip()
    target.respondida = True
    target.respondida_por = "usuario"
    sincronizar_informe_documento(doc)
    return target


def mensaje_pregunta_actual(doc: DocumentoAnalizado) -> str:
    return resumen_rubrica_chat(doc) or (
        f"Rúbrica del documento «{doc.tipo.value}» sin ítems precargados."
    )


def construir_informe_global_estructurado(sesion: SesionCompliance) -> str:
    """Informe global determinístico (sin LLM) con hallazgos y recomendaciones."""
    from app.agents.knowledge import etiqueta_modalidad

    mod = (
        etiqueta_modalidad(sesion.modalidad)
        if sesion.modalidad
        else "N/D"
    )
    tipo = sesion.tipo_contratacion.value if sesion.tipo_contratacion else "N/D"
    lineas: list[str] = [
        f"# Informe global de auditoría — {sesion.nomenclatura or sesion.id}",
        "",
        "## 1. Identificación del expediente",
        "",
        f"- **Nomenclatura:** {sesion.nomenclatura or 'N/D'}",
        f"- **Modalidad:** {mod}",
        f"- **Tipo de contratación:** {tipo}",
        f"- **Documentos revisados:** {len(sesion.documentos_analizados)}",
        "",
        "## 2. Documentos auditados",
        "",
        "| Tipo | Archivo | Identidad | Cumple | Observaciones |",
        "| --- | --- | --- | --- | --- |",
    ]
    criticas: list[str] = []
    advertencias: list[str] = []
    recomendaciones: list[str] = []

    for d in sesion.documentos_analizados:
        identidad = "OK" if getattr(d, "tipo_coincide", True) else (
            f"INCORRECTO→{d.tipo_detectado or '?'}"
        )
        lineas.append(
            f"| {d.tipo.value} | {d.nombre_archivo} | {identidad} | "
            f"{'sí' if d.cumple else 'no'} | {len(d.observaciones)} |"
        )
        for o in d.observaciones:
            item = f"**{d.tipo.value}** ({d.nombre_archivo}): {o.descripcion}"
            if o.severidad == "critica":
                criticas.append(item)
            elif o.severidad == "advertencia":
                advertencias.append(item)
            if o.subsanacion:
                recomendaciones.append(
                    f"[{d.tipo.value}] {o.subsanacion}"
                )
        if not getattr(d, "tipo_coincide", True):
            recomendaciones.append(
                f"[{d.tipo.value}] Reponer el documento correcto o reclasificar "
                f"el archivo (detectado: {d.tipo_detectado or 'otro'})."
            )

    lineas.extend(["", "## 3. Hallazgos críticos", ""])
    if criticas:
        lineas.extend(f"- {c}" for c in criticas)
    else:
        lineas.append("- Sin hallazgos críticos registrados.")

    lineas.extend(["", "## 4. Advertencias", ""])
    if advertencias:
        lineas.extend(f"- {a}" for a in advertencias)
    else:
        lineas.append("- Sin advertencias registradas.")

    lineas.extend(["", "## 5. Rúbrica por documento (Analista)", ""])
    hubo_qa = False
    for d in sesion.documentos_analizados:
        if not d.preguntas_seguimiento:
            continue
        hubo_qa = True
        hechas, total = progreso_cuestionario(d)
        lineas.append(f"### {d.tipo.value} — {d.nombre_archivo} ({hechas}/{total})")
        lineas.append("")
        for p in d.preguntas_seguimiento:
            est = f" [{p.estado}]" if p.estado else ""
            lineas.append(f"- **{p.texto}**{est}")
            if p.respondida and p.respuesta:
                lineas.append(f"  - Analista: {p.respuesta}")
                if p.ref:
                    lineas.append(f"  - Ref: {p.ref}")
            else:
                lineas.append("  - Analista: _(pendiente)_")
        lineas.append("")
    if not hubo_qa:
        lineas.append("- Aún no hay rúbricas asociadas.")

    lineas.extend(["", "## 5b. Dictámenes jurídicos", ""])
    if sesion.dictamenes_juridicos:
        for dj in sesion.dictamenes_juridicos:
            lineas.append(
                f"### Dictamen {dj.alcance.value} — {dj.fecha.isoformat()} "
                f"({len(dj.documento_ids)} doc(s))"
            )
            lineas.append("")
            lineas.append(dj.markdown or "_(vacío)_")
            lineas.append("")
            if dj.slots_pendientes:
                lineas.append(
                    "Limitación — slots pendientes: "
                    + ", ".join(s.value for s in dj.slots_pendientes)
                )
                lineas.append("")
    else:
        lineas.append("- Sin dictámenes jurídicos registrados.")

    pendientes_slots = [
        s.tipo_documento.value
        for s in sesion.checklist_slots
        if not s.auditado
    ]
    lineas.extend(["", "## 6. Cobertura del checklist sugerido", ""])
    if pendientes_slots:
        lineas.append(
            "Slots aún sin documento de identidad correcta: "
            + ", ".join(pendientes_slots)
        )
        recomendaciones.append(
            "Completar la carga de los documentos pendientes del checklist sugerido."
        )
    else:
        lineas.append("- Todos los slots sugeridos tienen al menos un documento con tipo coincidente.")

    # Dedup recomendaciones
    seen: set[str] = set()
    recs_uniq: list[str] = []
    for r in recomendaciones:
        if r not in seen:
            seen.add(r)
            recs_uniq.append(r)

    lineas.extend(["", "## 7. Conclusión", ""])
    n_ok = sum(1 for d in sesion.documentos_analizados if d.cumple and getattr(d, "tipo_coincide", True))
    n_bad = len(sesion.documentos_analizados) - n_ok
    lineas.append(
        f"De {len(sesion.documentos_analizados)} documento(s) revisado(s), "
        f"{n_ok} cumplen con identidad correcta y evaluación favorable; "
        f"{n_bad} presentan incumplimientos, tipo incorrecto u observaciones abiertas."
    )

    lineas.extend(["", "## 8. Recomendaciones", ""])
    if recs_uniq:
        for i, r in enumerate(recs_uniq, start=1):
            lineas.append(f"{i}. {r}")
    else:
        lineas.append(
            "1. Mantener trazabilidad del expediente y archivar los informes por documento."
        )
        lineas.append(
            "2. Revisar periódicamente la coherencia de nomenclatura entre piezas del expediente."
        )

    lineas.append("")
    return "\n".join(lineas)
