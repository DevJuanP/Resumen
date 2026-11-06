# Módulos

Responsabilidad de cada archivo, con las funciones que realmente existen.

Líneas de código reales:

| Archivo | Líneas |
|---|---|
| `resumen.py` | 9 |
| `clase_resumen/__init__.py` | 4 |
| `clase_resumen/almacen.py` | 154 |
| `clase_resumen/cli.py` | 341 |
| `clase_resumen/cursos.py` | 124 |
| `clase_resumen/fetch.py` | 365 |
| `clase_resumen/llm.py` | 274 |
| `clase_resumen/summarize.py` | 529 |
| `clase_resumen/visor.py` | 631 |
| **Total** | **2431** |

---

## `resumen.py`

Punto de entrada. Solo importa `main` y lo ejecuta con `sys.exit`.

```python
import sys
from clase_resumen.cli import main
if __name__ == "__main__":
    sys.exit(main())
```

---

## `clase_resumen/cli.py`

Argumentos, orquestación y salida por consola.

### `main(argv=None) -> int`

Único punto de entrada lógico. Devuelve el código de salida. Orden interno:

1. Parsear argumentos con `argparse`.
2. Construir `Clase` desde enlace o desde texto.
3. Crear carpeta de salida.
4. Atender `--solo-visor` / `--rehacer` (sin modelo).
5. Comprobar huella (sin modelo).
6. Cargar modelo.
7. `procesar()`.
8. `render()` y escritura.
9. Guardar JSON si `--crudo`.
10. `generar()` si `--visor`.
11. Actualizar huella.

### Funciones auxiliares

| Función | Para qué |
|---|---|
| `_verde(t)` | Añade ANSI verde solo si la consola lo soporta |
| `_gris(t)` | ANSI gris para mensajes secundarios |

`_verde` comprueba `os.name != "nt" or os.environ.get("WT_SESSION")`: no colorea en
`cmd.exe` antiguo para no imprimir secuencias raras.

### Constantes

| Constante | Valor |
|---|---|
| `RAIZ` | Carpeta padre del paquete |
| `SALIDA` | `RAIZ / "clases"` |

---

## `clase_resumen/fetch.py`

Obtención y normalización de la transcripción. Ver
[extraccion-class](extraccion-class.md) para el detalle del protocolo.

### Estructuras

| Nombre | Tipo | Campos |
|---|---|---|
| `Segmento` | `dataclass` | `segundos`, `hablante`, `texto`, `rol` |
| `Clase` | `dataclass` | Ver [modelo-de-datos](../04-datos/modelo-de-datos.md) |
| `ErrorDeClase` | `Exception` | Error esperado, con mensaje para el usuario |

### Funciones

| Función | Responsabilidad |
|---|---|
| `_pedir(url, *, datos, cabeceras, timeout)` | GET/POST con `urllib`. Traduce errores HTTP a `ErrorDeClase` |
| `_uuid_local()` | Lee o crea `.uuid`; respeta `RESUMEN_USER_UUID` |
| `_config_del_host(host)` | Lee `player/config.json` para descubrir la API |
| `_fecha(valor)` | Convierte UTC de la plataforma a hora local |
| `_normalizar_nombre(nombre)` | «EDISON LORENZO MERINO VILLAGARAY» → «Edison Merino» |
| `_es_ruido(texto)` | Filtra «This meeting is being recorded» |
| `obtener_clase(url)` | Orquesta todo y devuelve un `Clase` |
| `urls_de_video(clase)` | Pide las URLs firmadas de los artefactos |
| `clase_desde_texto(ruta, materia)` | Modo alternativo sin enlace |

### Constantes

| Constante | Valor |
|---|---|
| `PATRON_REPLAY` | Regex que extrae host, `class_uuid` y `recording_id` |
| `RUIDO_EXACTO` | Conjunto de tres frases a descartar |
| `HORA` | Regex para horas tipo `07:01:11 p. m.` |
| `UA` | User-Agent de Chrome 156 |

### Detalle: `_normalizar_nombre()`

Regla aplicada, con casos reales:

| Entrada | Salida | Partes |
|---|---|---|
| `EDISON LORENZO MERINO VILLAGARAY` | `Edison Merino` | 4 → nombre + apellido paterno |
| `CARLOS ENRIQUE DELGADO NAVARRO` | `Carlos Delgado` | 4 |
| `GUSTAVO HUAMAN BERROCAL` | `Gustavo Huaman` | 3 → nombre + apellido paterno |
| `ANA TORRES` | `Ana Torres` | 2 |
| `""` | `Sin nombre` | 0 |

Con tres palabras se toma la segunda, no la tercera, porque el patrón peruano es
nombres + apellido paterno + apellido materno.

---

## `clase_resumen/llm.py`

Cliente HTTP mínimo para cualquier endpoint compatible con OpenAI.

### Estructura `Modelo`

| Campo | Uso |
|---|---|
| `base_url` | Raíz de la API |
| `model` | Identificador |
| `api_key` | Clave |
| `extra` | Parámetros que se añaden a cada petición |
| `etiqueta` (propiedad) | Texto para consola: `modelo @ host` |

### Funciones

| Función | Responsabilidad |
|---|---|
| `_jsonc_a_json(texto)` | Quita comentarios y comas finales de `.jsonc` |
| `_desde_opencode()` | Detecta un proveedor OpenAI-compatible en la config de OpenCode |
| `cargar()` | Resuelve la configuración en cascada y devuelve `Modelo` |
| `_post(modelo, carga, timeout)` | POST a `/chat/completions` |
| `completar(...)` | Pide texto con reintentos |
| `completar_json(...)` | Pide y parsea JSON |
| `_extraer_json(texto)` | Recupera JSON incluso si viene con markdown alrededor |

### Reintentos de `completar()`

| Situación | Comportamiento |
|---|---|
| HTTP 408, 409, 429, 500, 502, 503, 504 | Reintenta hasta 4 veces, espera exponencial (máx. 60 s) |
| Otro código HTTP | Falla de inmediato con el detalle |
| Error de red o timeout | Reintenta con espera exponencial (máx. 45 s) |
| Respuesta sin `choices` | Reintenta |
| Contenido vacío con `reasoning_content` | Sube `max_tokens` a 8000 y reintenta una vez |
| Contenido vacío sin razonamiento | Reintenta |

El caso del razonamiento se añadió por un problema real: con
`deepseek-v4.1-flash-1017` el modelo consumía los 12 000 tokens en razonamiento interno y
devolvía contenido vacío.

### `_extraer_json()`

Tres intentos, en orden:

1. `json.loads` directo.
2. Quitar cercas de markdown (```` ```json ````) y reintentar.
3. Recorrer carácter a carácter buscando el primer objeto equilibrado, respetando cadenas y
   escapes.

Si los tres fallan, lanza `ErrorDeModelo` con los primeros 400 caracteres de la respuesta.

---

## `clase_resumen/summarize.py`

El núcleo. Bloques, prompts, fusión, auditoría y render del Markdown.

### Constantes de configuración

| Constante | Valor | Efecto |
|---|---|---|
| `BLOQUE_MIN` | 12.0 | Minutos por bloque |
| `SOLAPE_MIN` | 1.0 | Minutos de solape |
| `MAX_HILOS` | 3 | Llamadas concurrentes |

### Prompts

| Nombre | Cuándo se usa |
|---|---|
| `PROMPT_BLOQUE` | Una vez por bloque |
| `PROMPT_SINTESIS` | Una vez por clase, al final |

Ambos están completos en [resumen-y-auditoria](resumen-y-auditoria.md).

### Funciones de división

| Función | Qué hace |
|---|---|
| `dividir(clase)` | Devuelve `list[Bloque]` con solape |
| `Bloque.texto` (propiedad) | Une las líneas con `\n` |

### Funciones de normalización

| Función | Qué hace |
|---|---|
| `_normalizar_claves(obj)` | Aplica el diccionario `ALIAS` recursivamente |
| `_analizar_bloque(...)` | Una llamada al modelo + normalización |
| `_seg(texto)` | `"111:49"` → `6710` |
| `mmss(segundos)` | `6710` → `"111:49"` |

### Funciones de deduplicación

| Función | Umbral | Criterio |
|---|---|---|
| `_parecido(a, b)` | — | `SequenceMatcher` sobre el texto en minúsculas |
| `_fusionar(...)` | 0.78 | Texto similar **y** menos de N segundos de distancia |
| `_deduplicar_global(...)` | 0.82 | Texto similar, sin importar la distancia |
| `_jaccard(a, b)` | — | Intersección de palabras sobre unión, ignorando vacías |
| `_consolidar_avisos(...)` | 0.38 | Jaccard + menos de 40 s de distancia |

`_fusionar` recibe la ventana por parámetro según el tipo:

| Tipo | Ventana |
|---|---|
| ideas | 90 s |
| terminos | 300 s |
| avisos | 600 s |
| ejemplos | 90 s |
| preguntas | 90 s |
| menciones | 900 s |

### Funciones de corrección

| Función | Qué corrige |
|---|---|
| `_ajustar_tiempos(...)` | Minuto inventado → minuto real más cercano (tolerancia 45 s) |
| `_normalizar_cuando(...)` | Fecha de la propia clase → `hoy` |

### Funciones de auditoría

| Función | Qué mide |
|---|---|
| `_huecos(clase, ideas)` | Tramos >480 s sin ideas y con >1200 caracteres de texto |
| `_cobertura(clase, ideas)` | Porcentaje de tramos de 300 s con al menos una idea |

### Orquestación

`procesar(modelo, clase, progreso, auditoria=True)` devuelve:

```python
{
  "fusion": {...},      # 7 listas
  "sintesis": {...},    # 5 campos
  "bloques": 13,
  "cobertura": 96.4,
  "revisados": 0
}
```

### Render

| Función | Qué genera |
|---|---|
| `render(clase, datos, url_video=None)` | El Markdown completo |
| `_tabla_texto(valor, limite)` | Escapa `\|` y trunca |
| `_fecha_larga(dt)` | «martes 3 de noviembre de 2026 a las 19:01» |
| `nombre_archivo(clase)` | `2026-11-03-PRUEBAS-DE-SOFTWARE` |
| `huella(clase)` | SHA-1 de 12 caracteres |

---

## `clase_resumen/cursos.py`

Registro de cursos y resolución de la subcarpeta de destino.

### Estructura `Curso`

| Campo | Ejemplo |
|---|---|
| `codigo` | `DCGS12424` |
| `nombre` | `Pruebas de Software` |
| `carpeta` | `DCGS12424-Pruebas-de-Software` |
| `alias` | `["PRUEBAS DE SOFTWARE"]` |

### Funciones

| Función | Responsabilidad |
|---|---|
| `cargar_registro(ruta)` | Lee `cursos.json`. Tolera que no exista |
| `resolver(materia, codigo, cursos)` | Decide a qué curso pertenece una clase |
| `preparar(base, cursos)` | Crea la carpeta base y una por curso |
| `_sin_tildes(texto)` | Normaliza para comparar «Móviles» con «MOVILES» |
| `_slug(texto)` | Convierte un nombre en parte de carpeta |

### Orden de resolución de `resolver()`

1. Código explícito (`--curso`), aceptando prefijos: `dcgs` → `DCGS12424`.
2. Alias del curso contenido en el nombre de la materia.
3. Todas las palabras del nombre aparecen en la materia.
4. Si nada coincide, `ErrorDeCurso` con la lista de cursos disponibles.

**Por qué existe:** la respuesta de Class no trae el código del curso, solo
`meetingTopic` con el nombre de la materia. Comprobado buscando códigos `[A-Z]{3,5}\d{4,5}`
en los 1.48 MB de respuesta: cero coincidencias.

---

## `clase_resumen/almacen.py`

Rutas y persistencia de una clase. Una carpeta por clase.

### Estructura `Ubicacion`

Envuelve la carpeta y expone las rutas como propiedades:

| Propiedad | Archivo |
|---|---|
| `carpeta` | `clases/<CURSO>/2026-11-03/` |
| `resumen` | `resumen.md` |
| `datos` | `resumen.json` |
| `visor` | `visor.html` |
| `meta` | `clase.json` |
| `transcripcion` | `transcripcion.json` |
| `existe` | Si hay `resumen.md` |

### Funciones

| Función | Responsabilidad |
|---|---|
| `ubicar(base, curso, clase)` | Devuelve la carpeta de la clase, creándola |
| `leer_meta` / `leer_datos` | Lectura tolerante a archivos corruptos |
| `escribir_datos` | Escribe `resumen.json` |
| `leer_transcripcion` | Reconstruye `list[Segmento]` desde disco |
| `_escribir_transcripcion` | Guarda los segmentos en formato compacto |

### Cómo se nombra la carpeta

1. `2026-11-03` si es la primera clase de ese día en el curso.
2. `2026-11-03-2100` si ya existe otra grabación distinta ese día.
3. `2026-11-03-2100-2` en el caso extremo de coincidir hasta el minuto.

La comparación se hace por `recording_id` guardado en `clase.json`, no por el nombre.

### Por qué se guarda `transcripcion.json`

Es lo que permite que `--rehacer` funcione sin red y sobreviva a que la plataforma cambie
o a que se pierda el enlace. Cuesta 220 KB por clase.

---

## `clase_resumen/visor.py`

Generador del HTML. Ver [visor-html](visor-html.md).

### Estructura

| Elemento | Contenido |
|---|---|
| `CSS` | 239 líneas de estilos embebidos |
| `JS` | 153 líneas de comportamiento embebido |
| `generar(...)` | Construye el archivo |
| `_esc(t)` | Escapa HTML |
| `_vinculo(t)` | Genera un `<a data-t="mm:ss">` |

### Funciones JavaScript

| Función | Qué hace |
|---|---|
| `fmt(s)` | Segundos → `mm:ss` o `h:mm:ss` |
| `seek(sec)` | Salta al minuto y reproduce |
| `paint()` | Actualiza línea roja, capítulo activo y contador |
| `clamp(v, a, b)` | Limita un valor a un rango |
| `pct()` | Posición actual como fracción |

### Conectado desde el HTML

| Selector | Función |
|---|---|
| `[data-t]` | Salto de tiempo |
| `.seg button` | Cambio de pista |
| `#rail` | Clic en el mapa |
| `#q` | Búsqueda |
| `.check input` | Checklist persistente |
| `.buscar` | Copiar consulta |

---

## `clase_resumen/__init__.py`

Solo declara `__all__` con los cinco módulos y `__version__ = "1.0.0"`.
