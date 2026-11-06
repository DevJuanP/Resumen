# Errores y solución

Mensajes reales del programa y su causa.

## Errores previos al modelo (código de salida 2)

### «indica el enlace de la repetición o usa --texto»

```
resumen: error: indica el enlace de la repetición o usa --texto
```

**Causa:** no se pasó ningún argumento.
**Solución:**

```bash
python resumen.py "<enlace>"
```

### «El enlace no parece una repetición de Class»

```
✗ El enlace no parece una repetición de Class.
Debe verse así: https://<tu-insti>.class.com/player/recording/<clase>/<grabación>
```

**Causa:** la URL no encaja con el patrón `PATRON_REPLAY`. Debe tener
`/player/recording/` seguido de dos UUID de 36 caracteres.

Variantes que fallan:

| URL | Por qué falla |
|---|---|
| `https://cibertec.class.com/ics/meeting/95682...` | Es la sala en vivo, no la repetición |
| `https://cibertec.class.com/player/recording/abc/def` | `abc` y `def` no son UUID |
| Un enlace de Zoom sin pasar por Class | Es otra plataforma |

**Solución:** abre la repetición en el navegador y copia la URL completa, que debe tener dos
UUID.

### «No se pudo leer la configuración del reproductor»

```
✗ No se pudo leer la configuración del reproductor en https://{host}/player/config.json
```

**Causas posibles:**

1. El subdominio de la institución cambió.
2. El reproductor está detrás de autenticación que este equipo no tiene.
3. No hay conexión a internet.

**Comprobación manual:**

```bash
curl https://{host}/player/config.json
```

Debe devolver un JSON con una clave `api`.

### «La plataforma respondió N»

```
✗ La plataforma respondió 403 en https://...
```

| Código | Causa probable |
|---|---|
| 401, 403 | La grabación requiere sesión que este método no tiene |
| 404 | El identificador no existe o la grabación se borró |
| 500 | Fallo del lado de la plataforma |

**Solución:** comprueba que el enlace abre en el navegador. Si abre pero el programa falla,
la plataforma puede haber cambiado el permiso de acceso a la API.

### «La grabación existe pero todavía no tiene transcripción publicada»

```
✗ La grabación existe pero todavía no tiene transcripción publicada.
Suele tardar unas horas después de la clase; vuelve a intentarlo más tarde.
```

**Causa:** Zoom aún está procesando la transcripción automática. También aparece si el
docente desactivó la transcripción para esa sesión.

**Solución:** esperar. Si tras 24 horas sigue igual, es que esa grabación no tiene
transcripción.

### «No se reconoció ninguna intervención en {archivo}»

**Causa:** el archivo de `--texto` no tiene el formato esperado.

Formatos válidos:

```
NOMBRE DEL HABLANTE   07:01:11 p. m.
Texto de lo que dijo.
```

```
[03:15] Nombre: texto en la misma línea
```

**Solución:** copia el panel «Transcripción» completo. El nombre y la hora deben ir en la
misma línea, separados por espacios.

### «No hay ningún modelo configurado»

```
✗ No hay ningún modelo configurado.
Crea config.json junto a resumen.py con este contenido:
{
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key_env": "OPENAI_API_KEY"
}
```

**Causa:** fallaron las cuatro vías de resolución: `config.json`, la coincidencia con
OpenCode, las variables `RESUMEN_*` y la detección automática.

**Solución:** crea el `config.json`. Ver [instalación](../02-uso/instalacion.md).

### «No hay JSON guardado»

```
✗ No hay JSON guardado en ...\clases\2026-11-03-PRUEBAS-DE-SOFTWARE.json
  Genera primero los apuntes con --crudo.
```

**Causa:** usaste `--rehacer` o `--solo-visor` sin haber generado nunca el `.json`.

**Solución:** ejecuta una vez con `--crudo`:

```bash
python resumen.py "<enlace>" --crudo --visor
```

## Errores del modelo (código de salida 3)

### «El modelo rechazó la petición (N)»

```
✗ El modelo rechazó la petición (401).
{"error":{"message":"Incorrect API key provided..."}}
```

| Código | Causa |
|---|---|
| 401 | Clave incorrecta o ausente |
| 403 | Clave sin permiso para ese modelo |
| 404 | El modelo no existe en ese endpoint |
| 400 | Parámetro inválido, a menudo `reasoning_effort` no soportado |

Este error **no se reintenta**: es definitivo.

### «No active plan was found» / «insufficient credits»

```
{"error":{"message":"No active plan was found on this account ... wallet balance can't cover this model"}}
```

**Causa:** el proveedor no tiene saldo o plan activo.

**Solución:** recargar, o cambiar de proveedor editando `config.json` o usando `--modelo`.

> Ocurrió realmente durante el desarrollo con dos proveedores distintos.

### Respuestas vacías

```
✗ El modelo devolvió una respuesta vacía.
```

**Causa más probable:** el modelo gasta todo el presupuesto de tokens en razonamiento interno.

**Comprobación:**

```bash
# el campo usage lo delata
# "completion_tokens_details": {"reasoning_tokens": 6000}
# "content": ""
```

**Solución:** `completar()` ya lo detecta y sube `max_tokens` a 8000 en el primer reintento.
Si persiste, cambia a un modelo que no razone o añade `"reasoning_effort": "low"` al
`config.json`.

### «El modelo no devolvió JSON válido»

```
✗ El modelo no devolvió JSON válido:
{ "ideas": [ ...
```

**Causa:** la respuesta no se pudo parsear ni siquiera con las tres estrategias de
`_extraer_json()`.

**Solución:** reintentar. Si es sistemático, el modelo no respeta el formato; prueba otro.

### «Sin respuesta del modelo»

```
✗ Sin respuesta del modelo: timed out
```

**Causa:** timeout de red. Se reintenta hasta 4 veces con espera exponencial.

**Solución:** si persiste, comprueba la conexión o el estado del proveedor.

## Problemas sin mensaje de error

### El visor abre pero el video está en negro

**Causa:** las URLs firmadas caducaron (12 h).

**Solución:**

```bash
python resumen.py "<enlace>" --solo-visor
```

### El video se corta o carga lento

**Causa:** está haciendo streaming desde CloudFront, no reproducción local. La pista de
diapositivas pesa 146.7 MB.

**Solución:** cambiar a la pista «Docente» (115.6 MB) o esperar a que cargue.

### La fecha de la clase está mal

Verifica primero si es problema de zona horaria. El código convierte con
`.astimezone()`, que usa la zona del sistema. Si tu equipo está en otra zona que la clase,
la fecha puede desplazarse un día.

**Solución:** fijar la zona horaria del sistema, o cambiar a
`ZoneInfo("America/Lima")` en `fetch._fecha()` (no implementado).

### No se puede regenerar el visor porque perdí el enlace

**Causa:** el `.json` guardado no incluye `school_id`, `class_uuid` ni `recording_id`.

**Solución:** buscar el enlace en el historial del navegador o en la plataforma. Ver
[mejoras propuestas](../08-futuro/mejoras-propuestas.md) para la corrección de fondo.

### El contador de bloques salta de 3 a 7

**No es un error.** Hay 3 hilos trabajando y el contador refleja el orden en que terminan,
no el orden de los bloques.

### «Ya existe y está actualizado» pero quiero regenerar

**Solución:** añadir `--forzar`.

## Cómo diagnosticar sin el mensaje

```bash
# ¿Se descarga la transcripción?
python -c "from clase_resumen.fetch import obtener_clase; c=obtener_clase('URL'); print(len(c.segmentos), round(c.duracion_s/60), c.materia, c.docente)"

# ¿Se resuelve el modelo?
python -c "from clase_resumen.llm import cargar; m=cargar(); print(m.etiqueta, m.extra)"

# ¿Qué se guardó?
python -c "import json; d=json.load(open('clases/ARCHIVO.json',encoding='utf-8')); print({k: (len(v) if isinstance(v,list) else 'txt') for k,v in d['fusion'].items()}); print('cobertura', d['cobertura'], 'revisados', d['revisados'])"
```
