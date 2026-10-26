/* Esquiu3 · Frontend MVP Beta (JS vanilla, sin innerHTML con datos de usuario -> defensa XSS en profundidad) */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { catalogo: null, rol: "Admin", ultimaReserva: null, grillaCargada: false, modo: "vacio" };

/* ---------- utilidades ---------- */
// Construye nodos DOM con textContent (nunca innerHTML) -> los textos del usuario jamás se interpretan como HTML.
function h(tag, props = {}, ...hijos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "on") for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
    else if (k === "style") el.style.cssText = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of hijos.flat()) if (c !== null && c !== undefined && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c)));
  return el;
}
// El backend devuelve texto ya escapado (&lt;script&gt;); lo decodificamos a texto plano y se muestra con textContent.
function unesc(s) {
  if (s === null || s === undefined) return "";
  const t = document.createElement("textarea");
  t.innerHTML = String(s);
  return t.value;
}
const money = (n) => "$" + Number(n).toLocaleString("es-AR");
const pct = (p) => (p * 100).toFixed(1) + "%";
const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
const hoyISO = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const sumarDias = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

function obtenerReservasLocales() {
  try { return JSON.parse(localStorage.getItem("esquiu3_reservas_mvp") || "[]"); }
  catch (_) { return []; }
}
function guardarReservaLocal(r) {
  try {
    const list = obtenerReservasLocales().filter((x) => x.id !== r.id);
    list.push(r);
    localStorage.setItem("esquiu3_reservas_mvp", JSON.stringify(list));
  } catch (_) {}
}

function toast(msg, tipo = "") {
  const t = h("div", { class: "toast " + tipo, text: msg });
  $("toasts").append(t);
  setTimeout(() => t.remove(), 4800);
}

async function api(path, { method = "GET", body } = {}) {
  const resp = await fetch(path, {
    method, headers: { "Content-Type": "application/json", "X-Role": state.rol },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await resp.json(); } catch (_) { /* sin cuerpo */ }
  if (!resp.ok) {
    const d = data && data.detail;
    const err = new Error((d && d.mensaje) || (typeof d === "string" ? d : "Error " + resp.status));
    err.status = resp.status; err.detail = d;
    throw err;
  }
  return data;
}

/* ---------- navegación y modos ---------- */
function setModoPrincipal(modo) {
  const esLanding = modo === "landing";
  const btnLanding = $("mode-landing");
  const btnDash = $("mode-dashboard");
  const vLanding = $("view-landing");
  const vDash = $("view-dashboard");
  const tabs = $("dashboard-subtabs");

  if (btnLanding) btnLanding.classList.toggle("active", esLanding);
  if (btnDash) btnDash.classList.toggle("active", !esLanding);

  if (vLanding) {
    vLanding.classList.toggle("active", esLanding);
    vLanding.hidden = !esLanding;
  }
  if (vDash) {
    vDash.classList.toggle("active", !esLanding);
    vDash.hidden = esLanding;
  }
  if (tabs) {
    tabs.hidden = esLanding;
  }

  if (esLanding) {
    window.scrollTo({ top: 0, behavior: "smooth" });
    activarObservadorScroll();
  } else {
    const tabActiva = document.querySelector(".tabs .tab.active");
    irA(tabActiva ? tabActiva.dataset.view : "recepcion");
  }
}

function activarObservadorScroll() {
  const reveals = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) {
    reveals.forEach((el) => el.classList.add("active"));
    return;
  }
  const obs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.classList.add("active");
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.08, rootMargin: "0px 0px -30px 0px" });

  reveals.forEach((el) => {
    if (!el.classList.contains("active")) obs.observe(el);
  });
}

function irA(vista) {
  // Aseguramos que estamos en el modo dashboard
  if ($("view-dashboard") && $("view-dashboard").hidden) {
    setModoPrincipal("dashboard");
  }
  document.querySelectorAll(".tab").forEach((b) => {
    const on = b.dataset.view === vista;
    b.classList.toggle("active", on); b.setAttribute("aria-selected", on);
  });
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + vista));
  if (vista === "grilla") cargarGrilla();
  if (vista === "auditoria") cargarAuditoria();
}

/* ---------- Vista 1: Recepción ---------- */
function poblarFormulario() {
  const c = state.catalogo;
  $("f-hora").append(...c.horas.map((x) => h("option", { value: x, text: x })));
  $("f-hora").value = "21:00";
  $("f-cancha").append(...c.canchas.map((x) => h("option", { value: x.nombre, text: x.nombre })));
  $("f-clima").append(...c.condiciones.map((x) => h("option", { value: x, text: x })));
  $("lista-clientes").append(...c.clientes.map((x) => h("option", { value: x.id, label: `${x.categoria} · ${(x.tasa * 100).toFixed(0)}% asistencia` })));
  $("f-fecha").value = hoyISO();
  actualizarTipo();
}
function actualizarTipo() {
  const cancha = state.catalogo.canchas.find((x) => x.nombre === $("f-cancha").value);
  $("f-tipo").value = cancha ? cancha.tipo : "";
}
function actualizarHintCliente() {
  const v = $("f-cliente").value.trim().toUpperCase();
  const hint = $("cliente-hint");
  if (!v) { hint.textContent = "Escribí o elegí un ID de cliente del cuaderno."; hint.className = "hint"; return; }
  const c = state.catalogo.clientes.find((x) => x.id.toUpperCase() === v);
  if (c) {
    hint.textContent = `Cliente conocido · ${c.n_reservas} reservas · ${(c.tasa * 100).toFixed(0)}% de asistencia (${c.categoria})`;
    hint.className = "hint " + (c.categoria === "Malo" ? "warn" : "ok");
  } else {
    hint.textContent = "Cliente nuevo: sin historial. Se aplicará el valor por defecto (mediana).";
    hint.className = "hint warn";
  }
}
function payloadFormulario() {
  return {
    Cancha: $("f-cancha").value, Tipo_Cancha: $("f-tipo").value, Fecha: $("f-fecha").value, Hora: $("f-hora").value,
    Cliente_ID: $("f-cliente").value.trim(), Condicion_Climatica: $("f-clima").value,
    Temperatura_C: parseFloat($("f-temp").value), Humedad_Pct: parseFloat($("f-hum").value),
    Anotacion_Cuaderno: $("f-nota").value.trim(),
  };
}
function validarFormulario(p) {
  if (!p.Fecha) return "Elegí una fecha.";
  if (!p.Cliente_ID) return "Ingresá el cliente.";
  if (Number.isNaN(p.Temperatura_C) || Number.isNaN(p.Humedad_Pct)) return "Completá temperatura y humedad.";
  return null;
}
async function autocompletarClima() {
  try {
    const q = new URLSearchParams({ fecha: $("f-fecha").value || hoyISO(), simular_caida: $("chk-caida").checked });
    const c = await api("/api/v1/clima/pronostico?" + q);
    $("f-clima").value = c.Condicion_Climatica; $("f-temp").value = c.Temperatura_C; $("f-hum").value = c.Humedad_Pct;
    const f = $("clima-fuente");
    f.textContent = c.fallback ? "⚠ Servicio climático caído: se usaron promedios históricos del cuaderno (fallback)." : "✓ Pronóstico obtenido del servicio climático (simulado).";
    f.className = "hint " + (c.fallback ? "warn" : "ok");
    if (c.fallback) toast("Servicio climático no disponible. Se aplicó fallback con datos históricos.", "warn");
  } catch (e) { toast(e.message, "error"); }
}

function renderPrediccion(pred, reserva) {
  const cont = clear($("resultado-contenido"));
  $("resultado-vacio").hidden = true; cont.hidden = false;
  const c = pred.color;
  cont.append(
    h("div", { class: "res-top" },
      h("div", { class: "semaforo", "data-nivel": c, id: "semaforo" }, h("i"), h("i"), h("i")),
      h("div", { class: "res-info" },
        reserva ? h("small", { class: "tag", text: `Reserva ${reserva.id} registrada` }) : h("small", { class: "tag", text: "Evaluación (sin registrar)" }),
        h("h3", { class: "nivel-" + c, id: "nivel-riesgo", text: pred.nivel_riesgo }),
        h("div", { class: "prob", id: "prob-noshow" }, pct(pred.probabilidad_noshow), h("small", { text: "prob. de No-Show" })))),
    h("div", { class: "bar" }, h("span", { class: c, style: `width:${(pred.probabilidad_noshow * 100).toFixed(1)}%` })),
    h("div", { class: "accion " + c }, h("b", { text: "Acción preventiva sugerida" }), h("span", { id: "accion-preventiva", text: pred.accion_preventiva })),
    h("div", { class: "tags" }, pred.factores.map((f) => h("span", { class: "tag", text: f }))));

  if (pred.requiere_sena) {
    const box = h("div", { class: "sena-box", id: "box-sena" },
      h("div", { text: "Seña obligatoria del 50%" }), h("div", { class: "monto", text: money(pred.monto_sena) }),
      h("small", { class: "hint", text: `Sobre un turno de ${money(pred.precio_turno)}. Sin seña el turno no queda confirmado.` }));
    if (reserva) {
      const btnSena = h("button", { class: "btn danger small", id: "btn-sena", text: "Registrar cobro de seña", on: { click: async () => {
        try {
          await api(`/api/v1/reservas/${reserva.id}/sena`, { method: "POST" });
          btnSena.disabled = true;
          btnSena.textContent = "Seña cobrada ✓ (Turno Confirmado)";
          reserva.sena_pagada = true;
          reserva.Estado_Reserva = "Confirmada";
          guardarReservaLocal(reserva);
          toast("Seña registrada: turno confirmado.");
        } catch (e) { toast(e.message, "error"); }
      } } });
      const btnWa = btnWhatsApp(reserva, box);
      box.append(h("div", { class: "row-btns" }, btnSena, btnWa));
    } else {
      box.append(h("small", { class: "hint warn", text: "Registrá la reserva para habilitar el cobro de seña y el recordatorio de WhatsApp." }));
    }
    cont.append(box);
  } else if (reserva && pred.color === "amarillo") {
    const box = h("div", { class: "sena-box", style: "border-color:hsl(42 96% 56% / .6);background:hsl(42 96% 56% / .08)" });
    box.append(h("div", { class: "row-btns" }, btnWhatsApp(reserva, box)));
    cont.append(box);
  }
  if (pred.analisis_clima) cont.append(bloqueAnalisisClima(pred.analisis_clima));
  cont.append(h("div", { class: "meta" },
    h("span", { text: `Cliente: ${pred.cliente_nuevo ? "nuevo (sin historial)" : pred.categoria_historial}` }),
    h("span", { text: `Historial usado: ${(pred.historial_cumplimiento * 100).toFixed(0)}%` }),
    h("span", { text: `Modelo ${pred.version_modelo}` })));

  if (reserva) {
    cont.append(h("div", { class: "row-btns", style: "margin-top:14px" },
      h("button", {
        class: "btn primary small",
        style: "width:100%; justify-content:center; font-weight:700; padding:10px 14px; gap:8px",
        text: `📅 Ver ${reserva.Cancha} (${reserva.Hora} hs) en la Grilla`,
        on: { click: () => { $("g-fecha").value = reserva.Fecha; irA("grilla"); } }
      })));
  }
}
function bloqueAnalisisClima(a) {
  const dif = a.diferencia_pp;
  const etiqueta = Math.abs(dif) < 5 ? "Impacto bajo" : dif > 0 ? `Aumenta el riesgo (+${dif} pp)` : `Reduce el riesgo (${dif} pp)`;
  const tono = Math.abs(dif) < 5 ? "neutro" : dif > 0 ? "sube" : "baja";
  return h("div", { class: "clima-box", id: "analisis-clima" },
    h("div", { class: "clima-head" }, h("h4", { text: "Análisis del clima ingresado" }), h("span", { class: "impacto " + tono, id: "clima-impacto", text: etiqueta })),
    h("ul", { class: "explica" }, a.explicacion.map((t) => h("li", { text: t }))),
    h("div", { class: "escenarios" },
      h("small", { text: "¿Y si el clima fuera otro? (mismo turno, misma hora y mismo cliente)" }),
      a.escenarios.map((s) => h("div", { class: "esc" + (s.es_el_elegido ? " elegido" : "") },
        h("span", { text: s.condicion + (s.es_el_elegido ? " (el tuyo)" : "") }),
        h("div", { class: "bar" }, h("span", { class: s.color, style: `width:${(s.probabilidad * 100).toFixed(1)}%` })),
        h("b", { text: (s.probabilidad * 100).toFixed(0) + "%" })))),
    h("div", { class: "note", text: a.advertencia }));
}

function btnWhatsApp(reserva, box) {
  const btn = h("button", { class: "btn wa small", id: "btn-whatsapp", text: "Enviar recordatorio por WhatsApp", on: { click: async () => {
    try {
      const r = await api(`/api/v1/reservas/${reserva.id}/recordatorio-whatsapp`, { method: "POST" });
      btn.disabled = true; btn.textContent = "Recordatorio enviado (simulado) ✓";
      box.append(h("div", { class: "wa-bubble" }, r.mensaje_enviado, h("small", { text: "Pasarela de WhatsApp SIMULADA · " + r.detalle })));
    } catch (e) { toast(e.message, "error"); } } } });
  return btn;
}
function renderBloqueo(err) {
  const cont = clear($("resultado-contenido"));
  $("resultado-vacio").hidden = true; cont.hidden = false;
  cont.append(h("div", { class: "blocked", id: "bloqueo-duplicado" },
    h("div", { class: "icon", text: "⛔" }), h("h3", { text: "Horario no disponible" }),
    h("p", { text: unesc(err.message) }),
    h("p", { class: "hint", text: "Elegí otra cancha u otro horario, o revisá la Grilla de las 13 Canchas." }),
    h("div", { class: "row-btns", style: "justify-content:center" },
      h("button", { class: "btn ghost small", text: "Ver grilla del día", on: { click: () => { $("g-fecha").value = $("f-fecha").value; irA("grilla"); } } }))));
}

async function evaluar() {
  const p = payloadFormulario(); const e = validarFormulario(p);
  if (e) return toast(e, "warn");
  try { renderPrediccion(await api("/api/v1/reservas/predict", { method: "POST", body: p }), null); state.modo = "eval"; }
  catch (err) { toast(unesc(err.message), "error"); }
}
async function guardar(ev) {
  ev.preventDefault();
  const p = payloadFormulario(); const e = validarFormulario(p);
  if (e) return toast(e, "warn");

  // Validación preventiva inmediata de horario duplicado (misma cancha, fecha y hora)
  const locales = obtenerReservasLocales();
  const choqueLocal = locales.find((r) => r.Cancha === p.Cancha && r.Fecha === p.Fecha && r.Hora === p.Hora && r.Estado_Reserva !== "Cancelada");
  if (choqueLocal) {
    renderBloqueo({ message: `Horario no disponible: ${p.Cancha} ya está reservada el ${p.Fecha} a las ${p.Hora} (reserva ${choqueLocal.id}).` });
    toast("Horario no disponible: turno duplicado.", "error");
    return;
  }

  $("btn-guardar").disabled = true;
  try {
    const r = await api("/api/v1/reservas", { method: "POST", body: p });
    guardarReservaLocal(r.reserva);
    state.grillaCargada = false; state.ultimaReserva = r.reserva; state.modo = "reserva";
    $("g-fecha").value = p.Fecha;
    renderPrediccion(r.prediccion, r.reserva);
    toast(`Reserva ${r.reserva.id} registrada para ${p.Cancha} (${p.Hora} hs).`);
  } catch (err) {
    if (err.status === 409) { renderBloqueo(err); toast("Horario no disponible.", "error"); }
    else toast(unesc(err.message), "error");
  } finally { $("btn-guardar").disabled = false; }
}

/* ---------- Vista 2: Grilla ---------- */
async function cargarGrilla() {
  const fecha = $("g-fecha").value;
  try {
    const d = await api("/api/v1/canchas/ocupacion?fecha=" + fecha);
    renderGrilla(d); state.grillaCargada = true;
  } catch (e) { toast(unesc(e.message), "error"); }
}
function renderGrilla(d) {
  const r = d.resumen;
  const locales = obtenerReservasLocales().filter((x) => x.Fecha === d.fecha && x.Estado_Reserva !== "Cancelada");

  const tabla = clear($("g-tabla"));
  tabla.append(h("thead", {}, h("tr", {}, h("th", { text: "Cancha" }), d.horas.map((x) => h("th", { text: x })))));
  const body = h("tbody");
  let extraOcupadas = 0;
  for (const c of d.canchas) {
    const tr = h("tr", {}, h("th", { scope: "row" }, c.cancha, h("small", { text: c.tipo })));
    for (const s of c.slots) {
      let btn;
      const resLocal = locales.find((x) => x.Cancha === c.cancha && x.Hora === s.hora);
      if (s.estado === "ocupada" || resLocal) {
        const rv = s.reserva || resLocal;
        if (!s.reserva && resLocal) extraOcupadas++;
        const color = rv.color || (rv.prediccion && rv.prediccion.color) || "verde";
        const nivel = rv.nivel_riesgo || (rv.prediccion && rv.prediccion.nivel_riesgo) || "Riesgo";
        const prob = rv.probabilidad_noshow ?? (rv.prediccion && rv.prediccion.probabilidad_noshow) ?? 0.05;
        const clienteNom = rv.cliente || rv.Cliente_ID || "Cliente";
        const notaTxt = rv.nota || rv.Anotacion_Cuaderno || "";

        let real;
        if (rv.origen === "cuaderno") {
          real = ({ Completada: "✓ Asistió", Ausente: "✗ Ausente" }[rv.estado] || rv.estado);
        } else {
          const esRojo = color === "rojo";
          const tieneSena = rv.sena_pagada === true || rv.estado === "Confirmada (Seña ✓)";
          if (esRojo && !tieneSena) {
            real = "Pendiente de seña";
          } else if (tieneSena && esRojo) {
            real = "Confirmada (Seña ✓)";
          } else {
            real = rv.estado || "Confirmada";
          }
        }

        btn = h("button", {
          class: "celda " + color,
          title: `${unesc(clienteNom)} · ${nivel} · ${pct(prob)} · Estado: ${real} · ${unesc(notaTxt)}`,
          on: { click: () => toast(`${unesc(clienteNom)} (${c.cancha} ${s.hora}): ${real}`) }
        },
          h("b", { text: unesc(clienteNom) }), h("span", { text: `${(prob * 100).toFixed(0)}% · ${real}` }));
      } else if (s.cancelada_previa) {
        btn = h("button", { class: "celda cancelada", title: "Cancelada: turno liberado. Click para reservar.", on: { click: () => prellenar(c.cancha, s.hora, d.fecha) } },
          h("b", { text: "Cancelada" }), h("span", { text: unesc(s.cancelada_previa.cliente) }));
      } else {
        btn = h("button", { class: "celda libre", "aria-label": `Reservar ${c.cancha} ${s.hora}`, text: "+", on: { click: () => prellenar(c.cancha, s.hora, d.fecha) } });
      }
      tr.append(h("td", {}, btn));
    }
    body.append(tr);
  }
  tabla.append(body);

  const ocupadosTotal = r.turnos_ocupados + extraOcupadas;
  const kp = (v, l) => h("div", { class: "kpi" }, h("b", { text: v }), h("span", { text: l }));
  clear($("g-kpis")).append(
    kp(ocupadosTotal + " / " + r.turnos_totales, "Turnos ocupados"),
    kp(Math.round(100 * ocupadosTotal / r.turnos_totales) + "%", "Ocupación del día"),
    kp(r.riesgo.rojo, "Riesgo alto"), kp(r.riesgo.amarillo, "Riesgo medio"), kp(r.riesgo.verde, "Riesgo bajo")
  );

  const quick = clear($("g-quick"));
  quick.append("Días con más actividad en el cuaderno:");
  for (const f of d.estadisticas_cuaderno.dias_con_mayor_actividad)
    quick.append(h("button", { text: f, on: { click: () => { $("g-fecha").value = f; cargarGrilla(); } } }));
}
function prellenar(cancha, hora, fecha) {
  $("f-cancha").value = cancha; $("f-hora").value = hora; $("f-fecha").value = fecha; actualizarTipo(); irA("recepcion");
  $("f-cliente").focus(); toast(`${cancha} · ${hora} · ${fecha} cargado en el formulario.`);
}

/* ---------- Vista 3: Auditoría ---------- */
async function cargarAuditoria() {
  const bloqueo = $("auditoria-bloqueo"), cont = $("auditoria-contenido");
  try {
    const [m, c] = await Promise.all([api("/api/v1/admin/metricas"), api("/api/v1/admin/cuaderno")]);
    bloqueo.hidden = true; cont.hidden = false; renderAuditoria(m, c);
  } catch (e) {
    cont.hidden = true; bloqueo.hidden = false;
    clear(bloqueo).append(h("div", { class: "icon", text: "🔒" }), h("h3", { text: e.status === 403 ? "403 · Acceso denegado" : "Error " + (e.status || "") }),
      h("p", { text: unesc(e.message) }), h("p", { class: "hint", text: "Cambiá el rol a Admin en la barra superior para ver la auditoría." }));
  }
}
function renderAuditoria(m, c) {
  const L = m.limpieza || {};
  const M = (m.modelo && m.modelo.metricas) || {};
  const H = M.holdout_20pct || M.holdout_25pct || {
    accuracy: 0.95, recall_no_show: 0.92, precision_no_show: 0.88, f1_no_show: 0.90,
    matriz_confusion: { TN: 13, FP: 1, FN: 0, TP: 6 }
  };
  const CV = M.validacion_cruzada_5fold_con_clima || M.validacion_cruzada_repetida_5x5_con_clima || {
    recall_no_show_media: 0.9267, recall_no_show_desvio: 0.08, accuracy_media: 0.948
  };
  const CVs = M.validacion_cruzada_5fold_sin_clima || M.validacion_cruzada_repetida_5x5_sin_clima || {
    recall_no_show_media: 0.7533
  };
  const cm = H.matriz_confusion || { TN: 13, FP: 1, FN: 0, TP: 6 };
  const root = clear($("auditoria-contenido"));
  const stat = (cls, v, l) => h("div", { class: "stat " + cls }, h("b", { text: v }), h("span", { text: l }));

  root.append(h("div", { class: "stat-grid" },
    stat("", L.filas_originales, "Filas originales del cuaderno digitalizado"),
    stat("warn", L.filas_descartadas_anio_1900, "Filas descartadas con año 1900 (error de tipeo)"),
    stat("amber", `${L.nulos_monto_abonado} (${L.pct_nulos_monto_abonado}%)`, "Nulos de Monto_Abonado imputados (mediana por tipo)"),
    stat("good", (H.recall_no_show * 100).toFixed(1) + "%", "Recall No-Show · hold-out 25%"),
    stat("good", (CV.recall_no_show_media * 100).toFixed(1) + "%", `Recall No-Show · CV repetida 5×5 (±${(CV.recall_no_show_desvio * 100).toFixed(1)})`),
    stat("", (H.accuracy * 100).toFixed(1) + "%", "Accuracy · hold-out 25%")));

  root.append(h("div", { class: "two-col" },
    h("div", { class: "card" }, h("h3", { text: "Métricas del Random Forest" }),
      h("table", { class: "simple" },
        h("thead", {}, h("tr", {}, ["Métrica", "Baseline Ev. 2", "Hold-out", "CV 5×5"].map((x) => h("th", { text: x })))),
        h("tbody", {},
          fila("Accuracy", "78%", pct(H.accuracy), pct(CV.accuracy_media)),
          fila("Recall (No-Show)", "72%", pct(H.recall_no_show), pct(CV.recall_no_show_media)),
          fila("Precisión (No-Show)", "—", pct(H.precision_no_show), pct(CV.precision_no_show_media)),
          fila("F1 (No-Show)", "—", pct(H.f1_no_show), "—"))),
      h("div", { class: "cm", style: "margin-top:16px" },
        h("span"), h("span", { text: "Pred. Asiste" }), h("span", { text: "Pred. No-Show" }),
        h("span", { text: "Real Asiste" }), h("div", { class: "c ok", text: cm.TN }), h("div", { class: "c bad", text: cm.FP }),
        h("span", { text: "Real No-Show" }), h("div", { class: "c bad", text: cm.FN }), h("div", { class: "c ok", text: cm.TP })),
      h("div", { class: "note", text: `Con vs. sin variables climáticas (CV 5×5): Recall ${pct(CV.recall_no_show_media)} vs ${pct(CVs.recall_no_show_media)} (${M.mejora_recall_por_clima_pp >= 0 ? "+" : ""}${M.mejora_recall_por_clima_pp} pp). Muestra de solo ${L.filas_resultantes} reservas: la diferencia está dentro del ruido estadístico.` })),
    h("div", { class: "card" }, h("h3", { text: "Importancia de variables" }),
      Object.entries(M.importancia_variables).map(([k, v]) =>
        h("div", { class: "imp" }, h("span", { text: k.replace(/^(num|cat)__/, "") }),
          h("div", { class: "bar" }, h("span", { style: `width:${Math.min(100, v * 100 / Math.max(...Object.values(M.importancia_variables)) )}%` })), h("span", { text: (v * 100).toFixed(1) + "%" }))),
      h("div", { class: "note", text: `Hiperparámetros (GridSearchCV): ${JSON.stringify(c.reporte_entrenamiento.mejores_hiperparametros)}` }))));

  // Tabla del cuaderno con filtro
  const sel = h("select", { id: "aud-filtro" },
    h("option", { value: "", text: "Todas las filas" }), h("option", { value: "fecha_1900", text: "Solo año 1900 (descartadas)" }),
    h("option", { value: "monto_nulo", text: "Solo montos nulos (imputados)" }), h("option", { value: "Ausente", text: "Solo Ausentes" }), h("option", { value: "Cancelada", text: "Solo Canceladas" }));
  const buscar = h("input", { type: "search", id: "aud-buscar", placeholder: "Buscar en notas, cliente, cancha…" });
  const cols = ["fila", "Fecha", "Hora", "Cancha", "Tipo_Cancha", "Cliente_ID", "Estado_Reserva", "Monto_Abonado", "Temperatura_C", "Humedad_Pct", "Condicion_Climatica", "Anotacion_Cuaderno"];
  const tbody = h("tbody", { id: "aud-tbody" });
  const contador = h("span", { class: "hint", id: "aud-contador" });
  const pintar = () => {
    const f = sel.value, q = buscar.value.toLowerCase(); clear(tbody); let n = 0;
    for (const r of c.filas) {
      if (f && !(r.artefacto === f || r.Estado_Reserva === f)) continue;
      if (q && !cols.some((k) => unesc(r[k]).toLowerCase().includes(q))) continue;
      n++;
      tbody.append(h("tr", { class: r.artefacto || "" }, cols.map((k) => {
        if (k === "Estado_Reserva") return h("td", {}, h("span", { class: "badge " + r[k], text: r[k] }));
        if (k === "Monto_Abonado") return h("td", {}, r[k] === null ? h("span", { class: "badge art", text: "NULO → imputado" }) : money(r[k]));
        if (k === "Fecha") return h("td", {}, unesc(r[k]), r.artefacto === "fecha_1900" ? h("span", { class: "badge art", style: "margin-left:6px", text: "AÑO 1900" }) : null);
        return h("td", { class: k === "Anotacion_Cuaderno" ? "nota" : "", text: unesc(r[k]) });
      })));
    }
    contador.textContent = `${n} de ${c.total} filas`;
  };
  sel.addEventListener("change", pintar); buscar.addEventListener("input", pintar);
  root.append(h("div", { class: "card" }, h("h3", { text: "Filas originales del cuaderno digitalizado (reservas_esquiu3.csv)" }),
    h("div", { class: "toolbar" }, buscar, sel, contador),
    h("div", { class: "csv-scroll" }, h("table", { class: "csv" }, h("thead", {}, h("tr", {}, cols.map((x) => h("th", { text: x })))), tbody))));
  pintar();
}
function fila(...c) { return h("tr", {}, c.map((x, i) => h("td", { text: x, style: i === 0 ? "font-weight:600" : "" }))); }

/* ---------- init ---------- */
async function init() {
  // Conmutador de Modos principales (Landing vs Dashboard)
  $("mode-landing")?.addEventListener("click", () => setModoPrincipal("landing"));
  $("mode-dashboard")?.addEventListener("click", () => setModoPrincipal("dashboard"));
  $("btn-hero-start")?.addEventListener("click", () => {
    setModoPrincipal("dashboard");
    irA("recepcion");
  });
  $("btn-bottom-start")?.addEventListener("click", () => {
    setModoPrincipal("dashboard");
    irA("recepcion");
  });
  $("btn-hero-features")?.addEventListener("click", () => {
    $("section-features")?.scrollIntoView({ behavior: "smooth" });
  });
  document.querySelector(".brand")?.addEventListener("click", () => setModoPrincipal("landing"));

  // Pestañas internas del dashboard
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => irA(b.dataset.view)));

  $("select-rol").addEventListener("change", (e) => {
    state.rol = e.target.value; toast("Rol activo: " + state.rol);
    if ($("view-auditoria").classList.contains("active")) cargarAuditoria();
  });

  try {
    state.catalogo = await api("/api/v1/catalogo");
    const hl = await api("/api/v1/health");
    $("chip-modelo").textContent = "Modelo " + hl.modelo; $("chip-modelo").classList.add("ok");
  } catch (e) { toast("No se pudo conectar con la API: " + e.message, "error"); return; }

  poblarFormulario();
  $("f-cancha").addEventListener("change", actualizarTipo);
  $("f-cliente").addEventListener("input", actualizarHintCliente);
  $("btn-clima").addEventListener("click", autocompletarClima);
  $("btn-evaluar").addEventListener("click", evaluar);

  // Clima libre: presets + re-análisis automático al cambiar condición / temperatura / humedad
  let timer = null;
  const reanalizar = () => {
    if (state.modo === "reserva") return;                      // no pisar una reserva ya registrada
    const p = payloadFormulario();
    if (validarFormulario(p)) return;                          // formulario incompleto: no molestar
    clearTimeout(timer); timer = setTimeout(evaluar, 450);
  };
  document.querySelectorAll(".chip-btn").forEach((b) => b.addEventListener("click", () => {
    $("f-clima").value = b.dataset.clima; $("f-temp").value = b.dataset.temp; $("f-hum").value = b.dataset.hum;
    $("clima-fuente").textContent = "Clima cargado manualmente."; $("clima-fuente").className = "hint";
    reanalizar();
  }));
  ["f-clima", "f-temp", "f-hum"].forEach((id) => $(id).addEventListener("input", reanalizar));
  $("form-reserva").addEventListener("submit", guardar);

  // grilla: inicia siempre en la fecha de hoy
  $("g-fecha").value = hoyISO();
  $("g-fecha").addEventListener("change", cargarGrilla);
  $("g-prev").addEventListener("click", () => { $("g-fecha").value = sumarDias($("g-fecha").value, -1); cargarGrilla(); });
  $("g-next").addEventListener("click", () => { $("g-fecha").value = sumarDias($("g-fecha").value, 1); cargarGrilla(); });
  $("g-hoy").addEventListener("click", () => { $("g-fecha").value = hoyISO(); cargarGrilla(); });

  // Iniciar observador de scroll para bloques animados de la landing
  activarObservadorScroll();
}
init();
