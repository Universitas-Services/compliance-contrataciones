# compliance-contrataciones

API FastAPI para auditoría conversacional de compliance en contrataciones públicas (Venezuela): orquestador + dupla Analista / Jurídico por modalidad.

## Requisitos

- Python 3.11+
- Clave de Gemini (u otro proveedor OpenAI-compatible) en `.env`

## Arranque

```bash
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # o: cp .env.example .env
# Edita .env y rellena GEMINI_API_KEY (y opcionalmente FALLBACK_*)

uvicorn app.main:app --reload --port 8000
```

- Salud: http://127.0.0.1:8000/health  
- Docs: http://127.0.0.1:8000/docs  

## Variables de entorno

Copia `.env.example` → `.env`. **Nunca subas `.env` al repositorio.**

| Variable | Uso |
|----------|-----|
| `GEMINI_API_KEY` / `GEMINI_BASE_URL` / `GEMINI_MODEL` | Proveedor LLM primario |
| `FALLBACK_*` | Proveedor de respaldo si Gemini falla (429/404/503) |
| `CORS_ORIGINS` | Orígenes del front (coma-separados) |
| `MAX_UPLOAD_MB` | Límite de tamaño de archivos (default 25) |

## Datos de sesión

Hoy las sesiones se persisten en `data/sesiones.json` (local, **ignorado por git**). Cuando se conecte una base de datos, ese archivo dejará de usarse: la lógica pasará al store en BD y el JSON local se podrá borrar o migrar una vez.

## Seguridad (estado actual)

- Secretos solo vía `.env` (no hardcodeados).
- CORS restringible por `CORS_ORIGINS`.
- Cabeceras HTTP básicas (`X-Content-Type-Options`, `X-Frame-Options`, etc.).
- Validación de extensión y tamaño en uploads.
- Sin base de datos aún: la inyección SQL no aplica; al añadir BD usar ORM o SQL parametrizado (nunca concatenar input del usuario en queries).
- Auth de usuarios / API keys de clientes: pendiente para una fase posterior.

## Estructura

- `app/main.py` — FastAPI
- `app/routers/` — endpoints
- `app/agents/` — orquestador, extractor, modalidades, informes
- `app/core/` — LLM client, session store, seguridad
- `app/models/` — esquemas Pydantic
