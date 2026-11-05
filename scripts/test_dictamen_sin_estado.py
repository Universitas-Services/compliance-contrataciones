"""Pruebas sin LLM del dictamen sin estado (POST /api/dictamen)."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core import llm_client
from app.core import session_store

os.environ["AGENT_AUTH_ENABLED"] = "false"

from app.agents import orchestrator  # noqa: E402
from app.main import app  # noqa: E402


def _js(tipo: str, nombre: str, *, conformes: int = 1, estado: str = "no") -> dict:
    return {
        "documento_evaluado": nombre,
        "tipo_documento": tipo,
        "tipo_coincide": True,
        "tipo_contrato": "BIENES",
        "estatus_global": "Rojo",
        "hallazgos": [
            {
                "codigo_pregunta": "CAAUAI.14",
                "pregunta_evaluada": "¿Plazo mínimo?",
                "rango_criticidad": "CRÍTICO: 5",
                "estado": estado,
                "respuesta": "5 días hábiles frente a 7.",
                "evidencia": "Tabla 1",
            }
        ],
        "conformes": [
            {"codigo_pregunta": f"X.{i}", "rango_criticidad": "ORDINARIA: 1", "respuesta": "ok"}
            for i in range(conformes)
        ],
        "no_aplica": [],
    }


CUERPO = {
    "nomenclatura": "CA-001",
    "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA",
    "tipo_contratacion": "BIENES",
}


def _cliente(capturas: dict) -> TestClient:
    def falso(**kw):
        capturas["user"] = kw.get("user_content")
        return "## 1. Alcance\nok.\n## 4. Conclusión\nFin.", "stop"

    llm_client._llamar_modelo_meta = falso
    return TestClient(app)


def test_dictamen_con_jsons() -> None:
    capturas: dict = {}
    antes = len(session_store.listar_sesiones())
    r = _cliente(capturas).post(
        "/api/dictamen",
        json={**CUERPO, "documentos": [_js("ACTA_INICIO", "acta.docx", conformes=2)]},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["alcance"] == "PARCIAL" and d["markdown"].startswith("# Informe Ejecutivo Parcial")
    p = d["puntaje"]
    assert p["global"]["maximo"] == 7 and p["global"]["obtenidos"] == 2
    assert p["flag_nulidad_absoluta"] and p["hallazgo_raiz"]["codigo_pregunta"] == "CAAUAI.14"
    assert "ACTA_INICIO" not in d["pendientes"] and "CONTRATO" in d["pendientes"]
    # Los conteos del expediente salen del JSON, no de una sesión previa.
    assert "si=2" in capturas["user"] and "no=1" in capturas["user"]
    assert len(session_store.listar_sesiones()) == antes, "no debe guardar sesión"
    print("OK dictamen desde JSON, sin sesión guardada")


def test_validaciones() -> None:
    c = _cliente({})
    assert c.post("/api/dictamen", json={**CUERPO, "documentos": []}).status_code == 422
    malo = _js("NO_EXISTE", "x.docx")
    r = c.post("/api/dictamen", json={**CUERPO, "documentos": [malo]})
    assert r.status_code == 422 and "tipo_documento" in r.text, r.text
    print("OK validaciones (lista vacía y tipo inválido)")


def test_documento_incorrecto_no_cuenta() -> None:
    js = _js("ADJUDICACION_O_EQUIVALENTE", "notificacion.docx")
    js["tipo_coincide"] = False
    doc = orchestrator._documento_desde_json(js)
    assert doc.tipo_coincide is False
    r = _cliente({}).post(
        "/api/dictamen",
        json={**CUERPO, "documentos": [_js("ACTA_INICIO", "acta.docx"), js]},
    )
    d = r.json()
    assert "ADJUDICACION_O_EQUIVALENTE" in d["pendientes"], d["pendientes"]
    assert len(d["puntaje"]["documentos"]) == 1
    print("OK documento en la casilla equivocada no cuenta")


if __name__ == "__main__":
    test_dictamen_con_jsons()
    test_validaciones()
    test_documento_incorrecto_no_cuenta()
