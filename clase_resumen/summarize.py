"""Convierte una clase transcrita en apuntes estructurados.

Estrategia para no perder nada sin gastar contexto de más:
  1. La transcripción se parte en bloques de ~12 min con 1 min de solape.
  2. Cada bloque se analiza por separado y devuelve JSON con timestamps.
  3. Los bloques se fusionan eliminando duplicados del solape.
  4. Una segunda pasada ordena todo en un mapa de la clase y prioriza.
"""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .fetch import Clase
from .llm import Modelo, completar_json

BLOQUE_MIN = 12.0        # minutos por bloque
SOLAPE_MIN = 1.0         # solape entre bloques
MAX_HILOS = 3


def mmss(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 60:02d}:{s % 60:02d}"


def _limpio(texto: str) -> str:
    t = (texto or "").strip()
    return t if t else ""


@dataclass
class Bloque:
    inicio: float
    fin: float
    lineas: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(self.lineas)


def dividir(clase: Clase) -> list[Bloque]:
    if not clase.segmentos:
        return []
    bloques: list[Bloque] = []
    inicio = 0.0
    fin_total = clase.segmentos[-1].segundos
    paso = BLOQUE_MIN * 60
    solape = SOLAPE_MIN * 60
    while inicio <= fin_total:
        fin = min(inicio + paso, fin_total + 1)
        lineas = [
            f"{mmss(s.segundos)} {s.hablante}: {s.texto}"
            for s in clase.segmentos
            if inicio <= s.segundos < fin
        ]
        if lineas:
            bloques.append(Bloque(inicio, fin, lineas))
        if fin >= fin_total:
            break
        inicio = fin - solape
    return bloques


PROMPT_BLOQUE = """Conviertes la transcripción automática de una clase en apuntes estructurados en español.

La transcripción no tiene puntuación ni tildes y las frases están cortadas. Reconstruye el sentido.
Reglas:
- NO inventes. Si no se entiende, omite ese fragmento. Si un término clave es dudoso, añade " (?)".
- Español neutro, con tildes y puntuación correctas.
- Cada elemento lleva "t": el timestamp que aparece al inicio de la línea, copiado tal cual (mm:ss).
- "ideas": todo lo que aporte contenido académico. Una idea por concepto, no por frase.
- "avisos": fechas de examen, entregas, reglas del curso, herramientas obligatorias. Resuelve fechas
  relativas ("el viernes", "la próxima semana") usando la fecha de la clase: {fecha}.
- "menciones": libros, autores, herramientas, normas, siglas o temas que valga la pena investigar.
- "relleno": SOLO lo descartable (saludos, asistencia, bromas, audio, repeticiones). Ante la duda,
  NO lo incluyas aquí: es preferible una idea de más que una de menos.

Devuelve SOLO un objeto JSON válido, sin markdown, con esta forma exacta:
{{"ideas":[{{"t":"mm:ss","titulo":"3-8 palabras","explicacion":"1-3 frases autocontenidas","tipo":"concepto|definicion|procedimiento|comparacion|opinion"}}],
"terminos":[{{"t":"mm:ss","termino":"","definicion":""}}],
"avisos":[{{"t":"mm:ss","que":"","cuando":""}}],
"ejemplos":[{{"t":"mm:ss","ejemplo":"","ilustra":""}}],
"preguntas":[{{"t":"mm:ss","pregunta":"","respuesta":""}}],
"menciones":[{{"t":"mm:ss","item":"","contexto":""}}],
"relleno":["tema sin contenido"]}}

Contexto: clase de "{materia}", bloque de {inicio} a {fin}.

TRANSCRIPCIÓN
{texto}
"""


ALIAS = {
    "explicación": "explicacion", "explicacion_": "explicacion", "detalle": "explicacion",
    "descripcion": "explicacion", "descripción": "explicacion", "texto": "explicacion",
    "título": "titulo", "titulo_": "titulo", "punto": "titulo", "tema": "titulo",
    "definición": "definicion", "concepto": "termino", "nombre": "termino",
    "qué": "que", "cuándo": "cuando", "fecha": "cuando", "aviso": "que",
    "pregunta_": "pregunta", "respuesta_": "respuesta",
    "ejemplo_": "ejemplo", "ilustración": "ilustra", "ilustracion": "ilustra",
    "item_": "item", "elemento": "item", "contexto_": "contexto",
    "momento": "t", "timestamp": "t", "tiempo": "t", "minuto": "t",
}

CAMPOS = ("ideas", "terminos", "avisos", "ejemplos", "preguntas", "menciones")


def _normalizar_claves(obj):
    """Corrige variantes con tilde o sinónimos que devuelven algunos modelos."""
    if isinstance(obj, dict):
        salida = {}
        for k, v in obj.items():
            clave = str(k).strip().lower()
            clave = ALIAS.get(clave, clave)
            if clave in salida and v:
                # Se queda con el valor no vacío.
                if not salida[clave]:
                    salida[clave] = _normalizar_claves(v)
                continue
            salida[clave] = _normalizar_claves(v)
        return salida
    if isinstance(obj, list):
        return [_normalizar_claves(x) for x in obj]
    return obj


def _analizar_bloque(modelo: Modelo, clase: Clase, bloque: Bloque) -> dict:
    prompt = PROMPT_BLOQUE.format(
        fecha=clase.cuando.strftime("%Y-%m-%d"),
        materia=clase.materia,
        inicio=mmss(bloque.inicio),
        fin=mmss(bloque.fin),
        texto=bloque.texto,
    )
    datos = _normalizar_claves(completar_json(modelo, prompt, max_tokens=12000, timeout=900))
    for clave in CAMPOS:
        if not isinstance(datos.get(clave), list):
            datos[clave] = []
    if not isinstance(datos.get("relleno"), list):
        datos["relleno"] = []
    return datos


def _seg(texto: str) -> int:
    m = re.match(r"\s*(\d{1,3}):(\d{2})", texto or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def _parecido(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _fusionar(elementos: list[dict], clave_texto: str, ventana_s: int = 90) -> list[dict]:
    """Quita repetidos que aparecen en el solape de dos bloques."""
    salida: list[dict] = []
    for e in elementos:
        texto = _limpio(str(e.get(clave_texto, "")))
        if not texto:
            continue                      # sin el campo principal no aporta nada
        e[clave_texto] = texto
        t = _seg(str(e.get("t", "")))
        duplicado = False
        for previo in salida:
            if ventana_s and abs(_seg(str(previo.get("t", ""))) - t) > ventana_s:
                continue
            if _parecido(texto, str(previo.get(clave_texto, ""))) > 0.78:
                duplicado = True
                # Conserva la explicación más completa.
                if len(str(e.get("explicacion", ""))) > len(str(previo.get("explicacion", ""))):
                    previo.update(e)
                break
        if not duplicado:
            salida.append({k: v for k, v in e.items() if v not in (None, "")})
    return sorted(salida, key=lambda x: _seg(str(x.get("t", ""))))


def _palabras(texto: str) -> set[str]:
    stop = {"de", "la", "el", "los", "las", "un", "una", "que", "y", "o", "en", "para",
            "con", "por", "se", "del", "al", "es", "son", "su", "lo", "como", "más"}
    return {p for p in re.findall(r"\w{3,}", texto.lower()) if p not in stop}


def _jaccard(a: str, b: str) -> float:
    pa, pb = _palabras(a), _palabras(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


def _consolidar_avisos(avisos: list[dict]) -> list[dict]:
    """Une avisos del mismo minuto que hablan de lo mismo.

    Los bloques con solape repiten avisos con redacciones distintas, así que la
    comparación por texto sola no basta: se combina con la cercanía temporal.
    """
    salida: list[dict] = []
    for a in avisos:
        t = _seg(str(a.get("t", "")))
        fusionado = False
        for previo in salida:
            if abs(_seg(str(previo.get("t", ""))) - t) > 40:
                continue
            if _jaccard(str(a.get("que", "")), str(previo.get("que", ""))) >= 0.38:
                if len(str(a.get("que", ""))) > len(str(previo.get("que", ""))):
                    previo["que"] = a["que"]
                if not previo.get("cuando") and a.get("cuando"):
                    previo["cuando"] = a["cuando"]
                fusionado = True
                break
        if not fusionado:
            salida.append(dict(a))
    return salida


def _normalizar_cuando(avisos: list[dict], clase: Clase) -> list[dict]:
    """Convierte la fecha de la propia clase en 'hoy'.

    Solo toca ese caso: las demás fechas las resuelve el modelo con la fecha de
    la clase, que ya viene en hora local.
    """
    mismo_dia = clase.cuando.strftime("%Y-%m-%d")
    for a in avisos:
        cuando = str(a.get("cuando") or "").strip()
        if not cuando.startswith(mismo_dia):
            continue
        resto = cuando.replace(mismo_dia, "").strip(" ()")
        if "hoy" in cuando.lower():
            continue
        a["cuando"] = "hoy" + (f" ({resto})" if resto and "clase actual" not in resto else "")
    return avisos


def _deduplicar_global(elementos: list[dict], clave_texto: str, umbral: float = 0.82) -> list[dict]:
    """Elimina ideas repetidas que aparecen en bloques distintos y lejanos."""
    salida: list[dict] = []
    for e in elementos:
        texto = str(e.get(clave_texto, ""))
        if any(_parecido(texto, str(p.get(clave_texto, ""))) >= umbral for p in salida):
            continue
        salida.append(e)
    return salida


def _ajustar_tiempos(elementos: list[dict], clase: Clase, tolerancia_s: int = 45) -> list[dict]:
    """Ancla cada timestamp al segmento real más cercano.

    Evita que un modelo invente un minuto que no existe en la grabación: si el
    valor no coincide con ninguna intervención cercana, se corrige al vecino.
    """
    tiempos = sorted({s.segundos for s in clase.segmentos})
    if not tiempos:
        return elementos
    for e in elementos:
        t = _seg(str(e.get("t", "")))
        cercano = min(tiempos, key=lambda x: abs(x - t))
        if abs(cercano - t) > tolerancia_s:
            e["t"] = mmss(cercano)
    return elementos


PROMPT_SINTESIS = """Eres un curador de apuntes. Recibes la extracción estructurada de TODOS los bloques de una
clase de "{materia}" ({duracion} min) y debes organizarla para que un estudiante autodidacta sepa
exactamente qué estudiar y en qué orden.

Reglas:
- No inventes contenido nuevo: usa solo lo que aparece abajo. Puedes unir y reformular.
- Español neutro, tildes correctas.
- "mapa": entre 4 y 12 tramos que cubran toda la clase en orden cronológico, sin huecos.
- "clave": los 6-12 puntos que de verdad importan, ordenados por importancia, no por tiempo. Marca
  "peso" como "alto" si el docente lo repitió, lo llamó importante o lo vinculó a evaluación;
  "medio" si es base para entender lo demás; "bajo" si es contexto.
- "investigar": temas para que el estudiante amplíe por su cuenta, con una pista de búsqueda concreta.
- "relleno": resume en pocas líneas qué se descartó, para que se confíe en que no faltaba nada.

Devuelve SOLO JSON válido:
{{"resumen":"3-5 frases sobre de qué trató la clase y qué se llevó el estudiante",
"mapa":[{{"desde":"mm:ss","hasta":"mm:ss","tema":"","que_pasa":""}}],
"clave":[{{"t":"mm:ss","punto":"","desarrollo":"2-4 frases","peso":"alto|medio|bajo"}}],
"investigar":[{{"tema":"","por_que":"","buscar":"consulta sugerida"}}],
"relleno":["..."]}}

EXTRACCIÓN
{datos}
"""


def sintetizar(modelo: Modelo, clase: Clase, fusion: dict) -> dict:
    carga = {
        "ideas": fusion["ideas"],
        "terminos": fusion["terminos"],
        "avisos": fusion["avisos"],
        "ejemplos": fusion["ejemplos"],
        "preguntas": fusion["preguntas"],
        "menciones": fusion["menciones"],
        "relleno": fusion["relleno"],
    }
    prompt = PROMPT_SINTESIS.format(
        materia=clase.materia,
        duracion=round(clase.duracion_s / 60),
        datos=json.dumps(carga, ensure_ascii=False),
    )
    datos = completar_json(modelo, prompt, max_tokens=12000, timeout=900)
    for clave in ("mapa", "clave", "investigar", "relleno"):
        if not isinstance(datos.get(clave), list):
            datos[clave] = []
    return datos


def _huecos(clase: Clase, ideas: list[dict], minimo_s: float = 480) -> list[Bloque]:
    """Encuentra tramos largos de clase de los que no se extrajo ninguna idea.

    Es la red de seguridad contra los bloques que el modelo resumió de más:
    si hay más de `minimo_s` seguidos sin cobertura, se vuelven a analizar.
    """
    if not clase.segmentos:
        return []
    tiempos = sorted(_seg(str(i.get("t", ""))) for i in ideas)
    total = clase.segmentos[-1].segundos
    cortes = [0] + tiempos + [total]
    huecos: list[Bloque] = []
    for a, b in zip(cortes, cortes[1:]):
        if b - a < minimo_s:
            continue
        lineas = [f"{mmss(s.segundos)} {s.hablante}: {s.texto}"
                  for s in clase.segmentos if a <= s.segundos < b]
        # Un tramo casi vacío es silencio o pausa, no contenido perdido.
        if lineas and sum(len(l) for l in lineas) > 1200:
            huecos.append(Bloque(a, b, lineas))
    return huecos


def _cobertura(clase: Clase, ideas: list[dict], tramo_s: float = 300) -> float:
    """Porcentaje de tramos de 5 min con al menos una idea asociada."""
    if not clase.segmentos:
        return 100.0
    total = int(clase.segmentos[-1].segundos // tramo_s) + 1
    vistos = {int(_seg(str(i.get("t", ""))) // tramo_s) for i in ideas}
    return 100.0 * len([t for t in range(total) if t in vistos]) / total


def procesar(modelo: Modelo, clase: Clase, progreso=None, auditoria: bool = True) -> dict:
    bloques = dividir(clase)
    if not bloques:
        raise ValueError("La clase no tiene transcripción.")

    resultados: list[dict | None] = [None] * len(bloques)

    def tarea(i: int):
        resultados[i] = _analizar_bloque(modelo, clase, bloques[i])
        if progreso:
            progreso(i + 1, len(bloques), bloques[i])

    with ThreadPoolExecutor(max_workers=MAX_HILOS) as ex:
        list(ex.map(tarea, range(len(bloques))))

    crudos = [r for r in resultados if r]
    ideas = _ajustar_tiempos(_deduplicar_global(
        _fusionar([x for r in crudos for x in r["ideas"]], "titulo"), "titulo"), clase)

    # Segunda pasada sobre los tramos que quedaron sin cobertura.
    if auditoria and ideas:
        pendientes = _huecos(clase, ideas)
        for i, hueco in enumerate(pendientes, 1):
            if progreso:
                progreso(len(bloques) + i, len(bloques) + len(pendientes), hueco)
            extra = _analizar_bloque(modelo, clase, hueco)
            crudos.append(extra)
        if pendientes:
            ideas = _ajustar_tiempos(_deduplicar_global(
                _fusionar([x for r in crudos for x in r["ideas"]], "titulo"), "titulo"), clase)

    fusion = {
        "ideas": ideas,
        "terminos": _ajustar_tiempos(_deduplicar_global(
            _fusionar([x for r in crudos for x in r["terminos"]], "termino", 300), "termino"), clase),
        "avisos": _normalizar_cuando(_consolidar_avisos(
            _ajustar_tiempos(_fusionar([x for r in crudos for x in r["avisos"]], "que", 600), clase)), clase),
        "ejemplos": _ajustar_tiempos(_deduplicar_global(
            _fusionar([x for r in crudos for x in r["ejemplos"]], "ejemplo"), "ejemplo", 0.9), clase),
        "preguntas": _ajustar_tiempos(_fusionar([x for r in crudos for x in r["preguntas"]], "pregunta"), clase),
        "menciones": _ajustar_tiempos(_fusionar([x for r in crudos for x in r["menciones"]], "item", 900), clase),
        "relleno": sorted({str(x).strip() for r in crudos for x in r["relleno"] if str(x).strip()}),
    }
    sintesis = sintetizar(modelo, clase, fusion)
    return {"fusion": fusion, "sintesis": sintesis, "bloques": len(bloques),
            "cobertura": round(_cobertura(clase, fusion["ideas"]), 1),
            "revisados": len(_huecos(clase, fusion["ideas"])) if auditoria else 0}


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #

def _tabla_texto(valor: str, limite: int = 0) -> str:
    t = " ".join(str(valor).split())
    if limite and len(t) > limite:
        t = t[: limite - 1].rstrip() + "…"
    return t.replace("|", "\\|")


def _fecha_larga(dt) -> str:
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month - 1]} de {dt.year} a las {dt:%H:%M}"


def render(clase: Clase, datos: dict, url_video: str | None = None) -> str:
    fus, sin = datos["fusion"], datos["sintesis"]
    esc = clase.materia.replace('"', "'")
    L: list[str] = []

    L += [f"# {esc}", ""]
    L += [f"**Fecha:** {_fecha_larga(clase.cuando)}  "]
    L += [f"**Duración:** {round(clase.duracion_s / 60)} min  "]
    if clase.docente:
        L += [f"**Docente:** {clase.docente}  "]
    L += [f"**Fuente:** {clase.url or 'transcripción pegada manualmente'}", ""]
    if sin.get("resumen"):
        L += [f"> {sin['resumen']}", ""]

    L += ["---", "", "## Mapa de la clase", ""]
    L += ["| Tramo | Tema | Qué pasa |", "|---|---|---|"]
    for m in sin["mapa"]:
        tramo = f"{m.get('desde','')}–{m.get('hasta','')}"
        L.append(f"| `{tramo}` | **{_tabla_texto(m.get('tema',''),60)}** | {_tabla_texto(m.get('que_pasa',''),180)} |")
    L += [""]

    L += ["## Lo que importa", "", "_Ordenado por peso, no por tiempo._", ""]
    for i, c in enumerate(sin["clave"], 1):
        peso = (c.get("peso") or "medio").lower()
        marca = {"alto": "🔴", "medio": "🟡", "bajo": "⚪"}.get(peso, "🟡")
        L += [f"### {i}. {c.get('punto','')} — `{c.get('t','')}` {marca}", ""]
        L += [str(c.get("desarrollo", "")).strip(), ""]

    if fus["ideas"]:
        L += ["---", "", "## Desarrollo completo", "",
              "_Todos los conceptos que se tocaron, en orden de aparición._", ""]
        for idea in fus["ideas"]:
            tipo = f" `{idea.get('tipo')}`" if idea.get("tipo") else ""
            L.append(f"- **{idea.get('titulo','')}** `{idea.get('t','')}`{tipo} — {idea.get('explicacion','')}")
        L += [""]

    if fus["terminos"]:
        L += ["## Glosario", ""]
        for t in fus["terminos"]:
            L.append(f"- **{t.get('termino','')}** `{t.get('t','')}`: {t.get('definicion','')}")
        L += [""]

    L += ["---", "", "## Pendientes y avisos", ""]
    if fus["avisos"]:
        L += ["| Cuándo | Qué | Minuto |", "|---|---|---|"]
        for a in fus["avisos"]:
            L.append(f"| {_tabla_texto(a.get('cuando','') or '—', 40)} | {_tabla_texto(a.get('que',''), 200)} | `{a.get('t','')}` |")
    else:
        L.append("_No se anunciaron fechas ni entregas en esta sesión._")
    L += [""]

    if fus["ejemplos"]:
        L += ["## Ejemplos y analogías del docente", ""]
        for e in fus["ejemplos"]:
            L.append(f"- `{e.get('t','')}` **{e.get('ejemplo','')}** → ilustra: {e.get('ilustra','')}")
        L += [""]

    if fus["preguntas"]:
        L += ["## Preguntas de tus compañeros", ""]
        for p in fus["preguntas"]:
            L.append(f"- `{p.get('t','')}` **{p.get('pregunta','')}**  \n  {p.get('respuesta','')}")
        L += [""]

    if sin["investigar"] or fus["menciones"]:
        L += ["---", "", "## Para investigar por tu cuenta", ""]
        for x in sin["investigar"]:
            L.append(f"- **{x.get('tema','')}** — {x.get('por_que','')}")
            if x.get("buscar"):
                L.append(f"  - Buscar: `{x['buscar']}`")
        vistas = {str(x.get("tema", "")).lower() for x in sin["investigar"]}
        for m in fus["menciones"]:
            if str(m.get("item", "")).lower() in vistas:
                continue
            L.append(f"- **{m.get('item','')}** `{m.get('t','')}` — {m.get('contexto','')}")
        L += [""]

    relleno = sin["relleno"] or fus["relleno"]
    if relleno:
        L += ["---", "", "## Lo que se omitió", "",
              "_Descartado por no aportar contenido. La transcripción íntegra está en el anexo._", ""]
        for r in relleno[:25]:
            L.append(f"- {r}")
        L += [""]

    L += ["---", "", "## Cómo usar estos apuntes", ""]
    L += [
        "1. Lee **Lo que importa**. Si solo tienes 15 minutos, eso es lo esencial.",
        "2. Usa **Para investigar** como lista de búsquedas: es la parte que la clase no cubre.",
        "3. Revisa **Pendientes** antes de cerrar la sesión de estudio.",
        "4. Si dudas de una idea, el `mm:ss` te dice dónde está en la repetición.",
    ]
    if url_video:
        L += ["", f"Video de la sesión: {url_video}"]
    L += [""]

    L += ["---", "", "<details>", "<summary>Anexo: transcripción completa</summary>", ""]
    for s in clase.segmentos:
        etiqueta = "**Docente**" if s.rol == "docente" else s.hablante
        L.append(f"- `{mmss(s.segundos)}` {etiqueta}: {s.texto}")
    L += ["", "</details>", ""]
    return "\n".join(L)


def nombre_archivo(clase: Clase) -> str:
    base = re.sub(r"[^\w\s-]", "", clase.materia).strip()
    base = re.sub(r"\s+", "-", base)[:60] or "clase"
    return f"{clase.cuando:%Y-%m-%d}-{base}"


def huella(clase: Clase) -> str:
    h = hashlib.sha1()
    for s in clase.segmentos:
        h.update(f"{s.segundos:.0f}{s.texto}".encode())
    return h.hexdigest()[:12]
