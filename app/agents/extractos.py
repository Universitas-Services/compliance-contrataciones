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
_TAM_SECCION = 1000
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


_REF_SECCION_RE = re.compile(r"\[S(\d+)\](?:\s*[-–]\s*\[S(\d+)\])?")
# Línea que funciona como título: capítulo, cláusula, numeral romano, o una
# línea corta en mayúsculas. Los numerales arábigos solo si son cortos
# («1. Condiciones generales», no «1.8. Cuando el participante desee…»).
_TITULO_FUERTE_RE = re.compile(
    r"^(?:CAP[IÍ]TULO|CL[AÁ]USULA|T[IÍ]TULO|ANEXO|SECCI[OÓ]N|[IVXL]+\s*[.\-)]\s)"
)
_NUMERAL_RE = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2})*|[A-Z])\s*[.\-)]\s")
_MAX_ETIQUETA = 70


def _limpiar_linea(linea: str) -> str:
    t = re.sub(r"[*#_`]+", "", linea).split("\t")[0]
    return re.sub(r"\s+", " ", t).strip(" :.-")


def _es_titulo(t: str) -> bool:
    letras = [c for c in t if c.isalpha()]
    if len(letras) < 6 or len(t) > 90:
        return False
    if _TITULO_FUERTE_RE.match(t):
        return True
    if _NUMERAL_RE.match(t):
        return len(t) <= 50
    mayus = sum(c.isupper() for c in letras) / len(letras)
    return mayus > 0.8 and len(t.split()) >= 2


def _titulos(texto: str) -> list[tuple[int, str]]:
    """(n.º de línea, título) de las líneas que funcionan como título."""
    out = []
    for i, linea in enumerate(texto.splitlines()):
        t = _limpiar_linea(linea)
        if t and _es_titulo(t):
            out.append((i, t))
    return out


def etiquetas_secciones(secciones: list[Seccion]) -> dict[int, str]:
    """Referencia legible de cada sección para el usuario.

    - Tabla: «Tabla CRONOGRAMA DE EJECUCIÓN» (su primera celda).
    - Sección que empieza con un título: ese título.
    - Si no: el último título anterior, marcado «(cont.)».
    Se ignoran los membretes que se repiten en muchas páginas.
    """
    por_seccion = {s.idx: _titulos(s.texto) for s in secciones if not s.fijo}
    frecuencia = Counter(t for ts in por_seccion.values() for _, t in ts)
    membretes = {t for t, n in frecuencia.items() if n >= 3}
    etiquetas: dict[int, str] = {}
    vigente: str | None = None
    for s in secciones:
        if s.fijo:
            etiquetas[s.idx] = "Encabezado o pie de página"
            continue
        titulos = [(i, t) for i, t in por_seccion[s.idx] if t not in membretes]
        lineas = s.texto.lstrip().splitlines()
        if lineas and lineas[0].startswith("[tabla"):
            celda = _limpiar_linea(lineas[1]) if len(lineas) > 1 else ""
            base = f"Tabla {celda}" if celda else "Tabla"
        elif titulos and titulos[0][0] <= 1:
            base = titulos[0][1]
        elif vigente:
            base = f"{vigente} (cont.)"
        else:
            base = _limpiar_linea(s.texto.strip().splitlines()[0])
        if titulos:
            vigente = titulos[-1][1]
        if len(base) > _MAX_ETIQUETA:
            base = base[:_MAX_ETIQUETA].rsplit(" ", 1)[0] + "…"
        etiquetas[s.idx] = base
    return etiquetas


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
            # El bloque de encabezado/pie termina en la primera línea en blanco;
            # lo que sigue es cuerpo del documento y se trata como tal.
            cab, sep, resto = p.strip("\n").partition("\n\n")
            _cerrar(cab)
            if not resto.strip():
                continue
            p = resto
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
        self.n = n
        self.df = df
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def puntuar(self, consulta: str) -> list[tuple[float, int]]:
        q = set(_terminos(consulta))
        # Términos presentes en casi todo el documento («pliego», «condiciones»,
        # «ofertas») no distinguen secciones: se descartan si quedan otros.
        distintivos = {t for t in q if self.df.get(t, 0) <= 0.3 * self.n}
        if distintivos:
            q = distintivos
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
        self.etiquetas: dict[int, str] = {}
        if self.largo:
            self.secciones = partir_en_secciones(self.texto)
            self.indice = _Indice(self.secciones)
            self.etiquetas = etiquetas_secciones(self.secciones)

    def referencias_legibles(self, texto: str | None) -> str | None:
        """Cambia «[S127]» o «[S18]-[S78]» por el título de esas secciones.

        Los códigos [Sx] solo existen para el modelo; el usuario y el equipo
        legal necesitan una referencia que puedan ubicar en el documento.
        """
        if not texto or not self.etiquetas:
            return texto

        def nombre(n: str) -> str:
            return f"«{self.etiquetas.get(int(n), f'sección {n}')}»"

        def sub(m: re.Match) -> str:
            if m.group(2):
                a, b = nombre(m.group(1)), nombre(m.group(2))
                return a if a == b else f"de {a} a {b}"
            return nombre(m.group(1))

        out = _REF_SECCION_RE.sub(sub, texto)
        # Fusiona repeticiones seguidas de la misma referencia («A», «A»).
        out = re.sub(r"(«[^»]+»)(?:,\s*\1)+", r"\1", out)
        return re.sub(r"\b[Ss]ecci[oó]n\s+(«)", r"\1", out)

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
        # Candidatas por pregunta, en orden de relevancia.
        por_pregunta: list[list[int]] = []
        for q in preguntas:
            ranking = [i for s, i in self.indice.puntuar(q) if s > 0]
            cands = ranking[:_TOP_POR_PREGUNTA]
            if _PLAZOS_RE.search(q):
                extra = next(
                    (
                        i
                        for i in ranking[_TOP_POR_PREGUNTA:]
                        if _FECHA_RE.search(self.secciones[i].texto)
                        or self.secciones[i].texto.startswith("[tabla")
                    ),
                    None,
                )
                if extra is not None:
                    cands.append(extra)
            por_pregunta.append(cands)
        # Reparto por rondas: primero la mejor sección de CADA pregunta, luego
        # la segunda… así ninguna pregunta se queda sin su sección principal.
        total = sum(len(self.secciones[i].texto) for i in elegidas)
        for ronda in range(_TOP_POR_PREGUNTA + 1):
            for cands in por_pregunta:
                if ronda >= len(cands) or cands[ronda] in elegidas:
                    continue
                i = cands[ronda]
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
