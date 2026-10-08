"""Tema escuro no estilo do Dicta: ttk "clam", formas arredondadas desenhadas uma vez
(cantos com antisserrilhado, miolo largo que o Tk repete poucas vezes), chaves estilo
celular e "chips". Nada de pacotes extras.

Base copiada do projeto Dicta (apply_dark_theme, _shape_image, dark_title_bar)."""

from __future__ import annotations

import math
import sys
import tkinter as tk
from tkinter import ttk

IS_WINDOWS = sys.platform.startswith("win")

THEME = {
    "bg": "#0f1115",        # window
    "side": "#0b0d10",      # sidebar
    "card": "#171a21",      # panels
    "field": "#1f232c",     # inputs
    "hover": "#262b36",
    "border": "#2a2f3a",
    "text": "#e6e8ec",
    "muted": "#8b93a1",
    "accent": "#6d7cff",
    "accent_hover": "#8391ff",
    "danger": "#f87171",
    "warn": "#fbbf24",
}
FONT = "Segoe UI" if IS_WINDOWS else "DejaVu Sans"

def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _shape_image(root, w: int, h: int, r: float, fill: str, outer: str,
                 border: str | None = None, knob: tuple[float, float, str] | None = None):
    """A rounded rectangle (optionally with a 1px border and a round knob),
    anti-aliased against the colour behind it, built with one put().

    Only pixels near a curved edge are computed: every straight-edge row and
    column repeats, so a large shape costs about as much as a small one."""
    o, f = _rgb(outer), _rgb(fill)
    b = _rgb(border) if border else f
    k = _rgb(knob[2]) if knob else None

    def sdf(px, py, inset):
        """Signed distance from the rounded rectangle's edge (< 0 inside)."""
        rr = max(r - inset, 0.0)
        hx, hy = w / 2 - inset - rr, h / 2 - inset - rr
        qx, qy = abs(px - w / 2) - hx, abs(py - h / 2) - hy
        out = math.hypot(max(qx, 0.0), max(qy, 0.0))
        return out + min(max(qx, qy), 0.0) - rr

    def pixel(x, y):
        px, py = x + 0.5, y + 0.5
        a_out = min(max(0.5 - sdf(px, py, 0), 0.0), 1.0)
        a_in = min(max(0.5 - sdf(px, py, 1), 0.0), 1.0) if border else a_out
        col = [o[i] * (1 - a_out) + b[i] * (a_out - a_in) + f[i] * a_in for i in range(3)]
        if knob:
            a_k = min(max(0.5 - (math.hypot(px - knob[0], py - h / 2) - knob[1]), 0.0), 1.0)
            col = [col[i] * (1 - a_k) + k[i] * a_k for i in range(3)]
        return "#%02x%02x%02x" % tuple(int(round(v)) for v in col)

    edge = int(r) + 2
    if knob or w <= 2 * edge + 1:
        cols = range(w)  # small shapes (switches): just compute everything
        build = lambda y: " ".join(pixel(x, y) for x in cols)
    else:
        def build(y):
            # The shape is symmetric: compute the left edge, mirror it right.
            left = [pixel(x, y) for x in range(edge)]
            return " ".join(left + [pixel(edge, y)] * (w - 2 * edge) + left[::-1])
    if knob:
        rows = ["{" + build(y) + "}" for y in range(h)]
    else:
        top = ["{" + build(y) + "}" for y in range(edge)]
        flat = "{" + build(edge) + "}"  # every row between the corners is the same
        rows = top + [flat] * (h - 2 * edge) + top[::-1]
    img = tk.PhotoImage(master=root, width=w, height=h)
    img.put(" ".join(rows))
    return img


def _forma_em_cache(root, name, args, kw):
    """_shape_image com cache em PNG na pasta de dados: só a primeira abertura do
    programa desenha as formas (~150 ms); as seguintes só carregam os arquivos."""
    import hashlib

    from ..preferencias import pasta_dados

    chave = hashlib.sha1(repr((name, args, sorted(kw.items()), sorted(THEME.items()))).encode()).hexdigest()[:16]
    arquivo = pasta_dados() / "tema" / f"{chave}.png"
    try:
        if arquivo.exists():
            return tk.PhotoImage(master=root, file=str(arquivo))
    except tk.TclError:
        pass
    img = _shape_image(root, *args, **kw)
    try:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = arquivo.with_suffix(".tmp")
        img.write(str(tmp), format="png")
        tmp.replace(arquivo)
    except (OSError, tk.TclError):
        pass   # sem cache: só fica um pouco mais lento
    return img


def apply_dark_theme(root) -> None:
    t = THEME
    style = ttk.Style(root)
    style.theme_use("clam")
    images = root._dicta_images = {}  # Tk drops images nobody references

    def shape(name, *args, **kw):
        images[name] = _forma_em_cache(root, name, args, kw)
        return images[name]

    def rounded_element(element, fill, outer, states=(), r=8, border=None, size=None):
        """A stretchable rounded background: corners stay fixed, middle stretches."""
        side = size or 2 * r + 2 + 48  # a wide middle: Tk repeats it, so few repeats
        base = shape(element, side, side, r, fill, outer, border)
        specs = [(state, shape(f"{element}:{state}", side, side, r, f2, outer, b2))
                 for state, f2, b2 in states]
        # width/height: the minimum size is the corners, not the whole image
        style.element_create(element, "image", base, *specs, border=r + 1, sticky="nsew",
                             width=2 * r + 2, height=2 * r + 2)

    style.configure(".", background=t["bg"], foreground=t["text"], fieldbackground=t["field"],
                    bordercolor=t["border"], lightcolor=t["border"], darkcolor=t["border"],
                    troughcolor=t["card"], focuscolor=t["accent"], selectbackground=t["accent"],
                    selectforeground="white", insertcolor=t["text"], font=(FONT, 10))
    style.configure("TFrame", background=t["bg"])
    style.configure("Side.TFrame", background=t["side"])
    style.configure("Card.TFrame", background=t["card"])
    rounded_element("Dicta.panel", t["card"], t["bg"], r=14)
    style.layout("Panel.TFrame", [("Dicta.panel", {"sticky": "nswe"})])
    style.configure("Panel.TFrame", background=t["card"])

    style.configure("TLabel", background=t["bg"], foreground=t["text"])
    style.configure("Card.TLabel", background=t["card"])
    style.configure("Muted.Card.TLabel", background=t["card"], foreground=t["muted"], font=(FONT, 9))
    style.configure("Head.Card.TLabel", background=t["card"], font=(FONT, 13, "bold"))
    style.configure("Brand.TLabel", background=t["side"], font=(FONT, 15, "bold"))
    style.configure("SideMuted.TLabel", background=t["side"], foreground=t["muted"], font=(FONT, 9))
    style.configure("Msg.TLabel", background=t["card"], font=(FONT, 9))

    # Buttons: rounded pills on the card, with hover / pressed / disabled looks.
    for name, fill, hover, fg, outer in (
            ("TButton", t["field"], t["hover"], t["text"], t["card"]),
            ("Accent.TButton", t["accent"], t["accent_hover"], "white", t["card"]),
            ("Ghost.TButton", t["card"], t["hover"], t["text"], t["card"]),
            ("Danger.TButton", t["card"], t["hover"], t["danger"], t["card"])):
        element = f"Dicta.{name}.bg"
        rounded_element(element, fill, outer, states=(
            ("disabled", t["field"] if name != "Accent.TButton" else t["hover"], None),
            ("pressed", hover, None), ("active", hover, None)))
        style.layout(name, [(element, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [
                ("Button.label", {"sticky": "nswe"})]})]})])
        style.configure(name, foreground=fg, padding=(14, 7), anchor="center")
        style.map(name, foreground=[("disabled", t["muted"])])

    # Sidebar items: a rounded highlight on the selected / hovered page.
    rounded_element("Dicta.nav", t["side"], t["side"], states=(("active", t["field"], None),))
    rounded_element("Dicta.navon", t["card"], t["side"])
    for name, element, fg in (("Nav.TButton", "Dicta.nav", t["muted"]),
                              ("NavOn.TButton", "Dicta.navon", t["text"])):
        style.layout(name, [(element, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [
                ("Button.label", {"sticky": "w"})]})]})])
        style.configure(name, foreground=fg, padding=(14, 8), anchor="w")
        style.map(name, foreground=[("active", t["text"])])

    # Text fields and drop-downs: rounded, with an accent ring when focused.
    rounded_element("Dicta.field", t["field"], t["card"], border=t["border"],
                    states=(("focus", t["field"], t["accent"]),
                            ("disabled", t["card"], t["border"])))
    style.layout("TEntry", [("Dicta.field", {"sticky": "nswe", "children": [
        ("Entry.padding", {"sticky": "nswe", "children": [
            ("Entry.textarea", {"sticky": "nswe"})]})]})])
    style.configure("TEntry", foreground=t["text"], padding=(10, 6))
    style.layout("TCombobox", [("Dicta.field", {"sticky": "nswe", "children": [
        ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
        ("Combobox.padding", {"expand": "1", "sticky": "nswe", "children": [
            ("Combobox.textarea", {"sticky": "nswe"})]})]})])
    style.configure("TCombobox", foreground=t["text"], padding=(10, 5, 4, 5),
                    background=t["field"], arrowcolor=t["muted"], arrowsize=12,
                    bordercolor=t["field"], lightcolor=t["field"], darkcolor=t["field"])
    style.map("TCombobox", foreground=[("disabled", t["muted"])],
              background=[("disabled", t["card"]), ("active", t["field"])],
              bordercolor=[("disabled", t["card"])], lightcolor=[("disabled", t["card"])],
              darkcolor=[("disabled", t["card"])],
              selectbackground=[("readonly", t["field"])], selectforeground=[("readonly", t["text"])],
              arrowcolor=[("disabled", t["border"])])
    root.option_add("*TCombobox*Listbox.background", t["field"])
    root.option_add("*TCombobox*Listbox.foreground", t["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    # Phone-style switches: label on the left, switch on the right.
    w, h = 38, 22
    off = shape("switch:off", w, h, h / 2, t["border"], t["card"], knob=(h / 2, 8, "#c9ced6"))
    on = shape("switch:on", w, h, h / 2, t["accent"], t["card"], knob=(w - h / 2, 8, "#ffffff"))
    dis = shape("switch:dis", w, h, h / 2, t["field"], t["card"], knob=(h / 2, 8, t["border"]))
    dis_on = shape("switch:dis_on", w, h, h / 2, t["hover"], t["card"], knob=(w - h / 2, 8, t["muted"]))
    style.element_create("Dicta.switch", "image", off, ("disabled", "selected", dis_on),
                         ("disabled", dis), ("selected", on), sticky="e")
    style.layout("Switch.TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("Dicta.switch", {"side": "right", "sticky": "e"}),
        ("Checkbutton.label", {"side": "left", "sticky": "w"})]})])
    style.configure("Switch.TCheckbutton", background=t["card"], foreground=t["text"], padding=(0, 4))
    style.map("Switch.TCheckbutton", background=[("active", t["card"])],
              foreground=[("disabled", t["muted"])])

    # Language chips: rounded toggle pills that fill with the accent when on.
    rounded_element("Dicta.chip", t["field"], t["card"], r=17, size=36 + 48,
                    states=(("selected", t["accent"], None), ("active", t["hover"], None)))
    style.layout("Chip.TCheckbutton", [("Dicta.chip", {"sticky": "nswe", "children": [
        ("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("Checkbutton.label", {"sticky": "nswe"})]})]})])
    style.configure("Chip.TCheckbutton", background=t["card"], foreground=t["text"],
                    padding=(20, 0), font=(FONT, 10))
    style.map("Chip.TCheckbutton", foreground=[("selected", "white")],
              background=[("active", t["card"])])


def dark_title_bar(win) -> None:
    """Ask Windows 10/11 for a dark title bar on this window."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except Exception:
        pass




def aplicar_tema(root) -> None:
    """Tema do Dicta + o que o Recorta Mapas usa a mais."""
    apply_dark_theme(root)
    t = THEME
    style = ttk.Style(root)
    imagens = root._dicta_images

    # Escolha única em "chips" (mesmo visual dos chips de idioma do Dicta).
    style.layout("Chip.TRadiobutton", [("Dicta.chip", {"sticky": "nswe", "children": [
        ("Radiobutton.padding", {"sticky": "nswe", "children": [
            ("Radiobutton.label", {"sticky": "nswe"})]})]})])
    style.configure("Chip.TRadiobutton", background=t["card"], foreground=t["text"],
                    padding=(16, 0), font=(FONT, 10))
    style.map("Chip.TRadiobutton", foreground=[("selected", "white")],
              background=[("active", t["card"])])
    style.configure("Chip.TCheckbutton", padding=(14, 0))

    # Chips menores (colunas do CSV): mesmo desenho, raio e fonte menores.
    lado = 26 + 48
    base = imagens["Dicta.mini"] = _forma_em_cache(root, "Dicta.mini", (lado, lado, 12, t["field"], t["card"]), {})
    est = [(st, _forma_em_cache(root, f"Dicta.mini:{st}", (lado, lado, 12, cor, t["card"]), {}))
           for st, cor in (("selected", t["accent"]), ("active", t["hover"]))]
    for st, img in est:
        imagens[f"Dicta.mini:{st}"] = img
    style.element_create("Dicta.mini", "image", base, *est, border=13, sticky="nsew", width=26, height=26)
    style.layout("Mini.TCheckbutton", [("Dicta.mini", {"sticky": "nswe", "children": [
        ("Checkbutton.padding", {"sticky": "nswe", "children": [
            ("Checkbutton.label", {"sticky": "nswe"})]})]})])
    style.configure("Mini.TCheckbutton", background=t["card"], foreground=t["text"],
                    padding=(10, 3), font=(FONT, 9))
    style.map("Mini.TCheckbutton", foreground=[("selected", "white")], background=[("active", t["card"])])

    style.configure("Title.Card.TLabel", background=t["card"], font=(FONT, 20, "bold"))
    style.configure("Field.Card.TLabel", background=t["card"], foreground=t["muted"])
    style.configure("Path.Card.TLabel", background=t["card"], foreground=t["text"])
    style.configure("Empty.Card.TLabel", background=t["card"], foreground=t["muted"],
                    font=(FONT, 10, "italic"))
    style.configure("Ok.Card.TLabel", background=t["card"], foreground="#4ade80")
    style.configure("Warn.Card.TLabel", background=t["card"], foreground=t["warn"])
    style.configure("Danger.Card.TLabel", background=t["card"], foreground=t["danger"])

    # Barras de rolagem finas e escuras.
    for orient in ("Vertical", "Horizontal"):
        nome = f"{orient}.TScrollbar"
        style.configure(nome, background=t["field"], troughcolor=t["card"], bordercolor=t["card"],
                        lightcolor=t["field"], darkcolor=t["field"], arrowcolor=t["muted"],
                        gripcount=0, arrowsize=12)
        style.map(nome, background=[("active", t["hover"])])


def caixa_texto(pai, **kw) -> tk.Text:
    """Área de texto escura (relatório)."""
    t = THEME
    return tk.Text(pai, background=t["field"], foreground=t["text"], insertbackground=t["text"],
                   selectbackground=t["accent"], selectforeground="white", relief="flat",
                   borderwidth=0, highlightthickness=0, padx=12, pady=10,
                   font=("Consolas" if IS_WINDOWS else "DejaVu Sans Mono", 9), **kw)
