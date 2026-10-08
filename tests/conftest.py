"""Dados sintéticos perto de (-47, -15). 0,01° ≈ 1,1 km.

Mapa-mestre: quadrado lon [-47,10; -47,00] x lat [-15,10; -15,00].
T01: lon [-47,10; -47,05] x lat [-15,10; -15,05]
T02: lon [-47,05; -47,00] x lat [-15,10; -15,05]   (divisa com T01 em lon -47,05)
T03: lon [-47,03; -46,98] x lat [-15,05; -15,02]   (40% fora do mapa-mestre)
Área urbana: o resto do mapa-mestre (lat > -15,05 fora de T03).
"""

from __future__ import annotations

import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KML_NS = 'xmlns="http://www.opengis.net/kml/2.2"'


def ret(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def _c(coords):
    return " ".join(f"{x},{y},0" for x, y in coords)


def placemark(nome, geom_xml, estilo=None, dados=None):
    s = f"<Placemark><name>{nome}</name>"
    if estilo:
        s += f"<styleUrl>#{estilo}</styleUrl>"
    if dados:
        s += "<ExtendedData>" + "".join(
            f'<Data name="{k}"><value>{v}</value></Data>' for k, v in dados.items()) + "</ExtendedData>"
    return s + geom_xml + "</Placemark>"


def poligono_xml(coords):
    return (f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{_c(coords)}"
            "</coordinates></LinearRing></outerBoundaryIs></Polygon>")


def linha_xml(coords):
    return f"<LineString><coordinates>{_c(coords)}</coordinates></LineString>"


def ponto_xml(x, y):
    return f"<Point><coordinates>{x},{y},0</coordinates></Point>"


def documento(corpo, estilos="", nome="doc"):
    return (f'<?xml version="1.0" encoding="UTF-8"?><kml {KML_NS}><Document><name>{nome}</name>'
            f"{estilos}{corpo}</Document></kml>")


ESTILO_VERDE = ('<Style id="verde"><LineStyle><color>ff00ff00</color><width>3</width></LineStyle>'
                '<PolyStyle><color>4000ff00</color></PolyStyle></Style>')

MESTRE = ret(-47.10, -15.10, -47.00, -15.00)
T01 = ret(-47.10, -15.10, -47.05, -15.05)
T02 = ret(-47.05, -15.10, -47.00, -15.05)
T03 = ret(-47.03, -15.05, -46.98, -15.02)


def escrever(caminho, texto):
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return str(caminho)


@pytest.fixture
def dados(tmp_path):
    """Caminhos dos arquivos sintéticos básicos."""
    d = {}
    d["mestre"] = escrever(tmp_path / "mestre.kml",
                           documento(placemark("Congregação", poligono_xml(MESTRE)), nome="Mestre"))
    corpo = "<Folder><name>Rurais</name>" + "".join(
        placemark(n, poligono_xml(c), "verde", {"Obs": f"obs {n}"})
        for n, c in (("T01", T01), ("T02", T02), ("T03", T03))) + "</Folder>"
    d["territorios"] = escrever(tmp_path / "territorios.kml", documento(corpo, ESTILO_VERDE, "Rurais"))
    d["pasta"] = tmp_path
    return d
