import pytest

from conftest import (
    ESTILO_VERDE, T01, T02, documento, escrever, placemark, poligono_xml, ret,
)
from recorta_mapas.etapa1_ajuste import ajustar
from recorta_mapas.io_kml.leitor import ler_camada


def test_territorio_parcialmente_fora_e_aparado_com_alerta(dados):
    r = ajustar(ler_camada(dados["mestre"]), ler_camada(dados["territorios"]), limiar_pct=2.0)
    por_id = {l.id: l for l in r.linhas}
    assert set(por_id) == {"T01", "T02", "T03"}
    assert por_id["T01"].pct_removido == pytest.approx(0, abs=1e-6)
    assert not por_id["T01"].alerta
    # T03 tem 0,02° de 0,05° de largura fora do mestre: ~40% removido.
    assert por_id["T03"].pct_removido == pytest.approx(40, abs=0.5)
    assert por_id["T03"].alerta
    assert por_id["T03"].area_depois_ha < por_id["T03"].area_antes_ha
    assert any("T03" in a and "erro de desenho" in a for a in r.avisos)
    t03 = next(f for f in r.territorios if f.territorio == "T03")
    assert t03.geom.bounds[2] == pytest.approx(-47.00)
    # Nome, estilo, pasta e ExtendedData preservados.
    assert t03.estilo_url == "#verde"
    assert t03.dados["Obs"] == "obs T03"
    assert t03.pasta == ("Rurais",)
    assert not r.sobreposicoes


def test_sobreposicao_detectada_e_divisa_sem_alerta(tmp_path, dados):
    t02_invadindo = ret(-47.06, -15.10, -47.00, -15.05)  # invade 0,01° em T01
    corpo = "".join(placemark(n, poligono_xml(c)) for n, c in (("T01", T01), ("T02", t02_invadindo)))
    terr = escrever(tmp_path / "t.kml", documento(corpo, ESTILO_VERDE))
    r = ajustar(ler_camada(dados["mestre"]), ler_camada(terr))
    assert [(a, b) for a, b, _ in r.sobreposicoes] == [("T01", "T02")]
    assert r.sobreposicoes[0][2] > 1e6   # ~0,01° x 0,05° ≈ 6 km²

    # Divisa compartilhada sem sobreposição não gera aviso.
    corpo = "".join(placemark(n, poligono_xml(c)) for n, c in (("T01", T01), ("T02", T02)))
    terr2 = escrever(tmp_path / "t2.kml", documento(corpo))
    assert ajustar(ler_camada(dados["mestre"]), ler_camada(terr2)).sobreposicoes == []


def test_id_por_campo_quando_sem_nome_e_poligono_invalido_corrigido(tmp_path, dados):
    gravata = [(-47.09, -15.09), (-47.06, -15.06), (-47.06, -15.09), (-47.09, -15.06), (-47.09, -15.09)]
    corpo = (placemark("", poligono_xml(T01), dados={"COD": "R7"})
             + placemark("Gravata", poligono_xml(gravata)))
    terr = escrever(tmp_path / "t.kml", documento(corpo))
    r = ajustar(ler_camada(dados["mestre"]), ler_camada(terr), campo_id="COD")
    assert {f.territorio for f in r.territorios} == {"R7", "Gravata"}
    assert r.correcoes_territorios == 1
    assert all(f.geom.is_valid for f in r.territorios)
