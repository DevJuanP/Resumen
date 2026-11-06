"""Pruebas de la interfaz web. Sin red y sin llamar al modelo.

    python -m unittest discover -s pruebas -v

Cubren las tres piezas donde un error no se vería hasta ejecutar el motor de
verdad: el parser del progreso (que avanza con `\\r`), la resolución segura de
rutas y el contrato de argumentos con el CLI.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from web import catalogo, paginas            # noqa: E402
from web.trabajos import (                   # noqa: E402
    ANSI, ARGUMENTOS, Partidor, derivar_ubicacion, es_error_conocido, interpretar,
)


class TestPartidor(unittest.TestCase):
    """El progreso del CLI usa `\\r`; un lector por líneas no vería nada."""

    def test_corta_por_retorno_de_carro(self):
        """Sin terminador final, la última línea se entrega en `vaciar()`."""
        p = Partidor()
        self.assertEqual(p.alimentar("\r  bloques 1/13\r  bloques 2/13"),
                         ["  bloques 1/13"])
        self.assertEqual(p.vaciar(), ["  bloques 2/13"])

    def test_varias_lineas_terminadas(self):
        p = Partidor()
        self.assertEqual(p.alimentar("\r  bloques 1/13\r  bloques 2/13\r"),
                         ["  bloques 1/13", "  bloques 2/13"])

    def test_corta_por_salto_de_linea(self):
        p = Partidor()
        self.assertEqual(p.alimentar("uno\ndos\n"), ["uno", "dos"])

    def test_conserva_el_trozo_incompleto(self):
        p = Partidor()
        self.assertEqual(p.alimentar("bloq"), [])
        self.assertEqual(p.alimentar("ues 3/13\r"), ["bloques 3/13"])

    def test_mezcla_de_ambos_separadores(self):
        p = Partidor()
        salida = p.alimentar("a\r\nb\rc\nd")
        self.assertEqual(salida, ["a", "b", "c"])
        self.assertEqual(p.vaciar(), ["d"])

    def test_descarta_lineas_vacias(self):
        p = Partidor()
        self.assertEqual(p.alimentar("\n\n\r\r"), [])


class TestInterpretar(unittest.TestCase):
    """Traduce el stdout real del CLI a estados. Muestras tomadas de `cli.py`."""

    def test_bloques_con_ansi(self):
        """`cli._gris()` emite \\033[90m aunque no sea Windows Terminal."""
        a = interpretar(f"{ANSI.sub('', '')}\033[90m  bloques 7/13\033[0m")
        self.assertEqual(a.estado, "resumiendo")
        self.assertEqual(a.bloques_ok, 7)
        self.assertEqual(a.bloques_total, 13)
        self.assertIn("7/13", a.fase_txt)

    def test_descargando(self):
        a = interpretar("\033[90mDescargando la transcripción de Class…\033[0m")
        self.assertEqual(a.estado, "descargando")

    def test_resumiendo_con_modelo(self):
        a = interpretar("\033[90mResumiendo con deepseek-v4.1-flash @ api.deploy.com…\033[0m")
        self.assertEqual(a.estado, "resumiendo")

    def test_ubicacion_de_la_clase(self):
        a = interpretar("  Clase: D:\\x\\clases\\DCGS12424-Pruebas\\2026-11-03")
        self.assertIsNotNone(a.ubicacion)
        self.assertEqual(derivar_ubicacion(a.ubicacion, ""),
                         ("DCGS12424-Pruebas", "2026-11-03"))

    def test_ya_existe(self):
        a = interpretar("\033[32m✓ Ya existe y está actualizado: resumen.md\033[0m")
        self.assertTrue(a.ya_existia)
        self.assertNotEqual(a.estado, "error")

    def test_error_del_motor(self):
        a = interpretar("✗ El enlace no parece una repetición de Class.")
        self.assertEqual(a.estado, "error")
        self.assertIn("no parece", a.error)
        self.assertNotIn("✗", a.error)

    def test_escritura(self):
        a = interpretar("\033[32m✓ clases\\X\\2026-11-03\\visor.html\033[0m")
        self.assertEqual(a.estado, "escribiendo")

    def test_error_sin_la_equis(self):
        """`print(f"\\n✗ {e}\\n", file=sys.stderr)` deja el mensaje suelto.

        Regresión: una clase sin transcripción terminaba en `error` pero sin
        texto, así que la interfaz solo podía mostrar «Failed to fetch».
        """
        linea = "La clase no tiene transcripción utilizable."
        self.assertIsNone(interpretar(linea).estado)
        self.assertTrue(es_error_conocido(linea))

    def test_error_sin_la_equis_no_confunde_lineas_normales(self):
        self.assertFalse(es_error_conocido("  PRUEBAS DE SOFTWARE · 136 min"))
        self.assertFalse(es_error_conocido("  bloques 3/13"))
        self.assertFalse(es_error_conocido(""))

    def test_linea_irrelevante(self):
        a = interpretar("  PRUEBAS DE SOFTWARE · 03/11/2026 · 136 min")
        self.assertIsNone(a.estado)
        self.assertFalse(a.ya_existia)

    def test_linea_vacia(self):
        self.assertIsNone(interpretar("   ").estado)


class TestArgumentos(unittest.TestCase):
    """Contrato con el CLI: si alguien renombra una opción, esto falla."""

    def test_modos(self):
        self.assertEqual(ARGUMENTOS["generar"], ("--visor",))
        self.assertEqual(ARGUMENTOS["regenerar"], ("--forzar", "--visor"))
        self.assertEqual(ARGUMENTOS["renovar"], ("--solo-visor",))

    def test_opciones_existen_en_cli(self):
        from clase_resumen import cli
        fuente = Path(cli.__file__).read_text(encoding="utf-8")
        for opcion in ("--visor", "--forzar", "--solo-visor"):
            self.assertIn(f'"{opcion}"', fuente,
                          f"{opcion} ya no existe en el CLI")


class TestRutas(unittest.TestCase):
    """`ruta_bajo` es la única defensa contra leer fuera de clases/."""

    def test_acepta_segmentos_normales(self):
        base = Path(tempfile.gettempdir()) / "resumen-test"
        self.assertIsNotNone(catalogo.ruta_bajo(base, "curso", "2026-11-03"))

    def test_rechaza_punto_punto(self):
        base = Path(tempfile.gettempdir()) / "resumen-test"
        self.assertIsNone(catalogo.ruta_bajo(base, "..", "config.json"))

    def test_rechaza_punto_punto_embebido(self):
        base = Path(tempfile.gettempdir()) / "resumen-test"
        self.assertIsNone(catalogo.ruta_bajo(base, "../.."))
        self.assertIsNone(catalogo.ruta_bajo(base, "..\\.."))

    def test_rechaza_barras(self):
        base = Path(tempfile.gettempdir()) / "resumen-test"
        self.assertIsNone(catalogo.ruta_bajo(base, "a/b"))
        self.assertIsNone(catalogo.ruta_bajo(base, "a\\b"))

    def test_rechaza_vacio(self):
        base = Path(tempfile.gettempdir()) / "resumen-test"
        self.assertIsNone(catalogo.ruta_bajo(base, ""))


class TestVideoVigente(unittest.TestCase):
    """El badge de la UI depende de leer el Expires del visor."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.visor = self.tmp / "visor.html"

    def test_sin_visor(self):
        self.assertEqual(catalogo.video_vigente(self.visor), (False, None))

    def test_vigente(self):
        futuro = int(time.time()) + 3600
        self.visor.write_text(f'<a href="x.MP4?Expires={futuro}&Policy=z">', encoding="utf-8")
        vivo, expira = catalogo.video_vigente(self.visor)
        self.assertTrue(vivo)
        self.assertEqual(expira, futuro)

    def test_caducado(self):
        pasado = int(time.time()) - 3600
        self.visor.write_text(f'<a href="x.MP4?Expires={pasado}">', encoding="utf-8")
        vivo, expira = catalogo.video_vigente(self.visor)
        self.assertFalse(vivo)
        self.assertEqual(expira, pasado)

    def test_visor_sin_urls(self):
        self.visor.write_text("<html>sin video</html>", encoding="utf-8")
        self.assertEqual(catalogo.video_vigente(self.visor), (False, None))


class TestCatalogoReal(unittest.TestCase):
    """Contra los archivos que existen de verdad en clases/."""

    def test_escanear(self):
        cursos = catalogo.escanear()
        if not cursos:
            self.skipTest("no hay clases generadas todavía")
        # Se comprueba la clase conocida, no el número total: el usuario puede
        # ir añadiendo clases y las pruebas no deben romperse por eso.
        por_carpeta = {c.carpeta: c for c in cursos}
        self.assertIn("DCGS12424-Pruebas-de-Software", por_carpeta)

        curso = por_carpeta["DCGS12424-Pruebas-de-Software"]
        self.assertEqual(curso.codigo, "DCGS12424")
        clase = next((c for c in curso.clases if c.dia == "2026-11-03"), None)
        self.assertIsNotNone(clase, "falta la clase del 3 de noviembre")

        self.assertEqual(clase.materia, "PRUEBAS DE SOFTWARE")
        self.assertEqual(clase.ideas, 176)
        self.assertEqual(clase.avisos, 20)
        self.assertAlmostEqual(clase.cobertura, 96.4, places=1)
        self.assertEqual(clase.duracion_min, 136)
        self.assertTrue(clase.tiene_visor)
        self.assertTrue(clase.url.startswith("https://"))

    def test_orden_descendente(self):
        cursos = catalogo.escanear()
        for curso in cursos:
            fechas = [c.dia for c in curso.clases]
            self.assertEqual(fechas, sorted(fechas, reverse=True),
                             f"{curso.carpeta} no está ordenado de reciente a antiguo")

    def test_buscar_por_url(self):
        cursos = catalogo.escanear()
        if not cursos:
            self.skipTest("no hay clases generadas todavía")
        clase = cursos[0].clases[0]
        if not clase.url:
            self.skipTest("la clase no guardó la URL")
        self.assertEqual(catalogo.buscar_por_url(clase.url), (clase.curso, clase.dia))

    def test_url_desconocida(self):
        self.assertIsNone(catalogo.buscar_por_url("https://x.com/nada"))


class TestPaginas(unittest.TestCase):
    """El HTML del índice se genera por f-strings: hay que comprobar el escapado."""

    def test_escapa_contenido(self):
        self.assertEqual(paginas.E('<script>x</script>'),
                         "&lt;script&gt;x&lt;/script&gt;")

    def test_vacio(self):
        html = paginas.fragmento_cursos([])
        self.assertIn("Todavía no hay resúmenes", html)

    def test_indice_real(self):
        cursos = catalogo.escanear()
        if not cursos:
            self.skipTest("no hay clases generadas todavía")
        html = paginas.indice(cursos, {"modelo": "m", "base": "b", "modo": "low"})
        self.assertIn("PRUEBAS DE SOFTWARE", html)
        self.assertIn("/static/app.css", html)
        self.assertIn('id="form-nueva"', html)
        self.assertNotIn("<script>x</script>", html)

    def test_indice_con_modelo_caido(self):
        html = paginas.indice([], {"error": "No hay ningún modelo configurado."})
        self.assertIn("El modelo no está disponible", html)
        self.assertIn("disabled", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
