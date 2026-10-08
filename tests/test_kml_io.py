import zipfile

import pytest
from lxml import etree

from conftest import KML_NS, poligono_xml, ret
from recorta_mapas.config import Opcoes
from recorta_mapas.io_kml.escritor import gerar_kml, gravar, recursos_usados
from recorta_mapas.io_kml.leitor import ler_camada
from recorta_mapas.pipeline import executar

ICONE = b"\x89PNG\r\n\x1a\nfalso"


def _kmz_com_icone(caminho, pontos):
    estilos = ('<Style id="casa"><IconStyle><Icon><href>files/casa.png</href></Icon></IconStyle></Style>'
               '<Style id="casa_hl"><IconStyle><scale>1.3</scale></IconStyle></Style>'
               '<StyleMap id="mapa_casa"><Pair><key>normal</key><styleUrl>#casa</styleUrl></Pair>'
               '<Pair><key>highlight</key><styleUrl>#casa_hl</styleUrl></Pair></StyleMap>'
               '<Style id="nao_usado"><LineStyle><width>9</width></LineStyle></Style>')
    corpo = "<Folder><name>Sítios</name>" + "".join(
        f"<Placemark><name>{n}</name><styleUrl>#mapa_casa</styleUrl>"
        f'<ExtendedData><Data name="Família"><value>{n} &amp; cia</value></Data></ExtendedData>'
        f"<Point><coordinates>{x},{y},0</coordinates></Point></Placemark>"
        for n, (x, y) in pontos.items()) + "</Folder>"
    kml = f'<?xml version="1.0" encoding="UTF-8"?><kml {KML_NS}><Document><name>Casas</name>{estilos}{corpo}</Document></kml>'
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("doc.kml", kml)
        z.writestr("files/casa.png", ICONE)
    return str(caminho)


def test_leitura_kmz_com_icone_e_estilos(tmp_path):
    c = ler_camada(_kmz_com_icone(tmp_path / "c.kmz", {"Sítio A": (-47.08, -15.08)}))
    assert c.recursos == {"files/casa.png": ICONE}
    f = c.feicoes[0]
    assert (f.nome, f.estilo_url, f.pasta) == ("Sítio A", "#mapa_casa", ("Sítios",))
    assert f.dados == {"Família": "Sítio A & cia"}
    kml = gerar_kml("x", c.feicoes, c.estilos)
    raiz = etree.fromstring(kml)
    ids = [e.get("id") for e in raiz.iter("{*}Style", "{*}StyleMap")]
    assert set(ids) == {"casa", "casa_hl", "mapa_casa"}      # só os usados
    assert raiz.find(".//{*}Folder/{*}name").text == "Sítios"
    assert recursos_usados(c.feicoes, c.estilos, c.recursos) == {"files/casa.png": ICONE}

    destino = tmp_path / "saida.kmz"
    gravar(str(destino), kml, recursos_usados(c.feicoes, c.estilos, c.recursos), "kmz")
    c2 = ler_camada(str(destino))
    assert c2.recursos == {"files/casa.png": ICONE}
    assert c2.feicoes[0].dados == f.dados and c2.feicoes[0].estilo_url == "#mapa_casa"


def test_pipeline_kmz_de_pontos_mantem_icone(dados, tmp_path):
    kmz = _kmz_com_icone(tmp_path / "c.kmz", {"A": (-47.08, -15.08), "B": (-47.08, -15.02)})
    saida = tmp_path / "saida"
    from recorta_mapas.config import EntradaPontos
    r = executar(Opcoes(dados["mestre"], dados["territorios"], str(saida),
                        pontos=[EntradaPontos(kmz, "Casas_rurais")], formato="kmz"))
    arquivos = [a for m in r.plano.mapas for a in m.arquivos if not a.eh_territorios]
    assert len(arquivos) == 1 and arquivos[0].nome == "Casas_rurais_T01"
    with zipfile.ZipFile(saida / "Mapa_01" / "Casas_rurais_T01.kmz") as z:
        assert z.read("files/casa.png") == ICONE
    assert (saida / "Territorios_rurais.kmz").exists()
    assert (saida / "Mapa_01" / "Territorios_rurais.kmz").exists()
    texto = (saida / "relatorio.txt").read_text(encoding="utf-8")
    assert "ETAPA 1" in texto and "T03" in texto and "ALERTA" in texto


def test_corrige_linha_e_poligono_invalidos(tmp_path):
    gravata = [(-47.09, -15.09), (-47.06, -15.06), (-47.06, -15.09), (-47.09, -15.06), (-47.09, -15.09)]
    kml = (f'<kml {KML_NS}><Document><Placemark><name>g</name>{poligono_xml(gravata)}</Placemark>'
           "<Placemark><name>trilha</name><gx:Track xmlns:gx='http://www.google.com/kml/ext/2.2'/></Placemark>"
           "</Document></kml>")
    p = tmp_path / "x.kml"
    p.write_text(kml, encoding="utf-8")
    c = ler_camada(str(p))
    assert len(c.feicoes) == 1 and not c.feicoes[0].geom.is_valid
    assert c.geometrias_ignoradas == 1
