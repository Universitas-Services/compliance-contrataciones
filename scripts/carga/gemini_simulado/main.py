"""Gemini simulado para pruebas de carga: API compatible con OpenAI, sin modelo.

Responde JSON válido tras una espera parecida a la real. Con PROB_429 > 0 rechaza
una parte de las llamadas, como hace la capacidad compartida de Vertex.
"""

import asyncio
import json
import os
import random
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ESPERA_MIN = float(os.getenv("ESPERA_MIN_S", "8"))
ESPERA_MAX = float(os.getenv("ESPERA_MAX_S", "20"))
PROB_429 = float(os.getenv("PROB_429", "0"))
RUTA = os.getenv("RUTA_SECRETA", "local")
CODIGO = re.compile(r"\b[A-Z]{3,}\.\d+\b")

app = FastAPI()


@app.post(f"/{RUTA}/v1/chat/completions")
async def completar(request: Request) -> JSONResponse:
    cuerpo = await request.json()
    await asyncio.sleep(random.uniform(ESPERA_MIN, ESPERA_MAX))
    if random.random() < PROB_429:
        return JSONResponse({"error": {"message": "Resource exhausted"}}, status_code=429)
    texto = json.dumps(cuerpo.get("messages", []), ensure_ascii=False)
    rubrica = [
        {"id": c, "estado": "si", "respuesta": "Simulado.", "evidencia": "Simulado."}
        for c in dict.fromkeys(CODIGO.findall(texto))
    ]
    contenido = {
        "resumen": "Respuesta simulada.",
        "cumple": True,
        "estatus_global": "Verde",
        "tipo_coincide": True,
        "observaciones": [],
        "informe_markdown": "Simulado.",
        "rubrica": rubrica,
    }
    return JSONResponse({
        "id": "simulado",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": cuerpo.get("model", "simulado"),
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(contenido, ensure_ascii=False)},
        }],
        "usage": {"prompt_tokens": 5000, "completion_tokens": 1000, "total_tokens": 6000},
    })
