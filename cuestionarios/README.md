# Cuestionarios de auditoría

Estructura:

```text
cuestionarios/
  <MODALIDAD_ENUM>/
    <TIPO_DOCUMENTO_ENUM>.md
```

Los nombres de carpeta y archivo coinciden con los enums de la API
(`Modalidad`, `TipoDocumento`) para poder cargarlos por ruta.

## Cómo se usan

Al subir un documento, el backend busca
`cuestionarios/<modalidad>/<tipo>.md`:

1. Si existe → inyecta el markdown completo al Analista y persiste la rúbrica
   con códigos oficiales (`CAAUAP.1`, `CDAAP.1`, etc.).
2. Si no → usa el placeholder de `app/agents/knowledge/preguntas.py`.

Loader: `app/agents/knowledge/cuestionarios_loader.py`.

## Formato de cada pregunta

```text
**CAAUAI.14** ¿pregunta completa?
**RANGO DE CRITICIDAD: CRÍTICO: 5**
**Respuesta: SI; NO; N/A**
**APLICA_A:** BIENES
**ACCIÓN LEGAL:** …
**ADVERTENCIA PARA LA GERENCIA:** …
**FUNDAMENTO LEGAL VIOLENTADO EN CASO DE NO:** …
```

- `APLICA_A`: `BIENES`, `SERVICIOS`, `OBRAS` (separados por `;`) o `TODOS`.
  Las preguntas que no aplican al tipo de contrato de la sesión se marcan N/A
  sin llamar al LLM. Sin etiqueta (o con un valor inválido) el tipo se
  infiere del texto de la pregunta.
- Una condición previa al `¿` («Si la contratación…, ¿…?») se conserva.

Validar antes de copiar al repo o subir a GCS:

```bash
python -m scripts.validar_cuestionarios [carpeta] [--exigir-aplica-a]
```

## Estado actual

| Modalidad | Archivos |
|-----------|----------|
| `CA_ACTO_UNICO_APERTURA_UNICA` | 12 cuestionarios (oficiales, cableados) |
| `CONTRATACION_DIRECTA` | 11 cuestionarios (oficiales, cableados) |
| Resto de modalidades | Pendiente |

Más adelante estos `.md` podrán vivir en GCS con la misma jerarquía.
