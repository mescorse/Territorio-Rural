"""Ponto de entrada para o PyInstaller (executável do Windows)."""

import sys

from recorta_mapas.cli import main

if __name__ == "__main__":
    sys.exit(main())
