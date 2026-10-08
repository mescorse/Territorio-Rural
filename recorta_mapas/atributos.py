"""Colunas de saída, nome dos pontos e padrões do CNEFE."""

from __future__ import annotations

import re

from .config import (
    CNEFE_COLUNA_ESPECIE, CNEFE_COLUNAS_PADRAO, CNEFE_ESPECIE_DOMICILIO_PARTICULAR,
    CNEFE_MODELO_ENDERECO, EntradaPontos,
)
from .io_csv import InfoCSV

_CAMPO = re.compile(r"\{([^{}]+)\}")


class _Vazio(dict):
    def __missing__(self, chave):
        return ""


def montar_nome(modelo: str, linha: dict, numero: int = 0) -> str:
    valores = _Vazio({k: (v or "").strip() for k, v in linha.items() if k is not None})
    valores.setdefault("n", str(numero))
    try:
        texto = modelo.format_map(valores)
    except (ValueError, IndexError):
        texto = modelo
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s+,", ",", texto)
    texto = re.sub(r",(\s*,)+", ",", texto)
    return texto.strip(" ,-")


def campos_do_modelo(modelo: str) -> list[str]:
    return [c for c in _CAMPO.findall(modelo) if c != "n"]


def resolver_padroes(entrada: EntradaPontos, info: InfoCSV) -> list[str]:
    """Preenche filtro/colunas/nome não informados (None) com os padrões.
    Devolve avisos (ex.: coluna inexistente)."""
    avisos = []
    if entrada.filtro_coluna is None:
        if info.cnefe:
            entrada.filtro_coluna = CNEFE_COLUNA_ESPECIE
            entrada.filtro_valores = [CNEFE_ESPECIE_DOMICILIO_PARTICULAR]
        else:
            entrada.filtro_coluna = ""
    if entrada.colunas is None:
        entrada.colunas = [c for c in CNEFE_COLUNAS_PADRAO if c in info.colunas] if info.cnefe else []
    if entrada.nome_coluna is None and entrada.nome_modelo is None:
        if info.cnefe:
            entrada.nome_modelo = CNEFE_MODELO_ENDERECO
        else:
            for c in info.colunas:
                if c.strip().upper() in ("NOME", "NAME", "ENDERECO", "ENDEREÇO", "DESCRICAO"):
                    entrada.nome_coluna = c
                    break
            else:
                entrada.nome_modelo = "Ponto {n}"
    faltando = [c for c in entrada.colunas if c not in info.colunas]
    if entrada.filtro_coluna and entrada.filtro_coluna not in info.colunas:
        faltando.append(entrada.filtro_coluna)
    if entrada.nome_coluna and entrada.nome_coluna not in info.colunas:
        faltando.append(entrada.nome_coluna)
    if entrada.nome_modelo:
        faltando += [c for c in campos_do_modelo(entrada.nome_modelo) if c not in info.colunas]
    if faltando:
        avisos.append("Colunas não encontradas no CSV: " + ", ".join(dict.fromkeys(faltando)))
    return avisos
