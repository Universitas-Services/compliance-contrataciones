"""
Prueba e2e del flujo conversacional multi-modalidad.

Requisitos:
  - Servidor: uvicorn app.main:app --reload --port 8000
  - GEMINI_API_KEY en .env

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\probar_flujo.py
  .\\.venv\\Scripts\\python.exe scripts\\probar_flujo.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _docx(path: Path, titulo: str, cuerpo: str) -> Path:
    doc = Document()
    doc.add_heading(titulo, level=1)
    for line in cuerpo.split("\n"):
        doc.add_paragraph(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def generar_fixtures() -> dict[str, Path]:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    acta = _docx(
        FIXTURES / "acta_inicio.docx",
        "Acta de Inicio",
        """
ACTA DE INICIO
Objeto: adquisición de equipos. Número: CA-AU-2026-001.
Monto estimado: Bs. 1.000.000.
Verificación RNC de empresas: OK.
Empresas con NEC y calificación financiera: TechSur (NEC B).
Razones técnicas: experiencia previa.
Cronograma: llamado 10/03, recepción 25/03.
Firmas de la Comisión: presentes.
""".strip(),
    )
    solicitud = _docx(
        FIXTURES / "solicitud.docx",
        "Solicitud unidad usuaria",
        "Solicitud formal para adquirir laptops. Procedimiento CA-AU-2026-001.",
    )
    return {"acta": acta, "solicitud": solicitud}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    fixtures = generar_fixtures()
    try:
        with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
            health = client.get("/health")
            health.raise_for_status()
            print("health", health.json())

            # 1) Crear sesión configurada
            r = client.post(
                "/api/sesiones/",
                json={
                    "nomenclatura": "CA-AU-2026-001",
                    "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA",
                    "tipo_contratacion": "BIENES",
                },
            )
            r.raise_for_status()
            data = r.json()
            sid = data["sesion"]["id"]
            print("sesion", sid)
            print(data["mensaje"][:400], "...\n")

            # 2) Chat
            r2 = client.post(
                f"/api/sesiones/{sid}/mensaje",
                json={"mensaje": "¿Puedo cargar solo el Acta de Inicio sin el resto?"},
            )
            r2.raise_for_status()
            print("chat:", r2.json()["respuesta"][:300], "...\n")

            # 3) Subir un documento (sin orden)
            with fixtures["acta"].open("rb") as fh:
                up = client.post(
                    f"/api/sesiones/{sid}/documentos",
                    params={"tipo_documento": "ACTA_INICIO"},
                    files={
                        "archivo": (
                            "acta_inicio.docx",
                            fh,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                )
            up.raise_for_status()
            doc = up.json()["documento"]
            doc_id = doc["id"]
            print("doc", doc_id, "cumple", doc["cumple"])

            # 4) Descargas informe documento
            for ext in ("pdf", "docx"):
                dl = client.get(f"/api/sesiones/{sid}/documentos/{doc_id}/informe.{ext}")
                dl.raise_for_status()
                out = FIXTURES / f"informe_doc.{ext}"
                out.write_bytes(dl.content)
                print("saved", out, "bytes", len(dl.content))

            # 5) Segundo documento + informe global (sin LLM forzado opcional)
            with fixtures["solicitud"].open("rb") as fh:
                up2 = client.post(
                    f"/api/sesiones/{sid}/documentos",
                    params={"tipo_documento": "SOLICITUD_UNIDAD_USUARIA"},
                    files={
                        "archivo": (
                            "solicitud.docx",
                            fh,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                )
            up2.raise_for_status()
            print("segundo doc ok")

            glob_md = client.get(f"/api/sesiones/{sid}/informe", params={"usar_llm": True})
            glob_md.raise_for_status()
            print("\n===== INFORME GLOBAL =====\n")
            print(glob_md.json()["informe_markdown"][:2000])

            for ext in ("pdf", "docx"):
                dl = client.get(
                    f"/api/sesiones/{sid}/informe.{ext}",
                    params={"usar_llm": False},
                )
                # pdf/docx regeneran markdown; usar_llm=False evita segunda llamada si ya hay cache... 
                # export_global siempre regenera md; False usa sintético
                dl.raise_for_status()
                out = FIXTURES / f"informe_global.{ext}"
                out.write_bytes(dl.content)
                print("saved", out)

    except httpx.ConnectError:
        print("No hay servidor en", args.base_url, file=sys.stderr)
        return 1
    except Exception as exc:
        print("Fallo e2e:", exc, file=sys.stderr)
        return 1

    print("\nE2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
