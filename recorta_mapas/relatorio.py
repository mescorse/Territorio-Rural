"""Relatório em português (relatorio.txt e tela)."""

from __future__ import annotations

import os
from datetime import datetime

from .config import Limites, Opcoes
from .etapa1_ajuste import ResultadoEtapa1
from .etapa2_recorte import EstatEntrada
from .formatos import bytes_legivel, num
from .planejamento import Plano


def tabela(cabecalho: list[str], linhas: list[list[str]], direita: set[int] | None = None) -> str:
    direita = direita if direita is not None else set(range(1, len(cabecalho)))
    larg = [max(len(str(c)) for c in col) for col in zip(cabecalho, *linhas)]

    def fmt(l):
        return "  ".join(str(c).rjust(w) if i in direita else str(c).ljust(w)
                         for i, (c, w) in enumerate(zip(l, larg))).rstrip()

    sep = "  ".join("-" * w for w in larg)
    return "\n".join([fmt(cabecalho), sep] + [fmt(l) for l in linhas])


def _titulo(t: str) -> str:
    return f"\n{t}\n{'=' * len(t)}"


def _pct(v: float, lim: float) -> str:
    return f"{num(100 * v / lim, 0)}%" if lim else "-"


def gerar(op: Opcoes, e1: ResultadoEtapa1, ests: list[EstatEntrada], plano: Plano,
          avisos_gerais: list[str]) -> str:
    lim: Limites = op.limites
    s: list[str] = []
    s.append("RELATÓRIO - RECORTA MAPAS")
    s.append(f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    s.append(f"Mapa-mestre: {os.path.basename(op.mapa_mestre)}")
    s.append(f"Territórios rurais: {os.path.basename(op.territorios)}")
    for e in op.linhas:
        s.append(f"Linhas: {os.path.basename(e.caminho)}")
    for e in op.pontos:
        s.append(f"Pontos: {os.path.basename(e.caminho)}")
    s.append(f"Projeção para medidas: EPSG:{e1.projecao.epsg}")

    # ---------------- Etapa 1
    s.append(_titulo("ETAPA 1 - AJUSTE DOS TERRITÓRIOS RURAIS AO MAPA-MESTRE"))
    linhas = []
    for l in e1.linhas:
        situacao = "DESCARTADO (fora)" if l.removido else ("ALERTA" if l.alerta else "ok")
        linhas.append([l.id, num(l.area_antes_ha, 2), num(l.area_depois_ha, 2),
                       num(l.pct_removido, 2), situacao])
    s.append(tabela(["Território", "Área antes (ha)", "Área depois (ha)", "Removido (%)", "Situação"],
                    linhas, {1, 2, 3}))
    s.append(f"\nLimite de perda para alerta: {num(op.limiar_perda_pct, 1)}%")
    s.append(f"Geometrias corrigidas: mapa-mestre {e1.correcoes_mestre}, "
             f"territórios {e1.correcoes_territorios}")
    if e1.sobreposicoes:
        s.append("\nSobreposições entre territórios (vãos entre territórios não são problema):")
        s.append(tabela(["Território 1", "Território 2", "Área (m²)"],
                        [[a, b, num(m2, 0)] for a, b, m2 in e1.sobreposicoes], {2}))
    else:
        s.append("Nenhuma sobreposição entre territórios.")
    if e1.avisos:
        s.append("\nAvisos da etapa 1:")
        s.extend(f"  ! {a}" for a in e1.avisos)

    # ---------------- Etapa 2
    s.append(_titulo("ETAPA 2 - RECORTE PELOS TERRITÓRIOS RURAIS"))
    if op.linhas:
        modo = "cortar na borda" if op.modo_linhas == "cortar" else "manter feição inteira se tocar"
        s.append(f"Modo das linhas: {modo}")
        if op.simplificar_m > 0:
            s.append(f"Simplificação das linhas: {num(op.simplificar_m, 1)} m (preservando topologia)")
    for e in ests:
        s.append(f"\n{e.nome}  ->  camada \"{e.prefixo}\" ({e.tipo})")
        itens = [("Lidas", e.lidas)]
        if e.tipo == "linhas":
            itens += [("Mantidas inteiras", e.inteiras), ("Cortadas na borda", e.cortadas),
                      ("Descartadas (fora dos territórios rurais)", e.fora),
                      ("Tocam mais de um território", e.varios_territorios),
                      ("Feições geradas", e.saida)]
        else:
            itens += [("Mantidas", e.saida),
                      ("Descartadas (fora dos territórios rurais)", e.fora)]
            if e.filtro_coluna:
                itens.append((f"Descartadas pelo filtro ({e.filtro_coluna})", e.filtradas))
            itens += [("Sem coordenada válida", e.sem_coordenada),
                      ("Na divisa entre territórios (atribuídas ao 1º)", e.na_divisa)]
        itens += [("Geometrias corrigidas", e.corrigidas)]
        if e.ignoradas:
            itens.append(("Ignoradas (tipo de geometria diferente)", e.ignoradas))
        if e.tipo == "linhas":
            itens += [("Vértices antes / depois", f"{num(e.vertices_antes)} / {num(e.vertices_depois)}"),
                      ("km lidos / mantidos", f"{num(e.km_lidos, 1)} / {num(e.km_mantidos, 1)}")]
        larg = max(len(a) for a, _ in itens)
        for a, b in itens:
            s.append(f"  {a.ljust(larg)}  {b if isinstance(b, str) else num(b)}")
        if e.colunas:
            s.append(f"  Colunas na saída: {', '.join(e.colunas)}")
        if e.filtro_coluna:
            permitidos = set(e.filtro_valores)
            s.append(f"\n  Valores encontrados em {e.filtro_coluna} "
                     "(confira o código no dicionário de dados do IBGE):")
            vals = sorted(e.valores_total, key=lambda v: (-e.valores_total[v], v))
            s.append("  " + tabela(["Valor", "No arquivo", "Nos territórios rurais", "Mantido"],
                                   [[v or "(vazio)", num(e.valores_total[v]), num(e.valores_rurais.get(v, 0)),
                                     "sim" if v in permitidos else "não"] for v in vals],
                                   {1, 2}).replace("\n", "\n  "))
        for a in e.avisos:
            s.append(f"  ! {a}")

    # ---------------- Resumo por território
    pontos = [e for e in ests if e.tipo == "pontos"]
    linhas_e = [e for e in ests if e.tipo == "linhas"]
    if ests:
        s.append(_titulo("RESUMO POR TERRITÓRIO"))
        cab = ["Território"] + [f"{e.prefixo} (n)" for e in pontos] + [f"{e.prefixo} (km)" for e in linhas_e]
        linhas = []
        sem_casas = []
        for f in e1.territorios:
            t = f.territorio
            l = [t] + [num(e.por_territorio.get(t, 0)) for e in pontos] \
                + [num(e.por_territorio.get(t, 0), 1) for e in linhas_e]
            linhas.append(l)
            if pontos and all(e.por_territorio.get(t, 0) == 0 for e in pontos):
                sem_casas.append(t)
        total = ["TOTAL"] + [num(sum(e.por_territorio.values())) for e in pontos] \
            + [num(sum(e.por_territorio.values()), 1) for e in linhas_e]
        s.append(tabela(cab, linhas + [total]))
        if sem_casas:
            s.append(f"\n  ! Territórios sem nenhuma casa: {', '.join(sem_casas)}")

    # ---------------- Plano de mapas
    s.append(_titulo("ARQUIVOS DE SAÍDA E PLANO DE MAPAS"))
    s.append(f"Limites usados: por arquivo {num(lim.max_feicoes_arquivo)} feições e "
             f"{bytes_legivel(lim.max_bytes_arquivo)}; por mapa {lim.max_camadas_mapa} camadas, "
             f"{num(lim.max_feicoes_mapa)} feições, {num(lim.max_vertices_mapa)} vértices, "
             f"{num(lim.max_celulas_mapa)} células.")
    s.append(f"Formato: {op.formato.upper()}.  Agrupamento: "
             + ("territórios inteiros por arquivo" if op.agrupamento == "territorio" else "sequencial"))
    s.append(f"Total: {len(plano.mapas)} mapa(s), "
             f"{sum(len(m.arquivos) for m in plano.mapas)} arquivo(s) para importar.")
    avisos_limite: list[str] = []
    frac = lim.fracao_aviso
    ext = "." + op.formato
    for m in plano.mapas:
        s.append(f"\n{m.pasta}/   territórios: {', '.join(m.territorios) or '-'}")
        linhas = []
        for a in m.arquivos:
            p = a.peso
            linhas.append([a.nome + ext, num(p.feicoes), bytes_legivel(a.bytes_reais),
                           num(p.vertices), num(a.celulas)])
            if a.bytes_reais > frac * lim.max_bytes_arquivo:
                avisos_limite.append(f"{m.pasta}/{a.nome}: tamanho {bytes_legivel(a.bytes_reais)} perto do limite.")
            if p.feicoes > lim.max_feicoes_arquivo or a.bytes_reais > lim.max_bytes_arquivo:
                avisos_limite.append(f"{m.pasta}/{a.nome}: EXCEDE o limite por arquivo.")
        p = m.peso
        celulas = sum(a.celulas for a in m.arquivos)
        linhas.append(["TOTAL DO MAPA", num(p.feicoes), "", num(p.vertices), num(celulas)])
        s.append(tabela(["Arquivo", "Feições", "Tamanho", "Vértices", "Células"], linhas))
        uso = (f"  Uso: camadas {len(m.arquivos)}/{lim.max_camadas_mapa} "
               f"({_pct(len(m.arquivos), lim.max_camadas_mapa)}), "
               f"feições {_pct(p.feicoes, lim.max_feicoes_mapa)}, "
               f"vértices {_pct(p.vertices, lim.max_vertices_mapa)}, "
               f"células {_pct(celulas, lim.max_celulas_mapa)}")
        s.append(uso)
        if len(m.arquivos) > lim.max_camadas_mapa:
            avisos_limite.append(f"{m.pasta}: camadas EXCEDEM o limite ({len(m.arquivos)} > {lim.max_camadas_mapa}).")
        for nome, v, l in (("feições", p.feicoes, lim.max_feicoes_mapa),
                           ("vértices", p.vertices, lim.max_vertices_mapa),
                           ("células", celulas, lim.max_celulas_mapa)):
            if v > l:
                avisos_limite.append(f"{m.pasta}: {nome} EXCEDEM o limite ({num(v)} > {num(l)}).")
            elif v > frac * l:
                avisos_limite.append(f"{m.pasta}: {nome} perto do limite ({num(v)} de {num(l)}).")
    s.append(f"\nCamada de territórios ajustados: {plano.territorios.nome}{ext} "
             f"({num(len(plano.territorios.feicoes))} feições) na pasta principal.")
    todos_avisos = list(plano.avisos) + avisos_limite + list(avisos_gerais)
    if todos_avisos:
        s.append("\nAvisos:")
        s.extend(f"  ! {a}" for a in todos_avisos)
    s.append(_titulo("COMO IMPORTAR NO GOOGLE MY MAPS"))
    s.append("Para cada pasta Mapa_XX: crie um mapa novo no My Maps, e em cada camada use\n"
             "\"Importar\" com um dos arquivos da pasta (um arquivo = uma camada).")
    return "\n".join(s) + "\n"
