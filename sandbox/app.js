"use strict";
/*
 * Sandbox guiado: se comporta como la app (Nest) frente al agente.
 * - El agente no guarda nada: el historial vive en una carpeta de la PC elegida por el usuario
 *   (Chrome/Edge) o, si no hay carpeta, en el navegador (IndexedDB).
 * - Solo usa las rutas del contrato: GET /api/catalogo, POST /api/analizar y POST /api/dictamen,
 *   con los reintentos de la sección 8 de docs/API_DICTAMEN_NEST.md.
 *
 * Carpeta: <carpeta>/<ente>/<expediente>/
 *   expediente.json            estado completo (lo que el sandbox vuelve a leer)
 *   originales/                archivos subidos
 *   analisis/NN_TIPO_archivo.json y .md   json_analista e informe de cada documento
 *   dictamenes/AAAA-MM-DD_hhmm_ALCANCE.md
 */

// ---------- Almacenamiento local ----------

const DB_NOMBRE = "compliance-sandbox";
const CLAVE_USUARIO = "compliance-sandbox-usuario";
let db = null;
let carpeta = null; // FileSystemDirectoryHandle con permiso concedido

function abrirDB() {
  return new Promise((ok, mal) => {
    const req = indexedDB.open(DB_NOMBRE, 2);
    req.onupgradeneeded = () => {
      const d = req.result;
      if (!d.objectStoreNames.contains("expedientes")) d.createObjectStore("expedientes", { keyPath: "id" });
      if (!d.objectStoreNames.contains("config")) d.createObjectStore("config");
    };
    req.onsuccess = () => ok(req.result);
    req.onerror = () => mal(req.error);
  });
}

function tx(modo, fn, almacen = "expedientes") {
  return new Promise((ok, mal) => {
    const t = db.transaction(almacen, modo);
    const r = fn(t.objectStore(almacen));
    t.oncomplete = () => ok(r && r.result);
    t.onerror = () => mal(t.error);
  });
}

const soportaCarpeta = () => "showDirectoryPicker" in window;
const slug = (s) => String(s || "sin-nombre").normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60) || "sin-nombre";

/** Nombre de archivo seguro y corto, conservando la extensión. */
function slugArchivo(nombre) {
  const m = String(nombre).match(/^(.*?)(\.[A-Za-z0-9]{1,5})?$/);
  return slug(m[1]) + (m[2] || "").toLowerCase();
}

async function dirExpediente(e, crear = true) {
  const ente = await carpeta.getDirectoryHandle(slug(e.ente), { create: crear });
  return ente.getDirectoryHandle(`${slug(e.nomenclatura || "nuevo")}__${e.id.slice(0, 8)}`, { create: crear });
}

async function escribir(dir, ruta, contenido) {
  const partes = ruta.split("/");
  for (const p of partes.slice(0, -1)) dir = await dir.getDirectoryHandle(p, { create: true });
  const f = await dir.getFileHandle(partes[partes.length - 1], { create: true });
  const w = await f.createWritable();
  await w.write(contenido);
  await w.close();
}

/** Guarda el estado y los archivos legibles (informes, JSON y dictámenes) del expediente. */
async function guardarExpediente(e) {
  e.actualizado = new Date().toISOString();
  if (!carpeta) return tx("readwrite", (s) => s.put(e));
  // Si cambió la nomenclatura, la carpeta vieja ("nuevo__id") queda: se renombra al mover.
  if (e.carpeta_nombre && e.carpeta_nombre !== `${slug(e.nomenclatura || "nuevo")}__${e.id.slice(0, 8)}`) {
    try {
      const ente = await carpeta.getDirectoryHandle(slug(e.ente));
      await ente.removeEntry(e.carpeta_nombre, { recursive: true });
    } catch { /* ya no existe */ }
  }
  const dir = await dirExpediente(e);
  e.carpeta_nombre = dir.name;
  for (const [i, d] of e.documentos.entries()) {
    if (d.estado !== "ANALIZADO" || d.escrito) continue;
    const base = `analisis/${String(i + 1).padStart(2, "0")}_${d.tipo}_${slugArchivo(d.archivo).replace(/\.[a-z0-9]+$/, "")}`;
    await escribir(dir, `${base}.json`, JSON.stringify(d.json_analista, null, 2));
    await escribir(dir, `${base}.md`, d.informe_markdown || "");
    d.escrito = true;
  }
  for (const dic of e.dictamenes) {
    if (dic.escrito) continue;
    await escribir(dir, `dictamenes/${dic.fecha.slice(0, 16).replace(/[T:]/g, "-")}_${dic.alcance}.md`, dic.markdown || "");
    dic.escrito = true;
  }
  await escribir(dir, "expediente.json", JSON.stringify(e, null, 2));
}

async function guardarOriginal(e, archivo) {
  if (!carpeta) return;
  try {
    await escribir(await dirExpediente(e), `originales/${slugArchivo(archivo.name)}`, archivo);
  } catch (err) {
    console.warn("No se pudo copiar el original", err);
  }
}

async function leerExpedientes() {
  if (!carpeta) return tx("readonly", (s) => s.getAll());
  const lista = [];
  for await (const [, ente] of carpeta.entries()) {
    if (ente.kind !== "directory") continue;
    for await (const [, dir] of ente.entries()) {
      if (dir.kind !== "directory") continue;
      try {
        const f = await (await dir.getFileHandle("expediente.json")).getFile();
        lista.push(JSON.parse(await f.text()));
      } catch { /* carpeta ajena o incompleta */ }
    }
  }
  return lista;
}

/** Recupera la carpeta elegida antes; si el navegador pide permiso, queda pendiente de un clic. */
async function recuperarCarpeta() {
  if (!soportaCarpeta()) return "sin_soporte";
  const h = await tx("readonly", (s) => s.get("carpeta"), "config");
  if (!h) return "sin_elegir";
  if ((await h.queryPermission({ mode: "readwrite" })) === "granted") {
    carpeta = h;
    return "lista";
  }
  return "sin_permiso";
}

async function elegirCarpeta() {
  const h = await window.showDirectoryPicker({ id: "compliance", mode: "readwrite" });
  await tx("readwrite", (s) => s.put(h, "carpeta"), "config");
  const previos = carpeta ? await leerExpedientes() : await tx("readonly", (s) => s.getAll());
  carpeta = h;
  for (const e of previos) { // pasa lo guardado a la carpeta nueva
    delete e.carpeta_nombre;
    e.documentos.forEach((d) => { d.escrito = false; });
    e.dictamenes.forEach((d) => { d.escrito = false; });
    await guardarExpediente(e);
  }
}

async function reconectarCarpeta() {
  const h = await tx("readonly", (s) => s.get("carpeta"), "config");
  if (h && (await h.requestPermission({ mode: "readwrite" })) === "granted") carpeta = h;
}

function leerUsuario() {
  try { return JSON.parse(localStorage.getItem(CLAVE_USUARIO)); } catch { return null; }
}

// ---------- Llamadas al agente ----------

const TIEMPO_LLAMADA_MS = 15 * 60 * 1000;
const TIEMPO_MAXIMO_MS = 30 * 60 * 1000;
const ESPERAS_429_S = [15, 30, 60, 120];

function cabeceras(extra) {
  const h = Object.assign({}, extra);
  const clave = sessionStorage.getItem("compliance-sandbox-clave");
  if (clave) h["X-Agent-Key"] = clave;
  return h;
}

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

/** Reintentos del contrato. `aviso(texto)` informa las esperas al usuario. */
async function llamarConReintentos(hacerPeticion, aviso) {
  const inicio = Date.now();
  let intentos429 = 0;
  let fallos = 0;
  while (Date.now() - inicio < TIEMPO_MAXIMO_MS) {
    let r = null;
    try {
      const control = new AbortController();
      const reloj = setTimeout(() => control.abort(), TIEMPO_LLAMADA_MS);
      r = await hacerPeticion(control.signal);
      clearTimeout(reloj);
    } catch {
      r = null;
    }
    if (r && r.ok) return { ok: true, datos: await r.json() };
    if (r && r.status === 503 && r.headers.get("retry-after")) {
      const s = Number(r.headers.get("retry-after"));
      aviso(`El servicio está ocupado; reintento en ${s} s…`);
      await dormir(s * 1000);
      continue;
    }
    if (r && r.status === 429) {
      const s = ESPERAS_429_S[Math.min(intentos429++, ESPERAS_429_S.length - 1)];
      aviso(`Gemini está saturado; reintento en ${s} s…`);
      await dormir(s * 1000);
      continue;
    }
    if (!r || [502, 503, 504].includes(r.status)) {
      if (++fallos > 3) break;
      aviso(`Falló la conexión; reintento ${fallos} de 3…`);
      await dormir(15000 * fallos);
      continue;
    }
    let detalle = "";
    try { detalle = (await r.json()).detail; } catch { /* sin JSON */ }
    return { ok: false, definitivo: true, status: r.status, detalle: textoDetalle(detalle) };
  }
  return { ok: false, definitivo: false, detalle: "No se pudo completar tras varios reintentos." };
}

function textoDetalle(d) {
  if (!d) return "";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  return JSON.stringify(d);
}

async function cargarCatalogo() {
  const r = await fetch("/api/catalogo", { headers: cabeceras() });
  if (r.status === 401) throw new Error("clave");
  if (!r.ok) throw new Error(`catálogo HTTP ${r.status}`);
  return r.json();
}

// ---------- Estado de la pantalla ----------

let usuario = leerUsuario();
let catalogo = null;
let expediente = null;
let ocupado = false;

const $ = (id) => document.getElementById(id);

function modalidadDe(e) {
  return catalogo && catalogo.modalidades.find((m) => m.valor === e.modalidad);
}

function nombreTipo(e, tipo) {
  const m = modalidadDe(e);
  const s = m && m.checklist.find((x) => x.tipo_documento === tipo);
  return s ? s.nombre : tipo;
}

/** Un tipo del checklist está cubierto si tiene al menos un documento válido. */
function cubierto(e, tipo) {
  return e.documentos.some((d) => d.tipo === tipo && d.estado === "ANALIZADO" && d.tipo_coincide);
}

function pendientes(e) {
  const m = modalidadDe(e);
  return m ? m.checklist.filter((x) => !cubierto(e, x.tipo_documento)) : [];
}

// ---------- Mensajes ----------

function agregar(rol, texto, extra) {
  expediente.mensajes.push(Object.assign({ rol, texto, fecha: new Date().toISOString() }, extra || {}));
}

async function decir(texto, extra) {
  agregar("agente", texto, extra);
  await guardarExpediente(expediente);
  pintar();
}

function saludo() {
  return `Hola, ${usuario.nombre}. Soy el Coordinador de Compliance de Contrataciones. ` +
    "Te acompaño a auditar un expediente documento por documento, y puedes preguntarme lo que necesites en el camino.\n\n" +
    "Para empezar, ¿cuál es la nomenclatura del expediente? Por ejemplo: CA-SDEDTEOEL-CA-002-2026.";
}

// ---------- Flujo guiado ----------

async function nuevoExpediente() {
  expediente = {
    id: crypto.randomUUID(),
    usuario: usuario.nombre,
    ente: usuario.ente,
    creado: new Date().toISOString(),
    paso: "nomenclatura",
    nomenclatura: "",
    nombre: "",
    modalidad: "",
    tipo_contratacion: "",
    documentos: [],
    dictamenes: [],
    mensajes: [],
  };
  await decir(saludo());
  await pintarLista();
}

/** Paso del registro según los datos que ya tiene el expediente. */
function actualizarPaso(e) {
  if (!e.nomenclatura) e.paso = "nomenclatura";
  else if (!e.modalidad) e.paso = "modalidad";
  else if (!e.tipo_contratacion) e.paso = "tipo";
  else e.paso = "documentos";
}

/** Texto libre: lo responde el agente con POST /api/conversar (sin estado). */
async function recibirTexto(texto) {
  const e = expediente;
  const historial = e.mensajes
    .filter((m) => m.clase !== "progreso" && (m.rol === "usuario" || m.rol === "agente"))
    .slice(-20)
    .map((m) => ({ rol: m.rol, texto: m.texto }));
  agregar("usuario", texto);
  agregar("agente", "…", { clase: "progreso" });
  const progreso = e.mensajes[e.mensajes.length - 1];
  ocupado = true;
  pintar();

  const res = await llamarConReintentos((signal) => fetch("/api/conversar", {
    method: "POST",
    headers: cabeceras({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      usuario_nombre: usuario.nombre,
      ente: usuario.ente,
      expediente: {
        nomenclatura: e.nomenclatura || null,
        nombre: e.nombre || null,
        modalidad: e.modalidad || null,
        tipo_contratacion: e.tipo_contratacion || null,
        documentos: e.documentos.filter((d) => d.estado === "ANALIZADO").map((d) => d.json_analista),
        dictamenes: e.dictamenes.length,
      },
      historial,
      mensaje: texto,
    }),
    signal,
  }), (aviso) => { progreso.texto = aviso; pintar(); });

  ocupado = false;
  e.mensajes = e.mensajes.filter((x) => x !== progreso);
  if (!res.ok) {
    agregar("agente", `No pude responder: ${res.detalle || `HTTP ${res.status}`}.`, { clase: "error" });
    await guardarExpediente(e);
    pintar();
    return;
  }
  agregar("agente", res.datos.respuesta);
  let dictamen = null;
  for (const a of res.datos.acciones || []) {
    if (a.accion === "fijar_expediente") {
      for (const campo of ["nomenclatura", "nombre", "modalidad", "tipo_contratacion"]) {
        if (a[campo]) e[campo] = a[campo];
      }
    } else if (a.accion === "pedir_documento") {
      e.sugerido = a.tipo_documento;
    } else if (a.accion === "solicitar_dictamen") {
      dictamen = a;
    }
  }
  actualizarPaso(e);
  await guardarExpediente(e);
  pintar();
  await pintarLista();
  if (dictamen) await solicitarDictamen(dictamen.forzar_final, true);
}

async function elegirModalidad(valor) {
  const e = expediente;
  const m = catalogo.modalidades.find((x) => x.valor === valor);
  agregar("usuario", m.nombre);
  e.modalidad = valor;
  actualizarPaso(e);
  if (m.estado === "sin_validar") {
    agregar("agente", "Aviso: los cuestionarios de esta modalidad aún no tienen la revisión del equipo legal.", { clase: "aviso" });
  }
  await decir("¿Qué tipo de contratación es?");
}

async function elegirTipo(valor) {
  const e = expediente;
  const t = catalogo.tipos_contratacion.find((x) => x.valor === valor);
  agregar("usuario", t.nombre);
  e.tipo_contratacion = valor;
  actualizarPaso(e);
  const m = modalidadDe(e);
  await decir(`Perfecto: ${m.nombre}, ${t.nombre.toLowerCase()}. El checklist tiene ${m.checklist.length} documentos; ` +
    "ya puedes cargarlos en el orden que prefieras desde la lista de la derecha.");
}

let tipoParaSubir = null;

function abrirSelector(tipo) {
  tipoParaSubir = tipo;
  $("in-archivo").value = "";
  $("in-archivo").click();
}

async function subirArchivo(archivo, tipo) {
  const e = expediente;
  const doc = {
    id: crypto.randomUUID(),
    tipo,
    archivo: archivo.name,
    estado: "PROCESANDO",
    fecha: new Date().toISOString(),
  };
  e.documentos.push(doc);
  if (e.sugerido === tipo) e.sugerido = null;
  await guardarOriginal(e, archivo);
  agregar("usuario", `Subí «${archivo.name}» como ${nombreTipo(e, tipo)}.`);
  agregar("agente", "Analizando el documento. Puede tardar de 1 a 3 minutos, más si es escaneado…", { clase: "progreso" });
  const progreso = e.mensajes[e.mensajes.length - 1];
  await guardarExpediente(e);
  ocupado = true;
  pintar();

  const res = await llamarConReintentos((signal) => {
    const form = new FormData();
    form.append("archivo", archivo);
    form.append("nomenclatura", e.nomenclatura);
    form.append("modalidad", e.modalidad);
    form.append("tipo_contratacion", e.tipo_contratacion);
    form.append("tipo_documento", tipo);
    return fetch("/api/analizar", { method: "POST", body: form, headers: cabeceras(), signal });
  }, (texto) => { progreso.texto = texto; pintar(); });

  ocupado = false;
  e.mensajes = e.mensajes.filter((x) => x !== progreso);
  if (res.ok) {
    const d = res.datos;
    Object.assign(doc, {
      estado: "ANALIZADO",
      json_analista: d.json_analista,
      informe_markdown: d.informe_markdown,
      estatus_global: d.estatus_global,
      tipo_coincide: d.tipo_coincide,
      tipo_detectado: d.tipo_detectado,
    });
    agregar("agente", `Listo el resumen de «${archivo.name}». Puedes verlo y descargarlo.`, {
      tipo: "informe", doc_id: doc.id,
    });
    if (!d.tipo_coincide) {
      agregar("agente",
        `Este archivo no parece ser «${nombreTipo(e, tipo)}»` +
        (d.tipo_detectado ? ` (parece ${nombreTipo(e, d.tipo_detectado)})` : "") +
        ". No cuenta para el checklist: súbelo en la casilla correcta.",
        { clase: "aviso" });
    }
  } else if (res.definitivo && [400, 413, 415].includes(res.status)) {
    Object.assign(doc, { estado: "RECHAZADO", error: res.detalle });
    agregar("agente", `No pude analizar «${archivo.name}»: ${res.detalle}`, { clase: "error" });
  } else {
    Object.assign(doc, { estado: "ERROR", error: res.detalle || `HTTP ${res.status}` });
    agregar("agente", `Falló el análisis de «${archivo.name}»: ${doc.error}. Puedes intentarlo de nuevo.`, {
      clase: "error", reintentar: tipo,
    });
  }
  await guardarExpediente(e);
  pintar();
  await pintarLista();
}

async function solicitarDictamen(forzarFinal, desdeChat = false) {
  const e = expediente;
  const documentos = e.documentos.filter((d) => d.estado === "ANALIZADO").map((d) => d.json_analista);
  if (!documentos.length) {
    await decir("Primero necesito al menos un documento analizado.");
    return;
  }
  // Pedido por chat: el usuario ya lo escribió con sus palabras.
  if (!desdeChat) agregar("usuario", forzarFinal ? "Solicito el dictamen final." : "Solicito el dictamen.");
  agregar("agente", "Generando el dictamen jurídico. Suele tardar de 1 a 2 minutos…", { clase: "progreso" });
  const progreso = e.mensajes[e.mensajes.length - 1];
  await guardarExpediente(e);
  ocupado = true;
  pintar();

  const res = await llamarConReintentos((signal) => fetch("/api/dictamen", {
    method: "POST",
    headers: cabeceras({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      nomenclatura: e.nomenclatura,
      modalidad: e.modalidad,
      tipo_contratacion: e.tipo_contratacion,
      forzar_final: !!forzarFinal,
      documentos,
    }),
    signal,
  }), (texto) => { progreso.texto = texto; pintar(); });

  ocupado = false;
  e.mensajes = e.mensajes.filter((x) => x !== progreso);
  if (res.ok) {
    const dic = Object.assign({ id: crypto.randomUUID(), fecha: new Date().toISOString() }, res.datos);
    e.dictamenes.push(dic);
    agregar("agente", `Listo el dictamen ${dic.alcance === "FINAL" ? "final" : "parcial"}.`, {
      tipo: "dictamen", dictamen_id: dic.id,
    });
  } else {
    agregar("agente", `No se pudo generar el dictamen: ${res.detalle || `HTTP ${res.status}`}.`, { clase: "error" });
  }
  await guardarExpediente(e);
  pintar();
  await pintarLista();
}

// ---------- Pintar ----------

function el(tag, attrs, ...hijos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "onclick") n.addEventListener("click", v);
    else if (k === "class") n.className = v;
    else n.setAttribute(k, v);
  }
  for (const h of hijos) if (h != null) n.append(h);
  return n;
}

function estadoChip(texto, clase) {
  return el("span", { class: `estado ${clase}` }, texto);
}

function chipDocumento(d) {
  if (d.estado === "ANALIZADO") {
    return d.tipo_coincide ? estadoChip(d.estatus_global || "Analizado", d.estatus_global || "")
      : estadoChip("Tipo incorrecto", "rechazado");
  }
  const nombres = { PROCESANDO: "Analizando", RECHAZADO: "Rechazado", ERROR: "Error" };
  return estadoChip(nombres[d.estado] || d.estado, d.estado.toLowerCase());
}

function pintarMensaje(m) {
  const clase = m.rol === "usuario" ? "usuario" : (m.clase === "aviso" || m.clase === "error" ? m.clase : "agente");
  const caja = el("div", { class: `msg ${clase}` }, m.texto);
  if (m.tipo === "informe") {
    const d = expediente.documentos.find((x) => x.id === m.doc_id);
    if (d) {
      caja.append(el("div", { class: "fila" },
        chipDocumento(d),
        el("button", { class: "ligero", type: "button", onclick: () => verInforme(d) }, "Ver resumen")));
    }
  }
  if (m.tipo === "dictamen") {
    const dic = expediente.dictamenes.find((x) => x.id === m.dictamen_id);
    if (dic) {
      const g = dic.puntaje && dic.puntaje.global;
      if (g) caja.append(el("div", { class: "sutil" }, `Puntaje global: ${g.porcentaje} % (${g.rango}).`));
      if (dic.coherencia && dic.coherencia.length) {
        const ul = el("ul");
        dic.coherencia.forEach((c) => ul.append(el("li", null,
          `${c.dato}: ${c.documento_a} = ${c.valor_a}; ${c.documento_b} = ${c.valor_b}`)));
        caja.append(el("div", null, "Contradicciones entre documentos:"), ul);
      }
      caja.append(el("div", { class: "fila" },
        el("button", { class: "ligero", type: "button", onclick: () => verDictamen(dic) }, "Ver dictamen")));
    }
  }
  if (m.reintentar) {
    caja.append(el("div", { class: "fila" },
      el("button", { class: "ligero", type: "button", onclick: () => abrirSelector(m.reintentar) }, "Volver a subir")));
  }
  return caja;
}

function pintarAcciones() {
  const cont = $("acciones");
  cont.replaceChildren();
  const e = expediente;
  $("form-texto").hidden = !e || ocupado;
  if (!e || ocupado) return;
  $("in-texto").placeholder = e.paso === "nomenclatura"
    ? "Escribe la nomenclatura del expediente, o pregúntame lo que necesites"
    : "Escribe tu mensaje";
  $("in-texto").focus();

  if (e.paso === "nomenclatura") return;
  if (e.paso === "modalidad") {
    catalogo.modalidades.forEach((m) => {
      const b = el("button", { class: "ligero", type: "button", onclick: () => elegirModalidad(m.valor) },
        m.nombre + (m.estado === "sin_validar" ? " (sin validar)" : ""));
      if (m.estado === "sin_cuestionarios") {
        b.disabled = true;
        b.title = "Aún no tiene cuestionarios";
      }
      cont.append(b);
    });
    return;
  }
  if (e.paso === "tipo") {
    catalogo.tipos_contratacion.forEach((t) => cont.append(
      el("button", { class: "ligero", type: "button", onclick: () => elegirTipo(t.valor) }, t.nombre)));
    return;
  }
  if (e.sugerido) {
    cont.append(el("button", { type: "button", onclick: () => abrirSelector(e.sugerido) },
      `Subir ${nombreTipo(e, e.sugerido)}`));
  }
  const ultimo = e.documentos[e.documentos.length - 1];
  if (ultimo && ultimo.estado === "ANALIZADO") {
    cont.append(el("button", { class: "ligero", type: "button", onclick: () => abrirSelector(ultimo.tipo) },
      `Subir otro: ${nombreTipo(e, ultimo.tipo)}`));
  }
  if (e.documentos.some((d) => d.estado === "ANALIZADO")) {
    const faltan = pendientes(e).length;
    cont.append(el("button", { class: "ligero", type: "button", onclick: () => solicitarDictamen(false) },
      faltan ? `Dictamen parcial (faltan ${faltan})` : "Dictamen final"));
    if (faltan) {
      cont.append(el("button", { class: "ligero", type: "button", onclick: () => solicitarDictamen(true) },
        "Dictamen final de todas formas"));
    }
  }
}

function pintarChecklist() {
  const lista = $("lista-checklist");
  lista.replaceChildren();
  const e = expediente;
  const m = e && modalidadDe(e);
  $("datos-expediente").textContent = e
    ? [e.nomenclatura, e.nombre, m && m.nombre, e.tipo_contratacion].filter(Boolean).join(" · ")
    : "";
  if (!m) return;
  m.checklist.forEach((s) => {
    const docs = e.documentos.filter((d) => d.tipo === s.tipo_documento);
    const ultimo = docs[docs.length - 1];
    let chip = estadoChip("Pendiente", "pendiente");
    if (cubierto(e, s.tipo_documento)) {
      const peor = docs.filter((d) => d.estado === "ANALIZADO" && d.tipo_coincide)
        .map((d) => d.estatus_global).sort((a, b) => "RojoAmarilloVerde".indexOf(a) - "RojoAmarilloVerde".indexOf(b))[0];
      chip = estadoChip(peor || "Analizado", peor || "");
    } else if (ultimo) {
      chip = chipDocumento(ultimo);
    }
    const archivos = el("div", { class: "archivos" });
    docs.filter((d) => d.estado === "ANALIZADO").forEach((d, i) => {
      if (i) archivos.append(", ");
      archivos.append(el("a", { onclick: () => verInforme(d), title: "Ver resumen" }, d.archivo));
    });
    const subir = el("button", { class: "ligero", type: "button", onclick: () => abrirSelector(s.tipo_documento) }, "Subir");
    subir.disabled = ocupado || e.paso !== "documentos";
    lista.append(el("li", { class: s.tipo_documento === e.sugerido ? "siguiente" : "" },
      el("span", null, s.nombre, " ", chip), subir, docs.length ? archivos : null));
  });
}

function pintar() {
  const cont = $("mensajes");
  cont.replaceChildren();
  if (expediente) expediente.mensajes.forEach((m) => cont.append(pintarMensaje(m)));
  else {
    cont.append(el("div", { class: "msg agente" }, `Hola, ${usuario.nombre}. Crea un expediente nuevo o abre uno de la lista.`));
    if (estadoCarpeta === "sin_elegir" || estadoCarpeta === "sin_permiso") {
      cont.append(el("div", { class: "msg aviso" },
        estadoCarpeta === "sin_elegir"
          ? "Elige una carpeta de tu PC para guardar el historial (por ejemplo Documentos\Compliance). Mientras tanto se guarda en el navegador."
          : "Para ver tu historial, vuelve a dar permiso a la carpeta.",
        el("div", { class: "fila" }, el("button", { type: "button", onclick: accionCarpeta },
          estadoCarpeta === "sin_elegir" ? "Elegir carpeta" : "Reconectar carpeta"))));
    }
  }
  cont.scrollTop = cont.scrollHeight;
  pintarAcciones();
  pintarChecklist();
}

async function pintarLista() {
  const todos = (await leerExpedientes())
    .filter((x) => x.ente === usuario.ente)
    .sort((a, b) => (b.actualizado || "").localeCompare(a.actualizado || ""));
  const ul = $("lista-expedientes");
  ul.replaceChildren();
  if (!todos.length) ul.append(el("li", { class: "sutil" }, "Aún no hay expedientes."));
  todos.forEach((x) => {
    const analizados = x.documentos.filter((d) => d.estado === "ANALIZADO").length;
    const li = el("li", { class: expediente && x.id === expediente.id ? "activo" : "" },
      x.nomenclatura || "Expediente nuevo",
      el("small", null, `${x.nombre || "Sin nombre"} · ${analizados} analizados · ${x.dictamenes.length} dictamen(es)`));
    li.addEventListener("click", () => {
      if (ocupado) return;
      expediente = x;
      recuperarInterrumpidos(x);
      pintar();
      pintarLista();
    });
    ul.append(li);
  });
}

/** Si se cerró la página durante un análisis, ese documento queda como error. */
function recuperarInterrumpidos(e) {
  let hubo = false;
  e.documentos.filter((d) => d.estado === "PROCESANDO").forEach((d) => {
    d.estado = "ERROR";
    d.error = "Análisis interrumpido al cerrar la página.";
    hubo = true;
  });
  const antes = e.mensajes.length;
  e.mensajes = e.mensajes.filter((m) => m.clase !== "progreso");
  if (hubo || e.mensajes.length !== antes) guardarExpediente(e);
}

// ---------- Visor de informes ----------

let visorTexto = "";
let visorArchivo = "";

function abrirVisor(titulo, markdown, archivo) {
  visorTexto = markdown || "";
  visorArchivo = archivo;
  $("visor-titulo").textContent = titulo;
  $("visor-cuerpo").innerHTML = markdownAHtml(visorTexto || "_Sin contenido._");
  $("visor").showModal();
}

function verInforme(d) {
  abrirVisor(`Resumen: ${d.archivo}`, d.informe_markdown, `resumen_${d.archivo}.md`);
}

function verDictamen(dic) {
  abrirVisor(`Dictamen ${dic.alcance.toLowerCase()}: ${expediente.nomenclatura}`, dic.markdown,
    `dictamen_${expediente.nomenclatura}_${dic.fecha.slice(0, 10)}.md`);
}

function descargar(nombre, texto, tipo) {
  const url = URL.createObjectURL(new Blob([texto], { type: tipo }));
  const a = el("a", { href: url, download: nombre });
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Markdown mínimo: títulos, listas, tablas, negritas, cursivas y código. Escapa el HTML. */
function markdownAHtml(md) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const enLinea = (s) => esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
  const lineas = md.replace(/\r/g, "").split("\n");
  const out = [];
  let lista = null;
  let parrafo = [];
  const cerrarParrafo = () => { if (parrafo.length) { out.push(`<p>${parrafo.join("<br>")}</p>`); parrafo = []; } };
  const cerrarLista = () => { if (lista) { out.push(`</${lista}>`); lista = null; } };
  for (let i = 0; i < lineas.length; i++) {
    const l = lineas[i];
    const h = l.match(/^(#{1,6})\s+(.*)$/);
    const li = l.match(/^\s*([-*]|\d+\.)\s+(.*)$/);
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lineas.length && /^\s*\|[\s:|-]+\|\s*$/.test(lineas[i + 1])) {
      cerrarParrafo(); cerrarLista();
      const celdas = (x) => x.trim().replace(/^\||\|$/g, "").split("|").map((c) => enLinea(c.trim()));
      out.push("<table><tr>" + celdas(l).map((c) => `<th>${c}</th>`).join("") + "</tr>");
      i += 2;
      while (i < lineas.length && /^\s*\|.*\|\s*$/.test(lineas[i])) {
        out.push("<tr>" + celdas(lineas[i]).map((c) => `<td>${c}</td>`).join("") + "</tr>");
        i++;
      }
      i--;
      out.push("</table>");
    } else if (h) {
      cerrarParrafo(); cerrarLista();
      out.push(`<h${h[1].length}>${enLinea(h[2])}</h${h[1].length}>`);
    } else if (li) {
      cerrarParrafo();
      const tag = /\d/.test(li[1]) ? "ol" : "ul";
      if (lista !== tag) { cerrarLista(); out.push(`<${tag}>`); lista = tag; }
      out.push(`<li>${enLinea(li[2])}</li>`);
    } else if (/^\s*(---|\*\*\*)\s*$/.test(l)) {
      cerrarParrafo(); cerrarLista();
      out.push("<hr>");
    } else if (!l.trim()) {
      cerrarParrafo(); cerrarLista();
    } else {
      cerrarLista();
      parrafo.push(enLinea(l));
    }
  }
  cerrarParrafo(); cerrarLista();
  return out.join("\n");
}

// ---------- Arranque ----------

let estadoCarpeta = "sin_soporte";

function pintarCarpeta() {
  const b = $("btn-carpeta");
  const textos = {
    lista: `Carpeta: ${carpeta && carpeta.name}`,
    sin_elegir: "Elegir carpeta del historial",
    sin_permiso: "Reconectar carpeta",
    sin_soporte: "Historial en el navegador",
  };
  b.textContent = textos[estadoCarpeta];
  b.disabled = estadoCarpeta === "sin_soporte";
  b.title = estadoCarpeta === "sin_soporte"
    ? "Este navegador no permite guardar en una carpeta; usa Chrome o Edge."
    : "Carpeta de la PC donde se guardan los expedientes";
}

async function accionCarpeta() {
  if (ocupado) return;
  try {
    if (estadoCarpeta === "sin_permiso") await reconectarCarpeta();
    else await elegirCarpeta();
  } catch (err) {
    if (err.name !== "AbortError") alert("No se pudo usar la carpeta: " + err.message);
  }
  estadoCarpeta = carpeta ? "lista" : estadoCarpeta;
  pintarCarpeta();
  expediente = null;
  pintar();
  await pintarLista();
}

async function iniciarApp() {
  $("entrada").hidden = true;
  $("app").hidden = false;
  $("quien").textContent = `${usuario.nombre} · ${usuario.ente}`;
  estadoCarpeta = await recuperarCarpeta();
  pintarCarpeta();
  try {
    catalogo = await cargarCatalogo();
  } catch (err) {
    if (String(err.message) === "clave") {
      pedirClave("El servicio pide la clave X-Agent-Key.");
    } else {
      alert("No pude cargar el catálogo del agente: " + err.message);
    }
    return;
  }
  expediente = null;
  pintar();
  await pintarLista();
}

function pedirClave(motivo) {
  const clave = prompt(`${motivo ? motivo + "\n" : ""}Clave X-Agent-Key (se guarda solo en esta pestaña; vacío si no hace falta):`,
    sessionStorage.getItem("compliance-sandbox-clave") || "");
  if (clave === null) return;
  if (clave) sessionStorage.setItem("compliance-sandbox-clave", clave.trim());
  else sessionStorage.removeItem("compliance-sandbox-clave");
  iniciarApp();
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    db = await abrirDB();
  } catch {
    alert("Este navegador no permite guardar el historial (IndexedDB).");
    return;
  }

  $("form-entrada").addEventListener("submit", (ev) => {
    ev.preventDefault();
    usuario = { nombre: $("in-nombre").value.trim(), ente: $("in-ente").value.trim() };
    localStorage.setItem(CLAVE_USUARIO, JSON.stringify(usuario));
    iniciarApp();
  });
  $("form-texto").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const t = $("in-texto").value.trim();
    if (!t) return;
    $("in-texto").value = "";
    recibirTexto(t);
  });
  $("in-archivo").addEventListener("change", () => {
    const f = $("in-archivo").files[0];
    if (f && tipoParaSubir) subirArchivo(f, tipoParaSubir);
  });
  $("btn-nuevo").addEventListener("click", () => { if (!ocupado) nuevoExpediente(); });
  $("btn-clave").addEventListener("click", () => pedirClave(""));
  $("btn-carpeta").addEventListener("click", accionCarpeta);
  $("btn-salir").addEventListener("click", () => {
    if (ocupado) return;
    localStorage.removeItem(CLAVE_USUARIO);
    location.reload();
  });
  $("btn-exportar").addEventListener("click", async () => {
    const todos = await leerExpedientes();
    descargar(`respaldo_compliance_${new Date().toISOString().slice(0, 10)}.json`,
      JSON.stringify(todos, null, 2), "application/json");
  });
  $("visor-cerrar").addEventListener("click", () => $("visor").close());
  $("visor-descargar").addEventListener("click", () => descargar(visorArchivo, visorTexto, "text/markdown"));
  window.addEventListener("beforeunload", (ev) => { if (ocupado) { ev.preventDefault(); ev.returnValue = ""; } });

  if (usuario && usuario.nombre && usuario.ente) iniciarApp();
  else $("entrada").hidden = false;
});
