"""Linha de comando do Recorta Mapas."""

from __future__ import annotations

import argparse
import sys

from .config import (
    AGRUPAR_SEQUENCIAL, AGRUPAR_TERRITORIO, CAMADA_TERR_NAO, CAMADA_TERR_RESERVAR,
    CAMADA_TERR_SE_COUBER, MODO_CORTAR, MODO_INTEIRA, EntradaLinhas, EntradaPontos, Limites,
    OpcoesCSV, Opcoes,
)
from .formatos import num


def _lista(texto: str | None) -> list[str] | None:
    if texto is None:
        return None
    return [t.strip() for t in texto.split(",") if t.strip()]


def criar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="recorta-mapas",
        description="Prepara camadas de territórios rurais para o Google My Maps "
                    "a partir de dados do Censo 2022 (IBGE). Sem argumentos, abre a janela.",
    )
    g = p.add_argument_group("entradas")
    g.add_argument("--mestre", required=True, help="KML/KMZ com o limite geral da congregação")
    g.add_argument("--territorios", required=True, help="KML/KMZ com os territórios rurais")
    g.add_argument("--campo-id", help="campo do ExtendedData usado como ID quando o nome estiver vazio")
    g.add_argument("--linhas", action="append", default=[], metavar="ARQUIVO",
                   help="camada de linhas (ex.: trajetos dos recenseadores); pode repetir")
    g.add_argument("--prefixo-linhas", action="append", default=[],
                   help="nome base dos arquivos de cada --linhas (padrão: Trajetos)")
    g.add_argument("--pontos", action="append", default=[], metavar="ARQUIVO",
                   help="CSV (ex.: CNEFE) ou KML/KMZ de pontos; pode repetir")
    g.add_argument("--prefixo-pontos", action="append", default=[],
                   help="nome base dos arquivos de cada --pontos (padrão: Casas_rurais)")

    c = p.add_argument_group("CSV de pontos (valem para todos os CSV)")
    c.add_argument("--csv-codificacao", help="ex.: utf-8, latin-1 (padrão: detectar)")
    c.add_argument("--csv-delimitador", help="ex.: ';' (padrão: detectar)")
    c.add_argument("--csv-lat", help="coluna da latitude (padrão: detectar)")
    c.add_argument("--csv-lon", help="coluna da longitude (padrão: detectar)")
    c.add_argument("--filtro-coluna", help="coluna do filtro (CNEFE: COD_ESPECIE)")
    c.add_argument("--filtro-valores", help="valores permitidos separados por vírgula (CNEFE: 1)")
    c.add_argument("--sem-filtro", action="store_true", help="não filtrar os pontos")
    c.add_argument("--colunas", help="colunas que vão para a saída, separadas por vírgula")
    c.add_argument("--nome-coluna", help="coluna usada como nome do ponto")
    c.add_argument("--nome-modelo", help='modelo do nome, ex.: "{NOM_SEGLOGR}, {NUM_ENDERECO}"')
    c.add_argument("--listar-valores", metavar="COLUNA",
                   help="só mostra os valores distintos da coluna no(s) CSV e sai")

    e = p.add_argument_group("processamento")
    e.add_argument("--limiar-perda", type=float, default=2.0,
                   help="%% de área removida acima do qual o território recebe alerta (padrão 2)")
    e.add_argument("--modo-linhas", choices=[MODO_CORTAR, MODO_INTEIRA], default=MODO_CORTAR,
                   help="cortar na borda, ou manter a feição inteira se tocar (padrão: cortar)")
    e.add_argument("--simplificar", type=float, default=0.0, metavar="METROS",
                   help="simplificar as linhas após o recorte (0 = não)")
    e.add_argument("--agrupamento", choices=[AGRUPAR_TERRITORIO, AGRUPAR_SEQUENCIAL],
                   default=AGRUPAR_TERRITORIO,
                   help="territórios inteiros por arquivo, ou blocos sequenciais (padrão: territorio)")
    e.add_argument("--camada-territorios", default=CAMADA_TERR_NAO,
                   choices=[CAMADA_TERR_RESERVAR, CAMADA_TERR_SE_COUBER, CAMADA_TERR_NAO],
                   help="incluir os contornos dos territórios em cada mapa (padrão: nao)")

    s = p.add_argument_group("saída")
    s.add_argument("--saida", required=True, help="pasta de saída")
    s.add_argument("--formato", choices=["kml", "kmz"], default="kml")
    lim = Limites()
    s.add_argument("--max-feicoes-arquivo", type=int, default=lim.max_feicoes_arquivo)
    s.add_argument("--max-mb-arquivo", type=float, default=lim.max_bytes_arquivo / 1e6)
    s.add_argument("--max-camadas-mapa", type=int, default=lim.max_camadas_mapa)
    s.add_argument("--max-feicoes-mapa", type=int, default=lim.max_feicoes_mapa)
    s.add_argument("--max-vertices-mapa", type=int, default=lim.max_vertices_mapa)
    s.add_argument("--max-celulas-mapa", type=int, default=lim.max_celulas_mapa)
    return p


def opcoes_de_args(a) -> Opcoes:
    csv_op = OpcoesCSV(a.csv_codificacao, a.csv_delimitador, a.csv_lat, a.csv_lon)
    linhas = [EntradaLinhas(c, a.prefixo_linhas[i] if i < len(a.prefixo_linhas) else "Trajetos")
              for i, c in enumerate(a.linhas)]
    pontos = []
    for i, c in enumerate(a.pontos):
        ep = EntradaPontos(c, a.prefixo_pontos[i] if i < len(a.prefixo_pontos) else "Casas_rurais",
                           csv=OpcoesCSV(**vars(csv_op)))
        if a.sem_filtro:
            ep.filtro_coluna = ""
        elif a.filtro_coluna:
            ep.filtro_coluna = a.filtro_coluna
            ep.filtro_valores = _lista(a.filtro_valores) or []
        ep.colunas = _lista(a.colunas)
        ep.nome_coluna = a.nome_coluna
        ep.nome_modelo = a.nome_modelo
        pontos.append(ep)
    lim = Limites(a.max_feicoes_arquivo, int(a.max_mb_arquivo * 1e6), a.max_camadas_mapa,
                  a.max_feicoes_mapa, a.max_vertices_mapa, a.max_celulas_mapa)
    return Opcoes(
        mapa_mestre=a.mestre, territorios=a.territorios, saida=a.saida, linhas=linhas, pontos=pontos,
        campo_id=a.campo_id, limiar_perda_pct=a.limiar_perda, modo_linhas=a.modo_linhas,
        simplificar_m=a.simplificar, formato=a.formato, agrupamento=a.agrupamento,
        camada_territorios=a.camada_territorios, limites=lim,
    )


def _listar_valores(a) -> int:
    from .io_csv import inspecionar, valores_distintos
    for caminho in a.pontos:
        info = inspecionar(caminho, OpcoesCSV(a.csv_codificacao, a.csv_delimitador, a.csv_lat, a.csv_lon))
        if a.listar_valores not in info.colunas:
            print(f"Coluna '{a.listar_valores}' não existe em {caminho}. Colunas: {', '.join(info.colunas)}")
            return 2
        print(f"{caminho}  (codificação {info.opcoes.codificacao}, delimitador '{info.opcoes.delimitador}')")
        cont = valores_distintos(caminho, info.opcoes, a.listar_valores)
        for v, n in sorted(cont.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {v or '(vazio)':<20} {num(n):>12}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for fluxo in (sys.stdout, sys.stderr):
        # Console do Windows redirecionado usa cp1252: não travar em caracteres especiais.
        if fluxo is not None and hasattr(fluxo, "reconfigure"):
            try:
                fluxo.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
    if not argv:
        from .gui.app import main as gui_main
        gui_main()
        return 0
    if "--listar-valores" in argv:
        # Para listar valores só são necessários os pontos.
        p = argparse.ArgumentParser(add_help=False)
        for arg in ("--csv-codificacao", "--csv-delimitador", "--csv-lat", "--csv-lon", "--listar-valores"):
            p.add_argument(arg)
        p.add_argument("--pontos", action="append", default=[])
        a, _ = p.parse_known_args(argv)
        return _listar_valores(a)
    a = criar_parser().parse_args(argv)
    from .pipeline import executar
    try:
        r = executar(opcoes_de_args(a), progresso=lambda m: print(m, file=sys.stderr))
    except Exception as e:  # mensagens de erro já em português
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print(r.relatorio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
