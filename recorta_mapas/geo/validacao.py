"""Correção de geometrias inválidas (make_valid) mantendo apenas o tipo desejado."""

from __future__ import annotations

import shapely
from shapely.geometry import (
    GeometryCollection, LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon,
)
from shapely.ops import linemerge

POLIGONO, LINHA, PONTO = "poligono", "linha", "ponto"


def tipo_de(geom) -> str | None:
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, (Polygon, MultiPolygon)):
        return POLIGONO
    if isinstance(geom, (LineString, MultiLineString)):
        return LINHA
    if isinstance(geom, (Point, MultiPoint)):
        return PONTO
    tipos = {tipo_de(g) for g in geom.geoms} - {None}
    return tipos.pop() if len(tipos) == 1 else None


def _partes(geom):
    for g in shapely.get_parts(geom):
        if isinstance(g, GeometryCollection) or g.geom_type.startswith("Multi"):
            yield from _partes(g)
        elif not g.is_empty:
            yield g


def extrair(geom, tipo: str):
    """Mantém só as partes do tipo pedido (poligono/linha/ponto)."""
    if geom is None or geom.is_empty:
        return GeometryCollection()
    partes = list(_partes(geom))
    if tipo == POLIGONO:
        polis = [p for p in partes if isinstance(p, Polygon)]
        if not polis:
            return GeometryCollection()
        if len(polis) == 1:
            return polis[0]
        if all(p.is_valid for p in polis):
            return shapely.union_all(polis)
        return MultiPolygon(polis)      # inválido: corrigir() resolve depois
    if tipo == LINHA:
        linhas = [p for p in partes if isinstance(p, LineString) and p.length > 0]
        if not linhas:
            return GeometryCollection()
        if len(linhas) == 1:
            return linhas[0]
        return linemerge(MultiLineString(linhas))
    pontos = [p for p in partes if isinstance(p, Point)]
    if not pontos:
        return GeometryCollection()
    return pontos[0] if len(pontos) == 1 else MultiPoint(pontos)


def corrigir(geom, tipo: str):
    """Devolve (geometria, foi_corrigida)."""
    if geom is None or geom.is_empty or geom.is_valid:
        return geom, False
    return extrair(shapely.make_valid(geom), tipo), True
