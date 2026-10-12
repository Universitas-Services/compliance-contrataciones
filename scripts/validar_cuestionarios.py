"""Valida cuestionarios .md antes de copiarlos al repo o subirlos a GCS (sin LLM).

Uso:
    python -m scripts.validar_cuestionarios [carpeta_o_archivo ...] [--exigir-aplica-a]

Por defecto revisa `cuestionarios/`. Reporta por archivo: preguntas sin
criticidad / acción legal / advertencia / fundamento, sin APLICA_A, códigos
duplicados, saltos de numeración y encabezados que el parser no reconoce.
Sale con código 1 si hay errores (faltantes o duplicados).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from app.agents.knowledge.cuestionarios_loader import _parse_items

_REPO_ROOT = Path(__file__).resolve().parents[1]
# Encabezado de pregunta en bruto: «**CAAUAI** 2.-», «**CAAUC.** 39», «CDAAP. 1».
_HEAD_RE = re.compile(
    r"^\s*(?:\*\*)?\s*((?:CA|CD)[A-ZÁÉÍÓÚÑ]{2,}[A-Z0-9]*)\s*(?:\*\*)?\s*\.?\s*"
    r"(?:\*\*)?\s*(\d+(?:\.\d+)?)",
    re.MULTILINE,
)
_CAMPOS = {
    "criticidad": "rango_criticidad",
    "acción legal": "accion_legal",
    "advertencia": "advertencia_gerencia",
    "fundamento": "fundamento_legal",
}


def _orden(codigo: str) -> tuple:
    return tuple(int(p) for p in codigo.split(".")[1:] if p.isdigit())


def _saltos(codigos: list[str]) -> list[str]:
    """Números enteros ausentes entre el primero y el último de cada prefijo."""
    por_prefijo: dict[str, set[int]] = {}
    for c in codigos:
        pref, _, resto = c.partition(".")
        num = resto.split(".")[0]
        if num.isdigit():
            por_prefijo.setdefault(pref, set()).add(int(num))
    faltan = []
    for pref, nums in por_prefijo.items():
        faltan += [f"{pref}.{n}" for n in range(min(nums), max(nums) + 1) if n not in nums]
    return faltan


def validar_archivo(path: Path, exigir_aplica_a: bool) -> tuple[int, list[str]]:
    md = path.read_text(encoding="utf-8")
    items = _parse_items(md)
    errores: list[str] = []
    avisos: list[str] = []

    for etiqueta, attr in _CAMPOS.items():
        sin = [it.codigo for it in items if not getattr(it, attr)]
        if sin:
            errores.append(f"sin {etiqueta} ({len(sin)}): {', '.join(sin)}")

    sin_aplica = [it.codigo for it in items if it.aplica_a is None]
    if sin_aplica and len(sin_aplica) < len(items):
        (errores if exigir_aplica_a else avisos).append(
            f"sin APLICA_A ({len(sin_aplica)}): {', '.join(sin_aplica)}"
        )
    elif sin_aplica and exigir_aplica_a:
        errores.append("ninguna pregunta tiene APLICA_A")

    crudos = [f"{a}.{b}" for a, b in _HEAD_RE.findall(md)]
    dup = sorted((c for c, n in Counter(crudos).items() if n > 1), key=_orden)
    if dup:
        errores.append(f"códigos duplicados: {', '.join(dup)}")
    no_parseados = sorted(set(crudos) - {it.codigo for it in items}, key=_orden)
    if no_parseados:
        avisos.append(f"encabezados sin pregunta reconocible: {', '.join(no_parseados)}")
    saltos = _saltos([it.codigo for it in items])
    if saltos:
        avisos.append(f"saltos de numeración: {', '.join(saltos)}")
    if not items:
        errores.append("no se reconoció ninguna pregunta")

    lineas = [f"  ERROR  {e}" for e in errores] + [f"  aviso  {a}" for a in avisos]
    return len(items), (["  OK"] if not lineas else lineas), bool(errores)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rutas", nargs="*", type=Path, default=[_REPO_ROOT / "cuestionarios"])
    ap.add_argument("--exigir-aplica-a", action="store_true")
    args = ap.parse_args(argv)

    archivos: list[Path] = []
    for r in args.rutas:
        archivos += sorted(r.rglob("*.md")) if r.is_dir() else [r]
    archivos = [a for a in archivos if a.name.upper() != "README.MD"]

    con_error = 0
    total = 0
    for a in archivos:
        n, lineas, err = validar_archivo(a, args.exigir_aplica_a)
        total += n
        con_error += err
        print(f"{a.parent.name}/{a.name} — {n} preguntas")
        print("\n".join(lineas))
    print(f"\n{len(archivos)} archivos, {total} preguntas, {con_error} con errores.")
    return 1 if con_error else 0


if __name__ == "__main__":
    sys.exit(main())
