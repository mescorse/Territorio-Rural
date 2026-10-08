"""Pesos (feições, bytes, vértices, células) e divisão de grupos de feições em arquivos."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely

from .io_kml.escritor import CABECALHO, RODAPE, tamanho_placemark, xml_estilos
from .modelos import Feicao, chave_natural

INF = float("inf")


@dataclass
class Peso:
    feicoes: float = 0
    bytes: float = 0
    vertices: float = 0
    celulas: float = 0

    def __add__(self, o: "Peso") -> "Peso":
        return Peso(self.feicoes + o.feicoes, self.bytes + o.bytes,
                    self.vertices + o.vertices, self.celulas + o.celulas)

    def __sub__(self, o: "Peso") -> "Peso":
        return Peso(self.feicoes - o.feicoes, self.bytes - o.bytes,
                    self.vertices - o.vertices, self.celulas - o.celulas)

    def cabe(self, cap: "Peso") -> bool:
        return (self.feicoes <= cap.feicoes and self.bytes <= cap.bytes
                and self.vertices <= cap.vertices and self.celulas <= cap.celulas)

    def fracao(self, cap: "Peso") -> float:
        """Maior fração ocupada entre as dimensões (para ordenar e dividir)."""
        r = 0.0
        for a, b in ((self.feicoes, cap.feicoes), (self.bytes, cap.bytes),
                     (self.vertices, cap.vertices), (self.celulas, cap.celulas)):
            if b != INF:
                r = max(r, a / b if b > 0 else INF)
        return r


def somar(pesos) -> Peso:
    total = Peso()
    for p in pesos:
        total = total + p
    return total


@dataclass
class Categoria:
    """Um tipo de camada de saída (ex.: casas, trajetos)."""

    prefixo: str
    nome_doc: str
    feicoes: list[Feicao]
    estilos: dict = field(default_factory=dict)
    recursos: dict = field(default_factory=dict)
    colunas: int = 0          # colunas de atributos (união), para contar células
    sobrecarga: int = 0       # bytes fixos por arquivo (cabeçalho, estilos, pastas)
    pesos: dict = field(default_factory=dict)   # id(feição) -> Peso

    def preparar(self) -> None:
        cols: dict[str, None] = {}
        for f in self.feicoes:
            for k in f.dados:
                cols.setdefault(k, None)
        self.colunas = len(cols)
        celulas = 2 + self.colunas      # nome + descrição + atributos
        pastas = {f.pasta for f in self.feicoes}
        bytes_pastas = sum(sum(len(n.encode()) + 40 for n in p) for p in pastas)
        self.sobrecarga = (len(CABECALHO) + len(RODAPE) + 200 + bytes_pastas
                           + len(xml_estilos(self.feicoes, self.estilos).encode()))
        self.pesos = {
            id(f): Peso(1, tamanho_placemark(f), int(shapely.get_num_coordinates(f.geom)), celulas)
            for f in self.feicoes
        }

    def peso(self, feicoes) -> Peso:
        return somar(self.pesos[id(f)] for f in feicoes)


def _ponto_ref(g):
    if g.geom_type == "Point":
        return g.x, g.y
    if g.geom_type in ("LineString", "MultiLineString"):
        p = shapely.line_interpolate_point(g, 0.5, normalized=True) \
            if g.geom_type == "LineString" else g.representative_point()
        return p.x, p.y
    p = g.representative_point()
    return p.x, p.y


def dividir_espacial(itens: list, pesos: list[Peso], cap: Peso, cabe_parte=None) -> list[list]:
    """Divide itens (com geometria em .geom) em faixas contíguas ao longo do eixo maior.
    Cada parte é enchida até o limite e a última fica com o resto: assim o resto pode
    dividir arquivo/mapa com outros territórios (menos arquivos no total).
    `cabe_parte(lista)` permite um teste extra (ex.: número de camadas)."""
    if not itens:
        return []
    xy = np.array([_ponto_ref(i.geom) for i in itens])
    lat_media = float(np.mean(xy[:, 1]))
    dx = (xy[:, 0].max() - xy[:, 0].min()) * math.cos(math.radians(lat_media))
    dy = xy[:, 1].max() - xy[:, 1].min()
    ordem = np.argsort(xy[:, 0] if dx >= dy else xy[:, 1], kind="stable")
    itens = [itens[i] for i in ordem]
    pesos = [pesos[i] for i in ordem]
    n = len(itens)
    dims = [("feicoes", cap.feicoes), ("bytes", cap.bytes),
            ("vertices", cap.vertices), ("celulas", cap.celulas)]
    acum = {d: np.concatenate([[0.0], np.cumsum([getattr(p, d) for p in pesos])]) for d, _ in dims}
    partes, pos = [], 0
    while pos < n:
        k = n
        for d, c in dims:
            if c != INF:
                k = min(k, int(np.searchsorted(acum[d], acum[d][pos] + c, side="right")) - 1)
        k = max(k, pos + 1)
        if cabe_parte is not None and k > pos + 1 and not cabe_parte(itens[pos:k]):
            lo, hi = pos + 1, k - 1          # maior k que passa no teste (busca binária)
            while lo < hi:
                meio = (lo + hi + 1) // 2
                if cabe_parte(itens[pos:meio]):
                    lo = meio
                else:
                    hi = meio - 1
            k = lo
        partes.append(itens[pos:k])
        pos = k
    return partes


@dataclass
class Grupo:
    """Feições de um território (ou parte dele) em uma categoria."""

    territorio: str
    feicoes: list[Feicao]
    peso: Peso
    completo: bool = True


def empacotar(grupos: list[Grupo], cap: Peso, cat: Categoria) -> list[list[Grupo]]:
    """First-fit decreasing de grupos em arquivos; grupo maior que um arquivo é dividido."""
    itens: list[Grupo] = []
    for g in grupos:
        if g.peso.cabe(cap):
            itens.append(g)
            continue
        partes = dividir_espacial(g.feicoes, [cat.pesos[id(f)] for f in g.feicoes], cap)
        for p in partes:
            itens.append(Grupo(g.territorio, p, cat.peso(p), completo=False))
    # Em ordem natural (T01, T02...) dá nomes de arquivo com faixas contínuas;
    # só vale se não gastar mais arquivos que o first-fit decreasing.
    em_ordem = sorted(itens, key=lambda g: chave_natural(g.territorio))
    sequencia = _proximo_que_cabe(em_ordem, cap)
    itens.sort(key=lambda g: -g.peso.fracao(cap))
    arquivos: list[list[Grupo]] = []
    ocupacao: list[Peso] = []
    for g in itens:
        for k, oc in enumerate(ocupacao):
            novo = oc + g.peso
            if novo.cabe(cap):
                arquivos[k].append(g)
                ocupacao[k] = novo
                break
        else:
            arquivos.append([g])
            ocupacao.append(g.peso)
    return sequencia if len(sequencia) <= len(arquivos) else arquivos


def _proximo_que_cabe(itens: list[Grupo], cap: Peso) -> list[list[Grupo]]:
    arquivos: list[list[Grupo]] = []
    atual = Peso()
    for g in itens:
        if arquivos and (atual + g.peso).cabe(cap):
            arquivos[-1].append(g)
            atual = atual + g.peso
        else:
            arquivos.append([g])
            atual = g.peso
    return arquivos
