# Flujo completo

Recorrido exacto de una ejecución con `--crudo --visor`, siguiendo el código de
`clase_resumen/cli.py`.

## Diagrama

```
           python resumen.py <enlace> --crudo --visor
                              │
                              ▼
                 ┌────────────────────────┐
             1.  │   cli.main()           │  parsea argumentos
                 └───────────┬────────────┘
                             ▼
                 ┌────────────────────────┐
             2.  │  fetch.obtener_clase() │  HTTP a Class
                 │                        │  → objeto Clase
                 └───────────┬────────────┘  (1419 segmentos)
                             ▼
                 ┌────────────────────────┐
             3.  │  ¿huella coincide?     │──sí──▶ «Ya existe» → fin (0)
                 └───────────┬────────────┘
                             │ no
                             ▼
                 ┌────────────────────────┐
             4.  │  summarize.dividir()   │  13 bloques de 12 min
                 └───────────┬────────────┘  con 1 min de solape
                             ▼
                 ┌────────────────────────┐
             5.  │  3 hilos × bloques     │  una llamada al modelo
                 │  _analizar_bloque()    │  por bloque → JSON
                 └───────────┬────────────┘
                             ▼
                 ┌────────────────────────┐
             6.  │  fusión + dedup +      │  limpia solapes
                 │  anclaje de tiempos    │
                 └───────────┬────────────┘
                             ▼
                 ┌────────────────────────┐
             7.  │  auditoría de huecos   │  tramos >8 min sin ideas
                 │                        │  → reprocesa (aquí: 0)
                 └───────────┬────────────┘
                             ▼
                 ┌────────────────────────┐
             8.  │  sintetizar()          │  1 llamada al modelo
                 │                        │  → mapa, clave, investigar
                 └───────────┬────────────┘
                             ▼
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
  render() → .md       generar() → .html    json → .json
  (192 KB)             (345 KB)             (108 KB)
                              │
                              ▼
                 ┌────────────────────────┐
                 │  guardar huella        │  .huellas.json
                 └────────────────────────┘
```

## Paso a paso

### 1. Argumentos

`cli.main()` valida que haya `url` o `--texto`. Si no, termina con código 2.

### 2. Obtención de la clase

`fetch.obtener_clase(url)`:

1. Extrae `host`, `class_uuid` y `recording_id` de la URL con una expresión regular.
2. Lee `https://{host}/player/config.json` para descubrir la URL de la API.
3. Hace `POST {api}/meeting/{class_uuid}/v1_join_async_meeting` con
   `{"recordingUuid": recording_id}` y la cabecera `user_uuid`.
4. Recibe un JSON de ~1.4 MB con `recordingData.transcripts` y `students`.
5. Normaliza: convierte a `Segmento`, resuelve roles y descarta ruido.

Resultado para la clase documentada: 1419 segmentos, 136 min, docente Edison Merino,
64 participantes.

### 3. Control de duplicados

`summarize.huella(clase)` calcula SHA-1 sobre los segmentos. Se compara con
`clases/.huellas.json`. Si coincide y no hay `--forzar`, termina sin gastar modelo.

### 4. División en bloques

`summarize.dividir(clase)` con `BLOQUE_MIN = 12` y `SOLAPE_MIN = 1`.

Los 13 bloques reales:

```
[0, 12] [11, 23] [22, 34] [33, 45] [44, 56] [55, 67]
[66, 78] [77, 89] [88, 100] [99, 111] [110, 122] [121, 133] [132, 135.9]
```

Cada bloque se convierte en líneas de texto con el formato
`mm:ss Nombre: texto`.

### 5. Análisis en paralelo

`ThreadPoolExecutor(max_workers=3)` lanza `_analizar_bloque()` sobre cada bloque. Cada uno
es una llamada independiente al modelo con `PROMPT_BLOQUE`.

Devuelve JSON con siete listas: `ideas`, `terminos`, `avisos`, `ejemplos`, `preguntas`,
`menciones`, `relleno`.

Por qué en bloques y no la clase entera: un bloque mal resumido no arrastra al resto, y
cada llamada cabe cómodamente en el contexto del modelo.

### 6. Fusión

Cuatro operaciones sobre los resultados crudos:

| Función | Qué resuelve |
|---|---|
| `_normalizar_claves()` | Variantes como `explicación` con tilde o `detalle` se convierten a la clave canónica |
| `_fusionar()` | Quita duplicados dentro de la ventana de solape, comparando texto y cercanía temporal |
| `_deduplicar_global()` | Quita repetidos entre bloques lejanos por similitud de texto |
| `_ajustar_tiempos()` | Ancla cada minuto a una intervención real |

Detalle en [resumen-y-auditoria](resumen-y-auditoria.md).

### 7. Auditoría

`_huecos()` busca tramos de más de 8 minutos (`minimo_s=480`) sin ninguna idea asociada.
Si encuentra alguno con suficiente texto (>1200 caracteres, para no confundir silencios),
lo vuelve a analizar.

En la clase documentada: **0 huecos**. La cobertura fue del 96.4 %.

### 8. Síntesis

Una única llamada con `PROMPT_SINTESIS`, pasándole la extracción fusionada completa en JSON.
Devuelve cinco campos: `resumen`, `mapa`, `clave`, `investigar`, `relleno`.

Esta segunda pasada existe porque ordenar por importancia requiere ver la clase entera, algo
que ningún bloque individual puede hacer.

### 9. Escritura

| Archivo | Función |
|---|---|
| `.md` | `summarize.render()` |
| `.html` | `visor.generar()` |
| `.json` | `json.dumps()` dentro de `cli.main()` |
| `.huellas.json` | Actualización de la huella |

## Tiempos reales

Cuatro ejecuciones completas sobre la misma clase:

| Ejecución | Duración | Notas |
|---|---|---|
| 1 | 335 s | modelo `glm-5.3-flash` |
| 2 | 548 s | con auditoría activa, 0 huecos |
| 3 | 399 s | regeneración completa |
| 4 | 255 s | ejecución final |

El rango es amplio porque depende de la latencia del proveedor y de cuántos bloques corran
en paralelo. Los 3 hilos son un límite fijo en `MAX_HILOS`.

## Consumo del modelo

| Concepto | Valor |
|---|---|
| Llamadas por clase | 14 (13 bloques + 1 síntesis), más las de auditoría |
| Tokens de entrada aproximados | ~20 000 |
| `max_tokens` por bloque | 12 000 |
| `max_tokens` de síntesis | 12 000 |
| Reintentos | Hasta 4 por llamada, con espera exponencial |

Estimación: la transcripción completa son ~78 000 caracteres, unos 19 500 tokens. Al
dividir en bloques con solape, la suma de entradas ronda los 20 000 tokens.
