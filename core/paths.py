"""Emplacement des données de SecureID.

- En développement (python -m ...) : le dossier courant, c'est-à-dire la racine du projet.
- En exécutable (.exe PyInstaller) : %USERPROFILE%\\SecureID, partagé par les deux applications.
- La variable d'environnement SECUREID_HOME permet d'imposer un autre dossier.
"""

import os
import sys
from pathlib import Path


def base_dir() -> Path:
    if os.environ.get("SECUREID_HOME"):
        return Path(os.environ["SECUREID_HOME"])
    if getattr(sys, "frozen", False):
        return Path.home() / "SecureID"
    return Path.cwd()


BASE = base_dir()
KEYS_DIR = BASE / "keys"
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "sortie"
TRUST_DIR = BASE / "verif"
PHOTOS_DIR = DATA_DIR / "photos"

# Fichiers fournis avec l'application (icônes) : dans l'exécutable, PyInstaller les place dans sys._MEIPASS
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
