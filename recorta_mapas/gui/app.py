"""Janela principal (tkinter)."""

from __future__ import annotations

import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from ..config import (
    AGRUPAR_SEQUENCIAL, AGRUPAR_TERRITORIO, CAMADA_TERR_NAO, CAMADA_TERR_RESERVAR,
    CAMADA_TERR_SE_COUBER, MODO_CORTAR, MODO_INTEIRA, EntradaLinhas, EntradaPontos, Limites,
    OpcoesCSV, Opcoes,
)

TIPOS_KML = [("KML/KMZ", "*.kml *.kmz"), ("Todos os arquivos", "*.*")]
TIPOS_PONTOS = [("CSV, KML ou KMZ", "*.csv *.txt *.kml *.kmz"), ("Todos os arquivos", "*.*")]


def _eh_csv(caminho: str) -> bool:
    return os.path.splitext(caminho)[1].lower() in (".csv", ".txt", ".tsv")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Recorta Mapas - territórios rurais para o Google My Maps")
        self.geometry("880x660")
        self.minsize(760, 560)
        self.fila: queue.Queue = queue.Queue()
        self.pontos: list[EntradaPontos] = []
        self.linhas: list[str] = []
        self._montar()
        self.after(100, self._ler_fila)

    # ------------------------------------------------------------ montagem
    def _campo_arquivo(self, pai, linha, rotulo, var, tipos, pasta=False):
        ttk.Label(pai, text=rotulo).grid(row=linha, column=0, sticky="w", pady=3)
        ttk.Entry(pai, textvariable=var).grid(row=linha, column=1, sticky="ew", padx=4)

        def escolher():
            if pasta:
                c = filedialog.askdirectory(parent=self)
            else:
                c = filedialog.askopenfilename(parent=self, filetypes=tipos)
            if c:
                var.set(c)

        ttk.Button(pai, text="Escolher...", command=escolher).grid(row=linha, column=2)

    def _montar(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.nb = nb

        # ---- Entradas
        ent = ttk.Frame(nb, padding=8)
        nb.add(ent, text="Entradas")
        ent.columnconfigure(1, weight=1)
        self.v_mestre = tk.StringVar()
        self.v_terr = tk.StringVar()
        self.v_campo_id = tk.StringVar()
        self._campo_arquivo(ent, 0, "Mapa-mestre (limite da congregação):", self.v_mestre, TIPOS_KML)
        self._campo_arquivo(ent, 1, "Mapa de territórios rurais:", self.v_terr, TIPOS_KML)
        ttk.Label(ent, text="Campo de ID se o nome estiver vazio (opcional):").grid(row=2, column=0, sticky="w")
        ttk.Entry(ent, textvariable=self.v_campo_id, width=20).grid(row=2, column=1, sticky="w", padx=4)

        lf = ttk.LabelFrame(ent, text="Camadas de linhas (ex.: Trajetos dos recenseadores)", padding=6)
        lf.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=6)
        ent.rowconfigure(3, weight=1)
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.lb_linhas = tk.Listbox(lf, height=4)
        self.lb_linhas.grid(row=0, column=0, rowspan=3, sticky="nsew")
        ttk.Button(lf, text="Adicionar...", command=self._add_linhas).grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Button(lf, text="Remover", command=self._rem_linhas).grid(row=1, column=1, padx=4, sticky="ew")
        self.v_pref_linhas = tk.StringVar(value="Trajetos")
        ttk.Label(lf, text="Nome base dos arquivos:").grid(row=3, column=0, sticky="w")
        ttk.Entry(lf, textvariable=self.v_pref_linhas, width=24).grid(row=4, column=0, sticky="w")

        pf = ttk.LabelFrame(ent, text="Pontos (ex.: CSV do CNEFE 2022 ou KML/KMZ de casas)", padding=6)
        pf.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=6)
        ent.rowconfigure(4, weight=1)
        pf.columnconfigure(0, weight=1)
        pf.rowconfigure(0, weight=1)
        self.lb_pontos = tk.Listbox(pf, height=4)
        self.lb_pontos.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.lb_pontos.bind("<Double-Button-1>", lambda e: self._config_csv())
        ttk.Button(pf, text="Adicionar...", command=self._add_pontos).grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Button(pf, text="Configurar CSV...", command=self._config_csv).grid(row=1, column=1, padx=4, sticky="ew")
        ttk.Button(pf, text="Remover", command=self._rem_pontos).grid(row=2, column=1, padx=4, sticky="ew")
        self.v_pref_pontos = tk.StringVar(value="Casas_rurais")
        ttk.Label(pf, text="Nome base dos arquivos:").grid(row=3, column=0, sticky="w")
        ttk.Entry(pf, textvariable=self.v_pref_pontos, width=24).grid(row=4, column=0, sticky="w")

        # ---- Opções
        opc = ttk.Frame(nb, padding=8)
        nb.add(opc, text="Opções")
        opc.columnconfigure(0, weight=1)
        opc.columnconfigure(1, weight=1)

        e1 = ttk.LabelFrame(opc, text="Etapa 1 - ajuste ao mapa-mestre", padding=6)
        e1.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)
        self.v_limiar = tk.StringVar(value="2")
        ttk.Label(e1, text="Alertar se o território perder mais de (%):").grid(row=0, column=0, sticky="w")
        ttk.Entry(e1, textvariable=self.v_limiar, width=8).grid(row=0, column=1, padx=4)

        e2 = ttk.LabelFrame(opc, text="Etapa 2 - linhas", padding=6)
        e2.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=4)
        self.v_modo = tk.StringVar(value=MODO_CORTAR)
        ttk.Radiobutton(e2, text="Cortar na borda", value=MODO_CORTAR, variable=self.v_modo).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(e2, text="Manter feição inteira se tocar", value=MODO_INTEIRA,
                        variable=self.v_modo).grid(row=1, column=0, sticky="w")
        self.v_simpl = tk.StringVar(value="0")
        ttk.Label(e2, text="Simplificar trajetos (metros, 0 = não):").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(e2, textvariable=self.v_simpl, width=8).grid(row=2, column=1, padx=4, pady=(6, 0))

        dv = ttk.LabelFrame(opc, text="Divisão em arquivos e mapas", padding=6)
        dv.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=4)
        self.v_agr = tk.StringVar(value=AGRUPAR_TERRITORIO)
        ttk.Radiobutton(dv, text="Territórios inteiros por arquivo (quando couberem)",
                        value=AGRUPAR_TERRITORIO, variable=self.v_agr).pack(anchor="w")
        ttk.Radiobutton(dv, text="Blocos sequenciais (enche cada arquivo ao máximo)",
                        value=AGRUPAR_SEQUENCIAL, variable=self.v_agr).pack(anchor="w")
        ttk.Label(dv, text="Contornos dos territórios em cada mapa:").pack(anchor="w", pady=(8, 0))
        self.v_cam_terr = tk.StringVar(value=CAMADA_TERR_RESERVAR)
        for txt, val in (("Sempre (reservar espaço em cada mapa)", CAMADA_TERR_RESERVAR),
                         ("Só onde sobrar espaço", CAMADA_TERR_SE_COUBER),
                         ("Não incluir (só na pasta principal)", CAMADA_TERR_NAO)):
            ttk.Radiobutton(dv, text=txt, value=val, variable=self.v_cam_terr).pack(anchor="w")
        ttk.Label(dv, text="Formato de saída:").pack(anchor="w", pady=(8, 0))
        self.v_formato = tk.StringVar(value="kml")
        fr = ttk.Frame(dv)
        fr.pack(anchor="w")
        ttk.Radiobutton(fr, text="KML", value="kml", variable=self.v_formato).pack(side="left")
        ttk.Radiobutton(fr, text="KMZ", value="kmz", variable=self.v_formato).pack(side="left", padx=8)

        lm = ttk.LabelFrame(opc, text="Limites do Google My Maps (com margem)", padding=6)
        lm.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=4)
        lim = Limites()
        self.v_lim = {}
        for i, (chave, rot, val) in enumerate((
                ("max_feicoes_arquivo", "Feições por arquivo", lim.max_feicoes_arquivo),
                ("max_mb_arquivo", "MB por arquivo (KML sem compressão)", lim.max_bytes_arquivo / 1e6),
                ("max_camadas_mapa", "Camadas por mapa", lim.max_camadas_mapa),
                ("max_feicoes_mapa", "Feições por mapa", lim.max_feicoes_mapa),
                ("max_vertices_mapa", "Vértices por mapa", lim.max_vertices_mapa),
                ("max_celulas_mapa", "Células da tabela por mapa", lim.max_celulas_mapa))):
            ttk.Label(lm, text=rot + ":").grid(row=i, column=0, sticky="w")
            v = tk.StringVar(value=f"{val:g}")
            ttk.Entry(lm, textvariable=v, width=10).grid(row=i, column=1, padx=4, pady=1)
            self.v_lim[chave] = v

        # ---- Relatório
        rel = ttk.Frame(nb, padding=4)
        nb.add(rel, text="Relatório")
        self.txt = scrolledtext.ScrolledText(rel, wrap="none", font=("Consolas", 9))
        self.txt.pack(fill="both", expand=True)

        # ---- Rodapé
        rod = ttk.Frame(self, padding=(8, 0, 8, 8))
        rod.pack(fill="x")
        rod.columnconfigure(1, weight=1)
        self.v_saida = tk.StringVar()
        self._campo_arquivo(rod, 0, "Pasta de saída:", self.v_saida, None, pasta=True)
        self.bt = ttk.Button(rod, text="Processar", command=self._processar)
        self.bt.grid(row=1, column=2, pady=(6, 0), sticky="e")
        self.v_status = tk.StringVar(value="Escolha os arquivos e clique em Processar.")
        ttk.Label(rod, textvariable=self.v_status).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.prog = ttk.Progressbar(rod, mode="indeterminate")
        self.prog.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))

    # ------------------------------------------------------------ listas
    def _add_linhas(self):
        for c in filedialog.askopenfilenames(parent=self, filetypes=TIPOS_KML):
            self.linhas.append(c)
            self.lb_linhas.insert("end", c)

    def _rem_linhas(self):
        for i in reversed(self.lb_linhas.curselection()):
            self.lb_linhas.delete(i)
            del self.linhas[i]

    def _rotulo_pontos(self, e: EntradaPontos) -> str:
        if not _eh_csv(e.caminho):
            return e.caminho
        filtro = f"{e.filtro_coluna} = {', '.join(e.filtro_valores)}" if e.filtro_coluna else "sem filtro"
        return f"{e.caminho}   [{filtro}]"

    def _add_pontos(self):
        for c in filedialog.askopenfilenames(parent=self, filetypes=TIPOS_PONTOS):
            e = EntradaPontos(c, csv=OpcoesCSV() if _eh_csv(c) else None)
            self.pontos.append(e)
            self.lb_pontos.insert("end", c)
            if _eh_csv(c):
                self.lb_pontos.selection_clear(0, "end")
                self.lb_pontos.selection_set("end")
                self._config_csv()

    def _config_csv(self):
        sel = self.lb_pontos.curselection()
        if not sel:
            messagebox.showinfo("Pontos", "Selecione um CSV na lista.", parent=self)
            return
        i = sel[0]
        e = self.pontos[i]
        if not _eh_csv(e.caminho):
            messagebox.showinfo("Pontos", "Este arquivo é KML/KMZ: não há o que configurar.", parent=self)
            return
        from .dialogos import DialogoCSV
        d = DialogoCSV(self, e)
        self.wait_window(d)
        self.lb_pontos.delete(i)
        self.lb_pontos.insert(i, self._rotulo_pontos(e))

    def _rem_pontos(self):
        for i in reversed(self.lb_pontos.curselection()):
            self.lb_pontos.delete(i)
            del self.pontos[i]

    # ------------------------------------------------------------ execução
    def _numero(self, var, nome) -> float:
        try:
            return float(var.get().replace(",", "."))
        except ValueError:
            raise ValueError(f"Valor inválido em \"{nome}\": {var.get()}")

    def _opcoes(self) -> Opcoes:
        if not self.v_mestre.get() or not self.v_terr.get():
            raise ValueError("Escolha o mapa-mestre e o mapa de territórios rurais.")
        if not self.v_saida.get():
            raise ValueError("Escolha a pasta de saída.")
        l = {k: self._numero(v, k) for k, v in self.v_lim.items()}
        lim = Limites(int(l["max_feicoes_arquivo"]), int(l["max_mb_arquivo"] * 1e6), int(l["max_camadas_mapa"]),
                      int(l["max_feicoes_mapa"]), int(l["max_vertices_mapa"]), int(l["max_celulas_mapa"]))
        pref_p = self.v_pref_pontos.get().strip() or "Casas_rurais"
        for e in self.pontos:
            e.prefixo = pref_p
        return Opcoes(
            mapa_mestre=self.v_mestre.get(), territorios=self.v_terr.get(), saida=self.v_saida.get(),
            linhas=[EntradaLinhas(c, self.v_pref_linhas.get().strip() or "Trajetos") for c in self.linhas],
            pontos=[EntradaPontos(**vars(e)) for e in self.pontos],
            campo_id=self.v_campo_id.get().strip() or None,
            limiar_perda_pct=self._numero(self.v_limiar, "limiar de perda"),
            modo_linhas=self.v_modo.get(), simplificar_m=self._numero(self.v_simpl, "simplificar"),
            formato=self.v_formato.get(), agrupamento=self.v_agr.get(),
            camada_territorios=self.v_cam_terr.get(), limites=lim,
        )

    def _processar(self):
        try:
            op = self._opcoes()
        except ValueError as e:
            messagebox.showwarning("Recorta Mapas", str(e), parent=self)
            return
        self.bt.state(["disabled"])
        self.prog.start(12)
        self.txt.delete("1.0", "end")

        def trabalho():
            from ..pipeline import executar
            try:
                r = executar(op, progresso=lambda m: self.fila.put(("status", m)))
                self.fila.put(("fim", r))
            except Exception as e:
                self.fila.put(("erro", (e, traceback.format_exc())))

        threading.Thread(target=trabalho, daemon=True).start()

    def _ler_fila(self):
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "status":
                    self.v_status.set(valor)
                elif tipo == "fim":
                    self._terminar()
                    self.txt.insert("1.0", valor.relatorio)
                    self.nb.select(2)
                    n_arq = sum(len(m.arquivos) for m in valor.plano.mapas)
                    self.v_status.set(f"Concluído: {len(valor.plano.mapas)} mapa(s), {n_arq} arquivo(s) em "
                                      f"{valor.pasta_saida}")
                elif tipo == "erro":
                    self._terminar()
                    e, tb = valor
                    self.txt.insert("1.0", f"ERRO: {e}\n\nDetalhes técnicos:\n{tb}")
                    self.nb.select(2)
                    self.v_status.set("Erro no processamento.")
                    messagebox.showerror("Recorta Mapas", f"Erro: {e}", parent=self)
        except queue.Empty:
            pass
        self.after(100, self._ler_fila)

    def _terminar(self):
        self.prog.stop()
        self.bt.state(["!disabled"])


def main():
    App().mainloop()
