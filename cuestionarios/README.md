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

## Estado actual

| Modalidad | Archivos |
|-----------|----------|
| `CA_ACTO_UNICO_APERTURA_UNICA` | 12 cuestionarios (oficiales, cableados) |
| `CONTRATACION_DIRECTA` | 11 cuestionarios (oficiales, cableados) |
| Resto de modalidades | Pendiente |

Más adelante estos `.md` podrán vivir en GCS con la misma jerarquía.
