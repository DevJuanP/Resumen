"""Cola de trabajos: un solo worker que ejecuta el CLI como subproceso.

El progreso se lee del stdout de `resumen.py`, que tiene tres particularidades
que condicionan todo este módulo:

1. **Avanza con `\\r`, no con `\\n`.** `cli.main` hace
   ``print(f"\\r  bloques {i}/{total}", end="")``. Un lector por líneas no vería
   nada hasta el final.
2. **Incluye códigos ANSI siempre.** `_gris()` los emite aunque no sea Windows
   Terminal, así que el texto hay que limpiarlo antes de interpretarlo.
3. **La ruta final de la clase solo existe en el texto.** Se captura de la línea
   ``  Clase: <ruta>``; el respaldo es buscar por `recording_id` en disco.

El subproceso se usa en vez de importar `cli.main` a propósito: aísla un fallo
del motor, permite matarlo por timeout y no comparte estado global con el
servidor web.
"""

from __future__ import annotations

import codecs
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Un trabajo no debería pasar de aquí. El récord medido es 548 s.
TIMEOUT_S = 20 * 60

#: Códigos de color que emite `cli._gris()` / `_verde()`.
ANSI = re.compile(r"\x1b\[[0-9;]*m")

#: Argumentos del CLI según lo que se quiera hacer.
ARGUMENTOS = {
    "generar": ("--visor",),
    "regenerar": ("--forzar", "--visor"),
    "renovar": ("--solo-visor",),
}

#: Texto inicial que ve el usuario antes de que el CLI diga nada.
MENSAJE_INICIAL = {
    "generar": "En cola…",
    "regenerar": "En cola…",
    "renovar": "Renovando los enlaces del video…",
}

ACTIVOS = ("en_cola", "descargando", "resumiendo", "sintetizando", "escribiendo")


# --------------------------------------------------------------------------- #
# Interpretación del texto del CLI
# --------------------------------------------------------------------------- #

@dataclass
class Avance:
    """Lo que una línea suelta del CLI puede aportar al estado del trabajo."""

    estado: str | None = None
    fase_txt: str | None = None
    bloques_ok: int | None = None
    bloques_total: int | None = None
    ubicacion: str | None = None
    ya_existia: bool = False
    error: str | None = None


_RE_BLOQUES = re.compile(r"^bloques\s+(\d+)\s*/\s*(\d+)$")
_RE_CLASE = re.compile(r"^Clase:\s*(.+)$")
_RE_RESUMIENDO = re.compile(r"Resumiendo con\b")


def interpretar(linea: str) -> Avance:
    """Traduce una línea de stdout del CLI a un cambio de estado.

    Es una función pura para poder probarla con muestras reales sin lanzar el
    motor ni tocar la red.
    """
    texto = ANSI.sub("", linea).strip()
    if not texto:
        return Avance()

    m = _RE_BLOQUES.match(texto)
    if m:
        hechos, total = int(m.group(1)), int(m.group(2))
        return Avance(
            estado="resumiendo",
            fase_txt=f"Analizando bloques {hechos}/{total}…",
            bloques_ok=hechos,
            bloques_total=total,
        )

    m = _RE_CLASE.match(texto)
    if m:
        return Avance(ubicacion=m.group(1).strip())

    if "Descargando la transcripción" in texto:
        return Avance(estado="descargando",
                      fase_txt="Descargando la transcripción…")

    if _RE_RESUMIENDO.search(texto):
        return Avance(estado="resumiendo",
                      fase_txt="Resumiendo los bloques de la clase…")

    if "Ya existe y está actualizado" in texto:
        return Avance(ya_existia=True,
                      fase_txt="Ya estaba hecho: no se gastó cuota")

    if texto.startswith("✗"):
        return Avance(estado="error", error=texto.lstrip("✗").strip())

    if texto.startswith("✓"):
        if texto.endswith(".html") or ".html" in texto:
            return Avance(estado="escribiendo", fase_txt="Guardando el visor…")
        return Avance(estado="escribiendo", fase_txt="Guardando los apuntes…")

    return Avance()


class Partidor:
    """Corta un flujo de texto en líneas aceptando `\\r` y `\\n`.

    Es la pieza que evita el fallo clásico: `readline()` sobre el stdout del CLI
    no devuelve nada durante minutos porque el progreso termina en `\\r`.
    """

    def __init__(self) -> None:
        self._resto = ""

    def alimentar(self, trozo: str) -> list[str]:
        self._resto += trozo
        partes = re.split(r"[\r\n]", self._resto)
        self._resto = partes.pop()
        return [p for p in partes if p.strip()]

    def vaciar(self) -> list[str]:
        resto, self._resto = self._resto, ""
        return [resto] if resto.strip() else []


def derivar_ubicacion(ruta: str | None, url: str) -> tuple[str, str] | None:
    """De la ruta impresa por el CLI saca `(curso, dia)`.

    La ruta es `<…>/clases/<curso>/<dia>`, así que basta con los dos últimos
    componentes. Si no hay ruta se busca en disco por `recording_id`.
    """
    if ruta:
        partes = Path(ruta).parts
        if len(partes) >= 2:
            return (partes[-2], partes[-1])
    try:
        from . import catalogo
        return catalogo.buscar_por_url(url)
    except Exception:  # noqa: BLE001 - el respaldo nunca debe tumbar el trabajo
        return None


# --------------------------------------------------------------------------- #
# Trabajo
# --------------------------------------------------------------------------- #

@dataclass
class Trabajo:
    id: str
    url: str
    modo: str
    estado: str = "en_cola"
    fase_txt: str = "En cola…"
    bloques_ok: int = 0
    bloques_total: int = 0
    inicio: float = field(default_factory=time.time)
    fin: float | None = None
    resultado: tuple[str, str] | None = None
    error: str = ""
    ya_existia: bool = False
    salida: list[str] = field(default_factory=list)
    _ubicacion: str | None = None

    @property
    def activo(self) -> bool:
        return self.estado in ACTIVOS

    @property
    def transcurrido(self) -> int:
        return int((self.fin or time.time()) - self.inicio)

    def como_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "modo": self.modo,
            "estado": self.estado,
            "fase": self.fase_txt,
            "bloques_ok": self.bloques_ok,
            "bloques_total": self.bloques_total,
            "transcurrido": self.transcurrido,
            "resultado": list(self.resultado) if self.resultado else None,
            "error": self.error,
            "ya_existia": self.ya_existia,
            "activo": self.activo,
        }


# --------------------------------------------------------------------------- #
# Cola
# --------------------------------------------------------------------------- #

class Cola:
    """Un solo worker: nunca hay dos clases procesándose a la vez.

    Importa porque cada clase son 14 llamadas al modelo con 3 hilos internos
    (`MAX_HILOS = 3`). Con un worker, el proveedor nunca recibe más de tres
    peticiones simultáneas, aunque se pulsen varios botones.
    """

    def __init__(self, base: Path | None = None) -> None:
        self._base = base or RAIZ
        self._trabajos: dict[str, Trabajo] = {}
        self._candado = threading.Lock()
        self._pendientes: queue.Queue[Trabajo | None] = queue.Queue()
        self._hilo = threading.Thread(
            target=self._ciclo, name="trabajos", daemon=True
        )
        self._hilo.start()

    # -- API ------------------------------------------------------------- #

    def crear(self, url: str, modo: str = "generar") -> Trabajo:
        """Encola un trabajo, o devuelve el que ya está en curso para esa URL."""
        url = (url or "").strip()
        if modo not in ARGUMENTOS:
            raise ValueError(f"modo desconocido: {modo}")

        with self._candado:
            for t in self._trabajos.values():
                if t.activo and t.url == url:
                    return t
            trabajo = Trabajo(
                id=uuid.uuid4().hex,
                url=url,
                modo=modo,
                fase_txt=MENSAJE_INICIAL.get(modo, "En cola…"),
            )
            self._trabajos[trabajo.id] = trabajo

        self._pendientes.put(trabajo)
        return trabajo

    def obtener(self, id_: str) -> Trabajo | None:
        with self._candado:
            return self._trabajos.get(id_)

    def encolados(self) -> int:
        return self._pendientes.qsize()

    def parar(self) -> None:
        self._pendientes.put(None)

    # -- bucle del worker ------------------------------------------------ #

    def _ciclo(self) -> None:
        while True:
            trabajo = self._pendientes.get()
            if trabajo is None:
                return
            try:
                self._ejecutar(trabajo)
            except Exception as e:  # noqa: BLE001 - el worker no debe morir
                self._fijar(trabajo, estado="error",
                            error=f"Fallo interno de la interfaz: {e}",
                            fin=time.time())

    def _fijar(self, t: Trabajo, **cambios) -> None:
        with self._candado:
            for clave, valor in cambios.items():
                setattr(t, clave, valor)

    def _anotar(self, t: Trabajo, linea: str) -> None:
        with self._candado:
            t.salida.append(linea)
            del t.salida[:-60]

    def _aplicar(self, t: Trabajo, avance: Avance) -> None:
        with self._candado:
            if avance.error:
                t.estado = "error"
                t.error = avance.error
                t.fase_txt = avance.error
                return
            if avance.ubicacion:
                t._ubicacion = avance.ubicacion
            if avance.ya_existia:
                t.ya_existia = True
            if avance.bloques_total is not None:
                t.bloques_ok = avance.bloques_ok or 0
                t.bloques_total = avance.bloques_total
                # Tras el último bloque solo queda la llamada de síntesis.
                if t.bloques_ok >= t.bloques_total:
                    t.estado = "sintetizando"
                    t.fase_txt = "Ordenando la clase por importancia…"
                    return
            if avance.estado:
                t.estado = avance.estado
            if avance.fase_txt:
                t.fase_txt = avance.fase_txt

    # -- ejecución ------------------------------------------------------- #

    def _ejecutar(self, t: Trabajo) -> None:
        argumentos = ARGUMENTOS.get(t.modo, ("--visor",))
        orden = [sys.executable, "resumen.py", t.url, *argumentos]

        entorno = dict(os.environ)
        # Sin esto, los ✓ y … se rompen en la consola de Windows (cp1252).
        entorno["PYTHONIOENCODING"] = "utf-8"
        entorno["PYTHONUNBUFFERED"] = "1"

        try:
            proceso = subprocess.Popen(
                orden,
                cwd=str(self._base),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # un solo flujo: sin interbloqueos
                bufsize=0,
                env=entorno,
            )
        except OSError as e:
            self._fijar(t, estado="error",
                        error=f"No se pudo ejecutar el motor: {e}",
                        fin=time.time())
            return

        if t.modo == "generar":
            self._fijar(t, estado="en_cola", fase_txt="Arrancando el motor…")

        self._bombear(t, proceso)
        codigo = proceso.wait()
        self._finalizar(t, codigo)

    def _bombear(self, t: Trabajo, proceso: subprocess.Popen) -> None:
        """Lee el flujo hasta el final, respetando el timeout."""
        if proceso.stdout is None:      # pragma: no cover - defensivo
            return

        tramos: queue.Queue = queue.Queue()

        def leer() -> None:
            try:
                while True:
                    trozo = proceso.stdout.read(4096)
                    if not trozo:
                        break
                    tramos.put(trozo)
            finally:
                tramos.put(None)

        threading.Thread(target=leer, name="lector", daemon=True).start()

        limite = time.time() + TIMEOUT_S
        partidor = Partidor()
        decodificador = codecs.getincrementaldecoder("utf-8")(errors="replace")

        while True:
            restante = limite - time.time()
            if restante <= 0:
                proceso.kill()
                self._fijar(t, estado="error",
                            error="Se agotó el tiempo de espera (20 min).",
                            fase_txt="Tiempo agotado",
                            fin=time.time())
                return
            try:
                trozo = tramos.get(timeout=min(1.0, restante))
            except queue.Empty:
                continue

            terminado = trozo is None
            texto = decodificador.decode(b"" if terminado else trozo, terminado)
            for linea in partidor.alimentar(texto):
                self._procesar(t, linea)
            if terminado:
                break

        for linea in partidor.vaciar():
            self._procesar(t, linea)

    def _procesar(self, t: Trabajo, linea: str) -> None:
        self._anotar(t, ANSI.sub("", linea).strip())
        self._aplicar(t, interpretar(linea))

    def _finalizar(self, t: Trabajo, codigo: int) -> None:
        with self._candado:
            if t.estado == "error":
                t.fin = time.time()
                return
            if codigo == 0:
                t.estado = "listo"
                t.resultado = derivar_ubicacion(t._ubicacion, t.url)
                t.fase_txt = ("Ya estaba hecho, no se gastó cuota"
                              if t.ya_existia else "Resumen listo")
                t.error = ""
            else:
                t.estado = "error"
                t.error = t.error or "El motor terminó con errores."
                t.fase_txt = t.error
            t.fin = time.time()
