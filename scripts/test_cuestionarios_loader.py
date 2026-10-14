"""Pruebas rápidas sin LLM del parser de cuestionarios (formato con fundamento detallado)."""

from __future__ import annotations

from app.agents.knowledge.cuestionarios_loader import (
    _parse_items,
    cita_corta_fundamento,
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
**CONDICIONAL:** Solo si hubo prórroga ( ver CAAUC.25 ).
**Rango de Criticidad: RELEVANTE: 3**
**Acción Legal:** Corrección del contrato. ( incumplimiento del Art. 5 SUNAI).
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

    # CONDICIONAL explícito: se lee, se retira del bloque y normaliza «( ».
    i26 = items["CAAUC.26"]
    assert i26.condicion == "Solo si hubo prórroga (ver CAAUC.25).", i26.condicion
    assert i26.accion_legal == "Corrección del contrato. (incumplimiento del Art. 5 SUNAI).", i26
    assert items["CAAUAI.14"].condicion is None
    print("OK parser formato detallado")


def test_item_condicional() -> None:
    from app.core.llm_client import _es_item_condicional, _formato_lote_items

    assert _es_item_condicional({"texto": "Si la contratación fue plurianual, ¿…?"})
    assert not _es_item_condicional({"texto": "¿Se señalaron las causales?"})
    it = {"codigo": "CAAUIR.14", "texto": "¿Se señalaron las causales?",
          "condicion": "Solo si se apartó de la recomendación."}
    assert _es_item_condicional(it)
    assert "[CONDICIONAL: Solo si se apartó de la recomendación.]" in _formato_lote_items([it])
    print("OK ítems condicionales (etiqueta + redacción)")


def test_particion_por_tipo() -> None:
    items = _parse_items(_MD)
    aplic, excl = particionar_items_por_tipo(items, "BIENES")
    assert [i.codigo for i in excl] == ["CAAUC.26"], excl
    aplic, excl = particionar_items_por_tipo(items, "OBRAS")
    # 14 por etiqueta; 27 sin etiqueta válida → heurística («entrega de bienes»).
    assert {i.codigo for i in excl} == {"CAAUAI.14", "CAAUC.27"}, excl
    print("OK partición por tipo (APLICA_A + heurística)")


def test_cita_corta_fundamento() -> None:
    detallado = (
        "**Normativa principal:** **Reglamento de la Ley de Contrataciones Públicas:** "
        "**Artículo 107:** El acta (...) **Ley Orgánica de Procedimientos "
        "Administrativos:** **Artículo 18:** Todo acto (...) **Artículo 81:** La "
        "administración (...) **Normativa complementaria:** **Ley Contra la "
        "Corrupción:** **Artículo 17:** Las funcionarias (...)"
    )
    assert cita_corta_fundamento(detallado) == "Art. 107 RLCP; Arts. 18 y 81 LOPA"
    inline = (
        "**Normativa principal** **Artículo 6, numeral 2 de la Ley de Contrataciones "
        "Públicas:** A los fines (...) **Artículo 7 del Reglamento de la Ley de "
        "Contrataciones Públicas:** Para todas (...)"
    )
    assert cita_corta_fundamento(inline) == "Art. 6 num. 2 LCP; Art. 7 RLCP"
    sunai = "**Normas de Control Interno Aplicables a Contrataciones Públicas (SUNAI):** **Artículo 23:** Las (...)"
    assert cita_corta_fundamento(sunai) == "Art. 23 Normas SUNAI"
    assert cita_corta_fundamento("67.1, 78.1 LCP; 17, 22 LCC") == "Arts. 67.1, 78.1 LCP; 17, 22 LCC"
    assert cita_corta_fundamento(None) == ""
    print("OK cita corta de fundamento")


if __name__ == "__main__":
    test_parser_formato_detallado()
    test_item_condicional()
    test_particion_por_tipo()
    test_cita_corta_fundamento()
