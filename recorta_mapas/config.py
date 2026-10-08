"""Opções do processamento, compartilhadas pela interface gráfica e pela linha de comando."""

from __future__ import annotations

from dataclasses import dataclass, field

# Valores padrão do CNEFE 2022 (Cadastro Nacional de Endereços para Fins Estatísticos).
CNEFE_COLUNA_ESPECIE = "COD_ESPECIE"
CNEFE_ESPECIE_DOMICILIO_PARTICULAR = "1"
CNEFE_MODELO_ENDERECO = (
    "{NOM_TIPO_SEGLOGR} {NOM_TITULO_SEGLOGR} {NOM_SEGLOGR}, {NUM_ENDERECO} {DSC_MODIFICADOR}"
)
CNEFE_COLUNAS_PADRAO = ["COD_ESPECIE"]

ATRIBUTO_TERRITORIO = "Territorio"

MODO_CORTAR = "cortar"          # cortar na borda
MODO_INTEIRA = "inteira"        # manter feição inteira se tocar

AGRUPAR_TERRITORIO = "territorio"   # territórios inteiros por arquivo quando couberem
AGRUPAR_SEQUENCIAL = "sequencial"   # blocos sequenciais, preenchendo ao máximo

CAMADA_TERR_RESERVAR = "reservar"   # sempre incluir em cada mapa, reservando espaço
CAMADA_TERR_SE_COUBER = "se_couber"  # incluir só nos mapas onde sobrar espaço
CAMADA_TERR_NAO = "nao"             # não incluir nos mapas (só na pasta principal)


@dataclass
class Limites:
    """Limites do Google My Maps, já com margem de segurança."""

    max_feicoes_arquivo: int = 1900
    max_bytes_arquivo: int = 4_500_000
    max_camadas_mapa: int = 10
    max_feicoes_mapa: int = 9500
    max_vertices_mapa: int = 45_000
    max_celulas_mapa: int = 18_000
    # Aviso quando um valor passa desta fração do limite.
    fracao_aviso: float = 0.95


@dataclass
class OpcoesCSV:
    """Como ler um CSV de pontos. Campos None são detectados automaticamente."""

    codificacao: str | None = None
    delimitador: str | None = None
    coluna_lat: str | None = None
    coluna_lon: str | None = None


@dataclass
class EntradaPontos:
    caminho: str
    prefixo: str = "Casas_rurais"
    csv: OpcoesCSV | None = None            # None para KML/KMZ
    # Filtro: coluna e valores permitidos. coluna None = sem filtro.
    filtro_coluna: str | None = None
    filtro_valores: list[str] = field(default_factory=list)
    # Colunas do CSV que vão para a saída (além de "Territorio").
    colunas: list[str] | None = None
    # Nome do ponto: coluna OU modelo como "{NOM_SEGLOGR}, {NUM_ENDERECO}".
    nome_coluna: str | None = None
    nome_modelo: str | None = None


@dataclass
class EntradaLinhas:
    caminho: str
    prefixo: str = "Trajetos"


@dataclass
class Opcoes:
    mapa_mestre: str
    territorios: str
    saida: str
    linhas: list[EntradaLinhas] = field(default_factory=list)
    pontos: list[EntradaPontos] = field(default_factory=list)
    campo_id: str | None = None             # campo do ExtendedData se o nome estiver vazio
    limiar_perda_pct: float = 2.0
    tolerancia_sobreposicao_m2: float = 1.0
    modo_linhas: str = MODO_CORTAR
    simplificar_m: float = 0.0              # 0 = não simplificar
    formato: str = "kml"                    # "kml" ou "kmz"
    agrupamento: str = AGRUPAR_TERRITORIO
    camada_territorios: str = CAMADA_TERR_RESERVAR
    limites: Limites = field(default_factory=Limites)
