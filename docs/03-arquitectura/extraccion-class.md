# Extracción desde Class

Cómo se obtiene la transcripción. Todo lo de este documento se comprobó inspeccionando las
peticiones reales del reproductor.

## La clave: la transcripción ya existe

La plataforma Class (producto de class.com montado sobre Zoom) genera automáticamente una
transcripción con hablante y marca de tiempo. El panel «Transcripción» del reproductor es
solo una vista de esos datos.

El reproductor obtiene todo en **una sola petición**:

```
POST https://{host}/player/config.json          ← descubrir la API
POST {api}/meeting/{class_uuid}/v1_join_async_meeting
     user_uuid: <uuid estable>
     {"recordingUuid": "<recording_id>"}
```

Respuesta real: **1.48 MB**. No hizo falta ni descargar audio ni transcribir.

## Paso 1: descubrir la API

Cada institución tiene su propio subdominio. El reproductor publica la configuración en:

```
https://{host}/player/config.json
```

Respuesta real del Cibertec:

```json
{
  "api": "https://cibertec.rest.pod-2.sa-east-1.prod.class.com",
  "web": "https://cibertec.class.com",
  "websocket": "wss://websockets.pod-2.sa-east-1.prod.class.com",
  "enablePWA": false,
  "environment": "prod"
}
```

`fetch._config_del_host()` usa `api`. Si falla, lanza `ErrorDeClase` indicando la URL exacta
que no se pudo leer.

## Paso 2: identificar la grabación

La URL pública tiene esta forma:

```
https://{host}/player/recording/{class_uuid}/{recording_id}
```

Ambos son UUID. La expresión regular `PATRON_REPLAY` exige 36 caracteres hexadecimales con
guiones en ambos, así que una URL malformada se rechaza antes de hacer ninguna petición.

## Paso 3: pedir la grabación

### Cabeceras usadas

| Cabecera | Valor |
|---|---|
| `user_uuid` | UUID de `.uuid`, estable entre ejecuciones |

> **Comprobado:** la petición `join` **no requiere autenticación**. Se probó con un UUID
> inventado y sin cookies, y respondió `200` con los 1420 segmentos. Lo que sí está
> protegido con URL firmada y caducidad de 12 h es el **video** (CloudFront), no la
> transcripción.
| `Origin` | `https://{host}` |
| `Referer` | `https://{host}/` |
| `Content-Type` | `application/json` |
| `User-Agent` | Chrome 156 en Windows |
| `Accept-Encoding` | `identity` |

`Accept-Encoding: identity` es deliberado: se comprobó que la respuesta llega sin comprimir
y así se evita depender de un descompresor.

### Estructura de la respuesta

Claves de nivel superior observadas:

```
token, participant_id, meeting_id, password, user_uuid, is_host,
meetingProvider, meetingTopic, reportingEvents, zoomStates, notes,
chats, tabs, recordingData, adHocSessionDetails, classId, classUuid,
webhooks, students, settings
```

De todo eso el proyecto usa cuatro partes:

| Clave | Qué se toma |
|---|---|
| `recordingData.transcripts` | Los 1419 segmentos de transcripción |
| `recordingData.when` | Fecha de la grabación (en UTC) |
| `recordingData.duration` | Duración en segundos (8164) |
| `recordingData.schoolId`, `classId`, `recordingId` | Identificadores para pedir el video |
| `students` | Lista de participantes, para saber quién es el docente |
| `chats` | Se guarda en `Clase.chats` pero **no se usa en la salida** |
| `meetingTopic` | Nombre de la materia |

### Estructura de un transcript

```json
{
  "class_session_note_id": "93819616767_4:7:16786432:7:1675368214",
  "class_id": 3383,
  "student_id": 70289,
  "type": "transcript",
  "content": "Bueno, nuestro compañero",
  "timestamp": 1793750502265,
  "data": {
    "content": "Bueno, nuestro compañero",
    "end_time": 1793750504323,
    "start_time": 1793750502265,
    "user_name": "GUSTAVO HUAMAN BERROCAL",
    "message_id": "93819616767_4:7:16786432:7:1675368214",
    "is_recording": true,
    "breakout_name": "",
    "meeting_zoom_id": "93819616767_16786432_-DGhEUgsaFtZEP-"
  },
  "override_text": null,
  "override_author_user_id": null
}
```

Campos que el proyecto usa:

| Campo | Uso |
|---|---|
| `timestamp` | Minuto del segmento |
| `data.user_name` | Hablante |
| `data.content` | Texto |
| `override_text` | Si existe, tiene prioridad sobre `data.content` |

`override_text` permite que un docente corrija la transcripción a mano desde la plataforma.
En la clase documentada estaba vacío en los 1419 segmentos, pero el código lo respeta.

## Paso 4: normalizar

`obtener_clase()` aplica estas transformaciones:

### Cálculo del minuto

```python
segundos = (timestamp_del_segmento - when_de_la_grabación) / 1000
```

Resultado para la clase documentada: del primer segmento al último hay 135.8 minutos, y la
duración declarada es 8164 s = 136 min. Coherente.

### Resolución de roles

Se busca el nombre del hablante en la lista `students`. Si su `role` es `teacher`, `host` o
`co-host`, el segmento se marca como `docente`.

En la clase documentada: 63 estudiantes y 1 docente. Solo `Edison Merino` quedó como
docente, y los 1419 segmentos útiles son suyos salvo uno.

### Filtrado de ruido

`_es_ruido()` descarta, comparando en minúsculas:

- Texto vacío.
- `this meeting is being recorded.`
- `this meeting is being recorded`
- `recording...`

En la clase documentada esto eliminó el aviso inicial de grabación, dejando 1419 de 1420
segmentos.

### Limpieza del nombre de materia

```python
re.sub(r"\s*-\s*PROF\..*$", "", materia, flags=re.IGNORECASE)
```

`PRUEBAS DE SOFTWARE - PROF. EDISON MERINO V. (TE/LA)` → `PRUEBAS DE SOFTWARE`.

## Paso 5: los videos

Aparte de la transcripción, hay un endpoint para obtener URLs firmadas:

```
GET {api}/recording/v1/schools/{school_id}/class/{class_uuid}
    /recordings/{recording_id}/artifacts
    ?contents_list=active_speaker,shared_screen,audio_transcript,closed_caption
```

Respuesta: una lista con `contents`, `url`, `recordingId` y `timeToLive`.

Artefactos disponibles en la clase documentada:

| `contents` | Formato | Tamaño real |
|---|---|---|
| `active_speaker` | MP4 | 115.6 MB |
| `shared_screen` | MP4 | 146.7 MB |
| `audio_transcript` | VTT | 0.2 MB |
| `closed_caption` | VTT | 0.1 MB |
| `timeline` | JSON | 4.0 MB |

El proyecto solo usa los dos MP4. Los VTT no se descargan porque la transcripción del `join`
ya es más rica: incluye el nombre del hablante, que el VTT no siempre trae.

## Paso 5bis: respaldo con el VTT

**Añadido el 2026-11-06 tras un caso real.** Class no rellena `recordingData.transcripts` al
mismo tiempo que publica el artefacto `audio_transcript`. Hay grabaciones con
`transcripts: []` y `status: AVAILABLE` que sí tienen el VTT completo.

Sin este respaldo, esas clases fallaban con «La clase no tiene transcripción utilizable»
aunque su transcripción estuviera disponible desde el primer minuto.

### Cuándo se activa

Solo si `transcripts` no produjo ningún segmento. El camino normal nunca se ve afectado.

### Cómo se parsea

El VTT de Class trae el hablante al principio del texto, en mayúsculas:

```
WEBVTT

1
00:00:08.280 --> 00:00:16.490
ELVER NOEL MAYTA HERNANDEZ: Ya disculpen, estudiantes ahí.
```

`fetch.segmentos_desde_vtt()` acepta además el formato `<v Nombre>texto</v>` y las comas
decimales. La decisión de si lo que precede a los dos puntos es un nombre se toma con
`_parece_nombre()`: más del 80 % de letras en mayúscula. Así «ya dónde van a exponer»
no se confunde con un hablante.

### Roles

El VTT no distingue docente de estudiante. Se cruza con `students` del `join` comparando el
primer nombre, porque las dos fuentes abrevian distinto (`ELVER NOEL MAYTA HERNANDEZ` se
normaliza a `Elver Mayta` en un sitio y `Elver Hernandez` en el otro).

### Coste real medido

Caso: `SPTI02423 PROYECTO INTEGRADOR`, 168 min.

| Dato | VTT | Transcripción normal (136 min) |
|---|---|---|
| Cues / intervenciones | 579 | 1419 |
| Palabras | 5 852 | ~13 000 |
| Tokens de entrada | ~8 600 | ~19 500 |
| Cobertura temporal | 99,9 % (llega a 2:47:40) | 100 % |
| Hablantes distintos | 14 | 2 |

**El VTT es más barato pero menos denso**: 35 palabras por minuto frente a 96. Las ideas
extraídas serán menos, y el resumen puede quedarse corto en clases donde el docente habla
mucho y los subtítulos resumen.

### Detalle de los MP4

Comprobado pidiendo solo los primeros bytes de cada uno:

| Dato | Valor |
|---|---|
| Resolución | 1920×1080 |
| Audio | Sí, pista AAC (`mp4a`) presente en ambos |
| `timeToLive` | 43 200 s = 12 h |

Que ambos tengan audio importa: se puede escuchar la clase aunque el visor esté mostrando la
pista de diapositivas.

### Las URLs son firmadas

Ejemplo de parámetros:

```
?Expires=1793885944&Policy=eyJTdGF0ZW1lbnQi...&Signature=CJJe0y1Cz-uvDu7...&Key-Pair-Id=K3I2E6JIU6UFWX
```

Es el esquema de URLs firmadas de CloudFront. La firma caduca a las 12 horas.

**Consecuencia práctica:** el HTML generado deja de reproducir video al día siguiente. Hay
que regenerarlo con `--solo-visor`.

## Modo alternativo: `--texto`

Si no hay enlace, `clase_desde_texto()` interpreta texto pegado del panel «Transcripción».

Formatos aceptados:

```
NOMBRE DEL HABLANTE   07:01:11 p. m.
Texto de lo que dijo.
```

```
[03:15] Nombre: texto en la misma línea
```

El segundo formato también calcula la base a partir de la primera hora, para que los
minutos empiecen en cero.

Limitación real: en este modo no hay rol (todos quedan como `estudiante`), no hay docente y
no hay video asociado.
