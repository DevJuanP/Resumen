# Modelo de datos

Las dos estructuras que circulan por el proyecto, con valores reales de la clase
documentada.

## `Segmento`

Definida en `clase_resumen/fetch.py`. Una intervención de una persona.

| Campo | Tipo | Descripción | Ejemplo real |
|---|---|---|---|
| `segundos` | `float` | Segundos desde el inicio de la grabación | `1328.0` |
| `hablante` | `str` | Nombre normalizado | `Edison Merino` |
| `texto` | `str` | Lo que dijo | `es una metodología para ir desarrollando…` |
| `rol` | `str` | `docente` o `estudiante` | `docente` |

```python
@dataclass
class Segmento:
    segundos: float
    hablante: str
    texto: str
    rol: str = "estudiante"
```

### De dónde sale cada campo

| Campo | Origen en la respuesta de Class |
|---|---|
| `segundos` | `(timestamp - when) / 1000` |
| `hablante` | `_normalizar_nombre(data.user_name)` |
| `texto` | `override_text` o `data.content` |
| `rol` | Búsqueda del nombre en `students` |

### Distribución real

La clase documentada tiene 1419 segmentos:

| Rol | Segmentos |
|---|---|
| `docente` | 1418 |
| `estudiante` | 1 |

Casi toda la clase la habla el docente. El único segmento de estudiante es el saludo inicial
de Gustavo Huaman.

## `Clase`

Definida en `clase_resumen/fetch.py`. Todo lo necesario para procesar y renderizar.

| Campo | Tipo | Descripción | Valor real |
|---|---|---|---|
| `url` | `str` | Enlace de la repetición | `https://cibertec.class.com/player/recording/...` |
| `materia` | `str` | Nombre limpio de la asignatura | `PRUEBAS DE SOFTWARE` |
| `cuando` | `datetime` | Inicio en hora local, con zona | `2026-11-03T19:01:09-05:00` |
| `duracion_s` | `float` | Duración en segundos | `8164.0` |
| `segmentos` | `list[Segmento]` | Las intervenciones | 1419 elementos |
| `chats` | `list[dict]` | Mensajes del chat. **Se guarda pero no se usa en la salida** | 71 elementos |
| `docente` | `str` | Nombre del docente | `Edison Merino` |
| `participantes` | `int` | Total de asistentes | `64` |
| `grabacion` | `dict` | `recordingData` crudo de la plataforma | dict de ~15 claves |
| `api_base` | `str` | URL de la API | `https://cibertec.rest.pod-2.sa-east-1.prod.class.com` |
| `school_id` | `str` | Identificador de la institución | `9c635e8a-8fb4-4016-b10a-75ed67c1b0ec` |
| `class_uuid` | `str` | Identificador de la clase | `f389df80-8e8e-4d4d-aaf5-7331d1719e9b` |
| `recording_id` | `str` | Identificador de la grabación | `12227799-7fc3-5cbe-8023-9e859798763a` |

### Campos que solo sirven para el video

`api_base`, `school_id`, `class_uuid` y `recording_id` se usan exclusivamente en
`urls_de_video()`. Si usas `--texto`, quedan vacíos y por eso no hay reproductor.

### Campo `grabacion`

Guarda la respuesta cruda por si hace falta inspeccionar algo que no se extrajo. No se usa en
ningún cálculo.

### Campo `chats`

Se rellena con los 71 mensajes del chat de la clase, pero **ninguna parte del render lo lee**.

Es una vía de mejora evidente: las preguntas de estudiantes suelen estar en el chat y hoy se
obtienen solo de la transcripción de audio. Ver
[mejoras-propuestas](../08-futuro/mejoras-propuestas.md).

## `Bloque`

Interna de `summarize.py`. Un trozo de transcripción listo para el modelo.

| Campo | Tipo | Ejemplo |
|---|---|---|
| `inicio` | `float` | `1320.0` |
| `fin` | `float` | `8160.0` |
| `lineas` | `list[str]` | `["132:00 Edison Merino: en la fase de desarrollo…"]` |
| `texto` (propiedad) | `str` | Las líneas unidas con `\n` |

## `Modelo`

Interna de `llm.py`. La configuración resuelta del endpoint.

| Campo | Ejemplo |
|---|---|
| `base_url` | `https://api-cdn.thehive.ai/api/v3` |
| `model` | `zai-org/glm-5.3-flash` |
| `api_key` | *(en memoria, nunca se escribe a disco)* |
| `extra` | `{"reasoning_effort": "low"}` |

La propiedad `etiqueta` devuelve `zai-org/glm-5.3-flash @ api-cdn.thehive.ai/api/v3`, que es
lo que se imprime en consola.

## Flujo de los datos

```
respuesta de Class (1.48 MB)
        │
        ├─ transcripts ──▶ list[Segmento] ──▶ Clase
        ├─ students    ──▶ roles ───────────▶ Clase
        ├─ when        ──▶ datetime local ──▶ Clase
        └─ duration    ──▶ float ───────────▶ Clase
                                              │
                        ┌─────────────────────┘
                        ▼
              dividir() → list[Bloque]
                        │
                        ▼
              modelo → JSON por bloque
                        │
                        ▼
              fusion + sintesis (dict)
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
      .md             .html           .json
```
