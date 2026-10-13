"""Extractos relevantes por lote de rúbrica para documentos largos.

Los documentos largos (pliegos, informes) no caben enteros en cada lote: se
parten en secciones y a cada lote se le envían solo las que mejor responden
a sus preguntas (búsqueda léxica, sin embeddings). Los documentos cortos se
envían completos, como siempre.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

# Por debajo de este tamaño el documento va completo en cada lote.
UMBRAL_DOC_LARGO = 15_000
_TAM_SECCION = 1_500
_TOPE_LOTE = 20_000
_TOP_POR_PREGUNTA = 3
_INICIO_CHARS = 2_500
_FINAL_CHARS = 1_200

_STOP = frozenset(
    """a al ante bajo con contra de del desde durante e el en entre esta este
    fue fueron ha han hasta la las le lo los mas o para pero por que se segun
    si sin sobre su sus un una uno unos y ya como cual cuales cuando donde
    dicho dicha dichos dichas cada caso todo toda todos todas otro otra
    especifico especifica establecio indico incluyo incluye documento
    conforme ser sido mediante respectivo respectiva aplicable normativa""".split()
)
# Preguntas de plazos/fechas: se añaden las secciones con fechas o tablas.
_PLAZOS_RE = re.compile(r"plazo|lapso|fecha|cronograma|d[ií]as?\s+h[aá]biles|vigencia", re.I)
_FECHA_RE = re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b")
# Cortes naturales: títulos Markdown, cláusulas y numerales al inicio de línea.
_CORTE_RE = re.compile(
    r"\n(?=(?:##\s|\[tabla|\[encabezado|\[pie|CL[AÁ]USULA|CAP[IÍ]TULO|ART[IÍ]CULO|"
    r"Art[ií]culo\s+\d|(?:PRIMER|SEGUND|TERCER|CUART|QUINT|SEXT|S[EÉ]PTIM|OCTAV|"
    r"NOVEN|D[EÉ]CIM)[OA]\b|\d{1,2}(?:\.\d{1,2})*\s*[.\-)]\s))"
)


@dataclass(frozen=True)
class Seccion:
    idx: int
    texto: str
    fijo: bool  # encabezados/pies: van siempre


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _terminos(t: str) -> list[str]:
    """Raíces de 5 letras de las palabras con contenido."""
    out = []
    for w in re.findall(r"[a-zñ0-9]+", _normalizar(t)):
        if len(w) < 3 or w in _STOP:
            continue
        out.append(w[:5] if not w.isdigit() else w)
    return out


def partir_en_secciones(texto: str) -> list[Seccion]:
    """Secciones de ~1.500 caracteres respetando títulos, cláusulas y tablas."""
    piezas = [p for p in _CORTE_RE.split(texto or "") if p.strip()]
    secciones: list[Seccion] = []
    buf = ""

    def _cerrar(b: str) -> None:
        b = b.strip()
        if b:
            fijo = b.startswith("[encabezado") or b.startswith("[pie")
            secciones.append(Seccion(len(secciones) + 1, b, fijo))

    for p in piezas:
        es_fijo = p.lstrip().startswith(("[encabezado", "[pie"))
        if es_fijo:
            _cerrar(buf)
            buf = ""
            _cerrar(p)
            continue
        if buf and len(buf) + len(p) > _TAM_SECCION:
            _cerrar(buf)
            buf = ""
        buf += ("\n" if buf else "") + p.strip("\n")
        while len(buf) > 2 * _TAM_SECCION:
            corte = buf.rfind("\n", 0, _TAM_SECCION) or _TAM_SECCION
            corte = corte if corte > _TAM_SECCION // 3 else _TAM_SECCION
            _cerrar(buf[:corte])
            buf = buf[corte:]
    _cerrar(buf)
    return secciones


class _Indice:
    """BM25 mínimo sobre las secciones."""

    def __init__(self, secciones: list[Seccion]) -> None:
        self.secciones = secciones
        self.tf = [Counter(_terminos(s.texto)) for s in secciones]
        self.largo = [sum(c.values()) or 1 for c in self.tf]
        self.prom = sum(self.largo) / max(1, len(self.largo))
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(secciones)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def puntuar(self, consulta: str) -> list[tuple[float, int]]:
        q = set(_terminos(consulta))
        out = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf.get(t, 0) * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self.largo[i] / self.prom))
            out.append((s, i))
        return sorted(out, reverse=True)


@dataclass
class ExtractorLotes:
    """Prepara el texto que recibe cada lote de rúbrica."""

    texto: str

    def __post_init__(self) -> None:
        self.largo = len(self.texto or "") > UMBRAL_DOC_LARGO
        if self.largo:
            self.secciones = partir_en_secciones(self.texto)
            self.indice = _Indice(self.secciones)

    def texto_para_lote(self, preguntas: list[str]) -> str:
        """Documento completo (corto) o extractos relevantes (largo)."""
        if not self.largo:
            return self.texto
        elegidas: set[int] = {i for i, s in enumerate(self.secciones) if s.fijo}
        # Inicio del documento: título, partes, objeto.
        acum = 0
        for i, s in enumerate(self.secciones):
            if s.fijo:
                continue
            elegidas.add(i)
            acum += len(s.texto)
            if acum >= _INICIO_CHARS:
                break
        # Final del documento: firmas, fecha y lugar de emisión.
        acum = 0
        for i in range(len(self.secciones) - 1, -1, -1):
            if self.secciones[i].fijo:
                continue
            elegidas.add(i)
            acum += len(self.secciones[i].texto)
            if acum >= _FINAL_CHARS:
                break
        candidatos: list[tuple[float, int]] = []
        for q in preguntas:
            ranking = [r for r in self.indice.puntuar(q) if r[0] > 0]
            if not ranking:
                continue
            candidatos.extend(ranking[:_TOP_POR_PREGUNTA])
            if _PLAZOS_RE.search(q):
                for score, i in ranking[_TOP_POR_PREGUNTA:]:
                    if _FECHA_RE.search(self.secciones[i].texto) or self.secciones[i].texto.startswith("[tabla"):
                        candidatos.append((score, i))
                        break
        # Mejores primero hasta el tope de caracteres; luego en orden original.
        total = sum(len(self.secciones[i].texto) for i in elegidas)
        for score, i in sorted(candidatos, reverse=True):
            if i in elegidas:
                continue
            largo = len(self.secciones[i].texto)
            if total + largo > _TOPE_LOTE:
                continue
            elegidas.add(i)
            total += largo
        partes = []
        anterior = None
        for i in sorted(elegidas):
            if anterior is not None and i != anterior + 1:
                partes.append("[…]")
            s = self.secciones[i]
            partes.append(f"[S{s.idx}] {s.texto}")
            anterior = i
        return (
            f"(EXTRACTOS del documento: {len(elegidas)} de {len(self.secciones)} "
            f"secciones, seleccionadas para estas preguntas)\n" + "\n".join(partes)
        )


def texto_identidad(texto: str, *, cabeza: int = 12_000, cola: int = 3_000) -> str:
    """Inicio + final del documento para la pasada de identidad/hechos clave."""
    t = texto or ""
    if len(t) <= cabeza + cola + 500:
        return t
    fijos = "\n".join(
        s.texto for s in partir_en_secciones(t) if s.fijo
    )
    cuerpo = t[:cabeza] + "\n\n[…documento recortado para identificación…]\n\n" + t[-cola:]
    return (fijos + "\n\n" + cuerpo) if fijos and fijos[:200] not in cuerpo else cuerpo
