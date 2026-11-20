"""Optional native file drag-and-drop support for Tkinter apps."""
from __future__ import annotations
import importlib, os, subprocess, sys, tkinter as tk

def _load_tkdnd():
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
        return DND_FILES, TkinterDnD
    except ImportError:
        if os.environ.get("APP_DISABLE_DND_INSTALL") == "1": return None, None
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "tkinterdnd2"], check=True, capture_output=True, text=True, timeout=120)
            importlib.invalidate_caches()
            from tkinterdnd2 import DND_FILES, TkinterDnD
            return DND_FILES, TkinterDnD
        except Exception: return None, None
DND_FILES, _TK_DND = _load_tkdnd()
DND_AVAILABLE = _TK_DND is not None
DropAwareTk = _TK_DND.Tk if DND_AVAILABLE else tk.Tk

def register_file_drop(widget, callback) -> bool:
    if not DND_AVAILABLE: return False
    widget.drop_target_register(DND_FILES)
    widget.dnd_bind("<<DropEnter>>", lambda _e: "copy")
    widget.dnd_bind("<<DropPosition>>", lambda _e: "copy")
    widget.dnd_bind("<<DropLeave>>", lambda _e: None)
    def _drop(event):
        callback(tuple(str(x) for x in widget.tk.splitlist(event.data)))
        return getattr(event, "action", "copy") or "copy"
    widget.dnd_bind("<<Drop>>", _drop)
    return True
