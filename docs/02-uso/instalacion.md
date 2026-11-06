# Instalación y configuración

## Requisitos

| Requisito | Detalle |
|---|---|
| Python | 3.10 o superior (el código usa `X \| None` y `datetime.UTC`) |
| Probado con | Python 3.12.10 en Windows 11 |
| Dependencias | Ninguna. Solo biblioteca estándar |
| Conexión | Necesaria para Class y para el proveedor del modelo |

No hay `requirements.txt` ni `pyproject.toml`. No hace falta crear un entorno virtual,
aunque nada impide hacerlo.

## Comprobar que funciona

```bash
python resumen.py --help
```

Debe imprimir el uso con las nueve opciones (más `-h`, `--help`). Si eso funciona, el
código está bien instalado.

## Configurar el modelo

El proyecto necesita un endpoint **compatible con la API de OpenAI**
(`POST {base_url}/chat/completions`).

Crea `config.json` en la raíz del proyecto, junto a `resumen.py`:

```json
{
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key_env": "OPENAI_API_KEY"
}
```

### Campos aceptados en `config.json`

| Campo | Obligatorio | Para qué |
|---|---|---|
| `base_url` | Sí | Raíz de la API, sin `/chat/completions` |
| `model` | Sí | Identificador del modelo |
| `api_key` | No | Clave escrita directamente (menos seguro) |
| `api_key_env` | No | Nombre de la variable de entorno que contiene la clave |
| `reasoning_effort` | No | Se pasa al modelo como `reasoning_effort` (útil en modelos que razonan) |
| `extra` | No | Objeto con parámetros adicionales que se envían tal cual al modelo |
| `_nota` | No | Campo ignorado; se usa como comentario |

### Orden de resolución

`clase_resumen/llm.py → cargar()` intenta, en este orden:

1. `config.json` del proyecto.
2. Si `config.json` existe pero no tiene clave, se reutiliza la clave del proveedor
   configurado en OpenCode **solo si el `base_url` coincide exactamente**. Si no coincide,
   no se usa, para no mandar una clave a un endpoint equivocado.
3. Variables de entorno `RESUMEN_BASE_URL`, `RESUMEN_MODEL` y `RESUMEN_API_KEY` (las tres
   a la vez).
4. El primer proveedor OpenAI-compatible con `baseURL` y `apiKey` que aparezca en
   `~/.config/opencode/opencode.jsonc`.

Si nada de eso funciona, el programa termina con código 2 y un mensaje que muestra un
`config.json` de ejemplo.

### Configuración actual del proyecto

El `config.json` que hay en el repositorio apunta a:

```json
{
  "base_url": "https://api-cdn.thehive.ai/api/v3",
  "model": "zai-org/glm-5.3-flash",
  "reasoning_effort": "low"
}
```

No incluye `api_key`: la clave se toma del proveedor `hive-ai` configurado en OpenCode,
porque el `base_url` coincide.

> **Nota real de la puesta en marcha.** Con otro modelo del mismo proveedor
> (`deepseek-v4.1-flash-1017`) el resultado fueron respuestas vacías: gastaba los 12 000
> tokens de presupuesto en razonamiento interno y no escribía contenido. Con
> `glm-5.3-flash` y `reasoning_effort: low` funciona de forma consistente. Si cambias de
> modelo y obtienes texto vacío, revisa su consumo de razonamiento.

## Variables de entorno opcionales

| Variable | Efecto |
|---|---|
| `RESUMEN_BASE_URL` | Endpoint del modelo (alternativa a `config.json`) |
| `RESUMEN_MODEL` | Modelo a usar |
| `RESUMEN_API_KEY` | Clave del modelo |
| `RESUMEN_USER_UUID` | Identificador enviado a Class, si quieres fijar uno propio |

## Archivos que se crean solos

| Archivo | Cuándo | Contenido |
|---|---|---|
| `.uuid` | Al primer acceso a Class | UUID anónimo estable, para no generar uno nuevo en cada petición |
| `clases/.huellas.json` | Al terminar una clase | Huella SHA-1 por archivo, para detectar si ya está procesado |

Ambos están en `.gitignore`.
