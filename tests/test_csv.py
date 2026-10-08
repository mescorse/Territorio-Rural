from conftest import ret
from recorta_mapas.atributos import montar_nome, resolver_padroes
from recorta_mapas.config import EntradaPontos
from recorta_mapas.etapa1_ajuste import ajustar
from recorta_mapas.etapa2_recorte import filtrar_pontos_csv
from recorta_mapas.geo.indice import IndiceTerritorios
from recorta_mapas.io_csv import detectar_codificacao, inspecionar, valores_distintos
from recorta_mapas.io_kml.leitor import ler_camada

CAB = ("COD_UNICO_ENDERECO;NOM_TIPO_SEGLOGR;NOM_TITULO_SEGLOGR;NOM_SEGLOGR;NUM_ENDERECO;"
       "DSC_MODIFICADOR;DSC_LOCALIDADE;LATITUDE;LONGITUDE;COD_ESPECIE")
LINHAS = [
    "1;ESTRADA;;SÃO JOÃO;12;;CÓRREGO FUNDO;-15,08;-47,08;1",      # rural T01, domicílio
    "2;RUA;;DAS FLORES;0;SN;CENTRO;-15,02;-47,08;1",               # urbano
    "3;ESTRADA;;SÃO JOÃO;30;;CÓRREGO FUNDO;-15,08;-47,07;3",       # rural, agropecuário
    "4;ESTRADA;;SÃO JOÃO;40;;CÓRREGO FUNDO;-15,08;-47,02;1",       # rural T02
    "5;ESTRADA;;VICINAL;1;;;;-47,02;1",                            # sem coordenada
    "6;RODOVIA;;BR-060;;KM 3;;-15,08;-46,90;1",                    # fora do mestre
]


def _csv_latin1(tmp_path):
    p = tmp_path / "cnefe.csv"
    p.write_bytes(("\n".join([CAB] + LINHAS) + "\n").encode("latin-1"))
    return str(p)


def test_deteccao_latin1_ponto_e_virgula_e_colunas(tmp_path):
    p = _csv_latin1(tmp_path)
    assert detectar_codificacao(p) == "latin-1"
    info = inspecionar(p)
    assert info.opcoes.delimitador == ";"
    assert info.opcoes.coluna_lat == "LATITUDE" and info.opcoes.coluna_lon == "LONGITUDE"
    assert info.cnefe
    assert info.amostra[0]["NOM_SEGLOGR"] == "SÃO JOÃO"
    assert valores_distintos(p, info.opcoes, "COD_ESPECIE") == {"1": 5, "3": 1}


def test_utf8_virgula(tmp_path):
    p = tmp_path / "u.csv"
    p.write_text("nome,lat,lon\nSão José,-15.08,-47.08\n", encoding="utf-8")
    info = inspecionar(str(p))
    assert info.opcoes.codificacao == "utf-8" and info.opcoes.delimitador == ","
    assert (info.opcoes.coluna_lat, info.opcoes.coluna_lon) == ("lat", "lon")


def test_filtro_cnefe_e_colunas(dados, tmp_path):
    p = _csv_latin1(tmp_path)
    r = ajustar(ler_camada(dados["mestre"]), ler_camada(dados["territorios"]))
    indice = IndiceTerritorios([f.territorio for f in r.territorios], [f.geom for f in r.territorios])
    ep = EntradaPontos(p)
    resolver_padroes(ep, inspecionar(p))
    assert ep.filtro_coluna == "COD_ESPECIE" and ep.filtro_valores == ["1"]
    saida, est = filtrar_pontos_csv(ep, indice)
    assert [f.dados["Territorio"] for f in saida] == ["T01", "T02"]
    assert saida[0].nome == "ESTRADA SÃO JOÃO, 12"
    assert set(saida[0].dados) == {"COD_ESPECIE", "Territorio"}
    assert est.lidas == 6 and est.sem_coordenada == 1 and est.fora == 2 and est.filtradas == 1
    assert est.valores_rurais == {"1": 2, "3": 1}

    # Colunas e nome escolhidos pelo usuário.
    ep2 = EntradaPontos(p, filtro_coluna="", colunas=["DSC_LOCALIDADE"], nome_coluna="COD_UNICO_ENDERECO")
    saida2, est2 = filtrar_pontos_csv(ep2, indice)
    assert [f.nome for f in saida2] == ["1", "3", "4"]
    assert saida2[0].dados == {"DSC_LOCALIDADE": "CÓRREGO FUNDO", "Territorio": "T01"}


def test_modelo_de_nome():
    assert montar_nome("{A} {B}, {C} {D}", {"A": "RUA", "B": "", "C": "0", "D": "SN"}) == "RUA, 0 SN"
    assert montar_nome("{A}, {X}", {"A": "SITIO"}) == "SITIO"
    assert montar_nome("Casa {n}", {}, 7) == "Casa 7"
