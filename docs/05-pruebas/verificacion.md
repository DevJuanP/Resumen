# Verificación

Qué se comprobó realmente. Sin adornos: distingue lo probado de lo que solo se razonó.

## Probado ejecutando

### Caso completo sobre una clase real

| Paso | Resultado |
|---|---|
| Descarga de transcripción | 1.48 MB, 1420 segmentos |
| Filtrado de ruido | 1419 segmentos útiles |
| Cálculo de duración | 8164 s = 136 min |
| Fecha convertida a local | `2026-11-03T19:01:09-05:00` (martes) |
| Docente detectado | `Edison Merino` |
| Participantes | 64 |
| División en bloques | 13 bloques |
| Resumen | 4 ejecuciones completas sin error |
| Cobertura | 96.4 % |
| Huecos reprocesados | 0 |
| Archivos generados | `.md` 192 KB, `.html` 345 KB, `.json` 108 KB |

### Comandos

| Escenario | Resultado |
|---|---|
| `python resumen.py --help` | Lista las 9 opciones |
| Sin argumentos | Código 2, `indica el enlace de la repetición o usa --texto` |
| Enlace no válido | Código 2, mensaje con el formato esperado |
| `--solo-visor` sin JSON | Código 2, indicando dónde falta |
| Segunda pasada misma clase | `Ya existe y está actualizado`, sin modelo |
| `--rehacer` | Regenera `.md` y `.html` sin modelo |
| `--texto` con archivo de prueba | 4 segmentos parseados correctamente |

### Visor HTML en navegador real

| Comprobación | Resultado |
|---|---|
| El `<video>` carga | `readyState 4`, duración 8164 s |
| Reproduce | Sí, `currentTime` avanza |
| Salto desde el resumen | Clic en `73:33` → segundo 4416 |
| Cambio de pista | Docente → Diapositivas conservando el segundo |
| Línea de tiempo | Se mueve a 54.09 % al saltar |
| Capítulo activo | Cambia a `70:00` automáticamente |
| Búsqueda `junit` | 6 de 1718 elementos visibles |
| Checklist | Contador `0/6`, persistente en localStorage |
| Móvil 430×900 | Sin desbordamiento horizontal |
| Vídeo dentro del HTML | 0 bytes. Solo 2 URLs firmadas |

### Datos del video

| Comprobación | Resultado |
|---|---|
| `active_speaker` | 200, 115.6 MB, MP4 |
| `shared_screen` | 200, 146.7 MB, MP4 |
| Audio en ambas pistas | Sí, `mp4a` presente |
| Resolución | 1920×1080 |
| Caducidad de la firma | 12 h (43 200 s) |

### Verificaciones de código

| Comprobación | Resultado |
|---|---|
| `python -m py_compile` en todos los módulos | Sin errores |
| `ruff check` | Sin errores de corrección; solo avisos de estilo (excepciones amplias, imports) |
| Import sin usar | Corregido |
| Sintaxis de plantillas f-string con comillas anidadas | Corregido (falló al escribir) |

## Probado de forma aislada

Funciones ejecutadas sobre los datos reales, sin llamar al modelo:

| Función | Resultado |
|---|---|
| `_normalizar_nombre()` | 7 casos: «Edison Merino», «Juan Esteban», «Yuly Huanca», «Carlos Delgado», «Ana Torres», «Gustavo Huaman», «Sin nombre» |
| `_deduplicar_global()` | 179 ideas → 172 (medición aislada sobre datos antiguos) |
| `_ajustar_tiempos()` | Sin cambios cuando los minutos son válidos |
| `_cobertura()` | 96.4 % |
| `_huecos()` | 0 tramos de más de 8 min |
| `_consolidar_avisos()` | 16 avisos → 15 (eliminó el del delegado duplicado) |
| `clase_desde_texto()` | 4 segmentos de un archivo de 6 líneas |

## Bugs encontrados y corregidos durante el desarrollo

Estos ocurrieron de verdad y están corregidos. Se documentan porque explican decisiones del
código.

### 1. Zona horaria

La plataforma devuelve `when` en UTC. La clase figuraba como «miércoles 4 de noviembre»
cuando en Lima fue «martes 3 a las 19:01». Esto además corría un día los «el jueves» de los
avisos.

**Corrección:** `_fecha()` aplica `.astimezone()`.

### 2. Claves con tilde

El modelo devolvía `explicación` en lugar de `explicacion`. 13 ideas quedaron sin texto.

**Corrección:** diccionario `ALIAS` y `_normalizar_claves()`.

### 3. Respuestas vacías por razonamiento

Con `deepseek-v4.1-flash-1017`, el modelo gastaba los 12 000 tokens de presupuesto en
razonamiento interno y devolvía contenido vacío. El `usage` mostraba
`reasoning_tokens: 6000` con `content: ""`.

**Corrección:** detección de `reasoning_content` y aumento de `max_tokens`. Además se cambió
a `glm-5.3-flash` con `reasoning_effort: low`.

### 4. Duplicados en los solapes

El mismo aviso aparecía dos veces con redacciones distintas.

**Corrección:** `_consolidar_avisos()` con Jaccard.

### 5. Nombres mal abreviados

`EDISON LORENZO MERINO VILLAGARAY` se abreviaba como `Edison Villagaray` (apellido materno).

**Corrección:** con 3 palabras se toma `partes[1]`, no `partes[2]`.

### 6. Maquetación del visor

El contenedor del grid se cerraba antes de tiempo y las notas caían debajo del video a todo
el ancho.

**Corrección:** eliminar un `</div>` sobrante.

### 7. Barras del mapa invisibles

`inset: auto 0 0 0` dejaba altura cero en los segmentos.

**Corrección:** `inset: 0`.

### 8. Desbordamiento en móvil

508 px de ancho en una pantalla de 430, por tablas con contenido no ajustable.

**Corrección:** `table-layout: fixed` y `overflow-wrap: anywhere`.

### 9. Etiquetas pisadas en el mapa

Los minutos de tramos estrechos se superponían.

**Corrección:** solo se muestran si el tramo supera el 6 % del ancho; en móvil se ocultan.

### 10. Clave del modelo sin resolver

Al día siguiente, la configuración de OpenCode cambió: la clave ya no era un literal sino
una referencia `{file:~/.secrets/...}`. Sin resolverla, la petición salía con un token
inválido y el proveedor respondía `401 Unauthorized`.

**Corrección:** `_resolver_referencia()` en `llm.py`, que interpreta `{file:...}` y
`{env:...}` igual que OpenCode.

### 11. Huellas perdidas al crear subcarpetas

El control de duplicados leía `.huellas.json` de la carpeta base, pero los resúmenes
pasaron a subcarpetas por curso, así que no encontraba nada y volvía a resumir.

**Corrección:** la huella se guarda ahora dentro de `clase.json`, en la carpeta de cada
clase, con lectura del formato antiguo como respaldo.

### 12. Docente equivocado

La lista `students` incluye a todos los presentes. En una revisión aparecieron **dos
docentes** (Edison Merino y Giomar Castro) y el código se quedaba con el primero de la
lista. El orden de `students` no es estable entre peticiones, así que el nombre del
docente cambiaba de una ejecución a otra sin que cambiara la clase.

**Corrección:** se cuentan las intervenciones de cada docente y se elige al que más habla.
Resultado: Edison Merino (1418 intervenciones) en lugar de Giomar Castro (0).

### 13. `--rehacer` dependía de la red

Aunque el objetivo era re-renderizar sin modelo, seguía descargando 1.48 MB de la
plataforma. Inútil si la clase ya no está disponible o no hay conexión.

**Corrección:** `_buscar_por_grabacion()` localiza la clase en disco por el
`recording_id` de la URL. Ahora `--rehacer` y `--solo-visor` tardan **menos de un segundo**
y funcionan sin red.

## Lo que NO se probó

Sé honesto sobre esto al retomar el proyecto:

| Aspecto | Estado |
|---|---|
| Otra institución distinta de Cibertec | No probado. El código lee `config.json`, así que debería funcionar, pero no se verificó |
| Otra materia | Solo una clase procesada |
| Clase en otro idioma | El prompt pide español de salida; la transcripción en otro idioma no se probó |
| `--texto` de punta a punta con modelo | Solo se probó el parseo, no el resumen completo |
| Clases de más de 3 horas | No probado. El número de bloques crecería y `MAX_HILOS` es fijo en 3 |
| Grabaciones en breakout rooms | No probado. Todos los segmentos de la clase real tenían `breakout_name` vacío |
| Corrección de `override_text` | Ese campo estaba vacío en los 1419 segmentos |
| Modelos distintos de `glm-5.3-flash` | No probado de forma sistemática |
| Recuperación si el modelo devuelve JSON truncado | `_extraer_json` lo intenta, pero no se forzó el caso |
| Comportamiento si la plataforma cambia la API | No hay versión de API fijada |

## Cómo re-verificar

Si algo cambió en la plataforma o en el modelo:

```bash
# 1. ¿Sigue funcionando la extracción?
python -c "from clase_resumen.fetch import obtener_clase; c=obtener_clase('URL'); print(len(c.segmentos), c.materia)"

# 2. ¿Sigue funcionando el resumen?
python resumen.py "URL" --forzar --crudo --visor

# 3. ¿Qué cobertura dio?
python -c "import json; d=json.load(open('clases/ARCHIVO.json',encoding='utf-8')); print(d['cobertura'], d['revisados'])"

# 4. ¿El visor abre y reproduce?
# abrir el .html y pulsar un minuto del resumen
```
