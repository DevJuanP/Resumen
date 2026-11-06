"""Registro de cursos y organización de los resúmenes en subcarpetas.

La plataforma Class no expone el código del curso (SPTI02423, DCGS12424…): la
respuesta de `v1_join_async_meeting` solo trae el nombre de la materia. Por eso
los cursos se declaran en `cursos.json` y el curso de cada clase se resuelve por
el nombre de la materia o pasándolo a mano con `--curso`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "cursos.json"


class ErrorDeCurso(Exception):
    """El curso no se pudo determinar."""


@dataclass
class Curso:
    codigo: str
    nombre: str
    carpeta: str
    alias: list[str] = field(default_factory=list)

    @property
    def etiqueta(self) -> str:
        return f"{self.codigo} · {self.nombre}"


def _sin_tildes(texto: str) -> str:
    """'Pruebas de Aplicaciones Móviles' -> 'pruebas de aplicaciones moviles'."""
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plano).strip().lower()


def _slug(texto: str) -> str:
    limpio = re.sub(r"[^\w\s-]", "", _sin_tildes(texto)).strip()
    return re.sub(r"[\s_]+", "-", limpio)


def cargar_registro(ruta: Path | None = None) -> list[Curso]:
    ruta = ruta or REGISTRO
    if not ruta.is_file():
        return []
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    cursos = []
    for c in datos.get("cursos") or []:
        codigo = str(c.get("codigo") or "").strip()
        nombre = str(c.get("nombre") or "").strip()
        if not codigo or not nombre:
            continue
        carpeta = str(c.get("carpeta") or "").strip()
        if not carpeta:
            carpeta = f"{codigo}-{_slug(nombre).title().replace('-', '')}"
        cursos.append(Curso(
            codigo=codigo,
            nombre=nombre,
            carpeta=carpeta,
            alias=[str(a) for a in (c.get("alias") or [])],
        ))
    return cursos


def resolver(materia: str, codigo: str | None = None,
             cursos: list[Curso] | None = None) -> Curso:
    """Determina a qué curso pertenece una clase.

    Orden: código explícito, luego coincidencia por alias en el nombre de la
    materia. Si no hay coincidencia, falla con la lista de cursos disponibles
    para que se pueda pasar `--curso`.
    """
    cursos = cursos if cursos is not None else cargar_registro()
    if not cursos:
        raise ErrorDeCurso(
            "No hay cursos declarados en cursos.json.\n"
            "Crea el archivo o usa --salida para elegir la carpeta manualmente."
        )

    if codigo:
        buscado = codigo.strip().lower()
        for c in cursos:
            if c.codigo.lower() == buscado:
                return c
        for c in cursos:
            if c.codigo.lower().startswith(buscado):
                return c
        disponibles = ", ".join(c.codigo for c in cursos)
        raise ErrorDeCurso(
            f"No existe el curso «{codigo}». Disponibles: {disponibles}"
        )

    objetivo = _sin_tildes(materia)
    for c in cursos:
        for alias in [c.nombre, *c.alias]:
            if _sin_tildes(alias) and _sin_tildes(alias) in objetivo:
                return c

    # Último intento: todas las palabras del nombre aparecen en la materia.
    for c in cursos:
        palabras = [p for p in _sin_tildes(c.nombre).split() if len(p) > 3]
        if palabras and all(p in objetivo for p in palabras):
            return c

    listado = "\n".join(f"  --curso {c.codigo}   {c.nombre}" for c in cursos)
    raise ErrorDeCurso(
        f"No se pudo asociar «{materia}» a ningún curso.\n"
        f"Indícalo con --curso:\n{listado}"
    )


def preparar(base: Path, cursos: list[Curso] | None = None) -> Path:
    """Crea la carpeta base y una subcarpeta por curso. Devuelve la base."""
    base.mkdir(parents=True, exist_ok=True)
    for c in cursos if cursos is not None else cargar_registro():
        (base / c.carpeta).mkdir(parents=True, exist_ok=True)
    return base
