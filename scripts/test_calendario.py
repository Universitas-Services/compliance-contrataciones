"""Pruebas rápidas sin LLM del calendario de días hábiles."""

from __future__ import annotations

from datetime import date

from app.agents.knowledge.calendario import (
    bloque_calendario,
    fechas_en_texto,
    feriados_nacionales,
)


def test_feriados() -> None:
    f = feriados_nacionales(2026)
    assert f[date(2026, 5, 1)] == "Día del Trabajador"
    assert f[date(2026, 10, 12)] == "Día de la Resistencia Indígena"
    # Pascua 2026 = 5 de abril → Carnaval 16-17/02, Jueves y Viernes Santo 2-3/04.
    assert {date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 2), date(2026, 4, 3)} <= set(f)
    print("OK feriados nacionales")


def test_fechas_y_conteo() -> None:
    texto = (
        "En Barquisimeto a los 27 días de abril del 2026 (...) "
        "Disponibilidad del Pliego | 30/04/2026 al 11/05/2026 "
        "Acto Público de Recepción y Apertura | 11/05/2026"
    )
    assert fechas_en_texto(texto) == [date(2026, 4, 27), date(2026, 4, 30), date(2026, 5, 11)]
    cal = bloque_calendario(texto)
    assert "vie 01/05/2026 FERIADO (Día del Trabajador)" in cal
    assert "jue 30/04/2026* H4" in cal and "lun 11/05/2026* H10" in cal
    # Entre el 30/04 y el 11/05 (sin contar ninguno): 10 − 4 − 1 = 5 días hábiles.
    assert bloque_calendario("sin fechas") == ""
    print("OK fechas del texto + calendario numerado")


if __name__ == "__main__":
    test_feriados()
    test_fechas_y_conteo()
