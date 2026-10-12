"""Calendario de días hábiles (Venezuela) para las fechas citadas en un documento.

Los LLM cuentan mal días hábiles (días de la semana, feriados). Este módulo
detecta las fechas del documento y genera un calendario numerado que se
inyecta en el prompt de la rúbrica: el modelo lee el conteo, no lo calcula.

Feriados extra (decretos, regionales): variable FERIADOS_EXTRA con fechas
ISO separadas por coma, p. ej. «2026-03-19,2026-09-08».
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")

_FECHA_NUM_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
# «27 de abril de 2026», «27 días de abril del 2026», «27 días del mes de abril de 2026»
_FECHA_TXT_RE = re.compile(
    r"\b(\d{1,2})\s+(?:d[ií]as?\s+)?del?\s+(?:mes\s+de\s+)?("
    + "|".join(_MESES)
    + r")\s+del?\s+(?:a[ñn]o\s+)?(\d{4})\b",
    re.IGNORECASE,
)

# Fechas a menos de este margen se agrupan en un mismo tramo de calendario.
_MARGEN_TRAMO = 21
_MAX_DIAS_TRAMO = 75


def _pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo)."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def feriados_nacionales(anio: int) -> dict[date, str]:
    """Feriados nacionales de Venezuela (fijos + Carnaval y Semana Santa)."""
    p = _pascua(anio)
    out = {
        date(anio, 1, 1): "Año Nuevo",
        p - timedelta(days=48): "Carnaval",
        p - timedelta(days=47): "Carnaval",
        p - timedelta(days=3): "Jueves Santo",
        p - timedelta(days=2): "Viernes Santo",
        date(anio, 4, 19): "Declaración de la Independencia",
        date(anio, 5, 1): "Día del Trabajador",
        date(anio, 6, 24): "Batalla de Carabobo",
        date(anio, 7, 5): "Día de la Independencia",
        date(anio, 7, 24): "Natalicio del Libertador",
        date(anio, 10, 12): "Día de la Resistencia Indígena",
        date(anio, 12, 24): "Víspera de Navidad",
        date(anio, 12, 25): "Navidad",
        date(anio, 12, 31): "Fin de año",
    }
    for raw in (os.getenv("FERIADOS_EXTRA") or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            continue
        if d.year == anio:
            out.setdefault(d, "Feriado decretado")
    return out


def fechas_en_texto(texto: str) -> list[date]:
    """Fechas válidas (1990–2100) citadas en el texto, sin repetir y ordenadas."""
    encontradas: set[date] = set()
    for d, m, a in _FECHA_NUM_RE.findall(texto or ""):
        try:
            encontradas.add(date(int(a), int(m), int(d)))
        except ValueError:
            continue
    for d, mes, a in _FECHA_TXT_RE.findall(texto or ""):
        try:
            encontradas.add(date(int(a), _MESES[mes.lower()], int(d)))
        except (ValueError, KeyError):
            continue
    return sorted(f for f in encontradas if 1990 <= f.year <= 2100)


def _tramos(fechas: list[date]) -> list[tuple[date, date]]:
    tramos: list[list[date]] = []
    for f in fechas:
        if tramos and (f - tramos[-1][-1]).days <= _MARGEN_TRAMO:
            tramos[-1].append(f)
        else:
            tramos.append([f])
    out = []
    for t in tramos:
        ini, fin = t[0], t[-1]
        if (fin - ini).days > _MAX_DIAS_TRAMO:
            fin = ini + timedelta(days=_MAX_DIAS_TRAMO)
        out.append((ini, fin))
    return out


def bloque_calendario(texto: str) -> str:
    """Bloque para el prompt; "" si el documento no cita fechas."""
    fechas = fechas_en_texto(texto)
    if not fechas:
        return ""
    citadas = set(fechas)
    lineas = [
        "CALENDARIO DEL DOCUMENTO (calculado por el sistema; Venezuela). "
        "H# = número de día hábil dentro del tramo; '*' = fecha citada en el "
        "documento. Días hábiles ENTRE dos fechas (sin contar ninguna de las "
        "dos) = H# de la final − H# de la inicial − 1 (si la inicial no es "
        "hábil, usa el H# del último hábil anterior).",
    ]
    for ini, fin in _tramos(fechas):
        feriados: dict[date, str] = {}
        for anio in range(ini.year, fin.year + 1):
            feriados.update(feriados_nacionales(anio))
        n = 0
        dias: list[str] = []
        d = ini
        while d <= fin:
            marca = "*" if d in citadas else ""
            etiqueta = f"{_DIAS[d.weekday()]} {d:%d/%m/%Y}{marca}"
            if d in feriados:
                dias.append(f"{etiqueta} FERIADO ({feriados[d]})")
            elif d.weekday() >= 5:
                dias.append(f"{etiqueta} no hábil")
            else:
                n += 1
                dias.append(f"{etiqueta} H{n}")
            d += timedelta(days=1)
        lineas.append(f"Tramo {ini:%d/%m/%Y}–{fin:%d/%m/%Y}: " + " · ".join(dias))
    return "\n".join(lineas)
