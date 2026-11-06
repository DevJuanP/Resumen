# Comandos

Todas las opciones listadas existen en `clase_resumen/cli.py` y se probaron ejecutando el
programa.

## Dónde se guarda cada clase

Un curso tiene varias clases. Cada clase es **una carpeta** con su resumen:

```
clases/
  DCGS12424-Pruebas-de-Software/
    2026-11-03/
      resumen.md  resumen.json  visor.html  clase.json  transcripcion.json
    2026-11-05/
```

El curso se resuelve con el nombre de la materia buscando en `cursos.json`. Si la materia
no coincide con ningún alias, el programa falla y muestra los cursos disponibles; ahí se
puede forzar con `--curso`.

La carpeta se nombra con la fecha de la clase. Dos grabaciones el mismo día no se pisan:
la segunda añade la hora.

```bash
# Ver cursos y clases
python resumen.py --lista

# Forzar el curso (admite prefijos: dcgs)
python resumen.py "<enlace>" --curso DCGS12424
```

## Uso básico

```bash
python resumen.py "<enlace de la repetición>"
```

Descarga la transcripción, resume y escribe
`clases/<CODIGO-CURSO>/<fecha>-<MATERIA>.md`.

## Con visor HTML

```bash
python resumen.py "<enlace>" --visor
```

Añade `clases/<fecha>-<MATERIA>.html` con el video al lado de los apuntes.

## Guardando el JSON intermedio

```bash
python resumen.py "<enlace>" --crudo --visor
```

`--crudo` es lo que permite después usar `--rehacer` y `--solo-visor` sin volver a llamar
al modelo. **Si no guardas el JSON, esas dos opciones no sirven** y el programa termina con
código 2.

## Regenerar sin gastar modelo

Los enlaces de video que Class entrega caducan a las 12 horas. Cuando el visor se queda sin
video:

```bash
# Solo el HTML (mantiene el .md como está)
python resumen.py "<enlace>" --solo-visor

# El HTML y también el Markdown (útil si cambió el formato de los apuntes)
python resumen.py "<enlace>" --rehacer
```

Ninguna de las dos llama al modelo. Ambas vuelven a pedir la transcripción a Class, porque
necesitan la duración y los minutos para reconstruir el índice del visor.

## Todas las opciones

| Opción | Valor | Qué hace |
|---|---|---|
| `url` | enlace | Posicional. Enlace de la repetición en Class |
| `--texto` | archivo | Usa una transcripción pegada a mano en vez de un enlace |
| `--materia` | texto | Nombre de la asignatura cuando se usa `--texto`. Por defecto `Clase` |
| `--salida` | carpeta | Carpeta base de los cursos. Por defecto `clases/` |
| `--curso` | código | Fuerza el curso (`SPTI02423`, `DCGS12424`, `PROG04696`). Admite prefijos |
| `--lista` | — | Lista los cursos y sus resúmenes, del más reciente al más antiguo |
| `--forzar` | — | Regenera aunque la huella indique que ya está hecho |
| `--modelo` | texto | Sobrescribe el modelo de `config.json` |
| `--crudo` | — | Guarda además el JSON extraído |
| `--visor` | — | Genera además el HTML |
| `--solo-visor` | — | Regenera solo el HTML desde el JSON guardado |
| `--rehacer` | — | Regenera el `.md` y el `.html` desde el JSON guardado |
| `-h`, `--help` | — | Ayuda |

## Combinaciones que importan

### `--texto` no admite `--visor` con video

Cuando usas `--texto`, el objeto `Clase` se construye sin `api_base` ni `school_id`, así que
`urls_de_video()` devuelve un diccionario vacío y el HTML sale con un aviso en lugar del
reproductor. El `.md` funciona con normalidad.

```bash
python resumen.py --texto transcripcion.txt --materia "PRUEBAS DE SOFTWARE" --visor
```

### `--forzar` con `--visor`

`--forzar` vuelve a resumir **y** regenera el visor. Es lo que se usó para la ejecución
final de la clase documentada.

### Segunda pasada sobre la misma clase

Si la huella coincide, el programa imprime:

```
✓ Ya existe y está actualizado: ...\clases\2026-11-03-PRUEBAS-DE-SOFTWARE.md
```

y no llama al modelo. Si además pasas `--visor` y existe el `.json`, regenera el HTML con
enlaces nuevos. Verificado.

## Códigos de salida

| Código | Significado | Cuándo |
|---|---|---|
| `0` | Éxito | Incluye el caso «ya existe y está actualizado» |
| `2` | Error previo al modelo | Enlace inválido, sin argumentos, JSON ausente, modelo no configurado, grabación sin transcripción |
| `3` | Error del modelo | Fallo persistente tras reintentos, o JSON inválido devuelto por el modelo |

Comprobado ejecutando los tres casos.

## Formato del mensaje de progreso

```
  PRUEBAS DE SOFTWARE · 03/11/2026 · 136 min · 1419 intervenciones
Resumiendo con zai-org/glm-5.3-flash @ api-cdn.thehive.ai/api/v3…
  bloques 7/13
✓ D:\...\clases\2026-11-03-PRUEBAS-DE-SOFTWARE.md
  30540 palabras · 255 s · cobertura 96.4%
```

El contador `bloques N/M` avanza según terminan los bloques en paralelo, así que **no sale
en orden**. Es normal: hay 3 hilos trabajando a la vez.

## Ayuda integrada

```
usage: resumen [-h] [--texto ARCHIVO] [--materia MATERIA] [--salida SALIDA]
               [--forzar] [--modelo MODELO] [--crudo] [--visor] [--solo-visor]
               [--rehacer]
               [url]
```
