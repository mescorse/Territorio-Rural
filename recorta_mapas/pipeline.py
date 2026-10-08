"""Orquestra: etapa 1 -> etapa 2 -> divisão -> plano de mapas -> gravação -> relatório.
Usado igualmente pela interface gráfica e pela linha de comando."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from typing import Callable

from .atributos import resolver_padroes
from .config import Opcoes
from .divisao import Categoria
from .etapa1_ajuste import ResultadoEtapa1, ajustar
from .etapa2_recorte import EstatEntrada, filtrar_pontos_csv, filtrar_pontos_kml, recortar_linhas
from .formatos import nome_arquivo
from .geo.indice import IndiceTerritorios
from .io_csv import inspecionar
from .io_kml.escritor import gravar, recursos_usados
from .io_kml.leitor import ler_camada
from .planejamento import Plano, planejar
from . import relatorio

NOME_TERRITORIOS = "Territorios_rurais"
NOME_RELATORIO = "relatorio.txt"


@dataclass
class Resultado:
    etapa1: ResultadoEtapa1
    estatisticas: list[EstatEntrada]
    plano: Plano
    relatorio: str
    pasta_saida: str


def _eh_csv(caminho: str) -> bool:
    return os.path.splitext(caminho)[1].lower() in (".csv", ".txt", ".tsv")


def _prefixo_unico(prefixo: str, usados: set[str]) -> str:
    base = nome_arquivo(prefixo)
    p, n = base, 2
    while p in usados or p == NOME_TERRITORIOS:
        p = f"{base}_{n}"
        n += 1
    usados.add(p)
    return p


def _limpar_saida(pasta: str) -> None:
    """Remove somente o que o próprio programa gera, para não misturar com execuções antigas."""
    if not os.path.isdir(pasta):
        return
    for nome in os.listdir(pasta):
        caminho = os.path.join(pasta, nome)
        if os.path.isdir(caminho) and re.fullmatch(r"Mapa_\d+", nome):
            shutil.rmtree(caminho)
        elif nome in (NOME_RELATORIO, f"{NOME_TERRITORIOS}.kml", f"{NOME_TERRITORIOS}.kmz"):
            os.remove(caminho)


def executar(op: Opcoes, progresso: Callable[[str], None] | None = None) -> Resultado:
    avisar = progresso or (lambda m: None)

    avisar("Lendo o mapa-mestre e os territórios rurais...")
    mestre = ler_camada(op.mapa_mestre)
    terr = ler_camada(op.territorios)

    avisar("Etapa 1: ajustando os territórios rurais ao mapa-mestre...")
    e1 = ajustar(mestre, terr, op.campo_id, op.limiar_perda_pct, op.tolerancia_sobreposicao_m2)
    ids = [f.territorio for f in e1.territorios]
    indice = IndiceTerritorios(ids, [f.geom for f in e1.territorios])
    projecao = e1.projecao

    cats: list[Categoria] = []
    ests: list[EstatEntrada] = []
    avisos: list[str] = []
    usados: set[str] = set()
    for el in op.linhas:
        nome = os.path.basename(el.caminho)
        avisar(f"Etapa 2: recortando linhas de {nome}...")
        camada = ler_camada(el.caminho)
        prefixo = _prefixo_unico(el.prefixo, usados)
        feicoes, est = recortar_linhas(camada, prefixo, indice, projecao, op.modo_linhas, op.simplificar_m)
        est.nome = nome
        ests.append(est)
        cats.append(Categoria(prefixo, prefixo, feicoes, camada.estilos, camada.recursos))
    for ep in op.pontos:
        nome = os.path.basename(ep.caminho)
        avisar(f"Etapa 2: filtrando pontos de {nome}...")
        prefixo = _prefixo_unico(ep.prefixo, usados)
        if _eh_csv(ep.caminho):
            info = inspecionar(ep.caminho, ep.csv)
            ep.csv = info.opcoes
            avisos.extend(resolver_padroes(ep, info))
            ep.prefixo = prefixo
            feicoes, est = filtrar_pontos_csv(ep, indice)
            cats.append(Categoria(prefixo, prefixo, feicoes))
        else:
            camada = ler_camada(ep.caminho)
            feicoes, est = filtrar_pontos_kml(camada, prefixo, indice)
            est.nome = nome
            cats.append(Categoria(prefixo, prefixo, feicoes, camada.estilos, camada.recursos))
        ests.append(est)

    terr_cat = Categoria(NOME_TERRITORIOS, NOME_TERRITORIOS, e1.territorios, terr.estilos, terr.recursos)
    for c in cats + [terr_cat]:
        c.preparar()

    avisar("Dividindo em arquivos e planejando os mapas...")
    lim = op.limites
    fatores: dict[str, float] = {}
    for _ in range(8):
        plano = planejar(cats, ids, terr_cat, lim, op.agrupamento, op.camada_territorios, fatores)
        excedidos = []
        for m in plano.mapas:
            for a in m.arquivos:
                a.gerar()
                if a.bytes_reais > lim.max_bytes_arquivo and len(a.feicoes) > 1:
                    excedidos.append(a)
        if not plano.territorios.kml:
            plano.territorios.gerar()
        if not excedidos:
            break
        for a in excedidos:
            p = a.categoria.prefixo
            fatores[p] = fatores.get(p, 1.0) * lim.max_bytes_arquivo / a.bytes_reais * 0.97

    avisar("Gravando os arquivos...")
    os.makedirs(op.saida, exist_ok=True)
    _limpar_saida(op.saida)
    ext = "." + op.formato

    def gravar_arquivo(pasta, a):
        rec = recursos_usados(a.feicoes, a.categoria.estilos, a.categoria.recursos)
        gravar(os.path.join(pasta, a.nome + ext), a.kml, rec, op.formato)

    gravar_arquivo(op.saida, plano.territorios)
    for m in plano.mapas:
        pasta = os.path.join(op.saida, m.pasta)
        for a in m.arquivos:
            gravar_arquivo(pasta, a)

    texto = relatorio.gerar(op, e1, ests, plano, avisos)
    with open(os.path.join(op.saida, NOME_RELATORIO), "w", encoding="utf-8") as f:
        f.write(texto)
    avisar("Concluído.")
    return Resultado(e1, ests, plano, texto, op.saida)
