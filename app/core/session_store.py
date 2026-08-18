"""Almacén de sesiones de compliance (memoria + persistencia en disco).

Con uvicorn --reload, el proceso se reinicia y la memoria se pierde.
Persistimos en data/sesiones.json para conservar historial y contexto.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from app.models.schemas import SesionCompliance

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_sesiones: dict[str, SesionCompliance] = {}
_STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "sesiones.json"
_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    with _LOCK:
        if _loaded:
            return
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if _STORE_PATH.exists():
            try:
                raw = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for sid, payload in raw.items():
                        try:
                            _sesiones[sid] = SesionCompliance.model_validate(payload)
                        except Exception:
                            continue
            except Exception:
                pass
        _loaded = True


def _persist() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {sid: s.model_dump(mode="json") for sid, s in _sesiones.items()}
    tmp = _STORE_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_STORE_PATH)
    except OSError:
        logger.warning(
            "No se pudo persistir sesiones en %s (disco efímero?). Quedan solo en memoria.",
            _STORE_PATH,
        )


def get_sesion(sesion_id: str) -> SesionCompliance | None:
    _ensure_loaded()
    return _sesiones.get(sesion_id)


def guardar_sesion(sesion_id: str, sesion: SesionCompliance) -> SesionCompliance:
    _ensure_loaded()
    with _LOCK:
        _sesiones[sesion_id] = sesion
        _persist()
    return sesion


def listar_sesiones() -> list[SesionCompliance]:
    _ensure_loaded()
    return list(_sesiones.values())


def eliminar_todas() -> None:
    global _loaded
    with _LOCK:
        _sesiones.clear()
        _persist()
        _loaded = True


# Aliases de compatibilidad temporal (código legacy)
def get_expediente(expediente_id: str) -> SesionCompliance | None:
    return get_sesion(expediente_id)


def guardar_expediente(expediente_id: str, expediente: SesionCompliance) -> SesionCompliance:
    return guardar_sesion(expediente_id, expediente)


def eliminar_todos() -> None:
    eliminar_todas()
