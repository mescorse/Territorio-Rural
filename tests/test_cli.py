from recorta_mapas.cli import main


def test_cli_completo(dados, tmp_path, capsys):
    saida = tmp_path / "saida"
    codigo = main(["--mestre", dados["mestre"], "--territorios", dados["territorios"],
                   "--saida", str(saida), "--limiar-perda", "50"])
    assert codigo == 0
    out = capsys.readouterr().out
    assert "ETAPA 1" in out and "ALERTA" not in out      # 40% < 50%
    assert (saida / "Territorios_rurais.kml").exists()
    assert (saida / "relatorio.txt").exists()


def test_cli_erro_em_portugues(tmp_path, capsys):
    assert main(["--mestre", str(tmp_path / "nao.kml"), "--territorios", "x", "--saida", str(tmp_path)]) == 1
    assert "Não foi possível abrir" in capsys.readouterr().err
