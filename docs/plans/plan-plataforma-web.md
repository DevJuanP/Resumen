# Plan de implementación — Plataforma web de resúmenes

> **Estado:** **sustituido**. No se va a implementar.
> Lo reemplaza [`plan-interfaz-web-local.md`](plan-interfaz-web-local.md), que cubre el
> mismo objetivo (no escribir comandos en consola) sin multiusuario, sin Docker, sin
> límites por IP y sin BYO-key. Se conserva este documento como registro del análisis.

Documento de trabajo para construir una interfaz web sobre el motor de resúmenes que ya
funciona. El motor (`clase_resumen/`) se reutiliza casi sin cambios.

---

## 1. Objetivo

Que cualquiera —tú o tus amigos— entre a una web, pegue la URL de una repetición de Class y
obtenga el resumen, sin instalar nada ni usar la terminal.

Los resúmenes quedan listados por curso y ordenados por fecha, y se pueden volver a
generar o actualizar.

### Criterios de éxito

1. Pegar una URL y ver el progreso real de la generación.
2. Encontrar después esa clase dentro de su curso, sin recargar a mano.
3. Leer el resumen completo en la web y abrir el video en el minuto exacto.
4. Que un amigo pueda hacerlo sin tocar el código ni instalar Python.

### Lo que NO es este proyecto

No es una plataforma multi-usuario con cuentas, ni un producto público. Es una herramienta
para un grupo cerrado que, más adelante, podría desplegarse.

---

## 2. Decisiones cerradas

| Decisión | Elección | Motivo |
|---|---|---|
| Persistencia | Archivos en `clases/`, sin base de datos | Cero migración; ya funciona con la clase existente |
| Vista de la clase | Render desde `resumen.json` con plantillas propias | Control del diseño; el `.md` queda para descargar |
| Flujo de generación | Previsualizar → confirmar → generar | Evita gastar cuota y 4 minutos con una URL equivocada |
| Curso desconocido | Se crea automáticamente | No bloquea a nadie cuando llega una materia nueva |
| Límite | 3 clases/día por IP con la clave del servidor | Protege la cuota sin molestar al uso normal |
| Estilo visual | Dashboard moderno | Tarjetas, métricas y barra lateral |
| Modelos ofrecidos | Solo «Equilibrado» y «Tu propia IA» | Simplifica la UI; el rápido se descartó por perder avisos |
| Acceso | Sin login | Es una wiki de clases, no un producto con cuentas |
| Video | Botón que abre el visor en otra pestaña | Evita gestionar caducidad dentro de la página |
| Deploy | Dockerfile genérico + README comparativo | Sin acoplarse a una plataforma |
| Borrado | No hay borrado desde la web | Un visitante anónimo no debe poder borrar el trabajo de todos |

---

## 3. Arquitectura

```
Navegador ──HTMX──▶ FastAPI ──▶ cola (1 worker) ──▶ procesar()
                       │                                │
                       │                                ▼
                       └──▶ catalogo.py ──▶ clases/ (archivos)
```

### Stack

**FastAPI + Jinja2 + HTMX + CSS propio.**

- Sin Node, sin build de frontend, sin React.
- HTMX vendorizado (no CDN), para que funcione sin internet.
- Jinja escapa el contenido por defecto.

### Por qué un solo worker en la cola

Cada clase son **14 llamadas al modelo** con 3 hilos internos (`MAX_HILOS = 3`). Con un
worker, nunca hay más de 3 peticiones simultáneas al proveedor, aunque diez personas pulsen
a la vez. La segunda persona espera en cola, pero nadie bloquea el servidor y la cuota no se
multiplica.

---

## 4. Estructura de archivos

```
app/
  main.py           FastAPI: rutas y montaje de estáticos
  catalogo.py       escanea clases/ y construye objetos para la UI
  trabajos.py       cola de 1 worker, estados y progreso
  modelos.py        catálogo de IA y resolución de la clave del usuario
  seguridad.py      validación de URL y límite por IP
  plantillas/
    base.html                 layout, sidebar, topbar
    inicio.html               grid de cursos
    curso.html                clases del curso
    clase.html                resumen renderizado
    nueva.html                formulario de URL
    ajustes.html              formulario BYO
    _previsualizacion.html    partial HTMX
    _progreso.html            partial HTMX (polling)
  static/
    app.css
    app.js
    htmx.min.js               vendorizado

cursos.json         + campo opcional "creado" para los autogenerados
config.json         modelo del servidor
requirements.txt
Dockerfile
.env.example
README-DEPLOY.md
```

---

## 5. Cambios en el código existente

Solo tres, pequeños y compatibles hacia atrás.

| Archivo | Cambio | Motivo |
|---|---|---|
| `clase_resumen/visor.py` | Leer `location.hash` con formato `#t=12:34` y saltar a ese segundo | Enlazar los minutos del resumen con el video |
| `clase_resumen/summarize.py` | `progreso(fase, i, total)` con fase `bloques` o `sintesis` | Mostrar «ordenando la clase…» durante la última llamada |
| `clase_resumen/cursos.py` | `agregar(nombre)` que escribe en `cursos.json` | Autocrear un curso desconocido |

Nada más se toca. `almacen.py`, `fetch.py` y `llm.py` se usan tal cual.

### El detalle del deep-link

`visor.py` ya tiene `seek()` y `window.__seek`, pero no lee la URL. Hay que añadir, al
final del script:

```javascript
const m = /#t=(\d+):(\d+)/.exec(location.hash);
if (m) seek(+m[1] * 60 + +m[2]);
```

Y un listener de `hashchange` para que funcione si ya está abierta.

---

## 6. Modelo de datos en memoria

`catalogo.py` produce, por cada clase encontrada en disco:

```python
@dataclass
class ClaseVista:
    carpeta: str          # "2026-11-03"
    curso: str            # "DCGS12424-Pruebas-de-Software"
    materia: str          # "PRUEBAS DE SOFTWARE"
    cuando: datetime
    duracion_min: int
    docente: str
    ideas: int            # len(resumen.json → fusion.ideas)
    avisos: int
    cobertura: float
    tiene_visor: bool
    tiene_video: bool     # ¿las URLs firmadas siguen vigentes?
    actualizado: str      # ISO de clase.json
```

El escaneo ocurre al arrancar y se invalida al terminar un trabajo. Con 50 clases es del
orden de milisegundos.

`tiene_video` se calcula leyendo el `Expires` de las URLs dentro de `visor.html`: no hace
falta pedir nada a Class.

---

## 7. Rutas

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/` | Inicio: grid de cursos con contadores |
| GET | `/curso/{curso}` | Clases ordenadas, más reciente arriba |
| GET | `/clase/{curso}/{dia}` | Resumen renderizado desde `resumen.json` |
| GET | `/clase/{curso}/{dia}/visor` | `visor.html` servido |
| GET | `/clase/{curso}/{dia}/markdown` | Descarga del `.md` |
| POST | `/clase/{curso}/{dia}/renovar` | Regenera URLs de video (sin modelo, ~1 s) |
| GET | `/nueva` | Formulario |
| POST | `/nueva/previsualizar` | Partial: materia, fecha, curso, duración |
| POST | `/nueva/generar` | Crea trabajo → redirect |
| GET | `/trabajo/{id}` | Página de progreso |
| GET | `/trabajo/{id}/estado` | Partial para polling |
| GET | `/ajustes` | Formulario de IA propia |
| POST | `/ajustes/probar` | Prueba la clave con una llamada mínima |
| GET | `/api/salud` | Healthcheck para el deploy |

---

## 8. La cola de trabajos

```python
@dataclass
class Trabajo:
    id: str
    url: str
    curso: str
    estado: str          # en_cola|descargando|resumiendo|sintetizando|escribiendo|listo|error
    bloques_ok: int
    bloques_total: int
    mensaje: str         # texto mostrado al usuario
    clase: tuple[str, str] | None   # (curso, dia) al terminar
```

### Reglas

| Regla | Detalle |
|---|---|
| Concurrencia | `ThreadPoolExecutor(max_workers=1)` |
| Deduplicación | Si ya hay un trabajo con el mismo `recording_id`, se devuelve ese `id` en vez de duplicar |
| Persistencia | Estados **en memoria**: si se reinicia, se pierden los trabajos en curso |
| Polling | Cada 2 s desde HTMX. Sin WebSockets |
| Timeout | 20 min. Al excederse, se marca error |
| Progreso | `bloques N/M` durante el resumen; «ordenando la clase…» en la síntesis |

### Estados y lo que ve el usuario

| Estado | Texto |
|---|---|
| `en_cola` | «En cola, hay N delante» |
| `descargando` | «Descargando la transcripción…» |
| `resumiendo` | «Analizando bloques 7/13» |
| `sintetizando` | «Ordenando la clase por importancia…» |
| `escribiendo` | «Guardando los apuntes…» |
| `listo` | Redirige a la clase |
| `error` | Mensaje real + botón Reintentar |

---

## 9. Las dos opciones de modelo

### 9.1 Equilibrado (clave del servidor)

```json
{
  "base_url": "https://integrate.api.nvidia.com/v1",
  "model": "nvidia/nemotron-3-ultra-550b-a55b",
  "extra": { "reasoning_budget": 0 }
}
```

Medido sobre la clase real de 136 minutos:

| Métrica | Valor |
|---|---|
| Tiempo | 232 s (3,9 min) |
| Ideas | 187 |
| Términos | 52 |
| Avisos | 15 |
| Ejemplos | 27 |
| Preguntas | 19 |
| Menciones | 47 |
| Mapa / Clave | 12 / 12 |
| Cobertura | 96,4 % |

> **`reasoning_budget: 0` es obligatorio.** Con el modo *thinking* activo, la API de
> NVIDIA gasta todo el presupuesto en razonamiento y devuelve `content` vacío. Verificado
> con `nemotron-3-ultra-550b-a55b` (`out=8000, reasoning=8000, content=""`) y con
> `nemotron-3.5-lightning-30b-a3b` en modo thinking.

### 9.2 Tu propia IA

Formulario con tres campos:

| Campo | Ejemplo |
|---|---|
| Endpoint | `https://api.openai.com/v1` |
| Modelo | `gpt-4o-mini` |
| Clave | `sk-...` |

Presets de un clic: OpenAI, Groq, OpenRouter, DeepSeek, Together.

**Validación al guardar:** `POST {endpoint}/models` con la clave. Si responde 200, se
acepta. Si no, se muestra el error real del proveedor.

**La clave nunca toca el servidor.** Se guarda en `localStorage` y viaja en la cabecera
`X-IA-Config` solo durante la generación. El servidor la usa y la descarta; no se registra
en logs ni se escribe a disco.

### 9.3 Modelos descartados y por qué

| Modelo | Resultado | Motivo del descarte |
|---|---|---|
| `nemotron-3.5-lightning-30b-a3b` | 106 s, 140 ideas, **12 avisos** | Pierde 8 avisos frente a 20; los avisos son fechas de examen |
| `nemotron-3-ultra-550b-a55b` con thinking medium | 90 s, **contenido vacío** | Gasta 8 000 tokens razonando |
| `deepseek-v4.1-flash-1017` (Hive) | Funciona | Depende de un proveedor con saldo |

---

## 10. Seguridad

| Riesgo | Mitigación |
|---|---|
| **SSRF**: pegar una URL interna | Solo `https://<host>/player/recording/<uuid>/<uuid>`, con el host restringido a `*.class.com` (configurable por env) |
| **Abuso de cuota** | 3 clases/día por IP con la clave del servidor. Contador en `clases/.limites.json` |
| **Inyección HTML** | Autoescape de Jinja activo. Nada de `\|safe` sobre contenido generado por el modelo |
| **Claves ajenas** | Solo en el navegador. Nunca en logs ni en disco |
| **Enumeración de trabajos** | Los IDs son UUID v4 |
| **Borrado accidental** | Sin rutas de borrado |

### Sobre el límite por IP

Se cuenta en un archivo JSON con fecha. Se resetea a medianoche local. Limitación conocida:
detrás de un proxy todos comparten IP; en local funciona bien, y es suficiente para el
objetivo actual.

---

## 11. Pantallas

### Inicio

- Barra lateral con la lista de cursos y su contador de clases.
- Barra superior con buscador y botón «Nueva clase».
- Grid de tarjetas de curso: código, nombre, número de clases, última actualización.

### Curso

- Cabecera con código y nombre del curso.
- Lista de clases como tarjetas horizontales, ordenadas por fecha descendente.
- Cada tarjeta: fecha, duración, docente, tres métricas (ideas, avisos, cobertura) y un
  badge de estado del video (vigente / caducado).

### Clase

- Dos columnas: izquierda «Lo que importa» y el mapa de la clase; derecha avisos, glosario y
  desarrollo completo plegable.
- Arriba: «Ver con video» y «Descargar .md».
- Cada `mm:ss` es un enlace a `visor#t=mm:ss`.

### Nueva

- Un campo para la URL y un botón «Comprobar».
- Tras comprobar: tarjeta con materia, fecha, duración, curso detectado y número de
  intervenciones, más un aviso de si esa clase ya existe.
- Botón «Generar resumen» (y «Volver a generar» si ya existía).

### Generando

- Stepper vertical de las cinco fases, con barra de progreso y contador de bloques.
- Tiempo transcurrido, para que no parezca congelado.
- Si falla: error real y botón Reintentar.

### Ajustes

- Tarjeta 1: «Usar el modelo del servidor», con el aviso de 3 al día.
- Tarjeta 2: «Usar mi propia IA», con formulario, presets y botón Probar.

---

## 12. Fases de trabajo

### Fase 0 — Cimientos (45 min)

Instalar `fastapi uvicorn jinja2 python-multipart`, crear la estructura, `base.html` con el
layout y el CSS base del dashboard, `/api/salud`.

**Aceptación:** `uvicorn app.main:app` arranca y `/` responde.

### Fase 1 — Catálogo y navegación (1 h 30)

`catalogo.py`, inicio con los cursos reales, página de curso.

**Aceptación:** se ve `DCGS12424` con su clase del 3 de noviembre, ordenada y con métricas
correctas extraídas de `resumen.json`.

### Fase 2 — Vista de la clase (2 h)

Render de `resumen.json`, descarga del `.md`, servir el visor, botón «Renovar enlaces» y
deep-link `#t=mm:ss`.

**Aceptación:** la clase se lee completa en la web; un clic en `73:33` abre el video en ese
segundo.

### Fase 3 — Generación (3 h)

Formulario, previsualización, cola, progreso con polling y redirección al resultado.

**Aceptación:** una URL nueva pasa por confirmación, muestra progreso real y termina
apareciendo en su curso sin recargar.

### Fase 4 — Modelo propio (1 h 30)

Ajustes, presets, prueba de clave y paso de `X-IA-Config` al trabajo.

**Aceptación:** con una clave de Groq genera usando Groq; sin clave usa el servidor.

### Fase 5 — Pulido y preparación de deploy (1 h 30)

Buscador, estados vacíos, manejo de errores, `requirements.txt`, `Dockerfile`,
`.env.example` y `README-DEPLOY.md`.

| Fase | Tiempo | Acumulado |
|---|---|---|
| 0 | 45 min | 45 min |
| 1 | 1 h 30 | 2 h 15 |
| 2 | 2 h | 4 h 15 |
| 3 | 3 h | **7 h 15** |
| 4 | 1 h 30 | 8 h 45 |
| 5 | 1 h 30 | **10 h 15** |

A las ~7 horas ya se puede pegar una URL y ver el resumen aparecer. Ese es el punto para
decidir si el proyecto aporta el valor esperado.

---

## 13. Preparación para el deploy

El repo queda listo para cualquiera de estas opciones, sin acoplarse a ninguna.

| Archivo | Contenido |
|---|---|
| `Dockerfile` | Python 3.12-slim, uvicorn, volumen en `/data/clases` |
| `requirements.txt` | fastapi, uvicorn, jinja2, python-multipart (versiones fijadas) |
| `.env.example` | `RESUMEN_DATA_DIR`, `RESUMEN_HOST_PERMITIDO`, `RESUMEN_MODELO` |
| `README-DEPLOY.md` | Comparativa de plataformas y aviso del disco efímero |

### El escollo real del deploy gratuito

No es el hosting: es el **disco**. Los resúmenes viven en `clases/`. Si el contenedor se
reinicia y el disco es efímero, se pierden. Cualquier opción gratuita necesita un volumen
persistente, y la mayoría lo cobra.

| Plataforma | Gratis | Disco | Nota |
|---|---|---|---|
| Hugging Face Spaces | Sí, 16 GB RAM | Efímero sin pago | Duerme por inactividad |
| Render | 750 h/mes | Volumen de pago | Duerme a los 15 min |
| Fly.io | Crédito limitado | Volumen pequeño | Requiere tarjeta |
| VPS (Oracle) | Capa gratuita | Disco real | Configuración manual |

---

## 14. Riesgos y limitaciones aceptadas

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Latencia impredecible de NVIDIA (16 s vs 89 s el mismo bloque) | El progreso puede parecer congelado | Tiempo transcurrido + mensaje «sigue trabajando» |
| URLs de video caducan a 12 h | Reproductor negro | Botón «Renovar enlaces», ~1 s |
| Reinicio pierde trabajos en curso | Hay que relanzar | Se avisa en la UI |
| `localStorage` para claves | Riesgo de XSS | Escapado estricto; documentado |
| Disco efímero en deploy | Se pierden resúmenes | Volumen persistente o exportar `clases/` |
| Un solo worker | La segunda persona espera | Deliberado: protege la cuota |
| Límite por IP tras proxy | Todos comparten cuota | Aceptado para uso local |

---

## 15. Fuera de alcance

Para evitar sorpresas al revisar el resultado:

- Sin login, cuentas ni perfiles
- Sin borrado desde la web
- Sin edición manual del resumen
- Sin base de datos
- Sin WebSockets
- Sin notificaciones por email
- Sin procesamiento por lotes (una URL a la vez)
- Sin búsqueda semántica (solo filtro por texto)
- Sin multi-idioma

---

## 16. Anexo: por qué no se usan las IAs gratuitas de OpenCode

Se planteó inicialmente que los amigos usaran los modelos gratuitos de OpenCode. **No es
posible.**

Las «IAs gratis» de OpenCode no son una API pública: son credenciales gestionadas dentro
del propio cliente. Comprobado llamando al endpoint:

```
POST https://opencode.ai/zen/v1/chat/completions
→ HTTP 401 {"error":{"type":"authentication_error","code":"api_key_expired"}}
```

La documentación confirma que los proveedores del catálogo se conectan con `/connect`
dentro de OpenCode. No hay URL pública para que una app externa consuma esos modelos.

**Consecuencia:** la web ofrece la clave del servidor (NVIDIA) o la clave propia del
usuario. No hay tercera vía.
