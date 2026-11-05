# Dictamen jurídico para Nest (sin estado)

Propuesta para revisar con Frank. El agente no guarda los expedientes: Nest conserva el JSON de cada documento y lo envía al pedir el dictamen.

## Flujo

1. Por cada documento, Nest llama a `POST /api/analizar` y guarda el `json_analista` de la respuesta, asociado al expediente.
2. Para el dictamen, Nest envía todos los `json_analista` del expediente a `POST /api/dictamen`.
3. El agente calcula los puntajes, redacta el dictamen y lo devuelve. No guarda nada.
4. Nest guarda el Markdown y genera el PDF.

## `POST /api/analizar`

Autenticación: header `X-Agent-Key`. La petición es `multipart/form-data`:

| Campo | Ejemplo |
|---|---|
| `archivo` | el documento (máximo 25 MB) |
| `nomenclatura` | `CA-SDEDTEOEL-CA-002-2026` |
| `modalidad` | `CA_ACTO_UNICO_APERTURA_UNICA` |
| `tipo_contratacion` | `BIENES` |
| `tipo_documento` | `ACTA_INICIO` |

Respuesta (200):

```json
{
  "json_analista": {},
  "informe_markdown": "# Informe...",
  "estatus_global": "Rojo",
  "tipo_coincide": true,
  "tipo_detectado": null,
  "metricas": {"latencia_ms": 45000, "tokens_total": 27000}
}
```

Nest guarda `json_analista` sin modificarlo. El agente no conserva nada.

Errores: los de la tabla de abajo, más 400 (archivo ilegible), 413 (demasiado grande), 415 (extensión no permitida) y 502 (respuesta incompleta del modelo; se puede reintentar).

## `POST /api/dictamen`

Autenticación: header `X-Agent-Key`, como en el resto de la API.

Petición:

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

- `documentos`: los `json_analista` tal como los devolvió el análisis, sin modificarlos. El orden no importa: el agente los ordena según el checklist de la modalidad.
- `forzar_final`: `true` emite el informe Final aunque falten documentos. Por defecto es Parcial si falta alguno.
- `mensaje` (opcional): instrucción adicional para el Jurídico.

Respuesta (200):

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
  "pendientes": ["NOTIFICACION_NO_ADJUDICADOS", "CONTRATO"]
}
```

Errores:

| Código | Causa |
|---|---|
| 401 | Falta `X-Agent-Key` o no es válida |
| 422 | Lista vacía o un documento sin `tipo_documento` válido |
| 429 | Gemini saturado tras los reintentos; reintentar en unos minutos |
| 503 | Instancia ocupada; reintentar después de los segundos que indica `Retry-After` |

## Para tener en cuenta

- **Tiempo:** el dictamen de 12 documentos tardó 83 s en la prueba del 5/11, y puede tardar más si Gemini está saturado. El cliente necesita un tiempo de espera de al menos 5 minutos.
- **Tamaño:** los 12 JSON de la prueba pesan unos 150 KB.
- **Reintentos:** Nest debe reintentar los 503 respetando `Retry-After`. No significan que el documento falló.
- **Sin memoria entre documentos:** `POST /api/analizar` revisa cada documento por separado. Las incoherencias entre documentos quedan para el dictamen.
- **Documentos en la casilla equivocada:** llegan con `tipo_coincide: false`, no suman al puntaje y su tipo sigue figurando como pendiente.

## Por decidir con Frank

1. ¿Nest guarda el `json_analista` completo tal como llega?
2. ¿Le sirve la respuesta síncrona, o prefiere que el análisis y el dictamen corran en segundo plano y consultar cuándo terminan?
3. ¿Usa `puntaje` para mostrar datos en la app, o solo el Markdown?
