"""Servidor HTTP de la interfaz. Solo biblioteca estándar.

Se liga a 127.0.0.1: es una herramienta local, no debe verse desde la red.
Todas las rutas que tocan el disco pasan por `catalogo.ruta_bajo()`, que impide
salirse de `clases/`.
"""

from __future__ import annotations

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import catalogo, paginas
from .trabajos import Cola

RAIZ = Path(__file__).resolve().parent.parent
ESTATICOS = Path(__file__).resolve().parent / "static"
BASE_CLASES = RAIZ / "clases"

#: El visor se sirve tal cual; todo lo demás son descargas.
TIPOS = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def salud() -> dict:
    """Estado del modelo, sin llamar al proveedor."""
    from clase_resumen.llm import cargar

    info: dict = {"modelo": None, "base": None, "modo": None, "error": None}
    try:
        modelo = cargar()
    except Exception as e:  # noqa: BLE001 - se muestra en la UI
        info["error"] = str(e)
        return info
    extra = modelo.extra or {}
    info["modelo"] = modelo.model
    info["base"] = modelo.base_url
    info["modo"] = (
        extra.get("reasoning_effort")
        or extra.get("reasoning_budget")
        or "por defecto"
    )
    return info


class Manejador(BaseHTTPRequestHandler):
    servidor_version = "ResumenWeb/1.0"
    cola: Cola                     # lo inyecta `crear_servidor`
    candado_escaneo = threading.Lock()

    # -- utilidades de respuesta ---------------------------------------- #

    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str,
                extra: dict | None = None) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for clave, valor in (extra or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def _html(self, codigo: int, texto: str) -> None:
        self._enviar(codigo, texto.encode("utf-8"), "text/html; charset=utf-8")

    def _json(self, codigo: int, datos: dict) -> None:
        self._enviar(codigo, json.dumps(datos).encode("utf-8"),
                     "application/json; charset=utf-8")

    def _error(self, codigo: int, mensaje: str) -> None:
        self._json(codigo, {"error": mensaje})

    def log_message(self, formato: str, *args) -> None:
        """Silencia el log por petición: el polling cada 2 s lo haría ilegible."""
        return

    # -- validaciones ---------------------------------------------------- #

    def _origen_ok(self) -> bool:
        """Rechaza POST que no vengan de esta misma página (CSRF)."""
        origen = self.headers.get("Origin")
        if origen:
            anfitrion = self.headers.get("Host", "")
            return urlparse(origen).netloc == anfitrion
        # sin Origin (curl, tests) se acepta: solo escucha en loopback
        return True

    def _cuerpo(self) -> dict:
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if largo <= 0 or largo > 64_000:
            return {}
        crudo = self.rfile.read(largo)
        tipo = (self.headers.get("Content-Type") or "").lower()
        try:
            if "application/json" in tipo:
                return json.loads(crudo.decode("utf-8"))
            from urllib.parse import parse_qs
            return {k: v[0] for k, v in parse_qs(crudo.decode("utf-8")).items()}
        except (ValueError, UnicodeDecodeError):
            return {}

    def _clase(self, curso: str, dia: str, nombre: str) -> Path | None:
        carpeta = catalogo.ruta_bajo(BASE_CLASES, curso, dia)
        if carpeta is None or not carpeta.is_dir():
            return None
        archivo = catalogo.ruta_bajo(carpeta, nombre)
        if archivo is None or not archivo.is_file():
            return None
        return archivo

    # -- GET ------------------------------------------------------------- #

    def do_HEAD(self) -> None:      # noqa: N802 - API de BaseHTTPRequestHandler
        self.do_GET()

    def do_GET(self) -> None:       # noqa: N802
        ruta = urlparse(self.path).path
        partes = [unquote(p) for p in ruta.split("/") if p]

        try:
            if ruta in ("/", "/index.html"):
                with self.candado_escaneo:
                    cursos = catalogo.escanear(BASE_CLASES)
                self._html(200, paginas.indice(cursos, salud()))
                return

            if ruta == "/api/salud":
                info = salud()
                with self.candado_escaneo:
                    cursos = catalogo.escanear(BASE_CLASES)
                info["cursos"] = len(cursos)
                info["clases"] = catalogo.total_clases(cursos)
                self._json(200 if not info.get("error") else 503, info)
                return

            if ruta == "/api/cursos":
                with self.candado_escaneo:
                    cursos = catalogo.escanear(BASE_CLASES)
                self._html(200, paginas.fragmento_cursos(cursos))
                return

            if len(partes) == 2 and partes[0] == "static":
                self._estatico(partes[1])
                return

            if len(partes) == 3 and partes[0] == "ver":
                archivo = self._clase(partes[1], partes[2], catalogo.NOMBRE_VISOR)
                self._archivo(archivo, "text/html; charset=utf-8")
                return

            if len(partes) == 3 and partes[0] == "md":
                archivo = self._clase(partes[1], partes[2], catalogo.NOMBRE_RESUMEN)
                if archivo is None:
                    self._error(404, "No hay resumen en Markdown para esa clase.")
                    return
                nombre = f"{partes[2]}-{partes[1]}.md"
                self._archivo(
                    archivo, "text/markdown; charset=utf-8",
                    extra={"Content-Disposition": f'attachment; filename="{nombre}"'},
                )
                return

            if len(partes) == 2 and partes[0] == "trabajo":
                trabajo = self.cola.obtener(partes[1])
                if trabajo is None:
                    self._error(404, "Ese trabajo ya no existe (el servidor se reinició).")
                    return
                self._json(200, trabajo.como_dict())
                return

            self._error(404, "Ruta no encontrada.")

        except BrokenPipeError:
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._error(500, "Error interno del servidor.")

    def _estatico(self, nombre: str) -> None:
        archivo = catalogo.ruta_bajo(ESTATICOS, nombre)
        if archivo is None or not archivo.is_file():
            self._error(404, "Recurso no encontrado.")
            return
        tipo = TIPOS.get(archivo.suffix.lower()) or "application/octet-stream"
        datos = archivo.read_bytes()
        self._enviar(200, datos, tipo)

    def _archivo(self, archivo: Path | None, tipo: str,
                 extra: dict | None = None) -> None:
        if archivo is None:
            self._error(404, "Esa clase no existe o no tiene ese archivo.")
            return
        datos = archivo.read_bytes()
        self._enviar(200, datos, tipo, extra)

    # -- POST ------------------------------------------------------------ #

    def do_POST(self) -> None:      # noqa: N802
        ruta = urlparse(self.path).path
        partes = [unquote(p) for p in ruta.split("/") if p]

        if not self._origen_ok():
            self._error(403, "Origen no permitido.")
            return

        try:
            if ruta == "/nueva":
                cuerpo = self._cuerpo()
                url = str(cuerpo.get("url") or "").strip()
                if not url:
                    self._error(400, "Falta el enlace de la clase.")
                    return
                from clase_resumen.fetch import PATRON_REPLAY
                if not PATRON_REPLAY.search(url):
                    self._error(400, catalogo_mensaje_enlace())
                    return
                trabajo = self.cola.crear(url, "generar")
                self._json(202, trabajo.como_dict())
                return

            if len(partes) == 3 and partes[0] in ("renovar", "regenerar"):
                curso, dia = partes[1], partes[2]
                carpeta = catalogo.ruta_bajo(BASE_CLASES, curso, dia)
                if carpeta is None or not carpeta.is_dir():
                    self._error(404, "Esa clase no existe.")
                    return
                if partes[0] == "renovar":
                    trabajo = self.cola.crear(
                        self._url_guardada(carpeta), "renovar")
                else:
                    guardada = self._url_guardada(carpeta)
                    if not guardada:
                        self._error(
                            400,
                            "Esta clase no guardó el enlace original, así que no se "
                            "puede regenerar desde aquí.",
                        )
                        return
                    trabajo = self.cola.crear(guardada, "regenerar")
                self._json(202, trabajo.como_dict())
                return

            self._error(404, "Ruta no encontrada.")

        except BrokenPipeError:
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._error(500, "Error interno del servidor.")

    @staticmethod
    def _url_guardada(carpeta: Path) -> str:
        try:
            meta = json.loads((carpeta / catalogo.NOMBRE_META).read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        return str(meta.get("url") or "").strip()


def catalogo_mensaje_enlace() -> str:
    return (
        "El enlace no parece una repetición de Class. Debe verse así: "
        "https://<tu-insti>.class.com/player/recording/<clase>/<grabación>"
    )


# --------------------------------------------------------------------------- #
# Arranque
# --------------------------------------------------------------------------- #

def crear_servidor(host: str = "127.0.0.1", puerto: int = 8765) -> ThreadingHTTPServer:
    cola = Cola(RAIZ)
    manejador = type("ManejadorConCola", (Manejador,), {"cola": cola})
    servidor = ThreadingHTTPServer((host, puerto), manejador)
    servidor.daemon_threads = True
    servidor.cola = cola                    # para poder pararlo desde fuera
    return servidor


def arrancar(host: str = "127.0.0.1", puerto: int = 8765,
             abrir: bool = False) -> int:
    servidor = crear_servidor(host, puerto)
    url = f"http://{host}:{puerto}/"
    print(f"  Resúmenes de clase → {url}")
    print("  Ctrl+C para detener.\n")

    if abrir:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  Cerrando…")
    finally:
        try:
            servidor.cola.parar()
        except Exception:  # noqa: BLE001
            pass
        servidor.server_close()
    return 0
