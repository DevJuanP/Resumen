"""Acceso a un modelo de lenguaje compatible con la API de OpenAI.

La configuración se busca en este orden:
  1. config.json del proyecto (base_url, model, api_key o api_key_env)
  2. variables de entorno RESUMEN_BASE_URL / RESUMEN_MODEL / RESUMEN_API_KEY
  3. el proveedor ya configurado en OpenCode (~/.config/opencode/opencode.jsonc)

Nunca se envía audio: solo texto de la transcripción.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.json"


class ErrorDeModelo(Exception):
    pass


@dataclass
class Modelo:
    base_url: str
    model: str
    api_key: str
    extra: dict

    @property
    def etiqueta(self) -> str:
        return f"{self.model} @ {self.base_url.split('//')[-1]}"


def _jsonc_a_json(texto: str) -> str:
    """Quita comentarios y comas finales de un archivo .jsonc."""
    salida, i, n = [], 0, len(texto)
    en_cadena = False
    while i < n:
        c = texto[i]
        if en_cadena:
            salida.append(c)
            if c == "\\" and i + 1 < n:
                salida.append(texto[i + 1])
                i += 2
                continue
            if c == '"':
                en_cadena = False
            i += 1
            continue
        if c == '"':
            en_cadena = True
            salida.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and texto[i + 1] == "/":
            while i < n and texto[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and texto[i + 1] == "*":
            i += 2
            while i + 1 < n and not (texto[i] == "*" and texto[i + 1] == "/"):
                i += 1
            i += 2
            continue
        salida.append(c)
        i += 1
    limpio = re.sub(r",(\s*[}\]])", r"\1", "".join(salida))
    return limpio


def _resolver_referencia(valor: str) -> str:
    """Resuelve `{file:~/.secrets/x}` y `{env:VAR}` como hace OpenCode.

    La configuración de OpenCode puede no contener la clave literal sino una
    referencia a un archivo o a una variable de entorno. Sin resolverla, la
    petición sale con un token inválido y el proveedor responde 401.
    """
    valor = (valor or "").strip()
    m = re.fullmatch(r"\{file:(.+)\}", valor)
    if m:
        ruta = Path(os.path.expanduser(m.group(1).strip()))
        try:
            return ruta.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    m = re.fullmatch(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}", valor)
    if m:
        return os.environ.get(m.group(1), "").strip()
    return valor


def _desde_opencode() -> Modelo | None:
    """Reutiliza el proveedor OpenAI-compatible que ya usa el usuario en OpenCode."""
    candidatos = [
        Path(os.environ.get("OPENCODE_CONFIG", "")) / "opencode.jsonc",
        Path.home() / ".config" / "opencode" / "opencode.jsonc",
        Path.home() / ".config" / "opencode" / "opencode.json",
    ]
    for ruta in candidatos:
        if not ruta.is_file():
            continue
        try:
            cfg = json.loads(_jsonc_a_json(ruta.read_text(encoding="utf-8")))
        except Exception:
            continue
        proveedores = cfg.get("providers") or cfg.get("provider") or {}
        predilecto = cfg.get("model", "")
        orden = [predilecto.split("/")[0]] if predilecto else []
        orden += [p for p in proveedores if p not in orden]
        for nombre in orden:
            p = proveedores.get(nombre) or {}
            ajustes = p.get("settings") or {}
            base = ajustes.get("baseURL") or ajustes.get("base_url")
            clave = _resolver_referencia(ajustes.get("apiKey") or ajustes.get("api_key") or "")
            if not base or not clave:
                continue
            modelos = list((p.get("models") or {}).keys())
            if not modelos:
                continue
            modelo = predilecto.split("/", 1)[1] if predilecto.startswith(nombre + "/") else modelos[0]
            # Solo nos sirve si el endpoint expone /chat/completions estilo OpenAI.
            return Modelo(base.rstrip("/"), modelo, clave, {})
    return None


def cargar() -> Modelo:
    if CONFIG.is_file():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        base = (cfg.get("base_url") or "").rstrip("/")
        modelo = cfg.get("model")
        clave = cfg.get("api_key") or os.environ.get(cfg.get("api_key_env") or "", "")
        if base and modelo:
            if not clave:
                # Sin clave propia: se reutiliza la de OpenCode, pero solo si
                # apunta al mismo endpoint. Si no, el modelo elegido no serviría.
                detectado = _desde_opencode()
                if detectado and detectado.base_url.rstrip("/") == base:
                    clave = detectado.api_key
            if clave:
                extra = dict(cfg.get("extra") or {})
                if cfg.get("reasoning_effort"):
                    extra["reasoning_effort"] = cfg["reasoning_effort"]
                return Modelo(base, modelo, clave, extra)

    base = os.environ.get("RESUMEN_BASE_URL")
    modelo = os.environ.get("RESUMEN_MODEL")
    clave = os.environ.get("RESUMEN_API_KEY")
    if base and modelo and clave:
        return Modelo(base.rstrip("/"), modelo, clave, {})

    detectado = _desde_opencode()
    if detectado:
        return detectado

    raise ErrorDeModelo(
        "No hay ningún modelo configurado.\n"
        "Crea config.json junto a resumen.py con este contenido:\n"
        '{\n  "base_url": "https://api.openai.com/v1",\n'
        '  "model": "gpt-4o-mini",\n  "api_key_env": "OPENAI_API_KEY"\n}'
    )


# --------------------------------------------------------------------------- #

def _post(modelo: Modelo, carga: dict, timeout: int) -> dict:
    cuerpo = dict(carga)
    cuerpo.setdefault("temperature", 0.1)
    datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{modelo.base_url}/chat/completions",
        data=datos,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {modelo.api_key}",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def completar(modelo: Modelo, prompt: str, *, max_tokens: int = 4000,
              json_mode: bool = False, timeout: int = 600,
              intentos: int = 4) -> str:
    """Pide una completación y devuelve el texto, reintentando lo recuperable."""
    ultimo: Exception | None = None
    for intento in range(intentos):
        carga: dict = {
            "model": modelo.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if json_mode:
            carga["response_format"] = {"type": "json_object"}
        carga.update(modelo.extra)
        try:
            r = _post(modelo, carga, timeout)
        except urllib.error.HTTPError as e:
            detalle = e.read()[:300].decode("utf-8", "replace")
            if e.code in (408, 409, 429, 500, 502, 503, 504):
                ultimo = ErrorDeModelo(f"{e.code}: {detalle}")
                time.sleep(min(60, 4 * 2 ** intento) + random.random())
                continue
            raise ErrorDeModelo(f"El modelo rechazó la petición ({e.code}).\n{detalle}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo = ErrorDeModelo(f"Sin respuesta del modelo: {e}")
            time.sleep(min(45, 3 * 2 ** intento) + random.random())
            continue

        opciones = r.get("choices") or []
        if not opciones:
            ultimo = ErrorDeModelo(f"Respuesta sin contenido: {json.dumps(r)[:200]}")
            continue
        mensaje = opciones[0].get("message") or {}
        texto = (mensaje.get("content") or "").strip()
        if texto:
            return texto
        # Algunos modelos gastan todo el presupuesto en razonamiento interno.
        if intento == 0 and mensaje.get("reasoning_content"):
            max_tokens = max(max_tokens, 8000)
            continue
        ultimo = ErrorDeModelo("El modelo devolvió una respuesta vacía.")
    raise ultimo or ErrorDeModelo("No se pudo obtener respuesta del modelo.")


def completar_json(modelo: Modelo, prompt: str, **kwargs) -> dict:
    texto = completar(modelo, prompt, json_mode=True, **kwargs)
    return _extraer_json(texto)


def _extraer_json(texto: str) -> dict:
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = re.sub(r"^```[a-zA-Z]*\s*", "", limpio)
        limpio = re.sub(r"\s*```$", "", limpio)
    try:
        return json.loads(limpio)
    except json.JSONDecodeError:
        pass
    # Recupera el primer objeto equilibrado del texto.
    inicio = limpio.find("{")
    if inicio >= 0:
        profundidad, en_cadena, escape = 0, False, False
        for i, c in enumerate(limpio[inicio:], start=inicio):
            if en_cadena:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    en_cadena = False
                continue
            if c == '"':
                en_cadena = True
            elif c == "{":
                profundidad += 1
            elif c == "}":
                profundidad -= 1
                if profundidad == 0:
                    try:
                        return json.loads(limpio[inicio:i + 1])
                    except json.JSONDecodeError:
                        break
    raise ErrorDeModelo(f"El modelo no devolvió JSON válido:\n{texto[:400]}")
