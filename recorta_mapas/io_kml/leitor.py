"""Leitura de KML/KMZ preservando nomes, estilos, pastas e ExtendedData."""

from __future__ import annotations

import copy
import io
import os
import zipfile

from lxml import etree
from shapely.geometry import (
    GeometryCollection, LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon,
)

from ..modelos import Camada, Feicao

NS_KML = "http://www.opengis.net/kml/2.2"
NS_GX = "http://www.google.com/kml/ext/2.2"


class ErroLeitura(Exception):
    pass


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _normalizar(el: etree._Element) -> etree._Element:
    """Cópia do elemento com o namespace KML (qualquer versão ou nenhum) trocado por KML 2.2."""
    novo = copy.deepcopy(el)
    for e in novo.iter():
        if not isinstance(e.tag, str):
            continue
        q = etree.QName(e.tag)
        ns = q.namespace or ""
        if ns == "" or ("kml" in ns and "ext" not in ns):
            e.tag = f"{{{NS_KML}}}{q.localname}"
    etree.cleanup_namespaces(novo)
    return novo


def _abrir(caminho: str) -> tuple[bytes, dict[str, bytes]]:
    if zipfile.is_zipfile(caminho):
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
            kmls = [n for n in nomes if n.lower().endswith(".kml")]
            if not kmls:
                raise ErroLeitura(f"O arquivo KMZ não contém nenhum KML: {caminho}")
            principal = "doc.kml" if "doc.kml" in kmls else min(kmls, key=lambda n: (n.count("/"), n))
            recursos = {n: z.read(n) for n in nomes if n != principal and not n.endswith("/")}
            return z.read(principal), recursos
    with open(caminho, "rb") as f:
        return f.read(), {}


def _texto_filho(el, nome: str) -> str | None:
    f = el.find(f"{{*}}{nome}")
    return f.text if f is not None else None


def _coords(el) -> list[tuple[float, float]]:
    c = el.find("{*}coordinates") if _local(el.tag) != "coordinates" else el
    if c is None or not c.text:
        return []
    pts = []
    for tok in c.text.replace(", ", ",").split():
        partes = tok.split(",")
        if len(partes) < 2:
            continue
        try:
            pts.append((float(partes[0]), float(partes[1])))
        except ValueError:
            continue
    return pts


def _anel(el) -> list[tuple[float, float]]:
    anel = el.find("{*}LinearRing")
    return _coords(anel) if anel is not None else []


def _geometria(el):
    t = _local(el.tag)
    if t == "Point":
        c = _coords(el)
        return Point(c[0]) if c else None
    if t in ("LineString", "LinearRing"):
        c = _coords(el)
        return LineString(c) if len(c) >= 2 else None
    if t == "Polygon":
        externo = el.find("{*}outerBoundaryIs")
        casca = _anel(externo) if externo is not None else []
        if len(casca) < 3:
            return None
        furos = [_anel(i) for i in el.findall("{*}innerBoundaryIs")]
        return Polygon(casca, [f for f in furos if len(f) >= 3])
    if t == "MultiGeometry":
        partes = [g for g in (_geometria(c) for c in el if isinstance(c.tag, str)) if g is not None]
        if not partes:
            return None
        simples = []
        for p in partes:
            simples.extend(p.geoms if hasattr(p, "geoms") else [p])
        if all(isinstance(p, Point) for p in simples):
            return MultiPoint(simples)
        if all(isinstance(p, LineString) for p in simples):
            return MultiLineString(simples)
        if all(isinstance(p, Polygon) for p in simples):
            return MultiPolygon(simples)
        return GeometryCollection(simples)
    return None


_TIPOS_GEOM = {"Point", "LineString", "LinearRing", "Polygon", "MultiGeometry"}
_TIPOS_IGNORADOS = {"Track", "MultiTrack", "Model"}


def _dados_estendidos(pm) -> dict[str, str]:
    dados: dict[str, str] = {}
    ed = pm.find("{*}ExtendedData")
    if ed is None:
        return dados
    for d in ed.iter("{*}Data"):
        nome = d.get("name")
        if nome:
            v = d.find("{*}value")
            dados[nome] = (v.text or "") if v is not None else ""
    for sd in ed.iter("{*}SimpleData"):
        nome = sd.get("name")
        if nome:
            dados[nome] = sd.text or ""
    return dados


def _pasta(pm) -> tuple[str, ...]:
    nomes = []
    p = pm.getparent()
    while p is not None:
        if _local(p.tag) == "Folder":
            nomes.append((_texto_filho(p, "name") or "").strip())
        p = p.getparent()
    return tuple(reversed(nomes))


def ler_camada(caminho: str) -> Camada:
    try:
        dados, recursos = _abrir(caminho)
    except (OSError, zipfile.BadZipFile) as e:
        raise ErroLeitura(f"Não foi possível abrir {caminho}: {e}") from e
    parser = etree.XMLParser(huge_tree=True, recover=True, remove_blank_text=True)
    try:
        raiz = etree.parse(io.BytesIO(dados), parser).getroot()
    except etree.XMLSyntaxError as e:
        raise ErroLeitura(f"KML inválido em {caminho}: {e}") from e
    if raiz is None:
        raise ErroLeitura(f"KML vazio ou ilegível: {caminho}")

    doc = raiz.find("{*}Document")
    nome_doc = (_texto_filho(doc, "name") if doc is not None else None) or \
        os.path.splitext(os.path.basename(caminho))[0]
    camada = Camada(nome=nome_doc.strip(), recursos=recursos)

    for el in raiz.iter("{*}Style", "{*}StyleMap"):
        id_ = el.get("id")
        pai = el.getparent()
        if id_ and (pai is None or _local(pai.tag) != "Placemark"):
            camada.estilos[id_] = _normalizar(el)

    for pm in raiz.iter("{*}Placemark"):
        geom = None
        for filho in pm:
            t = _local(filho.tag)
            if t in _TIPOS_GEOM:
                geom = _geometria(filho)
                break
            if t in _TIPOS_IGNORADOS:
                break
        if geom is None or geom.is_empty:
            camada.geometrias_ignoradas += 1
            continue
        estilo_inline = None
        for filho in pm:
            if _local(filho.tag) in ("Style", "StyleMap"):
                estilo_inline = _normalizar(filho)
                break
        url = _texto_filho(pm, "styleUrl")
        camada.feicoes.append(Feicao(
            geom=geom,
            nome=(_texto_filho(pm, "name") or "").strip(),
            descricao=_texto_filho(pm, "description"),
            estilo_url=url.strip() if url else None,
            estilo_inline=estilo_inline,
            dados=_dados_estendidos(pm),
            pasta=_pasta(pm),
        ))
    return camada
