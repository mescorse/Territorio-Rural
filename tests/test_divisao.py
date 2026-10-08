"""Conjunto grande que força divisões em vários arquivos e vários mapas."""

import random

import pytest

from conftest import (
    ESTILO_VERDE, documento, escrever, linha_xml, placemark, poligono_xml, ret,
)
from recorta_mapas.config import (
    AGRUPAR_SEQUENCIAL, CAMADA_TERR_RESERVAR, EntradaLinhas, EntradaPontos, Limites, Opcoes,
)
from recorta_mapas.pipeline import executar


def _cenario(tmp_path, casas_por_terr):
    """6 territórios lado a lado em lon [-47,12; -47,00]."""
    mestre = escrever(tmp_path / "m.kml", documento(placemark("M", poligono_xml(ret(-47.2, -15.2, -46.9, -14.9)))))
    terrs = {f"T{i + 1:02d}": ret(-47.12 + 0.02 * i, -15.10, -47.10 + 0.02 * i, -15.00) for i in range(6)}
    t = escrever(tmp_path / "t.kml", documento(
        "".join(placemark(n, poligono_xml(c), "verde") for n, c in terrs.items()), ESTILO_VERDE))
    rnd = random.Random(1)
    linhas_csv = ["LATITUDE;LONGITUDE;COD_ESPECIE;NOM_SEGLOGR;NUM_ENDERECO"]
    for i, n in enumerate(casas_por_terr):
        x0 = -47.12 + 0.02 * i
        for k in range(n):
            linhas_csv.append(f"{rnd.uniform(-15.099, -15.001):.6f};{rnd.uniform(x0 + 0.0001, x0 + 0.0199):.6f};1;"
                              f"ESTRADA {i};{k}")
    csv = tmp_path / "c.csv"
    csv.write_text("\n".join(linhas_csv) + "\n", encoding="utf-8")
    rotas = "".join(
        placemark(f"R{i}", linha_xml([(-47.119 + 0.02 * i, -15.099 + 0.0001 * k) for k in range(300)]))
        for i in range(6))
    l = escrever(tmp_path / "l.kml", documento(rotas))
    return mestre, t, str(csv), l


def _verificar_limites(r, lim):
    for m in r.plano.mapas:
        assert len(m.arquivos) <= lim.max_camadas_mapa
        assert m.peso.feicoes <= lim.max_feicoes_mapa
        assert m.peso.vertices <= lim.max_vertices_mapa
        assert sum(a.celulas for a in m.arquivos) <= lim.max_celulas_mapa
        for a in m.arquivos:
            assert len(a.feicoes) <= lim.max_feicoes_arquivo
            assert a.bytes_reais <= lim.max_bytes_arquivo


def test_divisao_em_varios_arquivos_e_mapas(tmp_path):
    casas = [150, 40, 420, 60, 80, 30]
    mestre, t, csv, l = _cenario(tmp_path, casas)
    lim = Limites(max_feicoes_arquivo=100, max_bytes_arquivo=60_000, max_camadas_mapa=4,
                  max_feicoes_mapa=300, max_vertices_mapa=2000, max_celulas_mapa=1200)
    op = Opcoes(mestre, t, str(tmp_path / "s"), linhas=[EntradaLinhas(l)],
                pontos=[EntradaPontos(csv, colunas=["NOM_SEGLOGR"])], limites=lim,
                camada_territorios=CAMADA_TERR_RESERVAR)
    r = executar(op)
    _verificar_limites(r, lim)
    assert len(r.plano.mapas) >= 3
    # todas as casas e rotas foram escritas exatamente uma vez
    casas_saida = [f for m in r.plano.mapas for a in m.arquivos
                   if a.categoria.prefixo == "Casas_rurais" for f in a.feicoes]
    assert len(casas_saida) == sum(casas)
    assert len({id(f) for f in casas_saida}) == sum(casas)
    # territórios grandes divididos em partes; cada mapa tem a camada de territórios
    nomes = [a.nome for m in r.plano.mapas for a in m.arquivos]
    assert any("T03_parte" in n for n in nomes)
    assert all(m.arquivos[0].eh_territorios for m in r.plano.mapas)
    # pastas Mapa_01, Mapa_02, ... gravadas
    for m in r.plano.mapas:
        for a in m.arquivos:
            assert (tmp_path / "s" / m.pasta / f"{a.nome}.kml").exists()
    assert "Mapa_02" in r.relatorio


def test_territorios_pequenos_agrupados_em_um_arquivo(tmp_path):
    mestre, t, csv, l = _cenario(tmp_path, [10, 10, 10, 10, 10, 10])
    r = executar(Opcoes(mestre, t, str(tmp_path / "s"), linhas=[EntradaLinhas(l)],
                        pontos=[EntradaPontos(csv)]))
    assert len(r.plano.mapas) == 1
    nomes = sorted(a.nome for a in r.plano.mapas[0].arquivos)
    assert nomes == ["Casas_rurais_T01-T06", "Territorios_rurais", "Trajetos_T01-T06"]


def test_tamanho_em_bytes_forca_nova_divisao(tmp_path):
    mestre, t, csv, l = _cenario(tmp_path, [200, 0, 0, 0, 0, 0])
    lim = Limites(max_bytes_arquivo=12_000)
    r = executar(Opcoes(mestre, t, str(tmp_path / "s"), pontos=[EntradaPontos(csv)], limites=lim))
    _verificar_limites(r, lim)
    casas = [a for m in r.plano.mapas for a in m.arquivos if a.categoria.prefixo == "Casas_rurais"]
    assert len(casas) >= 2


def test_sequencial_preenche_mapas(tmp_path):
    casas = [150, 40, 420, 60, 80, 30]
    mestre, t, csv, l = _cenario(tmp_path, casas)
    lim = Limites(max_feicoes_arquivo=100, max_camadas_mapa=4, max_feicoes_mapa=300,
                  max_vertices_mapa=2000, max_celulas_mapa=1200)
    op = Opcoes(mestre, t, str(tmp_path / "s"), linhas=[EntradaLinhas(l)],
                pontos=[EntradaPontos(csv)], limites=lim, agrupamento=AGRUPAR_SEQUENCIAL)
    r = executar(op)
    _verificar_limites(r, lim)
    total = sum(len(a.feicoes) for m in r.plano.mapas for a in m.arquivos
                if a.categoria.prefixo == "Casas_rurais")
    assert total == sum(casas)
