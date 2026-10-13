"""Pruebas rápidas sin LLM de los extractos por lote (documentos largos)."""

from __future__ import annotations

from app.agents.extractos import UMBRAL_DOC_LARGO, ExtractorLotes, texto_identidad


def _doc_largo() -> str:
    relleno = "Texto general del pliego sin relación con las preguntas. " * 40
    return "\n".join(
        [
            "[encabezado]\nComisión de Contrataciones N° CA-SDEDTEOEL-CA-002-2026",
            "PLIEGO DE CONDICIONES CONCURSO ABIERTO",
            *[f"CLÁUSULA {n}.- {relleno}" for n in range(1, 15)],
            "CLÁUSULA 20.- GARANTÍA DE FIEL CUMPLIMIENTO: el contratista constituirá "
            "una fianza equivalente al veinte por ciento (20%) del monto del contrato.",
            *[f"CLÁUSULA {n}.- {relleno}" for n in range(21, 30)],
            "CRONOGRAMA: Disponibilidad del pliego 30/04/2026 al 11/05/2026.",
            "Firman: Comisión de Contrataciones. Barquisimeto, 27/04/2026.",
        ]
    )


def test_documento_corto_va_completo() -> None:
    texto = "Acta breve. " * 100
    assert len(texto) < UMBRAL_DOC_LARGO
    assert ExtractorLotes(texto).texto_para_lote(["¿pregunta?"]) == texto
    print("OK documento corto completo")


def test_documento_largo_extractos() -> None:
    texto = _doc_largo()
    assert len(texto) > UMBRAL_DOC_LARGO
    out = ExtractorLotes(texto).texto_para_lote(
        ["¿El pliego estableció la garantía de fiel cumplimiento especificando sus condiciones?"]
    )
    assert out.startswith("(EXTRACTOS")
    assert len(out) < len(texto) / 2
    assert "veinte por ciento (20%)" in out  # sección relevante
    assert "CA-SDEDTEOEL-CA-002-2026" in out  # encabezado siempre
    assert "Barquisimeto, 27/04/2026" in out  # final del documento siempre
    print("OK documento largo → extractos relevantes + encabezado + final")


def test_identidad_inicio_y_final() -> None:
    texto = "INICIO " + ("x " * 20_000) + " FINAL"
    t = texto_identidad(texto)
    assert t.startswith("INICIO") and t.rstrip().endswith("FINAL") and len(t) < 16_000
    print("OK identidad con inicio y final")


if __name__ == "__main__":
    test_documento_corto_va_completo()
    test_documento_largo_extractos()
    test_identidad_inicio_y_final()
