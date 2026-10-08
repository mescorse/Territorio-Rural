"""Estruturas de dados internas: feições e camadas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree
from shapely.geometry.base import BaseGeometry


@dataclass(eq=False)
class Feicao:
    """Um Placemark. A geometria está sempre em WGS84 (lon, lat)."""

    geom: BaseGeometry
    nome: str = ""
    descricao: str | None = None
    estilo_url: str | None = None           # ex.: "#estilo1"
    estilo_inline: etree._Element | None = None
    dados: dict[str, str] = field(default_factory=dict)
    pasta: tuple[str, ...] = ()
    territorio: str | None = None
    # Cache do XML do Placemark (preenchido na escrita/divisão).
    _xml: str | None = field(default=None, repr=False)


@dataclass
class Camada:
    nome: str
    feicoes: list[Feicao] = field(default_factory=list)
    estilos: dict[str, etree._Element] = field(default_factory=dict)
    recursos: dict[str, bytes] = field(default_factory=dict)   # ícones de um KMZ
    geometrias_ignoradas: int = 0           # tipos não suportados (ex.: gx:Track)


def chave_natural(texto: str):
    """Ordenação natural: T2 antes de T10."""
    return [int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", texto)]
