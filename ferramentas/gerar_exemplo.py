"""Gera uma pasta com dados de exemplo para experimentar o Recorta Mapas.

Uso: python ferramentas/gerar_exemplo.py [pasta]   (padrão: exemplo)

Cria: mapa_mestre.kml, territorios_rurais.kml (8 territórios, um deles saindo do
mapa-mestre de propósito), trajetos.kml e cnefe_exemplo.csv (';' e Latin-1, como o IBGE).
"""

import os
import random
import sys

NS = 'xmlns="http://www.opengis.net/kml/2.2"'


def anel(x0, y0, x1, y1):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return " ".join(f"{x:.6f},{y:.6f},0" for x, y in pts)


def doc(nome, corpo, estilos=""):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<kml {NS}><Document><name>{nome}</name>'
            f"{estilos}{corpo}</Document></kml>\n")


def poligono(nome, coords, estilo=None):
    s = f"<Placemark><name>{nome}</name>"
    if estilo:
        s += f"<styleUrl>#{estilo}</styleUrl>"
    return s + (f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates>"
                "</LinearRing></outerBoundaryIs></Polygon></Placemark>")


def main(pasta="exemplo"):
    os.makedirs(pasta, exist_ok=True)
    rnd = random.Random(2022)
    # Mapa-mestre: ~22 x 22 km perto de Brasília. Cidade no centro (urbano).
    X0, Y0, X1, Y1 = -47.90, -15.90, -47.70, -15.70
    with open(os.path.join(pasta, "mapa_mestre.kml"), "w", encoding="utf-8") as f:
        f.write(doc("Congregação (exemplo)", poligono("Congregação", anel(X0, Y0, X1, Y1))))

    estilo = ('<Style id="rural"><LineStyle><color>ff00aa00</color><width>2</width></LineStyle>'
              '<PolyStyle><color>3300aa00</color></PolyStyle></Style>')
    terrs = {}
    n = 1
    for j in range(2):          # duas faixas: sul e norte, deixando a cidade no meio
        y0 = Y0 if j == 0 else Y1 - 0.06
        for i in range(4):
            x0 = X0 + 0.05 * i
            x1 = x0 + 0.05 + (0.01 if n == 8 else 0)   # T08 sai 0,01° do mapa-mestre
            terrs[f"T{n:02d}"] = (x0, y0, x1, y0 + 0.06)
            n += 1
    with open(os.path.join(pasta, "territorios_rurais.kml"), "w", encoding="utf-8") as f:
        corpo = "<Folder><name>Rurais</name>" + "".join(
            poligono(t, anel(*b), "rural") for t, b in terrs.items()) + "</Folder>"
        f.write(doc("Territórios rurais (exemplo)", corpo, estilo))

    rotas = []
    for k in range(120):
        x, y = rnd.uniform(X0, X1), rnd.uniform(Y0, Y1)
        pts = []
        for _ in range(80):
            x += rnd.uniform(-0.0006, 0.0012)
            y += rnd.uniform(-0.0008, 0.0008)
            pts.append(f"{x:.6f},{y:.6f},0")
        rotas.append(f"<Placemark><name>Trajeto {k + 1}</name><ExtendedData>"
                     f'<Data name="CD_SETOR"><value>53001080500{k:04d}</value></Data></ExtendedData>'
                     f"<LineString><coordinates>{' '.join(pts)}</coordinates></LineString></Placemark>")
    with open(os.path.join(pasta, "trajetos.kml"), "w", encoding="utf-8") as f:
        f.write(doc("Trajetos dos recenseadores (exemplo)", "".join(rotas)))

    cab = ("COD_UNICO_ENDERECO;COD_UF;COD_MUNICIPIO;COD_SETOR;CEP;DSC_LOCALIDADE;NOM_TIPO_SEGLOGR;"
           "NOM_TITULO_SEGLOGR;NOM_SEGLOGR;NUM_ENDERECO;DSC_MODIFICADOR;LATITUDE;LONGITUDE;"
           "NV_GEO_COORD;COD_ESPECIE;DSC_ESTABELECIMENTO")
    localidades = ["CÓRREGO DO ARROZ", "SÃO JOÃO", "CAPÃO SECO", "TABOQUINHA", "MONJOLO"]
    especies = "1" * 14 + "2345678"
    linhas = [cab]
    for k in range(12000):
        lat, lon = rnd.uniform(Y0 - 0.02, Y1 + 0.02), rnd.uniform(X0 - 0.02, X1 + 0.02)
        esp = rnd.choice(especies)
        linhas.append(";".join([
            str(530010800000000 + k), "53", "5300108", f"53001080500{k % 120:04d}", "70000000",
            rnd.choice(localidades), rnd.choice(["ESTRADA", "RODOVIA", "RUA"]), "",
            f"VICINAL {rnd.randint(1, 40)}", str(rnd.randint(0, 900)), rnd.choice(["", "", "SN"]),
            f"{lat:.7f}".replace(".", ","), f"{lon:.7f}".replace(".", ","), "1", esp,
            "IGREJA" if esp == "8" else ""]))
    with open(os.path.join(pasta, "cnefe_exemplo.csv"), "wb") as f:
        f.write(("\n".join(linhas) + "\n").encode("latin-1"))
    print(f"Dados de exemplo gravados em {os.path.abspath(pasta)}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
