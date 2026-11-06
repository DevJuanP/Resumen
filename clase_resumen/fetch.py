"""Descarga la transcripción de una repetición de clase alojada en Class.

La plataforma Class (class.com, montada sobre Zoom) guarda la transcripción
automática con hablante y marca de tiempo. El reproductor la obtiene de una
llamada `v1_join_async_meeting`, así que no hace falta descargar audio ni
transcribir nada: se pide el mismo JSON que usa el reproductor.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)

RAIZ = Path(__file__).resolve().parent.parent
UUID_FILE = RAIZ / ".uuid"


class ErrorDeClase(Exception):
    """Fallo esperado con un mensaje que se le puede mostrar al usuario."""


@dataclass
class Segmento:
    segundos: float          # desde el inicio de la grabación
    hablante: str
    texto: str
    rol: str = "estudiante"  # "docente" | "estudiante"


@dataclass
class Clase:
    url: str
    materia: str
    cuando: datetime
    duracion_s: float
    segmentos: list[Segmento] = field(default_factory=list)
    chats: list[dict] = field(default_factory=list)
    docente: str = ""
    participantes: int = 0
    grabacion: dict = field(default_factory=dict)  # datos crudos de recordingData
    api_base: str = ""
    school_id: str = ""
    class_uuid: str = ""
    recording_id: str = ""


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def _pedir(url: str, *, datos: dict | None = None, cabeceras: dict | None = None,
           timeout: int = 120) -> bytes:
    cab = {"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "identity"}
    if cabeceras:
        cab.update(cabeceras)
    cuerpo = None
    if datos is not None:
        cuerpo = json.dumps(datos).encode("utf-8")
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=cuerpo, headers=cab,
                                 method="POST" if cuerpo else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detalle = e.read()[:400].decode("utf-8", "replace")
        raise ErrorDeClase(f"La plataforma respondió {e.code} en {url}\n{detalle}") from e
    except urllib.error.URLError as e:
        raise ErrorDeClase(f"No se pudo conectar con {url}\n{e.reason}") from e


def _uuid_local() -> str:
    """Identificador estable y anónimo para pedir la grabación."""
    if os.environ.get("RESUMEN_USER_UUID"):
        return os.environ["RESUMEN_USER_UUID"]
    if UUID_FILE.exists():
        valor = UUID_FILE.read_text(encoding="utf-8").strip()
        if valor:
            return valor
    valor = str(uuid.uuid4())
    UUID_FILE.write_text(valor, encoding="utf-8")
    return valor


# --------------------------------------------------------------------------- #
# Descubrimiento de la API
# --------------------------------------------------------------------------- #

PATRON_REPLAY = re.compile(
    r"https?://(?P<host>[^/]+)/player/recording/(?P<class_uuid>[0-9a-fA-F-]{36})/(?P<recording_id>[0-9a-fA-F-]{36})"
)


def _config_del_host(host: str) -> dict:
    try:
        crudo = _pedir(f"https://{host}/player/config.json", timeout=30)
        return json.loads(crudo)
    except Exception:
        # Deducir el endpoint a partir del host: cibertec.class.com ->
        # cibertec.rest.pod-2.sa-east-1.prod.class.com
        raise ErrorDeClase(
            f"No se pudo leer la configuración del reproductor en https://{host}/player/config.json"
        )


# --------------------------------------------------------------------------- #
# Parseo de la respuesta
# --------------------------------------------------------------------------- #

def _fecha(valor: str | None) -> datetime:
    """Convierte la marca de tiempo de la plataforma (UTC) a hora local.

    Class devuelve `when` en UTC. Si no se convierte, una clase de las 19:00 en
    Lima aparece como del día siguiente y los "el jueves" de los avisos quedan
    corridos un día.
    """
    if not valor:
        return datetime.now().astimezone()
    texto = valor.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone()


def _normalizar_nombre(nombre: str) -> str:
    """'EDISON LORENZO MERINO VILLAGARAY' -> 'Edison Merino'.

    Los nombres peruanos completos siguen el patrón nombres + apellido paterno +
    apellido materno. Con cuatro o más palabras el segundo nombre es el primero
    del medio; con tres, ese hueco es directamente el apellido paterno.
    """
    if not nombre:
        return "Sin nombre"
    partes = [p for p in re.split(r"\s+", nombre.strip()) if p]
    if len(partes) >= 4:
        return f"{partes[0].title()} {partes[2].title()}"
    if len(partes) >= 2:
        return f"{partes[0].title()} {partes[1].title()}"
    return partes[0].title() if partes else "Sin nombre"


RUIDO_EXACTO = {
    "this meeting is being recorded.",
    "this meeting is being recorded",
    "recording...",
}


def _es_ruido(texto: str) -> bool:
    limpio = texto.strip().lower()
    return not limpio or limpio in RUIDO_EXACTO


def obtener_clase(url: str) -> Clase:
    """Descarga y normaliza una repetición a partir de su URL pública."""
    m = PATRON_REPLAY.search(url.strip())
    if not m:
        raise ErrorDeClase(
            "El enlace no parece una repetición de Class.\n"
            "Debe verse así: https://<tu-insti>.class.com/player/recording/<clase>/<grabación>"
        )
    host, class_uuid, recording_id = m["host"], m["class_uuid"], m["recording_id"]
    cfg = _config_del_host(host)
    api = cfg.get("api", "").rstrip("/")
    if not api:
        raise ErrorDeClase("La configuración del reproductor no incluye la API.")

    crudo = _pedir(
        f"{api}/meeting/{class_uuid}/v1_join_async_meeting",
        datos={"recordingUuid": recording_id},
        cabeceras={"user_uuid": _uuid_local(), "Origin": f"https://{host}",
                   "Referer": f"https://{host}/"},
    )
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError as e:
        raise ErrorDeClase("La plataforma devolvió una respuesta ilegible.") from e

    rec = datos.get("recordingData") or {}
    if not rec.get("transcripts") and not rec.get("artifacts"):
        raise ErrorDeClase(
            "La grabación existe pero todavía no tiene transcripción publicada.\n"
            "Suele tardar unas horas después de la clase; vuelve a intentarlo más tarde."
        )

    inicio_ms = _fecha(rec.get("when")).timestamp() * 1000
    if not inicio_ms:
        inicio_ms = min((t.get("timestamp", 0) for t in rec.get("transcripts") or []), default=0)

    # Rol de cada participante según la lista de asistentes.
    # Puede haber varios docentes en la sala (el titular y un invitado). El
    # "docente" de la clase es el que realmente habla, no el primero de la lista:
    # el orden de `students` no es estable entre peticiones.
    roles = {}
    docentes: list[str] = []
    for p in datos.get("students") or []:
        nombre = p.get("user_name") or ""
        if p.get("role") in ("teacher", "host", "co-host"):
            roles[nombre] = "docente"
            docentes.append(nombre)
        else:
            roles[nombre] = "estudiante"

    segmentos: list[Segmento] = []
    for t in sorted(rec.get("transcripts") or [], key=lambda x: x.get("timestamp") or 0):
        d = t.get("data") or {}
        texto = (t.get("override_text") or d.get("content") or t.get("content") or "").strip()
        if _es_ruido(texto):
            continue
        nombre = d.get("user_name") or "Participante"
        segundos = max(0.0, ((t.get("timestamp") or inicio_ms) - inicio_ms) / 1000.0)
        segmentos.append(Segmento(
            segundos=segundos,
            hablante=_normalizar_nombre(nombre),
            texto=texto,
            rol=roles.get(nombre, "estudiante"),
        ))

    # El docente titular es el que acumula más intervenciones.
    if docentes:
        conteo = {n: 0 for n in docentes}
        for t in rec.get("transcripts") or []:
            quien = (t.get("data") or {}).get("user_name")
            if quien in conteo:
                conteo[quien] += 1
        docente = max(conteo, key=lambda n: conteo[n])

    duracion = float(rec.get("duration") or 0)
    if not duracion and segmentos:
        duracion = segmentos[-1].segundos

    materia = (datos.get("meetingTopic") or rec.get("name") or "Clase").strip()
    materia = re.sub(r"\s*-\s*PROF\..*$", "", materia, flags=re.IGNORECASE).strip()

    return Clase(
        url=url.strip(),
        materia=materia or "Clase",
        cuando=_fecha(rec.get("when")),
        duracion_s=duracion,
        segmentos=segmentos,
        chats=datos.get("chats") or [],
        docente=_normalizar_nombre(docente),
        participantes=len(datos.get("students") or []),
        grabacion=rec,
        api_base=api,
        school_id=str(rec.get("schoolId") or ""),
        class_uuid=class_uuid,
        recording_id=recording_id,
    )


# --------------------------------------------------------------------------- #
# Artefactos (video y subtítulos firmados)
# --------------------------------------------------------------------------- #

def urls_de_video(clase: Clase) -> dict[str, str]:
    """Devuelve URLs firmadas (12 h) de los videos de la grabación."""
    if not (clase.api_base and clase.school_id):
        return {}
    contenidos = "active_speaker,shared_screen,audio_transcript,closed_caption"
    url = (
        f"{clase.api_base}/recording/v1/schools/{clase.school_id}"
        f"/class/{clase.class_uuid}/recordings/{clase.recording_id}"
        f"/artifacts?contents_list={contenidos}"
    )
    crudo = _pedir(url, cabeceras={"user_uuid": _uuid_local()}, timeout=60)
    datos = json.loads(crudo)
    salida = {}
    for a in datos.get("artifacts") or []:
        if a.get("contents") and a.get("url"):
            salida[a["contents"]] = a["url"]
    return salida


# --------------------------------------------------------------------------- #
# Modo alternativo: pegar el texto del panel "Transcripción"
# --------------------------------------------------------------------------- #

HORA = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?\s*$", re.IGNORECASE)


def clase_desde_texto(ruta: Path, materia: str = "Clase") -> Clase:
    """Interpreta una transcripción copiada del panel de Class.

    Formato esperado (el que muestra la interfaz al copiar):
        NOMBRE DEL HABLANTE   07:01:11 p. m.
        Texto de lo que dijo.
    También acepta líneas con el formato `[mm:ss] Nombre: texto`.
    """
    lineas = [l.rstrip() for l in ruta.read_text(encoding="utf-8", errors="replace").splitlines()]
    segmentos: list[Segmento] = []
    actual: tuple[str, float] | None = None
    buffer: list[str] = []

    def volcar():
        nonlocal buffer, actual
        if actual and buffer:
            texto = " ".join(x.strip() for x in buffer if x.strip())
            if texto:
                segmentos.append(Segmento(segundos=actual[1], hablante=_normalizar_nombre(actual[0]),
                                          texto=texto, rol="estudiante"))
        buffer = []

    patron_linea = re.compile(r"^\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*([^:]{2,60}):\s*(.+)$")
    base: float | None = None
    for linea in lineas:
        if not linea.strip():
            continue
        m = patron_linea.match(linea.strip())
        if m:
            h, mi, s, quien, texto = m.groups()
            seg = int(h) * 3600 + int(mi) * 60 + int(s or 0) if s else int(h) * 60 + int(mi)
            volcar()
            actual = (quien.strip(), float(seg))
            buffer = [texto]
            continue
        # "NOMBRE   19:45:38" en una línea, el texto en las siguientes.
        partes = re.split(r"\s{2,}", linea.strip())
        if len(partes) >= 2:
            hora = HORA.match(partes[-1])
            nombre = " ".join(partes[:-1]).strip()
            if hora and nombre and len(nombre) > 3:
                h, mi, s, ampm = hora.groups()
                seg = int(h) * 3600 + int(mi) * 60 + int(s or 0) if s else int(h) * 60 + int(mi)
                if ampm:
                    seg = (seg % 43200) + (43200 if ampm.lower().startswith("p") else 0)
                volcar()
                base = seg if base is None else base
                actual = (nombre, float(seg - base))
                continue
        if actual is not None:
            buffer.append(linea)
    volcar()

    if not segmentos:
        raise ErrorDeClase(
            f"No se reconoció ninguna intervención en {ruta.name}.\n"
            "Copia el panel 'Transcripción' completo, con el nombre y la hora en una línea."
        )

    duracion = segmentos[-1].segundos
    return Clase(
        url="",
        materia=materia,
        cuando=datetime.now(UTC),
        duracion_s=duracion,
        segmentos=segmentos,
        docente="",
    )
