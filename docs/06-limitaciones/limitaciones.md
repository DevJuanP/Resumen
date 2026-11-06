# Limitaciones

Lo que el proyecto no hace o no garantiza. Escrito para que no te lleves sorpresas al
retomarlo.

## Limitaciones funcionales

### Una clase por ejecución

```bash
python resumen.py "<url1>" "<url2>"   # NO funciona
```

El argumento `url` es posicional y único. Procesar cinco clases significa escribir cinco
comandos. No hay procesamiento por lotes ni cola.

### No descubre clases

No hay ninguna función que consulte qué grabaciones existen en la plataforma. Hay que copiar
el enlace de cada repetición a mano.

### Solo Class

El extractor depende de:

- La ruta `/player/recording/{uuid}/{uuid}`
- El endpoint `v1_join_async_meeting`
- La estructura `recordingData.transcripts`

Cualquier otra plataforma requiere `--texto` con la transcripción copiada.

### El video no queda guardado

El `.html` es inservible para el video pasadas 12 horas. Los apuntes en `.md` no caducan.

### No analiza las diapositivas

El video de `shared_screen` se puede ver, pero su contenido **no se lee**. Si el docente
explica una fórmula solo en la pizarra y no la dice en voz alta, se pierde.

### El chat no se usa

Los 71 mensajes del chat se guardan en `Clase.chats` y ahí se quedan. Las preguntas de
compañeros salen únicamente de la transcripción de audio, así que las que se escribieron en
el chat no aparecen.

### Los timestamps son del inicio de la intervención

Cada idea apunta al momento en que el docente **empieza** a decir algo, no al momento exacto
en que dice la frase concreta. Como la transcripción segmenta cada 4-8 segundos, la
imprecisión es de ese orden.

## Limitaciones de calidad

### La transcripción viene con errores

Es automática y de Zoom. Errores observados en la clase real:

| Transcripción | Lo que era |
|---|---|
| «programación con TD» | TDD |
| «juez vamos a instalar la herramienta» | «el jueves vamos a instalar» |
| «moquito» | Mockito |
| «el correo» | «el código» |
| «Blackboard» | (correcto, pero podría confundirse) |

El modelo reconstruye mucho por contexto, pero los nombres propios y las herramientas en
inglés son frágiles. En la clase documentada aparece «Mike Cohn (?)» con la marca de duda,
que es el comportamiento deseado: señala la incertidumbre en vez de inventar.

### Las fechas son inferencias

El docente dice «el jueves», no una fecha. El modelo calcula la fecha a partir de la fecha de
la clase. Se comprobó que las de la clase documentada son coherentes, pero **conviene
verificar cualquier fecha de examen en el sílabo**.

### El peso es un juicio, no una métrica

`alto`/`medio`/`bajo` lo decide el modelo leyendo la transcripción. No hay puntuación
numérica ni frecuencia de menciones. Ver
[cómo leer los apuntes](../02-uso/interpretar-apuntes.md).

### La cobertura mide presencia, no corrección

96.4 % significa que el 96.4 % de los tramos de 5 minutos tiene al menos una idea asociada.
No significa que esas ideas sean correctas ni completas.

### Puede haber pérdida sutil

La auditoría detecta tramos **sin ninguna idea**. Un tramo con una idea mala pero presente no
se detecta. El anexo con la transcripción íntegra es la única garantía real.

## Limitaciones técnicas

### Sin caché de transcripciones

Cada ejecución vuelve a descargar 1.48 MB de la plataforma, incluso con `--solo-visor`. No se
guarda el JSON crudo de Class, solo el procesado.

### Sin tests automatizados

No hay ni un archivo de test. Toda la verificación fue manual. Ver
[verificación](../05-pruebas/verificacion.md).

### El estado vive en archivos sueltos

- `.uuid` — identidad anónima
- `clases/.huellas.json` — control de duplicados

Si compartes el proyecto o lo mueves, `.uuid` se regenera y `.huellas.json` puede quedar con
entradas obsoletas (de hecho, en este repositorio hay una entrada de
`2026-11-04-PRUEBAS-DE-SOFTWARE.md` de antes de corregir la zona horaria; no rompe nada).

### La huella es frágil al renombrar

Se calcula sobre la transcripción, no sobre el nombre. Pero se indexa por **nombre de
archivo**. Si renombras un `.md`, la próxima vez se vuelve a procesar.

### `MAX_HILOS = 3` es fijo

No se puede configurar. Con clases muy largas el tiempo crece linealmente en grupos de tres.

### El modelo se configura con una clave en texto plano si usas `api_key`

El `config.json` actual no la incluye (usa la de OpenCode), pero el código acepta `api_key`
en claro. Es una comodidad con riesgo: ese archivo no debería subirse a un repositorio
público.

### `--texto` no detecta roles

Todos los segmentos quedan como `estudiante`, no hay docente y no hay video. El resumen
funciona; el visor sale sin reproductor.

## Limitaciones de entorno

| Aspecto | Estado |
|---|---|
| Windows | Probado |
| Linux / macOS | No probado. No hay nada específico de Windows salvo el chequeo de color ANSI |
| Python < 3.10 | No funciona (`datetime.UTC`, uniones `X \| None`) |
| Sin internet | No funciona, ni siquiera con `--rehacer` (necesita la transcripción) |

## Lo que sí puedes dar por seguro

Para no quedarte solo con lo negativo:

- La transcripción completa se conserva en el `.md` y en el `.html`.
- La fecha se convierte correctamente a hora local.
- Los minutos del resumen existen en la grabación.
- Regenerar el visor no cuesta llamadas al modelo.
- Si el modelo falla, se reintenta hasta 4 veces.
- Si el video no está disponible, el visor sigue siendo útil.
