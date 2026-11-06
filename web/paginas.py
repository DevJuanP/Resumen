"""HTML del índice. Se construye con f-strings y `html.escape`.

Sin motor de plantillas a propósito: son dos pantallas y una sola dependencia
menos. Todo valor que venga del disco o del usuario pasa por `E()`.
"""

from __future__ import annotations

import html
from urllib.parse import quote

from .catalogo import ClaseVista, CursoVista, total_clases


def E(valor: object) -> str:
    """Escapa para HTML, incluidas comillas."""
    return html.escape(str(valor if valor is not None else ""), quote=True)


def _url(*partes: str) -> str:
    return "/" + "/".join(quote(p, safe="") for p in partes)


# --------------------------------------------------------------------------- #
# Piezas
# --------------------------------------------------------------------------- #

def _badge_video(clase: ClaseVista) -> str:
    if not clase.tiene_visor:
        return '<span class="badge badge--gris">sin visor</span>'
    if clase.video_vivo:
        return '<span class="badge badge--ok">video vigente</span>'
    return '<span class="badge badge--alerta">video caducado</span>'


def _fila(clase: ClaseVista) -> str:
    enlace = _url("ver", clase.curso, clase.dia)
    descarga = _url("md", clase.curso, clase.dia)
    datos = f'data-curso="{E(clase.curso)}" data-dia="{E(clase.dia)}"'

    ver = (
        f'<a class="btn btn--primario" href="{E(enlace)}" target="_blank" '
        f'rel="noopener">Ver</a>'
        if clase.tiene_visor
        else '<span class="btn btn--inactivo">Sin visor</span>'
    )
    renovar = (
        f'<button type="button" class="btn" data-accion="renovar" {datos}>'
        f'Renovar video</button>'
    )
    regenerar = (
        f'<button type="button" class="btn btn--tenue" data-accion="regenerar" '
        f'{datos} data-materia="{E(clase.materia)}">Regenerar</button>'
    )

    return f"""
      <article class="clase">
        <div class="clase__cabecera">
          <h3 class="clase__materia">{E(clase.materia)}</h3>
          <span class="clase__fecha">{E(clase.cuando_txt)}</span>
        </div>
        <dl class="clase__datos">
          <div><dt>Duración</dt><dd>{clase.duracion_min} min</dd></div>
          <div><dt>Docente</dt><dd>{E(clase.docente) or "—"}</dd></div>
          <div><dt>Ideas</dt><dd>{clase.ideas}</dd></div>
          <div><dt>Avisos</dt><dd>{clase.avisos}</dd></div>
          <div><dt>Cobertura</dt><dd>{clase.cobertura:g} %</dd></div>
        </dl>
        <div class="clase__pie">
          {_badge_video(clase)}
          <div class="clase__acciones">
            {ver}
            <a class="btn btn--tenue" href="{E(descarga)}">.md</a>
            {renovar}
            {regenerar}
          </div>
        </div>
      </article>"""


def _curso(curso: CursoVista) -> str:
    nombre = curso.nombre if curso.codigo else curso.carpeta
    codigo = f'<span class="curso__codigo">{E(curso.codigo)}</span>' if curso.codigo else ""
    filas = "".join(_fila(c) for c in curso.clases)
    return f"""
    <section class="curso">
      <header class="curso__cabecera">
        {codigo}
        <h2>{E(nombre)}</h2>
        <span class="curso__cuenta">{len(curso.clases)} clase{'s' if len(curso.clases) != 1 else ''}</span>
      </header>
      <div class="curso__clases">{filas}</div>
    </section>"""


def fragmento_cursos(cursos: list[CursoVista]) -> str:
    """Solo la lista de cursos: se cambia por JS sin recargar la página."""
    if not cursos:
        return """
    <div class="vacio">
      <p class="vacio__titulo">Todavía no hay resúmenes</p>
      <p class="vacio__texto">Pega arriba el enlace de una repetición de Class y pulsa
      «Generar resumen». La clase aparecerá aquí al terminar.</p>
    </div>"""
    return "".join(_curso(c) for c in cursos)


# --------------------------------------------------------------------------- #
# Página completa
# --------------------------------------------------------------------------- #

def indice(cursos: list[CursoVista], salud: dict) -> str:
    total = total_clases(cursos)

    if salud.get("error"):
        aviso = (
            '<div class="aviso aviso--error">'
            f'<strong>El modelo no está disponible.</strong> {E(salud["error"])}'
            "</div>"
        )
        desactivado = " disabled"
    else:
        modo = salud.get("modo") or "—"
        aviso = (
            '<p class="modelo">Modelo: '
            f'<code>{E(salud.get("modelo") or "—")}</code>'
            f' · <span class="modelo__modo">{E(modo)}</span>'
            f' · {E(salud.get("base") or "")}</p>'
        )
        desactivado = ""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Resúmenes de clase</title>
<link rel="stylesheet" href="/static/app.css">
</head>
<body>
<main class="pagina">

  <header class="cabecera">
    <div>
      <h1>Resúmenes de clase</h1>
      <p class="subtitulo">
        {total} clase{'s' if total != 1 else ''} en
        {len(cursos)} curso{'s' if len(cursos) != 1 else ''}
      </p>
    </div>
  </header>

  <section class="nueva">
    <form id="form-nueva" autocomplete="off">
      <label class="etiqueta" for="url">Enlace de la repetición de Class</label>
      <div class="nueva__fila">
        <input
          id="url"
          name="url"
          type="url"
          class="campo"
          placeholder="https://cibertec.class.com/player/recording/…/…"
          required{desactivado}>
        <button type="submit" class="btn btn--primario btn--grande"{desactivado}>
          Generar resumen
        </button>
      </div>
      <p class="ayuda">
        Descarga la transcripción, la resume por bloques y guarda los apuntes con
        el visor de video. Tarda entre 4 y 9 minutos.
      </p>
    </form>
    {aviso}
  </section>

  <section id="progreso" class="progreso" hidden aria-live="polite">
    <div class="progreso__cabecera">
      <span class="progreso__fase" id="progreso-fase">En cola…</span>
      <span class="progreso__tiempo" id="progreso-tiempo">0 s</span>
    </div>
    <div class="barra"><div class="barra__relleno" id="progreso-barra"></div></div>
    <div class="progreso__pie">
      <span id="progreso-bloques"></span>
      <button type="button" class="btn btn--tenue" id="cerrar-progreso">Ocultar</button>
    </div>
    <div id="progreso-acciones" class="progreso__acciones"></div>
  </section>

  <div id="lista-cursos" class="lista">
    {fragmento_cursos(cursos)}
  </div>

</main>
<script src="/static/app.js"></script>
</body>
</html>
"""
