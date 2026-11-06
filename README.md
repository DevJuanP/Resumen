# Apuntes automáticos de clases

Convierte una repetición de clase de **Class** (class.com) en apuntes de estudio con
timestamps, para no ver los 136 minutos completos.

No descarga audio ni transcribe nada: la plataforma ya genera la transcripción con
nombre del hablante y minuto. La herramienta la reutiliza tal cual.

## Qué obtienes

Un `.md` por clase con:

- **Mapa de la clase** — tramos cronológicos con lo que pasa en cada uno.
- **Lo que importa** — los puntos clave ordenados por peso, no por tiempo.
- **Desarrollo completo** — todas las ideas, en orden de aparición, cada una con su minuto.
- **Glosario**, **ejemplos del docente** y **preguntas de tus compañeros**.
- **Pendientes y avisos** — fechas de examen, entregas, herramientas obligatorias.
- **Para investigar por tu cuenta** — temas que la clase menciona pero no desarrolla.
- **Lo que se omitió** — qué se descartó por relleno, para que confíes en el resto.
- **Anexo** — la transcripción íntegra, buscable.

Y un `.html` opcional: el video de la clase al lado de los apuntes. Haces clic en
cualquier `mm:ss` y el video salta a ese punto. Incluye búsqueda, checklist de temas
investigados y un mapa de densidad de la clase.

## Uso

```bash
# Apuntes en Markdown
python resumen.py "https://cibertec.class.com/player/recording/<clase>/<grabación>"

# Apuntes + visor con video
python resumen.py "<enlace>" --visor

# Guardar el JSON intermedio (permite re-renderizar sin volver a resumir)
python resumen.py "<enlace>" --crudo --visor
```

### Interfaz web (sin escribir comandos)

```bash
python web.py            # → http://127.0.0.1:8765
```

O doble clic en **`Iniciar web.bat`**. Desde ahí:

- **Generar resumen** — pegas el enlace y ves el progreso real (bloques 7/13, tiempo,
  fase). Al terminar aparecen «Abrir resumen» y «Descargar .md».
- **Ver** — abre el visor con el video de la clase.
- **Renovar video** — regenera los enlaces firmados (caducan a las 12 h). Tarda ~1 s y no
  gasta modelo.
- **Regenerar** — vuelve a resumir con el modelo (pide confirmación: cuesta 14 llamadas).

Es local: escucha solo en `127.0.0.1`, sin login, sin dependencias nuevas. Los comandos de
abajo siguen funcionando igual; la web los invoca como subproceso.

Si los enlaces del video caducaron (duran 12 horas), regenera solo el visor:

```bash
python resumen.py "<enlace>" --solo-visor   # no llama al modelo
python resumen.py "<enlace>" --rehacer      # re-renderiza .md y .html
```

Otras opciones: `--forzar` (regenerar), `--modelo` (cambiar de modelo),
`--texto archivo.txt` (usar una transcripción copiada del panel *Transcripción*),
`--curso CODIGO` (forzar el curso) y `--lista` (ver cursos y clases).

## Cómo funciona, paso a paso

Resumen del recorrido completo. El detalle está en
[docs/03-arquitectura/flujo.md](docs/03-arquitectura/flujo.md).

### Paso 1 — Obtener la clase (`fetch.py`)

No hay IA ni audio: son peticiones HTTP a Class.

1. De la URL se extraen dos UUID: el de la clase y el de la grabación.
2. Se lee `https://{host}/player/config.json` para descubrir la URL de la API.
3. Se pide la grabación con `POST …/v1_join_async_meeting` → **1.48 MB** de JSON.
4. Se normaliza: 1420 segmentos → 1419 (se descarta el aviso de grabación), se
   resuelve quién es docente, y **UTC se convierte a hora local**.

Resultado: un objeto `Clase` con 1419 `Segmento` (quién, qué, en qué segundo).

> **Sobre la URL:** hace falta pegarla a mano, sí, pero no por un token de sesión.
> La transcripción se obtiene **sin login ni cookies**; lo que caduca en 12 horas es
> el enlace firmado del **video**. Si `--visor` no lo regeneras, el video dejará de
> verse, pero los apuntes no.

### Paso 2 — ¿Ya está hecho? (`huella()`)

SHA-1 de 12 caracteres sobre `segundos + texto` de todos los segmentos. Se compara con
`.huellas.json` de la carpeta del curso. Si coincide, termina sin llamar al modelo.
Así puedes correr el comando dos veces sin pagar dos veces.

### Paso 3 — Partir en bloques (`dividir()`)

`BLOQUE_MIN = 12`, `SOLAPE_MIN = 1`. Los 13 bloques reales de una clase de 136 min:

```
[0,12] [11,23] [22,34] [33,45] [44,56] [55,67] [66,78]
[77,89] [88,100] [99,111] [110,122] [121,133] [132,135.9]
```

Se pisan un minuto a propósito: una idea que empieza en el minuto 11:50 no queda
cortada. El precio son duplicados que se limpian después.

### Paso 4 — Resumir cada bloque (`_analizar_bloque()`)

Tres hilos en paralelo (`MAX_HILOS = 3`), una llamada al modelo por bloque. Por eso el
contador de progreso salta desordenado.

El prompt exige: reconstruir el sentido de una transcripción sin puntuación, **no
inventar**, copiar el timestamp tal cual, resolver fechas relativas con la fecha de la
clase, y descartar relleno *solo* cuando hay certeza («es preferible una idea de más
que una de menos»).

Devuelve JSON con `ideas`, `terminos`, `avisos`, `ejemplos`, `preguntas`, `menciones`,
`relleno`.

`_normalizar_claves()` corrige variantes como `explicación` con tilde, que si no se
pierden en silencio.

### Paso 5 — Fusionar

| Función | Qué quita |
|---|---|
| `_fusionar` | Duplicados del solape (texto parecido + <90 s) |
| `_deduplicar_global` | Repetidos lejanos (solo texto) |
| `_consolidar_avisos` | Avisos con otra redacción (Jaccard + 40 s) |
| `_ajustar_tiempos` | Minutos inventados: los ancla al segmento real |

La ventana cambia por tipo: ideas 90 s, términos 300 s, avisos 600 s, menciones 900 s.

### Paso 6 — Auditoría

`_huecos()` busca tramos de **más de 8 minutos sin ninguna idea** y los reprocesa.
Distingue «aquí no se habló» de «aquí se habló y no se extrajo nada» exigiendo más de
1200 caracteres de texto. `_cobertura()` informa el porcentaje de tramos de 5 minutos
con al menos una idea (en la clase de ejemplo: 96.4 %, con 0 huecos).

### Paso 7 — Síntesis (la segunda pasada)

Un bloque de 12 minutos no puede saber qué importa en la clase entera. Por eso hay
**una llamada final** con todo lo fusionado, que produce:

- `mapa`: tramos que cubren la clase sin huecos
- `clave`: los puntos importantes **ordenados por peso, no por tiempo**
- `investigar`: temas para ampliar, con consulta de búsqueda
- `resumen`: 3-5 frases

### Paso 8 — Escribir

`render()` produce el `.md` y `generar()` el `.html`. El anexo con la transcripción
íntegra se incluye siempre: es la red de seguridad.

**Total: 14 llamadas al modelo (13 bloques + 1 síntesis).**

## Organización de las clases

Un curso tiene varias clases; cada clase es una carpeta con **un único resumen que se
actualiza al volver a ejecutar**.

```
clases/
  DCGS12424-Pruebas-de-Software/
    2026-11-03/
      resumen.md          ← los apuntes
      resumen.json        ← datos estructurados
      visor.html          ← visor con video
      clase.json          ← fecha, ids de Class, huella
      transcripcion.json  ← los 1419 segmentos
    2026-11-05/
      ...
  PROG04696-Desarrollo-de-Aplicaciones-Moviles-II/
  SPTI02423-Proyecto-Integrador/
```

La carpeta lleva la fecha de la clase. Si el mismo día hubiera dos grabaciones distintas,
la segunda añade la hora (`2026-11-03-2100`) para no pisar la anterior.

Los cursos se declaran en [`cursos.json`](cursos.json). Class **no** expone el código del
curso en la respuesta (solo el nombre de la materia), así que el curso se resuelve
buscando el nombre en `cursos.json`, o a mano con `--curso`.

### Actualizar un resumen

```bash
# Vuelve a resumir solo esa clase y sobrescribe su carpeta
python resumen.py "<enlace>" --forzar --visor

# Re-renderiza el .md y el visor SIN modelo y SIN red
python resumen.py "<enlace>" --rehacer

# Solo refresca los enlaces del video (caducan a las 12 h)
python resumen.py "<enlace>" --solo-visor
```

`--rehacer` y `--solo-visor` localizan la clase en disco por el identificador de la
grabación, así que funcionan **sin conexión** y tardan menos de un segundo.

Para ver el estado:

```bash
python resumen.py --lista
```

## Instalación

Solo Python 3.10+ y biblioteca estándar. No hay dependencias que instalar.

## Configuración del modelo

Crea `config.json` junto a `resumen.py`:

```json
{
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key_env": "OPENAI_API_KEY"
}
```

Cualquier endpoint compatible con la API de OpenAI sirve. Si no hay `config.json`,
se intenta leer el proveedor ya configurado en OpenCode
(`~/.config/opencode/opencode.jsonc`).

**Privacidad:** el audio nunca sale de tu equipo. Solo el texto de la transcripción
se envía al modelo. Esa transcripción contiene las voces de tus compañeros.

## Cómo evita perder contenido

Tres mecanismos, porque pediste que no se pierda nada importante:

1. La clase se parte en bloques de 12 minutos (con solape) y **cada bloque se
   analiza por separado**. Un bloque que se resuma mal no arrastra al resto.
2. Los duplicados del solape se fusionan comparando texto y cercanía temporal.
3. Una **auditoría final** busca tramos de más de 8 minutos sin ninguna idea
   extraída y los vuelve a procesar. La cobertura se imprime al terminar.

Además, cada `mm:ss` se ancla a una intervención real de la grabación: si el modelo
inventa un minuto, se corrige al más cercano.

## Coste y tiempo

Una clase de 136 minutos tarda entre 4 y 9 minutos (255–548 s en cuatro ejecuciones) y
14 llamadas al modelo (~20 000 tokens de entrada). Ejecutar dos veces la misma clase no
cuesta nada: se detecta por huella de la transcripción y se omite.

## Documentación

La documentación detallada está en [`docs/`](docs/README.md): uso, arquitectura, formato de
las salidas, verificación y limitaciones.

## Estructura

```
resumen.py              punto de entrada
web.py                  interfaz web local (python web.py)
web/                    servidor HTTP, catálogo, cola y estáticos
pruebas/                pruebas de la interfaz (unittest, sin red)
clase_resumen/
  fetch.py              descarga y normaliza la transcripción
  llm.py                cliente del modelo (compatible OpenAI)
  summarize.py          bloques, fusión, auditoría y render Markdown
  visor.py              visor HTML con video sincronizado
  cursos.py             registro de cursos y resolución de subcarpetas
  cli.py                línea de comandos
config.json             endpoint y modelo
cursos.json             los tres cursos y su carpeta
clases/                 salida, una subcarpeta por curso
docs/                   documentación detallada
```

## Limitaciones conocidas

- Solo funciona con repeticiones alojadas en Class. Para otras plataformas, usa
  `--texto` con la transcripción copiada.
- La transcripción automática confunde términos técnicos en inglés (JUnit, Mockito,
  TDD). El modelo los reconstruye por contexto, pero conviene verificar nombres
  propios y herramientas contra el video.
- Las fechas relativas ("el jueves") se resuelven con la fecha de la clase, ya
  convertida de UTC a tu hora local. Si tu zona horaria cambia, revisa los avisos.
