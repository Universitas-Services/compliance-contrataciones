"""Códigos internos de pregunta (p. ej. CAAUAI.14) en los textos para el usuario.

Legal pidió que el dictamen y el informe no muestren códigos. Se pueden volver a
mostrar para revisiones internas con MOSTRAR_CODIGOS_PREGUNTA=1. El campo
`codigo_pregunta` de los JSON no se toca: es un dato para los clientes.
"""

from __future__ import annotations

import os
import re

_COD = r"\b[A-Z]{4,8}\.\d+(?:\.\d+)*\b"
_LISTA = rf"{_COD}(?:\s*(?:,|\by\b|\be\b)\s*{_COD})*"
_PALABRA = r"\b[cC][oó]digos?(?:\s+de\s+(?:la\s+)?pregunta)?\s*:?\s*"

REGLA_SIN_CODIGOS = (
    "\nCÓDIGOS INTERNOS: los datos traen códigos de pregunta (p. ej. CAAUAI.14) "
    "solo para que relaciones hallazgos. NUNCA los escribas en el dictamen: "
    "nombra el documento y describe el hecho incumplido.\n"
)


def mostrar_codigos() -> bool:
    return (os.getenv("MOSTRAR_CODIGOS_PREGUNTA") or "").strip().lower() in {"1", "true", "si", "sí"}


def quitar_codigos(texto: str) -> str:
    """Borra los códigos de pregunta de un texto, salvo que el interruptor esté encendido."""
    if not texto or mostrar_codigos():
        return texto
    t = re.sub(rf"[ \t]*\((?:(?:ver|v[eé]ase)\s+)?(?:{_PALABRA})?{_LISTA}\)", "", texto)
    t = re.sub(rf"[ \t]*,?[ \t]*{_PALABRA}{_LISTA}", "", t)
    t = re.sub(_LISTA, "", t)
    t = re.sub(r"\([ \t,;]*\)", "", t)
    t = re.sub(r"^([ \t]*[-*][ \t]*)[:,;][ \t]*", r"\1", t, flags=re.M)
    t = re.sub(r"[ \t]+([,.;:)])", r"\1", t)
    t = re.sub(r"\([ \t,;]+", "(", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t
