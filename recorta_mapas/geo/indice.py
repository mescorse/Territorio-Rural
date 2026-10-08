"""Índice espacial dos territórios rurais (consulta de pontos e linhas)."""

from __future__ import annotations

import numpy as np
import shapely
from shapely import STRtree


class IndiceTerritorios:
    """Territórios na ordem dada; "primeiro" = menor índice nessa ordem."""

    def __init__(self, ids: list[str], geoms: list):
        self.ids = list(ids)
        self.geoms = np.array(geoms, dtype=object)
        for g in self.geoms:
            shapely.prepare(g)
        self.arvore = STRtree(self.geoms)

    def localizar_pontos(self, xs, ys):
        """Para cada ponto: índice do primeiro território que o contém (ou -1)
        e quantos territórios o contêm (borda compartilhada / sobreposição)."""
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        n = len(xs)
        resultado = np.full(n, -1, dtype=np.int64)
        if n == 0:
            return resultado, np.zeros(0, dtype=np.int64)
        pts = shapely.points(xs, ys)
        ip, it = self.arvore.query(pts, predicate="intersects")
        contagem = np.bincount(ip, minlength=n)
        if len(ip):
            ordem = np.lexsort((it, ip))
            ip, it = ip[ordem], it[ordem]
            primeiro = np.ones(len(ip), dtype=bool)
            primeiro[1:] = ip[1:] != ip[:-1]
            resultado[ip[primeiro]] = it[primeiro]
        return resultado, contagem

    def candidatos(self, geom) -> list[int]:
        return sorted(int(i) for i in self.arvore.query(geom, predicate="intersects"))
