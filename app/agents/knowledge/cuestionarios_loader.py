"""Carga cuestionarios oficiales desde archivos .md por modalidad × tipo de documento."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.agents.knowledge.storage import leer_texto
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

# `\**` antes de los dos puntos: tolera «**ACCIÓN LEGAL**:» (dos puntos fuera
# de la negrita), frecuente en los cuestionarios con fundamento detallado.
_CRIT_RE = re.compile(
    r"(?:RANGO\s*S?\s*DE\s+CRITICIDAD|SIRITICIDAD|CRITICIDAD|"
    r"Ponderaci[oó]n)\s*\**\s*:\s*(?P<crit>[^\n*]+)",
    re.IGNORECASE,
)
_ACCION_RE = re.compile(
    r"ACCI[ÓO]N\s+LEGAL\s*\**\s*:\s*(?P<val>.+?)"
    r"(?=\n\s*(?:\*\*)?ADVERTENCIA|\*\*\s*ADVERTENCIA|\n\s*\*\*[A-Z]|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_ADV_RE = re.compile(
    r"ADVERTENCIA(?:\s+(?:PARA\s+LA\s+|A\s+LA\s+)?GERENCIA)?\s*\**\s*:\s*(?P<val>.+?)"
    r"(?=\n\s*(?:\*\*)?(?:CA|CD)[A-ZÁÉÍÓÚÑ]{2,}|\n\s*\*\*[A-ZÁÉÍÓÚÑ]{3,}|\Z)",
    re.IGNORECASE | re.DOTALL,
)
# Etiqueta explícita de alcance por tipo de contrato:
# «**APLICA_A:** BIENES; SERVICIOS» (TODOS = los tres).
_APLICA_A_RE = re.compile(
    r"^[ \t]*(?:\*\*)?\s*APLICA[_ ]?A\s*\**\s*:\s*\**(?P<val>[^\n]*)\n?",
    re.IGNORECASE | re.MULTILINE,
)
_TIPOS_CONTRATO = frozenset({"BIENES", "OBRAS", "SERVICIOS"})
# Preámbulo condicional válido antes del «¿» (p. ej. «Si la contratación…,»).
_PREAMBULO_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{2,}(?:\W+[A-Za-zÁÉÍÓÚÑáéíóúñ]+){2,}")
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

# Tope de fundamento en prompt compacto (antes hasta 1800 → hinchaba lotes).
_FUNDAMENTO_COMPACTO_MAX = 280


@dataclass(frozen=True)
class ItemCuestionario:
    codigo: str
    texto: str
    fundamento_legal: str | None = None
    rango_criticidad: str | None = None
    accion_legal: str | None = None
    advertencia_gerencia: str | None = None
    # Tipos de contrato declarados con APLICA_A; None = sin etiqueta (heurística).
    aplica_a: frozenset[str] | None = None


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
    return cargar_cuestionario(modalidad, tipo) is not None


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
    # Tomar desde el primer ¿; si antes hay una condición en prosa
    # («Si la contratación…, ¿…?») se conserva, porque da sentido a la pregunta.
    if "¿" in raw:
        idx = raw.index("¿")
        preambulo = raw[:idx].strip(" .-:")
        raw = raw[idx:]
        if _PREAMBULO_RE.search(preambulo):
            raw = f"{preambulo} {raw}"
    else:
        raw = "¿" + raw
    # Cerrar en el último ? de la línea (por si hay ? intermedios raros)
    if not raw.endswith("?"):
        raw = raw[: raw.rindex("?") + 1]
    texto = f"{pref}{raw}" if pref else raw
    return texto if len(raw) > 2 else None


def _parse_aplica_a(valor: str, codigo: str) -> frozenset[str] | None:
    """«BIENES; SERVICIOS» → frozenset. TODOS = los tres. Inválido → None (heurística)."""
    tokens = [
        t.strip().upper()
        for t in re.split(r"[;,/]|\s+y\s+", re.sub(r"\*+", "", valor or ""))
        if t.strip()
    ]
    if not tokens:
        logger.warning("APLICA_A vacío en %s; se usa la heurística", codigo)
        return None
    tipos: set[str] = set()
    for t in tokens:
        if t in {"TODOS", "TODAS"}:
            return _TIPOS_CONTRATO
        t = {"BIEN": "BIENES", "OBRA": "OBRAS", "SERVICIO": "SERVICIOS"}.get(t, t)
        if t not in _TIPOS_CONTRATO:
            logger.warning(
                "APLICA_A inválido en %s: %r; se usa la heurística", codigo, valor
            )
            return None
        tipos.add(t)
    return frozenset(tipos)


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

        # APLICA_A se lee y se retira del bloque: así no se cuela en el
        # fundamento aunque la etiqueta esté debajo del «FUNDAMENTO LEGAL».
        aplica_a = None
        ap_m = _APLICA_A_RE.search(bloque)
        if ap_m:
            aplica_a = _parse_aplica_a(ap_m.group("val"), codigo)
            bloque = bloque[: ap_m.start()] + bloque[ap_m.end() :]

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
            aplica_a=aplica_a,
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
    blob = f"{modalidad.value}/{tipo.value}.md"
    markdown = leer_texto(local_path=path, gcs_blob=blob, kind="cuestionario")
    if markdown is None:
        return None

    items = _parse_items(markdown)
    if not items:
        logger.warning("Cuestionario sin ítems parseados: %s", blob)

    return CuestionarioDocumento(
        modalidad=modalidad,
        tipo_documento=tipo,
        path=path,
        markdown=markdown,
        items=tuple(items),
    )


def textos_preguntas(cuest: CuestionarioDocumento) -> list[str]:
    return [it.texto for it in cuest.items]


# Encabezados del fundamento detallado: «**Reglamento de la Ley …:**» y
# «**Artículo 6, numeral 2 de la Ley de Contrataciones Públicas:**».
_LEY_HEAD_RE = re.compile(
    r"\*\*\s*((?:Ley|Reglamento|Decreto|Normas|Constituci)[^*:]{3,200}?)\s*:\s*\*\*"
)
_ART_HEAD_RE = re.compile(
    r"Art[ií]culo\s+(?P<num>\d+)"
    r"(?P<det>(?:\s*,\s*(?:numeral(?:es)?|literal(?:es)?|ordinal(?:es)?)\s+[\w.]+"
    r"(?:\s*(?:,|y)\s*[\w.]+)*)?)"
    r"(?:\s+(?:de\s+la|del|de\s+las|de\s+los)\s+(?P<ley>[^:;.*]{5,160}?))?"
    r"\s*\**\s*:"
)
_LEYES_ABREV = (
    # Orden importa: «Normas de Control Interno … Contrataciones Públicas»
    # debe resolverse antes que la LCP.
    (("control interno",), "Normas SUNAI"),
    (("sunai",), "Normas SUNAI"),
    (("reglamento", "contrataciones"), "RLCP"),
    (("contrataciones públicas",), "LCP"),
    (("contencios",), "LOJCA"),
    (("guerra económica",), "Ley contra la Guerra Económica"),
    (("procedimientos administrativos",), "LOPA"),
    (("corrupción",), "LCC"),
    (("contraloría",), "LOCGR"),
    (("constitución",), "CRBV"),
    (("administración pública",), "LOAP"),
    (("precios justos",), "LOPJ"),
)


def _abreviar_ley(nombre: str) -> str:
    n = (nombre or "").lower()
    for claves, abrev in _LEYES_ABREV:
        if all(c in n for c in claves):
            return abrev
    return re.sub(r"\s+", " ", nombre or "").strip()[:60]


def articulos_de_fundamento(
    fundamento: str | None, *, max_chars: int = 700
) -> list[tuple[str, str]]:
    """[(«Art. 67 LCP», texto del artículo), …] del fundamento detallado.

    Sirve para dar al Jurídico el texto normativo que ya trae el cuestionario
    (la KB de legislación no tiene todas las leyes completas).
    """
    raw = str(fundamento or "")
    eventos: list[tuple[int, str, re.Match]] = []
    for m in _LEY_HEAD_RE.finditer(raw):
        eventos.append((m.start(), "ley", m))
    for m in _ART_HEAD_RE.finditer(raw):
        eventos.append((m.start(), "art", m))
    eventos.sort(key=lambda e: e[0])
    out: list[tuple[str, str]] = []
    ley_actual = ""
    for k, (pos, tipo, m) in enumerate(eventos):
        if tipo == "ley":
            ley_actual = m.group(1)
            continue
        fin = eventos[k + 1][0] if k + 1 < len(eventos) else len(raw)
        cuerpo = raw[m.end() : fin]
        cuerpo = re.sub(r"\*+|\\", "", cuerpo)
        cuerpo = re.sub(r"Normativa\s+(?:principal|complementaria)\s*:?", "", cuerpo, flags=re.I)
        cuerpo = re.sub(r"\s+", " ", cuerpo).strip(" :")
        if len(cuerpo) < 15:
            continue
        if len(cuerpo) > max_chars:
            cuerpo = cuerpo[:max_chars].rsplit(" ", 1)[0] + "…"
        det = re.sub(r"\s+", " ", m.group("det") or "").strip(" ,")
        det = re.sub(r"numeral(?:es)?", "num.", det)
        ref = m.group("num") + (f" {det}" if det else "")
        cita = f"Art. {ref} {_abreviar_ley(m.group('ley') or ley_actual)}".strip()
        out.append((cita, cuerpo))
    return out


def cita_corta_fundamento(fundamento: str | None, *, max_leyes: int = 4) -> str:
    """«Art. 107 RLCP; Arts. 18 y 81 LOPA» a partir del fundamento del cuestionario.

    Con el formato detallado toma los artículos de la «Normativa principal»
    (o de todo el bloque si no hay sección principal). Con el formato antiguo
    («67.1, 78.1 LCP; 17, 22 LCC») devuelve la cita tal cual. "" si no hay nada.
    """
    raw = str(fundamento or "")
    if not raw.strip():
        return ""
    eventos: list[tuple[int, str, str]] = []
    for m in _LEY_HEAD_RE.finditer(raw):
        eventos.append((m.start(), "ley", m.group(1)))
    for m in _ART_HEAD_RE.finditer(raw):
        det = re.sub(r"\s+", " ", m.group("det") or "").strip(" ,")
        det = re.sub(r"numeral(?:es)?", "num.", det)
        det = re.sub(r"literal(?:es)?", "lit.", det)
        ref = m.group("num") + (f" {det}" if det else "")
        eventos.append((m.start(), "art", f"{ref}\x00{m.group('ley') or ''}"))
    if not any(t == "art" for _, t, _ in eventos):
        t = re.sub(r"\*+|\\", "", raw)
        t = re.sub(r"\.\s+(?=\d)", ".", t)  # «166\. 1» (escape de Markdown) → «166.1»
        t = re.sub(r"\s+", " ", t).strip(" .:")
        t = re.sub(r"^(?:Art[ií]culos?|Arts?\.)\s*:?\s*", "", t, flags=re.IGNORECASE)
        if len(t) > 200:
            corte = t[:200].rfind(";")
            t = t[: corte if corte > 40 else 200].rstrip(" ,;")
        return f"Arts. {t}" if t[:1].isdigit() else t

    eventos.sort()
    comp = re.search(r"Normativa\s+complementaria", raw, re.IGNORECASE)
    limite = comp.start() if comp else len(raw)
    if not any(pos < limite and t == "art" for pos, t, _ in eventos):
        limite = len(raw)

    ley_actual = ""
    grupos: dict[str, list[str]] = {}
    for pos, tipo, val in eventos:
        if pos >= limite:
            break
        if tipo == "ley":
            ley_actual = val
            continue
        ref, ley = val.split("\x00")
        # Sin ley identificable se cita solo el artículo («Art. 123»).
        abrev = _abreviar_ley(ley or ley_actual)
        refs = grupos.setdefault(abrev, [])
        if ref not in refs:
            refs.append(ref)

    partes = []
    for abrev, refs in list(grupos.items())[:max_leyes]:
        if len(refs) == 1:
            cita = f"Art. {refs[0]}"
        else:
            cita = f"Arts. {', '.join(refs[:-1])} y {refs[-1]}"
        partes.append(f"{cita} {abrev}".strip())
    return "; ".join(partes)


def alcance_tipo_contrato(texto: str) -> frozenset[str] | None:
    """Tipos de contrato a los que aplica la pregunta.

    None = aplica a BIENES, OBRAS y SERVICIOS.
    frozenset({'BIENES'}) = solo ese tipo (el resto se excluye del pipeline).
    """
    raw = (texto or "").strip()
    if not raw:
        return None

    pref = _TIPO_PREF_RE.match(raw)
    if pref:
        g = pref.group(1).upper()
        if g in {"BIENES", "OBRAS", "SERVICIOS"}:
            return frozenset({g})

    # La heurística mira solo la pregunta: el preámbulo condicional
    # («En adquisiciones que superen 5.000 UCAU Bienes, …») no define el tipo.
    tl = raw[raw.index("¿") :].lower() if "¿" in raw else raw.lower()
    # Preguntas que aplican a obra O servicio (no bienes).
    if re.search(
        r"obra o se prestar[ií]a el servicio|obra o(?:\s+se)?\s+servicio|"
        r"ejecutar[ií]a la obra o|"
        r"\(servicios\s*/\s*obras\)|servicios\s*/\s*obras|"
        r"estructura de costos|an[aá]lisis de precios unitarios|\bapu\b",
        tl,
    ):
        return frozenset({"OBRAS", "SERVICIOS"})

    flags: set[str] = set()
    if re.search(
        r"\(bienes\)|adquisici[oó]n de bienes|bienes a adquirir|"
        r"caracter[ií]sticas de los bienes|entrega de los bienes|"
        r"entrega de bienes|para (la )?adquisici[oó]n de bienes|"
        r"forma de entrega de los bienes|plazos para la entrega de bienes|"
        r"condiciones para la entrega de bienes|"
        r"los bienes una vez recibidos|"
        r"especificaciones t[eé]cnicas de los bienes|"
        r"contrataci[oó]n de bienes|"
        r"cantidades del bien|"
        r"bienes de gran importancia|"
        r"20\.?000\s*ucau|art\.?\s*77\.1\b|"
        r"no podr[aá] ser menor de 7 d[ií]as h[aá]biles",
        tl,
    ):
        flags.add("BIENES")
    if re.search(
        r"\(servicios\)|prestaci[oó]n de servicios|servicios a prestar|"
        r"caracter[ií]sticas de los servicios|para (la )?prestaci[oó]n|"
        r"forma de prestaci[oó]n del servicio|"
        r"plazos para la prestaci[oó]n del servicio|"
        r"condiciones para la prestaci[oó]n del servicio|"
        r"los servicios una vez recibidos|"
        r"especificaciones t[eé]cnicas de los servicios|"
        r"contrataci[oó]n de servicios|"
        r"alcance del servicio|"
        r"30\.?000\s*ucau|art\.?\s*77\.2\b|"
        r"no podr[aá] ser menor de 9 d[ií]as h[aá]biles",
        tl,
    ):
        flags.add("SERVICIOS")
    if re.search(
        r"\(obras\)|ejecuci[oó]n de (la )?obra|obras a ejecutar|"
        r"caracter[ií]sticas de las obras|listas de cantidades|"
        r"forma de ejecuci[oó]n de las obras|"
        r"plazos para la ejecuci[oó]n de la obra|"
        r"condiciones para la ejecuci[oó]n de la obra|"
        r"las obras una vez recibidas|"
        r"obra a ejecutar|especificaciones t[eé]cnicas de la obra|"
        r"ejecuci[oó]n de una obra|"
        r"proyecto como la obra|proyecto y la (ejecuci[oó]n de la )?obra|"
        r"anteproyecto|cantidades de obra|"
        r"50\.?000\s*ucau|art\.?\s*77\.3\b|"
        r"no podr[aá] ser menor de 11 d[ií]as h[aá]biles",
        tl,
    ):
        flags.add("OBRAS")

    if len(flags) == 1:
        return frozenset(flags)
    if flags == {"OBRAS", "SERVICIOS"}:
        return frozenset(flags)
    # Si menciona varios tipos de forma excluyente (bienes vs servicios vs obras
    # en ítems hermanos), no mezclar: None = transversal.
    return None


def item_aplica_a_tipo(
    texto: str,
    tipo_contratacion: str,
    aplica_a: frozenset[str] | None = None,
) -> bool:
    """True si la pregunta debe evaluarse con el tipo de contrato de la sesión.

    La etiqueta APLICA_A del cuestionario manda; sin ella se infiere del texto.
    """
    tipo = (tipo_contratacion or "").strip().upper()
    if not tipo:
        return True
    alcance = aplica_a if aplica_a is not None else alcance_tipo_contrato(texto)
    if alcance is None:
        return True
    return tipo in alcance


def particionar_items_por_tipo(
    items: list[ItemCuestionario] | tuple[ItemCuestionario, ...],
    tipo_contratacion: str,
) -> tuple[list[ItemCuestionario], list[ItemCuestionario]]:
    """Separa ítems a evaluar con LLM vs auto-na por tipo de contrato."""
    aplicables: list[ItemCuestionario] = []
    na_auto: list[ItemCuestionario] = []
    for it in items:
        if item_aplica_a_tipo(it.texto, tipo_contratacion, it.aplica_a):
            aplicables.append(it)
        else:
            na_auto.append(it)
    if items:
        con_etiqueta = sum(it.aplica_a is not None for it in items)
        logger.info(
            "Partición por tipo %s: %d a evaluar, %d excluidos [%s] "
            "(APLICA_A en %d/%d ítems; resto por heurística)",
            tipo_contratacion or "N/D",
            len(aplicables),
            len(na_auto),
            ", ".join(it.codigo for it in na_auto),
            con_etiqueta,
            len(items),
        )
    return aplicables, na_auto


def formato_cuestionario_compacto(
    cuest: CuestionarioDocumento,
    *,
    items: list[ItemCuestionario] | tuple[ItemCuestionario, ...] | None = None,
) -> str:
    """Versión liviana para el LLM (sin acción/advertencia largas)."""
    usados = tuple(items) if items is not None else cuest.items
    lineas: list[str] = [
        f"Cuestionario oficial — {cuest.tipo_documento.value} "
        f"({len(usados)} ítems a evaluar). Responde TODOS los códigos listados."
    ]
    for it in usados:
        lineas.append(f"- {it.codigo}: {it.texto}")
        if it.rango_criticidad:
            lineas.append(f"  Criticidad: {it.rango_criticidad}")
        if it.fundamento_legal:
            fund = it.fundamento_legal.strip()
            if len(fund) > _FUNDAMENTO_COMPACTO_MAX:
                fund = fund[:_FUNDAMENTO_COMPACTO_MAX].rstrip() + "…"
            lineas.append(f"  Fundamento: {fund}")
    return "\n".join(lineas)
