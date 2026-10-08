"""Etapa 1: ajustar os territórios rurais ao mapa-mestre."""

from __future__ import annotations

from dataclasses import dataclass, field

import shapely

from .formatos import num
from .geo.projecao import Projecao
from .geo.validacao import POLIGONO, corrigir, extrair, tipo_de
from .modelos import Camada, Feicao, chave_natural


class ErroEtapa1(Exception):
    pass


@dataclass
class LinhaTerritorio:
    id: str
    area_antes_ha: float
    area_depois_ha: float
    pct_removido: float
    alerta: bool
    removido: bool = False      # ficou totalmente fora do mapa-mestre


@dataclass
class ResultadoEtapa1:
    territorios: list[Feicao]                   # ajustados, em ordem natural de ID
    linhas: list[LinhaTerritorio]
    sobreposicoes: list[tuple[str, str, float]]  # (id1, id2, área m²)
    projecao: Projecao
    correcoes_mestre: int = 0
    correcoes_territorios: int = 0
    avisos: list[str] = field(default_factory=list)


def uniao_mestre(mestre: Camada) -> tuple[object, int]:
    polis, correcoes = [], 0
    for f in mestre.feicoes:
        if tipo_de(f.geom) != POLIGONO:
            g = extrair(f.geom, POLIGONO)
            if g.is_empty:
                continue
        else:
            g = f.geom
        g, c = corrigir(g, POLIGONO)
        correcoes += c
        if not g.is_empty:
            polis.append(g)
    if not polis:
        raise ErroEtapa1("O mapa-mestre não contém nenhum polígono.")
    return extrair(shapely.union_all(polis), POLIGONO), correcoes


def _ids(territorios: list[Feicao], campo_id: str | None, avisos: list[str]) -> list[str]:
    ids, usados = [], set()
    for i, f in enumerate(territorios, 1):
        id_ = f.nome.strip()
        if not id_ and campo_id:
            id_ = (f.dados.get(campo_id) or "").strip()
        if not id_:
            id_ = f"T{i:02d}"
            avisos.append(f"Território sem nome na posição {i}: recebeu o ID {id_}.")
        if id_ in usados:
            n = 2
            while f"{id_}_{n}" in usados:
                n += 1
            avisos.append(f"ID de território repetido '{id_}': renomeado para '{id_}_{n}'.")
            id_ = f"{id_}_{n}"
        usados.add(id_)
        ids.append(id_)
    return ids


def ajustar(mestre: Camada, territorios: Camada, campo_id: str | None = None,
            limiar_pct: float = 2.0, tolerancia_sobreposicao_m2: float = 1.0) -> ResultadoEtapa1:
    limite, corr_mestre = uniao_mestre(mestre)
    projecao = Projecao.para_geometria(limite)
    shapely.prepare(limite)

    avisos: list[str] = []
    polis = [f for f in territorios.feicoes if tipo_de(extrair(f.geom, POLIGONO)) == POLIGONO]
    ignoradas = len(territorios.feicoes) - len(polis)
    if ignoradas:
        avisos.append(f"{ignoradas} feição(ões) não poligonais no mapa de territórios foram ignoradas.")
    if not polis:
        raise ErroEtapa1("O mapa de territórios rurais não contém nenhum polígono.")
    ids = _ids(polis, campo_id, avisos)

    corr_terr = 0
    linhas, ajustados = [], []
    for id_, f in zip(ids, polis):
        g = extrair(f.geom, POLIGONO)
        g, c = corrigir(g, POLIGONO)
        corr_terr += c
        antes = projecao.area_ha(g)
        depois_g = extrair(g.intersection(limite), POLIGONO)
        depois = projecao.area_ha(depois_g)
        pct = 100.0 * (antes - depois) / antes if antes > 0 else 100.0
        pct = max(pct, 0.0)
        removido = depois_g.is_empty
        alerta = pct > limiar_pct
        linhas.append(LinhaTerritorio(id_, antes, depois, pct, alerta, removido))
        if removido:
            avisos.append(f"Território {id_} está totalmente fora do mapa-mestre e foi descartado.")
            continue
        if alerta:
            avisos.append(f"Território {id_} perdeu {num(pct, 1)}% da área no recorte "
                          f"(limite {num(limiar_pct, 1)}%): provável erro de desenho.")
        dados = dict(f.dados)
        ajustados.append(Feicao(
            geom=depois_g, nome=id_, descricao=f.descricao, estilo_url=f.estilo_url,
            estilo_inline=f.estilo_inline, dados=dados, pasta=f.pasta, territorio=id_,
        ))

    ajustados.sort(key=lambda f: chave_natural(f.territorio))
    linhas.sort(key=lambda l: chave_natural(l.id))

    sobreposicoes = []
    metricos = [projecao.para_metros(f.geom) for f in ajustados]
    arvore = shapely.STRtree(metricos)
    a, b = arvore.query(metricos, predicate="intersects")
    for i, j in zip(a, b):
        if i >= j:
            continue
        area = metricos[i].intersection(metricos[j]).area
        if area > tolerancia_sobreposicao_m2:
            sobreposicoes.append((ajustados[i].territorio, ajustados[j].territorio, area))
    for t1, t2, area in sobreposicoes:
        avisos.append(f"Territórios {t1} e {t2} se sobrepõem em {num(area)} m².")
    return ResultadoEtapa1(ajustados, linhas, sobreposicoes, projecao, corr_mestre, corr_terr, avisos)
