# Plan de implementación — Interfaz web local mínima

> **Estado:** **implementado y verificado** (2026-11-06).
> Sustituye a [`plan-plataforma-web.md`](plan-plataforma-web.md), que describía una
> plataforma multiusuario con Docker y BYO-key. Ese proyecto **no** se hace.

Documento de trabajo para poner una interfaz con botones sobre el motor de resúmenes que ya
funciona. Es **local, de un solo usuario (`git`)**: nada de cuentas, ni deploy, ni límites
por IP.

**Uso:** `python web.py` (o doble clic en `Iniciar web.bat`) → http://127.0.0.1:8765

---

## 1. Objetivo y criterios de éxito

Una web que corre en tu máquina, abierta con un comando, donde **no escribes nada en consola**:

1. Pegas el link de una repetición de Class → pulsas **Generar** → ves el progreso real →
   abres el resumen con el video.
2. Los resúmenes ya generados aparecen listados por curso, sin recargar a mano.
3. Botón **Renovar video** para las clases cuyo visor quedó en negro (links firmados de 12 h).
4. Botón **Regenerar** para rehacer una clase ya existente.
5. `clase_resumen/` **no se modifica**. El CLI sigue funcionando idéntico.

---

## 2. Decisiones cerradas (verificadas en este repo)

| Decisión | Elección | Evidencia |
|---|---|---|
| Dependencias | **Solo biblioteca estándar** (`http.server`, `threading`, `subprocess`) | `fastapi/uvicorn/jinja2` **no están instalados**. Mantener «cero instalación» del README |
| Modelo | **No se toca. Ya está correcto** | `llm.cargar()` devuelve `https://api.deploy.com/api/v1` · `deepseek-ai/deepseek-v4.1-flash-1017` · `{'reasoning_effort': 'low'}` |
| Prueba en vivo | El modelo acepta `json_object` en `low` | Llamada real: `{'ok': True, 'n': 1}` |
| Clave | Se resuelve sola desde `~/.secrets/deploy-key` vía `llm._desde_opencode()` | El archivo existe; `config.json` no contiene la clave |
| Ejecución del motor | **Subproceso** `python resumen.py <url> --visor` | Aisla fallos de un trabajo de 9 min; cero duplicación de la lógica de escritura |
| Previsualización | **Se elimina** (no estaba pedida) | Un link inválido falla en `obtener_clase()` **antes** de llamar al modelo (0 cuota), y `huella()` evita pagar dos veces. No aporta protección |
| Vista de la clase | Se sirve el **`visor.html` ya generado** | Es autocontenido (CSS y JS inline). No hay que renderizar `resumen.json` |
| Frontend | HTML + JS vanilla, sin HTMX ni build | Una sola página, `fetch` + `setInterval` |
| Bind | **`127.0.0.1` únicamente** | Es local; nunca expuesto en la red |

---

## 3. Qué NO se toca

`clase_resumen/*` (todos los módulos), `resumen.py`, `config.json`, `cursos.json`, `clases/`.
Cero refactors. Cero cambios de comportamiento del CLI.

> Consecuencia aceptada: la síntesis final no emite progreso propio. La UI lo infiere
> (ver §5). Documentado como limitación, no como bug.

---

## 4. Archivos nuevos

```
web.py                    entrada: python web.py [--puerto 8765] [--abrir]
web/
  __init__.py
  servidor.py             ThreadingHTTPServer, tabla de rutas, estáticos
  trabajos.py             cola de 1 worker + subproceso + parser de progreso
  catalogo.py             escaneo de clases/ → cursos y clases para la UI
  paginas.py              HTML del índice (string, sin motor de plantillas)
  static/
    app.css
    app.js
pruebas/
  test_web.py             unittest de catálogo, parser y rutas
Iniciar web.bat           doble clic para arrancar
```

Nada dentro de `clase_resumen/`. `web.py` vive al lado de `resumen.py`, así que
`RAIZ = Path(__file__).parent` funciona igual que en `cli.py`.

---

## 5. Contrato con el CLI (lo más delicado del plan)

`trabajos.py` lanza:

```
[sys.executable, "resumen.py", "<url>", "--visor"]              # generar
[sys.executable, "resumen.py", "<url>", "--forzar", "--visor"]  # regenerar
[sys.executable, "resumen.py", "<url>", "--solo-visor"]         # renovar
```

con `cwd=RAIZ` y `env` heredado + **`PYTHONIOENCODING=utf-8`** (obligatorio: el CLI imprime
`✓`, `…`, `·`).

### Parseo del progreso

Tres trampas reales del stdout actual, todas verificadas:

1. **El progreso usa `\r`, no `\n`** — `cli.main` hace
   `print(f"\r  bloques {i}/{total}", end="")`. Un lector por líneas no vería nada hasta el
   final. → Se lee en streaming y se corta por **`\r` y `\n`**.
2. **Hay códigos ANSI** — `_gris()` los emite siempre (`\033[90m`), no solo bajo Windows
   Terminal. → Se limpian con `re.sub(r"\x1b\[[0-9;]*m", "", linea)`.
3. **La ubicación final solo está en el texto** — `  Clase: <ruta>`. → Se captura con
   `^  Clase: (.+)$`; de ahí salen `(curso, dia)`. Respaldo: `catalogo.buscar_por_url()`.

### Máquina de estados

| Señal en stdout | Estado |
|---|---|
| proceso arrancado | `en_cola` |
| `Descargando la transcripción` | `descargando` |
| `Resumiendo con …` | `resumiendo` |
| `  bloques i/M` | `resumiendo` (i/M) |
| último bloque visto | `sintetizando` (heurística: la síntesis es la llamada final) |
| `✓ …resumen.md` | `escribiendo` |
| exit 0 | `listo` |
| exit ≠ 0 o timeout | `error` (mensaje real del stderr, sin ANSI) |

Caso especial: `✓ Ya existe y está actualizado` → `listo` con aviso «ya existía, no se
gastó cuota». Es exactamente el comportamiento de `huella()`.

---

## 6. Catálogo

`catalogo.py` escanea `clases/<curso>/<dia>/` y lee `clase.json` + `resumen.json`:

```python
@dataclass
class ClaseVista:
    curso: str            # carpeta del curso
    dia: str              # "2026-11-03"
    materia: str          # clase.json["materia"]
    cuando: datetime      # clase.json["cuando"]
    duracion_min: int
    docente: str
    url: str              # para el botón Regenerar
    ideas: int            # len(resumen.json["fusion"]["ideas"])
    avisos: int
    cobertura: float
    tiene_visor: bool
    video_vivo: bool      # ¿hay URL firmada con Expires futuro en visor.html?
    actualizado: str
```

`video_vivo`: se lee el `Expires=` de la URL del video dentro de `visor.html` y se compara
con `time.time()`. Sin red. Si no hay coincidencia → `False` (botón Renovar destacado).

Escaneo al arrancar + invalidación al terminar un trabajo. Con 1 clase son milisegundos.

### Datos reales de la única clase existente

Verificado leyendo sus archivos:

| Dato | Valor |
|---|---|
| Curso | `DCGS12424-Pruebas-de-Software` |
| Día | `2026-11-03` |
| Ideas | 176 |
| Avisos | 20 |
| Cobertura | 96.4 % |
| Duración | 136 min |
| Video | expiraba `2026-11-06 09:35`, aún vigente al implementar |

---

## 7. Rutas

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/` | Índice: formulario + cursos con sus clases |
| POST | `/nueva` | `{id}` del trabajo (JSON) |
| GET | `/trabajo/{id}` | Estado del trabajo (JSON, para polling) |
| GET | `/ver/{curso}/{dia}` | `visor.html` de esa clase (HTML) |
| GET | `/md/{curso}/{dia}` | `resumen.md` como descarga |
| POST | `/renovar/{curso}/{dia}` | Lanza `--solo-visor` → `{id}` |
| POST | `/regenerar/{curso}/{dia}` | Lanza `--forzar --visor` con la URL guardada → `{id}` |
| GET | `/api/salud` | JSON: modelo, si hay clave, nº de cursos |
| GET | `/static/*` | CSS y JS |

---

## 8. Cola de trabajos

```python
@dataclass
class Trabajo:
    id: str                  # uuid4().hex
    url: str
    modo: str                # generar | regenerar | renovar
    estado: str
    fase_txt: str            # lo que ve el usuario
    bloques_ok: int
    bloques_total: int
    inicio: float
    resultado: tuple[str, str] | None   # (curso, dia)
    error: str
```

- **1 worker**: `queue.Queue` + un `threading.Thread` daemon. Nunca dos clases a la vez, así
  que el motor mantiene como máximo sus `MAX_HILOS = 3` peticiones al proveedor.
- **Deduplicación**: si hay un trabajo activo con la misma URL, `POST /nueva` devuelve su
  `id` en vez de crear otro.
- **Timeout**: 20 min → `subprocess.kill()`, estado `error`.
- **Persistencia**: en memoria. Si reinicias el servidor, los trabajos en curso se pierden
  (la UI lo dice al no encontrar el `id`).
- El servidor es `ThreadingHTTPServer` para que el polling no se bloquee tras el worker.

---

## 9. Interfaz (una sola página)

**Arriba:** campo de URL + botón «Generar resumen». Debajo, un panel de progreso que solo
aparece cuando hay trabajo: barra, `bloques 7/13`, tiempo transcurrido y un texto de fase.
Al terminar: enlace «Abrir resumen» y «Descargar .md».

**Abajo:** un bloque por curso con su lista de clases. Cada fila: fecha, duración, docente,
ideas, avisos, cobertura, y dos botones — «Ver» y «Renovar video» (este último resaltado si
`video_vivo` es falso), más «Regenerar».

Estados vacíos: sin cursos («aún no hay resúmenes»), sin clases. Errores en un `div` visible,
con el mensaje real del CLI, nunca un «algo falló».

---

## 10. Seguridad

| Riesgo | Mitigación |
|---|---|
| Acceso desde la red | `HTTPServer` ligado a `127.0.0.1` |
| Path traversal en `/ver/{curso}/{dia}` | Validar cada segmento con `^[\w.\-]+$` y resolverse dentro de `clases/` antes de abrir |
| CSRF desde una web abierta en el navegador | Verificar `Origin`/`Host` en los `POST` |
| Inyección en la página | Los valores van por `textContent`, no `innerHTML`. El HTML del índice se escapa con `html.escape` |
| Fuga de la clave | Nunca sale de `~/.secrets`; el subproceso la hereda del entorno |
| Botón de borrado | No existe |

---

## 11. Modelo

No se modifica nada. Se **verifica** en `/api/salud` y al arrancar:

```
modelo : deepseek-ai/deepseek-v4.1-flash-1017
base   : https://api.deploy.com/api/v1
extra  : {"reasoning_effort": "low"}
```

### Por qué no hay que tocar `config.json`

Ya contiene exactamente eso:

```json
{
  "base_url": "https://api.deploy.com/api/v1",
  "model": "deepseek-ai/deepseek-v4.1-flash-1017",
  "reasoning_effort": "low"
}
```

`llm.cargar()` lo lee, no encuentra clave en el archivo, y la resuelve desde el proveedor
`deploy` de OpenCode (`{file:~/.secrets/deploy-key}`) porque coincide el `base_url`.

Si `llm.cargar()` falla (p. ej. desaparece `~/.secrets/deploy-key`), el servidor arranca
igual pero muestra un aviso claro y desactiva «Generar», en vez de fallar a los 9 minutos.

---

## 12. Fases

| Fase | Trabajo | Tiempo |
|---|---|---|
| **0** | `web.py` + `servidor.py` (rutas, estáticos, `/api/salud`, validación de segmentos) | 30 min |
| **1** | `catalogo.py` + índice con cursos y clases reales | 45 min |
| **2** | `trabajos.py` (cola, subproceso, parser `\r`, ANSI) + formulario + polling | 1 h 30 |
| **3** | Ver visor, descargar `.md`, renovar, regenerar | 45 min |
| **4** | CSS, estados vacíos, errores, `Iniciar web.bat`, `pruebas/test_web.py` | 45 min |
| | **Total** | **~4 h 15** |

Uso real desde la Fase 2, que es cuando ya pegas un link y sale el resumen.

---

## 13. Pruebas

`pruebas/test_web.py` con `unittest` (stdlib), sin red:

- `catalogo.escanear()` sobre `clases/` real → 1 curso, 1 clase, `ideas == 176`,
  `avisos == 20`, `cobertura == 96.4`.
- Parser de progreso con una muestra que contiene `\r`, ANSI y `Clase: <ruta>` → estados y
  ubicación correctos.
- Segmento con `..` o `/` → rechazado por `ruta_bajo()`.

Verificación manual, la que cuenta:

1. `python web.py` → abre el navegador y lista la clase del 3 de noviembre.
2. «Ver» → el visor reproduce el video.
3. Pegar la **misma** URL → termina al instante con «ya existía», sin gastar cuota.
4. Pegar una URL basura → error inmediato en < 2 s, sin llamadas al modelo.
5. `python resumen.py --lista` → salida idéntica a antes.

---

## 14. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| La shell del workspace falla con `grantWrite` | Bloquea ejecutar y probar | Usar `danger-full-access` al implementar, o ejecutar antes la skill `diagnose-windows-sandbox-acl` |
| El parser depende del texto impreso por el CLI | Cambiar un `print` rompe el progreso | Los mensajes quedan fijados como contrato; la prueba con muestra real los cubre |
| La síntesis no reporta progreso | Parece congelado el último minuto | Texto «ordenando la clase…» + cronómetro |
| `~/.secrets/deploy-key` desaparece | Nada genera | `/api/salud` lo detecta al arrancar |
| Reinicio a mitad de trabajo | Se pierde | Aviso en la UI; basta volver a pulsar |

---

## 15. Fuera de alcance

Sin login, sin multiusuario, sin Docker, sin deploy, sin base de datos, sin BYO-key, sin
previsualización, sin edición del resumen, sin borrado, sin HTMX, sin dependencias nuevas.

---

## 16. Paso 0 opcional

No hay repositorio git (solo `.gitignore`). Conviene `git init` + commit antes de empezar,
para poder revertir la Fase 2 si el parser da problemas.

---

## 17. Resultado de la implementación

Las cinco fases están hechas y las 33 pruebas pasan (`python -m unittest discover -s pruebas`).

| Fase | Resultado |
|---|---|
| 0 | `web.py` + `web/servidor.py`: 8 rutas, estáticos, `/api/salud`, CSRF por `Origin` |
| 1 | `web/catalogo.py`: 1 curso, 1 clase, 176 ideas, 20 avisos, 96,4 % |
| 2 | `web/trabajos.py`: cola de 1 worker, parser `\r`+ANSI, timeout de 20 min |
| 3 | Ver, `.md`, renovar y regenerar, con confirmación en el navegador |
| 4 | `app.css`, `app.js`, estados vacíos, `Iniciar web.bat`, 33 pruebas |

### Lo que se comprobó ejecutando

| Prueba | Resultado |
|---|---|
| `GET /` | 200, 3 560 bytes |
| `GET /api/salud` | 200, modelo `deepseek-v4.1-flash-1017`, modo `low` |
| `GET /ver/…` | 200, 350 149 bytes (el visor completo) |
| `GET /md/…` | 200, 193 064 bytes con `Content-Disposition` |
| `GET /trabajo/noexiste` | 404 |
| `GET /ver/../../resumen.py/x` | 404 |
| `GET /md/…/..%2f..%2fconfig.json` | 404 |
| `POST /nueva` con URL basura | 400, sin llamar al modelo |
| Trabajo real con URL existente | `descargando` → `listo` en 2 s, `ya_existia=True`, **sin gastar cuota** |
| `POST /renovar/…` | `listo`; el visor pasó de expirar a las 09:35 a las 12:46 |
| `python resumen.py --lista` | Salida idéntica a antes: el CLI quedó intacto |
| `python resumen.py` sin argumentos | Código 2, como siempre |

### Una corrección al plan

El plan (§13) preveía `ideos == 176` pero lo justificaba con el dato equivocado de la
documentación (187). El valor real, leído de `resumen.json`, es **176 ideas y 20 avisos**.
La prueba fija esos números.

### Diferencia con lo planeado

`derivar_ubicacion()` no depende solo de la línea `  Clase: <ruta>`: si el CLI no la imprime
(caso de `--solo-visor` con la clase ya en disco), cae en `catalogo.buscar_por_url()`, que
busca por `recording_id`. Sin ese respaldo, el botón «Renovar video» no habría sabido a qué
clase redirigir.
