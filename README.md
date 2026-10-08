# Territorio-Rural — Recorta Mapas

Programa local (Windows primeiro) que prepara as camadas dos **territórios rurais** da congregação
para o **Google My Maps**, a partir dos dados do Censo 2022 do IBGE.

## O que ele faz

**Etapa 1 — ajustar os territórios rurais ao mapa-mestre**
- Recorta cada território rural pelo mapa-mestre (limite geral da congregação), mantendo nome, estilo e ExtendedData.
- Relatório da área antes/depois (ha) e % removido; alerta quando a perda passa do limite (padrão 2%),
  que costuma indicar erro de desenho; aponta territórios que se sobrepõem (vãos entre eles são normais).
- Gera a camada `Territorios_rurais.kml`.

**Etapa 2 — os territórios rurais ajustados viram o único limite de recorte**
- **Linhas** (ex.: “Trajetos dos recenseadores”): ficam só as partes dentro de um território rural, com o
  atributo `Territorio`. Opções: *cortar na borda* ou *manter a feição inteira se tocar* (vai para o
  território onde está a maior parte). Simplificação opcional em metros.
- **Pontos** (ex.: CSV do CNEFE 2022 ou KML/KMZ): ficam só os pontos dentro de um território rural.
  Pontos na divisa vão para o primeiro território (ordem natural T1, T2, … T10) e são contados.
- **Filtro do CSV**: no CNEFE o padrão é `COD_ESPECIE = 1` (domicílio particular). O programa mostra todos os
  valores encontrados para você conferir no dicionário de dados do IBGE.
- Tudo o que fica fora dos territórios rurais (áreas urbanas) é descartado.

**Divisão para o My Maps**, com o menor número possível de mapas e de arquivos para importar:
- por arquivo (= uma camada): até 1.900 feições e 4,5 MB de KML;
- por mapa: até 10 camadas, 9.500 feições, 45.000 vértices e 18.000 células da tabela
  (feições × colunas; nas casas é este limite que costuma pesar — menos colunas = mais casas por mapa);
- territórios inteiros por arquivo quando cabem; território grande demais é dividido em partes;
- saída em pastas `Mapa_01/`, `Mapa_02/`… — cada arquivo é uma camada a importar naquele mapa.

## Instalação

Requer Python 3.11 ou mais novo.

```
pip install -e .
```

## Uso

Janela (sem argumentos):

```
python -m recorta_mapas
```

Linha de comando:

```
python -m recorta_mapas --mestre Congregacao.kmz --territorios Rurais.kmz ^
    --linhas Trajetos.kmz --pontos CNEFE_5300108.csv --saida C:\Mapas\saida
```

Ver os valores de uma coluna do CSV antes de escolher o filtro:

```
python -m recorta_mapas --pontos CNEFE_5300108.csv --listar-valores COD_ESPECIE
```

Principais opções: `--modo-linhas cortar|inteira`, `--simplificar METROS`, `--filtro-coluna`,
`--filtro-valores 1,2`, `--sem-filtro`, `--colunas COD_ESPECIE,DSC_LOCALIDADE`, `--nome-coluna`,
`--nome-modelo "{NOM_SEGLOGR}, {NUM_ENDERECO}"`, `--agrupamento territorio|sequencial`,
`--camada-territorios reservar|se_couber|nao`, `--formato kml|kmz` e os limites (`--max-...`).
Veja todas com `python -m recorta_mapas --help`.

Na pasta de saída ficam `relatorio.txt`, `Territorios_rurais.kml` e as pastas `Mapa_XX`.
Ao rodar de novo na mesma pasta, as pastas `Mapa_XX` antigas são apagadas.

## Testes

```
pip install -e .[dev]
pytest
```

## Executável para Windows (PyInstaller)

```
pip install pyinstaller
pyinstaller --onefile --windowed --name RecortaMapas --collect-data pyproj recorta_mapas_app.py
```
