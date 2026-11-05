"""Lanza N análisis a la vez contra el servicio de carga y resume los resultados.

Uso: python -m scripts.carga.generar_carga URL N [--reintentos]
Autentica con el token de identidad de gcloud; no usa la clave del cliente.
"""

from __future__ import annotations

import collections
import json
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

import fitz

CAMPOS = {
    "nomenclatura": "CA-CARGA-001",
    "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA",
    "tipo_contratacion": "BIENES",
    "tipo_documento": "ACTA_INICIO",
}
TOPE_S = 840


def pdf_de_prueba() -> bytes:
    doc = fitz.open()
    for _ in range(3):
        doc.new_page().insert_text((50, 72), "Acta de inicio de prueba. " * 8)
    return doc.tobytes()


def cuerpo_multipart(pdf: bytes) -> tuple[bytes, str]:
    limite = uuid.uuid4().hex
    partes = b"".join(
        f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in CAMPOS.items()
    )
    partes += (
        f'--{limite}\r\nContent-Disposition: form-data; name="archivo"; filename="acta.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf + f"\r\n--{limite}--\r\n".encode()
    return partes, f"multipart/form-data; boundary={limite}"


def enviar(url: str, token: str, cuerpo: bytes, tipo: str, reintentar: bool) -> tuple[int, float, int]:
    inicio = time.time()
    intentos = 0
    while True:
        intentos += 1
        espera = None
        req = urllib.request.Request(
            f"{url}/api/analizar",
            data=cuerpo,
            headers={"Content-Type": tipo, "Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TOPE_S) as r:
                json.load(r)
                codigo = r.status
        except urllib.error.HTTPError as e:
            codigo = e.code
            e.read()
            espera = e.headers.get("Retry-After") or (15 if codigo == 429 else None)
        except Exception:  # noqa: BLE001
            codigo = 0
        if codigo not in (429, 503) or not reintentar or espera is None:
            return codigo, time.time() - inicio, intentos
        if time.time() - inicio > TOPE_S:
            return codigo, time.time() - inicio, intentos
        time.sleep(float(espera))


def main() -> None:
    url, n = sys.argv[1].rstrip("/"), int(sys.argv[2])
    reintentar = "--reintentos" in sys.argv
    token = subprocess.run(
        "gcloud auth print-identity-token", shell=True, capture_output=True, text=True
    ).stdout.strip()
    cuerpo, tipo = cuerpo_multipart(pdf_de_prueba())
    arranque = threading.Barrier(n)

    def tarea(_: int) -> tuple[int, float, int]:
        arranque.wait()
        return enviar(url, token, cuerpo, tipo, reintentar)

    t0 = time.time()
    print(time.strftime("Inicio %H:%M:%S UTC", time.gmtime()), f"| {n} a la vez | reintentos={reintentar}")
    with ThreadPoolExecutor(n) as ex:
        res = list(ex.map(tarea, range(n)))
    ok = sorted(r[1] for r in res if r[0] == 200)
    print("códigos:", dict(collections.Counter(r[0] for r in res)))
    if ok:
        print(f"éxitos: {len(ok)} | mediana {statistics.median(ok):.0f}s | máximo {ok[-1]:.0f}s")
    print(f"intentos máx: {max(r[2] for r in res)} | total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
