"""Leitura de CSV de pontos (ex.: CNEFE 2022): codificação, delimitador e colunas de coordenadas."""

from __future__ import annotations

import codecs
import csv
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from .config import CNEFE_COLUNA_ESPECIE, OpcoesCSV

csv.field_size_limit(10_000_000)

NOMES_LAT = ["LATITUDE", "LAT", "NU_LATITUDE", "Y", "COORD_Y", "LATITUDE_DECIMAL"]
NOMES_LON = ["LONGITUDE", "LON", "LONG", "LNG", "NU_LONGITUDE", "X", "COORD_X", "LONGITUDE_DECIMAL"]


class ErroCSV(Exception):
    pass


def _normalizar_nome(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.strip().strip('"').upper().replace(" ", "_")


def detectar_codificacao(caminho: str, bloco: int = 1 << 20) -> str:
    """UTF-8 (com ou sem BOM) se o arquivo inteiro decodificar; senão Latin-1."""
    dec = codecs.getincrementaldecoder("utf-8")()
    with open(caminho, "rb") as f:
        inicio = f.read(3)
        tem_bom = inicio == codecs.BOM_UTF8
        try:
            if not tem_bom:
                dec.decode(inicio)
            while True:
                b = f.read(bloco)
                if not b:
                    dec.decode(b"", final=True)
                    break
                dec.decode(b)
        except UnicodeDecodeError:
            return "latin-1"
    return "utf-8-sig" if tem_bom else "utf-8"


def detectar_delimitador(amostra: str) -> str:
    linhas = [l for l in amostra.splitlines() if l.strip()][:50]
    if not linhas:
        return ";"
    try:
        return csv.Sniffer().sniff("\n".join(linhas), delimiters=";,\t|").delimiter
    except csv.Error:
        cab = linhas[0]
        return max(";,\t|", key=cab.count)


def _achar_coluna(colunas: list[str], candidatos: list[str]) -> str | None:
    norm = {_normalizar_nome(c): c for c in colunas}
    for cand in candidatos:
        if cand in norm:
            return norm[cand]
    for cand in candidatos[:2]:
        for n, original in norm.items():
            if n.startswith(cand):
                return original
    return None


def numero(texto) -> float | None:
    if texto is None:
        return None
    s = str(texto).strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class InfoCSV:
    opcoes: OpcoesCSV
    colunas: list[str]
    amostra: list[dict[str, str]] = field(default_factory=list)
    cnefe: bool = False


def inspecionar(caminho: str, opcoes: OpcoesCSV | None = None, n_amostra: int = 20) -> InfoCSV:
    """Detecta o que não foi informado manualmente e lê uma amostra."""
    o = OpcoesCSV(**vars(opcoes)) if opcoes else OpcoesCSV()
    if not o.codificacao:
        o.codificacao = detectar_codificacao(caminho)
    with open(caminho, encoding=o.codificacao, newline="") as f:
        amostra_txt = f.read(64 * 1024)
    if not o.delimitador:
        o.delimitador = detectar_delimitador(amostra_txt)
    with open(caminho, encoding=o.codificacao, newline="") as f:
        leitor = csv.DictReader(f, delimiter=o.delimitador)
        colunas = [c for c in (leitor.fieldnames or [])]
        amostra = []
        for i, linha in enumerate(leitor):
            if i >= n_amostra:
                break
            amostra.append(linha)
    if not colunas:
        raise ErroCSV(f"CSV sem cabeçalho: {caminho}")
    if not o.coluna_lat:
        o.coluna_lat = _achar_coluna(colunas, NOMES_LAT)
    if not o.coluna_lon:
        o.coluna_lon = _achar_coluna(colunas, NOMES_LON)
    for nome, col in (("latitude", o.coluna_lat), ("longitude", o.coluna_lon)):
        if col is None:
            raise ErroCSV(f"Não foi possível identificar a coluna de {nome}. Informe-a manualmente.")
        if col not in colunas:
            raise ErroCSV(f"Coluna de {nome} '{col}' não existe no CSV. Colunas: {', '.join(colunas)}")
    cnefe = CNEFE_COLUNA_ESPECIE in colunas and "NOM_SEGLOGR" in colunas
    return InfoCSV(opcoes=o, colunas=colunas, amostra=amostra, cnefe=cnefe)


def linhas(caminho: str, opcoes: OpcoesCSV):
    """Itera as linhas como dicionários (opções já resolvidas por inspecionar())."""
    with open(caminho, encoding=opcoes.codificacao, newline="") as f:
        yield from csv.DictReader(f, delimiter=opcoes.delimitador)


def valores_distintos(caminho: str, opcoes: OpcoesCSV, coluna: str) -> Counter:
    contagem: Counter = Counter()
    for linha in linhas(caminho, opcoes):
        contagem[(linha.get(coluna) or "").strip()] += 1
    return contagem
