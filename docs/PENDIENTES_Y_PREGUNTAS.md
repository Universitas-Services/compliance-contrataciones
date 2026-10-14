# Pendientes, decisiones y preguntas abiertas

Actualizado: 14/10/2026. Estado: **éxito parcial**. El Analista evalúa los 12 documentos de CA Acto Único Apertura Única y el Jurídico redacta el dictamen (formato de Mariana) a partir del JSON de cada documento. El equipo legal validó el contenido del dictamen; falta cerrar formato, puntajes, persistencia y despliegue definitivo.

## 0. Próxima sesión (15/10, a primera hora)

Corrida completa del 14/10 (`revision_nancy/corrida_2026-10-14/`, configuración de Cloud Run): 12 documentos + dictamen, 0 errores, 0 cortes, ~328.000 tokens, 10,9 min. Nota: **7/10** (Analista 8/10, Jurídico 6/10). **No enviar a Mariana hasta resolver el punto 1.**

1. **Puntajes calculados por código, no por el modelo (prioridad alta).** Hoy el Jurídico calcula Máx / Obtenidos / % / rango y no cuadran con los datos. Recalculado con los pesos 5/3/1 de cada pregunta:
   - Acta de inicio: dictamen 62 · 61,29 %; calculado 69 · 68,12 %.
   - Acta de recepción: dictamen 57,14 %; calculado 70,21 %.
   - Oferta Copikon: dictamen 13,16 %; calculado 0 %.
   - Además etiqueta «Hallazgos Significativos» a documentos con 56 % y 69 % (por la tabla, <84,99 % = Críticos).
   - Plan: calcular en `cuestionario.py`/`llm_client.py` (por documento y global, con rango) y pasarlo al Jurídico ya hecho para que solo lo copie e interprete. Depende de la pregunta legal 1.3 (¿«parcial» suma la mitad o cero?, ¿«no consta» cuenta como perdido?); mientras tanto, regla v1 configurable.
2. **Evidencia legible:** los extractos del pliego e informe aparecen como `[S127]`, `[S18]-[S78]`; traducir a referencias que entienda el usuario (capítulo, punto, tabla).
3. **«No consta» dudosos del pliego** (CAAUPC.16 idioma, 73 confidencialidad, 82, 83, 84): verificar contra el texto (sin tokens) y, si son falsos, mejorar la selección de extractos.
4. Dictamen: exagera algunos hallazgos (CAAUAP.17 «certificación sin firma», que es *parcial*, pasa a «inexistencia de disponibilidad presupuestaria» y a hallazgo raíz) y escribe «entre cinco y seis días» (pregunta 1.2). Citó «arts. 14 y 23 Normas SUNAI» (el 14 es de la LCP). Revisar con Mariana.

## 1. Equipo legal (Mariana y equipo)

Validado: la información del dictamen es correcta. Observación del jefe: «55 páginas es mucho, pero la información está bien».

Preguntas pendientes:
1. **Extensión del entregable.** ¿El documento final va «de 5b hacia abajo»? Es decir: el dictamen (4 secciones), la cobertura del checklist, la conclusión y las recomendaciones, sin las preguntas y respuestas por documento ni las secciones 1–4 del anexo (unas 6–8 páginas).
2. **Conteo de días hábiles.** ¿El día de recepción de ofertas cuenta dentro del plazo? Hoy el modelo a veces cuenta 6 (incluyéndolo) y a veces 5 (sin incluirlo). Ambos dan incumplimiento frente a 7, pero hay que fijar una sola regla en el calendario.
3. **Modelo de puntaje.** ¿Los puntajes 5/3/1 y los umbrales (≥95 sobresaliente, 90–94,99 aceptable, 85–89,99 significativos, <84,99 críticos) se aplican como ellos los entienden? ¿Un «parcial» suma la mitad, o cero? ¿Un «no consta» cuenta como punto perdido o se excluye del máximo? (Necesario para el punto 0.1.)
4. **Nulidad frente a reposición.** ¿El criterio para recomendar nulidad absoluta (Art. 19 LOPA) en vez de reposición (Art. 98 RLCP) está bien razonado?
5. **«No consta» en un ítem crítico.** Hoy da semáforo Amarillo (Rojo solo con incumplimiento demostrado). ¿Están de acuerdo?
6. **Cuestionarios (Nancy):**
   - Validar la tabla APLICA_A (`revision_nancy/APLICA_A_CA_ACTO_UNICO_APERTURA_UNICA.xlsx`).
   - Correcciones: CAAUC.40 sin criticidad; CAAUC.58 inexistente (¿fusionada con la 57?); CAAUNA.6 dice «No Adjudicación»; ACTA_INICIO usa «U.T.» frente a «UCAU»; el art. 107 menciona «Concurso Cerrado»; CAAUAI.32 está recortada; ACTIVIDADES PREVIAS dice «tres () a seis ()».
   - Preguntas dependientes: ya marcadas con `**CONDICIONAL:**` (CAAUIR.14, 20 y 27). Consultar: ¿CAAUIR.18 (declaratoria de desierta) aplica siempre o solo si el concurso quedó desierto?
   - Opcional: aclarar CAAUAI.10.
   - CAAUNA.4/14 y CAANNA.4/5/17 preguntan por el recibo o acuse: ¿qué documento sube el usuario?
7. **Legislación incompleta.** En `basamento-legal/legislacion` la LCP y el RLCP están incompletos (por ejemplo, faltan el art. 67 LCP y el art. 98 RLCP). ¿Quién facilita los textos completos?

## 2. Base de datos (José)

Hoy las sesiones y el JSON de cada documento viven en memoria y en `data/sesiones.json`. Funciona en local, pero **no sobrevive en Cloud Run** (reinicios, escalado, nuevos despliegues).

Preguntas:
1. ¿Dónde se guardan los JSON de cada documento (`json_analista`) de cada persona y expediente? ¿En la BD de la app o en una BD propia del agente?
2. ¿Opción A (recomendada): Nest guarda cada `json_analista` y lo envía al pedir el dictamen (agente sin estado)? ¿U opción B: el agente guarda las sesiones en una BD compartida (Firestore) y Nest solo manda el `sesion_id`?
3. Si es B: ¿qué base de datos, cómo se conecta con la BD de la app y quién es el dueño del dato (usuario ↔ sesión)?
4. ¿Dónde se guardan los archivos subidos (GCS de expedientes)? ¿Se conservan o solo su texto extraído?

## 3. Nest / backend (Frank)

Acordado: el dictamen llega como Markdown (texto plano, sin tablas) y Nest genera el PDF solo al emitir el dictamen jurídico.

Por decidir:
1. **Contenido del Markdown para Nest:** a) dictamen + cobertura + conclusión + recomendaciones en el mismo texto (recomendado), o b) solo el dictamen, con las recomendaciones aparte en JSON.
2. ¿Nest necesita un JSON resumen del dictamen (puntaje global, flag de nulidad, hallazgo raíz, pendientes) además del Markdown?
3. ¿Usa el `json_analista` por documento? ¿Qué campos? (Hoy: estado, respuesta, evidencia, conformes, no_aplica, resumen.)
4. Contrato de la API definitivo cuando José decida la BD (endpoint del dictamen que reciba la lista de JSON, si es la opción A).

## 4. Técnico (nuestro lado)

- [ ] Recortar el entregable según la respuesta del equipo legal (pregunta 1.1) y de Nest (3.1).
- [ ] Fijar la regla del día de recepción en el calendario (pregunta 1.2).
- [x] Preguntas dependientes como condicionales: etiqueta `**CONDICIONAL:**` (CAAUIR.14, CAAUIR.20 y CAAUIR.27, esta última por su «de ser el caso»). Por consultar a Nancy: ¿CAAUIR.18 (declaratoria de desierta) aplica siempre o solo si el concurso quedó desierto?
- [x] Reemplazar un documento al volver a subir el mismo archivo (mismo tipo y nombre). Ofertas o notificaciones con nombres distintos se conservan.
- [x] Modelo vigente: `gemini-3.8-flash` (local) y `google/gemini-3.8-flash` en Vertex `global` (14/10: acta en 45 s frente a 153 s con 2.5-flash). `.env.example` actualizado; `VERTEX_LOCATION=global` soportado; identidad con 8192 tokens (antes se cortaba en 4096).
- [ ] Completar la LCP y el RLCP en `basamento-legal`.
- [x] Tokens (D2, 14/10): medido con modelo simulado; el basamento por lote era <1 % (descartado). La caché implícita de Gemini dio `cache=0` en Vertex global (revertido el reordenamiento; queda el contador `tokens_cache`). Lotes de 15 preguntas en documentos cortos y 10 en largos (`LLM_RUBRICA_LOTE_TAM`, `LLM_RUBRICA_LOTE_TAM_LARGO`): acta −20 % tokens, expediente −6 %.
- [x] Regla «discrepancia entre partes del documento = parcial, no si» (CAAUAI.3, CAAUPC.1).
- [ ] Contratación Directa: cuestionarios en el formato nuevo (cuando Nancy los tenga).
- [ ] Decidir qué hacer con `CONTEXTO_TRABAJO.md` (staged sin commit) y `revision_nancy/` (`.gitignore` o commit).

## 5. GitHub y GCP

1. **GitHub:** `git push` de la rama `claude/project-thread-9itlyv` → PR a `main` (borrador hasta validar APLICA_A, o directo si se acepta la v1).
2. **Despliegue (definir el flujo):** hoy se sube a GitHub y a GCP por separado. Opciones: trigger de Cloud Build conectado a `main` (recomendado) o despliegue manual siempre desde `main`.
3. **Cuestionarios a GCS (con confirmación explícita):**
   - Validar: `python -m scripts.validar_cuestionarios cuestionarios --exigir-aplica-a`
   - Simular: `gcloud storage rsync -r --dry-run --checksums-only cuestionarios gs://compliance-cuestionarios-26265028623` (**ojo:** en `gcloud storage`, `-n` NO es simulación, es «no sobrescribir»: sube los archivos nuevos).
   - Revisar la lista → subida real sin borrar → versionado del bucket.
   - Reiniciar o desplegar Cloud Run para que tome los `.md` nuevos (hay caché en memoria).
4. **Variables de Cloud Run:** `KNOWLEDGE_SOURCE=gcs`, `GCS_BUCKET_CUESTIONARIOS`, `GCS_BUCKET_BASAMENTO`, `LLM_REASONING_EFFORT_RUBRICA=low`, `LLM_MAX_TOKENS_RUBRICA=8192`, `LLM_TEMPERATURE_RUBRICA=0.2`, `FERIADOS_EXTRA`, `LOG_LEVEL=INFO`, `MAX_UPLOAD_MB` (el informe de prueba pesaba 27,6 MB).
5. **Prueba en Cloud Run** con el mismo expediente; comparar con local (~350k tokens en total, ~10 min) y buscar en los logs «Partición por tipo … APLICA_A en N/N».
6. **Estado al 14/10:** revisión `compliance-contrataciones-00012-6ss` (100 % del tráfico), `VERTEX_LOCATION=global`, `GEMINI_MODEL=google/gemini-3.8-flash`, sin `GEMINI_BASE_URL`. Rollback: revisión 00011. En el bucket quedaron por error (inofensivos) `README.md` y 5 `.gitkeep`; decidir si se borran (lo ejecuta el usuario).
7. Recordatorio: mientras no esté la BD (sección 2), las pruebas en Cloud Run deben subir los documentos y pedir el dictamen en la misma sesión y el mismo día.
