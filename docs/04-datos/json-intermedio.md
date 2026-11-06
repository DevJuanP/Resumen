# El JSON intermedio

Archivo que se genera con `--crudo`. Es la pieza que permite re-renderizar sin volver a
llamar al modelo.

## Por qué existe

Resumir cuesta 14 llamadas al modelo (13 bloques + 1 síntesis) y entre 4 y 9 minutos. El JSON guarda el resultado de
ese trabajo para que puedas:

- Regenerar el `.md` si cambias el formato (`--rehacer`).
- Regenerar el `.html` cuando caduquen los enlaces del video (`--solo-visor`).
- Revisar exactamente qué extrajo el modelo.
- Reutilizar los datos en otra herramienta.

## Estructura

Archivo real: `clases/2026-11-03-PRUEBAS-DE-SOFTWARE.json`, 108 KB.

```json
{
  "clase": { ... },
  "fusion": { ... },
  "sintesis": { ... },
  "bloques": 13,
  "cobertura": 96.4,
  "revisados": 0
}
```

### `clase`

Metadatos. Se elimina al cargar para re-renderizar (`datos.pop("clase")`), porque el objeto
`Clase` se reconstruye desde la plataforma.

| Campo | Ejemplo |
|---|---|
| `materia` | `PRUEBAS DE SOFTWARE` |
| `cuando` | `2026-11-03T19:01:09-05:00` |
| `url` | Enlace de la repetición |
| `duracion_s` | `8164.0` |

### `fusion`

Lo extraído bloque a bloque, ya fusionado y deduplicado.

| Clave | Elementos reales | Campos de cada elemento |
|---|---|---|
| `ideas` | 176 | `t`, `titulo`, `explicacion`, `tipo` |
| `terminos` | 43 | `t`, `termino`, `definicion` |
| `avisos` | 20 | `t`, `que`, `cuando` |
| `ejemplos` | 28 | `t`, `ejemplo`, `ilustra` |
| `preguntas` | 15 | `t`, `pregunta`, `respuesta` |
| `menciones` | 35 | `t`, `item`, `contexto` |
| `relleno` | 40 | texto libre |

Ejemplo de una idea:

```json
{
  "t": "04:21",
  "titulo": "Pruebas de software como herramienta principal",
  "explicacion": "El docente plantea cambiar el concepto común de que las pruebas se hacen al final del proyecto. Se propone entenderlas como una herramienta principal que guía paso a paso el ciclo de desarrollo de software.",
  "tipo": "concepto"
}
```

### `sintesis`

El resultado de la segunda pasada.

| Clave | Tipo | Real |
|---|---|---|
| `resumen` | `str` | Texto de 559 caracteres |
| `mapa` | `list` | 12 tramos |
| `clave` | `list` | 12 puntos |
| `investigar` | `list` | 6 temas |
| `relleno` | `list` | 7 resúmenes |

Campos de cada elemento:

| Clave | Campos |
|---|---|
| `mapa[]` | `desde`, `hasta`, `tema`, `que_pasa` |
| `clave[]` | `t`, `punto`, `desarrollo`, `peso` |
| `investigar[]` | `tema`, `por_que`, `buscar` |

Ejemplo de un punto clave:

```json
{
  "t": "111:49",
  "punto": "Ciclo TDD: rojo, verde, refactorizar",
  "desarrollo": "TDD (Test-Driven Development), creado por Kent Beck dentro de Extreme Programming, consiste en escribir primero la prueba que falla (rojo)…",
  "peso": "alto"
}
```

### Métricas

| Campo | Significado |
|---|---|
| `bloques` | Cuántos bloques se analizaron (13) |
| `cobertura` | Porcentaje de tramos de 5 min con ideas (96.4) |
| `revisados` | Cuántos huecos se reprocesaron (0) |

## Valores posibles de los campos enumerados

### `ideas[].tipo`

El prompt pide `concepto`, `definicion`, `procedimiento`, `comparacion` u `opinion`.

**No hay validación.** En la clase documentada el modelo devolvió además `pregunta` (1) y
`ejemplo` (1). Se escriben tal cual y el render los muestra sin problema, porque el tipo solo
se usa como etiqueta.

### `clave[].peso`

`alto`, `medio`, `bajo`. En la clase documentada: 8 altos, 3 medios y 1 bajo.

Cualquier otro valor cae en `medio` al renderizar:

```python
peso = (c.get("peso") or "medio").lower()
marca = {"alto": "🔴", "medio": "🟡", "bajo": "⚪"}.get(peso, "🟡")
```

### `ideas[].t`, `avisos[].t`, etc.

Siempre `mm:ss`. Ya ajustados a intervenciones reales por `_ajustar_tiempos()`.

## Cómo se usa

### `--rehacer`

```python
datos = json.loads(crudo.read_text(encoding="utf-8"))
datos.pop("clase", None)          # el objeto Clase se reconstruye
destino.write_text(render(clase, datos), encoding="utf-8")
generar(clase, datos, visor)
```

### `--solo-visor`

Igual, pero sin el `render()`.

### Sin `--crudo`

Si no guardaste el JSON, `--rehacer` y `--solo-visor` fallan con código 2:

```
✗ No hay JSON guardado en ...\clases\2026-11-03-PRUEBAS-DE-SOFTWARE.json
  Genera primero los apuntes con --crudo.
```

Comprobado.

## Uso más allá del proyecto

El JSON es la forma más cómoda de llevar los apuntes a otra herramienta: tarjetas de Anki,
una base de datos, o cualquier generador propio. Las ideas con minuto y tipo son
directamente convertibles en preguntas.
