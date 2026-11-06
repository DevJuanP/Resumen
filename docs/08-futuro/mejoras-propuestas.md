# Mejoras propuestas

Ideas **no implementadas**. Cada una indica qué problema resuelve, qué tan cara es y qué
archivos tocaría. Nada de esto está hecho.

Ordenadas por relación entre utilidad y esfuerzo.

---

## 1. Guardar los identificadores en el JSON

### Problema

Hoy no puedes regenerar el visor si perdiste el enlace de la repetición, porque el `.json`
solo guarda `url`, y regenerar exige volver a llamar a `obtener_clase()`.

### Propuesta

Añadir al JSON de la clase:

```json
"clase": {
  "materia": "...",
  "cuando": "...",
  "url": "...",
  "duracion_s": 8164.0,
  "school_id": "9c635e8a-...",
  "class_uuid": "f389df80-...",
  "recording_id": "12227799-...",
  "api_base": "https://cibertec.rest..."
}
```

Y una función `clase_desde_json()` en `fetch.py` que reconstruya un `Clase` a partir de esos
datos más los segmentos, que también habría que guardar.

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Baja |
| Archivos | `cli.py`, `fetch.py`, `summarize.py` |
| Tamaño del JSON | Crecería de 108 KB a ~600 KB si se guardan los 1419 segmentos |

Es la mejora con mejor relación utilidad/esfuerzo.

---

## 2. Guardar la transcripción en caché

### Problema

Cada ejecución con `--solo-visor` vuelve a descargar 1.48 MB de Class, aunque ya tengas todo
procesado.

### Propuesta

Guardar `clase.segmentos` en un archivo aparte (`<nombre>.transcript.json`) y reutilizarlo
cuando exista, con una opción `--offline` que nunca toque la red salvo para el video.

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Baja |
| Archivos | `fetch.py`, `cli.py` |
| Disk | ~500 KB por clase |

Depende de la mejora 1.

---

## 3. Descargar el video una vez

### Problema

El visor deja de tener video a las 12 horas.

### Propuesta

Opción `--descargar-video` que guarde el MP4 y apunte el HTML a una ruta local.

```bash
python resumen.py "<enlace>" --descargar-video
```

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Media (descarga por rangos con progreso) |
| Disk | 115 MB (solo docente) o 262 MB (ambas pistas) por clase |
| Archivos | `fetch.py`, `visor.py`, `cli.py` |

Discutido con el autor: 20 clases serían ~5 GB. Una variante razonable es descargar solo
`active_speaker` y borrarlo cuando ya no se necesite.

---

## 4. Procesar varias clases a la vez

### Problema

Una URL por ejecución.

### Propuesta

```bash
python resumen.py --lote clases.txt
```

Donde `clases.txt` tiene una URL por línea. Reutilizaría la misma lógica de `main()` en un
bucle, con un resumen final.

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Baja |
| Archivos | `cli.py` |
| Cuidado | El paralelismo por clase multiplicaría las llamadas simultáneas al modelo |

---

## 5. Usar el chat de la clase

### Problema

Los 71 mensajes del chat se guardan y no se usan. Muchas preguntas de compañeros se escriben
ahí, no las dicen en voz alta.

### Propuesta

Pasar los chats al prompt de síntesis para enriquecer `preguntas`, o añadir una sección
«Del chat».

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Baja |
| Archivos | `summarize.py` (prompt y render), `visor.py` |
| Riesgo | Aumenta el tamaño del prompt de síntesis |

---

## 6. Anonimizar antes de enviar

### Problema

La transcripción completa, con nombres de compañeros, va al proveedor del modelo.

### Propuesta

Sustituir nombres propios por marcadores antes de llamar al modelo y restaurarlos al
renderizar.

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Media-alta |
| Problema real | Reconocer nombres sin listas externas es difícil; los nombres peruanos compuestos complican más el proceso |

---

## 7. Exportar a otras herramientas

### Problema

Hoy solo hay Markdown, HTML y JSON.

### Propuesta

| Formato | Utilidad |
|---|---|
| Anki (CSV o `.apkg`) | Repaso espaciado de las 176 ideas |
| PDF | Imprimir o leer en el móvil |
| Obsidian | Ya funciona: basta abrir `clases/` como bóveda |
| Notion | Requiere API y token |

### Coste

| Formato | Dificultad |
|---|---|
| Anki CSV | Baja: las ideas ya tienen pregunta y respuesta potenciales |
| PDF | Media: requiere dependencia externa |
| Notion | Media: requiere credenciales |

---

## 8. Tests automatizados

### Problema

Cero tests. Toda la verificación fue manual y se documentó en
[verificación](../05-pruebas/verificacion.md).

### Propuesta

Casos que valdría la pena fijar:

| Función | Caso |
|---|---|
| `_normalizar_nombre()` | Los 7 casos de la documentación |
| `_seg()` | `"111:49"` → `6710` |
| `dividir()` | 136 min → 13 bloques con los rangos exactos |
| `_parecido()` | Umbrales 0.78 y 0.82 |
| `_extraer_json()` | JSON con cercas, JSON sucio, JSON truncado |
| `_fecha()` | UTC → local |
| `_ajustar_tiempos()` | Minuto fuera de rango |

Y un fixture con una transcripción pequeña en `tests/`.

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Baja |
| Archivos nuevos | `tests/test_summarize.py`, `tests/test_fetch.py`, `tests/fixtures/` |

---

## 9. Interfaz gráfica o página de historial

### Problema

Hoy hay que escribir un comando por clase.

### Propuesta

Un `index.html` en `clases/` que liste todas las clases procesadas, leídas de los `.json`.
Clic en una y abre su visor.

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Baja |
| Archivos | `visor.py` (función nueva) |
| Ventaja | No requiere modelo ni servidor |

Combinado con la mejora 1, permitiría tener un archivo por clase siempre disponible.

---

## 10. Detectar clases nuevas

### Problema

No hay forma de saber si hay una repetición nueva sin entrar a la plataforma.

### Propuesta

Revisar periódicamente la plataforma y procesar lo que falte.

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Alta |
| Bloqueo real | Requiere un endpoint que liste las grabaciones de un curso. **No se comprobó que exista ni cómo autenticarse** |

Es la única propuesta que podría no ser viable: el método actual funciona sin login, pero
listar grabaciones probablemente sí lo requiera.

---

## 11. Corregir la transcripción contra el audio

### Problema

«moquito» en vez de Mockito, «TD» en vez de TDD.

### Propuesta

Usar el VTT de subtítulos, que ya está disponible como artefacto, para contrastar.

### Coste

| Aspecto | Estimación |
|---|---|
| Dificultad | Media |
| Problema | El VTT viene del mismo motor de Zoom, así que probablemente tenga los mismos errores. Solo serviría para detectar discrepancias, no para corregirlas |

**Probablemente no vale la pena.** Se documenta para no repetir el análisis.

---

## Prioridad sugerida

Si retomas el proyecto con poco tiempo:

1. **Mejora 1** (guardar identificadores): resuelve un bloqueo real.
2. **Mejora 5** (usar el chat): datos que ya están descargados y se tiran.
3. **Mejora 8** (tests): barato y evita romper lo que funciona.
4. **Mejora 3** (descargar video): solo si el disco no es problema.
5. **Mejora 4** (lote): cuando ya tengas varias clases acumuladas.
