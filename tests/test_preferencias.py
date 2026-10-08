from recorta_mapas import preferencias
from recorta_mapas.config import EntradaLinhas, EntradaPontos, Limites, OpcoesCSV, Opcoes


def test_salvar_e_carregar(tmp_path, monkeypatch):
    monkeypatch.setenv("RECORTA_MAPAS_DADOS", str(tmp_path))
    assert preferencias.carregar() == Opcoes()          # sem arquivo: padrão
    op = Opcoes("m.kml", "t.kml", "saída", linhas=[EntradaLinhas("l.kml")],
                pontos=[EntradaPontos("c.csv", csv=OpcoesCSV("latin-1", ";", "LAT", "LON"),
                                      filtro_coluna="COD_ESPECIE", filtro_valores=["1"],
                                      colunas=["DSC_LOCALIDADE"], nome_modelo="{NOM_SEGLOGR}")],
                simplificar_m=5, formato="kmz", limites=Limites(max_feicoes_arquivo=1000))
    preferencias.salvar(op)
    assert preferencias.carregar() == op


def test_arquivo_estragado_ou_antigo(tmp_path, monkeypatch):
    monkeypatch.setenv("RECORTA_MAPAS_DADOS", str(tmp_path))
    (tmp_path / "preferencias.json").write_text("{ruim", encoding="utf-8")
    assert preferencias.carregar() == Opcoes()
    # campos desconhecidos (versão futura/antiga) são ignorados
    (tmp_path / "preferencias.json").write_text(
        '{"mapa_mestre": "m.kml", "campo_novo": 1, "limites": {"max_camadas_mapa": 8, "x": 2}}',
        encoding="utf-8")
    op = preferencias.carregar()
    assert op.mapa_mestre == "m.kml" and op.limites.max_camadas_mapa == 8
