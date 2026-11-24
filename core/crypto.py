"""Gestion des clés Ed25519 : génération, sauvegarde chiffrée, signature, vérification."""

from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_keypair(kid: str, password: str, keys_dir: str | Path = "keys") -> tuple[Path, Path]:
    """Crée une paire de clés et l'enregistre dans keys_dir.

    La clé privée est chiffrée avec le mot de passe (PKCS#8).
    Retourne les chemins (clé privée, clé publique).
    """
    if len(password) < 12:
        raise ValueError("Le mot de passe doit contenir au moins 12 caractères.")

    keys_dir = Path(keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    priv_path = keys_dir / f"{kid}_private.pem"
    pub_path = keys_dir / f"{kid}_public.pem"
    if priv_path.exists():
        raise FileExistsError(f"Une clé existe déjà pour kid={kid!r}.")

    private_key = Ed25519PrivateKey.generate()
    priv_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
        )
    )
    pub_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return priv_path, pub_path


def load_private_key(path: str | Path, password: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=password.encode())
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("La clé chargée n'est pas une clé Ed25519.")
    return key


def load_public_key(path: str | Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("La clé chargée n'est pas une clé Ed25519.")
    return key


def sign(private_key: Ed25519PrivateKey, data: bytes) -> bytes:
    """Retourne une signature de 64 octets."""
    return private_key.sign(data)


def verify(public_key: Ed25519PublicKey, signature: bytes, data: bytes) -> bool:
    try:
        public_key.verify(signature, data)
        return True
    except InvalidSignature:
        return False
