/* Interfaz de resúmenes: formulario, polling del progreso y acciones por clase.
   Sin dependencias. Usa textContent siempre que el valor venga del servidor. */

(function () {
  "use strict";

  var formulario = document.getElementById("form-nueva");
  var campo = document.getElementById("url");
  var panel = document.getElementById("progreso");
  var fase = document.getElementById("progreso-fase");
  var tiempo = document.getElementById("progreso-tiempo");
  var barra = document.getElementById("progreso-barra");
  var bloques = document.getElementById("progreso-bloques");
  var acciones = document.getElementById("progreso-acciones");
  var cerrar = document.getElementById("cerrar-progreso");
  var lista = document.getElementById("lista-cursos");

  var sondeo = null;
  var trabajoActual = null;
  var inicioLocal = 0;

  function texto(nodo, valor) {
    if (nodo) nodo.textContent = valor == null ? "" : String(valor);
  }

  function mostrarPanel(si) {
    if (panel) panel.hidden = !si;
  }

  function detener() {
    if (sondeo) {
      clearInterval(sondeo);
      sondeo = null;
    }
  }

  /* ---------- progreso ---------- */

  function pintar(estado) {
    texto(fase, estado.fase || estado.estado);

    var seg = inicioLocal
      ? Math.max(0, Math.round((Date.now() - inicioLocal) / 1000))
      : estado.transcurrido || 0;
    if (seg >= 60) {
      texto(tiempo, Math.floor(seg / 60) + " min " + (seg % 60) + " s");
    } else {
      texto(tiempo, seg + " s");
    }

    var hayBloques = estado.bloques_total > 0;
    if (hayBloques) {
      var pct = Math.min(100, Math.round(
        (100 * estado.bloques_ok) / estado.bloques_total
      ));
      barra.classList.remove("barra__relleno--indeterminada");
      barra.style.width = pct + "%";
      texto(bloques, "bloques " + estado.bloques_ok + "/" + estado.bloques_total);
    } else {
      barra.classList.add("barra__relleno--indeterminada");
    }
  }

  function accionesFinales(estado) {
    acciones.replaceChildren();

    if (estado.error) {
      var div = document.createElement("div");
      div.className = "aviso aviso--error";
      div.textContent = estado.error;
      acciones.appendChild(div);
      return;
    }

    if (estado.estado !== "listo") return;

    if (estado.resultado) {
      var curso = estado.resultado[0];
      var dia = estado.resultado[1];

      var ver = document.createElement("a");
      ver.className = "btn btn--primario";
      ver.target = "_blank";
      ver.rel = "noopener";
      ver.href = "/ver/" + encodeURIComponent(curso) + "/" + encodeURIComponent(dia);
      ver.textContent = "Abrir resumen";
      acciones.appendChild(ver);

      var md = document.createElement("a");
      md.className = "btn";
      md.href = "/md/" + encodeURIComponent(curso) + "/" + encodeURIComponent(dia);
      md.textContent = "Descargar .md";
      acciones.appendChild(md);
    }

    if (estado.ya_existia) {
      var nota = document.createElement("span");
      nota.className = "badge badge--ok";
      nota.textContent = "ya estaba hecho · sin coste";
      acciones.appendChild(nota);
    }
  }

  function refrescarCursos() {
    return fetch("/api/cursos", { cache: "no-store" })
      .then(function (r) { return r.text(); })
      .then(function (htmlTexto) {
        if (lista) lista.innerHTML = htmlTexto;
      })
      .catch(function () { /* la lista se reintenta en el próximo trabajo */ });
  }

  function seguir(id) {
    detener();
    trabajoActual = id;

    var consultar = function () {
      fetch("/trabajo/" + encodeURIComponent(id), { cache: "no-store" })
        .then(function (r) {
          if (!r.ok) throw new Error("no encontrado");
          return r.json();
        })
        .then(function (estado) {
          pintar(estado);
          if (estado.activo) return;

          detener();
          accionesFinales(estado);
          if (estado.estado === "listo") refrescarCursos();
        })
        .catch(function () {
          detener();
          texto(fase, "Se perdió el estado del trabajo (¿se reinició el servidor?).");
          barra.classList.remove("barra__relleno--indeterminada");
          barra.style.width = "0%";
        });
    };

    consultar();
    sondeo = setInterval(consultar, 2000);
  }

  function lanzar(url, cuerpo) {
    mostrarPanel(true);
    inicioLocal = Date.now();
    texto(fase, "Enviando…");
    texto(tiempo, "0 s");
    texto(bloques, "");
    acciones.replaceChildren();
    barra.classList.add("barra__relleno--indeterminada");

    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo || {}),
    })
      .then(function (r) {
        return r.json().then(function (datos) {
          if (!r.ok) throw new Error(datos.error || "El servidor rechazó la petición.");
          return datos;
        });
      })
      .then(function (datos) { seguir(datos.id); })
      .catch(function (e) {
        acciones.replaceChildren();
        var div = document.createElement("div");
        div.className = "aviso aviso--error";
        div.textContent = e.message;
        acciones.appendChild(div);
        texto(fase, "No se pudo iniciar");
        barra.classList.remove("barra__relleno--indeterminada");
        barra.style.width = "0%";
      });
  }

  /* ---------- eventos ---------- */

  if (formulario) {
    formulario.addEventListener("submit", function (e) {
      e.preventDefault();
      var url = (campo && campo.value || "").trim();
      if (!url) {
        campo && campo.focus();
        return;
      }
      lanzar("/nueva", { url: url });
    });
  }

  if (cerrar) {
    cerrar.addEventListener("click", function () {
      mostrarPanel(false);
      detener();
    });
  }

  /* Delegación: los botones de la lista se regeneran por completo. */
  document.addEventListener("click", function (e) {
    var boton = e.target.closest("[data-accion]");
    if (!boton) return;

    var curso = boton.getAttribute("data-curso");
    var dia = boton.getAttribute("data-dia");
    var accion = boton.getAttribute("data-accion");
    if (!curso || !dia) return;

    if (accion === "regenerar") {
      var materia = boton.getAttribute("data-materia") || "esta clase";
      var aviso =
        "Se volverá a llamar al modelo y se sobrescribirá el resumen de " +
        materia + ".\n\nTarda entre 4 y 9 minutos y consume 14 llamadas.\n\n¿Continuar?";
      if (!window.confirm(aviso)) return;
    }

    boton.disabled = true;
    lanzar("/" + accion + "/" + encodeURIComponent(curso) + "/" + encodeURIComponent(dia), {});
    setTimeout(function () { boton.disabled = false; }, 1500);
  });

  /* Cronómetro local: el servidor solo informa el tiempo cada 2 s, pero el
     contador debe moverse aunque la red tarde. */
  setInterval(function () {
    if (!trabajoActual || !inicioLocal || !panel || panel.hidden) return;
    var seg = Math.max(0, Math.round((Date.now() - inicioLocal) / 1000));
    if (seg >= 60) {
      texto(tiempo, Math.floor(seg / 60) + " min " + (seg % 60) + " s");
    } else {
      texto(tiempo, seg + " s");
    }
  }, 1000);
})();
