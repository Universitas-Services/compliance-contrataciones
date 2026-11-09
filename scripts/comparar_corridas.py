"""Compara corridas de un expediente pregunta por pregunta.

Uso: python -m scripts.comparar_corridas CARPETA_A CARPETA_B [CARPETA_C ...]

Cada carpeta tiene los `NN_TIPO.json` y el `puntaje.json` de scripts.correr_expediente.
Muestra, para cada par de corridas, cuántas preguntas cambian de estado y la diferencia
de puntaje global. Con dos corridas por modo, la variación dentro de un mismo modo es
el ruido del modelo; lo que la supere se debe al modo.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path


def estados(carpeta: Path) -> dict[tuple[str, str], str]:
    res: dict[tuple[str, str], str] = {}
    for f in sorted(carpeta.glob("[0-9][0-9]_*.json")):
        js = json.loads(f.read_text(encoding="utf-8"))
        doc = f.stem
        for h in js.get("hallazgos") or []:
            res[(doc, h["codigo_pregunta"])] = h.get("estado") or "no_consta"
        for c in js.get("conformes") or []:
            res[(doc, c["codigo_pregunta"])] = "si"
        for n in js.get("no_aplica") or []:
            res[(doc, n["codigo_pregunta"])] = "na"
    return res


def puntaje(carpeta: Path) -> dict:
    return json.loads((carpeta / "puntaje.json").read_text(encoding="utf-8"))


def main() -> None:
    carpetas = [Path(c) for c in sys.argv[1:]]
    datos = {c.name: (estados(c), puntaje(c)) for c in carpetas}
    for nombre, (est, pt) in datos.items():
        g = pt["global"]
        print(f"{nombre}: global {g['porcentaje']} % ({g['obtenidos']}/{g['maximo']}), "
              f"raíz {(pt.get('hallazgo_raiz') or {}).get('codigo_pregunta')}, "
              f"flag {pt.get('flag_nulidad_absoluta')}, {len(est)} preguntas")
    print()
    for a, b in itertools.combinations(datos, 2):
        ea, eb = datos[a][0], datos[b][0]
        claves = sorted(set(ea) | set(eb))
        cambios = [k for k in claves if ea.get(k) != eb.get(k)]
        dif = datos[b][1]["global"]["porcentaje"] - datos[a][1]["global"]["porcentaje"]
        print(f"{a} vs {b}: {len(cambios)} de {len(claves)} cambian "
              f"({100 * len(cambios) / max(len(claves), 1):.1f} %), global {dif:+.2f} puntos")
        for doc, codigo in cambios:
            print(f"   {doc:40} {codigo:12} {ea.get((doc, codigo))} -> {eb.get((doc, codigo))}")
        print()


if __name__ == "__main__":
    main()
