"""Point d'entrée de l'exécutable « SecureID Émission »."""

from core.crashlog import install

install("SecureID Émission")  # avant tout import lourd : une bibliothèque manquante sera signalée

from apps.issuer.main import main  # noqa: E402

if __name__ == "__main__":
    main()
