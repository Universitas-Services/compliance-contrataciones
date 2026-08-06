"""Helpers de cuestionario de seguimiento e informes."""

from __future__ import annotations

import re

from app.models.schemas import DocumentoAnalizado, PreguntaSeguimiento, SesionCompliance

_QA_SECTION = "## Respuestas de seguimiento / cuestionario"
_QA_SECTION_ALT = "## Respuestas de seguimiento"


def pregunta_pendiente(doc: DocumentoAnalizado) -> PreguntaSeguimiento | None:
    for p in doc.preguntas_seguimiento:
        if not p.respondida:
            return p
    return None


def progreso_cuestionario(doc: DocumentoAnalizado) -> tuple[int, int]:
    total = len(doc.preguntas_seguimiento)
    hechas = sum(1 for p in doc.preguntas_seguimiento if p.respondida)
    return hechas, total


def documento_cuestionario_activo(
    sesion: SesionCompliance,
) -> DocumentoAnalizado | None:
    if sesion.documento_en_cuestionario:
        for d in sesion.documentos_analizados:
            if d.id == sesion.documento_en_cuestionario:
                if pregunta_pendiente(d) is not None:
                    return d
                break
    # Fallback: último doc con preguntas pendientes
    for d in reversed(sesion.documentos_analizados):
        if pregunta_pendiente(d) is not None:
            return d
    return None


def sincronizar_informe_documento(doc: DocumentoAnalizado) -> None:
    """Reescribe la sección de Q&A del informe del documento desde el estado actual."""
    base = doc.informe_markdown or ""
    for marker in (_QA_SECTION, _QA_SECTION_ALT):
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
        f"Progreso: {hechas}/{total} respondidas.",
        "",
    ]
    for i, p in enumerate(doc.preguntas_seguimiento, start=1):
        estado = "respondida" if p.respondida else "pendiente"
        lineas.append(f"### Pregunta {i} ({estado})")
        lineas.append("")
        lineas.append(p.texto)
        lineas.append("")
        if p.respondida and p.respuesta:
            lineas.append(f"**Respuesta del usuario:** {p.respuesta}")
        else:
            lineas.append("**Respuesta del usuario:** _(pendiente)_")
        lineas.append("")

    doc.informe_markdown = (base + "\n" + "\n".join(lineas)).strip() + "\n"


def registrar_respuesta(
    doc: DocumentoAnalizado,
    texto_respuesta: str,
    *,
    pregunta_id: str | None = None,
) -> PreguntaSeguimiento | None:
    """Registra respuesta a una pregunta (por id o a la siguiente pendiente)."""
    target: PreguntaSeguimiento | None = None
    if pregunta_id:
        target = next((p for p in doc.preguntas_seguimiento if p.id == pregunta_id), None)
    if target is None:
        target = pregunta_pendiente(doc)
    if target is None:
        return None
    target.respuesta = texto_respuesta.strip()
    target.respondida = True
    sincronizar_informe_documento(doc)
    return target


def mensaje_pregunta_actual(doc: DocumentoAnalizado) -> str:
    pend = pregunta_pendiente(doc)
    if pend is None:
        return (
            f"Cuestionario del documento «{doc.tipo.value}» completado. "
            "Las respuestas quedan en el informe del documento y se incluirán "
            "en el informe global del expediente."
        )
    hechas, total = progreso_cuestionario(doc)
    n = hechas + 1
    return (
        f"Cuestionario — {doc.tipo.value} ({doc.nombre_archivo})\n"
        f"Pregunta {n} de {total}:\n\n"
        f"{pend.texto}"
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

    lineas.extend(["", "## 5. Cuestionario de seguimiento (respuestas del usuario)", ""])
    hubo_qa = False
    for d in sesion.documentos_analizados:
        if not d.preguntas_seguimiento:
            continue
        hubo_qa = True
        hechas, total = progreso_cuestionario(d)
        lineas.append(f"### {d.tipo.value} — {d.nombre_archivo} ({hechas}/{total})")
        lineas.append("")
        for p in d.preguntas_seguimiento:
            lineas.append(f"- **{p.texto}**")
            if p.respondida and p.respuesta:
                lineas.append(f"  - Respuesta: {p.respuesta}")
            else:
                lineas.append("  - Respuesta: _(pendiente)_")
        lineas.append("")
    if not hubo_qa:
        lineas.append("- Aún no hay cuestionarios asociados.")

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
