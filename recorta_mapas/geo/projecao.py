"""Projeção métrica local (SIRGAS 2000 / UTM) para áreas, comprimentos e simplificação."""

from __future__ import annotations

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry


def epsg_utm(lon: float, lat: float) -> int:
    zona = min(max(int((lon + 180) // 6) + 1, 1), 60)
    if -75 <= lon <= -28 and -35 <= lat <= 7:
        # SIRGAS 2000 / UTM: 31960+zona (sul), 31954+zona (norte)
        return 31960 + zona if lat < 0 else 31954 + zona
    return (32700 if lat < 0 else 32600) + zona


class Projecao:
    def __init__(self, lon: float, lat: float):
        self.epsg = epsg_utm(lon, lat)
        self._ida = Transformer.from_crs(4326, self.epsg, always_xy=True)
        self._volta = Transformer.from_crs(self.epsg, 4326, always_xy=True)

    @classmethod
    def para_geometria(cls, geom: BaseGeometry) -> "Projecao":
        c = geom.centroid if not geom.is_empty else None
        if c is None or c.is_empty:
            return cls(-47.0, -15.0)
        return cls(c.x, c.y)

    def _aplicar(self, geom, trans):
        def f(coords):
            x, y = trans.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])
        return shapely.transform(geom, f)

    def para_metros(self, geom):
        return self._aplicar(geom, self._ida)

    def para_graus(self, geom):
        return self._aplicar(geom, self._volta)

    def area_ha(self, geom) -> float:
        return 0.0 if geom is None or geom.is_empty else self.para_metros(geom).area / 10_000

    def area_m2(self, geom) -> float:
        return 0.0 if geom is None or geom.is_empty else self.para_metros(geom).area

    def comprimento_km(self, geom) -> float:
        return 0.0 if geom is None or geom.is_empty else self.para_metros(geom).length / 1000

    def simplificar(self, geom, tolerancia_m: float):
        if tolerancia_m <= 0 or geom.is_empty:
            return geom
        m = self.para_metros(geom).simplify(tolerancia_m, preserve_topology=True)
        return self.para_graus(m)
