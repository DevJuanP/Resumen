# La huella

El mecanismo que evita pagar dos veces por la misma clase. Está en
`summarize.py → huella()` y en `cli.py`.

## El problema que resuelve

Resumir una clase cuesta 14 llamadas al modelo y entre 4 y 9 minutos. Sin control de
duplicados, cualquier despiste (volver a ejecutar el comando, regenerar el visor, un
script en bucle) volvería a pagar ese coste entero.

## Cómo se calcula

```python
def huella(clase: Clase) -> str:
    h = hashlib.sha1()
    for s in clase.segmentos:
        h.update(f"{s.segundos:.0f}{s.texto}".encode())
    return h.hexdigest()[:12]
```

Se recorre **cada segmento** y se le pasa al SHA-1 dos cosas:

| Dato | Ejemplo |
|---|---|
| `segundos` redondeado a entero | `1328` |
| `texto` | `es una metodología para ir desarrollando` |

Se concatenan tal cual (`1328es una metodología…`) y se trunca el hash a **12 caracteres
hexadecimales**.

Valor real de la clase de ejemplo: `989c82d1c017`.

## Por qué esos dos campos y no otros

- **`texto`**: si el docente corrige algo, o Zoom reprocesa la transcripción, el texto
  cambia y la huella cambia. El resumen se regenera, que es lo correcto.
- **`segundos`**: dos frases idénticas en momentos distintos son contenido distinto. Sin
  el tiempo, un cambio de minutaje pasaría inadvertido.
- **No se incluye el modelo ni la configuración**: si cambias de modelo, la huella sigue
  igual. Eso es deliberado — para forzar un reproceso con otro modelo está `--forzar`.

## Dónde se guarda

```json
// clases/DCGS12424-Pruebas-de-Software/.huellas.json
{
  "2026-11-03-PRUEBAS-DE-SOFTWARE.md": "989c82d1c017"
}
```

Un archivo por carpeta de curso. La clave es el **nombre del archivo `.md`**, no el título
de la clase.

## Cómo se usa

Dentro de `cli.main()`, antes de cargar el modelo:

```python
if destino.exists() and not args.forzar:
    if _huellas(carpeta).get(destino.name) == huella(clase):
        print("✓ Ya existe y está actualizado: …")
        return 0
```

Tres condiciones para omitir el trabajo:

1. El `.md` existe.
2. No se pasó `--forzar`.
3. La huella guardada coincide con la recién calculada.

Si las tres se cumplen, **no se llama al modelo** y el programa termina con código 0.

## La huella heredada

Al pasar de una carpeta plana a subcarpetas por curso, los `.huellas.json` antiguos
quedaron en la carpeta base. `_huellas()` los fusiona para no perder ese trabajo:

```python
def _huellas(carpeta: Path) -> dict:
    salida = {}
    heredado = carpeta.parent / ".huellas.json"   # formato antiguo
    actual = carpeta / ".huellas.json"            # formato nuevo
    for ruta in (heredado, actual):
        if ruta.is_file():
            salida.update(json.loads(...))
    return salida
```

Probado: tras mover los archivos a la subcarpeta, el programa siguió reconociendo la clase
como ya procesada en lugar de volver a resumirla.

## Qué NO detecta

Es importante saber dónde falla.

| Situación | ¿Detecta? | Por qué |
|---|---|---|
| Volver a ejecutar el mismo comando | Sí | Misma transcripción → misma huella |
| Regenerar tras caducar el video | Sí | Solo cambian las URLs, no la transcripción |
| La plataforma corrige la transcripción | Sí | El texto o los segundos cambian |
| Cambias de modelo | No | La huella no incluye el modelo |
| Cambias el prompt o el formato del `.md` | No | Idem. Hay que usar `--forzar` o `--rehacer` |
| Renombras el `.md` a mano | No | Se indexa por nombre de archivo |
| Borras `.huellas.json` | No | Vuelve a resumir |

Para los casos que no detecta, la solución es `--forzar` (reprocesa todo) o `--rehacer`
(solo re-renderiza desde el JSON, sin modelo).

## Comparación con alternativas

| Enfoque | Ventaja | Desventaja |
|---|---|---|
| **Huella del contenido** (el actual) | Detecta cambios reales en la transcripción | Requiere descargar la clase para calcularla |
| Comparar fecha de modificación | Trivial de implementar | Frágil: copiar el archivo cambia la fecha |
| Guardar el ID de la grabación | Sin descarga | No detecta reprocesos de la plataforma |

La huella obliga a descargar 1.48 MB antes de saber si hace falta resumir. Es el precio de
la precisión: es la única forma de detectar que la transcripción cambió de verdad.
