# Resumen y auditoría

Cómo se convierte la transcripción en apuntes sin perder contenido. Esta es la parte que
responde a la petición de «que no se pierda nada».

## El problema

Una clase de 136 minutos son ~78 000 caracteres, unos 19 500 tokens. Cabe en el contexto de
un modelo moderno, pero:

- Un solo resumen largo tiende a perder el final o a resumir de más.
- Si falla, se pierde todo el trabajo.
- Ordenar por importancia requiere ver la clase entera, cosa que un bloque no puede hacer.

De ahí la estrategia de dos capas: **bloques** para extraer, **síntesis** para priorizar.

## Capa 1: extracción por bloques

### División

`BLOQUE_MIN = 12`, `SOLAPE_MIN = 1`. Los 13 bloques reales:

```
[0, 12] [11, 23] [22, 34] [33, 45] [44, 56] [55, 67]
[66, 78] [77, 89] [88, 100] [99, 111] [110, 122] [121, 133] [132, 135.9]
```

El solape de 1 minuto evita que una idea que empieza al final de un bloque quede cortada. Se
paga con duplicados, que se eliminan después.

### Formato de entrada

Cada línea que ve el modelo:

```
22:08 Edison Merino: es una metodología para ir desarrollando y codificando el sistema
```

`mm:ss`, nombre y texto. Los timestamps van en la propia línea para que el modelo los copie
literalmente y no tenga que calcularlos.

### El prompt de bloque

Está en `summarize.py → PROMPT_BLOQUE`. Texto completo:

```
Conviertes la transcripción automática de una clase en apuntes estructurados en español.

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
```

Dos decisiones explícitas en el prompt:

1. **«Ante la duda, no lo incluyas aquí»** aplica solo a `relleno`. La consigna es conservar.
2. **«Si un término clave es dudoso, añade " (?)"»** permite marcar incertidumbre sin
   inventar. En la clase documentada aparece, por ejemplo, en «Mike Cohn (?)».

### Formato de salida por bloque

```json
{
  "ideas":     [{"t","titulo","explicacion","tipo"}],
  "terminos":  [{"t","termino","definicion"}],
  "avisos":    [{"t","que","cuando"}],
  "ejemplos":  [{"t","ejemplo","ilustra"}],
  "preguntas": [{"t","pregunta","respuesta"}],
  "menciones": [{"t","item","contexto"}],
  "relleno":   ["texto libre"]
}
```

### Normalización de claves

Algunos modelos devuelven `explicación` con tilde en vez de `explicacion`, y entonces el
campo se pierde silenciosamente. Ocurrió de verdad: 13 ideas quedaron vacías.

`_normalizar_claves()` aplica el diccionario `ALIAS`, que mapea variantes y sinónimos:

| Variante recibida | Clave canónica |
|---|---|
| `explicación`, `detalle`, `descripcion`, `texto` | `explicacion` |
| `título`, `punto`, `tema` | `titulo` |
| `definición`, `concepto`, `nombre` | `termino` |
| `qué`, `aviso` | `que` |
| `cuándo`, `fecha` | `cuando` |
| `ilustración`, `ilustracion` | `ilustra` |
| `elemento` | `item` |
| `momento`, `timestamp`, `tiempo`, `minuto` | `t` |

Se aplica recursivamente a toda la estructura.

Si dos claves colapsan en la misma, se conserva el valor no vacío.

## Capa 2: fusión

### `_fusionar()`: duplicados del solape

Compara por similitud de texto (`SequenceMatcher` > 0.78) **y** cercanía temporal. La
ventana depende del tipo, porque no todos los datos se repiten igual:

| Tipo | Ventana |
|---|---|
| ideas | 90 s |
| terminos | 300 s |
| avisos | 600 s |
| menciones | 900 s |

Cuando encuentra un duplicado, conserva la explicación más larga.

Un elemento sin su campo principal (por ejemplo una idea sin `titulo`) se descarta, porque
no aporta nada.

### `_deduplicar_global()`: repetidos lejanos

El mismo concepto puede aparecer al minuto 20 y al 100. `_fusionar` no lo detecta porque la
distancia temporal es grande. Esta función compara solo texto, con umbral 0.82.

Medición aislada sobre la primera versión de los datos: 179 ideas en bruto → 172 tras la
deduplicación global. La ejecución final, con todas las correcciones, cerró en 176 ideas.

### `_consolidar_avisos()`: avisos con redacciones distintas

Los avisos son el caso más difícil: el mismo aviso aparece en dos bloques con palabras
diferentes. Por eso se usa otra medida: **Jaccard** (intersección de palabras sobre unión),
ignorando palabras vacías, con umbral 0.38 y ventana de 40 s.

Resultado en la clase documentada: 20 avisos, sin duplicados como el del delegado que
aparecía dos veces (06:28 y 11:03).

### `_ajustar_tiempos()`: minutos reales

```python
cercano = min(tiempos_reales, key=lambda x: abs(x - t))
if abs(cercano - t) > 45:
    e["t"] = mmss(cercano)
```

Si el modelo escribe `91:07` y no hay ninguna intervención en los 45 segundos alrededor, se
corrige al minuto real más cercano. Impide que un enlace del visor apunte a la nada.

### `_normalizar_cuando()`: «hoy»

Si un aviso tiene la fecha de la propia clase, se escribe `hoy` en lugar de repetirla. Evita
que un aviso de la sesión actual parezca una tarea pendiente.

## Capa 3: auditoría de huecos

Esta es la red de seguridad.

```python
def _huecos(clase, ideas, minimo_s=480):
    # 1. ordenar los minutos de las ideas
    # 2. calcular los intervalos entre minutos consecutivos
    # 3. quedarse con intervalos de más de 8 minutos
    # 4. descartar los que tienen poco texto (<1200 caracteres): son silencios
```

El umbral de 1200 caracteres distingue «no se extrajo nada de aquí» de «aquí no se habló».

Si hay huecos, **se vuelven a analizar** con el mismo prompt y se fusionan de nuevo. En el
mensaje final se informa: `· N tramo(s) reprocesado(s)`.

### Cobertura

`_cobertura()` divide la clase en tramos de 5 minutos y calcula qué porcentaje tiene al menos
una idea asociada.

Fórmula:

```
cobertura = 100 * (tramos_con_idea / tramos_totales)
```

En la clase documentada: **96.4 %**, con `revisados: 0` (no hizo falta reprocesar nada).

El 3.6 % restante corresponde a los primeros minutos de saludos y logística, que no generan
ideas académicas.

## Capa 4: síntesis

Una sola llamada al final con `PROMPT_SINTESIS`. Recibe toda la extracción fusionada en JSON.

Lo que solo se puede hacer viendo la clase entera:

| Campo | Por qué necesita la clase completa |
|---|---|
| `mapa` | Los tramos deben cubrir sin huecos |
| `clave` | Ordenar por importancia requiere comparar todo |
| `investigar` | Detectar qué quedó sin explicar |
| `resumen` | Sintetizar el conjunto |

Reglas del prompt:

- «No inventes contenido nuevo: usa solo lo que aparece abajo.»
- «`clave`: los 6-12 puntos que de verdad importan, ordenados por importancia, no por tiempo.»
- `mapa`: «entre 4 y 12 tramos que cubran toda la clase en orden cronológico, sin huecos».

## Resumen de garantías

| Mecanismo | Qué evita | Verificado |
|---|---|---|
| Bloques independientes | Que un bloque malo arrastre todo | Sí, 13 bloques |
| Solape de 1 min | Perder ideas en los cortes | Sí |
| `_fusionar` | Duplicados del solape | Sí |
| `_deduplicar_global` | Repetidos lejanos | Sí, 179 → 172 en una medición aislada |
| `_consolidar_avisos` | Avisos con redacción distinta | Sí, 16 → 15 |
| `_ajustar_tiempos` | Minutos inventados | Sí |
| Auditoría de huecos | Tramos sin procesar | Sí, 0 huecos detectados |
| Anexo con transcripción | Perder el original | Sí, 1419 intervenciones |

**Ninguna de estas garantías equivale a una revisión humana.** La cobertura mide que haya
ideas asociadas a cada tramo, no que esas ideas sean correctas.
