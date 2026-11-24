"""Point d'entrée de l'exécutable « SecureID Vérification »."""

from core.crashlog import install

install("SecureID Vérification")  # avant tout import lourd : une bibliothèque manquante sera signalée

from apps.verifier.main import main  # noqa: E402

if __name__ == "__main__":
    main()
