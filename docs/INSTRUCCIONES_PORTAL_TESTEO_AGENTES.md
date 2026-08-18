# Instrucciones Cursor: portal de prueba de agentes (Laravel + Angular)

Documento para **otra instancia de Cursor**. Objetivo: crear dos proyectos hermanos que permitan a admins y testers expertos probar agentes FastAPI (como `compliance-contrataciones`) **sin desplegar el front de producción** y **sin exponer las APIs de agentes al navegador**.

**Decisión de stack fijada aquí (no debatirla):**

| Pieza | Elección | Por qué |
|-------|----------|---------|
| Backend portal | **Laravel 11+** (API) | Auth SPA, gateway HTTP, admin |
| Front portal | **Angular** (SPA) | Admin + tester en una app |
| Base de datos | **PostgreSQL (Supabase)** | Hosting gestionado, SSL, backups |
| ORM | **Eloquent (Laravel)** | Nativo; **no usar Prisma** (Prisma es Node; con Laravel añade fricción y dos ORMs) |
| Auth humano | **Laravel Sanctum** | SPA cookie/token |
| Roles | **spatie/laravel-permission** | `admin` / `tester` + permisos por agente |

**RLS (Supabase):** la app Laravel se conecta con la connection string de Postgres (rol de servicio / DB user de Laravel). **La autorización de negocio se aplica en Laravel** (policies + middleware). RLS en Supabase es defensa en profundidad opcional (fase 2); no bloquear el MVP con RLS complejo. Si se activa RLS, Laravel no debe usar la `anon` key del browser contra tablas sensibles.

---

## 0. Contexto del ecosistema (léelo entero antes de codear)

### 0.1 Problema de negocio

- Se construyen varios agentes (FastAPI) en paralelo.
- Hoy se prueban en el front de producción (o no se puede desplegar staging completo).
- El programador puede “ver si responde”; el **experto de dominio** necesita probar calidad sin estar en local ni tocar el monorepo de producción.
- Solución: **portal universal de testing** (Angular) + **backend gateway** (Laravel) que:
  - autentica usuarios,
  - decide **qué usuario puede probar qué agente**,
  - reenvía llamadas **server-to-server** al FastAPI interno,
  - registra logs y feedback del tester.

### 0.2 Arquitectura objetivo

```text
Angular (SPA)
  → Laravel (Sanctum + permisos + gateway + admin)
      → FastAPI Agente compliance (red interna / URL no pública al browser)
      → FastAPI Agente N …
```

- El browser **nunca** llama a FastAPI.
- Nest/Next (producción del Gestor) es **otro** consumidor del mismo FastAPI, con **otra** API key. Este portal Laravel es solo el entorno de **pruebas**.

### 0.3 Cómo funciona el agente `compliance-contrataciones` (referencia)

Repo del agente (ya existente): FastAPI de auditoría conversacional de contrataciones públicas (Venezuela).

Flujo del agente:

1. Crear sesión → configurar **nomenclatura + modalidad + tipo de contrato**.
2. Sesión ACTIVA → checklist de documentos según modalidad.
3. Subir documento por tipo de slot → Analista (rúbrica / semáforo Verde|Amarillo|Rojo).
4. Opcional: revisión jurídica (parcial/final).
5. Informes markdown / PDF / DOCX.

Rutas relevantes del agente (prefijo `/api/sesiones`):

| Método | Path | Uso |
|--------|------|-----|
| GET | `/api/sesiones/` | Listar sesiones |
| POST | `/api/sesiones/` | Crear sesión |
| POST | `/api/sesiones/{id}/mensaje` | Chat orquestador |
| GET | `/api/sesiones/{id}` | Detalle sesión |
| GET | `/api/sesiones/{id}/checklist` | Checklist |
| POST | `/api/sesiones/{id}/documentos` | Upload + análisis |
| POST | `/api/sesiones/{id}/juridico` | Dictamen jurídico |
| GET | `/api/sesiones/{id}/documentos/{doc}/informe[.pdf|.docx]` | Informe doc |
| GET | `/api/sesiones/{id}/informe[.pdf|.docx]` | Informe global |
| GET | `/health` | Salud (**sin** auth de gateway) |

Auth ya implementada en el agente:

- Header obligatorio hacia FastAPI: **`X-Agent-Key`**.
- Env del agente: `AGENT_AUTH_ENABLED=true`, `AGENT_CLIENT_LARAVEL_KEY=<secreto>`, `AGENT_CLIENT_NEST_KEY=<otro>`.
- Laravel debe mandar exactamente el valor de `AGENT_CLIENT_LARAVEL_KEY`.
- `/health` sin key.

**No** hacer proxy genérico `/{path}` hacia FastAPI. Rutas explícitas en Laravel que mapean a paths conocidos del contrato del agente.

### 0.4 Carpetas destino (ajusta rutas si el usuario indica otras)

Crear **hermanos** del repo del agente, no dentro de `app/` del FastAPI:

```text
…/Agentes/
  hecho con claude/          ← FastAPI compliance (ya existe)
  portal-agentes-api/        ← PARTE A: Laravel (este documento)
  portal-agentes-web/        ← PARTE B: Angular (este documento)
```

Si el usuario da otras rutas absolutas, úsalas. No mezclar PHP/Angular dentro del venv del FastAPI.

### 0.5 Orden de trabajo recomendado para Cursor

1. Completar **PARTE A (Laravel)** hasta `GET /api/health` + login + CRUD mínimo de agentes + un forward `chat/mensaje` de prueba.
2. Completar **PARTE B (Angular)** consumiendo solo Laravel.
3. Integrar end-to-end con el FastAPI local (`AGENT_AUTH_ENABLED=true` + misma key).

---

# PARTE A — Backend Laravel (`portal-agentes-api`)

> Instrucciones para la instancia Cursor del **backend**. Ejecutar en Windows (PowerShell) salvo que el usuario diga lo contrario.

## A1. Instalar PHP, Composer y herramientas (Windows)

Si no hay PHP 8.2+:

1. Instalar **PHP 8.2+** (recomendado: [php.net](https://windows.php.net/download/) o `winget install PHP.PHP.8.3`).
2. Extensiones mínimas en `php.ini`: `openssl`, `pdo_pgsql`, `mbstring`, `tokenizer`, `xml`, `ctype`, `json`, `fileinfo`, `curl`.
3. Instalar **Composer**: [getcomposer.org](https://getcomposer.org/).
4. Verificar:

```powershell
php -v
composer -V
```

5. Opcional local: Laravel Herd / Sail / Docker. Para MVP: `php artisan serve` basta.
6. Node **no** es obligatorio en el API; el front es otro repo.

## A2. Crear el proyecto

```powershell
cd "C:\Users\unive\OneDrive\Desktop\frank\Agentes"
composer create-project laravel/laravel portal-agentes-api
cd portal-agentes-api
```

Paquetes:

```powershell
composer require laravel/sanctum spatie/laravel-permission
php artisan vendor:publish --provider="Laravel\Sanctum\SanctumServiceProvider"
php artisan vendor:publish --provider="Spatie\Permission\PermissionServiceProvider"
```

Configurar Sanctum para SPA (cookie stateful) **o** tokens Bearer para Angular; elegir **una** y documentarla en `.env.example`. Recomendación MVP: **token Bearer Sanctum** (más simple con Angular en otro origen) + CORS estricto al origen Angular.

## A3. Variables de entorno (nunca committear `.env`)

Crear `.env.example` con:

```env
APP_NAME="Portal Agentes API"
APP_ENV=local
APP_DEBUG=true
APP_URL=http://127.0.0.1:8001

# Postgres Supabase (connection pooler o direct)
DB_CONNECTION=pgsql
DB_HOST=db.XXXX.supabase.co
DB_PORT=5432
DB_DATABASE=postgres
DB_USERNAME=postgres
DB_PASSWORD=

# O DATABASE_URL=postgresql://postgres:....@db.XXXX.supabase.co:5432/postgres

SANCTUM_STATEFUL_DOMAINS=localhost:4200,127.0.0.1:4200
FRONTEND_URL=http://localhost:4200
SESSION_DOMAIN=localhost

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200

# Cifrado de secretos de agentes en BD (APP_KEY de Laravel sirve para encrypt())
# No guardar secret_key de agentes en claro en logs

# Rate limiting
RATE_LIMIT_API=60
RATE_LIMIT_GATEWAY=20

LOG_CHANNEL=stack
LOG_LEVEL=debug
```

Reglas:

- `.env` en `.gitignore`.
- Secretos de agentes (`secret_key` hacia FastAPI) **cifrados** en BD con `Crypt::encryptString` / cast `encrypted`.
- Nunca loguear `X-Agent-Key`, passwords, ni bodies de upload completos.

## A4. Modelo de datos (Eloquent + migraciones)

Tablas mínimas:

### `users`

Campos estándar Laravel + `is_active` boolean.

### `agents`

| Columna | Tipo | Notas |
|---------|------|--------|
| id | uuid/ulid | PK |
| name | string | Ej. “Compliance contrataciones” |
| slug | string unique | |
| base_url | string | URL interna FastAPI, ej. `http://127.0.0.1:8000` — **nunca** exponer al Angular |
| secret_key | text encrypted | Valor = `AGENT_CLIENT_LARAVEL_KEY` del agente |
| status | enum | `dev`, `staging`, `active`, `disabled` |
| contract_version | string nullable | ej. `sesiones-v1` |
| notes | text nullable | |
| timestamps / softDeletes | | |

### `agent_user` (pivote)

| Columna | Notas |
|---------|--------|
| agent_id | FK |
| user_id | FK |
| can_chat | bool default true |
| can_upload | bool default true |
| assigned_by | user_id nullable |
| timestamps | unique(agent_id, user_id) |

### `agent_logs`

| Columna | Notas |
|---------|--------|
| id | |
| agent_id | |
| user_id | |
| action | `mensaje`, `crear_sesion`, `upload`, `juridico`, `health_check`, … |
| external_session_id | string nullable (id sesión FastAPI) |
| request_meta | json (sin secretos; path, tamaños) |
| response_meta | json (status HTTP, latencia_ms; no volcar LLM completo si es enorme — truncar) |
| feedback_rating | smallint nullable (−1/0/1 o 1–5) |
| feedback_comment | text nullable |
| ip | string nullable |
| user_agent | string nullable |
| timestamps | |

### Roles Spatie

- Rol `admin`: CRUD users/agents, asignaciones, ver todos los logs.
- Rol `tester`: solo agentes asignados, chat/upload según pivote, enviar feedback.

Seed: un admin inicial (password solo en `.env` / tinker, no hardcodear en repo).

## A5. Seguridad obligatoria (implementar desde el día 1)

### A5.1 Auth por rutas

- Grupo `auth:sanctum` para casi toda `/api/*`.
- Grupo `role:admin` (o middleware Spatie `role:admin` / `permission:…`) para:
  - CRUD agents, users, asignaciones.
  - Listado global de logs.
- Tester: policies `AgentPolicy::view` / `use` basadas en pivote `agent_user`.

### A5.2 Validación de input (anti inyección / XSS / path abuse)

- **Form Requests** en todos los endpoints que escriben.
- Nunca concatenar SQL; solo Eloquent / Query Builder con bindings.
- Validar UUIDs, enums, tamaños de string, MIME de uploads.
- En el gateway: **no** aceptar `path` libre del cliente hacia FastAPI. Paths construidos en código:

```text
POST /api/agents/{agent}/proxy/sesiones
POST /api/agents/{agent}/proxy/sesiones/{sesionId}/mensaje
POST /api/agents/{agent}/proxy/sesiones/{sesionId}/documentos
…
```

Mapa interno fijo `action → path FastAPI`.

### A5.3 Rate limiting

- `RateLimiter` en `RouteServiceProvider` / `bootstrap/app.php`:
  - API general: 60/min por user+IP.
  - Gateway (forward a LLM): más estricto (ej. 20/min) — protege costo y abuso.
- Responder `429` con JSON uniforme.

### A5.4 Protección admin

- Middleware role + throttle aparte.
- Audit log en mutaciones admin (quién creó/asignó/desactivó un agente).
- No devolver `secret_key` ni `base_url` en JSON al front (o `base_url` solo a admin si hace falta depurar; por defecto **omitir**).

### A5.5 Errores

- `APP_DEBUG=false` en no-local.
- Respuestas JSON:

```json
{ "message": "…", "code": "AGENT_FORBIDDEN", "errors": {} }
```

- No filtrar stack traces al cliente.
- Mapear timeouts/5xx del FastAPI a 502/504 con mensaje claro.

### A5.6 Tablas / superficie pública

- Ningún endpoint público excepto: `POST /api/login` (o register deshabilitado), `GET /api/health` del **Laravel**.
- No exponer `/telescope` ni debugbar en prod.
- Deshabilitar registro abierto si no se necesita; altas de tester solo por admin.

### A5.7 Logging

**Backend (Laravel):**

- Canal `stack` + `daily`.
- Log estructurado: `user_id`, `agent_id`, `action`, `latency_ms`, `http_status`.
- **No** loguear: API keys, Authorization, contenido completo de PDFs, prompts LLM enteros si contienen PII (truncar).
- Guardar fila en `agent_logs` en cada forward exitoso/fallido.

**Para el frontend (contrato de errores):**

- Códigos estables (`UNAUTHENTICATED`, `FORBIDDEN_AGENT`, `RATE_LIMITED`, `AGENT_UNAVAILABLE`) para que Angular muestre mensajes UX sin parsear HTML.

### A5.8 CORS / headers

- CORS solo orígenes Angular.
- Headers de seguridad: `X-Content-Type-Options`, `X-Frame-Options`, etc. (middleware).
- HTTPS en staging/prod.

## A6. `AgentGatewayService` (núcleo)

Responsabilidades:

1. Recibir `Agent` + `action` + payload (+ archivo si upload).
2. Verificar permiso del user (policy).
3. `Http::timeout(…)->withHeaders(['X-Agent-Key' => decrypt(secret), 'Accept' => 'application/json'])->…` hacia `base_url + path`.
4. Medir latencia; persistir `agent_logs`.
5. Devolver JSON/stream al Angular **sin** añadir la key.

Health del agente (admin):

- `GET {base_url}/health` **sin** key (el FastAPI lo permite).

## A7. Rutas API Laravel (esqueleto)

```text
POST   /api/login
POST   /api/logout
GET    /api/me

# admin
GET|POST          /api/admin/users
PATCH             /api/admin/users/{id}
GET|POST          /api/admin/agents
PATCH             /api/admin/agents/{id}
POST              /api/admin/agents/{id}/assign   { user_id }
DELETE            /api/admin/agents/{id}/assign/{user}
GET               /api/admin/logs

# tester / admin asignado
GET    /api/agents                         # solo asignados (admin: todos)
GET    /api/agents/{id}
POST   /api/agents/{id}/sesiones           # → FastAPI POST /api/sesiones/
POST   /api/agents/{id}/sesiones/{sid}/mensaje
POST   /api/agents/{id}/sesiones/{sid}/documentos
POST   /api/agents/{id}/sesiones/{sid}/juridico
GET    /api/agents/{id}/sesiones/{sid}
GET    /api/agents/{id}/sesiones/{sid}/checklist
POST   /api/agents/{id}/logs/{logId}/feedback

GET    /api/health                         # health del portal Laravel
```

Añadir más proxies **explícitos** solo cuando el contrato del agente lo requiera (informes PDF/DOCX: reenviar binario con `Content-Type` correcto).

## A8. Tests mínimos Laravel

- Feature: login.
- Feature: tester sin pivote → 403 al mensaje.
- Feature: tester con pivote → gateway mockeado (Http::fake) → 200.
- Feature: admin crea agent sin filtrar `secret_key` en response.
- Unit: Form Request rechaza path traversal / campos extra.

## A9. README del repo Laravel

Incluir: arranque, `.env`, cómo generar key compartida con FastAPI, CORS, roles, y advertencia de no exponer `base_url` al browser.

## A10. Criterio de “hecho” (Parte A)

- [ ] PHP/Composer instalados y documentados.
- [ ] Migraciones en Supabase Postgres aplicadas.
- [ ] Sanctum + Spatie roles funcionando.
- [ ] Gateway con `X-Agent-Key` hacia FastAPI real o mock.
- [ ] Rate limit + Form Requests + policies admin.
- [ ] Logs en BD + logs de aplicación sin secretos.
- [ ] `.env.example` completo; `.env` no commiteado.

---

# PARTE B — Frontend Angular (`portal-agentes-web`)

> Instrucciones para la instancia Cursor del **frontend**. Proyecto separado.

## B1. Crear el proyecto

```powershell
cd "C:\Users\unive\OneDrive\Desktop\frank\Agentes"
npx -y @angular/cli@19 new portal-agentes-web --routing --style=scss --ssr=false
cd portal-agentes-web
```

(Usa la versión de Angular que el CLI estable ofrezca si 19 no aplica; documenta la versión en el README.)

Dependencias útiles:

- HttpClient.
- Algún store ligero (signals / servicios) — evitar over-engineering.
- UI: componentes propios simples o Angular Material (una sola librería; no mezclar 3 design systems).

## B2. Configuración y secretos

- `environment.ts` / `environment.development.ts`: solo `apiBaseUrl` (URL del **Laravel**, nunca del FastAPI).
- **Prohibido** poner `X-Agent-Key`, secretos de agentes, o URL interna FastAPI en Angular.
- `.gitignore`: no subir `environment.prod.ts` con URLs secretas si aplica; preferir variables de build.

Ejemplo:

```ts
export const environment = {
  production: false,
  apiBaseUrl: 'http://127.0.0.1:8001/api',
};
```

## B3. Auth y guards

- `AuthService`: login → guarda token Sanctum (memory + `sessionStorage` o cookie según Parte A).
- Interceptor HTTP: `Authorization: Bearer <token>`.
- `AuthGuard`: rutas privadas.
- `RoleGuard`: `admin` vs `tester`.
- Logout limpia token y navega a `/login`.

Rutas sugeridas:

```text
/login
/app/agents                 # lista asignados
/app/agents/:id/chat        # tester
/app/agents/:id/session/:sid
/admin/users
/admin/agents
/admin/assignments
/admin/logs
```

## B4. Vistas

### Login

- Form reactivo; validación cliente; errores del API con códigos (`UNAUTHENTICATED`).

### Tester

- Lista de agentes asignados (nombre, status; **sin** URL/secret).
- Flujo compliance (mínimo viable):
  1. Crear sesión (proxy Laravel).
  2. Chat mensajes.
  3. Upload documento (multipart vía Laravel).
  4. Ver checklist / estatus.
  5. Pedir jurídico si aplica.
- Botón **feedback** (👍/👎 + comentario) → `POST .../feedback` ligado al `agent_log` o a la sesión.

### Admin

- CRUD usuarios (activar/desactivar, asignar rol).
- CRUD agentes (nombre, base_url, secret_key solo en formulario create/edit admin; **nunca** re-mostrar el secret en claro tras guardar — UI tipo “dejar vacío para no cambiar”).
- Asignar tester ↔ agente.
- Dashboard logs (filtros por agente/usuario/fecha) + rating.

## B5. Seguridad front

- No usar `innerHTML` con respuestas del agente sin sanitizar.
- No guardar tokens en `localStorage` si se puede evitar (XSS); si se usa, documentar el riesgo y CSP básica en index.
- Interceptor de errores: 401 → logout; 403 → toast “Sin permiso sobre este agente”; 429 → “Demasiadas solicitudes”; 502 → “Agente no disponible”.
- Deshabilitar double-submit en chat/upload.
- Validar tamaño/tipo de archivo **antes** de subir (alineado a lo que acepta el agente: pdf, docx, etc.).

## B6. Logging en el frontend

- Logger de app: solo en `development` a consola.
- Eventos UX opcionales enviados al backend (no a un SaaS sin consentimiento): “feedback”, “error de carga”.
- **No** enviar a analytics el texto completo de expedientes / PII.
- Errores de red: mensaje genérico al usuario + `code` del API si existe.

## B7. UX del chat (agente compliance)

- Mostrar que el usuario habla con el “módulo de compliance”, no revelar “agentes internos”.
- Estados: enviando, analizando documento (puede tardar), error recuperable.
- No implementar proxy directo a `:8000` (FastAPI).

## B8. Criterio de “hecho” (Parte B)

- [ ] Login contra Laravel.
- [ ] Guards admin/tester.
- [ ] Lista agentes + chat/upload vía Laravel.
- [ ] Feedback del tester.
- [ ] Admin básico (users/agents/assign/logs).
- [ ] Ningún secreto FastAPI en el bundle.
- [ ] README con `ng serve` y `apiBaseUrl`.

---

## Apéndice C — Checklist de integración E2E

1. FastAPI compliance en `:8000` con:

```env
AGENT_AUTH_ENABLED=true
AGENT_CLIENT_LARAVEL_KEY=<mismo valor cifrado en agents.secret_key vía Laravel>
```

2. Laravel en `:8001`, Angular en `:4200`.
3. Crear agent en admin apuntando a `http://127.0.0.1:8000`.
4. Asignar usuario tester.
5. Login tester → crear sesión → mensaje → (opcional) upload.
6. Verificar `agent_logs` y que sin key directa a FastAPI desde browser falle (401).

---

## Apéndice D — Fuera de alcance (no implementar en el MVP)

- Portal Nest/Next de producción (otro consumidor).
- JWT corto firmado Laravel→FastAPI (evolución; hoy API key estática).
- Prisma.
- Proxy catch-all de paths.
- Desplegar el Gestor de producción completo para testing.

---

## Apéndice E — Prompt corto para pegar en Cursor (Parte A)

```text
Lee docs/INSTRUCCIONES_PORTAL_TESTEO_AGENTES.md PARTE A completa.
Crea el proyecto Laravel en …/Agentes/portal-agentes-api según el documento.
Instala PHP/Composer si faltan. Usa Eloquent + Postgres Supabase (no Prisma).
Implementa Sanctum, Spatie roles, migraciones agents/agent_user/agent_logs,
AgentGatewayService con X-Agent-Key, Form Requests, rate limits, policies admin,
y rutas proxy explícitas al contrato /api/sesiones del agente FastAPI.
No expongas base_url/secret_key al cliente. No edites el plan .cursor.
```

## Apéndice F — Prompt corto para pegar en Cursor (Parte B)

```text
Lee docs/INSTRUCCIONES_PORTAL_TESTEO_AGENTES.md PARTE B completa.
Crea Angular en …/Agentes/portal-agentes-web.
Solo habla con el API Laravel (apiBaseUrl). AuthGuard + RoleGuard.
Vistas login, tester (chat/upload/feedback) y admin (users/agents/assign/logs).
Cero secretos FastAPI en el front. Sigue seguridad y logging del documento.
```
