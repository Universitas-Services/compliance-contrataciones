"""Carga cuestionarios oficiales desde archivos .md por modalidad × tipo de documento."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.models.schemas import Modalidad, TipoDocumento

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CUESTIONARIOS_DIR = _REPO_ROOT / "cuestionarios"

# Códigos de rúbrica CA… (Apertura Única) y CD… (Contratación Directa).
# Variantes: **CAAUAP.1**¿ | CDAAP. 1¿ | **CDAIOC.2** ¿ | CDACTO.4 (BIENES) ¿
_ITEM_RE = re.compile(
    r"(?:\*\*)?"
    r"(?P<code>(?:CA|CD)[A-ZÁÉÍÓÚÑ]{2,}[A-Z0-9]*)"
    r"\.?\s*"
    r"(?P<num_in>\d+(?:\.\d+)?)?"
    r"\s*:?\s*"
    r"(?:\\?[.\-])*\s*"
    r"(?P<pre_close>[^*\n]*?)"
    r"(?:\*\*)?"
    r"\s*"
    r"(?:\\?[.\-])*\s*"
    r"(?P<num_out>\d+(?:\.\d+)?)?"
    r"\s*:?\s*"
    r"(?:\\?[.\-])*\s*"
    r"(?P<body>[^\n]*\?)",
    re.MULTILINE,
)

_CRIT_RE = re.compile(
    r"(?:RANGO\s*S?\s*DE\s+CRITICIDAD|SIRITICIDAD|CRITICIDAD|"
    r"Ponderaci[oó]n)\s*:\s*(?P<crit>[^\n*]+)",
    re.IGNORECASE,
)
_ACCION_RE = re.compile(
    r"ACCI[ÓO]N\s+LEGAL\s*:\s*(?P<val>.+?)"
    r"(?=\n\s*(?:\*\*)?ADVERTENCIA|\*\*\s*ADVERTENCIA|\n\s*\*\*[A-Z]|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_ADV_RE = re.compile(
    r"ADVERTENCIA(?:\s+(?:PARA\s+LA\s+|A\s+LA\s+)?GERENCIA)?\s*:\s*(?P<val>.+?)"
    r"(?=\n\s*(?:\*\*)?(?:CA|CD)[A-ZÁÉÍÓÚÑ]{2,}|\n\s*\*\*[A-ZÁÉÍÓÚÑ]{3,}|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_ART_RE = re.compile(
    r"(?:\*\*)?(?:Art[ií]culos?|Base\s+Legal|ART[ÍI]CULOS)\*?\*?\s*:?\s*"
    r"(?P<val>.+?)"
    r"(?=\n\s*(?:\*\*)?(?:RANGO|CRITICIDAD|Ponderaci[oó]n|Respuesta))",
    re.IGNORECASE | re.DOTALL,
)
# Formato detallado: texto íntegro de artículos bajo el bloque de fundamento.
_FUND_DETALLADO_RE = re.compile(
    r"FUNDAMENTO\s+LEGAL\s+(?:VIOLENTADO|APLICABLE)"
    r"(?:\s+EN\s+CASO\s+DE\s+NO)?\s*:?\s*"
    r"(?P<val>.+)",
    re.IGNORECASE | re.DOTALL,
)
_TIPO_PREF_RE = re.compile(
    r"^\(\s*(BIENES|OBRAS|SERVICIOS|URGENCIA)\s*\)\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ItemCuestionario:
    codigo: str
    texto: str
    fundamento_legal: str | None = None
    rango_criticidad: str | None = None
    accion_legal: str | None = None
    advertencia_gerencia: str | None = None


@dataclass(frozen=True)
class CuestionarioDocumento:
    modalidad: Modalidad
    tipo_documento: TipoDocumento
    path: Path
    markdown: str
    items: tuple[ItemCuestionario, ...]


def ruta_cuestionario(modalidad: Modalidad, tipo: TipoDocumento) -> Path:
    return _CUESTIONARIOS_DIR / modalidad.value / f"{tipo.value}.md"


def existe_cuestionario(modalidad: Modalidad, tipo: TipoDocumento) -> bool:
    return ruta_cuestionario(modalidad, tipo).is_file()


def _limpiar(txt: str) -> str:
    t = re.sub(r"\s+", " ", txt or "").strip()
    return t.strip("*").strip().rstrip("\\").strip()


def _extraer_pregunta(pre_close: str, body: str) -> str | None:
    """Une fragmentos del encabezado y normaliza la pregunta (añade ¿ si falta)."""
    raw = _limpiar(f"{pre_close or ''} {body or ''}")
    raw = re.sub(r"\*+", "", raw).strip(" .-:")
    raw = _limpiar(raw)
    if not raw or "?" not in raw:
        return None
    pref = ""
    pm = _TIPO_PREF_RE.match(raw)
    if pm:
        pref = f"({pm.group(1).upper()}) "
        raw = _limpiar(raw[pm.end() :])
    # Tomar desde el primer ¿ si existe (permite preámbulo antes)
    if "¿" in raw:
        raw = raw[raw.index("¿") :]
    else:
        raw = "¿" + raw
    # Cerrar en el último ? de la línea (por si hay ? intermedios raros)
    if not raw.endswith("?"):
        raw = raw[: raw.rindex("?") + 1]
    texto = f"{pref}{raw}" if pref else raw
    return texto if len(raw) > 2 else None


def _parse_items(markdown: str) -> list[ItemCuestionario]:
    matches = list(_ITEM_RE.finditer(markdown))
    items: list[ItemCuestionario] = []
    seen: set[str] = set()

    for i, m in enumerate(matches):
        code = _limpiar(m.group("code"))
        num = m.group("num_in") or m.group("num_out")
        body = m.group("body") or ""
        pre_close = m.group("pre_close") or ""

        # **CAAUA**. 1 ¿… → el número quedó en el body
        if not num:
            bm = re.match(
                r"(\d+(?:\.\d+)?)\s*(?:\\?[.\-])*\s*(.*)$",
                body.strip(),
            )
            if bm:
                num = bm.group(1)
                body = bm.group(2)
        if not num:
            continue

        codigo = f"{code}.{num}"
        pregunta = _extraer_pregunta(pre_close, body)
        if not pregunta:
            continue

        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        bloque = markdown[start:end]

        fund = None
        # Preferir bloque detallado (texto íntegro de artículos); si no, cita corta.
        fund_m = _FUND_DETALLADO_RE.search(bloque)
        if fund_m:
            fund = _limpiar(fund_m.group("val"))
        else:
            art_m = _ART_RE.search(bloque)
            if art_m:
                fund = _limpiar(art_m.group("val"))

        crit = None
        crit_m = _CRIT_RE.search(bloque)
        if crit_m:
            crit = _limpiar(crit_m.group("crit"))

        accion = None
        acc_m = _ACCION_RE.search(bloque)
        if acc_m:
            accion = _limpiar(acc_m.group("val"))

        adv = None
        adv_m = _ADV_RE.search(bloque)
        if adv_m:
            adv = _limpiar(adv_m.group("val"))

        item = ItemCuestionario(
            codigo=codigo,
            texto=pregunta,
            fundamento_legal=fund or None,
            rango_criticidad=crit or None,
            accion_legal=accion or None,
            advertencia_gerencia=adv or None,
        )
        if codigo in seen:
            # Duplicado: conservar el que traiga más metadatos (p. ej. CDACTO.19).
            prev_i = next(i for i, it in enumerate(items) if it.codigo == codigo)
            prev = items[prev_i]
            prev_score = sum(
                bool(x)
                for x in (
                    prev.fundamento_legal,
                    prev.rango_criticidad,
                    prev.accion_legal,
                )
            )
            new_score = sum(
                bool(x)
                for x in (
                    item.fundamento_legal,
                    item.rango_criticidad,
                    item.accion_legal,
                )
            )
            if new_score > prev_score:
                items[prev_i] = item
            continue
        seen.add(codigo)
        items.append(item)
    return items


@lru_cache(maxsize=128)
def cargar_cuestionario(
    modalidad: Modalidad,
    tipo: TipoDocumento,
) -> CuestionarioDocumento | None:
    path = ruta_cuestionario(modalidad, tipo)
    if not path.is_file():
        return None
    try:
        markdown = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("No se pudo leer cuestionario %s: %s", path, exc)
        return None

    items = _parse_items(markdown)
    if not items:
        logger.warning("Cuestionario sin ítems parseados: %s", path)

    return CuestionarioDocumento(
        modalidad=modalidad,
        tipo_documento=tipo,
        path=path,
        markdown=markdown,
        items=tuple(items),
    )


def textos_preguntas(cuest: CuestionarioDocumento) -> list[str]:
    return [it.texto for it in cuest.items]


def formato_cuestionario_compacto(cuest: CuestionarioDocumento) -> str:
    """Versión liviana para el LLM (sin acción/advertencia largas; esas viven en BD).

    Si el fundamento trae texto íntegro de artículos (formato detallado), se deja
    más margen para que el Analista cite sin inventar.
    """
    lineas: list[str] = [
        f"Cuestionario oficial — {cuest.tipo_documento.value} "
        f"({len(cuest.items)} ítems). Responde TODOS los códigos."
    ]
    for it in cuest.items:
        lineas.append(f"- {it.codigo}: {it.texto}")
        if it.rango_criticidad:
            lineas.append(f"  Criticidad: {it.rango_criticidad}")
        if it.fundamento_legal:
            fund = it.fundamento_legal
            # Cita corta vs. texto íntegro embebido en el MD
            limite = 1800 if len(fund) > 400 else 220
            if len(fund) > limite:
                fund = fund[:limite].rstrip() + "…"
            lineas.append(f"  Fundamento: {fund}")
    return "\n".join(lineas)
