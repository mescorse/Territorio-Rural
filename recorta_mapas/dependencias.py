"""Confere e instala as bibliotecas necessárias quando o programa roda a partir do código.

O RecortaMapas.exe já vem com tudo (sys.frozen): nada é conferido nem instalado.
A conferência usa só os metadados instalados (não importa nada), então leva menos de 1 ms."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from importlib import metadata

# Mesmos mínimos do pyproject.toml.
REQUISITOS = {"shapely": "2.0", "lxml": "4.9", "pyproj": "3.5", "numpy": "1.24"}


def _versao(texto: str) -> tuple[int, ...]:
    import re
    partes = []
    for p in texto.split("."):
        m = re.match(r"\d+", p)
        if not m:
            break
        partes.append(int(m.group()))
    return tuple(partes)


def ausentes() -> list[str]:
    """Só confere se existem (find_spec, ~0,3 ms). Usado na abertura da janela."""
    if getattr(sys, "frozen", False):
        return []
    from importlib.util import find_spec
    return [nome for nome in REQUISITOS if find_spec(nome) is None]


def faltando() -> list[str]:
    """Bibliotecas ausentes ou em versão antiga demais (lê os metadados: ~15 ms)."""
    if getattr(sys, "frozen", False):
        return []
    falta = []
    for nome, minima in REQUISITOS.items():
        try:
            if _versao(metadata.version(nome)) < _versao(minima):
                falta.append(nome)
        except metadata.PackageNotFoundError:
            falta.append(nome)
    return falta


def pode_instalar() -> bool:
    return not getattr(sys, "frozen", False)


def comando_manual() -> str:
    return "py -m pip install -e ." if os.name == "nt" else "python3 -m pip install -e ."


def instalar(pacotes: list[str], ao_progredir=None) -> tuple[bool, str]:
    """Roda o pip deste mesmo Python. Devolve (deu_certo, últimas linhas da saída).
    Se não houver permissão na pasta do Python, tenta de novo com --user."""
    avisar = ao_progredir or (lambda linha: None)
    alvos = [f"{p}>={REQUISITOS[p]}" for p in pacotes]
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
            "--no-input", "--upgrade", *alvos]
    extra = {"creationflags": 0x08000000} if os.name == "nt" else {}   # sem janela de console
    ultimas: list[str] = []
    for tentativa in (base, base + ["--user"]):
        try:
            proc = subprocess.Popen(tentativa, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", **extra)
        except OSError as exc:
            return False, str(exc)
        ultimas = []
        for linha in proc.stdout:
            linha = linha.strip()
            if linha:
                ultimas = (ultimas + [linha])[-15:]
                avisar(linha)
        if proc.wait() == 0:
            importlib.invalidate_caches()
            return not faltando(), "\n".join(ultimas)
        texto = "\n".join(ultimas).lower()
        if not ("permission" in texto or "access is denied" in texto or "acesso negado" in texto):
            break
    return False, "\n".join(ultimas)


def resumo_pip(linha: str) -> str:
    """Linha do pip em português curto para o rodapé."""
    l = linha.strip()
    for ingles, pt in (("Collecting", "Procurando"), ("Downloading", "Baixando"),
                       ("Installing collected packages", "Instalando"),
                       ("Successfully installed", "Instalado"),
                       ("Requirement already satisfied", "Já instalado")):
        if l.startswith(ingles):
            resto = l[len(ingles):].strip(" :").split(" in ")[0].split(" (")[0]
            return f"{pt} {resto.replace(chr(92), '/').split('/')[-1][:70]}"
    return ""
