"""Almacenamiento en disco: una carpeta por clase dentro de la carpeta del curso.

Estructura resultante:

    clases/
      DCGS12424-Pruebas-de-Software/
        2026-11-03/
          resumen.md            apuntes (se reescribe al actualizar)
          resumen.json          datos estructurados
          visor.html            visor con video
          clase.json            metadatos: fecha, ids, huella
          transcripcion.json    segmentos, para re-renderizar sin la plataforma

La carpeta de la clase se nombra con la fecha. Si el mismo día hubiera dos clases
distintas del mismo curso, la segunda añade la hora: `2026-11-03-2100`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .fetch import Clase, Segmento

NOMBRE_RESUMEN = "resumen.md"
NOMBRE_DATOS = "resumen.json"
NOMBRE_VISOR = "visor.html"
NOMBRE_META = "clase.json"
NOMBRE_TRANSCRIPCION = "transcripcion.json"


@dataclass
class Ubicacion:
    """Rutas de los archivos de una clase."""

    carpeta: Path

    @property
    def resumen(self) -> Path:
        return self.carpeta / NOMBRE_RESUMEN

    @property
    def datos(self) -> Path:
        return self.carpeta / NOMBRE_DATOS

    @property
    def visor(self) -> Path:
        return self.carpeta / NOMBRE_VISOR

    @property
    def meta(self) -> Path:
        return self.carpeta / NOMBRE_META

    @property
    def transcripcion(self) -> Path:
        return self.carpeta / NOMBRE_TRANSCRIPCION

    @property
    def existe(self) -> bool:
        return self.resumen.is_file()


# --------------------------------------------------------------------------- #
# Lectura y escritura genérica
# --------------------------------------------------------------------------- #

def _leer_json(ruta: Path) -> dict:
    if not ruta.is_file():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _escribir_json(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def leer_meta(ubic: Ubicacion) -> dict:
    return _leer_json(ubic.meta)


def leer_datos(ubic: Ubicacion) -> dict:
    return _leer_json(ubic.datos)


def escribir_datos(ubic: Ubicacion, datos: dict) -> None:
    _escribir_json(ubic.datos, datos)


def leer_transcripcion(ubic: Ubicacion) -> list[Segmento]:
    crudo = _leer_json(ubic.transcripcion)
    salida = []
    for s in crudo.get("segmentos") or []:
        salida.append(Segmento(
            segundos=float(s.get("s", 0)),
            hablante=str(s.get("h", "")),
            texto=str(s.get("t", "")),
            rol=str(s.get("r", "estudiante")),
        ))
    return salida


def _escribir_transcripcion(ubic: Ubicacion, clase: Clase) -> None:
    _escribir_json(ubic.transcripcion, {
        "segmentos": [
            {"s": round(s.segundos, 2), "h": s.hablante, "t": s.texto, "r": s.rol}
            for s in clase.segmentos
        ]
    })


# --------------------------------------------------------------------------- #
# Ubicación de la carpeta de una clase
# --------------------------------------------------------------------------- #

def ubicar(base: Path, curso, clase: Clase) -> Ubicacion:
    """Devuelve la carpeta de esta clase, creándola si hace falta.

    Se identifica por fecha. Si ya existe una carpeta de ese día con otra
    grabación distinta, se usa la variante con hora para no pisar la anterior.
    """
    raiz = base / curso.carpeta
    raiz.mkdir(parents=True, exist_ok=True)

    dia = f"{clase.cuando:%Y-%m-%d}"
    candidatos = [dia]

    previa = _leer_json(raiz / dia / NOMBRE_META)
    anterior_id = str(previa.get("recording_id") or "")
    if anterior_id and clase.recording_id and anterior_id != clase.recording_id:
        candidatos.append(f"{dia}-{clase.cuando:%H%M}")

    for nombre in candidatos:
        carpeta = raiz / nombre
        if not carpeta.exists():
            carpeta.mkdir(parents=True, exist_ok=True)
            return Ubicacion(carpeta)
        meta = _leer_json(carpeta / NOMBRE_META)
        actual = str(meta.get("recording_id") or "")
        if not actual or not clase.recording_id or actual == clase.recording_id:
            return Ubicacion(carpeta)

    # Dos grabaciones distintas el mismo minuto: sufijo incremental.
    i = 2
    while (raiz / f"{dia}-{clase.cuando:%H%M}-{i}").exists():
        i += 1
    carpeta = raiz / f"{dia}-{clase.cuando:%H%M}-{i}"
    carpeta.mkdir(parents=True, exist_ok=True)
    return Ubicacion(carpeta)
