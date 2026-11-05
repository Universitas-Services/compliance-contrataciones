"""Pruebas sin LLM de la carga concurrente, con un servidor uvicorn real."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

import uvicorn

from app.core import llm_client  # noqa: F401  (carga .env antes de sobrescribir)

os.environ["AGENT_AUTH_ENABLED"] = "false"
os.environ["KNOWLEDGE_SOURCE"] = "local"

from app.core import capacidad, session_store  # noqa: E402
from app.main import app  # noqa: E402
from app.models.schemas import EstadoSesion, Modalidad, SesionCompliance, TipoContratacion  # noqa: E402
from app.routers import sesiones  # noqa: E402

ESPERA_S = 1.5
CAMPOS = {
    "nomenclatura": "CA-001",
    "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA",
    "tipo_contratacion": "BIENES",
    "tipo_documento": "ACTA_INICIO",
}


def _analisis_falso(*_a, **_k) -> dict:
    time.sleep(ESPERA_S)
    return {"resumen": "ok", "cumple": True, "observaciones": [], "tipo_coincide": True}


def _multipart(campos: dict, nombre: str) -> tuple[bytes, str]:
    limite = uuid.uuid4().hex
    partes = [
        f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
        for k, v in campos.items()
    ]
    partes.append(
        f'--{limite}\r\nContent-Disposition: form-data; name="archivo"; '
        f'filename="{nombre}"\r\nContent-Type: text/plain\r\n\r\ncontenido\r\n--{limite}--\r\n'
    )
    return "".join(partes).encode(), f"multipart/form-data; boundary={limite}"


def _post(url: str, campos: dict, nombre: str = "acta.txt") -> tuple[int, dict, dict]:
    cuerpo, tipo = _multipart(campos, nombre)
    req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": tipo})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.load(e)


def _rafaga(base: str, n: int) -> list[tuple[int, dict, dict]]:
    with ThreadPoolExecutor(n) as ex:
        return list(ex.map(lambda _: _post(f"{base}/api/analizar", CAMPOS), range(n)))


def prueba_en_paralelo_y_health(base: str) -> None:
    n = capacidad.MAX_ANALISIS
    antes = len(session_store.listar_sesiones())
    t0 = time.time()
    with ThreadPoolExecutor(1) as ex:
        rafaga = ex.submit(_rafaga, base, n)
        time.sleep(ESPERA_S / 3)
        t_health = time.time()
        with urllib.request.urlopen(f"{base}/health", timeout=5) as r:
            assert r.status == 200
        t_health = time.time() - t_health
        res = rafaga.result()
    total = time.time() - t0
    assert [r[0] for r in res] == [200] * n, [(r[0], r[2]) for r in res]
    assert total < ESPERA_S * 2, f"no corrieron en paralelo: {total:.1f}s"
    assert t_health < ESPERA_S / 3, f"/health esperó {t_health:.2f}s"
    assert len(session_store.listar_sesiones()) == antes, "guardó una sesión"
    print(f"ok {n} en paralelo en {total:.1f}s; /health en {t_health:.3f}s; sin sesiones")


def prueba_sobrecarga(base: str) -> None:
    n = capacidad.MAX_ANALISIS
    res = _rafaga(base, n + 4)
    codigos = sorted(r[0] for r in res)
    assert codigos == [200] * n + [503] * 4, codigos
    ocupado = next(r for r in res if r[0] == 503)
    assert {k.lower(): v for k, v in ocupado[1].items()}.get("retry-after") == "30", ocupado[1]
    assert _post(f"{base}/api/analizar", CAMPOS)[0] == 200, "no liberó los cupos"
    print("ok sobrecarga: 503 con Retry-After y los cupos se liberan")


def prueba_error_libera_cupo(base: str) -> None:
    for _ in range(capacidad.MAX_ANALISIS + 1):
        assert _post(f"{base}/api/analizar", CAMPOS, "virus.exe")[0] == 415
    assert _post(f"{base}/api/analizar", CAMPOS)[0] == 200
    print("ok los rechazos no consumen cupos")


def prueba_misma_sesion(base: str) -> None:
    sid = str(uuid.uuid4())
    modalidad = Modalidad.CA_ACTO_UNICO_APERTURA_UNICA
    sesion = SesionCompliance(
        id=sid,
        nomenclatura="CA-001",
        modalidad=modalidad,
        tipo_contratacion=TipoContratacion.BIENES,
        estado=EstadoSesion.ACTIVA,
        fecha_inicio=sesiones.datetime.now(sesiones.timezone.utc),
        checklist_slots=sesiones.get_modalidad_agent(modalidad, TipoContratacion.BIENES).obtener_checklist(),
    )
    session_store.guardar_sesion(sid, sesion)
    url = f"{base}/api/sesiones/{sid}/documentos"
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(
            lambda i: _post(url, {"tipo_documento": "ACTA_INICIO"}, f"acta_{i}.txt"), range(6)
        ))
    assert [r[0] for r in res] == [200] * 6, [(r[0], r[2]) for r in res]
    assert len(sesion.documentos_analizados) == 6, len(sesion.documentos_analizados)
    print("ok 6 cargas simultáneas en una sesión: no se pierde ninguna")


def main() -> None:
    sesiones.analizar_documento = _analisis_falso
    sesiones.procesar_archivo = lambda *_a: {"texto_extraido": "contenido", "modo": "texto"}
    session_store._persist = lambda: None  # no tocar data/sesiones.json

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(app, port=puerto, log_level="warning"))
    threading.Thread(target=servidor.run, daemon=True).start()
    while not servidor.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{puerto}"
    try:
        prueba_en_paralelo_y_health(base)
        prueba_sobrecarga(base)
        prueba_error_libera_cupo(base)
        prueba_misma_sesion(base)
    finally:
        servidor.should_exit = True
    print("TODO OK")


if __name__ == "__main__":
    main()
