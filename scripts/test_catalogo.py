"""Pruebas sin LLM de GET /api/catalogo y de las páginas del sandbox."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core import llm_client  # noqa: F401  (carga .env antes de sobrescribir)

os.environ["AGENT_AUTH_ENABLED"] = "false"

from app.main import app  # noqa: E402


def main() -> None:
    c = TestClient(app)
    d = c.get("/api/catalogo").json()
    estados = {m["valor"]: m["estado"] for m in d["modalidades"]}
    assert estados["CA_ACTO_UNICO_APERTURA_UNICA"] == "disponible"
    assert estados["CONTRATACION_DIRECTA"] == "sin_validar"
    assert estados["CONCURSO_CERRADO"] == "sin_cuestionarios"
    au = next(m for m in d["modalidades"] if m["valor"] == "CA_ACTO_UNICO_APERTURA_UNICA")
    assert [s["tipo_documento"] for s in au["checklist"]][:2] == ["ACTIVIDADES_PREVIAS", "ACTA_INICIO"]
    assert len(au["checklist"]) == 12 and all(s["nombre"] for s in au["checklist"])
    assert [t["valor"] for t in d["tipos_contratacion"]] == ["BIENES", "OBRAS", "SERVICIOS"]
    print("OK catálogo: modalidades con estado, checklist y tipos")

    for ruta in ("/sandbox", "/sandbox/clasico", "/sandbox/static/app.js", "/sandbox/static/estilos.css"):
        assert c.get(ruta).status_code == 200, ruta
    print("OK sandbox nuevo y clásico disponibles")


if __name__ == "__main__":
    main()
