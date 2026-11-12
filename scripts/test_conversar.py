"""Pruebas sin LLM de POST /api/conversar (chat sin estado)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.agents.cuestionario import informe_documento_descargable
from app.core import llm_client
from app.models.schemas import Modalidad, TipoContratacion, TipoDocumento

os.environ["AGENT_AUTH_ENABLED"] = "false"

from app.main import app  # noqa: E402


def main() -> None:
    capturas: dict = {}

    def falso(**kw):
        capturas["user"] = kw["user_content"]
        return json.dumps({
            "respuesta": "Registré el expediente **CA-001**. Ahora sube las Actividades Previas.",
            "acciones": [
                {"accion": "fijar_expediente", "nomenclatura": "CA-001",
                 "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA", "tipo_contratacion": "BIENES"},
                {"accion": "pedir_documento", "tipo_documento": "ACTIVIDADES_PREVIAS"},
                {"accion": "fijar_expediente", "modalidad": "INVENTADA"},
                {"accion": "borrar_todo"},
            ],
        }), "stop"

    llm_client._llamar_modelo_meta = falso
    oferta = {
        "documento_evaluado": "oferta.pdf", "tipo_documento": "OFERTAS", "tipo_coincide": True,
        "estatus_global": "Rojo",
        "hallazgos": [{"codigo_pregunta": "CAAUO.1", "estado": "no", "rango_criticidad": "CRÍTICO: 5",
                       "pregunta_evaluada": "¿TEXTO DE LA PREGUNTA?", "respuesta": "Falta la garantía."}],
    }
    r = TestClient(app).post("/api/conversar", json={
        "usuario_nombre": "Carlos", "ente": "Alcaldía de Iribarren",
        "expediente": {"modalidad": "CA_ACTO_UNICO_APERTURA_UNICA", "documentos": [oferta]},
        "historial": [{"rol": "agente", "texto": "Hola, Carlos."}],
        "mensaje": "es el CA-001, concurso abierto de bienes",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert "**" not in d["respuesta"]
    assert "corresponde subir" not in d["respuesta"]
    assert d["acciones"] == [
        {"accion": "fijar_expediente", "nomenclatura": "CA-001",
         "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA", "tipo_contratacion": "BIENES"},
    ], d["acciones"]
    u = capturas["user"]
    assert "Falta la garantía." in u and "¿TEXTO DE LA PREGUNTA?" not in u
    assert "OFERTAS (Ofertas): analizado" in u and "Hola, Carlos." in u
    print("OK conversar: al completar el registro no pide documento; sin texto de preguntas")

    llm_client._llamar_modelo_meta = lambda **kw: (json.dumps({
        "respuesta": "Te faltan las Actividades Previas, entre otros.",
        "acciones": [{"accion": "pedir_documento", "tipo_documento": "ACTIVIDADES_PREVIAS"},
                     {"accion": "pedir_documento", "tipo_documento": "INVITACIONES"}],
    }), "stop")
    r = TestClient(app).post("/api/conversar", json={
        "expediente": {"nomenclatura": "CA-001", "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA",
                       "tipo_contratacion": "BIENES", "documentos": [oferta]},
        "mensaje": "¿qué me falta?",
    })
    assert r.status_code == 200, r.text
    assert r.json()["acciones"] == [
        {"accion": "pedir_documento", "tipo_documento": "ACTIVIDADES_PREVIAS"},
    ], r.json()["acciones"]
    print("OK conversar: con el registro completo, sugiere solo documentos del checklist")

    llm_client._llamar_modelo_meta = lambda **kw: ("no es json", "stop")
    r = TestClient(app).post("/api/conversar", json={"mensaje": "hola"})
    assert r.status_code == 200 and r.json()["acciones"] == []
    print("OK conversar: respuesta inválida del modelo no rompe el chat")

    md = informe_documento_descargable(
        "# Informe del modelo\n\nHe finalizado la revisión.",
        nomenclatura="CA-001",
        modalidad=Modalidad.CA_ACTO_UNICO_APERTURA_UNICA,
        tipo_contratacion=TipoContratacion.BIENES,
        tipo_documento=TipoDocumento.ACTA_INICIO,
        nombre_archivo="acta.docx",
        estatus_global="Rojo",
        fecha=datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc),
    )
    assert md.startswith("# Resumen de revisión: Acta de Inicio\n"), md
    assert "- **Expediente:** CA-001" in md and "- **Fecha de revisión:** 12/11/2026" in md
    assert md.count("\n# ") == 0 and "## Informe del modelo" in md
    print("OK resumen descargable: título, datos del expediente y fecha de Venezuela")


if __name__ == "__main__":
    main()
