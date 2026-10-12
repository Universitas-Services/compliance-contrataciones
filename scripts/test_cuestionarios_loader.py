"""Pruebas rápidas sin LLM del parser de cuestionarios (formato con fundamento detallado)."""

from __future__ import annotations

from app.agents.knowledge.cuestionarios_loader import (
    _parse_items,
    particionar_items_por_tipo,
)

_MD = """**CUESTIONARIO AUDITORÍA ACTA DE INICIO**

**CAAUAI 1**.-¿Se especificó la fecha del Acta de Inicio?
**RANGO DE CRITICIDAD:ORDINARIA: 1**
**Respuesta: SI; NO; N/A**
**ACCIÓN LEGAL**:Subsanación administrativa de errores materiales.
**ADVERTENCIA PARA LA GERENCIA**: La falta de fecha impide el cómputo de lapsos.
**FUNDAMENTO LEGAL VIOLENTADO EN CASO DE NO:**
**Artículo 18:** Todo acto administrativo deberá contener (...) fecha.

**CAAUAI** 14 .-¿El plazo para presentar ofertas en la adquisición de bienes no podrá ser menor a siete días hábiles?
**RANGO DE CRITICIDAD: CRÍTICO: 5**
**Respuesta: SI; NO; N/A**
**APLICA_A:** BIENES
**ACCIÓN LEGAL:** Reposición de la causa al estado de publicación.
**ADVERTENCIA PARA LA GERENCIA:** Restringe la libre competencia.
**FUNDAMENTO LEGAL VIOLENTADO EN CASO DE NO:**
**Artículo 67:** (...)

**CAAUAI** 31- Si la contratación se proyectó con una ejecución plurianual, ¿el Acta de Inicio reflejó esta condición?
**RANGO DE CRITICIDAD:ORDINARIA: 1**
**Respuesta: SI; NO; N/A**
**ACCIÓN LEGAL:** Recomendación de ajuste contable-presupuestario.
**ADVERTENCIA PARA LA GERENCIA:** Compromete pagos futuros.
**FUNDAMENTO LEGAL VIOLENTADO EN CASO DE NO:**
**Artículo 10:** (...)
**APLICA_A:** TODOS

**CAAUC.** 26 ¿El contrato determinó de manera expresa la fecha de terminación de la obra?
**Respuesta: SI; NO; N/A**
**APLICA_A:** Obras; Servicios
**Rango de Criticidad: RELEVANTE: 3**
**Acción Legal:** Corrección del contrato.
**Advertencia a la Gerencia:** Impide medir el retraso.

**CAAUC.** 27 ¿El contrato determinó de manera expresa la fecha de entrega de bienes?
**Respuesta: SI; NO; N/A**
**APLICA_A:** MAQUINARIA
**RANGO DE CRITICIDAD: RELEVANTE: 3**
"""


def test_parser_formato_detallado() -> None:
    items = {it.codigo: it for it in _parse_items(_MD)}
    assert list(items) == ["CAAUAI.1", "CAAUAI.14", "CAAUAI.31", "CAAUC.26", "CAAUC.27"]

    # Dos puntos fuera de la negrita.
    i1 = items["CAAUAI.1"]
    assert i1.accion_legal and i1.accion_legal.startswith("Subsanación"), i1
    assert i1.advertencia_gerencia and "cómputo de lapsos" in i1.advertencia_gerencia, i1
    assert i1.aplica_a is None

    # APLICA_A explícito, sin colarse en el fundamento.
    assert items["CAAUAI.14"].aplica_a == frozenset({"BIENES"})
    i31 = items["CAAUAI.31"]
    assert i31.aplica_a == frozenset({"BIENES", "OBRAS", "SERVICIOS"})
    assert "APLICA" not in (i31.fundamento_legal or "")

    # Condición antes del «¿» se conserva.
    assert i31.texto.startswith("Si la contratación se proyectó"), i31.texto

    # Mayúsculas/minúsculas y valor inválido → heurística.
    assert items["CAAUC.26"].aplica_a == frozenset({"OBRAS", "SERVICIOS"})
    assert items["CAAUC.26"].rango_criticidad == "RELEVANTE: 3"
    assert items["CAAUC.27"].aplica_a is None
    print("OK parser formato detallado")


def test_particion_por_tipo() -> None:
    items = _parse_items(_MD)
    aplic, excl = particionar_items_por_tipo(items, "BIENES")
    assert [i.codigo for i in excl] == ["CAAUC.26"], excl
    aplic, excl = particionar_items_por_tipo(items, "OBRAS")
    # 14 por etiqueta; 27 sin etiqueta válida → heurística («entrega de bienes»).
    assert {i.codigo for i in excl} == {"CAAUAI.14", "CAAUC.27"}, excl
    print("OK partición por tipo (APLICA_A + heurística)")


if __name__ == "__main__":
    test_parser_formato_detallado()
    test_particion_por_tipo()
