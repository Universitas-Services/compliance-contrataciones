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
| `CORS_ORIGINS` | Orígenes del front (coma-separados). Con gateways, preferir vacío o internos |
| `MAX_UPLOAD_MB` | Límite de tamaño de archivos (default 25) |
| `AGENT_AUTH_ENABLED` | `true` en staging/prod; `false` solo demos locales sin gateway |
| `AGENT_CLIENT_LARAVEL_KEY` | Secreto del portal Laravel (pruebas) |
| `AGENT_CLIENT_NEST_KEY` | Secreto del gateway Nest (producción) |
| `DOCS_ENABLED` | Swagger/ReDoc (`false` en staging/prod) |

## Auth gateway (servicio-a-servicio)

El navegador **no** debe llamar a esta API directo. Laravel (pruebas) o Nest (producción) reenvían con el header:

```http
X-Agent-Key: <clave del cliente>
```

- `/health` queda **sin** auth (monitoreo).
- Todas las rutas bajo `/api/...` exigen la key cuando `AGENT_AUTH_ENABLED=true`.
- Cada entorno tiene su propia key: filtrar la de pruebas no obliga a rotar la de producción.

### Prueba rápida (curl)

Con auth activada y keys en `.env`:

```bash
# Sin key → 401
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/api/sesiones/

# Health sin key → 200
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/health

# Con key Laravel → 200 (listado)
curl -s -o NUL -w "%{http_code}" -H "X-Agent-Key: TU_CLAVE_LARAVEL" http://127.0.0.1:8000/api/sesiones/
```

Hasta que Nest/Laravel manden la key, en local puedes dejar `AGENT_AUTH_ENABLED=false`. **No** metas la key en el bundle del browser (Angular/Next).

## Datos de sesión

Hoy las sesiones se persisten en `data/sesiones.json` (local, **ignorado por git**). Cuando se conecte una base de datos, ese archivo dejará de usarse: la lógica pasará al store en BD y el JSON local se podrá borrar o migrar una vez.

## Seguridad (estado actual)

- Secretos solo vía `.env` (no hardcodeados).
- CORS restringible por `CORS_ORIGINS`.
- Cabeceras HTTP básicas (`X-Content-Type-Options`, `X-Frame-Options`, etc.).
- Validación de extensión y tamaño en uploads.
- Auth multi-cliente por `X-Agent-Key` (Laravel / Nest); ver sección anterior.
- Sin base de datos aún: la inyección SQL no aplica; al añadir BD usar ORM o SQL parametrizado (nunca concatenar input del usuario en queries).
- Permisos de usuario humano (quién puede probar qué agente): viven en el gateway (Laravel/Nest), no en esta API.

## Estructura

- `app/main.py` — FastAPI
- `app/routers/` — endpoints
- `app/agents/` — orquestador, extractor, modalidades, informes
- `app/core/` — LLM client, session store, seguridad
- `app/models/` — esquemas Pydantic
- `cuestionarios/` — rúbricas oficiales por modalidad
- `basamento-legal/` — KB normativa (LCP, RLCP, LOPA, etc.; recuperación por artículo)
