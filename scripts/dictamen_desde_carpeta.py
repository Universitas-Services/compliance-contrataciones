"""Emite el dictamen a partir de los JSON de una carpeta, como lo haría Nest.

Uso: python -m scripts.dictamen_desde_carpeta MANIFIESTO CARPETA SALIDA.md

Usa los `NN_TIPO.json` de scripts.correr_expediente y la configuración de Cloud Run.
Gasta tokens (una llamada larga del Jurídico).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import scripts.correr_expediente  # noqa: F401  (configuración de Cloud Run)
from app.agents.orchestrator import dictamen_desde_documentos
from app.models.schemas import Modalidad, TipoContratacion


def main() -> None:
    manifiesto = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    carpeta, salida = Path(sys.argv[2]), Path(sys.argv[3])
    documentos = [
        json.loads(f.read_text(encoding="utf-8"))
        for f in sorted(carpeta.glob("[0-9][0-9]_*.json"))
    ]
    t0 = time.time()
    dictamen = dictamen_desde_documentos(
        nomenclatura=manifiesto["nomenclatura"],
        modalidad=Modalidad(manifiesto["modalidad"]),
        tipo_contratacion=TipoContratacion(manifiesto["tipo_contratacion"]),
        documentos=documentos,
        mensaje="Emite el informe ejecutivo de compliance según el formato oficial (4 secciones).",
    )
    salida.write_text(dictamen.markdown, encoding="utf-8")
    salida.with_suffix(".coherencia.json").write_text(
        json.dumps(dictamen.coherencia, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{dictamen.alcance.value} | {len(dictamen.markdown)} caracteres | "
          f"{len(dictamen.coherencia)} contradicciones | {time.time() - t0:.0f}s -> {salida}")
    for c in dictamen.coherencia:
        print(f"  [{c['gravedad']}] {c['dato']}: {c['documento_a']}={c['valor_a']} | "
              f"{c['documento_b']}={c['valor_b']}")


if __name__ == "__main__":
    main()
