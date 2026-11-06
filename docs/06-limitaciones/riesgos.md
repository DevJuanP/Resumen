# Riesgos

Decisiones que implican un riesgo, con su impacto real.

## 1. Privacidad: la transcripción sale del equipo

### Qué se envía

El texto completo de la transcripción al proveedor del modelo configurado. En la clase
documentada son 78 000 caracteres que incluyen:

- Lo que dice el docente.
- Lo que dicen tus compañeros.
- Nombres completos de los participantes.

### Qué NO se envía

- Audio.
- Video.
- Imágenes.
- Credenciales de la plataforma.

### Riesgo real

Ese texto contiene conversaciones de terceros que no dieron permiso para que un modelo de
lenguaje las procese. En el caso de la clase documentada, el propio docente menciona nombres
de estudiantes al pasar lista y comenta sobre ellos.

### Opciones

| Opción | Efecto |
|---|---|
| Usar un modelo local | Nada sale del equipo. Requiere hardware y el resumen baja de calidad |
| Aceptar el riesgo | Es lo que hace hoy el proyecto |
| Anonimizar antes de enviar | **No implementado.** Sería un paso de sustitución de nombres por `PERSONA_1`, etc. |

## 2. El `.uuid` identifica tu equipo ante la plataforma

### Qué es

Un UUID v4 aleatorio que se envía en la cabecera `user_uuid` en cada petición a Class. Se
guarda en `.uuid` y se reutiliza siempre.

### Riesgo

No está vinculado a tu cuenta ni a tu nombre, pero es **estable**: la plataforma puede
correlacionar todas tus consultas de grabaciones como provenientes del mismo cliente.

### Opciones

| Opción | Efecto |
|---|---|
| Dejarlo | Es lo que hace hoy |
| Borrar `.uuid` | Se genera uno nuevo en la siguiente ejecución |
| Definir `RESUMEN_USER_UUID` | Control manual del identificador |

## 3. Los enlaces del video caducan

### Qué pasa

Las URLs firmadas de CloudFront tienen `timeToLive: 43200` (12 horas). Pasado ese tiempo:

- El `.html` abre correctamente.
- Los apuntes, el mapa y la búsqueda funcionan.
- El reproductor queda en negro.

### Por qué no es grave

Regenerar cuesta cero llamadas al modelo:

```bash
python resumen.py "<enlace>" --solo-visor
```

### Lo que sí es una molestia

Necesitas **el enlace original**. Si perdiste la URL de la repetición, el `.json` no contiene
lo suficiente para regenerar el visor: le falta `school_id` y la relación con la plataforma.
Esta es una limitación real del diseño actual.

> **Sugerencia no implementada:** guardar `school_id`, `class_uuid` y `recording_id` dentro
> del JSON para poder regenerar sin el enlace. Ver
> [mejoras](../08-futuro/mejoras-propuestas.md).

## 4. Dependencia de una API no documentada

### Qué se usa

- `GET /player/config.json`
- `POST /meeting/{id}/v1_join_async_meeting`
- `GET /recording/v1/schools/{id}/class/{id}/recordings/{id}/artifacts`

Ninguno de estos endpoints es público ni está documentado por Class. Se descubrieron
inspeccionando el reproductor.

### Riesgo

Si Class cambia la estructura de la respuesta o renombra un endpoint, el proyecto deja de
funcionar sin aviso. El código no tiene ninguna comprobación de versión.

### Mitigación actual

Los errores son explícitos: si `recordingData.transcripts` no existe, el mensaje dice «La
grabación existe pero todavía no tiene transcripción publicada», que también cubre el caso
de un cambio de esquema.

## 5. Dependencia del proveedor del modelo

### Qué se usa

Un endpoint compatible con OpenAI. Hoy apunta a `api-cdn.thehive.ai`.

### Riesgos observados

- **Saldo.** Durante el desarrollo, la clave de OpenAI del entorno no tenía créditos y la de
  tokenharbor no tenía saldo. El proyecto solo funcionó con el proveedor de OpenCode.
- **Modelos que razonan.** `deepseek-v4.1-flash-1017` devolvía respuestas vacías por gastar
  el presupuesto en razonamiento interno.
- **Cambios de catálogo.** Los modelos disponibles cambian; el que hoy funciona puede
  desaparecer.

### Mitigación

| Mecanismo | Dónde |
|---|---|
| Reintentos con espera exponencial | `llm.completar()` |
| Aumento de `max_tokens` si detecta razonamiento | `llm.completar()` |
| Cambio de modelo sin editar código | `--modelo` |
| Re-renderizar sin modelo | `--rehacer` |

El último es el más importante: si cambias de proveedor, el trabajo ya hecho no se pierde.

## 6. Coste por clase

### Estimación real

| Concepto | Valor |
|---|---|
| Llamadas | 13 |
| Tokens de entrada | ~20 000 |
| Tokens de salida | Variable, hasta 12 000 por llamada |

No se midió el coste monetario porque se ejecutó sobre una suscripción, no por token. Para
dimensionarlo: una clase son unas 13 peticiones con prompts de ~3 000 tokens cada una.

### Riesgo

Reprocesar por error cuesta dinero. La huella lo evita, pero `--forzar` lo salta. Y en los
cuatro ciclos de desarrollo de este proyecto se reprocesó la misma clase cuatro veces.

## 7. Riesgo académico

### Qué contiene el `.md`

Apuntes generados por un modelo, sin revisión humana.

### Riesgo

Si el resumen interpreta mal una definición y estudias de ahí, el error se propaga. Ejemplo
real de la clase documentada: «Mike Cohn (?)» con marca de duda es correcto, pero otras
afirmaciones van sin marca.

### Mitigación disponible

- El anexo con la transcripción completa.
- El minuto en cada idea, para verificar en el video.
- La sección «Lo que se omitió», para saber qué no está.
