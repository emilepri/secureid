"""Rend visibles les erreurs de démarrage de la version installée (.exe sans console).

- Toute exception non gérée est écrite dans %USERPROFILE%\\SecureID\\secureid.log
  et affichée dans une fenêtre Windows (même si Qt n'a pas pu démarrer).
- Un plantage natif (DLL, Qt) est aussi tracé grâce à faulthandler.
Ce module n'importe rien de lourd : il doit fonctionner même si une bibliothèque manque.
"""

import datetime
import faulthandler
import os
import platform
import sys
import traceback
from pathlib import Path


def _log_path() -> Path:
    base = Path(os.environ.get("SECUREID_HOME") or (Path.home() / "SecureID"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "secureid.log"


def _message_box(title: str, text: str) -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)  # icône d'erreur
            return
        except Exception:
            pass
    print(f"{title}\n{text}", file=sys.stderr)


def install(app_name: str) -> Path:
    path = _log_path()
    log = open(path, "a", encoding="utf-8", buffering=1)
    log.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} · {app_name} · Python {platform.python_version()}"
              f" · {platform.platform()} · exe={getattr(sys, 'frozen', False)}\n")
    faulthandler.enable(log)  # plantages natifs
    if sys.stderr is None:  # exécutable sans console : on redirige vers le journal
        sys.stderr = log
    if sys.stdout is None:
        sys.stdout = log

    def hook(exc_type, exc, tb):
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        log.write(detail)
        log.flush()
        _message_box(f"{app_name} n'a pas pu démarrer",
                     f"{exc_type.__name__} : {exc}\n\nLe détail est enregistré dans :\n{path}\n\n"
                     "Envoie ce fichier pour obtenir de l'aide.")

    sys.excepthook = hook
    return path
