# Contrato de integración: Nest y agente de compliance

Versión del 10/11/2026. Este documento es para el equipo de Nest y para cualquier asistente de IA que implemente la integración. Todo lo descrito aquí ya está desplegado en la URL de la sección 3.

## 1. Qué es el agente

El agente de compliance audita expedientes de **contrataciones públicas venezolanas** (LCP, RLCP, Normas SUNAI y leyes relacionadas). Lo usa un funcionario de un ente público (por ejemplo, una alcaldía) para revisar, documento por documento, si un procedimiento de compra cumple la ley, y para obtener al final un dictamen jurídico.

Por dentro trabaja con tres roles, pero el usuario solo ve uno, el «Coordinador de Compliance»:

- **Coordinador (chat):** conversa con el usuario, registra los datos del expediente, le pide los documentos en orden y le explica los resultados. Responde dudas de contrataciones públicas y rechaza temas ajenos.
- **Analista:** revisa cada documento con el cuestionario de su tipo (decenas de preguntas con su peso legal) y devuelve los hallazgos y un semáforo.
- **Jurídico:** con todos los documentos analizados, calcula el puntaje, busca contradicciones entre documentos y redacta el dictamen.

El agente usa Gemini por dentro. Nest no llama a Gemini: solo llama a las rutas de este contrato.

### 1.1 Glosario

| Término | Qué es |
|---|---|
| Ente | Organismo público dueño del expediente (alcaldía, gobernación, servicio desconcentrado…) |
| Expediente | Un procedimiento de contratación completo, identificado por su nomenclatura (por ejemplo, `CA-SDEDTEOEL-CA-002-2026`) |
| Modalidad | Tipo de procedimiento: concurso abierto, consulta de precios, contratación directa… Define qué documentos se piden |
| Tipo de contratación | Bienes, obras o servicios. Cambia algunas preguntas del cuestionario |
| Checklist | Lista ordenada de los documentos que exige la modalidad (12 en Concurso Abierto Acto Único Apertura Única) |
| `json_analista` | Resultado del análisis de un documento: hallazgos, conformes, datos clave. Es interno: lo guarda Nest y lo reenvía, pero no se le muestra al usuario |
| Semáforo (`estatus_global`) | Verde, Amarillo o Rojo para cada documento |
| Hallazgo | Algo que no cumple o no consta en el documento, con su gravedad |
| Dictamen | Informe jurídico final en Markdown. **Parcial** si faltan documentos, **Final** si están todos |
| Contradicción (`coherencia`) | Un mismo dato que difiere entre documentos (monto, fecha, nomenclatura, adjudicatario) |

### 1.2 Resumen de las rutas

Tiene estas operaciones:

| Operación | Ruta | Entrada | Salida |
|---|---|---|---|
| Leer los catálogos | `GET /api/catalogo` | Nada | Modalidades, tipos de contratación y checklist |
| Analizar un documento | `POST /api/analizar` | Un archivo y sus datos | `json_analista` del documento |
| Conversar | `POST /api/conversar` | Mensaje, historial y estado del expediente | Respuesta y acciones |
| Emitir el dictamen | `POST /api/dictamen` | Todos los `json_analista` del expediente | Dictamen en Markdown, puntaje y contradicciones |

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
10. Sigue el flujo de la sección 4: el saludo y los mensajes de estado del chat los genera Nest; las respuestas a lo que escribe el usuario, `/api/conversar`.
11. Aplica solo las `acciones` de `/api/conversar` que trae la respuesta; no deduzcas otras del texto.
12. Filtra siempre por ente: un usuario solo ve los expedientes de su ente. El agente no lo controla.

## 3. Conexión

| Dato | Valor |
|---|---|
| URL base | `https://compliance-contrataciones-26265028623.us-east4.run.app` |
| Autenticación | Header `X-Agent-Key: <clave>` en todas las llamadas |
| Variable sugerida en Nest | `COMPLIANCE_AGENT_KEY` |
| Comprobar que el servicio responde | `GET /health`, sin clave |

### 3.1 La clave de Nest

- **Qué es:** una clave propia de Nest (el agente la identifica como `nest-production`), distinta de la de pruebas. Se crea cuando el backend esté listo para conectarse y se entrega por un canal seguro, fuera de este documento.
- **Dónde va:** solo en el servidor de Nest, en la variable `COMPLIANCE_AGENT_KEY` (o en su gestor de secretos). Nunca en el código, en el repositorio, en el navegador ni en una app móvil.
- **Cómo se usa:** en cada llamada a `/api/...`, en el header `X-Agent-Key`. `GET /health` no la necesita.
- **Logs:** no registrar el valor de la clave ni el header `X-Agent-Key`.
- **Primera prueba:** `GET /api/catalogo` con la clave debe responder 200; sin clave o con una equivocada, 401.
- **Si se cambia la clave** (por ejemplo, si se filtró): el agente deja de aceptar la anterior y Nest recibe 401 en todas las llamadas. Basta con actualizar la variable con el valor nuevo; no hace falta tocar código. Un 401 no se reintenta (sección 8): se avisa al equipo técnico.

## 4. Flujo completo

La pantalla principal de un expediente es un chat con el Coordinador, más la lista de documentos del checklist. Así funciona de principio a fin (el sandbox interno del agente hace exactamente esto):

**A. Inicio de sesión y lista de expedientes**

1. El usuario entra a la app con su cuenta. Nest sabe su nombre y su ente.
2. Nest muestra solo los expedientes de ese ente, con su progreso y riesgo (sección 10).
3. Al abrir la app, Nest pide una vez `GET /api/catalogo` y lo guarda en memoria: modalidades, tipos y checklists.

**B. Registro del expediente (chat)**

4. El usuario crea un expediente. Nest muestra un saludo fijo, sin llamar al agente. Texto sugerido: «Hola, {nombre}. Soy el Coordinador de Compliance de Contrataciones de {ente}. Te acompaño a auditar un expediente documento por documento. Para empezar, ¿cuál es el número del expediente y cómo se llama?».
5. Cada mensaje del usuario va a `POST /api/conversar` con el historial y el estado del expediente. Nest muestra la `respuesta` y aplica las `acciones`: con `fijar_expediente` guarda nomenclatura, nombre, modalidad o tipo.
6. Opcional: mientras falten la modalidad o el tipo, Nest puede mostrar botones con las opciones del catálogo (solo modalidades `disponible`). Al tocar uno, Nest guarda el dato directamente, sin llamar al agente.

**C. Carga y análisis de documentos**

7. Con el expediente registrado, Nest muestra el botón para subir el siguiente documento: el primero del checklist que aún no tenga un documento `ANALIZADO` con `tipo_coincide: true`. Si `/api/conversar` devolvió `pedir_documento`, se usa ese tipo.
8. El usuario sube el archivo. Nest lo guarda, crea el documento en estado `PENDIENTE`, agrega al chat un mensaje del usuario («Subí acta.pdf como Acta de Inicio») y responde de inmediato.
9. Un proceso de fondo llama a `POST /api/analizar`, con los reintentos de la sección 8. Mientras tanto, el documento está en `PROCESANDO` y el chat muestra «Analizando…».
10. Al terminar, Nest guarda el `json_analista` y el informe, pasa el documento a `ANALIZADO` y agrega al chat un mensaje del agente con el semáforo y un enlace al informe. Si `tipo_coincide` es `false`, agrega un aviso de que el archivo no corresponde. Si respondió 400, 413 o 415, lo pasa a `RECHAZADO` y muestra el motivo (`detail`).
11. Nest pide el siguiente documento (paso 7). El usuario puede preguntar en cualquier momento por el chat, por ejemplo «¿por qué salió rojo el acta?»: el agente responde con los `json_analista` que recibe en `expediente.documentos`.

**D. Dictamen**

12. El usuario pide el dictamen con un botón o por el chat (acción `solicitar_dictamen`). Si faltan documentos, sale `PARCIAL`; el usuario puede pedir el `FINAL` de todas formas con `forzar_final: true`.
13. Un proceso de fondo envía todos los `json_analista` a `POST /api/dictamen`. Nest guarda la respuesta, genera el PDF a partir del Markdown y agrega al chat un mensaje del agente con el puntaje global, las contradicciones (`coherencia`) y el enlace al dictamen.

**E. Historial**

14. Todo queda guardado en Nest: conversación, archivos, análisis y dictámenes. Si el usuario vuelve otro día, el expediente se abre igual que lo dejó y sigue donde quedó.

Los mensajes del chat que genera Nest (saludo, «Subí…», «Analizando…», resultado del análisis o del dictamen) se guardan en el historial como los demás, y se envían a `/api/conversar` en los mensajes siguientes. Así el agente sabe qué pasó.

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
| `informe_markdown` | Informe del documento. No muestra códigos de pregunta. Guardarlo; mostrarlo o no al usuario está por decidir (sección 12) |
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
| `markdown` | El entregable. Guardarlo y convertirlo a PDF. No trae tablas ni códigos de pregunta (los códigos solo van en los campos de datos, como `puntaje.hallazgo_raiz.codigo_pregunta`) |
| `puntaje` | Datos calculados por código. Guardarlo; se puede usar en pantallas de la app |
| `pendientes` | Tipos de documento que faltan |
| `coherencia` | Contradicciones entre documentos: montos, fechas, partes o nomenclatura. Lista vacía si no hay. También aparecen en el Markdown. Opcional mostrarlas en la app |

Un expediente de 12 documentos pesa unos 150 KB en JSON y tardó 83 s en la prueba del 5/11.

## 6.1 `POST /api/conversar`

Chat con el Coordinador de Compliance. **La app lo usa desde el inicio** (decidido el 10/11): el usuario conversa con el agente durante todo el expediente. Es sin estado: Nest guarda la conversación y envía en cada mensaje el historial reciente y el estado del expediente. Responde en 5 a 15 segundos.

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

Errores: los mismos de la sección 8 (401, 422, 429, 502, 503). Como el usuario está esperando la respuesta, conviene un tiempo de espera de 60 segundos y, si falla, mostrar «No pude responder, intenta de nuevo» en vez de reintentar varios minutos.

El agente solo devuelve códigos de los catálogos; las acciones mal formadas se descartan antes de responder. `pedir_documento` solo trae tipos del checklist de la modalidad, y en el mensaje que completa el registro la respuesta siempre incluye `pedir_documento` con el primer documento pendiente. Los archivos se suben siempre con `POST /api/analizar`: el chat no recibe archivos. Si el usuario pregunta algo ajeno a contrataciones públicas, el agente lo rechaza con amabilidad.

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

Un tipo puede tener varios archivos. Por ejemplo, cada oferta se analiza por separado con `OFERTAS`, y cada notificación con `NOTIFICACION_ADJUDICADOS` o `NOTIFICACION_NO_ADJUDICADOS`. Todos los `json_analista` que se envíen al dictamen cuentan.

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
| `alcance`, `markdown`, `puntaje`, `pendientes`, `coherencia` | Campos de la respuesta |
| `ruta_pdf` | PDF generado por Nest |

**Conversación:** mensajes con `rol` (`usuario` o `agente`), texto y fecha, por expediente.

Para el dictamen se envían los documentos en estado `ANALIZADO`, incluidos los que tienen `tipo_coincide: false`: el agente sabe no contarlos.

Datos útiles para la pantalla de expedientes:

| Columna | De dónde sale |
|---|---|
| Progreso | Tipos del checklist con al menos un documento `ANALIZADO` y `tipo_coincide: true`, sobre el total del checklist de `GET /api/catalogo` (por ejemplo, 9/12) |
| Riesgo | Del último dictamen: `puntaje.global.rango` y `puntaje.flag_nulidad_absoluta`. Antes del primer dictamen, el peor `estatus_global` de los documentos |
| Estado | Lo define Nest (por ejemplo, configurando, activo, cerrado). El agente no guarda estados |

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
- [ ] Las modalidades y el checklist se leen de `GET /api/catalogo`; solo se ofrecen las de `estado: disponible`.
- [ ] Cada mensaje va a `/api/conversar`, se aplican sus `acciones` y se guarda la conversación.

Pruebas mínimas antes de producción:

1. Analizar un `.docx` válido y comprobar que se guarda el JSON.
2. Analizar un PDF escaneado legible.
3. Subir un PDF en blanco y comprobar que queda `RECHAZADO`.
4. Simular un 503 con `Retry-After: 1` y comprobar el reintento.
5. Declarar un tipo equivocado y comprobar el aviso de `tipo_coincide: false`.
6. Pedir un dictamen con documentos faltantes y comprobar que sale `PARCIAL`.
7. Pedir un dictamen con los 12 tipos y comprobar que sale `FINAL` y que se genera el PDF.
