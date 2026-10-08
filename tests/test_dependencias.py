import sys

from recorta_mapas import dependencias


def test_versao_e_faltando(monkeypatch):
    assert dependencias._versao("2.0.6") == (2, 0, 6)
    assert dependencias._versao("3.7.1rc1") == (3, 7, 1)
    assert dependencias.faltando() == []          # ambiente de teste tem tudo
    versoes = {"shapely": "1.8.5", "lxml": "5.0", "pyproj": "3.6", "numpy": "2.0"}

    def falsa(nome):
        if nome not in versoes:
            raise dependencias.metadata.PackageNotFoundError(nome)
        return versoes[nome]

    monkeypatch.setattr(dependencias.metadata, "version", falsa)
    assert dependencias.faltando() == ["shapely"]  # 1.8 é antiga demais
    del versoes["lxml"]
    assert dependencias.faltando() == ["shapely", "lxml"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert dependencias.faltando() == []           # o .exe nunca instala nada
    assert not dependencias.pode_instalar()


def test_resumo_pip():
    assert dependencias.resumo_pip("Collecting shapely>=2.0") == "Procurando shapely>=2.0"
    assert dependencias.resumo_pip(
        "Downloading shapely-2.1.0-cp314-cp314-win_amd64.whl (1.7 MB)") == \
        "Baixando shapely-2.1.0-cp314-cp314-win_amd64.whl"
    assert dependencias.resumo_pip("  |████████| 1.7 MB") == ""
    assert dependencias.resumo_pip(
        r"Requirement already satisfied: shapely>=2.0 in c:\python\lib\site-packages (2.2.0)") == \
        "Já instalado shapely>=2.0"


def test_ausentes_rapido(monkeypatch):
    assert dependencias.ausentes() == []
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: None if n == "pyproj" else real(n, *a))
    assert dependencias.ausentes() == ["pyproj"]
