# Visión general

## Qué es

Una herramienta de línea de comandos en Python que toma el enlace de una repetición de
clase alojada en **Class** (`class.com`, la plataforma montada sobre Zoom que usa Cibertec)
y produce apuntes de estudio en Markdown, con cada idea anclada al minuto exacto de la
grabación.

Opcionalmente genera un visor HTML que pone el video de la clase al lado de los apuntes.

## Qué problema resuelve

El autor del proyecto planteó tres necesidades concretas:

1. La clase avanza despacio y verla completa cuesta tiempo.
2. No se puede perder nada importante, porque hay cosas que sí importan.
3. Hay muchos comentarios irrelevantes que conviene saltarse.

La herramienta ataca las tres: condensa, audita la cobertura para no perder contenido y
separa explícitamente el relleno.

## Decisión de diseño principal: no transcribir audio

El proyecto **no descarga audio ni ejecuta ningún modelo de reconocimiento de voz**.

La plataforma Class ya genera una transcripción automática con nombre del hablante y marca
de tiempo, y el reproductor la obtiene de una llamada HTTP. La herramienta reutiliza esa
misma respuesta.

Consecuencias reales de esta decisión:

- No hace falta GPU ni `ffmpeg`.
- No hay dependencias que instalar.
- La calidad de la transcripción es la que da Zoom, no la que podría dar un Whisper local.
- Los errores de la transcripción automática se heredan (ver
  [limitaciones](../06-limitaciones/limitaciones.md)).

## Qué hace

Verificado ejecutándolo sobre una clase real:

- Extrae la transcripción completa con hablante, minuto y rol (docente o estudiante).
- Descarta avisos de grabación del tipo «This meeting is being recorded».
- Convierte la marca de tiempo de la plataforma de UTC a hora local.
- Resume la clase en bloques paralelos y fusiona los resultados.
- Audita la cobertura y reprocesa tramos sin contenido extraído.
- Ancla cada minuto a una intervención real de la grabación.
- Genera un `.md` con nueve secciones y un anexo con la transcripción íntegra.
- Genera un `.html` con el video, búsqueda, checklist persistente y mapa de la clase.
- Guarda un `.json` intermedio que permite re-renderizar sin llamar al modelo.
- Evita reprocesar una clase ya hecha comparando una huella de la transcripción.
- Acepta una transcripción pegada a mano si no hay enlace disponible.

## Qué NO hace

Esta lista es tan importante como la anterior:

- **No descarga el video.** El HTML solo contiene URLs firmadas; no hay bytes de video
  dentro del archivo. Comprobado: 0 coincidencias de `data:video` en el HTML generado.
- **No descarga el audio.**
- **No transcribe.** No hay Whisper ni ningún motor de voz en el proyecto.
- **No se conecta a Class con usuario y contraseña.** No hay login ni gestión de sesión.
  La transcripción se obtiene sin autenticación; solo el video usa URLs firmadas.
- **No descubre clases automáticamente.** Hay que pasarle el enlace de cada repetición.
- **No conoce el código del curso.** Class no lo expone en la respuesta; se declara en
  `cursos.json` y se resuelve por el nombre de la materia.
- **No procesa varias clases en una sola ejecución.** Una URL, una clase.
- **No exporta a PDF, Word, Anki ni Notion.**
- **No resume las diapositivas.** Solo analiza el texto de la transcripción; no hay OCR ni
  análisis de imagen, aunque el video de diapositivas sí se puede ver en el visor.
- **No guarda historial ni base de datos.** El estado son archivos en disco.
- **No funciona con plataformas distintas de Class** salvo usando `--texto` con una
  transcripción copiada a mano.
- **No corrige la transcripción contra el audio.** No verifica si el hablante o el minuto
  son correctos en origen.

## Componentes

```
resumen.py              punto de entrada (9 líneas)
clase_resumen/
  fetch.py              obtención y normalización de la transcripción
  llm.py                cliente HTTP para un endpoint compatible con OpenAI
  summarize.py          bloques, fusión, auditoría, render Markdown
  visor.py              generador del HTML autocontenido
  cli.py                argumentos, orquestación, códigos de salida
```

Detalle de cada uno en [arquitectura](../03-arquitectura/modulos.md).

## Audiencia de esta documentación

Escrita para que puedas retomar el proyecto después de un tiempo sin recordar nada, y para
que otra persona pueda mantenerlo leyendo solo estos archivos.
