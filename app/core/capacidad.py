"""Control de carga: cuánto trabajo pesado corre a la vez en esta instancia.

Si se llena, se responde 503 con Retry-After en vez de acumular peticiones hasta
agotar memoria o tiempo: el cliente reintenta y Cloud Run puede abrir instancias.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

MAX_ANALISIS = int(os.getenv("MAX_ANALISIS_CONCURRENTES", "8"))
# Cada OCR en curso suma ~500 MiB: 8 a la vez agotaron los 2 GiB de la instancia.
MAX_OCR = int(os.getenv("MAX_OCR_CONCURRENTES", "2"))
_REINTENTO_S = os.getenv("REINTENTO_OCUPADO_S", "30")
_cupos = threading.BoundedSemaphore(MAX_ANALISIS)
_cupos_ocr = threading.BoundedSemaphore(MAX_OCR)


@contextmanager
def _cupo(semaforo: threading.BoundedSemaphore) -> Iterator[None]:
    if not semaforo.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="El servicio está ocupado. Reintenta en unos segundos.",
            headers={"Retry-After": _REINTENTO_S},
        )
    try:
        yield
    finally:
        semaforo.release()


def cupo_analisis():
    return _cupo(_cupos)


def cupo_ocr():
    return _cupo(_cupos_ocr)
