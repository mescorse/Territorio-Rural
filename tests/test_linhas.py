import pytest

from conftest import documento, escrever, linha_xml, placemark
from recorta_mapas.config import MODO_CORTAR, MODO_INTEIRA
from recorta_mapas.etapa1_ajuste import ajustar
from recorta_mapas.etapa2_recorte import recortar_linhas
from recorta_mapas.geo.indice import IndiceTerritorios
from recorta_mapas.io_kml.leitor import ler_camada


def _preparar(dados, tmp_path):
    r = ajustar(ler_camada(dados["mestre"]), ler_camada(dados["territorios"]))
    indice = IndiceTerritorios([f.territorio for f in r.territorios], [f.geom for f in r.territorios])
    linhas = {
        # do rural T01 (lat -15,08) até a área urbana (lat -15,02)
        "rural_urbano": [(-47.08, -15.08), (-47.08, -15.02)],
        "dentro_T02": [(-47.03, -15.09), (-47.01, -15.06)],
        "urbana": [(-47.09, -15.03), (-47.06, -15.03)],
        "cruza_T01_T02": [(-47.07, -15.09), (-47.02, -15.09)],
    }
    corpo = "".join(placemark(n, linha_xml(c), dados={"SETOR": n}) for n, c in linhas.items())
    camada = ler_camada(escrever(tmp_path / "l.kml", documento(corpo)))
    return camada, indice, r.projecao


def test_cortar_na_borda(dados, tmp_path):
    camada, indice, proj = _preparar(dados, tmp_path)
    saida, est = recortar_linhas(camada, "Trajetos", indice, proj, MODO_CORTAR)
    assert est.lidas == 4 and est.fora == 1 and est.inteiras == 1 and est.cortadas == 2
    ru = [f for f in saida if f.nome == "rural_urbano"]
    assert len(ru) == 1
    assert ru[0].territorio == "T01"
    assert ru[0].geom.bounds[3] == pytest.approx(-15.05)   # cortada na borda do rural
    assert ru[0].dados == {"SETOR": "rural_urbano", "Territorio": "T01"}
    cruza = sorted(f.territorio for f in saida if f.nome == "cruza_T01_T02")
    assert cruza == ["T01", "T02"]
    assert est.varios_territorios == 1
    assert est.km_mantidos < est.km_lidos
    assert est.por_territorio["T02"] > 0


def test_manter_inteira(dados, tmp_path):
    camada, indice, proj = _preparar(dados, tmp_path)
    saida, est = recortar_linhas(camada, "Trajetos", indice, proj, MODO_INTEIRA)
    ru = next(f for f in saida if f.nome == "rural_urbano")
    assert ru.geom.bounds[3] == pytest.approx(-15.02)      # inteira
    cruza = [f for f in saida if f.nome == "cruza_T01_T02"]
    assert len(cruza) == 1
    assert cruza[0].territorio == "T02"   # 0,03° em T02 contra 0,02° em T01
    assert est.fora == 1 and len(saida) == 3


def test_simplificacao_reduz_vertices(dados, tmp_path):
    r = ajustar(ler_camada(dados["mestre"]), ler_camada(dados["territorios"]))
    indice = IndiceTerritorios([f.territorio for f in r.territorios], [f.geom for f in r.territorios])
    coords = [(-47.09 + i * 0.0004, -15.08 + (0.00001 if i % 2 else 0)) for i in range(50)]
    camada = ler_camada(escrever(tmp_path / "z.kml", documento(placemark("zig", linha_xml(coords)))))
    _, sem = recortar_linhas(camada, "T", indice, r.projecao)
    _, com = recortar_linhas(camada, "T", indice, r.projecao, simplificar_m=5)
    assert com.vertices_depois < sem.vertices_depois
