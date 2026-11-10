"""Pruebas sin LLM de POST /api/conversar (chat sin estado)."""

from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from app.core import llm_client

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
    assert d["acciones"] == [
        {"accion": "fijar_expediente", "nomenclatura": "CA-001",
         "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA", "tipo_contratacion": "BIENES"},
        {"accion": "pedir_documento", "tipo_documento": "ACTIVIDADES_PREVIAS"},
    ], d["acciones"]
    u = capturas["user"]
    assert "Falta la garantía." in u and "¿TEXTO DE LA PREGUNTA?" not in u
    assert "OFERTAS (Ofertas): analizado" in u and "Hola, Carlos." in u
    print("OK conversar: acciones válidas, sin texto de preguntas, con historial y checklist")

    llm_client._llamar_modelo_meta = lambda **kw: ("no es json", "stop")
    r = TestClient(app).post("/api/conversar", json={"mensaje": "hola"})
    assert r.status_code == 200 and r.json()["acciones"] == []
    print("OK conversar: respuesta inválida del modelo no rompe el chat")


if __name__ == "__main__":
    main()
