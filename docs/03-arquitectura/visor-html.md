# El visor HTML

Todo lo de este documento se comprobó abriendo el HTML generado en un navegador real y
midiendo el resultado.

## Qué es

Un archivo único de 345 KB que pone el video de la clase al lado de los apuntes. Sin
servidor, sin build, sin instalación: se abre con doble clic.

## De dónde sale el video

Esta es la pregunta más importante y la respuesta es tajante: **el HTML no contiene el
video**.

### Comprobación

| Verificación | Resultado |
|---|---|
| ¿Contiene `data:video`? | No |
| ¿Contiene `<source>` embebido? | No |
| Bytes de video dentro del archivo | 0 |
| URLs de video dentro del archivo | 2 |

### Qué contiene en realidad

Dos URLs firmadas de CloudFront, una por pista:

```javascript
window.__CLASE__ = {
  "id": "PRUEBAS-DE-SOFTWARE-20261103",
  "duration": 8164.0,
  "videos": {
    "active_speaker": "https://recordings.pod-2.sa-east-1.prod.class.com/artifacts/.../active_speaker.MP4?Expires=...&Signature=...",
    "shared_screen": "https://recordings.pod-2.sa-east-1.prod.class.com/artifacts/.../shared_screen.MP4?Expires=...&Signature=..."
  }
}
```

El navegador pide el video por rangos (`206 Partial Content`), igual que cuando ves la
repetición en Class. Nunca se descarga el archivo completo a disco.

### Consecuencia

| Aspecto | Efecto |
|---|---|
| Peso del HTML | Bajo (345 KB) |
| Generación | Instantánea |
| Disco ocupado | 0 bytes de video |
| Funciona sin internet | No |
| Funciona al día siguiente | **No**, la firma caduca a las 12 h |

Cuando expira, el reproductor queda en negro y hay que regenerar con `--solo-visor`.

## Estructura

```
┌─────────────────────────────────────────────────────┐
│ cabecera sticky: materia · fecha · duración · buscar │
├────────────────────────┬────────────────────────────┤
│                        │                            │
│  VIDEO                 │  resumen (lede)            │
│  (sticky)              │  Lo que importa            │
│                        │  Investigá por tu cuenta   │
│  Mapa de la clase      │  Pendientes y avisos       │
│  (barra proporcional)  │  Desarrollo completo       │
│                        │  Glosario                  │
│  Capítulos             │  Ejemplos                  │
│                        │  Preguntas                 │
│                        │  Lo que se omitió          │
│                        │  Transcripción             │
└────────────────────────┴────────────────────────────┘
```

En pantallas de menos de 1120 px se convierte en una columna y aparece una barra inferior
fija con reproducción, progreso y salto al video.

## Funciones verificadas

### Salto de tiempo

Cualquier elemento con `data-t="mm:ss"` salta al video.

Prueba real: clic en `73:33` → el video quedó en el segundo 4416 (esperado 4413, la
diferencia es el tiempo de carga del stream).

En la transcripción hay **1419** elementos clicables.

### Cambio de pista

| Botón | Pista |
|---|---|
| Docente | `active_speaker` |
| Diapositivas | `shared_screen` |

Al cambiar, se conserva el segundo actual y el estado de reproducción. Probado: cambio en el
segundo 4429 → siguió en 4433.

Ambas pistas tienen audio, así que puedes escuchar mientras ves las diapositivas.

### Mapa de la clase

Barra horizontal dividida en tramos, con ancho proporcional a la duración real.

La **altura** de cada tramo varía según la densidad de ideas:

```javascript
nivel = min(1.0, ideas_por_minuto / 3.0)
```

Es decir: un tramo con 3 o más ideas por minuto se pinta al máximo; uno vacío queda pálido.

La línea roja marca la posición actual. El tramo activo se resalta en negro.

Las etiquetas de minuto solo se muestran si el tramo mide al menos 6 % del ancho, para
evitar que se pisen. En móvil se ocultan todas.

### Búsqueda

Filtra en vivo todos los elementos con `data-buscable` y oculta las secciones que quedan
vacías.

Probado: buscar `junit` dejó 6 de 1718 elementos visibles.

### Checklist

Los temas de «Investigá por tu cuenta» tienen casilla. El estado se guarda en
`localStorage` con la clave `resumen:{id}` y el contador de la cabecera se actualiza.

Persiste entre sesiones del mismo navegador. No se sincroniza entre dispositivos.

### Copiar consultas

Cada sugerencia de búsqueda es un botón que copia el texto al portapapeles y muestra
«Copiado» durante 1.2 s.

### Atajos

| Tecla | Acción |
|---|---|
| `Espacio` | Reproducir / pausar |
| `→` | +10 s |
| `←` | −10 s |

Se ignoran cuando el foco está en un input.

## Detalles de implementación

### Sin dependencias

Todo el CSS y el JS están embebidos. La única petición externa es la hoja de Google Fonts
(`Newsreader`, `IBM Plex Sans`, `IBM Plex Mono`). Si no hay internet, el navegador usa las
fuentes de respaldo del sistema.

### Accesibilidad

| Elemento | Atributo |
|---|---|
| Buscador | `aria-label` |
| Mapa | `role="slider"`, `aria-label`, `tabindex="0"` |
| Botones de pista | `aria-pressed` |
| Tramos | `aria-label` con tema y rango |
| Foco visible | `outline` de 2 px en todos los interactivos |
| Movimiento reducido | `prefers-reduced-motion` desactiva transiciones y scroll suave |

### Modo móvil

Verificado a 430×900. Sin desbordamiento horizontal (`scrollWidth === clientWidth === 430`).

Hubo que corregir un desbordamiento real de 508 px causado por tablas con
`table-layout: fixed` y `overflow-wrap: anywhere`.

## Cuándo se regenera

`generar()` se llama en tres situaciones:

| Situación | Cómo |
|---|---|
| Ejecución normal con `--visor` | Tras resumir |
| Clase ya procesada con `--visor` | Reutiliza el `.json` |
| Enlaces caducados | `--solo-visor` |

Solo la primera cuesta llamadas al modelo.

## Qué pasa si falla la obtención de URLs

`generar()` envuelve `urls_de_video()` en `try/except`. Si falla, `videos = {}` y el HTML se
genera igual, con un recuadro en lugar del reproductor que dice:

> Los enlaces del video caducaron o no están disponibles.
> Regenera el visor sin volver a resumir:
> `python resumen.py "<url>" --solo-visor`

Es decir: el visor es útil aunque no haya video. Los apuntes, el mapa y la búsqueda siguen
funcionando.
