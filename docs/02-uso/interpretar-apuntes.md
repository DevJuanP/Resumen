# Cómo leer los apuntes

Guía de interpretación. Útil para no confundir lo que es criterio del modelo con lo que es
dato de la clase.

## «Lo que importa»: 15 minutos de lectura

Es la sección que reemplaza ver la clase. Cada punto trae el minuto exacto por si quieres
comprobarlo en el video.

### De dónde sale el peso

El peso **no** es una métrica calculada con números. Lo asigna el modelo siguiendo tres
criterios definidos en el prompt (`PROMPT_SINTESIS`, `summarize.py`):

| Peso | Criterio textual del prompt |
|---|---|
| `alto` | «si el docente lo repitió, lo llamó importante o lo vinculó a evaluación» |
| `medio` | «si es base para entender lo demás» |
| `bajo` | «si es contexto» |

Es decir: es un juicio del modelo sobre la transcripción, no una medición objetiva. Sirve
como orientación, no como garantía.

### Orden

Los puntos van ordenados **por importancia, no por tiempo**. Por eso el primero de la clase
documentada es `111:49` (el ciclo TDD) y no algo del minuto 0.

## «Mapa de la clase»: orientarse

Tabla de tramos cronológicos. Sirve para dos cosas:

1. Elegir qué parte ver si quieres profundizar en algo concreto.
2. Confirmar que la clase completa quedó cubierta: los tramos deben empezar en `00:00` y
   terminar en la duración total.

En la clase documentada los 12 tramos cubren de `00:00` a `136:00`.

## «Desarrollo completo»: nada se perdió

Es la sección larga. 176 ideas en la clase documentada, cada una con minuto y tipo.

### Los tipos de idea

El prompt pide cinco valores, pero **no hay validación**: lo que devuelva el modelo se
escribe tal cual.

Valores pedidos en el prompt:

| Tipo | Qué significa |
|---|---|
| `concepto` | Explicación de una idea |
| `definicion` | Define un término |
| `procedimiento` | Pasos o forma de hacer algo |
| `comparacion` | Contraste entre dos cosas |
| `opinion` | Valoración del docente |

Valores que aparecieron realmente en la clase documentada (176 ideas):

| Tipo | Cantidad |
|---|---|
| `concepto` | 108 |
| `definicion` | 24 |
| `opinion` | 16 |
| `procedimiento` | 15 |
| `comparacion` | 11 |
| `pregunta` | 1 |
| `ejemplo` | 1 |

Los dos últimos no están en la lista del prompt. El modelo los inventó y el render los
muestra igual, porque el tipo solo se imprime como etiqueta. No rompe nada, pero confirma
que el campo no es un enum cerrado.

## «Para investigar por tu cuenta»

Fue una petición explícita: eres autodidacta y quieres saber qué buscar después.

Viene de dos fuentes combinadas:

1. `sintesis.investigar` — temas con una consulta de búsqueda sugerida, generada por el
   modelo. En el HTML cada consulta es un botón que la copia al portapapeles.
2. `fusion.menciones` — herramientas, autores y normas que el docente nombró al pasar
   (JUnit, Mockito, Mike Cohn, PMBOK…). Se filtran las que ya aparecen en el primer grupo,
   comparando el texto del tema.

## «Pendientes y avisos»: lo que no puedes olvidar

Tabla de fechas, entregas, exámenes y herramientas obligatorias.

### Las fechas relativas ya vienen resueltas

El docente dice «el jueves», no «el 5 de noviembre». El prompt le pasa la fecha de la clase
y le pide resolverlas. En la clase documentada, «el jueves» aparece como
`jueves 2026-11-05`.

### La fecha de la clase se muestra como «hoy»

Si un aviso habla de la propia sesión, en lugar de repetir la fecha se escribe `hoy`, para
que no parezca una tarea pendiente a futuro. Lo hace `_normalizar_cuando()`.

> **Precaución real.** Estas fechas son inferencias del modelo a partir de la fecha de la
> clase. Se comprobó que son coherentes con la transcripción, pero conviene verificar
> cualquier fecha de examen en el sílabo antes de confiar en ella.

## «Lo que se omitió»: por qué puedes confiar

Lista lo que el modelo consideró relleno: saludos, asistencia, problemas de audio, bromas.

Existe para una razón de diseño concreta: el prompt de cada bloque dice explícitamente que
**ante la duda no se descarte nada**. La consigna es «es preferible una idea de más que una
de menos». Por eso el relleno que aparece aquí suele ser genuinamente descartable.

## El anexo: la red de seguridad

Dentro de `<details>` al final del `.md` está la transcripción completa con hablante y
minuto. Si algo del resumen no te cuadra, ahí está el original.

En el HTML está en una sección plegable con scroll propio y búsqueda.

## Los minutos

Formato `mm:ss`. En clases de más de una hora, `111:49` significa 111 minutos y 49
segundos, es decir 1 h 51 min 49 s.

Todos los minutos se verifican contra la transcripción real mediante
`_ajustar_tiempos()`: si el modelo inventa uno que no existe, se corrige al más cercano
(tolerancia de 45 s). Ver [resumen-y-auditoria](../03-arquitectura/resumen-y-auditoria.md).
