"""Normalización canónica de documentos + OCR (RapidOCR) multipágina."""

from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

_TEXTO_MINIMO_PAGINA = 20
_CHUNK_CHARS = 12000  # ~ bloques densos para map-reduce


@dataclass
class BloqueDocumento:
    id: str
    etiqueta: str  # p.ej. "p.1", "hoja:Resumen"
    texto: str


@dataclass
class DocumentoCanonico:
    texto: str
    metodo: str
    paginas: int = 0
    advertencias: list[str] = field(default_factory=list)
    cobertura_ocr: float | None = None
    bloques: list[BloqueDocumento] = field(default_factory=list)
    imagenes_selectivas: list[dict] = field(default_factory=list)

    @property
    def num_bloques(self) -> int:
        return len(self.bloques) if self.bloques else (1 if self.texto.strip() else 0)


def _colapsar_ws(texto: str) -> str:
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _ocr_imagen_bytes(png_bytes: bytes) -> str:
    """OCR local con RapidOCR; vacío si no está instalado o falla."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        logger.warning("rapidocr_onnxruntime no instalado; OCR omitido")
        return ""
    try:
        engine = RapidOCR()
        # RapidOCR acepta ndarray o path; usamos temp png
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            tmp.write(png_bytes)
            tmp.close()
            result, _ = engine(tmp.name)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        if not result:
            return ""
        lineas = [str(item[1]) for item in result if len(item) > 1 and item[1]]
        return "\n".join(lineas).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR falló: %s", exc)
        return ""


def rasterizar_pagina_pdf(path: str, page_index: int, zoom: float = 2.0) -> bytes:
    doc = fitz.open(path)
    try:
        if page_index < 0 or page_index >= doc.page_count:
            raise ValueError(f"Página fuera de rango: {page_index}")
        pix = doc[page_index].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def ocr_pdf_todas_paginas(path: str) -> tuple[list[BloqueDocumento], list[str], float]:
    """OCR de todas las páginas. Devuelve bloques, advertencias, cobertura 0..1."""
    doc = fitz.open(path)
    bloques: list[BloqueDocumento] = []
    advertencias: list[str] = []
    ok = 0
    try:
        total = doc.page_count
        for i in range(total):
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            texto = _ocr_imagen_bytes(pix.tobytes("png"))
            etiqueta = f"p.{i + 1}"
            if len(texto) >= _TEXTO_MINIMO_PAGINA:
                ok += 1
                bloques.append(BloqueDocumento(id=f"b{i+1}", etiqueta=etiqueta, texto=texto))
            else:
                advertencias.append(f"OCR débil o vacío en {etiqueta}")
                bloques.append(
                    BloqueDocumento(
                        id=f"b{i+1}",
                        etiqueta=etiqueta,
                        texto=texto or f"[{etiqueta}: sin texto OCR usable]",
                    )
                )
        cobertura = (ok / total) if total else 0.0
        return bloques, advertencias, cobertura
    finally:
        doc.close()


def ocr_archivo_imagen(path: str) -> tuple[str, list[str]]:
    data = Path(path).read_bytes()
    texto = _ocr_imagen_bytes(data)
    adv: list[str] = []
    if len(texto) < _TEXTO_MINIMO_PAGINA:
        adv.append("OCR de imagen insuficiente; considerar visión selectiva")
    return texto, adv


def armar_texto_canonico(
    *,
    meta_lineas: list[str],
    bloques: list[BloqueDocumento],
) -> str:
    partes = list(meta_lineas)
    for b in bloques:
        partes.append(f"## {b.etiqueta}")
        partes.append(b.texto)
    return _colapsar_ws("\n\n".join(partes))


def partir_en_chunks(texto: str, max_chars: int = _CHUNK_CHARS) -> list[str]:
    """Divide texto largo sin omitir contenido (por límites de caracteres)."""
    t = texto.strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]
    chunks: list[str] = []
    # Preferir corte por secciones ## 
    secciones = re.split(r"(?=\n## )", t)
    buf = ""
    for sec in secciones:
        if not sec.strip():
            continue
        if buf and len(buf) + len(sec) > max_chars:
            chunks.append(buf.strip())
            buf = sec
        else:
            buf = f"{buf}{sec}" if buf else sec
        while len(buf) > max_chars:
            chunks.append(buf[:max_chars])
            buf = buf[max_chars:]
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def chunks_desde_bloques(
    bloques: list[BloqueDocumento],
    max_chars: int = _CHUNK_CHARS,
) -> list[str]:
    if not bloques:
        return []
    chunks: list[str] = []
    buf_parts: list[str] = []
    buf_len = 0
    for b in bloques:
        piece = f"## {b.etiqueta}\n{b.texto}"
        if buf_parts and buf_len + len(piece) > max_chars:
            chunks.append("\n\n".join(buf_parts))
            buf_parts = [piece]
            buf_len = len(piece)
        else:
            buf_parts.append(piece)
            buf_len += len(piece) + 2
        while buf_len > max_chars and buf_parts:
            # un bloque gigante
            big = buf_parts[-1]
            if len(big) > max_chars:
                buf_parts.pop()
                for i in range(0, len(big), max_chars):
                    chunks.append(big[i : i + max_chars])
                buf_len = sum(len(x) + 2 for x in buf_parts)
            else:
                break
    if buf_parts:
        chunks.append("\n\n".join(buf_parts))
    return chunks
