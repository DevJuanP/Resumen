"""Pruebas del respaldo WebVTT de `fetch.py`.

Sin red: el VTT se construye en el propio test. Lo que se comprueba es el
parseo, que es donde estaban los fallos posibles (hablante pegado al texto,
nombres en mayúsculas, cues sin nombre).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from clase_resumen.fetch import (            # noqa: E402
    _normalizar_nombre, _parece_nombre, _segmentos_del_vtt, _url_subtitulos,
    segmentos_desde_vtt,
)

VTT_MINIMO = """WEBVTT

1
00:00:08.280 --> 00:00:16.490
ELVER NOEL MAYTA HERNANDEZ: Ya disculpen, estudiantes.

2
00:00:16.700 --> 00:00:23.709
GERSON DANIEL QUEZADA SIFUENTES: Qué tal, buena noche.
"""


class TestSegmentosDesdeVtt(unittest.TestCase):

    def test_parsea_dos_cues(self):
        segmentos = segmentos_desde_vtt(VTT_MINIMO)
        self.assertEqual(len(segmentos), 2)
        self.assertAlmostEqual(segmentos[0].segundos, 8.28, places=2)
        self.assertAlmostEqual(segmentos[1].segundos, 16.70, places=2)

    def test_extrae_el_hablante(self):
        segmentos = segmentos_desde_vtt(VTT_MINIMO)
        # `_normalizar_nombre` deja nombres + apellido paterno.
        self.assertEqual(segmentos[0].hablante, "Elver Mayta")
        self.assertEqual(segmentos[1].hablante, "Gerson Quezada")

    def test_el_texto_no_conserva_el_nombre(self):
        segmentos = segmentos_desde_vtt(VTT_MINIMO)
        self.assertEqual(segmentos[0].texto, "Ya disculpen, estudiantes.")
        self.assertNotIn("ELVER", segmentos[0].texto)

    def test_los_dos_puntos_dentro_de_una_frase_no_confunden(self):
        """Regresión: «donde van a exponer» no debe tratarse como hablante."""
        vtt = """WEBVTT

1
00:00:10.000 --> 00:00:14.000
ya dónde van a exponer su proyecto final.
"""
        segmentos = segmentos_desde_vtt(vtt)
        self.assertEqual(len(segmentos), 1)
        self.assertEqual(segmentos[0].hablante, "Participante")
        self.assertIn("exponer", segmentos[0].texto)

    def test_etiquetas_de_voz(self):
        vtt = """WEBVTT

1
00:00:05.000 --> 00:00:09.000
<v ANA SOFIA MARTINEZ>Hola, buenas noches.</v>
"""
        segmentos = segmentos_desde_vtt(vtt)
        self.assertEqual(len(segmentos), 1)
        self.assertEqual(segmentos[0].texto, "Hola, buenas noches.")

    def test_ignora_numeros_de_cue_y_notas(self):
        vtt = """WEBVTT

NOTE esto es una nota

1
00:00:01.000 --> 00:00:02.000
CESAR ROMAN QUISPE: Texto válido.
"""
        segmentos = segmentos_desde_vtt(vtt)
        self.assertEqual(len(segmentos), 1)
        self.assertIn("Texto válido", segmentos[0].texto)

    def test_formato_con_coma_decimal(self):
        vtt = """WEBVTT

1
00:00:01,500 --> 00:00:02,900
CESAR ROMAN QUISPE: Con coma.
"""
        segmentos = segmentos_desde_vtt(vtt)
        self.assertAlmostEqual(segmentos[0].segundos, 1.5, places=2)

    def test_vtt_vacio(self):
        self.assertEqual(segmentos_desde_vtt("WEBVTT\n"), [])
        self.assertEqual(segmentos_desde_vtt(""), [])

    def test_cue_con_horas(self):
        vtt = """WEBVTT

1
02:47:40.000 --> 02:47:45.000
ELVER NOEL MAYTA HERNANDEZ: Al final de la clase.
"""
        segmentos = segmentos_desde_vtt(vtt)
        self.assertAlmostEqual(segmentos[0].segundos, 10060.0, places=1)


class TestPareceNombre(unittest.TestCase):

    def test_nombres_en_mayusculas(self):
        self.assertTrue(_parece_nombre("ELVER NOEL MAYTA HERNANDEZ"))
        self.assertTrue(_parece_nombre("GERSON DANIEL QUEZADA SIFUENTES"))

    def test_frases_normales(self):
        self.assertFalse(_parece_nombre("ya dónde van a exponer su proyecto final"))
        self.assertFalse(_parece_nombre("Recuerden que el curso"))
        self.assertFalse(_parece_nombre(""))

    def test_muy_largo(self):
        self.assertFalse(_parece_nombre("A" * 100))


class TestRoles(unittest.TestCase):
    """El VTT no trae roles: se infieren de la lista de asistentes."""

    def test_marca_docente_desde_asistentes(self):
        datos = {"students": [
            {"user_name": "ELVER NOEL MAYTA HERNANDEZ", "role": "teacher"},
            {"user_name": "GERSON DANIEL QUEZADA SIFUENTES", "role": "student"},
        ]}
        rec = {"artifactsComplete": [
            {"contents": "audio_transcript", "url": "https://x/vtt"},
        ]}
        from clase_resumen import fetch
        original = fetch._pedir
        fetch._pedir = lambda *a, **k: VTT_MINIMO.encode("utf-8")
        try:
            segmentos = _segmentos_del_vtt(datos, rec)
        finally:
            fetch._pedir = original

        self.assertEqual(len(segmentos), 2)
        self.assertEqual(segmentos[0].rol, "docente")
        self.assertEqual(segmentos[1].rol, "estudiante")


class TestUrlSubtitulos(unittest.TestCase):

    def test_encuentra_el_artefacto(self):
        rec = {"artifactsComplete": [
            {"contents": "active_speaker", "url": "https://x/mp4"},
            {"contents": "audio_transcript", "url": "https://x/vtt"},
        ]}
        self.assertEqual(_url_subtitulos({}, rec), "https://x/vtt")

    def test_desescala_ampersand(self):
        rec = {"artifactsComplete": [
            {"contents": "audio_transcript", "url": "https://x/vtt?a=1&amp;b=2"},
        ]}
        self.assertEqual(_url_subtitulos({}, rec), "https://x/vtt?a=1&b=2")

    def test_sin_artefacto(self):
        self.assertEqual(_url_subtitulos({}, {"artifactsComplete": []}), "")


class TestNormalizarNombre(unittest.TestCase):
    """Ya existía; se fija el comportamiento del que dependen los roles."""

    def test_cuatro_palabras(self):
        self.assertEqual(_normalizar_nombre("ELVER NOEL MAYTA HERNANDEZ"), "Elver Mayta")

    def test_dos_palabras(self):
        self.assertEqual(_normalizar_nombre("GERSON QUEZADA"), "Gerson Quezada")

    def test_vacio(self):
        self.assertEqual(_normalizar_nombre(""), "Sin nombre")


if __name__ == "__main__":
    unittest.main(verbosity=2)
