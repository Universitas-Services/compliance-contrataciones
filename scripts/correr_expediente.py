"""Corre un expediente completo con Gemini real y guarda los JSON y el puntaje.

Uso:
  python -m scripts.correr_expediente MANIFIESTO SALIDA --modo con_memoria|sin_memoria

MANIFIESTO es un JSON con la nomenclatura, la modalidad, el tipo de contratación y
la lista de documentos en orden ({"archivo": ruta, "tipo": TipoDocumento}).

- con_memoria: como el sandbox; cada documento ve los anteriores.
- sin_memoria: como POST /api/analizar; cada documento se analiza solo.

Usa la configuración de Cloud Run (Vertex global, conocimiento en GCS) y gasta tokens.
El puntaje se calcula por código, sin dictamen.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core import llm_client
from app.agents.modalities import get_modalidad_agent  # noqa: E402
from app.agents.puntaje import puntaje_de_documentos  # noqa: E402
from app.core.security import sanitizar_nombre_archivo  # noqa: E402
from app.models.schemas import (  # noqa: E402
    EstadoSesion,
    Modalidad,
    SesionCompliance,
    TipoContratacion,
    TipoDocumento,
)
from app.routers.sesiones import _analizar_archivo  # noqa: E402

# Primero todos los imports: alguno carga .env, y la configuración de Cloud Run va después.

os.environ.update({
    "LLM_PROVIDER": "vertex",
    "GCP_PROJECT_ID": "marine-alchemy-510716-j5",
    "VERTEX_LOCATION": "global",
    "GEMINI_MODEL": "google/gemini-3.8-flash",
    "GEMINI_TIMEOUT": "110",
    "KNOWLEDGE_SOURCE": "gcs",
    "GCS_BUCKET_CUESTIONARIOS": "compliance-cuestionarios-26265028623",
    "GCS_BUCKET_BASAMENTO": "compliance-basamento-legal-26265028623",
    "FALLBACK_ENABLED": "false",
    "LLM_PRIORIDAD_429": "true",
    "LLM_REASONING_EFFORT_RUBRICA": "low",
    "LLM_MAX_TOKENS_RUBRICA": "8192",
    "LLM_TEMPERATURE_RUBRICA": "0.2",
})
for _k in ("GEMINI_BASE_URL", "OPENAI_BASE_URL"):
    os.environ.pop(_k, None)



def _sesion(manifiesto: dict) -> SesionCompliance:
    modalidad = Modalidad(manifiesto["modalidad"])
    tipo_ct = TipoContratacion(manifiesto["tipo_contratacion"])
    return SesionCompliance(
        id=str(uuid.uuid4()),
        nomenclatura=manifiesto["nomenclatura"],
        modalidad=modalidad,
        tipo_contratacion=tipo_ct,
        estado=EstadoSesion.ACTIVA,
        fecha_inicio=datetime.now(timezone.utc),
        checklist_slots=get_modalidad_agent(modalidad, tipo_ct).obtener_checklist(),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifiesto")
    ap.add_argument("salida")
    ap.add_argument("--modo", choices=["con_memoria", "sin_memoria"], required=True)
    args = ap.parse_args()

    manifiesto = json.loads(Path(args.manifiesto).read_text(encoding="utf-8"))
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    llm_client._vertex_access_token()  # credenciales listas antes de empezar

    expediente = _sesion(manifiesto)
    resumen = []
    t0 = time.time()
    for n, item in enumerate(manifiesto["documentos"], start=1):
        ruta = Path(item["archivo"])
        tipo = TipoDocumento(item["tipo"])
        nombre = sanitizar_nombre_archivo(ruta.name)
        # Sin memoria, cada documento se analiza en un expediente vacío.
        sesion = expediente if args.modo == "con_memoria" else _sesion(manifiesto)
        inicio = time.time()
        doc = _analizar_archivo(sesion, tipo, str(ruta), nombre)
        expediente.documentos_analizados.append(doc)
        (salida / f"{n:02d}_{tipo.value}.json").write_text(
            json.dumps(doc.json_analista, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        met = doc.metricas.model_dump() if doc.metricas else {}
        resumen.append({
            "n": n,
            "tipo": tipo.value,
            "archivo": ruta.name,
            "estatus": doc.estatus_global,
            "tipo_coincide": doc.tipo_coincide,
            "segundos": round(time.time() - inicio),
            **met,
        })
        print(f"{n:02d} {tipo.value:34} {doc.estatus_global:8} {time.time() - inicio:4.0f}s "
              f"{met.get('tokens_total', 0):6} tokens", flush=True)

    validos = {d.tipo for d in expediente.documentos_analizados if d.tipo_coincide}
    pendientes = [s.tipo_documento for s in expediente.checklist_slots if s.tipo_documento not in validos]
    puntaje, _ = puntaje_de_documentos(
        expediente.documentos_analizados,
        modalidad=expediente.modalidad,
        checklist_slots=expediente.checklist_slots,
        pendientes=pendientes,
    )
    (salida / "puntaje.json").write_text(
        json.dumps(puntaje.a_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tokens = sum(r.get("tokens_total", 0) for r in resumen)
    (salida / "resumen.json").write_text(json.dumps({
        "modo": args.modo,
        "documentos": resumen,
        "tokens_total": tokens,
        "minutos_total": round((time.time() - t0) / 60, 1),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Global {puntaje.porcentaje} % | {tokens} tokens | {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
