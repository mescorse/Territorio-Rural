"""Formatação de números e nomes de arquivo no padrão brasileiro."""

from __future__ import annotations

import re
import unicodedata


def num(valor: float, casas: int = 0) -> str:
    """1234567.891 -> '1.234.567,89'"""
    s = f"{valor:,.{casas}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def bytes_legivel(n: int) -> str:
    if n >= 1_000_000:
        return f"{num(n / 1_000_000, 2)} MB"
    if n >= 1000:
        return f"{num(n / 1000, 1)} kB"
    return f"{n} B"


def nome_arquivo(texto: str) -> str:
    """Remove acentos e caracteres inválidos no Windows."""
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\-]+", "_", s).strip("_")
    return s or "sem_nome"
