"""Diálogo de configuração de um CSV de pontos: detecção, filtro, colunas e nome."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..atributos import resolver_padroes
from ..config import EntradaPontos, OpcoesCSV
from ..formatos import num
from ..io_csv import ErroCSV, inspecionar, valores_distintos

CODIFICACOES = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
DELIMITADORES = {";": ";", ",": ",", "tab": "\t", "|": "|"}


def _nome_delim(d: str) -> str:
    return "tab" if d == "\t" else d


class DialogoCSV(tk.Toplevel):
    """Edita uma EntradaPontos de CSV. Em caso de OK, self.ok = True e a entrada é alterada."""

    def __init__(self, pai, entrada: EntradaPontos):
        super().__init__(pai)
        self.title("Configurar CSV de pontos")
        self.transient(pai)
        self.entrada = entrada
        self.ok = False
        self.info = None
        self._valores_cache: dict[str, dict] = {}
        self._montar()
        self._recarregar(primeira=True)
        self.grab_set()
        self.geometry("1000x700")

    # ------------------------------------------------------------ interface
    def _montar(self):
        f = ttk.Frame(self, padding=8)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text=self.entrada.caminho, foreground="#555").grid(row=0, column=0, columnspan=4, sticky="w")

        det = ttk.LabelFrame(f, text="Leitura do arquivo", padding=6)
        det.grid(row=1, column=0, columnspan=4, sticky="ew", pady=4)
        self.v_cod = tk.StringVar()
        self.v_del = tk.StringVar()
        self.v_lat = tk.StringVar()
        self.v_lon = tk.StringVar()
        ttk.Label(det, text="Codificação:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(det, textvariable=self.v_cod, values=CODIFICACOES, width=10).grid(row=0, column=1, padx=4)
        ttk.Label(det, text="Delimitador:").grid(row=0, column=2, sticky="w")
        ttk.Combobox(det, textvariable=self.v_del, values=list(DELIMITADORES), width=5).grid(row=0, column=3, padx=4)
        ttk.Label(det, text="Latitude:").grid(row=0, column=4, sticky="w")
        self.cb_lat = ttk.Combobox(det, textvariable=self.v_lat, width=16)
        self.cb_lat.grid(row=0, column=5, padx=4)
        ttk.Label(det, text="Longitude:").grid(row=0, column=6, sticky="w")
        self.cb_lon = ttk.Combobox(det, textvariable=self.v_lon, width=16)
        self.cb_lon.grid(row=0, column=7, padx=4)
        ttk.Button(det, text="Recarregar", command=self._recarregar).grid(row=0, column=8, padx=4)

        prev = ttk.LabelFrame(f, text="Prévia (primeiras linhas)", padding=4)
        prev.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=4)
        f.rowconfigure(2, weight=1)
        self.tree = ttk.Treeview(prev, show="headings", height=6)
        sx = ttk.Scrollbar(prev, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=sx.set)
        self.tree.pack(fill="both", expand=True)
        sx.pack(fill="x")

        baixo = ttk.Frame(f)
        baixo.grid(row=3, column=0, columnspan=4, sticky="nsew")
        f.rowconfigure(3, weight=2)
        for c in range(3):
            baixo.columnconfigure(c, weight=1)
        baixo.rowconfigure(0, weight=1)

        # Filtro
        fil = ttk.LabelFrame(baixo, text="Filtro", padding=6)
        fil.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.v_filtrar = tk.BooleanVar()
        self.v_fcol = tk.StringVar()
        ttk.Checkbutton(fil, text="Manter só os valores marcados da coluna:",
                        variable=self.v_filtrar).pack(anchor="w")
        self.cb_fcol = ttk.Combobox(fil, textvariable=self.v_fcol)
        self.cb_fcol.pack(fill="x")
        self.cb_fcol.bind("<<ComboboxSelected>>", lambda e: self._mostrar_valores())
        ttk.Button(fil, text="Ver valores encontrados", command=self._mostrar_valores).pack(anchor="w", pady=2)
        self.lb_valores = tk.Listbox(fil, selectmode="multiple", exportselection=False, height=8)
        self.lb_valores.pack(fill="both", expand=True)
        ttk.Label(fil, wraplength=260, foreground="#555",
                  text="Confira o código no dicionário de dados do IBGE. "
                       "CNEFE: COD_ESPECIE 1 = domicílio particular.").pack(anchor="w")

        # Colunas
        col = ttk.LabelFrame(baixo, text="Colunas na saída (além de Territorio)", padding=6)
        col.grid(row=0, column=1, sticky="nsew", padx=4)
        self.lb_colunas = tk.Listbox(col, selectmode="multiple", exportselection=False)
        self.lb_colunas.pack(fill="both", expand=True)
        ttk.Label(col, wraplength=260, foreground="#555",
                  text="Menos colunas = mais casas por mapa (limite de células do My Maps).").pack(anchor="w")

        # Nome
        nom = ttk.LabelFrame(baixo, text="Nome do ponto", padding=6)
        nom.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        self.v_nome_tipo = tk.StringVar(value="modelo")
        self.v_nome_col = tk.StringVar()
        self.v_nome_mod = tk.StringVar()
        ttk.Radiobutton(nom, text="Da coluna:", value="coluna", variable=self.v_nome_tipo).pack(anchor="w")
        self.cb_nome = ttk.Combobox(nom, textvariable=self.v_nome_col)
        self.cb_nome.pack(fill="x")
        ttk.Radiobutton(nom, text="Modelo:", value="modelo", variable=self.v_nome_tipo).pack(anchor="w", pady=(6, 0))
        ttk.Entry(nom, textvariable=self.v_nome_mod).pack(fill="x")
        ttk.Label(nom, wraplength=260, foreground="#555",
                  text="Use {COLUNA} para inserir valores e {n} para numerar. "
                       "Ex.: {NOM_SEGLOGR}, {NUM_ENDERECO}").pack(anchor="w")

        bot = ttk.Frame(f)
        bot.grid(row=4, column=0, columnspan=4, sticky="e", pady=(6, 0))
        ttk.Button(bot, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(bot, text="OK", command=self._confirmar).pack(side="right", padx=6)

    # ------------------------------------------------------------ lógica
    def _opcoes_tela(self) -> OpcoesCSV:
        return OpcoesCSV(self.v_cod.get() or None, DELIMITADORES.get(self.v_del.get(), self.v_del.get() or None),
                         self.v_lat.get() or None, self.v_lon.get() or None)

    def _recarregar(self, primeira=False):
        op = self.entrada.csv if primeira else self._opcoes_tela()
        if not primeira and self.info and op.delimitador != self.info.opcoes.delimitador:
            op.coluna_lat = op.coluna_lon = None   # colunas mudam com o delimitador
        try:
            self.info = inspecionar(self.entrada.caminho, op)
        except (ErroCSV, UnicodeDecodeError, OSError) as e:
            messagebox.showerror("Erro no CSV", f"{e}\n\nAjuste as opções de leitura e clique em Recarregar.",
                                 parent=self)
            return
        self._valores_cache.clear()
        o = self.info.opcoes
        self.v_cod.set(o.codificacao)
        self.v_del.set(_nome_delim(o.delimitador))
        self.v_lat.set(o.coluna_lat)
        self.v_lon.set(o.coluna_lon)
        cols = self.info.colunas
        for cb in (self.cb_lat, self.cb_lon, self.cb_fcol, self.cb_nome):
            cb["values"] = cols
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=110, stretch=False)
        self.tree.delete(*self.tree.get_children())
        for linha in self.info.amostra:
            self.tree.insert("", "end", values=[linha.get(c, "") for c in cols])

        if primeira:
            resolver_padroes(self.entrada, self.info)
        e = self.entrada
        self.v_filtrar.set(bool(e.filtro_coluna))
        self.v_fcol.set(e.filtro_coluna or "")
        self.lb_colunas.delete(0, "end")
        for i, c in enumerate(cols):
            self.lb_colunas.insert("end", c)
            if c in (e.colunas or []):
                self.lb_colunas.selection_set(i)
        if e.nome_coluna:
            self.v_nome_tipo.set("coluna")
            self.v_nome_col.set(e.nome_coluna)
        else:
            self.v_nome_tipo.set("modelo")
            self.v_nome_mod.set(e.nome_modelo or "")
        if e.filtro_coluna:
            self._mostrar_valores()

    def _mostrar_valores(self):
        col = self.v_fcol.get()
        if not col or self.info is None or col not in self.info.colunas:
            return
        if col not in self._valores_cache:
            self.config(cursor="watch")
            self.update_idletasks()
            try:
                self._valores_cache[col] = valores_distintos(self.entrada.caminho, self.info.opcoes, col)
            finally:
                self.config(cursor="")
        cont = self._valores_cache[col]
        marcados = set(self.entrada.filtro_valores) if col == self.entrada.filtro_coluna else set()
        self.lb_valores.delete(0, "end")
        self._valores_lista = sorted(cont, key=lambda v: (-cont[v], v))[:500]
        for i, v in enumerate(self._valores_lista):
            self.lb_valores.insert("end", f"{v or '(vazio)'}   ({num(cont[v])})")
            if v in marcados:
                self.lb_valores.selection_set(i)

    def _confirmar(self):
        if self.info is None:
            self.destroy()
            return
        e = self.entrada
        e.csv = self._opcoes_tela()
        if self.v_filtrar.get() and self.v_fcol.get():
            valores = [self._valores_lista[i] for i in self.lb_valores.curselection()] \
                if getattr(self, "_valores_lista", None) else []
            if not valores:
                messagebox.showwarning("Filtro", "Marque pelo menos um valor para manter, "
                                       "ou desligue o filtro.", parent=self)
                return
            e.filtro_coluna = self.v_fcol.get()
            e.filtro_valores = valores
        else:
            e.filtro_coluna = ""
            e.filtro_valores = []
        e.colunas = [self.lb_colunas.get(i) for i in self.lb_colunas.curselection()]
        if self.v_nome_tipo.get() == "coluna" and self.v_nome_col.get():
            e.nome_coluna, e.nome_modelo = self.v_nome_col.get(), None
        else:
            e.nome_coluna, e.nome_modelo = None, self.v_nome_mod.get() or "Ponto {n}"
        self.ok = True
        self.destroy()
