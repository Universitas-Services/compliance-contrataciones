"""Pruebas sin LLM del puntaje calculado por código (app/agents/puntaje.py)."""

from __future__ import annotations

from app.agents.puntaje import (
    bloque_resultados,
    peso_criticidad,
    puntaje_documento,
    puntaje_expediente,
    rango_porcentaje,
)


def _js(conformes: list[tuple[str, str]], hallazgos: list[tuple[str, str, str]]) -> dict:
    return {
        "conformes": [{"codigo_pregunta": c, "rango_criticidad": r} for c, r in conformes],
        "hallazgos": [
            {"codigo_pregunta": c, "rango_criticidad": r, "estado": e} for c, r, e in hallazgos
        ],
        "no_aplica": [{"codigo_pregunta": "X.9", "motivo": "no plurianual"}],
    }


def test_pesos_y_rangos() -> None:
    assert peso_criticidad("CRÍTICO: 5") == 5
    assert peso_criticidad("RELEVANTE (3)") == 3
    assert peso_criticidad("ORDINARIA : 1") == 1
    assert peso_criticidad("Crítica") == 5 and peso_criticidad(None) is None
    assert rango_porcentaje(95) == "Cumplimiento Sobresaliente"
    assert rango_porcentaje(94.99) == "Cumplimiento Aceptable"
    assert rango_porcentaje(89.99) == "Hallazgos Significativos"
    assert rango_porcentaje(84.99) == "Hallazgos Críticos"
    print("OK pesos y rangos")


def test_documento_regla_v1() -> None:
    js = _js(
        [("A.1", "CRÍTICO: 5"), ("A.2", "ORDINARIA: 1")],
        [("A.3", "CRÍTICO: 5", "parcial"), ("A.4", "RELEVANTE: 3", "no_consta"),
         ("A.5", "CRÍTICO: 5", "no")],
    )
    pd = puntaje_documento(js, tipo_documento="ACTA_INICIO", nombre="acta.docx")
    # Máx = 5+1+5+3+5 = 19 (el N/A no cuenta); obtenidos = solo «si» = 6.
    assert (pd.maximo, pd.obtenidos, pd.perdidos) == (19, 6, 13)
    assert pd.porcentaje == 31.58 and pd.rango == "Hallazgos Críticos"
    # Flag solo con «no» crítico, no con «parcial».
    assert pd.criticos_no == ["A.5"]
    # Peso desde el cuestionario si el JSON no lo trae.
    js2 = {"conformes": [{"codigo_pregunta": "B.1"}], "hallazgos": []}
    pd2 = puntaje_documento(js2, tipo_documento="LLAMADO", nombre="l", peso_por_codigo=lambda c: 3)
    assert pd2.maximo == 3 and not pd2.sin_peso
    print("OK documento (parcial = 0, N/A fuera, flag solo con «no»)")


def test_expediente_raiz_y_fase() -> None:
    orden = ["ACTIVIDADES_PREVIAS", "ACTA_INICIO", "PLIEGO_CONDICIONES", "ADJUDICACION_O_EQUIVALENTE"]
    docs = [
        # Subido primero, pero es una fase posterior: no puede ser la raíz.
        ("PLIEGO_CONDICIONES", "pliego", _js([("P.1", "CRÍTICO: 5")], [("P.2", "CRÍTICO: 5", "no")])),
        ("ACTIVIDADES_PREVIAS", "previas", _js([], [("P0.1", "CRÍTICO: 5", "parcial")])),
        ("ACTA_INICIO", "acta", _js([("I.1", "RELEVANTE: 3")], [("I.2", "CRÍTICO: 5", "no")])),
    ]
    px = puntaje_expediente(docs, orden_tipos=orden, pendientes=["ADJUDICACION_O_EQUIVALENTE"])
    assert [d.tipo_documento for d in px.documentos] == orden[:3]
    assert px.hallazgo_raiz["codigo_pregunta"] == "I.2"  # el parcial de previas no cuenta
    assert px.flag_nulidad and not px.informe_final and not px.incluye_adjudicacion
    assert (px.maximo, px.obtenidos) == (5 + 3 + 5 + 5 + 5, 3 + 5)
    txt = bloque_resultados(px)
    assert "Hallazgo Raíz" in txt and "I.2" in txt and "PARCIAL" in txt
    assert "reposición" in txt and "Art. 98 RLCP" in txt
    print("OK expediente (orden cronológico, raíz, flag, parcial, fase)")


if __name__ == "__main__":
    test_pesos_y_rangos()
    test_documento_regla_v1()
    test_expediente_raiz_y_fase()
