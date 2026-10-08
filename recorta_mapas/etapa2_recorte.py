"""Etapa 2: os territórios rurais ajustados são o único limite de recorte."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import shapely

from .atributos import montar_nome
from .config import ATRIBUTO_TERRITORIO, MODO_CORTAR, MODO_INTEIRA, EntradaPontos
from .geo.indice import IndiceTerritorios
from .geo.projecao import Projecao
from .geo.validacao import LINHA, PONTO, corrigir, extrair
from .io_csv import inspecionar, linhas as linhas_csv, numero
from .modelos import Camada, Feicao


class ErroEtapa2(Exception):
    pass


@dataclass
class EstatEntrada:
    nome: str
    tipo: str                       # "linhas" ou "pontos"
    prefixo: str
    lidas: int = 0
    saida: int = 0                  # feições geradas
    inteiras: int = 0               # entraram sem corte
    cortadas: int = 0               # foram aparadas na borda (ou divididas)
    fora: int = 0                   # descartadas: fora de todos os territórios rurais
    filtradas: int = 0              # descartadas pelo filtro (ex.: espécie)
    sem_coordenada: int = 0
    corrigidas: int = 0
    ignoradas: int = 0              # tipo de geometria diferente
    na_divisa: int = 0              # pontos em divisa/sobreposição (atribuídos ao 1º)
    varios_territorios: int = 0     # linhas que tocam mais de um território
    vertices_antes: int = 0
    vertices_depois: int = 0
    km_lidos: float = 0.0
    km_mantidos: float = 0.0
    por_territorio: Counter = field(default_factory=Counter)   # casas (n) ou km
    filtro_coluna: str | None = None
    filtro_valores: list[str] = field(default_factory=list)
    valores_total: Counter = field(default_factory=Counter)
    valores_rurais: Counter = field(default_factory=Counter)
    colunas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _copiar(f: Feicao, geom, territorio: str) -> Feicao:
    dados = dict(f.dados)
    dados[ATRIBUTO_TERRITORIO] = territorio
    return Feicao(geom=geom, nome=f.nome, descricao=f.descricao, estilo_url=f.estilo_url,
                  estilo_inline=f.estilo_inline, dados=dados, pasta=f.pasta, territorio=territorio)


def recortar_linhas(camada: Camada, prefixo: str, indice: IndiceTerritorios, projecao: Projecao,
                    modo: str = MODO_CORTAR, simplificar_m: float = 0.0):
    est = EstatEntrada(camada.nome, "linhas", prefixo)
    est.ignoradas = camada.geometrias_ignoradas
    saida: list[Feicao] = []
    for f in camada.feicoes:
        est.lidas += 1
        g = extrair(f.geom, LINHA)
        if g.is_empty:
            est.ignoradas += 1
            continue
        if not g.is_valid:
            g, c = corrigir(g, LINHA)
            est.corrigidas += c
            if g.is_empty:
                est.ignoradas += 1
                continue
        est.vertices_antes += shapely.get_num_coordinates(g)
        est.km_lidos += projecao.comprimento_km(g)
        cands = indice.candidatos(g)
        if not cands:
            est.fora += 1
            continue
        pecas: list[tuple[int, object]] = []
        if modo == MODO_INTEIRA:
            comprimentos = [g.intersection(indice.geoms[t]).length for t in cands]
            melhor = cands[int(np.argmax(comprimentos))]
            pecas.append((melhor, g))
            est.inteiras += 1
            if len(cands) > 1:
                est.varios_territorios += 1
        else:
            restante = g
            for t in cands:
                terr = indice.geoms[t]
                if terr.contains(restante):
                    pecas.append((t, restante))
                    restante = None
                    break
                p = extrair(restante.intersection(terr), LINHA)
                if not p.is_empty:
                    pecas.append((t, p))
                    restante = extrair(restante.difference(terr), LINHA)
                    if restante.is_empty:
                        restante = None
                        break
            if not pecas:
                est.fora += 1
                continue
            if len(pecas) == 1 and pecas[0][1] is g:
                est.inteiras += 1
            else:
                est.cortadas += 1
            if len(pecas) > 1:
                est.varios_territorios += 1
        for t, p in pecas:
            if simplificar_m > 0:
                p = extrair(projecao.simplificar(p, simplificar_m), LINHA)
                if p.is_empty:
                    continue
            nova = _copiar(f, p, indice.ids[t])
            saida.append(nova)
            km = projecao.comprimento_km(p)
            est.km_mantidos += km
            est.por_territorio[indice.ids[t]] += km
            est.vertices_depois += shapely.get_num_coordinates(p)
    est.saida = len(saida)
    est.colunas = _colunas_uniao(saida)
    return saida, est


def _colunas_uniao(feicoes) -> list[str]:
    cols: dict[str, None] = {}
    for f in feicoes:
        for k in f.dados:
            cols.setdefault(k, None)
    return list(cols)


def filtrar_pontos_kml(camada: Camada, prefixo: str, indice: IndiceTerritorios):
    est = EstatEntrada(camada.nome, "pontos", prefixo)
    est.ignoradas = camada.geometrias_ignoradas
    pontos = []
    for f in camada.feicoes:
        est.lidas += 1
        g = extrair(f.geom, PONTO)
        if g.is_empty:
            est.ignoradas += 1
            continue
        p = g if g.geom_type == "Point" else g.geoms[0]
        pontos.append((f, p))
    xs = [p.x for _, p in pontos]
    ys = [p.y for _, p in pontos]
    idx, cont = indice.localizar_pontos(xs, ys)
    saida = []
    for (f, p), i, c in zip(pontos, idx, cont):
        if i < 0:
            est.fora += 1
            continue
        if c > 1:
            est.na_divisa += 1
        t = indice.ids[i]
        saida.append(_copiar(f, p, t))
        est.por_territorio[t] += 1
    est.inteiras = est.saida = len(saida)
    est.vertices_antes = len(pontos)
    est.vertices_depois = len(saida)
    est.colunas = _colunas_uniao(saida)
    return saida, est


def filtrar_pontos_csv(entrada: EntradaPontos, indice: IndiceTerritorios, bloco: int = 50_000):
    """Lê o CSV em blocos; mantém só os pontos dentro de um território rural que passam no filtro."""
    from os.path import basename

    info = inspecionar(entrada.caminho, entrada.csv)
    op = info.opcoes
    est = EstatEntrada(basename(entrada.caminho), "pontos", entrada.prefixo)
    filtro_col = entrada.filtro_coluna or None
    if filtro_col and filtro_col not in info.colunas:
        raise ErroEtapa2(f"Coluna do filtro '{filtro_col}' não existe no CSV {est.nome}.")
    permitidos = {v.strip() for v in entrada.filtro_valores} if filtro_col else None
    colunas = [c for c in (entrada.colunas or []) if c in info.colunas]
    faltando = [c for c in (entrada.colunas or []) if c not in info.colunas]
    if faltando:
        est.avisos.append(f"{est.nome}: colunas ignoradas (não existem): {', '.join(faltando)}")
    est.filtro_coluna = filtro_col
    est.filtro_valores = sorted(permitidos) if permitidos else []
    est.colunas = colunas + [ATRIBUTO_TERRITORIO]

    saida: list[Feicao] = []
    buffer: list[tuple[dict, float, float]] = []

    def processar():
        if not buffer:
            return
        idx, cont = indice.localizar_pontos([b[1] for b in buffer], [b[2] for b in buffer])
        for (linha, lon, lat), i, c in zip(buffer, idx, cont):
            if i < 0:
                est.fora += 1
                continue
            valor = (linha.get(filtro_col) or "").strip() if filtro_col else ""
            if filtro_col:
                est.valores_rurais[valor] += 1
                if valor not in permitidos:
                    est.filtradas += 1
                    continue
            if c > 1:
                est.na_divisa += 1
            t = indice.ids[i]
            n = len(saida) + 1
            if entrada.nome_coluna:
                nome = (linha.get(entrada.nome_coluna) or "").strip()
            else:
                nome = montar_nome(entrada.nome_modelo or "Ponto {n}", linha, n)
            dados = {c2: (linha.get(c2) or "").strip() for c2 in colunas}
            dados[ATRIBUTO_TERRITORIO] = t
            saida.append(Feicao(geom=shapely.Point(lon, lat), nome=nome, dados=dados, territorio=t))
            est.por_territorio[t] += 1
        buffer.clear()

    for linha in linhas_csv(entrada.caminho, op):
        est.lidas += 1
        if filtro_col:
            est.valores_total[(linha.get(filtro_col) or "").strip()] += 1
        lat = numero(linha.get(op.coluna_lat))
        lon = numero(linha.get(op.coluna_lon))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            est.sem_coordenada += 1
            continue
        buffer.append((linha, lon, lat))
        if len(buffer) >= bloco:
            processar()
    processar()
    est.inteiras = est.saida = len(saida)
    est.vertices_antes = est.lidas - est.sem_coordenada
    est.vertices_depois = len(saida)
    return saida, est
