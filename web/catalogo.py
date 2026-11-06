"""Escaneo de `clases/` para construir lo que muestra la interfaz.

Solo lectura: no crea, mueve ni borra nada. Se reutiliza `cursos.json` a través
de `clase_resumen.cursos` para no duplicar la resolución de cursos.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from clase_resumen import cursos as registro

RAIZ = Path(__file__).resolve().parent.parent
BASE = RAIZ / "clases"

# Un segmento de ruta aceptable: letras, dígitos, guion, punto y guion bajo.
# "." y ".." se rechazan aparte, en `ruta_bajo`.
SEGMENTO_VALIDO = re.compile(r"^[\w.\-]+$")

# Las URLs firmadas del video caducan; el epoch va en el query.
EXPIRES = re.compile(r"Expires=(\d{9,13})")

NOMBRE_META = "clase.json"
NOMBRE_DATOS = "resumen.json"
NOMBRE_VISOR = "visor.html"
NOMBRE_RESUMEN = "resumen.md"


# --------------------------------------------------------------------------- #
# Modelo de vista
# --------------------------------------------------------------------------- #

@dataclass
class ClaseVista:
    """Una clase ya generada, tal como se pinta en el índice."""

    curso: str
    dia: str
    materia: str
    cuando: datetime | None
    cuando_txt: str
    duracion_min: int
    docente: str
    url: str
    ideas: int
    avisos: int
    cobertura: float
    tiene_visor: bool
    video_vivo: bool
    expira: int | None
    actualizado: str
    grabacion: str


@dataclass
class CursoVista:
    """Una carpeta de curso con sus clases, de la más reciente a la más antigua."""

    carpeta: str
    codigo: str
    nombre: str
    clases: list[ClaseVista] = field(default_factory=list)

    @property
    def etiqueta(self) -> str:
        return self.codigo or self.carpeta


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def ruta_bajo(base: Path, *segmentos: str) -> Path | None:
    """Resuelve `base/segmentos…` solo si no se sale de `base`.

    Evita que una URL con `..` o con separadores lea archivos de fuera de
    `clases/`. Devuelve `None` si algún segmento no es aceptable.
    """
    for s in segmentos:
        if not s or s in (".", "..") or not SEGMENTO_VALIDO.match(s):
            return None
    raiz = base.resolve()
    destino = raiz.joinpath(*segmentos).resolve()
    try:
        destino.relative_to(raiz)
    except ValueError:
        return None
    return destino


def _leer_json(ruta: Path) -> dict:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fecha(valor: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(valor or ""))
    except ValueError:
        return None


def _texto_fecha(dt: datetime | None) -> str:
    return dt.strftime("%d/%m/%Y · %H:%M") if dt else "—"


def video_vigente(visor: Path, ahora: float | None = None,
                  cache: dict | None = None) -> tuple[bool, int | None]:
    """¿Las URLs firmadas del visor siguen vigentes?

    Se lee el `Expires` incrustado en `visor.html`; no se pregunta nada a Class.
    """
    if not visor.is_file():
        return (False, None)
    ahora = time.time() if ahora is None else ahora
    try:
        marca = visor.stat().st_mtime
    except OSError:
        return (False, None)

    clave = (str(visor), marca)
    if cache is not None and clave in cache:
        expira = cache[clave]
    else:
        try:
            contenido = visor.read_text(encoding="utf-8", errors="replace")
        except OSError:
            expira = None
        else:
            momentos = [int(x) for x in EXPIRES.findall(contenido)]
            expira = max(momentos) if momentos else None
        if cache is not None:
            cache[clave] = expira

    if expira is None:
        return (False, None)
    return (expira > ahora, expira)


# --------------------------------------------------------------------------- #
# Escaneo
# --------------------------------------------------------------------------- #

def _clase(carpeta: Path, curso: str, ahora: float,
           cache: dict) -> ClaseVista | None:
    meta = _leer_json(carpeta / NOMBRE_META)
    datos = _leer_json(carpeta / NOMBRE_DATOS)
    if not meta and not datos:
        return None

    fusion = datos.get("fusion") or {}
    cuando = _fecha(meta.get("cuando"))
    visor = carpeta / NOMBRE_VISOR
    vivo, expira = video_vigente(visor, ahora, cache)

    duracion = float(meta.get("duracion_s") or 0)
    if not duracion:
        try:
            duracion = float((datos.get("clase") or {}).get("duracion_s") or 0)
        except (TypeError, ValueError):
            duracion = 0.0

    return ClaseVista(
        curso=curso,
        dia=carpeta.name,
        materia=str(meta.get("materia") or (datos.get("clase") or {}).get("materia") or curso),
        cuando=cuando,
        cuando_txt=_texto_fecha(cuando),
        duracion_min=round(duracion / 60) if duracion else 0,
        docente=str(meta.get("docente") or ""),
        url=str(meta.get("url") or ""),
        ideas=len(fusion.get("ideas") or []),
        avisos=len(fusion.get("avisos") or []),
        cobertura=float(datos.get("cobertura") or 0.0),
        tiene_visor=visor.is_file(),
        video_vivo=vivo,
        expira=expira,
        actualizado=str(meta.get("actualizado") or ""),
        grabacion=str(meta.get("recording_id") or ""),
    )


def escanear(base: Path | None = None) -> list[CursoVista]:
    """Devuelve todos los cursos con sus clases. Cuesta milisegundos."""
    base = base or BASE
    if not base.is_dir():
        return []

    declarados = {c.carpeta: c for c in registro.cargar_registro()}
    ahora = time.time()
    cache: dict = {}
    salida: list[CursoVista] = []

    for carpeta in sorted(p for p in base.iterdir() if p.is_dir()):
        conocida = declarados.get(carpeta.name)
        vista = CursoVista(
            carpeta=carpeta.name,
            codigo=conocida.codigo if conocida else "",
            nombre=conocida.nombre if conocida else carpeta.name,
        )
        for sub in carpeta.iterdir():
            if not sub.is_dir():
                continue
            clase = _clase(sub, carpeta.name, ahora, cache)
            if clase is not None:
                vista.clases.append(clase)
        vista.clases.sort(
            key=lambda c: (c.cuando.timestamp() if c.cuando else 0.0, c.dia),
            reverse=True,
        )
        if vista.clases:
            salida.append(vista)

    salida.sort(key=lambda c: c.nombre.lower())
    return salida


def total_clases(cursos: list[CursoVista]) -> int:
    return sum(len(c.clases) for c in cursos)


def buscar_por_url(url: str, base: Path | None = None) -> tuple[str, str] | None:
    """Localiza `(curso, dia)` a partir de la URL, leyendo `clase.json`.

    Es el respaldo cuando el CLI no imprime la ruta de la clase.
    """
    from clase_resumen.fetch import PATRON_REPLAY

    m = PATRON_REPLAY.search(url or "")
    if not m:
        return None
    objetivo = m["recording_id"]
    base = base or BASE
    for cursos_dir in base.iterdir() if base.is_dir() else []:
        if not cursos_dir.is_dir():
            continue
        for carpeta in cursos_dir.iterdir():
            if not carpeta.is_dir():
                continue
            meta = _leer_json(carpeta / NOMBRE_META)
            if str(meta.get("recording_id") or "") == objetivo:
                return (cursos_dir.name, carpeta.name)
    return None
