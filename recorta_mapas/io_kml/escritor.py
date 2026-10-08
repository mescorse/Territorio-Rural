"""Escrita de KML/KMZ. O XML é montado como texto para medir o tamanho exato de cada feição."""

from __future__ import annotations

import os
import re
import zipfile
from xml.sax.saxutils import escape, quoteattr

from lxml import etree
from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon

from ..modelos import Feicao
from .leitor import NS_GX, NS_KML

_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

CABECALHO = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    f'<kml xmlns="{NS_KML}" xmlns:gx="{NS_GX}"><Document>'
)
RODAPE = "</Document></kml>\n"


def _txt(s) -> str:
    return escape(_CONTROLE.sub("", str(s)))


def _num(v: float) -> str:
    r = round(v, 6)
    s = repr(r)
    return s[:-2] if s.endswith(".0") else s


def _coords(seq) -> str:
    return " ".join(f"{_num(x)},{_num(y)}" for x, y, *_ in seq)


def _geom_xml(g) -> str:
    if isinstance(g, Point):
        return f"<Point><coordinates>{_num(g.x)},{_num(g.y)}</coordinates></Point>"
    if isinstance(g, LineString):
        return f"<LineString><tessellate>1</tessellate><coordinates>{_coords(g.coords)}</coordinates></LineString>"
    if isinstance(g, Polygon):
        s = ("<Polygon><outerBoundaryIs><LinearRing><coordinates>"
             f"{_coords(g.exterior.coords)}</coordinates></LinearRing></outerBoundaryIs>")
        for anel in g.interiors:
            s += ("<innerBoundaryIs><LinearRing><coordinates>"
                  f"{_coords(anel.coords)}</coordinates></LinearRing></innerBoundaryIs>")
        return s + "</Polygon>"
    if isinstance(g, (MultiPoint, MultiLineString, MultiPolygon)) or hasattr(g, "geoms"):
        partes = [g2 for g2 in g.geoms if not g2.is_empty]
        if len(partes) == 1:
            return _geom_xml(partes[0])
        return "<MultiGeometry>" + "".join(_geom_xml(p) for p in partes) + "</MultiGeometry>"
    raise ValueError(f"Tipo de geometria não suportado: {g.geom_type}")


def _elemento_xml(el: etree._Element) -> str:
    return etree.tostring(el, encoding="unicode")


def xml_placemark(f: Feicao) -> str:
    if f._xml is not None:
        return f._xml
    partes = ["<Placemark>"]
    if f.nome:
        partes.append(f"<name>{_txt(f.nome)}</name>")
    if f.descricao:
        partes.append(f"<description>{_txt(f.descricao)}</description>")
    if f.estilo_url:
        partes.append(f"<styleUrl>{_txt(f.estilo_url)}</styleUrl>")
    if f.estilo_inline is not None:
        partes.append(_elemento_xml(f.estilo_inline))
    if f.dados:
        partes.append("<ExtendedData>")
        for k, v in f.dados.items():
            partes.append(f"<Data name={quoteattr(_CONTROLE.sub('', str(k)))}><value>{_txt(v)}</value></Data>")
        partes.append("</ExtendedData>")
    partes.append(_geom_xml(f.geom))
    partes.append("</Placemark>")
    f._xml = "".join(partes)
    return f._xml


def tamanho_placemark(f: Feicao) -> int:
    return len(xml_placemark(f).encode("utf-8"))


def estilos_usados(feicoes, estilos: dict) -> list[str]:
    """IDs de estilos referenciados (incluindo os estilos dentro de StyleMap), em ordem."""
    vistos: list[str] = []
    pendentes = []
    for f in feicoes:
        if f.estilo_url and f.estilo_url.startswith("#"):
            pendentes.append(f.estilo_url[1:])
        if f.estilo_inline is not None:
            pendentes.extend(u.text.strip()[1:] for u in f.estilo_inline.iter(f"{{{NS_KML}}}styleUrl")
                             if u.text and u.text.strip().startswith("#"))
    conjunto = set()
    while pendentes:
        id_ = pendentes.pop(0)
        if id_ in conjunto or id_ not in estilos:
            continue
        conjunto.add(id_)
        vistos.append(id_)
        for u in estilos[id_].iter(f"{{{NS_KML}}}styleUrl"):
            if u.text and u.text.strip().startswith("#"):
                pendentes.append(u.text.strip()[1:])
    # StyleMap depende dos Style: escrever os Style primeiro.
    return sorted(vistos, key=lambda i: etree.QName(estilos[i].tag).localname == "StyleMap")


def xml_estilos(feicoes, estilos: dict) -> str:
    return "".join(_elemento_xml(estilos[i]) for i in estilos_usados(feicoes, estilos))


def recursos_usados(feicoes, estilos: dict, recursos: dict) -> dict[str, bytes]:
    if not recursos:
        return {}
    hrefs = set()
    elementos = [estilos[i] for i in estilos_usados(feicoes, estilos)]
    elementos += [f.estilo_inline for f in feicoes if f.estilo_inline is not None]
    for el in elementos:
        for h in el.iter(f"{{{NS_KML}}}href"):
            if h.text:
                hrefs.add(h.text.strip())
    return {k: v for k, v in recursos.items() if k in hrefs}


def _corpo(feicoes) -> str:
    """Placemarks agrupados em pastas, mantendo a ordem da primeira aparição."""
    arvore: dict = {}
    for f in feicoes:
        no = arvore
        for nome in f.pasta:
            no = no.setdefault(("pasta", nome), {})
        no.setdefault(("itens", None), []).append(f)

    def montar(no) -> str:
        s = []
        for (tipo, nome), conteudo in no.items():
            if tipo == "itens":
                s.extend(xml_placemark(f) for f in conteudo)
            else:
                s.append(f"<Folder><name>{_txt(nome)}</name>{montar(conteudo)}</Folder>")
        return "".join(s)

    return montar(arvore)


def gerar_kml(nome_doc: str, feicoes, estilos: dict) -> bytes:
    texto = (CABECALHO + f"<name>{_txt(nome_doc)}</name>" + xml_estilos(feicoes, estilos)
             + _corpo(feicoes) + RODAPE)
    return texto.encode("utf-8")


def gravar(caminho: str, kml: bytes, recursos: dict[str, bytes], formato: str) -> None:
    """Grava KML ou KMZ. No formato KML os ícones são copiados ao lado do arquivo."""
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    if formato == "kmz":
        with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("doc.kml", kml)
            for nome, dados in recursos.items():
                z.writestr(nome, dados)
        return
    with open(caminho, "wb") as f:
        f.write(kml)
    base = os.path.abspath(os.path.dirname(caminho))
    for nome, dados in recursos.items():
        destino = os.path.abspath(os.path.join(base, nome))
        if os.path.commonpath([base, destino]) != base:
            continue   # caminho suspeito dentro do KMZ
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "wb") as f:
            f.write(dados)
