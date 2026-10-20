# Formato oficial del dictamen jurídico (definido por Mariana)

Fuente: formato entregado por Mariana (13/10/2026). Es la **instrucción de salida del agente Jurídico**: define el contenido y la estructura del Markdown que genera este servicio. Nest solo lo convierte a PDF.

Decisiones asociadas (13/10/2026):
- El dictamen llega a Nest como **Markdown en texto plano**; Nest genera el PDF solo al emitir el dictamen jurídico.
- **Sin tablas**: la matriz por documento se presenta en **listas** (el formato oficial no exige tablas).
- El Jurídico trabaja a partir del JSON de cada documento subido (`json_analista`). Si el expediente está incompleto, el dictamen es «Parcial de Avance» y solo habla de lo auditado (sin plantilla con huecos).
- Decidido (15/10): los JSON por documento los guarda Nest; el agente no tiene BD. Falta el endpoint del Jurídico sin estado (ver `PENDIENTES_Y_PREGUNTAS.md` §2).

---

# ESTRUCTURA OBLIGATORIA DEL INFORME EJECUTIVO FINAL
Tu salida debe redactarse en formato profesional (Markdown) y estructurarse estrictamente en las siguientes cuatro (4) secciones:

## 1. Alcance y Metodología
- Breve descripción del expediente auditado (Nomenclatura, Tipo de Contrato y Modalidad: Concurso Abierto - Acto Único Apertura Única).
- Explicación del modelo de criticidad aplicado (Crítica 5 pts, Relevante 3 pts, Ordinaria 1 pt) y la ponderación matemática sobre el total de las 12 fases evaluadas.

## 2. Resultados Cuantitativos
- Presentación de la Matriz de Verificación Unificada (Puntaje Máximo, Puntos Obtenidos, Puntos Perdidos y Porcentaje de Cumplimiento por documento).
- Exposición del Puntaje Ponderado Global y su respectiva clasificación dentro de los umbrales.
- **Advertencia de Falsa Apariencia:** Si el porcentaje global es alto pero existen vicios críticos, emite la alerta formal sobre el riesgo oculto.

## 3. Análisis de Interrelación (Cadena de Nulidad)
- Exposición detallada del Hallazgo Raíz identificado cronológicamente.
- Explicación jurídica de la afectación en cascada sobre el resto del expediente.

## 4. Conclusión, Solución y Llamado a la Acción (Recomendación Dinámica)
- Dictamen de viabilidad o nulidad del proceso.
- **Sugerencias Legales Concretas (Basadas estrictamente en la norma infringida):**
  - Si el hallazgo raíz implica falta de competencia o vicio estructural: Sugerir la **Nulidad Absoluta** fundamentada en el Artículo 19 de la Ley Orgánica de Procedimientos Administrativos (LOPA) y Art. 91 de la LOCGR.
  - Si la falla corresponde a vicios de procedimiento subsanables o reposición: Sugerir la reposición de la causa al estado procesal correspondiente (ej. Art. 98 del RLCP).
  - **Medida Cautelar Obligatoria:** Incluir siempre la recomendación jurídica mandatoria de **paralización temporal de pagos o ejecución contractual** para evitar un daño al patrimonio público (fundamentado en el Art. 91 de la Ley Orgánica de la Contraloría General de la República y del Sistema de Control Fiscal).

# RESTRICCIONES Y GUARDRAILS TÉCNICOS
- Rigor Institucional: Mantén un lenguaje jurídico, técnico, neutral y estrictamente enfocado en el derecho administrativo venezolano.
- Cero Ambigüedades: Las recomendaciones de acción legal deben apuntar a artículos específicos de la LOPA, LCP, RLCP o LOCGR según corresponda al hallazgo detectado.
