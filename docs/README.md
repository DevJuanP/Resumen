# Documentación del proyecto

Este directorio documenta **lo que el proyecto hace hoy**, verificado ejecutándolo.
Cuando algo es una sugerencia y no una función existente, está marcado como tal.

## Estado actual

| Dato | Valor |
|---|---|
| Versión del paquete | `1.0.0` (`clase_resumen/__init__.py`) |
| Python probado | 3.12.10 (Windows) |
| Dependencias externas | Ninguna. Solo biblioteca estándar |
| Clases procesadas con éxito | 1 (`PRUEBAS DE SOFTWARE`, 03/11/2026) en `DCGS12424` |
| Cursos registrados | 3 (`SPTI02423`, `DCGS12424`, `PROG04696`) |
| Cobertura medida en esa clase | 96.4 % |
| Tiempo de proceso | 255–548 s en 4 ejecuciones (varía por el proveedor del modelo) |
| Llamadas al modelo por clase | 14 (13 bloques + 1 síntesis), más las de auditoría |

## Por dónde empezar

| Si quieres… | Lee |
|---|---|
| Usar la herramienta ahora mismo | [02-uso/comandos.md](02-uso/comandos.md) |
| Entender qué produce exactamente | [02-uso/salidas.md](02-uso/salidas.md) |
| Saber cómo funciona por dentro | [03-arquitectura/flujo.md](03-arquitectura/flujo.md) |
| Ver qué se comprobó y qué no | [05-pruebas/verificacion.md](05-pruebas/verificacion.md) |
| Saber qué falta o falla | [06-limitaciones/limitaciones.md](06-limitaciones/limitaciones.md) |
| Solucionar un error | [07-solucion-de-problemas/errores.md](07-solucion-de-problemas/errores.md) |

## Índice completo

### 01 — Visión general
- [README.md](01-vision-general/README.md) — qué es, qué problema resuelve, qué no hace

### 02 — Uso
- [instalacion.md](02-uso/instalacion.md) — requisitos y configuración del modelo
- [comandos.md](02-uso/comandos.md) — todas las opciones del CLI, verificadas
- [salidas.md](02-uso/salidas.md) — estructura del `.md`, del `.html` y del `.json`
- [interpretar-apuntes.md](02-uso/interpretar-apuntes.md) — cómo leer «Lo que importa», los pesos y los minutos

### 03 — Arquitectura
- [flujo.md](03-arquitectura/flujo.md) — el recorrido completo, paso a paso
- [modulos.md](03-arquitectura/modulos.md) — responsabilidad de cada archivo y sus funciones
- [extraccion-class.md](03-arquitectura/extraccion-class.md) — cómo se obtiene la transcripción de la plataforma
- [resumen-y-auditoria.md](03-arquitectura/resumen-y-auditoria.md) — bloqueo, fusión, deduplicación y auditoría
- [huella.md](03-arquitectura/huella.md) — cómo se evita pagar dos veces por la misma clase
- [visor-html.md](03-arquitectura/visor-html.md) — cómo funciona el visor y de dónde saca el video

### 04 — Datos
- [modelo-de-datos.md](04-datos/modelo-de-datos.md) — las estructuras `Clase` y `Segmento`
- [json-intermedio.md](04-datos/json-intermedio.md) — el JSON que permite re-renderizar sin gastar modelo

### 05 — Pruebas
- [verificacion.md](05-pruebas/verificacion.md) — qué se comprobó realmente y cómo

### 06 — Limitaciones
- [limitaciones.md](06-limitaciones/limitaciones.md) — qué no hace, qué puede fallar
- [riesgos.md](06-limitaciones/riesgos.md) — privacidad, caducidad de enlaces, dependencia externa

### 07 — Solución de problemas
- [errores.md](07-solucion-de-problemas/errores.md) — mensajes de error y su causa real

### 08 — Futuro
- [mejoras-propuestas.md](08-futuro/mejoras-propuestas.md) — ideas no implementadas, con su coste

### plans — Planes de trabajo
- [plan-interfaz-web-local.md](plans/plan-interfaz-web-local.md) — interfaz web local mínima (en implementación)
- [plan-plataforma-web.md](plans/plan-plataforma-web.md) — plataforma multiusuario (**sustituido**, no se implementa)
