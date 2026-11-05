"""Pruebas sin LLM: un PDF escaneado ilegible no llega al modelo."""

from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from unittest import mock

import fitz
from fastapi.testclient import TestClient

from app.core import llm_client  # noqa: F401  (carga .env antes de sobrescribir)

os.environ["AGENT_AUTH_ENABLED"] = "false"

from app.core import capacidad  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import sesiones  # noqa: E402

CAMPOS = {
    "nomenclatura": "CA-001",
    "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA",
    "tipo_contratacion": "BIENES",
    "tipo_documento": "OFERTAS",
}


def _pdf_en_blanco() -> bytes:
    doc = fitz.open()
    doc.new_page()
    return doc.tobytes()


def _analizar(cliente: TestClient) -> tuple[int, str]:
    r = cliente.post(
        "/api/analizar",
        data=CAMPOS,
        files={"archivo": ("oferta.pdf", _pdf_en_blanco(), "application/pdf")},
    )
    return r.status_code, r.json()["detail"]


def main() -> None:
    llm = mock.Mock(side_effect=AssertionError("no debía llamar al modelo"))
    with mock.patch.object(sesiones, "analizar_documento", llm):
        cliente = TestClient(app)
        codigo, detalle = _analizar(cliente)
        assert codigo == 400 and "sin texto reconocible" in detalle, (codigo, detalle)
        print("OK PDF sin texto reconocible: 400 sin gastar tokens")

        with mock.patch.dict(sys.modules, {"rapidocr_onnxruntime": None}):
            codigo, detalle = _analizar(cliente)
        assert codigo == 503 and "no está disponible" in detalle, (codigo, detalle)
        print("OK motor de OCR sin cargar: 503, no se analiza a ciegas")

        with ExitStack() as cupos:
            for _ in range(capacidad.MAX_OCR):
                cupos.enter_context(capacidad.cupo_ocr())
            r = cliente.post(
                "/api/analizar",
                data=CAMPOS,
                files={"archivo": ("oferta.pdf", _pdf_en_blanco(), "application/pdf")},
            )
        assert r.status_code == 503 and r.headers["retry-after"] == "30", r.status_code
        assert _analizar(cliente)[0] == 400, "no liberó el cupo de OCR"
        print("OK cupo de OCR lleno: 503 con Retry-After y se libera")


if __name__ == "__main__":
    main()
