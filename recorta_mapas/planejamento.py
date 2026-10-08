"""Plano de mapas: distribui os arquivos (camadas) em Mapa_01, Mapa_02, ...
respeitando os limites do Google My Maps, com o menor número de mapas e de arquivos."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .config import (
    AGRUPAR_SEQUENCIAL, CAMADA_TERR_NAO, CAMADA_TERR_RESERVAR, CAMADA_TERR_SE_COUBER, Limites,
)
from .divisao import INF, Categoria, Grupo, Peso, dividir_espacial, empacotar, somar
from .formatos import nome_arquivo
from .io_kml.escritor import gerar_kml
from .modelos import chave_natural


@dataclass(eq=False)
class Arquivo:
    categoria: Categoria
    grupos: list[Grupo]
    nome: str = ""
    kml: bytes | None = None
    eh_territorios: bool = False

    @property
    def feicoes(self):
        return [f for g in self.grupos for f in g.feicoes]

    @property
    def peso(self) -> Peso:
        return somar(g.peso for g in self.grupos)

    @property
    def bytes_reais(self) -> int:
        return len(self.kml) if self.kml is not None else 0

    @property
    def celulas(self) -> int:
        return len(self.feicoes) * (2 + self.categoria.colunas)

    def gerar(self) -> None:
        self.kml = gerar_kml(self.nome, self.feicoes, self.categoria.estilos)


@dataclass
class Mapa:
    numero: int
    arquivos: list[Arquivo] = field(default_factory=list)

    @property
    def pasta(self) -> str:
        return f"Mapa_{self.numero:02d}"

    @property
    def peso(self) -> Peso:
        return somar(a.peso for a in self.arquivos)

    @property
    def territorios(self) -> list[str]:
        ts = {g.territorio for a in self.arquivos if not a.eh_territorios for g in a.grupos}
        return sorted(ts, key=chave_natural)


@dataclass
class Plano:
    mapas: list[Mapa]
    territorios: Arquivo
    avisos: list[str] = field(default_factory=list)


class _Contexto:
    def __init__(self, cats: list[Categoria], lim: Limites, cap_mapa: Peso, cap_camadas: int,
                 fatores: dict[str, float]):
        self.cats = cats
        self.cap_mapa = cap_mapa
        self.cap_camadas = cap_camadas
        self.cap_arq = [
            Peso(lim.max_feicoes_arquivo,
                 lim.max_bytes_arquivo * fatores.get(c.prefixo, 1.0) - c.sobrecarga,
                 cap_mapa.vertices, cap_mapa.celulas)
            for c in cats
        ]
        self.cat_de = {id(f): ci for ci, c in enumerate(cats) for f in c.feicoes}

    def grupos_de(self, feicoes, territorio, completo=True) -> dict[int, Grupo]:
        por: dict[int, list] = defaultdict(list)
        for f in feicoes:
            por[self.cat_de[id(f)]].append(f)
        return {ci: Grupo(territorio, fs, self.cats[ci].peso(fs), completo) for ci, fs in por.items()}

    def camadas(self, grupos_por_cat: dict[int, list[Grupo]]) -> int:
        return sum(len(empacotar(gs, self.cap_arq[ci], self.cats[ci]))
                   for ci, gs in grupos_por_cat.items() if gs)


@dataclass
class _Bloco:
    territorio: str
    grupos: dict[int, Grupo]

    @property
    def peso(self) -> Peso:
        return somar(g.peso for g in self.grupos.values())


def _blocos_por_territorio(ctx: _Contexto, ordem: list[str]) -> list[_Bloco]:
    por_terr: dict[str, list] = defaultdict(list)
    for c in ctx.cats:
        for f in c.feicoes:
            por_terr[f.territorio].append(f)
    blocos = []
    for t in ordem:
        feicoes = por_terr.get(t)
        if not feicoes:
            continue
        grupos = ctx.grupos_de(feicoes, t)
        bloco = _Bloco(t, grupos)
        if bloco.peso.cabe(ctx.cap_mapa) and \
                ctx.camadas({ci: [g] for ci, g in grupos.items()}) <= ctx.cap_camadas:
            blocos.append(bloco)
            continue
        pesos = [ctx.cats[ctx.cat_de[id(f)]].pesos[id(f)] for f in feicoes]

        def cabe_parte(fs, t=t):
            return ctx.camadas({ci: [g] for ci, g in ctx.grupos_de(fs, t).items()}) <= ctx.cap_camadas

        for parte in dividir_espacial(feicoes, pesos, ctx.cap_mapa, cabe_parte):
            blocos.append(_Bloco(t, ctx.grupos_de(parte, t, completo=False)))
    return blocos


def _por_territorio(ctx: _Contexto, ordem: list[str]) -> list[list[Arquivo]]:
    blocos = _blocos_por_territorio(ctx, ordem)
    blocos.sort(key=lambda b: -b.peso.fracao(ctx.cap_mapa))
    mapas: list[list[_Bloco]] = []
    ocupacao: list[Peso] = []
    for b in blocos:
        for k, oc in enumerate(ocupacao):
            novo = oc + b.peso
            if not novo.cabe(ctx.cap_mapa):
                continue
            grupos = defaultdict(list)
            for b2 in mapas[k] + [b]:
                for ci, g in b2.grupos.items():
                    grupos[ci].append(g)
            if ctx.camadas(grupos) <= ctx.cap_camadas:
                mapas[k].append(b)
                ocupacao[k] = novo
                break
        else:
            mapas.append([b])
            ocupacao.append(b.peso)
    resultado = []
    for blocos_mapa in mapas:
        grupos = defaultdict(list)
        for b in blocos_mapa:
            for ci, g in b.grupos.items():
                grupos[ci].append(g)
        arquivos = []
        for ci in sorted(grupos):
            for conteudo in empacotar(grupos[ci], ctx.cap_arq[ci], ctx.cats[ci]):
                arquivos.append(Arquivo(ctx.cats[ci], conteudo))
        resultado.append(arquivos)
    return resultado


def _sequencial(ctx: _Contexto, ordem: list[str]) -> list[list[Arquivo]]:
    """Preenche cada mapa ao máximo, na ordem dos territórios."""
    pos = {t: i for i, t in enumerate(ordem)}
    mapas: list[dict] = []

    def novo_mapa():
        m = {"peso": Peso(), "arquivos": defaultdict(list), "camadas": 0}
        mapas.append(m)
        return m

    feicoes = [(pos.get(f.territorio, 10**9), ci, k, f)
               for ci, c in enumerate(ctx.cats) for k, f in enumerate(c.feicoes)]
    feicoes.sort(key=lambda x: (x[0], x[1], x[2]))

    def cabe(m, ci, p) -> tuple[bool, bool]:
        arqs = m["arquivos"][ci]
        abre_novo = not arqs or not (arqs[-1][1] + p).cabe(ctx.cap_arq[ci])
        camadas = m["camadas"] + (1 if abre_novo else 0)
        return (m["peso"] + p).cabe(ctx.cap_mapa) and camadas <= ctx.cap_camadas, abre_novo

    atual = None
    for _, ci, _, f in feicoes:
        p = ctx.cats[ci].pesos[id(f)]
        if atual is None:
            atual = novo_mapa()
        ok, abre_novo = cabe(atual, ci, p)
        if not ok and atual["camadas"] > 0:
            atual = novo_mapa()      # feição maior que um mapa vazio fica sozinha
            ok, abre_novo = cabe(atual, ci, p)
        arqs = atual["arquivos"][ci]
        if abre_novo:
            arqs.append([[], Peso()])
            atual["camadas"] += 1
        arqs[-1][0].append(f)
        arqs[-1][1] = arqs[-1][1] + p
        atual["peso"] = atual["peso"] + p
    resultado = []
    for m in mapas:
        arquivos = []
        for ci in sorted(m["arquivos"]):
            for fs, _ in m["arquivos"][ci]:
                por_t: dict[str, list] = defaultdict(list)
                for f in fs:
                    por_t[f.territorio].append(f)
                grupos = [Grupo(t, l, ctx.cats[ci].peso(l), False) for t, l in por_t.items()]
                arquivos.append(Arquivo(ctx.cats[ci], grupos))
        resultado.append(arquivos)
    return resultado


def _marcar_completos(mapas: list[Mapa]) -> None:
    total: Counter = Counter()
    for m in mapas:
        for a in m.arquivos:
            for g in a.grupos:
                total[(a.categoria.prefixo, g.territorio)] += len(g.feicoes)
    for m in mapas:
        for a in m.arquivos:
            juntos: Counter = Counter()
            for g in a.grupos:
                juntos[g.territorio] += len(g.feicoes)
            novos = []
            for t in dict.fromkeys(g.territorio for g in a.grupos):
                fs = [f for g in a.grupos if g.territorio == t for f in g.feicoes]
                completo = juntos[t] == total[(a.categoria.prefixo, t)]
                novos.append(Grupo(t, fs, a.categoria.peso(fs), completo))
            a.grupos = novos


def _nomear(mapas: list[Mapa], ordem: list[str]) -> None:
    pos = {t: i for i, t in enumerate(ordem)}
    contador_partes: Counter = Counter()
    usados: set[str] = set()
    for m in mapas:
        for k, a in enumerate(a2 for a2 in m.arquivos if not a2.eh_territorios):
            a.grupos.sort(key=lambda g: pos.get(g.territorio, 10**9))
            tokens: list[str] = []
            run: list[str] = []          # territórios completos e consecutivos

            def fechar():
                if run:
                    a1, a2 = nome_arquivo(run[0]), nome_arquivo(run[-1])
                    tokens.append(a1 if len(run) == 1 else f"{a1}-{a2}")
                    run.clear()

            for g in a.grupos:
                if g.completo:
                    if run and pos.get(g.territorio, -5) != pos.get(run[-1], -9) + 1:
                        fechar()
                    run.append(g.territorio)
                else:
                    fechar()
                    chave = (a.categoria.prefixo, g.territorio)
                    contador_partes[chave] += 1
                    tokens.append(f"{nome_arquivo(g.territorio)}_parte{contador_partes[chave]}")
            fechar()
            nome = f"{a.categoria.prefixo}_{'_'.join(tokens)}"
            if len(nome) > 80:
                nome = f"{a.categoria.prefixo}_{m.pasta}_{k + 1}"
            base, n = nome, 2
            while nome in usados:
                nome = f"{base}_{n}"
                n += 1
            usados.add(nome)
            a.nome = nome


def planejar(cats: list[Categoria], ordem: list[str], terr: Categoria, lim: Limites,
             agrupamento: str, modo_territorios: str,
             fatores: dict[str, float] | None = None) -> Plano:
    fatores = fatores or {}
    cats = [c for c in cats if c.feicoes]
    avisos: list[str] = []
    cap_mapa = Peso(lim.max_feicoes_mapa, INF, lim.max_vertices_mapa, lim.max_celulas_mapa)
    cap_camadas = lim.max_camadas_mapa
    arq_terr = Arquivo(terr, [Grupo("*", terr.feicoes, terr.peso(terr.feicoes))],
                       nome=terr.prefixo, eh_territorios=True)
    peso_terr = arq_terr.peso
    if modo_territorios == CAMADA_TERR_RESERVAR:
        if peso_terr.cabe(cap_mapa) and cap_camadas > 1:
            cap_mapa = cap_mapa - peso_terr
            cap_camadas -= 1
        else:
            avisos.append("A camada de territórios é grande demais para reservar espaço em cada mapa; "
                          "ela será incluída apenas onde couber.")
            modo_territorios = CAMADA_TERR_SE_COUBER

    ctx = _Contexto(cats, lim, cap_mapa, cap_camadas, fatores)
    if agrupamento == AGRUPAR_SEQUENCIAL:
        listas = _sequencial(ctx, ordem)
    else:
        listas = _por_territorio(ctx, ordem)

    pos = {t: i for i, t in enumerate(ordem)}
    mapas = [Mapa(0, arqs) for arqs in listas if arqs]
    mapas.sort(key=lambda m: min((pos.get(g.territorio, 10**9) for a in m.arquivos for g in a.grupos),
                                 default=0))
    for i, m in enumerate(mapas, 1):
        m.numero = i
    _marcar_completos(mapas)
    _nomear(mapas, ordem)

    cap_total = Peso(lim.max_feicoes_mapa, INF, lim.max_vertices_mapa, lim.max_celulas_mapa)
    if not mapas and modo_territorios != CAMADA_TERR_NAO:
        mapas.append(Mapa(1))
    for m in mapas:
        if modo_territorios == CAMADA_TERR_RESERVAR:
            m.arquivos.insert(0, arq_terr)
        elif modo_territorios == CAMADA_TERR_SE_COUBER:
            if (m.peso + peso_terr).cabe(cap_total) and len(m.arquivos) < lim.max_camadas_mapa:
                m.arquivos.insert(0, arq_terr)
            else:
                avisos.append(f"{m.pasta}: sem espaço para a camada de territórios.")
    return Plano(mapas, arq_terr, avisos)
