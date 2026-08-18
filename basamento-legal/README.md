# Basamento legal (KB normativa)

Corpus local de normas venezolanas de contrataciones / control fiscal.
**No es un RAG vectorial:** se recuperan artículos y extractos por cita
(`Art. 19 LOPA`) y palabras clave, con tope de caracteres por llamada al LLM.

Las tres carpetas son **tipos de fuente**, no slots del expediente (acta, pliego, etc.):

| Carpeta | Contenido |
|---------|-----------|
| `legislacion/` | 15 MD — LCP, RLCP, LOPA, LOCGR, SUNAI, LOJCA, corrupción, precios justos, etc. |
| `doctrina-administrativa/` | 9 MD — oficios CGR/SNC, resoluciones, UCAU, responsabilidad social |
| `sentencias/` | 2 MD — SPA-TSJ (p. ej. Manuitt) |

Loader: `app/agents/knowledge/basamento_loader.py`.
Se inyecta en Coordinador (chat), Analista (rúbrica/informe) y Jurídico.

Citar **solo** lo recuperado o lo que traiga el cuestionario. Si el artículo no
está en el extracto → marcar fundamento pendiente; no inventar numeración.

Algunos MD de origen (p. ej. LCP/RLCP) pueden estar incompletos respecto del
texto oficial: el loader no inventa artículos ausentes del archivo.
