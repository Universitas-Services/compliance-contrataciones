# Contrato de integración: Nest y agente de compliance

Versión del 5/11/2026. Este documento es para el equipo de Nest y para cualquier asistente de IA que implemente la integración.

## 1. Resumen

El agente audita documentos de contrataciones públicas con Gemini. Tiene dos operaciones:

| Operación | Ruta | Entrada | Salida |
|---|---|---|---|
| Analizar un documento | `POST /api/analizar` | Un archivo y sus datos | `json_analista` del documento |
| Conversar (opcional) | `POST /api/conversar` | Mensaje, historial y estado del expediente | Respuesta y acciones |
| Emitir el dictamen | `POST /api/dictamen` | Todos los `json_analista` del expediente | Dictamen en Markdown y puntaje |

**El agente no guarda nada.** Nest es dueño de los archivos, los JSON, los dictámenes y el estado del expediente.

Las llamadas son lentas: de segundos a varios minutos. Por eso se hacen desde un proceso de fondo de Nest, nunca durante la petición del usuario.

## 2. Instrucciones para un asistente de IA

Si eres un asistente de IA que implementa esta integración, cumple estas reglas:

1. Llama al agente solo desde el servidor. La clave nunca debe llegar al navegador.
2. Haz las llamadas desde un proceso de fondo o cola de trabajos, no dentro del controlador que atiende al usuario.
3. Implementa los reintentos de la sección 8 tal como están. Un 503 o un 429 no significan que el documento falló.
4. Guarda `json_analista` exactamente como llega. No renombres, filtres ni reordenes campos.
5. Envía a `POST /api/dictamen` esos mismos JSON, sin modificarlos.
6. No muestres `json_analista` al usuario final. Contiene las preguntas internas del cuestionario.
7. No llames a `/api/sesiones`. Esas rutas son del sandbox interno.
8. No inventes campos, códigos ni valores. Si algo no está en este documento, pregunta.
9. Lee la clave de una variable de entorno. No la escribas en el código ni en los logs.

## 3. Conexión

| Dato | Valor |
|---|---|
| URL base | `https://compliance-contrataciones-26265028623.us-east4.run.app` |
| Autenticación | Header `X-Agent-Key: <clave>` en todas las llamadas |
| Variable sugerida en Nest | `COMPLIANCE_AGENT_KEY` |
| Comprobar que el servicio responde | `GET /health`, sin clave |

La clave se entrega por un canal seguro, fuera de este documento.

## 4. Flujo completo

1. El usuario sube un documento y elige su tipo.
2. Nest guarda el archivo, crea un registro en estado `PENDIENTE` y responde de inmediato.
3. Un proceso de fondo llama a `POST /api/analizar`, con los reintentos de la sección 8.
4. Nest guarda el resultado y pasa el registro a `ANALIZADO`, o a `RECHAZADO` si el archivo no sirve.
5. La app avisa al usuario.
6. Cuando el usuario pide el dictamen, otro trabajo de fondo envía los JSON a `POST /api/dictamen`.
7. Nest guarda el Markdown, genera el PDF y avisa al usuario.

El dictamen se puede pedir antes de tener todos los documentos: sale como informe `PARCIAL` e indica los pendientes.

## 5. `POST /api/analizar`

Analiza un documento. La petición es `multipart/form-data`.

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `archivo` | Archivo | Sí | Máximo 30 MB. Formatos en la sección 7.4 |
| `nomenclatura` | Texto | Sí | Código del expediente, por ejemplo `CA-SDEDTEOEL-CA-002-2026` |
| `modalidad` | Catálogo | Sí | Sección 7.1 |
| `tipo_contratacion` | Catálogo | Sí | Sección 7.2 |
| `tipo_documento` | Catálogo | Sí | Sección 7.3 |

Ejemplo:

```bash
curl -X POST "$URL/api/analizar" \
  -H "X-Agent-Key: $COMPLIANCE_AGENT_KEY" \
  -F "archivo=@acta_de_inicio.docx" \
  -F "nomenclatura=CA-SDEDTEOEL-CA-002-2026" \
  -F "modalidad=CA_ACTO_UNICO_APERTURA_UNICA" \
  -F "tipo_contratacion=BIENES" \
  -F "tipo_documento=ACTA_INICIO"
```

Respuesta 200:

```json
{
  "json_analista": {
    "documento_evaluado": "acta_de_inicio.docx",
    "tipo_documento": "ACTA_INICIO",
    "tipo_coincide": true,
    "tipo_contrato": "BIENES",
    "estatus_global": "Rojo",
    "hallazgos": [],
    "resumen": {"evaluados": 26, "conformes": 16, "hallazgos": 10, "no_aplica": 0},
    "conformes": [],
    "no_aplica": [],
    "hechos_clave": {
      "montos": [{"etiqueta": "Presupuesto Base Estimado", "texto": "", "valor_num": 10096939.28, "moneda": "VES"}],
      "plazos": [{"etiqueta": "Acto Público de Recepción y Apertura", "texto": "11/05/2026"}],
      "partes": [],
      "nomenclatura_encontrada": "CA-SDEDTEOEL-CA-002-2026",
      "otros": []
    },
    "observaciones": [{"severidad": "advertencia", "descripcion": "..."}]
  },
  "informe_markdown": "# Informe...",
  "estatus_global": "Rojo",
  "tipo_coincide": true,
  "tipo_detectado": "ACTA_INICIO",
  "metricas": {
    "latencia_ms": 45000,
    "tokens_prompt": 21000,
    "tokens_completion": 3000,
    "tokens_total": 27000,
    "tokens_cache": 0,
    "llamadas_llm": 3
  }
}
```

| Campo | Qué hacer con él |
|---|---|
| `json_analista` | Guardarlo completo. Se envía después al dictamen. Incluye `hechos_clave` (montos, plazos, partes y nomenclatura) y `observaciones`, que el dictamen usa para comparar documentos |
| `informe_markdown` | Informe del documento. Guardarlo; mostrarlo o no al usuario está por decidir (sección 12) |
| `estatus_global` | `Verde`, `Amarillo` o `Rojo`. Sirve para mostrar el estado en la app |
| `tipo_coincide` | Si es `false`, el archivo no corresponde al tipo declarado (sección 9) |
| `tipo_detectado` | Tipo que el agente cree que es, si no coincide. Puede ser `null` |
| `metricas` | Opcional. Sirve para medir tiempos y consumo |

## 6. `POST /api/dictamen`

Emite el dictamen del expediente. La petición es JSON.

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `nomenclatura` | Texto | Sí | Código del expediente |
| `modalidad` | Catálogo | Sí | Sección 7.1 |
| `tipo_contratacion` | Catálogo | Sí | Sección 7.2 |
| `documentos` | Lista de objetos | Sí | Los `json_analista`, sin modificar. Al menos uno |
| `forzar_final` | Booleano | No | `true` emite informe Final aunque falten documentos. Por defecto, `false` |
| `mensaje` | Texto | No | Instrucción adicional. Normalmente no se envía |

El orden de `documentos` no importa: el agente los ordena según el checklist.

Ejemplo de petición:

```json
{
  "nomenclatura": "CA-SDEDTEOEL-CA-002-2026",
  "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA",
  "tipo_contratacion": "BIENES",
  "forzar_final": false,
  "documentos": [
    {
      "documento_evaluado": "acta_de_inicio.docx",
      "tipo_documento": "ACTA_INICIO",
      "tipo_coincide": true,
      "tipo_contrato": "BIENES",
      "estatus_global": "Rojo",
      "hallazgos": [],
      "resumen": {},
      "conformes": [],
      "no_aplica": []
    }
  ]
}
```

Respuesta 200:

```json
{
  "alcance": "PARCIAL",
  "markdown": "# Informe Ejecutivo Parcial de Avance\n\n## 1. Alcance y Metodología\n...",
  "puntaje": {
    "informe": "PARCIAL",
    "regla_parcial": 0.0,
    "documentos": [
      {
        "tipo_documento": "ACTA_INICIO",
        "documento": "acta_de_inicio.docx",
        "maximo": 69,
        "obtenidos": 50,
        "perdidos": 19,
        "porcentaje": 72.46,
        "rango": "Hallazgos Críticos",
        "criticos_no": ["CAAUAI.14"]
      }
    ],
    "global": {"maximo": 803, "obtenidos": 456, "porcentaje": 56.79, "rango": "Hallazgos Críticos"},
    "flag_nulidad_absoluta": true,
    "hallazgo_raiz": {"codigo_pregunta": "CAAUAI.14", "tipo_documento": "ACTA_INICIO"},
    "incluye_adjudicacion": true,
    "revisados": ["Acta de Inicio"],
    "faltantes": ["Contrato (u Orden de Compra/Servicio)"]
  },
  "pendientes": ["NOTIFICACION_NO_ADJUDICADOS", "CONTRATO"],
  "coherencia": [
    {
      "dato": "Monto adjudicado a Distribuidora Ofilar, C.A.",
      "documento_a": "acta_de_adjudicacion.docx",
      "valor_a": "3905511.43 VES",
      "documento_b": "notificacion_ofilar.docx",
      "valor_b": "4905511.43 VES",
      "gravedad": "alta",
      "explicacion": "El monto notificado no coincide con el del acta de adjudicación."
    }
  ]
}
```

| Campo | Qué hacer con él |
|---|---|
| `alcance` | `PARCIAL` o `FINAL` |
| `markdown` | El entregable. Guardarlo y convertirlo a PDF. No trae tablas |
| `puntaje` | Datos calculados por código. Guardarlo; se puede usar en pantallas de la app |
| `pendientes` | Tipos de documento que faltan |
| `coherencia` | Contradicciones entre documentos: montos, fechas, partes o nomenclatura. Lista vacía si no hay. También aparecen en el Markdown. Opcional mostrarlas en la app |

Un expediente de 12 documentos pesa unos 150 KB en JSON y tardó 83 s en la prueba del 5/11.

## 6.1 `POST /api/conversar` (opcional)

Chat con el Coordinador de Compliance, sin estado: Nest guarda la conversación y envía en cada mensaje el historial reciente y el estado del expediente. Responde en 5 a 15 segundos.

Petición:

```json
{
  "usuario_nombre": "Carlos Pérez",
  "ente": "Alcaldía del Municipio Iribarren",
  "expediente": {
    "nomenclatura": "CA-SDEDTEOEL-CA-002-2026",
    "nombre": "Adquisición de insumos tecnológicos",
    "modalidad": "CA_ACTO_UNICO_APERTURA_UNICA",
    "tipo_contratacion": "BIENES",
    "documentos": [],
    "dictamenes": 0
  },
  "historial": [{"rol": "agente", "texto": "Hola, Carlos..."}, {"rol": "usuario", "texto": "..."}],
  "mensaje": "¿Por qué salió rojo el acta de inicio?"
}
```

- `expediente.documentos`: los `json_analista` ya analizados, sin modificar. El agente los usa para explicar resultados.
- Los campos del expediente pueden ir en `null` mientras el usuario no los haya dado.
- `historial`: hasta 60 mensajes; el agente usa los últimos 20.

Respuesta:

```json
{
  "respuesta": "Registré el expediente CA-ALC-IRI-007-2026. ¿Cuál es la modalidad?",
  "acciones": [
    {"accion": "fijar_expediente", "nomenclatura": "CA-ALC-IRI-007-2026", "nombre": "Compra de mobiliario escolar"},
    {"accion": "pedir_documento", "tipo_documento": "ACTIVIDADES_PREVIAS"},
    {"accion": "solicitar_dictamen", "forzar_final": false}
  ]
}
```

| Acción | Qué hace Nest |
|---|---|
| `fijar_expediente` | Guarda los campos que trae (nomenclatura, nombre, modalidad, tipo_contratacion) |
| `pedir_documento` | Muestra el botón para subir ese tipo de documento |
| `solicitar_dictamen` | Lanza `POST /api/dictamen` como en la sección 6 |

El agente solo devuelve códigos de los catálogos; las acciones mal formadas se descartan antes de responder. Los archivos se suben siempre con `POST /api/analizar`: el chat no recibe archivos. Si el usuario pregunta algo ajeno a contrataciones públicas, el agente lo rechaza con amabilidad.

## 7. Catálogos

Los valores se envían exactamente como aparecen aquí. También se pueden leer del agente con `GET /api/catalogo` (con `X-Agent-Key`), que devuelve:

```json
{
  "modalidades": [
    {
      "valor": "CA_ACTO_UNICO_APERTURA_UNICA",
      "nombre": "Concurso Abierto - Acto Único Apertura Única",
      "estado": "disponible",
      "checklist": [{"tipo_documento": "ACTIVIDADES_PREVIAS", "nombre": "Actividades Previas"}]
    }
  ],
  "tipos_contratacion": [{"valor": "BIENES", "nombre": "Bienes"}]
}
```

`estado` es `disponible`, `sin_validar` (tiene cuestionarios sin revisión legal) o `sin_cuestionarios` (no usar). El `checklist` viene en el orden en que se piden los documentos.

### 7.1 `modalidad`

| Valor | Estado |
|---|---|
| `CA_ACTO_UNICO_APERTURA_UNICA` | Disponible y probada con un expediente completo |
| `CONTRATACION_DIRECTA` | Tiene cuestionarios, pero falta la revisión del equipo legal |
| `CA_ACTO_UNICO_APERTURA_DIFERIDA` | Sin cuestionarios: no usar todavía |
| `CA_ACTO_SEPARADO` | Sin cuestionarios: no usar todavía |
| `CONCURSO_CERRADO` | Sin cuestionarios: no usar todavía |
| `CONSULTA_PRECIO` | Sin cuestionarios: no usar todavía |
| `MODALIDADES_EXCLUIDAS` | Sin cuestionarios: no usar todavía |

### 7.2 `tipo_contratacion`

`BIENES`, `OBRAS`, `SERVICIOS`.

### 7.3 `tipo_documento` para `CA_ACTO_UNICO_APERTURA_UNICA`

Son 12 tipos, en este orden:

1. `ACTIVIDADES_PREVIAS`
2. `ACTA_INICIO`
3. `PLIEGO_CONDICIONES`
4. `LLAMADO`
5. `ACTA_RECEPCION_SOBRES`
6. `ACTA_APERTURA_SOBRES`
7. `OFERTAS`
8. `INFORME_EVALUACION_RECOMENDACION`
9. `ADJUDICACION_O_EQUIVALENTE`
10. `NOTIFICACION_ADJUDICADOS`
11. `NOTIFICACION_NO_ADJUDICADOS`
12. `CONTRATO`

Un tipo puede tener varios archivos. Por ejemplo, cada oferta se analiza por separado con `OFERTAS`.

### 7.4 Formatos de archivo

`.pdf`, `.docx`, `.xlsx`, `.xls`, `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.webp`, `.bmp`.

No uses `.txt`: pasa la primera validación, pero el análisis lo rechaza con 400.

## 8. Errores y reintentos

Los errores llegan como JSON con el campo `detail`, salvo los que genere la propia plataforma de Cloud Run.

| Código | Significado | Acción de Nest | ¿Reintentar? |
|---|---|---|---|
| 200 | Correcto | Guardar el resultado | No |
| 400 | Archivo ilegible, por ejemplo un PDF escaneado sin texto reconocible | Marcar `RECHAZADO` y pedir una copia más nítida | No |
| 401 | Falta la clave o no es válida | Registrar el error y avisar al equipo técnico | No |
| 413 | Archivo de más de 30 MB | Marcar `RECHAZADO` | No |
| 415 | Extensión no permitida | Marcar `RECHAZADO` | No |
| 422 | Datos inválidos, por ejemplo un valor fuera de catálogo | Corregir la integración | No |
| 429 | Gemini o Cloud Run saturados | Esperar con tiempo creciente | Sí |
| 502 | Respuesta incompleta del modelo | Esperar con tiempo creciente | Sí, hasta 3 veces |
| 503 | Instancia ocupada | Esperar los segundos de `Retry-After` | Sí |
| 504 | Tiempo agotado hacia el modelo | Esperar con tiempo creciente | Sí, hasta 3 veces |
| Sin respuesta | Conexión cortada | Esperar con tiempo creciente | Sí, hasta 3 veces |

Con carga, el 503 es normal. En la prueba del 5/11, sin reintentos fallaba el 93 % de un pico de 1000 documentos; con reintentos terminaron todos.

Si la respuesta se corta, Nest no sabe si el análisis terminó. Reintentar es correcto, aunque puede consumir tokens otra vez.

Pseudocódigo de referencia:

```ts
const TIEMPO_MAXIMO_MS = 30 * 60 * 1000;
const ESPERAS_429_S = [15, 30, 60, 120];
const MAX_FALLOS_TEMPORALES = 3;

async function llamarConReintentos(llamada) {
  const inicio = Date.now();
  let intentos429 = 0;
  let fallos = 0;

  while (Date.now() - inicio < TIEMPO_MAXIMO_MS) {
    let r;
    try {
      r = await llamada({ timeoutMs: 15 * 60 * 1000 });
    } catch {
      r = null; // conexión cortada o tiempo agotado
    }

    if (r?.status === 200) return { ok: true, datos: await r.json() };

    if (r?.status === 503 && r.headers.get("retry-after")) {
      await dormir(Number(r.headers.get("retry-after")) * 1000);
      continue;
    }
    if (r?.status === 429) {
      const i = Math.min(intentos429++, ESPERAS_429_S.length - 1);
      await dormir(ESPERAS_429_S[i] * 1000);
      continue;
    }
    if (!r || [502, 503, 504].includes(r.status)) {
      if (++fallos > MAX_FALLOS_TEMPORALES) break;
      await dormir(15000 * fallos);
      continue;
    }
    return { ok: false, definitivo: true, status: r.status, detalle: await r.text() };
  }
  return { ok: false, definitivo: false };
}
```

Si el resultado es `definitivo: false`, el trabajo pasa a `ERROR` y el usuario puede reintentarlo.

## 9. Reglas de negocio

- **Documento en la casilla equivocada:** si `tipo_coincide` es `false`, el análisis responde 200, pero el documento no suma al puntaje y su tipo sigue pendiente. Nest debe avisar al usuario y permitirle reemplazarlo. No debe contarlo como entregado.
- **Reemplazar un documento:** si el usuario sube una versión corregida, Nest sustituye el JSON anterior. Si envía los dos al dictamen, ambos cuentan.
- **Dictamen Parcial y Final:** por defecto es `PARCIAL` si falta algún documento. `forzar_final: true` emite `FINAL` aunque falten.
- **Sin memoria entre documentos:** cada análisis revisa un solo documento. Las contradicciones entre documentos las busca el dictamen, que recibe todos los JSON juntos, y las devuelve en `coherencia`. Por eso Nest debe enviar el `json_analista` completo. En la medición del 9/11, analizar sin memoria dio resultados dentro de la variación normal del modelo.
- **Lo que ve el usuario final:** el entregable es el dictamen. No debe ver las preguntas del cuestionario.

## 10. Datos que debe guardar Nest

Modelo sugerido; los nombres se pueden adaptar.

**Expediente**

| Campo | Descripción |
|---|---|
| `id` | Identificador interno |
| `nomenclatura` | Código del expediente |
| `modalidad` | Catálogo 7.1 |
| `tipo_contratacion` | Catálogo 7.2 |

**Documento**

| Campo | Descripción |
|---|---|
| `id`, `expediente_id` | Identificadores |
| `tipo_documento` | Catálogo 7.3 |
| `ruta_archivo` | Dónde guarda Nest el archivo |
| `estado` | `PENDIENTE`, `PROCESANDO`, `ANALIZADO`, `RECHAZADO` o `ERROR` |
| `json_analista` | JSON completo. Se recomienda `jsonb` |
| `informe_markdown` | Informe del documento |
| `estatus_global`, `tipo_coincide` | Copias para consultar y mostrar en pantallas |
| `error` | Último error, si existe |

**Dictamen**

| Campo | Descripción |
|---|---|
| `id`, `expediente_id` | Identificadores |
| `estado` | `PENDIENTE`, `PROCESANDO`, `LISTO` o `ERROR` |
| `alcance`, `markdown`, `puntaje`, `pendientes` | Campos de la respuesta |
| `ruta_pdf` | PDF generado por Nest |

Para el dictamen se envían los documentos en estado `ANALIZADO`, incluidos los que tienen `tipo_coincide: false`: el agente sabe no contarlos.

## 11. Capacidad y límites

| Dato | Valor actual |
|---|---|
| Tiempo de espera por llamada | 15 minutos |
| Tiempo normal de análisis | Cerca de 1 minuto; el pliego tardó 2 |
| PDF escaneado de 15 páginas | De 3 a 9 minutos |
| Análisis simultáneos por instancia | 8 |
| Escaneados simultáneos por instancia | 2 |
| Instancias máximas hoy | 10, es decir, hasta 80 análisis a la vez |
| Llamadas simultáneas recomendadas desde Nest | Hasta 60 |

Resultados de la prueba de carga del 5/11, con Gemini simulado:

| Escenario | Resultado |
|---|---|
| 1000 a la vez, hasta 32 instancias, con reintentos | 1000 de 1000 en 9 minutos |
| 1000 a la vez, 10 instancias, con reintentos | 999 de 1000 en 15 minutos |
| 500 a la vez con 20 % de rechazos simulados | 499 de 500 en 7 minutos |

Esa prueba no incluyó Gemini real ni OCR. El límite real con muchos usuarios lo pondrá Gemini.

## 12. Por decidir con el equipo de Nest

1. ¿Nest ya tiene una cola de trabajos? Si no, hay que elegir una. Con esa cola no hace falta cambiar el agente.
2. ¿Se muestra al usuario el `informe_markdown` de cada documento, o solo el dictamen?
3. ¿La app usará `puntaje` en pantallas, o solo el Markdown?
4. ¿Hay documentos de más de 30 MB? Si los hay, habría que diseñar una subida por GCS.

## 13. Lista de comprobación

- [ ] La clave se lee de una variable de entorno y solo se usa en el servidor.
- [ ] Las llamadas se hacen desde un proceso de fondo con 15 minutos de tiempo de espera.
- [ ] Hay reintentos para 429, 502, 503, 504 y conexión cortada.
- [ ] 400, 401, 413, 415 y 422 no se reintentan.
- [ ] Nest no lanza más de 60 llamadas simultáneas.
- [ ] `json_analista` se guarda y se reenvía sin cambios.
- [ ] Reemplazar un documento sustituye su JSON.
- [ ] `tipo_coincide: false` genera un aviso al usuario.
- [ ] `json_analista` no se muestra al usuario final.

Pruebas mínimas antes de producción:

1. Analizar un `.docx` válido y comprobar que se guarda el JSON.
2. Analizar un PDF escaneado legible.
3. Subir un PDF en blanco y comprobar que queda `RECHAZADO`.
4. Simular un 503 con `Retry-After: 1` y comprobar el reintento.
5. Declarar un tipo equivocado y comprobar el aviso de `tipo_coincide: false`.
6. Pedir un dictamen con documentos faltantes y comprobar que sale `PARCIAL`.
7. Pedir un dictamen con los 12 tipos y comprobar que sale `FINAL` y que se genera el PDF.
