# Pendientes, decisiones y preguntas abiertas

Actualizado: 16/10/2026. Estado: **éxito parcial**. El Analista evalúa los 12 documentos de CA Acto Único Apertura Única y el Jurídico redacta el dictamen (formato de Mariana) a partir del JSON de cada documento. El equipo legal validó el contenido del dictamen; falta cerrar formato, puntajes, persistencia y despliegue definitivo.

## 0. Estado al 21/10 y plan

**21/10:** respuestas de Mariana y Nancy integradas en la sección 1 (CAAUIR.18, no hay reglamento nuevo, entregable sin preguntas). Sigue sin respuesta el valor de «parcial» y «no consta» (se mantiene 0). OCR con Gemini de la LCP (Decreto 1.399) y el RLCP (Decreto 6.708) en curso para completar el basamento. Vertex `global` dio muchos 429 el 20 y el 21/10: configurar un modelo de respaldo antes de producción.

**Pendiente desde el 16/10:** prueba completa en Cloud Run (revisión 00013) desde el sandbox: los 12 documentos de CA Acto Único Apertura Única + dictamen jurídico. Revisar: puntajes del dictamen = cálculo del código, plazos en 5 días, CAAUPC.16 (idioma) ya no «no consta», evidencia legible, hallazgo raíz CAAUAI.14, nulidad por haber adjudicación. Si sale bien → enviar a Mariana (punto 4).

**Hecho el 15/10** (commits `7bb230f`, `e978e61`, `b452f1d`, `e4037d9`; desplegado en la revisión 00013):
- Puntajes, flag, hallazgo raíz, fase e informe Parcial/Final calculados por código (`app/agents/puntaje.py`); el dictamen guarda `puntaje` (JSON para Nest). Validado con el modelo real regenerando el dictamen desde los JSON del 14/10 (`revision_nancy/corrida_2026-10-14/DICTAMEN_v2…`, `…v3…`): cifras copiadas exactas, raíz CAAUAI.14, nulidad justificada por la adjudicación.
- Regla de días hábiles (el día del acto no cuenta) en el Analista y el Jurídico; verificado: acta y pliego dan 5 días.
- Título oficial del dictamen («# Informe Ejecutivo Parcial de Avance / Final de Cierre»).
- Evidencia legible y corrección de extractos (detalle en los puntos 2 y 3).

### Plan del 15/10 (referencia)

Corrida completa del 14/10 (`revision_nancy/corrida_2026-10-14/`, configuración de Cloud Run): 12 documentos + dictamen, 0 errores, 0 cortes, ~328.000 tokens, 10,9 min. Nota: **7/10** (Analista 8/10, Jurídico 6/10). **No enviar a Mariana hasta resolver el punto 1.**

1. **[HECHO 15/10, validado con el modelo real] Puntajes calculados por código, no por el modelo.** Módulo `app/agents/puntaje.py`; el Jurídico recibe un bloque «RESULTADOS CUANTITATIVOS CALCULADOS POR EL SISTEMA» y el dictamen guarda `puntaje` (JSON para Nest). Regla v1: parcial = 0 (`PUNTAJE_VALOR_PARCIAL`), N/A fuera del máximo. Hoy el Jurídico calcula Máx / Obtenidos / % / rango y no cuadran con los datos. Recalculado con los pesos 5/3/1 de cada pregunta:
   - Acta de inicio: dictamen 62 · 61,29 %; calculado 69 · 68,12 %.
   - Acta de recepción: dictamen 57,14 %; calculado 70,21 %.
   - Oferta Copikon: dictamen 13,16 %; calculado 0 %.
   - Además etiqueta «Hallazgos Significativos» a documentos con 56 % y 69 % (por la tabla, <84,99 % = Críticos).
   - Plan: calcular en código y pasarlo al Jurídico ya hecho para que solo lo copie e interprete. Lo calculable según el prompt oficial del dictamen (ver 1.3):
     - Máx / Obtenidos / % por documento y **puntaje global**, con su **rango** (≥95 sobresaliente; 90–94,99 aceptable; 85–89,99 significativos; <84,99 críticos).
     - **Flag de Riesgo de Nulidad Absoluta:** al menos un **«no»** en una pregunta CRÍTICA (5).
     - **Hallazgo raíz:** el primer «no» crítico en la fase más temprana del expediente (orden cronológico de los 12 documentos). El 14/10 el modelo eligió CAAUAP.17, que es *parcial*; con la regla sería CAAUAI.14.
     - **Informe Final de Cierre** (12 documentos auditados) o **Parcial de Avance** (menos de 12), con la lista de revisados y faltantes.
   - Regla v1 mientras legal confirma (configurable): «si» suma el peso; «parcial» y «no consta» suman 0; N/A (por tipo o condicional) se excluye del máximo.
2. **[HECHO 15/10] Evidencia legible:** los extractos del pliego e informe aparecen como `[S127]`, `[S18]-[S78]`; traducir a referencias que entienda el usuario (capítulo, punto, tabla).
3. **[HECHO 15/10] «No consta» dudosos del pliego** — revisados contra el texto: solo CAAUPC.16 (idioma, en «2. Carta Oferta») era falso; 73, 82, 83 y 84 no aparecen en el pliego (reales). Corregido: ancla de la palabra más rara de la pregunta y el cronograma siempre en preguntas de plazos. (CAAUPC.16 idioma, 73 confidencialidad, 82, 83, 84): verificar contra el texto (sin tokens) y, si son falsos, mejorar la selección de extractos.
4. Dictamen: exagera algunos hallazgos (CAAUAP.17 «certificación sin firma», que es *parcial*, pasa a «inexistencia de disponibilidad presupuestaria» y a hallazgo raíz) y escribe «entre cinco y seis días» (pregunta 1.2). Citó «arts. 14 y 23 Normas SUNAI» (el 14 es de la LCP). Revisar con Mariana.

## 1. Equipo legal (Mariana y equipo)

Validado: la información del dictamen es correcta. Observación del jefe: «55 páginas es mucho, pero la información está bien».

Preguntas pendientes:
1. **Extensión del entregable.** **Respondido (21/10, Mariana):** el dictamen final va **sin las preguntas**: el usuario no debe ver ninguna pregunta del cuestionario. Pendiente técnico: quitar del entregable todo lo que exponga preguntas (y confirmar si los códigos tipo «CAAUAI.14» se pueden mostrar o hay que describir el hallazgo sin código).
2. **Conteo de días hábiles.** ¿El día de recepción de ofertas cuenta dentro del plazo? Hoy el modelo a veces cuenta 6 (incluyéndolo) y a veces 5 (sin incluirlo).
   - **Respuesta (validada por el equipo legal, 15/10):** **no cuenta**. El plazo empieza el día hábil siguiente a la disponibilidad del pliego y el día del acto es el vencimiento: los días mínimos deben transcurrir completos *entre* ambos. En el expediente de prueba: del 04/05 al 08/05 = **5 días** (incumple los 7). Implementada el 15/10 en el Analista y el Jurídico.
3. **Modelo de puntaje.** ¿Los puntajes 5/3/1 y los umbrales (≥95 sobresaliente, 90–94,99 aceptable, 85–89,99 significativos, <84,99 críticos) se aplican como ellos los entienden? ¿Un «parcial» suma la mitad, o cero? ¿Un «no consta» cuenta como punto perdido o se excluye del máximo? (Necesario para el punto 0.1.)
   - **Confirmado (prompt oficial del dictamen):** pesos 5/3/1, máximo = suma de las preguntas, los 4 umbrales, flag con al menos un «no» crítico, hallazgo raíz = primer crítico en la fase más temprana, informe Final (12) o Parcial (<12). El informe Parcial es correcto.
   - **Sin respuesta:** el valor de «parcial» y de «no consta». Se usa la regla v1 del punto 0.1.
   - **Corregido el 15/10:** el flag lo calcula `app/agents/puntaje.py` y se activa solo con **«no»** en un crítico, como dice el texto oficial. (El semáforo del Analista por documento sigue en Rojo con «no» o «parcial» crítico: es otra métrica, la del documento, no el flag del dictamen.)
   - «Parcial» = 0 y «no consta» = 0: regla v1 elegida por el usuario el 15/10 según la lectura literal del formato oficial («sumatoria de sus preguntas»). Falta que Mariana lo confirme explícitamente.
4. **Nulidad frente a reposición.** ¿El criterio para recomendar nulidad absoluta (Art. 19 LOPA) en vez de reposición (Art. 98 RLCP) está bien razonado?
   - **Respuesta (validada por el equipo legal, 15/10):** depende de la fase. **Antes de la adjudicación** → reposición (Art. 98 RLCP, norma especial). **Con la adjudicación ya dictada** y un vicio insubsanable de orden público → nulidad absoluta (Art. 19 LOPA). Si el vicio impide continuar antes de adjudicar → cancelación o decaimiento del procedimiento.
   - Aplicación (hecha el 15/10): el código indica al Jurídico si el expediente contiene la adjudicación. El expediente de prueba **sí la contiene**, así que la nulidad es coherente; con solo el acta de inicio corresponde reposición (como hizo el dictamen parcial del 14/10).
5. **«No consta» en un ítem crítico.** Hoy da semáforo Amarillo (Rojo solo con incumplimiento demostrado). ¿Están de acuerdo?
   - Coherente con el prompt oficial (el flag solo se activa con «no»). Se mantiene salvo que legal diga otra cosa.
6. **Cuestionarios (Nancy):**
   - Tabla APLICA_A (`revision_nancy/APLICA_A_CA_ACTO_UNICO_APERTURA_UNICA.xlsx`): **Nancy la ojeó y le parece bien (21/10)**, sin revisión detallada. Se mantiene la v1 y la cotejamos nosotros con la LCP y el RLCP completos.
   - Correcciones: CAAUC.40 sin criticidad; CAAUC.58 inexistente (¿fusionada con la 57?); CAAUNA.6 dice «No Adjudicación»; ACTA_INICIO usa «U.T.» frente a «UCAU»; el art. 107 menciona «Concurso Cerrado»; CAAUAI.32 está recortada; ACTIVIDADES PREVIAS dice «tres () a seis ()».
   - Preguntas dependientes: marcadas con `**CONDICIONAL:**` (CAAUIR.14, 20 y 27). **CAAUIR.18 aplica en todos los casos (Mariana/Nancy, 21/10): no es condicional.**
   - Opcional: aclarar CAAUAI.10.
   - CAAUNA.4/14 y CAANNA.4/5/17 preguntan por el recibo o acuse: ¿qué documento sube el usuario?
     - **Respuesta (validada por el equipo legal, 15/10):** la notificación **con el acuse de recibo** firmado y sellado por el contratista (o el comprobante de entrega si es electrónica); solo el acuse prueba la fecha desde la que corren los lapsos. Falta: indicarlo en la carga de documentos (Nest). En el expediente de prueba se subieron oficios sin acuse; por eso esas preguntas salen «no consta».
7. **Legislación incompleta.** En `basamento-legal/legislacion` la LCP y el RLCP están incompletos (por ejemplo, faltan el art. 67 LCP y el art. 98 RLCP). ¿Quién facilita los textos completos?
   - **15/10:** el usuario reunirá unas 9 leyes y reformas en texto completo para cargarlas en `basamento-legal` (y en el bucket de basamento). Prioridad: LCP (Decreto 1.399, 2014) y RLCP completos.
   - **Respondido (21/10, Nancy):** **no existe un Reglamento nuevo de 2026**; el «Decreto 5.364» que mencionó la búsqueda era un error. El vigente es el RLCP de 2009 (Decreto 6.708), que es el que se carga en el basamento. Si en el futuro sale uno nuevo, se evaluará entonces.
   - Las leyes sirven para que el agente cite con el texto exacto; lo que es criterio del equipo (puntaje, reglas del dictamen) lo sigue decidiendo legal.

## 2. Base de datos (José)

Hoy las sesiones y el JSON de cada documento viven en memoria y en `data/sesiones.json`. Funciona en local, pero **no sobrevive en Cloud Run** (reinicios, escalado, nuevos despliegues).

**Decidido (15/10, con Edwards y Frank): opción A.** Los JSON de cada documento se guardan en **Nest**; el agente no tendrá base de datos propia. Consecuencias técnicas:
- [ ] Endpoint del Jurídico **sin estado**: recibe la lista de `json_analista` del expediente (más modalidad, tipo de contrato y nomenclatura) y devuelve el dictamen, sin depender de la sesión en memoria.
- [ ] El `json_analista` debe llevar lo que necesitan el puntaje y el dictamen: código, estado y documento (los pesos 5/3/1 se toman del cuestionario por código).
- [ ] Archivos originales: el agente **no** necesita guardarlos (los procesa y devuelve el JSON). Si se conservan, lo decide Nest; el agente no requiere un bucket de expedientes.
- Las sesiones en memoria quedan solo para el sandbox y las pruebas.

Preguntas originales (respondidas por la decisión; se conservan como referencia):
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
4. Contrato de la API definitivo: con la opción A decidida, definir con Frank el endpoint del dictamen que recibe la lista de JSON (campos, tamaño y orden de los documentos).

## 4. Técnico (nuestro lado)

- [ ] Recortar el entregable según la respuesta del equipo legal (pregunta 1.1) y de Nest (3.1).
- [x] Regla del día de recepción (pregunta 1.2, validada por legal): el día del acto no se cuenta. En el Analista y el Jurídico desde el 15/10.
- [x] Preguntas dependientes como condicionales: etiqueta `**CONDICIONAL:**` (CAAUIR.14, CAAUIR.20 y CAAUIR.27, esta última por su «de ser el caso»). Por consultar a Nancy: ¿CAAUIR.18 (declaratoria de desierta) aplica siempre o solo si el concurso quedó desierto?
- [x] Reemplazar un documento al volver a subir el mismo archivo (mismo tipo y nombre). Ofertas o notificaciones con nombres distintos se conservan.
- [x] Modelo vigente: `gemini-3.8-flash` (local) y `google/gemini-3.8-flash` en Vertex `global` (14/10: acta en 45 s frente a 153 s con 2.5-flash). `.env.example` actualizado; `VERTEX_LOCATION=global` soportado; identidad con 8192 tokens (antes se cortaba en 4096).
- [ ] Completar la LCP y el RLCP en `basamento-legal`.
- [x] Tokens (D2, 14/10): medido con modelo simulado; el basamento por lote era <1 % (descartado). La caché implícita de Gemini dio `cache=0` en Vertex global (revertido el reordenamiento; queda el contador `tokens_cache`). Lotes de 15 preguntas en documentos cortos y 10 en largos (`LLM_RUBRICA_LOTE_TAM`, `LLM_RUBRICA_LOTE_TAM_LARGO`): acta −20 % tokens, expediente −6 %.
- [x] Regla «discrepancia entre partes del documento = parcial, no si» (CAAUAI.3, CAAUPC.1).
- [ ] Contratación Directa: cuestionarios en el formato nuevo. **Nancy no ha empezado (21/10)**; sin fecha.
- [ ] Decidir qué hacer con `CONTEXTO_TRABAJO.md` (staged sin commit) y `revision_nancy/` (`.gitignore` o commit). `revision_nancy/corrida_2026-10-14/` guarda la corrida completa de referencia (informes, JSON, dictamen, `resumen.json`).
- [ ] Opcional: script oficial en `scripts/` para correr el expediente completo con un comando (comparar versiones). Ayer se usó uno temporal fuera del repo.

## 5. GitHub y GCP

1. **GitHub:** `git push` de la rama `claude/project-thread-9itlyv` → PR a `main` (borrador hasta validar APLICA_A, o directo si se acepta la v1).
2. **Despliegue (definir el flujo):** hoy se sube a GitHub y a GCP por separado. Opciones: trigger de Cloud Build conectado a `main` (recomendado) o despliegue manual siempre desde `main`.
3. **Cuestionarios a GCS (con confirmación explícita):**
   - Validar: `python -m scripts.validar_cuestionarios cuestionarios --exigir-aplica-a`
   - Simular: `gcloud storage rsync -r --dry-run --checksums-only cuestionarios gs://compliance-cuestionarios-26265028623` (**ojo:** en `gcloud storage`, `-n` NO es simulación, es «no sobrescribir»: sube los archivos nuevos).
   - Revisar la lista → subida real sin borrar → versionado del bucket.
   - Reiniciar o desplegar Cloud Run para que tome los `.md` nuevos (hay caché en memoria).
4. **Variables de Cloud Run:** `LLM_PROVIDER=vertex`, `VERTEX_LOCATION=global`, `GEMINI_MODEL=google/gemini-3.8-flash` (ya sin `GEMINI_BASE_URL`), `KNOWLEDGE_SOURCE=gcs`, `GCS_BUCKET_CUESTIONARIOS`, `GCS_BUCKET_BASAMENTO`, `LLM_REASONING_EFFORT_RUBRICA=low`, `LLM_MAX_TOKENS_RUBRICA=8192`, `LLM_TEMPERATURE_RUBRICA=0.2`, `FERIADOS_EXTRA`, `LOG_LEVEL=INFO`, `MAX_UPLOAD_MB=30` (el informe de prueba pesaba 27,6 MB). Opcionales con valor por defecto en el código: `LLM_RUBRICA_LOTE_TAM=15`, `LLM_RUBRICA_LOTE_TAM_LARGO=10`, `LLM_MAX_TOKENS_IDENTIDAD=8192`.
5. **Pruebas (14/10):** en Cloud Run se probaron el acta (40 s, 20.935 tokens con lotes de 15) y el pliego (66 s); los logs muestran la partición APLICA_A, `Rúbrica: N ítems en M lote(s)` y `finish_reason=stop` en todas las llamadas. El expediente completo se corrió en local con la configuración de Cloud Run (~328k tokens, 10,9 min); falta repetirlo en Cloud Run cuando haya sesiones persistentes (sección 2).
6. **Estado al 19/10:** revisión `compliance-contrataciones-00014-r2m` (100 % del tráfico, desplegada el 16/10: el sandbox acumula los documentos en el mismo expediente con `sesion_id`), `VERTEX_LOCATION=global`, `GEMINI_MODEL=google/gemini-3.8-flash`, sin `GEMINI_BASE_URL`. Rollback: revisión 00013. En el bucket quedaron por error (inofensivos) `README.md` y 5 `.gitkeep`; decidir si se borran (lo ejecuta el usuario).
7. **Revisión del despliegue (14/10, pendiente antes de producción):**
   - Servicio público (`allUsers` + ingress `all`), protegido solo por `X-Agent-Key`: cuando Nest sea el único cliente, exigir también IAM (cuenta de servicio de Nest).
   - Concurrencia 160 por instancia con `max-instances=1`: bajarla a 10–20 (análisis de ~45 s).
   - `CORS_ORIGINS` solo admite el sandbox local: añadir el origen de Nest o dejarlo vacío si Nest llama de servidor a servidor.
   - `AGENT_CLIENT_NEST_KEY` sin configurar (solo existe la clave «laravel-testing»).
   - Despliegue manual desde la PC: definir el flujo (punto 2).
8. Recordatorio: mientras no esté la BD (sección 2), las pruebas en Cloud Run deben subir los documentos y pedir el dictamen en la misma sesión y el mismo día.

## 6. Cómo arrancar el entorno local (sandbox)

En PowerShell, desde la carpeta del proyecto (`compliance-contrataciones-clean`):

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

- Usar `python -m uvicorn` (el comando `uvicorn` a secas no se encuentra en este PC).
- Sandbox: http://127.0.0.1:8000/sandbox
  - **Local:** dejar vacío «API base» (usa el `.env`: AI Studio, sin clave de agente).
  - **Cloud Run:** «API base» = `https://compliance-contrataciones-26265028623.us-east4.run.app` y la clave `X-Agent-Key` (cliente laravel-testing). `CORS_ORIGINS` de Cloud Run ya admite `http://127.0.0.1:8000` y `http://localhost:8000`.
- Expediente completo: recargar la página antes de empezar, subir los documentos seguidos (el contador «Expediente: N documentos» debe subir) y pedir el dictamen al final. «Nuevo expediente» empieza de cero.
- Detener el servidor: `Ctrl + C` en la terminal.
- Si `Activate.ps1` da error («la ejecución de scripts está deshabilitada»), no hace falta activar el entorno: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000`. O permitir scripts solo para tu usuario: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
