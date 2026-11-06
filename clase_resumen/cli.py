"""Herramienta de línea de comandos: resumen.py"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from . import almacen
from .almacen import Ubicacion
from .cursos import ErrorDeCurso, cargar_registro, preparar, resolver
from .fetch import Clase, ErrorDeClase, PATRON_REPLAY, clase_desde_texto, obtener_clase
from .llm import ErrorDeModelo, cargar
from .summarize import huella, procesar, render
from .visor import generar

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "clases"


def _verde(t: str) -> str:
    return f"\033[32m{t}\033[0m" if os.name != "nt" or os.environ.get("WT_SESSION") else t


def _gris(t: str) -> str:
    return f"\033[90m{t}\033[0m"


def _fecha_legible(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return iso or "—"


# --------------------------------------------------------------------------- #
# Listado
# --------------------------------------------------------------------------- #

def _clases_de(raiz: Path) -> list[Ubicacion]:
    """Carpetas de clase de un curso, de la más reciente a la más antigua."""
    if not raiz.is_dir():
        return []
    ubicaciones = [Ubicacion(p) for p in raiz.iterdir() if p.is_dir()]
    return sorted(ubicaciones, key=lambda u: u.carpeta.name, reverse=True)


def _listar(base: Path, cursos) -> None:
    if not cursos:
        print(_gris("No hay cursos declarados en cursos.json."))
        return
    total = 0
    for c in cursos:
        clases = _clases_de(base / c.carpeta)
        total += len(clases)
        print(f"\n{c.codigo} · {c.nombre}   {_gris(f'({len(clases)} clases)')}")
        print(_gris(f"  clases/{c.carpeta}/"))
        if not clases:
            print(_gris("  sin clases todavía"))
            continue
        for u in clases:
            meta = almacen.leer_meta(u)
            fecha = _fecha_legible(meta.get("cuando", ""))
            partes = ["md"]
            if u.datos.is_file():
                partes.append("json")
            if u.visor.is_file():
                partes.append("html")
            if u.transcripcion.is_file():
                partes.append("transcripción")
            titulo = str(meta.get("materia") or u.carpeta.name)
            print(f"  {fecha}  {u.carpeta.name}   {_gris('· ' + ' '.join(partes))}")
            if titulo and titulo != u.carpeta.name:
                print(_gris(f"        {titulo}"))
            actualizado = meta.get("actualizado")
            if actualizado:
                print(_gris(f"        actualizado {actualizado[:16].replace('T', ' ')}"))
    print(f"\n{_gris(f'Total: {total} clases en {len(cursos)} cursos')}")


# --------------------------------------------------------------------------- #
# Reconstrucción desde disco
# --------------------------------------------------------------------------- #

def _clase_desde_disco(ubic: Ubicacion) -> Clase | None:
    """Reconstruye la clase con lo guardado, sin tocar la red.

    Permite re-renderizar el Markdown y regenerar el visor aunque se haya
    perdido la transcripción original o cambiado la plataforma.
    """
    meta = almacen.leer_meta(ubic)
    segmentos = almacen.leer_transcripcion(ubic)
    if not segmentos:
        return None
    try:
        cuando = datetime.fromisoformat(str(meta.get("cuando") or ""))
    except ValueError:
        cuando = datetime.now().astimezone()
    return Clase(
        url=str(meta.get("url") or ""),
        materia=str(meta.get("materia") or "Clase"),
        cuando=cuando,
        duracion_s=float(meta.get("duracion_s") or segmentos[-1].segundos),
        segmentos=segmentos,
        docente=str(meta.get("docente") or ""),
        participantes=int(meta.get("participantes") or 0),
        api_base=str(meta.get("api_base") or ""),
        school_id=str(meta.get("school_id") or ""),
        class_uuid=str(meta.get("class_uuid") or ""),
        recording_id=str(meta.get("recording_id") or ""),
    )


def _guardar_meta(ubic: Ubicacion, clase: Clase, huella_valor: str) -> None:
    previo = almacen.leer_meta(ubic)
    almacen._escribir_json(ubic.meta, {
        "materia": clase.materia,
        "cuando": clase.cuando.isoformat(),
        "url": clase.url,
        "duracion_s": clase.duracion_s,
        "docente": clase.docente,
        "participantes": clase.participantes,
        "api_base": clase.api_base,
        "school_id": clase.school_id,
        "class_uuid": clase.class_uuid,
        "recording_id": clase.recording_id,
        "huella": huella_valor,
        "creado": previo.get("creado") or datetime.now().isoformat(timespec="seconds"),
        "actualizado": datetime.now().isoformat(timespec="seconds"),
    })


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="resumen",
        description="Convierte una repetición de clase en apuntes de estudio con timestamps.",
        epilog="Ejemplo: python resumen.py https://cibertec.class.com/player/recording/...",
    )
    p.add_argument("url", nargs="?", help="enlace de la repetición en Class")
    p.add_argument("--texto", metavar="ARCHIVO",
                   help="usar una transcripción copiada del panel 'Transcripción'")
    p.add_argument("--materia", default="Clase", help="nombre de la asignatura (con --texto)")
    p.add_argument("--salida", default=str(SALIDA), help="carpeta base donde guardar los apuntes")
    p.add_argument("--curso", help="código del curso (SPTI02423, DCGS12424, PROG04696…)")
    p.add_argument("--lista", action="store_true", help="listar los cursos y sus clases")
    p.add_argument("--forzar", action="store_true", help="regenerar aunque ya exista")
    p.add_argument("--modelo", help="sobrescribir el modelo configurado")
    p.add_argument("--visor", action="store_true", help="generar además el visor HTML con el video")
    p.add_argument("--solo-visor", action="store_true",
                   help="regenerar solo el visor desde los datos guardados, sin llamar al modelo")
    p.add_argument("--rehacer", action="store_true",
                   help="re-renderizar el Markdown desde los datos guardados, sin llamar al modelo")
    args = p.parse_args(argv)

    base = Path(args.salida)
    try:
        cursos = cargar_registro()
        preparar(base, cursos)
    except (json.JSONDecodeError, OSError) as e:
        print(f"\n✗ No se pudo leer cursos.json: {e}\n", file=sys.stderr)
        return 2

    if args.lista:
        _listar(base, cursos)
        return 0

    if not args.url and not args.texto:
        p.error("indica el enlace de la repetición o usa --texto")

    t0 = time.time()

    # ------------------------------------------------------------------ #
    # Modo sin modelo: --rehacer / --solo-visor
    # ------------------------------------------------------------------ #
    if args.rehacer or args.solo_visor:
        return _modo_sin_modelo(args, base, cursos)

    # ------------------------------------------------------------------ #
    # Modo normal: obtener la clase
    # ------------------------------------------------------------------ #
    try:
        if args.texto:
            print(_gris(f"Leyendo {args.texto}…"))
            clase = clase_desde_texto(Path(args.texto), args.materia)
        else:
            print(_gris("Descargando la transcripción de Class…"))
            clase = obtener_clase(args.url)
    except ErrorDeClase as e:
        print(f"\n✗ {e}\n", file=sys.stderr)
        return 2

    if not clase.segmentos:
        print("\n✗ La clase no tiene transcripción utilizable.\n", file=sys.stderr)
        return 2

    try:
        curso = resolver(clase.materia, args.curso, cursos)
    except ErrorDeCurso as e:
        print(f"\n✗ {e}\n", file=sys.stderr)
        return 2

    ubic = almacen.ubicar(base, curso, clase)

    print(f"  {clase.materia} · {clase.cuando:%d/%m/%Y} · "
          f"{round(clase.duracion_s/60)} min · {len(clase.segmentos)} intervenciones")
    print(f"  Curso: {curso.etiqueta}")
    print(f"  Clase: {_gris(str(ubic.carpeta))}")

    # ¿Ya existe y está igual?
    if ubic.existe and not args.forzar:
        guardada = str(almacen.leer_meta(ubic).get("huella") or "")
        if guardada and guardada == huella(clase):
            print(_verde(f"✓ Ya existe y está actualizado: {ubic.resumen}"))
            if args.visor:
                datos = almacen.leer_datos(ubic)
                if datos:
                    generar(clase, datos, ubic.visor)
                    print(_verde(f"✓ {ubic.visor}"))
            return 0

    # ------------------------------------------------------------------ #
    # Resumir
    # ------------------------------------------------------------------ #
    try:
        modelo = cargar()
        if args.modelo:
            modelo.model = args.modelo
    except ErrorDeModelo as e:
        print(f"\n✗ {e}\n", file=sys.stderr)
        return 2

    print(_gris(f"Resumiendo con {modelo.etiqueta}…"))

    def progreso(i: int, total: int, _bloque):
        print(f"\r  bloques {i}/{total}", end="", flush=True)

    try:
        datos = procesar(modelo, clase, progreso)
    except ErrorDeModelo as e:
        print(f"\n\n✗ {e}\n", file=sys.stderr)
        return 3
    print()

    # ------------------------------------------------------------------ #
    # Escribir todo
    # ------------------------------------------------------------------ #
    texto = render(clase, datos)
    ubic.resumen.write_text(texto, encoding="utf-8")
    almacen.escribir_datos(ubic, datos)
    almacen._escribir_transcripcion(ubic, clase)
    _guardar_meta(ubic, clase, huella(clase))

    if args.visor:
        generar(clase, datos, ubic.visor)
        print(_verde(f"✓ {ubic.visor}"))

    palabras = len(texto.split())
    print(_verde(f"✓ {ubic.resumen}"))
    cobertura = datos.get("cobertura")
    extra = f" · cobertura {cobertura}%" if cobertura is not None else ""
    if datos.get("revisados"):
        extra += f" · {datos['revisados']} tramo(s) reprocesado(s)"
    print(_gris(f"  {palabras} palabras · {round(time.time()-t0)} s{extra}"))
    return 0


def _buscar_por_grabacion(base: Path, url: str) -> Ubicacion | None:
    """Encuentra en disco la clase correspondiente a una URL, sin tocar la red."""
    m = PATRON_REPLAY.search(url or "")
    if not m:
        return None
    objetivo = m["recording_id"]
    for meta in base.glob("*/*/" + almacen.NOMBRE_META):
        try:
            datos = json.loads(meta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if str(datos.get("recording_id") or "") == objetivo:
            return Ubicacion(meta.parent)
    return None


def _modo_sin_modelo(args, base: Path, cursos) -> int:
    """--rehacer y --solo-visor: trabajan con lo guardado en disco.

    No descargan la transcripción: localizan la clase por el identificador de la
    grabación que va en la URL. Así puedes actualizar el resumen aunque la
    plataforma ya no responda o cambies de red.
    """
    ubic = _buscar_por_grabacion(base, args.url) if args.url else None

    if ubic is None:
        # No está en disco: primera vez, hay que descargarla.
        if args.texto:
            clase = clase_desde_texto(Path(args.texto), args.materia)
        else:
            try:
                clase = obtener_clase(args.url)
            except ErrorDeClase as e:
                print(f"\n✗ No se encontró esa clase en disco y no se pudo descargar.\n{e}\n",
                      file=sys.stderr)
                return 2
        try:
            curso = resolver(clase.materia, args.curso, cursos)
        except ErrorDeCurso as e:
            print(f"\n✗ {e}\n", file=sys.stderr)
            return 2
        ubic = almacen.ubicar(base, curso, clase)
        if not ubic.datos.is_file():
            print(f"\n✗ No hay datos guardados en {ubic.datos}\n"
                  "  Ejecuta primero el resumen completo con --visor.\n", file=sys.stderr)
            return 2

    datos = almacen.leer_datos(ubic)
    if not datos:
        print(f"\n✗ No hay datos guardados en {ubic.datos}\n", file=sys.stderr)
        return 2

    clase_disco = _clase_desde_disco(ubic)
    if clase_disco is None:
        print(f"\n✗ Falta la transcripción en {ubic.transcripcion}\n"
              "  Vuelve a ejecutar el resumen completo.\n", file=sys.stderr)
        return 2

    if args.rehacer:
        ubic.resumen.write_text(render(clase_disco, datos), encoding="utf-8")
        print(_verde(f"✓ {ubic.resumen}"))

    if args.solo_visor or args.rehacer:
        generar(clase_disco, datos, ubic.visor)
        print(_verde(f"✓ {ubic.visor}"))

    return 0
