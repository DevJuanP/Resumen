# Salidas

Cada clase vive en su propia carpeta dentro del curso. Las cifras son las de la clase real
`PRUEBAS DE SOFTWARE` del 03/11/2026.

```
clases/DCGS12424-Pruebas-de-Software/2026-11-03/
```

| Archivo | Tamaño real | Contenido |
|---|---|---|
| `resumen.md` | 192 KB | Apuntes de estudio |
| `resumen.json` | 108 KB | Datos estructurados |
| `visor.html` | 344 KB | Visor con video |
| `clase.json` | <1 KB | Metadatos: fecha, ids, huella |
| `transcripcion.json` | 220 KB | Los 1419 segmentos, para re-renderizar sin red |

`resumen.md` es el archivo que se actualiza: al volver a resumir la misma clase se
sobrescribe, nunca se duplica.

## 1. El Markdown

### Cabecera

```markdown
# PRUEBAS DE SOFTWARE

**Fecha:** martes 3 de noviembre de 2026 a las 19:01  
**Duración:** 136 min  
**Docente:** Edison Merino  
**Fuente:** https://cibertec.class.com/player/recording/...

> Primera sesión del curso de Pruebas de Software, centrada en introducir el TDD…
```

La fecha se muestra en **hora local**, ya convertida desde UTC. Si el docente no aparece en
la lista de participantes, la línea se omite.

### Secciones generadas

En este orden exacto (`summarize.py → render()`):

| Sección | Origen | Contenido |
|---|---|---|
| `## Mapa de la clase` | `sintesis.mapa` | Tabla de 4 a 12 tramos con tema y resumen |
| `## Lo que importa` | `sintesis.clave` | 6 a 12 puntos con peso alto/medio/bajo |
| `## Desarrollo completo` | `fusion.ideas` | Todas las ideas en orden de aparición |
| `## Glosario` | `fusion.terminos` | Término, definición y minuto |
| `## Pendientes y avisos` | `fusion.avisos` | Tabla con cuándo, qué y minuto |
| `## Ejemplos y analogías del docente` | `fusion.ejemplos` | Ejemplo y qué ilustra |
| `## Preguntas de tus compañeros` | `fusion.preguntas` | Pregunta y respuesta |
| `## Para investigar por tu cuenta` | `sintesis.investigar` + `fusion.menciones` | Temas con consulta de búsqueda sugerida |
| `## Lo que se omitió` | `sintesis.relleno` o, si está vacío, `fusion.relleno` | Lista de lo descartado |
| `## Cómo usar estos apuntes` | Texto fijo | Guía de 4 pasos |
| Anexo | `clase.segmentos` | Transcripción íntegra dentro de `<details>` |

> **Detalle real:** el `.md` muestra como máximo **25** elementos en «Lo que se omitió»;
> el `.html` muestra hasta **40**. Es una asimetría que existe en el código
> (`summarize.py` usa `relleno[:25]`, `visor.py` usa `omitido[:40]`) y que no se ha unificado.

Las secciones de **desarrollo completo, glosario, ejemplos, preguntas, para investigar y lo
que se omitió** solo aparecen si tienen contenido.

Siempre aparecen:

| Sección | Si está vacía |
|---|---|
| **Mapa de la clase** | Deja la tabla con solo la cabecera |
| **Lo que importa** | Deja el subtítulo «_Ordenado por peso, no por tiempo._» y nada más |
| **Pendientes y avisos** | Muestra «_No se anunciaron fechas ni entregas en esta sesión._» |
| **Cómo usar estos apuntes** | Texto fijo, no depende de datos |
| **Anexo** | Se genera siempre, aunque no haya segmentos |

Comprobado generando un Markdown con todos los datos vacíos.

### Cuerpo real de la clase documentada

| Sección | Elementos |
|---|---|
| Mapa de la clase | 12 tramos |
| Lo que importa | 12 puntos (8 altos, 3 medios, 1 bajo) |
| Desarrollo completo | 176 ideas |
| Glosario | 43 términos |
| Pendientes y avisos | 20 avisos |
| Ejemplos | 28 |
| Preguntas | 15 |
| Para investigar | 6 temas + 35 menciones |
| Lo que se omitió | 7 resúmenes de relleno |
| Anexo | 1419 intervenciones |

Total: 30 540 palabras.

Los 20 avisos incluyen 7 sin fecha (`cuando` vacío), que se muestran con `—` en la tabla.

### Marcas de peso

En «Lo que importa» cada punto lleva un emoji según `peso`:

| Peso | Marca |
|---|---|
| `alto` | 🔴 |
| `medio` | 🟡 |
| `bajo` | ⚪ |

## 2. El visor HTML

Archivo único de 345 KB, sin recursos externos salvo una hoja de Google Fonts.

### Composición

- **Cabecera fija** con materia, fecha, duración, número de intervenciones y docente.
- **Columna izquierda (sticky):** reproductor de video y mapa de la clase.
- **Columna derecha:** todos los apuntes.
- **Barra inferior** en pantallas estrechas con reproducción y salto al video.

### Qué incluye

| Elemento | Comportamiento verificado |
|---|---|
| Reproductor | `<video controls>` con `preload=metadata` |
| Selector Docente / Diapositivas | Cambia de pista manteniendo el segundo actual |
| Mapa de la clase | Barra proporcional a la duración; la altura de cada tramo varía según densidad de ideas |
| Línea roja | Marca la posición actual de reproducción |
| Capítulos | Lista clicable bajo la barra |
| Búsqueda | Filtra apuntes y transcripción en vivo |
| Checklist | Persiste en `localStorage`, con contador `0/6` |
| Botones de búsqueda | Copian la consulta al portapapeles |
| Transcripción | Cada minuto es clicable y salta al video |

### Saltos de tiempo

Cualquier elemento con `data-t="mm:ss"` salta al video. Probado: clic en `73:33` dejó el
video en el segundo 4416 (3 s de diferencia por el tiempo de carga del stream).

En la transcripción hay 1419 elementos clicables, uno por intervención.

### Atajos de teclado

| Tecla | Acción |
|---|---|
| `Espacio` | Reproducir / pausar |
| `→` | Avanzar 10 s |
| `←` | Retroceder 10 s |

Los atajos se desactivan cuando el foco está en un campo de texto.

### El video NO está dentro del HTML

El HTML contiene únicamente dos URLs firmadas de CloudFront, una por pista. No hay bytes de
video embebidos. Ver [visor-html](../03-arquitectura/visor-html.md).

## 3. El JSON

Estructura completa en [json-intermedio](../04-datos/json-intermedio.md).

## Archivos auxiliares

### `clase.json`

Metadatos de la clase. Es lo que permite re-renderizar sin volver a la plataforma.

```json
{
  "materia": "PRUEBAS DE SOFTWARE",
  "cuando": "2026-11-03T19:01:09-05:00",
  "url": "https://cibertec.class.com/player/recording/…",
  "duracion_s": 8164.0,
  "docente": "Edison Merino",
  "participantes": 65,
  "api_base": "https://cibertec.rest.pod-2.sa-east-1.prod.class.com",
  "school_id": "9c635e8a-…",
  "class_uuid": "f389df80-…",
  "recording_id": "12227799-…",
  "huella": "989c82d1c017",
  "creado": "2026-11-05T21:40:00",
  "actualizado": "2026-11-05T22:10:00"
}
```

`huella` es el SHA-1 truncado a 12 caracteres sobre `segundos + texto` de todos los
segmentos. Si coincide con la recién calculada, se omite el resumen.
Ver [huella](../03-arquitectura/huella.md).

### `.uuid`

UUID anónimo que se envía en la cabecera `user_uuid` a Class. Se genera una vez y se
reutiliza. Se puede fijar con `RESUMEN_USER_UUID`.
