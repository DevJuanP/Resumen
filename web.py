#!/usr/bin/env python
"""Interfaz web local para los resúmenes de clase.

    python web.py                 # abre en http://127.0.0.1:8765
    python web.py --puerto 9000
    python web.py --abrir         # además abre el navegador

Solo usa la biblioteca estándar. El motor (`resumen.py`) no se modifica: se
invoca como subproceso, igual que se haría desde la consola.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="web",
        description="Interfaz web local para generar y consultar los resúmenes de clase.",
    )
    p.add_argument("--host", default="127.0.0.1",
                   help="interfaz de red donde escuchar (por defecto solo local)")
    p.add_argument("--puerto", type=int, default=8765, help="puerto (por defecto 8765)")
    p.add_argument("--abrir", action="store_true", help="abrir el navegador al arrancar")
    args = p.parse_args(argv)

    from web.servidor import arrancar
    return arrancar(args.host, args.puerto, args.abrir)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
