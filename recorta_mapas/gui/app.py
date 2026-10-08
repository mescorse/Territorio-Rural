"""Janela principal no modelo do Dicta: barra lateral escura com páginas, painel arredondado,
chips e chaves, mensagens dentro da janela (nada de caixas de diálogo claras do sistema).

Desempenho antes de tudo: as páginas são montadas uma vez; trocar de página é só tkraise();
leitura de CSV e processamento rodam em segundo plano e falam com o Tk por uma fila."""

from __future__ import annotations

import copy
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, ttk

from .. import preferencias
from ..atributos import montar_nome, resolver_padroes
from ..config import (
    AGRUPAR_SEQUENCIAL, AGRUPAR_TERRITORIO, CNEFE_COLUNA_ESPECIE, MODO_CORTAR, MODO_INTEIRA,
    EntradaLinhas, EntradaPontos, Limites, OpcoesCSV, Opcoes,
)
from ..formatos import num
from .tema import FONT, IS_WINDOWS, THEME, aplicar_tema, caixa_texto, dark_title_bar

TIPOS_KML = [("KML ou KMZ", "*.kml *.kmz"), ("Todos os arquivos", "*.*")]
TIPOS_PONTOS = [("CSV do CNEFE, KML ou KMZ", "*.csv *.txt *.kml *.kmz"), ("Todos os arquivos", "*.*")]

# Significado provável dos códigos de espécie do CNEFE 2022 (confira no dicionário do IBGE).
ESPECIES_CNEFE = {
    "1": "Domicílio particular", "2": "Domicílio coletivo", "3": "Estab. agropecuário",
    "4": "Estab. de ensino", "5": "Estab. de saúde", "6": "Outras finalidades",
    "7": "Em construção", "8": "Estab. religioso",
}
LIMITES = (
    ("max_feicoes_arquivo", "Feições por arquivo", 1),
    ("max_bytes_arquivo", "MB por arquivo", 1e6),
    ("max_camadas_mapa", "Camadas por mapa", 1),
    ("max_feicoes_mapa", "Feições por mapa", 1),
    ("max_vertices_mapa", "Vértices por mapa", 1),
    ("max_celulas_mapa", "Células por mapa", 1),
)


PACOTES = ("shapely", "lxml", "pyproj", "numpy")


def pacotes_faltando() -> list[str]:
    """Bibliotecas necessárias que não estão instaladas (sem importá-las: é instantâneo)."""
    from importlib.util import find_spec
    return [p for p in PACOTES if find_spec(p) is None]


def mensagem_pacotes(faltando) -> str:
    return (f"Falta instalar: {', '.join(faltando)}. Num terminal, na pasta do projeto, rode:  "
            "py -m pip install -e .   (o RecortaMapas.exe já vem com tudo)")


def eh_csv(caminho: str) -> bool:
    return os.path.splitext(caminho)[1].lower() in (".csv", ".txt", ".tsv")


def encurtar(caminho: str, n: int = 64) -> str:
    if len(caminho) <= n:
        return caminho
    nome = os.path.basename(caminho)
    if len(nome) >= n - 4:
        return "…" + nome[-(n - 1):]
    return caminho[: n - len(nome) - 2] + "…" + os.sep + nome


def abrir_no_sistema(caminho: str) -> None:
    if IS_WINDOWS:
        os.startfile(caminho)  # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", caminho])


class App(tk.Tk):
    PAGINAS = ("Arquivos", "Casas", "Opções", "Avançado", "Resultado")

    def __init__(self):
        inicio = time.perf_counter()
        super().__init__()
        self.withdraw()
        self.title("Recorta Mapas")
        aplicar_tema(self)
        self.configure(bg=THEME["side"])
        self.geometry("1020x640")
        self.minsize(940, 580)
        self.protocol("WM_DELETE_WINDOW", self.fechar)

        self.op: Opcoes = preferencias.carregar()
        self.faltam_pacotes = pacotes_faltando()
        self.fila: queue.Queue = queue.Queue()
        self.infos: dict[str, object] = {}        # caminho do CSV -> InfoCSV
        self.valores: dict[tuple, object] = {}    # (caminho, coluna) -> Counter
        self.lendo: set = set()
        self.casa_atual = 0
        self.processando = False
        self.ultimo_resultado = None
        self._confirmar_padroes = False

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._barra_lateral()
        self._painel()
        for p in self.op.pontos:
            if eh_csv(p.caminho):
                self.lendo.add(p.caminho)
        self.atualizar_tudo()
        self.mostrar("Arquivos")
        self.deiconify()
        dark_title_bar(self)
        self._timer = self.after(100, self._ler_fila)
        # Ler os CSV só depois que a janela aparece, para não atrasar a abertura.
        self.after(30, lambda: [self._inspecionar(p) for p in self.op.pontos if eh_csv(p.caminho)])
        self.tempo_abertura_ms = (time.perf_counter() - inicio) * 1000

    # ================================================================ estrutura
    def _barra_lateral(self):
        lado = ttk.Frame(self, style="Side.TFrame", padding=(10, 18, 10, 18))
        lado.grid(row=0, column=0, sticky="ns")
        ttk.Label(lado, text="Recorta Mapas", style="Brand.TLabel").pack(anchor="w", padx=12)
        ttk.Label(lado, text="Territórios rurais → My Maps", style="SideMuted.TLabel").pack(
            anchor="w", padx=12, pady=(0, 16))
        self.nav = {}
        for nome in self.PAGINAS:
            b = ttk.Button(lado, text=nome, style="Nav.TButton", width=14,
                           command=lambda n=nome: self.mostrar(n))
            b.pack(fill="x", pady=1)
            self.nav[nome] = b

    def _painel(self):
        fora = ttk.Frame(self, style="Side.TFrame", padding=(0, 12, 12, 12))
        fora.grid(row=0, column=1, sticky="nsew")
        fora.columnconfigure(0, weight=1)
        fora.rowconfigure(0, weight=1)
        painel = ttk.Frame(fora, style="Panel.TFrame", padding=(8, 8, 8, 4))
        painel.grid(row=0, column=0, sticky="nsew")
        painel.columnconfigure(0, weight=1)
        painel.rowconfigure(0, weight=1)
        corpo = ttk.Frame(painel, style="Card.TFrame")
        corpo.grid(row=0, column=0, sticky="nsew")
        corpo.columnconfigure(0, weight=1)
        corpo.rowconfigure(0, weight=1)
        self.paginas = {}
        for nome in self.PAGINAS:
            card = ttk.Frame(corpo, style="Card.TFrame", padding=(18, 14, 18, 8))
            card.grid(row=0, column=0, sticky="nsew")
            card.columnconfigure(0, weight=1)
            self.paginas[nome] = card
        self._pagina_arquivos(self.paginas["Arquivos"])
        self._pagina_casas(self.paginas["Casas"])
        self._pagina_opcoes(self.paginas["Opções"])
        self._pagina_avancado(self.paginas["Avançado"])
        self._pagina_resultado(self.paginas["Resultado"])

        rodape = ttk.Frame(painel, style="Card.TFrame", padding=(18, 8, 10, 10))
        rodape.grid(row=1, column=0, sticky="ew")
        rodape.columnconfigure(0, weight=1)
        self.msg = ttk.Label(rodape, style="Msg.TLabel", wraplength=520, justify="left")
        self.msg.grid(row=0, column=0, sticky="w")
        self.bt_abrir = ttk.Button(rodape, text="Abrir pasta de saída", style="Ghost.TButton",
                                   command=self.abrir_saida)
        self.bt_abrir.grid(row=0, column=1, padx=(8, 8))
        self.bt_processar = ttk.Button(rodape, text="Processar", style="Accent.TButton",
                                       command=self.processar)
        self.bt_processar.grid(row=0, column=2)

    def mostrar(self, nome: str) -> None:
        if nome == "Casas" and getattr(self, "_casas_sujo", False):
            self.render_casas()
        self.paginas[nome].tkraise()
        for pagina, b in self.nav.items():
            b.configure(style="NavOn.TButton" if pagina == nome else "Nav.TButton")
        self.pagina_atual = nome

    @staticmethod
    def titulo(card, texto: str, sub: str, linha: int = 0) -> None:
        ttk.Label(card, text=texto, style="Head.Card.TLabel").grid(row=linha, column=0, sticky="w")
        ttk.Label(card, text=sub, style="Muted.Card.TLabel", wraplength=620, justify="left").grid(
            row=linha + 1, column=0, sticky="w", pady=(2, 14))

    def dizer(self, texto: str, tipo: str = "text") -> None:
        self.msg.configure(text=texto, foreground=THEME.get(tipo, THEME["text"]))

    # ================================================================ Arquivos
    def _pagina_arquivos(self, card):
        self.titulo(card, "Arquivos", "Escolha os mapas e os dados do IBGE. "
                    "O programa lembra tudo para a próxima vez.")
        g = self.grade_arquivos = ttk.Frame(card, style="Card.TFrame")
        g.grid(row=2, column=0, sticky="ew")
        g.columnconfigure(1, weight=1)

    def _linha_arquivo(self, g, r, rotulo, valor, escolher, remover=None, extra=None):
        ttk.Label(g, text=rotulo, style="Field.Card.TLabel").grid(
            row=r, column=0, sticky="w", padx=(0, 16), pady=4)
        ttk.Label(g, text=encurtar(valor) if valor else "Nenhum arquivo escolhido",
                  style="Path.Card.TLabel" if valor else "Empty.Card.TLabel").grid(
            row=r, column=1, sticky="w")
        if extra:
            texto, cmd = extra
            ttk.Button(g, text=texto, command=cmd).grid(row=r, column=2, padx=(8, 0), sticky="ew")
        if escolher:
            ttk.Button(g, text="Escolher…", command=escolher).grid(row=r, column=2, padx=(8, 0), sticky="ew")
        if remover:
            ttk.Button(g, text="\u2715", width=2, style="Ghost.TButton", command=remover).grid(
                row=r, column=3, padx=(4, 0))

    def render_arquivos(self):
        g = self.grade_arquivos
        for w in g.winfo_children():
            w.destroy()
        op = self.op
        r = 0
        self._linha_arquivo(g, r, "Mapa-mestre", op.mapa_mestre,
                            lambda: self._escolher("mapa_mestre", "Mapa-mestre"))
        r += 1
        self._linha_arquivo(g, r, "Territórios rurais", op.territorios,
                            lambda: self._escolher("territorios", "Territórios rurais"))
        r += 1
        ttk.Separator(g).grid(row=r, column=0, columnspan=5, sticky="ew", pady=8)
        r += 1
        for i, e in enumerate(op.linhas):
            self._linha_arquivo(g, r, "Trajetos" if i == 0 else "", e.caminho, None,
                                remover=lambda i=i: self._remover("linhas", i))
            r += 1
        ttk.Button(g, text="+  Adicionar trajetos", style="Ghost.TButton",
                   command=self._add_linhas).grid(row=r, column=1, sticky="w", pady=(0, 6))
        r += 1
        for i, e in enumerate(op.pontos):
            extra = ("Configurar", lambda i=i: self._configurar_casa(i)) if eh_csv(e.caminho) else None
            self._linha_arquivo(g, r, "Casas" if i == 0 else "", e.caminho, None,
                                remover=lambda i=i: self._remover("pontos", i), extra=extra)
            r += 1
        ttk.Button(g, text="+  Adicionar casas (CSV do CNEFE ou KML)", style="Ghost.TButton",
                   command=self._add_pontos).grid(row=r, column=1, sticky="w", pady=(0, 6))
        r += 1
        ttk.Separator(g).grid(row=r, column=0, columnspan=5, sticky="ew", pady=8)
        r += 1
        self._linha_arquivo(g, r, "Pasta de saída", op.saida, self._escolher_saida)

    def _pasta_inicial(self) -> str | None:
        for c in (self.op.territorios, self.op.mapa_mestre, self.op.saida):
            if c and os.path.exists(os.path.dirname(c) or c):
                return os.path.dirname(c) if os.path.isfile(c) else c
        return None

    def _escolher(self, campo, titulo):
        c = filedialog.askopenfilename(parent=self, title=titulo, filetypes=TIPOS_KML,
                                       initialdir=self._pasta_inicial())
        if c:
            setattr(self.op, campo, os.path.normpath(c))
            self.atualizar_tudo()

    def _escolher_saida(self):
        c = filedialog.askdirectory(parent=self, title="Pasta de saída", initialdir=self._pasta_inicial())
        if c:
            self.op.saida = os.path.normpath(c)
            self.atualizar_tudo()

    def _add_linhas(self):
        for c in filedialog.askopenfilenames(parent=self, title="Trajetos", filetypes=TIPOS_KML,
                                             initialdir=self._pasta_inicial()):
            self.op.linhas.append(EntradaLinhas(os.path.normpath(c)))
        self.atualizar_tudo()

    def _add_pontos(self):
        novos = filedialog.askopenfilenames(parent=self, title="Casas", filetypes=TIPOS_PONTOS,
                                            initialdir=self._pasta_inicial())
        for c in novos:
            c = os.path.normpath(c)
            e = EntradaPontos(c, csv=OpcoesCSV() if eh_csv(c) else None)
            self.op.pontos.append(e)
            if eh_csv(c):
                self._inspecionar(e)
        self.atualizar_tudo()
        if any(eh_csv(c) for c in novos):
            self._configurar_casa(len(self.op.pontos) - 1)

    def _remover(self, lista, i):
        item = getattr(self.op, lista).pop(i)
        self.infos.pop(getattr(item, "caminho", None), None)
        self.casa_atual = 0
        self.atualizar_tudo()

    # ================================================================ Casas
    def _pagina_casas(self, card):
        self.titulo(card, "Casas", "Quais pontos do CSV viram casas, e o que aparece em cada uma.")
        card.rowconfigure(2, weight=1)
        self.casas = self._area_rolavel(card, 2)
        self.v_ajuste_manual = tk.BooleanVar(value=False)

    def _area_rolavel(self, card, linha):
        """Conteúdo que pode passar da altura da janela: um Canvas com rolagem."""
        caixa = ttk.Frame(card, style="Card.TFrame")
        caixa.grid(row=linha, column=0, sticky="nsew")
        caixa.columnconfigure(0, weight=1)
        caixa.rowconfigure(0, weight=1)
        tela = tk.Canvas(caixa, background=THEME["card"], highlightthickness=0, borderwidth=0)
        tela.grid(row=0, column=0, sticky="nsew")
        barra = ttk.Scrollbar(caixa, orient="vertical", command=tela.yview)
        tela.configure(yscrollcommand=barra.set)
        dentro = ttk.Frame(tela, style="Card.TFrame")
        janela = tela.create_window(0, 0, window=dentro, anchor="nw")

        def ajustar(_=None):
            tela.configure(scrollregion=(0, 0, dentro.winfo_reqwidth(), dentro.winfo_reqheight()))
            precisa = dentro.winfo_reqheight() > tela.winfo_height() > 1
            if precisa:
                barra.grid(row=0, column=1, sticky="ns")
            else:
                barra.grid_remove()
                tela.yview_moveto(0)

        dentro.bind("<Configure>", ajustar)
        tela.bind("<Configure>", lambda ev: (tela.itemconfigure(janela, width=ev.width), ajustar()))

        def rolar(ev):
            if dentro.winfo_reqheight() > tela.winfo_height():
                passo = -1 if (getattr(ev, "delta", 0) > 0 or getattr(ev, "num", 0) == 4) else 1
                tela.yview_scroll(passo * 3, "units")

        for alvo in (tela, dentro):
            alvo.bind("<Enter>", lambda _: (self.bind_all("<MouseWheel>", rolar),
                                            self.bind_all("<Button-4>", rolar),
                                            self.bind_all("<Button-5>", rolar)))
            alvo.bind("<Leave>", lambda _: (self.unbind_all("<MouseWheel>"),
                                            self.unbind_all("<Button-4>"),
                                            self.unbind_all("<Button-5>")))
        dentro.columnconfigure(0, weight=1)
        return dentro

    def _fluxo(self, pai, textos, criar, fonte=10, folga=36, largura=None):
        """Chips que quebram linha conforme a largura (medida pela fonte, sem esperar o Tk)."""
        from tkinter import font as tkfont
        if not hasattr(self, "_fontes"):
            self._fontes = {}
        f = self._fontes.setdefault(fonte, tkfont.Font(root=self, family=FONT, size=fonte))
        largura = largura or max(self.casas_largura(), 400)
        caixa = ttk.Frame(pai, style="Card.TFrame")
        linha, usado = None, largura + 1
        for i, texto in enumerate(textos):
            w = f.measure(texto) + folga + 6
            if usado + w > largura:
                linha = ttk.Frame(caixa, style="Card.TFrame")
                linha.pack(anchor="w", pady=2)
                usado = 0
            criar(linha, i).pack(side="left", padx=(0, 6))
            usado += w
        return caixa

    def casas_largura(self) -> int:
        w = self.casas.master.winfo_width() if hasattr(self, "casas") else 0
        return int((w - 24) * 0.92) if w > 50 else 640

    def _csvs(self) -> list[EntradaPontos]:
        return [p for p in self.op.pontos if eh_csv(p.caminho)]

    def _configurar_casa(self, i_ponto: int):
        csvs = self._csvs()
        alvo = self.op.pontos[i_ponto]
        if alvo in csvs:
            self.casa_atual = csvs.index(alvo)
        self.render_casas()
        self.mostrar("Casas")

    def _inspecionar(self, e: EntradaPontos, opcoes: OpcoesCSV | None = None):
        """Detecta codificação/separador/colunas em segundo plano."""
        caminho = e.caminho
        self.lendo.add(caminho)

        def trabalho():
            try:
                from ..io_csv import inspecionar
                info = inspecionar(caminho, opcoes or e.csv)
                self.fila.put(("info", (e, info)))
            except Exception as exc:  # noqa: BLE001 - mostrado na tela
                self.fila.put(("info_erro", (e, str(exc))))

        threading.Thread(target=trabalho, daemon=True).start()

    def _ler_valores(self, e: EntradaPontos, coluna: str):
        chave = (e.caminho, coluna)
        if chave in self.valores or chave in self.lendo:
            return
        info = self.infos.get(e.caminho)
        if info is None:
            return
        self.lendo.add(chave)

        def trabalho():
            try:
                from ..io_csv import valores_distintos
                self.fila.put(("valores", (chave, valores_distintos(e.caminho, info.opcoes, coluna))))
            except Exception as exc:  # noqa: BLE001
                self.fila.put(("valores", (chave, exc)))

        threading.Thread(target=trabalho, daemon=True).start()

    def render_casas(self):
        self._casas_sujo = False
        f = self.casas
        for w in f.winfo_children():
            w.destroy()
        csvs = self._csvs()
        if not csvs:
            ttk.Label(f, style="Empty.Card.TLabel", text="Nenhum CSV de casas. Adicione o CSV do CNEFE "
                      "na página Arquivos. (Casas em KML/KMZ entram como estão.)").grid(row=0, column=0, sticky="w")
            return
        self.casa_atual = min(self.casa_atual, len(csvs) - 1)
        e = csvs[self.casa_atual]
        r = 0
        if len(csvs) > 1:
            chips = ttk.Frame(f, style="Card.TFrame")
            chips.grid(row=r, column=0, sticky="w", pady=(0, 10))
            v = tk.IntVar(value=self.casa_atual)
            for i, p in enumerate(csvs):
                ttk.Radiobutton(chips, text=os.path.basename(p.caminho), value=i, variable=v,
                                style="Chip.TRadiobutton",
                                command=lambda v=v: (setattr(self, "casa_atual", v.get()), self.render_casas())
                                ).grid(row=0, column=i, padx=(0, 8))
            r += 1
        info = self.infos.get(e.caminho)
        if info is None:
            texto = "Lendo o arquivo…" if e.caminho in self.lendo else getattr(e, "_erro", "Não foi possível ler.")
            ttk.Label(f, text=texto, style="Muted.Card.TLabel" if e.caminho in self.lendo
                      else "Danger.Card.TLabel", wraplength=620).grid(row=r, column=0, sticky="w")
            return
        o = info.opcoes
        sep = {"\t": "tabulação", ";": "ponto e vírgula", ",": "vírgula"}.get(o.delimitador, o.delimitador)
        ttk.Label(f, style="Card.TLabel", text=(
            f"{os.path.basename(e.caminho)}:  {o.codificacao.upper()} · {sep} · "
            f"coordenadas em {o.coluna_lat} / {o.coluna_lon}"
            + ("  ·  formato CNEFE" if info.cnefe else "")), wraplength=640, justify="left").grid(
            row=r, column=0, sticky="w")
        r += 1
        ttk.Checkbutton(f, text="Ajustar a leitura manualmente", variable=self.v_ajuste_manual,
                        style="Switch.TCheckbutton", command=self.render_casas).grid(
            row=r, column=0, sticky="ew", pady=(4, 0))
        r += 1
        if self.v_ajuste_manual.get():
            r = self._ajuste_manual(f, r, e, info)

        # --- filtro
        ttk.Label(f, text="QUAIS PONTOS MANTER", style="Muted.Card.TLabel").grid(
            row=r, column=0, sticky="w", pady=(16, 4))
        r += 1
        linha = ttk.Frame(f, style="Card.TFrame")
        linha.grid(row=r, column=0, sticky="w")
        v_filtrar = tk.BooleanVar(value=bool(e.filtro_coluna))
        v_col = tk.StringVar(value=e.filtro_coluna or (CNEFE_COLUNA_ESPECIE if info.cnefe else ""))

        def mudar_filtro(*_):
            if v_filtrar.get() and v_col.get():
                if v_col.get() != e.filtro_coluna:
                    e.filtro_coluna, e.filtro_valores = v_col.get(), []
            else:
                e.filtro_coluna, e.filtro_valores = "", []
            self.render_casas()
            self.validar()

        ttk.Checkbutton(linha, text="Filtrar pela coluna ", variable=v_filtrar,
                        style="Switch.TCheckbutton", command=mudar_filtro).grid(row=0, column=0, padx=(0, 10))
        cb = ttk.Combobox(linha, textvariable=v_col, values=info.colunas, state="readonly", width=24)
        cb.grid(row=0, column=1)
        cb.bind("<<ComboboxSelected>>", mudar_filtro)
        r += 1
        if e.filtro_coluna:
            r = self._chips_valores(f, r, e)

        # --- colunas
        ttk.Label(f, text="COLUNAS EM CADA CASA (além de Territorio)", style="Muted.Card.TLabel").grid(
            row=r, column=0, sticky="w", pady=(16, 4))
        r += 1
        escolhidas = set(e.colunas or [])
        ignorar = {o.coluna_lat, o.coluna_lon}
        visiveis = [c for c in info.colunas if c not in ignorar]

        def chip_coluna(pai, i):
            c = visiveis[i]
            v = tk.BooleanVar(value=c in escolhidas)

            def alternar():
                atual = list(e.colunas or [])
                if v.get() and c not in atual:
                    atual.append(c)
                elif not v.get() and c in atual:
                    atual.remove(c)
                e.colunas = [x for x in info.colunas if x in atual]

            b = ttk.Checkbutton(pai, text=c, variable=v, style="Mini.TCheckbutton", command=alternar)
            b._var = v
            return b

        self._fluxo(f, visiveis, chip_coluna, fonte=9, folga=22).grid(row=r, column=0, sticky="w")
        r += 1
        ttk.Label(f, style="Muted.Card.TLabel", text="Menos colunas = mais casas em cada mapa "
                  "(o My Maps limita as células da tabela).").grid(row=r, column=0, sticky="w", pady=(4, 0))
        r += 1

        # --- nome
        ttk.Label(f, text="NOME DE CADA CASA", style="Muted.Card.TLabel").grid(
            row=r, column=0, sticky="w", pady=(16, 4))
        r += 1
        v_nome = tk.StringVar(value=e.nome_modelo or (f"{{{e.nome_coluna}}}" if e.nome_coluna else ""))
        ttk.Entry(f, textvariable=v_nome, width=70).grid(row=r, column=0, sticky="w")
        r += 1
        exemplo = ttk.Label(f, style="Muted.Card.TLabel", wraplength=620, justify="left")
        exemplo.grid(row=r, column=0, sticky="w", pady=(4, 0))

        def mudar_nome(*_):
            e.nome_modelo, e.nome_coluna = v_nome.get().strip() or "Casa {n}", None
            amostra = info.amostra[0] if info.amostra else {}
            exemplo.configure(text=f"Exemplo: {montar_nome(e.nome_modelo, amostra, 1) or '(vazio)'}"
                              "      Use {COLUNA} para inserir valores e {n} para numerar.")

        v_nome.trace_add("write", mudar_nome)
        mudar_nome()

    def _ajuste_manual(self, f, r, e, info):
        o = info.opcoes
        g = ttk.Frame(f, style="Card.TFrame")
        g.grid(row=r, column=0, sticky="w", pady=(6, 0))
        vs = {}
        for i, (rot, chave, valores) in enumerate((
                ("Codificação", "codificacao", ["utf-8", "utf-8-sig", "latin-1", "cp1252"]),
                ("Separador", "delimitador", [";", ",", "tab", "|"]),
                ("Latitude", "coluna_lat", info.colunas),
                ("Longitude", "coluna_lon", info.colunas))):
            atual = getattr(o, chave)
            vs[chave] = tk.StringVar(value="tab" if atual == "\t" else atual)
            ttk.Label(g, text=rot, style="Field.Card.TLabel").grid(row=0, column=2 * i, padx=(0, 6))
            ttk.Combobox(g, textvariable=vs[chave], values=valores, width=12 if i > 1 else 9).grid(
                row=0, column=2 * i + 1, padx=(0, 14))

        def reler():
            d = vs["delimitador"].get()
            novas = OpcoesCSV(vs["codificacao"].get() or None, "\t" if d == "tab" else (d or None),
                              vs["coluna_lat"].get() or None, vs["coluna_lon"].get() or None)
            if novas.delimitador != o.delimitador:
                novas.coluna_lat = novas.coluna_lon = None
            e.csv = novas
            self.infos.pop(e.caminho, None)
            self.valores = {k: v for k, v in self.valores.items() if k[0] != e.caminho}
            self._inspecionar(e, novas)
            self.render_casas()

        ttk.Button(g, text="Reler", command=reler).grid(row=0, column=8)
        return r + 1

    def _chips_valores(self, f, r, e):
        chave = (e.caminho, e.filtro_coluna)
        cont = self.valores.get(chave)
        if cont is None:
            self._ler_valores(e, e.filtro_coluna)
            ttk.Label(f, text="Contando os valores…", style="Muted.Card.TLabel").grid(
                row=r, column=0, sticky="w", pady=(6, 0))
            return r + 1
        if isinstance(cont, Exception):
            ttk.Label(f, text=f"Erro ao ler os valores: {cont}", style="Danger.Card.TLabel").grid(
                row=r, column=0, sticky="w", pady=(6, 0))
            return r + 1
        cnefe = e.filtro_coluna == CNEFE_COLUNA_ESPECIE
        valores = sorted(cont, key=lambda v: (-cont[v], v))[:40]
        marcados = set(e.filtro_valores)
        textos = []
        for val in valores:
            nome = ESPECIES_CNEFE.get(val, "") if cnefe else ""
            textos.append(f"{val or '(vazio)'}{'  ' + nome if nome else ''}  ·  {num(cont[val])}")

        def chip_valor(pai, i):
            val = valores[i]
            v = tk.BooleanVar(value=val in marcados)

            def alternar():
                atual = set(e.filtro_valores)
                atual.add(val) if v.get() else atual.discard(val)
                e.filtro_valores = sorted(atual)
                self.validar()

            b = ttk.Checkbutton(pai, text=textos[i], variable=v, style="Chip.TCheckbutton", command=alternar)
            b._var = v
            return b

        self._fluxo(f, textos, chip_valor, fonte=10, folga=44).grid(row=r, column=0, sticky="w", pady=(8, 0))
        r += 1
        if cnefe:
            ttk.Label(f, style="Muted.Card.TLabel", wraplength=620, justify="left", text=(
                "Os nomes dos códigos são os prováveis do CNEFE 2022: confira no dicionário de dados "
                "do IBGE. Para casas, normalmente só o 1 (domicílio particular).")).grid(
                row=r, column=0, sticky="w", pady=(4, 0))
            r += 1
        return r

    # ================================================================ Opções
    def _chips(self, pai, linha, variavel, escolhas, ao_mudar):
        g = ttk.Frame(pai, style="Card.TFrame")
        g.grid(row=linha, column=0, sticky="w", pady=(0, 4))
        for i, (valor, texto) in enumerate(escolhas):
            ttk.Radiobutton(g, text=texto, value=valor, variable=variavel, style="Chip.TRadiobutton",
                            command=ao_mudar).grid(row=0, column=i, padx=(0, 8))

    def _secao(self, card, linha, texto):
        ttk.Label(card, text=texto, style="Muted.Card.TLabel").grid(row=linha, column=0, sticky="w", pady=(10, 6))

    def _pagina_opcoes(self, card):
        self.titulo(card, "Opções", "Como os trajetos são recortados e o formato dos arquivos.")
        self.v_modo = tk.StringVar()
        self.v_simplificar = tk.BooleanVar()
        self.v_metros = tk.StringVar()
        self.v_formato = tk.StringVar()
        self._secao(card, 2, "TRAJETOS QUE SAEM DO TERRITÓRIO RURAL")
        self._chips(card, 3, self.v_modo, ((MODO_CORTAR, "Cortar na borda"),
                                           (MODO_INTEIRA, "Manter o trajeto inteiro")), self._ler_opcoes)
        ttk.Label(card, style="Muted.Card.TLabel", wraplength=620, justify="left", text=(
            "Inteiro: um trajeto que toca vários territórios vai para onde está a maior parte dele.")).grid(
            row=4, column=0, sticky="w")
        linha = ttk.Frame(card, style="Card.TFrame")
        linha.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        linha.columnconfigure(0, weight=1)
        ttk.Checkbutton(linha, text="Simplificar os trajetos (arquivos menores, cabem mais por mapa)",
                        variable=self.v_simplificar, style="Switch.TCheckbutton",
                        command=self._ler_opcoes).grid(row=0, column=0, sticky="ew")
        ttk.Entry(linha, textvariable=self.v_metros, width=6).grid(row=0, column=1, padx=(12, 6))
        ttk.Label(linha, text="metros", style="Card.TLabel").grid(row=0, column=2)
        self.v_metros.trace_add("write", lambda *_: self._ler_opcoes())
        self._secao(card, 6, "FORMATO DOS ARQUIVOS")
        self._chips(card, 7, self.v_formato, (("kml", "KML"), ("kmz", "KMZ (compactado)")), self._ler_opcoes)

    def _pagina_avancado(self, card):
        self.titulo(card, "Avançado", "Normalmente não precisa mexer. Os limites já têm margem de "
                    "segurança em relação aos do Google My Maps.")
        self.v_agrupar = tk.StringVar()
        self.v_limiar = tk.StringVar()
        self.v_campo_id = tk.StringVar()
        self._secao(card, 2, "COMO DIVIDIR OS ARQUIVOS")
        self._chips(card, 3, self.v_agrupar, ((AGRUPAR_TERRITORIO, "Territórios inteiros por arquivo"),
                                              (AGRUPAR_SEQUENCIAL, "Encher cada arquivo ao máximo")),
                    self._ler_opcoes)
        g = ttk.Frame(card, style="Card.TFrame")
        g.grid(row=4, column=0, sticky="w", pady=(14, 0))
        for i, (rot, var, larg) in enumerate((
                ("Alertar se o território perder mais de (%)", self.v_limiar, 8),
                ("Campo de ID quando o território não tem nome", self.v_campo_id, 18))):
            ttk.Label(g, text=rot, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=3, padx=(0, 12))
            ttk.Entry(g, textvariable=var, width=larg).grid(row=i, column=1, sticky="w", pady=3)
            var.trace_add("write", lambda *_: self._ler_opcoes())
        self._secao(card, 5, "LIMITES DO GOOGLE MY MAPS (COM MARGEM)")
        g2 = ttk.Frame(card, style="Card.TFrame")
        g2.grid(row=6, column=0, sticky="w")
        self.v_lim = {}
        for i, (chave, rot, _) in enumerate(LIMITES):
            self.v_lim[chave] = var = tk.StringVar()
            linha, col = i // 2, (i % 2) * 2
            ttk.Label(g2, text=rot, style="Card.TLabel").grid(row=linha, column=col, sticky="w", pady=3,
                                                              padx=(0 if col == 0 else 28, 12))
            ttk.Entry(g2, textvariable=var, width=9).grid(row=linha, column=col + 1, sticky="w", pady=3)
            var.trace_add("write", lambda *_: self._ler_opcoes())
        self.bt_padroes = ttk.Button(card, text="Restaurar padrões", style="Ghost.TButton",
                                     command=self._restaurar_padroes)
        self.bt_padroes.grid(row=0, column=0, sticky="ne")

    def _restaurar_padroes(self):
        if not self._confirmar_padroes:          # confirma no próprio botão, sem caixa de diálogo
            self._confirmar_padroes = True
            self.bt_padroes.configure(text="Clique de novo para restaurar")
            self.after(4000, self._cancelar_padroes)
            return
        self._cancelar_padroes()
        p = Opcoes()
        o = self.op
        o.limites, o.limiar_perda_pct, o.agrupamento, o.campo_id = p.limites, p.limiar_perda_pct, p.agrupamento, None
        o.modo_linhas, o.simplificar_m, o.formato = p.modo_linhas, p.simplificar_m, p.formato
        self.atualizar_tudo()
        self.dizer("Opções restauradas.", "muted")

    def _cancelar_padroes(self):
        self._confirmar_padroes = False
        self.bt_padroes.configure(text="Restaurar padrões")

    def _carregar_opcoes_na_tela(self):
        o = self.op
        self._carregando = True
        self.v_modo.set(o.modo_linhas)
        self.v_simplificar.set(o.simplificar_m > 0)
        self.v_metros.set(f"{o.simplificar_m:g}" if o.simplificar_m > 0 else "5")
        self.v_formato.set(o.formato)
        self.v_agrupar.set(o.agrupamento)
        self.v_limiar.set(f"{o.limiar_perda_pct:g}".replace(".", ","))
        self.v_campo_id.set(o.campo_id or "")
        for chave, _, escala in LIMITES:
            self.v_lim[chave].set(f"{getattr(o.limites, chave) / escala:g}".replace(".", ","))
        self._carregando = False

    def _ler_opcoes(self):
        if getattr(self, "_carregando", False):
            return
        o = self.op
        self.erros_opcoes = []

        def numero(var, rot):
            try:
                return float(var.get().replace(",", "."))
            except ValueError:
                self.erros_opcoes.append(f"Valor inválido em \"{rot}\".")
                return None

        o.modo_linhas = self.v_modo.get()
        o.formato = self.v_formato.get()
        o.agrupamento = self.v_agrupar.get()
        if self.v_simplificar.get():
            m = numero(self.v_metros, "metros")
            o.simplificar_m = m if m and m > 0 else 0.0
        else:
            o.simplificar_m = 0.0
        lim = numero(self.v_limiar, "alertar se perder mais de")
        if lim is not None:
            o.limiar_perda_pct = lim
        o.campo_id = self.v_campo_id.get().strip() or None
        for chave, rot, escala in LIMITES:
            v = numero(self.v_lim[chave], rot)
            if v is not None and v > 0:
                setattr(o.limites, chave, int(v * escala))
            elif v is not None:
                self.erros_opcoes.append(f"\"{rot}\" precisa ser maior que zero.")
        self.validar()

    # ================================================================ Resultado
    def _pagina_resultado(self, card):
        card.rowconfigure(4, weight=1)
        self.res_titulo = ttk.Label(card, text="Ainda não processado", style="Title.Card.TLabel")
        self.res_titulo.grid(row=0, column=0, sticky="w")
        self.res_sub = ttk.Label(card, style="Muted.Card.TLabel", wraplength=640, justify="left", text=(
            "Escolha os arquivos e clique em Processar. O resultado aparece aqui."))
        self.res_sub.grid(row=1, column=0, sticky="w", pady=(2, 8))
        self.res_avisos = ttk.Label(card, style="Warn.Card.TLabel", wraplength=640, justify="left")
        self.res_avisos.grid(row=2, column=0, sticky="w")
        ttk.Label(card, text="RELATÓRIO COMPLETO (também salvo em relatorio.txt)",
                  style="Muted.Card.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 4))
        caixa = ttk.Frame(card, style="Card.TFrame")
        caixa.grid(row=4, column=0, sticky="nsew")
        caixa.columnconfigure(0, weight=1)
        caixa.rowconfigure(0, weight=1)
        self.txt = caixa_texto(caixa, wrap="none", height=10)
        self.txt.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(caixa, orient="vertical", command=self.txt.yview)
        sy.grid(row=0, column=1, sticky="ns")
        sx = ttk.Scrollbar(caixa, orient="horizontal", command=self.txt.xview)
        sx.grid(row=1, column=0, sticky="ew")
        self.txt.configure(yscrollcommand=sy.set, xscrollcommand=sx.set, state="disabled")

    def mostrar_resultado(self, r):
        n_mapas = len(r.plano.mapas)
        n_arq = sum(len(m.arquivos) for m in r.plano.mapas)
        self.res_titulo.configure(text=f"{n_mapas} mapa{'s' if n_mapas != 1 else ''} · "
                                       f"{n_arq} arquivo{'s' if n_arq != 1 else ''} para importar")
        mapas = "   ".join(f"{m.pasta}: {', '.join(m.territorios) or '-'}" for m in r.plano.mapas[:6])
        self.res_sub.configure(text=(
            "Para cada pasta Mapa_XX, crie um mapa no My Maps e importe cada arquivo como uma camada.\n"
            + mapas + ("   …" if n_mapas > 6 else "")))
        avisos = [l.strip()[2:] for l in r.relatorio.splitlines() if l.strip().startswith("! ")]
        if avisos:
            mais = f"\n… e mais {len(avisos) - 5} aviso(s) no relatório." if len(avisos) > 5 else ""
            self.res_avisos.configure(text="Atenção:\n• " + "\n• ".join(avisos[:5]) + mais)
        else:
            self.res_avisos.configure(text="")
        self._texto(r.relatorio)

    def _texto(self, texto):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", texto)
        self.txt.configure(state="disabled")

    # ================================================================ estado
    def atualizar_tudo(self):
        self.render_arquivos()
        self.render_casas()
        self._carregar_opcoes_na_tela()
        self.erros_opcoes = []
        self.validar()

    def faltando(self) -> list[str]:
        o, f = self.op, []
        if not o.mapa_mestre:
            f.append("o mapa-mestre")
        if not o.territorios:
            f.append("os territórios rurais")
        if not o.linhas and not o.pontos:
            f.append("trajetos ou casas")
        if not o.saida:
            f.append("a pasta de saída")
        return f

    def validar(self) -> bool:
        if self.processando:
            return False
        erros = list(getattr(self, "erros_opcoes", []))
        if getattr(self, "faltam_pacotes", None):
            erros.insert(0, mensagem_pacotes(self.faltam_pacotes))
        for p in self._csvs():
            if p.filtro_coluna and not p.filtro_valores and (p.caminho, p.filtro_coluna) in self.valores:
                erros.append(f"{os.path.basename(p.caminho)}: marque ao menos um valor para manter "
                             "(página Casas) ou desligue o filtro.")
            if p.caminho in self.lendo:
                erros.append(f"Lendo {os.path.basename(p.caminho)}…")
        falta = self.faltando()
        ok = not erros and not falta
        if erros:
            self.dizer("\n".join(erros), "danger" if not erros[0].startswith("Lendo") else "muted")
        elif falta:
            self.dizer("Falta escolher " + ", ".join(falta) + ".", "muted")
        elif not self.ultimo_resultado:
            self.dizer("Tudo pronto. Clique em Processar.", "muted")
        self.bt_processar.state(["!disabled"] if ok else ["disabled"])
        existe = bool(self.op.saida) and os.path.isdir(self.op.saida)
        self.bt_abrir.state(["!disabled"] if existe else ["disabled"])
        return ok

    def salvar_preferencias(self):
        try:
            preferencias.salvar(self.op)
        except OSError:
            pass   # lembrar é conveniência: nunca atrapalha o uso

    # ================================================================ processar
    def processar(self):
        if not self.validar():
            return
        op = copy.deepcopy(self.op)
        for p in op.pontos:
            info = self.infos.get(p.caminho)
            if info is not None:
                p.csv = info.opcoes
        self.salvar_preferencias()
        self.processando = True
        self.bt_processar.state(["disabled"])
        self.dizer("Começando…", "muted")
        self.inicio_proc = time.perf_counter()

        def trabalho():
            try:
                from ..pipeline import executar
                self.fila.put(("fim", executar(op, progresso=lambda m: self.fila.put(("status", m)))))
            except Exception as exc:  # noqa: BLE001 - mostrado na tela
                self.fila.put(("erro", (exc, traceback.format_exc())))

        threading.Thread(target=trabalho, daemon=True).start()

    def _ler_fila(self):
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "status":
                    self.dizer(valor, "muted")
                elif tipo == "fim":
                    self.processando = False
                    self.ultimo_resultado = valor
                    self.mostrar_resultado(valor)
                    self.mostrar("Resultado")
                    s = time.perf_counter() - self.inicio_proc
                    self.validar()
                    self.dizer(f"Concluído em {num(s, 1)} s. Arquivos em {encurtar(valor.pasta_saida, 50)}", "text")
                elif tipo == "erro":
                    self.processando = False
                    exc, tb = valor
                    if isinstance(exc, ModuleNotFoundError):
                        exc = RuntimeError(mensagem_pacotes([exc.name]))
                    self.validar()
                    self.dizer(f"Erro: {exc}", "danger")
                    self.res_titulo.configure(text="Não foi possível processar")
                    self.res_sub.configure(text=str(exc))
                    self.res_avisos.configure(text="")
                    self._texto(f"ERRO: {exc}\n\nDetalhes técnicos:\n{tb}")
                    self.mostrar("Resultado")
                elif tipo == "info":
                    e, info = valor
                    self.lendo.discard(e.caminho)
                    if e in self.op.pontos:
                        self.infos[e.caminho] = info
                        e.csv = info.opcoes
                        resolver_padroes(e, info)
                        if e.filtro_coluna:
                            self._ler_valores(e, e.filtro_coluna)
                    self.render_casas()
                    self.validar()
                elif tipo == "info_erro":
                    e, msg = valor
                    self.lendo.discard(e.caminho)
                    e._erro = f"Não foi possível ler {os.path.basename(e.caminho)}: {msg}"
                    self.render_casas()
                    self.validar()
                elif tipo == "valores":
                    chave, cont = valor
                    self.lendo.discard(chave)
                    self.valores[chave] = cont
                    if self.pagina_atual == "Casas":
                        self.render_casas()
                    else:
                        self._casas_sujo = True
                    self.validar()
        except queue.Empty:
            pass
        self._timer = self.after(100, self._ler_fila)

    def abrir_saida(self):
        if self.op.saida and os.path.isdir(self.op.saida):
            abrir_no_sistema(self.op.saida)

    def fechar(self):
        self.salvar_preferencias()
        self.after_cancel(self._timer)
        self.destroy()


def main():
    if IS_WINDOWS:
        try:  # texto nítido em telas com escala (125%, 150%...)
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    App().mainloop()
