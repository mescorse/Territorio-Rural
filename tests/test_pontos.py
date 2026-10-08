from conftest import documento, escrever, placemark, ponto_xml
from recorta_mapas.etapa1_ajuste import ajustar
from recorta_mapas.etapa2_recorte import filtrar_pontos_kml
from recorta_mapas.geo.indice import IndiceTerritorios
from recorta_mapas.io_kml.leitor import ler_camada


def _indice(dados):
    r = ajustar(ler_camada(dados["mestre"]), ler_camada(dados["territorios"]))
    return IndiceTerritorios([f.territorio for f in r.territorios], [f.geom for f in r.territorios])


def test_pontos_rural_urbano_fora_e_divisa(dados, tmp_path):
    pontos = {
        "rural_T01": (-47.08, -15.08),
        "rural_T02": (-47.02, -15.08),
        "urbano": (-47.08, -15.02),          # dentro do mestre, fora dos rurais
        "fora_mestre": (-46.90, -15.08),
        "divisa": (-47.05, -15.07),          # divisa T01/T02
        "T03_aparado": (-46.99, -15.03),     # dentro do T03 original, fora do mestre
    }
    corpo = "".join(placemark(n, ponto_xml(x, y), dados={"id": n}) for n, (x, y) in pontos.items())
    camada = ler_camada(escrever(tmp_path / "p.kml", documento(corpo)))
    saida, est = filtrar_pontos_kml(camada, "Casas", _indice(dados))
    por_nome = {f.nome: f for f in saida}
    assert set(por_nome) == {"rural_T01", "rural_T02", "divisa"}
    assert por_nome["rural_T01"].dados["Territorio"] == "T01"
    assert por_nome["rural_T02"].dados["Territorio"] == "T02"
    assert por_nome["divisa"].territorio == "T01"   # primeiro na ordem
    assert por_nome["divisa"].dados["id"] == "divisa"  # ExtendedData preservado
    assert est.na_divisa == 1
    assert est.fora == 3
    assert est.lidas == 6
    assert est.por_territorio == {"T01": 2, "T02": 1}
