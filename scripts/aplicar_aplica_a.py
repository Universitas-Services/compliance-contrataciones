"""Inserta/actualiza la etiqueta **APLICA_A:** en los cuestionarios desde el Excel de revisión.

Uso:
    python -m scripts.aplicar_aplica_a <excel.xlsx> <carpeta_modalidad> [--dry-run]

El Excel tiene una hoja por documento (nombre = archivo .md sin extensión) con
las columnas «Código», «APLICA_A propuesto», «Validación Nancy» y
«Corrección Nancy». Se usa la corrección cuando la validación es CAMBIAR; si
no, la propuesta. La línea se coloca tras «Respuesta: …» (o tras la pregunta)
y reemplaza una etiqueta APLICA_A previa.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

from app.agents.knowledge.cuestionarios_loader import _ITEM_RE, _limpiar

_VALIDOS = {"TODOS", "BIENES", "SERVICIOS", "OBRAS"}
_RESPUESTA_RE = re.compile(r"^[ \t]*\**\s*Respuestas?\b[^\n]*\n?", re.IGNORECASE | re.MULTILINE)
_APLICA_RE = re.compile(r"^[ \t]*\**\s*APLICA[_ ]?A\b[^\n]*\n?", re.IGNORECASE | re.MULTILINE)


def leer_etiquetas(excel: Path) -> dict[str, dict[str, str]]:
    """{documento: {codigo: valor}} con la decisión final de cada fila.

    El documento sale de la columna «Documento» (Excel trunca el nombre de
    la hoja a 31 caracteres).
    """
    wb = load_workbook(excel, read_only=True, data_only=True)
    out: dict[str, dict[str, str]] = {}
    for ws in wb.worksheets:
        filas = ws.iter_rows(values_only=True)
        cab = next(filas, None)
        if not cab or "Código" not in cab:
            continue
        col = {n: i for i, n in enumerate(cab)}
        for f in filas:
            codigo = f[col["Código"]]
            if not codigo:
                continue
            valor = f[col["APLICA_A propuesto"]]
            if str(f[col["Validación Nancy"]] or "").strip().upper() == "CAMBIAR":
                valor = f[col["Corrección Nancy"]] or valor
            valor = "; ".join(t.strip().upper() for t in str(valor).split(";") if t.strip())
            if not set(valor.split("; ")) <= _VALIDOS:
                raise ValueError(f"{ws.title} {codigo}: valor APLICA_A inválido {valor!r}")
            doc = str(f[col["Documento"]] or ws.title).strip()
            out.setdefault(doc, {})[str(codigo).strip()] = valor
    return out


def _codigo(m: re.Match) -> str | None:
    """Mismo cálculo de código que `_parse_items`."""
    num = m.group("num_in") or m.group("num_out")
    if not num:
        bm = re.match(r"(\d+(?:\.\d+)?)", (m.group("body") or "").strip())
        num = bm.group(1) if bm else None
    return f"{_limpiar(m.group('code'))}.{num}" if num else None


def etiquetar(markdown: str, etiquetas: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """Devuelve (markdown nuevo, códigos etiquetados, códigos sin etiqueta en el Excel)."""
    matches = list(_ITEM_RE.finditer(markdown))
    partes: list[str] = []
    hechos: list[str] = []
    sin_excel: list[str] = []
    cursor = 0
    vistos: set[str] = set()
    for i, m in enumerate(matches):
        codigo = _codigo(m)
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        if not codigo or codigo in vistos:
            continue
        vistos.add(codigo)
        valor = etiquetas.get(codigo)
        if valor is None:
            sin_excel.append(codigo)
            continue
        bloque = markdown[m.end() : fin]
        bloque = _APLICA_RE.sub("", bloque, count=1)
        linea = f"**APLICA_A:** {valor}  \n"
        r = _RESPUESTA_RE.search(bloque)
        if r:
            sep = "" if r.group(0).endswith("\n") else "\n"
            bloque = bloque[: r.end()] + sep + linea + bloque[r.end() :]
        else:
            nl = bloque.find("\n")
            bloque = linea if nl < 0 else bloque[: nl + 1] + linea + bloque[nl + 1 :]
        partes.append(markdown[cursor : m.end()])
        partes.append(bloque)
        cursor = fin
        hechos.append(codigo)
    partes.append(markdown[cursor:])
    return "".join(partes), hechos, sin_excel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("excel", type=Path)
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    por_hoja = leer_etiquetas(args.excel)
    problemas = 0
    for hoja, etiquetas in por_hoja.items():
        md_path = args.carpeta / f"{hoja}.md"
        if not md_path.exists():
            print(f"{hoja}: no existe {md_path}")
            problemas += 1
            continue
        md = md_path.read_text(encoding="utf-8")
        nuevo, hechos, sin_excel = etiquetar(md, etiquetas)
        sobran = sorted(set(etiquetas) - set(hechos))
        print(f"{hoja}: {len(hechos)} etiquetadas")
        if sin_excel:
            print(f"  sin fila en el Excel: {', '.join(sin_excel)}")
        if sobran:
            print(f"  en el Excel pero no en el .md: {', '.join(sobran)}")
        problemas += bool(sin_excel)
        if not args.dry_run and nuevo != md:
            md_path.write_text(nuevo, encoding="utf-8", newline="")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
