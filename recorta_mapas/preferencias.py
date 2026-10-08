"""Lembra os últimos arquivos e opções entre execuções.

Fica fora da pasta do programa (como o Dicta): %APPDATA%\\RecortaMapas no Windows,
~/.config/recorta_mapas nos outros sistemas. RECORTA_MAPAS_DADOS muda a pasta (testes)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path

from .config import EntradaLinhas, EntradaPontos, Limites, OpcoesCSV, Opcoes

ARQUIVO = "preferencias.json"


def pasta_dados() -> Path:
    if os.environ.get("RECORTA_MAPAS_DADOS"):
        return Path(os.environ["RECORTA_MAPAS_DADOS"])
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "RecortaMapas"
    return Path.home() / ".config" / "recorta_mapas"


def _filtrar(cls, d: dict) -> dict:
    nomes = {f.name for f in fields(cls)}
    return {k: v for k, v in d.items() if k in nomes}


def para_dict(op: Opcoes) -> dict:
    return asdict(op)


def de_dict(d: dict) -> Opcoes:
    d = dict(d)
    linhas = [EntradaLinhas(**_filtrar(EntradaLinhas, x)) for x in d.pop("linhas", []) or []]
    pontos = []
    for x in d.pop("pontos", []) or []:
        x = _filtrar(EntradaPontos, x)
        csv = x.pop("csv", None)
        pontos.append(EntradaPontos(**x, csv=OpcoesCSV(**_filtrar(OpcoesCSV, csv)) if csv else None))
    limites = Limites(**_filtrar(Limites, d.pop("limites", {}) or {}))
    return Opcoes(**_filtrar(Opcoes, d), linhas=linhas, pontos=pontos, limites=limites)


def carregar() -> Opcoes:
    """Preferências salvas, ou o padrão se não houver (ou se o arquivo estiver estragado)."""
    try:
        with open(pasta_dados() / ARQUIVO, encoding="utf-8") as f:
            return de_dict(json.load(f))
    except (OSError, ValueError, TypeError):
        return Opcoes()


def salvar(op: Opcoes) -> None:
    pasta = pasta_dados()
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = pasta / (ARQUIVO + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(para_dict(op), f, ensure_ascii=False, indent=1)
    os.replace(tmp, pasta / ARQUIVO)
