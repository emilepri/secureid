"""Jeton SID1 : payload canonique signé, placé dans le QR code de la carte.

Format : SID1.<payload en base64url>.<signature en base64url>
"""

import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import date

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from core import crypto

PREFIX = "SID1"
VERSION = 1
REQUIRED_FIELDS = {"kid", "id", "nom", "prenom", "naiss", "role", "etab", "emis", "exp", "ph"}

# Statuts renvoyés au vérificateur
AUTHENTIQUE = "AUTHENTIQUE"
FALSIFIEE = "FALSIFIEE"
EXPIREE = "EXPIREE"
INVALIDE = "INVALIDE"  # QR illisible ou format inconnu


@dataclass
class VerificationResult:
    status: str
    reason: str
    payload: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == AUTHENTIQUE


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def canonical(payload: dict) -> bytes:
    """Sérialisation stable : mêmes données -> mêmes octets -> même signature."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def encode_token(data: dict, private_key: Ed25519PrivateKey) -> str:
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        raise ValueError(f"Champs manquants : {sorted(missing)}")
    payload = {"v": VERSION, **data}
    body = canonical(payload)
    signature = crypto.sign(private_key, body)
    return f"{PREFIX}.{_b64e(body)}.{_b64e(signature)}"


def verify_token(
    token: str,
    public_keys: dict[str, Ed25519PublicKey],
    today: date | None = None,
) -> VerificationResult:
    """Vérifie un jeton lu dans un QR. public_keys associe kid -> clé publique."""
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        return VerificationResult(INVALIDE, "Format de QR non reconnu.")

    try:
        body = _b64d(parts[1])
        signature = _b64d(parts[2])
        payload = json.loads(body)
    except (binascii.Error, ValueError):
        return VerificationResult(INVALIDE, "QR illisible ou corrompu.")

    if not isinstance(payload, dict):
        return VerificationResult(INVALIDE, "Contenu du QR inattendu.")

    key = public_keys.get(payload.get("kid"))
    if key is None:
        return VerificationResult(FALSIFIEE, "Clé de signature inconnue.", payload)

    if not crypto.verify(key, signature, body):
        return VerificationResult(FALSIFIEE, "Signature invalide : données modifiées ou fausse carte.", payload)

    try:
        expiry = date.fromisoformat(payload["exp"])
    except (KeyError, TypeError, ValueError):
        return VerificationResult(INVALIDE, "Date d'expiration absente ou invalide.", payload)

    if (today or date.today()) > expiry:
        return VerificationResult(EXPIREE, f"Carte expirée depuis le {expiry.isoformat()}.", payload)

    return VerificationResult(AUTHENTIQUE, "Signature valide.", payload)
