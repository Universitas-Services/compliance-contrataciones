"""Puntaje del expediente calculado por código (no por el LLM).

Modelo oficial del dictamen (formato de Mariana):
- Peso por criticidad: Crítica 5, Relevante 3, Ordinaria 1.
- Máximo de un documento = suma de los pesos de sus preguntas evaluadas.
- Umbrales: ≥95 Sobresaliente; 90–94,99 Aceptable; 85–89,99 Hallazgos
  Significativos; <84,99 Hallazgos Críticos.
- Flag de Riesgo de Nulidad Absoluta: al menos un «no» en una pregunta crítica.
- Hallazgo raíz: el primer «no» crítico en la fase más temprana del expediente.

Regla v1 (configurable mientras legal no diga otra cosa): «si» suma su peso;
«parcial» y «no_consta» suman 0 (PUNTAJE_VALOR_PARCIAL); N/A no entra al máximo.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PESO_CRITICO = 5
_PESOS_NOMBRE = {"CRIT": 5, "RELEV": 3, "ORDIN": 1}
_DIGITO_RE = re.compile(r"\b([135])\b")
# Fracción del peso que suma un «parcial» (0 = regla literal del formato oficial).
VALOR_PARCIAL = float(os.getenv("PUNTAJE_VALOR_PARCIAL", "0"))

UMBRALES: tuple[tuple[float, str], ...] = (
    (95.0, "Cumplimiento Sobresaliente"),
    (90.0, "Cumplimiento Aceptable"),
    (85.0, "Hallazgos Significativos"),
    (0.0, "Hallazgos Críticos"),
)


def peso_criticidad(rango: str | None) -> int | None:
    """«CRÍTICO: 5», «RELEVANTE (3)», «ORDINARIA : 1» → 5 / 3 / 1."""
    txt = (rango or "").upper()
    m = _DIGITO_RE.search(txt)
    if m:
        return int(m.group(1))
    for clave, peso in _PESOS_NOMBRE.items():
        if clave in txt.replace("Í", "I"):
            return peso
    return None


def rango_porcentaje(pct: float) -> str:
    # Los umbrales oficiales usan 2 decimales (84,99 / 85): se compara redondeado.
    pct = round(pct, 2)
    for minimo, etiqueta in UMBRALES:
        if pct >= minimo:
            return etiqueta
    return UMBRALES[-1][1]


@dataclass
class PuntajeDocumento:
    tipo_documento: str
    nombre: str
    maximo: float = 0
    obtenidos: float = 0
    criticos_no: list[str] = field(default_factory=list)
    sin_peso: list[str] = field(default_factory=list)

    @property
    def perdidos(self) -> float:
        return self.maximo - self.obtenidos

    @property
    def porcentaje(self) -> float:
        return round(100 * self.obtenidos / self.maximo, 2) if self.maximo else 0.0

    @property
    def rango(self) -> str:
        return rango_porcentaje(self.porcentaje) if self.maximo else "Sin preguntas evaluadas"


@dataclass
class PuntajeExpediente:
    documentos: list[PuntajeDocumento]
    revisados: list[str]
    faltantes: list[str]
    hallazgo_raiz: dict | None
    incluye_adjudicacion: bool

    @property
    def maximo(self) -> float:
        return sum(d.maximo for d in self.documentos)

    @property
    def obtenidos(self) -> float:
        return sum(d.obtenidos for d in self.documentos)

    @property
    def porcentaje(self) -> float:
        return round(100 * self.obtenidos / self.maximo, 2) if self.maximo else 0.0

    @property
    def rango(self) -> str:
        return rango_porcentaje(self.porcentaje)

    @property
    def flag_nulidad(self) -> bool:
        return any(d.criticos_no for d in self.documentos)

    @property
    def informe_final(self) -> bool:
        return not self.faltantes

    def a_dict(self) -> dict:
        """Resumen estructurado (para Nest y para auditar el dictamen)."""
        return {
            "informe": "FINAL" if self.informe_final else "PARCIAL",
            "regla_parcial": VALOR_PARCIAL,
            "documentos": [
                {
                    "tipo_documento": d.tipo_documento,
                    "documento": d.nombre,
                    "maximo": _num(d.maximo),
                    "obtenidos": _num(d.obtenidos),
                    "perdidos": _num(d.perdidos),
                    "porcentaje": d.porcentaje,
                    "rango": d.rango,
                    "criticos_no": d.criticos_no,
                }
                for d in self.documentos
            ],
            "global": {
                "maximo": _num(self.maximo),
                "obtenidos": _num(self.obtenidos),
                "porcentaje": self.porcentaje,
                "rango": self.rango,
            },
            "flag_nulidad_absoluta": self.flag_nulidad,
            "hallazgo_raiz": self.hallazgo_raiz,
            "incluye_adjudicacion": self.incluye_adjudicacion,
            "revisados": self.revisados,
            "faltantes": self.faltantes,
        }


def _num(x: float) -> float | int:
    return int(x) if float(x).is_integer() else round(x, 2)


def _fmt(x: float) -> str:
    return str(_num(x)).replace(".", ",")


def puntaje_documento(
    json_analista: dict,
    *,
    tipo_documento: str,
    nombre: str,
    peso_por_codigo: Callable[[str], int | None] | None = None,
) -> PuntajeDocumento:
    """Puntaje de un documento a partir de su `json_analista`.

    El peso sale del `rango_criticidad` del propio JSON; si falta (conformes de
    JSON antiguos), de `peso_por_codigo` (cuestionario). Sin peso → 1 y aviso.
    """
    pd = PuntajeDocumento(tipo_documento=tipo_documento, nombre=nombre)

    def peso(item: dict) -> int:
        cod = str(item.get("codigo_pregunta") or "")
        p = peso_criticidad(item.get("rango_criticidad"))
        if p is None and peso_por_codigo:
            p = peso_por_codigo(cod)
        if p is None:
            pd.sin_peso.append(cod)
            return 1
        return p

    for c in json_analista.get("conformes") or []:
        if isinstance(c, dict):
            p = peso(c)
            pd.maximo += p
            pd.obtenidos += p
    for h in json_analista.get("hallazgos") or []:
        if not isinstance(h, dict):
            continue
        p = peso(h)
        estado = str(h.get("estado") or "").lower()
        pd.maximo += p
        if estado == "parcial":
            pd.obtenidos += p * VALOR_PARCIAL
        if estado == "no" and p == PESO_CRITICO:
            pd.criticos_no.append(str(h.get("codigo_pregunta") or ""))
    if pd.sin_peso:
        logger.warning("Puntaje %s: preguntas sin criticidad (peso 1): %s", nombre, pd.sin_peso)
    return pd


def puntaje_expediente(
    documentos: Iterable[tuple[str, str, dict]],
    *,
    orden_tipos: list[str],
    etiquetas: dict[str, str] | None = None,
    pendientes: list[str] | None = None,
    peso_por_codigo: Callable[[str, str], int | None] | None = None,
) -> PuntajeExpediente:
    """Puntaje del expediente.

    `documentos`: (tipo_documento, nombre, json_analista) de cada pieza auditada.
    `orden_tipos`: tipos en el orden cronológico del checklist de la modalidad
    (define el hallazgo raíz). `pendientes`: tipos aún sin auditar.
    """
    etiquetas = etiquetas or {}
    posicion = {t: i for i, t in enumerate(orden_tipos)}
    docs = sorted(
        (
            (tipo, nombre, js)
            for tipo, nombre, js in documentos
            if isinstance(js, dict)
        ),
        key=lambda x: posicion.get(x[0], len(orden_tipos)),
    )
    puntajes = [
        puntaje_documento(
            js,
            tipo_documento=tipo,
            nombre=nombre,
            peso_por_codigo=(lambda cod, t=tipo: peso_por_codigo(t, cod)) if peso_por_codigo else None,
        )
        for tipo, nombre, js in docs
    ]
    raiz = None
    for (tipo, nombre, js), pd in zip(docs, puntajes):
        if not pd.criticos_no:
            continue
        cod = pd.criticos_no[0]
        h = next(
            (x for x in js.get("hallazgos") or [] if x.get("codigo_pregunta") == cod), {}
        )
        raiz = {
            "codigo_pregunta": cod,
            "tipo_documento": tipo,
            "documento": nombre,
            "respuesta": h.get("respuesta"),
            "fundamento_legal": h.get("fundamento_legal"),
        }
        break
    revisados = list(dict.fromkeys(etiquetas.get(t, t) for t, _, _ in docs))
    return PuntajeExpediente(
        documentos=puntajes,
        revisados=revisados,
        faltantes=[etiquetas.get(t, t) for t in (pendientes or [])],
        hallazgo_raiz=raiz,
        incluye_adjudicacion=any(t == "ADJUDICACION_O_EQUIVALENTE" for t, _, _ in docs),
    )


def bloque_resultados(px: PuntajeExpediente, *, etiquetas: dict[str, str] | None = None) -> str:
    """Bloque para el prompt del Jurídico: resultados YA calculados."""
    etiquetas = etiquetas or {}
    lineas = [
        "RESULTADOS CUANTITATIVOS CALCULADOS POR EL SISTEMA (cópialos tal cual en "
        "la sección 2; NO recalcules ni cambies cifras, rangos ni el flag):",
    ]
    for d in px.documentos:
        lineas.append(
            f"- {etiquetas.get(d.tipo_documento, d.tipo_documento)} ({d.nombre}) — "
            f"Máx {_fmt(d.maximo)} · Obtenidos {_fmt(d.obtenidos)} · "
            f"Perdidos {_fmt(d.perdidos)} · {_fmt(d.porcentaje)} % · Estatus: {d.rango}"
        )
    lineas.append(
        f"Puntaje Ponderado Global: {_fmt(px.porcentaje)} % "
        f"({_fmt(px.obtenidos)} de {_fmt(px.maximo)} puntos) → {px.rango}."
    )
    if px.flag_nulidad:
        cods = ", ".join(c for d in px.documentos for c in d.criticos_no)
        lineas.append(
            f"Flag de Riesgo de Nulidad Absoluta: ACTIVADO (incumplimiento «no» en "
            f"pregunta crítica: {cods}). Emite la Advertencia de Falsa Apariencia."
        )
    else:
        lineas.append(
            "Flag de Riesgo de Nulidad Absoluta: NO activado (ninguna pregunta "
            "crítica con estado «no»)."
        )
    if px.hallazgo_raiz:
        r = px.hallazgo_raiz
        lineas.append(
            f"Hallazgo Raíz (primer «no» crítico en la fase más temprana): "
            f"{r['codigo_pregunta']} en {etiquetas.get(r['tipo_documento'], r['tipo_documento'])}."
        )
    else:
        lineas.append(
            "Hallazgo Raíz: no hay preguntas críticas en «no»; no declares un "
            "hallazgo raíz de nulidad (analiza los parciales y no consta como "
            "riesgos a verificar)."
        )
    lineas.append(
        "Informe: "
        + (
            "FINAL (todas las fases auditadas)."
            if px.informe_final
            else f"PARCIAL. Faltan: {', '.join(px.faltantes)}."
        )
    )
    lineas.append(
        "Fase del procedimiento: "
        + (
            "la adjudicación YA fue dictada (consta en el expediente): ante un "
            "vicio insubsanable de orden público corresponde nulidad absoluta "
            "(Art. 19 LOPA)."
            if px.incluye_adjudicacion
            else "aún NO consta la adjudicación: la vía es la reposición al estado "
            "de la omisión (Art. 98 RLCP), no la nulidad absoluta."
        )
    )
    return "\n".join(lineas)


def puntaje_de_documentos(
    docs: Iterable,
    *,
    modalidad,
    checklist_slots: Iterable,
    pendientes: Iterable,
) -> tuple[PuntajeExpediente, dict[str, str]]:
    """Puntaje a partir de los `DocumentoAnalizado` de una sesión (o equivalentes).

    Solo cuentan las piezas con identidad correcta (`tipo_coincide`). Devuelve
    también las etiquetas legibles por tipo, en el orden del checklist.
    """
    from app.agents.knowledge import etiqueta_documento
    from app.agents.knowledge.cuestionarios_loader import cargar_cuestionario

    slots = list(checklist_slots or [])
    etiquetas = {
        s.tipo_documento.value: (s.descripcion or etiqueta_documento(s.tipo_documento))
        for s in slots
    }
    cache: dict[str, dict[str, int | None]] = {}

    def peso_por_codigo(tipo: str, codigo: str) -> int | None:
        if tipo not in cache:
            cache[tipo] = {}
            try:
                from app.models.schemas import TipoDocumento

                cuest = cargar_cuestionario(modalidad, TipoDocumento(tipo)) if modalidad else None
            except (ValueError, KeyError):
                cuest = None
            for it in (cuest.items if cuest else []):
                cache[tipo][it.codigo] = peso_criticidad(it.rango_criticidad)
        return cache[tipo].get(codigo)

    piezas = [
        (d.tipo.value, d.nombre_archivo, d.json_analista)
        for d in docs
        if getattr(d, "tipo_coincide", True) and isinstance(getattr(d, "json_analista", None), dict)
    ]
    px = puntaje_expediente(
        piezas,
        orden_tipos=[s.tipo_documento.value for s in slots],
        etiquetas=etiquetas,
        pendientes=[getattr(p, "value", p) for p in pendientes],
        peso_por_codigo=peso_por_codigo,
    )
    return px, etiquetas
