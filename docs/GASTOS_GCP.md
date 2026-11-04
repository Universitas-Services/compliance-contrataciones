# Gastos de GCP — compliance-contrataciones

Actualizado: 22/10/2026. Período: 5/10/2026 al 21/10/2026 (el export de facturación llega con hasta ~1 día de retraso).

**Fuente:** export de facturación en BigQuery, tabla `chatbot-academy-wp.gcp_billing_data.gcp_billing_export_v1_01F3BF_E7F1E5_966A76`, filtrada por `project.id = 'marine-alchemy-510716-j5'`. Es la misma fuente del tablero de Looker Studio («Gastos de Google Cloud Platform»). Consultas al final del documento.

## 1. Resumen

| Concepto | USD |
|---|---|
| Costo bruto (lo que muestra el tablero) | **9,81** |
| Descuentos aplicados por Google (tipo `DISCOUNT`, en Vertex AI y Cloud Run) | −2,28 |
| **Costo neto (lo que se paga)** | **7,53** |

El tablero muestra el costo **bruto**; conviene añadirle el neto (ver §7).

## 2. Por servicio

| Servicio | Bruto | Descuento | Neto | Qué es |
|---|---|---|---|---|
| Vertex AI | 6,50 | −2,19 | 4,31 | Gemini desde Cloud Run y desde scripts con la credencial de gcloud (pruebas, transcripción de leyes) |
| Gemini API | 1,79 | 0 | 1,79 | Gemini por AI Studio (pruebas en local con el `.env`, 12–16/10) |
| Cloud Run | 1,08 | −0,09 | 0,99 | Servicio del agente; incluye la instancia fija encendida (§4) |
| Cloud Build | 0,35 | 0 | 0,35 | Construcción de imágenes en cada despliegue |
| Artifact Registry | 0,07 | 0 | 0,07 | Almacenamiento de las imágenes (≈0,7 GB) |
| Secret Manager | 0,03 | 0 | 0,03 | Clave del agente |
| Cloud Storage | 0,00 | 0 | 0,00 | Buckets de cuestionarios y basamento |

**Gemini (Vertex AI + Gemini API) es el 85 % del gasto.**

## 3. Precios unitarios observados (bruto, por millón de tokens)

| Modelo | Entrada | Salida |
|---|---|---|
| `gemini-3.8-flash` (Vertex `global` y AI Studio) | **1,50 USD** | **7,50 USD** |
| `gemini-2.5-flash` (Vertex, usado hasta el 14/10) | 0,30 USD | 2,50 USD (con razonamiento) |

- La salida cuesta 5 veces más que la entrada: cada token que el modelo escribe pesa mucho más que los que lee.
- `gemini-3.8-flash` es ~5× más caro en entrada y ~3× en salida que `2.5-flash`, pero dio respuestas claramente mejores (ver `PENDIENTES_Y_PREGUNTAS.md`). Vertex aplicó un descuento de ~34 % sobre el bruto.

Tokens consumidos (5–21/10): 3.8-flash en Vertex 1,11 M de entrada y 0,34 M de salida; en AI Studio 1,01 M y 0,27 M; 2.5-flash 1,56 M y 0,66 M.

## 4. Por día y qué pasó

| Día | Neto USD | Qué pasó |
|---|---|---|
| 5–7/10 | 2,25 | Primeras pruebas en Cloud Run con `gemini-2.5-flash` |
| 8–11/10 | 0,02 | Sin actividad (solo almacenamiento) |
| 12/10 | 0,55 | Pruebas locales (AI Studio): cuestionarios nuevos, calendario |
| 13/10 | 1,21 | Pruebas locales: expediente completo y dictamen |
| 14/10 | 0,97 | Cambio a 3.8-flash en Cloud Run, despliegues, expediente completo |
| 15/10 | 0,28 | Puntajes por código, regeneración del dictamen, pliego |
| 16/10 | 0,54 | Pruebas de documentos y sandbox |
| 17–19/10 | 0,03 | Sin actividad |
| 20/10 | 0,79 | Prueba del expediente en Cloud Run (429 y reinicios) + instancia fija desde las 14:40 |
| 21/10 | 0,90* | Instancia fija ~15 h + transcripción de la LCP y el RLCP con Gemini (51 páginas) |

\* El 21/10 aún puede subir: el tablero mostraba ~1,5 USD brutos.

## 5. Instancia fija de Cloud Run

- `min-instances=1` mantiene una instancia encendida aunque no haya uso, para que el sandbox no pierda el expediente.
- Costo real medido: ~147.800 segundos (≈41 h) por **0,74 USD** → **≈0,018 USD por hora, ≈0,43 USD por día, ≈13 USD por mes** si se dejara siempre encendida.
- Regla: encenderla solo durante una prueba de expediente completo y apagarla al terminar (comandos en `PENDIENTES_Y_PREGUNTAS.md` §8). En producción no hará falta: los JSON los guarda Nest y el agente no necesita memoria entre peticiones.

## 6. Costo por documento y por expediente (gemini-3.8-flash, CA Acto Único Apertura Única)

Con la corrida completa del 14/10 (12 documentos: 263.001 tokens de entrada y 48.860 de salida) y los precios del §3:

| Unidad | Bruto | Neto (−34 %) |
|---|---|---|
| Documento corto (actas, llamado, notificaciones; ~15–24 mil tokens) | 0,04–0,06 USD | 0,03–0,04 USD |
| Pliego de condiciones (~86 mil tokens) | ~0,20 USD | ~0,13 USD |
| **Expediente completo** (12 documentos) | **~0,76 USD** | **~0,50 USD** |
| Dictamen jurídico (1 llamada) | ~0,05 USD | ~0,03 USD |
| **Expediente + dictamen** | **~0,80 USD** | **~0,53 USD** |

### Proyección mensual (solo Gemini, neto, sin la instancia fija)

| Expedientes al mes | USD al mes |
|---|---|
| 10 | ~5 |
| 50 | ~27 |
| 200 | ~106 |

Cloud Run en reposo (mínimo 0) cuesta casi nada; con tráfico real, el CPU por petición fue ~0,31 USD en todo el período. Cloud Build y Artifact Registry dependen de cuántas veces se despliegue.

## 7. Qué falta / recomendaciones

1. **Alerta de presupuesto** (Facturación → Presupuestos y alertas): por ejemplo, correo al 50 %, 90 % y 100 % de 15 USD al mes para este proyecto. Hoy no hay ninguna.
2. **Tablero de Looker Studio:**
   - Mostrar **neto** además de bruto (restar `credits`).
   - Gráfico por **SKU de Gemini** (entrada / salida / imagen), que es donde se decide el costo.
   - Indicador de **costo por expediente** (costo de Gemini del día ÷ expedientes procesados).
   - Aviso de que el último día está incompleto (retraso del export).
3. **Costo por expediente en producción:** hoy cada documento ya devuelve sus tokens (`metricas` en el JSON). Si Nest los guarda junto al `json_analista`, se puede calcular el costo real de cada expediente y por cliente sin depender de la facturación.
4. **Separar ambientes:** las pruebas locales con AI Studio (Gemini API) y las de Cloud Run (Vertex) van al mismo proyecto. Conviene que las pruebas locales usen Vertex con la misma configuración que Cloud Run, o un proyecto aparte, para leer el tablero sin mezclar pruebas y uso real.
5. **Decidir el modelo con números:** 2.5-flash cuesta ~70 % menos, pero dio peor calidad. Si el volumen crece, evaluar 3.8-flash solo para el pliego e informe (documentos largos y críticos) y un modelo más barato para documentos cortos, comparando resultados pregunta por pregunta.
6. **Saturación (429) de Vertex `global`:** no cuesta (las llamadas rechazadas no se cobran) pero alarga las pruebas; ver el modelo de respaldo en `PENDIENTES_Y_PREGUNTAS.md`.

## 8. Consultas (BigQuery, solo lectura)

```sql
-- Bruto, descuentos y neto por servicio
SELECT service.description AS servicio,
       ROUND(SUM(cost), 4) AS bruto,
       ROUND(SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)), 4) AS descuentos,
       ROUND(SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)), 4) AS neto
FROM `chatbot-academy-wp.gcp_billing_data.gcp_billing_export_v1_01F3BF_E7F1E5_966A76`
WHERE project.id = 'marine-alchemy-510716-j5'
GROUP BY servicio ORDER BY bruto DESC;

-- Por SKU (tokens de Gemini, instancia fija, etc.)
SELECT service.description AS servicio, sku.description AS sku,
       ROUND(SUM(usage.amount_in_pricing_units), 2) AS cantidad,
       ANY_VALUE(usage.pricing_unit) AS unidad, ROUND(SUM(cost), 4) AS bruto
FROM `chatbot-academy-wp.gcp_billing_data.gcp_billing_export_v1_01F3BF_E7F1E5_966A76`
WHERE project.id = 'marine-alchemy-510716-j5'
GROUP BY servicio, sku HAVING bruto > 0.005 ORDER BY bruto DESC;

-- Neto por día (hora de Venezuela)
SELECT DATE(usage_start_time, 'America/Caracas') AS dia,
       ROUND(SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)), 4) AS neto
FROM `chatbot-academy-wp.gcp_billing_data.gcp_billing_export_v1_01F3BF_E7F1E5_966A76`
WHERE project.id = 'marine-alchemy-510716-j5'
GROUP BY dia ORDER BY dia;
```
